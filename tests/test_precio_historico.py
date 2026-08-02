"""
Actualizar Precios Masivo (Productos) + la regla de alcance por nivel.

Existe por un bug real: cliente_en_nivel prueba PERTENENCIA, no la cascada.
Un cliente L20 con precio propio en PreciosCliente cotiza por ese precio, pero
al editar Zona Hogares se le reescribía el pedido igual. alcanzado_por_nivel lo
arregla consultando la fuente real con cli_precio.

Lo que se pincha:
  - un precio individual NO se pisa desde la zona ni desde el grupo;
  - el nivel General alcanza solo a quien no tiene ninguna lista especial;
  - una lista de zona que config no mapea no alcanza a nadie (y se puede
    detectar antes de aplicar, en vez de escribir en silencio);
  - aplicar escribe el precio y NUNCA el costo.

    python tests/test_precio_historico.py
"""
import sys
import types
from datetime import date

from _stubs import Reporte, instalar_streamlit, por_fila, raiz_repo

raiz_repo()
instalar_streamlit()

ESCRITO = []

# Cuatro clientes de la MISMA zona Hogares (L20), con distinta cascada:
#   Thelma  -> precio individual en PreciosCliente
#   Cori    -> precio de grupo
#   Marta   -> nada propio: le manda la zona
#   Lucia   -> nada propio tampoco
# Y uno de Río (L01), zona que config NO mapea.
CLIENTES = [
    {"nombre": "Thelma Porres", "codigo_lugar": "L20", "grupo": "",
     "es_antigua": False},
    {"nombre": "Cori Guzman",   "codigo_lugar": "L20", "grupo": "Condominio",
     "es_antigua": False},
    {"nombre": "Marta Lopez",   "codigo_lugar": "L20", "grupo": "",
     "es_antigua": False},
    {"nombre": "Lucia Diaz",    "codigo_lugar": "L20", "grupo": "",
     "es_antigua": False},
    {"nombre": "Cafe del Rio",  "codigo_lugar": "L01", "grupo": "",
     "es_antigua": False},
]

TABLAS = {
    "preciosclient": {("thelma porres", "manzana"): 8.0},
    "preciosgrupo":  {("condominio", "manzana"): 9.0},
    "precioszona":   {("hogares", "manzana"): 10.0,
                      # Lista de zona que ZONA_LISTA_CODIGOS no conoce.
                      ("rio", "manzana"): 11.0},
}
CATALOGO = [{"nombre": "Manzana", "precio": 15.0, "costo": 6.0,
             "tipo_producto": "Fresco", "unidad": "lb"}]


def _ped(row, cli, f, precio, cant, sem):
    return {"row_num": row, "cliente": cli, "producto": "Manzana", "fecha": f,
            "precio": precio, "costo": 6.0, "cantidad": cant,
            "total": round(precio * cant, 2), "semana": sem, "año": 2026,
            "status": "Pendiente"}


PEDIDOS = [
    _ped(10, "Thelma Porres", date(2026, 6, 3),  8.0, 2, 23),
    _ped(11, "Cori Guzman",   date(2026, 6, 3),  9.0, 3, 23),
    _ped(12, "Marta Lopez",   date(2026, 6, 3), 10.0, 4, 23),
    _ped(13, "Lucia Diaz",    date(2026, 6, 10), 10.0, 5, 24),
    _ped(14, "Cafe del Rio",  date(2026, 6, 3), 15.0, 6, 23),
    # Fuera del rango que se corrige
    _ped(15, "Marta Lopez",   date(2026, 7, 8), 10.0, 9, 28),
]

from utils import _sf                                          # noqa: E402

excel_stub = types.ModuleType("excel_helper")
excel_stub.leer_pedidos = lambda: [dict(p) for p in PEDIDOS]
excel_stub.leer_pedidos_op = excel_stub.leer_pedidos
excel_stub.leer_productos_con_fila = lambda es_antigua=False: (
    [] if es_antigua else [dict(c) for c in CATALOGO])
excel_stub.DIAS_ES = ["Lunes"] * 7
excel_stub.MESES_N = ["Ene"] * 12
excel_stub._sf = _sf
sys.modules["excel_helper"] = excel_stub

gsheets = types.ModuleType("gsheets")
gsheets.update_cells = lambda hoja, ups: ESCRITO.extend(ups)
gsheets.append_rows = lambda *a, **k: None
gsheets.get_all_rows = lambda *a, **k: []
sys.modules["gsheets"] = gsheets

# data_helper real necesita streamlit+gspread. Se reimplementan cli_precio y
# alcanzado_por_nivel sobre las tablas de arriba, con la MISMA lógica del
# original (cliente -> grupo -> zona -> general), para probar la regla sin red.
from config import (zona_lista_de, cliente_en_nivel,            # noqa: E402
                    margen_neto_q)

