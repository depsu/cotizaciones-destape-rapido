/* postventa-logica.js — LAS REGLAS de la página de postventa (21-nov-2026), sin pantalla ni red.

   Qué baño está en terreno, hasta cuándo, cuándo le toca la limpieza y dónde está. Es el puerto a JS de las
   MISMAS reglas que usan la tarjeta del repartidor y el bot (no se inventa ninguna):
     · generar_listado.py: texto_aseo, dias_del_plazo, meses_del_plazo, notas_sin_marcas, cantidad_banos,
       derivar_geo / maps_query (comunas) y RE_LARGO;
     · conexiones/agenda-del-equipo.py (clon destaperapido): servicio_de (inicio, fin, renovable, cada_dias,
       limpiezas hechas) y lugar_corto.
   tests/probar-postventa-logica.cjs compara este archivo contra el Python con TODAS las entregas reales: si
   alguien cambia una regla allá y no acá, el test lo dice.

   Lo NUEVO de esta página vive en la tabla postventa_evento y se suma encima:
     · extension  → el plazo queda hasta esa fecha (renovó por llamada, por WhatsApp…);
     · limpieza   → cuenta como hecha ese día (con quién la hizo y su foto);
     · retiro     → el baño ya no está (sale de la lista de activos);
     · ubicacion  → el link de Google Maps o la dirección exacta que manda para «Cómo llegar».
   Una anotación anulada no cuenta. Una extensión posterior a un retiro reactiva el servicio. */
