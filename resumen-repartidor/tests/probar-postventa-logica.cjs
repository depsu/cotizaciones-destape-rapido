// ¿La página de postventa lee los plazos y el aseo IGUAL que la tarjeta y el bot? (21-nov-2026)
//
// Baja TODAS las entregas de Supabase (solo lectura) y compara, entrega por entrega, lo que dice
// postventa-logica.js contra el Python de siempre: generar_listado.py (texto_aseo, cantidad, comunas)
// y el conector del bot agenda-del-equipo.py (inicio, fin, renovable, cada cuántos días va el aseo,
// el lugar corto). Si alguien cambia una regla en Python y no acá, este test falla.
//
//   node resumen-repartidor/tests/probar-postventa-logica.cjs
//   (AGENDA_DEL_EQUIPO=<ruta a agenda-del-equipo.py> si el clon no está en su lugar de siempre)
//
// Además prueba lo nuevo (extensión, limpieza, retiro, ubicación) con casos armados a mano.
'use strict';
const path = require('path');
const { execFileSync } = require('child_process');
const PV = require('../postventa-logica.js');

const SCRIPTS = path.join(__dirname, '..', 'scripts');
const AGENDA = process.env.AGENDA_DEL_EQUIPO
  || path.join(process.env.HOME, 'SaSS/DIXDY/clientes/destaperapido/conexiones/agenda-del-equipo.py');

const py = String.raw`
import json, sys, importlib.util
sys.path.insert(0, sys.argv[1])
import generar_listado as gl
spec = importlib.util.spec_from_file_location('ag', sys.argv[2]); ag = importlib.util.module_from_spec(spec); spec.loader.exec_module(ag)
filas = ag.get('entrega?select=id,fecha,eliminado,data')
hoy = '2099-01-01'
salida = {'comunas': {k: [v[0], v[1]] for k, v in gl.COMUNAS_GEO.items()}, 'filas': [], 'esperado': {}}
for f in filas:
    e = f.get('data') or {}
    if not ag.fecha_iso(f.get('fecha')) and not ag.fecha_iso(e.get('fecha')):
        continue
    # servicio_de con estado «entregado» y un hoy lejano: devuelve inicio/fin/renovable/cada_dias de TODAS
    s = ag.servicio_de(f, 'entregado', {}, ag.fecha_iso(f.get('fecha')) or ag.fecha_iso(e.get('fecha')))
    if s is None:
        continue
    salida['filas'].append(f)
    salida['esperado'][f['id']] = {
        'inicio': s['inicio'], 'fin': s['fin'], 'renovable': s['renovable'], 'cada': s['cada_dias'],
        'lugar': s['lugar'], 'cantidad': gl.cantidad_banos(e), 'aseo': gl.texto_aseo(e),
        'mapsq': gl.maps_query(e), 'comuna': gl.derivar_geo(e)['comuna'],
    }
print(json.dumps(salida, ensure_ascii=False))
`;

const crudo = execFileSync('python3', ['-c', py, SCRIPTS, AGENDA], { maxBuffer: 64 * 1024 * 1024 }).toString();
const { comunas, filas, esperado } = JSON.parse(crudo);
let malas = 0;
const falla = (msg) => { malas += 1; if (malas <= 25) console.log('✗ ' + msg); };

// 1) la tabla de comunas es la misma
for (const [k, v] of Object.entries(comunas)) {
  const j = PV.COMUNAS_GEO[k];
  if (!j || j[0] !== v[0] || j[1] !== v[1]) falla(`comuna ${k}: python ${v} · js ${j}`);
}
if (Object.keys(PV.COMUNAS_GEO).length !== Object.keys(comunas).length) falla('la tabla de comunas tiene otro largo');

// 2) entrega por entrega
const ETIQ = { nunoa: 'Ñuñoa', penaflor: 'Peñaflor', conchali: 'Conchalí', curacavi: 'Curacaví', 'til til': 'Til Til',
  penalolen: 'Peñalolén', maipu: 'Maipú', 'estacion central': 'Estación Central', 'pedro aguirre cerda': 'Pedro Aguirre Cerda',
  'san ramon': 'San Ramón' };
const titulo = (k) => ETIQ[k] || k.replace(/(^|\s)(\S)/g, (_, a, b) => a + b.toUpperCase());
for (const f of filas) {
  const p = esperado[f.id];
  const s = PV.servicio(Object.assign({}, f, { eliminado: false }), { estado: 'entregado' }, {}, [], p.inicio);
  if (!s) { falla(`${f.id}: js no armó el servicio`); continue; }
  const e = f.data || {};
  const cmp = (campo, a, b) => { if (JSON.stringify(a) !== JSON.stringify(b)) falla(`${f.id} · ${campo}: python ${JSON.stringify(a)} · js ${JSON.stringify(b)}`); };
  cmp('inicio', p.inicio, s.inicio);
  cmp('fin', p.fin, s.finBase);
  cmp('renovable', p.renovable, s.renovable);
  cmp('cada_dias', p.cada, s.cadaDias);
  cmp('lugar', p.lugar, s.lugar);
  cmp('cantidad', p.cantidad, s.cantidad);
  cmp('texto_aseo', p.aseo, PV.textoAseo(e));
  cmp('maps_query', p.mapsq, PV.mapsQuery(e));
  // la comuna: igual que el JS de la página de entregas, el campo `comuna` manda; sin él, la dirección (Python)
  if (!e.comuna) cmp('comuna', p.comuna, s.comunaKey ? titulo(s.comunaKey) : 'Sin comuna');
}
console.log(`${filas.length} entregas reales comparadas contra Python`);

