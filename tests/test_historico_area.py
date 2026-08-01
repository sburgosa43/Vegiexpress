"""
Histórico por Área (Facturación Mensual → 📊 Histórico por Área).

Reporte de SOLO LECTURA sobre un rango libre de fechas. Lo que se pincha:
  - venta y compra salen del precio y costo GUARDADOS en cada línea;
  - los filtros de fecha y cliente recortan de verdad;
  - las tres granularidades (Mes / Semana / Solo área) agrupan bien;
  - el % del TOTAL sale de los totales, no de promediar filas;
  - nada escribe en el Sheet.

    python tests/test_historico_area.py
"""
import sys
import types
from datetime import date

from _stubs import Reporte, instalar_streamlit, raiz_repo

raiz_repo()
instalar_streamlit()

ESCRITO = []

# 'total' es precio x cantidad, igual que lo arma excel_helper.leer_pedidos.
def _ped(row, cli, prod, f, precio, costo, cant, sem, año):
    return {"row_num": row, "cliente": cli, "producto": prod, "fecha": f,
            "precio": precio, "costo": costo, "cantidad": cant,
            "total": round(precio * cant, 2), "semana": sem, "año": año,
            "proveedor": "Don Chus", "status": "Pendiente"}


PEDIDOS = [
    # Junio 2026 — Antigua (Hotelito)
    _ped(10, "Hotelito", "Lechuga",     date(2026, 6, 3), 10.0, 6.0,  5, 23, 2026),
    _ped(11, "Hotelito", "Tomate",      date(2026, 6, 3), 20.0, 12.0, 2, 23, 2026),
    # Junio 2026 — Río (Sundog), otra semana
    _ped(12, "Sundog",   "Lechuga",     date(2026, 6, 17), 12.0, 6.0, 10, 25, 2026),
    # Julio 2026 — Antigua
    _ped(13, "Hotelito", "Lechuga",     date(2026, 7, 8), 11.0, 6.0,  4, 28, 2026),
    # Línea sin producto: basura de la hoja
    _ped(14, "Hotelito", "  ",          date(2026, 6, 4), 10.0, 6.0,  7, 23, 2026),
    # Cliente sin codigo_lugar conocido -> "Sin área"
    _ped(15, "Desconocido", "Lechuga",  date(2026, 6, 5), 10.0, 6.0,  3, 23, 2026),
]

CLIENTES = [
    {"nombre": "Hotelito", "codigo_lugar": "L03", "grupo": ""},
    {"nombre": "Sundog",   "codigo_lugar": "L01", "grupo": ""},
]

from utils import _sf                                          # noqa: E402

excel_stub = types.ModuleType("excel_helper")
excel_stub.leer_pedidos    = lambda: [dict(p) for p in PEDIDOS]
excel_stub.leer_pedidos_op = excel_stub.leer_pedidos
excel_stub._sf = _sf
excel_stub._si = lambda v: int(_sf(v))
sys.modules["excel_helper"] = excel_stub

gsheets = types.ModuleType("gsheets")
gsheets.update_cells = lambda hoja, ups: ESCRITO.extend(ups)
gsheets.append_rows  = lambda *a, **k: None
gsheets.get_all_rows = lambda *a, **k: []
sys.modules["gsheets"] = gsheets

from config import ZONAS_MAP                                   # noqa: E402

_cod_area = {c: n for n, cods in ZONAS_MAP.items() for c in cods}
MAPA = {c["nombre"].lower(): {"area": _cod_area.get(c["codigo_lugar"],
                                                    "Sin área"),
                              "grupo": "Sin grupo"}
        for c in CLIENTES}

data_helper = types.ModuleType("data_helper")
data_helper.mapa_area_grupo = lambda: MAPA
data_helper.cargar_clientes = lambda: CLIENTES
sys.modules["data_helper"] = data_helper

pdf_stub = types.ModuleType("pdf_helper")
pdf_stub.generar_facturacion_mensual = lambda *a, **k: b""
pdf_stub.nombre_archivo_factura = lambda *a, **k: "x.pdf"
pdf_stub.MESES_ES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                     "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre",
                     "Diciembre"]
sys.modules["pdf_helper"] = pdf_stub

from modulo_facturacion import (agregar_historico,             # noqa: E402
                                totales_historico,
                                _rango_historico, _periodo_de)

