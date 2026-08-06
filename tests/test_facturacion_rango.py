"""
Facturación por rango de fechas (Facturación Mensual → 🧾 Facturación del mes).

La pestaña dejó de filtrar por mes/año y pasó a filtrar por un rango con los
dos bordes incluidos. El modo Mes NO es una rama aparte: es el mismo filtro,
con desde/hasta calculados por utils.rango_mes.

Lo que se pincha:
  - los bordes del rango entran (>= desde, <= hasta), y un día afuera queda
    afuera — es la clase de error que hace facturar de menos o de más;
  - el modo Mes da EXACTAMENTE lo mismo que el filtro viejo por mes/año. Se
    compara contra una reimplementación de esa regla, no contra números
    escritos a mano: así el test falla si el atajo del mes se desvía;
  - las exclusiones de siempre (cancelado, sin producto, sin fecha) siguen;
  - la etiqueta del período dice el mes solo si el rango ES ese mes entero.
    Del 01/07 al 30/07 no lo es: le falta el 31.

    python tests/test_facturacion_rango.py
"""
import sys
import types
from datetime import date

from _stubs import Reporte, instalar_streamlit, raiz_repo

raiz_repo()
instalar_streamlit()


def _ped(cli, prod, f, precio, cant, status="Pendiente", semana=None):
    """Una línea como la arma excel_helper.leer_pedidos: 'total' ya calculado
    y 'semana' la de la hoja (None = que la deduzca de la fecha)."""
    return {"cliente": cli, "producto": prod, "fecha": f, "precio": precio,
            "cantidad": cant, "unidad": "lb", "status": status,
            "total": round(precio * cant, 2) if precio and cant else 0,
            "semana": semana, "año": f.year if f else None}


JUL1  = date(2026, 7, 1)     # primer día de julio
JUL20 = date(2026, 7, 20)
JUL31 = date(2026, 7, 31)    # último día de julio
AGO1  = date(2026, 8, 1)
AGO10 = date(2026, 8, 10)
JUN30 = date(2026, 6, 30)

PEDIDOS = [
    # Cazador Italiano: uno en cada borde de julio y uno en el medio.
    _ped("Cazador Italiano", "Lechuga", JUL1,  10.0, 10),   # Q100
    _ped("Cazador Italiano", "Tomate",  JUL20, 20.0, 10),   # Q200
    _ped("Cazador Italiano", "Cebolla", JUL31, 30.0, 10),   # Q300
    # Doña Luz: justo antes de julio y ya en agosto.
    _ped("Doña Luz", "Lechuga", JUN30, 40.0, 10),           # Q400
    _ped("Doña Luz", "Tomate",  AGO1,  50.0, 10),           # Q500
    _ped("Doña Luz", "Cebolla", AGO10, 60.0, 10),           # Q600
    # Basura que nunca debe entrar, toda dentro de julio para que el filtro de
    # fechas no la esté tapando de casualidad.
    _ped("Cazador Italiano", "Zanahoria", date(2026, 7, 15), 99.0, 10,
         status="Cancelado"),
    _ped("Cazador Italiano", "",          date(2026, 7, 16), 99.0, 10),
    _ped("Cazador Italiano", "Papa",      None,              99.0, 10),
    # Mismo mes y día, otro año: el rango tiene que verlo distinto.
    _ped("Cazador Italiano", "Lechuga", date(2025, 7, 20), 70.0, 10),
]

excel_stub = types.ModuleType("excel_helper")
excel_stub.leer_pedidos = lambda: [dict(p) for p in PEDIDOS]
sys.modules["excel_helper"] = excel_stub

data_stub = types.ModuleType("data_helper")
data_stub.cargar_clientes = lambda: []
data_stub.mapa_area_grupo = lambda: {}
sys.modules["data_helper"] = data_stub

gsheets = types.ModuleType("gsheets")
gsheets.update_cells = lambda *a, **k: None
gsheets.append_rows  = lambda *a, **k: None
gsheets.get_all_rows = lambda *a, **k: []
sys.modules["gsheets"] = gsheets

# pdf_helper de verdad necesita reportlab; acá solo se prueba el filtrado, así
# que va doble. El PDF tiene su propio archivo: test_facturacion_rango_pdf.py
pdf_stub = types.ModuleType("pdf_helper")
pdf_stub.generar_facturacion_mensual = lambda *a, **k: b""
pdf_stub.nombre_archivo_factura = lambda *a, **k: "x.pdf"
sys.modules["pdf_helper"] = pdf_stub

from utils import etiqueta_periodo, es_mes_completo, rango_mes   # noqa: E402
from modulo_facturacion import _construir_datos, _clave_periodo  # noqa: E402

r = Reporte()


def _totales(datos: dict) -> dict:
    return {cli: round(v["total"], 2) for cli, v in datos.items()}


def _filtro_viejo(pedidos: list, mes: int, año: int) -> dict:
    """La regla que tenía _construir_datos ANTES del rango. Se conserva acá
    como referencia: el modo Mes tiene que seguir dando esto y nada más."""
    tot = {}
    for p in pedidos:
        if p["status"] == "Cancelado": continue
        if not p["fecha"]:             continue
        if p["fecha"].month != mes:    continue
        if p["fecha"].year  != año:    continue
        if not p["producto"]:          continue
        tot[p["cliente"]] = round(tot.get(p["cliente"], 0)
                                  + float(p["total"]), 2)
    return tot


print("=== 1. rango_mes calcula bien los dos bordes ===")
r.check(rango_mes(7, 2026) == (JUL1, JUL31), f"julio 2026 → {rango_mes(7, 2026)}")
r.check(rango_mes(2, 2024) == (date(2024, 2, 1), date(2024, 2, 29)),
        "febrero bisiesto termina el 29")