(function (raiz) {
  'use strict';

  var ASEO_LARGO = 'Incluido cada 7 a 10 días';
  var ASEO_SIN_DATO = 'Pendiente de confirmar con la oficina';
  var DIAS_DESDE_ASEO_INCLUIDO = 7;
  var CLAVES_NOTA = ['EQUIPO', 'ACCESO', 'RECIBE', 'PAGA', 'PAGO', 'RETIRO', 'RESPALDO'];
  var RE_MARCA_NOTA = /^([A-ZÁÉÍÓÚÑ]{4,8})\s*:\s*.+$/;
  var PALABRAS_NUMERO = { un: 1, uno: 1, una: 1, dos: 2, tres: 3, cuatro: 4, cinco: 5, seis: 6, siete: 7, ocho: 8,
    nueve: 9, diez: 10, once: 11, doce: 12, quince: 15, veinte: 20, treinta: 30 };
  var RE_PALABRA_NUMERO = new RegExp('\\b(' + Object.keys(PALABRAS_NUMERO)
    .sort(function (a, b) { return b.length - a.length; }).join('|') + ')\\b', 'g');
  var RE_PLAZO = /\b(\d{1,3})\s*(dias?|noches?|semanas?|quincenas?)\b(\s+y\s+medi[oa]\b)?/;
  var RE_MESES = /\b(\d{1,2}|un|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce)\s+mes(?:es)?\b/i;
  var ISO = /^\d{4}-\d{2}-\d{2}$/;

  // Centros aproximados de comuna/sector (copia de COMUNAS_GEO de generar_listado.py; el test vigila que sea igual)
  var COMUNAS_GEO = {
    'lo barnechea': [-33.353, -70.518], 'las condes': [-33.409, -70.569], 'vitacura': [-33.380, -70.575],
    'la reina': [-33.443, -70.537], 'nunoa': [-33.456, -70.597], 'providencia': [-33.430, -70.610],
    'penalolen': [-33.485, -70.545], 'macul': [-33.485, -70.598], 'santiago centro': [-33.445, -70.660],
    'santiago': [-33.445, -70.660], 'independencia': [-33.417, -70.665], 'recoleta': [-33.414, -70.640],
    'estacion central': [-33.452, -70.685], 'san miguel': [-33.497, -70.652], 'san joaquin': [-33.492, -70.628],
    'pedro aguirre cerda': [-33.487, -70.673], 'colina': [-33.203, -70.676], 'chicureo': [-33.283, -70.667],
    'lo pinto': [-33.262, -70.723], 'lampa': [-33.283, -70.883], 'til til': [-33.083, -70.930],
    'quilicura': [-33.367, -70.729], 'huechuraba': [-33.370, -70.645], 'conchali': [-33.383, -70.675],
    'renca': [-33.404, -70.726], 'pudahuel': [-33.443, -70.760], 'cerro navia': [-33.423, -70.735],
    'lo prado': [-33.443, -70.720], 'maipu': [-33.510, -70.760], 'cerrillos': [-33.495, -70.715],
    'curacavi': [-33.410, -71.140], 'padre hurtado': [-33.573, -70.810], 'penaflor': [-33.610, -70.878],
    'talagante': [-33.665, -70.928], 'el monte': [-33.677, -71.010], 'isla de maipo': [-33.752, -70.897],
    'melipilla': [-33.688, -71.215], 'calera de tango': [-33.632, -70.782], 'san bernardo': [-33.592, -70.699],
    'buin': [-33.732, -70.741], 'paine': [-33.808, -70.741], 'pirque': [-33.640, -70.548],
    'puente alto': [-33.611, -70.575], 'la florida': [-33.552, -70.583], 'la pintana': [-33.583, -70.630],
    'la granja': [-33.540, -70.625], 'el bosque': [-33.562, -70.675], 'la cisterna': [-33.537, -70.663],
    'san ramon': [-33.535, -70.645]
  };
  var COMUNAS_ORD = Object.keys(COMUNAS_GEO).sort(function (a, b) { return b.length - a.length; });

  // ── texto ──────────────────────────────────────────────────────────────────────────────────
  function texto(v) { return v === null || v === undefined ? '' : String(v).trim(); }
  function sinTildes(s) { return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, ''); }
  function norm(s) { return sinTildes(String(s || '').toLowerCase()); }
  function fechaIso(v) { var t = texto(v).slice(0, 10); return ISO.test(t) ? t : null; }

  function partirNotas(notas) {
    var marcas = {};
    var resto = [];
    String(notas === null || notas === undefined ? '' : notas).split('·').forEach(function (p) {
      var parte = p.trim();
      if (!parte) { return; }
      var clave = parte.split(':')[0].trim();
      if (RE_MARCA_NOTA.test(parte) && CLAVES_NOTA.indexOf(clave) !== -1) {
        if (!(clave in marcas)) { marcas[clave] = parte.slice(parte.indexOf(':') + 1).trim(); }
      } else {
        resto.push(parte);
      }
    });
    return { marcas: marcas, resto: resto.join(' · ') };
  }
  function notasSinMarcas(notas) { return partirNotas(notas).resto; }

  // RE_LARGO de Python: mensual|indefinid|permanente|(?<!medi[oa] )\bmes(?:es)?\b (sin lookbehind: Safari viejo)
  function esLargo(s) {
    s = String(s || '');
    if (/mensual|indefinid|permanente/i.test(s)) { return true; }
    var re = /\bmes(?:es)?\b/gi;
    var m;
    while ((m = re.exec(s)) !== null) {
      if (!/medi[oa] $/i.test(s.slice(Math.max(0, m.index - 6), m.index))) { return true; }
    }
    return false;
  }

  function diasDelPlazo(t0) {
    var t = norm(t0);
    t = t.replace(/\bmedi[oa]\s+mes\b/g, '15 dias').replace(/\bmedia\s+semana\b/g, '4 dias');
    t = t.replace(RE_PALABRA_NUMERO, function (_, w) { return String(PALABRAS_NUMERO[w]); });
    var m = RE_PLAZO.exec(t);
    if (m) {
      var n = parseInt(m[1], 10);
      var unidad = m[2];
      var media = !!m[3];
      if (/^(dia|noche)/.test(unidad)) { return n; }
      if (/^semana/.test(unidad)) { return n * 7 + (media ? 4 : 0); }
      return n * 15 + (media ? 8 : 0);
    }
    if (t.indexOf('quincen') !== -1) { return 15; }
    if (/\bfin de semana\b/.test(t)) { return 2; }
    if (/\bsemana\b/.test(t)) { return 7; }
    return null;
  }

  function mesesDelPlazo(e) {
    var m = RE_MESES.exec(texto(e.periodo === undefined ? '' : (e.periodo || '')) + ' ' + notasSinMarcas(e.notas));
    // (Python arma f"{periodo or ''} {notas}" sin strip: da igual para buscar)
    if (!m) { return 1; }
    var n = /^\d+$/.test(m[1]) ? parseInt(m[1], 10) : (PALABRAS_NUMERO[m[1].toLowerCase()] || 1);
    return n > 0 ? n : 1;
  }

  function textoAseo(e) {
    var dicho = texto(e.aseo);
    if (dicho) { return dicho; }
    var donde = texto(e.periodo) + ' ' + notasSinMarcas(e.notas) + ' ' + (e.servicio || '');
    var agendado = (Array.isArray(e.limpiezas) ? e.limpiezas : []).some(function (x) {
      return x && typeof x === 'object' && !Array.isArray(x) && String(x.tipo || '') !== 'extra';
    });
    var dias = diasDelPlazo(donde);
    if (dias !== null && dias >= DIAS_DESDE_ASEO_INCLUIDO) { return ASEO_LARGO; }
    if (esLargo(donde) || agendado) { return ASEO_LARGO; }
    if (dias !== null && dias >= 1 && dias < DIAS_DESDE_ASEO_INCLUIDO) {
      return 'Sin aseo periódico (' + dias + ' día' + (dias === 1 ? '' : 's') + '): el baño se retira antes del primer ciclo';
    }
    return ASEO_SIN_DATO;
  }

  /** [mín, máx] de días entre aseos (la regla del bot); null = sin aseo periódico. */
  function cadaDias(e) {
    var t = textoAseo(e).toLowerCase();
    if (/^(sin |no )|no corresponde|no incluid|pendiente de confirmar/.test(t)) { return null; }
    if (t.indexOf('7 a 10') !== -1 || t === ASEO_LARGO.toLowerCase()) { return [7, 10]; }
    if (/semanal|(1|una) vez (por|a la) semana|cada semana/.test(t)) { return [7, 8]; }
    return null;
  }

  function cantidadBanos(e) {
    var c = e.cantidad;
    if (typeof c === 'number' && Math.floor(c) === c && c > 0) { return c; }
    var m = /(\d+)\s*ba[ñn]o/i.exec(String(e.servicio || ''));
    return m ? parseInt(m[1], 10) : 1;
  }

  // ── fechas (AAAA-MM-DD, en calendario, sin husos) ─────────────────────────────────────────────
  function aUTC(iso) { var p = iso.split('-').map(Number); return Date.UTC(p[0], p[1] - 1, p[2]); }
  function deUTC(ms) { return new Date(ms).toISOString().slice(0, 10); }
  function sumarDias(iso, n) { return deUTC(aUTC(iso) + n * 86400000); }
  function diasEntre(a, b) { return Math.round((aUTC(b) - aUTC(a)) / 86400000); }
  function masMeses(iso, meses) {
    var p = iso.split('-').map(Number);
    var m = p[1] - 1 + meses;
    var anio = p[0] + Math.floor(m / 12);
    var mes = (m % 12 + 12) % 12;
    var ultimo = new Date(Date.UTC(anio, mes + 1, 0)).getUTCDate();
    return deUTC(Date.UTC(anio, mes, Math.min(p[2], ultimo)));
  }
  function hoyLocal(d) {
    d = d || new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }
  /** La fecha LOCAL (Chile, la del teléfono) de una marca de tiempo ISO. */
  function fechaDeMarca(ts) {
    var d = new Date(ts);
    return isNaN(d.getTime()) ? fechaIso(ts) : hoyLocal(d);
  }

  // ── lugar y mapa ────────────────────────────────────────────────────────────────────────────
  function lugarCorto(e) {
    var comuna = texto(e.comuna).split(/\s+[—–-]\s+|\(/)[0].trim();
    var calle = texto(e.direccion).replace(/https?:\/\/\S+/g, ' ').replace(/^[ ,·-]+|[ ,·-]+$/g, '')
      .split(/\s+[—–]\s+/)[0].trim();
    var ultimo = calle.indexOf(',') !== -1 ? calle.split(',').pop().trim() : '';
    if (!comuna) {
      comuna = (ultimo.length >= 3 && ultimo.length <= 25 && !/\d/.test(ultimo)) ? ultimo : calle.slice(0, 40);
    }
    return comuna.slice(0, 60);
  }

  /** La dirección para leer (sin links pegados ni «Región Metropolitana»). */
  function direccionLimpia(e) {
    return texto(e.direccion).replace(/https?:\/\/\S+/g, ' ').replace(/\b(Waze|Ubicaci[oó]n)\s*:?\s*$/i, '')
      .replace(/,?\s*Regi[oó]n Metropolitana( de Santiago)?/ig, '').replace(/\s+/g, ' ')
      .replace(/\s+,/g, ',').replace(/^[\s,·.;—-]+|[\s,·.;—-]+$/g, '');
  }

  /** maps_query de Python: lo que se busca en un mapa para navegar (nunca el centro de la comuna). */
  function mapsQuery(e) {
    var coords = texto(e.coordenadas);
    if (coords) { return coords; }
    var d = String(e.direccion || '');
    ['http', 'Waze', 'Ubicación', 'ubicación'].forEach(function (marca) {
      var i = d.indexOf(marca);
      if (i !== -1) { d = d.slice(0, i); }
    });
    d = d.replace(/\([^)]*\)/g, ' ').replace(/[()]/g, ' ');
    if (d.indexOf('—') !== -1) {
      var der = d.split('—').slice(1).join('—');
      if (der.indexOf(',') !== -1 || /\d/.test(der)) { d = der; }
    }
    return d.replace(/\s+/g, ' ').replace(/\s+,/g, ',').replace(/^[\s.,;—-]+|[\s.,;—-]+$/g, '');
  }

  var RE_COORD = /@?(-?\d{1,2}\.\d{3,}),\s*(-?\d{1,3}\.\d{3,})/;
  var GEOHASH = '0123456789bcdefghjkmnpqrstuvwxyz';
  function deGeohash(h) {
    var lat = [-90, 90];
    var lng = [-180, 180];
    var par = true;
    for (var i = 0; i < h.length; i++) {
      var v = GEOHASH.indexOf(h.charAt(i));
      if (v < 0) { return null; }
      for (var b = 4; b >= 0; b--) {
        var r = par ? lng : lat;
        var mitad = (r[0] + r[1]) / 2;
        if ((v >> b) & 1) { r[0] = mitad; } else { r[1] = mitad; }
        par = !par;
      }
    }
    return [(lat[0] + lat[1]) / 2, (lng[0] + lng[1]) / 2];
  }
  /** Un punto exacto escrito en un texto: «-33.4,-70.6», un link de Google con las coordenadas o uno de Waze. */
  function coordsDe(t) {
    var s = String(t || '');
    try { s = decodeURIComponent(s); } catch (err) { /* un % suelto: se lee tal cual */ }
    var m = RE_COORD.exec(s);
    if (m) {
      var lat = parseFloat(m[1]);
      var lng = parseFloat(m[2]);
      if (lat < -17 && lat > -56 && lng < -66 && lng > -76) { return [lat, lng]; }   // dentro de Chile
    }
    var w = /waze\.com\/ul\/h([0-9b-hjkmnp-z]{6,12})/i.exec(s);
    if (w) {
      var p = deGeohash(w[1].toLowerCase());
      if (p && p[0] < -17 && p[0] > -56) { return p; }
    }
    return null;
  }
  function linkCorto(t) {
    var m = /https?:\/\/(?:maps\.app\.goo\.gl|goo\.gl\/maps)\/[^\s,)]+/i.exec(String(t || ''));
    return m ? m[0] : '';
  }
  function primerLink(t) {
    var m = /https?:\/\/\S+/.exec(String(t || ''));
    return m ? m[0].replace(/[),.;]+$/, '') : '';
  }

  function comunaDe(e) {
    var buscar = function (t) {
      for (var i = 0; i < COMUNAS_ORD.length; i++) { if (t.indexOf(COMUNAS_ORD[i]) !== -1) { return COMUNAS_ORD[i]; } }
      return '';
    };
    var key = e.comuna ? buscar(norm(e.comuna)) : '';
    if (!key) {
      var dirN = norm(e.direccion);
      var segs = dirN.split('region metropolitana')[0].split(',').map(function (s) { return s.trim(); })
        .filter(Boolean).slice(-3).reverse();
      for (var i = 0; i < segs.length && !key; i++) { key = buscar(segs[i]); }
      if (!key) { key = buscar(dirN); }
    }
    return key;
  }

  // ── el servicio de UNA entrega ────────────────────────────────────────────────────────────────
  /**
   * fila: {id, fecha, data} de la tabla `entrega` · ov: su fila de `entrega_estado` (o {}) · tareas: {id → fila de
   * tarea_estado} · eventos: las filas de postventa_evento de ESTA entrega · hoy: 'AAAA-MM-DD'.
   * Devuelve null si la entrega no está entregada (la postventa empieza cuando el baño está instalado).
   */
  function servicio(fila, ov, tareas, eventos, hoy) {
    var e = (fila && fila.data) || {};
    ov = ov || {};
    tareas = tareas || {};
    var id = texto(fila && fila.id);
    if (!id || fila.eliminado === true || ov.eliminado === true) { return null; }
    var inicio = fechaIso(ov.fecha) || fechaIso(fila.fecha) || fechaIso(e.fecha);
    if (!inicio) { return null; }
    var est = texto(ov.estado || e.estado || 'pendiente').toLowerCase();
    if (est !== 'entregado' && est !== 'cobrado') { return null; }

    var donde = texto(e.periodo) + ' ' + notasSinMarcas(e.notas) + ' ' + texto(e.servicio);
    var retiroObj = (e.retiro && typeof e.retiro === 'object' && !Array.isArray(e.retiro)) ? e.retiro : {};
    var retiroAcordado = fechaIso(retiroObj.fecha);
    var finBase;
    if (retiroAcordado) { finBase = retiroAcordado; }
    else if (esLargo(donde)) { finBase = masMeses(inicio, mesesDelPlazo(e)); }
    else {
      var dd = diasDelPlazo(donde);
      finBase = dd ? sumarDias(inicio, Math.max(dd, 1) - 1) : null;
    }
    var renovable = /renovable|mes a mes/i.test(donde) || esLargo(donde);
    var cada = cadaDias(e);

    // las anotaciones vigentes, en el orden en que se hicieron
    var evs = (eventos || []).filter(function (x) { return x && x.anulado !== true; })
      .slice().sort(function (a, b) { return String(a.created_at).localeCompare(String(b.created_at)); });
    var extensiones = evs.filter(function (x) { return x.tipo === 'extension' && fechaIso(x.fecha); });
    var ultimaExt = extensiones.length ? extensiones[extensiones.length - 1] : null;
    var retiros = evs.filter(function (x) { return x.tipo === 'retiro'; });
    var ultimoRetiro = retiros.length ? retiros[retiros.length - 1] : null;
    // una extensión DESPUÉS del retiro lo reactiva (se equivocaron o volvió a arrendar)
    if (ultimoRetiro && ultimaExt && String(ultimaExt.created_at) > String(ultimoRetiro.created_at)) { ultimoRetiro = null; }
    var ubicaciones = evs.filter(function (x) { return x.tipo === 'ubicacion' && texto(x.nota); });
    var ubicacion = ubicaciones.length ? texto(ubicaciones[ubicaciones.length - 1].nota) : '';

    var fin = ultimaExt ? fechaIso(ultimaExt.fecha) : finBase;
    var retiroTarea = (tareas[id + '::retiro'] || {}).realizada === true;
    var retirado = null;
    if (ultimoRetiro) {
      retirado = { fecha: fechaIso(ultimoRetiro.fecha) || fechaDeMarca(ultimoRetiro.created_at), por: texto(ultimoRetiro.por),
        nota: texto(ultimoRetiro.nota), fuente: 'pagina' };
    } else if (retiroTarea && !ultimaExt) {
      var t = tareas[id + '::retiro'];
      retirado = { fecha: fechaIso(t.realizada_at) ? fechaDeMarca(t.realizada_at) : (retiroAcordado || hoy), por: '',
        nota: 'marcado en la página de entregas', fuente: 'tarea' };
    }

    // limpiezas hechas: las de esta página + las que marcó el bot o la página de entregas
    var hechas = [];
    (Array.isArray(e.limpiezas) ? e.limpiezas : []).forEach(function (lp, i) {
      if (!lp || typeof lp !== 'object' || String(lp.tipo || '') === 'extra') { return; }
      var tt = tareas[id + '::lim::' + i] || {};
      if (tt.realizada === true) {
        hechas.push({ fecha: fechaIso(tt.realizada_at) || fechaIso(lp.hecha_el) || fechaIso(lp.fecha) || hoy,
          por: '', nota: texto(lp.nota), foto: '', fuente: 'bot' });
      } else if (texto(lp.estado) === 'hecha') {
        var f = fechaIso(lp.hecha_el) || fechaIso(lp.fecha);
        if (f) { hechas.push({ fecha: f, por: '', nota: texto(lp.nota), foto: '', fuente: 'bot' }); }
      }
    });
    evs.forEach(function (x) {
      if (x.tipo === 'limpieza') {
        hechas.push({ fecha: fechaIso(x.fecha) || fechaDeMarca(x.created_at), por: texto(x.por), nota: texto(x.nota),
          foto: texto(x.foto), fuente: 'pagina', id: x.id, ts: x.created_at });
      }
    });
    hechas.sort(function (a, b) { return a.fecha.localeCompare(b.fecha); });
    var hastaHoy = hechas.filter(function (h) { return h.fecha <= hoy; });
    var ultima = hastaHoy.length ? hastaHoy[hastaHoy.length - 1].fecha : null;

    // la próxima limpieza: desde la última (o desde la entrega) + el ciclo; si el baño se va antes, no hay
    var limpieza = null;
    if (cada && !retirado) {
      var base = ultima && ultima > inicio ? ultima : inicio;
      var toca = sumarDias(base, cada[0]);
      var vence = sumarDias(base, cada[1]);
      if (fin && toca > fin) {
        limpieza = { estado: 'no-toca', base: base, toca: toca, vence: vence, atraso: 0 };
      } else if (hoy < toca) {
        limpieza = { estado: 'al-dia', base: base, toca: toca, vence: vence, atraso: 0, faltan: diasEntre(hoy, toca) };
      } else if (hoy <= vence) {
        limpieza = { estado: 'toca', base: base, toca: toca, vence: vence, atraso: 0 };
      } else {
        limpieza = { estado: 'atrasada', base: base, toca: toca, vence: vence, atraso: diasEntre(vence, hoy) };
      }
    }

    var duracion = fin ? diasEntre(inicio, fin) + 1 : null;
    var corto = !cada && duracion !== null && duracion < DIAS_DESDE_ASEO_INCLUIDO;
    var grupo;
    if (retirado) { grupo = 'retirado'; }
    else if (fin && fin < hoy) {
      var pasados = diasEntre(fin, hoy);
      grupo = corto ? (pasados <= 3 ? 'retirar' : 'terminado') : (pasados <= 45 ? 'revisar' : 'terminado');
    } else if (!fin && diasEntre(inicio, hoy) > 60) { grupo = 'terminado'; }
    else { grupo = 'activo'; }

    var marcas = partirNotas(e.notas).marcas;
    var mapsUrl = texto(e.maps_url);
    var coordsTxt = texto(e.coordenadas);
    var exacto = coordsDe(ubicacion) || coordsDe(coordsTxt) || coordsDe(mapsUrl) || coordsDe(e.direccion);
    var corta = linkCorto(ubicacion) || (ubicacion ? '' : (linkCorto(mapsUrl) || linkCorto(e.direccion)));
    var navegar;
    if (ubicacion && primerLink(ubicacion)) { navegar = primerLink(ubicacion); }
    else if (ubicacion) { navegar = 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(ubicacion); }
    else if (mapsUrl) { navegar = mapsUrl; }
    else if (exacto) { navegar = 'https://www.google.com/maps/search/?api=1&query=' + exacto[0] + ',' + exacto[1]; }
    else { var mq = mapsQuery(e); navegar = mq ? 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(mq) : ''; }
    var comunaKey = comunaDe(e);

    return {
      id: id,
      cliente: texto(e.cliente) || 'Sin nombre',
      telefono: texto(e.telefono).replace(/\D/g, ''),
      direccion: ubicacion && !primerLink(ubicacion) ? ubicacion : direccionLimpia(e),
      direccionOriginal: texto(e.direccion),
      lugar: lugarCorto(e),
      cantidad: cantidadBanos(e),
      inicio: inicio,
      inicioOriginal: fechaIso(fila.fecha) || fechaIso(e.fecha),
      finBase: finBase,
      fin: fin,
      retiroAcordado: ultimaExt ? null : retiroAcordado,
      renovable: renovable,
      extensiones: extensiones,
      cadaDias: cada,
      aseoTexto: textoAseo(e),
      periodo: texto(e.periodo),
      servicioTexto: texto(e.servicio),
      hechas: hechas,
      ultimaLimpieza: ultima,
      limpieza: limpieza,
      retirado: retirado,
      grupo: grupo,
      corto: corto,
      duracion: duracion,
      marcas: marcas,
      notas: notasSinMarcas(e.notas),
      ubicacion: ubicacion,
      navegar: navegar,
      exacto: exacto,
      linkCorto: corta,
      // lo que se busca para el mapa: el link corto (lo resuelve el script), la dirección escrita a mano o la de la ficha
      geoQ: corta || (ubicacion && !primerLink(ubicacion) ? ubicacion : mapsQuery(e)),
      comunaKey: comunaKey,
      comunaCentro: comunaKey ? COMUNAS_GEO[comunaKey] : null,
      eventos: evs
    };
  }

  /** Qué buscar en OpenStreetMap, de lo más fino a lo más grueso (OSM no conoce muchos números de casa en Chile):
   *  la dirección tal cual · calle y número con la comuna · la calle sola con la comuna. */
  function consultasGeo(s) {
    var base = s.linkCorto ? mapsQuery({ direccion: s.direccionOriginal }) : s.geoQ;
    var out = [];
    var add = function (q) { q = String(q || '').replace(/\s+/g, ' ').replace(/^[\s,.-]+|[\s,.-]+$/g, ''); if (q.length >= 4 && out.indexOf(q) === -1) { out.push(q); } };
    add(base);
    var comuna = s.comunaKey ? s.comunaKey.replace(/(^|\s)(\S)/g, function (_, a, b) { return a + b.toUpperCase(); }) : '';
    var segs = String(base || '').split(/[,.]\s+|,/).map(function (x) { return x.trim(); }).filter(Boolean);
    // sin comuna conocida, la búsqueda se acota a la Región Metropolitana (hay una Av. Santa Rosa en cada ciudad)
    if (!comuna && out.length && !/metropolitana|santiago/i.test(out[0])) { out[0] = out[0] + ', Región Metropolitana'; }
    var conNum = segs.filter(function (x) {
      return /\d/.test(x) && /[a-záéíóúñ]{3}/i.test(x) && !/^(paradero|casa|depto|dpto|departamento|lote|parcela|sitio|local|of|oficina|km)\b/i.test(x);
    })[0];
    if (conNum) {
      var limpio = conNum.replace(/\b(casa|depto|dpto|departamento|of|oficina|lote|parcela|sitio|local|condominio)\b.*$/i, '')
        .replace(/N[°º]|#|°|º/g, ' ').replace(/^calle\s+/i, '').replace(/\bav(da)?\.?\s/i, 'Avenida ').replace(/\s+/g, ' ').trim();
      var conComuna = function (t) {
        if (!comuna) { return /metropolitana/i.test(t) ? t : t + ', Región Metropolitana'; }
        return PV_norm(t).indexOf(PV_norm(comuna)) === -1 ? t + ', ' + comuna : t;
      };
      add(conComuna(limpio));
      var calle = limpio.replace(/\b\d[\d.]*\b/g, ' ').replace(/\s+/g, ' ').trim();
      if (calle.length >= 4 && calle !== limpio) { add(conComuna(calle)); }
    }
    return out.slice(0, 3);
  }
  function PV_norm(t) { return norm(t); }

  /** ¿Un punto encontrado es creíble? A menos de 30 km del centro de su comuna (si se sabe) y dentro de la zona. */
  function puntoCreible(s, lat, lng) {
    if (!(lat < -32.9 && lat > -34.4 && lng < -70.1 && lng > -71.8)) { return false; }
    if (!s.comunaCentro) { return true; }
    var dy = (lat - s.comunaCentro[0]) * 111;
    var dx = (lng - s.comunaCentro[1]) * 93;
    return Math.sqrt(dx * dx + dy * dy) <= 30;
  }

  /** Mes del arriendo en que va (1 = el primero), contado desde la entrega. */
  function mesDelArriendo(inicio, hoy) {
    var n = 0;
    while (n < 120 && masMeses(inicio, n + 1) <= hoy) { n += 1; }
    return n + 1;
  }

  /** ¿Qué le toca a este servicio hoy? Para los filtros y el orden (más urgente primero). */
  function urgencia(s, hoy) {
    var p = 0;
    if (s.grupo === 'revisar') { p = Math.max(p, 70 + Math.min(diasEntre(s.fin, hoy), 20)); }
    if (s.grupo === 'retirar') { p = Math.max(p, 80); }
    if (s.limpieza && s.limpieza.estado === 'atrasada') { p = Math.max(p, 60 + Math.min(s.limpieza.atraso, 30)); }
    if (s.limpieza && s.limpieza.estado === 'toca') { p = Math.max(p, 50); }
    if (s.grupo === 'activo' && s.fin && s.fin === hoy) { p = Math.max(p, s.corto || !s.renovable ? 78 : 55); }
    if (s.grupo === 'activo' && s.fin && s.fin > hoy && diasEntre(hoy, s.fin) <= 5) { p = Math.max(p, 40 - diasEntre(hoy, s.fin)); }
    return p;
  }

  var api = {
    ASEO_LARGO: ASEO_LARGO, COMUNAS_GEO: COMUNAS_GEO,
    texto: texto, norm: norm, fechaIso: fechaIso, partirNotas: partirNotas, notasSinMarcas: notasSinMarcas,
    esLargo: esLargo, diasDelPlazo: diasDelPlazo, mesesDelPlazo: mesesDelPlazo, textoAseo: textoAseo,
    cadaDias: cadaDias, cantidadBanos: cantidadBanos, sumarDias: sumarDias, diasEntre: diasEntre,
    masMeses: masMeses, hoyLocal: hoyLocal, fechaDeMarca: fechaDeMarca, lugarCorto: lugarCorto,
    direccionLimpia: direccionLimpia, mapsQuery: mapsQuery, coordsDe: coordsDe, deGeohash: deGeohash,
    linkCorto: linkCorto, comunaDe: comunaDe, servicio: servicio, consultasGeo: consultasGeo, puntoCreible: puntoCreible, mesDelArriendo: mesDelArriendo, urgencia: urgencia
  };
  if (typeof module === 'object' && module.exports) { module.exports = api; }
  else { raiz.PV = api; }
})(typeof window !== 'undefined' ? window : this);
