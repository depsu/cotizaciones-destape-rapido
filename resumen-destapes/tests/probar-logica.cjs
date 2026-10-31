// Prueba sin navegador de la lógica de la agenda de destapes: montos ("$140.000"), lectura del
// valor que escribe la persona, comisión sobre el valor final, cobro (valor final + cobrado en un
// solo guardado), atrasados agrupados con su fecha, realizados y cobrados fuera de la agenda.
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

// ── montos con el formato de plata de siempre ($140.000). "140 mil" es solo para el WhatsApp del bot ──
assert.strictEqual(T.clp(140000), '$140.000');
assert.strictEqual(T.clp(17750), '$17.750');
assert.strictEqual(T.clp(1250000), '$1.250.000');
assert.strictEqual(T.clp(750), '$750');

// ── lo que escribe la persona al cobrar ───────────────────────────────────
for (const [txt, n] of [['140', 140000], ['140 mil', 140000], ['140.000', 140000], ['$140.000', 140000], ['$ 140.000', 140000],
  ['140000', 140000], ['140mil', 140000], ['140k', 140000], ['140 lucas', 140000], [' 140 Mil ', 140000], ['17 mil 750', 17750],
  ['17.750', 17750], ['71 mil', 71000], ['1,5 millones', 1500000], ['1 millón 200 mil', 1200000], ['1.200.000', 1200000],
  ['', 0], ['abc', 0], ['0', 0]]) {
  assert.strictEqual(T.leerMonto(txt), n, 'leerMonto(' + JSON.stringify(txt) + ')');
}

// ── factura: "sin factura" empieza con "si" y NO es factura (caso real del conector) ──
const FACTURAS = [['si', true], ['sí', true], ['Sí', true], ['si, con factura', true], ['sí con factura', true], ['con factura', true],
  ['sin factura', false], ['Sin factura', false], ['no', false], ['No, boleta', false], ['boleta', false], ['', null], [null, null]];
for (const [v, esperado] of FACTURAS) assert.strictEqual(T.conFactura(v), esperado, 'conFactura(' + JSON.stringify(v) + ')');
// La misma regla en Python (tarjeta que sube subir_destape.py). El valor es neto, con factura se suma el IVA.
const py = require('child_process').execFileSync('python3', ['-c', [
  'import sys, json; sys.path.insert(0, sys.argv[1]); import generar_destapes as g',
  'vals = json.loads(sys.argv[2])',
  'print(json.dumps({"fac": [g.con_factura(v) for v in vals], "iva": [g.iva_txt(v) for v in ["sin factura", "si, con factura", ""]],',
  '  "tarjeta": g.tarjeta({"id": "x", "precio_neto": 120000, "factura": "sin factura"})}))'].join('\n'),
  path.join(__dirname, '..', 'scripts'), JSON.stringify(FACTURAS.map((x) => x[0]))], { encoding: 'utf8' });
const P = JSON.parse(py);
assert.deepStrictEqual(P.fac, FACTURAS.map((x) => x[1]), 'con_factura en Python igual que en JS');
assert.deepStrictEqual(P.iva, ['Sin factura', 'Con factura: + IVA', 'Si pide factura se suma el IVA']);
assert.ok(P.tarjeta.includes('desde <b>$120.000</b>') && P.tarjeta.includes('Sin factura') && !P.tarjeta.includes('IVA'), 'tarjeta: desde $120.000, sin factura');

// ── datos de prueba ───────────────────────────────────────────────────────
const dia = (d) => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Santiago' }).format(new Date(Date.now() + d * 864e5));
const hoy = dia(0), ayer = dia(-1), anteayer = dia(-2);
const f = (id, fecha, neto, extra) => ({ id, fecha, informado_at: '2026-10-24T10:00:00Z', card_html: `<article data-id="${id}"></article>`,
  data: Object.assign({ id, fecha, precio_neto: neto, servicio: 'Destape con hidrojet', direccion: 'X 1', telefono: '56912345678' }, extra || {}) });
const filas = [f('a', hoy, 140000, { hora: '10:00' }), f('b', ayer, 100000), f('c', hoy, 200000), f('d', hoy, 80000, { comision_pct: 30 }),
  f('e', hoy, 50000), f('g', anteayer, 90000, { hora: '15:00', factura: 'sin factura' }), f('h', ayer, 60000, { factura: 'si, con factura' }), f('r', hoy, 120000)];
const est = { b: { estado: 'cobrado', valor_final: 180000 }, c: { estado: 'cobrado', comision_pagada: true, pagada_at: '2026-10-24T12:00:00Z' },
  e: { eliminado: true, estado: 'cobrado' }, r: { estado: 'realizado' } };
