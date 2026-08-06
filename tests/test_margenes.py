"""
Control de Márgenes (Operación Diaria → 📈 Control de Márgenes).

Reporte de SOLO LECTURA. Lo que se pincha acá:
  - la aritmética de costo, ingreso y ambos márgenes;
  - que los % del TOTAL salgan de los totales y no de promediar filas — con
    productos de tamaños distintos, promediar da un margen que no existe;
  - que los filtros de área y proveedor recorten de verdad;
  - que nada escriba en el Sheet.

    python tests/test_margenes.py
"""
import sys
import types
from datetime import date

from _stubs import Reporte, instalar_streamlit, raiz_repo

raiz_repo()
instalar_streamlit()

ESCRITO = []

# Dos áreas, dos proveedores, un producto repetido en ambas áreas.
PEDIDOS = [
    {"row_num": 10, "cliente": "Hotelito", "producto": "Lechuga",
     "fecha": date(2026, 6, 3), "precio": 10.0, "costo": 6.0, "cantidad": 5,
     "proveedor": "Don Chus"},
    {"row_num": 11, "cliente": "Sundog", "producto": "Lechuga",
     "fecha": date(2026, 6, 5), "precio": 12.0, "costo": 6.0, "cantidad": 10,
     "proveedor": "Don Chus"},
    {"row_num": 12, "cliente": "Hotelito", "producto": "Salsa Pesto",
     "fecha": date(2026, 6, 8), "precio": 40.0, "costo": 20.0, "cantidad": 2,
     "proveedor": "Cocina"},
    # Fuera del rango que se va a consultar
    {"row_num": 13, "cliente": "Hotelito", "producto": "Lechuga",
     "fecha": date(2026, 7, 1), "precio": 10.0, "costo": 6.0, "cantidad": 99,
     "proveedor": "Don Chus"},
    # Cliente en EXCLUIR_PROVEEDORES ("wilson"): no cuenta como venta
    {"row_num": 14, "cliente": "Wilson Mayoreo", "producto": "Lechuga",
     "fecha": date(2026, 6, 4), "precio": 10.0, "costo": 6.0, "cantidad": 50,
     "proveedor": "Don Chus"},
    # Producto vacío: línea basura de la hoja
    {"row_num": 15, "cliente": "Hotelito", "producto": "  ",
     "fecha": date(2026, 6, 4), "precio": 10.0, "costo": 6.0, "cantidad": 7,
     "proveedor": "Don Chus"},
]

CLIENTES = [
    {"nombre": "Hotelito", "codigo_lugar": "L03", "grupo": ""},   # 🔖 Antigua & Chimal
    {"nombre": "Sundog",   "codigo_lugar": "L01", "grupo": ""},   # 🌊 Río
    {"nombre": "Wilson Mayoreo", "codigo_lugar": "L03", "grupo": ""},
]

from utils import _sf                                          # noqa: E402

excel_stub = types.ModuleType("excel_helper")
excel_stub.leer_pedidos_op = lambda: [dict(p) for p in PEDIDOS]
excel_stub.leer_pedidos    = excel_stub.leer_pedidos_op
excel_stub._sf = _sf
excel_stub._si = lambda v: int(_sf(v))
sys.modules["excel_helper"] = excel_stub

gsheets = types.ModuleType("gsheets")
gsheets.update_cells = lambda hoja, ups: ESCRITO.extend(ups)
gsheets.append_rows  = lambda *a, **k: None
gsheets.get_all_rows = lambda *a, **k: []
sys.modules["gsheets"] = gsheets

import config                                                   # noqa: E402
from config import ZONAS_MAP, margen_neto_q                     # noqa: E402

# data_helper real necesita streamlit+gspread; se sustituye por un doble que
# reproduce mapa_area_grupo con la MISMA regla (codigo_lugar contra ZONAS_MAP).
_cod_area = {c: n for n, cods in ZONAS_MAP.items() for c in cods}
data_helper = types.ModuleType("data_helper")
FACTURA = {"hotelito": True, "sundog": False, "desconocido": None}
data_helper.mapa_factura = lambda: dict(FACTURA)
data_helper.mapa_area_grupo = lambda: {
    c["nombre"].lower(): {"area": _cod_area.get(c["codigo_lugar"], "Sin área"),
                          "grupo": c["grupo"] or "Sin grupo"}
    for c in CLIENTES}
data_helper.cargar_clientes = lambda: CLIENTES
sys.modules["data_helper"] = data_helper

