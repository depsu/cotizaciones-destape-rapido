// Prueba sin navegador de la lógica de la agenda de destapes (comisión, agrupación, textos).
// Uso: node resumen-destapes/tests/probar-logica.cjs
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert');
const html = fs.readFileSync(path.join(__dirname, '..', 'destapes.html'), 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
const els = {};
function el(id) {
  return els[id] || (els[id] = { id, innerHTML: '', textContent: '', hidden: false, disabled: false, value: '',
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } }, style: { setProperty() {} },
    addEventListener() {}, offsetHeight: 70, setAttribute() {}, getAttribute() { return null; } });
}
const store = {};
const ctx = {
  window: {}, console, Intl, Date, Math, JSON, Promise, encodeURIComponent, decodeURIComponent, setTimeout, clearTimeout,
  location: { hash: '' },
  localStorage: { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } },
  fetch: () => Promise.reject(new Error('sin red en la prueba')),
  document: { getElementById: el, querySelector: (s) => el(s), querySelectorAll: () => [], addEventListener() {},
    documentElement: { style: { setProperty() {} } }, body: { classList: { add() {} } }, hidden: false },
};
ctx.window = ctx; ctx.addEventListener = () => {}; ctx.scrollTo = () => {}; ctx.open = () => {}; vm.createContext(ctx);
scripts.forEach((s) => vm.runInContext(s, ctx));
const T = ctx.__DESTAPES__;
const hoy = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Santiago' }).format(new Date());
const ayer = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Santiago' }).format(new Date(Date.now() - 864e5));
const f = (id, fecha, neto, extra) => ({ id, fecha, informado_at: '2026-10-24T10:00:00Z', card_html: `<article data-id="${id}"></article>`,
  data: Object.assign({ id, fecha, precio_neto: neto, servicio: 'Destape con hidrojet', direccion: 'X 1' }, extra || {}) });
const filas = [f('a', hoy, 140000), f('b', ayer, 100000), f('c', hoy, 200000), f('d', hoy, 80000, { comision_pct: 30 }), f('e', hoy, 50000)];
const est = { b: { estado: 'cobrado', valor_final: 180000 }, c: { estado: 'cobrado', comision_pagada: true, pagada_at: '2026-10-24T12:00:00Z' },
  e: { eliminado: true, estado: 'cobrado' } };
T._set(filas, est);
assert.strictEqual(T.comDe(filas[0]), 35000, '25 % de 140.000');
assert.strictEqual(T.comDe(filas[1]), 45000, 'valor final manda: 25 % de 180.000');
assert.strictEqual(T.comDe(filas[3]), 24000, 'el % propio del destape manda');
assert.deepStrictEqual(T.porPagar().map((x) => x.id), ['b'], 'te deben = cobrados sin pagar y no eliminados');
// La primera carga cae al respaldo (fetch rechazado). Esperar y revisar lo pintado.
setTimeout(() => {
  assert.ok(/Mañana ·|Hoy ·|No hay destapes/.test(els.agenda.innerHTML), 'la carga sin red cae al respaldo y pinta');
  const g = f('g', ayer, 90000);
  T._set(filas.concat([g]), est); T.pintar();
  const ag = els.agenda.innerHTML, com = els.comision.innerHTML;
  assert.ok(ag.includes('Atrasados') && ag.includes('data-id="g"'), 'atrasado pendiente arriba');
  assert.ok(ag.indexOf('Atrasados') < ag.indexOf('Hoy ·'), 'atrasados antes que hoy');
  assert.ok(ag.includes('data-id="a"') && ag.includes('data-id="d"'), 'pendientes de hoy');
  assert.ok(!ag.includes('data-id="e"'), 'eliminado no aparece');
  assert.ok(!ag.includes('<div class="dw is-cobrado"'), 'cobrados fuera de la agenda');
  assert.ok(ag.includes('Ver cobrados (2)'), 'botón ver cobrados');
  assert.ok(com.includes('Te deben') && com.includes('$45.000') && com.includes('Pago 1'), 'vista comisión');
  assert.strictEqual(els['hdr-com'].textContent, '$45.000');
  const visible = html.replace(/<script>[\s\S]*?<\/script>/g, '').replace(/<style>[\s\S]*?<\/style>/g, '').replace(/<[^>]+>/g, ' ');
  for (const malo of [';', '«', '»', '—']) assert.ok(!visible.includes(malo), 'texto visible sin ' + malo);
  for (const malo of ['«', '»', '—']) { assert.ok(!ag.includes(malo) && !com.includes(malo), 'pintado sin ' + malo); }
  const sinEnt = (ag + com).replace(/&[a-z#0-9]+;/gi, '').replace(/<[^>]+>/g, ' ');
  assert.ok(!sinEnt.includes(';'), 'pintado sin punto y coma');
  console.log('OK lógica de destapes: 25 %, valor final, % propio, te deben, agrupación, cobrados, eliminados, textos limpios');
}, 50);
