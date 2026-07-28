"""
Propagación de costo a los pedidos de la semana en curso.

Regla: al cambiar el costo de un producto, TODAS las líneas de ese producto con
fecha dentro de la semana en curso (lunes a domingo) quedan con el costo nuevo
— incluidas las de días anteriores. El precio de venta NO se toca, porque cada
línea puede tener un precio negociado por cliente/grupo/zona.

    python tests/test_propagacion_costo.py
"""
import ast
import os
import sys
import types
from datetime import date

from _stubs import Reporte, instalar_streamlit, por_fila, raiz_repo

RAIZ = raiz_repo()
st = instalar_streamlit()

# Miércoles. La semana en curso va del lunes 27/07 al domingo 02/08.
HOY = date(2026, 7, 29)

PEDIDOS = [
    # lunes, con precio NEGOCIADO 9.50 (el del catálogo es 8.00)
    {"row_num": 10, "producto": "Lechuga", "fecha": date(2026, 7, 27),
     "precio": 9.50, "costo": 5.0, "cantidad": 10, "status": "Pendiente"},
    {"row_num": 11, "producto": "Lechuga", "fecha": date(2026, 7, 28),
     "precio": 8.00, "costo": 5.0, "cantidad": 4, "status": "Pendiente"},
    {"row_num": 12, "producto": "Lechuga", "fecha": HOY,
     "precio": 8.00, "costo": 5.0, "cantidad": 2, "status": ""},
    # domingo: último día de la semana, entra
    {"row_num": 13, "producto": "Lechuga", "fecha": date(2026, 8, 2),
     "precio": 8.00, "costo": 5.0, "cantidad": 1, "status": "Pendiente"},
    # domingo anterior: semana pasada, NO entra
    {"row_num": 14, "producto": "Lechuga", "fecha": date(2026, 7, 26),
     "precio": 8.00, "costo": 5.0, "cantidad": 7, "status": "Pendiente"},
    # lunes siguiente: semana que viene, NO entra
    {"row_num": 15, "producto": "Lechuga", "fecha": date(2026, 8, 3),
     "precio": 8.00, "costo": 5.0, "cantidad": 3, "status": "Pendiente"},
    # otro producto de la misma semana, NO entra
    {"row_num": 16, "producto": "Tomate", "fecha": date(2026, 7, 27),
     "precio": 6.00, "costo": 3.0, "cantidad": 5, "status": "Pendiente"},
    # estado escrito a mano: entra igual, ya no se filtra por estado
    {"row_num": 17, "producto": "Lechuga", "fecha": date(2026, 7, 27),
     "precio": 8.00, "costo": 5.0, "cantidad": 6, "status": "Entregado"},
]

ESCRITO = []

from utils import _sf                                      # noqa: E402

excel_helper = types.ModuleType("excel_helper")
excel_helper.leer_pedidos = lambda: [dict(p) for p in PEDIDOS]
excel_helper.leer_pedidos_op = excel_helper.leer_pedidos
excel_helper.DIAS_ES = ["Lunes"] * 7
excel_helper.MESES_N = ["Ene"] * 12
excel_helper._sf = _sf
sys.modules["excel_helper"] = excel_helper

gsheets = types.ModuleType("gsheets")
gsheets.update_cells = lambda hoja, ups: ESCRITO.extend(ups)
gsheets.append_rows = lambda *a, **k: None
gsheets.get_all_rows = lambda *a, **k: []
sys.modules["gsheets"] = gsheets

data_helper = types.ModuleType("data_helper")
data_helper.refrescar_datos = lambda **k: []
sys.modules["data_helper"] = data_helper

# order_helper REAL: ahí vive la regla compartida
from order_helper import _calcular, semana_en_curso        # noqa: E402
from config import margen_neto_q                           # noqa: E402

# _propagar_precios_pedidos REAL, que delega en order_helper
_src = open(os.path.join(RAIZ, "modulo_productos.py"), encoding="utf-8").read()
_ns = {"st": st}
exec(compile(ast.Module(
    body=[n for n in ast.parse(_src).body
          if isinstance(n, ast.FunctionDef)
          and n.name == "_propagar_precios_pedidos"],
    type_ignores=[]), "modulo_productos", "exec"), _ns)
_propagar = _ns["_propagar_precios_pedidos"]

r = Reporte()
print(f"=== Hoy = miércoles {HOY}; semana = {semana_en_curso(HOY)} ===\n")

# El costo de la Lechuga pasa de 5.00 a 6.00; el precio del catálogo es 8.00.
n = _propagar([{"row_num": 1,
                "data": {"nombre": "Lechuga", "costo": 6.0, "precio": 8.0}}])
pf = por_fila(ESCRITO)

print("=== 1. Alcance: qué filas se tocaron ===")
r.check(sorted(pf) == [10, 11, 12, 13, 17],
        f"filas tocadas = {sorted(pf)} (esperado [10,11,12,13,17])")
r.check(10 in pf, "el pedido del LUNES 27/07 se actualiza (era el bug)")
r.check(11 in pf, "el del martes 28/07 también")
r.check(13 in pf, "el del domingo 02/08 entra (último día de la semana)")
r.check(14 not in pf, "el del domingo 26/07 (semana pasada) NO se toca")
r.check(15 not in pf, "el del lunes 03/08 (semana que viene) NO se toca")
r.check(16 not in pf, "otro producto (Tomate) NO se toca")
r.check(17 in pf, "un estado escrito a mano ya NO se filtra")

print("\n=== 2. El precio negociado queda intacto ===")
cols = {c for f in pf.values() for c in f}
r.check("E" not in cols, f"nunca se escribe E (precio). Escritas: {sorted(cols)}")
r.check(pf[10]["F"] == 6.0, "fila 10: costo actualizado a 6.00")
r.check(abs(pf[10]["G"] - 95.0) < 1e-9, f"fila 10: total usa 9.50 -> {pf[10]['G']}")
r.check(abs(pf[10]["H"] - 60.0) < 1e-9, f"fila 10: total_costo -> {pf[10]['H']}")
r.check(abs(pf[10]["I"] - round(margen_neto_q(6.0, 9.50) * 10, 4)) < 1e-6,
        "fila 10: margen recalculado con SU precio 9.50")
r.check(abs(pf[10]["I"] - _calcular(8.00, 6.0, 10)["margen_q"]) > 1e-6,
        "el margen NO coincide con el que daría el precio del catálogo")
r.check("K" in pf[10], "se escribe el IVA (K), que antes quedaba viejo")

print("\n=== 3. El conteo que alimenta el mensaje ===")
r.check(n == 5, f"devuelve {n} líneas actualizadas (esperado 5)")
r.check(_propagar([]) == 0, "sin ediciones devuelve 0")

r.salir()
