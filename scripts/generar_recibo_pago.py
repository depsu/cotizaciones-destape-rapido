#!/usr/bin/env python3
"""
Generador de comprobantes de pago recibido - Destape Rápido

Uso:
    python generar_recibo_pago.py <ruta-json-config> <ruta-salida-pdf>

Genera un PDF formal "RECIBO DE PAGO" / "COMPROBANTE DE PAGO RECIBIDO"
con el mismo estilo visual de las cotizaciones (paleta azul, Helvetica).
"""
import json
import sys
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    KeepTogether, HRFlowable,
)

# Datos por defecto del emisor
EMISOR_DEFAULT = {
    "empresa": "Destape Rápido",
    "giro": "Servicios sanitarios y arriendo de baños químicos",
    "direccion": "Maipú, Región Metropolitana",
    "telefono": "+56 9 3647 0112",
    "web": "destaperapido.cl",
    "subtitulo_header": "Soluciones sanitarias profesionales  ·  Región Metropolitana",
    "ubicacion_corta": "Maipú, RM",
}

# Paleta
BRAND = colors.HexColor("#1F5AA8")
BRAND_SOFT = colors.HexColor("#E8F0FB")
GRAY = colors.HexColor("#666666")
GRAY_SOFT = colors.HexColor("#F4F4F4")
LINE = colors.HexColor("#BFBFBF")
DARK = colors.HexColor("#1F1F1F")
ACCENT = colors.HexColor("#0E8F5E")
ACCENT_SOFT = colors.HexColor("#E5F5EE")

MESES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def fecha_larga(d: date) -> str:
    return f"{d.day:02d} de {MESES[d.month]} de {d.year}"


def clp(n: int) -> str:
    return f"${n:,.0f}".replace(",", ".")


