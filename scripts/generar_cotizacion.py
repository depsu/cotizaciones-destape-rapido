#!/usr/bin/env python3
"""
Generador de cotizaciones formales - Destape Rápido

Uso:
    python generar_cotizacion.py <ruta-json-config> <ruta-salida-pdf>

El JSON de configuración define el cliente, ítems, condiciones y observaciones
extra. Los datos del emisor están hardcodeados (son siempre los mismos).

Ver SKILL.md para el schema completo del JSON.
"""
import json
import sys
from datetime import date, timedelta
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

# ============================================================
# DATOS POR DEFECTO DEL EMISOR (se pueden sobreescribir desde el JSON)
# ============================================================
EMISOR_DEFAULT = {
    "empresa": "Destape Rápido",
    "giro": "Servicios sanitarios y arriendo de baños químicos",
    "direccion": "Maipú, Región Metropolitana",
    "telefono": "+56 9 3647 0112",
    "web": "destaperapido.cl",
    "subtitulo_header": "Soluciones sanitarias profesionales  ·  Región Metropolitana",
    "ubicacion_corta": "Maipú, RM",
}

# ============================================================
# PALETA DE COLORES
# ============================================================
BRAND = colors.HexColor("#1F5AA8")
BRAND_SOFT = colors.HexColor("#E8F0FB")
GRAY = colors.HexColor("#666666")
GRAY_SOFT = colors.HexColor("#F4F4F4")
LINE = colors.HexColor("#BFBFBF")
DARK = colors.HexColor("#1F1F1F")
ACCENT = colors.HexColor("#0E8F5E")

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


# ============================================================
# HEADER Y FOOTER
# ============================================================
def make_draw_header_footer(emisor: dict):
    def draw_header_footer(canv, doc):
        canv.saveState()
        w, h = letter

        # --- Header ---
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
        # Lado derecho del header: hasta 3 líneas (teléfono, web, ubicación corta)
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

        # --- Footer ---
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


