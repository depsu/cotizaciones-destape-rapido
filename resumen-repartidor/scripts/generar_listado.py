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

# Pago de la comisión: el repartidor le transfiere a Alejandro y avisa por WhatsApp.
WHATSAPP_COMISION = "56930153632"
DATOS_BANCARIOS = {
    "titular": "Alejandro Rivera Carrasco",
    "banco": "BancoEstado",
    "cuenta": "000019955346",
    "email": "rivera.ale982@gmail.com",
}

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
    "entregado": ("Entregado", "#1E40AF", "#DBEAFE"),
    "cobrado": ("Cliente ya pagó", "#92600A", "#FEF3C7"),
}

# Clase de color de la card según estado (coincide con el JS).
CLASE_ESTADO = {"entregado": " is-entregado", "cobrado": " is-cobrado"}

# Barra de progreso de entregas del día (el JS la rellena). El 🚚 va en la punta.
PROG_MARKUP = (
    '<span class="prog"><span class="prog-bar">'
    '<span class="prog-fill"><span class="prog-truck">🚚</span></span></span>'
    '<span class="prog-num"></span></span>'
)

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


def plazo_de(e: dict) -> str:
    """Plazo corto del arriendo a partir del texto del servicio.

    'mensual'/cualquier cantidad de meses => 'mensual'; 'N semana(s)' => 'N semana(s)'.
    Devuelve '' si no aplica (p. ej. mantención).
    """
    s = (e.get("servicio") or "").lower()
    if "mensual" in s or "mes" in s:
        return "mensual"
    m = re.search(r"(\d+)\s*semana", s)
    if m:
        n = int(m.group(1))
        return f"{n} semana" + ("s" if n != 1 else "")
    if "semana" in s:
        return "1 semana"
    return ""


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


def boton(href: str, etiqueta: str, color: str, target_blank: bool = True) -> str:
    target = ' target="_blank" rel="noopener"' if target_blank else ""
    return (
        f'<a class="btn" href="{esc(href)}"{target} '
        f'style="background:{color}">{etiqueta}</a>'
    )