from modulo_margenes import agregar_margenes, totales, _pct     # noqa: E402

JUN1, JUN30 = date(2026, 6, 1), date(2026, 6, 30)
# El nombre del area sale de ZONAS_MAP, no se escribe a mano: si el
# catalogo renombra una zona, el test debe seguir apuntando a la misma.
AREA_ANT = next(n for n, c in ZONAS_MAP.items() if "L03" in c)
AREA_RIO = next(n for n, c in ZONAS_MAP.items() if "L01" in c)
r = Reporte()

print("=== 1. Alcance: qué líneas entran ===")
df = agregar_margenes(JUN1, JUN30, (), ())
prods = sorted(df["Producto"])
r.check(prods == ["Lechuga", "Salsa Pesto"], f"productos: {prods}")
lech = df[df["Producto"] == "Lechuga"].iloc[0]
r.check(lech["Cantidad"] == 15.0,
        f"cantidad = solo junio, sin excluidos: {lech['Cantidad']} (5+10)")
r.check(99 not in list(df["Cantidad"]), "julio queda fuera del rango")

print("\n=== 2. Aritmética por producto ===")
r.check(lech["Costo (Q)"] == 90.0,   f"costo 6x5 + 6x10 = {lech['Costo (Q)']}")
r.check(lech["Ingreso (Q)"] == 170.0,
        f"ingreso 10x5 + 12x10 = {lech['Ingreso (Q)']}")
r.check(lech["Margen Bruto (Q)"] == 80.0,
        f"bruto = ingreso - costo = {lech['Margen Bruto (Q)']}")
# Hotelito factura (descuenta) y Sundog no (precio - costo). El neto se
# acumula línea por línea y cada una usa la regla de SU cliente.
from config import margen_neto_q_cliente as _mnc               # noqa: E402
_neto_esp = _mnc(6.0, 10.0, True) * 5 + _mnc(6.0, 12.0, False) * 10
r.check(abs(lech["Margen Neto (Q)"] - round(_neto_esp, 2)) < 0.01,
        f"neto por línea, con la regla de cada cliente: "
        f"{lech['Margen Neto (Q)']}")
r.check(lech["Margen Neto (Q)"] < lech["Margen Bruto (Q)"],
        "el neto del producto queda debajo del bruto porque parte se facturó")
r.check(lech["Margen Neto (Q)"] > margen_neto_q(6.0, 10.0) * 5
                                 + margen_neto_q(6.0, 12.0) * 10,
        "y es MAYOR que descontándole a todos: es la corrección de Factura=No")
r.check(abs(lech["Bruto %"] - round(80.0 / 170.0 * 100, 1)) < 0.05,
        f"bruto % sobre ingreso: {lech['Bruto %']}%")

print("\n=== 3. El TOTAL % sale de los totales, no del promedio de filas ===")
t = totales(df)
r.check(abs(t["ingreso"] - 250.0) < 0.01, f"ingreso total: {t['ingreso']}")
r.check(abs(t["costo"] - 130.0) < 0.01,   f"costo total: {t['costo']}")
r.check(abs(t["bruto"] - 120.0) < 0.01,   f"bruto total: {t['bruto']}")
r.check(abs(t["bruto_pct"] - 48.0) < 0.05,
        f"bruto % del total = 120/250 = {t['bruto_pct']}%")
_promedio = sum(df["Bruto %"]) / len(df)
r.check(abs(_promedio - t["bruto_pct"]) > 0.5,
        f"y NO es el promedio de las filas ({_promedio:.1f}%), que sería otro "
        f"número")
r.check(abs(t["neto_pct"] - round(t["neto"] / t["ingreso"] * 100, 1)) < 0.05,
        "el neto % también sale de los totales")

print("\n=== 4. Filtros ===")
d_ant = agregar_margenes(JUN1, JUN30, (AREA_ANT,), ())
r.check(float(d_ant[d_ant["Producto"] == "Lechuga"]["Cantidad"].iloc[0]) == 5.0,
        "filtrar por área deja solo las 5 de Hotelito")
d_pv = agregar_margenes(JUN1, JUN30, (), ("Cocina",))
r.check(sorted(d_pv["Producto"]) == ["Salsa Pesto"],
        f"filtrar por proveedor: {sorted(d_pv['Producto'])}")
r.check(agregar_margenes(JUN1, JUN30, (AREA_ANT,), ("Cocina",)).shape[0] == 1,
        "los dos filtros se combinan (AND)")
