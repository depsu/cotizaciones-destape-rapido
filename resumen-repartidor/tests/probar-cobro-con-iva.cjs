// Arnés (5-oct-2026, iva-remate): la fila «💰 Falta cobrar» (card compacta), el mensaje de cobro
// y la lista del mes dicen si el monto trae IVA, con la MISMA regla que la tarjeta y el WhatsApp
// del repartidor (`cuenta_cobro` en Python, `metaDeData` en JS). Corre el JS del panel con un DOM
// de mentira, como probar-mes.cjs: el navegador queda para la pintura real.
//
//   python3 resumen-repartidor/scripts/generar_listado.py /tmp/listado-nuevo.html
//   node resumen-repartidor/tests/probar-cobro-con-iva.cjs /tmp/listado-nuevo.html
const fs = require('fs'), vm = require('vm');

const ruta = process.argv[2] || '/tmp/listado-nuevo.html';
const html = fs.readFileSync(ruta, 'utf8');
const bloques = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);

function nodo(tag = 'div', id = '') {
  const n = {
    tagName: String(tag).toUpperCase(), id, hidden: false, innerHTML: '', textContent: '',
    value: '', children: [], attrs: {}, _cls: new Set(), style: {}, handlers: {}, dataset: {},
  };
  n.classList = {
    add: (c) => n._cls.add(c), remove: (c) => n._cls.delete(c), contains: (c) => n._cls.has(c),
    toggle: (c, on) => { const v = on === undefined ? !n._cls.has(c) : !!on; if (v) n._cls.add(c); else n._cls.delete(c); return v; },
  };
  n.setAttribute = (k, v) => { n.attrs[k] = String(v); };
  n.getAttribute = (k) => (k in n.attrs ? n.attrs[k] : null);
  n.hasAttribute = (k) => k in n.attrs;
  n.removeAttribute = (k) => { delete n.attrs[k]; };
  n.addEventListener = (ev, fn) => { (n.handlers[ev] = n.handlers[ev] || []).push(fn); };
  n.removeEventListener = () => {};
  n.appendChild = (c) => { n.children.push(c); return c; };
  n.prepend = (c) => { n.children.unshift(c); return c; };
  n._hijos = new Map();
  n.querySelector = (sel) => { if (!n._hijos.has(sel)) n._hijos.set(sel, nodo('div')); return n._hijos.get(sel); };
  n.querySelectorAll = () => [];
  n.closest = () => null;
  n.insertAdjacentElement = () => {};
  n.insertAdjacentHTML = () => {};
  n.focus = () => {}; n.scrollIntoView = () => {}; n.remove = () => {}; n.contains = () => false;
  n.getBoundingClientRect = () => ({ top: 0, left: 0, width: 0, height: 0, bottom: 0, right: 0 });
  n.style.setProperty = () => {}; n.style.removeProperty = () => {};
  return n;
}

const APP = JSON.parse(bloques[0].replace(/^\s*window\.__APP__\s*=\s*/, '').replace(/;\s*$/, ''));
// tres entregas YA entregadas y sin cobrar: con IVA (marca nueva), sin factura y una vieja sin marca
const base = (APP.entregas || []).find((e) => !e.es_servicio) || {};
const casos = [
  { ...base, id: 'iva-1', cliente: 'Cliente con IVA', fecha: '2026-10-03', estado: 'entregado', monto: 154700, neto: 130000, con_iva: true, tel: '56911112222' },
  { ...base, id: 'neto-1', cliente: 'Cliente sin factura', fecha: '2026-10-03', estado: 'entregado', monto: 100000, neto: 100000, con_iva: false, tel: '56911113333' },
  { ...base, id: 'viejo-1', cliente: 'Cliente de antes', fecha: '2026-10-03', estado: 'entregado', monto: 119000, neto: 100000, con_iva: null, tel: '56911114444' },
];
APP.entregas = [...casos, ...(APP.entregas || [])];

const cards = casos.map((c) => { const n = nodo('div'); n.setAttribute('data-id', c.id); n.setAttribute('data-fecha', c.fecha); n._cls.add('card-wrap'); return n; });
const porId = new Map();
const get = (id) => { if (!porId.has(id)) porId.set(id, nodo('div', id)); return porId.get(id); };
const vistas = ['entregas', 'comision', 'mes'].map((v) => { const n = nodo('div'); n.setAttribute('data-vista', v); n.hidden = v !== 'entregas'; return n; });
const botones = ['entregas', 'comision', 'mes'].map((v) => { const b = nodo('button'); b.setAttribute('data-vista', v); return b; });
const document = {
  body: nodo('body'), documentElement: nodo('html'), getElementById: get, hidden: false,
  querySelector: (sel) => {
    if (sel.includes('data-vista="mes"')) return vistas[2];
    if (sel.includes('data-vista="entregas"')) return vistas[0];
    return nodo('div');
  },
  querySelectorAll: (sel) => {
    if (sel === '.card-wrap[data-id]') return cards;
    if (sel === '.vista-btn') return botones;
    if (sel === '.vista') return vistas;
    return [];
  },
  createElement: nodo, addEventListener: () => {}, removeEventListener: () => {},
  createTextNode: (t) => ({ textContent: t }),
};
const ctx = {
  window: { __APP__: APP, addEventListener() {}, scrollTo() {}, matchMedia: () => ({ matches: false, addEventListener() {} }),
    location: { href: '', search: '' }, navigator: { onLine: true }, innerWidth: 390, innerHeight: 800 },
  document, console,
  fetch: () => new Promise(() => {}),          // la red no responde: se prueba con lo horneado
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  setTimeout, clearTimeout, setInterval: () => 0, clearInterval,
  requestAnimationFrame: (f) => setTimeout(f, 0),
  Intl, Date, Math, JSON, encodeURIComponent, decodeURIComponent, URL,
  navigator: { onLine: true, clipboard: { writeText: () => Promise.resolve() } },
  alert() {}, confirm: () => true, prompt: () => null,
};
ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
vm.runInContext(bloques[1], ctx, { filename: 'panel.js' });

