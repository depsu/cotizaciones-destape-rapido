// ¿El JS del panel calcula la comisión igual que Python? Se le pasan las entregas VIVAS de
// Supabase a metaDeData (la función que pisa lo horneado al refrescar) y se comparan sus
// cifras con las que da comision_de() en Python.
const fs = require('fs'), vm = require('vm');
const js = fs.readFileSync('/tmp/js-1.js', 'utf8');

// se extrae metaDeData con sus ayudantes, sin arrancar el panel entero
const trozos = ['soloDigitosJS', 'banosDeJS', 'metaDeData'].map(nombre => {
  const i = js.indexOf(`function ${nombre}(`);
  if (i === -1) throw new Error(`no encontré ${nombre}`);
  let prof = 0, j = js.indexOf('{', i);
  for (let k = j; k < js.length; k++) {
    if (js[k] === '{') prof++;
    else if (js[k] === '}' && --prof === 0) return js.slice(i, k + 1);
  }
});
const ctx = { Math, parseInt, String, Number };
vm.createContext(ctx);
vm.runInContext(trozos.join('\n'), ctx);

const vivos = JSON.parse(fs.readFileSync('/tmp/crudo.json', 'utf8'));
const esperado = JSON.parse(fs.readFileSync('/tmp/esperado-com.json', 'utf8'));
const clp = n => '$' + Math.round(n).toLocaleString('es-CL');

let malas = 0, n = 0;
for (const e of vivos) {
  const m = vm.runInContext('metaDeData', ctx)(e);
  const py = esperado[e.id];
  if (py === undefined) continue;
  n++;
  if (m.comision !== py) {
    malas++;
    console.log(`❌ ${e.id}\n     JS ${clp(m.comision)}  ≠  Python ${clp(py)}`);
  }
}
console.log(`\n${n} entregas comparadas · ${malas ? malas + ' distintas' : 'todas coinciden ✅'}`);

// y el caso que importa
const ac = vivos.find(e => e.id === '2026-09-17-american-container-tobalaba');
if (ac) {
  const m = vm.runInContext('metaDeData', ctx)(ac);
  console.log(`\nAmerican Container en el panel: ${clp(m.comision)}` +
              `  (20% habría dado ${clp(Math.round(m.neto * 0.2))})`);
}
process.exit(malas ? 1 : 0);
