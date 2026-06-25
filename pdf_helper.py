"""
pdf_helper.py — Generación de PDFs para VeggiExpress
Organizado en secciones: Helpers | Envíos | Facturación | Cotización | Proveedores | Checklist | Remisión

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
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)
from reportlab.platypus import Image as RLImage

# ── BRAND COLORS ──────────────────────────────────────────────────────────────
VERDE_OSC = colors.HexColor('#2D7A2D')

# Meses en español (nivel de módulo, reutilizable desde otros módulos)
_MESES_ES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo",
             6: "junio", 7: "julio", 8: "agosto", 9: "septiembre",
             10: "octubre", 11: "noviembre", 12: "diciembre"}
VERDE_LIM = colors.HexColor('#8DC63F')
GRIS_CARB = colors.HexColor('#4A4A4A')
GRIS_CLR  = colors.HexColor('#F5F5F5')
GRIS_TAB  = colors.HexColor('#F0F8F0')
BLANCO    = colors.white

LOGO_PATH = "VeggiExpress-02.png"


def _logo_proporcional(ancho_mm: float):
    """Carga el logo escalado al ancho dado, MANTENIENDO la relación de aspecto.
    Lee las dimensiones reales de la imagen y calcula el alto proporcional,
    así el logo nunca se ve estirado ni achatado. Si falla, retorna None."""
    import os
    from reportlab.platypus import Image as _RLImg
    from reportlab.lib.units import mm as _mm
    if not os.path.exists(LOGO_PATH):
        return None
    try:
        from reportlab.lib.utils import ImageReader
        iw, ih = ImageReader(LOGO_PATH).getSize()   # dimensiones reales en px
        ratio = ih / iw if iw else 0.3
        ancho = ancho_mm * _mm
        alto  = ancho * ratio                       # alto proporcional
        return _RLImg(LOGO_PATH, width=ancho, height=alto)
    except Exception:
        return None
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
def generar_cotizacion(lineas: list, desde: "date", hasta: "date",
                       cotizador: str = "", cotizador_tel: str = "",
                       notas: str = "") -> bytes:
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
        logo = _logo_proporcional(40) or RLImage(LOGO_PATH, width=40*mm, height=12*mm)
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

    _notas_txt = notas.strip() if notas and notas.strip() \
                 else "Precios sujetos a cambios por disponibilidad."
    for linea_nota in _notas_txt.splitlines():
        if linea_nota.strip():
            story.append(_p(_s(linea_nota.strip()), nota_style))
    story.append(Spacer(1, 4*mm))
    story.append(_p("Saludos cordiales,", firma_style))
    story.append(Spacer(1, 1*mm))
    _nombre_firma = cotizador if cotizador else "Sergio Burgos Alburez"
    _tel_firma    = cotizador_tel if cotizador_tel else "Tel. 5874-9679"
    story.append(_p(f"<b>{_s(_nombre_firma)}</b>", ParagraphStyle("fn",
                    fontSize=9, fontName="Helvetica-Bold",
                    textColor=GRIS_CARB, leading=12)))
    story.append(_p(_s(_tel_firma), firma_style))

    story.append(Spacer(1, 8*mm))
    story.append(HRFlowable(width="100%", thickness=2, color=VERDE_LIM, spaceAfter=3))
    story.append(_p(_s("Más fresco, imposible.   ·   VeggiExpress   ·   Guatemala"),
                    S["footer"]))

    doc.build(story)
    return buffer.getvalue()


# ── LISTA DE COMPRAS A PROVEEDORES ──────────────────────────────────────────

def generar_cotizacion_formal(
    lineas: list,           # [{producto, unidad, especificacion, volumen_semanal, precio_cotizar}]
    desde: "date",
    hasta: "date",
    empresa: str = "",
    atencion: str = "",
    cuerpo: str = "",
    cotizador: str = "",
    cotizador_tel: str = "",
    num_cot: str = "",
    notas: str = "",
    condiciones_txt: str = "",
    mostrar_total_col: bool = False,
    mostrar_total_fila: bool = False,
) -> bytes:
    """
    PDF de cotizacion formal para empresas procesadoras.
    Membrete VeggiExpress + cuerpo de presentacion + tabla de productos
    con especificacion y volumen semanal + condiciones + firma.
    """
    from reportlab.platypus import KeepTogether

    def _fecha_es(d):
        return f"{d.day:02d}/{d.month:02d}/{d.year}"
    def _fecha_larga_es(d):
        return f"{d.day} de {_MESES_ES[d.month]} de {d.year}"

    buffer = BytesIO()
    S_base = _S()

    # Estilos adicionales para cotizacion formal
    def sty(name, **kw):
        defaults = dict(fontName="Helvetica", fontSize=9,
                        textColor=GRIS_CARB, leading=13)
        defaults.update(kw)
        return ParagraphStyle(name, **defaults)

    S = {
        **S_base,
        "cot_titulo":  sty("cot_titulo",  fontSize=22, fontName="Helvetica-Bold",
                            textColor=GRIS_CARB, alignment=TA_RIGHT, leading=26),
        "cot_sub":     sty("cot_sub",     fontSize=9,  fontName="Helvetica-Oblique",
                            textColor=VERDE_OSC, alignment=TA_RIGHT, leading=12),
        "cot_num":     sty("cot_num",     fontSize=8,  textColor=GRIS_CARB,
                            alignment=TA_RIGHT, leading=11),
        "dest_lbl":    sty("dest_lbl",    fontSize=7.5, fontName="Helvetica-Bold",
                            textColor=VERDE_OSC, leading=10),
        "dest_empresa":sty("dest_empresa",fontSize=11, fontName="Helvetica-Bold",
                            textColor=GRIS_CARB, leading=15),
        "dest_info":   sty("dest_info",   fontSize=9,  textColor=GRIS_CARB, leading=12),
        "cuerpo":      sty("cuerpo",      fontSize=9.5, textColor=GRIS_CARB,
                            leading=14, spaceAfter=4),
        "cond_titulo": sty("cond_titulo", fontSize=8.5, fontName="Helvetica-Bold",
                            textColor=VERDE_OSC, leading=11, spaceBefore=6),
        "cond_item":   sty("cond_item",   fontSize=8.5, textColor=GRIS_CARB, leading=11),
        "firma_nombre":sty("firma_nombre",fontSize=9, fontName="Helvetica-Bold",
                            textColor=GRIS_CARB, alignment=TA_CENTER, leading=13),
        "firma_cargo": sty("firma_cargo", fontSize=7.5, textColor=GRIS_CARB,
                            alignment=TA_CENTER, leading=11),
        "brand_footer":sty("brand_footer",fontSize=8, fontName="Helvetica-Oblique",
                            textColor=GRIS_CARB, alignment=TA_CENTER, leading=10),
    }

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=12*mm, bottomMargin=20*mm,
        title=f"Cotizacion Formal VeggiExpress {num_cot}",
    )
    story = []
    CW = PAGE_W - 36*mm

    # ── 1. HEADER: Logo + Titulo + Numero ─────────────────────────────────────
    if os.path.exists(LOGO_PATH):
        logo = _logo_proporcional(40) or RLImage(LOGO_PATH, width=40*mm, height=12*mm)
    else:
        logo = _p("VeggiExpress", ParagraphStyle("lg", fontSize=18,
                  fontName="Helvetica-Bold", textColor=VERDE_OSC))

    _cot_titulo_sm = ParagraphStyle("cot_titulo_sm", parent=S["cot_titulo"],
                                     fontSize=13, leading=16)
    hdr_right = [
        _p("COTIZACION COMERCIAL", _cot_titulo_sm),
        Spacer(1, 2*mm),
        _p(f"Fecha: {_fecha_es(desde)}", S["cot_num"]),
        _p(f"Valida hasta: {_fecha_es(hasta)}", S["cot_num"]),
    ]

    ht = Table([[logo, hdr_right]], colWidths=[55*mm, CW - 55*mm])
    ht.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("ALIGN",  (1,0), (1,0),   "RIGHT"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))
    story.append(ht)
    story.append(Spacer(1, 4*mm))
    story.append(HRFlowable(width=CW, color=VERDE_OSC, thickness=1.5))
    story.append(Spacer(1, 4*mm))

    # ── 2. DESTINATARIO (ancho completo) ───────────────────────────────────────
    dest_block = [
        _p("A:", S["dest_lbl"]),
        _p(_s(empresa) or "Empresa", S["dest_empresa"]),
    ]
    if atencion:
        dest_block.append(_p(f"A la atencion de: {_s(atencion)}", S["dest_info"]))

    sec_table = Table([[dest_block]], colWidths=[CW])
    sec_table.setStyle(TableStyle([
        ("VALIGN",  (0,0), (-1,-1), "TOP"),
        ("ALIGN",   (0,0), (0,0),   "LEFT"),
        ("LEFTPADDING",  (0,0), (0,0), 8),
        ("BACKGROUND",   (0,0), (0,0), GRIS_TAB),
        ("ROUNDEDCORNERS", [3]),
        ("TOPPADDING",   (0,0), (0,0), 6),
        ("BOTTOMPADDING",(0,0), (0,0), 6),
    ]))
    story.append(sec_table)
    story.append(Spacer(1, 5*mm))

    # ── 4. CUERPO DE PRESENTACION ─────────────────────────────────────────────
    if cuerpo:
        _cuerpo_just = ParagraphStyle("cuerpo_just", fontSize=9.5,
            textColor=GRIS_CARB, leading=14, alignment=TA_JUSTIFY, spaceAfter=4)
        for parrafo in _s(cuerpo).split("\n"):
            if parrafo.strip():
                story.append(_p(parrafo.strip(), _cuerpo_just))
            else:
                story.append(Spacer(1, 2*mm))
        story.append(Spacer(1, 3*mm))

    # ── 5. TABLA DE PRODUCTOS ─────────────────────────────────────────────────
    # Columnas dinámicas según checkboxes
    # Base: No. | Producto | Especificacion | Vol. Semanal | Precio/u
    # Opcional: + Total Est./sem. (columna por fila)
    cols_def = [
        ("No.",            8*mm,    "right"),
        ("Producto",       None,    "left"),
        ("Especificacion", None,    "left"),
        ("Vol. Semanal",   None,    "right"),
        ("Precio/u",       None,    "right"),
    ]
    if mostrar_total_col:
        cols_def.append(("Total Est./Sem.", None, "right"))

    # Anchos proporcionales según si hay columna total o no
    if mostrar_total_col:
        anchos_prop = [8*mm, CW*0.22, CW*0.27, CW*0.13, CW*0.12, CW*0.16]
    else:
        anchos_prop = [8*mm, CW*0.28, CW*0.34, CW*0.16, CW*0.14]
    col_w = anchos_prop
    ncols = len(col_w)

    th_sty = TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), VERDE_OSC),
        ("TEXTCOLOR",     (0,0), (-1,0), BLANCO),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,0), 8.5),
        ("ALIGN",         (0,0), (-1,0), "CENTER"),
        ("VALIGN",        (0,0), (-1,-1),"MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("RIGHTPADDING",  (0,0), (-1,-1), 4),
        ("ALIGN",         (3,1), (ncols-1,-1), "RIGHT"),
        ("FONTSIZE",      (0,1), (-1,-1), 8.5),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [BLANCO, GRIS_TAB]),
        ("GRID",          (0,0), (-1,-1), 0.3, colors.HexColor("#CCCCCC")),
        ("VALIGN",        (0,1), (-1,-1), "TOP"),
    ])

    def _th(txt):
        return _p(txt, ParagraphStyle("th_f", fontName="Helvetica-Bold",
                  fontSize=8.5, textColor=BLANCO, alignment=TA_CENTER, leading=11))
    def _td(txt, right=False):
        al = TA_RIGHT if right else TA_LEFT
        return _p(txt, ParagraphStyle("td_f", fontSize=8.5,
                  textColor=GRIS_CARB, alignment=al, leading=11))

    encabezados = [_th(c[0]) for c in cols_def]
    tbl_data = [encabezados]

    total_semana = 0.0
    for i, l in enumerate(lineas, 1):
        vol   = float(l.get("volumen_semanal") or 0)
        prec  = float(l.get("precio_cotizar")  or 0)
        total = vol * prec
        total_semana += total

        vol_txt  = f"{vol:,.0f} {l.get('unidad','lbs')}" if vol else "—"
        prec_txt = f"Q{prec:,.2f}" if prec else "—"

        fila = [
            _td(str(i),                    right=True),
            _td(_s(l.get("producto",""))),
            _td(_s(l.get("especificacion",""))),
            _td(vol_txt,                   right=True),
            _td(prec_txt,                  right=True),
        ]
        if mostrar_total_col:
            total_txt = f"Q{total:,.2f}" if total else "—"
            fila.append(_td(total_txt, right=True))
        tbl_data.append(fila)

    # Fila de total general (opcional)
    if mostrar_total_fila:
        fila_total = [_p("", S["td"]) for _ in range(ncols)]
        # Etiqueta en penúltima columna, valor en última
        fila_total[ncols-2] = _p("TOTAL SEMANAL EST.",
            ParagraphStyle("tot_lbl_f", fontSize=8.5, fontName="Helvetica-Bold",
                           textColor=VERDE_OSC, alignment=TA_RIGHT, leading=11))
        fila_total[ncols-1] = _p(f"Q{total_semana:,.2f}",
            ParagraphStyle("tot_val_f", fontSize=9.5, fontName="Helvetica-Bold",
                           textColor=GRIS_CARB, alignment=TA_RIGHT, leading=12))
        tbl_data.append(fila_total)
        th_sty.add("BACKGROUND", (0, len(tbl_data)-1), (-1, len(tbl_data)-1), GRIS_CLR)
        th_sty.add("LINEABOVE",  (0, len(tbl_data)-1), (-1, len(tbl_data)-1), 1.0, VERDE_OSC)
    else:
        th_sty.add("LINEBELOW", (0,-1), (-1,-1), 0.8, VERDE_OSC)

    prod_tbl = Table(tbl_data, colWidths=col_w, repeatRows=1)
    prod_tbl.setStyle(th_sty)
    story.append(prod_tbl)
    story.append(Spacer(1, 5*mm))


    # Estilo justificado para párrafos de observaciones/condiciones
    cond_just = ParagraphStyle("cond_just", fontSize=9.5, textColor=GRIS_CARB,
                                leading=14, alignment=TA_JUSTIFY, spaceAfter=4)

    # ── 6. OBSERVACIONES (sin subtítulo, párrafos justificados) ────────────────
    if notas and notas.strip():
        for bloque in _s(notas).split("\n"):
            if bloque.strip():
                story.append(_p(bloque.strip(), cond_just))
            else:
                story.append(Spacer(1, 2*mm))   # preserva el salto de párrafo
        story.append(Spacer(1, 4*mm))

    # ── 7. CONDICIONES GENERALES (abajo, editable, justificadas) ───────────────
    if condiciones_txt and condiciones_txt.strip():
        cond_lineas = [l for l in _s(condiciones_txt).split("\n")]
    else:
        # Precargadas por default
        cond_lineas = [
            "Moneda: Quetzales guatemaltecos (GTQ), precios sin IVA.",
            "Calidad: Productos frescos de primera calidad, seleccionados y calibrados.",
            "Entrega: Sujeto a programa y volumen acordado con el cliente.",
            "Empaque: Segun especificacion del cliente o estandar VeggiExpress.",
            f"Validez de la cotizacion: {_fecha_larga_es(hasta)}.",
            "Precios sujetos a variacion por condiciones de mercado fuera del periodo de vigencia.",
        ]

    story.append(_p("CONDICIONES GENERALES", S["cond_titulo"]))
    for cond in cond_lineas:
        cs = cond.strip()
        if not cs:
            continue
        # Si el usuario ya puso viñeta, no duplicar
        txt = cs if cs.startswith(("•", "-", "·")) else f"• {cs}"
        story.append(_p(txt, cond_just))
    story.append(Spacer(1, 3*mm))

    # ── 7. CIERRE Y FIRMA ─────────────────────────────────────────────────────
    cierre = ("Quedamos a sus ordenes para cualquier consulta, ajuste en "
              "especificaciones o coordinacion de visita. Esperamos poder "
              "ser su proveedor de confianza.")
    _cierre_just = ParagraphStyle("cierre_just", fontSize=9.5, textColor=GRIS_CARB,
                                   leading=14, alignment=TA_JUSTIFY)
    story.append(_p(cierre, _cierre_just))
    story.append(Spacer(1, 5*mm))

    # Firma (espacios reducidos para entrar en una página)
    firma_tel = cotizador_tel or "Tel. 5874-9679"
    firma_data = [[
        [
            Spacer(1, 5*mm),
            HRFlowable(width=45*mm, color=GRIS_CARB, thickness=0.7),
            Spacer(1, 1.5*mm),
            _p(_s(cotizador) or "VeggiExpress", S["firma_nombre"]),
            _p("Gerente de Produccion y Comercializacion", S["firma_cargo"]),
            _p("VeggiExpress  |  Productos Alimenticios Super Bueno", S["firma_cargo"]),
            _p(f"{firma_tel}  |  sburgosa@gmail.com", S["firma_cargo"]),
        ]
    ]]
    firma_tbl = Table(firma_data, colWidths=[CW])
    firma_tbl.setStyle(TableStyle([("ALIGN", (0,0), (-1,-1), "CENTER")]))
    story.append(firma_tbl)

    # Footer (espacios reducidos)
    story.append(Spacer(1, 4*mm))
    story.append(HRFlowable(width=CW, color=VERDE_LIM, thickness=0.8))
    story.append(Spacer(1, 1.5*mm))
    story.append(_p(
        "VeggiExpress  |  Productos Alimenticios Super Bueno  |  "
        "Guatemala  |  sburgosa@gmail.com  |  5874-9679",
        S["brand_footer"]))

    doc.build(story)
    return buffer.getvalue()


def generar_lista_compras_proveedor(prov: str, items: list,
                                    semana: int, año: int) -> bytes:
    """
    PDF portrait A4 B&W para UN proveedor.
    Columnas: Producto | Unidad | Antigua | Río | Hogares | Total | A Comprar
    Máx 50 filas por página — paginación manual con header y footer en cada página.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib           import colors as rc
    from reportlab.platypus      import PageBreak
    from datetime import date as _date

    buf   = BytesIO()
    ML = MR = 12*mm
    MT = MB = 10*mm
    PW, PH = A4
    CW = PW - ML - MR          # ancho útil

    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=ML, rightMargin=MR,
        topMargin=MT, bottomMargin=MB,
        title=f"{prov} · Sem {semana}/{año}")

    story = []
    NEGRO = rc.black
    HOY   = _date.today().strftime("%d/%m/%Y")
    ROWS_PER_PAGE = 50

    def ts(name, **kw):
        d = dict(fontSize=7, fontName="Helvetica", textColor=NEGRO, leading=9)
        d.update(kw); return ParagraphStyle(name, **d)

    s_title = ts("tit", fontSize=10, fontName="Helvetica-Bold", leading=12)
    s_sub   = ts("sub", fontSize=7,  alignment=TA_RIGHT)
    s_th    = ts("th",  fontSize=6.5, fontName="Helvetica-Bold", alignment=TA_CENTER)
    s_th_l  = ts("thl", fontSize=6.5, fontName="Helvetica-Bold")
    s_td    = ts("td",  fontSize=7)
    s_td_c  = ts("tdc", fontSize=7,  alignment=TA_CENTER)
    s_td_b  = ts("tdb", fontSize=7,  fontName="Helvetica-Bold", alignment=TA_CENTER)
    s_ft    = ParagraphStyle("ft", fontSize=6, fontName="Helvetica-Oblique",
                              textColor=NEGRO, alignment=TA_CENTER, leading=8)

    # ── Anchos de columna ────────────────────────────────────────────────────
    wP  = CW * 0.32
    wU  = CW * 0.10
    wA  = CW * 0.13
    wT  = CW * 0.09
    wC  = CW * 0.10
    col_w = [wP, wU, wA, wA, wA, wT, wC]

    # ── Fila de encabezado de columnas ───────────────────────────────────────
    def header_row():
        return [
            _p("Producto",  s_th_l),
            _p("Unidad",    s_th),
            _p("Antigua",   s_th),
            _p("Río",       s_th),
            _p("Hogares",   s_th),
            _p("Total",     s_th),
            _p("A Comprar", s_th),
        ]

    def data_row(it):
        def area_val(a):
            v = float(it.get(a, 0) or 0)
            return _p(f"{v:g}" if v > 0 else "—", s_td_c)
        a_cmp = it.get("a_comprar", "")
        cmp   = _p("PEND." if str(a_cmp).upper() == "P" else str(a_cmp), s_td_b)
        return [
            _p(_s(it["producto"]),          s_td),
            _p(_s(it.get("unidad", "")),    s_td_c),
            area_val("Antigua"),
            area_val("Río"),
            area_val("Hogares"),
            _p(f"{float(it.get('cantidad', 0) or 0):g}", s_td_c),
            cmp,
        ]

    def table_style(n_rows):
        return TableStyle([
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 7),
            ("LINEBELOW",     (0, 0), (-1, 0),  0.8, NEGRO),
            ("BOX",           (0, 0), (-1, -1), 0.5, NEGRO),
            ("INNERGRID",     (0, 0), (-1, -1), 0.25, NEGRO),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING",   (0, 0), (-1, -1), 2),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 2),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),

        ])

    def page_header(page_num, total_pages):
        hdr = Table([[
            _p(_s(f"A Pedir: {prov}"), s_title),
            _p(f"Semana {semana}/{año}  ·  {HOY}"
               + (f"  ·  Pág. {page_num}/{total_pages}"
                  if total_pages > 1 else ""), s_sub),
        ]], colWidths=[CW * 0.6, CW * 0.4])
        hdr.setStyle(TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return hdr

    def page_footer():
        return _p(_s("VeggiExpress  ·  Más fresco, imposible."), s_ft)

    # ── Paginar items en chunks de ROWS_PER_PAGE ─────────────────────────────
    chunks = [items[i:i + ROWS_PER_PAGE]
              for i in range(0, max(len(items), 1), ROWS_PER_PAGE)]
    total_pages = len(chunks)

    for page_idx, chunk in enumerate(chunks):
        if page_idx > 0:
            story.append(PageBreak())

        # Header
        story.append(page_header(page_idx + 1, total_pages))
        story.append(HRFlowable(width="100%", thickness=1,
                                 color=NEGRO, spaceAfter=2*mm))

        # Tabla de datos
        rows = [header_row()] + [data_row(it) for it in chunk]
        tbl = Table(rows, colWidths=col_w, splitByRow=False)
        tbl.setStyle(table_style(len(chunk)))
        story.append(tbl)

        # Footer
        story.append(Spacer(1, 3*mm))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                 color=NEGRO, spaceAfter=1))
        story.append(page_footer())

    doc.build(story)
    return buf.getvalue()


