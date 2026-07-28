"""
Unificación de las rutas que modifican costos y precios de pedidos.

Todas escriben la línea a través de order_helper.celdas_linea(), así ninguna
puede dejar la fila incoherente consigo misma. Lo que NO se unifica —a
propósito— es la selección: Corrección Masiva trabaja sobre la semana que el
usuario elige y sí escribe el precio, porque para eso existe.

    python tests/test_rutas_costo.py
"""
import ast
import os
import sys
import types
from datetime import date

from _stubs import Reporte, instalar_streamlit, por_fila, raiz_repo

RAIZ = raiz_repo()
instalar_streamlit()

HOY = date(2026, 7, 29)          # miércoles; semana 27/07 .. 02/08
ESCRITO = []

PEDIDOS = [
    # lunes de la semana en curso, precio NEGOCIADO 9.50
    {"row_num": 10, "producto": "Lechuga", "fecha": date(2026, 7, 27),
     "precio": 9.50, "costo": 5.0, "cantidad": 10, "semana": 31, "año": 2026},
    {"row_num": 12, "producto": "Lechuga", "fecha": HOY,
     "precio": 8.00, "costo": 5.0, "cantidad": 2, "semana": 31, "año": 2026},
    # semana PASADA: fuera de la semana en curso, pero alcanzable pidiendo sem 30
    {"row_num": 20, "producto": "Lechuga", "fecha": date(2026, 7, 20),
     "precio": 8.00, "costo": 5.0, "cantidad": 4, "semana": 30, "año": 2026},
]

from utils import _sf                                      # noqa: E402


def _leer_pedidos():
    return [dict(p) for p in PEDIDOS]


_leer_pedidos.clear = lambda: None

excel_helper = types.ModuleType("excel_helper")
excel_helper.leer_pedidos = _leer_pedidos
excel_helper.leer_pedidos_op = _leer_pedidos
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

from order_helper import (celdas_linea, propagar_costo_semana,   # noqa: E402
                          semana_en_curso)
from config import margen_neto_q                                 # noqa: E402

# actualizar_precio_semana REAL, con sus dependencias inyectadas
_src = open(os.path.join(RAIZ, "excel_helper.py"), encoding="utf-8").read()
_fn = next(n for n in ast.parse(_src).body
           if isinstance(n, ast.FunctionDef)
           and n.name == "actualizar_precio_semana")
_g = {"leer_pedidos": _leer_pedidos, "leer_pedidos_op": _leer_pedidos,
      "_sf": _sf, "update_cells": gsheets.update_cells, "_K_PED": "pedidos",
      "_actualizar_precio_catalogo": lambda *a, **k: 0}
exec(compile(ast.Module(body=[_fn], type_ignores=[]), "excel_helper", "exec"), _g)
actualizar_precio_semana = _g["actualizar_precio_semana"]

r = Reporte()
print(f"=== semana en curso ({HOY}) = {semana_en_curso(HOY)} ===\n")

print("=== A. La función compartida escribe SIEMPRE los derivados ===")
cols = sorted(u["range"][0] for u in celdas_linea(99, 10, 9.50, 6.0))
r.check(cols == ["F", "G", "H", "I", "J", "K"], f"sin precio -> {cols}")
cols = sorted(u["range"][0]
              for u in celdas_linea(99, 10, 9.50, 6.0, escribir_precio=True))
r.check(cols == ["E", "F", "G", "H", "I", "J", "K"], f"con precio -> {cols}")

print("\n=== B. Ruta de costo (Productos, edición completa, hijos) ===")
ESCRITO.clear()
n = propagar_costo_semana({"lechuga": 6.0}, hoy=HOY)
pf = por_fila(ESCRITO)
r.check(n == 2, f"toca 2 líneas de la semana en curso (devolvió {n})")
r.check(sorted(pf) == [10, 12], f"filas {sorted(pf)} (la 20 es de otra semana)")
r.check("E" not in pf[10], "NO escribe E: el precio negociado 9.50 queda intacto")
r.check(abs(pf[10]["G"] - 95.0) < 1e-9, f"total usa 9.50 -> {pf[10]['G']}")
r.check(abs(pf[10]["H"] - 60.0) < 1e-9, f"total_costo = 6.00 x 10 -> {pf[10]['H']}")
r.check(abs(pf[10]["I"] - round(margen_neto_q(6.0, 9.50) * 10, 4)) < 1e-6,
        "margen recalculado con SU precio")
r.check("K" in pf[10], "escribe IVA")

print("\n=== C. Corrección Masiva conserva semana elegida y escritura de precio ===")
ESCRITO.clear()
cambios = [{"producto": "Lechuga", "row_num": 1,
            "costo_ant": 5.0, "costo_nuevo": 0,
            "precio_ant": 8.0, "precio_nuevo": 11.0,
            "p_cambia": True, "c_cambia": False}]
res = actualizar_precio_semana(cambios, 30, 2026, actualizar_catalogo=False)
pf = por_fila(ESCRITO)
r.check(sorted(pf) == [20], f"trabaja sobre la semana ELEGIDA (30): {sorted(pf)}")
r.check(pf[20]["E"] == 11.0, "SÍ escribe el precio: es su propósito")
r.check(abs(pf[20]["G"] - 44.0) < 1e-9, f"total recalculado 11.00 x 4 -> {pf[20]['G']}")
r.check(abs(pf[20]["F"] - 5.0) < 1e-9, "costo 0 no se escribe: conserva el suyo")
r.check(set("EFGHIJK") <= set(pf[20]), f"fila coherente: {sorted(pf[20])}")
r.check(res["filas_pedidos"] == 1,
        f"cuenta LÍNEAS, no celdas (devolvió {res['filas_pedidos']})")

print("\n=== D. Misma fila, mismo resultado por cualquier ruta ===")
esperado = celdas_linea(10, 10, 9.50, 6.0)
ESCRITO.clear()
propagar_costo_semana({"lechuga": 6.0}, hoy=HOY)
obtenido = [u for u in ESCRITO if u["range"][1:] == "10"]
r.check(esperado == obtenido,
        "propagar_costo_semana produce exactamente celdas_linea()")

r.salir()
