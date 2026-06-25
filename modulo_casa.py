"""
modulo_casa.py — Resumen financiero personal: operacion vs gastos casa.
Registro en modulo_gastos. Aqui solo analisis.
"""
import streamlit as st
import pandas as pd
from datetime import date
import calendar
from utils import _sf


MESES_ES = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
            "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]


def _get_data(sem_or_mes: int, año: int, modo: str):
    """
    Calcula resultado operacional, gastos casa y financiero
    para semana o mes dado.
    """
    from modulo_gastos import (
        _leer_gastos, _cargar_config, _filtro_gastos_semana,
        _finanzas_detallado, _GASTOS_VEGGI_MAP,
        _VEGGI_RIO_PCT, _VEGGI_ANT_PCT, _VEGGI_CHIM_PCT, _VEGGI_HOG_PCT,
    )
    from excel_helper import leer_pedidos
    from data_helper  import cargar_clientes as _cc

    cfg        = _cargar_config()
    campo_clis = cfg["campo_clis"]
    gastos_all = _leer_gastos()
    pedidos    = leer_pedidos()

    # ── Zona map ──────────────────────────────────────────────────────────────
    _clis    = _cc()
    cli_zona = {}
    for c in _clis:
        for z, cods in _GASTOS_VEGGI_MAP.items():
            if c.get("codigo_lugar","") in cods:
                cli_zona[c["nombre"].lower().strip()] = z
                break

    # ── Filtros segun modo ────────────────────────────────────────────────────
    if modo == "Semana":
        filtro_ped = lambda p: p["semana"] == sem_or_mes and p["año"] == año
        gas_op     = _filtro_gastos_semana(gastos_all, sem_or_mes, año)
        gas_casa   = [g for g in gas_op if g["categoria"] == "Casa"]
        gas_fin    = [g for g in gas_op if g["categoria"] == "Financiero"]
        gas_op_neg = [g for g in gas_op if g["categoria"] not in ("Casa","Financiero","Compras")]
    else:
        mes = sem_or_mes
        filtro_ped = lambda p: (p["fecha"] and
                                p["fecha"].month == mes and
                                p["fecha"].year  == año)
        gas_mes = [g for g in gastos_all
                   if g["fecha"] and g["fecha"].month == mes and g["fecha"].year == año]
        gas_casa   = [g for g in gas_mes if g["categoria"] == "Casa"]
        gas_fin    = [g for g in gas_mes if g["categoria"] == "Financiero"]
        gas_op_neg = [g for g in gas_mes if g["categoria"] not in ("Casa","Financiero","Compras")]

    # ── Operacion ─────────────────────────────────────────────────────────────
    fin    = _finanzas_detallado(pedidos, campo_clis, filtro_ped, cli_zona)
    inc    = fin["inc"];  costo_p = fin["costo"]
    def _t(d): return sum(d.values())

    def _gas_cat(lst, cat):
        d = {}
        for g in lst:
            if g["categoria"] == cat:
                d[g["subcat"]] = d.get(g["subcat"], 0) + g["monto"]
        return sum(d.values())

    gas_campo_t = _gas_cat(gas_op_neg, "Campo")
    gas_veggi_t = _gas_cat(gas_op_neg, "Veggi")
    gas_vrio_t  = round(gas_veggi_t * _VEGGI_RIO_PCT,  2)
    gas_vant_t  = round(gas_veggi_t * _VEGGI_ANT_PCT,  2)
    gas_vchim_t = round(gas_veggi_t * _VEGGI_CHIM_PCT, 2)
    gas_vhog_t  = round(gas_veggi_t * _VEGGI_HOG_PCT,  2)

    campo_mn  = _t(inc["Campo"]) - gas_campo_t
    vrio_mn   = _t(inc["Veggi"]["Rio"])          - _t(costo_p["Veggi"]["Rio"])          - gas_vrio_t
    vant_mn   = _t(inc["Veggi"]["Antigua"])      - _t(costo_p["Veggi"]["Antigua"])      - gas_vant_t
    vchim_mn  = _t(inc["Veggi"]["Chimaltenango"])- _t(costo_p["Veggi"]["Chimaltenango"])- gas_vchim_t
    vh_mn     = _t(inc["Interno"])               - _t(costo_p["Interno"])               - gas_vhog_t
    total_op  = campo_mn + vrio_mn + vant_mn + vchim_mn + vh_mn

    op_detail = {
        "Campo":               campo_mn,
        "Veggi Rio":           vrio_mn,
        "Veggi Antigua":       vant_mn,
        "Veggi Chimaltenango": vchim_mn,
        "Veggi Hogares":       vh_mn,
    }

    # ── Casa ──────────────────────────────────────────────────────────────────
    casa_d = {}
    for g in gas_casa:
        casa_d[g["subcat"]] = casa_d.get(g["subcat"], 0) + g["monto"]
    total_casa = sum(casa_d.values())

    # ── Financiero ────────────────────────────────────────────────────────────
    fin_d = {}
    for g in gas_fin:
        fin_d[g["subcat"]] = fin_d.get(g["subcat"], 0) + g["monto"]
    total_fin = sum(fin_d.values())

    return {
        "op_detail":  op_detail,
        "total_op":   total_op,
        "casa_d":     casa_d,
        "total_casa": total_casa,
        "fin_d":      fin_d,
        "total_fin":  total_fin,
        "disponible": total_op - total_casa - total_fin,
        "budgets":    cfg["budgets"],
    }


