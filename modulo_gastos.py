"""
modulo_gastos.py — Registro y análisis de gastos operativos + personales
Tabs: ➕ Registrar | 📊 Operación | 🏠 Casa | 📋 Historial | ⚙️ Categorías
"""
import streamlit as st

def _conf(key: str, msg: str):
    """Guarda mensaje de confirmación para mostrar en el próximo render."""
    st.session_state[f"_conf_{key}"] = msg

def _show_conf(key: str):
    """Muestra y consume el mensaje de confirmación (desaparece en siguiente acción)."""
    msg = st.session_state.pop(f"_conf_{key}", None)
    if msg:
        st.success(msg)

import pandas as pd
from datetime import date, datetime
from gsheets import get_all_rows, append_rows, update_cells
from excel_helper import _sf, _si

_K_G  = "gastos"
_K_GC = "gastosconfig"

MESES_ES = ["","Ene","Feb","Mar","Abr","May","Jun",
            "Jul","Ago","Sep","Oct","Nov","Dic"]

# ── Defaults ──────────────────────────────────────────────────────────────────
SUBCATS_DEFAULT = [
    ("MO Campo","Campo"),("Agroquimicos","Campo"),
    ("Transporte Campo","Campo"),("Semilla","Campo"),("Otros Campo","Campo"),
    ("Transporte Veggi","Veggi"),("Mano Obra","Veggi"),("Empaque","Veggi"),
    ("Compras Lechugas","Veggi"),("Compras Patzi","Veggi"),
    ("Compras Carlos","Veggi"),("Compras Cenma","Veggi"),("Otros Veggi","Veggi"),
    ("Colegios","Casa"),("Transporte Casa","Casa"),("Ocio","Casa"),
    ("Energia Electrica","Casa"),("Celulares","Casa"),("Otros Casa","Casa"),
]
CAMPO_CLIENTS_DEFAULT = ["aldyk","tierra fria","legume","4 pinos","cebollines"]
CATS = ["Campo","Veggi","Casa"]

PROVEEDORES = ["CENMA","Patojas","El Huerto","Productor Directo",
               "Importado","Otro","Sin Proveedor"]


# ── Config I/O ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def _cargar_config() -> dict:
    """
    Lee GastosConfig sheet.
    Format: col A = tipo (SUBCAT/CAMPO/BUDGET), B = val1, C = val2
    """
    subcats, campo_clis, budgets = list(SUBCATS_DEFAULT), list(CAMPO_CLIENTS_DEFAULT), {}
    try:
        rows = get_all_rows(_K_GC)
        subcats_custom, campo_custom = [], []
        for row in rows:
            if not row or not row[0]: continue
            t = str(row[0]).strip().upper()
            if t == "SUBCAT" and len(row) >= 3:
                subcats_custom.append((str(row[1]).strip(), str(row[2]).strip()))
            elif t == "CAMPO" and len(row) >= 2:
                campo_custom.append(str(row[1]).strip().lower())
            elif t == "BUDGET" and len(row) >= 3:
                budgets[str(row[1]).strip()] = _sf(row[2])
        if subcats_custom: subcats = subcats_custom
        if campo_custom:   campo_clis = campo_custom
    except Exception:
        pass
    return {"subcats": subcats, "campo_clis": campo_clis, "budgets": budgets}


def _guardar_config(subcats, campo_clis, budgets):
    rows = []
    for sub, cat in subcats:
        rows.append(["SUBCAT", sub, cat, "", "", ""])
    for cli in campo_clis:
        rows.append(["CAMPO", cli, "", "", "", ""])
    for sub, monto in budgets.items():
        rows.append(["BUDGET", sub, str(monto), "", "", ""])
    # Clear and rewrite
    try:
        from gsheets import ws as _ws
        sheet = _ws(_K_GC)
        sheet.clear()
        if rows:
            sheet.append_rows([["Tipo","Val1","Val2","","",""]] + rows,
                               value_input_option="USER_ENTERED")
        _cargar_config.clear()
    except Exception as e:
        st.error(f"Error guardando config: {e}")


# ── Gastos I/O ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _leer_gastos() -> list[dict]:
    gastos = []
    try:
        rows = get_all_rows(_K_G)
        for i, row in enumerate(rows, start=2):
            while len(row) < 9: row.append("")
            fecha = None
            try: fecha = datetime.strptime(str(row[0]).strip(), "%d/%m/%Y").date()
            except: pass
            gastos.append({
                "row_num":    i,
                "fecha":      fecha,
                "semana":     _si(row[1]),
                "año":        _si(row[2]),
                "mes":        fecha.month if fecha else 0,
                "categoria":  str(row[3] or ""),
                "subcat":     str(row[4] or ""),
                "proveedor":  str(row[5] or ""),
                "concepto":   str(row[6] or ""),
                "monto":      _sf(row[7]),
                "area":        str(row[8] or "").strip(),
            })
    except Exception:
        pass
    return gastos


