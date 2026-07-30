"""
"A Comprar" en Compras a Proveedores → A Pedir.

El bug: al filtrar por área, base_dfs_f es una COPIA temporal del DataFrame
(se rearma en cada rerun), así que las cantidades escritas ahí se perdían y el
PDF —que leía el DataFrame— decía "Ingresá cantidades primero" aunque
estuvieran ingresadas.

La corrección es un mapa en session_state indexado POR PRODUCTO, que sobrevive
al filtro y a los reruns, y del que leen tanto el PDF como el guardado.

    python tests/test_apedir_comprar.py
"""
import ast
import os
import sys
import types

from _stubs import Reporte, instalar_streamlit, raiz_repo

RAIZ = raiz_repo()
st = instalar_streamlit()

import pandas as pd                                          # noqa: E402

SEMANA, AÑO = 31, 2026
K = f"apedir_comprar_{SEMANA}_{AÑO}"

# Catálogo de costos
PROD_MAP = {"lechuga": {"costo": 5.0}, "tomate": {"costo": 3.0},
            "ajo": {"costo": 6.0}}

# DataFrame como lo arma A Pedir: demanda por área + Total + A Comprar
def _df_base():
    return pd.DataFrame([
        {"Producto": "Lechuga", "Unidad": "Lb", "Antigua": 10.0, "Río": 4.0,
         "Hogares": 0.0, "Total": 14.0, "A Comprar": "", "_costo": 5.0},
        {"Producto": "Tomate",  "Unidad": "Lb", "Antigua": 0.0,  "Río": 6.0,
         "Hogares": 2.0, "Total": 8.0,  "A Comprar": "", "_costo": 3.0},
        {"Producto": "Ajo",     "Unidad": "Red", "Antigua": 5.0, "Río": 0.0,
         "Hogares": 0.0, "Total": 5.0,  "A Comprar": "", "_costo": 6.0},
    ])


TODAS_AREAS = ["Antigua", "Río", "Hogares"]

# Cargar del módulo real solo lo que no depende de Streamlit
_src = open(os.path.join(RAIZ, "modulo_proveedores.py"), encoding="utf-8").read()
_mod = ast.parse(_src)
_ns = {"st": st, "pd": pd}
exec(compile(ast.Module(
    body=[n for n in _mod.body
          if isinstance(n, ast.FunctionDef)
          and n.name in {"_val_comprar", "_recolectar_compras"}],
    type_ignores=[]), "modulo_proveedores", "exec"), _ns)
_val_comprar = _ns["_val_comprar"]
_recolectar  = _ns["_recolectar_compras"]

r = Reporte()

print("=== 1. Interpretación de la celda 'A Comprar' ===")
for val, esp in [("10", (True, False, 10.0)), ("P", (True, True, 0.0)),
                 ("", (False, False, 0.0)), ("0", (False, False, 0.0)),
                 ("2,5", (True, False, 2.5)), ("basura", (False, False, 0.0))]:
    got = _val_comprar(val)
    r.check(got == esp, f"{val!r} -> {got}")

print("\n=== 2. La vista filtrada es una COPIA (raíz del bug) ===")
base = _df_base()
# Reproduce lo que hace A Pedir al filtrar a un área
areas_f = ["Antigua"]
copia = base.copy()
copia["Total"] = copia["Antigua"]
copia = copia[copia["Total"] > 0].reset_index(drop=True)
copia = copia[["Producto", "Unidad", "Antigua", "Total", "A Comprar", "_costo"]]
copia.loc[0, "A Comprar"] = "12"          # el usuario escribe en la vista
r.check(base.loc[0, "A Comprar"] == "",
        "escribir en la copia NO toca el DataFrame original")
r.check(copia.loc[0, "A Comprar"] == "12",
        "el valor solo existe en la copia, que se rearma en cada rerun")

print("\n=== 3. El mapa por producto sí sobrevive ===")
st.session_state.clear()
st.session_state[K] = {}
mapa = st.session_state[K]
# Lo que hace ahora el fragmento al editar
for prod, val in [("Lechuga", "12"), ("Ajo", "P")]:
    mapa[("CENMA", prod)] = val
