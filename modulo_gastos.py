"""
modulo_gastos.py — Registro y analisis de gastos operativos.
Categorias: Campo | Veggi | Compras | Casa
"""
import streamlit as st
import pandas as pd
from datetime import date, datetime
from gsheets import get_all_rows, append_rows, update_cells, ws as _ws

_K_G  = "gastos"
_K_GC = "gastosconfig"

# ── Exclusiones financieras ───────────────────────────────────────────────────
_EXCLUIR_FINANCIERO = {"wilson"}
_INTERNOS           = {"veggi hogares"}

# ── Zonas Veggi (solo para Gastos, separa Antigua L03 de Chimal L04) ──────────
_GASTOS_VEGGI_MAP = {
    "Rio":           ["L01", "L02"],
    "Antigua":       ["L03"],
    "Chimaltenango": ["L04"],
}

# ── Prorrateo gastos operativos Veggi: 4/2/1/1 ───────────────────────────────
_VEGGI_RIO_PCT  = 4/8   # 50%
_VEGGI_ANT_PCT  = 2/8   # 25%
_VEGGI_CHIM_PCT = 1/8   # 12.5%
_VEGGI_HOG_PCT  = 1/8   # 12.5%

# ── Subcategorias que auto-defaultean a Frecuencia=Mensual ───────────────────
_MENSUAL_SUBCATS = {
    "Energia Campo","Energia Veggi","Agua Veggi","Agua Campo",
    "Alquiler","Comunicaciones","Colegios","Celulares","Seguros",
    "Energia Casa","Agua Casa",
}

# ── Subcategorias default por categoria ──────────────────────────────────────
SUBCATS_DEFAULT = {
    "Campo":   ["MO Campo","Agroquimicos","Fertilizantes","Semilla",
                "Transporte Campo","Alquiler Campo","Riego/Agua Campo",
                "Energia Campo","Herramientas/Equipo","Otros Campo"],
    "Veggi":   ["MO Veggi","Empaque","Transporte Veggi",
                "Energia Veggi","Agua Veggi","Comunicaciones",
                "Mantenimiento","Alquiler","Otros Veggi"],
    "Compras": ["Lechugas","Patzi","Carlos","Cenma","Otros Compras"],
    "Casa":    ["Colegios","Transporte Casa","Ocio",
                "Energia Casa","Agua Casa","Celulares",
                "Seguros","Otros Casa"],
    "Financiero": ["Prestamo Capital","Credito Capital",
                   "Credito Interes","Otros Financiero"],
}

CATS = ["Campo","Veggi","Compras","Casa","Financiero"]
CAMPO_CLIENTS_DEFAULT = ["aldyk","tierra fria","legume","4 pinos","cebollines"]
PROVEEDORES = ["CENMA","Patojas","El Huerto","Productor Directo",
               "Importado","Otro","Sin Proveedor"]


# ── Helpers numericos ─────────────────────────────────────────────────────────
def _sf(v):
    try:    return float(str(v).replace(",","").strip() or 0)
    except: return 0.0

def _si(v):
    try:    return int(float(str(v).replace(",","").strip() or 0))
    except: return 0


# ── Config I/O ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def _cargar_config() -> dict:
    rows       = get_all_rows(_K_GC)
    subcats    = {c: [] for c in CATS}
    campo_clis = []
    budgets    = {}

    for row in rows:
        while len(row) < 4: row.append("")
        tipo = str(row[0]).strip().upper()
        if tipo == "SUBCAT":
            cat = str(row[1]).strip()
            val = str(row[2]).strip()
            if cat in subcats and val:
                subcats[cat].append(val)
        elif tipo == "CAMPO":
            v = str(row[1]).strip().lower()
            if v: campo_clis.append(v)
        elif tipo == "BUDGET":
            budgets[str(row[1]).strip()] = _sf(row[2])

    for cat, defaults in SUBCATS_DEFAULT.items():
        if not subcats[cat]:
            subcats[cat] = defaults[:]

    if not campo_clis:
        campo_clis = CAMPO_CLIENTS_DEFAULT[:]

    return {"subcats": subcats, "campo_clis": campo_clis, "budgets": budgets}


