// Tests sin navegador de la Fase 10 (ley DIXDY: verificar desde el código primero).
// 1) Funciones puras del panel (partirCitas, quitarRe, participantesTxt, entradasHilo)
// 2) Threading del Worker (normAsunto, contraparte, derivarThreadId con DB falsa)
import { readFileSync } from "node:fs";
import vm from "node:vm";

const BASE = process.argv[2] || new URL(".", import.meta.url).pathname.replace(/\/$/, "");
let fallos = 0, oks = 0;
function check(nombre, cond, extra) {
  if (cond) { oks++; console.log("  ✓", nombre); }
  else { fallos++; console.log("  ✗ FALLO:", nombre, extra !== undefined ? "→ " + JSON.stringify(extra) : ""); }
}

// ---------- 1) Panel: evaluar el <script> con stubs de DOM ----------
const html = readFileSync(BASE + "/panel.html", "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const elStub = () => ({
  style: {}, classList: { toggle() {}, add() {}, remove() {}, contains: () => false },
  addEventListener() {}, appendChild() {}, querySelectorAll: () => [], querySelector: () => null,
  innerHTML: "", textContent: "", dataset: {}, focus() {}, remove() {},
});
const ctx = {
  document: {
    getElementById: elStub, createElement: elStub, querySelectorAll: () => [], querySelector: () => null,
    addEventListener() {}, body: elStub(),
  },
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  navigator: { onLine: true }, window: { Squire: undefined, DOMPurify: undefined, addEventListener() {} },
  setInterval() {}, clearTimeout() {}, setTimeout() {},
  fetch: async () => ({ json: async () => ({}) }), console, atob: (s)=>Buffer.from(s,"base64").toString("binary"),
  Notification: undefined, URL, alert() {}, confirm: () => false, prompt: () => null, event: {},
  Map, Set, TextEncoder, crypto: undefined,
};
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(script, ctx);

console.log("\n== partirCitas (recorte de citas ES/EN) ==");
{
  const gmailES = "Hola, confirmo la fecha.\nSaludos\n\nEl lun, 11 ago 2026 a las 10:03, Negocio Ejemplo (<contacto@negocio.cl>) escribió:\n> Estimada Rita\n> Adjunto cotización";
  const r1 = ctx.partirCitas(gmailES);
  check("Gmail ES: separa 'El ... escribió:'", r1.visible === "Hola, confirmo la fecha.\nSaludos" && r1.cita.startsWith("El lun"), r1);

  const outlookES = "Perfecto, gracias.\n\nDe: Negocio Ejemplo <contacto@negocio.cl>\nEnviado: lunes 11 de agosto\nPara: Rita Pérez\nAsunto: Re: Cotización\n\ntexto viejo";
  const r2 = ctx.partirCitas(outlookES);
  check("Outlook ES: bloque 'De:/Enviado:/Para:'", r2.visible === "Perfecto, gracias." && r2.cita.startsWith("De:"), r2);

  const desde = "Adjunto comprobante.\nSaludos Rita\n\nDesde: Negocio Ejemplo <contacto@negocio.cl>\nEnviado: 7 ago\nPara: rperez@cierreparcela.cl\n\nhola";
  const r3 = ctx.partirCitas(desde);
  check("'Desde:' con cabeceras también corta", r3.visible.includes("Saludos Rita") && r3.cita.startsWith("Desde:"), r3);

  const firma = "Estimados:\nAdjunto comprobante.\nDe: Rita Pérez\nGerente de obra";
  const r4 = ctx.partirCitas(firma);
  check("'De:' de firma (sin cabeceras) NO corta", r4.cita === "" && r4.visible === firma, r4);

  const mayor = "Ok perfecto\n> texto citado\n> más citado";
  const r5 = ctx.partirCitas(mayor);
  check("líneas '>' cortan", r5.visible === "Ok perfecto" && r5.cita.startsWith(">"), r5);

  const soloCita = "El 5 ago escribió:\n> hola";
  const r6 = ctx.partirCitas(soloCita);
  check("mensaje que ES pura cita queda visible (idx 0)", r6.visible === soloCita && r6.cita === "", r6);

  const enWrote = "Sure, confirmed.\n\nOn Mon, Aug 11, 2026 at 10:03 AM Negocio Ejemplo wrote:\n> quote";
  const r7 = ctx.partirCitas(enWrote);
  check("inglés 'On ... wrote:'", r7.visible === "Sure, confirmed." && r7.cita.startsWith("On Mon"), r7);

  const original = "Gracias.\n\n-----Mensaje original-----\nDe: x";
  const r8 = ctx.partirCitas(original);
  check("'-----Mensaje original-----'", r8.visible === "Gracias." && r8.cita.startsWith("-----"), r8);
}

