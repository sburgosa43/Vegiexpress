"""
pdf_envio.py — Generación del PDF de envío semanal.
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


def generar_envio(cliente: dict, fecha: date, lineas: list, unico: str = "") -> bytes:
    """
    Genera PDF de envío VeggiExpress. Retorna bytes del PDF.

    cliente : dict con nombre, empresa, direccion, nit, telefono
    fecha   : date de entrega
    lineas  : lista de dicts {producto, cantidad, unidad, precio, total}
    unico   : código único del pedido
    """
    buffer = BytesIO()
    S = _S()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15*mm,
        rightMargin=15*mm,
        topMargin=12*mm,
        bottomMargin=22*mm,
        title=f"Envio - {cliente.get('nombre','')} - {fecha.strftime('%d/%m/%Y')}",
    )

    story = []
    CW = CONTENT_W   # content width in points

    # ── 1. HEADER: Logo + Título ───────────────────────────────────────────────
    if os.path.exists(LOGO_PATH):
        logo = _logo_proporcional(40) or RLImage(LOGO_PATH, width=40*mm, height=12*mm)
    else:
        logo = _p("VeggiExpress",
                  ParagraphStyle("lg", fontSize=18, fontName="Helvetica-Bold",
                                  textColor=VERDE_OSC))

    header_data = [[
        logo,
        [_p("ENVÍO", S["h_titulo"]),
         _p("Más fresco, imposible.", S["h_sub"])],
    ]]
    ht = Table(header_data, colWidths=[58*mm, CW - 58*mm])
    ht.setStyle(TableStyle([
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
        ("TOPPADDING",   (0,0), (-1,-1), 2),
    ]))
    story.append(ht)
    story.append(HRFlowable(width="100%", thickness=3,
                             color=VERDE_LIM, spaceAfter=5*mm))

    # ── 2. INFO: Cliente + Pedido ─────────────────────────────────────────────
    semana    = fecha.isocalendar()[1]
    cli_nom   = _s(cliente.get("nombre", "—"))
    cli_emp   = _s(cliente.get("empresa", ""))
    cli_dir   = _s(cliente.get("direccion", ""))
    cli_nit   = _s(cliente.get("nit", "CF"))
    cli_tel   = _s(cliente.get("telefono", ""))

    # Info table: 5 rows × 2 columns
    info_rows = [
        [_p("CLIENTE",                  S["sec_lbl"]),
         _p("PEDIDO",                   S["sec_lbl"])],

        [_p(cli_nom,                    S["cli_nom"]),
         _p(fecha.strftime("%d / %m / %Y"), S["ped_fecha"])],

        [_p(cli_emp if cli_emp != cli_nom else "", S["cli_info"]),
         _p(f"Semana {semana}  ·  {fecha.year}", S["ped_sem"])],

        [_p(cli_dir,                    S["cli_info"]),
         _p(f"Código: {_s(unico)}" if unico else "", S["ped_info"])],

        [_p(f"NIT: {cli_nit}" +
            (f"   ·   Tel: {cli_tel}" if cli_tel else ""),
            S["cli_info"]),
         _p("",                         S["ped_info"])],
    ]

    COL_CLI = CW * 0.57
    COL_PED = CW * 0.43

    it = Table(info_rows, colWidths=[COL_CLI, COL_PED])
    it.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (0,-1), GRIS_CLR),
        ("BACKGROUND",   (1,0), (1,-1), GRIS_TAB),
        ("LEFTPADDING",  (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING",   (0,0), (-1,-1), 3),
        ("BOTTOMPADDING",(0,0), (-1,-1), 3),
        ("TOPPADDING",   (0,0), (-1,0),  6),
        ("BOTTOMPADDING",(0,-1),(-1,-1), 6),
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("LINEAFTER",    (0,0), (0,-1),  0.5, colors.HexColor('#DDDDDD')),
    ]))
    story.append(it)
    story.append(Spacer(1, 5*mm))

    # ── 3. TABLA DE PRODUCTOS ─────────────────────────────────────────────────
    # Columnas: # | Producto | Cant. | Unidad | Precio | Total
    col_w = [7*mm, 73*mm, 16*mm, 23*mm, 28*mm, CW - 7*mm - 73*mm - 16*mm - 23*mm - 28*mm]

    encabezado = [
        _p("#",         S["th"]),
        _p("Producto",  S["th"]),
        _p("Cant.",     S["th_r"]),
        _p("Unidad",    S["th"]),
        _p("Precio",    S["th_r"]),
        _p("Total",     S["th_r"]),
    ]
    prod_rows = [encabezado]
    total_pedido = 0.0

    for i, l in enumerate(lineas):
        cantidad = float(l.get("cantidad") or 0)
        precio   = float(l.get("precio")   or 0)
        subtotal = cantidad * precio
        total_pedido += subtotal
        prod_rows.append([
            _p(str(i + 1),                        S["td"]),
            _p(_s(l.get("producto", "")),          S["td"]),
            _p(f"{cantidad:g}",                   S["td_r"]),
            _p(_s(l.get("unidad", "")),            S["td"]),
            _p(f"Q {precio:,.2f}",                S["td_r"]),
            _p(f"Q {subtotal:,.2f}",              S["td_r"]),
        ])

    pt = Table(prod_rows, colWidths=col_w, repeatRows=1)
    pts = TableStyle([
        ("BACKGROUND",   (0,0), (-1,0),   VERDE_OSC),
        ("FONTNAME",     (0,0), (-1,0),   "Helvetica-Bold"),
        ("TOPPADDING",   (0,0), (-1,-1),  4),
        ("BOTTOMPADDING",(0,0), (-1,-1),  4),
        ("LEFTPADDING",  (0,0), (-1,-1),  4),
        ("RIGHTPADDING", (0,0), (-1,-1),  4),
        ("VALIGN",       (0,0), (-1,-1),  "MIDDLE"),
        ("LINEBELOW",    (0,0), (-1,0),   1.5, VERDE_LIM),
        ("LINEBELOW",    (0,-1),(-1,-1),  0.8, VERDE_OSC),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [BLANCO, GRIS_TAB]),
    ])
    pt.setStyle(pts)
    story.append(pt)

    # ── 4. TOTAL ───────────────────────────────────────────────────────────────
    story.append(Spacer(1, 3*mm))
    tot_data = [[
        "",
        _p("TOTAL  DEL  PEDIDO", S["tot_lbl"]),
        _p(f"Q  {total_pedido:,.2f}", S["tot_val"]),
    ]]
    tt = Table(tot_data, colWidths=[CW - 85*mm, 45*mm, 40*mm])
    tt.setStyle(TableStyle([
        ("BACKGROUND",   (1,0), (2,0),   GRIS_CLR),
        ("LINEABOVE",    (1,0), (2,0),   1.5, VERDE_OSC),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
        ("LEFTPADDING",  (1,0), (1,0),   8),
        ("RIGHTPADDING", (2,0), (2,0),   8),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(tt)

    # ── 5. FIRMA ───────────────────────────────────────────────────────────────
    story.append(Spacer(1, 14*mm))
    sign_w = CW / 3 - 4*mm
    sign_data = [[
        _p("Entregado por", S["sign"]),
        _p("Recibido por",  S["sign"]),
        _p("Conforme",      S["sign"]),
    ]]
    st_ = Table(sign_data, colWidths=[sign_w, sign_w, sign_w],
                spaceBefore=2*mm)
    st_.setStyle(TableStyle([
        ("LINEABOVE", (0,0), (-1,0), 0.8, GRIS_CARB),
        ("TOPPADDING",(0,0), (-1,-1), 3),
        ("ALIGN",     (0,0), (-1,-1), "CENTER"),
        ("LEFTPADDING",(0,0),(-1,-1), 6*mm),
        ("RIGHTPADDING",(0,0),(-1,-1), 6*mm),
    ]))
    story.append(st_)

    # ── 6. FOOTER ─────────────────────────────────────────────────────────────
    story.append(Spacer(1, 10*mm))
    story.append(HRFlowable(width="100%", thickness=2,
                             color=VERDE_LIM, spaceAfter=3))
    story.append(_p(
        "Más fresco, imposible.   ·   VeggiExpress   ·   Guatemala",
        S["footer"],
    ))

    doc.build(story)
    return buffer.getvalue()


# ── PDF DE FACTURACIÓN MENSUAL ────────────────────────────────────────────────
MESES_ES = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
             "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]