def _guardar_config(subcats: dict, campo_clis: list, budgets: dict):
    sheet = _ws(_K_GC)
    sheet.clear()
    rows = []
    for cat, subs in subcats.items():
        for s in subs:
            rows.append([f"SUBCAT", cat, s, ""])
    for cli in campo_clis:
        rows.append(["CAMPO", cli, "", ""])
    for k, v in budgets.items():
        rows.append(["BUDGET", k, v, ""])
    if rows:
        sheet.append_rows(rows, value_input_option="USER_ENTERED")
    _cargar_config.clear()


# ── Gastos I/O ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _leer_gastos() -> list:
    gastos = []
    try:
        rows = get_all_rows(_K_G)
        for i, row in enumerate(rows, start=2):
            while len(row) < 10: row.append("")
            fecha = None
            try: fecha = datetime.strptime(str(row[0]).strip(), "%d/%m/%Y").date()
            except: pass
            gastos.append({
                "row_num":    i,
                "fecha":      fecha,
                "semana":     _si(row[1]),
                "año":        _si(row[2]),
                "categoria":  str(row[3] or "").strip(),
                "subcat":     str(row[4] or "").strip(),
                "area":       str(row[5] or "").strip(),
                "proveedor":  str(row[6] or "").strip(),
                "concepto":   str(row[7] or "").strip(),
                "monto":      _sf(row[8]),
                "frecuencia": str(row[9] or "Semanal").strip() or "Semanal",
            })
    except Exception:
        pass
    return gastos


def _guardar_gasto_row(fecha: date, categoria: str, subcat: str, area: str,
                        proveedor: str, concepto: str, monto: float,
                        frecuencia: str = "Semanal"):
    sem = fecha.isocalendar()[1]
    año = fecha.year
    row = [fecha.strftime("%d/%m/%Y"), sem, año,
           categoria, subcat, area, proveedor, concepto, monto, frecuencia]
    append_rows(_K_G, [row])
    _leer_gastos.clear()


# ── Filtro semanal con soporte Mensual ────────────────────────────────────────
def _filtro_gastos_semana(gastos: list, semana: int, año: int) -> list:
    """
    Filtra gastos para una semana.
    Gastos Mensuales: incluye si el mes coincide y proratea por semanas del mes.
    """
    import calendar
    d = date.fromisocalendar(año, semana, 1)
    mes, año_m = d.month, d.year
    _, days = calendar.monthrange(año_m, mes)
    n_sem = max(4, round(days / 7))

    result = []
    for g in gastos:
        if g["frecuencia"] == "Mensual":
            if g["fecha"] and g["fecha"].month == mes and g["fecha"].year == año_m:
                gc = dict(g)
                gc["monto"] = round(g["monto"] / n_sem, 2)
                result.append(gc)
        else:
            if g["semana"] == semana and g["año"] == año:
                result.append(g)
    return result


# ── Calculos financieros ──────────────────────────────────────────────────────
def _ingresos_campo_veggi(pedidos: list, campo_clis: list, filtro_fn) -> dict:
    """Version simple para Inicio y Casa."""
    campo_set = {c.lower().strip() for c in campo_clis}
    inc = {"Campo": 0.0, "Veggi": 0.0}
    for p in pedidos:
        if not filtro_fn(p): continue
        if p["status"] == "Cancelado": continue
        total = _sf(p.get("total", 0))
        cli   = p["cliente"].lower().strip()
        if any(x in cli for x in _EXCLUIR_FINANCIERO): continue
        if any(x in cli for x in _INTERNOS):           continue
        inc["Campo" if cli in campo_set else "Veggi"] += total
    return inc


def _finanzas_detallado(pedidos: list, campo_clis: list,
                         filtro_fn, cli_zona: dict = None) -> dict:
    """
    Ingreso + costo_producto por area en una sola pasada.
    Retorna {"inc": {...}, "costo": {...}}
    """
    campo_set = {c.lower().strip() for c in campo_clis}
    cli_zona  = cli_zona or {}

    def _mk():
        return {"Campo": {},
                "Veggi": {"Rio": {}, "Antigua": {}, "Chimaltenango": {}},
                "Interno": {}}
    inc = _mk(); costo = _mk()

    for p in pedidos:
        if not filtro_fn(p): continue
        if p["status"] == "Cancelado": continue
        total      = _sf(p.get("total", 0))
        costo_prod = round(_sf(p.get("costo", 0)) * _sf(p.get("cantidad", 0)), 2)
        cli        = p["cliente"].lower().strip()
        nom        = p["cliente"]

        if any(x in cli for x in _EXCLUIR_FINANCIERO): continue

        if any(x in cli for x in _INTERNOS):
            inc["Interno"][nom]   = inc["Interno"].get(nom, 0)   + total
            costo["Interno"][nom] = costo["Interno"].get(nom, 0) + costo_prod
        elif cli in campo_set:
            inc["Campo"][nom]   = inc["Campo"].get(nom, 0)   + total
            costo["Campo"][nom] = costo["Campo"].get(nom, 0) + costo_prod
        else:
            zona = cli_zona.get(cli, "")
            sub  = zona if zona in ("Rio","Antigua","Chimaltenango") else "Rio"
            inc["Veggi"][sub][nom]   = inc["Veggi"][sub].get(nom, 0)   + total
            costo["Veggi"][sub][nom] = costo["Veggi"][sub].get(nom, 0) + costo_prod

    return {"inc": inc, "costo": costo}


