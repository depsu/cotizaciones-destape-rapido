// ¿La página nueva muestra EXACTAMENTE lo mismo que la vieja? Mismos datos reales de Supabase
// (solo GET; toda escritura se intercepta y se anota, nunca llega a la base). Compara cabecera,
// reparto de hoy, cada día con su barra, cada tarjeta visible en orden con sus clases y su texto,
// la pestaña Comisión, la del Mes, el modo completadas, el modal «Ver toda la info», y lo que se
// escribiría al tocar Entregado / Cobrado / reagendar.
// Uso (desde la raíz del repo): node resumen-repartidor/tests/navegador/probar-equivalencia.mjs <listado-publicado.html> <listado-nuevo.html> [p-9t4kqv|r-…]
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
const [viejo, nuevo, VISTA = "p-9t4kqv"] = process.argv.slice(2);
const htmls = { viejo: readFileSync(viejo), nuevo: readFileSync(nuevo) };
let actual = "viejo";
const server = createServer((req, res) => {
  const url = new URL(req.url, "http://x");
  if (url.pathname.endsWith("/listado.html")) { res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" }); res.end(htmls[actual]); return; }
  const f = join(REPO, url.pathname.replace(/^\/resumen-repartidor\//, ""));
  if (!existsSync(f) || !statSync(f).isFile()) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "Content-Type": extname(f) === ".png" ? "image/png" : "application/octet-stream" }); res.end(readFileSync(f));
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const URL_PAG = `http://127.0.0.1:${server.address().port}/resumen-repartidor/listado.html?repartidor=${VISTA}`;
const browser = await lanzar();

// Foto de lo que se ve (normalizada: sin la hora de «Actualizado»)
function foto() {
  const vis = (el) => !!el && el.offsetParent !== null && getComputedStyle(el).visibility !== "hidden";
  const txt = (el) => (el ? el.innerText.replace(/Actualizado \d\d:\d\d/g, "Actualizado HH:MM").replace(/\s+/g, " ").trim() : null);
  const clases = (el) => [...el.classList].filter((c) => c !== "card-nueva").sort().join(".");
  const v = document.querySelector('.vista[data-vista="entregas"]');
  const dias = [...v.querySelectorAll("section[data-fecha]")].filter(vis).map((s) => ({
    fecha: s.getAttribute("data-fecha"),
    titulo: txt(s.querySelector("h2")),
    barra: (s.querySelector(".prog-fill") || {}).style ? s.querySelector(".prog-fill").style.width : null,
    tarjetas: [...s.querySelectorAll(".card-wrap[data-id]")].filter(vis).map((c) => ({ id: c.getAttribute("data-id"), clases: clases(c), texto: txt(c) })),
  }));
  return {
    cabecera: txt(document.querySelector("header")),
    aviso: vis(document.getElementById("estado-online")) ? txt(document.getElementById("estado-online")) : null,
    reparto: vis(document.getElementById("recomendacion-hoy")) ? txt(document.getElementById("recomendacion-hoy")) : null,
    boton: vis(document.getElementById("toggle-anteriores")) ? txt(document.getElementById("toggle-anteriores")) : null,
    modo: vis(document.getElementById("modo-titulo")) ? txt(document.getElementById("modo-titulo")) : null,
    dias,
  };
}
const esperarQuieto = async (page) => {
  // espera a que el número de tarjetas visibles deje de cambiar (la nueva trae las completadas en tandas)
  let antes = -1;
  for (let i = 0; i < 80; i++) {
    const n = await page.evaluate(() => [...document.querySelectorAll(".card-wrap[data-id]")].filter((c) => c.offsetParent !== null).length);
    if (n === antes) { await page.waitForTimeout(400); const n2 = await page.evaluate(() => [...document.querySelectorAll(".card-wrap[data-id]")].filter((c) => c.offsetParent !== null).length); if (n2 === n) return n; }
    antes = n; await page.waitForTimeout(250);
  }
  return antes;
};

let F_ms_modo = 0, F_ms_todas = 0;
async function recorrer(cual) {
  actual = cual;
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: "es-CL", timezoneId: "America/Santiago" });
  const page = await ctx.newPage();
  const escrituras = [];
  const errores = [];
  page.on("pageerror", (e) => errores.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errores.push(m.text()); });
  page.on("dialog", (d) => d.accept());
  await page.route(/supabase\.co/, async (route) => {
    const r = route.request();
    if (["GET", "HEAD", "OPTIONS"].includes(r.method())) { await route.continue(); return; }
    escrituras.push(r.method() + " " + r.url().replace(/^https:\/\/[^/]+/, "").replace(/[?&]apikey=[^&]+/, "") + " " + r.postData());
    await route.fulfill({ status: r.method() === "PATCH" ? 204 : 201, headers: { "access-control-allow-origin": "*" }, body: "" });
  });
  const F = {};
  await page.goto(URL_PAG, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.body.classList.contains("listo"), null, { timeout: 60000 });
  await page.waitForTimeout(1500);
  F.lista = await page.evaluate(foto);
  await page.click('.vista-btn[data-vista="comision"]'); await page.waitForTimeout(300);
  F.comision = await page.evaluate(() => document.querySelector('.vista[data-vista="comision"]').innerText.replace(/\s+/g, " ").trim());
  await page.click('.vista-btn[data-vista="mes"]'); await page.waitForTimeout(300);
  F.mes = await page.evaluate(() => document.querySelector('.vista[data-vista="mes"]').innerText.replace(/\s+/g, " ").trim());
  F.meses = await page.evaluate(() => [...document.querySelectorAll("#mes-select option")].map((o) => o.value));
  // otro mes (el segundo de la lista)
  const m2 = F.meses[1];
  if (m2) { await page.selectOption("#mes-select", m2); await page.waitForTimeout(200); F.mes2 = await page.evaluate(() => document.getElementById("mes-panel").innerText.replace(/\s+/g, " ").trim()); }
  await page.click('.vista-btn[data-vista="entregas"]'); await page.waitForTimeout(300);
  // modo completadas
  const hayComp = await page.evaluate(() => { const b = document.getElementById("toggle-anteriores"); return !!b && !b.hidden; });
  if (hayComp) {
    const N = await page.evaluate(() => Number((/\((\d+)\)/.exec(document.getElementById("toggle-anteriores").textContent) || [])[1] || 0));
    F.nCompletadas = N;
    const t0 = Date.now();
    await page.click("#toggle-anteriores");
    await page.waitForFunction(() => document.body.classList.contains("modo-completadas"), null, { timeout: 60000 });
    F_ms_modo = Date.now() - t0;
    await page.waitForFunction((N) => [...document.querySelectorAll(".card-wrap[data-id]")].filter((c) => c.offsetParent !== null).length >= N, N, { timeout: 60000 }).catch(() => {});
    F_ms_todas = Date.now() - t0;
    await esperarQuieto(page);
    F.completadas = await page.evaluate(foto);
    await page.evaluate(() => document.getElementById("toggle-anteriores").click());
    await page.waitForTimeout(600);
    F.vuelta = await page.evaluate(foto);
  }
  // «Ver toda la info» de la primera comisión ya pagada (una completada que en la nueva no está en la lista)
  await page.click('.vista-btn[data-vista="comision"]'); await page.waitForTimeout(300);
  F.infoId = await page.evaluate(() => { const b = document.querySelector(".com-pagada .com-info:not(.pub-info)") || document.querySelector(".com-info:not(.pub-info)"); if (!b) return null; b.click(); return b.getAttribute("data-id"); });
  if (F.infoId) {
    await page.waitForFunction(() => { const m = document.querySelector(".modal .info-clon"); return m && !/Cargando…/.test(m.innerText); }, null, { timeout: 30000 });
    F.info = await page.evaluate(() => document.querySelector(".modal").innerText.replace(/\s+/g, " ").trim());
    await page.click(".modal .cancelar");
  }
  await page.click('.vista-btn[data-vista="entregas"]'); await page.waitForTimeout(300);
  // acciones (escrituras interceptadas): Entregado y Cobrado en la primera pendiente visible con botones
  F.idAccion = await page.evaluate(() => {
    const c = [...document.querySelectorAll(".card-wrap[data-id]")].find((c) => c.offsetParent !== null && c.querySelector('.gt-estados:not([hidden]) .est-btn[data-estado="entregado"]:not(.activo)'));
    return c && c.getAttribute("data-id");
  });
  if (F.idAccion) {
    const sel = (e) => `.card-wrap[data-id="${F.idAccion}"] .est-btn[data-estado="${e}"]`;
    await page.click(sel("entregado")); await page.waitForTimeout(500);
    F.trasEntregado = await page.evaluate(foto);
    await page.click(sel("cobrado")); await page.waitForTimeout(3500);
    F.trasCobrado = await page.evaluate(foto);
  }
  // reagendar la primera visible con fecha a +3 días
  F.idReag = await page.evaluate(() => {
    const c = [...document.querySelectorAll(".card-wrap[data-id]")].find((c) => c.offsetParent !== null && c.querySelector(".fecha-input"));
    if (!c) return null;
    const inp = c.querySelector(".fecha-input"); const d = new Date(); d.setDate(d.getDate() + 3);
    inp.value = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
    inp.dispatchEvent(new Event("change", { bubbles: true }));
    return c.getAttribute("data-id");
  });
  await page.waitForTimeout(900);
  F.trasReagendar = await page.evaluate(foto);
  F.comisionFinal = await page.evaluate(() => { document.querySelector('.vista-btn[data-vista="comision"]').click(); return document.querySelector('.vista[data-vista="comision"]').innerText.replace(/\s+/g, " ").trim(); });
  console.log(`[${cual}] completadas: modo a los ${F_ms_modo} ms, todas a los ${F_ms_todas} ms`);
  F.escrituras = escrituras;
  F.errores = errores;
  await ctx.close();
  return F;
}

