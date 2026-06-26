"""
pdf_base.py — Constantes, estilos y helpers compartidos para PDFs VeggiExpress.
Importado internamente por pdf_envio, pdf_facturacion, pdf_cotizacion,
pdf_proveedores y pdf_remision. No usar directamente desde módulos UI.
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
# Meses en español — dos variantes que usan distintos módulos:
_MESES_ES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo",
             6: "junio", 7: "julio", 8: "agosto", 9: "septiembre",
             10: "octubre", 11: "noviembre", 12: "diciembre"}

# Lista con mayúsculas (índice 0-based: MESES_ES[mes-1])
MESES_ES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
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

def boton_imprimir_html(pdf_bytes: bytes, fn_id: str,
                        label: str = "Imprimir",
                        color: str = "#2D7A2D") -> str:
    """
    Genera el HTML+JS de un botón que abre el PDF en una pestaña nueva con el
    visor PDF nativo del navegador, donde el usuario imprime con Ctrl+P
    respetando márgenes y tamaño real (igual que Adobe). Imprimir desde un
    iframe embebido reescala y pierde márgenes; por eso abrimos en pestaña.
    Patrón unificado: usado por modulo_gestion, modulo_envios, modulo_proveedores.

    fn_id: identificador único de la función JS (sin guiones ni puntos).
    """
    import base64
    b64 = base64.b64encode(pdf_bytes).decode()
    fn  = "imp_" + str(fn_id).replace("-", "_").replace(".", "_").replace(" ", "_")

    # OPCIÓN A: abrir el PDF en pestaña nueva con el visor NATIVO del navegador
    # (igual que Adobe). Ahí el usuario imprime con Ctrl+P respetando márgenes y
    # tamaño real. Imprimir desde un iframe embebido reescala el PDF y pierde los
    # márgenes; el visor nativo no. Por eso abrimos en pestaña en vez de iframe.
    tmpl = (
        "<script>"
        "function __FNID__(){"
        "var b64='B64';"
        "var raw=atob(b64);"
        "var arr=new Uint8Array(raw.length);"
        "for(var i=0;i<raw.length;i++)arr[i]=raw.charCodeAt(i);"
        "var blob=new Blob([arr],{type:'application/pdf'});"
        "var url=URL.createObjectURL(blob);"
        "window.open(url,'_blank');"
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
