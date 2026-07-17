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
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import quote

BASE = Path(__file__).resolve().parent.parent
DATA_PATH = BASE / "entregas.json"
DEFAULT_OUT = BASE / "listado.html"

# Logo real de WhatsApp (SVG inline, hereda el color del texto del botón: blanco).
WA_ICON = (
    '<svg class="ico-wa" viewBox="0 0 24 24" width="15" height="15" fill="currentColor" '
    'aria-hidden="true"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15'
    '-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48'
    '-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.52.149-.174.198-.298.298-.497.099'
    '-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01'
    '-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 '
    '2.096 3.2 5.077 4.487.71.306 1.263.489 1.694.625.712.227 1.36.195 1.872.118.571-.085 1.758-.719 2.006'
    '-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031'
    '-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888'
    '-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413'
    '-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305'
    '-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>'
)

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
# Chevron para colapsar/expandir la sección del día.
CHEVRON = '<span class="sec-chevron">▾</span>'

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


def calle_negrita(direccion: str) -> str:
    """Resalta en negrita el nombre de la calle (lo anterior a la primera coma)."""
    direccion = direccion or ""
    if "," in direccion:
        calle, resto = direccion.split(",", 1)
        return f"<b>{esc(calle.strip())}</b>, {esc(resto.strip())}"
    return f"<b>{esc(direccion)}</b>"


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


