"""
Reporte de valor comprado a costo (Compras a Proveedores → 📊 Reportes).

Verifica que Σ(costo × cantidad) dé el número esperado, que cada filtro recorte
lo que debe, que los subtotales sumen el total general, y que un cliente sin
codigo_lugar conocido aparezca en "Sin área" en vez de desaparecer.

    python tests/test_reporte_compras.py
"""
import ast
import os
import sys
import types
from datetime import date, timedelta

from _stubs import Reporte, instalar_streamlit, raiz_repo

RAIZ = raiz_repo()
instalar_streamlit()

HOY = date(2026, 7, 29)                       # miércoles, semana 27/07..02/08
SEM_INI, SEM_FIN = date(2026, 7, 27), date(2026, 8, 2)

# ── Datos sintéticos ─────────────────────────────────────────────────────────
# Áreas via ZONAS_MAP: L03->Antigua&Chimal, L05->Guatemala&Santiago, L20->Hogares
CLIENTES = [
    {"nombre": "Hotelito",  "codigo_lugar": "L03", "grupo": "Italianos"},
    {"nombre": "Sundog",    "codigo_lugar": "L05", "grupo": "Italianos"},
    {"nombre": "Tijax",     "codigo_lugar": "L20", "grupo": ""},
    {"nombre": "Rarito",    "codigo_lugar": "L99", "grupo": "PorQueNo"},  # sin área
    {"nombre": "Wilson",    "codigo_lugar": "L03", "grupo": ""},          # excluido
]

PEDIDOS = [
    # (cliente, producto, proveedor, fecha, cantidad, costo)
    ("Hotelito", "Lechuga", "CENMA",   SEM_INI,               10, 5.0),   # 50
    ("Hotelito", "Tomate",  "Patojas", HOY,                    4, 3.0),   # 12
    ("Sundog",   "Lechuga", "CENMA",   SEM_FIN,                6, 5.0),   # 30
    ("Tijax",    "Lechuga", "CENMA",   HOY,                    2, 5.0),   # 10
    ("Rarito",   "Tomate",  "Patojas", HOY,                    5, 3.0),   # 15
    ("Wilson",   "Lechuga", "CENMA",   HOY,                  100, 5.0),   # excluido
    ("Hotelito", "Lechuga", "CENMA",   SEM_INI - timedelta(1), 99, 5.0),  # fuera
    ("Hotelito", "Lechuga", "CENMA",   SEM_FIN + timedelta(1), 99, 5.0),  # fuera
]
# Total dentro de la semana, sin Wilson: 50 + 12 + 30 + 10 + 15 = 117.00


def _fila(cli, prod, prov, f, cant, costo, i):
    return {"row_num": i, "cliente": cli, "producto": prod, "proveedor": prov,
            "fecha": f, "cantidad": cant, "costo": costo, "precio": 0.0,
            "status": "Pendiente", "semana": f.isocalendar()[1], "año": f.year,
            "unidad": "lb"}


excel_helper = types.ModuleType("excel_helper")
excel_helper.leer_pedidos_op = lambda: [
    _fila(*p, i + 2) for i, p in enumerate(PEDIDOS)]
excel_helper.leer_pedidos = excel_helper.leer_pedidos_op
excel_helper.DIAS_ES = ["Lunes"] * 7
excel_helper.MESES_N = ["Ene"] * 12
sys.modules["excel_helper"] = excel_helper

data_helper = types.ModuleType("data_helper")
data_helper.cargar_clientes = lambda: [dict(c) for c in CLIENTES]
data_helper.cargar_productos = lambda *a, **k: []
sys.modules["data_helper"] = data_helper

pdf_helper = types.ModuleType("pdf_helper")
pdf_helper.generar_lista_compras_proveedor = lambda *a, **k: b""
sys.modules["pdf_helper"] = pdf_helper

gsheets = types.ModuleType("gsheets")
gsheets.update_cells = lambda *a, **k: None
gsheets.get_all_rows = lambda *a, **k: []
gsheets.append_rows = lambda *a, **k: None      # lo importa order_helper
sys.modules["gsheets"] = gsheets

