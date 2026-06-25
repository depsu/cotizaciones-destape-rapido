#!/usr/bin/env python3
"""Genera un listado web (HTML mobile-first) de entregas a partir de entregas.json.

El HTML es autocontenido (sin dependencias externas): se puede abrir directo en
el celular o subir al hosting. Cada entrega se muestra agrupada por fecha; al
tocarla se despliega toda la info, con botones de WhatsApp al cliente, mapa para
llegar y llamar.

Uso:
    python scripts/generar_listado.py            # genera ../listado.html
    python scripts/generar_listado.py salida.html
"""

from __future__ import annotations

import html
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

BASE = Path(__file__).resolve().parent.parent
DATA_PATH = BASE / "entregas.json"
DEFAULT_OUT = BASE / "listado.html"

# Supabase: estado mutable de las entregas (lo cambia el repartidor desde la
# página y lo ve Alejandro). La anon key es pública por diseño (ya viaja en el
# bundle de la app); el acceso está acotado por RLS a la tabla entrega_estado.
# Ver resumen-repartidor/supabase/entrega_estado.sql
SUPABASE_URL = "https://abmzkzraptmjgebwjzys.supabase.co"
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFibXprenJhcHRtamdlYndqenlzIiwicm9sZSI6"
    "ImFub24iLCJpYXQiOjE3NzY5MDA1ODQsImV4cCI6MjA5MjQ3NjU4NH0."
    "9qN07nBI9HdfreiWdVFl1cYrT5tlke7WWr5wi_Cwbho"
)

# Comisión de Alejandro: 20% del valor NETO de cada cliente conseguido.
TASA_COMISION = 0.20
IVA = 1.19

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

# Frecuencia de aseo por defecto si la entrega no especifica otra.
ASEO_DEFAULT = "Aseo semanal (cada 7 a 10 días)"

ESTADOS = {
    "pendiente": ("Pendiente", "#B45309", "#FEF3C7"),
    "en-camino": ("En camino", "#1E40AF", "#DBEAFE"),
    "entregado": ("Entregado", "#166534", "#DCFCE7"),
}

# Tipo de limpieza: "incluida" (parte del arriendo) o "extra" (se cobra aparte).
TIPO_LIMPIEZA = {
    "incluida": ("Incluida", "#166534", "#DCFCE7"),
    "extra": ("Extra", "#B45309", "#FEF3C7"),
}
# Estado de cada limpieza: pendiente o hecha.
ESTADO_LIMPIEZA = {
    "pendiente": ("○", "#94A3B8"),
    "hecha": ("✓", "#166534"),
}


def clp(monto) -> str:
    """Formatea un número como pesos chilenos: 160000 -> $160.000."""
    try:
        n = int(round(float(monto)))
    except (TypeError, ValueError):
        return str(monto)
    return "$" + f"{n:,}".replace(",", ".")


def neto_de(e: dict):
    """Valor neto de la entrega: si lleva factura, monto/1,19; si es boleta, el monto."""
    monto = (e.get("pago") or {}).get("monto")
    if monto is None:
        return None
    lleva_factura = bool((e.get("factura") or {}).get("requiere"))
    return int(round(monto / IVA)) if lleva_factura else int(monto)


def comisiona(e: dict) -> bool:
    """¿Esta entrega genera comisión? (default sí, salvo comision:false o sin monto)."""
    if e.get("comision") is False:
        return False
    return (e.get("pago") or {}).get("monto") is not None


def comision_de(e: dict) -> int:
    """Comisión de Alejandro para la entrega: 20% del neto (0 si no comisiona)."""
    if not comisiona(e):
        return 0
    return int(round((neto_de(e) or 0) * TASA_COMISION))


def cantidad_banos(e: dict) -> int:
    """Cantidad de baños: usa 'cantidad' o la infiere del texto del servicio."""
    c = e.get("cantidad")
    if isinstance(c, int) and c > 0:
        return c
    m = re.search(r"(\d+)\s*ba[ñn]o", e.get("servicio", ""), re.IGNORECASE)
    return int(m.group(1)) if m else 1


def icono_banos(n: int) -> str:
    """1–4 baños => esa cantidad de 🚽; más de 4 => 🚽+."""
    if n <= 0:
        n = 1
    return "🚽+" if n > 4 else "🚽" * n


def solo_digitos(telefono: str) -> str:
    d = re.sub(r"\D", "", telefono or "")
    if d.startswith("56"):
        return d
    if d.startswith("9") and len(d) == 9:
        return "56" + d
    return d


def esc(texto: str) -> str:
    return html.escape(str(texto or ""))


def encabezado_fecha(iso: str) -> str:
    try:
        f = date.fromisoformat(iso)
        return f"{DIAS[f.weekday()].capitalize()} {f.day} de {MESES[f.month - 1]}"
    except (ValueError, IndexError):
        return iso or "Sin fecha"


def fecha_corta(iso: str) -> str:
    """Fecha compacta para la lista de limpiezas: '26 jun' o 'vie 26 jun'."""
    try:
        f = date.fromisoformat(iso)
        return f"{DIAS[f.weekday()][:3]} {f.day} {MESES[f.month - 1][:3]}"
    except (ValueError, IndexError):
        return iso or ""


