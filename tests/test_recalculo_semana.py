"""
Recálculo de la semana en curso (precio + costo).

Reaplica a los pedidos de esta semana el precio que hoy manda la cascada
(cliente → grupo → zona → general) y el costo del catálogo. Es el "martillo
grande": a diferencia de la propagación, que solo toca lo que se acaba de
cambiar, esto revisa TODAS las líneas de la semana.

Va siempre con vista previa porque no puede distinguir un precio tecleado a
mano de uno viejo: los dos son un número que no coincide con la lista.

    python tests/test_recalculo_semana.py
"""
import sys
import types
from datetime import date

from _stubs import Reporte, instalar_streamlit, por_fila, raiz_repo

raiz_repo()
instalar_streamlit()

HOY = date(2026, 7, 29)               # miércoles; semana 27/07 .. 02/08
ESCRITO = []

CLIENTES = [
    {"nombre": "Casa Lopez", "codigo_lugar": "L20", "grupo": ""},
    {"nombre": "Sundog",     "codigo_lugar": "L05", "grupo": ""},
]

# Precio vigente por cliente según la cascada, y su origen
CASCADA = {
    ("casa lopez", "manzana amarilla"): (7.5, "zona"),
    ("sundog",     "manzana amarilla"): (8.0, "general"),
    ("casa lopez", "lechuga"):          (5.0, "general"),
}
CATALOGO = [{"nombre": "Manzana Amarilla", "costo": 4.5},
            {"nombre": "Lechuga",          "costo": 3.0}]

PEDIDOS = [
    # semana en curso, precio desactualizado (6.00 vs 7.50 de zona)
    {"row_num": 10, "cliente": "Casa Lopez", "producto": "Manzana Amarilla",
     "fecha": date(2026, 7, 27), "precio": 6.0, "costo": 4.0, "cantidad": 3,
     "status": "Pendiente"},
    # semana en curso, ya al día -> no debe aparecer como diferencia
    {"row_num": 11, "cliente": "Sundog", "producto": "Manzana Amarilla",
     "fecha": HOY, "precio": 8.0, "costo": 4.5, "cantidad": 2,
     "status": "Pendiente"},
    # semana en curso, solo el costo cambia
    {"row_num": 12, "cliente": "Casa Lopez", "producto": "Lechuga",
     "fecha": HOY, "precio": 5.0, "costo": 9.9, "cantidad": 4,
     "status": "Pendiente"},
    # cancelado -> fuera
    {"row_num": 13, "cliente": "Casa Lopez", "producto": "Manzana Amarilla",
     "fecha": HOY, "precio": 1.0, "costo": 1.0, "cantidad": 5,
     "status": "Cancelado"},
    # semana PASADA -> el historial no se toca
    {"row_num": 20, "cliente": "Casa Lopez", "producto": "Manzana Amarilla",
     "fecha": date(2026, 7, 20), "precio": 6.0, "costo": 4.0, "cantidad": 7,
     "status": "Pendiente"},
]

from utils import _sf                                        # noqa: E402


def _leer_pedidos():
    return [dict(p) for p in PEDIDOS]


_leer_pedidos.clear = lambda: None

excel_stub = types.ModuleType("excel_helper")
excel_stub.leer_pedidos = _leer_pedidos
excel_stub.leer_pedidos_op = _leer_pedidos
excel_stub.leer_productos_con_fila = lambda es_antigua=False: [
    dict(p) for p in CATALOGO]
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
data_helper.cargar_clientes = lambda: [dict(c) for c in CLIENTES]
data_helper.cli_precio = lambda cli, prod: CASCADA.get(
    (str((cli or {}).get("nombre", "")).strip().lower(),
     str(prod).strip().lower()), (0.0, "general"))
sys.modules["data_helper"] = data_helper

from order_helper import (calcular_diferencias_semana,        # noqa: E402
                          aplicar_diferencias, semana_en_curso)
from config import margen_neto_q                              # noqa: E402

r = Reporte()
print(f"=== Hoy = {HOY}; semana = {semana_en_curso(HOY)} ===\n")

print("=== 1. Qué líneas se detectan como desactualizadas ===")
difs = calcular_diferencias_semana(hoy=HOY)
filas = sorted(d["row_num"] for d in difs)
r.check(filas == [10, 12], f"filas con diferencia: {filas}")
r.check(11 not in filas, "la línea ya al día NO aparece")
r.check(13 not in filas, "la cancelada NO aparece")
r.check(20 not in filas, "la semana pasada NO aparece: el historial no se toca")

print("\n=== 2. Precio desde la cascada, costo desde el catálogo ===")
d10 = next(d for d in difs if d["row_num"] == 10)
r.check(d10["Precio actual"] == 6.0 and d10["Precio nuevo"] == 7.5,
        f"precio 6.00 -> 7.50 ({d10['Origen precio']})")
r.check(d10["Origen precio"] == "zona", "informa de qué nivel sale el precio")
r.check(d10["Costo actual"] == 4.0 and d10["Costo nuevo"] == 4.5,
        "costo 4.00 -> 4.50 (del catálogo)")

d12 = next(d for d in difs if d["row_num"] == 12)
r.check(d12["Precio actual"] == d12["Precio nuevo"] == 5.0,
        "línea con precio correcto: solo cambia el costo")
r.check(d12["Costo nuevo"] == 3.0, f"costo 9.90 -> 3.00 ({d12['Costo nuevo']})")

print("\n=== 3. Calcular NO escribe nada ===")
r.check(ESCRITO == [], "la vista previa no toca el Sheet")

print("\n=== 4. Aplicar escribe la fila coherente ===")
n = aplicar_diferencias(difs)
pf = por_fila(ESCRITO)
r.check(n == 2, f"aplica 2 líneas ({n})")
r.check(sorted(pf) == [10, 12], f"escribe solo esas filas: {sorted(pf)}")
r.check(pf[10]["E"] == 7.5, f"precio nuevo: {pf[10]['E']}")
r.check(pf[10]["F"] == 4.5, f"costo nuevo: {pf[10]['F']}")
r.check(abs(pf[10]["G"] - 22.5) < 1e-9, f"total 7.50 x 3 -> {pf[10]['G']}")
r.check(abs(pf[10]["H"] - 13.5) < 1e-9, f"totalCosto 4.50 x 3 -> {pf[10]['H']}")
r.check(abs(pf[10]["I"] - round(margen_neto_q(4.5, 7.5) * 3, 4)) < 1e-6,
        "margen recalculado con los valores nuevos")
r.check(set("EFGHIJK") <= set(pf[10]), f"fila completa: {sorted(pf[10])}")

print("\n=== 5. Sin diferencias no se escribe ===")
ESCRITO.clear()
r.check(aplicar_diferencias([]) == 0, "lista vacía devuelve 0")
r.check(ESCRITO == [], "y no manda ningún update")

print("\n=== 6. Un precio que la cascada no resuelve se conserva ===")
# Producto sin entrada en CASCADA: devuelve 0.0 y no debe poner el precio en 0.
PEDIDOS.append({"row_num": 30, "cliente": "Casa Lopez", "producto": "Rarito",
                "fecha": HOY, "precio": 12.0, "costo": 6.0, "cantidad": 1,
                "status": "Pendiente"})
difs2 = calcular_diferencias_semana(hoy=HOY)
d30 = [d for d in difs2 if d["row_num"] == 30]
r.check(not d30 or d30[0]["Precio nuevo"] == 12.0,
        "no se pisa con 0 un precio que la cascada no pudo resolver")

r.salir()
