// Casos borde de la versión nueva (datos reales, solo GET; escrituras interceptadas):
// sin clave, sin red con caché v2 / con caché v1 / sin nada, la caché de tarjetas se usa y se
// invalida por updated_at, el delta evita el paso 2, la v1 se borra, el ancla, fallas parciales.
// Uso (desde la raíz del repo): node resumen-repartidor/tests/navegador/probar-bordes.mjs <listado-publicado.html> <listado-nuevo.html>
// El publicado se baja con curl de GitHub Pages; el nuevo sale de generar_listado.py <salida.html>.
import { createRequire } from "node:module";
import { createServer } from "node:http";
import { readFileSync, existsSync, statSync } from "node:fs";
import { join, extname, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir } from "node:os";
const require = createRequire(import.meta.url);
// playwright-core: el del proyecto, el de destaperapido en DIXDY o el de la caché de npx
function resolverPlaywright() {
  const cands = ["playwright-core", "playwright", join(homedir(), "SaSS/DIXDY/clientes/destaperapido/node_modules/playwright-core")];
  try { for (const d of require("node:fs").readdirSync(join(homedir(), ".npm/_npx"))) cands.push(join(homedir(), ".npm/_npx", d, "node_modules/playwright-core")); } catch { /* sin npx */ }
  for (const p of cands) { try { return require(p); } catch { /* siguiente */ } }
  console.error("✗ No encuentro playwright-core. Corre una vez: npx playwright@latest --version"); process.exit(2);
}
const { chromium } = resolverPlaywright();
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const lanzar = () => chromium.launch(existsSync(CHROME) ? { executablePath: CHROME, headless: true } : { headless: true });
const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const [viejo, nuevo] = process.argv.slice(2);
const htmls = { viejo: readFileSync(viejo), nuevo: readFileSync(nuevo) };
let actual = "nuevo";
const server = createServer((req, res) => {
  const url = new URL(req.url, "http://x");
  if (url.pathname.endsWith("/listado.html")) { res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" }); res.end(htmls[actual]); return; }
  const f = join(REPO, url.pathname.replace(/^\/resumen-repartidor\//, ""));
  if (!existsSync(f) || !statSync(f).isFile()) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "Content-Type": extname(f) === ".png" ? "image/png" : "application/octet-stream" }); res.end(readFileSync(f));
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const BASE = `http://127.0.0.1:${server.address().port}/resumen-repartidor/listado.html`;
const browser = await lanzar();
const fallos = [];
const ok = (c, msg, det) => { console.log((c ? "✅ " : "❌ ") + msg + (!c && det !== undefined ? "\n    → " + JSON.stringify(det).slice(0, 400) : "")); if (!c) fallos.push(msg); };

async function abrir(ctx, { url = BASE + "?repartidor=p-9t4kqv", bloquear = null, cual = "nuevo" } = {}) {
  actual = cual;
  const page = await ctx.newPage();
  const pedidos = [];
  const errores = [];
  page.on("pageerror", (e) => errores.push(String(e)));
  page.on("dialog", (d) => d.accept());
  await page.route(/supabase\.co/, async (route) => {
    const r = route.request();
    const u = decodeURIComponent(r.url().replace(/^https:\/\/[^/]+/, "")).replace(/[?&]apikey=[^&]+/, "");
    pedidos.push(r.method() + " " + u);
    if (bloquear && bloquear(u, r)) { await route.abort(); return; }
    if (["GET", "HEAD", "OPTIONS"].includes(r.method())) { await route.continue(); return; }
    await route.fulfill({ status: 201, headers: { "access-control-allow-origin": "*" }, body: "" });
  });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.body.classList.contains("listo"), null, { timeout: 60000 });
  await page.waitForTimeout(2500); // incluye el guardado en el teléfono (requestIdleCallback)
  const estado = await page.evaluate(() => ({
    h1: document.querySelector("header h1").textContent,
    act: document.getElementById("hdr-act").textContent,
    aviso: document.getElementById("estado-online").hidden ? null : document.getElementById("estado-online").textContent,
    visibles: [...document.querySelectorAll(".card-wrap[data-id]")].filter((c) => c.offsetParent !== null).map((c) => c.getAttribute("data-id")),
    textoTarjetas: [...document.querySelectorAll(".card-wrap[data-id]")].map((c) => c.innerText).join("\n"),
    ls: Object.keys(localStorage).reduce((o, k) => { o[k] = (localStorage.getItem(k) || "").length; return o; }, {}),
    resalta: [...document.querySelectorAll(".card-wrap.resalta")].map((c) => c.getAttribute("data-id")),
    precalentar: !!document.getElementById("precalentar"),
  }));
  return { page, pedidos, errores, estado };
}
const nuevoCtx = () => browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, locale: "es-CL", timezoneId: "America/Santiago" });
const esTarjetas = (p) => /\/rest\/v1\/entrega\?select=id,updated_at,card_html&id=in\./.test(p);
const esDelta = (p) => /updated_at=gt\./.test(p);