def limpiezas_html(e: dict) -> str:
    """Bloque de limpiezas: lista las que corresponden (incluidas) y las extras.

    Cada limpieza en entregas.json: {fecha, etiqueta?, tipo: incluida|extra,
    valor? (CLP, solo extras), estado: pendiente|hecha, nota?}.
    Si la entrega no tiene 'limpiezas', el bloque no se muestra.
    """
    limpiezas = e.get("limpiezas") or []
    if not limpiezas:
        return ""

    filas = []
    total_extra = 0
    n_extra = 0
    for lp in limpiezas:
        tipo = lp.get("tipo", "incluida")
        etq_t, col_t, bg_t = TIPO_LIMPIEZA.get(tipo, TIPO_LIMPIEZA["incluida"])
        estado = lp.get("estado", "pendiente")
        marca, col_e = ESTADO_LIMPIEZA.get(estado, ESTADO_LIMPIEZA["pendiente"])
        valor = lp.get("valor")
        valor_html = ""
        if tipo == "extra" and valor:
            total_extra += valor
            n_extra += 1
            valor_html = f'<span class="lp-valor">{esc(clp(valor))}</span>'
        etiqueta = esc(lp.get("etiqueta") or "Limpieza")
        fecha_l = esc(fecha_corta(lp.get("fecha", "")))
        nota = f'<span class="lp-nota">{esc(lp.get("nota"))}</span>' if lp.get("nota") else ""
        clase_hecha = " lp-done" if estado == "hecha" else ""
        filas.append(
            f'<li class="lp-item{clase_hecha}">'
            f'<span class="lp-check" style="color:{col_e}">{marca}</span>'
            f'<span class="lp-fecha">{fecha_l}</span>'
            f'<span class="lp-etq">{etiqueta}{nota}</span>'
            f'<span class="lp-badge" style="color:{col_t};background:{bg_t}">{etq_t}</span>'
            f'{valor_html}</li>'
        )

    total_html = ""
    if n_extra:
        total_html = (
            f'<div class="lp-total">{n_extra} limpieza(s) extra · '
            f'<b>{esc(clp(total_extra))} neto</b></div>'
        )
    return (
        f'<div class="bloque"><span class="etq">🧽 Limpiezas</span>'
        f'<ul class="lp-lista">{"".join(filas)}</ul>{total_html}</div>'
    )


def boton(href: str, etiqueta: str, color: str) -> str:
    return (
        f'<a class="btn" href="{esc(href)}" target="_blank" rel="noopener" '
        f'style="background:{color}">{etiqueta}</a>'
    )