def generar_listado_checklist(clientes_grupos: list,
                               area_label: str,
                               semana: int, año: int) -> bytes:
    """
    Portrait A4, 2 columnas (Frames), sin colores.
    clientes_grupos: [(nombre_cliente, [rows])]
      donde rows = [{cliente, producto, unidad, cantidad}]
    - Cada cliente es una mini-tabla KeepTogether (nunca se corta)
    - Clientes muy grandes se dividen en 2 mitades (misma página si cabe)
    - Header dibujado por callback por página
    """
    from reportlab.lib.pagesizes   import A4
    from reportlab.lib             import colors as rc
    from reportlab.platypus        import KeepTogether, FrameBreak
    from reportlab.platypus.doctemplate import (BaseDocTemplate,
                                                 PageTemplate, Frame)
    from reportlab.pdfbase         import pdfmetrics
    from datetime                  import date
    from io                        import BytesIO as _BIO

    buf = _BIO()
    PW, PH = A4
    # Márgenes seguros para impresoras (área no imprimible típica ~10-12mm).
    # Antes 8mm laterales hacía que se cortaran líneas al imprimir.
    ML = MR = 12*mm
    MB = 12*mm
    HEADER_H = 24*mm        # espacio reservado arriba para el header
    MT = HEADER_H + 5*mm    # margen superior = header + pequeño gap

    GAP = 4*mm
    HW  = (PW - ML - MR - GAP) / 2   # ancho de cada columna ~94mm
    FH  = PH - MT - MB               # altura del frame de contenido ~680pt

    # ── Estilos ───────────────────────────────────────────────────────────────
    NEGRO  = rc.black
    BLANCO = rc.white

    def sty(name, **kw):
        d = dict(fontSize=8, fontName="Helvetica",
                 textColor=NEGRO, leading=10)
        d.update(kw)
        return ParagraphStyle(name, **d)

    s_col = sty("col", fontSize=7.5, fontName="Helvetica-Bold",
                alignment=TA_CENTER)
    s_td  = sty("td")
    s_tdc = sty("tdc", alignment=TA_CENTER)

    # Anchos dentro de cada frame
    wC = HW * 0.29; wP = HW * 0.36
    wU = HW * 0.13; wQ = HW * 0.12; wX = HW * 0.10
    COL_W = [wC, wP, wU, wQ, wX]

    BASE_STYLE = TableStyle([
        ("FONTNAME",     (0,0),(-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0,0),(-1,-1), 8),
        ("LINEBELOW",    (0,0),(-1,0),  0.8, NEGRO),
        ("BOX",          (0,0),(-1,-1), 0.5, NEGRO),
        ("INNERGRID",    (0,0),(-1,-1), 0.3, NEGRO),
        ("TOPPADDING",   (0,0),(-1,-1), 1.5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 1.5),
        ("LEFTPADDING",  (0,0),(-1,-1), 2),
        ("RIGHTPADDING", (0,0),(-1,-1), 2),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("ALIGN",        (2,0),(-1,-1), "CENTER"),
    ])

    HDR_ROW = [
        _p("Cliente",  s_col), _p("Producto", s_col),
        _p("Unidad",   s_col), _p("Cant.",    s_col),
        _p("□",        s_col),
    ]

    def make_mini_table(rows_subset):
        """Mini-tabla para un bloque de filas de UN cliente."""
        trows = [HDR_ROW]
        for r in rows_subset:
            trows.append([
                _p(_s(r["cliente"]),  s_td),
                _p(_s(r["producto"]), s_td),
                _p(_s(r["unidad"]),   s_tdc),
                _p(f"{r['cantidad']:g}", s_tdc),
                "",
            ])
        t = Table(trows, colWidths=COL_W)
        t.setStyle(BASE_STYLE)
        return t

    # ── Máximo de filas por bloque ─────────────────────────────────────────────
    CAP = 48

    # ── Construir story midiendo alturas para forzar salto de columna ──────────
    # Medimos cuánto se llenó la columna. Cuando un pedido no cabe en lo que
    # resta, FrameBreak lo manda COMPLETO a la otra columna (no se desborda).
    story = []
    _usado = [0.0]
    _EPS = 2 * mm

    def _emitir(tbl):
        _w, _h = tbl.wrap(HW, FH)
        if _usado[0] > 0 and (_usado[0] + _h) > (FH - _EPS):
            story.append(FrameBreak())
            _usado[0] = 0.0
        story.append(KeepTogether(tbl))
        _usado[0] += _h

    for nombre, rows in clientes_grupos:
        if len(rows) <= CAP:
            _emitir(make_mini_table(rows))
        else:
            for _ini in range(0, len(rows), CAP):
                _emitir(make_mini_table(rows[_ini:_ini + CAP]))

    # ── Callback: header por página ───────────────────────────────────────────
    today = date.today().strftime("%d/%m/%Y")
    from reportlab.pdfgen import canvas as cv_mod

    def draw_header(canvas, doc):
        canvas.saveState()
        y_line = PH - HEADER_H + 2
        # Título
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(ML, y_line + 8, "VeggiExpress — Listado de Empaque")
        # Info derecha
        canvas.setFont("Helvetica", 7)
        info = (f"Área: {area_label}  ·  "
                f"Semana {semana}/{año}  ·  {today}  ·  "
                f"Pág. {doc.page}")
        canvas.drawRightString(PW - MR, y_line + 8, info)
        # Línea separadora
        canvas.setLineWidth(0.8)
        canvas.line(ML, y_line, PW - MR, y_line)
        canvas.restoreState()

    # ── Frames: 2 columnas por página ─────────────────────────────────────────
    frame_l = Frame(ML,          MB, HW, FH,
                    leftPadding=0, rightPadding=0,
                    topPadding=0,  bottomPadding=0, id="left")
    frame_r = Frame(ML + HW + GAP, MB, HW, FH,
                    leftPadding=0, rightPadding=0,
                    topPadding=0,  bottomPadding=0, id="right")

    page_tpl = PageTemplate(id="TwoCol",
                             frames=[frame_l, frame_r],
                             onPage=draw_header)

    doc = BaseDocTemplate(buf, pagesize=A4,
                          pageTemplates=[page_tpl])
    doc.build(story)
    return buf.getvalue()