data_helper = types.ModuleType("data_helper")
data_helper.cargar_clientes = lambda: [dict(c) for c in CLIENTES]
data_helper.refrescar_datos = lambda **k: []


def _cli_precio(cliente, producto):
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
    for c in CATALOGO:
        if c["nombre"].lower() == prod:
            return float(c["precio"]), "general"
    return 0.0, "general"


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

from order_helper import (diferencias_precio_historico,         # noqa: E402
                          aplicar_precio_historico,
                          clientes_alcanzados)

JUN1, JUN30 = date(2026, 6, 1), date(2026, 6, 30)
PRECIOS = {"manzana": 12.0}          # la zona Hogares sube de 10.00 a 12.00

r = Reporte()

print("=== 1. La cascada manda: el precio individual NO se pisa ===")
difs = diferencias_precio_historico(PRECIOS, "precioszona", "hogares",
                                    JUN1, JUN30)
filas = sorted(d["row_num"] for d in difs)
r.check(filas == [12, 13],
        f"solo Marta y Lucia, que cotizan POR la zona: filas {filas}")
r.check(10 not in filas,
        "Thelma tiene precio individual (Q8): editar la zona no se lo toca")
r.check(11 not in filas,
        "Cori cotiza por su grupo (Q9): la zona tampoco se lo pisa")
r.check(14 not in filas, "Cafe del Rio no es de Hogares")
r.check(15 not in filas, "julio queda fuera del rango elegido")

print("\n=== 2. Contraprueba: sin la regla, Thelma y Cori entrarían ===")
# cliente_en_nivel (el criterio viejo) las da por buenas a las dos. Sin este
# check, el de arriba pasaría también con una implementación que no toque nada.
_viejo = [c["nombre"] for c in CLIENTES
          if cliente_en_nivel(c, "precioszona", "hogares")]
r.check(sorted(_viejo) == ["Cori Guzman", "Lucia Diaz", "Marta Lopez",
                           "Thelma Porres"],
        f"el criterio viejo alcanzaba a los 4 de L20: {sorted(_viejo)}")
r.check(sorted(clientes_alcanzados("Manzana", "precioszona", "hogares"))
        == ["Lucia Diaz", "Marta Lopez"],
        "el criterio nuevo deja 2")

print("\n=== 3. Nivel General: solo quien no tiene lista especial ===")
d_gen = diferencias_precio_historico({"manzana": 20.0}, "general", "",
                                     JUN1, JUN30)
r.check(sorted(d["row_num"] for d in d_gen) == [14],
        "solo Cafe del Rio cotiza por catálogo")
r.check(clientes_alcanzados("Manzana", "general", "") == ["Cafe del Rio"],
        "y es el único alcanzado por el nivel General")

print("\n=== 4. Una lista de zona que config no mapea no alcanza a nadie ===")
# "rio" está en PreciosZona pero no en ZONA_LISTA_CODIGOS: hoy no le da precio
# a nadie. Se puede detectar ANTES de aplicar, en vez de escribir en silencio.
r.check(zona_lista_de("L01") is None,
        "config no mapea L01 a ninguna lista de zona")
r.check(clientes_alcanzados("Manzana", "precioszona", "rio") == [],
        "la lista 'rio' no alcanza a ningún cliente")
r.check(diferencias_precio_historico(PRECIOS, "precioszona", "rio",
                                     JUN1, JUN30) == [],
        "y por lo tanto no propone ningún cambio")

print("\n=== 5. Nivel grupo ===")
d_grp = diferencias_precio_historico({"manzana": 9.5}, "preciosgrupo",
                                     "condominio", JUN1, JUN30)
r.check(sorted(d["row_num"] for d in d_grp) == [11],
        "editar el grupo alcanza solo a Cori")

print("\n=== 6. Calcular NO escribe ===")
r.check(ESCRITO == [], "la vista previa no toca el Sheet")

print("\n=== 7. Aplicar: escribe el precio, NUNCA el costo ===")
n = aplicar_precio_historico(difs)
pf = por_fila(ESCRITO)
r.check(n == 2, f"aplica 2 líneas ({n})")
r.check(sorted(pf) == [12, 13], f"escribe solo esas: {sorted(pf)}")
r.check(pf[12]["E"] == 12.0, f"precio nuevo en E: {pf[12]['E']}")
r.check(pf[12]["F"] == 6.0,
        f"el costo de la línea queda como estaba: {pf[12]['F']}")
r.check(abs(pf[12]["G"] - 48.0) < 1e-9, f"total 12.00 x 4 -> {pf[12]['G']}")
r.check(abs(pf[12]["H"] - 24.0) < 1e-9, f"totalCosto 6.00 x 4 -> {pf[12]['H']}")
r.check(abs(pf[12]["I"] - round(margen_neto_q(6.0, 12.0) * 4, 4)) < 1e-6,
        "margen recalculado con el precio nuevo")