def tarjeta(e: dict) -> str:
    cliente = esc(e.get("cliente", "—"))
    direccion = e.get("direccion", "")
    telefono = e.get("telefono", "")
    servicio = esc(e.get("servicio", ""))
    banos_icono = icono_banos(cantidad_banos(e))
    hora = esc(e.get("hora", ""))
    notas = e.get("notas", "")
    estado = e.get("estado", "pendiente")
    etiqueta, color_txt, color_bg = ESTADOS.get(estado, ESTADOS["pendiente"])
    ent_id = e.get("id", "")
    fecha_iso = e.get("fecha", "")

    # Bloque de gestión: estado (lo cambia el repartidor), reagendar y comisión.
    neto = neto_de(e)
    com = comision_de(e)
    if comisiona(e):
        comision_mini = (
            f'<div class="comision-mini">💰 Tu comisión: <b>{esc(clp(com))}</b>'
            f'<span class="cm-base">20% de {esc(clp(neto))} neto</span></div>'
        )
    else:
        comision_mini = '<div class="comision-mini comision-no">Sin comisión (servicio extra)</div>'
    gestion_html = (
        '<div class="gestion"><span class="etq">Gestión</span>'
        '<div class="estado-control" role="group" aria-label="Estado de la entrega">'
        '<button type="button" class="est-btn" data-estado="pendiente">Pendiente</button>'
        '<button type="button" class="est-btn" data-estado="entregado">Entregado</button>'
        '<button type="button" class="est-btn est-cobrado" data-estado="cobrado">✓ Cobrado</button>'
        '</div>'
        '<label class="reagendar"><span class="rg-lbl">📅 Reagendar entrega</span>'
        f'<input type="date" class="fecha-input" value="{esc(fecha_iso)}"></label>'
        f'{comision_mini}</div>'
    )

    # Pago: lo que el repartidor (dueño) le cobra al cliente.
    pago = e.get("pago") or {}
    monto = pago.get("monto")
    monto_chip = f'<span class="monto">💵 {esc(clp(monto))}</span>' if monto is not None else ""
    cobro_html = ""
    if monto is not None:
        nota_pago = f'<span class="cobro-nota">{esc(pago.get("nota"))}</span>' if pago.get("nota") else ""
        cobro_html = (
            f'<div class="cobro"><span class="cobro-etq">💵 Cobrar al cliente</span>'
            f'<span class="cobro-monto">{esc(clp(monto))}</span>{nota_pago}</div>'
        )

    # Aseo: lo indicado o el valor por defecto.
    aseo = esc(e.get("aseo") or ASEO_DEFAULT)

    # Limpiezas (incluidas + extras), si la entrega las define.
    limpiezas_bloque = limpiezas_html(e)

    # Factura (si el cliente la requiere).
    factura = e.get("factura") or {}
    factura_html = ""
    if factura.get("requiere") or factura.get("razon_social"):
        filas = []
        for etq, clave in (("Razón social", "razon_social"), ("RUT", "rut"),
                           ("Giro", "giro"), ("Dirección", "direccion"), ("Email", "email")):
            if factura.get(clave):
                filas.append(f"<li><b>{etq}:</b> {esc(factura[clave])}</li>")
        cuerpo = f"<ul>{''.join(filas)}</ul>" if filas else "<p>Requiere factura.</p>"
        factura_html = f'<div class="bloque"><span class="etq">🧾 Factura</span>{cuerpo}</div>'

    detalle = e.get("detalle") or []
    detalle_html = ""
    if detalle:
        items = "".join(f"<li>{esc(d)}</li>" for d in detalle)
        detalle_html = f'<div class="bloque"><span class="etq">Qué hacer</span><ul>{items}</ul></div>'

    notas_html = ""
    if notas:
        notas_html = f'<div class="bloque"><span class="etq">Notas</span><p>{esc(notas)}</p></div>'

    # Botones de acción.
    num = solo_digitos(telefono)
    botones = []
    if num:
        botones.append(boton(f"https://wa.me/{num}", "💬 WhatsApp", "#22A45D"))
        botones.append(boton(f"tel:{esc(telefono)}", "📞 Llamar", "#475569"))
    if direccion:
        maps = f"https://www.google.com/maps/search/?api=1&query={quote(direccion)}"
        botones.append(boton(maps, "🗺️ Cómo llegar", "#1F5AA8"))
    botones_html = f'<div class="acciones">{"".join(botones)}</div>'

    hora_chip = f'<span class="hora">🕐 {hora}</span>' if hora else ""

    return f"""
    <details class="card" data-id="{esc(ent_id)}" data-fecha="{esc(fecha_iso)}" data-estado-orig="{esc(estado)}">
      <summary>
        <div class="resumen-top">
          <span class="cliente">{cliente}</span>
          <span class="badge" style="color:{color_txt};background:{color_bg}">{etiqueta}</span>
        </div>
        <div class="resumen-sub">
          <span class="banos">{banos_icono}</span>
          <span class="dir">📍 {esc(direccion)}</span>
          {hora_chip}
          {monto_chip}
        </div>
        <div class="reagendada-chip" hidden></div>
      </summary>
      <div class="detalle">
        {gestion_html}
        {cobro_html}
        {f'<div class="bloque"><span class="etq">Servicio</span><p>{banos_icono} {servicio}</p></div>' if servicio else ""}
        <div class="bloque"><span class="etq">Aseo</span><p>{aseo}</p></div>
        {limpiezas_bloque}
        {f'<div class="bloque"><span class="etq">Teléfono</span><p>{esc(telefono)}</p></div>' if telefono else ""}
        {factura_html}
        {detalle_html}
        {notas_html}
        {botones_html}
      </div>
    </details>"""


