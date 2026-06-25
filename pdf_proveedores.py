"""
pdf_proveedores.py — PDFs de lista de compras y checklist de entrega por ruta.
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