T._set(filas, est);
assert.strictEqual(T.comDe(filas[0]), 35000, '25 % de $140.000');
assert.strictEqual(T.comDe(filas[1]), 45000, 'el valor final manda: 25 % de $180.000');
assert.strictEqual(T.comDe(filas[3]), 24000, 'el % propio del destape manda');
assert.deepStrictEqual(T.porPagar().map((x) => x.id), ['b'], 'por pagar = cobrados sin pagar y no eliminados');

function textosLimpios(h, donde) {
  for (const malo of ['«', '»', '—', '~']) assert.ok(!h.includes(malo), donde + ' sin ' + malo);
  const sinEnt = h.replace(/&[a-z#0-9]+;/gi, '').replace(/<[^>]+>/g, ' ');
  assert.ok(!sinEnt.includes(';'), donde + ' sin punto y coma');
}

// La primera carga cae al respaldo (fetch rechazado). Esperar y revisar lo pintado.
setTimeout(async () => {
  assert.ok(/dia-tit|No hay destapes/.test(els.agenda.innerHTML), 'la carga sin red cae al respaldo y pinta');
  T._set(filas, JSON.parse(JSON.stringify(est))); T.pintar();
  let ag = els.agenda.innerHTML, com = els.comision.innerHTML;

  // Atrasados: cada día con su fecha (como en baños) y la fecha en la tarjeta.
  const largo = (iso) => { const p = iso.split('-'), d = new Date(+p[0], +p[1] - 1, +p[2]);
    return ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'][d.getDay()] + ' ' + d.getDate() + ' de '
      + ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'][d.getMonth()]; };
  assert.ok(ag.includes('data-grupo="atrasados"') && ag.includes('⚠️ Atrasados'), 'los atrasados van juntos arriba');
  assert.ok(!ag.includes('data-grupo="' + anteayer + '"') && !ag.includes('data-grupo="' + ayer + '"'), 'sin repetir un título por cada día atrasado');
  assert.ok(ag.indexOf('data-grupo="atrasados"') < ag.indexOf('data-grupo="' + hoy + '"'), 'atrasados antes que hoy');
  assert.ok(ag.indexOf('data-id="g"') < ag.indexOf('data-id="h"'), 'dentro de atrasados, el más antiguo primero');
  assert.ok(ag.includes('Atrasado · ' + largo(anteayer)) && ag.includes('Atrasado · ' + largo(ayer)), 'cada tarjeta atrasada dice su fecha');
  assert.ok(ag.includes('data-id="a"') && ag.includes('data-id="d"') && ag.includes('data-id="g"') && ag.includes('data-id="h"'), 'por hacer en la agenda');
  assert.ok(!ag.includes('data-id="e"'), 'eliminado no aparece');
  // Realizados y cobrados fuera de la vista principal, detrás de botones.
  assert.ok(!ag.includes('data-id="r"'), 'realizado fuera de la agenda');
  assert.ok(!ag.includes('data-id="b"') && !ag.includes('data-id="c"'), 'cobrados fuera de la agenda');
  assert.ok(ag.includes('Por hacer (4)') && ag.includes('Falta cobrar (1)') && ag.includes('Cobrados (2)'), 'botones para ver realizados y cobrados');
  assert.ok(ag.indexOf('data-acc="cobrar"') < ag.indexOf('data-acc="realizado"'), 'Cobrado primero en la tarjeta');
  assert.strictEqual(els['hdr-pend'].textContent, 4, 'por hacer: a, d, g, h');
  assert.strictEqual(els['hdr-atr'].textContent, ' · 2 atrasados');
  assert.ok(ag.includes('$140.000') && !/\d mil\b/.test(ag), 'montos como $140.000 en la página, nunca "140 mil"');
  const tarjeta = (id) => { const i = ag.indexOf('data-id="' + id + '"'); return ag.slice(i, ag.indexOf('data-id=', i + 10)); };
  assert.ok(tarjeta('g').includes('Sin factura') && !tarjeta('g').includes('Con factura'), '"sin factura" se muestra Sin factura');
  assert.ok(tarjeta('h').includes('Con factura: + IVA ($71.400 en total)'), '"si, con factura" suma el 19 %');
  assert.ok(tarjeta('a').includes('Si pide factura se suma el IVA'), 'sin dato de factura');
  T._modo('realizados'); T.pintar(); ag = els.agenda.innerHTML;
  assert.ok(ag.includes('data-id="r"') && !ag.includes('data-id="a"') && ag.includes('Volver a la agenda'), 'modo falta cobrar');
  T._modo('cobrados'); T.pintar(); ag = els.agenda.innerHTML;
  assert.ok(ag.includes('data-id="b"') && ag.includes('data-id="c"') && !ag.includes('data-id="a"'), 'modo cobrados');
  assert.ok(ag.includes('Se cobró <b>$180.000</b>'), 'el cobrado muestra lo que se cobró');
  assert.ok(ag.includes('Falta el valor final'), 'el cobrado sin valor final lo avisa');
  T._modo('agenda'); T.pintar();

  // Vista comisión.
  com = els.comision.innerHTML;
  assert.ok(com.includes('Comisión por pagar') && com.includes('$45.000') && com.includes('Cobrados, comisión sin pagar'), 'vista comisión');
  assert.ok(!/\d mil\b/.test(com), 'comisión sin "mil"');
  assert.ok(com.includes('Realizados, falta cobrar') && com.includes('Ver pagos hechos (1)'), 'falta cobrar y pagos hechos');
  assert.strictEqual(els['hdr-com'].textContent, '$45.000');
  textosLimpios(els.agenda.innerHTML, 'agenda'); textosLimpios(com, 'comisión');

  // ── Cobrar: "¿Cuánto se cobró?" con el valor ya puesto, guarda valor final y cobrado juntos ──
  const enviados = [];
  ctx.fetch = (url, op) => { enviados.push({ url, cuerpo: JSON.parse(op.body) }); return Promise.resolve({ ok: true }); };
  T.abrirCobro('a'); ag = els.agenda.innerHTML;
  assert.ok(ag.includes('¿Cuánto se cobró?') && ag.includes('value="$140.000"') && ag.includes('Guardar cobrado'), 'cobro abierto con el valor desde');
  assert.ok(ag.includes('Comisión 25 %: <b>$35.000</b>'), 'muestra la comisión antes de guardar');
  textosLimpios(ag, 'cobro abierto');
  assert.strictEqual(await T.guardarCobro('a', '170 mil'), true);
  assert.deepStrictEqual(enviados.map((x) => x.cuerpo), [{ id: 'a', estado: 'cobrado', valor_final: 170000 }], 'un solo guardado con valor final y cobrado');
  assert.ok(enviados[0].url.includes('/rest/v1/destape_estado'), 'guarda en destape_estado');
  assert.strictEqual(T.estadoDe('a'), 'cobrado');
  assert.strictEqual(T.comDe(filas[0]), 42500, 'comisión sobre el valor final: 25 % de $170.000');
  assert.ok(!els.agenda.innerHTML.includes('data-id="a"'), 'al cobrarse sale de la agenda');
  assert.strictEqual(els['hdr-com'].textContent, '$87.500', 'suma a la comisión por pagar');

  // Corregir el valor de uno ya cobrado, desde la vista comisión ("Cobrados sin pagar").
  T._modo('agenda', 'comision'); T.abrirCobro('b'); com = els.comision.innerHTML;
  assert.ok(com.includes('value="$180.000"') && com.includes('Guardar valor') && com.includes('No se cobró'), 'corregir desde comisión');
  assert.strictEqual(await T.guardarCobro('b', '$150.000'), true);
  assert.deepStrictEqual(enviados[1].cuerpo, { id: 'b', estado: 'cobrado', valor_final: 150000 });
  assert.strictEqual(T.comDe(filas[1]), 37500, '25 % de $150.000');

  // Comisión ya pagada: no se cambia el valor (hay que revocar el pago antes).
  assert.strictEqual(await T.guardarCobro('c', '300'), false);
  assert.strictEqual(enviados.length, 2, 'no se envía nada si la comisión ya está pagada');
  // Valor que no se entiende: no guarda.
  assert.strictEqual(await T.guardarCobro('d', 'nada'), false);
  assert.strictEqual(enviados.length, 2);

  // Si Supabase falla: no queda cobrado y el formulario vuelve abierto con lo escrito.
  ctx.fetch = () => Promise.resolve({ ok: false, status: 503 });
  T._modo('agenda', 'agenda');
  assert.strictEqual(await T.guardarCobro('d', '90'), false);
  assert.strictEqual(T.estadoDe('d'), 'pendiente', 'se revierte');
  assert.ok(els.agenda.innerHTML.includes('value="90"'), 'el formulario vuelve con lo escrito');

  const visible = html.replace(/<script>[\s\S]*?<\/script>/g, '').replace(/<style>[\s\S]*?<\/style>/g, '').replace(/<[^>]+>/g, ' ');
  for (const malo of [';', '«', '»', '—', '~']) assert.ok(!visible.includes(malo), 'texto visible sin ' + malo);
  console.log('OK lógica de destapes: montos $140.000, lectura del valor ("140", "140 mil", "$140.000"), cobro con valor final, comisión 25 %, % propio,'
    + ' atrasados con su fecha, realizados y cobrados escondidos, corregir desde comisión, pagada bloqueada, falla revierte, textos limpios');
}, 50);