r.check(mapa[("CENMA", "Lechuga")] == "12", "queda indexado por producto")
# Cambiar el filtro rearma el DataFrame, pero el mapa sigue
base2 = _df_base()
sembrado = [mapa.get(("CENMA", str(p)), "") for p in base2["Producto"]]
r.check(sembrado == ["12", "", "P"],
        f"al rearmar la tabla las cantidades se recuperan: {sembrado}")

print("\n=== 4. El PDF ve las cantidades con filtro aplicado ===")
# Misma lógica que el fragmento: filtra a Antigua y arma los items del PDF
areas_f = ["Antigua"]
dfa = _df_base()
dfa["Total"] = dfa["Antigua"]
dfa = dfa[dfa["Total"] > 0].reset_index(drop=True)

items_pdf = []
for _, row in dfa.iterrows():
    ok, pend, n = _val_comprar(mapa.get(("CENMA", str(row["Producto"])), ""))
    if ok:
        it = {"producto": row["Producto"], "unidad": row["Unidad"],
              "cantidad": float(row["Total"]),
              "a_comprar": "P" if pend else f"{n:g}"}
        for a in areas_f:
            it[a] = float(row[a] or 0)
        items_pdf.append(it)

r.check(len(items_pdf) == 2,
        f"{len(items_pdf)} líneas al PDF (Lechuga y Ajo tienen cantidad)")
r.check([i["producto"] for i in items_pdf] == ["Lechuga", "Ajo"],
        "Tomate queda fuera: no tiene demanda en Antigua")
r.check(items_pdf[0]["a_comprar"] == "12", "Lechuga lleva la cantidad escrita")
r.check(items_pdf[1]["a_comprar"] == "P", "Ajo lleva P (pendiente)")
r.check(set(items_pdf[0]) - {"producto", "unidad", "cantidad", "a_comprar"}
        == {"Antigua"},
        "solo la columna del área filtrada, no las tres siempre")
r.check(items_pdf, "con cantidades el PDF NO queda deshabilitado")

print("\n=== 5. Sin cantidades el PDF sí se deshabilita ===")
st.session_state[K] = {}
vacio = [row["Producto"] for _, row in dfa.iterrows()
         if _val_comprar(st.session_state[K].get(("CENMA", str(row["Producto"])),
                                                 ""))[0]]
r.check(vacio == [], "mapa vacío -> ninguna línea -> botón deshabilitado")

print("\n=== 6. El guardado lee del mismo mapa ===")
st.session_state[K] = {("CENMA", "Lechuga"): "12", ("CENMA", "Ajo"): "4"}
compras = _recolectar({"CENMA"}, {"CENMA": _df_base()}, PROD_MAP,
                      TODAS_AREAS, SEMANA, AÑO)
prods = sorted(c["producto"] for c in compras)
r.check(prods == ["Ajo", "Lechuga"], f"recolecta del mapa: {prods}")
_lech = next(c for c in compras if c["producto"] == "Lechuga")
r.check(abs(_lech["cantidad"] - 12.0) < 1e-9,
        f"cantidad desde el mapa: {_lech['cantidad']}")
r.check(abs(_lech["costo_unit"] - 5.0) < 1e-9, "costo del catálogo")
r.check(_lech["areas"] == {"Antigua": 10.0, "Río": 4.0},
        f"demanda por área para el reparto: {_lech['areas']}")

# "P" no es cantidad: no debe entrar al guardado
st.session_state[K] = {("CENMA", "Lechuga"): "P"}
r.check(_recolectar({"CENMA"}, {"CENMA": _df_base()}, PROD_MAP,
                    TODAS_AREAS, SEMANA, AÑO) == [],
        "una línea marcada 'P' no se guarda como compra")

print("\n=== 7. Sin semana/año cae a la columna (compatibilidad) ===")
df_con = _df_base()
df_con.loc[0, "A Comprar"] = "7"
compras = _recolectar({"CENMA"}, {"CENMA": df_con}, PROD_MAP, TODAS_AREAS)
r.check(len(compras) == 1 and abs(compras[0]["cantidad"] - 7.0) < 1e-9,
        "sin mapa usa el valor del DataFrame")

r.salir()
