"""
pdf_helper.py — Generación de PDF de Envío con branding VeggiExpress
Usa reportlab para diseño preciso con logo, colores de marca y tabla de productos.
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
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)
from reportlab.platypus import Image as RLImage

# ── BRAND COLORS ──────────────────────────────────────────────────────────────
VERDE_OSC = colors.HexColor('#2D7A2D')
VERDE_LIM = colors.HexColor('#8DC63F')
GRIS_CARB = colors.HexColor('#4A4A4A')
GRIS_CLR  = colors.HexColor('#F5F5F5')
GRIS_TAB  = colors.HexColor('#F0F8F0')
BLANCO    = colors.white

LOGO_PATH = "VeggiExpress-02.png"
PAGE_W, PAGE_H = A4          # 595.28 x 841.89 pt
CONTENT_W = PAGE_W - 30*mm   # 180mm


# ── HELPERS ───────────────────────────────────────────────────────────────────
def _s(texto) -> str:
    """Normaliza texto para compatibilidad con reportlab."""
    if not texto:
        return ""
    return unicodedata.normalize('NFKC', str(texto))


def nombre_archivo(cliente_nombre: str, fecha: date) -> str:
    """CazadorItaliano_14_05_2026.pdf"""
    n = unicodedata.normalize('NFKD', cliente_nombre or "cliente")
    n = n.encode('ascii', 'ignore').decode('ascii')
    n = re.sub(r'[^a-zA-Z0-9]', '', n) or "cliente"
    return f"{n}_{fecha.day:02d}_{fecha.month:02d}_{fecha.year}.pdf"


def _p(texto, estilo) -> Paragraph:
    return Paragraph(_s(texto), estilo)


# ── ESTILOS ───────────────────────────────────────────────────────────────────
def _S():
    def sty(name, **kw):
        defaults = dict(fontName="Helvetica", fontSize=9,
                        textColor=GRIS_CARB, leading=13)
        defaults.update(kw)
        return ParagraphStyle(name, **defaults)

    return {
        "h_titulo":  sty("h_titulo",  fontSize=28, fontName="Helvetica-Bold",
                          textColor=GRIS_CARB, alignment=TA_RIGHT, leading=32),
        "h_sub":     sty("h_sub",     fontSize=9,  fontName="Helvetica-Oblique",
                          textColor=GRIS_CARB, alignment=TA_RIGHT, leading=12),
        "sec_lbl":   sty("sec_lbl",   fontSize=7.5, fontName="Helvetica-Bold",
                          textColor=VERDE_OSC, leading=10),
        "cli_nom":   sty("cli_nom",   fontSize=12, fontName="Helvetica-Bold",
                          textColor=GRIS_CARB, leading=15),
        "cli_info":  sty("cli_info",  fontSize=9,  leading=12),
        "ped_fecha": sty("ped_fecha", fontSize=15, fontName="Helvetica-Bold",
                          textColor=GRIS_CARB, alignment=TA_RIGHT, leading=18),
        "ped_sem":   sty("ped_sem",   fontSize=9,  fontName="Helvetica-Bold",
                          textColor=VERDE_OSC, alignment=TA_RIGHT, leading=12),
        "ped_info":  sty("ped_info",  fontSize=8.5, alignment=TA_RIGHT, leading=12),
        "th":        sty("th",        fontSize=9,  fontName="Helvetica-Bold",
                          textColor=BLANCO, leading=11),
        "th_r":      sty("th_r",      fontSize=9,  fontName="Helvetica-Bold",
                          textColor=BLANCO, alignment=TA_RIGHT, leading=11),
        "td":        sty("td",        fontSize=9,  leading=11),
        "td_r":      sty("td_r",      fontSize=9,  alignment=TA_RIGHT, leading=11),
        "tot_lbl":   sty("tot_lbl",   fontSize=11, fontName="Helvetica-Bold",
                          textColor=VERDE_OSC, alignment=TA_RIGHT, leading=14),
        "tot_val":   sty("tot_val",   fontSize=14, fontName="Helvetica-Bold",
                          textColor=GRIS_CARB, alignment=TA_RIGHT, leading=17),
        "normal":    sty("normal",    fontSize=9,  leading=12),
        "sign":      sty("sign",      fontSize=8,  textColor=colors.HexColor('#AAAAAA'),
                          alignment=TA_CENTER, leading=10),
        "footer":    sty("footer",    fontSize=8,  fontName="Helvetica-Oblique",
                          textColor=GRIS_CARB, alignment=TA_CENTER, leading=10),
    }


# ── GENERADOR PRINCIPAL ───────────────────────────────────────────────────────
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
        logo = RLImage(LOGO_PATH, width=55*mm, height=18*mm)
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


def nombre_archivo_fact(cliente_nombre: str, mes: int, año: int) -> str:
    nombre = unicodedata.normalize("NFKD", cliente_nombre)
    nombre = nombre.encode("ascii","ignore").decode("ascii")
    nombre = re.sub(r"[^a-zA-Z0-9]", "", nombre) or "cliente"
    return f"{nombre}_Facturacion_{MESES_ES[mes-1]}{año}.pdf"


def generar_facturacion(cliente: dict, mes: int, año: int,
                        por_semana: dict) -> bytes:
    """
    Genera PDF de facturación mensual.
    por_semana: {semana_num: [pedido_dicts]}  — ya filtrado, sin cancelados
    """
    buffer = BytesIO()
    S = _S()

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=12*mm, bottomMargin=22*mm,
        title=f"Facturacion {cliente.get('nombre','')} {MESES_ES[mes-1]} {año}",
    )
    story = []
    CW = CONTENT_W

    # ── HEADER ────────────────────────────────────────────────────────────────
    if os.path.exists(LOGO_PATH):
        logo = RLImage(LOGO_PATH, width=55*mm, height=18*mm)
    else:
        logo = _p("VeggiExpress", ParagraphStyle("lg", fontSize=18,
                   fontName="Helvetica-Bold", textColor=VERDE_OSC))

    titulo_txt = f"FACTURACIÓN — {MESES_ES[mes-1].upper()} {año}"
    hd = Table([[logo, _p(titulo_txt, S["h_titulo"])]],
               colWidths=[58*mm, CW-58*mm])
    hd.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                             ("BOTTOMPADDING",(0,0),(-1,-1),4)]))
    story.append(hd)
    story.append(HRFlowable(width="100%", thickness=3,
                             color=VERDE_LIM, spaceAfter=4*mm))

    # ── INFO CLIENTE ──────────────────────────────────────────────────────────
    info_rows = [
        [_p("CLIENTE",                    S["sec_lbl"]),
         _p(f"PERÍODO",                   S["sec_lbl"])],
        [_p(_s(cliente.get("nombre","")), S["cli_nom"]),
         _p(f"{MESES_ES[mes-1]} {año}",
            ParagraphStyle("per", fontSize=14, fontName="Helvetica-Bold",
                            textColor=GRIS_CARB, alignment=2))],
        [_p(_s(cliente.get("empresa","")),S["cli_info"]),
         _p(f"NIT: {_s(cliente.get('nit','CF'))}",
            ParagraphStyle("nitp", fontSize=9, alignment=2, textColor=GRIS_CARB))],
        [_p(_s(cliente.get("direccion","")), S["cli_info"]),
         _p("",S["cli_info"])],
    ]
    it = Table(info_rows, colWidths=[CW*0.57, CW*0.43])
    it.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(0,-1), GRIS_CLR),
        ("BACKGROUND",(1,0),(1,-1), GRIS_TAB),
        ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3),
        ("TOPPADDING",(0,0),(-1,0),6),("BOTTOMPADDING",(0,-1),(-1,-1),6),
        ("LINEAFTER",(0,0),(0,-1),0.5,colors.HexColor("#DDDDDD")),
    ]))
    story.append(it)
    story.append(Spacer(1, 5*mm))

    # ── DESGLOSE POR SEMANA ───────────────────────────────────────────────────
    total_mes = 0.0
    prod_acum: dict = {}   # {(producto, unidad): {cant, total}}

    col_w_det = [CW*0.38, CW*0.12, CW*0.14, CW*0.18, CW*0.18]

    for semana in sorted(por_semana.keys()):
        lineas = por_semana[semana]
        fecha_sem = min(
            (l["fecha"] for l in lineas if l["fecha"]),
            default=None)
        fecha_str = fecha_sem.strftime("%d/%m/%Y") if fecha_sem else ""

        # Encabezado de semana
        story.append(Spacer(1, 3*mm))
        sem_hdr = Table(
            [[_p(f"SEMANA {semana}  —  Entrega: {fecha_str}",
                 ParagraphStyle("sh", fontSize=9, fontName="Helvetica-Bold",
                                 textColor=BLANCO))]],
            colWidths=[CW])
        sem_hdr.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),VERDE_OSC),
            ("LEFTPADDING",(0,0),(-1,-1),8),
            ("TOPPADDING",(0,0),(-1,-1),4),
            ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ]))
        story.append(sem_hdr)

        # Encabezado de columnas
        det_hdr = [[
            _p("Producto",  S["th"]),
            _p("Cant.",     S["th_r"]),
            _p("Unidad",    S["th"]),
            _p("Precio",    S["th_r"]),
            _p("Subtotal",  S["th_r"]),
        ]]
        # Filas de detalle
        subtotal_sem = 0.0
        det_rows = list(det_hdr)
        for l in sorted(lineas, key=lambda x: x["producto"]):
            cant   = float(l.get("cantidad") or 0)
            precio = float(l.get("precio")   or 0)
            sub    = cant * precio
            subtotal_sem += sub
            total_mes    += sub
            key = (l["producto"], l.get("unidad",""))
            if key not in prod_acum:
                prod_acum[key] = {"cant": 0, "total": 0}
            prod_acum[key]["cant"]  += cant
            prod_acum[key]["total"] += sub

            det_rows.append([
                _p(_s(l["producto"]),      S["td"]),
                _p(f"{cant:g}",           S["td_r"]),
                _p(_s(l.get("unidad","")),S["td"]),
                _p(f"Q{precio:,.2f}",     S["td_r"]),
                _p(f"Q{sub:,.2f}",        S["td_r"]),
            ])

        # Fila subtotal semana
        det_rows.append([
            _p("", S["td"]), _p("", S["td"]), _p("", S["td"]),
            _p("Subtotal:", ParagraphStyle("stl", fontSize=8.5,
                fontName="Helvetica-Bold", alignment=2, textColor=VERDE_OSC)),
            _p(f"Q{subtotal_sem:,.2f}",
               ParagraphStyle("stv", fontSize=8.5,
                fontName="Helvetica-Bold", alignment=2, textColor=GRIS_CARB)),
        ])

        dt = Table(det_rows, colWidths=col_w_det, repeatRows=1)
        dt.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),   VERDE_OSC),
            ("ROWBACKGROUNDS",(0,1),(-1,-2),[BLANCO, GRIS_TAB]),
            ("BACKGROUND",(0,-1),(-1,-1), GRIS_CLR),
            ("FONTSIZE",(0,0),(-1,-1),    8.5),
            ("TOPPADDING",(0,0),(-1,-1),  3),
            ("BOTTOMPADDING",(0,0),(-1,-1),3),
            ("LEFTPADDING",(0,0),(-1,-1), 4),
            ("RIGHTPADDING",(0,0),(-1,-1),4),
            ("LINEBELOW",(0,0),(-1,0),    1, VERDE_LIM),
            ("LINEABOVE",(0,-1),(-1,-1),  0.5, VERDE_OSC),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ]))
        story.append(dt)

    # ── RESUMEN POR PRODUCTO ──────────────────────────────────────────────────
    story.append(Spacer(1, 5*mm))
    story.append(HRFlowable(width="100%", thickness=1.5,
                             color=VERDE_LIM, spaceAfter=3*mm))
    story.append(_p("RESUMEN POR PRODUCTO",
                    ParagraphStyle("rp", fontSize=9, fontName="Helvetica-Bold",
                                    textColor=VERDE_OSC)))
    story.append(Spacer(1, 2*mm))

    col_w_res = [CW*0.44, CW*0.18, CW*0.18, CW*0.20]
    res_rows = [[
        _p("Producto",      S["th"]),
        _p("Total Cant.",   S["th_r"]),
        _p("Unidad",        S["th"]),
        _p("Total (Q)",     S["th_r"]),
    ]]
    for (prod, unidad), vals in sorted(prod_acum.items()):
        res_rows.append([
            _p(_s(prod),              S["td"]),
            _p(f"{vals['cant']:g}",   S["td_r"]),
            _p(_s(unidad),            S["td"]),
            _p(f"Q{vals['total']:,.2f}", S["td_r"]),
        ])

    rt = Table(res_rows, colWidths=col_w_res, repeatRows=1)
    rt.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),  VERDE_OSC),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[BLANCO, GRIS_TAB]),
        ("FONTSIZE",(0,0),(-1,-1),   8.5),
        ("TOPPADDING",(0,0),(-1,-1), 3),("BOTTOMPADDING",(0,0),(-1,-1),3),
        ("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),
        ("LINEBELOW",(0,0),(-1,0),   1, VERDE_LIM),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ]))
    story.append(rt)

    # ── TOTALES ───────────────────────────────────────────────────────────────
    story.append(Spacer(1, 5*mm))
    base_sin_iva = total_mes / 1.12
    iva_q        = total_mes - base_sin_iva
    isr_q        = base_sin_iva * 0.05

    tot_rows = [
        ["", _p("Total del mes:",    S["tot_lbl"]),
             _p(f"Q {total_mes:,.2f}", S["tot_val"])],
        ["", _p("Base sin IVA:",
                ParagraphStyle("bl",fontSize=9,textColor=GRIS_CARB,alignment=2)),
             _p(f"Q {base_sin_iva:,.2f}",
                ParagraphStyle("bv",fontSize=9,textColor=GRIS_CARB,
                                fontName="Helvetica-Bold",alignment=2))],
        ["", _p("IVA incluido (12%):",
                ParagraphStyle("il",fontSize=9,textColor=GRIS_CARB,alignment=2)),
             _p(f"Q {iva_q:,.2f}",
                ParagraphStyle("iv",fontSize=9,textColor=GRIS_CARB,
                                fontName="Helvetica-Bold",alignment=2))],
        ["", _p("ISR retenido (5% base):",
                ParagraphStyle("irl",fontSize=9,textColor=GRIS_CARB,alignment=2)),
             _p(f"Q {isr_q:,.2f}",
                ParagraphStyle("irv",fontSize=9,textColor=GRIS_CARB,
                                fontName="Helvetica-Bold",alignment=2))],
    ]
    tt = Table(tot_rows, colWidths=[CW-85*mm, 50*mm, 35*mm])
    tt.setStyle(TableStyle([
        ("BACKGROUND",(1,0),(2,0), GRIS_CLR),
        ("LINEABOVE",(1,0),(2,0),  1.5, VERDE_OSC),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LEFTPADDING",(1,0),(1,-1),6),("RIGHTPADDING",(2,0),(2,-1),6),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ]))
    story.append(tt)

    # ── FOOTER ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 8*mm))
    story.append(HRFlowable(width="100%", thickness=2,
                             color=VERDE_LIM, spaceAfter=3))
    story.append(_p("Más fresco, imposible.   ·   VeggiExpress   ·   Guatemala",
                    S["footer"]))

    doc.build(story)
    return buffer.getvalue()


# ── FACTURACIÓN MENSUAL ───────────────────────────────────────────────────────
MESES_ES = {
    1:"Enero", 2:"Febrero", 3:"Marzo", 4:"Abril",
    5:"Mayo", 6:"Junio", 7:"Julio", 8:"Agosto",
    9:"Septiembre", 10:"Octubre", 11:"Noviembre", 12:"Diciembre"
}


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
        logo = RLImage(LOGO_PATH, width=55*mm, height=18*mm)
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
    col_w = [8*mm, 70*mm, 16*mm, 22*mm, 28*mm, CW-8*mm-70*mm-16*mm-22*mm-28*mm]

    # Encabezado de tabla
    encab = [
        _p("#",         S2["th"]),
        _p("Producto",  S2["th"]),
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

            filas_bloque.append([
                _p(str(n_linea),           S2["td"]),
                _p(_s(prod),               S2["td"]),
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
def generar_cotizacion(lineas: list, desde: "date", hasta: "date") -> bytes:
    """
    PDF de cotización de precios para prospección o actualización de precios.
    lineas: [{producto, unidad, precio_cotizar}]
    """
    buffer = BytesIO()
    S = _S()
    CW = CONTENT_W

    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=12*mm, bottomMargin=22*mm,
        title="Cotización de Precios VeggiExpress")
    story = []

    # Header
    if os.path.exists(LOGO_PATH):
        logo = RLImage(LOGO_PATH, width=55*mm, height=18*mm)
    else:
        logo = _p("VeggiExpress", ParagraphStyle("lg", fontSize=18,
                   fontName="Helvetica-Bold", textColor=VERDE_OSC))

    tit_style = ParagraphStyle("ct", fontSize=22, fontName="Helvetica-Bold",
                                textColor=GRIS_CARB, alignment=TA_RIGHT, leading=26)
    sub_style = ParagraphStyle("cs", fontSize=9, fontName="Helvetica-Oblique",
                                textColor=VERDE_OSC, alignment=TA_RIGHT, leading=12)

    ht = Table([[logo, [_p("COTIZACIÓN DE PRECIOS", tit_style),
                        _p(f"Vigente del {desde.strftime('%d/%m/%Y')} "
                           f"al {hasta.strftime('%d/%m/%Y')}", sub_style)]]],
               colWidths=[58*mm, CW-58*mm])
    ht.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                             ("BOTTOMPADDING",(0,0),(-1,-1),4)]))
    story.append(ht)
    story.append(HRFlowable(width="100%", thickness=3, color=VERDE_LIM, spaceAfter=5*mm))

    # Texto introductorio
    intro_style = ParagraphStyle("intro", fontSize=10, textColor=GRIS_CARB,
                                  fontName="Helvetica", leading=15)
    story.append(_p("Estimado Cliente,", ParagraphStyle("sal", fontSize=10,
                    fontName="Helvetica-Bold", textColor=GRIS_CARB, leading=14)))
    story.append(Spacer(1, 2*mm))
    story.append(_p(
        _s(f"A continuación le compartimos nuestro listado de productos y precios "
           f"con vigencia del {desde.day} de {MESES_ES[desde.month]} de {desde.year} "
           f"al {hasta.day} de {MESES_ES[hasta.month]} de {hasta.year}. "
           f"Quedamos atentos a sus comentarios o dudas."),
        intro_style))
    story.append(Spacer(1, 5*mm))

    # Tabla de productos
    col_w = [CW*0.55, CW*0.20, CW*0.25]
    header = [_p("Producto", S["th"]), _p("Unidad", S["th"]),
              _p("Precio", S["th_r"])]
    rows = [header]
    for l in lineas:
        rows.append([
            _p(_s(l["producto"]), S["td"]),
            _p(_s(l["unidad"]),   S["td"]),
            _p(f"Q {l['precio_cotizar']:,.2f}", S["td_r"]),
        ])

    pt = Table(rows, colWidths=col_w, repeatRows=1)
    pt.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  VERDE_OSC),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [BLANCO, GRIS_TAB]),
        ("FONTSIZE",      (0,0),(-1,-1), 9),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("RIGHTPADDING",  (0,0),(-1,-1), 6),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("LINEBELOW",     (0,-1),(-1,-1),0.8, VERDE_OSC),
    ]))
    story.append(pt)
    story.append(Spacer(1, 6*mm))

    # Nota y firma
    nota_style = ParagraphStyle("nota", fontSize=8, fontName="Helvetica-Oblique",
                                 textColor=colors.HexColor("#888888"), leading=11)
    firma_style = ParagraphStyle("firma", fontSize=9, fontName="Helvetica",
                                  textColor=GRIS_CARB, leading=13)

    story.append(_p(_s("Precios sujetos a cambios por disponibilidad."), nota_style))
    story.append(Spacer(1, 4*mm))
    story.append(_p("Saludos cordiales,", firma_style))
    story.append(Spacer(1, 1*mm))
    story.append(_p("<b>Sergio Burgos Alburez</b>", ParagraphStyle("fn",
                    fontSize=9, fontName="Helvetica-Bold",
                    textColor=GRIS_CARB, leading=12)))
    story.append(_p("Tel. 5874-9679", firma_style))

    story.append(Spacer(1, 8*mm))
    story.append(HRFlowable(width="100%", thickness=2, color=VERDE_LIM, spaceAfter=3))
    story.append(_p(_s("Más fresco, imposible.   ·   VeggiExpress   ·   Guatemala"),
                    S["footer"]))

    doc.build(story)
    return buffer.getvalue()


# ── LISTA DE COMPRAS A PROVEEDORES ──────────────────────────────────────────
def generar_lista_compras(por_proveedor: dict, semana: int, año: int) -> bytes:
    """
    PDF compacto B&W — dos proveedores por fila en landscape.
    Sin fondos de color. Solo líneas de tabla. Columnas numéricas centradas.
    """
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib           import colors as rl_colors

    buffer = BytesIO()
    PW, PH = landscape(A4)          # 841 × 595 pt  (297 × 210 mm)
    ML = MR = 10*mm
    MT = MB = 8*mm
    CW = PW - ML - MR               # ancho total disponible
    GAP = 4*mm                      # espacio entre las dos columnas
    HW = (CW - GAP) / 2             # ancho de cada mitad

    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
        leftMargin=ML, rightMargin=MR, topMargin=MT, bottomMargin=MB,
        title=f"Lista Compras Sem {semana}/{año}")
    story = []

    # ── Estilos B&W ──────────────────────────────────────────────────────────
    NEGRO  = rl_colors.black
    GRIS_L = rl_colors.HexColor("#F0F0F0")   # solo para separar, no se usa en fill

    def sty(name, **kw):
        base = dict(fontSize=7, fontName="Helvetica",
                    textColor=NEGRO, leading=9)
        base.update(kw)
        return ParagraphStyle(name, **base)

    s_hdr   = sty("h",   fontName="Helvetica-Bold", fontSize=7)
    s_prov  = sty("p",   fontName="Helvetica-Bold", fontSize=8, leading=10)
    s_col   = sty("c",   fontName="Helvetica-Bold", fontSize=6.5)
    s_col_c = sty("cc",  fontName="Helvetica-Bold", fontSize=6.5,
                  alignment=TA_CENTER)
    s_td    = sty("td")
    s_td_c  = sty("tdc", alignment=TA_CENTER)
    s_td_b  = sty("tdb", fontName="Helvetica-Bold", alignment=TA_CENTER)
    s_td_p  = sty("tdp", fontName="Helvetica-Bold", alignment=TA_CENTER,
                  textColor=rl_colors.HexColor("#555555"))

    # ── Header global ─────────────────────────────────────────────────────────
    s_title = ParagraphStyle("tit", fontSize=10, fontName="Helvetica-Bold",
                              textColor=NEGRO, leading=12)
    s_sub   = ParagraphStyle("sub", fontSize=7,  fontName="Helvetica",
                              textColor=NEGRO, alignment=TA_RIGHT, leading=9)

    hdr_tbl = Table([[
        _p(f"Lista de Compras — Semana {semana} / {año}", s_title),
        _p(f"VeggiExpress  ·  "
           f"{__import__('datetime').date.today().strftime('%d/%m/%Y')}", s_sub),
    ]], colWidths=[CW*0.6, CW*0.4])
    hdr_tbl.setStyle(TableStyle([
        ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),(-1,-1), 0),
        ("BOTTOMPADDING", (0,0),(-1,-1), 2),
    ]))
    story.append(hdr_tbl)
    story.append(HRFlowable(width="100%", thickness=1, color=NEGRO,
                             spaceAfter=3*mm))

    # ── Columnas por mitad ────────────────────────────────────────────────────
    # Producto | Unidad | Pedido | A Comprar
    cw = [HW*0.52, HW*0.15, HW*0.15, HW*0.18]

    BORDE = TableStyle([
        ("BOX",         (0,0), (-1,-1), 0.5, NEGRO),
        ("INNERGRID",   (0,0), (-1,-1), 0.3, NEGRO),
        ("TOPPADDING",  (0,0), (-1,-1), 1.5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 1.5),
        ("LEFTPADDING", (0,0), (-1,-1), 3),
        ("RIGHTPADDING",(0,0), (-1,-1), 3),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
    ])

    def _supplier_block(prov, items):
        """Construye la sub-tabla B&W de un proveedor."""
        rows = []

        # Fila nombre proveedor (span completo, negrita, sin fill)
        rows.append([
            _p(_s(prov), s_prov), "", "", ""
        ])

        # Encabezados de columna
        rows.append([
            _p("Producto",  s_col),
            _p("Unidad",    s_col_c),
            _p("Pedido",    s_col_c),
            _p("A Comprar", s_col_c),
        ])

        for item in items:
            a = item.get("a_comprar", "")
            es_p = (str(a).upper() == "P")
            rows.append([
                _p(_s(item["producto"]), s_td),
                _p(_s(item["unidad"]),   s_td_c),
                _p(f"{item['cantidad']:,.1f}", s_td_c),
                _p("PEND." if es_p else str(a), s_td_p if es_p else s_td_b),
            ])

        tbl = Table(rows, colWidths=cw)
        ts  = TableStyle([
            # Proveedor header
            ("SPAN",          (0,0), (-1,0)),
            ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,0), 8),
            ("LINEBELOW",     (0,0), (-1,0), 0.5, NEGRO),
            # Encabezados col
            ("FONTNAME",      (0,1), (-1,1), "Helvetica-Bold"),
            ("FONTSIZE",      (0,1), (-1,1), 6.5),
            ("LINEBELOW",     (0,1), (-1,1), 0.5, NEGRO),
            # Grid general
            ("BOX",           (0,0), (-1,-1), 0.5, NEGRO),
            ("INNERGRID",     (0,0), (-1,-1), 0.25, NEGRO),
            ("TOPPADDING",    (0,0), (-1,-1), 1.5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 1.5),
            ("LEFTPADDING",   (0,0), (-1,-1), 3),
            ("RIGHTPADDING",  (0,0), (-1,-1), 3),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            # Alineación centrada en columnas numéricas
            ("ALIGN",         (1,0), (-1,-1), "CENTER"),
        ])
        tbl.setStyle(ts)
        return tbl

    # ── Layout dos columnas por fila ──────────────────────────────────────────
    provs = list(por_proveedor.keys())

    for i in range(0, len(provs), 2):
        left_prov  = provs[i]
        right_prov = provs[i+1] if i+1 < len(provs) else None

        left_blk  = _supplier_block(left_prov, por_proveedor[left_prov])
        right_blk = (_supplier_block(right_prov, por_proveedor[right_prov])
                     if right_prov else Spacer(HW, 1))

        # Fila par: dos proveedores lado a lado
        pair = Table([[left_blk, right_blk]],
                     colWidths=[HW, HW],
                     hAlign="LEFT")
        pair.setStyle(TableStyle([
            ("VALIGN",         (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING",    (0,0), (-1,-1), 0),
            ("RIGHTPADDING",   (0,0), (0,-1),  GAP/2),
            ("RIGHTPADDING",   (1,0), (1,-1),  0),
            ("TOPPADDING",     (0,0), (-1,-1), 0),
            ("BOTTOMPADDING",  (0,0), (-1,-1), 0),
        ]))
        story.append(pair)
        story.append(Spacer(1, 3*mm))

    # ── Pie ───────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 2*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=NEGRO,
                             spaceAfter=1))
    story.append(_p(_s("VeggiExpress  ·  Más fresco, imposible."),
                    ParagraphStyle("ft", fontSize=6, fontName="Helvetica-Oblique",
                                   textColor=NEGRO, alignment=TA_CENTER,
                                   leading=8)))

    doc.build(story)
    return buffer.getvalue()
