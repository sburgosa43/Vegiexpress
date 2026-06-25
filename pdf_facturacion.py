"""
pdf_facturacion.py — Generación del PDF de facturación mensual.
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


def nombre_archivo_fact(cliente_nombre: str, mes: int, año: int) -> str:
    nombre = unicodedata.normalize("NFKD", cliente_nombre)
    nombre = nombre.encode("ascii","ignore").decode("ascii")
    nombre = re.sub(r"[^a-zA-Z0-9]", "", nombre) or "cliente"
    return f"{nombre}_Facturacion_{MESES_ES[mes-1]}{año}.pdf"


def nombre_archivo_factura(cliente_nombre: str, mes: int, año: int) -> str:
    """CazadorItaliano_Mayo2026.pdf"""
    n = unicodedata.normalize("NFKD", cliente_nombre or "cliente")
    n = n.encode("ascii", "ignore").decode("ascii")
    n = re.sub(r"[^a-zA-Z0-9]", "", n) or "cliente"
    return f"{n}_{MESES_ES[mes]}{año}.pdf"


def generar_facturacion_mensual(cliente: dict, mes: int, año: int,
                                 por_semana: dict) -> bytes:
    """
    Genera PDF de resumen de facturación mensual.

    cliente   : dict con nombre, empresa, direccion, nit, telefono
    mes, año  : período
    por_semana: {semana_num: {"fecha": date, "lineas": [...]}}
                cada linea: {producto, cantidad, unidad, precio, total}
    """
    from reportlab.platypus import KeepTogether

    buffer = BytesIO()
    S = _S()
    CW = CONTENT_W

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=12*mm, bottomMargin=22*mm,
        title=f"Facturacion - {cliente.get('nombre','')} - {MESES_ES[mes]} {año}",
    )

    story = []

    # ── HEADER (mismo que envío) ──────────────────────────────────────────────
    if os.path.exists(LOGO_PATH):
        logo = _logo_proporcional(40) or RLImage(LOGO_PATH, width=40*mm, height=12*mm)
    else:
        logo = _p("VeggiExpress",
                  ParagraphStyle("lg", fontSize=18, fontName="Helvetica-Bold",
                                  textColor=VERDE_OSC))

    titulo_style = ParagraphStyle("ftit", fontSize=22, fontName="Helvetica-Bold",
                                   textColor=GRIS_CARB, alignment=TA_RIGHT, leading=26)
    sub_style    = ParagraphStyle("fsub", fontSize=10, fontName="Helvetica-Bold",
                                   textColor=VERDE_OSC, alignment=TA_RIGHT, leading=13)

    header_data = [[
        logo,
        [_p("RESUMEN DE FACTURACIÓN", titulo_style),
         _p(f"{MESES_ES[mes].upper()} {año}", sub_style)],
    ]]
    ht = Table(header_data, colWidths=[58*mm, CW - 58*mm])
    ht.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(ht)
    story.append(HRFlowable(width="100%", thickness=3, color=VERDE_LIM, spaceAfter=5*mm))

    # ── INFO CLIENTE ──────────────────────────────────────────────────────────
    S2 = _S()
    cli_nom = _s(cliente.get("nombre", "—"))
    cli_emp = _s(cliente.get("empresa", ""))
    cli_dir = _s(cliente.get("direccion", ""))
    cli_nit = _s(cliente.get("nit", "CF"))
    cli_tel = _s(cliente.get("telefono", ""))

    info_rows = [
        [_p("CLIENTE",                           S2["sec_lbl"]),
         _p(f"PERÍODO: {MESES_ES[mes]} {año}",  S2["sec_lbl"])],
        [_p(cli_nom,                             S2["cli_nom"]),
         _p(f"{len(por_semana)} semana(s) de entrega",
            ParagraphStyle("ps", fontSize=11, fontName="Helvetica-Bold",
                            textColor=VERDE_OSC, alignment=TA_RIGHT, leading=14))],
        [_p(cli_emp if cli_emp != cli_nom else "", S2["cli_info"]),
         _p("",                                  S2["ped_info"])],
        [_p(cli_dir,                             S2["cli_info"]),
         _p("",                                  S2["ped_info"])],
        [_p(f"NIT: {cli_nit}" +
            (f"   ·   Tel: {cli_tel}" if cli_tel else ""), S2["cli_info"]),
         _p("",                                  S2["ped_info"])],
    ]
    it = Table(info_rows, colWidths=[CW*0.57, CW*0.43])
    it.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (0,-1), GRIS_CLR),
        ("BACKGROUND",   (1,0), (1,-1), GRIS_TAB),
        ("LEFTPADDING",  (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING",   (0,0), (-1,-1), 3),
        ("BOTTOMPADDING",(0,0), (-1,-1), 3),
        ("TOPPADDING",   (0,0), (-1,0),  6),
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
    ]))
    story.append(it)
    story.append(Spacer(1, 5*mm))

    # ── DETALLE POR SEMANA ────────────────────────────────────────────────────
    col_w = [8*mm, 58*mm, 22*mm, 14*mm, 20*mm, 24*mm, CW-8*mm-58*mm-22*mm-14*mm-20*mm-24*mm]

    # Encabezado de tabla
    encab = [
        _p("#",         S2["th"]),
        _p("Producto",  S2["th"]),
        _p("Fecha",     S2["th"]),
        _p("Cant.",     S2["th_r"]),
        _p("Unidad",    S2["th"]),
        _p("Precio",    S2["th_r"]),
        _p("Total",     S2["th_r"]),
    ]

    total_mes  = 0.0
    prod_agg   = {}   # producto → {cantidad, total, unidad}
    n_linea    = 0

    for semana_num in sorted(por_semana.keys()):
        bloque     = por_semana[semana_num]
        fecha_sem  = bloque["fecha"]
        lineas_sem = bloque["lineas"]
        sub_sem    = sum(l["total"] for l in lineas_sem)

        # Fila de encabezado de semana
        sem_lbl = f"Semana {semana_num}  ·  {fecha_sem.strftime('%d/%m/%Y')}"
        sem_row = [
            _p(sem_lbl,
               ParagraphStyle("sh", fontSize=9, fontName="Helvetica-Bold",
                               textColor=BLANCO, leading=11)),
            "", "", "", "",
            _p(f"Q {sub_sem:,.2f}",
               ParagraphStyle("sht", fontSize=9, fontName="Helvetica-Bold",
                               textColor=BLANCO, alignment=TA_RIGHT, leading=11)),
        ]

        filas_bloque = [encab, sem_row]

        for l in lineas_sem:
            n_linea += 1
            cant     = float(l.get("cantidad") or 0)
            precio   = float(l.get("precio")   or 0)
            subtot   = float(l.get("total")    or cant * precio)
            total_mes += subtot

            prod = l["producto"]
            if prod not in prod_agg:
                prod_agg[prod] = {"cantidad": 0, "total": 0.0,
                                   "unidad": l.get("unidad",""), "precio": precio}
            prod_agg[prod]["cantidad"] += cant
            prod_agg[prod]["total"]    += subtot

            fecha_l  = l.get("fecha")
            fecha_str = fecha_l.strftime("%d/%m/%y") if fecha_l else ""
            filas_bloque.append([
                _p(str(n_linea),           S2["td"]),
                _p(_s(prod),               S2["td"]),
                _p(fecha_str,              S2["td"]),
                _p(f"{cant:g}",            S2["td_r"]),
                _p(_s(l.get("unidad","")), S2["td"]),
                _p(f"Q {precio:,.2f}",     S2["td_r"]),
                _p(f"Q {subtot:,.2f}",     S2["td_r"]),
            ])

        tbl = Table(filas_bloque, colWidths=col_w, repeatRows=1)
        ts  = TableStyle([
            # Encabezado columnas
            ("BACKGROUND",   (0,0), (-1,0),  VERDE_OSC),
            ("LINEBELOW",    (0,0), (-1,0),  1, VERDE_LIM),
            # Encabezado de semana
            ("BACKGROUND",   (0,1), (-1,1),  VERDE_LIM),
            ("SPAN",         (0,1), (4,1)),
            # Filas de producto
            ("ROWBACKGROUNDS",(0,2),(-1,-1), [BLANCO, GRIS_TAB]),
            ("FONTSIZE",     (0,0), (-1,-1), 9),
            ("TOPPADDING",   (0,0), (-1,-1), 4),
            ("BOTTOMPADDING",(0,0), (-1,-1), 4),
            ("LEFTPADDING",  (0,0), (-1,-1), 4),
            ("RIGHTPADDING", (0,0), (-1,-1), 4),
            ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
            ("LINEBELOW",    (0,-1),(-1,-1), 0.5, VERDE_OSC),
        ])
        tbl.setStyle(ts)
        story.append(KeepTogether([tbl, Spacer(1, 3*mm)]))

    # ── RESUMEN POR PRODUCTO ──────────────────────────────────────────────────
    story.append(Spacer(1, 3*mm))
    story.append(HRFlowable(width="100%", thickness=1, color=VERDE_OSC, spaceAfter=2*mm))

    res_style = ParagraphStyle("rh", fontSize=10, fontName="Helvetica-Bold",
                                textColor=VERDE_OSC, leading=13)
    story.append(_p("RESUMEN POR PRODUCTO", res_style))
    story.append(Spacer(1, 2*mm))

    res_col_w = [CW - 25*mm - 30*mm - 30*mm, 25*mm, 30*mm, 30*mm]
    res_header = [
        _p("Producto",  S2["th"]),
        _p("Unidades",  S2["th_r"]),
        _p("Precio",    S2["th_r"]),
        _p("Total",     S2["th_r"]),
    ]
    res_rows = [res_header]
    for prod, agg in sorted(prod_agg.items()):
        res_rows.append([
            _p(_s(prod),                         S2["td"]),
            _p(f"{agg['cantidad']:,.1f} {_s(agg['unidad'])}", S2["td_r"]),
            _p(f"Q {agg['precio']:,.2f}",        S2["td_r"]),
            _p(f"Q {agg['total']:,.2f}",         S2["td_r"]),
        ])

    res_tbl = Table(res_rows, colWidths=res_col_w)
    res_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),   VERDE_OSC),
        ("ROWBACKGROUNDS",(0,1), (-1,-1),  [BLANCO, GRIS_TAB]),
        ("FONTSIZE",      (0,0), (-1,-1),  9),
        ("TOPPADDING",    (0,0), (-1,-1),  4),
        ("BOTTOMPADDING", (0,0), (-1,-1),  4),
        ("LEFTPADDING",   (0,0), (-1,-1),  4),
        ("RIGHTPADDING",  (0,0), (-1,-1),  4),
        ("LINEBELOW",     (0,-1),(-1,-1),  1, VERDE_OSC),
        ("VALIGN",        (0,0), (-1,-1),  "MIDDLE"),
    ]))
    story.append(res_tbl)

    # ── TOTALES ───────────────────────────────────────────────────────────────
    story.append(Spacer(1, 3*mm))
    iva_mes = round(total_mes * 0.12 / 1.12, 2)
    isr_mes = round(total_mes * 0.05 / 1.12, 2)

    tot_col_w = [CW - 45*mm - 35*mm, 45*mm, 35*mm]
    tot_rows = [
        [_p("Base sin IVA",  S2["normal"]),
         _p("",              S2["normal"]),
         _p(f"Q {total_mes - iva_mes:,.2f}", S2["td_r"])],
        [_p("IVA (12%)",     S2["normal"]),
         _p("",              S2["normal"]),
         _p(f"Q {iva_mes:,.2f}", S2["td_r"])],
        [_p("ISR retenido (5% sobre base)",
             ParagraphStyle("isr", fontSize=8, textColor=GRIS_CARB,
                             fontName="Helvetica", alignment=TA_LEFT, leading=10)),
         _p("",              S2["normal"]),
         _p(f"Q {isr_mes:,.2f}", S2["td_r"])],
        [_p("TOTAL A FACTURAR",
             ParagraphStyle("tf", fontSize=13, fontName="Helvetica-Bold",
                             textColor=VERDE_OSC, leading=16)),
         _p("",              S2["normal"]),
         _p(f"Q {total_mes:,.2f}",
             ParagraphStyle("tfv", fontSize=13, fontName="Helvetica-Bold",
                             textColor=GRIS_CARB, alignment=TA_RIGHT, leading=16))],
    ]
    tot_tbl = Table(tot_rows, colWidths=tot_col_w)
    tot_tbl.setStyle(TableStyle([
        ("ALIGN",        (2,0), (2,-1),  "RIGHT"),
        ("TOPPADDING",   (0,0), (-1,-1), 3),
        ("BOTTOMPADDING",(0,0), (-1,-1), 3),
        ("LINEABOVE",    (0,-1),(-1,-1), 1.5, VERDE_OSC),
        ("BACKGROUND",   (0,-1),(-1,-1), GRIS_CLR),
        ("TOPPADDING",   (0,-1),(-1,-1), 6),
        ("BOTTOMPADDING",(0,-1),(-1,-1), 6),
    ]))
    story.append(tot_tbl)

    # ── FOOTER ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 8*mm))
    story.append(HRFlowable(width="100%", thickness=2, color=VERDE_LIM, spaceAfter=3))
    story.append(_p(
        _s("Más fresco, imposible.   ·   VeggiExpress   ·   Guatemala"),
        S2["footer"],
    ))

    doc.build(story)
    return buffer.getvalue()


# ── COTIZACIÓN DE PRECIOS ─────────────────────────────────────────────────────
