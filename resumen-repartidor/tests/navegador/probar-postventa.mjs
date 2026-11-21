// La página de postventa en un Chrome de verdad, con los datos REALES de Supabase (solo lecturas):
// toda escritura (anotaciones, fotos, puntos del mapa) se intercepta y se anota, nunca llega a la base,
// y OpenStreetMap (búsqueda de direcciones) se responde con un punto de mentira.
//
// Uso (desde la raíz del repo): node resumen-repartidor/tests/navegador/probar-postventa.mjs [carpeta-capturas]
import { createRequire } from "node:module";
import { createServer } from "node:http";
import { readFileSync, existsSync, statSync, mkdirSync } from "node:fs";
import { join, extname, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir, tmpdir } from "node:os";
const require = createRequire(import.meta.url);
function resolverPlaywright() {
  const cands = ["playwright-core", "playwright", join(homedir(), "SaSS/DIXDY/clientes/destaperapido/node_modules/playwright-core")];
  try { for (const d of require("node:fs").readdirSync(join(homedir(), ".npm/_npx"))) cands.push(join(homedir(), ".npm/_npx", d, "node_modules/playwright-core")); } catch { /* sin npx */ }
  for (const p of cands) { try { return require(p); } catch { /* siguiente */ } }
  console.error("✗ No encuentro playwright-core. Corre una vez: npx playwright@latest --version"); process.exit(2);
}
const { chromium } = resolverPlaywright();
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const CARPETA = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const CAPTURAS = process.argv[2] || join(tmpdir(), "postventa-capturas");
// la clave del enlace especial vive fuera del repo (es público)
const CLAVE = (process.env.POSTVENTA_CLAVE || readFileSync(join(homedir(), ".dixdy/postventa-clave"), "utf8")).trim();
mkdirSync(CAPTURAS, { recursive: true });