# CSS extra (gestión por tarjeta + panel de comisión). Se inyecta como variable
# para evitar duplicar llaves dentro del f-string del <style>.
ESTILOS_EXTRA = """
  /* Gestión por tarjeta */
  .gestion { margin-top:4px; padding:12px 14px; background:#F8FAFC; border:1px solid var(--linea); border-radius:12px; }
  .estado-control { display:flex; gap:6px; margin-top:4px; }
  .est-btn { flex:1 1 0; padding:9px 6px; border:1px solid var(--linea); background:#fff; color:var(--gris);
    font-size:13px; font-weight:600; border-radius:9px; cursor:pointer; font-family:inherit; min-height:42px; }
  .est-btn:active { filter:brightness(.96); }
  .est-btn.activo { background:var(--azul); color:#fff; border-color:var(--azul); }
  .est-btn.est-cobrado.activo { background:#065F46; border-color:#065F46; }
  .reagendar { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-top:10px; font-size:14px; }
  .rg-lbl { color:var(--gris); font-weight:600; }
  .fecha-input { font-family:inherit; font-size:15px; padding:8px 10px; border:1px solid var(--linea);
    border-radius:9px; background:#fff; color:var(--tinta); min-height:40px; }
  .comision-mini { margin-top:10px; font-size:14px; color:#7C3AED; display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 8px; }
  .comision-mini b { font-size:16px; }
  .comision-mini .cm-base { color:var(--gris); font-size:12px; }
  .comision-mini.comision-no { color:var(--gris); }
  .reagendada-chip { margin-top:6px; font-size:12px; font-weight:700; color:#B45309; background:#FEF3C7;
    display:inline-block; padding:3px 9px; border-radius:20px; }
  /* Panel de comisión */
  .comision-panel { background:#fff; border:1px solid var(--linea); border-radius:16px; padding:16px;
    margin:6px 0 16px; box-shadow:0 2px 10px rgba(124,58,237,.08); border-top:4px solid #7C3AED; }
  .cp-head { display:flex; align-items:center; justify-content:space-between; }
  .cp-titulo { font-size:15px; font-weight:800; color:#5B21B6; text-transform:uppercase; letter-spacing:.5px; }
  .cp-total { display:flex; align-items:baseline; justify-content:space-between; margin-top:10px; gap:10px; }
  .cp-total-lbl { font-size:13px; color:var(--gris); font-weight:600; }
  .cp-total-val { font-size:30px; font-weight:800; color:#5B21B6; font-variant-numeric:tabular-nums; }
  .cp-sub { margin-top:4px; font-size:13px; color:var(--gris); }
  .cp-lista { list-style:none; margin:14px 0 0; padding:0; }
  .cp-row { display:flex; align-items:center; gap:8px; padding:9px 0; border-top:1px solid var(--linea); font-size:14px; }
  .cp-cli { flex:1 1 auto; min-width:0; font-weight:600; overflow-wrap:anywhere; }
  .cp-chip { font-size:10px; font-weight:700; padding:2px 8px; border-radius:20px; white-space:nowrap; text-transform:uppercase; letter-spacing:.4px; }
  .cp-chip.cp-pagada { color:#166534; background:#DCFCE7; }
  .cp-monto { font-weight:800; color:#5B21B6; font-variant-numeric:tabular-nums; white-space:nowrap; }
  .cp-row-pagada .cp-monto, .cp-row-pagada .cp-cli { opacity:.5; text-decoration:line-through; }
  .cp-toggle { font-family:inherit; font-size:12px; font-weight:600; padding:6px 9px; border-radius:8px;
    border:1px solid var(--linea); background:#fff; color:var(--azul); cursor:pointer; white-space:nowrap; }
  .cp-toggle.on { background:#DCFCE7; border-color:#BBF7D0; color:#166534; }
  .cp-vacio { color:var(--gris); font-size:13px; margin-top:10px; }
  .estado-online { display:block; margin:0 0 12px; padding:10px 14px; border-radius:10px; font-size:13px; font-weight:600;
    background:#FEF2F2; color:#B91C1C; border:1px solid #FECACA; }
  /* Pestañas de vista (Entregas / Comisión) */
  .vistas { display:flex; gap:8px; margin:0 0 14px; }
  .vista-btn { flex:1 1 0; padding:11px; border:1px solid var(--linea); background:#fff; color:var(--gris);
    font-family:inherit; font-size:14px; font-weight:700; border-radius:11px; cursor:pointer; min-height:46px; }
  .vista-btn:active { filter:brightness(.96); }
  .vista-btn.activo { background:var(--azul); color:#fff; border-color:var(--azul); }
  .vista[hidden] { display:none; }
  /* Secciones agregadas (limpiezas / retiros) */
  .agregado { margin-top:22px; }
  .ag-lista { list-style:none; margin:8px 0 0; padding:0; }
  .ag-item { display:flex; align-items:flex-start; gap:10px; padding:11px 12px; margin-top:8px;
    background:#fff; border:1px solid var(--linea); border-radius:12px; font-size:14px; }
  .ag-fecha { font-variant-numeric:tabular-nums; white-space:nowrap; color:var(--gris); flex:none; min-width:64px; font-weight:600; }
  .ag-main { flex:1 1 auto; min-width:0; display:flex; flex-direction:column; gap:2px; }
  .ag-dir { color:var(--gris); font-size:13px; overflow-wrap:anywhere; }
  .ag-sub { color:var(--gris); font-size:13px; }
  .agregado .lp-badge { align-self:center; }
  .agregado .lp-valor { align-self:center; }
"""

