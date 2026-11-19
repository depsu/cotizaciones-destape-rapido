// Clientes perdidos (19-nov-2026): al pie de Entregas y al final del Mes, con los datos REALES de
// Supabase (solo GET; toda escritura se intercepta y nunca llega a la base).
// Uso (desde la raíz del repo):
//   curl -s https://depsu.github.io/cotizaciones-destape-rapido/resumen-repartidor/listado.html -o /tmp/publicado.html
//   python3 resumen-repartidor/scripts/generar_listado.py /tmp/nuevo.html
//   node resumen-repartidor/tests/navegador/probar-perdidos.mjs /tmp/publicado.html /tmp/nuevo.html [carpeta-capturas]
import { createRequire } from "node:module";
import { createServer } from "node:http";
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
const require = createRequire(import.meta.url);
function resolverPlaywright() {
  const cands = ["playwright-core", "playwright", join(homedir(), "SaSS/DIXDY/clientes/destaperapido/node_modules/playwright-core")];
  try { for (const d of require("node:fs").readdirSync(join(homedir(), ".npm/_npx"))) cands.push(join(homedir(), ".npm/_npx", d, "node_modules/playwright-core")); } catch { /* sin npx */ }
  for (const p of cands) { try { return require(p); } catch { /* siguiente */ } }
  console.error("✗ No encuentro playwright-core. Corre una vez: npx playwright@latest --version"); process.exit(2);
}
const { chromium } = resolverPlaywright();
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const [viejo, nuevo, capturas] = process.argv.slice(2);
const htmls = { viejo: readFileSync(viejo), nuevo: readFileSync(nuevo) };
let actual = "nuevo";
const server = createServer((req, res) => { res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" }); res.end(htmls[actual]); });
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const BASE = `http://127.0.0.1:${server.address().port}/resumen-repartidor/listado.html`;
const browser = await chromium.launch(existsSync(CHROME) ? { executablePath: CHROME, headless: true } : { headless: true });
const fallos = [];
const ok = (c, msg, det) => { console.log((c ? "✅ " : "❌ ") + msg + (!c && det !== undefined ? "\n    → " + JSON.stringify(det).slice(0, 600) : "")); if (!c) fallos.push(msg); };

async function abrir(cual, clave = "p-9t4kqv") {
  actual = cual;
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, locale: "es-CL", timezoneId: "America/Santiago" });
  const page = await ctx.newPage();
  const pedidos = [], errores = [], escrituras = [];
  page.on("pageerror", (e) => errores.push(String(e)));
  await page.route(/supabase\.co/, async (route) => {
    const r = route.request();
    pedidos.push({ m: r.method(), u: decodeURIComponent(r.url()).replace(/[?&]apikey=[^&]+/, ""), t: Date.now() });
    if (["GET", "HEAD", "OPTIONS"].includes(r.method())) { await route.continue(); return; }
    escrituras.push(r.method() + " " + r.url());
    await route.fulfill({ status: 201, headers: { "access-control-allow-origin": "*" }, body: "" });
  });
  await page.goto(BASE + "?repartidor=" + clave, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.body.classList.contains("listo"), null, { timeout: 60000 });
  const listoEn = Date.now();
  await page.waitForTimeout(3000);
  return { ctx, page, pedidos, errores, escrituras, listoEn };
}
const totalesMes = (page) => page.evaluate(async () => {
  document.querySelector('.vista-btn[data-vista="mes"]').click();
  await new Promise((r) => setTimeout(r, 200));
  const sel = document.getElementById("mes-select");
  const out = {};
  for (const o of [...sel.options]) {
    sel.value = o.value; sel.dispatchEvent(new Event("change"));
    const p = document.getElementById("mes-panel");
    out[o.value] = {
      cifras: [...p.querySelectorAll(".mes-c .v")].map((x) => x.textContent),
      entregas: p.querySelectorAll(".mes-lista:not(.perd) .mes-f").length,
      perdTit: (p.querySelector(".mes-tit.perd") || {}).textContent || "",
      perdidos: [...p.querySelectorAll(".mes-lista.perd .mes-f")].map((f) => f.querySelector(".cli").childNodes[0].textContent),
    };
  }
  return out;
});