def _setup_gastos_headers():
    """Escribe los encabezados correctos en la fila 1 del Sheet Gastos."""
    from gsheets import update_cells
    headers = [["Fecha","Semana","Año","Categoria","SubCategoria",
                 "Area","Proveedor","Concepto","Monto","Frecuencia"]]
    sheet = _ws(_K_G)
    sheet.update("A1:J1", headers)


# ── TAB 1: Registrar ──────────────────────────────────────────────────────────
def _tab_registrar(cfg: dict):
    st.markdown("#### Registrar Gasto")
    subcats  = cfg["subcats"]

    c1, c2 = st.columns(2)
    fecha     = c1.date_input("Fecha", value=date.today(), key="gr_fecha")
    categoria = c2.selectbox("Categoria", CATS, key="gr_cat")

    subs = subcats.get(categoria, [])
    subcat = st.selectbox("Sub-Categoria", subs, key="gr_sub") if subs else \
             st.text_input("Sub-Categoria", key="gr_sub_txt")

    # Area: solo para Veggi
    area = ""
    if categoria == "Veggi":
        area = st.selectbox("Area Veggi", ["Rio","Antigua","Chimaltenango","Hogares"],
                            key="gr_area")

    # Frecuencia: auto-switch si la subcat es mensual
    frec_default = "Mensual" if subcat in _MENSUAL_SUBCATS else "Semanal"
    frecuencia = st.selectbox("Frecuencia", ["Semanal","Mensual"],
                              index=0 if frec_default == "Semanal" else 1,
                              key="gr_frec",
                              help="Mensual: se prorratea por semanas del mes al ver por semana")

    proveedor = st.text_input("Proveedor / Pagado a", key="gr_prov")
    concepto  = st.text_input("Concepto", key="gr_conc")
    monto     = st.number_input("Monto (Q)", min_value=0.0, step=5.0, key="gr_monto")

    if st.button("Guardar Gasto", type="primary", key="gr_save"):
        if monto <= 0:
            st.warning("Monto debe ser mayor a 0.")
        else:
            _guardar_gasto_row(fecha, categoria, subcat, area,
                               proveedor, concepto, monto, frecuencia)
            st.success(f"Gasto guardado: {categoria} / {subcat} — Q{monto:,.2f}")
            st.rerun()