def _guardar_gasto_row(fecha: date, categoria: str, subcat: str,
                        proveedor: str, concepto: str, monto: float,
                        area: str = ""):
    sem = fecha.isocalendar()[1]
    año = fecha.year
    row = [
        fecha.strftime("%d/%m/%Y"), sem, año,
        categoria, subcat, proveedor, concepto, monto, area
    ]
    append_rows(_K_G, [row])
    _leer_gastos.clear()


# ── Helpers financieros ───────────────────────────────────────────────────────
# Clientes excluidos de financiero
_EXCLUIR_FINANCIERO = {"wilson"}          # excluye totalmente
_INTERNOS           = {"veggi hogares"}     # mostrar aparte, no sumar

# Mapa zonas para Gastos: separa Antigua (L03/L04) de Chimaltenango (L10)
_GASTOS_VEGGI_MAP = {
    "Rio":           ["L01", "L02"],
    "Antigua":       ["L03"],
    "Chimaltenango": ["L04"],
}
_VEGGI_RIO_PCT  = 0.60
_VEGGI_ANT_PCT  = 0.20
_VEGGI_CHIM_PCT = 0.20

def _ingresos_campo_veggi(pedidos: list, campo_clis: list,
                           filtro_fn) -> dict:
    """
    Separa ingresos en Campo y Veggi (simple, para Inicio y Casa).
    Wilson: excluido. Internos (veggi/chimalt): excluidos del total.
    """
    campo_set = {c.lower().strip() for c in campo_clis}
    inc = {"Campo": 0.0, "Veggi": 0.0}
    for p in pedidos:
        if not filtro_fn(p): continue
        if p["status"] == "Cancelado": continue
        total = _sf(p.get("total", 0))
        cli   = p["cliente"].lower().strip()
        if any(x in cli for x in _EXCLUIR_FINANCIERO): continue
        if any(x in cli for x in _INTERNOS):           continue
        if cli in campo_set:
            inc["Campo"] += total
        else:
            inc["Veggi"] += total
    return inc


def _finanzas_detallado(pedidos: list, campo_clis: list,
                         filtro_fn, cli_zona: dict = None) -> dict:
    """
    Una sola pasada: calcula ingreso Y costo_producto por area.
    cli_zona debe usar los keys de _GASTOS_VEGGI_MAP: Rio, Antigua, Chimaltenango.
    Retorna: {"inc": {...}, "costo": {...}}
    """
    campo_set = {c.lower().strip() for c in campo_clis}
    cli_zona  = cli_zona or {}

    def _mk():
        return {
            "Campo":   {},
            "Veggi":   {"Rio": {}, "Antigua": {}, "Chimaltenango": {}},
            "Interno": {},
        }

    inc   = _mk()
    costo = _mk()

    for p in pedidos:
        if not filtro_fn(p): continue
        if p["status"] == "Cancelado": continue

        total      = _sf(p.get("total", 0))
        costo_prod = round(_sf(p.get("costo", 0)) * _sf(p.get("cantidad", 0)), 2)
        cli        = p["cliente"].lower().strip()
        nom        = p["cliente"]

        if any(x in cli for x in _EXCLUIR_FINANCIERO):
            continue  # Wilson: invisible

        if any(x in cli for x in _INTERNOS):
            inc["Interno"][nom]   = inc["Interno"].get(nom, 0)   + total
            costo["Interno"][nom] = costo["Interno"].get(nom, 0) + costo_prod
        elif cli in campo_set:
            inc["Campo"][nom]   = inc["Campo"].get(nom, 0)   + total
            costo["Campo"][nom] = costo["Campo"].get(nom, 0) + costo_prod
        else:
            zona = cli_zona.get(cli, "")
            sub  = zona if zona in ("Rio", "Antigua", "Chimaltenango") else "Rio"
            inc["Veggi"][sub][nom]   = inc["Veggi"][sub].get(nom, 0)   + total
            costo["Veggi"][sub][nom] = costo["Veggi"][sub].get(nom, 0) + costo_prod

    return {"inc": inc, "costo": costo}