r.check(agregar_margenes(JUN1, JUN30, ("No Existe",), ()).empty,
        "un filtro sin coincidencias devuelve vacío, no todo")

print("\n=== 5. Casos borde ===")
r.check(agregar_margenes(date(2026, 1, 1), date(2026, 1, 31), (), ()).empty,
        "rango sin pedidos devuelve vacío")
r.check(agregar_margenes(JUN30, JUN1, (), ()).empty,
        "rango invertido no devuelve nada")
r.check(totales(agregar_margenes(JUN30, JUN1, (), ()))["ingreso"] == 0.0,
        "totales de un DataFrame vacío no explota")
r.check(_pct(50.0, 0.0) == 0.0,
        "sin ingreso el % es 0, no una división por cero")

print("\n=== 5b. Las tres dimensiones: mismo total, otro reparto ===")
from modulo_margenes import DIMENSIONES, cols_de              # noqa: E402

d_cli  = agregar_margenes(JUN1, JUN30, (), (), "Cliente")
d_area = agregar_margenes(JUN1, JUN30, (), (), "Área")
r.check(sorted(DIMENSIONES) == ["Cliente", "Producto", "Área"],
        f"dimensiones disponibles: {sorted(DIMENSIONES)}")
r.check(list(d_cli.columns)[0] == "Cliente"
        and list(d_area.columns)[0] == "Área",
        "la primera columna es la dimensión elegida")
r.check(list(d_cli.columns)[1:] == list(df.columns)[1:],
        "las columnas de métrica son las mismas en las tres")
r.check(sorted(d_cli["Cliente"]) == ["Hotelito", "Sundog"],
        f"por cliente: {sorted(d_cli['Cliente'])}")
r.check(sorted(d_area["Área"]) == sorted({AREA_ANT, AREA_RIO}),
        f"por área: {sorted(d_area['Área'])}")

# Lo que hay que proteger: cambiar de pestaña reparte, no recalcula. Si un
# total difiere, dos pestañas del mismo reporte se contradicen en pantalla.
for _col in ("Costo (Q)", "Ingreso (Q)", "Margen Bruto (Q)",
             "Margen Neto (Q)", "Cantidad"):
    _p, _c, _a = (float(x[_col].sum()) for x in (df, d_cli, d_area))
    r.check(abs(_p - _c) < 0.01 and abs(_p - _a) < 0.01,
            f"{_col}: producto {_p:,.2f} = cliente {_c:,.2f} = área {_a:,.2f}")
for _k in ("ingreso", "costo", "bruto", "neto", "bruto_pct", "neto_pct"):
    r.check(abs(totales(d_cli)[_k] - totales(df)[_k]) < 0.05,
            f"totales['{_k}'] no cambia entre pestañas")

print("\n=== 5c. Los filtros siguen aplicando en cada dimensión ===")
r.check(sorted(agregar_margenes(JUN1, JUN30, (AREA_ANT,), (), "Cliente")
               ["Cliente"]) == ["Hotelito"],
        "filtrar por área deja un solo cliente")
r.check(list(agregar_margenes(JUN1, JUN30, (), ("Cocina",), "Área")["Área"])
        == [AREA_ANT], "filtrar por proveedor recorta también la vista por área")
r.check(agregar_margenes(JUN1, JUN30, ("No Existe",), (), "Cliente").empty,
        "un filtro sin coincidencias devuelve vacío en cualquier dimensión")
r.check(list(cols_de("Cliente")) == ["Cliente"] + list(df.columns)[1:],
        "cols_de arma el encabezado de cada dimensión")

print("\n=== 5d. Factura=No: NO se descuentan impuestos ===")
from modulo_margenes import clientes_sin_factura_cargada      # noqa: E402

d_cli2 = agregar_margenes(JUN1, JUN30, (), (), "Cliente")
_hot = d_cli2[d_cli2["Cliente"] == "Hotelito"].iloc[0]
_sun = d_cli2[d_cli2["Cliente"] == "Sundog"].iloc[0]

# EL invariante: al que no lleva factura no se le resta IVA ni ISR, así que su
# margen neto es exactamente el bruto. Si alguien deja un 0.95 colgado, falla.
r.check(_sun["Margen Neto (Q)"] == _sun["Margen Bruto (Q)"],
        f"Sundog (Factura=No): neto {_sun['Margen Neto (Q)']} == "
        f"bruto {_sun['Margen Bruto (Q)']}")