# ── TAB 2: Operacion ──────────────────────────────────────────────────────────
def _tab_operacion(pedidos: list, cfg: dict):
    hoy     = date.today()
    sem_def = hoy.isocalendar()[1]

    c1, c2 = st.columns(2)
    sem  = c1.number_input("Semana", 1, 53, sem_def, key="op_sem")
    año  = c2.number_input("Año",  2020, 2030, hoy.year, key="op_año")

    # Periodo anterior para comparacion
    sem_ant, año_ant = (sem-1, año) if sem > 1 else (52, año-1)
    periodo_lbl = f"Semana {sem} / {año}"

    gastos_all = _leer_gastos()
    gas_sem    = _filtro_gastos_semana(gastos_all, sem, año)
    gas_ant    = _filtro_gastos_semana(gastos_all, sem_ant, año_ant)

    filtro_ped     = lambda p: p["semana"] == sem  and p["año"] == año
    filtro_ped_ant = lambda p: p["semana"] == sem_ant and p["año"] == año_ant

    campo_clis = cfg["campo_clis"]

    # Mapa cliente→zona usando zonas Gastos
    from data_helper import cargar_clientes as _cc
    _clis    = _cc()
    cli_zona = {}
    for _c in _clis:
        for _z, _cods in _GASTOS_VEGGI_MAP.items():
            if _c.get("codigo_lugar","") in _cods:
                cli_zona[_c["nombre"].lower().strip()] = _z
                break

    fin  = _finanzas_detallado(pedidos, campo_clis, filtro_ped,  cli_zona)
    inc  = fin["inc"];  costo_p = fin["costo"]

    # ── Gastos por categoria ──────────────────────────────────────────────────
    def _gas_por_subcat(cat):
        d = {}
        for g in gas_sem:
            if g["categoria"] == cat:
                d[g["subcat"]] = d.get(g["subcat"], 0) + g["monto"]
        return d

    gas_campo_d  = _gas_por_subcat("Campo")
    gas_veggi_d  = _gas_por_subcat("Veggi")
    gas_compras_d = _gas_por_subcat("Compras")
    gas_campo_t  = sum(gas_campo_d.values())
    gas_veggi_t  = sum(gas_veggi_d.values())

    gas_vrio_t   = round(gas_veggi_t * _VEGGI_RIO_PCT,  2)
    gas_vant_t   = round(gas_veggi_t * _VEGGI_ANT_PCT,  2)
    gas_vchim_t  = round(gas_veggi_t * _VEGGI_CHIM_PCT, 2)
    gas_vhog_t   = round(gas_veggi_t * _VEGGI_HOG_PCT,  2)

    # ── Totales de ingreso y costo por area ───────────────────────────────────
    def _t(d): return sum(d.values())

    campo_it  = _t(inc["Campo"]);          campo_mn  = campo_it - gas_campo_t
    vrio_it   = _t(inc["Veggi"]["Rio"]);   vrio_cc   = _t(costo_p["Veggi"]["Rio"])
    vant_it   = _t(inc["Veggi"]["Antigua"]);vant_cc  = _t(costo_p["Veggi"]["Antigua"])
    vchim_it  = _t(inc["Veggi"]["Chimaltenango"]); vchim_cc = _t(costo_p["Veggi"]["Chimaltenango"])
    vh_it     = _t(inc["Interno"]);        vh_cc     = _t(costo_p["Interno"])

    vrio_mn   = vrio_it  - vrio_cc  - gas_vrio_t
    vant_mn   = vant_it  - vant_cc  - gas_vant_t
    vchim_mn  = vchim_it - vchim_cc - gas_vchim_t
    vh_mn     = vh_it    - vh_cc    - gas_vhog_t

    tot_op_it  = campo_it + vrio_it + vant_it + vchim_it
    tot_op_cc  = vrio_cc  + vant_cc  + vchim_cc
    tot_op_gas = gas_campo_t + gas_veggi_t
    tot_op_mn  = campo_mn + vrio_mn + vant_mn + vchim_mn
    tot_gen_it = tot_op_it + vh_it
    tot_gen_cc = tot_op_cc + vh_cc
    tot_gen_mn = tot_op_mn + vh_mn

    # ── Resumen 4 metricas ────────────────────────────────────────────────────
    st.markdown(f"### Resumen Operacion — {periodo_lbl}")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Ingresos",     f"Q{tot_gen_it:,.0f}")
    r2.metric("Costo Prod.",  f"Q{tot_gen_cc:,.0f}")
    r3.metric("Gastos Op.",   f"Q{tot_op_gas:,.0f}")
    r4.metric("Margen Neto",  f"Q{tot_gen_mn:,.0f}",
              delta=f"{tot_gen_mn/tot_gen_it*100:.1f}%" if tot_gen_it else "—")
    st.divider()

    # ── Helper: seccion por area ──────────────────────────────────────────────
    def _fq(v): return f"Q{v:,.0f}"
    def _seccion(title, cli_inc, cli_costo, inc_t, cc_t, gas_op, mn, pct="",
                 show_cc=True):
        st.markdown(f"#### {title}")
        rows = []
        for cli in sorted(cli_inc, key=lambda x: -cli_inc[x]):
            ic = cli_inc[cli]
            cc = cli_costo.get(cli, 0) if show_cc else None
            r  = {"Cliente": cli, "Ingreso": _fq(ic)}
            if show_cc: r["Costo Prod."] = _fq(cc); r["M.Bruto"] = _fq(ic-cc)
            rows.append(r)
        rows.append({"Cliente": "── Sub Total", "Ingreso": _fq(inc_t),
                     **(({"Costo Prod.": _fq(cc_t), "M.Bruto": _fq(inc_t-cc_t)}) if show_cc else {})})
        if len(rows) > 1:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        if gas_op:
            ga, _, gc = st.columns([3,2,2])
            ga.caption(f"(-) Gastos Operativos{pct}: Q{gas_op:,.0f}")
            gc.metric("Margen Neto", _fq(mn),
                      delta=f"{mn/inc_t*100:.1f}%" if inc_t else "—")
        elif inc_t:
            st.caption(f"Margen: {_fq(mn)} ({mn/inc_t*100:.1f}%)" if inc_t else "")
        st.divider()

    # ── Secciones por area ────────────────────────────────────────────────────
    _seccion("Campo", inc["Campo"], costo_p["Campo"],
             campo_it, 0, gas_campo_t, campo_mn, show_cc=False)
    _seccion("Veggi — Rio",           inc["Veggi"]["Rio"],          costo_p["Veggi"]["Rio"],
             vrio_it,  vrio_cc,  gas_vrio_t,  vrio_mn,  " (50%)")
    _seccion("Veggi — Antigua",       inc["Veggi"]["Antigua"],      costo_p["Veggi"]["Antigua"],
             vant_it,  vant_cc,  gas_vant_t,  vant_mn,  " (25%)")
    _seccion("Veggi — Chimaltenango", inc["Veggi"]["Chimaltenango"],costo_p["Veggi"]["Chimaltenango"],
             vchim_it, vchim_cc, gas_vchim_t, vchim_mn, " (12.5%)")

    # ── Tabla resumen ─────────────────────────────────────────────────────────
    st.markdown("#### Resumen por Area")
    filas = [
        {"Area": "Campo",              "Ingreso": _fq(campo_it), "Costo Prod.": "—",          "Gastos Op.": _fq(gas_campo_t), "Margen Neto": _fq(campo_mn)},
        {"Area": "Veggi Rio",          "Ingreso": _fq(vrio_it),  "Costo Prod.": _fq(vrio_cc),  "Gastos Op.": _fq(gas_vrio_t),  "Margen Neto": _fq(vrio_mn)},
        {"Area": "Veggi Antigua",      "Ingreso": _fq(vant_it),  "Costo Prod.": _fq(vant_cc),  "Gastos Op.": _fq(gas_vant_t),  "Margen Neto": _fq(vant_mn)},
        {"Area": "Veggi Chimaltenango","Ingreso": _fq(vchim_it), "Costo Prod.": _fq(vchim_cc), "Gastos Op.": _fq(gas_vchim_t), "Margen Neto": _fq(vchim_mn)},
        {"Area": "── TOTAL Op.",       "Ingreso": _fq(tot_op_it),"Costo Prod.": _fq(tot_op_cc),"Gastos Op.": _fq(tot_op_gas),  "Margen Neto": _fq(tot_op_mn)},
        {"Area": "",                   "Ingreso": "",             "Costo Prod.": "",             "Gastos Op.": "",               "Margen Neto": ""},
        {"Area": "Veggi Hogares",      "Ingreso": _fq(vh_it),    "Costo Prod.": _fq(vh_cc),     "Gastos Op.": _fq(gas_vhog_t),  "Margen Neto": _fq(vh_mn)},
        {"Area": "",                   "Ingreso": "",             "Costo Prod.": "",             "Gastos Op.": "",               "Margen Neto": ""},
        {"Area": "TOTAL GENERAL",      "Ingreso": _fq(tot_gen_it),"Costo Prod.": _fq(tot_gen_cc),"Gastos Op.": _fq(tot_op_gas), "Margen Neto": _fq(tot_gen_mn)},
    ]
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)

    # ── Reconciliacion Compras ────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Inversion en Producto (Reconciliacion)")
    tot_compras = sum(gas_compras_d.values())
    costo_pedidos = tot_op_cc + vh_cc   # suma de costo×cant todos los pedidos Veggi

    if gas_compras_d:
        df_comp = pd.DataFrame([
            {"Proveedor/Origen": k, "Invertido": _fq(v)}
            for k, v in sorted(gas_compras_d.items(), key=lambda x: -x[1])
        ] + [{"Proveedor/Origen": "── Total Compras", "Invertido": _fq(tot_compras)}])
        st.dataframe(df_comp, hide_index=True, use_container_width=True)
    else:
        st.info("Sin compras registradas en esta semana.")

    rc1, rc2, rc3 = st.columns(3)
    rc1.metric("Total Compras registradas", _fq(tot_compras))
    rc2.metric("Costo Producto en Pedidos", _fq(costo_pedidos))
    diff = tot_compras - costo_pedidos
    rc3.metric("Diferencia (inventario/ajuste)", _fq(diff),
               delta="Comprado > Vendido" if diff > 0 else ("Vendido > Comprado" if diff < 0 else "Exacto"),
               delta_color="normal")


