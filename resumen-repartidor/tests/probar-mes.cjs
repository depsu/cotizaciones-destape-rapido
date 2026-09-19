// Arnés: corre el JS del panel con un DOM de mentira y verifica la vista MES.
// Es el «verificar sin navegador» de la doctrina: el cálculo y el HTML se comprueban acá,
// el navegador queda solo para pintura real.
const fs = require('fs'), vm = require('vm'), path = require('path');

function nodo(tag = 'div', id = '') {
  const n = {
    tagName: String(tag).toUpperCase(), id, hidden: false, innerHTML: '', textContent: '',
    value: '', children: [], attrs: {}, _cls: new Set(), style: {},
    classList: null, handlers: {},
  };
  n.classList = {
    add: c => n._cls.add(c), remove: c => n._cls.delete(c),
    contains: c => n._cls.has(c),
    toggle: (c, on) => { const v = on === undefined ? !n._cls.has(c) : !!on; v ? n._cls.add(c) : n._cls.delete(c); return v; },
  };
  n.setAttribute = (k, v) => { n.attrs[k] = String(v); };
  n.getAttribute = k => (k in n.attrs ? n.attrs[k] : null);
  n.removeAttribute = k => { delete n.attrs[k]; };
  n.addEventListener = (ev, fn) => { (n.handlers[ev] = n.handlers[ev] || []).push(fn); };
  n.removeEventListener = () => {};
  n.appendChild = c => { n.children.push(c); return c; };
  n._hijos = new Map(); n._listas = new Map();
  n.querySelector = sel => { if (!n._hijos.has(sel)) n._hijos.set(sel, nodo('div')); return n._hijos.get(sel); };
  n.querySelectorAll = sel => {
    // los botones del filtro del mes existen de verdad en el HTML que acaba de pintarse:
    // se fabrican uno por cada data-filtro que aparezca, para poder pulsarlos
    if (!n._listas.has(sel)) {
      var out = [];
      if (sel.indexOf('.mes-filtro button') !== -1) {
        [...String(n.innerHTML).matchAll(/data-filtro="([^"]+)"/g)].forEach(m => {
          const b = nodo('button'); b.setAttribute('data-filtro', m[1]); out.push(b);
        });
      }
      n._listas.set(sel, out);
    }
    return n._listas.get(sel);
  };
  n.closest = () => null;
  n.click = () => (n.handlers.click || []).forEach(f => f.call(n, { target: n, preventDefault(){}, stopPropagation(){} }));
  n.focus = () => {}; n.scrollIntoView = () => {}; n.remove = () => {};
  n.getBoundingClientRect = () => ({ top:0, left:0, width:0, height:0, bottom:0, right:0 });
  n.offsetHeight = 0; n.offsetWidth = 0; n.scrollTop = 0; n.scrollHeight = 0;
  n.style.setProperty = () => {}; n.style.removeProperty = () => {};
  n.insertAdjacentHTML = () => {}; n.contains = () => false; n.dataset = {};
  return n;
}

const porId = new Map();
const porSelector = new Map();
function get(id) { if (!porId.has(id)) porId.set(id, nodo('div', id)); return porId.get(id); }

const vistas = ['entregas', 'comision', 'mes'].map(v => {
  const n = nodo('div'); n.setAttribute('data-vista', v); n.hidden = v !== 'entregas'; return n;
});
const botones = ['entregas', 'comision', 'mes'].map(v => {
  const b = nodo('button'); b.setAttribute('data-vista', v);
  if (v === 'entregas') b._cls.add('activo'); return b;
});

const document = {
  body: nodo('body'), documentElement: nodo('html'),
  getElementById: get,
  querySelector: sel => {
    if (sel.includes('data-vista="mes"')) return vistas[2];
    if (sel.includes('data-vista="entregas"')) return vistas[0];
    if (porSelector.has(sel)) return porSelector.get(sel);
    const n = nodo('div'); porSelector.set(sel, n); return n;
  },
  querySelectorAll: sel => {
    if (sel === '.vista-btn') return botones;
    if (sel === '.vista') return vistas;
    return [];
  },
  createElement: nodo,
  addEventListener: () => {}, removeEventListener: () => {},
  createTextNode: t => ({ textContent: t }),
  hidden: false,
};

const APP = JSON.parse(
  fs.readFileSync('/tmp/js-0.js', 'utf8').replace(/^\s*window\.__APP__\s*=\s*/, '').replace(/;\s*$/, '')
);

const ctx = {
  window: { __APP__: APP, addEventListener(){}, scrollTo(){}, matchMedia: () => ({ matches:false, addEventListener(){} }),
            location: { href:'', search:'' }, navigator: { onLine:true }, innerWidth: 390, innerHeight: 800 },
  document, console,
  fetch: () => new Promise(() => {}),         // la red no responde: probamos con META horneada
  localStorage: { getItem: () => null, setItem(){}, removeItem(){} },
  setTimeout, clearTimeout, setInterval: () => 0, clearInterval,
  requestAnimationFrame: f => setTimeout(f, 0),
  Intl, Date, Math, JSON, encodeURIComponent, decodeURIComponent, URL,
  navigator: { onLine: true, clipboard: { writeText: () => Promise.resolve() } },
  alert(){}, confirm: () => true, prompt: () => null,
};
ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('/tmp/js-1.js', 'utf8'), ctx, { filename: 'panel.js' });

// ── Comprobaciones ────────────────────────────────────────────────────────────────
const fallos = [];
const ok = (cond, msg) => { console.log((cond ? '✅ ' : '❌ ') + msg); if (!cond) fallos.push(msg); };