// ── 1 · la página principal (Pindus) ─────────────────────────────────────────────
const n = await abrir("nuevo");
const pie = await n.page.evaluate(() => {
  const p = document.getElementById("perdidos-pie");
  const v = document.querySelector('.vista[data-vista="entregas"]');
  return { hidden: p.hidden, ultimo: v.lastElementChild === p, boton: (p.querySelector(".ver-perdidos") || {}).textContent || "" };
});
ok(!pie.hidden && /✕ Ver clientes perdidos \(\d+\)/.test(pie.boton), "al pie de Entregas: «" + pie.boton + "»", pie);
ok(pie.ultimo, "el botón queda al final de todo (después del último día)");
const pPerd = n.pedidos.find((p) => /eliminado=eq\.true/.test(p.u));
ok(!!pPerd && pPerd.t >= n.listoEn - 50, "las que retiró el bot se piden DESPUÉS de mostrar la página", pPerd);
ok(!n.pedidos.some((p) => /eliminado=eq\.true/.test(p.u) && /card_html/.test(p.u)), "y sin las tarjetas armadas (solo los datos)");

if (capturas) await n.page.evaluate(() => document.getElementById("perdidos-pie").scrollIntoView({ block: "center" }));
if (capturas) await n.page.screenshot({ path: join(capturas, "1-pie-cerrado.png") });
await n.page.click(".ver-perdidos");
await n.page.waitForTimeout(600);
const lista = await n.page.evaluate(() => ({
  boton: document.querySelector(".ver-perdidos").textContent,
  hero: document.querySelector(".perd-hero") ? document.querySelector(".perd-hero").innerText : "",
  meses: [...document.querySelectorAll(".perd-mes")].map((x) => x.innerText.replace(/\s+/g, " ")),
  filas: [...document.querySelectorAll(".perd-item")].map((x) => ({
    cli: x.querySelector(".perd-cli").textContent, motivo: x.querySelector(".perd-motivo").textContent,
    monto: x.querySelector(".perd-monto").innerText.replace(/\s+/g, " "), texto: x.innerText,
  })),
}));
if (capturas) await n.page.screenshot({ path: join(capturas, "2-pie-abierto.png") });
const N = Number((pie.boton.match(/\((\d+)\)/) || [])[1]);
ok(lista.filas.length === N && N > 0, `abierto: ${lista.filas.length} clientes perdidos (el botón dice ${N})`);
ok(/Cerrar clientes perdidos/.test(lista.boton), "el botón pasa a «Cerrar clientes perdidos»");
ok(/Clientes perdidos/i.test(lista.hero) && /\$[\d.]+/.test(lista.hero), "arriba el total perdido: " + lista.hero.replace(/\s+/g, " "));
const nombres = lista.filas.map((f) => f.cli);
const tiene = (re) => nombres.some((x) => re.test(x));
ok(!tiene(/prueba/i), "sin tarjetas de prueba", nombres.filter((x) => /prueba/i.test(x)));
ok(!lista.filas.some((f) => /\+?56930153632/.test(f.texto)), "sin el WhatsApp de Alejandro (pruebas)");
// (los casos con nombre se revisaron a mano el 19-nov; acá van las reglas, sin datos de clientes: el repo es público)
// la lista viene agrupada por mes: dentro de un mes, nadie repetido por teléfono
const repetidos = await n.page.evaluate(() => {
  const vistos = {}, rep = [];
  let mes = "";
  for (const x of document.querySelectorAll("#perdidos-pie > .perd-mes, #perdidos-pie > .perd-item")) {
    if (x.classList.contains("perd-mes")) { mes = x.innerText; continue; }
    const t = ((x.innerText.match(/\+(\d{8,})/) || [])[1] || "").slice(-8);
    if (!t) continue;
    const k = mes + "|" + t;
    if (vistos[k]) rep.push(k);
    vistos[k] = 1;
  }
  return rep;
});
ok(repetidos.length === 0, "nadie sale dos veces en el mismo mes (reemplazadas y perdidas dos veces se juntan)", repetidos);
const conNota = lista.filas.filter((f) => !/Canceló con el bot|Se sacó de la lista/.test(f.motivo));
ok(conNota.every((f) => f.motivo.length > 3), `las que tienen nota la muestran como motivo (${conNota.length})`);
ok(lista.filas.some((f) => /Canceló con el bot/.test(f.motivo)) && lista.filas.some((f) => /Se sacó de la lista/.test(f.motivo)), "los dos orígenes: lo que sacó el bot y lo que se sacó desde la página");
ok(lista.filas.every((f) => /\$[\d.]+/.test(f.monto)) && !lista.filas.some((f) => /undefined|NaN|null|\[object/.test(f.texto)), "cada uno con su monto, sin undefined ni NaN");
ok(lista.meses.length >= 2 && /^Nov 2026/i.test(lista.meses[0]), "agrupados por mes, lo más nuevo arriba: " + lista.meses.slice(0, 3).join(" | "));
ok(!lista.filas.some((f) => /[;«»~]/.test(f.motivo)), "los motivos sin ; « » ~");

// ── 2 · el mes: las cifras de siempre no cambian, los perdidos van aparte al final ──
const mesNuevo = await totalesMes(n.page);
if (capturas) {
  await n.page.evaluate(() => { const s = document.getElementById("mes-select"); s.value = "2026-11"; s.dispatchEvent(new Event("change")); });
  await n.page.evaluate(() => document.querySelector(".mes-tit.perd").scrollIntoView({ block: "start" }));
  await n.page.waitForTimeout(200);
  await n.page.screenshot({ path: join(capturas, "3-mes-perdidos.png") });
}
const v = await abrir("viejo");
const mesViejo = await totalesMes(v.page);
const igual = Object.keys(mesViejo).every((m) => mesNuevo[m] && JSON.stringify(mesNuevo[m].cifras) === JSON.stringify(mesViejo[m].cifras) && mesNuevo[m].entregas === mesViejo[m].entregas);
ok(igual && Object.keys(mesViejo).length === Object.keys(mesNuevo).length, "Mes: total, cobrado, por cobrar y la lista de cada mes, idénticos a la versión publicada", { viejo: mesViejo["2026-11"], nuevo: mesNuevo["2026-11"] });
const nov = mesNuevo["2026-11"];
ok(nov && nov.perdidos.length > 0 && /clientes? perdidos?/.test(nov.perdTit), `Nov 2026: «${nov && nov.perdTit.replace(/\s+/g, " ")}» al final`, nov);
const sumaMeses = Object.values(mesNuevo).reduce((s, m) => s + m.perdidos.length, 0);
ok(sumaMeses === N, `la suma de los perdidos de cada mes (${sumaMeses}) es la lista completa (${N})`);
ok(n.errores.length === 0 && v.errores.length === 0, "sin errores de JS", n.errores);
ok(n.escrituras.length === 0, "mirar no escribe nada en la base", n.escrituras);

// ── 3 · sacar una tarjeta desde la página la suma al tiro ────────────────────────
const s = await abrir("nuevo");
const antes = await s.page.evaluate(() => Number((document.querySelector(".ver-perdidos").textContent.match(/\((\d+)\)/) || [])[1]));
const sacada = await s.page.evaluate(async () => {
  const c = [...document.querySelectorAll(".card-wrap[data-id]")].find((x) => x.offsetParent !== null && x.querySelector(".btn-eliminar"));
  if (!c) return null;
  c.querySelector(".btn-eliminar").click();
  await new Promise((r) => setTimeout(r, 150));
  const si = [...c.querySelectorAll("button")].find((b) => /^(Sí|Si|Eliminar)/i.test(b.textContent.trim()));
  if (si) si.click();
  return c.getAttribute("data-id");
});
await s.page.waitForTimeout(1200);
const despues = await s.page.evaluate(() => Number((document.querySelector(".ver-perdidos").textContent.match(/\((\d+)\)/) || [])[1]));
ok(!!sacada && despues === antes + 1, `sacar una tarjeta (${sacada}) la suma al tiro: ${antes} → ${despues}`);
ok(s.escrituras.length >= 1 && s.escrituras.every((e) => /entrega_estado/.test(e)), "esa escritura (interceptada) es la de siempre a entrega_estado", s.escrituras);

// ── 4 · la página del relevo solo ve los suyos ───────────────────────────────────
const r = await abrir("nuevo", "r-x7m2hd");
const rel = await r.page.evaluate(async () => {
  const b = document.querySelector(".ver-perdidos");
  if (!b) return { n: 0, nombres: [] };
  b.click(); await new Promise((x) => setTimeout(x, 300));
  return { n: document.querySelectorAll(".perd-item").length, nombres: [...document.querySelectorAll(".perd-cli")].map((x) => x.textContent) };
});
ok(rel.nombres.every((x) => !nombres.includes(x)), `relevo: solo sus perdidos (${rel.n}: ${rel.nombres.join(", ")})`, rel);
ok(!rel.nombres.some((x) => /no conectado/i.test(x)), "relevo: sin la tarjeta «no conectado» (prueba)");
ok(r.errores.length === 0, "relevo sin errores de JS", r.errores);

await browser.close(); server.close();
console.log("\nPerdidos (página principal):");
lista.filas.forEach((f) => console.log("  · " + f.cli + " | " + f.monto + " | " + f.motivo));
console.log(fallos.length ? `\n❌ ${fallos.length} fallo(s)` : "\n✅ clientes perdidos en verde");
process.exit(fallos.length ? 1 : 0);
