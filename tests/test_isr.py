"""
ISR mensual a pagar (modulo_isr).

    Base        = Σ (total / 1.12) de los clientes que APLICAN
    ISR total   = 5% × min(Base, 30,000) + 7% × max(0, Base − 30,000)
    Ya retenido = 5% × Σ (total / 1.12) de los que APLICAN **y** RETIENEN
    A pagar     = ISR total − Ya retenido

Lo que se pincha, en orden de importancia:
  - un cliente que RETIENE pero NO aplica queda TOTALMENTE afuera: ni suma a
    la base ni se descuenta su retención (los dos campos no son simétricos);
  - el tramo de Q30,000 se evalúa sobre la base MENSUAL total;
  - un dato faltante o raro va a 'pendientes' y no se asume como "No";
  - un nombre que no está en el catálogo va a 'sin_match', no al cálculo;
  - el aporte prorrateado por cliente suma exactamente el ISR total.

    python tests/test_isr.py
"""
import sys
import types
from datetime import date

from _stubs import Reporte, instalar_streamlit, raiz_repo

raiz_repo()
instalar_streamlit()

ESCRITO = []
IVA = 1.12


def _tot(base_sin_iva_deseada: float) -> float:
    """Total CON IVA que produce la base sin IVA que se quiere probar."""
    return round(base_sin_iva_deseada * IVA, 2)


def _ped(row, cli, f, total):
    return {"row_num": row, "cliente": cli, "producto": "Lechuga", "fecha": f,
            "total": total, "cantidad": 1, "precio": total, "costo": 0.0,
            "semana": f.isocalendar()[1], "año": f.year, "status": "Pendiente"}


# Junio: base 25,000 -> por debajo del tramo.
# Julio: base 40,000 -> lo cruza.
# Agosto: base 30,000 -> justo en el borde.
PEDIDOS = [
    # ── Junio ───────────────────────────────────────────────────────────────
    _ped(10, "Alfa",  date(2026, 6, 3),  _tot(20000)),   # aplica + retiene
    _ped(11, "Beta",  date(2026, 6, 5),  _tot(5000)),    # aplica, no retiene
    _ped(12, "Gama",  date(2026, 6, 8),  _tot(9000)),    # RETIENE pero NO aplica
    _ped(13, "Delta", date(2026, 6, 9),  _tot(7000)),    # sin dato de aplica
    _ped(14, "Epsilon", date(2026, 6, 10), _tot(3000)),  # aplica, retiene sin dato
    _ped(15, "Wilson Mayoreo", date(2026, 6, 11), _tot(50000)),  # excluido
    _ped(16, "Fantasma", date(2026, 6, 12), _tot(4000)),         # sin match
    # ── Julio ───────────────────────────────────────────────────────────────
    _ped(20, "Alfa", date(2026, 7, 3), _tot(30000)),
    _ped(21, "Beta", date(2026, 7, 5), _tot(10000)),
    # ── Agosto: exactamente en el limite ────────────────────────────────────
    _ped(30, "Alfa", date(2026, 8, 3), _tot(30000)),
]

