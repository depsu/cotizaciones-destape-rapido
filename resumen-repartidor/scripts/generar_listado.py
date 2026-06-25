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
    <details class="card">
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
      </summary>
      <div class="detalle">
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


def construir_html(data: dict) -> str:
    entregas = data.get("entregas", [])
    # Ordenar por fecha y agrupar.
    entregas_ordenadas = sorted(entregas, key=lambda e: (e.get("fecha", ""), e.get("hora", "")))

    grupos: dict[str, list] = {}
    for e in entregas_ordenadas:
        grupos.setdefault(e.get("fecha", ""), []).append(e)

    pendientes = sum(1 for e in entregas if e.get("estado", "pendiente") != "entregado")

    secciones = []
    for fecha, items in grupos.items():
        tarjetas = "".join(tarjeta(e) for e in items)
        secciones.append(
            f'<section><h2 class="fecha-titulo">{esc(encabezado_fecha(fecha))}'
            f'<span class="conteo">{len(items)}</span></h2>{tarjetas}</section>'
        )

    cuerpo = "".join(secciones) if secciones else '<p class="vacio">No hay entregas cargadas.</p>'
    actualizado = date.today().strftime("%d/%m/%Y")

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
  footer {{ text-align:center; color:var(--gris); font-size:12px; padding:24px 16px 40px; }}
</style>
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