AREA_ANT = next(n for n, c in ZONAS_MAP.items() if "L03" in c)
AREA_RIO = next(n for n, c in ZONAS_MAP.items() if "L01" in c)
JUN1, JUL31 = date(2026, 6, 1), date(2026, 7, 31)

r = Reporte()

print("=== 1. Venta y compra por área, agrupadas por mes ===")
df = agregar_historico(PEDIDOS, MAPA, JUN1, JUL31, (), "Mes")
jun_ant = df[(df["Período"] == "2026-06") & (df["Área"] == AREA_ANT)].iloc[0]
r.check(jun_ant["Venta (Q)"] == 90.0,
        f"venta 10x5 + 20x2 = {jun_ant['Venta (Q)']}")
r.check(jun_ant["Compra (Q)"] == 54.0,
        f"compra 6x5 + 12x2 = {jun_ant['Compra (Q)']}")
r.check(jun_ant["Diferencia (Q)"] == 36.0,
        f"diferencia = venta - compra = {jun_ant['Diferencia (Q)']}")
r.check(jun_ant["Líneas"] == 2,
        f"la línea sin producto no cuenta: {jun_ant['Líneas']} línea(s)")
r.check(abs(jun_ant["Dif %"] - 40.0) < 0.05,
        f"dif % sobre la venta = 36/90 = {jun_ant['Dif %']}%")

print("\n=== 2. Cada área va por separado, y julio no se mezcla con junio ===")
periodos = sorted(set(df["Período"]))
r.check(periodos == ["2026-06", "2026-07"], f"períodos: {periodos}")
r.check(df[df["Período"] == "2026-06"].shape[0] == 3,
        "junio abre en 3 áreas (Antigua, Río y Sin área)")
r.check(float(df[(df["Período"] == "2026-07")]["Venta (Q)"].iloc[0]) == 44.0,
        "julio queda aparte: 11x4")
r.check(df["Período"].iloc[0] == "2026-07",
        "lo más reciente va arriba")

print("\n=== 3. Cliente sin codigo_lugar cae en 'Sin área', no se pierde ===")
sin = df[df["Área"] == "Sin área"]
r.check(not sin.empty and float(sin["Venta (Q)"].iloc[0]) == 30.0,
        "el desconocido aparece con su venta (10x3), no se descarta")

print("\n=== 4. Granularidades ===")
d_sem = agregar_historico(PEDIDOS, MAPA, JUN1, JUL31, (), "Semana")
r.check("2026-S23" in set(d_sem["Período"]),
        f"por semana usa año-Snn: {sorted(set(d_sem['Período']))}")
r.check(d_sem[(d_sem["Período"] == "2026-S25")]["Área"].iloc[0] == AREA_RIO,
        "la semana 25 es la de Sundog (Río)")
d_tot = agregar_historico(PEDIDOS, MAPA, JUN1, JUL31, (), "Solo área (todo el rango)")
r.check(set(d_tot["Período"]) == {"Todo el rango"},
        "'Solo área' colapsa todo en un período")
r.check(d_tot.shape[0] == 3, f"y deja una fila por área: {d_tot.shape[0]}")
r.check(abs(float(d_tot["Venta (Q)"].sum()) - float(df["Venta (Q)"].sum())) < 0.01,
        "cambiar la granularidad no cambia el total")

print("\n=== 5. Filtros ===")
d_cli = agregar_historico(PEDIDOS, MAPA, JUN1, JUL31, ("Hotelito",), "Mes")
r.check(set(d_cli["Área"]) == {AREA_ANT},
        "filtrar por cliente deja solo su área")
r.check(abs(float(d_cli["Venta (Q)"].sum()) - 134.0) < 0.01,
        f"y solo su venta (90 + 44): {float(d_cli['Venta (Q)'].sum())}")
d_jun = agregar_historico(PEDIDOS, MAPA, JUN1, date(2026, 6, 30), (), "Mes")
r.check(set(d_jun["Período"]) == {"2026-06"},
        "el rango de fechas recorta julio")
r.check(agregar_historico(PEDIDOS, MAPA, JUN1, JUL31, ("Nadie",), "Mes").empty,
        "un cliente sin coincidencias devuelve vacío, no todo")