def _costo_proyectado(pedidos: list, campo_clis: list, filtro_fn) -> dict:
    """Suma costo×cantidad por categoría desde pedidos."""
    campo_set = {c.lower().strip() for c in campo_clis}
    proy = {"Campo": 0.0, "Veggi": 0.0}
    for p in pedidos:
        if not filtro_fn(p): continue
        if p["status"] == "Cancelado": continue
        costo = _sf(p.get("costo", 0)) * _sf(p.get("cantidad", 0))
        if any(k in p["cliente"].lower() for k in campo_set):
            proy["Campo"] += costo
        else:
            proy["Veggi"] += costo
    return proy


def _semanas_del_mes(mes: int, año: int) -> list[int]:
    """Retorna lista de números de semana ISO que caen en ese mes/año."""
    import calendar
    sems = set()
    for d in range(1, calendar.monthrange(año, mes)[1] + 1):
        sems.add(date(año, mes, d).isocalendar()[1])
    return list(sems)


# ── TAB Registrar ─────────────────────────────────────────────────────────────
def _tab_registrar(cfg: dict):
    _show_conf("gasto")
    st.markdown("#### ➕ Registrar Gasto")
    subcats = cfg["subcats"]
    cat_opts = CATS + sorted({c for _, c in subcats if c not in CATS})
    subcat_map = {}
    for sub, cat in subcats:
        subcat_map.setdefault(cat, []).append(sub)

    c1, c2 = st.columns(2)
    fecha    = c1.date_input("Fecha", value=date.today(), key="gto_fecha")
    categoria = c2.selectbox("Categoría", cat_opts, key="gto_cat")
    subcats_disp = subcat_map.get(categoria, [])
    subcat   = st.selectbox("SubCategoría", subcats_disp, key="gto_sub") \
               if subcats_disp else st.text_input("SubCategoría", key="gto_sub_txt")

    c3, c4 = st.columns(2)
    proveedor = c3.selectbox("Proveedor", [""] + PROVEEDORES, key="gto_prov")
    monto     = c4.number_input("Monto (Q)", min_value=0.0, step=10.0,
                                 format="%.2f", key="gto_monto")
    concepto  = st.text_input("Concepto / Descripción", key="gto_concepto",
                               placeholder="Ej: Compra semilla Mercedes F1, pago jornal...")

    if st.button("💾 Guardar Gasto", type="primary", key="gto_save"):
        if monto <= 0:
            st.error("El monto debe ser mayor a 0.")
        else:
            _guardar_gasto_row(fecha, categoria,
                               subcat if subcat else concepto,
                               proveedor, concepto, monto)
            _conf("gasto", f"✅ Gasto guardado — {subcat or concepto} · "
                           f"Q{monto:,.2f} · {categoria} · {fecha.strftime('%d/%m/%Y')}")
            st.rerun()