const fallos = [];
const ok = (cond, msg, detalle) => {
  console.log((cond ? '✅ ' : '❌ ') + msg + (!cond && detalle !== undefined ? `\n   → ${String(detalle).slice(0, 300)}` : ''));
  if (!cond) fallos.push(msg);
};
const plano = (h) => String(h).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
const mini = (i) => cards[i].querySelector('.cobro-mini').innerHTML;
const mensaje = (i) => decodeURIComponent((/text=([^"]+)"/.exec(mini(i)) || [])[1] || '');

ok(cards.every((c) => c._cls.has('cobro-pendiente')), 'las tres entregas entregadas y sin cobrar quedan como card compacta «Falta cobrar»');
ok(/\$154\.700/.test(plano(mini(0))) && /\$154\.700 con IVA/.test(plano(mini(0))), 'con IVA: la fila dice «$154.700 con IVA»', plano(mini(0)));
ok(/\$100\.000 neto/.test(plano(mini(1))), 'sin factura: la fila dice «$100.000 neto»', plano(mini(1)));
ok(/\$119\.000/.test(plano(mini(2))) && !/con IVA|neto/.test(plano(mini(2))), 'entrega de antes sin marca: el monto como siempre, sin afirmar nada', plano(mini(2)));
ok(mensaje(0).includes('el pago de $154.700 (IVA incluido)'), 'el mensaje de cobro al cliente dice «(IVA incluido)»', mensaje(0));
ok(!/con factura/.test(mensaje(0)), 'y ya no dice «(con factura)» (un particular sin factura también paga con IVA)', mensaje(0));
ok(mensaje(1).includes('el pago de $100.000.') && !/IVA/.test(mensaje(1)), 'sin factura: el mensaje dice el monto solo', mensaje(1));
ok(mensaje(2).includes('$119.000 (IVA incluido)'), 'entrega de antes con monto > neto: «(IVA incluido)» como antes decía «(con factura)»', mensaje(2));

// la lista del mes: la marca junto al monto de cada fila
const ganado = get('ganado-total');
(ganado.handlers.click || []).forEach((f) => f.call(ganado, { target: ganado, preventDefault() {}, stopPropagation() {} }));
const sel = get('mes-select');
sel.value = '2026-10';
(sel.handlers.change || []).forEach((f) => f.call(sel, { target: sel }));
const mes = get('mes-panel').innerHTML;
ok(/\$154\.700<small class="mto-c">con IVA<\/small>/.test(mes), 'el mes: «$154.700 con IVA» en la fila de la entrega con IVA', mes.slice(0, 400));
ok(/\$100\.000<small class="mto-c">neto<\/small>/.test(mes), 'el mes: «$100.000 neto» en la fila sin factura');
ok(/\$119\.000<\/span>/.test(mes), 'el mes: la entrega de antes sin marca queda como siempre');
ok(!/undefined|NaN|\[object/.test(mes + mini(0) + mini(1) + mini(2)), 'nada de undefined, NaN ni [object Object]');

// la marca horneada desde Python (META de entregas.json) usa la misma regla que la tarjeta
const horneadas = (JSON.parse(bloques[0].replace(/^\s*window\.__APP__\s*=\s*/, '').replace(/;\s*$/, '')).entregas || []);
const conMarca = horneadas.filter((e) => e.con_iva === true).length;
ok(horneadas.length > 0 && horneadas.every((e) => e.con_iva === true || e.con_iva === false || e.con_iva === null),
  `las ${horneadas.length} entregas horneadas traen la marca con_iva (true/false/null)`);
console.log(`   (${conMarca} con IVA, ${horneadas.filter((e) => e.con_iva === false).length} sin factura, ${horneadas.filter((e) => e.con_iva === null).length} sin marca)`);

console.log(fallos.length ? `\n❌ ${fallos.length} fallo(s)` : '\n✅ todo verde');
process.exit(fallos.length ? 1 : 0);
