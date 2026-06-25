"""
pdf_cotizacion.py — Generación de PDFs de cotización (simple y formal).
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