r.check(rango_mes(2, 2026) == (date(2026, 2, 1), date(2026, 2, 28)),
        "febrero normal termina el 28")
r.check(rango_mes(12, 2026) == (date(2026, 12, 1), date(2026, 12, 31)),
        "diciembre no se pasa al año siguiente")

print("\n=== 2. El rango incluye los dos bordes ===")
d = _construir_datos(PEDIDOS, JUL20, AGO10)
r.check(_totales(d) == {"Cazador Italiano": 500.0, "Doña Luz": 1100.0},
        f"del 20/07 al 10/08 → {_totales(d)}")
r.check("Lechuga" not in [l["producto"]
                          for s in d["Cazador Italiano"]["por_semana"].values()
                          for l in s["lineas"]],
        "el pedido del 01/07 (fuera del rango) no entró")

# Un día adentro de cada borde: se caen justo los dos pedidos de los extremos.
d2 = _construir_datos(PEDIDOS, date(2026, 7, 21), date(2026, 8, 9))
r.check(_totales(d2) == {"Cazador Italiano": 300.0, "Doña Luz": 500.0},
        f"del 21/07 al 09/08 deja afuera ambos bordes → {_totales(d2)}")

d3 = _construir_datos(PEDIDOS, JUL20, JUL20)
r.check(_totales(d3) == {"Cazador Italiano": 200.0},
        f"un solo día trae solo ese día → {_totales(d3)}")

print("\n=== 3. El modo Mes da exactamente lo de siempre ===")
for mes, año in ((7, 2026), (8, 2026), (6, 2026), (7, 2025), (2, 2026)):
    esperado = _filtro_viejo(PEDIDOS, mes, año)
    obtenido = _totales(_construir_datos(PEDIDOS, *rango_mes(mes, año)))
    r.check(obtenido == esperado,
            f"{mes:02d}/{año}: rango_mes == filtro viejo → {obtenido}")

r.check(_totales(_construir_datos(PEDIDOS, *rango_mes(7, 2026)))
        == {"Cazador Italiano": 600.0},
        "julio 2026 suma los tres pedidos del mes (Q600)")
r.check(_totales(_construir_datos(PEDIDOS, *rango_mes(7, 2025)))
        == {"Cazador Italiano": 700.0},
        "el mismo mes de otro año no se mezcla (Q700)")

print("\n=== 4. Las exclusiones de siempre siguen ===")
todo_julio = _construir_datos(PEDIDOS, JUL1, JUL31)
prods = [l["producto"]
         for c in todo_julio.values()
         for s in c["por_semana"].values() for l in s["lineas"]]
r.check("Zanahoria" not in prods, "un pedido Cancelado no se factura")
r.check("" not in prods, "una línea sin producto no entra")
r.check("Papa" not in prods, "una línea sin fecha no entra")
r.check(len(prods) == 3, f"julio deja exactamente 3 líneas ({len(prods)})")

print("\n=== 5. La agrupación por semana no cambió ===")
c = _construir_datos(PEDIDOS, JUL20, AGO10)["Doña Luz"]["por_semana"]
r.check(set(c.keys()) == {AGO1.isocalendar()[1], AGO10.isocalendar()[1]},
        f"semanas deducidas de la fecha cuando la hoja no las trae: {sorted(c)}")
sem_ago1 = c[AGO1.isocalendar()[1]]
r.check(sem_ago1["fecha"] == AGO1 and len(sem_ago1["lineas"]) == 1,
        "cada semana guarda su fecha más temprana y sus líneas")

cruza = _construir_datos(PEDIDOS, date(2026, 6, 25), date(2026, 8, 5))
r.check(_totales(cruza) == {"Cazador Italiano": 600.0, "Doña Luz": 900.0},
        f"un rango que cruza tres meses junta las partes → {_totales(cruza)}")

print("\n=== 6. La etiqueta del período nunca miente ===")
r.check(etiqueta_periodo(JUL1, JUL31) == "Julio 2026",
        f"julio entero se llama por su nombre: {etiqueta_periodo(JUL1, JUL31)}")
r.check(etiqueta_periodo(JUL20, AGO10) == "del 20/07/2026 al 10/08/2026",
        f"un rango libre muestra las fechas: {etiqueta_periodo(JUL20, AGO10)}")
r.check(etiqueta_periodo(JUL1, date(2026, 7, 30))
        == "del 01/07/2026 al 30/07/2026",
        "del 01/07 al 30/07 NO es 'Julio 2026': le falta el 31")
r.check(etiqueta_periodo(date(2026, 7, 2), JUL31)
        == "del 02/07/2026 al 31/07/2026",
        "arrancar el 02 tampoco es el mes completo")
r.check(etiqueta_periodo(JUL20, JUL20) == "del 20/07/2026 al 20/07/2026",
        "un solo día se muestra como rango, no como mes")
r.check(es_mes_completo(*rango_mes(2, 2024))
        and not es_mes_completo(date(2024, 2, 1), date(2024, 2, 28)),
        "febrero bisiesto solo está completo con el 29 adentro")

print("\n=== 7. La key de widget distingue períodos ===")
r.check(_clave_periodo(JUL1, JUL31) != _clave_periodo(JUL1, date(2026, 7, 30)),
        "dos rangos distintos no comparten key (si no, Streamlit reusa el PDF)")
r.check(_clave_periodo(JUL20, AGO10) == "20260720_20260810",
        f"la key lleva las dos fechas: {_clave_periodo(JUL20, AGO10)}")

r.salir()