# JS que carga el estado desde Supabase, cablea los controles de cada tarjeta y
# calcula/pinta el panel de comisión. No es f-string: las llaves van literales.
SCRIPT_ESTADO = r"""<script>
(function () {
  var APP = window.__APP__ || {};
  var SUPA = { url: APP.url, key: APP.key };
  var META = {};
  (APP.entregas || []).forEach(function (e) { META[e.id] = e; });
  var estado = {}; // id -> {id, estado, fecha, comision_pagada}

  var ESTADOS = {
    'pendiente': ['Pendiente', '#B45309', '#FEF3C7'],
    'en-camino': ['En camino', '#1E40AF', '#DBEAFE'],
    'entregado': ['Entregado', '#166534', '#DCFCE7'],
    'cobrado':   ['✓ Cobrado', '#065F46', '#A7F3D0']
  };
  var MESES = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];

  function clp(n) { return '$' + (Math.round(Number(n) || 0)).toLocaleString('es-CL'); }
  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' }[c];
    });
  }
  function fechaLarga(iso) {
    var p = (iso || '').split('-');
    if (p.length !== 3) return iso;
    return parseInt(p[2], 10) + ' ' + (MESES[parseInt(p[1], 10) - 1] || '') + ' ' + p[0];
  }
  function headers(extra) {
    var h = { 'apikey': SUPA.key, 'Authorization': 'Bearer ' + SUPA.key };
    if (extra) { for (var k in extra) h[k] = extra[k]; }
    return h;
  }

  function estadoDe(id) {
    var st = estado[id];
    if (st && st.estado) return st.estado;
    return (META[id] && META[id].estado) || 'pendiente';
  }
  function fechaDe(id) {
    var st = estado[id];
    if (st && st.fecha) return st.fecha;
    return (META[id] && META[id].fecha) || '';
  }
  function pagadaDe(id) {
    var st = estado[id];
    if (st && typeof st.comision_pagada === 'boolean') return st.comision_pagada;
    return !!(META[id] && META[id].comision_pagada);
  }

  function pintarCard(card) {
    var id = card.getAttribute('data-id');
    var est = estadoDe(id);
    var info = ESTADOS[est] || ESTADOS['pendiente'];
    var badge = card.querySelector('.badge');
    if (badge) { badge.textContent = info[0]; badge.style.color = info[1]; badge.style.background = info[2]; }
    card.querySelectorAll('.est-btn').forEach(function (b) {
      b.classList.toggle('activo', b.getAttribute('data-estado') === est);
    });
    var input = card.querySelector('.fecha-input');
    var fOrig = card.getAttribute('data-fecha');
    var fAct = fechaDe(id);
    if (input && fAct) { input.value = fAct; }
    var chip = card.querySelector('.reagendada-chip');
    if (chip) {
      if (fAct && fAct !== fOrig) { chip.hidden = false; chip.textContent = '📅 Reagendada: ' + fechaLarga(fAct); }
      else { chip.hidden = true; }
    }
  }
  function pintarTodo() { document.querySelectorAll('.card[data-id]').forEach(pintarCard); }

  function renderPanel() {
    var panel = document.getElementById('comision-panel');
    if (!panel) return;
    var rows = [], teDeben = 0, porCobrar = 0, yaPagada = 0;
    Object.keys(META).forEach(function (id) {
      var m = META[id];
      if (!m.comisiona || !m.comision) return;
      var est = estadoDe(id), pagada = pagadaDe(id), cobrada = (est === 'cobrado');
      if (cobrada && !pagada) teDeben += m.comision;
      else if (cobrada && pagada) yaPagada += m.comision;
      else porCobrar += m.comision;
      rows.push({ id: id, cliente: m.cliente, comision: m.comision, est: est, pagada: pagada, cobrada: cobrada });
    });
    rows.sort(function (a, b) { return b.comision - a.comision; });

    var lis = rows.map(function (r) {
      var info = ESTADOS[r.est] || ESTADOS['pendiente'];
      var chip = r.pagada
        ? '<span class="cp-chip cp-pagada">✓ Pagada</span>'
        : '<span class="cp-chip" style="color:' + info[1] + ';background:' + info[2] + '">' + info[0] + '</span>';
      var accion = r.cobrada
        ? '<button type="button" class="cp-toggle' + (r.pagada ? ' on' : '') + '" data-id="' + escapeHtml(r.id) + '">' + (r.pagada ? 'Pagada' : 'Marcar pagada') + '</button>'
        : '';
      return '<li class="cp-row' + (r.pagada ? ' cp-row-pagada' : '') + '">'
        + '<span class="cp-cli">' + escapeHtml(r.cliente) + '</span>' + chip
        + '<span class="cp-monto">' + clp(r.comision) + '</span>' + accion + '</li>';
    }).join('');
    if (!rows.length) { lis = '<p class="cp-vacio">No hay entregas que generen comisión.</p>'; }

    panel.innerHTML =
      '<div class="cp-head"><span class="cp-titulo">💰 Comisión a pagar</span></div>'
      + '<div class="cp-total"><span class="cp-total-lbl">Te deben ahora</span>'
      + '<span class="cp-total-val">' + clp(teDeben) + '</span></div>'
      + '<div class="cp-sub">Por cobrar (pendientes): <b>' + clp(porCobrar) + '</b>'
      + (yaPagada ? ' · Ya pagada: ' + clp(yaPagada) : '') + '</div>'
      + '<ul class="cp-lista">' + lis + '</ul>';
    panel.hidden = false;
    panel.querySelectorAll('.cp-toggle').forEach(function (b) {
      b.addEventListener('click', function () {
        var id = b.getAttribute('data-id');
        upsert(id, { comision_pagada: !pagadaDe(id) });
      });
    });
  }

  function bannerOnline(ok) {
    var p = document.getElementById('estado-online');
    if (!p) return;
    if (ok) { p.hidden = true; }
    else { p.hidden = false; p.textContent = '⚠ Sin conexión: el último cambio no se guardó. Reintenta.'; }
  }

  function upsert(id, patch) {
    var row = { id: id, estado: estadoDe(id), fecha: fechaDe(id) || null, comision_pagada: pagadaDe(id) };
    for (var k in patch) { row[k] = patch[k]; }
    if (row.fecha === '') { row.fecha = null; }
    estado[id] = row;
    var card = document.querySelector('.card[data-id="' + String(id).replace(/"/g, '\\"') + '"]');
    if (card) { pintarCard(card); }
    renderPanel();
    if (!SUPA.url || !SUPA.key) return;
    fetch(SUPA.url + '/rest/v1/entrega_estado', {
      method: 'POST',
      headers: headers({ 'Content-Type': 'application/json', 'Prefer': 'resolution=merge-duplicates,return=minimal' }),
      body: JSON.stringify(row)
    }).then(function (r) {
      if (!r.ok) { throw new Error('HTTP ' + r.status); }
      bannerOnline(true);
    }).catch(function (e) { console.warn('No se pudo guardar', e); bannerOnline(false); });
  }

  function load() {
    if (!SUPA.url || !SUPA.key) { pintarTodo(); renderPanel(); return; }
    fetch(SUPA.url + '/rest/v1/entrega_estado?select=*', { headers: headers() })
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (rows) { rows.forEach(function (row) { estado[row.id] = row; }); })
      .catch(function (e) { console.warn(e); })
      .then(function () { pintarTodo(); renderPanel(); });
  }

  function wire() {
    document.querySelectorAll('.card[data-id]').forEach(function (card) {
      var id = card.getAttribute('data-id');
      card.querySelectorAll('.est-btn').forEach(function (b) {
        b.addEventListener('click', function (ev) {
          ev.preventDefault(); ev.stopPropagation();
          upsert(id, { estado: b.getAttribute('data-estado') });
        });
      });
      var input = card.querySelector('.fecha-input');
      if (input) {
        input.addEventListener('click', function (ev) { ev.stopPropagation(); });
        input.addEventListener('change', function () { upsert(id, { fecha: input.value || null }); });
      }
    });
  }

  function wireVistas() {
    var btns = document.querySelectorAll('.vista-btn');
    btns.forEach(function (b) {
      b.addEventListener('click', function () {
        var v = b.getAttribute('data-vista');
        btns.forEach(function (x) { x.classList.toggle('activo', x === b); });
        document.querySelectorAll('.vista').forEach(function (sec) {
          sec.hidden = (sec.getAttribute('data-vista') !== v);
        });
        window.scrollTo(0, 0);
      });
    });
  }

  wireVistas();
  wire();
  load();
})();
</script>"""


