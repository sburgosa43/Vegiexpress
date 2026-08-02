"""
Propagación de precios de zona/grupo/cliente a los pedidos de la semana.

Dos problemas que cubre:

1. Lista de Precios Especiales guardaba el precio en la hoja y NO tocaba los
   pedidos: cambiar el precio de Manzana Amarilla para Hogares no se reflejaba
   en Envíos ni Facturación de la semana en curso.

2. Corrección Masiva sí tocaba pedidos, pero filtraba solo por producto +
   semana + año, SIN mirar el cliente. Corregir el precio de Zona Hogares se lo
   reescribía a todos los clientes con ese producto, incluidos los que cotizan
   por el precio general o por otra zona.

    python tests/test_precio_nivel.py
"""
import ast
import os
import sys
import types
from datetime import date

from _stubs import Reporte, instalar_streamlit, por_fila, raiz_repo

RAIZ = raiz_repo()
instalar_streamlit()

HOY = date(2026, 7, 29)               # miércoles; semana 27/07 .. 02/08
ESCRITO = []

# Hogares = L20 · Antigua = L03/L04 · el resto usa el precio general
CLIENTES = [
    {"nombre": "Casa Lopez",  "codigo_lugar": "L20", "grupo": ""},
    {"nombre": "Casa Perez",  "codigo_lugar": "L20", "grupo": ""},
    {"nombre": "Hotelito",    "codigo_lugar": "L03", "grupo": "Italianos"},
    {"nombre": "Sundog",      "codigo_lugar": "L05", "grupo": ""},
    # También L20, pero con precio individual negociado: la zona no debe
    # pisárselo. Es el caso que rompía el criterio viejo de pertenencia.
    {"nombre": "Casa Ruiz",   "codigo_lugar": "L20", "grupo": ""},
]

# Estado de las hojas de precios que implica este escenario. Se declara para
# que cli_precio del doble resuelva la MISMA cascada que el original.
TABLAS = {
    "preciosclient": {("casa ruiz", "manzana amarilla"): 5.0},
    "preciosgrupo":  {},
    "precioszona":   {("hogares", "manzana amarilla"): 6.0,
                      ("antigua", "manzana amarilla"): 9.0},
}
CATALOGO_PRECIO = 8.0

PEDIDOS = [
    # Semana en curso
    {"row_num": 10, "cliente": "Casa Lopez", "producto": "Manzana Amarilla",
     "fecha": date(2026, 7, 27), "precio": 6.0, "costo": 4.0, "cantidad": 3,
     "semana": 31, "año": 2026},
    {"row_num": 11, "cliente": "Casa Perez", "producto": "Manzana Amarilla",
     "fecha": HOY, "precio": 6.0, "costo": 4.0, "cantidad": 2,
     "semana": 31, "año": 2026},
    {"row_num": 12, "cliente": "Hotelito", "producto": "Manzana Amarilla",
     "fecha": HOY, "precio": 9.0, "costo": 4.0, "cantidad": 5,
     "semana": 31, "año": 2026},
    {"row_num": 13, "cliente": "Sundog", "producto": "Manzana Amarilla",
     "fecha": HOY, "precio": 8.0, "costo": 4.0, "cantidad": 4,
     "semana": 31, "año": 2026},
    {"row_num": 14, "cliente": "Casa Ruiz", "producto": "Manzana Amarilla",
     "fecha": HOY, "precio": 5.0, "costo": 4.0, "cantidad": 6,
     "semana": 31, "año": 2026},
    # Semana PASADA — el historial no se toca
    {"row_num": 20, "cliente": "Casa Lopez", "producto": "Manzana Amarilla",
     "fecha": date(2026, 7, 20), "precio": 6.0, "costo": 4.0, "cantidad": 7,
     "semana": 30, "año": 2026},
]

from utils import _sf                                        # noqa: E402


def _leer_pedidos():
    return [dict(p) for p in PEDIDOS]


_leer_pedidos.clear = lambda: None

excel_stub = types.ModuleType("excel_helper")
excel_stub.leer_pedidos = _leer_pedidos
excel_stub.leer_pedidos_op = _leer_pedidos
excel_stub.DIAS_ES = ["Lunes"] * 7
excel_stub.MESES_N = ["Ene"] * 12
excel_stub._sf = _sf
sys.modules["excel_helper"] = excel_stub

