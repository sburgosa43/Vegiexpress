"""
Cambio masivo de costos en el historial (Productos → Actualizar Costos Masivo).

Es la ÚNICA herramienta que toca semanas pasadas — todo lo demás está acotado a
la semana en curso a propósito. Existe para corregir costos mal cargados, y por
eso la pantalla arranca filtrando productos de PROCESO: su costo sale de una
receta y es estable. En producto fresco el costo varía cada semana, así que
sobrescribir el histórico borraría el costo real en vez de corregir un error.

    python tests/test_costo_historico.py
"""
import sys
import types
from datetime import date

from _stubs import Reporte, instalar_streamlit, por_fila, raiz_repo

raiz_repo()
instalar_streamlit()

ESCRITO = []

PEDIDOS = [
    # Junio — dentro del rango que se va a corregir
    {"row_num": 10, "cliente": "Hotelito", "producto": "Salsa Pesto",
     "fecha": date(2026, 6, 3), "precio": 20.0, "costo": 8.0, "cantidad": 5,
     "semana": 23, "año": 2026, "status": "Pendiente"},
    {"row_num": 11, "cliente": "Sundog", "producto": "Salsa Pesto",
     "fecha": date(2026, 6, 17), "precio": 20.0, "costo": 8.0, "cantidad": 2,
     "semana": 25, "año": 2026, "status": "Pendiente"},
    # Julio — fuera del rango
    {"row_num": 12, "cliente": "Hotelito", "producto": "Salsa Pesto",
     "fecha": date(2026, 7, 15), "precio": 20.0, "costo": 8.0, "cantidad": 3,
     "semana": 29, "año": 2026, "status": "Pendiente"},
    # Otro producto, dentro del rango
    {"row_num": 13, "cliente": "Hotelito", "producto": "Lechuga",
     "fecha": date(2026, 6, 10), "precio": 8.0, "costo": 5.0, "cantidad": 4,
     "semana": 24, "año": 2026, "status": "Pendiente"},
    # Cancelado, dentro del rango
    {"row_num": 14, "cliente": "Sundog", "producto": "Salsa Pesto",
     "fecha": date(2026, 6, 5), "precio": 20.0, "costo": 8.0, "cantidad": 9,
     "semana": 23, "año": 2026, "status": "Cancelado"},
    # Ya tiene el costo correcto: no debe aparecer
    {"row_num": 15, "cliente": "Sundog", "producto": "Salsa Pesto",
     "fecha": date(2026, 6, 20), "precio": 20.0, "costo": 12.0, "cantidad": 1,
     "semana": 25, "año": 2026, "status": "Pendiente"},
]

from utils import _sf                                        # noqa: E402


def _leer_pedidos():
    return [dict(p) for p in PEDIDOS]


_leer_pedidos.clear = lambda: None

excel_stub = types.ModuleType("excel_helper")
excel_stub.leer_pedidos = _leer_pedidos
excel_stub.leer_pedidos_op = _leer_pedidos
excel_stub.leer_productos_con_fila = lambda es_antigua=False: []
excel_stub.DIAS_ES = ["Lunes"] * 7
excel_stub.MESES_N = ["Ene"] * 12
excel_stub._sf = _sf
sys.modules["excel_helper"] = excel_stub

gsheets = types.ModuleType("gsheets")
gsheets.update_cells = lambda hoja, ups: ESCRITO.extend(ups)
gsheets.append_rows = lambda *a, **k: None
gsheets.get_all_rows = lambda *a, **k: []
sys.modules["gsheets"] = gsheets

data_helper = types.ModuleType("data_helper")
data_helper.refrescar_datos = lambda **k: []
sys.modules["data_helper"] = data_helper

from order_helper import (diferencias_costo_historico,        # noqa: E402
                          aplicar_costo_historico)
from config import margen_neto_q                              # noqa: E402

JUN1, JUN30 = date(2026, 6, 1), date(2026, 6, 30)
COSTOS = {"salsa pesto": 12.0}          # se corrige de 8.00 a 12.00

r = Reporte()

print("=== 1. Alcance: solo el rango, el producto y lo activo ===")
difs = diferencias_costo_historico(COSTOS, JUN1, JUN30)
filas = sorted(d["row_num"] for d in difs)
r.check(filas == [10, 11], f"filas dentro del rango: {filas}")
r.check(12 not in filas, "julio queda fuera del rango elegido")
r.check(13 not in filas, "otro producto NO se toca")
r.check(14 not in filas, "la línea cancelada NO se toca")
r.check(15 not in filas, "la que ya tenía el costo correcto no aparece")

print("\n=== 2. Muestra el impacto en el margen ===")
d10 = next(d for d in difs if d["row_num"] == 10)
r.check(d10["Costo actual"] == 8.0 and d10["Costo nuevo"] == 12.0,
        "costo 8.00 -> 12.00")
r.check(abs(d10["Margen actual"] - round(margen_neto_q(8.0, 20.0) * 5, 2)) < 0.01,
        f"margen actual: Q{d10['Margen actual']}")
r.check(abs(d10["Margen nuevo"] - round(margen_neto_q(12.0, 20.0) * 5, 2)) < 0.01,
        f"margen nuevo: Q{d10['Margen nuevo']}")
r.check(d10["Margen nuevo"] < d10["Margen actual"],
        "subir el costo baja el margen: el impacto se ve antes de aplicar")
r.check("Fecha" in d10 and "Cliente" in d10,
        "la vista previa identifica cada línea por fecha y cliente")

print("\n=== 3. Calcular NO escribe ===")
r.check(ESCRITO == [], "la vista previa no toca el Sheet")

print("\n=== 4. Aplicar: cambia el costo, NUNCA el precio ===")
n = aplicar_costo_historico(difs)
pf = por_fila(ESCRITO)
r.check(n == 2, f"aplica 2 líneas ({n})")
r.check(sorted(pf) == [10, 11], f"escribe solo esas: {sorted(pf)}")
r.check("E" not in pf[10],
        "NO escribe E: el precio histórico de la factura queda intacto")
r.check(pf[10]["F"] == 12.0, f"costo nuevo: {pf[10]['F']}")
r.check(abs(pf[10]["G"] - 100.0) < 1e-9, f"total sigue con 20.00 x 5 -> {pf[10]['G']}")
r.check(abs(pf[10]["H"] - 60.0) < 1e-9, f"totalCosto 12.00 x 5 -> {pf[10]['H']}")
r.check(abs(pf[10]["I"] - round(margen_neto_q(12.0, 20.0) * 5, 4)) < 1e-6,
        "margen recalculado con el costo nuevo")
r.check(set("FGHIJK") <= set(pf[10]), f"fila coherente: {sorted(pf[10])}")

print("\n=== 5. Casos borde ===")
ESCRITO.clear()
r.check(diferencias_costo_historico({}, JUN1, JUN30) == [],
        "sin productos no devuelve nada")
r.check(diferencias_costo_historico(COSTOS, JUN30, JUN1) == [],
        "rango invertido no devuelve nada")
r.check(aplicar_costo_historico([]) == 0, "lista vacía devuelve 0")
r.check(ESCRITO == [], "y no manda ningún update")
r.check(len(diferencias_costo_historico(COSTOS, date(2026, 1, 1),
                                        date(2026, 12, 31))) == 3,
        "un rango amplio alcanza también julio (3 líneas)")

r.salir()
