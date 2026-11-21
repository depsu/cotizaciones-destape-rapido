// geo-postventa.mjs — LOS PUNTOS DEL MAPA de postventa, de una vez (21-nov-2026).
//
// La página ubica sola lo que falta (OpenStreetMap, de a uno por segundo) y lo guarda en postventa_geo, pero:
//   · un link corto de Google Maps (maps.app.goo.gl) no se puede abrir desde el navegador: este script lo sigue
//     hasta el punto exacto y lo guarda con fuente «link»;
//   · la primera vez son ~60 direcciones: correrlo antes evita que el primero que abre el mapa espere un minuto.
// Usa las MISMAS reglas que la página (postventa-logica.js) para saber qué baños están en terreno y qué buscar.
// Solo escribe en postventa_geo. Se puede correr las veces que se quiera: lo ya ubicado no se vuelve a buscar.
//
//   node resumen-repartidor/scripts/geo-postventa.mjs            # ubica lo que falta
//   node resumen-repartidor/scripts/geo-postventa.mjs --seco     # dice qué haría, sin escribir
//   node resumen-repartidor/scripts/geo-postventa.mjs --reintentar  # busca de nuevo los que quedaron en su comuna
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const PV = require('../postventa-logica.js');

const SUPA = 'https://abmzkzraptmjgebwjzys.supabase.co';
const KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFibXprenJhcHRtamdlYndqenlzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY5MDA1ODQsImV4cCI6MjA5MjQ3NjU4NH0.9qN07nBI9HdfreiWdVFl1cYrT5tlke7WWr5wi_Cwbho';
const SECO = process.argv.includes('--seco');
// --reintentar: vuelve a buscar los que quedaron en el centro de su comuna (si cambió la regla de búsqueda)
const REINTENTAR = process.argv.includes('--reintentar');
const H = { apikey: KEY, Authorization: 'Bearer ' + KEY };
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

async function leer(ruta) {
  const r = await fetch(`${SUPA}/rest/v1/${ruta}`, { headers: H });
  if (!r.ok) throw new Error(`${ruta}: ${r.status}`);
  return r.json();
}

/** Sigue un link corto hasta la URL larga y saca el punto (@lat,lng · !3d…!4d… · q=lat,lng). */
async function resolverLink(url) {
  let u = url;
  for (let i = 0; i < 6; i++) {
    const r = await fetch(u, { redirect: 'manual', headers: { 'User-Agent': 'Mozilla/5.0 (Macintosh) postventa-mapa' } });
    const sig = r.headers.get('location');
    const texto = decodeURIComponent(sig || u);
    const m = /!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/.exec(texto) || /@(-?\d+\.\d+),(-?\d+\.\d+)/.exec(texto)
      || /[?&](?:q|query|ll|destination)=(-?\d+\.\d+),\s*(-?\d+\.\d+)/.exec(texto);
    if (m) return [parseFloat(m[1]), parseFloat(m[2])];
    if (!sig) {
      // a veces el punto viene en la página y no en la URL
      const html = await r.text().catch(() => '');
      const p = /!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/.exec(html) || /center=(-?\d+\.\d+)%2C(-?\d+\.\d+)/.exec(html);
      return p ? [parseFloat(p[1]), parseFloat(p[2])] : null;
    }
    u = new URL(sig, u).toString();
  }
  return null;
}

async function osm(q) {
  const url = 'https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&countrycodes=cl&accept-language=es'
    + '&viewbox=-71.75,-32.85,-70.15,-34.25&q=' + encodeURIComponent(q + (/chile/i.test(q) ? '' : ', Chile'));
  const r = await fetch(url, { headers: { 'User-Agent': 'destaperapido-postventa/1.0 (mapa interno de baños)' } });
  const x = r.ok ? (await r.json())[0] : null;
  if (!x || Math.abs(parseFloat(x.lat) + 33.5) > 1.6 || Math.abs(parseFloat(x.lon) + 70.8) > 1.6) return null;
  return { lat: parseFloat(x.lat), lng: parseFloat(x.lon), fino: Number(x.place_rank || 0) >= 26 };
}

