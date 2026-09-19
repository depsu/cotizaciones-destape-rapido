#!/usr/bin/env python3
"""Informe mensual de entregas en PDF, leído directo de Supabase.

Alejandro pregunta seguido «cuánto generó el mes» y hasta ahora la respuesta vivía en un
chat. Esto arma la misma cuenta como documento: el total facturado, lo cobrado, lo que
falta cobrar, la comisión, y la lista completa de entregas con su estado.

Usa la misma marca que las cotizaciones (mismo teal, mismo ámbar, misma Avenir) para que
los dos documentos se vean de la misma casa.

Uso:
    python3 resumen-repartidor/scripts/informe_mes.py [AAAA-MM] [salida.pdf]
    python3 resumen-repartidor/scripts/informe_mes.py            # el mes en curso
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))
import generar_listado as gl            # noqa: E402  (paleta de Supabase + reglas de plata)
import sync_entregas_supabase as S      # noqa: E402

# ── Marca, la misma de las cotizaciones ────────────────────────────────────────────
BRAND = colors.HexColor("#0F6E6E")
BRAND_DARK = colors.HexColor("#0A4F4F")
BRAND_SOFT = colors.HexColor("#EAF4F2")
ACCENT = colors.HexColor("#E0A82E")
ACCENT_SOFT = colors.HexColor("#FBF1DC")
GRAY = colors.HexColor("#5F6B6B")
GRAY_SOFT = colors.HexColor("#F5F7F7")
LINE = colors.HexColor("#D2DEDC")
DARK = colors.HexColor("#1E2A2A")
HX_BRAND, HX_GRAY = "#0F6E6E", "#5F6B6B"

FONT, FONT_MED, FONT_BOLD, FONT_HEAVY = ("Helvetica",) * 2 + ("Helvetica-Bold",) * 2


def _fuentes() -> None:
    """Avenir Next si el Mac la tiene; si no, Helvetica y el documento igual sale."""
    global FONT, FONT_MED, FONT_BOLD, FONT_HEAVY
    path = "/System/Library/Fonts/Avenir Next.ttc"
    if not Path(path).exists():
        return
    try:
        for nombre, idx in (("Avenir", 7), ("Avenir-Med", 5), ("Avenir-Demi", 2),
                            ("Avenir-Heavy", 8)):
            pdfmetrics.registerFont(TTFont(nombre, path, subfontIndex=idx))
        registerFontFamily("Avenir", normal="Avenir", bold="Avenir-Demi")
        FONT, FONT_MED, FONT_BOLD, FONT_HEAVY = "Avenir", "Avenir-Med", "Avenir-Demi", "Avenir-Heavy"
    except Exception:
        pass


MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
         "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
LISTO = {"entregado", "cobrado", "pagado-pendiente"}
ROTULO = {"pendiente": "por entregar", "en-camino": "en camino", "entregado": "entregado",
          "cobrado": "cobrado", "pagado-pendiente": "cobrado"}


def clp(n) -> str:
    return "$" + f"{int(n or 0):,}".replace(",", ".")


def corto(texto: str, n: int) -> str:
    """Nombre recortado con puntos suspensivos: cortar a secas deja «Hacienda To»."""
    t = str(texto).strip()
    return t if len(t) <= n else t[: n - 1].rstrip(" ·,-") + "…"


def traer(tabla: str, select: str) -> list[dict]:
    url = f"{gl.SUPABASE_URL}/rest/v1/{tabla}?select={select}&limit=1000"
    req = urllib.request.Request(url, headers=S._headers())
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def datos_del_mes(mes: str) -> list[dict]:
    """Las entregas del mes con su estado, ordenadas por día. `mes` = 'AAAA-MM'."""
    entregas = [f for f in traer("entrega", "id,fecha,eliminado,data") if not f.get("eliminado")]
    estados = {f["id"]: (f.get("estado") or "pendiente")
               for f in traer("entrega_estado", "id,estado,eliminado") if not f.get("eliminado")}
    filas = []
    for f in sorted((x for x in entregas if x["fecha"].startswith(mes)), key=lambda x: x["fecha"]):
        e = f["data"] or {}
        st = estados.get(f["id"], "pendiente")
        filas.append({
            "dia": f["fecha"][8:],
            "cliente": str(e.get("cliente") or "sin nombre"),
            "banos": e.get("cantidad") if isinstance(e.get("cantidad"), int) else 0,
            "monto": (e.get("pago") or {}).get("monto") or 0,
            "comision": gl.comision_de(e),
            "estado": ROTULO.get(st, st),
            "cobrado": st in LISTO,
        })
    return filas


def generar(mes: str, salida: str) -> dict:
    _fuentes()
    filas = datos_del_mes(mes)
    anio, num = int(mes[:4]), int(mes[5:7])
    titulo_mes = f"{MESES[num - 1].capitalize()} {anio}"

    total = sum(f["monto"] for f in filas)
    cobrado = sum(f["monto"] for f in filas if f["cobrado"])
    comision = sum(f["comision"] for f in filas)
    banos = sum(f["banos"] for f in filas)

    st_body = ParagraphStyle("body", fontName=FONT, fontSize=9, leading=12.5, textColor=DARK)
    st_small = ParagraphStyle("small", parent=st_body, fontSize=8.5, leading=11.5)
    st_num = ParagraphStyle("num", parent=st_small, alignment=TA_RIGHT)
    st_num_b = ParagraphStyle("numb", parent=st_num, fontName=FONT_BOLD)
    st_h2 = ParagraphStyle("h2", fontName=FONT_BOLD, fontSize=11, leading=14,
                           textColor=BRAND, spaceAfter=2)

    doc = SimpleDocTemplate(salida, pagesize=letter,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Entregas {titulo_mes}", author="Destape Rápido")
    ANCHO = doc.width
    story: list = []

    # ── Membrete ──────────────────────────────────────────────────────────────────
    cab = Table([[
        Paragraph(f'<font name="{FONT_HEAVY}" size="17" color="{HX_BRAND}">DESTAPE RÁPIDO</font>'
                  f'<br/><font size="8.5" color="{HX_GRAY}">Soluciones sanitarias profesionales'
                  f' · Región Metropolitana</font>', st_body),
        Paragraph(f'<para alignment="right"><font size="8.5" color="{HX_GRAY}">'
                  f'+56 9 3647 0112<br/>destaperapido.cl<br/>Maipú, RM</font></para>', st_body),
    ]], colWidths=[ANCHO * 0.62, ANCHO * 0.38])
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                             ("LINEBELOW", (0, 0), (-1, -1), 1.2, BRAND)]))
    story += [cab, Spacer(1, 16)]

    st_titulo = ParagraphStyle("titulo", fontName=FONT_HEAVY, fontSize=26, leading=29,
                               textColor=BRAND)
    story.append(Paragraph(f"ENTREGAS DE {titulo_mes.upper()}", st_titulo))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f'<font size="10" color="{HX_GRAY}">{len(filas)} entregas · {banos} baños movidos · '
        f'informe al {date.today().day} de {MESES[date.today().month - 1]}</font>', st_body))
    story.append(Spacer(1, 16))

    # ── Los cuatro números ────────────────────────────────────────────────────────
    HUECO = 6
    anchos = [(ANCHO - 2 * HUECO) * r for r in (0.38, 0.31, 0.31)]

    def tarjeta(rotulo: str, valor: str, fondo, tinta: str, ancho: float, grande=False) -> Table:
        t = Table([[Paragraph(f'<font size="7.5" color="{tinta}">{rotulo.upper()}</font>', st_small)],
                   [Paragraph(f'<font name="{FONT_HEAVY}" size="{14 if grande else 11.5}" '
                              f'color="{tinta}">{valor}</font>', st_small)]],
                  colWidths=[ancho])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), fondo),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (0, 0), 9), ("BOTTOMPADDING", (0, 0), (0, 0), 2),
            ("TOPPADDING", (0, 1), (0, 1), 0), ("BOTTOMPADDING", (0, 1), (0, 1), 10),
        ]))
        return t

    hero = Table([[tarjeta("Facturado", clp(total), BRAND, "#FFFFFF", anchos[0], grande=True),
                   tarjeta("Ya cobrado", clp(cobrado), BRAND_SOFT, HX_BRAND, anchos[1], grande=True),
                   tarjeta("Por cobrar", clp(total - cobrado), ACCENT_SOFT, "#8A6314", anchos[2],
                           grande=True)]],
                 colWidths=[a + HUECO for a in anchos[:2]] + [anchos[2]])
    hero.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                              ("RIGHTPADDING", (-1, 0), (-1, -1), 0)]))
    story += [hero, Spacer(1, 18)]

    # ── El detalle ────────────────────────────────────────────────────────────────
    story.append(Paragraph("DETALLE DE ENTREGAS", st_h2))
    story.append(Spacer(1, 5))

    cab_t = [Paragraph(f'<font name="{FONT_BOLD}" color="#FFFFFF" size="8">DÍA</font>', st_small),
             Paragraph(f'<font name="{FONT_BOLD}" color="#FFFFFF" size="8">CLIENTE</font>', st_small),
             Paragraph(f'<para alignment="right"><font name="{FONT_BOLD}" color="#FFFFFF" size="8">BAÑOS</font></para>', st_small),
             Paragraph(f'<para alignment="right"><font name="{FONT_BOLD}" color="#FFFFFF" size="8">MONTO</font></para>', st_small),
             Paragraph(f'<font name="{FONT_BOLD}" color="#FFFFFF" size="8">ESTADO</font>', st_small)]
    rows = [cab_t]
    for f in filas:
        col = HX_GRAY if f["cobrado"] else "#8A6314"
        rows.append([
            Paragraph(f'<font color="{HX_GRAY}">{f["dia"]}</font>', st_small),
            Paragraph(corto(f["cliente"], 44), st_small),
            Paragraph(str(f["banos"] or ""), st_num),
            Paragraph(clp(f["monto"]), st_num_b if not f["cobrado"] else st_num),
            Paragraph(f'<font color="{col}" size="8">{f["estado"]}</font>', st_small),
        ])
    rows.append([Paragraph(f'<font name="{FONT_BOLD}">TOTAL</font>', st_small), "",
                 Paragraph(f'<font name="{FONT_BOLD}">{banos}</font>', st_num),
                 Paragraph(f'<font name="{FONT_BOLD}">{clp(total)}</font>', st_num), ""])

    tbl = Table(rows, colWidths=[11 * mm, 74 * mm, 15 * mm, 30 * mm, 40 * mm], repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 1), (-1, -2), 0.3, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, -1), (-1, -1), BRAND_SOFT),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, BRAND),
        ("SPAN", (0, -1), (1, -1)),
    ]
    # las filas sin cobrar se marcan con una franja ámbar: son las que hay que perseguir
    for i, f in enumerate(filas, start=1):
        if not f["cobrado"]:
            estilo.append(("BACKGROUND", (0, i), (-1, i), ACCENT_SOFT))
    tbl.setStyle(TableStyle(estilo))
    story.append(tbl)

    # ── Lo que hay que perseguir ──────────────────────────────────────────────────
    faltan = [f for f in filas if not f["cobrado"]]
    if faltan:
        story.append(Spacer(1, 16))
        bloque = [Paragraph("LO QUE FALTA COBRAR", st_h2), Spacer(1, 5)]
        cuerpo = [[Paragraph(f'<font color="{HX_GRAY}">{f["dia"]}</font>', st_small),
                   Paragraph(corto(f["cliente"], 52), st_small),
                   Paragraph(clp(f["monto"]), st_num_b)] for f in faltan]
        cuerpo.append([Paragraph(f'<font name="{FONT_BOLD}">Total por cobrar</font>', st_small), "",
                       Paragraph(f'<font name="{FONT_BOLD}">{clp(total - cobrado)}</font>', st_num)])
        t2 = Table(cuerpo, colWidths=[11 * mm, 119 * mm, 40 * mm])
        t2.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -2), ACCENT_SOFT),
            ("BACKGROUND", (0, -1), (-1, -1), ACCENT),
            ("SPAN", (0, -1), (1, -1)),
            ("BOX", (0, 0), (-1, -1), 0.5, ACCENT),
            ("LINEBELOW", (0, 0), (-1, -3), 0.3, colors.HexColor("#E8D9AE")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        bloque.append(t2)
        story.append(KeepTogether(bloque))

    def pie(canvas, documento):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        y = 13 * mm
        canvas.line(documento.leftMargin, y, documento.leftMargin + documento.width, y)
        canvas.setFont(FONT, 7.5)
        canvas.setFillColor(GRAY)
        canvas.drawString(documento.leftMargin, y - 4.5 * mm,
                          f"Destape Rápido · entregas de {titulo_mes.lower()}")
        canvas.drawRightString(documento.leftMargin + documento.width, y - 4.5 * mm,
                               f"Página {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=pie, onLaterPages=pie)
    return {"entregas": len(filas), "banos": banos, "total": total,
            "cobrado": cobrado, "por_cobrar": total - cobrado, "comision": comision}


def main() -> None:
    hoy = date.today()
    mes = sys.argv[1] if len(sys.argv) > 1 else f"{hoy.year}-{hoy.month:02d}"
    salida = sys.argv[2] if len(sys.argv) > 2 else f"informe-entregas-{mes}.pdf"
    r = generar(mes, salida)
    print(f"OK: {salida}")
    print(f"   {r['entregas']} entregas · {r['banos']} baños")
    print(f"   facturado {clp(r['total'])} · cobrado {clp(r['cobrado'])} · "
          f"por cobrar {clp(r['por_cobrar'])}")


if __name__ == "__main__":
    main()