# ── TAB Operación ─────────────────────────────────────────────────────────────
def _tab_operacion(pedidos: list, cfg: dict):
    st.markdown("#### 📊 Resumen Operacional")

    hoy     = date.today()
    sem_act = hoy.isocalendar()[1]
    año_act = hoy.year
    mes_act = hoy.month

    modo = st.radio("Ver por:", ["Semana","Mes"], horizontal=True, key="op_modo")
    c1, c2 = st.columns(2)
    if modo == "Semana":
        sem = c1.number_input("Semana", 1, 53, sem_act, key="op_sem")
        año = c2.number_input("Año", 2020, 2030, año_act, key="op_año")
        filtro_ped = lambda p: p["semana"]==sem and p["año"]==año
        filtro_gas = lambda g: g["semana"]==sem and g["año"]==año
        periodo_lbl = f"Semana {sem}/{año}"
        # Mes anterior mismo período
        prev_sem = sem - 1 if sem > 1 else 52
        prev_año = año if sem > 1 else año - 1
        filtro_ant = lambda g: g["semana"]==prev_sem and g["año"]==prev_año
        filtro_ped_ant = lambda p: p["semana"]==prev_sem and p["año"]==prev_año
    else:
        mes = c1.selectbox("Mes", list(range(1,13)),
                            index=mes_act-1,
                            format_func=lambda m: MESES_ES[m],
                            key="op_mes")
        año = c2.number_input("Año", 2020, 2030, año_act, key="op_año_m")
        filtro_ped = lambda p: (p["fecha"] and p["fecha"].month==mes
                                and p["fecha"].year==año)
        filtro_gas = lambda g: g["mes"]==mes and g["año"]==año
        periodo_lbl = f"{MESES_ES[mes]} {año}"
        prev_mes = mes-1 if mes>1 else 12
        prev_año = año if mes>1 else año-1
        filtro_ant = lambda g: g["mes"]==prev_mes and g["año"]==prev_año
        filtro_ped_ant = lambda p: (p["fecha"] and p["fecha"].month==prev_mes
                                    and p["fecha"].year==prev_año)

    gastos = _leer_gastos()
    campo_clis = cfg["campo_clis"]

    # Mapa cliente → zona usando mapa Gastos (separa Antigua de Chimal)
    from data_helper import cargar_clientes as _cc
    _clis = _cc()
    cli_zona = {}
    for _c in _clis:
        for _z, _cods in _GASTOS_VEGGI_MAP.items():
            if _c.get("codigo_lugar","") in _cods:
                cli_zona[_c["nombre"].lower().strip()] = _z
                break

    # Finanzas detalladas (ingreso + costo_producto por zona, una sola pasada)
    fin     = _finanzas_detallado(pedidos, campo_clis, filtro_ped,     cli_zona)
    fin_ant = _finanzas_detallado(pedidos, campo_clis, filtro_ped_ant, cli_zona)
    inc     = fin["inc"]
    costo_p = fin["costo"]
    inc_s   = _ingresos_campo_veggi(pedidos, campo_clis, filtro_ped)

    # Gastos reales por categoría (sin Casa)
    gas_op  = [g for g in gastos if filtro_gas(g) and g["categoria"] != "Casa"]
    gas_ant = [g for g in gastos if filtro_ant(g) and g["categoria"] != "Casa"]

    gas_cat = {}
    for g in gas_op:
        gas_cat.setdefault(g["categoria"], {})
        gas_cat[g["categoria"]][g["subcat"]] = \
            gas_cat[g["categoria"]].get(g["subcat"], 0) + g["monto"]

    total_inc   = sum(inc_s.values())
    st.markdown(f"**{periodo_lbl}**")

    # ── Totales por area ──────────────────────────────────────────────────────
    gas_veggi   = gas_cat.get("Veggi", {})
    gas_veggi_t = sum(gas_veggi.values())
    gas_campo_d = gas_cat.get("Campo", {})
    gas_campo_t = sum(gas_campo_d.values())

    gas_vrio_t  = round(gas_veggi_t * _VEGGI_RIO_PCT,  2)
    gas_vant_t  = round(gas_veggi_t * _VEGGI_ANT_PCT,  2)
    gas_vchim_t = round(gas_veggi_t * _VEGGI_CHIM_PCT, 2)

    # Ingreso / CostoCompra por área (de pedidos)
    campo_it   = sum(inc["Campo"].values())
    campo_cc   = 0   # Campo no tiene costo de compra — usa gastos reales
    campo_mn   = campo_it - gas_campo_t

    vrio_it    = sum(inc["Veggi"]["Rio"].values())
    vrio_cc    = sum(costo_p["Veggi"]["Rio"].values())
    vrio_mn    = vrio_it - vrio_cc - gas_vrio_t

    vant_it    = sum(inc["Veggi"]["Antigua"].values())
    vant_cc    = sum(costo_p["Veggi"]["Antigua"].values())
    vant_mn    = vant_it - vant_cc - gas_vant_t

    vchim_it   = sum(inc["Veggi"]["Chimaltenango"].values())
    vchim_cc   = sum(costo_p["Veggi"]["Chimaltenango"].values())
    vchim_mn   = vchim_it - vchim_cc - gas_vchim_t

    vh_it      = sum(inc["Interno"].values())
    vh_cc      = sum(costo_p["Interno"].values())
    vh_mn      = vh_it - vh_cc

    # Totales operativos (sin Hogares)
    tot_op_it  = campo_it + vrio_it + vant_it + vchim_it
    tot_op_cc  = vrio_cc  + vant_cc  + vchim_cc          # Campo no tiene CC
    tot_op_gas = gas_campo_t + gas_veggi_t
    tot_op_mn  = campo_mn + vrio_mn + vant_mn + vchim_mn

    # Gran total (incluyendo Hogares)
    tot_gen_it  = tot_op_it  + vh_it
    tot_gen_cc  = tot_op_cc  + vh_cc
    tot_gen_gas = tot_op_gas                              # Hogares sin gastos op
    tot_gen_mn  = tot_op_mn  + vh_mn

    # ── RESUMEN 4 MÉTRICAS ────────────────────────────────────────────────────
    st.markdown("### Resumen Operación")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Ingresos",      f"Q{tot_gen_it:,.0f}")
    r2.metric("Costo Compra",  f"Q{tot_gen_cc:,.0f}")
    r3.metric("Gastos Op.",    f"Q{tot_gen_gas:,.0f}")
    r4.metric("Margen Neto",   f"Q{tot_gen_mn:,.0f}",
              delta=f"{tot_gen_mn/tot_gen_it*100:.1f}%" if tot_gen_it else "—")
    st.divider()

    # ── Helper: sección detallada por área ────────────────────────────────────
    def _seccion(title, cli_inc, cli_costo, inc_t, cc_t, gas_op_val, mn, pct_str="",
                 show_cc=True):
        st.markdown(f"#### {title}")
        rows = []
        for cli in sorted(cli_inc, key=lambda x: -cli_inc[x]):
            ic = cli_inc[cli]
            cc = cli_costo.get(cli, 0) if show_cc else None
            row = {"Cliente": cli, "Ingreso": f"Q{ic:,.0f}"}
            if show_cc:
                row["Costo Compra"] = f"Q{cc:,.0f}"
                row["M. Bruto"]     = f"Q{ic-cc:,.0f}"
            rows.append(row)
        # Sub total
        sub = {"Cliente": "── Sub Total", "Ingreso": f"Q{inc_t:,.0f}"}
        if show_cc:
            sub["Costo Compra"] = f"Q{cc_t:,.0f}"
            sub["M. Bruto"]     = f"Q{inc_t-cc_t:,.0f}"
        rows.append(sub)
        if rows[:-1]:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        if gas_op_val:
            ga, _, gc = st.columns([3, 2, 2])
            ga.caption(f"(-) Gastos Operativos{pct_str}: Q{gas_op_val:,.0f}")
            gc.metric("Margen Neto", f"Q{mn:,.0f}",
                      delta=f"{mn/inc_t*100:.1f}%" if inc_t else "—")
        elif inc_t:
            st.caption(f"Margen: Q{mn:,.0f}"
                       + (f" ({mn/inc_t*100:.1f}%)" if inc_t else ""))
        st.divider()

    # ── SECCIONES POR ÁREA ────────────────────────────────────────────────────
    _seccion("Campo",
             inc["Campo"], costo_p["Campo"],
             campo_it, 0, gas_campo_t, campo_mn,
             show_cc=False)

    _seccion("Veggi — Río",
             inc["Veggi"]["Rio"], costo_p["Veggi"]["Rio"],
             vrio_it, vrio_cc, gas_vrio_t, vrio_mn, " (60%)")

    _seccion("Veggi — Antigua",
             inc["Veggi"]["Antigua"], costo_p["Veggi"]["Antigua"],
             vant_it, vant_cc, gas_vant_t, vant_mn, " (20%)")

    _seccion("Veggi — Chimaltenango",
             inc["Veggi"]["Chimaltenango"], costo_p["Veggi"]["Chimaltenango"],
             vchim_it, vchim_cc, gas_vchim_t, vchim_mn, " (20%)")

    # ── TABLA RESUMEN ─────────────────────────────────────────────────────────
    st.markdown("#### Resumen por Área")

    def _fq(v): return f"Q{v:,.0f}"
    def _fd(v): return "—"

    filas = [
        {"Área": "Campo",               "Ingreso": _fq(campo_it), "Costo Compra": _fd(0),    "Gastos Op": _fq(gas_campo_t), "Margen Neto": _fq(campo_mn)},
        {"Área": "Veggi Río",           "Ingreso": _fq(vrio_it),  "Costo Compra": _fq(vrio_cc),  "Gastos Op": _fq(gas_vrio_t),  "Margen Neto": _fq(vrio_mn)},
        {"Área": "Veggi Antigua",       "Ingreso": _fq(vant_it),  "Costo Compra": _fq(vant_cc),  "Gastos Op": _fq(gas_vant_t),  "Margen Neto": _fq(vant_mn)},
        {"Área": "Veggi Chimaltenango", "Ingreso": _fq(vchim_it), "Costo Compra": _fq(vchim_cc), "Gastos Op": _fq(gas_vchim_t), "Margen Neto": _fq(vchim_mn)},
        {"Área": "── TOTAL Op.",        "Ingreso": _fq(tot_op_it),"Costo Compra": _fq(tot_op_cc),"Gastos Op": _fq(tot_op_gas),  "Margen Neto": _fq(tot_op_mn)},
        {"Área": "",                    "Ingreso": "",             "Costo Compra": "",             "Gastos Op": "",               "Margen Neto": ""},
        {"Área": "Veggi Hogares",       "Ingreso": _fq(vh_it),    "Costo Compra": _fq(vh_cc),     "Gastos Op": _fd(0),           "Margen Neto": _fq(vh_mn)},
        {"Área": "",                    "Ingreso": "",             "Costo Compra": "",             "Gastos Op": "",               "Margen Neto": ""},
        {"Área": "TOTAL GENERAL",       "Ingreso": _fq(tot_gen_it),"Costo Compra":_fq(tot_gen_cc),"Gastos Op": _fq(tot_gen_gas), "Margen Neto": _fq(tot_gen_mn)},
    ]
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
    # Proyección próximas 4 semanas
    if modo == "Semana":
        ult4 = [g["monto"] for g in gastos
                if g["año"]==año and abs(g["semana"]-sem) <= 4
                and g["categoria"] != "Casa"]
        if ult4:
            prom4 = sum(ult4) / 4
            st.info(f"📆 Proyección próxima semana (prom. 4 sem.): **Q{prom4:,.0f}**")
    else:
        meses_idx = [(mes-i-1) % 12 + 1 for i in range(4)]
        años_idx  = [año if mes-i-1 >= 0 else año-1 for i in range(4)]
        tot_ult4  = [sum(g["monto"] for g in gastos
                         if g["mes"]==m and g["año"]==a and g["categoria"]!="Casa")
                     for m, a in zip(meses_idx, años_idx)]
        if any(t > 0 for t in tot_ult4):
            prom4 = sum(tot_ult4) / 4
            st.info(f"📆 Proyección próximo mes (prom. 4 meses): **Q{prom4:,.0f}**")


