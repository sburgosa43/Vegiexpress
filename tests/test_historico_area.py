"""
Histórico por Área (Facturación Mensual → 📊 Histórico por Área).

Reporte de SOLO LECTURA. El área es el FILTRO y el cliente es la fila.

Lo que se pincha, en orden de importancia:
  - el ISR se calcula POR FACTURA SEMANAL, respetando exentos y el umbral de
    Q2,800. Calcularlo sobre el total del período inflaría el ISR de quien
    factura poco cada semana pero mucho en el mes;
  - venta, compra, IVA y ambos márgenes salen del precio y costo GUARDADOS;
  - los márgenes usan la misma definición que Control de Márgenes;
  - los % viven en los totales, no por fila;
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
def _ped(row, cli, prod, f, precio, costo, cant, sem):
    return {"row_num": row, "cliente": cli, "producto": prod, "fecha": f,
            "precio": precio, "costo": costo, "cantidad": cant,
            "total": round(precio * cant, 2), "semana": sem, "año": 2026,
            "proveedor": "Don Chus", "status": "Pendiente"}


PEDIDOS = [
    # Cazador Italiano (Antigua, NO exento): dos semanas de Q2,000. En el mes
    # suma Q4,000, pero ninguna FACTURA llega al umbral -> ISR 0.
    _ped(10, "Cazador Italiano", "Lechuga", date(2026, 6, 3),  100.0, 60.0, 20, 23),
    _ped(11, "Cazador Italiano", "Tomate",  date(2026, 6, 10), 100.0, 60.0, 20, 24),
    # Doña Luz (Río, NO exenta): una sola factura de Q4,000 -> sí retiene.
    _ped(12, "Doña Luz", "Lechuga", date(2026, 6, 4), 200.0, 120.0, 20, 23),
    # Sundog (Río) está en ISR_EXENTOS: factura Q5,000 y aun así no retiene.
    _ped(13, "Sundog",   "Lechuga", date(2026, 6, 5), 200.0, 120.0, 25, 23),
    # Julio: fuera del rango que se consulta.
    _ped(14, "Cazador Italiano", "Lechuga", date(2026, 7, 8), 100.0, 60.0, 10, 28),
    # Línea sin producto: basura de la hoja.
    _ped(15, "Cazador Italiano", "  ", date(2026, 6, 4), 100.0, 60.0, 7, 23),
    # Cliente sin codigo_lugar conocido -> "Sin área". Margen del 10%, distinto
    # del 40% de los demás: si todas las filas tuvieran el mismo margen, el
    # check de "el % del total no es el promedio de las filas" no probaría nada.
    _ped(16, "Desconocido", "Lechuga", date(2026, 6, 5), 50.0, 45.0, 2, 23),
]

CLIENTES = [
    {"nombre": "Cazador Italiano", "codigo_lugar": "L03", "grupo": ""},
    {"nombre": "Doña Luz",         "codigo_lugar": "L01", "grupo": ""},
    {"nombre": "Sundog",           "codigo_lugar": "L01", "grupo": ""},
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

from config import (ZONAS_MAP, margen_neto_q, iva_incluido,    # noqa: E402
                    calcular_liquido, ISR_UMBRAL)

_cod_area = {c: n for n, cods in ZONAS_MAP.items() for c in cods}
MAPA = {c["nombre"].lower(): {"area": _cod_area.get(c["codigo_lugar"],
                                                    "Sin área"),
                              "grupo": "Sin grupo"}
        for c in CLIENTES}

# Sin tratamiento_cliente a propósito: calcular_liquido cae al fallback de las
# listas de config, que es determinista y no necesita el Sheet.
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
                                _rango_historico, _periodo_de, COLS_HIST)

AREA_ANT = next(n for n, c in ZONAS_MAP.items() if "L03" in c)
AREA_RIO = next(n for n, c in ZONAS_MAP.items() if "L01" in c)
JUN1, JUN30 = date(2026, 6, 1), date(2026, 6, 30)
JUL31 = date(2026, 7, 31)

r = Reporte()


def _fila(df, cliente, periodo="2026-06"):
    sub = df[(df["Cliente"] == cliente) & (df["Período"] == periodo)]
    return sub.iloc[0]


print("=== 1. La fila es el CLIENTE, el área quedó como filtro ===")
df = agregar_historico(PEDIDOS, MAPA, JUN1, JUN30, (), "Mes")
r.check(list(df.columns) == COLS_HIST, f"columnas: {list(df.columns)}")
r.check("Área" not in df.columns, "el área ya no es columna")
r.check("Líneas" not in df.columns, "la columna Líneas se quitó")
r.check(not any("%" in c for c in df.columns),
        "no hay columnas de % en la tabla")
r.check(sorted(df["Cliente"]) == ["Cazador Italiano", "Desconocido",
                                  "Doña Luz", "Sundog"],
        f"un renglón por cliente: {sorted(df['Cliente'])}")
r.check(df["Cliente"].iloc[0] == "Sundog",
        "dentro del período, el que más vendió va primero")

print("\n=== 2. ISR: por factura SEMANAL, no sobre el total del período ===")
caz = _fila(df, "Cazador Italiano")
r.check(caz["Venta (Q)"] == 4000.0, f"venta del mes: {caz['Venta (Q)']}")
r.check(caz["ISR (Q)"] == 0.0,
        f"ISR 0: sus dos facturas fueron de Q2,000, bajo el umbral "
        f"(dio {caz['ISR (Q)']})")
# Contraprueba: si se calculara sobre el total del mes, SÍ retendría. Sin esto
# el check de arriba pasaría también con una implementación que ignore el ISR.
_isr_si_fuera_mensual = calcular_liquido("Cazador Italiano", 4000.0)[1]
r.check(_isr_si_fuera_mensual > 0,
        f"y no es que nunca retenga: sobre Q4,000 de una vez serían "
        f"Q{_isr_si_fuera_mensual:,.2f}")
luz = _fila(df, "Doña Luz")
r.check(luz["ISR (Q)"] == round(4000.0 / 1.12 * 0.05, 2),
        f"Doña Luz factura Q4,000 en UNA semana: retiene Q{luz['ISR (Q)']}")
sun = _fila(df, "Sundog")
r.check(sun["Venta (Q)"] == 5000.0 and sun["ISR (Q)"] == 0.0,
        f"Sundog está exento: Q5,000 vendidos y Q{sun['ISR (Q)']} de ISR")
r.check(ISR_UMBRAL == 2800.0, f"umbral vigente: Q{ISR_UMBRAL:,.0f}")

print("\n=== 3. Venta, compra, IVA y márgenes ===")
r.check(caz["Compra (Q)"] == 2400.0, f"compra 60x20 x2 = {caz['Compra (Q)']}")
r.check(abs(caz["IVA (Q)"] - round(iva_incluido(4000.0), 2)) < 0.01,
        f"IVA contenido en la venta: {caz['IVA (Q)']}")
r.check(caz["Margen Bruto (Q)"] == 1600.0,
        f"bruto = venta - compra = {caz['Margen Bruto (Q)']}")
_neto = round(margen_neto_q(60.0, 100.0) * 20 * 2, 2)
r.check(abs(caz["Margen Neto (Q)"] - _neto) < 0.01,
        f"neto con la misma fórmula que Control de Márgenes: "
        f"{caz['Margen Neto (Q)']}")
r.check(caz["Margen Neto (Q)"] < caz["Margen Bruto (Q)"],
        "el neto queda por debajo del bruto (IVA + ISR)")

print("\n=== 4. El área filtra; el cliente desconocido no se pierde ===")
d_ant = agregar_historico(PEDIDOS, MAPA, JUN1, JUN30, (AREA_ANT,), "Mes")
r.check(sorted(d_ant["Cliente"]) == ["Cazador Italiano"],
        f"filtrar Antigua deja solo su cliente: {sorted(d_ant['Cliente'])}")
d_rio = agregar_historico(PEDIDOS, MAPA, JUN1, JUN30, (AREA_RIO,), "Mes")
r.check(sorted(d_rio["Cliente"]) == ["Doña Luz", "Sundog"],
        f"filtrar Río deja los dos: {sorted(d_rio['Cliente'])}")
r.check(agregar_historico(PEDIDOS, MAPA, JUN1, JUN30,
                          (AREA_ANT, AREA_RIO), "Mes").shape[0] == 3,
        "dos áreas suman sus clientes")
r.check(float(_fila(df, "Desconocido")["Venta (Q)"]) == 100.0,
        "el cliente sin área aparece igual, no se descarta")
d_sin = agregar_historico(PEDIDOS, MAPA, JUN1, JUN30, ("Sin área",), "Mes")
r.check(sorted(d_sin["Cliente"]) == ["Desconocido"],
        "y se puede filtrar por 'Sin área' para encontrarlo")

print("\n=== 5. Granularidades ===")
d_sem = agregar_historico(PEDIDOS, MAPA, JUN1, JUN30, (), "Semana")
_caz_sem = d_sem[d_sem["Cliente"] == "Cazador Italiano"]
r.check(_caz_sem.shape[0] == 2,
        f"por semana, Cazador abre en 2 filas ({_caz_sem.shape[0]})")
r.check(set(_caz_sem["ISR (Q)"]) == {0.0},
        "y ninguna de las dos retiene ISR")
r.check(sorted(set(d_sem["Período"])) == ["2026-S23", "2026-S24"],
        f"etiquetas de semana: {sorted(set(d_sem['Período']))}")
d_tot = agregar_historico(PEDIDOS, MAPA, JUN1, JUN30, (),
                          "Sin período (todo el rango)")
r.check(set(d_tot["Período"]) == {"Todo el rango"},
        "'Sin período' colapsa todo en una etiqueta")
for col in ("Venta (Q)", "Compra (Q)", "Margen Neto (Q)"):
    r.check(abs(float(d_tot[col].sum()) - float(df[col].sum())) < 0.01,
            f"cambiar la granularidad no cambia el total de {col}")

print("\n=== 6. Rango de fechas ===")
d_jul = agregar_historico(PEDIDOS, MAPA, JUN1, JUL31, (), "Mes")
r.check(sorted(set(d_jul["Período"])) == ["2026-06", "2026-07"],
        f"julio entra al ampliar el rango: {sorted(set(d_jul['Período']))}")
r.check(d_jul["Período"].iloc[0] == "2026-07", "lo más reciente va arriba")
r.check(float(_fila(d_jul, "Cazador Italiano", "2026-07")["Venta (Q)"]) == 1000.0,
        "julio no se mezcla con junio")

print("\n=== 7. Totales: los % salen de los totales, no de promediar filas ===")
t = totales_historico(df)
# Venta y compra esperadas se derivan del fixture, no se copian a mano: una
# suma mal hecha en el test es tan mala como un bug en el código.
_EN_JUNIO = [p for p in PEDIDOS
             if JUN1 <= p["fecha"] <= JUN30 and p["producto"].strip()]
_VENTA = round(sum(p["total"] for p in _EN_JUNIO), 2)
_COMPRA = round(sum(p["costo"] * p["cantidad"] for p in _EN_JUNIO), 2)
r.check(abs(t["venta"] - _VENTA) < 0.01, f"venta total: {t['venta']}")
r.check(abs(t["compra"] - _COMPRA) < 0.01, f"compra total: {t['compra']}")
r.check(abs(t["bruto"] - (_VENTA - _COMPRA)) < 0.01,
        f"bruto total: {t['bruto']}")
r.check(abs(t["isr"] - luz["ISR (Q)"]) < 0.01,
        f"el ISR total es solo el de Doña Luz: {t['isr']}")
r.check(abs(t["bruto_pct"] - round((_VENTA - _COMPRA) / _VENTA * 100, 1)) < 0.05,
        f"bruto % = {_VENTA - _COMPRA:,.0f}/{_VENTA:,.0f} = {t['bruto_pct']}%")
r.check(abs(t["neto_pct"] - round(t["neto"] / t["venta"] * 100, 1)) < 0.05,
        f"neto % sobre la venta = {t['neto_pct']}%")
_prom = sum((row["Margen Bruto (Q)"] / row["Venta (Q)"] * 100)
            for _, row in df.iterrows()) / len(df)
r.check(abs(_prom - t["bruto_pct"]) > 0.5,
        f"y NO es el promedio por fila ({_prom:.1f}%)")

print("\n=== 8. Casos borde ===")
r.check(agregar_historico(PEDIDOS, MAPA, date(2025, 1, 1), date(2025, 1, 31),
                          (), "Mes").empty,
        "rango sin pedidos devuelve vacío")
r.check(agregar_historico(PEDIDOS, MAPA, JUN30, JUN1, (), "Mes").empty,
        "rango invertido no devuelve nada")
r.check(agregar_historico(PEDIDOS, MAPA, JUN1, JUN30, ("No Existe",),
                          "Mes").empty,
        "un área sin coincidencias devuelve vacío, no todo")
_vacio = totales_historico(agregar_historico(PEDIDOS, MAPA, JUN30, JUN1,
                                             (), "Mes"))
r.check(_vacio["venta"] == 0.0 and _vacio["bruto_pct"] == 0.0,
        "totales de un DataFrame vacío no explota")
_regalado = [_ped(90, "Doña Luz", "Muestra", date(2026, 6, 9), 0.0, 4.0, 1, 24)]
_d0 = agregar_historico(_regalado, MAPA, JUN1, JUN30, (), "Mes")
r.check(_d0["Margen Bruto (Q)"].iloc[0] == -4.0,
        "producto regalado: costó y no se cobró, el bruto queda negativo")
r.check(totales_historico(_d0)["bruto_pct"] == 0.0,
        "y con venta 0 el % no divide por cero")

print("\n=== 9. Atajos de rango ===")
HOY = date(2026, 8, 1)
r.check(_rango_historico("Este año", HOY, PEDIDOS)[0] == date(2026, 1, 1),
        "'Este año' arranca el 1 de enero")
r.check(_rango_historico("Todo", HOY, PEDIDOS)[0] == date(2026, 6, 3),
        "'Todo' arranca en el pedido más viejo de la hoja, no en fecha fija")
r.check(_rango_historico("Todo", HOY, [])[0] == HOY,
        "sin pedidos, 'Todo' no explota")
r.check(_periodo_de(PEDIDOS[0], "Mes") == "2026-06", "etiqueta de mes")

print("\n=== 10. El reporte NO escribe ===")
r.check(ESCRITO == [], "ningún update_cells: es solo lectura")

print("\n=== 11. Exportación e impresión ===")
# El PDF sale de las MISMAS filas que muestra la pantalla: si maquetara a
# partir de otra cosa, papel y pantalla podrían discrepar sin que se note.
sys.modules.pop("pdf_helper", None)
try:
    from pdf_helper import generar_reporte_historico, generar_pdf_reporte
    pdf = generar_reporte_historico(df.to_dict("records"), JUN1, JUN30,
                                    f"Área: {AREA_ANT} · Ver por: Mes", t)
    r.check(pdf[:4] == b"%PDF" and len(pdf) > 1200,
            f"PDF válido de {len(pdf):,} bytes")
    r.check(generar_reporte_historico([], JUN1, JUN30, "", {})[:4] == b"%PDF",
            "un reporte sin filas tampoco explota")
    r.check(generar_reporte_historico(df.to_dict("records"), JUN1, JUN30,
                                      "", None)[:4] == b"%PDF",
            "sin totales también genera")
    _multi = generar_reporte_historico(df.to_dict("records") * 20, JUN1,
                                       JUN30, "", t)
    r.check(len(_multi) > len(pdf),
            f"80 filas ocupan más de una página ({len(_multi):,} bytes)")
    r.check(generar_pdf_reporte("X", ["A", "B"], [["1", "2"]],
                                JUN1, JUN30)[:4] == b"%PDF",
            "el maquetador genérico funciona con anchos por defecto")
except ImportError:
    print("  (reportlab no instalado: se omite)")

r.salir()