# ============================================================
# GENERADOR PRINCIPAL
# ============================================================
def generar(config: dict, output_path: str) -> None:
    # ----- Emisor (default + override desde config) -----
    emisor = {**EMISOR_DEFAULT, **(config.get("emisor") or {})}
    solo_neto = bool(config.get("solo_neto", False))

    # ----- Fechas y numeración -----
    # fecha_emision opcional en formato ISO (YYYY-MM-DD) para regenerar cotizaciones antiguas
    hoy = date.fromisoformat(config["fecha_emision"]) if config.get("fecha_emision") else date.today()
    fecha_str = fecha_larga(hoy)
    validez_date = hoy + timedelta(days=15)
    validez_str = fecha_larga(validez_date)

    num_cot = config.get("numero_cotizacion") or \
        f"N° {hoy.year}-{hoy.month:02d}{hoy.day:02d}-001"
    subtitulo = config.get("subtitulo", "Servicios sanitarios y baños químicos")

    # ----- Estilos -----
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
    st_white_bold_center = ParagraphStyle("white_bold_center",
        parent=st_white_bold, alignment=TA_CENTER)
    st_bullet = ParagraphStyle("bullet", parent=st_normal,
        leftIndent=12, bulletIndent=0, spaceAfter=2)

    # ----- Documento -----
    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=35 * mm, bottomMargin=22 * mm,
        title=f"Cotización {num_cot} - {emisor['empresa']}",
        author=emisor["empresa"],
    )
    story = []

    # ----- Título -----
    story.append(Paragraph("COTIZACIÓN", st_title))
    story.append(Paragraph(subtitulo, st_subtitle))
    story.append(Spacer(1, 4))

    # ----- Meta -----
    meta_data = [
        [Paragraph("N° Cotización", st_small_bold), Paragraph(num_cot, st_small),
         Paragraph("Fecha emisión", st_small_bold), Paragraph(fecha_str, st_small)],
        [Paragraph("Validez oferta", st_small_bold),
         Paragraph(f"15 días (hasta {validez_str})", st_small),
         Paragraph("Moneda", st_small_bold),
         Paragraph("Pesos chilenos (CLP)", st_small)],
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
        f"<b>{label}:</b> {value}" for label, value in emisor_lines if value
    )
    emisor_para = Paragraph(emisor_html, st_small)

    cliente_cfg = config.get("cliente")
    if cliente_cfg:
        cliente_titulo = cliente_cfg.get("titulo", "CLIENTE")
        cliente_campos = cliente_cfg.get("campos", [])
        cliente_html = "<br/>".join(
            f"<b>{label}:</b> {value}" for label, value in cliente_campos
        )
        cliente_para = Paragraph(cliente_html, st_small)

        partes_tbl = Table(
            [
                [Paragraph("EMISOR", st_white_bold),
                 Paragraph(cliente_titulo, st_white_bold)],
                [emisor_para, cliente_para],
            ],
            colWidths=[85 * mm, 85 * mm],
        )
    else:
        # Solo emisor, ancho completo
        partes_tbl = Table(
            [
                [Paragraph("EMISOR", st_white_bold)],
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

    # ----- Detalle del servicio -----
    story.append(Paragraph("DETALLE DEL SERVICIO", st_section))
    story.append(HRFlowable(width="100%", thickness=0.8, color=BRAND,
                            spaceBefore=0, spaceAfter=6))

    items = config.get("items", [])
    detalle_rows = [[
        Paragraph("Ítem", st_white_bold_center),
        Paragraph("Descripción", st_white_bold),
        Paragraph("Cant.", st_white_bold_center),
        Paragraph("Valor unitario<br/>(neto)", st_white_bold_center),
        Paragraph("Subtotal<br/>(neto)", st_white_bold_center),
    ]]

    total_neto = 0
    for i, item in enumerate(items, start=1):
        titulo = item.get("descripcion_titulo", "")
        bullets = item.get("descripcion_bullets", [])
        cant = item.get("cantidad", 1)
        valor_unit = item.get("valor_unitario_neto", 0)
        subtotal = cant * valor_unit
        total_neto += subtotal

        desc_html = f"<b>{titulo}</b>"
        if bullets:
            desc_html += "<br/>" + "<br/>".join(f"• {b}" for b in bullets)

        detalle_rows.append([
            Paragraph(str(i), st_small),
            Paragraph(desc_html, st_small),
            Paragraph(str(cant), st_small),
            Paragraph(clp(valor_unit), st_small),
            Paragraph(clp(subtotal), st_small),
        ])

    detalle_tbl = Table(detalle_rows,
                        colWidths=[12 * mm, 95 * mm, 15 * mm, 24 * mm, 24 * mm])
    detalle_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("ALIGN", (2, 1), (2, -1), "CENTER"),
        ("ALIGN", (3, 1), (4, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(detalle_tbl)

    # ----- Totales -----
    if solo_neto:
        # Solo se muestra el total neto, sin IVA.
        tot_data = [
            ["", Paragraph("TOTAL NETO", st_white_bold),
             Paragraph(clp(total_neto), st_white_bold)],
        ]
        tot_tbl = Table(tot_data, colWidths=[122 * mm, 24 * mm, 24 * mm])
        tot_tbl.setStyle(TableStyle([
            ("BACKGROUND", (1, 0), (2, 0), BRAND),
            ("BOX", (1, 0), (2, 0), 0.4, LINE),
            ("ALIGN", (1, 0), (2, 0), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (1, 0), (2, 0), 6),
            ("BOTTOMPADDING", (1, 0), (2, 0), 6),
        ]))
    else:
        iva = round(total_neto * 0.19)
        total = total_neto + iva

        tot_data = [
            ["", Paragraph("Valor neto", st_small_bold),
             Paragraph(clp(total_neto), st_small_bold)],
            ["", Paragraph("IVA (19%)", st_small_bold),
             Paragraph(clp(iva), st_small_bold)],
            ["", Paragraph("TOTAL", st_white_bold),
             Paragraph(clp(total), st_white_bold)],
        ]
        tot_tbl = Table(tot_data, colWidths=[122 * mm, 24 * mm, 24 * mm])
        tot_tbl.setStyle(TableStyle([
            ("BACKGROUND", (1, 0), (2, 1), BRAND_SOFT),
            ("BACKGROUND", (1, 2), (2, 2), BRAND),
            ("BOX", (1, 0), (2, -1), 0.4, LINE),
            ("INNERGRID", (1, 0), (2, -1), 0.4, LINE),
            ("ALIGN", (1, 0), (2, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (1, 0), (2, -1), 6),
            ("BOTTOMPADDING", (1, 0), (2, -1), 6),
        ]))
    story.append(tot_tbl)

    # ----- Condiciones comerciales -----
    story.append(Paragraph("CONDICIONES COMERCIALES", st_section))
    story.append(HRFlowable(width="100%", thickness=0.8, color=BRAND,
                            spaceBefore=0, spaceAfter=6))

    valores_txt = (
        "Expresados en pesos chilenos (CLP), netos."
        if solo_neto
        else "Expresados en pesos chilenos (CLP), netos. Se les suma IVA (19%)."
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
        [Paragraph(f"<b>{k}</b>", st_small), Paragraph(v, st_small)]
        for k, v in condiciones
    ]
    cond_tbl = Table(cond_data, colWidths=[40 * mm, 130 * mm])
    cond_tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [GRAY_SOFT, colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(cond_tbl)

    # ----- Datos para transferencia (opcional) -----
    datos_tx = config.get("datos_transferencia")
    if datos_tx:
        story.append(Paragraph("DATOS PARA TRANSFERENCIA", st_section))
        story.append(HRFlowable(width="100%", thickness=0.8, color=BRAND,
                                spaceBefore=0, spaceAfter=6))
        tx_campos = datos_tx.get("campos", [])
        tx_data = [
            [Paragraph(f"<b>{k}</b>", st_small), Paragraph(v, st_small)]
            for k, v in tx_campos
        ]
        tx_tbl = Table(tx_data, colWidths=[40 * mm, 130 * mm])
        tx_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BRAND_SOFT),
            ("BOX", (0, 0), (-1, -1), 0.4, BRAND),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(KeepTogether(tx_tbl))

    # ----- Observaciones -----
    story.append(Paragraph("OBSERVACIONES", st_section))
    story.append(HRFlowable(width="100%", thickness=0.8, color=BRAND,
                            spaceBefore=0, spaceAfter=6))

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
        story.append(Paragraph(f"• {o}", st_bullet))

    # ----- Firmas -----
    story.append(Spacer(1, 22))

    firma_emisor = Paragraph(
        "_________________________________<br/>"
        f"<b>Por {emisor['empresa']}</b><br/>"
        "Nombre: ____________________<br/>"
        "Cargo: ______________________<br/>"
        f"Fecha: {fecha_str}",
        st_small,
    )

    if cliente_cfg:
        firma_cliente = Paragraph(
            "_________________________________<br/>"
            "<b>Aceptación del cliente</b><br/>"
            "Nombre: ____________________<br/>"
            "RUT: _______________________<br/>"
            "Fecha: ______________________",
            st_small,
        )
        firma_tbl = Table([[firma_emisor, firma_cliente]],
                          colWidths=[85 * mm, 85 * mm])
    else:
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
            "<i>Agradecemos la oportunidad de cotizar. Para cualquier consulta, "
            f"contáctenos al {emisor['telefono']}.</i>"
        )
    else:
        thanks = "<i>Agradecemos la oportunidad de cotizar.</i>"
    story.append(Paragraph(
        thanks,
        ParagraphStyle("thanks", parent=st_small, alignment=TA_CENTER, textColor=GRAY),
    ))

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
