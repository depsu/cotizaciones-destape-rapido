// Contratos C1 del rediseño dixdybot (oct-2026, fase 2-C1).
// Por qué existe: dixdybot va a PROYECTAR y OPERAR este buzón (lista, hilos, responder con
// IA). Para eso necesita (a) leer sin efectos secundarios, (b) un cursor de cambios que no
// pierda filas ni borrados, (c) revisiones para no pisar el trabajo del otro redactor (la
// ronda-correo) y (d) idempotencia para que un reintento jamás duplique un envío.
// Todo es ADITIVO: las rutas y formas viejas (panel.html, ronda-correo) no cambian.
// Detalle del contrato: DIXDY/clientes/destaperapido/mejoras-destaperapido/rediseno-2026-10/
// 02-plan/contrato-correo-worker.md

// Milisegundos UNIX calculados por SQLite (D1). Se usa el reloj de la BASE y no el del
// Worker: el Worker corre en otro datacenter y su reloj puede ir distinto; el cursor de
// cambios compara contra la misma fuente que escribió modificado_en.
export const AHORA_MS_SQL = `CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER)`;
const msDe = (col) => `CAST((julianday(${col}) - 2440587.5) * 86400000 AS INTEGER)`;

// Margen de asentamiento del cursor de cambios: solo se entregan filas modificadas hace más
// de este tiempo. Así una escritura que cae en el MISMO milisegundo que la lectura (o un reloj
// que retrocede un poco) no queda detrás del cursor y se pierde para siempre.
export const MARGEN_CAMBIOS_MS = 1500;

// Una operación de envío que quedó 'en_curso' más de esto se reporta como INCIERTA (el
// Worker pudo morir a mitad del envío): nunca se reintenta sola.
export const OP_EN_CURSO_MAX_MS = 120000;

export const jsonApi = (obj, status = 200, extraHeaders = {}) =>
  new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...extraHeaders },
  });

// Error uniforme (compatible con lo viejo: sigue trayendo `error` legible para el panel).
export function errApi(status, codigo, error, extra = {}) {
  return jsonApi({ ok: false, codigo, error, ...extra }, status);
}

// ============================================================
// Migración idempotente AL ARRANCAR (una vez por isolate)
// ============================================================
// Por qué triggers y no tocar cada INSERT/UPDATE: hay ~40 escrituras sobre `correos`
// repartidas por el Worker (más las que haga `wrangler d1 execute` a mano). Un trigger cubre
// TODAS, incluidas las futuras, sin depender de que alguien se acuerde de poner
// modificado_en. Se revisaron una por una (ver contrato §Migración).
export const ESQUEMA = { ok: false };
let esquemaPromesa = null;

export function _reiniciarEsquema() {
  // Solo para pruebas: cada prueba usa una base nueva en el mismo proceso.
  ESQUEMA.ok = false;
  esquemaPromesa = null;
}

export function asegurarEsquema(env) {
  if (ESQUEMA.ok) return Promise.resolve(true);
  if (!esquemaPromesa) {
    esquemaPromesa = migrarC1(env)
      .then(() => {
        ESQUEMA.ok = true;
        return true;
      })
      .catch((e) => {
        // Si falla, las rutas viejas siguen funcionando; las nuevas responden 503. Se
        // reintenta en la próxima petición.
        console.error("migración C1 falló:", e && e.message);
        esquemaPromesa = null;
        return false;
      });
  }
  return esquemaPromesa;
}

const OBJETOS_C1 = [
  "correos_borrados",
  "operaciones",
  "idx_correos_modificado",
  "correos_rev_ai",
  "correos_rev_au",
  "correos_rev_ad",
  "idx_correos_hilo",
  "idx_correos_message_id",
];