# ── TAB Casa ─────────────────────────────────────────────────────────────────
def _tab_casa(pedidos: list, cfg: dict):
    st.markdown("#### 🏠 Casa — Gastos Personales")

    hoy     = date.today()
    mes_act = hoy.month
    año_act = hoy.year

    c1, c2 = st.columns(2)
    mes = c1.selectbox("Mes", list(range(1,13)),
                        index=mes_act-1,
                        format_func=lambda m: MESES_ES[m], key="cs_mes")
    año = c2.number_input("Año", 2020, 2030, año_act, key="cs_año")

    gastos   = _leer_gastos()
    budgets  = cfg["budgets"]
    campo_clis = cfg["campo_clis"]

    gas_casa = [g for g in gastos
                if g["mes"]==mes and g["año"]==año and g["categoria"]=="Casa"]
    gas_prev = [g for g in gastos
                if g["mes"]==(mes-1 if mes>1 else 12)
                and g["año"]==(año if mes>1 else año-1)
                and g["categoria"]=="Casa"]

    total_casa = sum(g["monto"] for g in gas_casa)
    total_prev = sum(g["monto"] for g in gas_prev)
    total_ppto = sum(budgets.values())

    # Ganancia operacional del mismo período
    filtro_ped = lambda p: (p["fecha"] and p["fecha"].month==mes
                            and p["fecha"].year==año)
    inc     = _ingresos_campo_veggi(pedidos, campo_clis, filtro_ped)
    gas_op  = [g for g in gastos
               if g["mes"]==mes and g["año"]==año and g["categoria"]!="Casa"]
    gan_op  = sum(inc.values()) - sum(g["monto"] for g in gas_op)
    flujo_neto = gan_op - total_casa

    st.divider()

    # KPIs
    k1, k2, k3 = st.columns(3)
    k1.metric("Ganancia operacional", f"Q{gan_op:,.0f}")
    k2.metric("Gastos Casa", f"Q{total_casa:,.0f}",
               delta=f"Q{total_casa-total_prev:+,.0f} vs mes ant.",
               delta_color="inverse")
    k3.metric("💰 Flujo Neto Familiar", f"Q{flujo_neto:,.0f}",
               delta=f"{'✅ positivo' if flujo_neto>=0 else '⚠️ déficit'}")

    st.divider()

    # Por subcategoría con vs presupuesto
    st.markdown("**Detalle por categoría**")
    subcats_casa = sorted({g["subcat"] for g in gas_casa}
                          | set(budgets.keys()))
    rows_casa = []
    for sub in subcats_casa:
        real  = sum(g["monto"] for g in gas_casa if g["subcat"]==sub)
        ppto  = budgets.get(sub, 0)
        diff  = real - ppto
        if real > 0 or ppto > 0:
            rows_casa.append({
                "SubCategoría": sub,
                "Real": f"Q{real:,.2f}",
                "Presupuesto": f"Q{ppto:,.2f}" if ppto > 0 else "—",
                "Diferencia": (f"✅ Q{abs(diff):,.2f}" if diff <= 0
                               else f"⚠️ +Q{diff:,.2f}"),
            })

    if rows_casa:
        st.dataframe(pd.DataFrame(rows_casa), hide_index=True,
                     use_container_width=True,
                     column_config={
                         "SubCategoría": st.column_config.TextColumn(width="medium"),
                         "Real":         st.column_config.TextColumn(width="small"),
                         "Presupuesto":  st.column_config.TextColumn(width="small"),
                         "Diferencia":   st.column_config.TextColumn(width="medium"),
                     })

    st.divider()
    st.markdown(f"**Total Casa: Q{total_casa:,.2f}** "
                f"· Presupuesto: Q{total_ppto:,.2f} "
                + ("✅" if total_casa <= total_ppto else f"⚠️ +Q{total_casa-total_ppto:,.2f}"))