r.check(set("EFGHIJK") <= set(pf[12]), f"fila coherente: {sorted(pf[12])}")

print("\n=== 8. La vista previa muestra el impacto ===")
d12 = next(d for d in difs if d["row_num"] == 12)
r.check(d12["Precio actual"] == 10.0 and d12["Precio nuevo"] == 12.0,
        "precio 10.00 -> 12.00")
r.check(d12["Total actual"] == 40.0 and d12["Total nuevo"] == 48.0,
        f"total {d12['Total actual']} -> {d12['Total nuevo']}")
r.check(d12["Margen nuevo"] > d12["Margen actual"],
        "subir el precio sube el margen: el impacto se ve antes de aplicar")
r.check("Fecha" in d12 and "Cliente" in d12,
        "cada línea se identifica por fecha y cliente")

print("\n=== 9. Casos borde ===")
ESCRITO.clear()
r.check(diferencias_precio_historico({}, "precioszona", "hogares",
                                     JUN1, JUN30) == [],
        "sin productos no devuelve nada")
r.check(diferencias_precio_historico(PRECIOS, "precioszona", "hogares",
                                     JUN30, JUN1) == [],
        "rango invertido no devuelve nada")
r.check(diferencias_precio_historico({"manzana": 0.0}, "precioszona",
                                     "hogares", JUN1, JUN30) == [],
        "un precio 0 no se aplica: borraría la venta")
r.check(diferencias_precio_historico({"manzana": 10.0}, "precioszona",
                                     "hogares", JUN1, JUN30) == [],
        "si el precio ya es el mismo, no hay nada que cambiar")
r.check(aplicar_precio_historico([]) == 0, "lista vacía devuelve 0")
r.check(ESCRITO == [], "y no manda ningún update")
r.check(diferencias_precio_historico(PRECIOS, "hoja_inventada", "x",
                                     JUN1, JUN30) == [],
        "un nivel desconocido no alcanza a nadie")

print("\n=== 10. El selector lee las listas de las HOJAS ===")
# Las listas especiales se crean en el Sheet sin tocar codigo, asi que
# hardcodearlas dejaria el selector viejo el dia que se agregue una.
import ast                                                     # noqa: E402
import os                                                      # noqa: E402

_HOJAS = {
    "precioszona":  [["Lista", "Producto", "Precio"],
                     ["Hogares", "Manzana", 10.0],
                     ["hogares", "Pera", 12.0],       # mismo nombre, otro caso
                     ["Rio", "Manzana", 11.0]],
    "preciosgrupo": [["Lista", "Producto", "Precio"],
                     ["Condominio", "Manzana", 9.0],
                     ["", "", ""]],                   # fila vacia de la hoja
}
_gs = types.ModuleType("gsheets")
_gs.get_all_rows = lambda hoja: [list(r) for r in _HOJAS[hoja]]
sys.modules["gsheets"] = _gs

_src = open(os.path.join(raiz_repo(), "modulo_productos.py"),
            encoding="utf-8").read()
_fn = next(n for n in ast.parse(_src).body
           if isinstance(n, ast.FunctionDef) and n.name == "_listas_de_precio")
_ns = {"st": sys.modules["streamlit"]}
exec(compile(ast.Module(body=[_fn], type_ignores=[]),
             "modulo_productos", "exec"), _ns)
opciones = _ns["_listas_de_precio"]()

r.check(opciones[0] == ("General (catálogo)", "general", ""),
        f"General va primero: {opciones[0]}")
_etiq = [o[0] for o in opciones]
r.check(_etiq == ["General (catálogo)", "Zona: Hogares", "Zona: Rio",
                  "Grupo: Condominio"],
        f"lee zonas y grupos de las hojas: {_etiq}")
r.check(sum(1 for o in opciones if o[0].startswith("Zona: Hogares")) == 1,
        "no duplica una lista que aparece en varias filas")
r.check(("Zona: Rio", "precioszona", "Rio") in opciones,
        "aparece incluso una zona que config no mapea: el aviso de alcance "
        "es el que va a decir que no le llega a nadie")
r.check(all(o[1] in ("general", "precioszona", "preciosgrupo")
            for o in opciones), "cada opción trae su hoja")

# Si una hoja falla, el selector no debe caerse: pierde esas listas y avisa.
_gs.get_all_rows = lambda hoja: (_ for _ in ()).throw(
    RuntimeError("sin credenciales"))
_ns2 = {"st": sys.modules["streamlit"]}
exec(compile(ast.Module(body=[_fn], type_ignores=[]),
             "modulo_productos", "exec"), _ns2)
r.check(_ns2["_listas_de_precio"]() == [("General (catálogo)", "general", "")],
        "si no se puede leer una hoja, queda General y no revienta")

r.salir()