const TIPOS = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".png": "image/png" };
const server = createServer((req, res) => {
  const url = new URL(req.url, "http://x");
  const f = join(CARPETA, url.pathname.replace(/^\/resumen-repartidor\//, ""));
  if (!existsSync(f) || !statSync(f).isFile()) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "Content-Type": TIPOS[extname(f)] || "application/octet-stream", "Cache-Control": "no-store" });
  res.end(readFileSync(f));
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const BASE = `http://127.0.0.1:${server.address().port}/resumen-repartidor/postventa.html`;
const browser = await chromium.launch(existsSync(CHROME) ? { executablePath: CHROME, headless: true } : { headless: true });
const fallos = [];
const sinCabecera = [];
const ok = (c, msg, det) => { console.log((c ? "✅ " : "❌ ") + msg + (!c && det !== undefined ? "\n    → " + JSON.stringify(det).slice(0, 500) : "")); if (!c) fallos.push(msg); };

async function abrir(url) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: "es-CL", timezoneId: "America/Santiago" });
  const page = await ctx.newPage();
  const pedidos = [], escrituras = [], errores = [], osm = [];
  page.on("pageerror", (e) => errores.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error" && !/tile|favicon|ERR_FAILED/i.test(m.text())) errores.push("console: " + m.text()); });
  await page.route(/supabase\.co/, async (route) => {
    const r = route.request();
    const u = decodeURIComponent(r.url().replace(/^https:\/\/[^/]+/, "")).replace(/[?&]apikey=[^&]+/, "");
    pedidos.push(r.method() + " " + u);
    if (/postventa_/.test(u) && r.headers()["x-clave"] !== CLAVE) sinCabecera.push(r.method() + " " + u);
    // los puntos ya guardados se esconden: así la prueba ve a la página buscar en OSM como la primera vez
    if (r.method() === "GET" && /postventa_geo/.test(u)) { await route.fulfill({ status: 200, headers: { "access-control-allow-origin": "*", "content-type": "application/json" }, body: "[]" }); return; }
    if (["GET", "HEAD", "OPTIONS"].includes(r.method())) { await route.continue(); return; }
    const cuerpo = r.postData() || "";
    escrituras.push({ metodo: r.method(), ruta: u, cuerpo: /^\{|^\[/.test(cuerpo) ? JSON.parse(cuerpo) : `(${cuerpo.length} bytes)` });
    let resp = "";
    if (/postventa_evento/.test(u) && r.method() === "POST") {
      resp = JSON.stringify([Object.assign({ id: "prueba-" + escrituras.length, anulado: false, created_at: new Date().toISOString() }, JSON.parse(cuerpo))]);
    } else if (/postventa_evento/.test(u)) resp = "[]";
    else if (/storage/.test(u)) resp = JSON.stringify({ Key: "x" });
    await route.fulfill({ status: 201, headers: { "access-control-allow-origin": "*", "content-type": "application/json" }, body: resp });
  });
  await page.route(/nominatim\.openstreetmap\.org/, async (route) => {
    osm.push(decodeURIComponent(route.request().url()));
    await route.fulfill({ status: 200, headers: { "access-control-allow-origin": "*", "content-type": "application/json" },
      body: JSON.stringify([{ lat: "-33.40", lon: "-70.55", place_rank: 30 }]) });
  });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  return { ctx, page, pedidos, escrituras, errores, osm };
}

// 1) sin clave, con la clave vieja de entregas o con una inventada: nada a la base
for (const [nombre, q] of [["sin clave", ""], ["con la clave de entregas", "?repartidor=p-9t4kqv"], ["con una clave inventada", "?k=abcdefghjkmnpq"]]) {
  const r = await abrir(BASE + q);
  await r.page.waitForTimeout(1200);
  const txt = await r.page.textContent("main");
  ok(/incompleto/i.test(txt) && r.pedidos.length === 0, nombre + ": «enlace incompleto» y cero pedidos a Supabase", { txt, pedidos: r.pedidos });
  await r.ctx.close();
}

// 2) con clave: la lista con los datos reales
const r = await abrir(BASE + "?k=" + CLAVE);
const { page } = r;
await page.waitForSelector(".card", { timeout: 60000 });
await page.waitForFunction(() => /al día/.test(document.getElementById("act").textContent), null, { timeout: 60000 });
const lista = await page.evaluate(() => ({
  resumen: document.getElementById("resumen").textContent,
  secciones: [...document.querySelectorAll("h2.sec")].map((h) => h.innerText.replace(/\s+/g, " ")),
  fichas: document.querySelectorAll(".card").length,
  chips: [...document.querySelectorAll(".chip-f")].map((c) => c.innerText.replace(/\s+/g, " ")),
  anchoMax: document.documentElement.scrollWidth,
  sinLlegar: [...document.querySelectorAll(".card")].filter((c) => !c.querySelector("a.b.p")).map((c) => c.dataset.id),
}));
console.log("   ", lista.resumen, "·", lista.secciones.join(" | "), "·", lista.chips.join(" | "));
ok(lista.fichas > 10, "la lista trae los servicios en terreno", lista);
ok(lista.anchoMax <= 391, "nada se sale del ancho del teléfono (390 px)", lista.anchoMax);
ok(lista.sinLlegar.length === 0, "todas las fichas tienen «Cómo llegar»", lista.sinLlegar);
await page.screenshot({ path: join(CAPTURAS, "1-lista.png") });

// 3) extender una que terminó el plazo (pide el nombre la primera vez)
const idRevisar = await page.evaluate(() => { const c = document.querySelector("h2.sec.rojo + .sec-ayuda + .card, h2.sec.rojo + .card"); return c && c.dataset.id; });
ok(!!idRevisar, "hay al menos una ficha con el plazo terminado", idRevisar);
if (idRevisar) {
  await page.click(`[data-id="${idRevisar}"] [data-acc="extender"]`);
  await page.waitForSelector("#q-nombre");
  await page.screenshot({ path: join(CAPTURAS, "2-quien.png") });
  await page.fill("#q-nombre", "Prueba");
  await page.click(".hoja button[type=submit]");
  await page.waitForSelector("input[name=ext]");
  await page.screenshot({ path: join(CAPTURAS, "3-extender.png") });
  await page.fill("#e-nota", "renovó por llamada (prueba)");
  await page.click(".hoja button[type=submit]");
  await page.waitForSelector(".velo", { state: "detached" });
  const ev = r.escrituras.filter((e) => /postventa_evento/.test(e.ruta)).pop();
  ok(ev && ev.cuerpo.tipo === "extension" && ev.cuerpo.entrega_id === idRevisar && ev.cuerpo.por === "Prueba" && /^\d{4}-\d{2}-\d{2}$/.test(ev.cuerpo.fecha),
    "Extender guarda una extensión con fecha, quién y nota", ev);
  const seccion = await page.evaluate((id) => { const c = document.getElementById("f-" + id); let h = c && c.previousElementSibling; while (h && h.tagName !== "H2") h = h.previousElementSibling; return h && h.innerText; }, idRevisar);
  ok(seccion && !/Terminó/i.test(seccion), "tras extender, la ficha sale de «Terminó el plazo»", seccion);
}

// 4) limpieza hecha con foto
const idLimpia = await page.evaluate(() => { const c = [...document.querySelectorAll(".card")].find((x) => /Limpieza\s+(atrasada|toca)/.test(x.querySelector(".filas").innerText)); return c && c.dataset.id; });
ok(!!idLimpia, "hay una ficha a la que le toca limpieza", idLimpia);
if (idLimpia) {
  await page.click(`[data-id="${idLimpia}"] [data-acc="limpieza"]`);
  await page.waitForSelector("#f-foto", { state: "attached" });
  // una foto chica de verdad (PNG 2x2) para el input
  const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8z8DAwMDAxMDAwMDAAAANHQEDasKb6QAAAABJRU5ErkJggg==", "base64");
  await page.setInputFiles("#f-foto", { name: "bano.png", mimeType: "image/png", buffer: png });
  await page.waitForSelector("#f-prev img", { timeout: 10000 });
  await page.screenshot({ path: join(CAPTURAS, "4-limpieza.png") });
  await page.click(".hoja button[type=submit]");
  await page.waitForSelector(".velo", { state: "detached" });
  const sube = r.escrituras.find((e) => /storage\/v1\/object\/postventa-fotos\//.test(e.ruta));
  const ev = r.escrituras.filter((e) => /postventa_evento/.test(e.ruta)).pop();
  ok(!!sube && ev.cuerpo.tipo === "limpieza" && ev.cuerpo.foto && ev.cuerpo.foto.startsWith(idLimpia + "/"), "Limpieza hecha sube la foto y guarda la limpieza con su ruta", { sube, ev });
  const linea = await page.evaluate((id) => document.querySelector(`#f-${CSS.escape(id)} .filas`).innerText, idLimpia);
  ok(/al día/.test(linea), "tras la limpieza, la ficha queda al día", linea);
}

// 5) retirado: sale de la lista
const idRetiro = await page.evaluate(() => { const c = [...document.querySelectorAll(".card")].pop(); return c && c.dataset.id; });
await page.click(`[data-id="${idRetiro}"] [data-acc="retiro"]`);
await page.waitForSelector("#r-fecha");
await page.click(".hoja button[type=submit]");
await page.waitForSelector(".velo", { state: "detached" });
ok(!(await page.$(`#f-${idRetiro.replace(/[^a-z0-9-]/gi, "\\$&")}`)), "Retirado saca la ficha de los activos");

// 6) anular desde el historial (lo vuelve a poner)
await page.fill("#buscar", idRetiro);
await page.waitForTimeout(400);
await page.evaluate((id) => { const d = document.querySelector(`#f-${CSS.escape(id)} details.mas`); d.open = true; }, idRetiro);
await page.click(`[data-id="${idRetiro}"] [data-acc="anular"]`);
await page.click(".hoja button[type=submit]");
await page.waitForSelector(".velo", { state: "detached" });
const anula = r.escrituras.filter((e) => e.metodo === "PATCH").pop();
ok(anula && anula.cuerpo.anulado === true && /postventa_evento\?id=eq\./.test(anula.ruta), "Anular manda solo anulado=true", anula);
await page.fill("#buscar", "");
await page.waitForTimeout(400);

// 7) el mapa
await page.click('[data-tab="mapa"]');
await page.waitForSelector(".leaflet-interactive", { timeout: 30000 });
await page.waitForTimeout(4000);
const mapa = await page.evaluate(() => ({
  puntos: document.querySelectorAll(".leaflet-interactive").length,
  estado: document.getElementById("mapa-estado").hidden ? "" : document.getElementById("mapa-estado").textContent,
  alto: document.getElementById("mapa").getBoundingClientRect().height,
}));
ok(mapa.puntos > 10 && mapa.alto > 300, "el mapa muestra los baños", mapa);
ok(r.osm.length >= 1 && r.osm.length <= 6, "busca direcciones en OSM de a una por segundo (no en ráfaga)", r.osm.length);
const geo = r.escrituras.filter((e) => /postventa_geo/.test(e.ruta));
ok(geo.length >= 1 && geo[0].cuerpo.lat !== undefined, "guarda el punto encontrado para la próxima vez", geo[0]);
await page.screenshot({ path: join(CAPTURAS, "5-mapa.png") });
await page.click(".leaflet-interactive");
await page.waitForSelector(".pop", { timeout: 5000 });
await page.screenshot({ path: join(CAPTURAS, "6-mapa-ficha.png") });
await page.click(".pop [data-ir]");
await page.waitForTimeout(800);
ok(await page.evaluate(() => !document.getElementById("vista-lista").hidden), "«Ver ficha» vuelve a la lista");

// 8) buscar
await page.fill("#buscar", "las condes");
await page.waitForTimeout(400);
ok((await page.$$(".card")).length >= 1, "el buscador encuentra por nombre");

ok(r.errores.length === 0, "sin errores de JavaScript", r.errores);
ok(sinCabecera.length === 0, "todo pedido a las tablas de postventa lleva la clave", sinCabecera);
const fotos = r.escrituras.filter((e) => /storage\/v1\/object\/postventa-fotos\//.test(e.ruta));
ok(fotos.every((e) => /-[0-9a-f]{18}\.jpg$/.test(e.ruta)), "el nombre de cada foto lleva una parte al azar", fotos.map((e) => e.ruta));
const raras = r.escrituras.filter((e) => !/postventa_evento|postventa_geo|storage\/v1\/object\/postventa-fotos/.test(e.ruta));
ok(raras.length === 0, "solo escribe en sus tablas (nunca en entrega ni entrega_estado)", raras);
console.log(`\ncapturas en ${CAPTURAS}`);
await browser.close();
server.close();
if (fallos.length) { console.log(`\n❌ ${fallos.length} falla(s)`); process.exit(1); }
console.log("\n✅ todo bien");