console.log("\n== quitarRe / participantesTxt ==");
{
  check("quitarRe simple", ctx.quitarRe("Re: RE: Fwd: Cotización baño") === "Cotización baño");
  check("quitarRe vacío", ctx.quitarRe("") === "(sin asunto)");
  const h1 = { participantes: "Rita Pérez|Rita Pérez|yo", salientes: 1, n: 3 };
  check("participantes dedup + yo al final", ctx.participantesTxt(h1) === "Rita, yo", ctx.participantesTxt(h1));
  const h2 = { participantes: "rperez@cierreparcela.cl", salientes: 0 };
  check("1 participante sin nombre → dirección completa", ctx.participantesTxt(h2) === "rperez@cierreparcela.cl");
  const h3 = { participantes: "Rita Pérez|Carlos Torres", salientes: 1 };
  check("varios: nombres de pila + yo", ctx.participantesTxt(h3) === "Rita, Carlos, yo", ctx.participantesTxt(h3));
  const h4 = { participantes: "", salientes: 1 };
  check("solo salientes → 'yo'", ctx.participantesTxt(h4) === "yo", ctx.participantesTxt(h4));
}

console.log("\n== entradasHilo (aplanar conversación) ==");
{
  const msgs = [
    { id: 1, de: "rita@x.cl", de_nombre: "Rita", estado: "respondido", recibido_en: "2026-08-06T10:00:00Z",
      respondido_en: "2026-08-07T09:00:00Z", respuesta_enviada: "Cotización adjunta", adjunto_nombre: "cot.pdf",
      cuerpo_texto: "Necesito baño químico", leido: 1 },
    { id: 2, de: "rita@x.cl", de_nombre: "Rita", estado: "nuevo", recibido_en: "2026-08-11T10:03:00Z",
      cuerpo_texto: "Adjunto comprobante", leido: 0 },
  ];
  const ent = ctx.entradasHilo(msgs);
  check("3 entradas (2 entrantes + 1 respuesta)", ent.length === 3, ent.length);
  check("orden cronológico", ent[0].id === "1" && ent[1].id === "r1" && ent[2].id === "2",
    ent.map(e => e.id));
  check("respuesta es saliente con PDF", ent[1].dir === "out" && ent[1].adj === "cot.pdf");
  check("último no leído", ent[2].leido === 0);
}

console.log("\n== fmtFechaSql (fechas de SQLite en UTC) ==");
{
  // "ahora" en formato datetime() de SQLite (UTC): debe mostrarse como hora local de hoy
  const sqlAhora = new Date().toISOString().replace("T", " ").slice(0, 19);
  const r = ctx.fmtFechaSql(sqlAhora);
  check("fecha de hoy → hora (contiene ':')", /\d{1,2}:\d{2}/.test(r), r);
  check("fecha vacía → ''", ctx.fmtFechaSql(null) === "");
}

// htmlATexto, partirCitasHtml, sanitizarCorreo y montarIframe dependen del DOM real
// (createElement/innerHTML/iframe): se verifican en el navegador, no aquí.