print("\n=== 6. El TOTAL % sale de los totales, no del promedio de filas ===")
t = totales_historico(df)
r.check(abs(t["venta"] - 284.0) < 0.01, f"venta total: {t['venta']}")
r.check(abs(t["compra"] - 156.0) < 0.01, f"compra total: {t['compra']}")
r.check(abs(t["dif"] - 128.0) < 0.01, f"diferencia total: {t['dif']}")
r.check(abs(t["dif_pct"] - round(128.0 / 284.0 * 100, 1)) < 0.05,
        f"dif % del total = 128/284 = {t['dif_pct']}%")
_prom = sum(df["Dif %"]) / len(df)
r.check(abs(_prom - t["dif_pct"]) > 0.5,
        f"y NO es el promedio de las filas ({_prom:.1f}%)")
r.check(t["lineas"] == 5, f"líneas de pedido contadas: {t['lineas']}")

print("\n=== 7. Casos borde ===")
r.check(agregar_historico(PEDIDOS, MAPA, date(2025, 1, 1), date(2025, 1, 31),
                          (), "Mes").empty,
        "rango sin pedidos devuelve vacío")
r.check(agregar_historico(PEDIDOS, MAPA, JUL31, JUN1, (), "Mes").empty,
        "rango invertido no devuelve nada")
r.check(totales_historico(agregar_historico(PEDIDOS, MAPA, JUL31, JUN1,
                                            (), "Mes"))["venta"] == 0.0,
        "totales de un DataFrame vacío no explota")
_regalado = [_ped(90, "Hotelito", "Muestra", date(2026, 6, 9), 0.0, 4.0, 1,
                  23, 2026)]
_d0 = agregar_historico(_regalado, MAPA, JUN1, JUL31, (), "Mes")
r.check(float(_d0["Dif %"].iloc[0]) == 0.0,
        "venta 0 no divide por cero (producto regalado con costo)")
r.check(float(_d0["Diferencia (Q)"].iloc[0]) == -4.0,
        "y la diferencia sí queda negativa: costó y no se cobró")

print("\n=== 8. Atajos de rango ===")
HOY = date(2026, 8, 1)
r.check(_rango_historico("Este año", HOY, PEDIDOS)[0] == date(2026, 1, 1),
        "'Este año' arranca el 1 de enero")
r.check(_rango_historico("Todo", HOY, PEDIDOS)[0] == date(2026, 6, 3),
        "'Todo' arranca en el pedido más viejo de la hoja, no en fecha fija")
r.check(_rango_historico("Todo", HOY, [])[0] == HOY,
        "sin pedidos, 'Todo' no explota")
r.check(_rango_historico("Últimos 12 meses", HOY, PEDIDOS)[1] == HOY,
        "el 'hasta' de los atajos es hoy")

print("\n=== 9. El reporte NO escribe ===")
r.check(ESCRITO == [], "ningún update_cells: es solo lectura")

print("\n=== 10. Exportación e impresión ===")
# El PDF debe salir de las MISMAS filas que muestra la pantalla: si maquetara
# a partir de otra cosa, papel y pantalla podrian discrepar sin que se note.
sys.modules.pop("pdf_helper", None)
try:
    from pdf_helper import generar_reporte_historico, generar_pdf_reporte
    pdf = generar_reporte_historico(df.to_dict("records"), JUN1, JUL31,
                                    f"Cliente: Hotelito · Ver por: Mes", t)
    r.check(pdf[:4] == b"%PDF" and len(pdf) > 1200,
            f"PDF válido de {len(pdf):,} bytes")
    r.check(generar_reporte_historico([], JUN1, JUL31, "", {})[:4] == b"%PDF",
            "un reporte sin filas tampoco explota")
    # Sin fila_total no debe dibujarse un TOTAL en blanco.
    r.check(generar_reporte_historico(df.to_dict("records"), JUN1, JUL31,
                                      "", None)[:4] == b"%PDF",
            "sin totales tambien genera")
    # Mas filas que las que entran en una pagina -> tiene que paginar.
    _muchas = df.to_dict("records") * 20
    _multi = generar_reporte_historico(_muchas, JUN1, JUL31, "", t)
    r.check(len(_multi) > len(pdf),
            f"{len(_muchas)} filas ocupan mas de una pagina "
            f"({len(_multi):,} bytes vs {len(pdf):,})")
    r.check(generar_pdf_reporte("X", ["A", "B"], [["1", "2"]], JUN1, JUL31,
                                )[:4] == b"%PDF",
            "el maquetador generico funciona con anchos por defecto")
except ImportError:
    print("  (reportlab no instalado: se omite)")

r.salir()