const A = await recorrer("viejo");
const B = await recorrer("nuevo");
let difs = 0;
function comparar(ruta, a, b) {
  if (JSON.stringify(a) === JSON.stringify(b)) return;
  if (a && b && typeof a === "object" && typeof b === "object") {
    const ks = new Set([...Object.keys(a), ...Object.keys(b)]);
    for (const k of ks) comparar(ruta + "." + k, a[k], b[k]);
    return;
  }
  difs++;
  if (difs <= 40) console.log(`≠ ${ruta}\n   viejo: ${JSON.stringify(a)?.slice(0, 300)}\n   nuevo: ${JSON.stringify(b)?.slice(0, 300)}`);
}
for (const k of Object.keys(A)) comparar(k, A[k], B[k]);
const n = (f) => (f ? f.dias.reduce((s, d) => s + d.tarjetas.length, 0) : 0);
console.log(`\nvista ${VISTA}: lista ${n(A.lista)}/${n(B.lista)} tarjetas · completadas ${n(A.completadas)}/${n(B.completadas)} · escrituras ${A.escrituras.length}/${B.escrituras.length} · errores ${A.errores.length}/${B.errores.length}`);
console.log(difs ? `❌ ${difs} diferencia(s)` : "✅ IDÉNTICAS (todo lo comparado)");
await browser.close(); server.close();