def mostrar():
    st.markdown("## 🏡 Casa / Personal")
    if st.button("Inicio", key="btn_home_casa", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    hoy = date.today()

    # ── Selector de modo y periodo ────────────────────────────────────────────
    modo = st.radio("Vista", ["Semana","Mes"], horizontal=True, key="casa_modo")

    if modo == "Semana":
        c1, c2 = st.columns(2)
        periodo = c1.number_input("Semana", 1, 53,
                                   hoy.isocalendar()[1], key="casa_sem")
        año     = c2.number_input("Año", 2020, 2030, hoy.year, key="casa_año_s")
        titulo  = f"Semana {periodo} / {año}"
    else:
        c1, c2 = st.columns(2)
        periodo = c1.selectbox("Mes", list(range(1,13)),
                                index=hoy.month-1,
                                format_func=lambda m: MESES_ES[m-1],
                                key="casa_mes")
        año     = c2.number_input("Año", 2020, 2030, hoy.year, key="casa_año_m")
        titulo  = f"{MESES_ES[periodo-1]} {año}"

    with st.spinner("Calculando..."):
        data = _get_data(periodo, año, modo)

    st.markdown(f"### {titulo}")

    # ── Top KPIs ──────────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Resultado Op.",    f"Q{data['total_op']:,.0f}")
    k2.metric("Gastos Casa",      f"Q{data['total_casa']:,.0f}")
    k3.metric("Compromisos Fin.", f"Q{data['total_fin']:,.0f}")
    disp = data["disponible"]
    k4.metric("Disponible",       f"Q{disp:,.0f}",
              delta="✅" if disp >= 0 else "⚠️ Deficit",
              delta_color="normal" if disp >= 0 else "inverse")
    st.divider()

    # ── Resultado Operacion ───────────────────────────────────────────────────
    with st.expander("Resultado Operación", expanded=True):
        rows_op = [{"Area": k, "Margen Neto": f"Q{v:,.0f}"}
                   for k, v in data["op_detail"].items()]
        rows_op.append({"Area": "── TOTAL", "Margen Neto": f"Q{data['total_op']:,.0f}"})
        st.dataframe(pd.DataFrame(rows_op), hide_index=True, use_container_width=True)

    # ── Gastos Casa ───────────────────────────────────────────────────────────
    with st.expander("Gastos Personales (Casa)", expanded=True):
        if data["casa_d"]:
            budgets = data["budgets"]
            rows_casa = []
            for sub, monto in sorted(data["casa_d"].items(), key=lambda x: -x[1]):
                bud = budgets.get(sub, 0)
                rows_casa.append({
                    "Categoria":    sub,
                    "Gastado":      f"Q{monto:,.0f}",
                    "Presupuesto":  f"Q{bud:,.0f}" if bud else "—",
                    "Diferencia":   f"Q{bud-monto:,.0f}" if bud else "—",
                })
            rows_casa.append({
                "Categoria":   "── TOTAL",
                "Gastado":     f"Q{data['total_casa']:,.0f}",
                "Presupuesto": f"Q{sum(budgets.values()):,.0f}" if budgets else "—",
                "Diferencia":  f"Q{sum(budgets.values())-data['total_casa']:,.0f}" if budgets else "—",
            })
            st.dataframe(pd.DataFrame(rows_casa), hide_index=True, use_container_width=True)
        else:
            st.info("Sin gastos Casa registrados en este periodo.")

    # ── Compromisos Financieros ───────────────────────────────────────────────
    with st.expander("Compromisos Financieros", expanded=True):
        if data["fin_d"]:
            rows_fin = [{"Concepto": k, "Monto": f"Q{v:,.0f}"}
                        for k, v in sorted(data["fin_d"].items(), key=lambda x: -x[1])]
            rows_fin.append({"Concepto": "── TOTAL", "Monto": f"Q{data['total_fin']:,.0f}"})
            st.dataframe(pd.DataFrame(rows_fin), hide_index=True, use_container_width=True)
        else:
            st.info("Sin compromisos financieros en este periodo.")

    # ── Resumen final ─────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Resumen")
    res_rows = [
        {"Concepto": "Resultado Operacional",    "Monto": f"Q{data['total_op']:,.0f}"},
        {"Concepto": "(-) Gastos Casa",          "Monto": f"Q{data['total_casa']:,.0f}"},
        {"Concepto": "(-) Compromisos Financ.",  "Monto": f"Q{data['total_fin']:,.0f}"},
        {"Concepto": "━━ Disponible",            "Monto": f"Q{data['disponible']:,.0f}"},
    ]
    st.dataframe(pd.DataFrame(res_rows), hide_index=True, use_container_width=True)
    if data["disponible"] < 0:
        st.error(f"⚠️ Déficit de Q{abs(data['disponible']):,.0f} — los gastos superan el resultado operacional.")
