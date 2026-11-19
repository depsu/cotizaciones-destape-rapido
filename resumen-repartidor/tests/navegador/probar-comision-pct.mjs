// Comisión con porcentaje propio (`data.comision_pct`, 19-nov-2026): con los datos REALES de Supabase, a
// una entrega se le pone comision_pct en la RESPUESTA (no en la base) y se mira que la tarjeta, la
// compacta de «falta cobrar», la pestaña Comisión y el pago lo digan. Toda escritura se intercepta.
// Uso (desde la raíz del repo):
//   python3 resumen-repartidor/scripts/generar_listado.py /tmp/nuevo.html
//   node resumen-repartidor/tests/navegador/probar-comision-pct.mjs /tmp/nuevo.html <id-entrega> [pct] [carpeta-capturas]
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
  console.error("✗ No encuentro playwright-core."); process.exit(2);
}
const { chromium } = resolverPlaywright();
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const [nuevo, ID, pctArg, capturas] = process.argv.slice(2);
const PCT = Number(pctArg || 10);
const html = readFileSync(nuevo);
const server = createServer((req, res) => { res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" }); res.end(html); });
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const URL0 = `http://127.0.0.1:${server.address().port}/listado.html?repartidor=p-9t4kqv`;
const browser = await chromium.launch(existsSync(CHROME) ? { executablePath: CHROME, headless: true } : { headless: true });
const fallos = [];
const ok = (c, msg, det) => { console.log((c ? "✅ " : "❌ ") + msg + (!c && det !== undefined ? "\n    → " + JSON.stringify(det).slice(0, 500) : "")); if (!c) fallos.push(msg); };

async function abrir({ cobrado = false } = {}) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, locale: "es-CL", timezoneId: "America/Santiago" });
  const page = await ctx.newPage();
  const errores = [], escrituras = [];
  page.on("pageerror", (e) => errores.push(String(e)));
  await page.route(/supabase\.co/, async (route) => {
    const r = route.request(), u = decodeURIComponent(r.url());
    if (!["GET", "HEAD", "OPTIONS"].includes(r.method())) { escrituras.push(r.method() + " " + u); await route.fulfill({ status: 201, headers: { "access-control-allow-origin": "*" }, body: "" }); return; }
    const esLite = /\/entrega\?select=id,fecha,informado_at,updated_at,data&eliminado=eq\.false/.test(u);
    const esEstado = /\/entrega_estado\?select=\*/.test(u);
    if (!esLite && !esEstado) { await route.continue(); return; }
    const resp = await route.fetch();
    const filas = await resp.json();
    for (const f of filas) {
      if (f.id !== ID) continue;
      if (esLite) f.data = { ...f.data, comision_pct: PCT };
      if (esEstado && cobrado) { f.estado = "cobrado"; f.comision_pagada = false; }
    }
    await route.fulfill({ response: resp, json: filas });
  });
  await page.goto(URL0, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.body.classList.contains("listo"), null, { timeout: 60000 });
  await page.waitForTimeout(2000);
  return { ctx, page, errores, escrituras };
}

// 1 · entregada sin cobrar: la compacta de «falta cobrar» y la tarjeta completa
const a = await abrir();
const t = await a.page.evaluate((id) => {
  const cw = document.querySelector('.card-wrap[data-id="' + id + '"]');
  if (!cw) return null;
  const mini = cw.querySelector(".cobro-mini");
  return { mini: mini ? mini.innerText.replace(/\s+/g, " ") : "", chips: [...cw.querySelectorAll(".com-pct-chip")].map((x) => x.textContent), otras: document.querySelectorAll(".com-pct-chip").length };
}, ID);
ok(!!t, "la tarjeta " + ID + " está en la lista");
ok(t && new RegExp("comisión " + PCT + "%").test(t.mini), "la compacta de «falta cobrar» lo dice: " + (t && t.mini));
ok(t && t.chips.length >= 2, "también al lado del monto en la tarjeta completa (" + (t && t.chips.length) + " etiquetas)");
ok(t && t.otras === t.chips.length, "ninguna otra tarjeta lleva la etiqueta");
if (capturas) {
  await a.page.evaluate((id) => document.querySelector('.card-wrap[data-id="' + id + '"]').scrollIntoView({ block: "center" }), ID);
  await a.page.screenshot({ path: join(capturas, "4-tarjeta-pct.png") });
}
ok(a.errores.length === 0 && a.escrituras.length === 0, "sin errores y sin escribir", { e: a.errores, w: a.escrituras });

// 2 · ya cobrada: la pestaña Comisión, la barra de pago y el WhatsApp a Alejandro
const b = await abrir({ cobrado: true });
const c = await b.page.evaluate(async (id) => {
  document.querySelector('.vista-btn[data-vista="comision"]').click();
  await new Promise((r) => setTimeout(r, 300));
  const chk = document.querySelector('.com-check[data-id="' + id + '"]');
  const cardC = chk ? chk.closest(".com-card") : null;
  return { card: cardC ? cardC.innerText.replace(/\s+/g, " ") : "", n: document.querySelectorAll(".com-card .com-pct-chip").length };
}, ID);
ok(new RegExp("comisión " + PCT + "%").test(c.card) && new RegExp("al " + PCT + "%").test(c.card), "pestaña Comisión: la fila lo dice: " + c.card);
if (capturas) {
  await b.page.evaluate((id) => document.querySelector('.com-check[data-id="' + id + '"]').closest(".com-card").scrollIntoView({ block: "center" }), ID);
  await b.page.screenshot({ path: join(capturas, "5-comision-pct.png") });
}
const modal = await b.page.evaluate(async () => {
  document.querySelector("#barra-pagar .btn-pagar").click();
  await new Promise((r) => setTimeout(r, 400));
  const rows = [...document.querySelectorAll(".bank-row")].map((x) => x.innerText.replace(/\s+/g, " "));
  return rows;
});
ok(modal.some((r) => new RegExp("comisión " + PCT + "%").test(r)), "al pagar, el detalle lo dice: " + modal.filter((r) => /comisión/.test(r)).join(" | "));
if (capturas) await b.page.screenshot({ path: join(capturas, "6-pago-pct.png") });
ok(b.errores.length === 0, "sin errores de JS", b.errores);

await browser.close(); server.close();
console.log(fallos.length ? `\n❌ ${fallos.length} fallo(s)` : "\n✅ comisión con porcentaje propio en verde");
process.exit(fallos.length ? 1 : 0);