// ---------- 2) Worker: threading (extraer funciones y probarlas con DB falsa) ----------
console.log("\n== Worker: normAsunto / derivarThreadId ==");
const worker = readFileSync(BASE + "/src/index.js", "utf8");
function extraerFn(nombre) {
  const re = new RegExp(`((?:async )?function ${nombre}\\([\\s\\S]*?)\\n(?=(?:async )?function |// |const |export )`, "m");
  const m = worker.match(re);
  if (!m) throw new Error("no encontré " + nombre);
  return m[1];
}
const wctx = { console, Date, RegExp };
vm.createContext(wctx);
vm.runInContext(extraerFn("normAsunto"), wctx);
vm.runInContext(extraerFn("cuentas"), wctx);
vm.runInContext(extraerFn("esNuestra"), wctx);
vm.runInContext(extraerFn("contraparte"), wctx);
vm.runInContext(extraerFn("derivarThreadId"), wctx);
// env de prueba: una cuenta por CONTACT_EMAIL (respaldo) y dos por CUENTAS (subcuentas).
const ENV1 = { CONTACT_EMAIL: "contacto@negocio.cl" };
const ENV2 = { CUENTAS: "contacto@negocio.cl, ventas@negocio.cl|Ventas" };

check("normAsunto quita Re:/Fwd:", wctx.normAsunto("RE: Re: Fwd: Cotización  Baño") === "cotización baño");
check("cuentas: CSV con etiqueta", JSON.stringify(wctx.cuentas(ENV2)) === JSON.stringify(["contacto@negocio.cl","ventas@negocio.cl"]));
check("esNuestra con respaldo CONTACT_EMAIL", wctx.esNuestra(ENV1, "Contacto@Negocio.cl") === true);
check("esNuestra: ajena es falsa", wctx.esNuestra(ENV2, "rita@x.cl") === false);
check("contraparte nuestro→para", wctx.contraparte(ENV1, "contacto@negocio.cl", "rita@x.cl") === "rita@x.cl");
check("contraparte cliente→de", wctx.contraparte(ENV1, "Rita@X.cl", "contacto@negocio.cl") === "rita@x.cl");
check("contraparte subcuenta→para", wctx.contraparte(ENV2, "Ventas@Negocio.cl", "rita@x.cl") === "rita@x.cl");

// DB falsa: se programa por consulta.
function fakeDB(porHeader, recientes) {
  return {
    prepare(sql) {
      return {
        bind() {
          return {
            async first() { return sql.includes("message_id IN") ? porHeader : null; },
            async all() { return { results: sql.includes("datetime(creado_en)") ? recientes : [] }; },
          };
        },
      };
    },
  };
}

{
  // 1) adopta por header
  const env = { CONTACT_EMAIL: "contacto@negocio.cl", DB: fakeDB({ thread_id: "hilo-por-header" }, []) };
  const t = await wctx.derivarThreadId(env, "rita@x.cl", "contacto@negocio.cl", "Re: Cotización", "<mid1>", "", "u1");
  check("adopta hilo por In-Reply-To/References", t === "hilo-por-header", t);
}
{
  // 2) sin header: adopta por asunto+contraparte reciente (responde a cotización proactiva 'enviado')
  const env = { CONTACT_EMAIL: "contacto@negocio.cl", DB: fakeDB(null, [{ asunto: "Cotización Negocio Ejemplo — baño químico", thread_id: "hilo-enviado-77" }]) };
  const t = await wctx.derivarThreadId(env, "rita@x.cl", "contacto@negocio.cl",
    "Re: Cotización Negocio Ejemplo — baño químico", "", "", "u2");
  check("adopta hilo por asunto+contraparte (7 días)", t === "hilo-enviado-77", t);
}
{
  // 3) sin nada: hilo nuevo único con sufijo
  const env = { CONTACT_EMAIL: "contacto@negocio.cl", DB: fakeDB(null, [{ asunto: "Otro tema totalmente distinto", thread_id: "hilo-x" }]) };
  const t = await wctx.derivarThreadId(env, "rita@x.cl", "contacto@negocio.cl", "Consulta nueva", "", "", "uniq99");
  check("hilo nuevo único (con cuenta + sufijo uniq)", t === "s:consulta nueva|rita@x.cl|contacto@negocio.cl|uniq99", t);
  // Subcuentas (fase 16): el mismo cliente y asunto hacia DOS cuentas nuestras = DOS hilos.
  const envSub = { CUENTAS: "contacto@negocio.cl,ventas@negocio.cl", DB: fakeDB(null, []) };
  const tA = await wctx.derivarThreadId(envSub, "rita@x.cl", "contacto@negocio.cl", "Consulta nueva", "", "", "u1");
  const tB = await wctx.derivarThreadId(envSub, "rita@x.cl", "ventas@negocio.cl", "Consulta nueva", "", "", "u1");
  check("subcuentas: hilos separados por cuenta", tA !== tB && tA.includes("contacto@") && tB.includes("ventas@"), [tA, tB]);
}
{
  // 4) dos conversaciones iguales separadas en el tiempo NO se pegan (ventana vacía)
  const env = { CONTACT_EMAIL: "contacto@negocio.cl", DB: fakeDB(null, []) };
  const t1 = await wctx.derivarThreadId(env, "rita@x.cl", "contacto@negocio.cl", "Cotización", "", "", "a1");
  const t2 = await wctx.derivarThreadId(env, "rita@x.cl", "contacto@negocio.cl", "Cotización", "", "", "b2");
  check("mismo asunto meses después → hilos distintos", t1 !== t2, [t1, t2]);
}

