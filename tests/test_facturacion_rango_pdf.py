"""
PDF de facturación por período (pdf_helper.generar_facturacion_mensual).

Este PDF se le manda al cliente, así que el encabezado no puede mentir sobre
qué recorte tiene adentro: dice el nombre del mes SOLO cuando el rango es ese
mes calendario entero, y en cualquier otro caso muestra las dos fechas reales.
El nombre del archivo sigue la misma regla.

Lo que se pincha:
  - un mes completo sigue saliendo igual que siempre ("JULIO 2026");
  - un rango libre imprime el rango y NO nombra ningún mes;
  - del 01/07 al 30/07 no es julio: le falta el 31, y el PDF lo dice;
  - el nombre del archivo distingue los dos casos.

Requiere reportlab (está en requirements.txt). Si no está instalado, la prueba
se salta con aviso en vez de fallar.

    python tests/test_facturacion_rango_pdf.py
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

from pdf_helper import (generar_facturacion_mensual,          # noqa: E402
                        nombre_archivo_factura)
from utils import rango_mes                                   # noqa: E402

r = Reporte()

CLIENTE = {"nombre": "Cazador Italiano", "empresa": "Cazador S.A.",
           "direccion": "Antigua Guatemala", "nit": "1234567-8",
           "telefono": "5555-5555"}

# Dos semanas de entrega, una en julio y otra en agosto: sirve igual para el
# mes completo (solo la de julio) que para el rango que cruza el cambio de mes.
POR_SEMANA = {
    30: {"fecha": date(2026, 7, 20),
         "lineas": [{"producto": "Tomate", "fecha": date(2026, 7, 20),
                     "cantidad": 10, "unidad": "lb", "precio": 20.0,
                     "total": 200.0}]},
    33: {"fecha": date(2026, 8, 10),
         "lineas": [{"producto": "Cebolla", "fecha": date(2026, 8, 10),
                     "cantidad": 10, "unidad": "lb", "precio": 60.0,
                     "total": 600.0}]},
}


def _texto(pdf: bytes) -> str:
    """Texto de los content streams del PDF.

    reportlab comprime con Flate y luego codifica en ASCII85, así que hay que
    deshacer las dos capas en ese orden. El stream termina con el marcador
    '~>' de ASCII85 pero NO empieza con '<~', así que hay que sacarlo a mano.
    Mismo decodificador que test_reporte_compras_pdf.py.
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


print("=== 1. Mes completo: exactamente lo de siempre ===")
JUL1, JUL31 = rango_mes(7, 2026)
pdf_mes = generar_facturacion_mensual(cliente=CLIENTE, desde=JUL1, hasta=JUL31,
                                      por_semana={30: POR_SEMANA[30]})
r.check(pdf_mes[:5] == b"%PDF-", f"genera un PDF válido ({len(pdf_mes)} bytes)")
t_mes = _texto(pdf_mes)
r.check("JULIO 2026" in t_mes, "el encabezado dice JULIO 2026")
r.check("Julio 2026" in t_mes, "la ficha de período dice Julio 2026")
r.check("del 01/07/2026 al 31/07/2026" not in t_mes,
        "un mes entero se nombra, no se imprime como rango")

print("\n=== 2. Rango libre: el rango real, nunca un mes ===")
JUL20, AGO10 = date(2026, 7, 20), date(2026, 8, 10)
pdf_rng = generar_facturacion_mensual(cliente=CLIENTE, desde=JUL20,
                                      hasta=AGO10, por_semana=POR_SEMANA)
r.check(pdf_rng[:5] == b"%PDF-", f"genera un PDF válido ({len(pdf_rng)} bytes)")
t_rng = _texto(pdf_rng)
r.check("del 20/07/2026 al 10/08/2026" in t_rng,
        "la ficha de período imprime el rango real")
r.check("DEL 20/07/2026 AL 10/08/2026" in t_rng,
        "el encabezado grande también lo imprime")
r.check("JULIO 2026" not in t_rng and "AGOSTO 2026" not in t_rng,
        "no nombra ningún mes: el recorte no es un mes")
r.check("Julio 2026" not in t_rng and "Agosto 2026" not in t_rng,
        "tampoco en la ficha de período")
r.check("200.00" in t_rng and "600.00" in t_rng and "800.00" in t_rng,
        "las dos semanas y su total (Q800) están en el documento")

print("\n=== 3. Un mes al que le falta un día no es ese mes ===")
t_casi = _texto(generar_facturacion_mensual(
    cliente=CLIENTE, desde=JUL1, hasta=date(2026, 7, 30),
    por_semana={30: POR_SEMANA[30]}))
r.check("del 01/07/2026 al 30/07/2026" in t_casi,
        "del 01/07 al 30/07 se imprime como rango")
r.check("JULIO 2026" not in t_casi,
        "y NO se encabeza como 'Julio 2026': le falta el 31")

print("\n=== 4. El nombre del archivo sigue la misma regla ===")
r.check(nombre_archivo_factura("Cazador Italiano", JUL1, JUL31)
        == "CazadorItaliano_Julio2026.pdf",
        f"mes completo: {nombre_archivo_factura('Cazador Italiano', JUL1, JUL31)}")
r.check(nombre_archivo_factura("Cazador Italiano", JUL20, AGO10)
        == "CazadorItaliano_20260720_20260810.pdf",
        f"rango: {nombre_archivo_factura('Cazador Italiano', JUL20, AGO10)}")
r.check(nombre_archivo_factura("Doña Luz", JUL20, AGO10)
        == "DonaLuz_20260720_20260810.pdf",
        "los acentos y espacios se siguen limpiando")
r.check(nombre_archivo_factura("Cazador Italiano", JUL1, JUL31)
        != nombre_archivo_factura("Cazador Italiano", JUL1, date(2026, 7, 30)),
        "dos períodos distintos no comparten nombre de archivo")

print("\n=== 5. Casos borde ===")
r.check(generar_facturacion_mensual(cliente=CLIENTE, desde=JUL20, hasta=JUL20,
                                    por_semana={30: POR_SEMANA[30]})[:5]
        == b"%PDF-", "un rango de un solo día genera el PDF igual")
r.check(generar_facturacion_mensual(cliente={}, desde=JUL20, hasta=AGO10,
                                    por_semana={})[:5] == b"%PDF-",
        "sin cliente y sin semanas no revienta")

r.salir()