def maps_href(direccion: str, coordenadas: str = "") -> str:
    """URL de Google Maps para el botón 'Cómo llegar'. Si la entrega trae
    `coordenadas` ('lat,lng'), cae en el PUNTO EXACTO (clave en sectores rurales
    sin calle/número); si no, busca por el texto de la dirección."""
    q = (coordenadas or "").strip() or (direccion or "")
    return f"https://www.google.com/maps/search/?api=1&query={quote(q)}"


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
        if "recambio" in sl:
            res_icono, res_txt = "♻️", "Recambio"
        elif "retiro" in sl and "limpieza" not in sl and "mantenci" not in sl:
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
        # Desglose breve de cómo se llega al monto (baño + extras + IVA), si viene.
        desglose_pago = f'<span class="cobro-nota">{esc(pago.get("desglose"))}</span>' if pago.get("desglose") else ""
        nota_pago = f'<span class="cobro-nota">{esc(pago.get("nota"))}</span>' if pago.get("nota") else ""
        cobro_html = (
            f'<div class="cobro"><span class="cobro-etq">💵 Cobrar al cliente</span>'
            f'<span class="cobro-monto">{esc(clp(monto))}</span>{desglose_pago}{nota_pago}</div>'
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
        botones.append(boton(f"whatsapp://send?phone={num}", f"{WA_ICON}&nbsp;WhatsApp", "#25D366", target_blank=False))
        botones.append(boton(f"tel:{esc(telefono)}", "📞 Llamar", "#475569", target_blank=False))
    coordenadas = e.get("coordenadas", "")
    # El pin exacto que mandó el cliente (maps_url) manda sobre la búsqueda por texto.
    maps_url = (e.get("maps_url") or "").strip()
    if direccion or coordenadas or maps_url:
        maps = maps_url or maps_href(direccion, coordenadas)
        botones.append(boton(maps, "🗺️ Cómo llegar", "#1F5AA8"))
    botones_html = f'<div class="acciones">{"".join(botones)}</div>'

    # Accesos rápidos (se muestran en la card cuando el cliente ya fue contactado).
    accesos = []
    if num:
        accesos.append(f'<a class="acc-link acc-wa" href="whatsapp://send?phone={num}">{WA_ICON}WhatsApp</a>')
        accesos.append(f'<a class="acc-link acc-call" href="tel:{esc(telefono)}">📞 Llamar</a>')
    if direccion or coordenadas or maps_url:
        maps_q = maps_url or maps_href(direccion, coordenadas)
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
            <span class="dir">📍 {calle_negrita(direccion)}</span>
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
          {f'<div class="bloque"><span class="etq">Teléfono</span><p>{esc("+" + num if num else telefono)}</p></div>' if telefono else ""}
          {factura_html}
          {horario_html}
          {notas_html}
          {botones_html}
          <div class="detalle-danger">
            <button type="button" class="btn-eliminar" data-id="{esc(ent_id)}" title="Eliminar esta entrega">✕ Eliminar</button>
          </div>
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
  /* Colapsar el día al pinchar su encabezado */
  .fecha-titulo { cursor:pointer; -webkit-user-select:none; user-select:none; }
  .sec-chevron { flex:none; font-size:12px; color:var(--azul); transition:transform .2s; transform:rotate(180deg); }
  section.colapsada-dia .sec-chevron { transform:rotate(0deg); }
  section.colapsada-dia > .card-wrap { display:none !important; }
  /* Al colapsar un día, un aviso "abajito" para que no parezca vacío */
  section.colapsada-dia .fecha-titulo { flex-wrap:wrap; }
  section.colapsada-dia .fecha-titulo::after {
    content:"👆 toca para ver las entregas de este día";
    flex-basis:100%; margin-top:2px; font-size:11px; font-weight:600;
    text-transform:none; letter-spacing:0; color:var(--azul); opacity:.9;
  }
  /* Recomendación de reparto de hoy */
  .reco { background:#fff; border:1px solid var(--linea); border-left:4px solid var(--azul);
    border-radius:12px; padding:12px 14px; margin:4px 0 14px; box-shadow:0 1px 2px rgba(15,23,42,.05); }
  .reco-head { display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; margin-bottom:8px; }
  .reco-head b { font-size:15px; color:var(--tinta); }
  .reco-head .reco-sub { font-size:12px; color:var(--gris); }
  .reco-grupo { margin:8px 0 0; padding:8px 10px; border-radius:10px; background:#F8FAFC; border:1px solid var(--linea); }
  .reco-grupo.juntos { background:#ECFDF5; border-color:#A7F3D0; }
  .reco-junta { font-size:12px; font-weight:800; color:#166534; margin-bottom:6px; }
  .reco-sep { height:1px; background:var(--linea); margin:10px 8px; }
  .reco-pin { text-decoration:none; font-size:16px; line-height:1; margin-left:2px; flex:none; }
  .reco-zona { margin:8px 0 0; }
  .reco-zona-tit { font-size:12px; font-weight:800; text-transform:uppercase; letter-spacing:.5px;
    color:var(--gris); margin-bottom:3px; }
  .reco-chain { display:flex; flex-wrap:wrap; align-items:center; gap:6px 8px; font-size:14px; }
  .reco-stop { background:#EFF6FF; border:1px solid #BFDBFE; color:#1E3A8A; font-weight:700;
    border-radius:999px; padding:3px 10px; }
  .reco-stop .reco-n { color:var(--azul); font-weight:800; }
  .reco-stop .reco-cli { font-weight:600; color:#475569; font-size:12px; margin-left:2px; }
  /* Entregada: se tacha EN SU LUGAR (no se manda abajo), para mantener el orden */
  .reco-stop.hecho { background:#F1F5F9; border-color:#E2E8F0; color:#94A3B8;
    text-decoration:line-through; text-decoration-color:#16A34A; }
  .reco-stop.hecho .reco-n, .reco-stop.hecho .reco-cli { color:#94A3B8; }
  .reco-maps { display:inline-flex; align-items:center; gap:6px; margin-top:12px; padding:10px 16px;
    background:var(--azul); color:#fff; font-weight:800; font-size:14px; border-radius:10px;
    text-decoration:none; }
  .reco-maps:active { filter:brightness(.95); }
  .reco-maps-grupo { display:inline-flex; align-items:center; gap:5px; margin-top:8px; padding:6px 12px;
    background:#ECFDF5; color:#166534; border:1px solid #A7F3D0; font-weight:700; font-size:13px;
    border-radius:8px; text-decoration:none; }
  .reco-maps-grupo:active { filter:brightness(.97); }
  .reco-min { font-size:12px; color:var(--gris); white-space:nowrap; }
  .reco-min::before { content:"→ "; }
  .reco-done { margin-top:10px; font-size:13px; color:#166534; }
  .reco-done s { color:var(--gris); }
  .reco-todo { margin-top:8px; font-size:14px; color:#166534; font-weight:700; }
  /* Botón "Ver completadas / Volver": al estar en modo, queda fijo abajo y te sigue */
  .ver-anteriores.modo-activo { position:fixed; bottom:16px; left:50%; transform:translateX(-50%);
    width:calc(100% - 24px); max-width:536px; z-index:30; background:var(--azul); color:#fff;
    border-style:solid; border-color:var(--azul); box-shadow:0 6px 18px rgba(15,23,42,.30); }
  body.modo-completadas main { padding-bottom:140px; }
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
  .ico-wa { vertical-align:-3px; }
  .acc-link .ico-wa { flex:0 0 auto; display:block; vertical-align:0; }
  .acc-link.acc-wa { background:#25D366; }
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
  header .ganado { margin-top:3px; font-weight:800; font-variant-numeric:tabular-nums;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  header .ganado:empty { display:none; }
  header .ganado .proy { font-weight:600; opacity:.75; font-size:12px; }
  .pago-adelantado-txt { margin-top:8px; font-size:13px; font-weight:800; color:#B45309;
    background:#FEF3C7; border:1px solid #FCD34D; border-radius:9px; padding:8px 10px; text-align:center; }
  .card-wrap.is-reagendado > .card, .card-wrap.is-reagendado > .gestion-top { border-color:#F87171; background:#FEF2F2; }
  .card-wrap.is-reagendado > .gestion-top { border-bottom:2px solid #FECACA; }
  .card-wrap.is-contactado > .card, .card-wrap.is-contactado > .gestion-top { border-color:#86EFAC; background:#F0FDF4; }
  .card-wrap.is-pendiente-reagendar > .card, .card-wrap.is-pendiente-reagendar > .gestion-top { border-color:#CBD5E1; background:#F1F5F9; }
  .card-wrap.oculto-anterior { display:none; }
  /* "Falta actualizar la fecha" (tras avisar, mientras no se mueve la fecha) */
  .btn-contacto.falta-fecha, .btn-contacto.falta-fecha:disabled { background:#FEF3C7; color:#92600A; border:1px solid #FCD34D; }
  /* Brillo del reagendar cuando hay que reposicionar (la primera vez) */
  .gt-fecha.glow .fecha-input { animation: glow-pulse 1.1s ease 3; }
  @keyframes glow-pulse { 0%,100% { box-shadow:0 0 0 0 rgba(217,119,6,0); } 50% { box-shadow:0 0 0 5px rgba(217,119,6,.5); } }
  /* Animación de "completada con éxito" (genérica: cards y tareas) */
  .celebrando { position:relative; }
  .celebra-overlay { position:absolute; inset:0; z-index:7; display:flex; align-items:center;
    justify-content:center; text-align:center; padding:18px; border-radius:14px;
    background:#FCD34D; color:#7C2D12; font-weight:800; font-size:17px; line-height:1.3;
    box-shadow:0 0 0 2px #F59E0B inset; animation:celebra-in .35s ease both; }
  @keyframes celebra-in { from { opacity:0; transform:scale(.94); } to { opacity:1; transform:scale(1); } }
  .colapsando { overflow:hidden; opacity:0;
    transition:height .5s ease, opacity .5s ease, margin .5s ease; }
  /* Salir por la izquierda (al des-marcar en "Ver completadas") */
  .saliendo-anim { overflow:hidden;
    transition:transform .32s ease, opacity .32s ease, height .35s ease, margin .35s ease; }
  /* Confirmación dentro de la card */
  .card-wrap.con-confirm, .tarea-card.con-confirm { position:relative; }
  .confirm-overlay { position:absolute; inset:0; z-index:9; display:flex; flex-direction:column;
    align-items:center; justify-content:center; gap:12px; text-align:center; padding:14px; border-radius:14px;
    background:rgba(254,242,242,.98); border:2px solid #F87171; animation:celebra-in .25s ease both; }
  .conf-msg { font-weight:800; color:#991B1B; font-size:14px; line-height:1.3; }
  .conf-acc { display:flex; gap:10px; }
  .conf-no, .conf-si { font-family:inherit; font-weight:700; font-size:13px; padding:10px 16px; border-radius:9px; cursor:pointer; min-height:42px; }
  .conf-no { background:#fff; border:1px solid var(--linea); color:var(--tinta); }
  .conf-si { background:#DC2626; border:none; color:#fff; }
  /* Título del modo "Ver completadas": flota justo encima del botón */
  .modo-titulo { position:fixed; bottom:72px; left:50%; transform:translateX(-50%);
    width:calc(100% - 24px); max-width:536px; z-index:30; margin:0;
    font-weight:800; color:#166534; background:#DCFCE7; border:1px solid #BBF7D0;
    border-radius:10px; padding:9px 12px; text-align:center; font-size:13px;
    box-shadow:0 4px 14px rgba(15,23,42,.18); }
  /* Tareas (limpiezas / retiros) interactivas */
  .tarea-lista { margin:8px 0 0; }
  /* Agrupación por día: encabezado de fecha por bloque */
  .tarea-dia { margin-top:6px; }
  .tarea-dia.oculto { display:none; }
  .dia-cab { font-size:12.5px; font-weight:800; color:var(--gris); text-transform:capitalize;
    letter-spacing:.3px; margin:10px 2px 6px; padding-bottom:4px; border-bottom:1px solid var(--linea); }
  .tarea-card { background:#fff; border:1px solid var(--linea); border-radius:12px; padding:11px 13px; margin-bottom:8px; }
  .tarea-info { display:flex; align-items:flex-start; gap:10px; }
  .tarea-card .btn-contacto, .tarea-card .contacto-accesos { margin-top:8px; }
  /* "Coordinar con el cliente" abre WhatsApp -> verde WhatsApp + su logo. */
  .btn-coordinar { background:#25D366; display:flex; align-items:center; justify-content:center; gap:6px; }
  .btn-coordinar .ico-wa { vertical-align:0; }
  /* "Realizada" es VERDE pero distinto del de WhatsApp (verde bosque, más oscuro). */
  .btn-realizada { width:100%; margin-top:8px; background:#15803D; color:#fff; border:none;
    font-family:inherit; font-weight:800; font-size:14px; padding:12px; border-radius:10px; cursor:pointer; min-height:46px; }
  .btn-realizada:active { filter:brightness(.95); }
  .tarea-card.oculto-anterior, .tarea-card.oculto-futuro, .tarea-card.oculto-no-entregado { display:none; }
  .card-wrap.oculto-eliminado { display:none; }
  /* Botón eliminar (dentro del detalle, al final): X roja discreta con confirmación */
  .detalle-danger { margin-top:12px; padding-top:10px; border-top:1px solid var(--linea); text-align:right; }
  .btn-eliminar { font-family:inherit; font-weight:700; font-size:13px; padding:8px 14px; border-radius:9px;
    background:#fff; color:#DC2626; border:1px solid #FCA5A5; cursor:pointer; min-height:40px; }
  .btn-eliminar:active { background:#FEF2F2; }
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
  .com-card { padding:11px 13px; margin-bottom:8px; background:#FFFBEB; border:1px solid #FCD34D; border-radius:12px; }
  .com-top { display:flex; align-items:center; gap:10px; }
  .com-acciones { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
  .com-wa, .com-info { flex:1 1 0; min-width:0; padding:9px 6px; border-radius:9px; font-family:inherit;
    font-size:12.5px; font-weight:700; cursor:pointer; min-height:42px; }
  .com-wa { background:#16A34A; color:#fff; border:none; }
  .com-info { background:#fff; color:#1F5AA8; border:1px solid #BFDBFE; }
  .com-wa:active, .com-info:active { filter:brightness(.96); }
  .info-reag { margin-top:8px; font-weight:800; color:#B91C1C; background:#FEE2E2; border:1px solid #FCA5A5; padding:7px 10px; border-radius:8px; }
  .info-clon { margin-top:10px; }
  /* Grupos de pago (Pago 1, Pago 2…) en "Mis pagos recibidos" */
  .pago-grupo { background:#F8FAFC; border:1px solid var(--linea); border-radius:14px; padding:12px; margin-bottom:12px; }
  .pago-head { display:flex; align-items:baseline; justify-content:space-between; gap:10px; }
  .pago-tit { font-weight:800; color:#166534; }
  .pago-tot { font-weight:800; color:#166534; font-variant-numeric:tabular-nums; }
  .com-ver-transf { width:100%; margin:8px 0 10px; padding:10px; border-radius:9px; font-family:inherit;
    font-weight:700; font-size:13px; cursor:pointer; background:#fff; color:#1F5AA8; border:1px solid #BFDBFE; }
  .com-ver-transf:active { filter:brightness(.96); }
  .transf-img { max-width:100%; border-radius:10px; display:block; }
  .transf-falta { color:var(--gris); font-size:14px; padding:12px; text-align:center; }
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
  /* Barra y botón pagar: fijo al fondo del viewport (sticky no es confiable en
     iOS por la barra de Safari dinámica; con fixed queda siempre a la vista). */
  .barra-pagar { position:fixed; left:0; right:0; bottom:0; z-index:30;
    padding:10px 12px calc(10px + env(safe-area-inset-bottom));
    background:rgba(255,255,255,.97); border-top:1px solid var(--linea);
    box-shadow:0 -4px 14px rgba(15,23,42,.10); }
  .btn-pagar { width:100%; max-width:536px; margin:0 auto; display:block;
    background:#16A34A; color:#fff; border:none; font-family:inherit;
    font-size:16px; font-weight:800; padding:15px; border-radius:13px; cursor:pointer; min-height:54px; }
  .btn-pagar:disabled { background:#CBD5E1; cursor:default; }
  body.vista-comision main { padding-bottom:96px; }
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
  // Logo de WhatsApp (para botones cuyo texto se fija por JS: hereda el color del texto).
  var WA_SVG = '<svg class="ico-wa" viewBox="0 0 24 24" width="15" height="15" fill="currentColor" aria-hidden="true"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.71.306 1.263.489 1.694.625.712.227 1.36.195 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>';
  var BANCO = APP.banco || {};
  var COMPROB = APP.comprobantes || {}; // fecha de pago -> ruta de la foto del comprobante
  var META = {};
  (APP.entregas || []).forEach(function (e) { META[e.id] = e; });
  var estado = {}; // id -> {id, estado, fecha, comision_pagada, pagada_at}
  var TAREAS = {};
  (APP.tareas || []).forEach(function (t) { TAREAS[t.id] = t; });
  var GEO = APP.geo || {};     // id -> {comuna, zona, lat, lng, aprox}
  var ZONAS = APP.zonas || {}; // zona -> {label, emoji, orden}
  var tEstado = {}; // id -> {contactado, realizada, realizada_at}
  var modoCompletadas = false; // false = ver pendientes; true = ver solo completadas
  // Guardamos las DESELECCIONADAS (no las seleccionadas): así toda comisión por
  // pagar entra marcada por defecto, incluso las que llegan luego desde Supabase.
  var comDesel = null; // Set de ids que el usuario destildó
  var comPorPagar = []; // ids cobrados sin pagar (se recalcula en renderComision)
  var SEL_KEY = 'comision_desel_v1';

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
  function eliminadoDe(id) { var st = estado[id]; return !!(st && st.eliminado); }
  // Fecha ISO (AAAA-MM-DD) de hoy y de hoy+N (medianoche local). Comparables como texto.
  function isoDesplazado(dias) {
    var d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + (dias || 0));
    return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
  }
  function parentEntId(tid) { return String(tid).split('::')[0]; }
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
    if (effISO && effISO < hoy) return 'a la brevedad';
    if (effISO === hoy) return 'hoy';
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
  function reagendarAvisadoDe(id) { var st = estado[id]; return !!(st && st.reagendar_avisado); }
  // Entrega contactada pero vencida sin entregar: hay que reagendar con el cliente.
  function requiereReagendar(id) {
    return estadoDe(id) === 'pendiente' && contactadoDe(id) && !!fechaDe(id) && fechaDe(id) < todayISO();
  }
  function pendienteReagendar(id) { return requiereReagendar(id) && !reagendarAvisadoDe(id); }
  function faltaActualizarFecha(id) { return requiereReagendar(id) && reagendarAvisadoDe(id); }
  function pagadaAtDe(id) {
    var st = estado[id];
    if (st && st.pagada_at) return st.pagada_at;
    return (META[id] && META[id].pagada_at) || '';
  }

  function pintarCard(card) {
    var id = card.getAttribute('data-id');
    var est = estadoDe(id);
    var fOrig = card.getAttribute('data-fecha');
    var fAct = fechaDe(id);
    var reagendado = !!(fAct && fOrig && fAct !== fOrig);
    var info = ESTADOS[est] || ESTADOS['pendiente'];

    // Dimensiones independientes.
    var entregado = entregadoDe(id);
    var cobrado = cobradoDe(id);
    var pagoAdelantado = (est === 'pagado-pendiente'); // cobrado sin entregar
    var listo = (est === 'cobrado');                   // entregado + cobrado
    var esPendiente = (est === 'pendiente');
    var contactado = contactadoDe(id);
    var esServ = !!(META[id] && META[id].es_servicio); // recambio/limpieza/retiro
    var rr = requiereReagendar(id); // contactada pero vencida sin entregar
    var pr = pendienteReagendar(id);
    var ff = faltaActualizarFecha(id);

    var badge = card.querySelector('.badge');
    if (badge) {
      var blbl = (est === 'entregado' && esServ) ? 'Realizado' : info[0];
      badge.textContent = blbl; badge.style.color = info[1]; badge.style.background = info[2];
    }

    // Color de la card. Prioridad: listo(dorado) > pago adelantado(ámbar) > entregado(azul) > reagendado(rojo) > pendiente-reagendar(gris) > contactado(verde).
    card.classList.toggle('is-cobrado', listo);
    card.classList.toggle('is-pago-adelantado', pagoAdelantado);
    card.classList.toggle('is-entregado', entregado && !cobrado);
    card.classList.toggle('is-reagendado', esPendiente && reagendado);
    card.classList.toggle('is-pendiente-reagendar', rr);
    card.classList.toggle('is-contactado', esPendiente && !reagendado && contactado && !rr);

    // Botones de estado (entregado y cobrado independientes).
    card.querySelectorAll('.est-btn').forEach(function (b) {
      var e = b.getAttribute('data-estado');
      var activo = (e === 'entregado' && entregado) || (e === 'cobrado' && cobrado);
      b.classList.toggle('activo', activo);
      if (e === 'cobrado') { b.textContent = cobrado ? 'Cliente ya pagó' : 'Cobrado'; }
      else if (e === 'entregado') { b.textContent = esServ ? 'Realizado' : 'Entregado'; }
    });

    // Aviso "pagó adelantado, falta entregar".
    var pa = card.querySelector('.pago-adelantado-txt');
    if (pa) { pa.hidden = !pagoAdelantado; }

    // Texto sutil que explica el color/estado de la card.
    var hint = card.querySelector('.estado-hint');
    if (hint) {
      var ht = '';
      if (est === 'entregado') { ht = esServ ? '🔵 Realizado · falta cobrar' : '🔵 Entregado · falta cobrar'; }
      else if (esPendiente && reagendado) { ht = '🔴 Reagendada · no se entregó a tiempo'; }
      else if (ff) { ht = '⚫ Falta actualizar la fecha'; }
      else if (pr) { ht = '⚫ Pendiente reagendar · no se entregó a tiempo'; }
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
      cbtn.classList.remove('contactado', 'reagendar-prompt', 'falta-fecha');
      if (pr) {
        cbtn.textContent = '💬 Pendiente reagendar — escribir al cliente'; cbtn.disabled = false;
      } else if (ff) {
        cbtn.textContent = '📅 Falta actualizar la fecha'; cbtn.disabled = true; cbtn.classList.add('falta-fecha');
      } else if (contactado) {
        cbtn.textContent = '✓ Cliente contactado'; cbtn.disabled = true; cbtn.classList.add('contactado');
      } else {
        cbtn.textContent = '💬 Avisar al cliente que voy a entregar'; cbtn.disabled = false;
      }
    }
    // Accesos rápidos (Llamar / Llegar / WhatsApp): SIEMPRE visibles. En reagendar
    // se oculta el WhatsApp (el botón de arriba ya va a WhatsApp), quedan Llamar y Llegar.
    var accesos = card.querySelector('.contacto-accesos');
    if (accesos) { accesos.hidden = false; }
    // Oculta el WhatsApp de accesos solo cuando el botón de arriba ya va a WhatsApp
    // (avisar o pendiente-reagendar), para no duplicar. Quedan Llamar y Llegar.
    var awa = card.querySelector('.acc-wa');
    if (awa) { awa.hidden = pr || (mostrar && !contactado); }
    // Brillo en el reagendar mientras esté vencida sin reagendar.
    var gtf = card.querySelector('.gt-fecha');
    if (gtf) { gtf.classList.toggle('glow', rr); }
  }
  function pintarTodo() { document.querySelectorAll('.card-wrap[data-id]').forEach(pintarCard); }

  // FLIP: ejecuta fn (que reordena las cards) y anima suavemente el reposicionamiento.
  function flipReubicar(fn) {
    var cards = Array.prototype.slice.call(document.querySelectorAll('.card-wrap[data-id]'))
      .filter(function (c) { return c.offsetParent !== null; });
    var firsts = cards.map(function (c) { return c.getBoundingClientRect().top; });
    fn();
    var movidas = [];
    cards.forEach(function (c, i) {
      if (c.offsetParent === null) return;
      var delta = firsts[i] - c.getBoundingClientRect().top;
      if (Math.abs(delta) > 1) { c.style.transition = 'none'; c.style.transform = 'translateY(' + delta + 'px)'; movidas.push(c); }
    });
    if (!movidas.length) return;
    requestAnimationFrame(function () {
      movidas.forEach(function (c) { c.style.transition = 'transform .4s ease'; c.style.transform = ''; });
      setTimeout(function () { movidas.forEach(function (c) { c.style.transition = ''; c.style.transform = ''; }); }, 460);
    });
  }

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
    h.innerHTML = escapeHtml(encabezadoFecha(fecha)) + PROG + '<span class="sec-chevron">▾</span>';
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
    // Orden general. UNA sección por día (getOrCreateSection reutiliza la sección de
    // esa fecha, así que cada data-fecha aparece una sola vez, con sus cards juntas).
    // Con cards de Supabase (traen data-informado) los días van por FECHA DESCENDENTE
    // (día más nuevo arriba) y, dentro de cada día, las cards por informado_at DESC
    // (lo último informado primero). Sin ese dato (horneadas de respaldo) se conserva
    // el orden histórico por fecha ascendente.
    var usaInformado = !!cont.querySelector('.card-wrap[data-informado]');
    var secs = Array.prototype.slice.call(cont.querySelectorAll('section[data-fecha]'));
    if (usaInformado) {
      secs.sort(function (a, b) { return b.getAttribute('data-fecha').localeCompare(a.getAttribute('data-fecha')); });
    } else {
      secs.sort(function (a, b) { return a.getAttribute('data-fecha').localeCompare(b.getAttribute('data-fecha')); });
    }
    secs.forEach(function (s) {
      var n = s.querySelectorAll('.card-wrap[data-id]').length;
      if (!n) { s.remove(); return; }
      var c = s.querySelector('.conteo'); if (c) { c.textContent = n; }
      var h2 = s.querySelector('h2');
      // Dentro del día, las cards por informado DESC (la más reciente informada arriba).
      if (h2 && usaInformado) {
        Array.prototype.slice.call(s.querySelectorAll('.card-wrap[data-id]'))
          .sort(function (a, b) { var ia = a.getAttribute('data-informado') || '', ib = b.getAttribute('data-informado') || ''; return ia < ib ? 1 : (ia > ib ? -1 : 0); })
          .forEach(function (cw) { s.appendChild(cw); });
      }
      // Las reagendadas (urgentes) van primero dentro del día.
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
        if (!META[id] || META[id].tipo !== 'bano') return; // limpiezas/retiros no cuentan baños
        if (eliminadoDe(id)) return; // eliminada no cuenta en el progreso
        var b = META[id].banos || 1;
        total += b;
        var e = estadoDe(id);
        if (e === 'entregado' || e === 'cobrado') { done += b; }
      });
      var pct = total ? Math.round(done / total * 100) : 0;
      var fill = sec.querySelector('.prog-fill'); if (fill) { fill.style.width = pct + '%'; }
      var num = sec.querySelector('.prog-num'); if (num) { num.textContent = done + '/' + total; }
    });
    renderRecomendacion(); // el plan de hoy se recalcula con cada cambio de estado
  }

  // ── Recomendación de reparto de HOY ──────────────────────────────────────
  // Arma la ruta del día, conecta las paradas cercanas (≤ JUNTOS_KM) como "cárgalos
  // juntos" y estima km/min "~" entre paradas. Todo con datos horneados (GEO) +
  // estado vivo (Supabase). Se recalcula al marcar entregas (via actualizarProgreso).
  var JUNTOS_KM = 12;     // umbral "van juntos" en km de MANEJO (ajustable: tu rango 10-15)
  var ROAD_FACTOR = 1.4;  // línea recta -> manejo aprox (las calles no van derechas)
  function haversineKm(a, b) {
    if (!a || !b || a.lat == null || b.lat == null) return null;
    var R = 6371, rad = Math.PI / 180;
    var dLat = (b.lat - a.lat) * rad, dLng = (b.lng - a.lng) * rad;
    var la1 = a.lat * rad, la2 = b.lat * rad;
    var h = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(la1) * Math.cos(la2) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
  }
  function roadKm(a, b) { var k = haversineKm(a, b); return k == null ? null : k * ROAD_FACTOR; }
  function kmMin(km) { return km == null ? null : Math.max(5, Math.round(km * 2.2 / 5) * 5); } // ~urbano
  function haversineMin(a, b) { return kmMin(roadKm(a, b)); }
  function recorta(s, n) { s = String(s || ''); return s.length > (n || 24) ? s.slice(0, (n || 24) - 1) + '…' : s; }

  // URL de Google Maps con la ruta completa. SIN origen fijo: Maps arranca desde la
  // ubicación actual del repartidor (su celular). Usa la DIRECCIÓN REAL de cada pedido
  // (mapsq), no el centro de la comuna, para que navegue al cliente.
  function buildMapsUrl(orderedStops) {
    var qs = [];
    orderedStops.forEach(function (c) {
      (c.mapsqsPend || []).forEach(function (q) { if (q) { qs.push(q); } });
    });
    if (!qs.length) return '';
    var url = 'https://www.google.com/maps/dir/?api=1&travelmode=driving' +
              '&destination=' + encodeURIComponent(qs[qs.length - 1]);
    var mids = qs.slice(0, -1);
    if (mids.length) { url += '&waypoints=' + mids.map(encodeURIComponent).join('%7C'); }
    return url;
  }

  function renderRecomendacion() {
    var box = document.getElementById('recomendacion-hoy');
    if (!box) return;
    var hoy = todayISO();

    // TODAS las entregas de hoy (fecha efectiva), baños, no eliminadas, entregadas o no.
    // Guardamos entregadas Y pendientes juntas: el ORDEN del día se calcula una sola
    // vez sobre todas, así no se reordena cuando el repartidor va marcando en ruta.
    var comunas = {}; // comuna -> {geo, banos, banosDone, clientes[], mapsqsPend[], done}
    var banosTot = 0, banosDone = 0;
    Object.keys(META).forEach(function (id) {
      var m = META[id];
      if (!m || m.tipo !== 'bano') return;
      if (eliminadoDe(id)) return;
      if (fechaDe(id) !== hoy) return;
      var g = GEO[id] || { comuna: 'Sin comuna', zona: 'otra', lat: null, lng: null, cliente: '', mapsq: '' };
      var b = m.banos || 1;
      var c = comunas[g.comuna] || (comunas[g.comuna] = { geo: g, banos: 0, banosDone: 0, clientes: [], mapsqsPend: [] });
      c.banos += b; banosTot += b;
      if (g.cliente) { c.clientes.push(g.cliente); }
      if (entregadoDe(id)) { c.banosDone += b; banosDone += b; }
      else if (g.mapsq) { c.mapsqsPend.push(g.mapsq); }
    });

    var stops = Object.keys(comunas).map(function (k) { return comunas[k]; });
    if (stops.length === 0) { box.hidden = true; box.innerHTML = ''; return; }
    box.hidden = false;
    stops.forEach(function (c) { c.done = c.banos > 0 && c.banosDone >= c.banos; });

    // Orden FIJO del día: por cercanía (norte→sur, sin base fija), sobre TODAS las
    // paradas (entregadas incluidas). Como el conjunto del día no cambia al entregar,
    // el orden se mantiene estable y el repartidor sigue su ruta sin saltos.
    stops = ordenarPorCercania(stops);
    // Paradas que faltan, en el MISMO orden: para los minutos restantes y la ruta a Maps.
    var pendientes = stops.filter(function (c) { return !c.done; });
    var banosPend = banosTot - banosDone;

    // Grupos "cárgalos juntos" sobre el orden fijo (mientras el salto sea ≤ JUNTOS_KM).
    var grupos = [];
    stops.forEach(function (c, i) {
      var km = i > 0 ? roadKm(stops[i - 1].geo, c.geo) : null;
      if (i === 0 || km == null || km > JUNTOS_KM) {
        grupos.push({ paradas: [{ stop: c, km: null }], saltoKm: km });
      } else {
        grupos[grupos.length - 1].paradas.push({ stop: c, km: km });
      }
    });
    // Link de Maps para UNA parada: validar/navegar esa dirección desde donde estés.
    function pinUrl(c) {
      var q = (c.mapsqsPend && c.mapsqsPend[0]) || '';
      return q ? 'https://www.google.com/maps/dir/?api=1&travelmode=driving&destination=' + encodeURIComponent(q) : '';
    }

    function chip(c) {
      var emoji = (ZONAS[c.geo.zona] || {}).emoji || '📍';
      var quien = '';
      if (c.clientes && c.clientes.length === 1 && c.clientes[0]) {
        quien = '<span class="reco-cli">· ' + escapeHtml(recorta(c.clientes[0])) + '</span>';
      } else if (c.clientes && c.clientes.length > 1) {
        quien = '<span class="reco-cli">· ' + c.clientes.length + ' clientes</span>';
      }
      var marca = c.done ? '✓ ' : '';
      var pin = (!c.done && pinUrl(c))
        ? '<a class="reco-pin" href="' + pinUrl(c) + '" target="_blank" rel="noopener" title="Ver / ir a esta dirección">📍</a>'
        : '';
      return '<span class="reco-stop' + (c.done ? ' hecho' : '') + '">' + marca + emoji + ' ' +
             escapeHtml(c.geo.comuna) + ' <span class="reco-n">' + c.banos + '</span>' + quien + '</span>' + pin;
    }

    var html = '';
    var sub = banosPend > 0
      ? ('Faltan ' + banosPend + ' de ' + banosTot + ' baño' + (banosTot === 1 ? '' : 's'))
      : '✅ ' + banosTot + ' baño' + (banosTot === 1 ? '' : 's') + ' entregado' + (banosTot === 1 ? '' : 's');
    html += '<div class="reco-head"><b>🗺️ Reparto de hoy</b><span class="reco-sub">' + sub + '</span></div>';

    grupos.forEach(function (g, gi) {
      if (gi > 0) { html += '<div class="reco-sep"></div>'; } // separador simple entre paradas lejanas
      // "Cárgalos juntos" solo si en el grupo queda MÁS DE UNA pendiente (ya entregadas no).
      var pendEnGrupo = g.paradas.filter(function (x) { return !x.stop.done; });
      var juntos = pendEnGrupo.length > 1;
      var banosG = pendEnGrupo.reduce(function (s, x) { return s + (x.stop.banos - x.stop.banosDone); }, 0);
      var chain = '';
      g.paradas.forEach(function (x, i) {
        if (i > 0 && x.km != null) { chain += '<span class="reco-min">~' + Math.round(x.km) + ' km</span>'; }
        chain += chip(x.stop);
      });
      // Botón de Maps del GRUPO: solo las cercanas, para ver la distancia/ruta entre ellas.
      var grupoMaps = juntos ? buildMapsUrl(pendEnGrupo.map(function (x) { return x.stop; })) : '';
      html += '<div class="reco-grupo' + (juntos ? ' juntos' : '') + '">' +
              (juntos ? '<div class="reco-junta">🚚 Carga estos ' + banosG + ' juntos (quedan cerca)</div>' : '') +
              '<div class="reco-chain">' + chain + '</div>' +
              (grupoMaps ? '<a class="reco-maps-grupo" href="' + grupoMaps + '" target="_blank" rel="noopener">🧭 Ver ruta de estos en Maps</a>' : '') +
              '</div>';
    });

    if (banosPend > 0) {
      var mapsUrl = buildMapsUrl(pendientes); // la ruta a Maps es solo lo que FALTA
      if (mapsUrl) {
        html += '<a class="reco-maps" href="' + mapsUrl + '" target="_blank" rel="noopener">🧭 Abrir ruta en Maps</a>';
      }
    } else {
      html += '<div class="reco-todo">🎉 ¡Todo lo de hoy entregado!</div>';
    }
    box.innerHTML = html;
  }

  // Ordena las paradas por vecino más cercano. SIN base fija (Maipú no tiene que ver
  // con el repartidor): parte de la más al norte y encadena por cercanía. Da un orden
  // estable y geográfico; en Maps la ruta arranca igual desde donde esté el repartidor.
  function ordenarPorCercania(lista) {
    var arr = lista.slice();
    if (arr.length <= 1) return arr;
    arr.sort(function (a, b) { return (b.geo.lat || -99) - (a.geo.lat || -99); }); // norte primero
    var orden = [arr.shift()], guard = 0;
    while (arr.length && guard++ < 100) {
      var last = orden[orden.length - 1], best = 0, bd = Infinity;
      for (var i = 0; i < arr.length; i++) {
        var d = haversineKm(last.geo, arr[i].geo);
        if (d != null && d < bd) { bd = d; best = i; }
      }
      orden.push(arr.splice(best, 1)[0]);
    }
    return orden;
  }

  // Fija la altura real del header para el 'top' de los encabezados sticky.
  function setHeaderH() {
    var h = document.querySelector('header');
    if (h) { document.documentElement.style.setProperty('--header-h', h.offsetHeight + 'px'); }
  }

  // ---- Completadas (estado 'cobrado'). En modo normal se ocultan; en "Ver
  //      completadas" se muestran SOLO ellas y se oculta todo lo demás. ----
  function aplicarAnteriores() {
    var nComp = 0;
    document.querySelectorAll('.card-wrap[data-id]').forEach(function (cw) {
      if (cw.classList.contains('celebrando') || cw.classList.contains('saliendo')) { return; } // animándose
      var id = cw.getAttribute('data-id');
      var elim = eliminadoDe(id);
      cw.classList.toggle('oculto-eliminado', elim);
      if (elim) { cw.classList.remove('oculto-anterior'); return; } // eliminada: fuera de la vista y de los conteos
      var completada = estadoDe(id) === 'cobrado';
      if (completada) { nComp++; }
      var ocultar = modoCompletadas ? !completada : completada;
      cw.classList.toggle('oculto-anterior', ocultar);
    });
    document.querySelectorAll('.vista[data-vista="entregas"] section[data-fecha]').forEach(function (sec) {
      var vis = sec.querySelectorAll('.card-wrap:not(.oculto-anterior):not(.oculto-eliminado)').length;
      sec.style.display = vis ? '' : 'none';
    });
    // En "Ver completadas" se ocultan también limpiezas/retiros (solo completadas).
    document.querySelectorAll('.vista[data-vista="entregas"] section.agregado').forEach(function (sec) {
      sec.style.display = modoCompletadas ? 'none' : '';
    });
    var btn = document.getElementById('toggle-anteriores');
    if (!btn) return;
    if (!nComp) { btn.hidden = true; btn.classList.remove('modo-activo'); modoCompletadas = false; return; }
    btn.hidden = false;
    btn.classList.toggle('modo-activo', modoCompletadas);
    document.body.classList.toggle('modo-completadas', modoCompletadas);
    btn.textContent = modoCompletadas ? '← Volver a ver clientes pendientes por entregar' : ('✓ Ver completadas (' + nComp + ')');
    var tit = document.getElementById('modo-titulo');
    if (tit) { tit.hidden = !modoCompletadas; tit.textContent = '👀 Estás viendo los clientes entregados y cobrados'; }
  }

  // Animación al completar (entregado + cobrado): card dorada con mensaje de éxito,
  // luego se desvanece y colapsa suavemente (las de abajo suben sin brusquedad).
  function celebrar(card, mensaje, onFin) {
    card.classList.add('celebrando');
    var ov = document.createElement('div');
    ov.className = 'celebra-overlay';
    ov.textContent = mensaje;
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
        if (onFin) { onFin(); }
        card.classList.remove('colapsando');
        card.style.height = ''; card.style.marginTop = ''; card.style.marginBottom = '';
      };
      card.addEventListener('transitionend', fin);
      setTimeout(fin, 700);
    }, 1800);
  }

  // Confirmación DENTRO de la card (al des-marcar entregado/cobrado).
  function confirmarEnCard(card, mensaje, onSi) {
    card.classList.add('con-confirm');
    var ov = document.createElement('div');
    ov.className = 'confirm-overlay';
    ov.innerHTML = '<div class="conf-msg">' + escapeHtml(mensaje) + '</div>'
      + '<div class="conf-acc"><button type="button" class="conf-no">Cancelar</button>'
      + '<button type="button" class="conf-si">Sí, confirmar</button></div>';
    card.appendChild(ov);
    function cerrar() { if (ov.parentNode) { ov.parentNode.removeChild(ov); } card.classList.remove('con-confirm'); }
    ov.querySelector('.conf-no').addEventListener('click', function (ev) { ev.preventDefault(); ev.stopPropagation(); cerrar(); });
    ov.querySelector('.conf-si').addEventListener('click', function (ev) { ev.preventDefault(); ev.stopPropagation(); cerrar(); onSi(); });
  }

  // Sale por la izquierda y cierra el hueco suavemente (las de abajo suben).
  function salirIzquierda(card, onFin) {
    card.style.height = card.offsetHeight + 'px';
    void card.offsetHeight;
    card.classList.add('saliendo-anim');
    card.style.transform = 'translateX(-110%)';
    card.style.opacity = '0';
    setTimeout(function () { card.style.height = '0px'; card.style.marginTop = '0'; card.style.marginBottom = '0'; }, 280);
    var hecho = false;
    function fin() {
      if (hecho) return; hecho = true;
      card.classList.remove('saliendo-anim');
      card.style.height = ''; card.style.transform = ''; card.style.opacity = ''; card.style.marginTop = ''; card.style.marginBottom = '';
      if (onFin) { onFin(); }
    }
    setTimeout(fin, 660);
  }

  // ====================== TAREAS (limpiezas / retiros) ======================
  function tContactadoDe(id) { var s = tEstado[id]; return !!(s && s.contactado); }
  function tRealizadaDe(id) {
    var s = tEstado[id];
    if (s && typeof s.realizada === 'boolean') return s.realizada;
    return !!(TAREAS[id] && TAREAS[id].hecha);
  }
  function pintarTarea(card) {
    var id = card.getAttribute('data-tid');
    var cont = tContactadoDe(id);
    var cb = card.querySelector('.btn-coordinar');
    if (cb) {
      if (cont) { cb.textContent = '✓ Ya lo contacté'; cb.disabled = true; cb.classList.add('contactado'); }
      else { cb.innerHTML = WA_SVG + ' Coordinar con el cliente'; cb.disabled = false; cb.classList.remove('contactado'); }
    }
    var acc = card.querySelector('.contacto-accesos');
    if (acc) { acc.hidden = !cont; }
    var hint = card.querySelector('.tarea-hint');
    if (hint) { hint.textContent = cont ? '🟢 Coordinado · listo para realizar' : '⚪ Pendiente · coordina con el cliente'; hint.hidden = false; }
  }
  function pintarTareas() { document.querySelectorAll('.tarea-card[data-tid]').forEach(pintarTarea); }

  function tUpsert(id, patch) {
    var prev = tEstado[id] || {};
    var row = { id: id, contactado: tContactadoDe(id), realizada: tRealizadaDe(id), realizada_at: prev.realizada_at || null };
    for (var k in patch) { row[k] = patch[k]; }
    tEstado[id] = row;
    var card = document.querySelector('.tarea-card[data-tid="' + String(id).replace(/"/g, '\\"') + '"]');
    if (card) { pintarTarea(card); }
    if (!SUPA.url || !SUPA.key) return Promise.resolve();
    return fetch(SUPA.url + '/rest/v1/tarea_estado', {
      method: 'POST',
      headers: headers({ 'Content-Type': 'application/json', 'Prefer': 'resolution=merge-duplicates,return=minimal' }),
      body: JSON.stringify(row)
    }).then(function (r) { if (!r.ok) { throw new Error('HTTP ' + r.status); } bannerOnline(true); })
      .catch(function (e) { console.warn(e); bannerOnline(false); });
  }

  // Filtra las tareas (limpiezas/retiros) por sección:
  //  - solo se muestran las de entregas ENTREGADAS (y no eliminadas);
  //  - por defecto solo hasta hoy+5 días (más los pendientes vencidos);
  //  - las realizadas se ocultan salvo "Ver realizadas".
  // Dos toggles arriba (bajo el título): "Ver todas" (futuras) y "Ver realizadas".
  function aplicarTareas() {
    var lim = isoDesplazado(5); // ventana: hasta hoy + 5 días
    document.querySelectorAll('section.agregado[data-tareas]').forEach(function (sec) {
      var verReal = sec.getAttribute('data-ver-real') === 'si';
      var verTodas = sec.getAttribute('data-ver-todas') === 'si';
      var nReal = 0, nFuturo = 0, nVisible = 0;
      sec.querySelectorAll('.tarea-card[data-tid]').forEach(function (c) {
        if (c.classList.contains('celebrando')) return;
        var tid = c.getAttribute('data-tid');
        var ent = c.getAttribute('data-ent') || parentEntId(tid);
        var f = c.getAttribute('data-fecha') || '';
        var entregado = entregadoDe(ent) && !eliminadoDe(ent);
        var realizada = tRealizadaDe(tid);
        var futuro = f > lim;
        var hideNoEnt = !entregado;
        var hideReal = entregado && realizada && !verReal;
        var hideFut = entregado && !realizada && futuro && !verTodas;
        c.classList.toggle('oculto-no-entregado', hideNoEnt);
        c.classList.toggle('oculto-anterior', hideReal);
        c.classList.toggle('oculto-futuro', hideFut);
        if (entregado && realizada) nReal++;
        if (entregado && !realizada && futuro) nFuturo++;
        if (!hideNoEnt && !hideReal && !hideFut) nVisible++;
      });
      // Ocultar encabezados de día sin tareas visibles.
      sec.querySelectorAll('.tarea-dia').forEach(function (dia) {
        var vis = dia.querySelectorAll('.tarea-card:not(.oculto-no-entregado):not(.oculto-anterior):not(.oculto-futuro)').length;
        dia.classList.toggle('oculto', !vis);
      });
      var cnt = sec.querySelector('.conteo');
      if (cnt) { cnt.textContent = nVisible; }
      var bTodas = sec.querySelector('.ver-todas');
      if (bTodas) {
        if (!nFuturo) { bTodas.hidden = true; }
        else {
          bTodas.hidden = false;
          bTodas.textContent = (verTodas ? '▴ Mostrar solo próximos 5 días' : '📅 Ver todas — próximas (' + nFuturo + ')');
          bTodas.classList.toggle('modo-activo', verTodas);
        }
      }
      var bReal = sec.querySelector('.ver-realizadas');
      if (bReal) {
        if (!nReal) { bReal.hidden = true; }
        else {
          bReal.hidden = false;
          bReal.textContent = (verReal ? '▴ Ocultar realizadas (' : '✓ Ver realizadas (') + nReal + ')';
          bReal.classList.toggle('modo-activo', verReal);
        }
      }
      // Si no queda nada visible ni toggles disponibles, se oculta la sección
      // (a menos que estemos en "Ver completadas", que lo maneja aplicarAnteriores).
      if (!modoCompletadas) { sec.style.display = (nVisible || nReal || nFuturo) ? '' : 'none'; }
    });
  }

  function wireTareas() {
    document.querySelectorAll('.tarea-card[data-tid]').forEach(function (card) {
      var id = card.getAttribute('data-tid');
      var t = TAREAS[id] || {};
      var cb = card.querySelector('.btn-coordinar');
      if (cb) {
        cb.addEventListener('click', function (ev) {
          ev.preventDefault();
          if (cb.disabled || tContactadoDe(id)) return;
          var dia = diaRelativo(t.fecha);
          var msg = (t.tipo === 'retiro')
            ? 'Hola 👋, le escribo de Destape Rápido. Le aviso que vamos a retirar el baño ' + dia + '. Le confirmo el horario en que pasaremos. ¡Gracias!'
            : 'Hola 👋, le escribo de Destape Rápido. Le aviso que vamos a hacer el aseo de su baño ' + dia + '. Le confirmo el horario en que pasaremos. ¡Gracias!';
          tUpsert(id, { contactado: true });
          if (t.tel) { window.location.href = 'whatsapp://send?phone=' + t.tel + '&text=' + encodeURIComponent(msg); }
        });
      }
      card.querySelectorAll('.acc-link').forEach(function (a) {
        a.addEventListener('click', function (ev) {
          ev.preventDefault(); ev.stopPropagation();
          var href = a.getAttribute('href') || '';
          if (/^https?:/.test(href)) { window.open(href, '_blank'); } else { window.location.href = href; }
        });
      });
      var rb = card.querySelector('.btn-realizada');
      if (rb) {
        rb.addEventListener('click', function (ev) {
          ev.preventDefault();
          if (tRealizadaDe(id)) return;
          var pregunta = (t.tipo === 'retiro') ? '¿Confirmas que hiciste el retiro?' : '¿Confirmas que hiciste la limpieza?';
          confirmarEnCard(card, pregunta, function () {
            card.classList.add('celebrando');
            tUpsert(id, { realizada: true, realizada_at: new Date().toISOString() });
            var msg = (t.tipo === 'retiro') ? '✅ Retiro realizado con éxito' : '✅ Limpieza realizada con éxito';
            celebrar(card, msg, aplicarTareas);
          });
        });
      }
    });
    // Toggle "Ver realizadas": muestra/oculta las tareas ya hechas de esa sección.
    document.querySelectorAll('.ver-realizadas').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var sec = btn.closest('section.agregado');
        if (!sec) return;
        sec.setAttribute('data-ver-real', sec.getAttribute('data-ver-real') === 'si' ? 'no' : 'si');
        aplicarTareas();
      });
    });
    // Toggle "Ver todas": muestra/oculta las tareas más allá de los próximos 5 días.
    document.querySelectorAll('.ver-todas').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var sec = btn.closest('section.agregado');
        if (!sec) return;
        sec.setAttribute('data-ver-todas', sec.getAttribute('data-ver-todas') === 'si' ? 'no' : 'si');
        aplicarTareas();
      });
    });
  }

  function loadTareas() {
    if (!SUPA.url || !SUPA.key) { pintarTareas(); aplicarTareas(); return; }
    fetch(SUPA.url + '/rest/v1/tarea_estado?select=*', { headers: headers() })
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (rows) { rows.forEach(function (row) { tEstado[row.id] = row; }); })
      .catch(function (e) { console.warn(e); })
      .then(function () { pintarTareas(); aplicarTareas(); });
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
      comision_pagada: pagadaDe(id), pagada_at: prev.pagada_at || null, contactado: contactadoDe(id),
      reagendar_avisado: reagendarAvisadoDe(id), eliminado: eliminadoDe(id)
    };
    for (var k in patch) { row[k] = patch[k]; }
    if (row.fecha === '') { row.fecha = null; }
    estado[id] = row;
    var card = qCard(id);
    if (card) { pintarCard(card); }
    reubicarCards();
    actualizarProgreso();
    aplicarAnteriores();
    aplicarTareas();
    actualizarGanado();
    renderComision();
    if (!SUPA.url || !SUPA.key) return Promise.resolve(true);
    return fetch(SUPA.url + '/rest/v1/entrega_estado', {
      method: 'POST',
      headers: headers({ 'Content-Type': 'application/json', 'Prefer': 'resolution=merge-duplicates,return=minimal' }),
      body: JSON.stringify(row)
    }).then(function (r) {
      if (!r.ok) { throw new Error('HTTP ' + r.status); }
      bannerOnline(true); return true;
    }).catch(function (e) { console.warn('No se pudo guardar', e); bannerOnline(false); return false; });
  }

  // ====================== VISTA COMISIÓN (flujo de pago) ======================
  function loadSel() { try { return JSON.parse(localStorage.getItem(SEL_KEY)); } catch (e) { return null; } }
  function saveSel() { try { localStorage.setItem(SEL_KEY, JSON.stringify(Array.from(comDesel))); } catch (e) {} }
  function seleccionadas() { return comPorPagar.filter(function (id) { return !comDesel.has(id); }); }

  function comisionables() {
    var ids = Object.keys(META).filter(function (id) {
      var m = META[id];
      return m.comisiona && m.comision && cobradoDe(id) && !eliminadoDe(id);
    });
    ids.sort(function (a, b) { return (fechaDe(a) || '').localeCompare(fechaDe(b) || ''); });
    return ids;
  }

  // Total recaudado: lo que LLEVAN (cobrado) y el total si se concreta TODO.
  // También actualiza el contador de pendientes (no completadas) en vivo.
  function actualizarGanado() {
    var llevan = 0, total = 0, pend = 0;
    Object.keys(META).forEach(function (id) {
      if (eliminadoDe(id)) { return; }
      var mm = META[id].monto || 0;
      total += mm;
      if (cobradoDe(id)) { llevan += mm; }
      if (estadoDe(id) !== 'cobrado') { pend++; }
    });
    var el = document.getElementById('ganado-total');
    if (el) { el.innerHTML = '💰 <b>' + clp(llevan) + '</b> <span class="proy">/ ' + clp(total) + ' si se cobra todo</span>'; }
    var pc = document.getElementById('pend-count');
    if (pc) { pc.textContent = pend; }
    setHeaderH(); // el alto del header cambia con la línea de "ganado"
  }

  // Modal con TODA la info del cliente/entrega (reusa el detalle de su card).
  function verInfoEntrega(id) {
    var m = META[id] || {};
    var card = document.querySelector('.card-wrap[data-id="' + String(id).replace(/"/g, '\\"') + '"]');
    var detalle = card ? card.querySelector('.detalle').innerHTML : '<p>Sin detalle disponible.</p>';
    var estLbl = (ESTADOS[estadoDe(id)] || ESTADOS['pendiente'])[0];
    var fOrig = m.fecha, fAct = fechaDe(id);
    var reag = (fAct && fOrig && fAct !== fOrig)
      ? '<div class="info-reag">⚠ Reagendada: de ' + fechaLarga(fOrig) + ' a ' + fechaLarga(fAct) + '</div>' : '';
    var bg = document.createElement('div');
    bg.className = 'modal-bg';
    bg.innerHTML = '<div class="modal"><h3>' + escapeHtml(m.cliente || 'Cliente') + '</h3>'
      + '<div class="modal-sub">Estado: ' + estLbl + ' · Entrega: ' + fechaLarga(fAct || fOrig) + '</div>'
      + reag
      + '<div class="info-clon">' + detalle + '</div>'
      + '<div class="modal-acciones"><button type="button" class="btn-modal cancelar">Cerrar</button></div></div>';
    document.body.appendChild(bg);
    bg.addEventListener('click', function (ev) { if (ev.target === bg) { document.body.removeChild(bg); } });
    bg.querySelector('.cancelar').addEventListener('click', function () { document.body.removeChild(bg); });
  }

  // Modal con la foto del comprobante de un pago (la sube Alejandro manual).
  function verTransferencia(key) {
    var url = COMPROB[key];
    var bg = document.createElement('div');
    bg.className = 'modal-bg';
    bg.innerHTML = '<div class="modal"><h3>Comprobante de transferencia</h3>'
      + '<div class="transf-cuerpo"></div>'
      + '<div class="modal-acciones"><button type="button" class="btn-modal cancelar">Cerrar</button></div></div>';
    var cuerpo = bg.querySelector('.transf-cuerpo');
    if (url) {
      var img = document.createElement('img');
      img.className = 'transf-img'; img.alt = 'comprobante'; img.src = url;
      var falta = document.createElement('div');
      falta.className = 'transf-falta'; falta.style.display = 'none';
      falta.textContent = 'Aún no subiste la foto de este pago (' + url + ').';
      img.addEventListener('error', function () { img.style.display = 'none'; falta.style.display = 'block'; });
      cuerpo.appendChild(img); cuerpo.appendChild(falta);
    } else {
      cuerpo.innerHTML = '<div class="transf-falta">Aún no hay comprobante para este pago. Súbelo manualmente.</div>';
    }
    document.body.appendChild(bg);
    bg.addEventListener('click', function (ev) { if (ev.target === bg) { document.body.removeChild(bg); } });
    bg.querySelector('.cancelar').addEventListener('click', function () { document.body.removeChild(bg); });
  }

  function renderComision() {
    actualizarGanado();
    var cont = document.getElementById('comision-panel');
    if (!cont) return;
    var ids = comisionables();
    var porPagar = ids.filter(function (id) { return !pagadaDe(id); });
    var pagadas = ids.filter(function (id) { return pagadaDe(id); });

    if (comDesel === null) { comDesel = new Set(loadSel() || []); }
    comPorPagar = porPagar; // por defecto todas marcadas, salvo las destildadas

    var deuda = porPagar.reduce(function (s, id) { return s + META[id].comision; }, 0);
    var yaPagada = pagadas.reduce(function (s, id) { return s + META[id].comision; }, 0);

    function card(id, paid) {
      var m = META[id];
      var check = paid
        ? '<span class="com-pagada-tag">✓ Pagada</span>'
        : '<input type="checkbox" class="com-check" data-id="' + escapeHtml(id) + '"' + (comDesel.has(id) ? '' : ' checked') + '>';
      var rev = paid ? '<button type="button" class="com-revocar" data-id="' + escapeHtml(id) + '">Revocar</button>' : '';
      var wa = m.tel ? '<button type="button" class="com-wa" data-id="' + escapeHtml(id) + '"><svg class="ico-wa" viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.71.306 1.263.489 1.694.625.712.227 1.36.195 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg> Revisar en WhatsApp</button>' : '';
      return '<div class="com-card' + (paid ? ' com-pagada' : '') + '">'
        + '<div class="com-top">' + check
        + '<div class="com-main"><div class="com-cli">' + escapeHtml(m.cliente) + '</div>'
        + '<div class="com-dir">📍 ' + escapeHtml(m.direccion || '') + ' · ' + fechaLarga(fechaDe(id)) + '</div></div>'
        + '<div class="com-monto">' + clp(m.comision) + '</div>' + rev + '</div>'
        + '<div class="com-acciones">' + wa
        + '<button type="button" class="com-info" data-id="' + escapeHtml(id) + '">📋 Ver toda la info</button></div>'
        + '</div>';
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
      // Agrupar por momento de pago: cada grupo es un "Pago N" con su comprobante.
      var grupos = {};
      pagadas.forEach(function (id) {
        var k = pagadaAtDe(id) || 'sin-fecha';
        (grupos[k] = grupos[k] || []).push(id);
      });
      var claves = Object.keys(grupos).sort();
      html += '<div class="com-sec-tit">Mis pagos recibidos · ' + clp(yaPagada) + '</div>';
      claves.forEach(function (k, i) {
        var idsg = grupos[k];
        var tot = idsg.reduce(function (s, id) { return s + META[id].comision; }, 0);
        var fechaTxt = (k === 'sin-fecha') ? 'sin fecha' : fechaLarga(k.split('T')[0]);
        html += '<div class="pago-grupo"><div class="pago-head">'
          + '<span class="pago-tit">Pago ' + (i + 1) + ' · ' + fechaTxt + '</span>'
          + '<span class="pago-tot">' + clp(tot) + '</span></div>'
          + '<button type="button" class="com-ver-transf" data-key="' + escapeHtml(k) + '">📷 Ver transferencia</button>'
          + idsg.map(function (id) { return card(id, true); }).join('')
          + '</div>';
      });
    }
    cont.innerHTML = html;

    cont.querySelectorAll('.com-check').forEach(function (ch) {
      ch.addEventListener('change', function () {
        var id = ch.getAttribute('data-id');
        if (ch.checked) comDesel.delete(id); else comDesel.add(id);
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
    cont.querySelectorAll('.com-wa').forEach(function (b) {
      b.addEventListener('click', function () {
        var tel = (META[b.getAttribute('data-id')] || {}).tel;
        if (tel) { window.location.href = 'whatsapp://send?phone=' + tel; }
      });
    });
    cont.querySelectorAll('.com-info').forEach(function (b) {
      b.addEventListener('click', function () { verInfoEntrega(b.getAttribute('data-id')); });
    });
    cont.querySelectorAll('.com-ver-transf').forEach(function (b) {
      b.addEventListener('click', function () { verTransferencia(b.getAttribute('data-key')); });
    });
    updateBarra();
  }

  function seleccionTotal() {
    return seleccionadas().reduce(function (t, id) { return t + (META[id] ? META[id].comision : 0); }, 0);
  }
  function updateBarra() {
    var barra = document.getElementById('barra-pagar');
    if (!barra) return;
    var n = seleccionadas().length;
    var total = seleccionTotal();
    var btn = barra.querySelector('.btn-pagar');
    btn.disabled = (n === 0);
    btn.textContent = n ? ('Pagar ' + clp(total) + ' · ' + n + ' selec.') : 'Selecciona comisiones';
    barra.hidden = false;
  }

  function abrirModalPago() {
    if (comDesel === null) return;
    var seleccion = seleccionadas();
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
      var btn = bg.querySelector('.confirmar');
      btn.disabled = true; btn.textContent = 'Guardando…';
      var ahora = new Date().toISOString();
      Promise.all(seleccion.map(function (id) { return upsert(id, { comision_pagada: true, pagada_at: ahora }); }))
        .then(function (oks) {
          // Si algún guardado falló, revertir el optimismo y NO dar por pagado.
          var fallo = false;
          oks.forEach(function (ok, i) {
            if (!ok) { fallo = true; var id = seleccion[i]; if (estado[id]) { estado[id].comision_pagada = false; estado[id].pagada_at = null; } }
          });
          if (fallo) {
            renderComision();
            btn.disabled = false; btn.textContent = 'Marcar pagadas y abrir WhatsApp';
            alert('No se pudo registrar el pago (sin conexión). Reintenta cuando tengas señal.');
            return;
          }
          var lineas = seleccion.map(function (id) { return '• ' + META[id].cliente + ': ' + clp(META[id].comision); });
          var texto = 'Hola Alejandro, te transfiero la comisión:\n' + lineas.join('\n')
            + '\nTotal: ' + clp(total) + '\nFecha: ' + new Date().toLocaleString('es-CL')
            + '\n(Te envío el comprobante de la transferencia.)';
          if (document.body.contains(bg)) document.body.removeChild(bg);
          if (WA) { window.location.href = 'whatsapp://send?phone=' + WA + '&text=' + encodeURIComponent(texto); }
        });
    });
  }

  // ---- Contenido de entregas desde Supabase (tabla `entrega`) ----
  // El contenido (cliente, monto, etc.) también vive en Supabase: la tarjeta ya
  // viene renderizada en `card_html` (misma función Python que hornea el listado).
  // La página pide ese HTML y lo inyecta, ordenado por `informado_at` DESC (la más
  // reciente informada arriba). Si el fetch falla o viene vacío, quedan las
  // horneadas de respaldo (free tier: Supabase se pausa por inactividad).

  // Puertos JS de las funciones puras del generador, para recomputar el META
  // (comisión, progreso, ganado) desde el `data` crudo de cada fila.
  function soloDigitosJS(t) {
    var d = String(t == null ? '' : t).replace(/\D/g, '');
    if (d.indexOf('56') === 0) { return d; }
    if (d.charAt(0) === '9' && d.length === 9) { return '56' + d; }
    return d;
  }
  function banosDeJS(e) {
    var c = e.cantidad;
    if (typeof c === 'number' && c > 0) { return c; }
    var m = /(\d+)\s*ba[ñn]o/i.exec(e.servicio || '');
    return m ? parseInt(m[1], 10) : 1;
  }
  function metaDeData(e) {
    e = e || {};
    var pago = e.pago || {};
    var monto = (pago.monto != null) ? pago.monto : null;
    var esServ = (e.comision === false);
    var lleva = !!((e.factura || {}).requiere);
    var neto = (monto == null) ? 0 : Math.round(lleva ? (monto / 1.19) : monto);
    var comisiona = !esServ && (monto != null);
    var comision = comisiona ? Math.round(neto * 0.20) : 0;
    return {
      id: e.id || '', cliente: e.cliente || '—', fecha: e.fecha || '',
      neto: neto, comision: comision, comisiona: comisiona,
      estado: e.estado || 'pendiente',
      comision_pagada: !!e.comision_pagada, pagada_at: e.pagada_at || null,
      tel: soloDigitosJS(e.telefono || ''), banos: banosDeJS(e),
      tipo: esServ ? 'limpieza' : 'bano', es_servicio: esServ,
      monto: monto || 0
    };
  }
  // Reemplaza las cards horneadas por las de Supabase (ya ordenadas por el fetch).
  function aplicarEntregas(rows) {
    // 1) META desde el `data` crudo → comisión, progreso y ganado se recomputan solos.
    var nuevo = {};
    rows.forEach(function (row) {
      var e = (row && row.data) || {};
      var id = e.id || (row && row.id);
      if (id) { nuevo[id] = metaDeData(e); }
    });
    META = nuevo;
    // 2) Inyecta las tarjetas pre-renderizadas, en el orden recibido (informado DESC).
    var cont = document.querySelector('.vista[data-vista="entregas"]');
    if (!cont) { return; }
    cont.querySelectorAll('.card-wrap[data-id]').forEach(function (c) { c.remove(); });
    cont.querySelectorAll('section[data-fecha]').forEach(function (s) {
      if (!s.querySelector('.card-wrap[data-id]')) { s.remove(); }
    });
    var tpl = document.createElement('template');
    rows.forEach(function (row) {
      if (!row || !row.card_html) { return; }
      tpl.innerHTML = String(row.card_html).trim();
      var cw = tpl.content.firstElementChild;
      if (!cw) { return; }
      // data-informado: sella cuándo se informó, para ordenar por eso en JS.
      if (row.informado_at) { cw.setAttribute('data-informado', row.informado_at); }
      var f = cw.getAttribute('data-fecha') || (row.fecha || '');
      getOrCreateSection(cont, f).appendChild(cw);
    });
    // Re-engancha los listeners sobre las cards inyectadas (guardado por card.__wired
    // y wire.__globals: no duplica listeners de cards ni globales ya enganchados).
    wire();
  }

  function load() {
    var done = function () { pintarTodo(); reubicarCards(); actualizarProgreso(); aplicarAnteriores(); aplicarTareas(); renderComision(); revelar(); };
    if (!SUPA.url || !SUPA.key) { done(); return; }
    // Estado mutable (entregado/cobrado/…): puebla el mapa `estado`.
    var pEstado = fetch(SUPA.url + '/rest/v1/entrega_estado?select=*', { headers: headers() })
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (rows) { rows.forEach(function (row) { estado[row.id] = row; }); })
      .catch(function (e) { console.warn(e); });
    // Contenido de entregas (card_html) ordenado por informado_at DESC.
    var pEntrega = fetch(SUPA.url + '/rest/v1/entrega?select=id,fecha,informado_at,data,card_html&eliminado=eq.false&order=informado_at.desc', { headers: headers() })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function (e) { console.warn(e); return null; });
    Promise.all([pEstado, pEntrega]).then(function (res) {
      var rows = res[1];
      if (rows && rows.length) {
        // Si algo falla al inyectar, dejamos las horneadas (respaldo).
        try { aplicarEntregas(rows); }
        catch (e) { console.warn('No se pudo aplicar entregas de Supabase, uso las horneadas:', e); }
      }
      done();
    });
  }

  function wire() {
    document.querySelectorAll('.card-wrap[data-id]').forEach(function (card) {
      var id = card.getAttribute('data-id');
      if (card.__wired) { return; } // no re-enganchar (cards ya inyectadas desde Supabase)
      card.__wired = true;
      card.querySelectorAll('.est-btn').forEach(function (b) {
        b.addEventListener('click', function (ev) {
          ev.preventDefault(); ev.stopPropagation();
          var e = b.getAttribute('data-estado');
          var quitando = (e === 'entregado' && entregadoDe(id)) || (e === 'cobrado' && cobradoDe(id));
          function aplicar() {
            var ent = entregadoDe(id), cob = cobradoDe(id);
            if (e === 'entregado') { ent = !ent; } else { cob = !cob; }
            var next = cob ? (ent ? 'cobrado' : 'pagado-pendiente') : (ent ? 'entregado' : 'pendiente');
            var completa = (next === 'cobrado' && estadoDe(id) !== 'cobrado');
            // En "Ver completadas", des-marcar saca la card de la vista: sale por la izquierda.
            var sale = modoCompletadas && estadoDe(id) === 'cobrado' && next !== 'cobrado';
            if (completa) { card.classList.add('celebrando'); }
            if (sale) { card.classList.add('saliendo'); }
            upsert(id, { estado: next });
            if (completa) {
              var mm = META[id] || {};
              var msgC = (mm.tipo === 'limpieza') ? '✅ Limpieza realizada con éxito'
                : '✅ ' + ((mm.banos > 1) ? 'Baños entregados' : 'Baño entregado') + ' con éxito';
              celebrar(card, msgC, function () { aplicarAnteriores(); reubicarCards(); actualizarProgreso(); renderComision(); });
            } else if (sale) {
              salirIzquierda(card, function () {
                card.classList.remove('saliendo');
                aplicarAnteriores(); reubicarCards(); actualizarProgreso(); renderComision();
              });
            }
          }
          if (quitando) {
            var msg = (e === 'cobrado')
              ? '¿Confirmas que el cliente NO pagó? Volverá a pendiente de cobro.'
              : '¿Confirmas que NO se entregó? Volverá a pendiente de entrega.';
            confirmarEnCard(card, msg, aplicar);
          } else { aplicar(); }
        });
      });
      var input = card.querySelector('.fecha-input');
      if (input) {
        input.addEventListener('change', function () {
          flipReubicar(function () { upsert(id, { fecha: input.value || null }); });
        });
      }
      var del = card.querySelector('.btn-eliminar');
      if (del) {
        del.addEventListener('click', function (ev) {
          ev.preventDefault(); ev.stopPropagation();
          if (eliminadoDe(id)) return;
          confirmarEnCard(card, '¿Eliminar esta entrega? Se quitará de la lista.', function () {
            card.classList.add('saliendo');
            upsert(id, { eliminado: true });
            salirIzquierda(card, function () {
              card.classList.remove('saliendo');
              reubicarCards(); actualizarProgreso(); aplicarAnteriores(); aplicarTareas(); actualizarGanado(); renderComision();
            });
          });
        });
      }
      var cbtn = card.querySelector('.btn-contacto');
      if (cbtn) {
        cbtn.addEventListener('click', function (ev) {
          ev.preventDefault(); ev.stopPropagation();
          var tel = (META[id] && META[id].tel) || '';
          // Pendiente reagendar: mensaje para reagendar; se activa una sola vez.
          if (pendienteReagendar(id)) {
            var msgR = 'Hola 👋, le escribo de Destape Rápido. No alcanzamos a entregar su baño el día previsto. '
              + '¿Lo reagendamos? ¿Qué día le acomoda mejor? ¡Gracias!';
            upsert(id, { reagendar_avisado: true });
            if (tel) { window.location.href = 'whatsapp://send?phone=' + tel + '&text=' + encodeURIComponent(msgR); }
            return;
          }
          if (cbtn.disabled || contactadoDe(id)) return;
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
    if (wire.__globals) { return; } // los listeners globales se enganchan una sola vez
    wire.__globals = true;
    var ta = document.getElementById('toggle-anteriores');
    if (ta) {
      ta.addEventListener('click', function () {
        modoCompletadas = !modoCompletadas;
        aplicarAnteriores();
        aplicarTareas();
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    }
    // Pinchar el encabezado de un día lo colapsa/expande (delegado, también sirve
    // para las secciones que crea el reagendado).
    var ve = document.querySelector('.vista[data-vista="entregas"]');
    if (ve) {
      ve.addEventListener('click', function (ev) {
        var h = ev.target.closest('.fecha-titulo');
        if (!h) return;
        var sec = h.closest('section[data-fecha]');
        if (sec) { sec.classList.toggle('colapsada-dia'); }
      });
    }
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
        document.body.classList.toggle('vista-comision', v === 'comision');
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
  pintarTareas(); aplicarTareas();
  setTimeout(revelar, 1500); // fallback si la red tarda demasiado
  wireVistas();
  wire();
  wireTareas();
  load();
  loadTareas();
})();
</script>"""


def _tarea_card(tid, fecha, cliente, direccion, tel, etiqueta, nota, extra_html, contexto, coordenadas="") -> str:
    """Card interactiva de una tarea (limpieza/retiro): coordinar, accesos, realizada."""
    num = solo_digitos(tel)
    accesos = []
    # OJO: el botón WhatsApp NO va aquí; "Coordinar con el cliente" ya abre WhatsApp
    # (mismo verde + logo), así que ponerlo también en los accesos sería redundante.
    if num:
        accesos.append(f'<a class="acc-link acc-call" href="tel:{esc(tel)}">📞 Llamar</a>')
    if direccion or coordenadas:
        maps_q = maps_href(direccion, coordenadas)
        accesos.append(f'<a class="acc-link acc-map" href="{esc(maps_q)}">🗺️ Llegar 🧭</a>')
    accesos_html = f'<div class="contacto-accesos" hidden>{"".join(accesos)}</div>'
    realizada_lbl = "✅ Limpieza realizada" if contexto == "limpieza" else "✅ Retiro realizado"
    nota_html = f'<span class="ag-sub">{esc(nota)}</span>' if nota else ""
    ent_tarea = tid.split("::")[0]
    return (
        f'<div class="tarea-card" data-tid="{esc(tid)}" data-ent="{esc(ent_tarea)}" data-fecha="{esc(fecha)}">'
        '<div class="tarea-info">'
        f'<span class="ag-main"><b>{esc(cliente)}</b>'
        f'<span class="ag-dir">📍 {calle_negrita(direccion)}</span>'
        f'<span class="ag-sub">{esc(etiqueta)}</span>{nota_html}</span>'
        f'{extra_html}</div>'
        '<div class="estado-hint tarea-hint" hidden></div>'
        '<button type="button" class="btn-contacto btn-coordinar"></button>'
        f'{accesos_html}'
        f'<button type="button" class="btn-realizada">{realizada_lbl}</button>'
        '</div>'
    )


def _lista_por_dia(cards) -> str:
    """Agrupa cards [(fecha, html), ...] (ya ordenadas) en bloques por día, con
    un encabezado de fecha por bloque. Facilita ver las tareas de cada día."""
    from itertools import groupby
    bloques = []
    for fecha, grupo in groupby(cards, key=lambda x: x[0]):
        cs = "".join(html for _, html in grupo)
        cab = esc(fecha_corta(fecha)) if fecha else "Sin fecha"
        bloques.append(
            f'<div class="tarea-dia" data-dia="{esc(fecha)}">'
            f'<div class="dia-cab">{cab}</div>{cs}</div>'
        )
    return "".join(bloques)


def _seccion_tareas(titulo, cards, n_total):
    """HTML de una sección de tareas: título + toggle 'Ver realizadas' (arriba),
    lista agrupada por día, y toggle 'Ver todas — próximas' (abajo, tras el límite)."""
    return (
        f'<section class="agregado" data-tareas><h2 class="fecha-titulo">{titulo}'
        f'<span class="conteo">{n_total}</span></h2>'
        '<button class="ver-anteriores ver-realizadas" type="button" hidden></button>'
        f'<div class="tarea-lista">{_lista_por_dia(cards)}</div>'
        '<button class="ver-anteriores ver-todas" type="button" hidden></button></section>'
    )


def seccion_limpiezas(entregas: list):
    """(html, tareas) — cada limpieza es una tarea interactiva, agrupada por día."""
    filas = []
    for e in entregas:
        for idx, lp in enumerate(e.get("limpiezas") or []):
            filas.append((lp.get("fecha", ""), e, idx, lp))
    if not filas:
        return "", []
    filas.sort(key=lambda x: x[0])
    cards, tareas = [], []
    for fecha, e, idx, lp in filas:
        tid = f'{e.get("id", "")}::lim::{idx}'
        tipo = lp.get("tipo", "incluida")
        etq_t, col_t, bg_t = TIPO_LIMPIEZA.get(tipo, TIPO_LIMPIEZA["incluida"])
        extra = f'<span class="lp-badge" style="color:{col_t};background:{bg_t}">{etq_t}</span>'
        if tipo == "extra" and lp.get("valor"):
            extra += f'<span class="lp-valor">{esc(clp(lp.get("valor")))}</span>'
        cards.append((fecha, _tarea_card(tid, fecha, e.get("cliente", "—"), e.get("direccion", ""),
                                         e.get("telefono", ""), lp.get("etiqueta") or "Limpieza",
                                         lp.get("nota"), extra, "limpieza", e.get("coordenadas", ""))))
        tareas.append({"id": tid, "tel": solo_digitos(e.get("telefono", "")), "fecha": fecha,
                       "tipo": "limpieza", "hecha": lp.get("estado") == "hecha"})
    return _seccion_tareas("🧽 Limpiezas a realizar", cards, len(filas)), tareas


def seccion_retiros(entregas: list):
    """(html, tareas) — cada retiro es una tarea interactiva, agrupada por día."""
    datos = [(r.get("fecha", ""), e, r) for e in entregas if (r := e.get("retiro"))]
    if not datos:
        return "", []
    datos.sort(key=lambda x: x[0])
    cards, tareas = [], []
    for fecha, e, r in datos:
        tid = f'{e.get("id", "")}::retiro'
        extra = '<span class="lp-badge" style="color:#1E40AF;background:#DBEAFE">Retiro</span>'
        cards.append((fecha, _tarea_card(tid, fecha, e.get("cliente", "—"), e.get("direccion", ""),
                                         e.get("telefono", ""), "Retiro", r.get("nota"), extra, "retiro",
                                         e.get("coordenadas", ""))))
        tareas.append({"id": tid, "tel": solo_digitos(e.get("telefono", "")), "fecha": fecha,
                       "tipo": "retiro", "hecha": False})
    return _seccion_tareas("📦 Retiros", cards, len(datos)), tareas


# ─────────────────────────────────────────────────────────────────────────────
# Geografía para la "Recomendación de hoy": deduce comuna + zona + un punto
# (lat,lng) por entrega. Todo offline (sin API, sin costo). Las coordenadas por
# comuna son CENTROS aproximados; sirven para agrupar y estimar minutos "~", no
# para navegar (para eso ya está el botón "Cómo llegar" de cada tarjeta).
# ─────────────────────────────────────────────────────────────────────────────

# comuna/sector -> (lat, lng, zona). Los sectores (Chicureo, Lo Pinto…) traen su
# propio punto pero comparten la zona de su comuna madre.
COMUNAS_GEO = {
    # Oriente
    "lo barnechea": (-33.353, -70.518, "oriente"),
    "las condes": (-33.409, -70.569, "oriente"),
    "vitacura": (-33.380, -70.575, "oriente"),
    "la reina": (-33.443, -70.537, "oriente"),
    "nunoa": (-33.456, -70.597, "oriente"),
    "providencia": (-33.430, -70.610, "oriente"),
    "penalolen": (-33.485, -70.545, "oriente"),
    "macul": (-33.485, -70.598, "oriente"),
    # Centro
    "santiago centro": (-33.445, -70.660, "centro"),
    "santiago": (-33.445, -70.660, "centro"),
    "independencia": (-33.417, -70.665, "centro"),
    "recoleta": (-33.414, -70.640, "centro"),
    "estacion central": (-33.452, -70.685, "centro"),
    "san miguel": (-33.497, -70.652, "centro"),
    "san joaquin": (-33.492, -70.628, "centro"),
    "pedro aguirre cerda": (-33.487, -70.673, "centro"),
    # Norte
    "colina": (-33.203, -70.676, "norte"),
    "chicureo": (-33.283, -70.667, "norte"),
    "lo pinto": (-33.262, -70.723, "norte"),
    "lampa": (-33.283, -70.883, "norte"),
    "til til": (-33.083, -70.930, "norte"),
    "quilicura": (-33.367, -70.729, "norte"),
    "huechuraba": (-33.370, -70.645, "norte"),
    "conchali": (-33.383, -70.675, "norte"),
    "renca": (-33.404, -70.726, "norte"),
    # Poniente
    "pudahuel": (-33.443, -70.760, "poniente"),
    "cerro navia": (-33.423, -70.735, "poniente"),
    "lo prado": (-33.443, -70.720, "poniente"),
    "maipu": (-33.510, -70.760, "poniente"),
    "cerrillos": (-33.495, -70.715, "poniente"),
    "curacavi": (-33.410, -71.140, "poniente"),
    # Sur-poniente rural
    "padre hurtado": (-33.573, -70.810, "surponiente"),
    "penaflor": (-33.610, -70.878, "surponiente"),
    "talagante": (-33.665, -70.928, "surponiente"),
    "el monte": (-33.677, -71.010, "surponiente"),
    "isla de maipo": (-33.752, -70.897, "surponiente"),
    "melipilla": (-33.688, -71.215, "surponiente"),
    "calera de tango": (-33.632, -70.782, "surponiente"),
    # Sur
    "san bernardo": (-33.592, -70.699, "sur"),
    "buin": (-33.732, -70.741, "sur"),
    "paine": (-33.808, -70.741, "sur"),
    "pirque": (-33.640, -70.548, "sur"),
    "puente alto": (-33.611, -70.575, "sur"),
    "la florida": (-33.552, -70.583, "sur"),
    "la pintana": (-33.583, -70.630, "sur"),
    "la granja": (-33.540, -70.625, "sur"),
    "el bosque": (-33.562, -70.675, "sur"),
    "la cisterna": (-33.537, -70.663, "sur"),
    "san ramon": (-33.535, -70.645, "sur"),
}

# Nombres bonitos (con tilde/Ñ) para las comunas cuya clave va normalizada.
COMUNA_LABEL = {
    "nunoa": "Ñuñoa", "penaflor": "Peñaflor", "conchali": "Conchalí",
    "curacavi": "Curacaví", "til til": "Til Til", "penalolen": "Peñalolén",
    "maipu": "Maipú", "estacion central": "Estación Central",
    "pedro aguirre cerda": "Pedro Aguirre Cerda", "san ramon": "San Ramón",
}

# zona -> (etiqueta legible, emoji, orden de recorrido sugerido)
ZONAS_INFO = {
    "oriente":     ("Oriente", "🌄", 1),
    "centro":      ("Centro", "🏙️", 2),
    "norte":       ("Norte", "🧭", 3),
    "poniente":    ("Poniente", "🌆", 4),
    "surponiente": ("Sur-poniente", "🌾", 5),
    "sur":         ("Sur", "🚜", 6),
    "otra":        ("Otra zona", "📍", 9),
}


def _norm_txt(s: str) -> str:
    """minúsculas y sin tildes, para comparar nombres de comuna."""
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# Comunas de más específicas/largas a menos, para preferir el sector (Chicureo)
# por sobre la comuna madre (Colina) cuando ambos aparecen en la dirección.
_COMUNAS_ORD = sorted(COMUNAS_GEO.keys(), key=len, reverse=True)
_COORD_RE = re.compile(r"@?(-?\d{1,2}\.\d{3,}),\s*(-?\d{1,3}\.\d{3,})")


def _match_comuna(texto: str) -> str:
    """Comuna conocida más específica (nombre más largo) contenida en `texto`."""
    for nombre in _COMUNAS_ORD:
        if nombre in texto:
            return nombre
    return ""


def derivar_geo(e: dict) -> dict:
    """Deduce {comuna, zona, lat, lng, aprox} de una entrega. Sin red, sin costo."""
    direccion = e.get("direccion", "") or ""
    dir_norm = _norm_txt(direccion)

    # 1) Comuna: en esta base va casi siempre justo antes de "Región Metropolitana".
    #    Miramos los últimos segmentos (de derecha a izquierda) antes de la región;
    #    así evitamos falsos positivos de nombres de calles/marcas (p.ej. "Cousiño
    #    Macul" en una dirección de Paine). Si falla, buscamos en toda la dirección.
    comuna_key = ""
    cabeza = dir_norm.split("region metropolitana")[0]
    segmentos = [s.strip() for s in cabeza.split(",") if s.strip()]
    for seg in reversed(segmentos[-3:]):
        comuna_key = _match_comuna(seg)
        if comuna_key:
            break
    if not comuna_key:
        comuna_key = _match_comuna(dir_norm)

    if comuna_key:
        clat, clng, zona = COMUNAS_GEO[comuna_key]
        comuna_label = COMUNA_LABEL.get(comuna_key, comuna_key.title())
    else:
        clat = clng = None
        zona = "otra"
        comuna_label = "Sin comuna"

    # 2) Punto exacto si lo hay: campo `coordenadas` o un @lat,lng en la dirección
    #    (links de Google/Waze). Si no, cae al centro de la comuna (aprox).
    lat = lng = None
    aprox = True
    coords = (e.get("coordenadas", "") or "").strip()
    m = _COORD_RE.search(coords) or _COORD_RE.search(direccion)
    if m:
        lat, lng, aprox = float(m.group(1)), float(m.group(2)), False
    elif clat is not None:
        lat, lng = clat, clng

    return {
        "comuna": comuna_label,
        "zona": zona,
        "lat": lat,
        "lng": lng,
        "aprox": aprox,
    }


def maps_query(e: dict) -> str:
    """Lo que se manda a Google Maps para NAVEGAR a esta entrega: coordenadas
    exactas si las hay; si no, la dirección real (sin los links pegados al final).
    Nunca el centro de la comuna: eso solo sirve para estimar cercanía en el panel."""
    coords = (e.get("coordenadas") or "").strip()
    if coords:
        return coords
    d = e.get("direccion") or ""
    for marca in ("http", "Waze", "Ubicación", "ubicación"):  # corta links pegados
        i = d.find(marca)
        if i != -1:
            d = d[:i]
    # Quita notas entre paréntesis: "(obra de construcción)", "(Condominio ...)",
    # "(frente al mall ...)". A Google le rompen la búsqueda.
    d = re.sub(r"\([^)]*\)", " ", d)
    d = d.replace("(", " ").replace(")", " ")  # paréntesis sueltos (de links cortados)
    # Si viene "Nombre del lugar — calle 123, comuna", quédate con el lado de la
    # dirección (el que trae número o comuna). Evita que el nombre de la obra/viña
    # confunda a Google (p.ej. "Viña Cousiño Macul" mandándolo a Macul).
    if "—" in d:
        izq, der = d.split("—", 1)
        if ("," in der) or re.search(r"\d", der):
            d = der
    d = re.sub(r"\s+", " ", d)
    d = re.sub(r"\s+,", ",", d)  # " ," -> ","
    d = d.strip().strip(".,;—- ").strip()
    return d


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
            f'{PROG_MARKUP}{CHEVRON}</h2>{tarjetas}</section>'
        )

    # Secciones agregadas (limpiezas / retiros) y sus tareas para el JS.
    limpiezas_sec, tareas_lim = seccion_limpiezas(entregas)
    retiros_sec, tareas_ret = seccion_retiros(entregas)
    tareas = tareas_lim + tareas_ret

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
            "pagada_at": e.get("pagada_at"),
            "tel": solo_digitos(e.get("telefono", "")),
            "banos": cantidad_banos(e),
            "tipo": "limpieza" if e.get("comision") is False else "bano",
            "es_servicio": e.get("comision") is False,
            "monto": (e.get("pago") or {}).get("monto") or 0,
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
            "tareas": tareas,
            "comprobantes": data.get("comprobantes", {}),
            # Geo por entrega (+ cliente + dirección real de navegación) + etiquetas de
            # zona, para la "Recomendación de hoy". `mapsq` = a dónde navega Maps (real);
            # lat/lng = centro de comuna, solo para estimar cercanía en el panel.
            "geo": {e.get("id", ""): {**derivar_geo(e), "cliente": e.get("cliente", ""),
                                      "mapsq": maps_query(e)}
                    for e in entregas},
            "zonas": {k: {"label": v[0], "emoji": v[1], "orden": v[2]}
                      for k, v in ZONAS_INFO.items()},
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")  # evita cerrar el <script> con datos
    config_script = f"<script>window.__APP__ = {config_json};</script>"

    # Botón para mostrar las entregas de días anteriores (ocultas por defecto vía JS).
    boton_anteriores = ('<div id="modo-titulo" class="modo-titulo" hidden></div>'
                        '<button id="toggle-anteriores" class="ver-anteriores" type="button" hidden></button>')

    # Recomendación de reparto de hoy (agrupa por zona; se rellena por JS en vivo).
    reco_block = '<div id="recomendacion-hoy" class="reco" hidden></div>'

    if secciones:
        vista_entregas = reco_block + boton_anteriores + "".join(secciones) + limpiezas_sec + retiros_sec
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
    <div class="sub"><span id="pend-count">{pendientes}</span> pendiente(s) · Actualizado {actualizado}</div>
    <div class="sub ganado" id="ganado-total"></div>
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