# leer_clientes_isr ahora lee de cargar_clientes (que ya llega hasta la R),
# asi que el doble es la lista de clientes y no filas crudas de la hoja.
CLIENTES = [
    {"nombre": "Alfa",           "aplica_isr": True,  "retiene_isr": True},
    {"nombre": "Beta",           "aplica_isr": True,  "retiene_isr": False},
    {"nombre": "Gama",           "aplica_isr": False, "retiene_isr": True},
    {"nombre": "Delta",          "aplica_isr": None,  "retiene_isr": True},
    {"nombre": "Epsilon",        "aplica_isr": True,  "retiene_isr": None},
    {"nombre": "Wilson Mayoreo", "aplica_isr": True,  "retiene_isr": False},
    {"nombre": "Zeta",           "aplica_isr": None,  "retiene_isr": True},
    {"nombre": "",               "aplica_isr": True,  "retiene_isr": True},
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

data_helper = types.ModuleType("data_helper")
data_helper.cargar_clientes = lambda: [dict(c) for c in CLIENTES]
sys.modules["data_helper"] = data_helper

import modulo_isr as M                                         # noqa: E402
from config import base_sin_iva                                # noqa: E402

r = Reporte()

print("=== 1. Lectura de los dos campos del cliente ===")
CLI = M.leer_clientes_isr()
r.check(CLI["alfa"] == {"nombre": "Alfa", "aplica": True, "retiene": True},
        f"Alfa: {CLI['alfa']}")
r.check(CLI["gama"]["aplica"] is False and CLI["gama"]["retiene"] is True,
        "Gama retiene pero no aplica")
r.check(CLI["delta"]["aplica"] is None,
        "celda vacía en Q -> None (pendiente), no False")
r.check(CLI["epsilon"]["retiene"] is None, "celda vacía en O -> None")
r.check(CLI["zeta"]["aplica"] is None,
        "un cliente sin el dato en Q queda en None")
r.check("" not in CLI, "una fila sin nombre se ignora")

print("\n=== 2. El sí/no tolerante: un valor raro NO es 'No' ===")
# _tri se fue de modulo_isr: ahora lo hace cargar_clientes con _tri_si_no, para
# que sea el MISMO criterio en toda la app. Se carga la función real por AST
# porque data_helper está doblado en esta prueba.
import ast as _ast                                            # noqa: E402
import os as _os                                              # noqa: E402

_dh_src = open(_os.path.join(raiz_repo(), "data_helper.py"), encoding="utf-8").read()
_ns = {}
exec(compile(_ast.Module(
    body=[n for n in _ast.parse(_dh_src).body
          if isinstance(n, _ast.FunctionDef) and n.name == "_tri_si_no"],
    type_ignores=[]), "data_helper", "exec"), _ns)
_tri_si_no = _ns["_tri_si_no"]

for v in ("Sí", "si", "SI", "s", "TRUE", "1", "x"):
    r.check(_tri_si_no(v) is True, f"{v!r} -> True")
for v in ("No", "no", "N", "FALSE", "0"):
    r.check(_tri_si_no(v) is False, f"{v!r} -> False")
for v in ("", "   ", None, "Pendiente", "?", "tal vez"):
    r.check(_tri_si_no(v) is None, f"{v!r} -> None (se muestra, no se asume)")

print("\n=== 3. JUNIO: el que retiene pero NO aplica queda afuera ===")
jun = M.calcular_isr(PEDIDOS, CLI, 6, 2026)
# Base = Alfa 20,000 + Beta 5,000 + Epsilon 3,000 = 28,000
# Gama (9,000) NO entra porque no aplica; Delta (7,000) tampoco: sin dato.
r.check(abs(jun["base"] - 28000) < 0.5, f"base = {jun['base']:,.2f} (28,000)")
r.check(abs(jun["isr_total"] - 0.05 * 28000) < 0.5,
        f"ISR total = 5% x 28,000 = {jun['isr_total']:,.2f}")
r.check(abs(jun["ya_retenido"] - 0.05 * 20000) < 0.5,
        f"ya retenido = solo Alfa = {jun['ya_retenido']:,.2f}")
r.check(abs(jun["a_pagar"] - (0.05 * 28000 - 0.05 * 20000)) < 0.5,
        f"a pagar = {jun['a_pagar']:,.2f}")

print("\n=== 4. Contraprueba del caso clave (Gama) ===")
# Sin esto, el check de arriba pasaria tambien con una implementacion que
# ignorara por completo el campo 'retiene'.
_gama = next(d for d in jun["detalle"] if d["Cliente"] == "Gama")
r.check(_gama["Aporte ISR (Q)"] == 0.0,
        "Gama no aporta a la base aunque facturó Q9,000")
r.check(_gama["Ya retenido (Q)"] == 0.0,
        "y su retención NO se descuenta, aunque el campo diga que retiene")
r.check(_gama["Retiene ISR"] == "Sí" and _gama["Aplica ISR"] == "No",
        "pero se muestra tal cual para poder auditarlo")
# OJO con la forma de esta contraprueba: comparar 'a pagar' NO sirve. Bajo el
# 5% plano, meter a la base un cliente que ademas retiene sube el ISR y la
# retencion en la misma cantidad y se cancelan -- daria el mismo numero por
# casualidad. Hay que atacar los dos errores por separado.

# (a) Si Gama entrara a la base, esta cruzaria el tramo de 30,000 (28,000 +
#     9,000 = 37,000) y el ISR total cambiaria de verdad.
_isr_con_gama = 0.05 * 30000 + 0.07 * (37000 - 30000)
r.check(abs(jun["isr_total"] - _isr_con_gama) > 1.0,
        f"si Gama entrara a la base, el ISR seria Q{_isr_con_gama:,.2f} "
        f"y no Q{jun['isr_total']:,.2f}")

# (b) El error inverso, que es el peligroso: descontar la retencion de alguien
#     que no aplica. Daria un 'a pagar' NEGATIVO, o sea plata que no existe.
_ret_mal = 0.05 * (20000 + 9000)
r.check(abs(jun["ya_retenido"] - _ret_mal) > 1.0,
        f"si se descontara la retención de Gama, 'ya retenido' seria "
        f"Q{_ret_mal:,.2f} en vez de Q{jun['ya_retenido']:,.2f}")
r.check(jun["a_pagar"] > 0,
        f"y 'a pagar' quedaria negativo (Q{jun['isr_total'] - _ret_mal:,.2f}), "
        f"que es plata inventada")

print("\n=== 5. Pendientes y sin match: nunca se asumen ===")
_pend = {d["Cliente"] for d in jun["pendientes"]}
r.check(_pend == {"Delta", "Epsilon"}, f"pendientes: {sorted(_pend)}")
r.check(all(d["Cliente"] != "Delta" or d["Aporte ISR (Q)"] == 0.0
            for d in jun["detalle"]),
        "Delta (sin dato de aplica) no aporta")
_eps = next(d for d in jun["detalle"] if d["Cliente"] == "Epsilon")
r.check(_eps["Aporte ISR (Q)"] > 0 and _eps["Ya retenido (Q)"] == 0.0,
        "Epsilon aplica, así que suma a la base; su 'retiene' sin dato "
        "cuenta como No y no descuenta")
_sm = {d["Cliente"] for d in jun["sin_match"]}
r.check(_sm == {"Fantasma"}, f"sin match: {sorted(_sm)}")
r.check(all(d["Cliente"] != "Fantasma" for d in jun["detalle"]),
        "el que no está en el catálogo no entra al detalle ni al cálculo")
r.check(all(d["Cliente"] != "Wilson Mayoreo" for d in jun["detalle"]),
        "el cliente interno (EXCLUIR_PROVEEDORES) se excluye")
r.check("Wilson Mayoreo" not in _sm, "y tampoco aparece como sin match")

print("\n=== 6. JULIO: el tramo de Q30,000 ===")
jul = M.calcular_isr(PEDIDOS, CLI, 7, 2026)
r.check(abs(jul["base"] - 40000) < 0.5, f"base = {jul['base']:,.2f}")
_esp = 0.05 * 30000 + 0.07 * 10000
r.check(abs(jul["isr_total"] - _esp) < 0.5,
        f"ISR = 5%x30,000 + 7%x10,000 = {jul['isr_total']:,.2f} ({_esp:,.2f})")
r.check(abs(jul["ya_retenido"] - 0.05 * 30000) < 0.5,
        f"ya retenido = {jul['ya_retenido']:,.2f}")
r.check(abs(jul["a_pagar"] - (_esp - 0.05 * 30000)) < 0.5,
        f"a pagar = {jul['a_pagar']:,.2f}")

print("\n=== 7. AGOSTO: justo en el límite, sin tramo alto ===")
ago = M.calcular_isr(PEDIDOS, CLI, 8, 2026)
r.check(abs(ago["base"] - 30000) < 0.5, f"base = {ago['base']:,.2f}")
r.check(abs(ago["isr_total"] - 0.05 * 30000) < 0.5,
        f"exactamente 30,000 va todo al 5%: {ago['isr_total']:,.2f}")
r.check(M.ISR_TRAMO_LIMITE == 30000.0 and M.ISR_TASA_BAJA == 0.05
        and M.ISR_TASA_ALTA == 0.07, "los parámetros fiscales son los pactados")

print("\n=== 8. El prorrateo suma exactamente el ISR total ===")
for etiq, res in (("junio", jun), ("julio", jul)):
    _suma = sum(d["Aporte ISR (Q)"] for d in res["detalle"])
    r.check(abs(_suma - res["isr_total"]) < 0.05,
            f"{etiq}: Σ aportes = {_suma:,.2f} vs ISR {res['isr_total']:,.2f}")
_alfa_jul = next(d for d in jul["detalle"] if d["Cliente"] == "Alfa")
r.check(abs(_alfa_jul["Aporte ISR (Q)"] - _esp * 30000 / 40000) < 0.5,
        f"Alfa aporta según su parte de la base: {_alfa_jul['Aporte ISR (Q)']:,.2f}")

print("\n=== 9. El IVA se saca con base_sin_iva de config ===")
r.check(abs(base_sin_iva(_tot(20000)) - 20000) < 0.5,
        "un total con IVA dividido 1.12 devuelve la base")
r.check(abs(jun["base"] - sum(base_sin_iva(p["total"]) for p in PEDIDOS
                              if p["fecha"].month == 6
                              and p["cliente"] in ("Alfa", "Beta", "Epsilon"))) < 0.5,
        "la base del mes es la suma de las bases sin IVA de los que aplican")

print("\n=== 10. Casos borde ===")
_vacio = M.calcular_isr(PEDIDOS, CLI, 1, 2026)
r.check(_vacio["base"] == 0.0 and _vacio["a_pagar"] == 0.0,
        "un mes sin pedidos da 0 y no divide por cero")
r.check(_vacio["detalle"] == [], "y no arma detalle")
r.check(M.calcular_isr([], CLI, 6, 2026)["base"] == 0.0,
        "sin pedidos tampoco explota")
_sin_cli = M.calcular_isr(PEDIDOS, {}, 6, 2026)
r.check(_sin_cli["base"] == 0.0,
        "sin catálogo de clientes no se asume que alguien aplica")
r.check(len(_sin_cli["sin_match"]) > 0,
        "todos caen a sin_match, que es visible")
_meses = M.meses_disponibles(PEDIDOS)
r.check(_meses[0] == (2026, 8), f"meses del más reciente al más viejo: {_meses}")

print("\n=== 11. El reporte NO escribe ===")
r.check(ESCRITO == [], "ningún update_cells: es solo lectura")

r.salir()