gsheets = types.ModuleType("gsheets")
gsheets.update_cells = lambda hoja, ups: ESCRITO.extend(ups)
gsheets.append_rows = lambda *a, **k: None
gsheets.get_all_rows = lambda *a, **k: []
sys.modules["gsheets"] = gsheets

from config import (cliente_en_nivel, zona_lista_de,          # noqa: E402
                    ZONA_LISTA_CODIGOS)

data_helper = types.ModuleType("data_helper")
data_helper.refrescar_datos = lambda **k: []
data_helper.cargar_clientes = lambda: [dict(c) for c in CLIENTES]


def _cli_precio(cliente, producto):
    """Misma cascada que el original: cliente -> grupo -> zona -> general."""
    prod = str(producto or "").lower().strip()
    nom  = str(cliente.get("nombre", "") or "").strip().lower()
    grp  = str(cliente.get("grupo", "") or "").strip().lower()
    zona = zona_lista_de(cliente.get("codigo_lugar", ""))
    v = TABLAS["preciosclient"].get((nom, prod))
    if v: return float(v), "cliente"
    if grp:
        v = TABLAS["preciosgrupo"].get((grp, prod))
        if v: return float(v), "grupo"
    if zona:
        v = TABLAS["precioszona"].get((zona, prod))
        if v: return float(v), "zona"
    return CATALOGO_PRECIO, "general"


def _alcanzado(cliente, producto, hoja_key, lista):
    _, fuente = _cli_precio(cliente, producto)
    if hoja_key == "general":
        return fuente == "general"
    esperada = {"precioszona": "zona", "preciosgrupo": "grupo",
                "preciosclient": "cliente"}.get(hoja_key)
    if not esperada:
        return False
    return fuente == esperada and cliente_en_nivel(cliente, hoja_key, lista)


data_helper.cli_precio = _cli_precio
data_helper.alcanzado_por_nivel = _alcanzado
sys.modules["data_helper"] = data_helper

from order_helper import propagar_precio_nivel               # noqa: E402

# actualizar_precio_semana REAL
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

print("=== 1. A qué clientes alcanza cada lista ===")
cl = {c["nombre"]: c for c in CLIENTES}
r.check(zona_lista_de("L20") == "hogares", "L20 -> lista 'hogares'")
r.check(zona_lista_de("L03") == "antigua", "L03 -> lista 'antigua'")
r.check(zona_lista_de("L05") is None, "L05 no tiene lista de zona")
r.check(cliente_en_nivel(cl["Casa Lopez"], "precioszona", "Hogares"),
        "Casa Lopez (L20) está en Zona Hogares")
r.check(not cliente_en_nivel(cl["Sundog"], "precioszona", "Hogares"),
        "Sundog (L05) NO está en Zona Hogares")
r.check(not cliente_en_nivel(cl["Hotelito"], "precioszona", "Hogares"),
        "Hotelito (L03) NO está en Zona Hogares")
r.check(cliente_en_nivel(cl["Hotelito"], "preciosgrupo", "Italianos"),
        "Hotelito está en Grupo Italianos")
r.check(cliente_en_nivel(cl["Sundog"], "preciosclient", "Sundog"),
        "un precio de cliente alcanza a ese cliente")

print("\n=== 2. Precios Especiales: propaga solo a Hogares ===")
ESCRITO.clear()
n = propagar_precio_nivel("Manzana Amarilla", 7.5, "precioszona", "Hogares",
                          hoy=HOY)
pf = por_fila(ESCRITO)
r.check(n == 2, f"toca las 2 líneas de Hogares de esta semana (devolvió {n})")
r.check(sorted(pf) == [10, 11], f"filas {sorted(pf)}")
r.check(12 not in pf, "Hotelito (Antigua) NO se toca")
r.check(13 not in pf, "Sundog (precio general) NO se toca")
r.check(14 not in pf,
        "Casa Ruiz es L20 pero tiene precio individual: la zona NO se lo pisa")