// 3) lo nuevo: anotaciones de la página
const hoy = '2026-11-21';
const base = { id: 'x-1', fecha: '2026-10-19', data: { cliente: 'Prueba', fecha: '2026-10-19', periodo: '1 mes',
  aseo: 'Incluido cada 7 a 10 días', direccion: 'Los Aromos 100, casa 2, Lo Barnechea', telefono: '+56 9 1234 5678' } };
const ev = (tipo, fecha, ts, extra) => Object.assign({ id: tipo + ts, entrega_id: 'x-1', tipo, fecha, created_at: ts, anulado: false }, extra || {});
const caso = (nombre, cond) => { if (!cond) falla('caso: ' + nombre); };

let s = PV.servicio(base, { estado: 'cobrado' }, {}, [], hoy);
caso('mensual vencido hace 2 días queda «revisar»', s.fin === '2026-11-19' && s.grupo === 'revisar');
caso('sin limpiezas: atrasada desde la entrega', s.limpieza.estado === 'atrasada' && s.limpieza.base === '2026-10-19');

s = PV.servicio(base, { estado: 'cobrado' }, {}, [ev('extension', '2026-12-19', '2026-11-20T15:00:00Z', { nota: 'renovó por llamada' })], hoy);
caso('la extensión mueve el fin y lo vuelve activo', s.fin === '2026-12-19' && s.grupo === 'activo' && s.extensiones.length === 1);

s = PV.servicio(base, { estado: 'cobrado' }, {}, [ev('extension', '2026-12-19', '2026-11-20T15:00:00Z', { anulado: true })], hoy);
caso('una extensión anulada no cuenta', s.fin === '2026-11-19' && s.grupo === 'revisar');

s = PV.servicio(base, { estado: 'cobrado' }, {}, [ev('limpieza', '2026-11-18', '2026-11-18T20:00:00Z'),
  ev('extension', '2026-12-19', '2026-11-20T15:00:00Z')], hoy);
caso('la limpieza del 18 deja la próxima entre el 25 y el 28', s.limpieza.estado === 'al-dia' && s.limpieza.toca === '2026-11-25' && s.limpieza.vence === '2026-11-28');

s = PV.servicio(base, { estado: 'cobrado' }, {}, [ev('retiro', '2026-11-20', '2026-11-20T18:00:00Z')], hoy);
caso('el retiro lo saca de los activos', s.grupo === 'retirado' && s.limpieza === null);

s = PV.servicio(base, { estado: 'cobrado' }, {}, [ev('retiro', '2026-11-20', '2026-11-20T18:00:00Z'),
  ev('extension', '2027-01-19', '2026-11-20T19:00:00Z')], hoy);
caso('una extensión después del retiro lo reactiva', s.grupo === 'activo' && s.retirado === null);

s = PV.servicio(base, { estado: 'cobrado' }, { 'x-1::retiro': { realizada: true, realizada_at: '2026-11-10T12:00:00Z' } }, [], hoy);
caso('el retiro marcado en la página de entregas también cuenta', s.grupo === 'retirado');

s = PV.servicio(base, { estado: 'pendiente' }, {}, [], hoy);
caso('una entrega sin entregar no es postventa', s === null);

s = PV.servicio(base, { estado: 'cobrado' }, {}, [ev('ubicacion', null, '2026-11-20T10:00:00Z', { nota: 'https://maps.app.goo.gl/abcDEF123' })], hoy);
caso('el link de ubicación manda en «Cómo llegar»', s.navegar === 'https://maps.app.goo.gl/abcDEF123' && s.linkCorto === 'https://maps.app.goo.gl/abcDEF123');

s = PV.servicio(base, { estado: 'cobrado' }, {}, [ev('ubicacion', null, '2026-11-20T10:00:00Z', { nota: 'https://www.google.com/maps/search/?api=1&query=-33.3612%2C-70.5104' })], hoy);
caso('las coordenadas de un link (con %2C) se leen', s.exacto && s.exacto[0] === -33.3612 && s.exacto[1] === -70.5104);

const w = PV.coordsDe('https://waze.com/ul/h66jb74zgw');
caso('el link de Waze (geohash) cae en Santiago', w && w[0] < -33 && w[0] > -34 && w[1] < -70 && w[1] > -71.5);

const corto = { id: 'x-2', fecha: '2026-11-20', data: { cliente: 'Evento', fecha: '2026-11-20', periodo: '3 días', direccion: 'Ñuñoa' } };
s = PV.servicio(corto, { estado: 'entregado' }, {}, [], '2026-11-24');
caso('un evento de 3 días que terminó ayer queda «retirar»', s.fin === '2026-11-22' && s.grupo === 'retirar' && s.corto);
s = PV.servicio(corto, { estado: 'entregado' }, {}, [], '2026-11-30');
caso('un evento corto viejo se archiva', s.grupo === 'terminado');

caso('mes del arriendo', PV.mesDelArriendo('2026-07-08', '2026-11-21') === 5 && PV.mesDelArriendo('2026-11-08', '2026-11-21') === 1);
caso('más meses con fin de mes', PV.masMeses('2026-01-31', 1) === '2026-02-28');

if (malas) { console.log(`\n✗ ${malas} diferencia(s)`); process.exit(1); }
console.log('✓ todo igual a Python y los casos nuevos pasan');