r.check(_sun["Neto %"] == _sun["Bruto %"], "y los % también coinciden")

_esp_hot = round(margen_neto_q(6.0, 10.0) * 5 + margen_neto_q(20.0, 40.0) * 2, 2)
r.check(abs(_hot["Margen Neto (Q)"] - _esp_hot) < 0.01,
        f"Hotelito (Factura=Sí): descuenta como siempre, "
        f"{_hot['Margen Neto (Q)']}")
r.check(_hot["Margen Neto (Q)"] < _hot["Margen Bruto (Q)"],
        "o sea que ahí el neto SÍ queda por debajo del bruto")

# Contraprueba: sin la regla, Sundog daría el valor descontado. Sin esto, el
# check de arriba pasaría también con una implementación que ignore el campo.
_sun_con_desc = round(margen_neto_q(6.0, 12.0) * 10, 2)
r.check(abs(_sun["Margen Neto (Q)"] - _sun_con_desc) > 1.0,
        f"si se le descontara, Sundog daría {_sun_con_desc} y no "
        f"{_sun['Margen Neto (Q)']}")

print("\n=== 5e. Default conservador: sin dato descuenta ===")
r.check(_mnc(6.0, 10.0, None) == _mnc(6.0, 10.0, True) == margen_neto_q(6.0, 10.0),
        "sin dato se comporta como CON factura: no cambia lo que ya existía")
r.check(_mnc(6.0, 10.0, False) == 10.0 - 6.0,
        f"y sin factura es precio - costo: {_mnc(6.0, 10.0, False)}")
r.check(_mnc(6.0, 10.0, False) > _mnc(6.0, 10.0, None),
        "sin factura el margen es MAYOR: es la corrección esperada")

print("\n=== 5f. La regla aplica en las TRES dimensiones ===")
# Es un hecho del cliente, no de la vista: si solo corrigiera Por Cliente, los
# totales dejarían de cuadrar entre pestañas.
for _col in ("Margen Neto (Q)", "Margen Bruto (Q)"):
    _p = float(agregar_margenes(JUN1, JUN30, (), (), "Producto")[_col].sum())
    _c = float(d_cli2[_col].sum())
    _a = float(agregar_margenes(JUN1, JUN30, (), (), "Área")[_col].sum())
    r.check(abs(_p - _c) < 0.01 and abs(_p - _a) < 0.01,
            f"{_col} cuadra en las tres: {_p:,.2f}")

print("\n=== 6. El reporte NO escribe ===")
r.check(ESCRITO == [], "ningún update_cells: es solo lectura")

print("\n=== 7. El PDF se genera con lo que muestra la pantalla ===")
try:
    from pdf_helper import generar_reporte_margenes, _sin_emoji
    pdf = generar_reporte_margenes(df.to_dict("records"), JUN1, JUN30,
                                   f"Área: {AREA_ANT}", t)
    r.check(pdf[:4] == b"%PDF" and len(pdf) > 1200,
            f"PDF válido de {len(pdf):,} bytes")
    # Los nombres de zona traen emoji; Helvetica no los tiene y los imprimiría
    # como un cuadro negro, así que se limpian antes de maquetar.
    r.check(_sin_emoji(AREA_ANT) == "Antigua & Chimal",
            f"el nombre de zona llega al papel sin el emoji: "
            f"{_sin_emoji(AREA_ANT)!r}")
    r.check(_sin_emoji("Área: 🏙️ Guatemala") == "Área: Guatemala",
            "también con selector de variación (U+FE0F), y sin perder acentos")
    r.check(_sin_emoji("sin filtros (todas las áreas)")
            == "sin filtros (todas las áreas)",
            "un texto sin emoji queda intacto")
    # El PDF de cada pestaña lee la columna de SU dimensión: si quedara fijo en
    # "Producto", las vistas por cliente y por área saldrían con la primera
    # columna en blanco y nadie lo notaría hasta imprimir.
    for _dim, _datos in (("Cliente", d_cli), ("Área", d_area)):
        _pdf = generar_reporte_margenes(_datos.to_dict("records"), JUN1, JUN30,
                                        "", totales(_datos), dim=_dim)
        r.check(_pdf[:4] == b"%PDF" and len(_pdf) > 1200,
                f"PDF por {_dim}: {len(_pdf):,} bytes")
except ImportError:
    print("  (reportlab no instalado: se omite)")

r.salir()