# ── TAB 3: Casa ───────────────────────────────────────────────────────────────
def _tab_casa(cfg: dict):
    hoy     = date.today()
    sem_def = hoy.isocalendar()[1]

    c1, c2 = st.columns(2)
    mes = c1.selectbox("Mes", list(range(1,13)),
                        index=hoy.month-1,
                        format_func=lambda m: ["Ene","Feb","Mar","Abr","May","Jun",
                                               "Jul","Ago","Sep","Oct","Nov","Dic"][m-1],
                        key="ca_mes")
    año = c2.number_input("Año", 2020, 2030, hoy.year, key="ca_año")

    gastos_all = _leer_gastos()
    gas_casa   = [g for g in gastos_all
                  if g["categoria"] == "Casa"
                  and g["fecha"] and g["fecha"].month == mes
                  and g["fecha"].year == año]

    budgets = cfg["budgets"]
    gas_by_sub: dict = {}
    for g in gas_casa:
        gas_by_sub[g["subcat"]] = gas_by_sub.get(g["subcat"], 0) + g["monto"]

    total_gas  = sum(gas_by_sub.values())
    total_bud  = sum(budgets.values())

    MESES_ES = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    st.markdown(f"### Gastos Casa — {MESES_ES[mes-1]} {año}")

    k1, k2, k3 = st.columns(3)
    k1.metric("Gastado",     f"Q{total_gas:,.0f}")
    k2.metric("Presupuesto", f"Q{total_bud:,.0f}")
    k3.metric("Diferencia",  f"Q{total_bud-total_gas:,.0f}",
              delta="dentro" if total_gas <= total_bud else "excedido",
              delta_color="normal" if total_gas <= total_bud else "inverse")

    st.divider()
    subs = cfg["subcats"].get("Casa", [])
    rows = []
    for s in subs:
        g_val = gas_by_sub.get(s, 0)
        b_val = budgets.get(s, 0)
        rows.append({
            "Categoria": s,
            "Gastado":   f"Q{g_val:,.0f}",
            "Presupuesto": f"Q{b_val:,.0f}",
            "Diferencia":  f"Q{b_val-g_val:,.0f}",
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


# ── TAB 4: Historial ──────────────────────────────────────────────────────────
def _tab_historial(cfg: dict):
    gastos = _leer_gastos()
    if not gastos:
        st.info("Sin gastos registrados.")
        return

    # ── Filtros ───────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    f_cat  = c1.selectbox("Categoria", ["Todas"] + CATS, key="hi_cat")
    f_año  = c2.number_input("Año", 2020, 2030, date.today().year, key="hi_año")
    sem_def = date.today().isocalendar()[1]
    f_sem  = c3.number_input("Semana (0=todas)", 0, 53, sem_def, key="hi_sem")
    f_frec = c4.selectbox("Frecuencia", ["Todas","Semanal","Mensual"], key="hi_frec")

    filtrados = [g for g in gastos
                 if (f_cat == "Todas" or g["categoria"] == f_cat)
                 and (g["año"] == f_año)
                 and (f_sem == 0 or g["semana"] == f_sem)
                 and (f_frec == "Todas" or g["frecuencia"] == f_frec)]

    df = pd.DataFrame([{
        "Fecha":        g["fecha"].strftime("%d/%m/%Y") if g["fecha"] else "",
        "Semana":       g["semana"],
        "Categoria":    g["categoria"],
        "SubCategoria": g["subcat"],
        "Area":         g["area"],
        "Frecuencia":   g["frecuencia"],
        "Proveedor":    g["proveedor"],
        "Concepto":     g["concepto"],
        "Monto (Q)":    g["monto"],
    } for g in reversed(filtrados)])

    st.dataframe(df, hide_index=True, use_container_width=True)
    if not df.empty:
        st.caption(f"{len(df)} registros · Total: Q{df['Monto (Q)'].sum():,.2f}")

    # ── Editar / Eliminar ─────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Editar / Eliminar registro")

    if not filtrados:
        st.info("Sin registros para el filtro seleccionado.")
        return

    PLACEHOLDER = "— Seleccionar registro —"
    opciones = {PLACEHOLDER: None} | {
        f"Fila {g['row_num']} | {g['fecha'].strftime('%d/%m/%Y') if g['fecha'] else '?'}"
        f" | {g['categoria']} / {g['subcat']} | Q{g['monto']:,.0f}": g
        for g in filtrados
    }
    sel_label = st.selectbox("Selecciona registro para editar / eliminar",
                              list(opciones.keys()), key="hi_sel")
    sel = opciones[sel_label]

    if sel is None:
        st.caption("Selecciona un registro arriba para ver el formulario de edición.")
        return

    with st.form("form_edit_gasto"):
        e1, e2 = st.columns(2)
        fecha_e = e1.date_input("Fecha", value=sel["fecha"] or date.today(), key="he_fecha")
        cat_e   = e2.selectbox("Categoria", CATS,
                                index=CATS.index(sel["categoria"]) if sel["categoria"] in CATS else 0,
                                key="he_cat")

        subs_e  = cfg["subcats"].get(cat_e, [])
        subcat_e = st.selectbox("SubCategoria", subs_e,
                                 index=subs_e.index(sel["subcat"]) if sel["subcat"] in subs_e else 0,
                                 key="he_sub") if subs_e else                    st.text_input("SubCategoria", value=sel["subcat"], key="he_sub_txt")

        areas  = ["","Rio","Antigua","Chimaltenango","Hogares"]
        area_e = st.selectbox(
            "Area (solo para Veggi)",
            areas,
            index=areas.index(sel["area"]) if sel["area"] in areas else 0,
            key="he_area",
            help="Selecciona el area si es un gasto Veggi"
        )

        frec_opts = ["Semanal","Mensual"]
        frec_e = st.selectbox("Frecuencia", frec_opts,
                               index=frec_opts.index(sel["frecuencia"]) if sel["frecuencia"] in frec_opts else 0,
                               key="he_frec")

        f1, f2 = st.columns(2)
        prov_e  = f1.text_input("Proveedor", value=sel["proveedor"], key="he_prov")
        conc_e  = f2.text_input("Concepto",  value=sel["concepto"],  key="he_conc")
        monto_e = st.number_input("Monto (Q)", value=float(sel["monto"]),
                                   min_value=0.0, step=5.0, key="he_monto")

        b1, b2 = st.columns(2)
        guardar  = b1.form_submit_button("💾 Actualizar", type="primary")
        eliminar = b2.form_submit_button("🗑️ Eliminar", type="secondary")

    if guardar:
        sem_e = fecha_e.isocalendar()[1]
        año_e = fecha_e.year
        upd = [
            {"range": f"A{sel['row_num']}", "values": [[fecha_e.strftime("%d/%m/%Y")]]},
            {"range": f"B{sel['row_num']}", "values": [[sem_e]]},
            {"range": f"C{sel['row_num']}", "values": [[año_e]]},
            {"range": f"D{sel['row_num']}", "values": [[cat_e]]},
            {"range": f"E{sel['row_num']}", "values": [[subcat_e]]},
            {"range": f"F{sel['row_num']}", "values": [[area_e]]},
            {"range": f"G{sel['row_num']}", "values": [[prov_e]]},
            {"range": f"H{sel['row_num']}", "values": [[conc_e]]},
            {"range": f"I{sel['row_num']}", "values": [[monto_e]]},
            {"range": f"J{sel['row_num']}", "values": [[frec_e]]},
        ]
        update_cells(_K_G, upd)
        _leer_gastos.clear()
        st.session_state.pop("hi_sel", None)
        st.success("Registro actualizado.")
        st.rerun()

    if eliminar:
        from gsheets import delete_rows
        delete_rows(_K_G, [sel["row_num"]])
        _leer_gastos.clear()
        st.session_state.pop("hi_sel", None)
        st.success("Registro eliminado.")
        st.rerun()


# ── TAB 5: Categorias ─────────────────────────────────────────────────────────
def _tab_categorias():
    cfg      = _cargar_config()
    subcats  = {k: list(v) for k, v in cfg["subcats"].items()}
    campo_clis = cfg["campo_clis"]
    budgets  = cfg["budgets"]

    st.markdown("#### Subcategorias por Categoria")
    st.caption("Agrega o elimina subcategorias para cada categoria de gasto.")

    for cat in CATS:
        st.markdown(f"**{cat}**")
        subs = subcats[cat]
        for i, s in enumerate(list(subs)):
            col1, col2 = st.columns([6, 1])
            col1.markdown(f"&nbsp;&nbsp;{s}")
            if col2.button("🗑️", key=f"del_{cat}_{i}", help=f"Eliminar {s}"):
                subs.remove(s)
                subcats[cat] = subs
                _guardar_config(subcats, campo_clis, budgets)
                st.success(f"'{s}' eliminado de {cat}.")
                st.rerun()

        with st.form(f"form_add_{cat}"):
            nc1, nc2 = st.columns([4,1])
            nueva = nc1.text_input(f"Nueva subcategoria en {cat}", key=f"new_{cat}")
            if nc2.form_submit_button("➕"):
                nueva = nueva.strip()
                if nueva and nueva not in subs:
                    subs.append(nueva)
                    subcats[cat] = subs
                    _guardar_config(subcats, campo_clis, budgets)
                    st.success(f"'{nueva}' agregado a {cat}.")
                    st.rerun()
                elif nueva in subs:
                    st.warning("Ya existe.")
        st.divider()

    # ── Clientes Campo ────────────────────────────────────────────────────────
    st.markdown("**Clientes Campo**")
    st.caption("Sus pedidos se contabilizan como ingreso Campo.")
    for i, cli in enumerate(list(campo_clis)):
        co1, co2 = st.columns([6,1])
        co1.markdown(f"&nbsp;&nbsp;{cli}")
        if co2.button("🗑️", key=f"del_campo_{i}"):
            campo_clis.remove(cli)
            _guardar_config(subcats, campo_clis, budgets)
            st.rerun()

    with st.form("form_add_campo"):
        cc1, cc2 = st.columns([4,1])
        nuevo_cli = cc1.text_input("Nuevo cliente Campo", placeholder="nombre en minusculas")
        if cc2.form_submit_button("➕"):
            nc = nuevo_cli.strip().lower()
            if nc and nc not in campo_clis:
                campo_clis.append(nc)
                _guardar_config(subcats, campo_clis, budgets)
                st.success(f"'{nc}' agregado.")
                st.rerun()
    st.divider()

    # ── Encabezados Sheet ────────────────────────────────────────────────────
    st.markdown("**Encabezados del Sheet de Gastos**")
    st.caption("Si las columnas en Google Sheets no coinciden con los datos, "
               "ejecuta esto una vez para corregir la fila de encabezados.")
    if st.button("Actualizar encabezados en Sheet Gastos", key="fix_headers"):
        _setup_gastos_headers()
        st.success("Encabezados actualizados: "
                   "Fecha | Semana | Año | Categoria | SubCategoria | "
                   "Area | Proveedor | Concepto | Monto | Frecuencia")
    st.divider()

    # ── Presupuestos Casa ─────────────────────────────────────────────────────
    st.markdown("**Presupuestos Mensuales Casa (Q)**")
    subs_casa = subcats.get("Casa", [])
    edited_bud = {}
    for s in subs_casa:
        edited_bud[s] = st.number_input(s, value=float(budgets.get(s, 0)),
                                         step=50.0, key=f"bud_{s}")
    if st.button("Guardar Presupuestos", key="bud_save"):
        _guardar_config(subcats, campo_clis, edited_bud)
        st.success("Presupuestos guardados.")
        st.rerun()


# ── MOSTRAR ────────────────────────────────────────────────────────────────────
def mostrar():
    st.markdown("## Gastos")
    if st.button("Inicio", key="btn_home_gas", type="secondary"):
        st.session_state["_nav_target"] = "Inicio"
        st.rerun()
    st.divider()

    cfg     = _cargar_config()
    from excel_helper import leer_pedidos
    pedidos = leer_pedidos()

    t1, t2, t3, t4 = st.tabs([
        "Registrar",
        "Operacion",
        "Historial",
        "Categorias",
    ])
    with t1: _tab_registrar(cfg)
    with t2: _tab_operacion(pedidos, cfg)
    with t3: _tab_historial(cfg)
    with t4: _tab_categorias()