def seccion_limpiezas(entregas: list) -> str:
    """Sección agregada con TODAS las limpiezas pendientes, ordenadas por fecha."""
    filas = []
    for e in entregas:
        for lp in (e.get("limpiezas") or []):
            if lp.get("estado") == "hecha":
                continue
            filas.append((lp.get("fecha", ""), e, lp))
    if not filas:
        return ""
    filas.sort(key=lambda x: x[0])
    items = []
    for fecha, e, lp in filas:
        tipo = lp.get("tipo", "incluida")
        etq_t, col_t, bg_t = TIPO_LIMPIEZA.get(tipo, TIPO_LIMPIEZA["incluida"])
        valor = lp.get("valor")
        valor_html = (
            f'<span class="lp-valor">{esc(clp(valor))}</span>'
            if tipo == "extra" and valor else ""
        )
        nota = f'<span class="ag-sub">{esc(lp.get("nota"))}</span>' if lp.get("nota") else ""
        items.append(
            '<li class="ag-item">'
            f'<span class="ag-fecha">{esc(fecha_corta(fecha))}</span>'
            f'<span class="ag-main"><b>{esc(e.get("cliente", "—"))}</b>'
            f'<span class="ag-dir">📍 {esc(e.get("direccion", ""))}</span>'
            f'<span class="ag-sub">{esc(lp.get("etiqueta") or "Limpieza")}</span>{nota}</span>'
            f'<span class="lp-badge" style="color:{col_t};background:{bg_t}">{etq_t}</span>'
            f'{valor_html}</li>'
        )
    return (
        '<section class="agregado"><h2 class="fecha-titulo">🧽 Limpiezas a realizar'
        f'<span class="conteo">{len(filas)}</span></h2>'
        f'<ul class="ag-lista">{"".join(items)}</ul></section>'
    )


def seccion_retiros(entregas: list) -> str:
    """Sección agregada con los retiros programados, ordenados por fecha."""
    datos = [(r.get("fecha", ""), e, r) for e in entregas if (r := e.get("retiro"))]
    if not datos:
        return ""
    datos.sort(key=lambda x: x[0])
    items = []
    for fecha, e, r in datos:
        nota = f'<span class="ag-sub">{esc(r.get("nota"))}</span>' if r.get("nota") else ""
        items.append(
            '<li class="ag-item">'
            f'<span class="ag-fecha">{esc(fecha_corta(fecha))}</span>'
            f'<span class="ag-main"><b>{esc(e.get("cliente", "—"))}</b>'
            f'<span class="ag-dir">📍 {esc(e.get("direccion", ""))}</span>{nota}</span>'
            '<span class="lp-badge" style="color:#1E40AF;background:#DBEAFE">Retiro</span></li>'
        )
    return (
        '<section class="agregado"><h2 class="fecha-titulo">📦 Retiros'
        f'<span class="conteo">{len(datos)}</span></h2>'
        f'<ul class="ag-lista">{"".join(items)}</ul></section>'
    )