# ── TAB Historial ────────────────────────────────────────────────────────────
def _tab_historial():
    st.markdown("#### 📋 Historial de Gastos")
    gastos = _leer_gastos()
    if not gastos:
        st.info("Sin gastos registrados aún."); return

    hoy  = date.today()
    c1, c2, c3 = st.columns(3)
    cat_f  = c1.selectbox("Categoría", ["Todas"]+CATS, key="h_cat")
    año_f  = c2.number_input("Año", 2020, 2030, hoy.year, key="h_año")
    mes_f  = c3.selectbox("Mes", [0]+list(range(1,13)),
                           format_func=lambda m: "Todos" if m==0 else MESES_ES[m],
                           key="h_mes")

    filt = [g for g in gastos
            if (cat_f=="Todas" or g["categoria"]==cat_f)
            and g["año"]==año_f
            and (mes_f==0 or g["mes"]==mes_f)]

    if not filt:
        st.info("Sin registros con esos filtros."); return

    total_f = sum(g["monto"] for g in filt)
    st.caption(f"{len(filt)} registro(s) · Total: Q{total_f:,.2f}")

    df = pd.DataFrame([{
        "Fecha":       g["fecha"].strftime("%d/%m/%Y") if g["fecha"] else "",
        "Categoría":   g["categoria"],
        "SubCategoría":g["subcat"],
        "Proveedor":   g["proveedor"],
        "Concepto":    g["concepto"],
        "Monto":       g["monto"],
    } for g in sorted(filt, key=lambda x: x["fecha"] or date.min, reverse=True)])

    st.dataframe(df, hide_index=True, use_container_width=True,
                 column_config={
                     "Fecha":       st.column_config.TextColumn(width="small"),
                     "Categoría":   st.column_config.TextColumn(width="small"),
                     "SubCategoría":st.column_config.TextColumn(width="medium"),
                     "Proveedor":   st.column_config.TextColumn(width="medium"),
                     "Concepto":    st.column_config.TextColumn(width="medium"),
                     "Monto":       st.column_config.NumberColumn(format="Q%.2f", width="small"),
                 })