// 1) sin clave: nada a la base
{
  const ctx = await nuevoCtx();
  const r = await abrir(ctx, { url: BASE });
  ok(r.estado.h1 === "Enlace incompleto" && r.pedidos.length === 0, "sin clave: «Enlace incompleto» y CERO pedidos a Supabase", { h1: r.estado.h1, pedidos: r.pedidos });
  ok(r.estado.visibles.length === 0, "sin clave: ninguna tarjeta");
  await ctx.close();
}
// 2) primera visita, segunda visita (caché + delta), caché v1 borrada, sin red con caché v2
{
  const ctx = await nuevoCtx();
  // antes, la versión VIEJA deja su caché v1 (1,7 MB) en este teléfono
  const v = await abrir(ctx, { cual: "viejo" });
  const tieneV1 = (v.estado.ls["entregas_cache_v1"] || 0) > 100000;
  await v.page.close();
  const a = await abrir(ctx);
  if (!tieneV1) console.log("·  la versión publicada ya no deja la caché v1 (se saltan sus pruebas de transición)");
  ok(a.pedidos.filter(esTarjetas).length >= 1 && !a.pedidos.some(esDelta), "1.ª visita nueva: pide las tarjetas de la lista (paso 2) y no hay delta todavía", a.pedidos);
  if (tieneV1) ok(!("entregas_cache_v1" in a.estado.ls), "tras una carga viva se borra la caché v1", a.estado.ls);
  ok((a.estado.ls["tarjetas_v2"] || 0) > 10000 && (a.estado.ls["entregas_lite_v2"] || 0) > 10000 && a.estado.ls["tarjetas_v2_desde:p-9t4kqv"] > 0, "guarda caché v2 (datos + tarjetas de la lista + marca)", a.estado.ls);
  const totalLs = Object.values(a.estado.ls).reduce((x, y) => x + y, 0);
  ok(totalLs < 700000, `el teléfono guarda ${Math.round(totalLs / 1024)} K caracteres (antes ~1.750 K)`);
  ok(!a.estado.precalentar, "la muestra invisible #precalentar se quita después de mostrar");
  ok(a.errores.length === 0, "sin errores de JS (1.ª visita)", a.errores);
  const visibles1 = a.estado.visibles;
  await a.page.close();
  const b = await abrir(ctx);
  ok(b.pedidos.some(esDelta), "2.ª visita: pide de una vez lo que cambió desde la anterior (delta)", b.pedidos);
  ok(b.pedidos.filter(esTarjetas).length === 0, "2.ª visita: NO hace el paso 2 (todas las tarjetas al día en el teléfono)", b.pedidos.filter(esTarjetas));
  ok(JSON.stringify(b.estado.visibles) === JSON.stringify(visibles1), "2.ª visita: mismas tarjetas en el mismo orden", { a: visibles1, b: b.estado.visibles });
  ok(!b.pedidos.some((p) => /tarea_estado/.test(p)), "ya no pide tarea_estado (no hay tareas en la página)");
  ok(!b.pedidos.some((p) => /^OPTIONS/.test(p)), "las lecturas no hacen consulta previa (OPTIONS)", b.pedidos.filter((p) => /^OPTIONS/.test(p)));
  // 3) la caché se USA: tarjeta guardada con el mismo updated_at y un texto marcado → se ve la marcada
  const id0 = visibles1[0];
  await b.page.evaluate((id0) => {
    const t = JSON.parse(localStorage.getItem("tarjetas_v2"));
    t[id0].h = t[id0].h.replace(/<span class="cliente">/, '<span class="cliente">MARCA-CACHE ');
    localStorage.setItem("tarjetas_v2", JSON.stringify(t));
  }, id0);
  await b.page.close();
  const c = await abrir(ctx);
  ok(/MARCA-CACHE/.test(c.estado.textoTarjetas), "la tarjeta guardada al día se usa tal cual (sin pedirla)");
  // 4) …y si su updated_at ya no coincide, se vuelve a pedir (gana la de Supabase)
  await c.page.evaluate((id0) => {
    const t = JSON.parse(localStorage.getItem("tarjetas_v2"));
    t[id0].h = t[id0].h.replace(/<span class="cliente">/, '<span class="cliente">MARCA-VIEJA ');
    t[id0].u = "2000-01-01T00:00:00+00:00";
    localStorage.setItem("tarjetas_v2", JSON.stringify(t));
  }, id0);
  await c.page.close();
  const d = await abrir(ctx);
  ok(!/MARCA-VIEJA/.test(d.estado.textoTarjetas) && d.pedidos.some(esTarjetas), "tarjeta guardada desactualizada: se pide de nuevo y se ve la vigente", d.pedidos.filter(esTarjetas));
  await d.page.close();
  // 5) sin red, con caché v2
  const e = await abrir(ctx, { bloquear: () => true });
  ok(JSON.stringify(e.estado.visibles) === JSON.stringify(visibles1), "sin red con caché: las mismas tarjetas de la última visita", { visibles: e.estado.visibles });
  ok(/lo último guardado/.test(e.estado.aviso || "") && /Sin conexión · lo último guardado/.test(e.estado.act), "sin red con caché: aviso «lo último guardado»", e.estado);
  // «Ver completadas» sin red: avisa y deja el botón como estaba
  const tc = await e.page.evaluate(async () => {
    const b = document.getElementById("toggle-anteriores"); const antes = b.textContent; b.click();
    await new Promise((r) => setTimeout(r, 1500));
    return { antes, despues: b.textContent, modo: document.body.classList.contains("modo-completadas"), aviso: document.getElementById("estado-online").textContent };
  });
  ok(!tc.modo && tc.antes === tc.despues && /no se pudieron cargar las completadas/.test(tc.aviso), "«Ver completadas» sin red: avisa y no cambia de modo", tc);
  ok(e.errores.length === 0, "sin errores de JS sin red", e.errores);
  await ctx.close();
}
// 6) sin red y solo con la caché v1 (teléfono que nunca abrió la nueva)
{
  const ctx = await nuevoCtx();
  const v = await abrir(ctx, { cual: "viejo" });
  const visV = v.estado.visibles;
  await v.page.close();
  const conV1 = (v.estado.ls["entregas_cache_v1"] || 0) > 100000;
  const n = await abrir(ctx, { bloquear: () => true });
  if (conV1) {
    ok(JSON.stringify(n.estado.visibles) === JSON.stringify(visV) && visV.length > 0, `sin red y solo caché v1: muestra las ${visV.length} tarjetas guardadas por la versión anterior`, { v1: visV.length, nueva: n.estado.visibles.length });
    ok("entregas_cache_v1" in n.estado.ls, "sin red no borra la caché v1 (todavía es lo único que hay)");
  } else {
    ok(JSON.stringify(n.estado.visibles) === JSON.stringify(visV), "sin red tras una visita de la versión publicada: las mismas tarjetas", { publicada: visV.length, nueva: n.estado.visibles.length });
  }
  await ctx.close();
}
// 7) sin red y sin nada
{
  const ctx = await nuevoCtx();
  const n = await abrir(ctx, { bloquear: () => true });
  ok(n.estado.visibles.length === 0 && /Sin conexión con la base\. Cuando vuelva la señal, recarga\./.test(n.estado.aviso || ""), "sin red y sin caché: lista vacía y aviso (antes: 33 entregas de junio-agosto como pendientes)", n.estado);
  await ctx.close();
}
// 8) falla solo el paso 2 (tarjetas): se ve lo que hay y se avisa
{
  const ctx = await nuevoCtx();
  const n = await abrir(ctx, { bloquear: (u) => /card_html&id=in\./.test(u) });
  ok(/puede que falten entregas o que alguna no esté al día/.test(n.estado.aviso || ""), "falla solo el paso 2: aviso de que pueden faltar entregas", n.estado.aviso);
  await ctx.close();
}
// 8b) primera visita de la nueva con la caché v1 en el teléfono y se corta el paso 2: las tarjetas salen de la v1
//     y la v1 NO se borra (era el único respaldo)
{
  const ctx = await nuevoCtx();
  const v = await abrir(ctx, { cual: "viejo" });
  const conV1 = (v.estado.ls["entregas_cache_v1"] || 0) > 100000;
  const visV = v.estado.visibles;
  await v.page.close();
  if (conV1) {
    const n = await abrir(ctx, { bloquear: (u) => /card_html&id=in\./.test(u) });
    ok(JSON.stringify(n.estado.visibles) === JSON.stringify(visV), `se corta el paso 2: las ${visV.length} tarjetas salen igual de la caché v1`, { v1: visV.length, nueva: n.estado.visibles.length });
    ok("entregas_cache_v1" in n.estado.ls, "y la caché v1 no se borra (la carga no fue completa)", n.estado.ls);
    ok(/puede que falten entregas o que alguna no esté al día/.test(n.estado.aviso || ""), "con aviso de que puede no estar al día", n.estado.aviso);
  } else {
    console.log("·  la versión publicada ya no deja la caché v1 (se salta la prueba del corte con v1)");
  }
  await ctx.close();
}
// 8c) tocar «Ver completadas» y, mientras carga, irse a Comisión: no cambia de modo a escondidas
{
  const ctx = await nuevoCtx();
  const n = await abrir(ctx);
  const r = await n.page.evaluate(async () => {
    document.getElementById("toggle-anteriores").click();
    document.querySelector('.vista-btn[data-vista="comision"]').click();
    await new Promise((res) => setTimeout(res, 4000));
    return { modo: document.body.classList.contains("modo-completadas"), boton: document.getElementById("toggle-anteriores").textContent, comisionVisible: !document.querySelector('.vista[data-vista="comision"]').hidden };
  });
  ok(!r.modo && /Ver completadas/.test(r.boton) && r.comisionVisible, "irse a Comisión mientras cargan las completadas: sigue en Comisión y la lista no cambia de modo", r);
  ok(n.errores.length === 0, "sin errores de JS", n.errores);
  await ctx.close();
}
// 9) el ancla del aviso de WhatsApp (#cola del id) centra y hace pulsar la tarjeta
{
  const ctx = await nuevoCtx();
  const a = await abrir(ctx);
  const id = a.estado.visibles[Math.min(5, a.estado.visibles.length - 1)];
  await a.page.close();
  const b = await abrir(ctx, { url: BASE + "?repartidor=p-9t4kqv#" + id.slice(-4) });
  ok(b.estado.resalta.length === 1 && b.estado.resalta[0].slice(-4) === id.slice(-4), "el ancla #" + id.slice(-4) + " resalta su tarjeta", b.estado.resalta);
  await ctx.close();
}
// 10) «Ver completadas» la 2.ª vez que se abre la página: la primera tanda sale del teléfono, sin esperar la red
{
  const ctx = await nuevoCtx();
  const a = await abrir(ctx);
  await a.page.evaluate(() => document.getElementById("toggle-anteriores").click());
  await a.page.waitForFunction(() => document.body.classList.contains("modo-completadas"), null, { timeout: 30000 });
  await a.page.waitForTimeout(2500);
  await a.page.close();
  const b = await abrir(ctx);
  const antes = b.pedidos.length;
  const r = await b.page.evaluate(async () => {
    const t = performance.now(); document.getElementById("toggle-anteriores").click();
    await new Promise((res) => { const chk = () => document.body.classList.contains("modo-completadas") ? res() : setTimeout(chk, 2); chk(); });
    return { ms: Math.round(performance.now() - t), visibles: [...document.querySelectorAll(".card-wrap[data-id]")].filter((c) => c.offsetParent !== null).length };
  });
  const pedidosAlCambiar = b.pedidos.slice(antes);
  ok(r.ms < 150 && r.visibles >= 20, `2.ª visita: «Ver completadas» muestra ${r.visibles} al tiro (${r.ms} ms, sin red de por medio)`, { r, pedidosAlCambiar });
  await ctx.close();
}
console.log(fallos.length ? `\n❌ ${fallos.length} fallo(s)` : "\n✅ todos los casos borde en verde");
await browser.close(); server.close();