def construir_html(data: dict) -> str:
    entregas = data.get("entregas", [])
    # Ordenar por fecha y agrupar.
    entregas_ordenadas = sorted(entregas, key=lambda e: (e.get("fecha", ""), e.get("hora", "")))

    grupos: dict[str, list] = {}
    for e in entregas_ordenadas:
        grupos.setdefault(e.get("fecha", ""), []).append(e)

    pendientes = sum(1 for e in entregas if e.get("estado", "pendiente") not in ("entregado", "cobrado"))

    secciones = []
    for fecha, items in grupos.items():
        tarjetas = "".join(tarjeta(e) for e in items)
        secciones.append(
            f'<section data-fecha="{esc(fecha)}"><h2 class="fecha-titulo">{esc(encabezado_fecha(fecha))}'
            f'<span class="conteo">{len(items)}</span></h2>{tarjetas}</section>'
        )

    # Metadatos por entrega para el JS (cálculo de comisión y panel).
    meta = [
        {
            "id": e.get("id", ""),
            "cliente": e.get("cliente", "—"),
            "fecha": e.get("fecha", ""),
            "neto": neto_de(e) or 0,
            "comision": comision_de(e),
            "comisiona": comisiona(e),
            "estado": e.get("estado", "pendiente"),
            "comision_pagada": bool(e.get("comision_pagada", False)),
        }
        for e in entregas
    ]
    config_json = json.dumps(
        {"url": SUPABASE_URL, "key": SUPABASE_ANON_KEY, "entregas": meta},
        ensure_ascii=False,
    ).replace("</", "<\\/")  # evita cerrar el <script> con datos
    config_script = f"<script>window.__APP__ = {config_json};</script>"

    # Botón para mostrar las entregas de días anteriores (ocultas por defecto vía JS).
    boton_anteriores = '<button id="toggle-anteriores" class="ver-anteriores" type="button" hidden></button>'

    # Secciones agregadas que van DEBAJO de las entregas (misma vista).
    limpiezas_sec = seccion_limpiezas(entregas)
    retiros_sec = seccion_retiros(entregas)

    if secciones:
        vista_entregas = boton_anteriores + "".join(secciones) + limpiezas_sec + retiros_sec
    else:
        vista_entregas = '<p class="vacio">No hay entregas cargadas.</p>'

    # Barra de pestañas + dos vistas (entregas / comisión). El JS las alterna sin
    # regenerar la página. El aviso de conexión queda arriba, visible en ambas.
    cuerpo = (
        '<div id="estado-online" class="estado-online" hidden></div>'
        '<div class="vistas">'
        '<button type="button" class="vista-btn activo" data-vista="entregas">🚚 Entregas</button>'
        '<button type="button" class="vista-btn" data-vista="comision">💰 Comisión</button>'
        '</div>'
        f'<div class="vista" data-vista="entregas">{vista_entregas}</div>'
        '<div class="vista" data-vista="comision" hidden>'
        '<div id="comision-panel" class="comision-panel"></div>'
        '</div>'
    )
    actualizado = date.today().strftime("%d/%m/%Y")

    # JS: oculta las secciones de días anteriores (según la fecha REAL del celular)
    # y muestra un botón "Ver anteriores" para desplegarlas. No es f-string: las
    # llaves van literales (no se duplican).
    script = """<script>
(function () {
  var ahora = new Date();
  var hoyISO = ahora.getFullYear() + '-' +
    String(ahora.getMonth() + 1).padStart(2, '0') + '-' +
    String(ahora.getDate()).padStart(2, '0');
  var pasadas = [];
  document.querySelectorAll('section[data-fecha]').forEach(function (s) {
    var f = s.getAttribute('data-fecha');
    if (f && f < hoyISO) { s.classList.add('pasada'); pasadas.push(s); }
  });
  var btn = document.getElementById('toggle-anteriores');
  if (!btn) { return; }
  if (pasadas.length === 0) { btn.remove(); return; }
  var abierto = false;
  function pintar() {
    pasadas.forEach(function (s) { s.classList.toggle('mostrar', abierto); });
    btn.textContent = abierto
      ? '\\u25B4 Ocultar anteriores'
      : '\\u25BE Ver anteriores (' + pasadas.length + ')';
  }
  btn.hidden = false;
  btn.addEventListener('click', function () { abierto = !abierto; pintar(); });
  pintar();
})();
</script>"""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Entregas — Destape Rápido</title>
<style>
  :root {{ --azul:#1F5AA8; --tinta:#0F172A; --gris:#64748B; --linea:#E2E8F0; --fondo:#F1F5F9; }}
  * {{ box-sizing:border-box; -webkit-tap-highlight-color:transparent; }}
  html, body {{ max-width:100%; overflow-x:hidden; }}
  body {{
    margin:0; background:var(--fondo); color:var(--tinta);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    font-size:16px; line-height:1.45; padding-bottom:env(safe-area-inset-bottom);
  }}
  header {{
    position:sticky; top:0; z-index:10; background:var(--azul); color:#fff;
    padding:16px 18px calc(16px + env(safe-area-inset-top)); padding-top:max(16px,env(safe-area-inset-top));
    box-shadow:0 2px 8px rgba(15,23,42,.18);
  }}
  header h1 {{ margin:0; font-size:19px; letter-spacing:.3px; }}
  header .sub {{ margin-top:3px; font-size:13px; opacity:.85; }}
  main {{ max-width:560px; margin:0 auto; padding:14px 12px 40px; }}
  .fecha-titulo {{
    display:flex; align-items:center; gap:8px; font-size:14px; text-transform:uppercase;
    letter-spacing:.6px; color:var(--gris); margin:22px 4px 10px;
  }}
  .conteo {{
    background:var(--azul); color:#fff; font-size:12px; min-width:22px; height:22px;
    border-radius:11px; display:inline-flex; align-items:center; justify-content:center; padding:0 7px;
  }}
  .card {{
    background:#fff; border:1px solid var(--linea); border-radius:14px; margin-bottom:10px;
    overflow:hidden; box-shadow:0 1px 2px rgba(15,23,42,.04);
  }}
  summary {{ list-style:none; cursor:pointer; padding:14px 16px; position:relative; }}
  summary::-webkit-details-marker {{ display:none; }}
  summary::after {{
    content:"⌄"; position:absolute; right:16px; top:14px; font-size:20px; color:var(--gris);
    transition:transform .2s;
  }}
  details[open] summary::after {{ transform:rotate(180deg); }}
  .resumen-top {{ display:flex; align-items:center; gap:10px; padding-right:24px; }}
  .cliente {{ font-weight:700; font-size:17px; }}
  .badge {{ font-size:11px; font-weight:700; padding:3px 9px; border-radius:20px; white-space:nowrap; }}
  .resumen-sub {{ display:flex; flex-wrap:wrap; gap:6px 12px; margin-top:5px; color:var(--gris); font-size:14px; }}
  .resumen-sub > * {{ min-width:0; }}
  .dir {{ overflow-wrap:anywhere; }}
  .hora {{ font-variant-numeric:tabular-nums; white-space:nowrap; }}
  .banos {{ white-space:nowrap; letter-spacing:1px; }}
  .monto {{ font-weight:700; color:#166534; white-space:nowrap; font-variant-numeric:tabular-nums; }}
  .cobro {{
    margin-top:12px; background:#F0FDF4; border:1px solid #BBF7D0; border-radius:12px;
    padding:12px 14px; display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 10px;
  }}
  .cobro-etq {{ font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; color:#166534; width:100%; }}
  .cobro-monto {{ font-size:26px; font-weight:800; color:#166534; font-variant-numeric:tabular-nums; }}
  .cobro-nota {{ font-size:13px; color:#15803D; }}
  .detalle {{ padding:4px 16px 16px; border-top:1px solid var(--linea); margin-top:2px; }}
  .bloque {{ margin-top:12px; }}
  .etq {{ display:block; font-size:11px; text-transform:uppercase; letter-spacing:.6px; color:var(--gris); margin-bottom:3px; }}
  .bloque p {{ margin:0; }}
  .bloque ul {{ margin:4px 0 0; padding-left:18px; }}
  .bloque li {{ margin:2px 0; }}
  .lp-lista {{ list-style:none; margin:4px 0 0; padding:0; }}
  .lp-item {{
    display:flex; align-items:center; gap:8px; padding:8px 10px; margin-top:6px;
    background:#F8FAFC; border:1px solid var(--linea); border-radius:10px; font-size:14px;
  }}
  .lp-item.lp-done {{ background:#F0FDF4; border-color:#BBF7D0; }}
  .lp-check {{ font-size:18px; font-weight:700; width:18px; text-align:center; flex:none; }}
  .lp-fecha {{ font-variant-numeric:tabular-nums; white-space:nowrap; color:var(--gris); flex:none; min-width:62px; }}
  .lp-etq {{ flex:1 1 auto; min-width:0; font-weight:600; }}
  .lp-nota {{ display:block; font-weight:400; font-size:12px; color:var(--gris); }}
  .lp-badge {{ font-size:10px; font-weight:700; padding:2px 8px; border-radius:20px; white-space:nowrap; flex:none; text-transform:uppercase; letter-spacing:.4px; }}
  .lp-valor {{ font-weight:700; color:#B45309; white-space:nowrap; font-variant-numeric:tabular-nums; flex:none; }}
  .lp-total {{ margin-top:8px; text-align:right; font-size:13px; color:var(--gris); }}
  .lp-total b {{ color:#B45309; }}
  .acciones {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:16px; }}
  .btn {{
    flex:1 1 calc(50% - 8px); text-align:center; text-decoration:none; color:#fff;
    font-weight:600; font-size:15px; padding:12px 10px; border-radius:10px; min-height:46px;
    display:flex; align-items:center; justify-content:center;
  }}
  .btn:active {{ filter:brightness(.92); }}
  .vacio {{ text-align:center; color:var(--gris); margin-top:40px; }}
  .ver-anteriores {{
    display:block; width:100%; margin:4px 0 6px; padding:12px; border:1px dashed var(--linea);
    background:#fff; color:var(--gris); font-size:14px; font-weight:600; border-radius:12px;
    cursor:pointer; font-family:inherit;
  }}
  .ver-anteriores:active {{ background:var(--fondo); }}
  section.pasada {{ display:none; }}
  section.pasada.mostrar {{ display:block; }}
  section.pasada .card {{ opacity:.72; }}
  footer {{ text-align:center; color:var(--gris); font-size:12px; padding:24px 16px 40px; }}
{ESTILOS_EXTRA}</style>
</head>
<body>
  <header>
    <h1>🚚 Entregas — Destape Rápido</h1>
    <div class="sub">{pendientes} pendiente(s) · Actualizado {actualizado}</div>
  </header>
  <main>
    {cuerpo}
  </main>
  <footer>Toca una entrega para ver el detalle · Destape Rápido</footer>
  {config_script}
  {script}
  {SCRIPT_ESTADO}
</body>
</html>
"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"❌ No se encontró {DATA_PATH}")
    except json.JSONDecodeError as e:
        sys.exit(f"❌ entregas.json tiene un error de formato: {e}")

    out.write_text(construir_html(data), encoding="utf-8")
    n = len(data.get("entregas", []))
    print(f"✅ Listado generado: {out}  ({n} entrega(s))")


if __name__ == "__main__":
    main()
