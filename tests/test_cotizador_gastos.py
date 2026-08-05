"""
Cotizador → Calcular Precio: gastos operativos del pedido.

Los tres gastos (mano de obra, empaque, transporte) son TOTALES del pedido.
Se suman y se reparten entre la cantidad para obtener el gasto por unidad:

    costo unitario real = costo del producto + gasto operativo por unidad

Ese costo real es el que entra a las DOS direcciones de la pestaña (margen →
precio y precio → margen), así que el margen neto después de ISR e IVA refleja
la ganancia verdadera del pedido.

Lo que se protege acá, en orden de importancia:
  - con gastos en cero el resultado es IDÉNTICO campo por campo al de antes,
    porque los gastos son opcionales y no deben romper el uso actual;
  - las dos direcciones usan el costo real, no solo el costo del producto;
  - cantidad en 0 con gastos cargados no divide por cero y queda marcado como
    ignorado, para que la pantalla avise en vez de descartarlos en silencio;
  - las fórmulas siguen siendo las de config: nada se recalcula a mano.

    python tests/test_cotizador_gastos.py
"""
import sys

from _stubs import Reporte, instalar_streamlit, raiz_repo

raiz_repo()
instalar_streamlit()

from modulo_cotizador import (_gasto_operativo, _desglose,      # noqa: E402
                              _desde_margen_pct, _desde_margen_q)
from config import (IVA_FACTOR, ISR_FACTOR, margen_neto_q,      # noqa: E402
                    punto_equilibrio)

COSTO = 5.0
CANT, MO, EMP, TRA = 100.0, 50.0, 25.0, 50.0     # total 125 -> 1.25 por unidad
REAL = 6.25

r = Reporte()

print("=== 1. Gasto por unidad: total del pedido entre la cantidad ===")
g = _gasto_operativo(CANT, MO, EMP, TRA)
r.check(g["total"] == 125.0, f"suma de los tres: {g['total']}")
r.check(g["por_unidad"] == 1.25, f"125 / 100 = {g['por_unidad']}")
r.check(g["ignorado"] is False, "con cantidad válida no se ignora nada")
r.check(COSTO + g["por_unidad"] == REAL,
        f"costo real = {COSTO} + {g['por_unidad']} = {REAL}")

print("\n=== 2. Cantidad 0 o gastos 0: se comporta como antes ===")
g0 = _gasto_operativo(0, 0, 0, 0)
r.check(g0["por_unidad"] == 0.0, "sin nada, el gasto por unidad es 0")
r.check(g0["ignorado"] is False, "y no hay nada que avisar")
gi = _gasto_operativo(0, MO, EMP, TRA)
r.check(gi["por_unidad"] == 0.0, "cantidad 0 NO divide por cero")
r.check(gi["ignorado"] is True,
        "pero queda marcado: hay Q125 cargados que no se están aplicando")
gsc = _gasto_operativo(CANT, 0, 0, 0)
r.check(gsc["por_unidad"] == 0.0 and gsc["ignorado"] is False,
        "cantidad sin gastos tampoco aporta nada")
r.check(_gasto_operativo(CANT, -50, 0, 0)["total"] == 0.0,
        "un gasto negativo no resta: se trata como 0")

print("\n=== 3. Con gastos en cero el resultado es IDÉNTICO al de antes ===")
# Es la garantía de que esto no rompe el uso actual de la pestaña.
for etiqueta, antes, ahora in (
        ("margen %", _desde_margen_pct(COSTO, 0.30),
                     _desde_margen_pct(COSTO, 0.30, None)),
        ("margen Q", _desde_margen_q(COSTO, 2.0),
                     _desde_margen_q(COSTO, 2.0, None)),
        ("desglose", _desglose(COSTO, 8.0), _desglose(COSTO, 8.0, None))):
    r.check(antes == ahora, f"{etiqueta}: mismo dict campo por campo")
# Y pasar un dict de gastos vacíos tampoco mueve ningún número.
_d_g0 = _desglose(COSTO, 8.0, g0)
_d_sin = _desglose(COSTO, 8.0)
r.check(all(abs(_d_g0[k] - _d_sin[k]) < 1e-9 for k in _d_sin
            if isinstance(_d_sin[k], (int, float))),
        "un dict de gastos en 0 no altera ningún número")

print("\n=== 4. Dirección 1: margen → precio, con el costo real ===")
p_sin = _desde_margen_pct(COSTO, 0.30)["precio"]
d_con = _desde_margen_pct(REAL, 0.30, g)
r.check(d_con["precio"] > p_sin,
        f"el precio sugerido sube: {p_sin:.4f} -> {d_con['precio']:.4f}")
r.check(abs(d_con["margen_neto_pct"] - 30.0) < 0.01,
        f"y sigue dando el 30% pedido: {d_con['margen_neto_pct']}%")
d_q = _desde_margen_q(REAL, 2.0, g)
r.check(abs(d_q["margen_neto_q"] - 2.0) < 0.01,
        f"en modo Q también: {d_q['margen_neto_q']}")
r.check(d_q["precio"] > _desde_margen_q(COSTO, 2.0)["precio"],
        "y el precio necesario para ganar Q2 es mayor con gastos")

print("\n=== 5. Dirección 2: precio → margen, con el costo real ===")
PRECIO = 9.0
m_sin = _desglose(COSTO, PRECIO)["margen_neto_q"]
m_con = _desglose(REAL, PRECIO, g)["margen_neto_q"]
r.check(m_con < m_sin,
        f"a precio fijo, el margen baja: {m_sin:.4f} -> {m_con:.4f}")