async function migrarC1(env) {
  const { results } = await env.DB.prepare(
    `SELECT name, sql FROM sqlite_master WHERE name IN ('correos','adjuntos',${OBJETOS_C1.map(
      (n) => `'${n}'`
    ).join(",")},'adjuntos_rev_ai')`
  ).all();
  const filas = results || [];
  const hay = new Set(filas.map((f) => f.name));
  const sqlCorreos = (filas.find((f) => f.name === "correos") || {}).sql || "";
  const tieneMod = /\bmodificado_en\b/.test(sqlCorreos);
  const tieneRev = /\brevision\b/.test(sqlCorreos);
  const faltaAdjTrigger = hay.has("adjuntos") && !hay.has("adjuntos_rev_ai");
  if (tieneMod && tieneRev && OBJETOS_C1.every((n) => hay.has(n)) && !faltaAdjTrigger) return;

  const q = (sql) => env.DB.prepare(sql).run();
  const agregarColumna = async (def) => {
    try {
      await q(`ALTER TABLE correos ADD COLUMN ${def}`);
    } catch (e) {
      // Otro isolate pudo agregarla en paralelo: eso no es un error.
      if (!/duplicate column/i.test(String(e && e.message))) throw e;
    }
  };
  if (!tieneMod) await agregarColumna("modificado_en INTEGER");
  if (!tieneRev) await agregarColumna("revision INTEGER");

  await q(`CREATE TABLE IF NOT EXISTS correos_borrados (
             id INTEGER PRIMARY KEY,
             borrado_en INTEGER NOT NULL)`);
  await q(`CREATE INDEX IF NOT EXISTS idx_correos_borrados_en ON correos_borrados(borrado_en, id)`);
  await q(`CREATE TABLE IF NOT EXISTS operaciones (
             id TEXT PRIMARY KEY,
             ruta TEXT NOT NULL,
             huella TEXT NOT NULL,
             estado TEXT NOT NULL,
             http INTEGER,
             resultado TEXT,
             creado_en INTEGER NOT NULL,
             actualizado_en INTEGER NOT NULL)`);

  // Backfill ANTES de crear los triggers (así no los dispara): la fecha "de cambio" de lo
  // histórico es la última actividad conocida del mensaje. Si alguna fecha no se puede
  // leer, se cae a la siguiente y, al final, a "ahora".
  // MIN(…, ahora): recibido_en sale de la cabecera Date que pone el REMITENTE; un correo
  // "fechado en 2099" quedaría escondido del feed /api/cambios hasta esa fecha.
  await q(`UPDATE correos SET
             modificado_en = COALESCE(modificado_en, MIN(COALESCE(${msDe("respondido_en")}, ${msDe(
    "recibido_en"
  )}, ${msDe("creado_en")}, ${AHORA_MS_SQL}), ${AHORA_MS_SQL})),
             revision = COALESCE(revision, 1)
           WHERE modificado_en IS NULL OR revision IS NULL`);
  await q(`CREATE INDEX IF NOT EXISTS idx_correos_modificado ON correos(modificado_en, id)`);
  // D1 (5-oct-2026): índice sobre la CLAVE de hilo (+ fecha e id del «último mensaje», en el
  // orden en que el rollup lo busca) que usan /api/hilos y /api/buscar (GROUP BY sin
  // ordenamiento temporal; último mensaje sin ordenar) y las ~15 consultas que filtran
  // `COALESCE(thread_id,'id:'||id) = ?` (revisión del hilo, marcar leído, archivar…), que
  // antes recorrían la tabla entera. SQLite lo reconoce aunque la consulta use un alias
  // (c.thread_id). Si falla no bloquea la migración: solo se pierde la mejora.
  try {
    await q(`CREATE INDEX IF NOT EXISTS idx_correos_hilo ON correos(
               COALESCE(thread_id, 'id:'||id),
               datetime(COALESCE(respondido_en, recibido_en, creado_en)) DESC,
               id DESC)`);
  } catch (e) {
    console.error("idx_correos_hilo no se pudo crear:", e && e.message);
  }
  // La captura busca duplicados e hilo por message_id (3 consultas por correo entrante) y
  // no había índice: cada correo nuevo recorría la tabla tres veces.
  try {
    await q(`CREATE INDEX IF NOT EXISTS idx_correos_message_id ON correos(message_id)`);
  } catch (e) {
    console.error("idx_correos_message_id no se pudo crear:", e && e.message);
  }

  // INSERT: nace con revisión 1 y su marca de tiempo.
  await q(`CREATE TRIGGER IF NOT EXISTS correos_rev_ai AFTER INSERT ON correos
           BEGIN
             UPDATE correos SET modificado_en = ${AHORA_MS_SQL}, revision = 1 WHERE id = NEW.id;
           END`);
  // UPDATE: cualquier cambio sube la revisión y la marca. El WHEN evita el bucle: el UPDATE
  // interno cambia `revision`, así que no vuelve a entrar (aunque recursive_triggers esté ON).
  await q(`CREATE TRIGGER IF NOT EXISTS correos_rev_au AFTER UPDATE ON correos
           WHEN NEW.revision IS OLD.revision
           BEGIN
             UPDATE correos SET modificado_en = ${AHORA_MS_SQL},
                                revision = COALESCE(OLD.revision, 0) + 1
             WHERE id = NEW.id;
           END`);
  // DELETE: deja la lápida para que quien proyecta el buzón también lo borre.
  await q(`CREATE TRIGGER IF NOT EXISTS correos_rev_ad AFTER DELETE ON correos
           BEGIN
             INSERT OR REPLACE INTO correos_borrados (id, borrado_en) VALUES (OLD.id, ${AHORA_MS_SQL});
           END`);
  // Los adjuntos se guardan DESPUÉS del INSERT del correo: si no tocaran su fila, quien leyó
  // el cambio entre medio se quedaría sin los adjuntos para siempre.
  if (hay.has("adjuntos")) {
    await q(`CREATE TRIGGER IF NOT EXISTS adjuntos_rev_ai AFTER INSERT ON adjuntos
             BEGIN
               UPDATE correos SET leido = leido WHERE id = NEW.correo_id;
             END`);
  }
}

