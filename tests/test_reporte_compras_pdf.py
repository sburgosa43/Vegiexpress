"""
PDF del reporte de compras (pdf_helper.generar_reporte_compras).

El PDF NO recalcula nada: recibe las filas ya agregadas por
modulo_proveedores._agregar_compras y solo las maqueta, para que no pueda
discrepar de lo que muestra la pantalla. Estas pruebas verifican que genere un
PDF válido, que pagine, y que los totales que se le pasan lleguen al documento.

Requiere reportlab (está en requirements.txt). Si no está instalado, la prueba
se salta con aviso en vez de fallar.

    python tests/test_reporte_compras_pdf.py
"""
import sys
from datetime import date

from _stubs import Reporte, instalar_streamlit, raiz_repo

raiz_repo()
instalar_streamlit()

try:
    import reportlab  # noqa: F401
except ImportError:
    print("  SALTADA | reportlab no está instalado (pip install reportlab)")
    sys.exit(0)

from pdf_helper import generar_reporte_compras                # noqa: E402

r = Reporte()

DESDE, HASTA = date(2026, 7, 27), date(2026, 8, 2)
FILAS = [
    {"Área": "🔖 Antigua & Chimal", "Valor a costo (Q)": 62.0,
     "Cantidad": 14.0, "Líneas": 2},
    {"Área": "🏙️ Guatemala & Santiago", "Valor a costo (Q)": 30.0,
     "Cantidad": 6.0, "Líneas": 1},
    {"Área": "🏠 Hogares", "Valor a costo (Q)": 10.0,
     "Cantidad": 2.0, "Líneas": 1},
    {"Área": "Sin área", "Valor a costo (Q)": 15.0,
     "Cantidad": 5.0, "Líneas": 1},
]
TOT_V, TOT_C, TOT_N = 117.0, 27.0, 5


def _texto(pdf: bytes) -> str:
    """Texto de los content streams del PDF.

    reportlab comprime con Flate y luego codifica en ASCII85, así que hay que
    deshacer las dos capas en ese orden. El stream termina con el marcador
    '~>' de ASCII85 pero NO empieza con '<~', así que hay que sacarlo a mano:
    a85decode(adobe=True) espera ambos y a85decode(adobe=False) se atraganta
    con el '~' final.
    """
    import base64
    import re
    import zlib
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        datos = m.group(1).strip()
        if datos.endswith(b"~>"):
            datos = datos[:-2]
        try:
            datos = base64.a85decode(datos, adobe=False)
            datos = zlib.decompress(datos)
        except Exception:
            pass                      # stream binario (fuentes, imágenes)
        out.append(datos.decode("latin-1", "ignore"))
    return "\n".join(out)


print("=== 1. Genera un PDF válido ===")
pdf = generar_reporte_compras(FILAS, "Área", DESDE, HASTA,
                              filtros_txt="sin filtros (todo el período)",
                              total_valor=TOT_V, total_cant=TOT_C,
                              total_lineas=TOT_N)
r.check(isinstance(pdf, bytes) and len(pdf) > 800,
        f"devuelve bytes ({len(pdf)} bytes)")
r.check(pdf[:5] == b"%PDF-", f"empieza con la cabecera PDF ({pdf[:5]!r})")
r.check(pdf.rstrip()[-5:] == b"%%EOF", "termina con %%EOF")

print("\n=== 2. El contenido llega al documento ===")
txt = _texto(pdf)
r.check("Valor comprado a costo" in txt, "el título está en el PDF")
r.check("TOTAL GENERAL" in txt, "la fila de total general está")
r.check("117.00" in txt, "el total de valor (117.00) aparece")
r.check("27.00" in txt, "la cantidad total (27.00) aparece")
r.check("27/07/2026" in txt and "02/08/2026" in txt,
        "el período impreso coincide con el rango pedido")

print("\n=== 3. Los filtros aplicados quedan impresos ===")
pdf2 = generar_reporte_compras(
    FILAS[:1], "Área", DESDE, HASTA,
    filtros_txt="Proveedor: CENMA · Producto: Lechuga",
    total_valor=62.0, total_cant=14.0, total_lineas=2)
t2 = _texto(pdf2)
r.check("CENMA" in t2 and "Lechuga" in t2,
        "un reporte filtrado dice de qué recorte es")

print("\n=== 4. Pagina cuando hay muchas filas ===")
muchas = [{"Producto": f"Producto {i:03d}", "Valor a costo (Q)": float(i),
           "Cantidad": float(i), "Líneas": 1} for i in range(1, 96)]
pdf3 = generar_reporte_compras(muchas, "Producto", DESDE, HASTA,
                               total_valor=sum(f["Valor a costo (Q)"]
                                               for f in muchas),
                               total_cant=0, total_lineas=len(muchas))
t3 = _texto(pdf3)
r.check(pdf3[:5] == b"%PDF-", "95 filas generan un PDF válido")
r.check("Pagina 1 de 3" in t3 or "gina 1 de 3" in t3,
        "95 filas / 40 por página = 3 páginas")
r.check("Producto 001" in t3 and "Producto 095" in t3,
        "la primera y la última fila están en el documento")

print("\n=== 5. Casos borde ===")
vacio = generar_reporte_compras([], "Área", DESDE, HASTA,
                                total_valor=0, total_cant=0, total_lineas=0)
r.check(vacio[:5] == b"%PDF-", "sin filas no revienta: genera el PDF igual")
largo = [{"Cliente": "Nombre de cliente extremadamente largo que podría "
                     "desbordar la celda de la tabla",
          "Valor a costo (Q)": 1.0, "Cantidad": 1.0, "Líneas": 1}]
r.check(generar_reporte_compras(largo, "Cliente", DESDE, HASTA,
                                total_valor=1, total_cant=1,
                                total_lineas=1)[:5] == b"%PDF-",
        "un nombre muy largo no rompe el armado")

r.salir()