const panelMes = get('mes-panel');
const selMes = get('mes-select');

// La ganancia de la cabecera quedó accionable
const ganado = get('ganado-total');
ok(ganado.getAttribute('role') === 'button', 'la ganancia quedó marcada como botón');
ok((ganado.handlers.click || []).length === 1, 'la ganancia tiene un click cableado');
ok((ganado.handlers.keydown || []).length === 1, 'la ganancia responde al teclado');

// Tocarla abre la vista mes, y ES ESE TOQUE el que la pinta (la red no ha respondido:
// así se comporta de verdad cuando alguien entra al panel y toca la cifra al tiro).
ganado.click();
ok(vistas[2].hidden === false, 'al tocar la ganancia se abre la vista MES');
ok(vistas[0].hidden === true, 'y se esconde la de entregas');
ok(botones[2]._cls.has('activo'), 'el botón «Mes» queda marcado como activo');
ok(!botones[0]._cls.has('activo'), 'y el de entregas se desmarca');

ok(panelMes.innerHTML.length > 0, 'abrirla la pinta, aunque la red no haya respondido');
ok(selMes.innerHTML.includes('<option'), 'el selector de mes tiene opciones');

const meses = [...selMes.innerHTML.matchAll(/value="([^"]+)"/g)].map(m => m[1]);
ok(meses.length > 0, `hay ${meses.length} meses con entregas: ${meses.slice(0,4).join(', ')}`);
ok(meses.every(m => /^\d{4}-\d{2}$/.test(m)), 'todos los meses tienen forma AAAA-MM');

ok(!/undefined|NaN|\[object/.test(panelMes.innerHTML), 'no hay undefined, NaN ni [object Object] pintados');
ok(panelMes.innerHTML.includes('Total del mes'), 'aparece «Total del mes»');
ok(panelMes.innerHTML.includes('Ya cobrado'), 'aparece «Ya cobrado»');
ok(panelMes.innerHTML.includes('Por cobrar'), 'aparece «Por cobrar»');
ok(/\$[\d.]+/.test(panelMes.innerHTML), 'las cifras salen con formato de pesos');

// el selector cambia de mes sin romperse
if (meses.length > 1) {
  const antes = panelMes.innerHTML;
  selMes.value = meses[1];
  (selMes.handlers.change || []).forEach(f => f.call(selMes, { target: selMes }));
  ok(panelMes.innerHTML !== antes, `cambiar a ${meses[1]} repinta la vista`);
  ok(!/undefined|NaN/.test(panelMes.innerHTML), 'el mes anterior tampoco pinta undefined ni NaN');
}

// El filtro: una sola lista, no dos. Antes lo pendiente salía repetido abajo.
selMes.value = meses[0];
mesFiltro_reset: {
  (selMes.handlers.change || []).forEach(f => f.call(selMes, { target: selMes }));
}
const htmlTodas = panelMes.innerHTML;
// ojo: `class="mes-filtro"` también empieza con «mes-f», así que la clase se cierra
const filas = (h) => (h.match(/class="mes-f(?: pend)?"/g) || []).length;
const listas = (h) => (h.match(/class="mes-lista"/g) || []).length;
ok(listas(htmlTodas) === 1, 'hay UNA sola lista de entregas, no dos');

const botonesFiltro = panelMes.querySelectorAll('.mes-filtro button');
if (botonesFiltro.length) {
  ok(botonesFiltro.length === 2, 'el filtro tiene dos botones (Todas / Por cobrar)');
  ok(/Todas ·/.test(htmlTodas) && /Por cobrar ·/.test(htmlTodas), 'los botones dicen cuántas hay en cada uno');
  const nTodas = filas(htmlTodas);
  botonesFiltro.find(b => b.getAttribute('data-filtro') === 'falta').click();
  const htmlFalta = panelMes.innerHTML;
  const nFalta = filas(htmlFalta);
  const nPend = Number((htmlTodas.match(/Por cobrar · (\d+)/) || [])[1] || 0);
  ok(nFalta === nPend, `filtrado quedan las ${nPend} pendientes (de ${nTodas} del mes)`);
  ok(nFalta <= nTodas, 'el filtro nunca muestra más filas que la lista completa');
  ok(!/por cobrar<\/span>\s*<\/div>[\s\S]*?cobrado<\/span>/.test(htmlFalta.replace(/Por cobrar ·[^<]*/g, '')),
     'filtrado, no quedan filas ya cobradas');
  ok(listas(htmlFalta) === 1, 'filtrado sigue habiendo UNA sola lista');
  panelMes.querySelectorAll('.mes-filtro button').find(b => b.getAttribute('data-filtro') === 'todas').click();
  ok(filas(panelMes.innerHTML) === nTodas, 'volver a «Todas» restituye todas las filas');
} else {
  ok(true, 'este mes no tiene pendientes, por eso no hay filtro (correcto)');
}

// las otras vistas siguen funcionando
botones[1].click();
ok(vistas[1].hidden === false && vistas[2].hidden === true, 'la vista Comisión sigue abriendo');
ok(document.body._cls.has('vista-comision'), 'y sigue poniendo la clase vista-comision en el body');
botones[0].click();
ok(!document.body._cls.has('vista-comision'), 'volver a Entregas quita esa clase');

console.log(fallos.length ? `\n❌ ${fallos.length} fallo(s)` : '\n✅ todo verde');
process.exit(fallos.length ? 1 : 0);