# ── TAB Categorías ────────────────────────────────────────────────────────────
def _tab_categorias(cfg: dict):
    st.markdown("#### ⚙️ Administrar Categorías y Configuración")

    subcats    = list(cfg["subcats"])
    campo_clis = list(cfg["campo_clis"])
    budgets    = dict(cfg["budgets"])

    # ── Subcategorías ─────────────────────────────────────────────────────────
    st.markdown("**SubCategorías de Gasto**")
    with st.form("form_new_sub"):
        nc1, nc2, nc3 = st.columns([2, 1.5, 1])
        nueva_sub = nc1.text_input("Nueva SubCategoría")
        nueva_cat = nc2.selectbox("Categoría", CATS)
        if nc3.form_submit_button("➕ Agregar"):
            if nueva_sub.strip() and (nueva_sub.strip(), nueva_cat) not in subcats:
                subcats.append((nueva_sub.strip(), nueva_cat))
                budgets.setdefault(nueva_sub.strip(), 0.0)
                _guardar_config(subcats, campo_clis, budgets)
                st.success(f"'{nueva_sub}' agregada a {nueva_cat}")
                st.rerun()

    df_sub = pd.DataFrame([{"SubCategoría": s, "Categoría": c} for s, c in subcats])
    st.dataframe(df_sub, hide_index=True, use_container_width=True,
                 column_config={
                     "SubCategoría": st.column_config.TextColumn(width="medium"),
                     "Categoría":    st.column_config.TextColumn(width="small"),
                 })

    st.divider()

    # ── Clientes Campo ────────────────────────────────────────────────────────
    st.markdown("**Clientes Campo** *(sus pedidos se contabilizan como ingreso Campo)*")
    st.caption("Sus pedidos generan ingresos de Campo (no Veggi). "
               "Wilson y clientes Veggi/Chimalt se manejan automáticamente.")

    # Tabla con botón de eliminar por fila
    if campo_clis:
        for idx_c, cli_c in enumerate(list(campo_clis)):
            row_c1, row_c2 = st.columns([5, 1])
            row_c1.markdown(f"**{cli_c}**")
            if row_c2.button("🗑️", key=f"del_campo_{idx_c}",
                             help=f"Eliminar {cli_c}"):
                campo_clis = [x for x in campo_clis if x != cli_c]
                _guardar_config(subcats, campo_clis, budgets)
                st.success(f"'{cli_c}' eliminado de clientes Campo.")
                st.rerun()
    else:
        st.info("Sin clientes Campo configurados.")

    with st.form("form_new_campo"):
        cc1, cc2 = st.columns([3, 1])
        nuevo_cli = cc1.text_input("Nuevo cliente Campo (en minúsculas)",
                                    placeholder="ej: legume")
        if cc2.form_submit_button("➕ Agregar"):
            cli_norm = nuevo_cli.strip().lower()
            if cli_norm and cli_norm not in campo_clis:
                campo_clis.append(cli_norm)
                _guardar_config(subcats, campo_clis, budgets)
                st.success(f"'{cli_norm}' agregado como cliente Campo")
                st.rerun()
            elif cli_norm in campo_clis:
                st.warning(f"'{cli_norm}' ya existe.")

    st.divider()

    # ── Presupuestos Casa ─────────────────────────────────────────────────────
    st.markdown("**Presupuesto Mensual Casa (Q)**")
    subcats_casa = [s for s, c in subcats if c == "Casa"]
    edited_budgets = {}
    cols_b = st.columns(min(3, len(subcats_casa) or 1))
    for i, sub in enumerate(subcats_casa):
        edited_budgets[sub] = cols_b[i % 3].number_input(
            sub, value=float(budgets.get(sub, 0)),
            min_value=0.0, step=50.0, format="%.2f",
            key=f"bgt_{sub}")

    if st.button("💾 Guardar presupuestos", type="primary", key="save_budgets"):
        budgets.update(edited_budgets)
        _guardar_config(subcats, campo_clis, budgets)
        st.success("✅ Presupuestos guardados")
        st.rerun()