const hoy = PV.hoyLocal();
const [filas, estados, tareas, eventos, geo] = await Promise.all([
  leer('entrega?select=id,fecha,eliminado,data&eliminado=eq.false'), leer('entrega_estado?select=id,estado,fecha,eliminado'),
  leer('tarea_estado?select=id,realizada,realizada_at'), leer('postventa_evento?select=*'), leer('postventa_geo?select=*'),
]);
const est = Object.fromEntries(estados.map((x) => [x.id, x]));
const tar = Object.fromEntries(tareas.map((x) => [x.id, x]));
const geoDe = Object.fromEntries(geo.map((x) => [x.id, x]));
const evs = {};
for (const x of eventos) (evs[x.entrega_id] = evs[x.entrega_id] || []).push(x);

const servicios = filas.map((f) => PV.servicio(f, est[f.id], tar, evs[f.id] || [], hoy))
  .filter((s) => s && ['activo', 'revisar', 'retirar'].includes(s.grupo) && !s.exacto);
let hechos = 0, links = 0, buscados = 0, comuna = 0, nada = 0;
for (const s of servicios) {
  const g = geoDe[s.id];
  const flojo = g && (g.fuente === 'comuna' || g.fuente === 'nada');
  if (g && g.q === s.geoQ && !(REINTENTAR && flojo)) continue;         // ya ubicado con lo que dice hoy la ficha
  if (g && g.q === 'dir:' + s.geoQ && !s.linkCorto) continue;
  let fila = null;
  if (s.linkCorto) {
    const p = await resolverLink(s.linkCorto).catch(() => null);
    if (p) { fila = { id: s.id, q: s.geoQ, lat: p[0], lng: p[1], fuente: 'link' }; links += 1; }
    await esperar(400);
  }
  if (!fila) {
    if (g && g.q === 'dir:' + s.geoQ && !(REINTENTAR && flojo)) continue; // el link no se pudo abrir y la dirección ya estaba
    let r = null;
    for (const q of PV.consultasGeo(s)) {                               // de lo más fino a la calle sola
      r = await osm(q).catch(() => null);
      await esperar(1100);                                              // OpenStreetMap pide máximo uno por segundo
      if (r && r.fino) break;
    }
    const q2 = s.linkCorto ? 'dir:' + s.geoQ : s.geoQ;
    if (r && r.fino) { fila = { id: s.id, q: q2, lat: r.lat, lng: r.lng, fuente: 'osm' }; buscados += 1; }
    else if (s.comunaCentro) { fila = { id: s.id, q: q2, lat: s.comunaCentro[0], lng: s.comunaCentro[1], fuente: 'comuna' }; comuna += 1; }
    else { fila = { id: s.id, q: q2, lat: null, lng: null, fuente: 'nada' }; nada += 1; }
  }
  hechos += 1;
  console.log(`${fila.fuente.padEnd(6)} ${s.cliente.slice(0, 30).padEnd(30)} ${String(s.geoQ).slice(0, 60)}`);
  if (!SECO) {
    const r = await fetch(`${SUPA}/rest/v1/postventa_geo`, { method: 'POST',
      headers: { ...H, 'Content-Type': 'application/json', Prefer: 'resolution=merge-duplicates,return=minimal' }, body: JSON.stringify(fila) });
    if (!r.ok) console.error(`  ✗ no se guardó ${s.id}: ${r.status} ${await r.text()}`);
  }
}
console.log(`\n${servicios.length} en terreno sin punto exacto · ${hechos} ubicados ahora: ${links} por link, ${buscados} por dirección, ${comuna} al centro de su comuna, ${nada} sin lugar${SECO ? ' (seco: nada se escribió)' : ''}`);
