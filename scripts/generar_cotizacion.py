#!/usr/bin/env python3
"""
Generador de cotizaciones formales - Destape Rápido

Uso:
    python generar_cotizacion.py <ruta-json-config> <ruta-salida-pdf>

El JSON de configuración define el cliente, ítems, condiciones y observaciones
extra. Los datos del emisor están hardcodeados (son siempre los mismos).

Mantiene el formato tradicional de cotización (encabezado, datos emisor/cliente,
tabla de ítems, subtotal/IVA/total, condiciones, observaciones), con un estilo
moderno: tipografía Avenir, paleta teal + ámbar y tablas limpias.

Ver SKILL.md para el schema completo del JSON.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    KeepTogether, HRFlowable,
)

# ============================================================
# DATOS POR DEFECTO DEL EMISOR (se pueden sobreescribir desde el JSON)
# ============================================================
EMISOR_DEFAULT = {
    "empresa": "Destape Rápido",
    "giro": "Servicios sanitarios y arriendo de baños químicos",
    "direccion": "Maipú, Región Metropolitana",
    "telefono": "+56 9 3647 0112",
    "web": "destaperapido.cl",
    "subtitulo_header": "Soluciones sanitarias profesionales · Región Metropolitana",
    "ubicacion_corta": "Maipú, RM",
}

# ============================================================
# PALETA DE COLORES — teal petróleo + acento ámbar (identidad propia)
# ============================================================
BRAND = colors.HexColor("#0F6E6E")        # teal petróleo — primario
BRAND_DARK = colors.HexColor("#0A4F4F")   # teal oscuro
BRAND_SOFT = colors.HexColor("#EAF4F2")   # teal muy claro — fondos
ACCENT = colors.HexColor("#E0A82E")       # ámbar cálido — acentos
ACCENT_SOFT = colors.HexColor("#FBF1DC")  # ámbar muy claro — avisos
GRAY = colors.HexColor("#5F6B6B")
GRAY_SOFT = colors.HexColor("#F5F7F7")
LINE = colors.HexColor("#D2DEDC")
DARK = colors.HexColor("#1E2A2A")

# Versiones hex (para <font color="..."> dentro de Paragraph)
HX_BRAND = "#0F6E6E"
HX_ACCENT = "#E0A82E"
HX_GRAY = "#5F6B6B"
HX_DARK = "#1E2A2A"

# ============================================================
# FUENTES — Avenir Next si está disponible (macOS); si no, Helvetica
# ============================================================
FONT = "Helvetica"
FONT_MED = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_HEAVY = "Helvetica-Bold"
FONT_IT = "Helvetica-Oblique"


def _register_fonts():
    global FONT, FONT_MED, FONT_BOLD, FONT_HEAVY, FONT_IT
    path = "/System/Library/Fonts/Avenir Next.ttc"
    if not Path(path).exists():
        return
    try:
        pdfmetrics.registerFont(TTFont("Avenir", path, subfontIndex=7))        # Regular
        pdfmetrics.registerFont(TTFont("Avenir-Med", path, subfontIndex=5))    # Medium
        pdfmetrics.registerFont(TTFont("Avenir-Demi", path, subfontIndex=2))   # DemiBold
        pdfmetrics.registerFont(TTFont("Avenir-Bold", path, subfontIndex=0))   # Bold
        pdfmetrics.registerFont(TTFont("Avenir-Heavy", path, subfontIndex=8))  # Heavy
        pdfmetrics.registerFont(TTFont("Avenir-It", path, subfontIndex=4))     # Italic
        registerFontFamily("Avenir", normal="Avenir", bold="Avenir-Demi",
                            italic="Avenir-It", boldItalic="Avenir-Bold")
        FONT = "Avenir"
        FONT_MED = "Avenir-Med"
        FONT_BOLD = "Avenir-Demi"
        FONT_HEAVY = "Avenir-Heavy"
        FONT_IT = "Avenir-It"
    except Exception:
        pass  # se queda con Helvetica


_register_fonts()

# ============================================================
# UTILIDADES
# ============================================================
MESES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def fecha_larga(d: date) -> str:
    return f"{d.day:02d} de {MESES[d.month]} de {d.year}"


def clp(n: int, signo: str = "") -> str:
    s = f"${n:,.0f}".replace(",", ".")
    return f"{signo}{s}" if signo else s


def section_heading(texto: str):
    """Título de sección teal + regla ámbar fina."""
    st = ParagraphStyle("section", fontName=FONT_BOLD, fontSize=11, leading=14,
                        textColor=BRAND, spaceBefore=15, spaceAfter=5)
    return [
        Paragraph(texto, st),
        HRFlowable(width="100%", thickness=1.0, color=ACCENT,
                   spaceBefore=0, spaceAfter=8),
    ]


# ============================================================
# HEADER Y FOOTER
# ============================================================
def make_draw_header_footer(emisor: dict):
    def draw(canv, doc):
        canv.saveState()
        w, h = letter

        # --- Encabezado: marca a la izquierda, contacto a la derecha ---
        canv.setFillColor(BRAND)
        canv.setFont(FONT_HEAVY, 18)
        canv.drawString(20 * mm, h - 16 * mm, emisor["empresa"].upper())
        subt = emisor.get("subtitulo_header")
        if subt:
            canv.setFillColor(GRAY)
            canv.setFont(FONT, 8.5)
            canv.drawString(20 * mm, h - 21 * mm, subt)

        canv.setFillColor(DARK)
        canv.setFont(FONT, 8.5)
        right_lines = [
            emisor.get("telefono"), emisor.get("web"),
            emisor.get("ubicacion_corta") or emisor.get("direccion"),
        ]
        right_lines = [l for l in right_lines if l]
        for idx, line in enumerate(right_lines):
            canv.drawRightString(w - 20 * mm, h - (15 + idx * 4.2) * mm, line)

        # Regla teal + acento ámbar corto
        canv.setStrokeColor(BRAND)
        canv.setLineWidth(1.4)
        canv.line(20 * mm, h - 26 * mm, w - 20 * mm, h - 26 * mm)
        canv.setStrokeColor(ACCENT)
        canv.setLineWidth(1.4)
        canv.line(20 * mm, h - 26.9 * mm, 62 * mm, h - 26.9 * mm)

        # --- Footer ---
        canv.setStrokeColor(BRAND)
        canv.setLineWidth(0.8)
        canv.line(20 * mm, 18 * mm, w - 20 * mm, 18 * mm)
        canv.setStrokeColor(ACCENT)
        canv.setLineWidth(0.8)
        canv.line(20 * mm, 18 * mm, 42 * mm, 18 * mm)

        canv.setFillColor(GRAY)
        canv.setFont(FONT, 7.5)
        footer_parts = [
            emisor.get("empresa"), emisor.get("direccion"),
            emisor.get("telefono"), emisor.get("web"),
        ]
        footer = "   ·   ".join(p for p in footer_parts if p)
        canv.drawString(20 * mm, 14 * mm, footer)
        canv.drawRightString(w - 20 * mm, 14 * mm, f"Página {canv.getPageNumber()}")

        canv.restoreState()
    return draw


# ============================================================
# GENERADOR PRINCIPAL
# ============================================================
def generar(config: dict, output_path: str) -> None:
    emisor = {**EMISOR_DEFAULT, **(config.get("emisor") or {})}
    solo_neto = bool(config.get("solo_neto", False))

    hoy = date.fromisoformat(config["fecha_emision"]) if config.get("fecha_emision") else date.today()
    fecha_str = fecha_larga(hoy)
    validez_str = fecha_larga(hoy + timedelta(days=15))

    num_cot = config.get("numero_cotizacion") or \
        f"N° {hoy.year}-{hoy.month:02d}{hoy.day:02d}-001"
    subtitulo = config.get("subtitulo", "Servicios sanitarios y baños químicos")

    # ----- Estilos -----
    st_body = ParagraphStyle("body", fontName=FONT, fontSize=9, leading=12.5, textColor=DARK)
    st_small = ParagraphStyle("small", parent=st_body, fontSize=8.5, leading=12)
    st_lbl = ParagraphStyle("lbl", parent=st_small, fontName=FONT_BOLD, textColor=BRAND)
    st_title = ParagraphStyle("title", fontName=FONT_HEAVY, fontSize=25, leading=28,
                              textColor=BRAND, alignment=TA_LEFT, spaceAfter=2)
    st_subtitle = ParagraphStyle("sub", parent=st_body, fontSize=10.5, textColor=GRAY,
                                 spaceAfter=2)
    st_white = ParagraphStyle("white", fontName=FONT_BOLD, fontSize=9, textColor=colors.white)
    st_white_center = ParagraphStyle("whitec", parent=st_white, alignment=TA_CENTER)
    st_total_lbl = ParagraphStyle("totlbl", fontName=FONT_BOLD, fontSize=10,
                                  textColor=colors.white, alignment=TA_RIGHT)
    st_total_val = ParagraphStyle("totval", fontName=FONT_HEAVY, fontSize=12.5,
                                  textColor=colors.white, alignment=TA_RIGHT)
    st_bullet = ParagraphStyle("bullet", parent=st_body, leftIndent=13,
                               bulletIndent=0, spaceAfter=3)

    # ----- Documento -----
    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=34 * mm, bottomMargin=22 * mm,
        title=f"Cotización {num_cot} - {emisor['empresa']}",
        author=emisor["empresa"],
    )
    story = []

    # ----- Título -----
    story.append(Paragraph("COTIZACIÓN", st_title))
    story.append(Paragraph(subtitulo, st_subtitle))
    story.append(Spacer(1, 6))

    # ----- Meta (N°, fecha, validez) -----
    def meta_cell(label, value):
        return Paragraph(
            f'<font name="{FONT_BOLD}" size="7.5" color="{HX_GRAY}">{label.upper()}</font><br/>'
            f'<font name="{FONT_MED}" size="10" color="{HX_DARK}">{value}</font>',
            ParagraphStyle("metacell", parent=st_small, leading=13))
    meta_tbl = Table([[
        meta_cell("N° Cotización", num_cot),
        meta_cell("Fecha de emisión", fecha_str),
        meta_cell("Válida hasta", validez_str),
    ]], colWidths=[56.7 * mm, 56.7 * mm, 56.6 * mm])
    meta_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_SOFT),
        ("LINEAFTER", (0, 0), (1, 0), 1.0, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 10))

    # ----- Emisor (+ Cliente si existe) -----
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
        f'<font name="{FONT_BOLD}" color="{HX_BRAND}">{label}:</font> {value}'
        for label, value in emisor_lines if value
    )
    emisor_para = Paragraph(emisor_html, st_small)

    cliente_cfg = config.get("cliente")
    if cliente_cfg:
        cliente_titulo = cliente_cfg.get("titulo", "CLIENTE")
        cliente_html = "<br/>".join(
            f'<font name="{FONT_BOLD}" color="{HX_BRAND}">{label}:</font> {value}'
            for label, value in cliente_cfg.get("campos", [])
        )
        cliente_para = Paragraph(cliente_html, st_small)
        partes_tbl = Table(
            [[Paragraph("EMISOR", st_white), Paragraph(cliente_titulo, st_white)],
             [emisor_para, cliente_para]],
            colWidths=[85 * mm, 85 * mm],
        )
    else:
        partes_tbl = Table(
            [[Paragraph("EMISOR", st_white)], [emisor_para]],
            colWidths=[170 * mm],
        )
    partes_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("BACKGROUND", (0, 1), (-1, 1), GRAY_SOFT),
        ("LINEBELOW", (0, 1), (-1, 1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 1), (-1, 1), 8),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 9),
    ]))
    story.append(partes_tbl)

    # ----- Detalle del servicio -----
    story += section_heading("DETALLE DEL SERVICIO")
    rows = [[
        Paragraph("N°", st_white_center),
        Paragraph("Descripción", st_white),
        Paragraph("Cant.", st_white_center),
        Paragraph("Valor unitario", st_white_center),
        Paragraph("Subtotal", st_white_center),
    ]]
    total_neto = 0
    for i, item in enumerate(config.get("items", []), start=1):
        titulo = item.get("descripcion_titulo", "")
        bullets = item.get("descripcion_bullets", [])
        cant = item.get("cantidad", 1)
        valor_unit = item.get("valor_unitario_neto", 0)
        subtotal = cant * valor_unit
        total_neto += subtotal

        desc_html = f'<font name="{FONT_BOLD}" color="{HX_DARK}">{titulo}</font>'
        for b in bullets:
            desc_html += f'<br/><font color="{HX_GRAY}">{b}</font>'
        rows.append([
            Paragraph(str(i), st_small),
            Paragraph(desc_html, st_small),
            Paragraph(str(cant), st_small),
            Paragraph(clp(valor_unit), st_small),
            Paragraph(clp(subtotal), st_small),
        ])

    detalle_tbl = Table(rows, colWidths=[13 * mm, 88 * mm, 15 * mm, 27 * mm, 27 * mm])
    detalle_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (4, -1), "CENTER"),
        ("ALIGN", (3, 1), (4, -1), "RIGHT"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(detalle_tbl)

    # ----- Totales (neto / IVA / total) — el TOTAL es el dato protagonista -----
    if solo_neto:
        tot_data = [["", Paragraph("TOTAL NETO", st_total_lbl),
                     Paragraph(clp(total_neto), st_total_val)]]
        tot_tbl = Table(tot_data, colWidths=[108 * mm, 31 * mm, 31 * mm])
        tot_tbl.setStyle(TableStyle([
            ("BACKGROUND", (1, 0), (2, 0), BRAND),
            ("ALIGN", (1, 0), (2, 0), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (1, 0), (2, 0), 10),
            ("BOTTOMPADDING", (1, 0), (2, 0), 10),
        ]))
    else:
        iva = round(total_neto * 0.19)
        total = total_neto + iva
        tot_data = [
            ["", Paragraph("Valor neto", st_small), Paragraph(clp(total_neto), st_small)],
            ["", Paragraph("IVA (19%)", st_small), Paragraph(clp(iva), st_small)],
            ["", Paragraph("TOTAL · IVA incluido", st_total_lbl),
             Paragraph(clp(total), st_total_val)],
        ]
        tot_tbl = Table(tot_data, colWidths=[108 * mm, 31 * mm, 31 * mm])
        tot_tbl.setStyle(TableStyle([
            ("BACKGROUND", (1, 0), (2, 1), BRAND_SOFT),
            ("BACKGROUND", (1, 2), (2, 2), BRAND),
            ("LINEBELOW", (1, 0), (2, 1), 0.4, LINE),
            ("ALIGN", (1, 0), (2, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (1, 0), (2, 1), 6),
            ("BOTTOMPADDING", (1, 0), (2, 1), 6),
            ("TOPPADDING", (1, 2), (2, 2), 10),
            ("BOTTOMPADDING", (1, 2), (2, 2), 10),
        ]))
    story.append(tot_tbl)

    # ----- Condiciones comerciales -----
    story += section_heading("CONDICIONES COMERCIALES")
    valores_txt = (
        "Valores netos."
        if solo_neto
        else "Valores netos; se les suma IVA (19%) al total."
    )
    condiciones_default = [
        ("Forma de pago", "Transferencia electrónica o depósito bancario."),
        ("Facturación", "Electrónica, a la razón social que indique el cliente."),
        ("Entrega", "Coordinada dentro de 24 a 48 horas hábiles tras la aceptación."),
        ("Mantención", "Incluida según servicio contratado."),
        ("Cobertura", "Región Metropolitana. Zonas de difícil acceso pueden implicar recargo."),
        ("Valores", valores_txt),
    ]
    if "condiciones" in config:
        condiciones = list(config["condiciones"])
    else:
        condiciones = condiciones_default + list(config.get("condiciones_extra", []))

    cond_data = [
        [Paragraph(f'<font name="{FONT_BOLD}" color="{HX_BRAND}">{k}</font>', st_small),
         Paragraph(v, st_small)]
        for k, v in condiciones
    ]
    cond_tbl = Table(cond_data, colWidths=[42 * mm, 128 * mm])
    cond_tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [GRAY_SOFT, colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(cond_tbl)

    # ----- Datos para transferencia (opcional) -----
    datos_tx = config.get("datos_transferencia")
    if datos_tx:
        story += section_heading("DATOS PARA TRANSFERENCIA")
        tx_data = [
            [Paragraph(f'<font name="{FONT_BOLD}" color="{HX_BRAND}">{k}</font>', st_small),
             Paragraph(v, st_small)]
            for k, v in datos_tx.get("campos", [])
        ]
        tx_tbl = Table(tx_data, colWidths=[42 * mm, 128 * mm])
        tx_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BRAND_SOFT),
            ("BOX", (0, 0), (-1, -1), 0.4, BRAND),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(KeepTogether(tx_tbl))

    # ----- Observaciones -----
    story += section_heading("OBSERVACIONES")
    observaciones_default = [
        "El cliente deberá asegurar un lugar estable y accesible para posicionar el baño químico.",
        "Daños por uso indebido, vandalismo o fuerza mayor se cobran aparte según evaluación.",
        "Los precios no incluyen traslados fuera de la Región Metropolitana.",
        "Esta cotización no constituye reserva de la(s) unidad(es) hasta su aceptación formal.",
    ]
    if "observaciones" in config:
        observaciones = list(config["observaciones"])
    else:
        observaciones = observaciones_default + list(config.get("observaciones_extra", []))
    for o in observaciones:
        story.append(Paragraph(f'<font color="{HX_ACCENT}">●</font>&nbsp; {o}', st_bullet))

    # ----- Cómo aceptar (sin firmas: aceptación respondiendo el correo) -----
    story.append(Spacer(1, 16))
    st_conf_title = ParagraphStyle("conf_title", parent=st_body,
        fontName=FONT_BOLD, fontSize=10.5, textColor=BRAND_DARK, spaceAfter=3)
    conf_tbl = Table([
        [Paragraph("¿Cómo aceptar esta cotización?", st_conf_title)],
        [Paragraph(
            "Para confirmar el servicio basta con <b>responder este correo</b> "
            "indicando su conformidad, o bien <b>si ya lo coordinamos por WhatsApp</b>, "
            "queda igualmente confirmado. No es necesario firmar ni imprimir el documento. "
            "Apenas tengamos su confirmación, coordinamos la entrega.", st_small)],
    ], colWidths=[170 * mm])
    conf_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ACCENT_SOFT),
        ("LINEABOVE", (0, 0), (-1, 0), 2.0, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (0, 0), 10),
        ("BOTTOMPADDING", (0, 0), (0, 0), 2),
        ("TOPPADDING", (0, 1), (0, 1), 0),
        ("BOTTOMPADDING", (0, 1), (0, 1), 10),
    ]))
    story.append(KeepTogether(conf_tbl))

    story.append(Spacer(1, 12))
    thanks = "<i>Gracias por preferir Destape Rápido.</i>"
    if emisor.get("telefono"):
        thanks = ("<i>Gracias por preferir Destape Rápido. Cualquier consulta, "
                  f"escríbanos o llámenos al {emisor['telefono']}.</i>")
    story.append(Paragraph(thanks, ParagraphStyle(
        "thanks", parent=st_small, alignment=TA_CENTER, textColor=GRAY)))

    # ----- Build -----
    draw_fn = make_draw_header_footer(emisor)
    doc.build(story, onFirstPage=draw_fn, onLaterPages=draw_fn)


# ============================================================
# ENTRADA CLI
# ============================================================
def main():
    if len(sys.argv) != 3:
        print("Uso: python generar_cotizacion.py <config.json> <salida.pdf>",
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