# ── MOSTRAR ───────────────────────────────────────────────────────────────────

def _ensure_gastos_sheets():
    """Crea las hojas Gastos y GastosConfig si no existen en el Sheet."""
    from gsheets import _wb as _get_wb, HOJAS
    try:
        wb = _get_wb()
        existing = [ws.title for ws in wb.worksheets()]
        created = []
        if HOJAS["gastos"] not in existing:
            sheet = wb.add_worksheet(title=HOJAS["gastos"], rows=2000, cols=10)
            sheet.append_row(
                ["Fecha","Semana","Año","Categoria","SubCategoria",
                 "Proveedor","Concepto","Monto"],
                value_input_option="USER_ENTERED")
            created.append(HOJAS["gastos"])
        if HOJAS["gastosconfig"] not in existing:
            sheet2 = wb.add_worksheet(title=HOJAS["gastosconfig"], rows=200, cols=6)
            sheet2.append_row(["Tipo","Val1","Val2","","",""],
                               value_input_option="USER_ENTERED")
            created.append(HOJAS["gastosconfig"])
        if created:
            st.info(f"✅ Hojas creadas automáticamente: {', '.join(created)}")
    except Exception:
        pass  # Las hojas se crearán manualmente si es necesario

def mostrar():
    st.markdown("## 💰 Gastos")
    if st.button("🏠 Inicio", key="btn_home_gto", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    # Crear hojas solo una vez por sesión (evita rate limit 429)
    if not st.session_state.get("_gastos_sheets_ok"):
        try:
            _ensure_gastos_sheets()
            st.session_state["_gastos_sheets_ok"] = True
        except Exception:
            st.session_state["_gastos_sheets_ok"] = True  # no reintentar
    cfg = _cargar_config()

    from excel_helper import leer_pedidos
    pedidos = leer_pedidos()

    t1, t2, t3, t4, t5 = st.tabs([
        "➕ Registrar",
        "📊 Operación",
        "🏠 Casa",
        "📋 Historial",
        "⚙️ Categorías",
    ])
    with t1: _tab_registrar(cfg)
    with t2: _tab_operacion(pedidos, cfg)
    with t3: _tab_casa(pedidos, cfg)
    with t4: _tab_historial()
    with t5: _tab_categorias(cfg)
