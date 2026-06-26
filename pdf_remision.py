"""
pdf_remision.py — Generación del PDF de remisión de entrega.
"""
import os
import re
import unicodedata
from datetime import date
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)
from reportlab.platypus import Image as RLImage

from pdf_base import (
    _s, _p, _S, _logo_proporcional, nombre_archivo,
    VERDE_OSC, VERDE_LIM, GRIS_CARB, GRIS_CLR, GRIS_TAB, BLANCO,
    LOGO_PATH, PAGE_W, PAGE_H, CONTENT_W, _MESES_ES,
)


def generar_remision(cliente: str, lineas: list,
                     semana: int, año: int, fecha_entrega: str) -> bytes:
    """
    PDF limpio B&W — una hoja por cliente.
    lineas: [{producto, unidad, cantidad, total}]
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib           import colors as rc

    buf    = BytesIO()
    ML = MR = 20*mm; MT = MB = 18*mm
    PW, PH = A4
    CW     = PW - ML - MR   # ~170mm

    NEGRO = rc.black

    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=ML, rightMargin=MR, topMargin=MT, bottomMargin=MB)
    story = []

    def sty(name, **kw):
        d = dict(fontSize=10, fontName="Helvetica",
                 textColor=NEGRO, leading=13)
        d.update(kw)
        return ParagraphStyle(name, **d)

    s_brand  = sty("brand", fontSize=14, fontName="Helvetica-Bold", leading=16)
    s_info   = sty("info",  fontSize=9)
    s_info_r = sty("infor", fontSize=9,  alignment=TA_RIGHT)
    s_th     = sty("th",    fontSize=9,  fontName="Helvetica-Bold",
                   alignment=TA_CENTER)
    s_th_l   = sty("thl",   fontSize=9,  fontName="Helvetica-Bold")
    s_td     = sty("td",    fontSize=9)
    s_td_c   = sty("tdc",   fontSize=9,  alignment=TA_CENTER)
    s_td_r   = sty("tdr",   fontSize=9,  alignment=TA_RIGHT)
    s_total  = sty("tot",   fontSize=10, fontName="Helvetica-Bold",
                   alignment=TA_RIGHT)

    # ── Encabezado ─────────────────────────────────────────────────────────────
    story.append(_p("VeggiExpress", s_brand))
    story.append(Spacer(1, 4*mm))

    meta = Table([[
        _p(f"Cliente: {_s(cliente)}", s_info),
        _p(f"Semana {semana} / {año}", s_info_r),
    ],[
        _p(f"Fecha de entrega: {fecha_entrega}", s_info),
        _p("", s_info_r),
    ]], colWidths=[CW*0.65, CW*0.35])
    meta.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "TOP"),
        ("TOPPADDING",   (0,0),(-1,-1), 1),
        ("BOTTOMPADDING",(0,0),(-1,-1), 1),
        ("LEFTPADDING",  (0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
    ]))
    story.append(meta)
    story.append(Spacer(1, 5*mm))
    story.append(HRFlowable(width="100%", thickness=0.8,
                             color=NEGRO, spaceAfter=3*mm))

    # ── Tabla de pedido ────────────────────────────────────────────────────────
    wP = CW * 0.46  # Producto
    wU = CW * 0.16  # Unidad
    wQ = CW * 0.15  # Cantidad
    wT = CW * 0.23  # Total
    col_w = [wP, wU, wQ, wT]

    rows = [[
        _p("Producto",  s_th_l),
        _p("Unidad",    s_th),
        _p("Cantidad",  s_th),
        _p("Total",     s_th),
    ]]
    total_gral = 0.0
    for l in lineas:
        total_gral += float(l.get("total") or 0)
        rows.append([
            _p(_s(l.get("producto","")), s_td),
            _p(_s(l.get("unidad","")),  s_td_c),
            _p(f"{float(l.get('cantidad') or 0):g}", s_td_c),
            _p(f"Q {float(l.get('total') or 0):,.2f}",  s_td_r),
        ])

    # Fila de total
    rows.append([
        _p("", s_td),
        _p("", s_td),
        _p("TOTAL", s_total),
        _p(f"Q {total_gral:,.2f}", s_total),
    ])

    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        # Encabezado
        ("LINEBELOW",    (0,0),(-1,0), 0.8, NEGRO),
        ("FONTNAME",     (0,0),(-1,0), "Helvetica-Bold"),
        # Línea antes de total
        ("LINEABOVE",    (0,-1),(-1,-1), 0.8, NEGRO),
        ("LINEBELOW",    (0,-1),(-1,-1), 0.8, NEGRO),
        # Fondo blanco, sin grid interno para filas de datos
        ("ROWBACKGROUNDS",(0,1),(-1,-2), [rc.white]),
        # Líneas sutiles entre filas de datos
        ("LINEBELOW",    (0,1),(-1,-2), 0.3, rc.Color(0.8,0.8,0.8)),
        # Padding
        ("TOPPADDING",   (0,0),(-1,-1), 3),
        ("BOTTOMPADDING",(0,0),(-1,-1), 3),
        ("LEFTPADDING",  (0,0),(-1,-1), 3),
        ("RIGHTPADDING", (0,0),(-1,-1), 3),
        ("FONTSIZE",     (0,0),(-1,-1), 9),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
    ]))
    story.append(tbl)

    story.append(Spacer(1, 8*mm))
    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=NEGRO, spaceAfter=2*mm))
    story.append(_p("Más fresco, imposible.",
                    sty("ft", fontSize=8, fontName="Helvetica-Oblique",
                        alignment=TA_CENTER)))

    doc.build(story)
    return buf.getvalue()


# ── Helper de impresión compartido ────────────────────────────────────────────