// ============================================================
// Direcciones y listas
// ============================================================
const RE_EMAIL = /^[^\s@<>(),;:"]+@[^\s@<>(),;:"]+\.[^\s@<>(),;:"]+$/;

// "Rita Pérez <Rita@X.cl>" → "rita@x.cl"; "rita@x.cl" → igual; basura → "".
export function direccion(s) {
  const t = String(s || "").trim();
  const m = t.match(/<([^<>]+)>\s*$/);
  const d = (m ? m[1] : t).trim().toLowerCase();
  return RE_EMAIL.test(d) ? d : "";
}

// cc/cco: el panel viejo manda "a@x, b@y" (se filtra en silencio, como siempre); el contrato
// nuevo manda un arreglo y ahí una dirección inválida es un error explícito.
export function normalizarLista(v) {
  if (v == null || v === "") return { lista: [], invalidos: [] };
  if (Array.isArray(v)) {
    const lista = [];
    const invalidos = [];
    for (const x of v) {
      const d = direccion(x);
      if (d) lista.push(d);
      else invalidos.push(String(x));
    }
    return { lista: [...new Set(lista)], invalidos, estricto: true };
  }
  const lista = String(v)
    .split(/[,;]+/)
    .map((x) => x.trim())
    .filter((x) => x.includes("@"));
  return { lista, invalidos: [] };
}

// Adjuntos [{nombre, mime, b64}]: tope 5 y 10 MB decodificados (el límite real de Resend
// es ~40 MB, pero D1 y el Worker sufren antes).
export const MAX_ADJUNTOS = 5;
export const MAX_ADJUNTOS_BYTES = 10 * 1024 * 1024;
export function validarAdjuntos(v) {
  if (v == null) return { adjuntos: [] };
  if (!Array.isArray(v)) return { error: "adjuntos debe ser un arreglo", status: 400, codigo: "ENTRADA_INVALIDA" };
  if (v.length > MAX_ADJUNTOS)
    return { error: `máximo ${MAX_ADJUNTOS} adjuntos`, status: 413, codigo: "LIMITE_ADJUNTOS" };
  let total = 0;
  const out = [];
  for (const a of v) {
    const nombre = String((a && a.nombre) || "").trim().slice(0, 180);
    const b64 = String((a && a.b64) || "").replace(/\s+/g, "");
    if (!nombre || !b64) return { error: "cada adjunto necesita nombre y b64", status: 400, codigo: "ENTRADA_INVALIDA" };
    if (!/^[A-Za-z0-9+/]+={0,2}$/.test(b64) || b64.length % 4 === 1)
      return { error: `adjunto «${nombre}»: base64 inválido`, status: 400, codigo: "ENTRADA_INVALIDA" };
    total += Math.floor((b64.length * 3) / 4) - (b64.endsWith("==") ? 2 : b64.endsWith("=") ? 1 : 0);
    out.push({ nombre, mime: String((a && a.mime) || "application/octet-stream").slice(0, 100), b64 });
  }
  if (total > MAX_ADJUNTOS_BYTES)
    return { error: "los adjuntos superan 10 MB", status: 413, codigo: "LIMITE_ADJUNTOS" };
  return { adjuntos: out };
}

// ============================================================
// Cursores opacos (base64url de JSON con versión y tipo)
// ============================================================
export function cursorCodificar(obj) {
  const s = JSON.stringify({ v: 1, ...obj });
  return btoa(unescape(encodeURIComponent(s))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
export function cursorLeer(s, tipo) {
  if (!s) return null;
  try {
    const b = s.replace(/-/g, "+").replace(/_/g, "/");
    const o = JSON.parse(decodeURIComponent(escape(atob(b + "===".slice((b.length + 3) % 4)))));
    if (!o || o.v !== 1 || o.k !== tipo) return undefined;
    return o;
  } catch (e) {
    return undefined; // undefined = cursor inválido (→ 400); null = sin cursor
  }
}

export function limiteDe(url, porDefecto, max = 100) {
  const n = parseInt(url.searchParams.get("limite") || String(porDefecto), 10);
  if (!Number.isFinite(n) || n < 1) return porDefecto;
  return Math.min(n, max);
}

// ============================================================
// Idempotencia (tabla `operaciones`)
// ============================================================
// JSON estable (claves ordenadas): la misma intención produce la misma huella aunque el
// cliente serialice las claves en otro orden.
function estable(v) {
  if (Array.isArray(v)) return "[" + v.map(estable).join(",") + "]";
  if (v && typeof v === "object")
    return "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + estable(v[k])).join(",") + "}";
  return JSON.stringify(v === undefined ? null : v);
}
async function sha256(s) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Devuelve {id} si esta petición es la dueña de la operación (o {id:null} sin solicitud_id),
// o {respuesta} lista para devolver (repetición, conflicto o en curso).
// Estados: en_curso → terminado (hubo o pudo haber efecto externo; se repite su resultado)
//          en_curso → rechazado (no se hizo nada; la clave queda libre para reintentar).
export async function abrirOperacion(env, solicitudId, ruta, cuerpo) {
  if (solicitudId == null || solicitudId === "") return { id: null };
  if (typeof solicitudId !== "string" || !/^[A-Za-z0-9._:-]{8,128}$/.test(solicitudId))
    return {
      respuesta: errApi(400, "ENTRADA_INVALIDA", "solicitud_id inválido (8-128 caracteres A-Z a-z 0-9 . _ : -)", {
        campos: ["solicitud_id"],
      }),
    };
  if (!ESQUEMA.ok)
    return { respuesta: errApi(503, "DEPENDENCIA_NO_DISPONIBLE", "migración C1 pendiente; reintenta") };
  const { solicitud_id, ...resto } = cuerpo || {};
  const huella = await sha256(ruta + "\n" + estable(resto));
  const ahora = Date.now();
  const ins = await env.DB.prepare(
    `INSERT OR IGNORE INTO operaciones (id, ruta, huella, estado, creado_en, actualizado_en)
     VALUES (?, ?, ?, 'en_curso', ?, ?)`
  )
    .bind(solicitudId, ruta, huella, ahora, ahora)
    .run();
  if (ins.meta && ins.meta.changes > 0) return { id: solicitudId };

  const op = await env.DB.prepare(`SELECT * FROM operaciones WHERE id=?`).bind(solicitudId).first();
  if (!op) return { respuesta: errApi(409, "EN_CURSO", "operación en carrera; reintenta", { operacionId: solicitudId, reintentarEnMs: 1000 }) };
  if (op.estado === "rechazado") {
    // Nada salió la vez anterior: la clave se puede reutilizar (incluso con otro cuerpo).
    const re = await env.DB.prepare(
      `UPDATE operaciones SET estado='en_curso', ruta=?, huella=?, http=NULL, resultado=NULL, actualizado_en=?
       WHERE id=? AND estado='rechazado'`
    )
      .bind(ruta, huella, ahora, solicitudId)
      .run();
    if (re.meta && re.meta.changes > 0) return { id: solicitudId };
    return { respuesta: errApi(429, "EN_CURSO", "la misma operación está en curso", { operacionId: solicitudId, reintentarEnMs: 2000 }) };
  }
  if (op.ruta !== ruta || op.huella !== huella)
    return {
      respuesta: errApi(409, "IDEMPOTENCIA_CONFLICTO", "esa solicitud_id ya se usó con otro contenido", {
        operacionId: solicitudId,
      }),
    };
  if (op.estado === "en_curso") {
    const colgada = ahora - Number(op.actualizado_en || 0) > OP_EN_CURSO_MAX_MS;
    // Un borrador colgado no tiene efecto externo: se retoma en vez de decir "no se sabe si
    // el correo salió".
    if (colgada && op.ruta === "/api/borrador") {
      const re = await env.DB.prepare(
        `UPDATE operaciones SET actualizado_en=? WHERE id=? AND estado='en_curso' AND actualizado_en=?`
      )
        .bind(ahora, solicitudId, op.actualizado_en)
        .run();
      if (re.meta && re.meta.changes > 0) return { id: solicitudId };
    }
    if (colgada)
      return {
        respuesta: jsonApi(
          {
            ok: false,
            codigo: "ENVIO_INCIERTO",
            error: "la operación quedó a medias; no se sabe si el correo salió. Revisa Enviados antes de reintentar.",
            operacion: { id: solicitudId, estado: "incierto", proveedorId: null, registroPendiente: true },
          },
          202
        ),
      };
    return { respuesta: errApi(429, "EN_CURSO", "la misma operación está en curso", { operacionId: solicitudId, reintentarEnMs: 2000 }) };
  }
  // terminado: misma clave → mismo resultado, byte a byte.
  return {
    respuesta: new Response(op.resultado || "{}", {
      status: op.http || 200,
      headers: { "content-type": "application/json; charset=utf-8", "x-idempotencia": "repetida" },
    }),
  };
}

export async function cerrarOperacion(env, opId, r) {
  if (!opId) return;
  try {
    await env.DB.prepare(
      `UPDATE operaciones SET estado=?, http=?, resultado=?, actualizado_en=? WHERE id=?`
    )
      .bind(r.efecto ? "terminado" : "rechazado", r.status, JSON.stringify(r.body), Date.now(), opId)
      .run();
  } catch (e) {
    // Si esto falla, la operación queda en_curso y a los 2 min se reporta incierta: nunca
    // se reenvía sola.
    console.error("cerrarOperacion falló:", e && e.message);
  }
}

// Revisión de un HILO (opaca): cambia con cualquier INSERT/UPDATE/DELETE de sus mensajes
// (n = cantidad, s = suma de revisiones, que solo crecen; m = id máximo).
export async function revisionHilo(env, tid) {
  const r = await env.DB.prepare(
    `SELECT COUNT(*) AS n, COALESCE(SUM(revision),0) AS s, COALESCE(MAX(id),0) AS m
     FROM correos WHERE COALESCE(thread_id,'id:'||id)=?`
  )
    .bind(tid)
    .first();
  return r ? `${r.n}.${r.s}.${r.m}` : "0.0.0";
}

// ============================================================
// GET /api/cambios?desde=&cursor=&limite=
// ============================================================
const COLS_CAMBIO = `c.id, c.thread_id, c.message_id, c.in_reply_to, c.de, c.de_nombre, c.para, c.asunto,
  c.estado, c.leido, c.destacado, c.pospuesto_hasta, c.etiquetas, c.confianza, c.motivo_revision,
  c.ajuste_pedido, c.ajuste_enviar, c.recibido_en, c.respondido_en, c.creado_en,
  substr(c.cuerpo_texto, 1, 50000) AS cuerpo_texto, length(c.cuerpo_texto) AS cuerpo_largo,
  c.respuesta_enviada, c.respuesta_borrador, c.adjunto_nombre, c.modificado_en, c.revision`;

export async function apiCambios(env, url, firmar) {
  if (!ESQUEMA.ok) return errApi(503, "DEPENDENCIA_NO_DISPONIBLE", "migración C1 pendiente; reintenta");
  const limite = limiteDe(url, 50);
  const cur = cursorLeer(url.searchParams.get("cursor"), "cambios");
  if (cur === undefined) return errApi(400, "ENTRADA_INVALIDA", "cursor inválido", { campos: ["cursor"] });
  let t, b, i;
  if (cur) {
    ({ t, b, i } = cur);
  } else {
    // desde (ms) es INCLUSIVO: reentregar un empate es inofensivo (upsert), perderlo no.
    const desde = parseInt(url.searchParams.get("desde") || "0", 10);
    t = Number.isFinite(desde) && desde > 0 ? desde : 0;
    b = -1;
    i = -1;
  }
  if (![t, b, i].every(Number.isFinite))
    return errApi(400, "ENTRADA_INVALIDA", "cursor inválido", { campos: ["cursor"] });

  // Un solo flujo ordenado por (ts, tipo, id): filas vivas (b=0) y lápidas (b=1). Ordenar
  // también por id rompe los empates del mismo milisegundo sin perder ninguna fila.
  //
  // D1 (5-oct-2026): antes era UN SELECT sobre un UNION ALL filtrando la columna calculada
  // `ts`: SQLite no podía usar idx_correos_modificado y cada llamada (1/min por dixdybot)
  // leía la tabla entera (~600 filas). Ahora son dos recorridos por índice con LIMIT
  // —correos(modificado_en,id) y correos_borrados(borrado_en,id)— y el merge va en JS: cada
  // llamada lee O(página). El corte «ahora − margen» se lee UNA vez del reloj de D1 y se usa
  // en las dos consultas (con dos relojes, una lápida podría adelantar el cursor por encima
  // de una fila viva todavía no entregada).
  const filaAhora = await env.DB.prepare(`SELECT ${AHORA_MS_SQL} AS ahora`).first();
  const corte = Number(filaAhora && filaAhora.ahora) - MARGEN_CAMBIOS_MS;
  // Posición del cursor dentro del ms `t`: una fila viva (b=0) va antes que una lápida (b=1).
  //   cursor b=-1 (inicio): entran todas las de ts=t → id > -1.
  //   cursor b=0: vivas de ts=t con id > i; lápidas de ts=t, todas.
  //   cursor b=1: vivas de ts=t ya pasaron (id > MAX); lápidas de ts=t con id > i.
  const SIN_MAS = Number.MAX_SAFE_INTEGER;
  const idVivos = b < 0 ? -1 : b === 0 ? i : SIN_MAS;
  const idLapidas = b < 1 ? -1 : i;
  const [{ results: vivos }, { results: lapidas }] = await Promise.all([
    env.DB.prepare(
      `SELECT 0 AS b, id, modificado_en AS ts FROM correos
       WHERE (modificado_en, id) > (?, ?) AND modificado_en < ?
       ORDER BY modificado_en ASC, id ASC LIMIT ?`
    )
      .bind(t, idVivos, corte, limite + 1)
      .all(),
    env.DB.prepare(
      `SELECT 1 AS b, id, borrado_en AS ts FROM correos_borrados
       WHERE (borrado_en, id) > (?, ?) AND borrado_en < ?
       ORDER BY borrado_en ASC, id ASC LIMIT ?`
    )
      .bind(t, idLapidas, corte, limite + 1)
      .all(),
  ]);
  const lista = [...(vivos || []), ...(lapidas || [])]
    .sort((x, y) => x.ts - y.ts || x.b - y.b || x.id - y.id)
    .slice(0, limite + 1);
  const hayMas = lista.length > limite;
  const pagina = lista.slice(0, limite);

  const idsVivos = pagina.filter((x) => x.b === 0).map((x) => x.id);
  const borrados = pagina.filter((x) => x.b === 1).map((x) => ({ id: x.id, borrado_en: x.ts }));
  let cambios = [];
  if (idsVivos.length) {
    const ph = idsVivos.map(() => "?").join(",");
    const { results: filas } = await env.DB.prepare(
      `SELECT ${COLS_CAMBIO} FROM correos c WHERE c.id IN (${ph})`
    )
      .bind(...idsVivos)
      .all();
    const porId = new Map((filas || []).map((f) => [f.id, f]));
    // Si una fila se borró entre las dos consultas, su lápida llegará en una página
    // siguiente: aquí simplemente no aparece.
    cambios = idsVivos.map((id) => porId.get(id)).filter(Boolean);
    for (const c of cambios) {
      c.cuerpo_truncado = (c.cuerpo_largo || 0) > 50000;
      delete c.cuerpo_largo;
      c.adjuntos = [];
      if (c.adjunto_nombre && firmar) {
        try {
          c.url_cotizacion = `/cotizacion?id=${c.id}&s=${await firmar("cot:" + c.id)}`;
        } catch (e) {
          c.url_cotizacion = null;
        }
      }
    }
    try {
      const { results: adjs } = await env.DB.prepare(
        `SELECT id, correo_id, nombre, mime, tamano, inline, (datos_b64 IS NOT NULL) AS guardado
         FROM adjuntos WHERE correo_id IN (${ph}) ORDER BY id ASC`
      )
        .bind(...idsVivos)
        .all();
      const porCorreo = new Map(cambios.map((c) => [c.id, c]));
      for (const a of adjs || []) {
        a.url = a.guardado && firmar ? `/adjunto?id=${a.id}&s=${await firmar("adj:" + a.id)}` : null;
        const c = porCorreo.get(a.correo_id);
        if (c) c.adjuntos.push(a);
      }
    } catch (e) {
      /* tabla adjuntos aún no migrada (pre fase 13): sin metadatos */
    }
  }
  const ult = pagina.length ? pagina[pagina.length - 1] : null;
  const sig = ult ? { t: ult.ts, b: ult.b, i: ult.id } : { t, b, i };
  return jsonApi({
    ok: true,
    cambios,
    borrados,
    siguienteCursor: cursorCodificar({ k: "cambios", ...sig }),
    hayMas,
    margenMs: MARGEN_CAMBIOS_MS,
  });
}

// Candados de un solo uso sobre la tabla `operaciones` (ruta='candado'): INSERT OR IGNORE es
// atómico en D1, así que solo UNA petición toma una clave como "candado:hilo:<tid>:<rev>".
// Se suelta solo si el envío fue rechazado (no salió); si salió, la revisión ya cambió y el
// candado viejo no estorba a nadie.
export async function tomarCandado(env, clave) {
  const ahora = Date.now();
  const r = await env.DB.prepare(
    `INSERT OR IGNORE INTO operaciones (id, ruta, huella, estado, creado_en, actualizado_en)
     VALUES (?, 'candado', '-', 'terminado', ?, ?)`
  )
    .bind(clave, ahora, ahora)
    .run();
  return !!(r.meta && r.meta.changes > 0);
}
export async function soltarCandado(env, clave) {
  try {
    await env.DB.prepare(`DELETE FROM operaciones WHERE id=? AND ruta='candado'`).bind(clave).run();
  } catch (e) {
    console.error("soltarCandado falló:", e && e.message);
  }
}