_esperado = ISR_FACTOR * IVA_FACTOR * g["por_unidad"]
r.check(abs((m_sin - m_con) - _esperado) < 1e-6,
        f"la caída es exactamente ISR x IVA x gasto = {_esperado:.4f}")
r.check(abs(m_con - margen_neto_q(REAL, PRECIO)) < 1e-9,
        "y coincide con margen_neto_q de config sobre el costo real")

print("\n=== 6. Ida y vuelta ===")
for m_pct in (0.10, 0.30, 0.55):
    _d = _desde_margen_pct(REAL, m_pct, g)
    _vuelta = _desglose(REAL, _d["precio"], g)
    r.check(abs(_vuelta["margen_neto_pct"] - m_pct * 100) < 0.01,
            f"pedir {m_pct:.0%} y releer el precio devuelve "
            f"{_vuelta['margen_neto_pct']:.2f}%")

print("\n=== 7. El punto de equilibrio sube: es el mínimo REAL ===")
r.check(abs(d_con["pto_equilibrio"] - punto_equilibrio(REAL)) < 1e-9,
        f"pto. equilibrio = costo real x 1.12 = {d_con['pto_equilibrio']:.4f}")
r.check(d_con["pto_equilibrio"] > _desglose(COSTO, 8.0)["pto_equilibrio"],
        "y es mayor que el que daba solo con el costo del producto")
r.check(_desglose(REAL, punto_equilibrio(REAL) - 0.01, g)["rentable"] is False,
        "vender por debajo de ese punto ya no es rentable")

print("\n=== 8. El desglose muestra de dónde sale el costo real ===")
r.check(abs(d_con["costo_producto"] - COSTO) < 1e-4,
        f"costo del producto: {d_con['costo_producto']}")
r.check(abs(d_con["gasto_unitario"] - 1.25) < 1e-4,
        f"gasto por unidad: {d_con['gasto_unitario']}")
r.check(abs(d_con["costo_producto"] + d_con["gasto_unitario"]
            - d_con["costo"]) < 1e-4,
        "producto + gasto = costo real, que es el que usó el cálculo")
r.check(d_con["gastos"]["mano_obra"] == MO
        and d_con["gastos"]["empaque"] == EMP
        and d_con["gastos"]["transporte"] == TRA,
        "los tres rubros llegan abiertos a la pantalla")
r.check("gastos" not in _desglose(COSTO, 8.0),
        "sin gastos no se agregan claves: el dict queda como antes")

print("\n=== 8b. Total a ganar del pedido completo ===")
from modulo_cotizador import _totales_pedido, _mostrar_resultado  # noqa: E402
import inspect                                                    # noqa: E402

t = _totales_pedido(d_con, CANT)
r.check(abs(t["venta"] - round(d_con["precio"] * CANT, 2)) < 0.01,
        f"venta total = precio x cantidad = Q{t['venta']:,.2f}")
r.check(abs(t["ganancia"] - round(d_con["margen_neto_q"] * CANT, 2)) < 0.01,
        f"ganancia total = margen unitario x cantidad = Q{t['ganancia']:,.2f}")
r.check(t["cantidad"] == CANT, "arrastra la cantidad para poder mostrarla")

# Los gastos se cargan como TOTALES del pedido, así que su impacto en la
# ganancia total tiene que ser exactamente ISR x IVA x el total cargado --
# sin rastro de la división por unidad ni de errores de redondeo acumulados.
_sin = _totales_pedido(_desglose(COSTO, d_con["precio"]), CANT)
_esp_total = ISR_FACTOR * IVA_FACTOR * g["total"]
r.check(abs((_sin["ganancia"] - t["ganancia"]) - _esp_total) < 0.02,
        f"al mismo precio, los gastos cuestan ISR x IVA x Q{g['total']:,.0f} "
        f"= Q{_esp_total:,.2f} de ganancia total")

print("\n=== 8c. Sin cantidad NO se inventa un total ===")
r.check(_totales_pedido(d_con, 0) is None,
        "cantidad 0 devuelve None, no un total con cantidad 1")
r.check(_totales_pedido(d_con, -5) is None, "cantidad negativa tampoco")
r.check(_totales_pedido(d_con, None) is None, "campo vacío tampoco")
r.check(_totales_pedido(None, CANT) is None, "sin desglose no hay total")
r.check(inspect.signature(_mostrar_resultado).parameters["cantidad"].default
        == 0.0,
        "la cantidad es opcional en la tarjeta: Verificar Margen no cotiza "
        "cantidad y su tarjeta no debe cambiar")

print("\n=== 9. Las otras pestañas no cambian ===")
# _tab_verificar y _tab_escenarios llaman sin `gastos`; el parámetro es
# opcional justamente para no tocarlas.
r.check(_desglose(4.0, 7.5) == _desglose(4.0, 7.5, None),
        "Verificar Margen: mismo resultado")
r.check(_desde_margen_pct(4.0, 0.25) == _desde_margen_pct(4.0, 0.25, None),
        "Escenarios: mismo resultado")

print("\n=== 10. Casos borde ===")
r.check(_desglose(0, 8.0, g) is None, "costo 0 sigue devolviendo None")
r.check(_desglose(REAL, 0, g) is None, "precio 0 también")
r.check(_desde_margen_pct(REAL, 0.99, g) is None,
        "un margen imposible sigue devolviendo None")
r.check(_gasto_operativo(None, None, None, None)["por_unidad"] == 0.0,
        "campos vacíos no explotan")
_gd = _gasto_operativo(3, 10, 0, 0)
r.check(abs(_gd["por_unidad"] - 10 / 3) < 1e-9,
        f"división no exacta: {_gd['por_unidad']}")

r.salir()