def numero_a_palabras(n: int) -> str:
    """Convierte un entero (0..999.999.999) a palabras en español, en mayúsculas."""
    if n == 0:
        return "CERO"

    UNIDADES = ["", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE",
                "DIEZ", "ONCE", "DOCE", "TRECE", "CATORCE", "QUINCE", "DIECISÉIS",
                "DIECISIETE", "DIECIOCHO", "DIECINUEVE", "VEINTE"]
    DECENAS = ["", "", "VEINTI", "TREINTA", "CUARENTA", "CINCUENTA",
               "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
    CENTENAS = ["", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS",
                "QUINIENTOS", "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS"]

    def _hasta_999(num: int) -> str:
        if num == 0:
            return ""
        if num == 100:
            return "CIEN"
        partes = []
        c = num // 100
        resto = num % 100
        if c > 0:
            partes.append(CENTENAS[c])
        if resto <= 20:
            if resto > 0:
                partes.append(UNIDADES[resto])
        else:
            d = resto // 10
            u = resto % 10
            if d == 2:
                partes.append("VEINTI" + (UNIDADES[u] if u > 0 else ""))
            else:
                if u == 0:
                    partes.append(DECENAS[d])
                else:
                    partes.append(f"{DECENAS[d]} Y {UNIDADES[u]}")
        return " ".join(p for p in partes if p)

    millones = n // 1_000_000
    miles = (n % 1_000_000) // 1000
    resto = n % 1000

    salida = []
    if millones > 0:
        if millones == 1:
            salida.append("UN MILLÓN")
        else:
            salida.append(f"{_hasta_999(millones)} MILLONES")
    if miles > 0:
        if miles == 1:
            salida.append("MIL")
        else:
            salida.append(f"{_hasta_999(miles)} MIL")
    if resto > 0:
        salida.append(_hasta_999(resto))

    return " ".join(salida).strip()


# Header / Footer (igual que cotización)
def make_draw_header_footer(emisor: dict):
    def draw_header_footer(canv, doc):
        canv.saveState()
        w, h = letter

        canv.setFillColor(BRAND)
        canv.setFont("Helvetica-Bold", 18)
        canv.drawString(20 * mm, h - 18 * mm, emisor["empresa"].upper())

        subt = emisor.get("subtitulo_header")
        if subt:
            canv.setFillColor(GRAY)
            canv.setFont("Helvetica-Oblique", 8.5)
            canv.drawString(20 * mm, h - 23 * mm, subt)

        canv.setFillColor(DARK)
        canv.setFont("Helvetica", 8.5)
        right_lines = [
            emisor.get("telefono"),
            emisor.get("web"),
            emisor.get("ubicacion_corta") or emisor.get("direccion"),
        ]
        right_lines = [l for l in right_lines if l]
        for idx, line in enumerate(right_lines):
            canv.drawRightString(w - 20 * mm, h - (18 + idx * 4) * mm, line)

        canv.setStrokeColor(BRAND)
        canv.setLineWidth(1.2)
        canv.line(20 * mm, h - 30 * mm, w - 20 * mm, h - 30 * mm)

        canv.setStrokeColor(BRAND)
        canv.setLineWidth(0.8)
        canv.line(20 * mm, 18 * mm, w - 20 * mm, 18 * mm)

        canv.setFillColor(GRAY)
        canv.setFont("Helvetica", 7.5)
        footer_parts = [
            emisor.get("empresa"),
            emisor.get("direccion"),
            emisor.get("telefono"),
            emisor.get("web"),
        ]
        footer = "  ·  ".join(p for p in footer_parts if p)
        canv.drawString(20 * mm, 14 * mm, footer)
        canv.drawRightString(w - 20 * mm, 14 * mm, f"Página {canv.getPageNumber()}")

        canv.restoreState()
    return draw_header_footer


def generar(config: dict, output_path: str) -> None:
    emisor = {**EMISOR_DEFAULT, **(config.get("emisor") or {})}

    hoy = date.today()
    fecha_str = fecha_larga(hoy)

    num_recibo = config.get("numero_recibo") or \
        f"N° {hoy.year}-{hoy.month:02d}{hoy.day:02d}-001"
    subtitulo = config.get("subtitulo", "Comprobante de pago recibido")

    monto = int(config.get("monto", 0))
    moneda = config.get("moneda", "Pesos chilenos (CLP)")
    metodo_pago = config.get("metodo_pago", "Transferencia electrónica")
    fecha_pago = config.get("fecha_pago", fecha_str)
    referencia = config.get("referencia_pago", "")
    concepto = config.get("concepto", "Servicio de arriendo de baño químico")

    # Estilos
    styles = getSampleStyleSheet()
    st_normal = ParagraphStyle("normal", parent=styles["Normal"],
        fontName="Helvetica", fontSize=9.5, leading=13, textColor=DARK)
    st_small = ParagraphStyle("small", parent=st_normal, fontSize=8.5, leading=11)
    st_small_bold = ParagraphStyle("small_bold", parent=st_small,
        fontName="Helvetica-Bold")
    st_title = ParagraphStyle("title", parent=styles["Title"],
        fontName="Helvetica-Bold", fontSize=26, leading=30,
        textColor=BRAND, alignment=TA_LEFT, spaceAfter=2)
    st_subtitle = ParagraphStyle("sub", parent=st_normal,
        fontSize=10, textColor=GRAY, alignment=TA_LEFT, spaceAfter=4)
    st_section = ParagraphStyle("section", parent=st_normal,
        fontName="Helvetica-Bold", fontSize=11, leading=14,
        textColor=BRAND, spaceBefore=14, spaceAfter=6)
    st_white_bold = ParagraphStyle("white_bold", parent=st_normal,
        fontName="Helvetica-Bold", fontSize=9.5, textColor=colors.white)
    st_amount_big = ParagraphStyle("amount_big", parent=st_normal,
        fontName="Helvetica-Bold", fontSize=22, leading=26,
        textColor=ACCENT, alignment=TA_CENTER)
    st_amount_label = ParagraphStyle("amount_label", parent=st_small,
        textColor=GRAY, alignment=TA_CENTER)
    st_amount_words = ParagraphStyle("amount_words", parent=st_small,
        fontName="Helvetica-Oblique", textColor=DARK, alignment=TA_CENTER)
    st_bullet = ParagraphStyle("bullet", parent=st_normal,
        leftIndent=12, bulletIndent=0, spaceAfter=2)

    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=35 * mm, bottomMargin=22 * mm,
        title=f"Recibo de pago {num_recibo} - {emisor['empresa']}",
        author=emisor["empresa"],
    )
    story = []

    # Título
    story.append(Paragraph("RECIBO DE PAGO", st_title))
    story.append(Paragraph(subtitulo, st_subtitle))
    story.append(Spacer(1, 4))

    # Meta
    meta_data = [
        [Paragraph("N° Recibo", st_small_bold), Paragraph(num_recibo, st_small),
         Paragraph("Fecha emisión", st_small_bold), Paragraph(fecha_str, st_small)],
        [Paragraph("Fecha de pago", st_small_bold), Paragraph(fecha_pago, st_small),
         Paragraph("Moneda", st_small_bold), Paragraph(moneda, st_small)],
    ]
    meta_tbl = Table(meta_data, colWidths=[32 * mm, 50 * mm, 32 * mm, 56 * mm])
    meta_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), BRAND_SOFT),
        ("BACKGROUND", (2, 0), (2, -1), BRAND_SOFT),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 10))

    # Emisor + cliente (pagador)
    emisor_lines = [
        ("Empresa", emisor.get("empresa")),
        ("Razón social", emisor.get("razon_social")),
        ("RUT", emisor.get("rut")),
        ("Giro", emisor.get("giro")),
        ("Dirección", emisor.get("direccion")),
        ("Teléfono", emisor.get("telefono")),
        ("Sitio web", emisor.get("web")),
    ]
    emisor_html = "<br/>".join(
        f"<b>{label}:</b> {value}" for label, value in emisor_lines if value
    )
    emisor_para = Paragraph(emisor_html, st_small)

    cliente_cfg = config.get("cliente")
    if cliente_cfg:
        cliente_titulo = cliente_cfg.get("titulo", "PAGADOR")
        cliente_campos = cliente_cfg.get("campos", [])
        cliente_html = "<br/>".join(
            f"<b>{label}:</b> {value}" for label, value in cliente_campos
        )
        cliente_para = Paragraph(cliente_html, st_small)

        partes_tbl = Table(
            [
                [Paragraph("RECEPTOR DEL PAGO", st_white_bold),
                 Paragraph(cliente_titulo, st_white_bold)],
                [emisor_para, cliente_para],
            ],
            colWidths=[85 * mm, 85 * mm],
        )
    else:
        partes_tbl = Table(
            [
                [Paragraph("RECEPTOR DEL PAGO", st_white_bold)],
                [emisor_para],
            ],
            colWidths=[170 * mm],
        )

    partes_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(partes_tbl)

    # Bloque destacado del monto recibido
    story.append(Spacer(1, 10))
    monto_palabras = numero_a_palabras(monto) + " PESOS CHILENOS"
    monto_block = Table(
        [
            [Paragraph("MONTO RECIBIDO", st_amount_label)],
            [Paragraph(clp(monto), st_amount_big)],
            [Paragraph(f"({monto_palabras})", st_amount_words)],
        ],
        colWidths=[170 * mm],
    )
    monto_block.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ACCENT_SOFT),
        ("BOX", (0, 0), (-1, -1), 1.0, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (0, 0), 8),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
    ]))
    story.append(monto_block)

    # Detalle del concepto
    story.append(Paragraph("DETALLE DEL PAGO", st_section))
    story.append(HRFlowable(width="100%", thickness=0.8, color=BRAND,
                            spaceBefore=0, spaceAfter=6))

    detalle_filas = [
        ["Concepto", concepto],
        ["Método de pago", metodo_pago],
        ["Fecha de pago", fecha_pago],
    ]
    if referencia:
        detalle_filas.append(["Referencia / N° operación", referencia])

    items = config.get("items", [])
    if items:
        items_html_parts = []
        for it in items:
            titulo = it.get("descripcion_titulo", "")
            bullets = it.get("descripcion_bullets", [])
            cant = it.get("cantidad")
            linea_items = f"<b>{titulo}</b>"
            if cant:
                linea_items += f" — Cantidad: {cant}"
            if bullets:
                linea_items += "<br/>" + "<br/>".join(f"• {b}" for b in bullets)
            items_html_parts.append(linea_items)
        detalle_filas.append([
            "Servicio prestado",
            "<br/><br/>".join(items_html_parts),
        ])

    periodo = config.get("periodo")
    if periodo:
        detalle_filas.append(["Período del servicio", periodo])

    direccion_servicio = config.get("direccion_servicio")
    if direccion_servicio:
        detalle_filas.append(["Lugar de instalación", direccion_servicio])

    estado = config.get("estado_pago", "PAGADO / RECIBIDO")
    detalle_filas.append(["Estado", f"<b><font color='#0E8F5E'>{estado}</font></b>"])

    det_data = [
        [Paragraph(f"<b>{k}</b>", st_small), Paragraph(v, st_small)]
        for k, v in detalle_filas
    ]
    det_tbl = Table(det_data, colWidths=[45 * mm, 125 * mm])
    det_tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [GRAY_SOFT, colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, LINE),
        ("BOX", (0, 0), (-1, -1), 0.4, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(det_tbl)

    # Observaciones
    if config.get("observaciones"):
        story.append(Paragraph("OBSERVACIONES", st_section))
        story.append(HRFlowable(width="100%", thickness=0.8, color=BRAND,
                                spaceBefore=0, spaceAfter=6))
        for o in config["observaciones"]:
            story.append(Paragraph(f"• {o}", st_bullet))

    # Declaración formal
    story.append(Paragraph("DECLARACIÓN", st_section))
    story.append(HRFlowable(width="100%", thickness=0.8, color=BRAND,
                            spaceBefore=0, spaceAfter=6))
    pagador_nombre = ""
    if cliente_cfg:
        for label, value in cliente_cfg.get("campos", []):
            if label.lower() in ("razón social", "razon social", "nombre", "cliente"):
                pagador_nombre = value
                break
    pagador_txt = f" de parte de <b>{pagador_nombre}</b>" if pagador_nombre else ""
    declaracion = (
        f"Por el presente documento, <b>{emisor['empresa']}</b> declara haber recibido "
        f"conforme la suma de <b>{clp(monto)}</b> ({monto_palabras}){pagador_txt}, "
        f"correspondiente al concepto detallado anteriormente. "
        f"Este recibo se emite con fecha {fecha_str} y constituye constancia "
        f"del pago efectuado."
    )
    story.append(Paragraph(declaracion, st_normal))

    # Firma
    story.append(Spacer(1, 26))
    firma_emisor = Paragraph(
        "_________________________________<br/>"
        f"<b>Por {emisor['empresa']}</b><br/>"
        "Nombre: ____________________<br/>"
        "Cargo: ______________________<br/>"
        f"Fecha: {fecha_str}",
        st_small,
    )
    firma_tbl = Table([[firma_emisor]], colWidths=[90 * mm])
    firma_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(KeepTogether(firma_tbl))

    story.append(Spacer(1, 14))
    if emisor.get("telefono"):
        thanks = (
            "<i>Gracias por confiar en nuestros servicios. Para cualquier consulta, "
            f"contáctenos al {emisor['telefono']}.</i>"
        )
    else:
        thanks = "<i>Gracias por confiar en nuestros servicios.</i>"
    story.append(Paragraph(
        thanks,
        ParagraphStyle("thanks", parent=st_small, alignment=TA_CENTER, textColor=GRAY),
    ))

    draw_fn = make_draw_header_footer(emisor)
    doc.build(story, onFirstPage=draw_fn, onLaterPages=draw_fn)


def main():
    if len(sys.argv) != 3:
        print("Uso: python generar_recibo_pago.py <config.json> <salida.pdf>",
              file=sys.stderr)
        sys.exit(1)

    config_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not config_path.exists():
        print(f"Error: no existe el archivo {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    generar(config, str(output_path))
    print(f"OK: {output_path}")


if __name__ == "__main__":
    main()