# _sf lo importa order_helper desde excel_helper
from utils import _sf as _sf_real                          # noqa: E402
excel_helper._sf = _sf_real

# Cargar solo las funciones del reporte desde el módulo real
import pandas as pd                                        # noqa: E402
from config import ZONAS_MAP, excluido_proveedores         # noqa: E402

_QUIERO = {"_mapa_clientes_rep", "_rango_atajo", "_lineas_reporte",
           "_opciones_reporte", "_agregar_compras"}
_src = open(os.path.join(RAIZ, "modulo_proveedores.py"), encoding="utf-8").read()
_mod = ast.parse(_src)
_ns = {
    "st": sys.modules["streamlit"], "pd": pd, "date": date, "timedelta": timedelta,
    "cargar_clientes": data_helper.cargar_clientes,
    "leer_pedidos": excel_helper.leer_pedidos_op,
    "_excluido": excluido_proveedores,
}
exec(compile(ast.Module(
    body=[n for n in _mod.body
          if isinstance(n, ast.FunctionDef) and n.name in _QUIERO]
         + [n for n in _mod.body
            if isinstance(n, ast.Assign)
            and getattr(n.targets[0], "id", "") == "_REP_CLAVE"],
    type_ignores=[]), "modulo_proveedores", "exec"), _ns)

_mapa           = _ns["_mapa_clientes_rep"]
_rango_atajo    = _ns["_rango_atajo"]
_agregar        = _ns["_agregar_compras"]
_opciones       = _ns["_opciones_reporte"]
TODO = (tuple(), tuple(), tuple(), tuple(), tuple())

r = Reporte()

print("=== 1. Área y grupo se resuelven desde ZONAS_MAP y cliente['grupo'] ===")
m = _mapa()
r.check(m["hotelito"]["area"] == "🔖 Antigua & Chimal",
        f"L03 -> {m['hotelito']['area']}")
r.check(m["sundog"]["area"] == "🏙️ Guatemala & Santiago",
        f"L05 (el default de la app) -> {m['sundog']['area']}")
r.check(m["tijax"]["area"] == "🏠 Hogares", f"L20 -> {m['tijax']['area']}")
r.check(m["rarito"]["area"] == "Sin área",
        "un codigo_lugar desconocido cae en 'Sin área', no desaparece")
r.check(m["hotelito"]["grupo"] == "Italianos", "grupo desde cliente['grupo']")
r.check(m["tijax"]["grupo"] == "Sin grupo", "cliente sin grupo -> 'Sin grupo'")

print("\n=== 2. Los atajos de fecha ===")
r.check(_rango_atajo("Esta semana", HOY) == (SEM_INI, SEM_FIN),
        f"Esta semana -> {_rango_atajo('Esta semana', HOY)}")
r.check(_rango_atajo("Este mes", HOY) == (date(2026, 7, 1), date(2026, 7, 31)),
        f"Este mes -> {_rango_atajo('Este mes', HOY)}")
r.check(_rango_atajo("Mes pasado", HOY) == (date(2026, 6, 1), date(2026, 6, 30)),
        f"Mes pasado -> {_rango_atajo('Mes pasado', HOY)}")

print("\n=== 3. El total: Σ(costo × cantidad) ===")
df = _agregar(SEM_INI, SEM_FIN, *TODO, "Área")
total = float(df["Valor a costo (Q)"].sum())
r.check(abs(total - 117.0) < 1e-9, f"total = Q{total:.2f} (esperado Q117.00)")
r.check(abs(float(df["Cantidad"].sum()) - 27.0) < 1e-9,
        f"cantidad = {float(df['Cantidad'].sum())} (10+4+6+2+5)")
r.check(int(df["Líneas"].sum()) == 5, "5 líneas (Wilson y las de otra semana fuera)")

print("\n=== 4. Los subtotales suman el total general ===")
por_area = dict(zip(df["Área"], df["Valor a costo (Q)"]))
r.check(abs(por_area.get("🔖 Antigua & Chimal", 0) - 62.0) < 1e-9,
        f"Antigua = Q{por_area.get('🔖 Antigua & Chimal', 0):.2f} (50 + 12)")