# ── REMISIÓN / NOTA DE ENTREGA ────────────────────────────────────────────────
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
        total_gral += float(l["total"] or 0)
        rows.append([
            _p(_s(l["producto"]),       s_td),
            _p(_s(l["unidad"]),         s_td_c),
            _p(f"{l['cantidad']:g}",    s_td_c),
            _p(f"Q {l['total']:,.2f}",  s_td_r),
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
def boton_imprimir_html(pdf_bytes: bytes, fn_id: str,
                        label: str = "Imprimir",
                        color: str = "#2D7A2D") -> str:
    """
    Genera el HTML+JS de un botón que abre el PDF en nueva pestaña e imprime.
    Patrón unificado: usado por modulo_gestion, modulo_envios.
    Usa placeholders (no f-string) en el bloque JS para evitar corrupción de
    llaves. Renderizar con: components.html(boton_imprimir_html(...), height=44)

    fn_id: identificador único de la función JS (sin guiones ni puntos).
    """
    import base64
    b64 = base64.b64encode(pdf_bytes).decode()
    fn  = "imp_" + str(fn_id).replace("-", "_").replace(".", "_").replace(" ", "_")

    # Método robusto: iframe oculto que carga el PDF y dispara print desde su
    # propia ventana cuando termina de cargar (onload). Es mucho más confiable
    # que window.open + setTimeout, que el navegador suele bloquear.
    # El iframe carga el PDF directamente. La clave para que NO se reescale al
    # imprimir es abrir el PDF en su visor nativo (que respeta el tamaño real) y
    # dejar que el usuario imprima a 100%. Forzamos el visor del navegador con
    # #zoom y abrimos en pestaña nueva como método principal (el más fiable para
    # respetar márgenes), con impresión automática vía iframe como complemento.
    tmpl = (
        "<script>"
        "function __FNID__(){"
        "var b64='B64';"
        "var raw=atob(b64);"
        "var arr=new Uint8Array(raw.length);"
        "for(var i=0;i<raw.length;i++)arr[i]=raw.charCodeAt(i);"
        "var blob=new Blob([arr],{type:'application/pdf'});"
        "var url=URL.createObjectURL(blob);"
        "var old=document.getElementById('ifr__FNID__');"
        "if(old){old.parentNode.removeChild(old);}"
        "var ifr=document.createElement('iframe');"
        "ifr.id='ifr__FNID__';"
        "ifr.style.position='fixed';ifr.style.right='0';ifr.style.bottom='0';"
        "ifr.style.width='0';ifr.style.height='0';ifr.style.border='0';"
        "ifr.src=url;"
        "ifr.onload=function(){"
        "setTimeout(function(){"
        "try{ifr.contentWindow.focus();ifr.contentWindow.print();}"
        "catch(e){var w=window.open(url,'_blank');}"
        "},600);"
        "};"
        "document.body.appendChild(ifr);"
        "}"
        "</script>"
        "<button onclick='__FNID__()' style='"
        "background:COLOR;color:white;border:none;border-radius:6px;"
        "padding:7px 14px;font-size:13px;cursor:pointer;width:100%;"
        "font-family:sans-serif'>LABEL</button>"
    )
    return (tmpl.replace("__FNID__", fn)
                .replace("B64", b64)
                .replace("COLOR", color)
                .replace("LABEL", label))