r.check(20 not in pf, "la semana PASADA no se toca: el historial queda intacto")
r.check(pf[10]["E"] == 7.5, f"precio nuevo escrito: {pf[10]['E']}")
r.check(abs(pf[10]["G"] - 22.5) < 1e-9, f"total recalculado 7.50 x 3 -> {pf[10]['G']}")
r.check(abs(pf[10]["F"] - 4.0) < 1e-9, "el costo de la línea NO cambia")
r.check(set("EFGHIJK") <= set(pf[10]), f"fila coherente: {sorted(pf[10])}")

print("\n=== 3. Corrección Masiva respeta el nivel ===")
cambios = [{"producto": "Manzana Amarilla", "row_num": 1,
            "costo_ant": 4.0, "costo_nuevo": 0,
            "precio_ant": 6.0, "precio_nuevo": 7.5,
            "p_cambia": True, "c_cambia": False}]
ESCRITO.clear()
res = actualizar_precio_semana(cambios, 31, 2026, actualizar_catalogo=False,
                               hoja_nivel="precioszona", lista_nivel="Hogares")
pf = por_fila(ESCRITO)
r.check(sorted(pf) == [10, 11],
        f"con nivel Hogares toca solo esas filas: {sorted(pf)}")
r.check(res["filas_pedidos"] == 2, f"cuenta 2 líneas ({res['filas_pedidos']})")

print("\n=== 4. Sin nivel (General) sigue tocando todas ===")
ESCRITO.clear()
res = actualizar_precio_semana(cambios, 31, 2026, actualizar_catalogo=False)
pf = por_fila(ESCRITO)
r.check(sorted(pf) == [10, 11, 12, 13, 14],
        f"sin nivel se tocan todas las líneas del producto: {sorted(pf)}")

print("\n=== 5. El bug que se corrigió ===")
# Antes, editar Zona Hogares reescribia el precio de Hogares a TODOS.
ESCRITO.clear()
actualizar_precio_semana(cambios, 31, 2026, actualizar_catalogo=False,
                         hoja_nivel="precioszona", lista_nivel="Hogares")
pf = por_fila(ESCRITO)
r.check(13 not in pf,
        "Sundog conserva su precio general: antes se lo pisaba el de Hogares")
r.check(12 not in pf,
        "Hotelito conserva su precio de Antigua")
r.check(14 not in pf,
        "y Casa Ruiz conserva su precio negociado")

print("\n=== 5b. Pertenecer a la zona NO alcanza: manda la cascada ===")
# Contraprueba del bug: el criterio viejo (cliente_en_nivel) daba por buenos a
# los TRES clientes L20. Sin esto, los checks de arriba pasarian tambien con una
# implementacion que simplemente no tocara nada.
_cl5 = {c["nombre"]: c for c in CLIENTES}
_viejo = sorted(n for n, c in _cl5.items()
                if cliente_en_nivel(c, "precioszona", "Hogares"))
r.check(_viejo == ["Casa Lopez", "Casa Perez", "Casa Ruiz"],
        f"el criterio viejo alcanzaba a los 3 de L20: {_viejo}")
_nuevo = sorted(n for n, c in _cl5.items()
                if _alcanzado(c, "Manzana Amarilla", "precioszona", "Hogares"))
r.check(_nuevo == ["Casa Lopez", "Casa Perez"],
        f"el criterio nuevo deja 2: {_nuevo}")
r.check(_cli_precio(_cl5["Casa Ruiz"], "Manzana Amarilla") == (5.0, "cliente"),
        "porque Casa Ruiz cotiza por su precio individual, no por la zona")

print("\n=== 6. Casos borde ===")
ESCRITO.clear()
r.check(propagar_precio_nivel("", 7.5, "precioszona", "Hogares", hoy=HOY) == 0,
        "producto vacío no hace nada")
r.check(propagar_precio_nivel("Manzana Amarilla", 0, "precioszona", "Hogares",
                              hoy=HOY) == 0, "precio 0 no se propaga")
r.check(propagar_precio_nivel("Manzana Amarilla", 7.5, "precioszona",
                              "Antigua", hoy=HOY) == 1,
        "Zona Antigua alcanza solo a Hotelito")
r.check(propagar_precio_nivel("Manzana Amarilla", 7.5, "preciosgrupo",
                              "NoExiste", hoy=HOY) == 0,
        "un grupo sin clientes no toca nada")

r.salir()