def tarjeta(e: dict) -> str:
    cliente = esc(e.get("cliente", "—"))
    direccion = e.get("direccion", "")
    telefono = e.get("telefono", "")
    servicio = esc(e.get("servicio", ""))
    n_banos = cantidad_banos(e)
    banos_icono = icono_banos(n_banos)
    # Etiqueta principal del resumen: baños+plazo, o "Limpieza extra"/"Retiro"
    # cuando es un servicio extra (comision:false), no un arriendo de baño.
    if e.get("comision") is False:
        sl = (e.get("servicio") or "").lower()
        if "retiro" in sl and "limpieza" not in sl and "mantenci" not in sl:
            res_icono, res_txt = "📦", "Retiro"
        else:
            res_icono, res_txt = "🧽", "Limpieza extra"
    else:
        res_icono = banos_icono
        res_txt = f"{n_banos} Baño" + ("s" if n_banos != 1 else "")
        plazo = plazo_de(e)
        if plazo:
            res_txt += f" · {plazo}"
    hora = esc(e.get("hora", ""))
    notas = e.get("notas", "")
    estado = e.get("estado", "pendiente")
    etiqueta, color_txt, color_bg = ESTADOS.get(estado, ESTADOS["pendiente"])
    ent_id = e.get("id", "")
    fecha_iso = e.get("fecha", "")

    # Barra de gestión ARRIBA de la card (fuera del despliegue). El JS la oculta
    # en las entregas futuras (solo aplica de hoy hacia atrás). Reagendar va primero.
    gestion_top = (
        '<div class="gestion-top">'
        '<label class="gt-fecha"><span class="gt-ico">📅</span>'
        '<span class="gt-rg-txt">Reagendar</span>'
        f'<input type="date" class="fecha-input" value="{esc(fecha_iso)}" aria-label="Reagendar entrega"></label>'
        '<div class="gt-estados" role="group" aria-label="Estado de la entrega">'
        '<button type="button" class="est-btn est-entregado" data-estado="entregado">Entregado</button>'
        '<button type="button" class="est-btn est-cobrado" data-estado="cobrado">Cobrado</button>'
        '</div>'
        '<span class="reagendada-chip" hidden></span>'
        '<span class="fecha-original-chip" hidden></span>'
        '</div>'
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

    notas_html = ""
    if notas:
        notas_html = f'<div class="bloque"><span class="etq">Notas</span><p>{esc(notas)}</p></div>'

    # Botones de acción.
    num = solo_digitos(telefono)
    botones = []
    if num:
        botones.append(boton(f"whatsapp://send?phone={num}", "💬 WhatsApp", "#22A45D", target_blank=False))
        botones.append(boton(f"tel:{esc(telefono)}", "📞 Llamar", "#475569", target_blank=False))
    if direccion:
        maps = f"https://www.google.com/maps/search/?api=1&query={quote(direccion)}"
        botones.append(boton(maps, "🗺️ Cómo llegar", "#1F5AA8"))
    botones_html = f'<div class="acciones">{"".join(botones)}</div>'

    # Accesos rápidos (se muestran en la card cuando el cliente ya fue contactado).
    accesos = []
    if num:
        accesos.append(f'<a class="acc-link acc-wa" href="whatsapp://send?phone={num}">💬 WhatsApp</a>')
        accesos.append(f'<a class="acc-link acc-call" href="tel:{esc(telefono)}">📞 Llamar</a>')
    if direccion:
        maps_q = f"https://www.google.com/maps/search/?api=1&query={quote(direccion)}"
        accesos.append(f'<a class="acc-link acc-map" href="{esc(maps_q)}">🗺️ Llegar 🧭</a>')
    accesos.append('<button type="button" class="btn-ver-info">Ver toda la información del cliente ▾</button>')
    accesos_html = f'<div class="contacto-accesos" hidden>{"".join(accesos)}</div>'

    # El horario va dentro del detalle (después de Factura), no en el resumen.
    horario_html = f'<div class="bloque"><span class="etq">🕐 Horario</span><p>{hora}</p></div>' if hora else ""

    return f"""
    <div class="card-wrap{CLASE_ESTADO.get(estado, "")}" data-id="{esc(ent_id)}" data-fecha="{esc(fecha_iso)}" data-estado-orig="{esc(estado)}">
      {gestion_top}
      <details class="card">
        <summary>
          <div class="resumen-top">
            <span class="cliente">{cliente}</span>
            <span class="badge" style="color:{color_txt};background:{color_bg}">{etiqueta}</span>
          </div>
          <div class="resumen-sub">
            <span class="banos">{res_icono} {res_txt}</span>
            <span class="dir">📍 {esc(direccion)}</span>
            {monto_chip}
          </div>
          <div class="estado-hint" hidden></div>
          <div class="pago-adelantado-txt" hidden>⚠️ Cliente pagó adelantado, falta entregar</div>
          <div class="contacto-row" hidden>
            <button type="button" class="btn-contacto"></button>
          </div>
          {accesos_html}
        </summary>
        <div class="detalle">
          {cobro_html}
          {f'<div class="bloque"><span class="etq">Servicio</span><p>{banos_icono} {servicio}</p></div>' if servicio else ""}
          <div class="bloque"><span class="etq">Aseo</span><p>{aseo}</p></div>
          {limpiezas_bloque}
          {f'<div class="bloque"><span class="etq">Teléfono</span><p>{esc(telefono)}</p></div>' if telefono else ""}
          {factura_html}
          {horario_html}
          {notas_html}
          {botones_html}
        </div>
      </details>
    </div>"""


# CSS extra (gestión por tarjeta + panel de comisión). Se inyecta como variable
# para evitar duplicar llaves dentro del f-string del <style>.
ESTILOS_EXTRA = """
  /* El atributo hidden siempre oculta (varios contenedores usan display:flex/block
     que de otro modo le ganarían al hidden). */
  [hidden] { display: none !important; }
  /* Velo de carga: evita que parpadeen las completadas antes de ocultarlas.
     El contenido aparece (con fade) cuando el JS ya aplicó el estado. La animación
     'velo-fallback' lo revela igual a los 2.2s aunque algo falle. */
  main { opacity:0; transition:opacity .3s ease; animation:velo-fallback 0s linear 2.2s forwards; }
  main.listo { opacity:1; }
  @keyframes velo-fallback { to { opacity:1; } }
  /* Barra de progreso de entregas del día (🚚 en la punta). */
  .prog { flex:1 1 auto; min-width:0; display:flex; align-items:center; gap:8px; }
  .prog-bar { position:relative; flex:1 1 auto; min-width:48px; height:16px;
    background:#E2E8F0; border-radius:8px; }
  .prog-fill { position:absolute; left:0; top:0; bottom:0; width:0; background:#16A34A;
    border-radius:8px; transition:width .45s ease; display:flex; align-items:center; justify-content:flex-end; }
  .prog-truck { font-size:13px; line-height:1; transform:translateX(42%); filter:drop-shadow(0 1px 1px rgba(0,0,0,.25)); }
  .prog-num { flex:none; font-size:12px; font-weight:800; color:var(--gris); font-variant-numeric:tabular-nums; }
  /* Gestión ARRIBA de la card */
  .card-wrap { margin-bottom:10px; }
  .gestion-top { display:flex; flex-wrap:wrap; align-items:center; gap:8px; padding:9px 12px;
    background:#fff; border:1px solid var(--linea); border-bottom:none; border-radius:14px 14px 0 0; }
  .card-wrap > .card { margin-bottom:0; border-top:none; border-radius:0 0 14px 14px; }
  .gt-fecha { display:flex; align-items:center; gap:5px; font-size:13px; color:var(--gris); font-weight:600; }
  .gt-rg-txt { display:none; }
  .fecha-input { font-family:inherit; font-size:14px; padding:6px 8px; border:1px solid var(--linea);
    border-radius:8px; background:#fff; color:var(--tinta); min-height:36px; }
  .gt-estados { display:flex; gap:6px; margin-left:auto; }
  .est-btn { padding:8px 12px; border:1px solid var(--linea); background:#fff; color:var(--gris);
    font-size:13px; font-weight:700; border-radius:9px; cursor:pointer; font-family:inherit; min-height:38px; }
  .est-btn:active { filter:brightness(.96); }
  .est-btn.est-entregado.activo { background:#1E40AF; color:#fff; border-color:#1E40AF; }
  .est-btn.est-cobrado.activo { background:#B8860B; color:#fff; border-color:#B8860B; }
  .reagendada-chip { width:100%; font-size:12px; font-weight:800; color:#B91C1C; background:#FEE2E2;
    padding:4px 9px; border-radius:8px; box-sizing:border-box; }
  .fecha-original-chip { width:100%; font-size:11px; color:var(--gris); padding:0 2px; box-sizing:border-box; }
  /* Botón "avisar al cliente" dentro de la card */
  .contacto-row { margin-top:10px; }
  .btn-contacto { width:100%; background:#22A45D; color:#fff; border:none; font-family:inherit;
    font-weight:700; font-size:14px; padding:11px; border-radius:10px; cursor:pointer; min-height:44px; }
  .btn-contacto:active { filter:brightness(.95); }
  .btn-contacto.contactado, .btn-contacto:disabled { background:#DCFCE7; color:#166534; cursor:default; }
  .contacto-accesos { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
  .acc-link { flex:1 1 0; min-width:0; display:flex; align-items:center; justify-content:center; gap:4px;
    text-decoration:none; font-family:inherit; font-size:12.5px; font-weight:700; white-space:nowrap;
    padding:9px 4px; border-radius:9px; min-height:44px; border:none; color:#fff; }
  .acc-link:active { filter:brightness(.92); }
  .acc-link.acc-wa { background:#16A34A; }
  .acc-link.acc-call { background:#fff; color:#0F172A; border:1px solid #CBD5E1; }
  .acc-link.acc-map { background:#1F5AA8; }
  .btn-ver-info { flex:1 1 100%; margin-top:2px; padding:12px; border-radius:9px;
    background:#EFF6FF; border:1px solid #BFDBFE; color:#1F5AA8; font-family:inherit;
    font-size:14px; font-weight:700; cursor:pointer; min-height:46px; }
  .btn-ver-info:active { filter:brightness(.97); }
  /* Colores de la card según estado */
  .card-wrap.is-entregado > .card, .card-wrap.is-entregado > .gestion-top { border-color:#93C5FD; background:#EFF6FF; }
  .card-wrap.is-cobrado > .card, .card-wrap.is-cobrado > .gestion-top { border-color:#FCD34D; background:#FFFBEB; }
  .card-wrap.is-pago-adelantado > .card, .card-wrap.is-pago-adelantado > .gestion-top { border-color:#F59E0B; background:#FFFBEB; }
  .estado-hint { margin-top:6px; font-size:12px; font-weight:600; color:var(--gris); }
  .pago-adelantado-txt { margin-top:8px; font-size:13px; font-weight:800; color:#B45309;
    background:#FEF3C7; border:1px solid #FCD34D; border-radius:9px; padding:8px 10px; text-align:center; }
  .card-wrap.is-reagendado > .card, .card-wrap.is-reagendado > .gestion-top { border-color:#F87171; background:#FEF2F2; }
  .card-wrap.is-reagendado > .gestion-top { border-bottom:2px solid #FECACA; }
  .card-wrap.is-contactado > .card, .card-wrap.is-contactado > .gestion-top { border-color:#86EFAC; background:#F0FDF4; }
  .card-wrap.oculto-anterior { display:none; }
  /* Animación de "completada con éxito" */
  .card-wrap.celebrando { position:relative; }
  .celebra-overlay { position:absolute; inset:0; z-index:7; display:flex; align-items:center;
    justify-content:center; text-align:center; padding:18px; border-radius:14px;
    background:#FCD34D; color:#7C2D12; font-weight:800; font-size:17px; line-height:1.3;
    box-shadow:0 0 0 2px #F59E0B inset; animation:celebra-in .35s ease both; }
  @keyframes celebra-in { from { opacity:0; transform:scale(.94); } to { opacity:1; transform:scale(1); } }
  .card-wrap.colapsando { overflow:hidden; opacity:0;
    transition:height .5s ease, opacity .5s ease, margin .5s ease; }
  .comision-mini { margin-top:2px; font-size:14px; color:#92600A; display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 8px; }
  .comision-mini b { font-size:16px; }
  .comision-mini .cm-base { color:var(--gris); font-size:12px; }
  .comision-mini.comision-no { color:var(--gris); }
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
  .estado-online { margin:0 0 12px; padding:10px 14px; border-radius:10px; font-size:13px; font-weight:600;
    background:#FEF2F2; color:#B91C1C; border:1px solid #FECACA; }
  .estado-online[hidden] { display:none; }
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
  /* Vista comisión: flujo de pago */
  .comision-panel { border-top-color:#B8860B; box-shadow:0 2px 10px rgba(184,134,11,.10); }
  .cp-titulo { color:#92600A; }
  .com-deuda { display:flex; justify-content:space-between; align-items:baseline; gap:10px;
    background:#FFFBEB; border:1px solid #FCD34D; border-radius:12px; padding:12px 14px; margin-top:12px; }
  .com-deuda b { font-size:24px; font-weight:800; color:#92600A; font-variant-numeric:tabular-nums; }
  .com-sec-tit { font-size:12px; text-transform:uppercase; letter-spacing:.6px; color:var(--gris);
    font-weight:700; margin:18px 2px 8px; }
  .com-card { display:flex; align-items:center; gap:10px; padding:11px 13px; margin-bottom:8px;
    background:#FFFBEB; border:1px solid #FCD34D; border-radius:12px; }
  .com-card.com-pagada { background:#F0FDF4; border-color:#BBF7D0; opacity:.85; }
  .com-check { width:22px; height:22px; flex:none; accent-color:#16A34A; }
  .com-main { flex:1 1 auto; min-width:0; }
  .com-cli { font-weight:700; }
  .com-dir { color:var(--gris); font-size:13px; overflow-wrap:anywhere; }
  .com-monto { font-weight:800; color:#92600A; font-variant-numeric:tabular-nums; white-space:nowrap; }
  .com-pagada .com-monto { color:#166534; }
  .com-pagada-tag { font-size:10px; font-weight:700; color:#166534; background:#DCFCE7; padding:3px 8px;
    border-radius:20px; flex:none; text-transform:uppercase; letter-spacing:.4px; }
  .com-revocar { font-size:12px; font-weight:600; padding:6px 9px; border:1px solid var(--linea);
    background:#fff; border-radius:8px; color:#B91C1C; cursor:pointer; flex:none; }
  /* Barra y botón pagar */
  .barra-pagar { position:sticky; bottom:0; margin:10px -12px 0; padding:12px;
    background:rgba(255,255,255,.96); border-top:1px solid var(--linea); }
  .btn-pagar { width:100%; background:#16A34A; color:#fff; border:none; font-family:inherit;
    font-size:16px; font-weight:800; padding:15px; border-radius:13px; cursor:pointer; min-height:54px; }
  .btn-pagar:disabled { background:#CBD5E1; cursor:default; }
  /* Modal de pago */
  .modal-bg { position:fixed; inset:0; background:rgba(15,23,42,.55); display:flex;
    align-items:flex-end; justify-content:center; z-index:50; }
  .modal { background:#fff; width:100%; max-width:520px; border-radius:18px 18px 0 0; padding:20px 18px;
    max-height:92vh; overflow:auto; box-shadow:0 -4px 24px rgba(15,23,42,.25); }
  .modal h3 { margin:0 0 4px; font-size:19px; }
  .modal-sub { margin:0 0 8px; font-size:13px; color:var(--gris); }
  .bank { background:#F8FAFC; border:1px solid var(--linea); border-radius:12px; padding:10px 14px; margin:10px 0; font-size:14px; }
  .bank-row { display:flex; justify-content:space-between; gap:12px; padding:4px 0; }
  .bank-row span { color:var(--gris); }
  .bank-row b { font-variant-numeric:tabular-nums; text-align:right; overflow-wrap:anywhere; }
  .bank-total { border-top:1px solid var(--linea); margin-top:4px; padding-top:8px; font-size:16px; }
  .file-comp { display:block; margin-top:10px; font-size:14px; font-weight:600; color:var(--azul); }
  .file-comp input { display:block; margin-top:6px; font-weight:400; }
  .comp-preview { display:none; margin-top:10px; max-width:100%; border-radius:10px; }
  .modal-acciones { display:flex; gap:10px; margin-top:16px; }
  .btn-modal { flex:1 1 0; padding:13px; border-radius:11px; font-family:inherit; font-weight:700;
    font-size:15px; cursor:pointer; border:1px solid var(--linea); background:#fff; color:var(--tinta); }
  .btn-modal.primary { background:#16A34A; color:#fff; border-color:#16A34A; }
"""

# JS que carga el estado desde Supabase, cablea los controles de cada tarjeta y
# calcula/pinta el panel de comisión. No es f-string: las llaves van literales.
SCRIPT_ESTADO = r"""<script>
(function () {
  var APP = window.__APP__ || {};
  var SUPA = { url: APP.url, key: APP.key };
  var WA = APP.whatsapp || '';
  var BANCO = APP.banco || {};
  var META = {};
  (APP.entregas || []).forEach(function (e) { META[e.id] = e; });
  var estado = {}; // id -> {id, estado, fecha, comision_pagada, pagada_at}
  var anterioresColapsado = true;
  var comSel = null; // Set de ids seleccionados para pagar (persistido en localStorage)
  var SEL_KEY = 'comision_sel_v1';

  // Etiqueta + colores del badge según estado.
  var ESTADOS = {
    'pendiente': ['Pendiente', '#B45309', '#FEF3C7'],
    'en-camino': ['En camino', '#1E40AF', '#DBEAFE'],
    'entregado': ['Entregado', '#1E40AF', '#DBEAFE'],
    'cobrado':   ['Cliente ya pagó', '#92600A', '#FEF3C7'],
    'pagado-pendiente': ['Pagó · falta entregar', '#B45309', '#FEF3C7']
  };
  // entregado y cobrado son dimensiones independientes (un cliente puede pagar
  // adelantado: cobrado sin estar entregado => estado 'pagado-pendiente').
  function entregadoDe(id) { var e = estadoDe(id); return e === 'entregado' || e === 'cobrado'; }
  function cobradoDe(id) { var e = estadoDe(id); return e === 'cobrado' || e === 'pagado-pendiente'; }
  var MESES = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
  var MESESL = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
  var DIAS = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo'];
  var PROG = '<span class="prog"><span class="prog-bar"><span class="prog-fill"><span class="prog-truck">🚚</span></span></span><span class="prog-num"></span></span>';

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
  function isoOf(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }
  function todayISO() { return isoOf(new Date()); }
  function diaRelativo(effISO) {
    var now = new Date();
    var hoy = isoOf(now);
    var man = isoOf(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1));
    if (effISO && effISO <= hoy) return 'hoy';
    if (effISO === man) return 'mañana';
    var p = (effISO || '').split('-');
    if (p.length === 3) return 'el ' + parseInt(p[2], 10) + ' de ' + (MESESL[parseInt(p[1], 10) - 1] || '');
    return 'pronto';
  }
  function headers(extra) {
    var h = { 'apikey': SUPA.key, 'Authorization': 'Bearer ' + SUPA.key };
    if (extra) { for (var k in extra) h[k] = extra[k]; }
    return h;
  }
  function qCard(id) { return document.querySelector('.card-wrap[data-id="' + String(id).replace(/"/g, '\\"') + '"]'); }

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
  function contactadoDe(id) { var st = estado[id]; return !!(st && st.contactado); }

  function pintarCard(card) {
    var id = card.getAttribute('data-id');
    var est = estadoDe(id);
    var fOrig = card.getAttribute('data-fecha');
    var fAct = fechaDe(id);
    var reagendado = !!(fAct && fOrig && fAct !== fOrig);
    var info = ESTADOS[est] || ESTADOS['pendiente'];

    var badge = card.querySelector('.badge');
    if (badge) { badge.textContent = info[0]; badge.style.color = info[1]; badge.style.background = info[2]; }

    // Dimensiones independientes.
    var entregado = entregadoDe(id);
    var cobrado = cobradoDe(id);
    var pagoAdelantado = (est === 'pagado-pendiente'); // cobrado sin entregar
    var listo = (est === 'cobrado');                   // entregado + cobrado
    var esPendiente = (est === 'pendiente');
    var contactado = contactadoDe(id);

    // Color de la card. Prioridad: listo(dorado) > pago adelantado(ámbar) > entregado(azul) > reagendado(rojo) > contactado(verde).
    card.classList.toggle('is-cobrado', listo);
    card.classList.toggle('is-pago-adelantado', pagoAdelantado);
    card.classList.toggle('is-entregado', entregado && !cobrado);
    card.classList.toggle('is-reagendado', esPendiente && reagendado);
    card.classList.toggle('is-contactado', esPendiente && !reagendado && contactado);

    // Botones de estado (entregado y cobrado independientes).
    card.querySelectorAll('.est-btn').forEach(function (b) {
      var e = b.getAttribute('data-estado');
      var activo = (e === 'entregado' && entregado) || (e === 'cobrado' && cobrado);
      b.classList.toggle('activo', activo);
      if (e === 'cobrado') { b.textContent = cobrado ? 'Cliente ya pagó' : 'Cobrado'; }
    });

    // Aviso "pagó adelantado, falta entregar".
    var pa = card.querySelector('.pago-adelantado-txt');
    if (pa) { pa.hidden = !pagoAdelantado; }

    // Texto sutil que explica el color/estado de la card.
    var hint = card.querySelector('.estado-hint');
    if (hint) {
      var ht = '';
      if (est === 'entregado') { ht = '🔵 Entregado · falta cobrar'; }
      else if (esPendiente && reagendado) { ht = '🔴 Reagendada · no se entregó a tiempo'; }
      else if (esPendiente && contactado) { ht = '🟢 Cliente contactado · listo para entregar'; }
      else if (esPendiente) { ht = '⚪ Pendiente · aún sin contactar'; }
      hint.textContent = ht;
      hint.hidden = !ht;
    }

    // Reagendar: input + chip + fecha original; oculta la gestión en entregas FUTURAS (gate por fecha original).
    var input = card.querySelector('.fecha-input');
    if (input && fAct) { input.value = fAct; }
    var chip = card.querySelector('.reagendada-chip');
    if (chip) {
      if (reagendado) { chip.hidden = false; chip.textContent = '⚠ Reagendada para ' + fechaLarga(fAct); }
      else { chip.hidden = true; }
    }
    var fo = card.querySelector('.fecha-original-chip');
    if (fo) {
      if (reagendado) { fo.hidden = false; fo.textContent = 'Fecha original: ' + fechaLarga(fOrig); }
      else { fo.hidden = true; }
    }
    // Botones Entregado/Cobrado: ocultos solo si la fecha EFECTIVA aún es futura y
    // no hay actividad. Si se reagenda a una fecha que ya llegó, o si el cliente
    // pagó adelantado / ya se entregó, los botones aparecen.
    var esFutura = !!(fAct && fAct > todayISO());
    var estados = card.querySelector('.gt-estados');
    if (estados) { estados.hidden = esFutura && !entregado && !cobrado; }

    // Botón "Avisar al cliente": solo en pendientes NO reagendadas y con teléfono.
    var tel = (META[id] && META[id].tel) || '';
    var crow = card.querySelector('.contacto-row');
    var cbtn = card.querySelector('.btn-contacto');
    var mostrar = esPendiente && !reagendado && !!tel;
    if (crow) { crow.hidden = !mostrar; }
    if (cbtn) {
      if (contactado) { cbtn.textContent = '✓ Cliente contactado'; cbtn.disabled = true; cbtn.classList.add('contactado'); }
      else { cbtn.textContent = '💬 Avisar al cliente que voy a entregar'; cbtn.disabled = false; cbtn.classList.remove('contactado'); }
    }
    // Accesos rápidos (llamar / llegar / WhatsApp): visibles cuando ya se contactó.
    var accesos = card.querySelector('.contacto-accesos');
    if (accesos) { accesos.hidden = !(mostrar && contactado); }
  }
  function pintarTodo() { document.querySelectorAll('.card-wrap[data-id]').forEach(pintarCard); }

  // ---- Reagendar: mueve la card a la sección del día que ahora le toca ----
  function encabezadoFecha(iso) {
    var p = (iso || '').split('-');
    if (p.length !== 3) return iso || 'Sin fecha';
    var d = new Date(parseInt(p[0], 10), parseInt(p[1], 10) - 1, parseInt(p[2], 10));
    if (isNaN(d.getTime())) return iso;
    var wd = (d.getDay() + 6) % 7; // lunes = 0
    var s = DIAS[wd] + ' ' + parseInt(p[2], 10) + ' de ' + (MESESL[parseInt(p[1], 10) - 1] || '');
    return s.charAt(0).toUpperCase() + s.slice(1);
  }
  function getOrCreateSection(cont, fecha) {
    var sec = cont.querySelector('section[data-fecha="' + String(fecha).replace(/"/g, '\\"') + '"]');
    if (sec) return sec;
    sec = document.createElement('section');
    sec.setAttribute('data-fecha', fecha);
    var h = document.createElement('h2');
    h.className = 'fecha-titulo';
    h.innerHTML = escapeHtml(encabezadoFecha(fecha)) + PROG;
    sec.appendChild(h);
    cont.appendChild(sec);
    return sec;
  }
  function reubicarCards() {
    var cont = document.querySelector('.vista[data-vista="entregas"]');
    if (!cont) return;
    document.querySelectorAll('.card-wrap[data-id]').forEach(function (cw) {
      var id = cw.getAttribute('data-id');
      var eff = fechaDe(id) || cw.getAttribute('data-fecha') || '';
      var cur = cw.closest('section[data-fecha]');
      if (cur && cur.getAttribute('data-fecha') === eff) return;
      getOrCreateSection(cont, eff).appendChild(cw);
    });
    // Reordena las secciones de día por fecha y quita las que quedaron vacías.
    var secs = Array.prototype.slice.call(cont.querySelectorAll('section[data-fecha]'));
    secs.sort(function (a, b) { return a.getAttribute('data-fecha').localeCompare(b.getAttribute('data-fecha')); });
    secs.forEach(function (s) {
      var n = s.querySelectorAll('.card-wrap[data-id]').length;
      if (!n) { s.remove(); return; }
      var c = s.querySelector('.conteo'); if (c) { c.textContent = n; }
      // Las reagendadas (urgentes) van primero dentro del día.
      var h2 = s.querySelector('h2');
      if (h2) {
        Array.prototype.slice.call(s.querySelectorAll('.card-wrap.is-reagendado')).reverse().forEach(function (cw) {
          h2.insertAdjacentElement('afterend', cw);
        });
      }
      cont.appendChild(s);
    });
    // Las secciones agregadas (limpiezas / retiros) siempre al final.
    cont.querySelectorAll('section.agregado').forEach(function (s) { cont.appendChild(s); });
  }

  // Barra de progreso por día: avanza según los baños ya entregados/cobrados.
  function actualizarProgreso() {
    document.querySelectorAll('.vista[data-vista="entregas"] section[data-fecha]').forEach(function (sec) {
      var total = 0, done = 0;
      sec.querySelectorAll('.card-wrap[data-id]').forEach(function (cw) {
        var id = cw.getAttribute('data-id');
        var b = (META[id] && META[id].banos) || 1;
        total += b;
        var e = estadoDe(id);
        if (e === 'entregado' || e === 'cobrado') { done += b; }
      });
      var pct = total ? Math.round(done / total * 100) : 0;
      var fill = sec.querySelector('.prog-fill'); if (fill) { fill.style.width = pct + '%'; }
      var num = sec.querySelector('.prog-num'); if (num) { num.textContent = done + '/' + total; }
    });
  }

  // Fija la altura real del header para el 'top' de los encabezados sticky.
  function setHeaderH() {
    var h = document.querySelector('header');
    if (h) { document.documentElement.style.setProperty('--header-h', h.offsetHeight + 'px'); }
  }

  // ---- Ocultar completadas: las que ya están entregadas + cobradas (estado 'cobrado') ----
  function aplicarAnteriores() {
    var ocultables = [];
    document.querySelectorAll('.card-wrap[data-id]').forEach(function (cw) {
      if (cw.classList.contains('celebrando')) { return; } // no ocultar mientras celebra
      var ocultable = estadoDe(cw.getAttribute('data-id')) === 'cobrado';
      if (ocultable) { ocultables.push(cw); }
      cw.classList.toggle('oculto-anterior', ocultable && anterioresColapsado);
    });
    document.querySelectorAll('.vista[data-vista="entregas"] section[data-fecha]').forEach(function (sec) {
      var vis = sec.querySelectorAll('.card-wrap:not(.oculto-anterior)').length;
      sec.style.display = vis ? '' : 'none';
    });
    var btn = document.getElementById('toggle-anteriores');
    if (!btn) return;
    if (!ocultables.length) { btn.hidden = true; return; }
    btn.hidden = false;
    btn.textContent = (anterioresColapsado ? '✓ Ver completadas (' : '▴ Ocultar completadas (') + ocultables.length + ')';
  }

  // Animación al completar (entregado + cobrado): card dorada con mensaje de éxito,
  // luego se desvanece y colapsa suavemente (las de abajo suben sin brusquedad).
  function celebrar(card, id) {
    var m = META[id] || {};
    var txt = (m.tipo === 'limpieza')
      ? '✅ Limpieza realizada con éxito'
      : '✅ ' + ((m.banos > 1) ? 'Baños entregados' : 'Baño entregado') + ' con éxito';
    card.classList.add('celebrando');
    var ov = document.createElement('div');
    ov.className = 'celebra-overlay';
    ov.textContent = txt;
    card.appendChild(ov);
    setTimeout(function () {
      card.style.height = card.offsetHeight + 'px';
      void card.offsetHeight; // reflow para animar desde la altura actual
      card.classList.add('colapsando');
      card.style.height = '0px'; card.style.marginTop = '0'; card.style.marginBottom = '0';
      var hecho = false;
      var fin = function () {
        if (hecho) return; hecho = true;
        card.removeEventListener('transitionend', fin);
        if (ov.parentNode) { ov.parentNode.removeChild(ov); }
        card.classList.remove('celebrando');
        aplicarAnteriores();         // ya queda oculta en "completadas"
        card.classList.remove('colapsando');
        card.style.height = ''; card.style.marginTop = ''; card.style.marginBottom = '';
        reubicarCards(); actualizarProgreso(); renderComision();
      };
      card.addEventListener('transitionend', fin);
      setTimeout(fin, 700);
    }, 1800);
  }

  function bannerOnline(ok) {
    var p = document.getElementById('estado-online');
    if (!p) return;
    if (ok) { p.hidden = true; }
    else { p.hidden = false; p.textContent = '⚠ Sin conexión: el último cambio no se guardó. Reintenta.'; }
  }

  function upsert(id, patch) {
    var prev = estado[id] || {};
    var row = {
      id: id, estado: estadoDe(id), fecha: fechaDe(id) || null,
      comision_pagada: pagadaDe(id), pagada_at: prev.pagada_at || null, contactado: contactadoDe(id)
    };
    for (var k in patch) { row[k] = patch[k]; }
    if (row.fecha === '') { row.fecha = null; }
    estado[id] = row;
    var card = qCard(id);
    if (card) { pintarCard(card); }
    reubicarCards();
    actualizarProgreso();
    aplicarAnteriores();
    renderComision();
    if (!SUPA.url || !SUPA.key) return Promise.resolve();
    return fetch(SUPA.url + '/rest/v1/entrega_estado', {
      method: 'POST',
      headers: headers({ 'Content-Type': 'application/json', 'Prefer': 'resolution=merge-duplicates,return=minimal' }),
      body: JSON.stringify(row)
    }).then(function (r) {
      if (!r.ok) { throw new Error('HTTP ' + r.status); }
      bannerOnline(true);
    }).catch(function (e) { console.warn('No se pudo guardar', e); bannerOnline(false); });
  }

  // ====================== VISTA COMISIÓN (flujo de pago) ======================
  function loadSel() { try { return JSON.parse(localStorage.getItem(SEL_KEY)); } catch (e) { return null; } }
  function saveSel() { try { localStorage.setItem(SEL_KEY, JSON.stringify(Array.from(comSel))); } catch (e) {} }

  function comisionables() {
    var ids = Object.keys(META).filter(function (id) {
      var m = META[id];
      return m.comisiona && m.comision && cobradoDe(id);
    });
    ids.sort(function (a, b) { return (fechaDe(a) || '').localeCompare(fechaDe(b) || ''); });
    return ids;
  }

  function renderComision() {
    var cont = document.getElementById('comision-panel');
    if (!cont) return;
    var ids = comisionables();
    var porPagar = ids.filter(function (id) { return !pagadaDe(id); });
    var pagadas = ids.filter(function (id) { return pagadaDe(id); });

    // Selección: por defecto todas las por pagar; respeta lo guardado.
    if (comSel === null) {
      var stored = loadSel();
      comSel = new Set(stored ? stored.filter(function (id) { return porPagar.indexOf(id) >= 0; }) : porPagar);
    } else {
      comSel.forEach(function (id) { if (porPagar.indexOf(id) < 0) comSel.delete(id); });
    }

    var deuda = porPagar.reduce(function (s, id) { return s + META[id].comision; }, 0);
    var yaPagada = pagadas.reduce(function (s, id) { return s + META[id].comision; }, 0);

    function card(id, paid) {
      var m = META[id];
      var check = paid
        ? '<span class="com-pagada-tag">✓ Pagada</span>'
        : '<input type="checkbox" class="com-check" data-id="' + escapeHtml(id) + '"' + (comSel.has(id) ? ' checked' : '') + '>';
      var rev = paid ? '<button type="button" class="com-revocar" data-id="' + escapeHtml(id) + '">Revocar</button>' : '';
      return '<div class="com-card' + (paid ? ' com-pagada' : '') + '">' + check
        + '<div class="com-main"><div class="com-cli">' + escapeHtml(m.cliente) + '</div>'
        + '<div class="com-dir">📍 ' + escapeHtml(m.direccion || '') + ' · ' + fechaLarga(fechaDe(id)) + '</div></div>'
        + '<div class="com-monto">' + clp(m.comision) + '</div>' + rev + '</div>';
    }

    var html = '<div class="cp-head"><span class="cp-titulo">💰 Comisión a pagar</span></div>'
      + '<div class="com-deuda"><span>Te deben (cobradas sin pagar)</span><b>' + clp(deuda) + '</b></div>';
    if (porPagar.length) {
      html += '<div class="com-sec-tit">Selecciona las que vas a pagar</div>'
        + porPagar.map(function (id) { return card(id, false); }).join('');
    } else {
      html += '<p class="cp-vacio">No hay comisiones pendientes de pago. 🎉</p>';
    }
    if (pagadas.length) {
      html += '<div class="com-sec-tit">Ya pagadas · ' + clp(yaPagada) + '</div>'
        + pagadas.map(function (id) { return card(id, true); }).join('');
    }
    cont.innerHTML = html;

    cont.querySelectorAll('.com-check').forEach(function (ch) {
      ch.addEventListener('change', function () {
        var id = ch.getAttribute('data-id');
        if (ch.checked) comSel.add(id); else comSel.delete(id);
        saveSel(); updateBarra();
      });
    });
    cont.querySelectorAll('.com-revocar').forEach(function (b) {
      b.addEventListener('click', function () {
        if (confirm('¿Revocar el pago de esta comisión? Volverá a quedar como pendiente.')) {
          upsert(b.getAttribute('data-id'), { comision_pagada: false, pagada_at: null });
        }
      });
    });
    updateBarra();
  }

  function seleccionTotal() {
    var t = 0; if (!comSel) return 0;
    comSel.forEach(function (id) { if (META[id] && !pagadaDe(id)) t += META[id].comision; });
    return t;
  }
  function updateBarra() {
    var barra = document.getElementById('barra-pagar');
    if (!barra) return;
    var n = 0; if (comSel) comSel.forEach(function (id) { if (!pagadaDe(id)) n++; });
    var total = seleccionTotal();
    var btn = barra.querySelector('.btn-pagar');
    btn.disabled = (n === 0);
    btn.textContent = n ? ('Pagar ' + clp(total) + ' · ' + n + ' selec.') : 'Selecciona comisiones';
    barra.hidden = false;
  }

  function abrirModalPago() {
    var seleccion = [];
    comSel.forEach(function (id) { if (!pagadaDe(id)) seleccion.push(id); });
    if (!seleccion.length) return;
    var total = seleccionTotal();
    var detalle = seleccion.map(function (id) { return '<div class="bank-row"><span>' + escapeHtml(META[id].cliente) + '</span><b>' + clp(META[id].comision) + '</b></div>'; }).join('');
    var bg = document.createElement('div');
    bg.className = 'modal-bg';
    bg.innerHTML =
      '<div class="modal"><h3>Pagar comisión</h3>'
      + '<p class="modal-sub">Transfiere el total y mándame el comprobante por WhatsApp. Queda registrada la hora del pago.</p>'
      + '<div class="bank">' + detalle + '<div class="bank-row bank-total"><span>Total</span><b>' + clp(total) + '</b></div></div>'
      + '<div class="bank"><div class="bank-row"><span>Titular</span><b>' + escapeHtml(BANCO.titular || '') + '</b></div>'
      + '<div class="bank-row"><span>Banco</span><b>' + escapeHtml(BANCO.banco || '') + '</b></div>'
      + '<div class="bank-row"><span>Cuenta RUT</span><b>' + escapeHtml(BANCO.cuenta || '') + '</b></div>'
      + (BANCO.email ? '<div class="bank-row"><span>Email</span><b>' + escapeHtml(BANCO.email) + '</b></div>' : '') + '</div>'
      + '<label class="file-comp">📎 Adjuntar comprobante (opcional)<input type="file" accept="image/*" class="comp-input"></label>'
      + '<img class="comp-preview" alt="comprobante">'
      + '<div class="modal-acciones"><button type="button" class="btn-modal cancelar">Cancelar</button>'
      + '<button type="button" class="btn-modal primary confirmar">Marcar pagadas y abrir WhatsApp</button></div></div>';
    document.body.appendChild(bg);
    bg.addEventListener('click', function (ev) { if (ev.target === bg) document.body.removeChild(bg); });
    bg.querySelector('.cancelar').addEventListener('click', function () { document.body.removeChild(bg); });
    var fileInput = bg.querySelector('.comp-input');
    var preview = bg.querySelector('.comp-preview');
    fileInput.addEventListener('change', function () {
      var f = fileInput.files && fileInput.files[0];
      if (f) { preview.src = URL.createObjectURL(f); preview.style.display = 'block'; }
    });
    bg.querySelector('.confirmar').addEventListener('click', function () {
      var ahora = new Date().toISOString();
      Promise.all(seleccion.map(function (id) { return upsert(id, { comision_pagada: true, pagada_at: ahora }); }))
        .then(function () {
          var lineas = seleccion.map(function (id) { return '• ' + META[id].cliente + ': ' + clp(META[id].comision); });
          var texto = 'Hola Alejandro, te transfiero la comisión:\n' + lineas.join('\n')
            + '\nTotal: ' + clp(total) + '\nFecha: ' + new Date().toLocaleString('es-CL')
            + '\n(Te adjunto el comprobante.)';
          comSel = new Set(); saveSel();
          if (document.body.contains(bg)) document.body.removeChild(bg);
          if (WA) { window.location.href = 'whatsapp://send?phone=' + WA + '&text=' + encodeURIComponent(texto); }
        });
    });
  }

  function load() {
    var done = function () { pintarTodo(); reubicarCards(); actualizarProgreso(); aplicarAnteriores(); renderComision(); revelar(); };
    if (!SUPA.url || !SUPA.key) { done(); return; }
    fetch(SUPA.url + '/rest/v1/entrega_estado?select=*', { headers: headers() })
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (rows) { rows.forEach(function (row) { estado[row.id] = row; }); })
      .catch(function (e) { console.warn(e); })
      .then(done);
  }

  function wire() {
    document.querySelectorAll('.card-wrap[data-id]').forEach(function (card) {
      var id = card.getAttribute('data-id');
      card.querySelectorAll('.est-btn').forEach(function (b) {
        b.addEventListener('click', function (ev) {
          ev.preventDefault(); ev.stopPropagation();
          var e = b.getAttribute('data-estado');
          // Combina las dos dimensiones (entregado/cobrado) en el estado guardado.
          var ent = entregadoDe(id), cob = cobradoDe(id);
          if (e === 'entregado') { ent = !ent; } else { cob = !cob; }
          var next = cob ? (ent ? 'cobrado' : 'pagado-pendiente') : (ent ? 'entregado' : 'pendiente');
          var completa = (next === 'cobrado' && estadoDe(id) !== 'cobrado');
          if (completa) { card.classList.add('celebrando'); } // que no la oculte antes de animar
          upsert(id, { estado: next });
          if (completa) { celebrar(card, id); }
        });
      });
      var input = card.querySelector('.fecha-input');
      if (input) {
        input.addEventListener('change', function () { upsert(id, { fecha: input.value || null }); });
      }
      var cbtn = card.querySelector('.btn-contacto');
      if (cbtn) {
        cbtn.addEventListener('click', function (ev) {
          ev.preventDefault(); ev.stopPropagation();
          if (cbtn.disabled || contactadoDe(id)) return;
          var tel = (META[id] && META[id].tel) || '';
          var msg = 'Hola 👋, le escribo de Destape Rápido. Le aviso que voy a entregar su baño químico '
            + diaRelativo(fechaDe(id)) + '. ¿Me confirma disponibilidad y la dirección? ¡Gracias!';
          upsert(id, { contactado: true });
          if (tel) { window.location.href = 'whatsapp://send?phone=' + tel + '&text=' + encodeURIComponent(msg); }
        });
      }
      // Accesos rápidos: navegan sin abrir/cerrar la card.
      card.querySelectorAll('.acc-link').forEach(function (a) {
        a.addEventListener('click', function (ev) {
          ev.preventDefault(); ev.stopPropagation();
          var href = a.getAttribute('href') || '';
          if (/^https?:/.test(href)) { window.open(href, '_blank'); }
          else { window.location.href = href; }
        });
      });
      // "Ver toda la información": abre/cierra el detalle (botón dentro de summary
      // no togglea solo). Texto inverso al estar abierto.
      var vi = card.querySelector('.btn-ver-info');
      if (vi) {
        vi.addEventListener('click', function (ev) {
          ev.preventDefault(); ev.stopPropagation();
          var det = card.querySelector('details');
          if (det) {
            det.open = !det.open;
            vi.textContent = det.open ? 'Ver menos información ▴' : 'Ver toda la información del cliente ▾';
          }
        });
      }
    });
    var ta = document.getElementById('toggle-anteriores');
    if (ta) { ta.addEventListener('click', function () { anterioresColapsado = !anterioresColapsado; aplicarAnteriores(); }); }
    var bp = document.getElementById('barra-pagar');
    if (bp) { bp.querySelector('.btn-pagar').addEventListener('click', abrirModalPago); }
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

  function revelar() { var m = document.querySelector('main'); if (m) { m.classList.add('listo'); } }

  setHeaderH();
  window.addEventListener('resize', setHeaderH);
  // Pintura inicial con META (bajo el velo) para que, si la red tarda, lo que se
  // revele ya esté lo más correcto posible. El velo se levanta en done() tras el fetch.
  pintarTodo(); reubicarCards(); actualizarProgreso(); aplicarAnteriores(); renderComision();
  setTimeout(revelar, 1500); // fallback si la red tarda demasiado
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
            f'{PROG_MARKUP}</h2>{tarjetas}</section>'
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
            "tel": solo_digitos(e.get("telefono", "")),
            "banos": cantidad_banos(e),
            "tipo": "limpieza" if e.get("comision") is False else "bano",
        }
        for e in entregas
    ]
    config_json = json.dumps(
        {
            "url": SUPABASE_URL,
            "key": SUPABASE_ANON_KEY,
            "whatsapp": WHATSAPP_COMISION,
            "banco": DATOS_BANCARIOS,
            "entregas": meta,
        },
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
        '<div id="barra-pagar" class="barra-pagar" hidden>'
        '<button type="button" class="btn-pagar" disabled>Selecciona comisiones</button>'
        '</div>'
        '</div>'
    )
    actualizado = date.today().strftime("%d/%m/%Y")

    # La lógica de "ver/ocultar anteriores" ahora vive en SCRIPT_ESTADO (ocultar
    # solo las cobradas de días pasados), porque depende del estado vivo.
    script = ""

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
    display:flex; align-items:center; gap:10px; font-size:14px; text-transform:uppercase;
    letter-spacing:.6px; color:var(--gris); margin:16px 0 8px; padding:8px 4px;
    position:sticky; top:var(--header-h, 64px); z-index:5; background:var(--fondo);
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
    content:"▾"; position:absolute; right:12px; top:12px; width:26px; height:26px;
    display:flex; align-items:center; justify-content:center; line-height:1;
    font-size:14px; color:#1F5AA8; background:#EFF6FF; border:1px solid #BFDBFE; border-radius:50%;
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
  .ver-anteriores[hidden] {{ display:none; }}
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