r.check(abs(por_area.get("🏙️ Guatemala & Santiago", 0) - 30.0) < 1e-9,
        f"Guatemala = Q{por_area.get('🏙️ Guatemala & Santiago', 0):.2f}")
r.check(abs(por_area.get("🏠 Hogares", 0) - 10.0) < 1e-9,
        f"Hogares = Q{por_area.get('🏠 Hogares', 0):.2f}")
r.check(abs(por_area.get("Sin área", 0) - 15.0) < 1e-9,
        f"Sin área = Q{por_area.get('Sin área', 0):.2f} (el cliente L99)")
r.check(abs(sum(por_area.values()) - total) < 1e-9,
        "la suma de los subtotales da el total general")

print("\n=== 5. Cambiar 'Agrupar por' no cambia el total ===")
for dim in ("Área", "Cliente", "Grupo", "Proveedor", "Producto", "Semana", "Mes"):
    d = _agregar(SEM_INI, SEM_FIN, *TODO, dim)
    r.check(abs(float(d["Valor a costo (Q)"].sum()) - 117.0) < 1e-9,
            f"agrupado por {dim}: Q{float(d['Valor a costo (Q)'].sum()):.2f}")

print("\n=== 6. Cada filtro recorta lo que debe ===")
d = _agregar(SEM_INI, SEM_FIN, ("🔖 Antigua & Chimal",), (), (), (), (), "Producto")
r.check(abs(float(d["Valor a costo (Q)"].sum()) - 62.0) < 1e-9,
        f"filtro área Antigua -> Q{float(d['Valor a costo (Q)'].sum()):.2f}")
d = _agregar(SEM_INI, SEM_FIN, (), (), (), ("CENMA",), (), "Cliente")
r.check(abs(float(d["Valor a costo (Q)"].sum()) - 90.0) < 1e-9,
        f"filtro proveedor CENMA -> Q{float(d['Valor a costo (Q)'].sum()):.2f} (50+30+10)")
d = _agregar(SEM_INI, SEM_FIN, (), (), (), (), ("Tomate",), "Cliente")
r.check(abs(float(d["Valor a costo (Q)"].sum()) - 27.0) < 1e-9,
        f"filtro producto Tomate -> Q{float(d['Valor a costo (Q)'].sum()):.2f} (12+15)")
d = _agregar(SEM_INI, SEM_FIN, (), ("Italianos",), (), (), (), "Cliente")
r.check(abs(float(d["Valor a costo (Q)"].sum()) - 92.0) < 1e-9,
        f"filtro grupo Italianos -> Q{float(d['Valor a costo (Q)'].sum()):.2f} (50+12+30)")
d = _agregar(SEM_INI, SEM_FIN, ("🏠 Hogares",), (), (), ("Patojas",), (), "Cliente")
r.check(d.empty, "filtros combinados sin coincidencias -> vacío")

print("\n=== 7. Exclusiones y solo-lectura ===")
d = _agregar(SEM_INI, SEM_FIN, (), (), ("Wilson",), (), (), "Cliente")
r.check(d.empty, "Wilson queda excluido por excluido_proveedores")
op = _opciones(SEM_INI, SEM_FIN)
r.check("Wilson" not in op["clientes"], "Wilson tampoco aparece en los filtros")
r.check(sorted(op["proveedores"]) == ["CENMA", "Patojas"],
        f"proveedores del rango: {op['proveedores']}")

print("\n=== 8. Cancelados fuera ===")
PEDIDOS_CANC = excel_helper.leer_pedidos_op()
PEDIDOS_CANC[0]["status"] = "Cancelado"
excel_helper.leer_pedidos_op = lambda: PEDIDOS_CANC
_ns["leer_pedidos"] = excel_helper.leer_pedidos_op
d = _agregar(SEM_INI, SEM_FIN, *TODO, "Área")
r.check(abs(float(d["Valor a costo (Q)"].sum()) - 67.0) < 1e-9,
        f"cancelando la línea de Q50 -> Q{float(d['Valor a costo (Q)'].sum()):.2f}")

r.salir()