console.log("\n== Worker: htmlATextoWorker (correos que llegan SOLO en HTML) ==");
vm.runInContext(worker.match(/const ENTIDADES = \{[\s\S]*?\n\};/)[0], wctx);
vm.runInContext(extraerFn("decodificarEntidades"), wctx);
vm.runInContext(extraerFn("htmlATextoWorker"), wctx);
{
  const html = "<html><body><p>Estimados,</p><p>Necesito <b>3 ba&ntilde;os qu&iacute;micos</b> " +
    "para la obra.</p><p>Saludos,<br>Pedro</p></body></html>";
  const t = wctx.htmlATextoWorker(html);
  check("acentos por entidad se decodifican", t.includes("baños químicos"), t);
  check("párrafos → saltos de línea", t.split("\n").length >= 3, t.split("\n"));
  check("no quedan etiquetas", !/[<>]/.test(t), t);
  check("entidad numérica &#241; → ñ", wctx.htmlATextoWorker("<p>ma&#241;ana</p>") === "mañana",
    wctx.htmlATextoWorker("<p>ma&#241;ana</p>"));
  check("entidad hex &#xF1; → ñ", wctx.htmlATextoWorker("<p>ma&#xF1;ana</p>") === "mañana");
  check("scripts y estilos se eliminan",
    !wctx.htmlATextoWorker("<style>.x{color:red}</style><script>alert(1)</script><p>Hola</p>").includes("color"),
    wctx.htmlATextoWorker("<style>.x{color:red}</style><script>alert(1)</script><p>Hola</p>"));
  check("entidad desconocida se deja tal cual", wctx.htmlATextoWorker("<p>&zzz; fin</p>").includes("&zzz;"));
  check("html vacío → ''", wctx.htmlATextoWorker("") === "" && wctx.htmlATextoWorker(null) === "");
}

console.log("\n== Worker: ftsQuery (consulta de búsqueda segura) ==");
vm.runInContext(extraerFn("ftsQuery"), wctx);
check("un término lleva prefijo *", wctx.ftsQuery("cotiza") === '"cotiza"*', wctx.ftsQuery("cotiza"));
check("dos términos: solo el último con *", wctx.ftsQuery("valle escondido") === '"valle" "escondido"*', wctx.ftsQuery("valle escondido"));
check("comillas y operadores se neutralizan", wctx.ftsQuery('ba"ño OR *') === '"baño" "OR"*', wctx.ftsQuery('ba"ño OR *'));
check("vacío devuelve ''", wctx.ftsQuery("   ") === "");
check("tope de 6 términos", wctx.ftsQuery("a b c d e f g h").split(" ").length === 6);

console.log(`\n${oks} OK · ${fallos} fallos`);
process.exit(fallos ? 1 : 0);
