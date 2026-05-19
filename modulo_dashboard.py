"""
modulo_dashboard.py — Dashboard de Desempeño VeggiExpress
Períodos: Sem Actual | Sem Anterior | MTD | YTD | PYTD
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
from excel_helper import leer_pedidos
from data_helper import cargar_clientes

# ── CONFIGURACIÓN ─────────────────────────────────────────────────────────────
ZONAS_MAP = {
    "Antigua & Chimal":     ["L03", "L04"],
    "Guatemala & Santiago": ["L05", "L06"],
    "Rio":                  ["L01"],
}
COLORES_ZONA = {
    "Antigua & Chimal":     "#2D7A2D",
    "Guatemala & Santiago": "#8DC63F",
    "Rio":                  "#4A4A4A",
}
COLORES_PERIODO = {
    "Sem Actual":  "#2D7A2D",
    "Sem Ant.":    "#8DC63F",
    "MTD":         "#4A9E4A",
    "YTD":         "#1A5C1A",
    "PYTD":        "#AAAAAA",
}
EXCLUIR = ["veggi", "chimalt", "wilson"]


# ── HELPERS ───────────────────────────────────────────────────────────────────
def _excluido(nombre): return any(x in nombre.lower() for x in EXCLUIR)

def _zona_de(codigo):
    for z, cs in ZONAS_MAP.items():
        if codigo in cs: return z
    return None

def _build_cli_map(clientes):
    return {c["nombre"].lower(): {
        "zona": _zona_de(c["codigo_lugar"]),
        "codigo_lugar": c["codigo_lugar"],
        "credito": c["credito"], "nit": c["nit"], "nombre": c["nombre"],
    } for c in clientes}

def _periodos(hoy=None):
    hoy = hoy or date.today()
    año = hoy.year; sem = hoy.isocalendar()[1]; mes = hoy.month

    sem_ant_n = sem - 1; sem_ant_a = año
    if sem_ant_n < 1: sem_ant_n = 52; sem_ant_a -= 1

    # PYTD: 1 ene año anterior → mismo día del año anterior
    # Ej: hoy 18 may 2026 → PYTD = 1 ene 2025 → 18 may 2025
    try:
        mismo_dia_py = date(año - 1, hoy.month, hoy.day)
    except ValueError:
        mismo_dia_py = date(año - 1, hoy.month, 28)

    return {
        "Sem Actual":  lambda p: p["semana"]==sem and p["año"]==año,
        "Sem Ant.":    lambda p: p["semana"]==sem_ant_n and p["año"]==sem_ant_a,
        "MTD":         lambda p: p["año"]==año and p["fecha"] and p["fecha"].month==mes,
        "YTD":         lambda p: p["año"]==año and p["fecha"] and p["fecha"]<=hoy,
        "PYTD":        lambda p: p["año"]==año-1 and p["fecha"] and p["fecha"]<=mismo_dia_py,
    }

def _filtrar(todos, fn_periodo, cli_map, excl_zona=None):
    """Filtra pedidos por período, excluye cancelados y clientes excluidos."""
    result = []
    for p in todos:
        if p["status"] == "Cancelado": continue
        if _excluido(p["cliente"]):    continue
        if not fn_periodo(p):          continue
        info = cli_map.get(p["cliente"].lower(), {})
        zona = info.get("zona")
        if not zona: continue
        if excl_zona and zona != excl_zona: continue
        result.append({**p, "zona": zona})
    return result

def _agg_periodo(todos, periodos, cli_map, campo="total"):
    """Agrega un campo por período → dict{período: valor_total}"""
    return {nombre: sum(p[campo] or 0 for p in _filtrar(todos, fn, cli_map))
            for nombre, fn in periodos.items()}

def _agg_grupo(todos, periodos, cli_map, by="cliente",
               campo="total", zona_filter=None):
    """
    Agrega campo por grupo (cliente o producto) para cada período.
    Para productos: agrega por (producto, zona) para evitar mezcla de zonas.
    zona_filter: si se indica, solo incluye pedidos de esa zona.
    """
    result = {}
    for nombre_p, fn in periodos.items():
        pedidos = _filtrar(todos, fn, cli_map,
                           excl_zona=zona_filter if zona_filter else None)
        for p in pedidos:
            if by == "producto":
                # Clave compuesta para separar el mismo producto por zona
                key = (p[by], p["zona"])
            else:
                key = p[by]
            if key not in result:
                result[key] = {k: 0 for k in periodos}
                result[key]["zona"]     = p["zona"]
                result[key]["_nombre"]  = p[by]
            result[key][nombre_p] += p[campo] or 0
    return result


# ── WARNING CLIENTES SIN PEDIDO ───────────────────────────────────────────────
def _warning_sin_pedido(todos, cli_map, periodos):
    act_clis = {p["cliente"].lower() for p in _filtrar(todos, periodos["Sem Actual"], cli_map)}
    ant_clis = {p["cliente"]         for p in _filtrar(todos, periodos["Sem Ant."],   cli_map)}
    sin = sorted({c for c in ant_clis if c.lower() not in act_clis})
    if sin:
        st.warning(
            f"⚠️ **{len(sin)} cliente(s) compraron la semana pasada pero aún no "
            f"tienen pedido esta semana:**\n\n" + "  ·  ".join(f"**{c}**" for c in sin))


# ── TAB 1: DESEMPEÑO ──────────────────────────────────────────────────────────
def _tab_desempeno(todos, cli_map, periodos):

    # Metas
    with st.expander("⚙️ Metas semanales por zona (Q)", expanded=False):
        cols = st.columns(len(ZONAS_MAP))
        for col, zona in zip(cols, ZONAS_MAP):
            k = f"meta_{zona}"
            if k not in st.session_state: st.session_state[k] = 0.0
            st.session_state[k] = col.number_input(
                zona, min_value=0.0, step=100.0,
                value=float(st.session_state[k]), key=f"inp_{k}")

    # KPIs globales
    agg_v = _agg_periodo(todos, periodos, cli_map, "total")
    agg_m = _agg_periodo(todos, periodos, cli_map, "margen_q")

    st.divider()
    k1, k2, k3 = st.columns(3)
    delta_v = agg_v["Sem Actual"] - agg_v["Sem Ant."]
    delta_m = agg_m["Sem Actual"] - agg_m["Sem Ant."]
    k1.metric("💰 Venta Sem Actual",  f"Q{agg_v['Sem Actual']:,.2f}",
              f"Q{delta_v:+,.2f} vs sem ant.")
    k2.metric("📈 Margen Sem Actual", f"Q{agg_m['Sem Actual']:,.2f}",
              f"Q{delta_m:+,.2f} vs sem ant.")
    pct = (agg_m["Sem Actual"]/agg_v["Sem Actual"]*100) if agg_v["Sem Actual"] else 0
    k3.metric("% Margen",             f"{pct:.1f}%")

    # Progreso vs meta
    meta_total = sum(st.session_state.get(f"meta_{z}", 0) for z in ZONAS_MAP)
    if meta_total > 0:
        pct_m = min(agg_v["Sem Actual"] / meta_total, 1.0)
        st.progress(pct_m, text=f"Q{agg_v['Sem Actual']:,.2f} de Q{meta_total:,.2f} "
                                 f"({pct_m*100:.1f}%)")
    st.divider()

    # ── Gráfico agrupado: zonas × períodos ───────────────────────────────────
    st.markdown("#### Ventas por Zona y Período")
    metric_sel = st.radio("Métrica", ["Q Venta", "Q Margen Neto"],
                           horizontal=True, key="desemp_metric")
    campo = "total" if metric_sel == "Q Venta" else "margen_q"

    rows = []
    for zona in ZONAS_MAP:
        for per_name, fn in periodos.items():
            val = sum(p[campo] or 0 for p in _filtrar(todos, fn, cli_map, excl_zona=zona))
            rows.append({"Zona": zona, "Período": per_name, "Valor": val})

    df_chart = pd.DataFrame(rows)
    fig = px.bar(df_chart, x="Zona", y="Valor", color="Período",
                 barmode="group",
                 color_discrete_map=COLORES_PERIODO,
                 text_auto=".2s")
    fig.update_traces(textposition="outside")
    fig.update_layout(yaxis_title="Q", legend_title="Período",
                       margin=dict(t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # Tabla resumen + progreso por zona
    st.divider()
    st.markdown("#### Detalle por zona")
    for zona in ZONAS_MAP:
        color  = COLORES_ZONA[zona]
        vals   = {per: sum(p["total"] or 0
                           for p in _filtrar(todos, fn, cli_map, excl_zona=zona))
                  for per, fn in periodos.items()}
        meta_z = st.session_state.get(f"meta_{zona}", 0)

        # Nombre de zona
        st.markdown(
            f"<div style='border-left:4px solid {color};padding:3px 10px;"
            f"margin:6px 0 2px 0;border-radius:4px;font-size:.85rem;"
            f"font-weight:bold'>{zona}</div>",
            unsafe_allow_html=True)

        # Métricas compactas en HTML
        items_html = "".join(
            f"<div style='text-align:center;min-width:90px;flex:1'>"
            f"<div style='font-size:.65rem;color:#888;margin-bottom:2px'>{per}</div>"
            f"<div style='font-size:.8rem;font-weight:bold;color:#2D2D2D'>"
            f"Q{val:,.0f}</div></div>"
            for per, val in vals.items()
        )
        st.markdown(
            f"<div style='display:flex;gap:4px;flex-wrap:wrap;"
            f"background:#f9f9f9;border-radius:6px;padding:6px 4px;"
            f"margin-bottom:4px'>{items_html}</div>",
            unsafe_allow_html=True)

        if meta_z > 0:
            pz = min(vals["Sem Actual"] / meta_z, 1.0)
            st.progress(pz,
                text=f"Q{vals['Sem Actual']:,.0f} / Meta Q{meta_z:,.0f} "
                     f"({pz*100:.1f}%)")


# ── TAB 2: TOP CLIENTES ───────────────────────────────────────────────────────
def _tab_top_clientes(todos, cli_map, periodos):
    metric = st.radio("Ordenar por", ["Q Venta", "Q Margen Neto"],
                       horizontal=True, key="topcli_metric")
    campo = "total" if metric == "Q Venta" else "margen_q"

    agg = _agg_grupo(todos, periodos, cli_map, by="cliente", campo=campo)
    if not agg:
        st.info("Sin datos."); return

    df_all = pd.DataFrame([
        {"cliente": v["_nombre"], "zona": v["zona"],
         **{p: v[p] for p in periodos}}
        for v in agg.values()
    ])

    for zona in ZONAS_MAP:
        color = COLORES_ZONA[zona]
        st.markdown(
            f"<div style='border-left:4px solid {color};padding:4px 10px;"
            f"margin:8px 0 4px 0;border-radius:4px;font-weight:bold'>{zona}</div>",
            unsafe_allow_html=True)

        top_n = 5 if zona in ("Antigua & Chimal", "Rio") else 3
        df_z = df_all[df_all["zona"]==zona].nlargest(top_n, "YTD")
        if df_z.empty:
            st.caption("Sin pedidos."); continue

        # Tabla
        cols_show = ["cliente"] + list(periodos.keys())
        df_show = df_z[cols_show].copy()
        df_show.columns = ["Cliente"] + list(periodos.keys())
        for col in periodos.keys():
            df_show[col] = df_show[col].apply(lambda x: f"Q{x:,.2f}")
        st.dataframe(df_show.reset_index(drop=True),
                     use_container_width=True, hide_index=True)

        # Gráfico barras agrupadas: cliente × período
        rows_g = []
        for _, row in df_z.iterrows():
            for per in periodos:
                rows_g.append({"Cliente": row["cliente"],
                                "Período": per, "Valor": row[per]})
        fig = px.bar(pd.DataFrame(rows_g), x="Cliente", y="Valor",
                     color="Período", barmode="group",
                     color_discrete_map=COLORES_PERIODO, text_auto=".2s")
        fig.update_traces(textposition="outside")
        fig.update_layout(margin=dict(t=10, b=10), showlegend=True)
        st.plotly_chart(fig, use_container_width=True)


# ── TAB 3: TOP PRODUCTOS ──────────────────────────────────────────────────────
def _tab_top_productos(todos, cli_map, periodos):
    c1, c2 = st.columns(2)
    with c1:
        metric = st.radio("Ordenar por",
                           ["Q Venta", "Q Margen Neto", "Unidades"],
                           horizontal=True, key="topprod_metric")
    with c2:
        zona_f = st.selectbox("Zona", ["Todas"] + list(ZONAS_MAP.keys()), key="topprod_zona")

    campo = {"Q Venta": "total", "Q Margen Neto": "margen_q", "Unidades": "cantidad"}[metric]

    agg = _agg_grupo(todos, periodos, cli_map, by="producto", campo=campo,
                     zona_filter=zona_f if zona_f != "Todas" else None)
    if not agg:
        st.info("Sin datos."); return

    df_all = pd.DataFrame([
        {"producto": v["_nombre"], "zona": v["zona"],
         **{p: v[p] for p in periodos}}
        for v in agg.values()
    ])

    df_top = df_all.nlargest(10, "YTD")

    # Tabla Top 10
    cols_show = ["producto"] + list(periodos.keys())
    df_show = df_top[cols_show].copy()
    df_show.columns = ["Producto"] + list(periodos.keys())
    fmt = "Q{:,.2f}" if metric != "Unidades" else "{:,.1f}"
    for col in periodos.keys():
        df_show[col] = df_show[col].apply(
            lambda x: f"Q{x:,.2f}" if metric != "Unidades" else f"{x:,.1f}")
    st.dataframe(df_show.reset_index(drop=True),
                 use_container_width=True, hide_index=True)

    # Gráfico Top 5
    st.markdown("**Gráfico Top 5 por período**")
    df_t5 = df_top.head(5)
    rows_g = []
    for _, row in df_t5.iterrows():
        for per in periodos:
            rows_g.append({"Producto": row["producto"][:20],
                            "Período": per, "Valor": row[per]})
    fig = px.bar(pd.DataFrame(rows_g), x="Producto", y="Valor",
                 color="Período", barmode="group",
                 color_discrete_map=COLORES_PERIODO, text_auto=".2s")
    fig.update_traces(textposition="outside")
    fig.update_layout(xaxis_tickangle=-30, margin=dict(t=10, b=60))
    st.plotly_chart(fig, use_container_width=True)


# ── TAB 4: CRÉDITOS ───────────────────────────────────────────────────────────
def _tab_creditos(todos, clientes):
    hoy = date.today()
    cli_map2 = {c["nombre"].lower(): c for c in clientes}
    vencidos: dict = {}
    for p in todos:
        if p["status"] == "Cancelado" or _excluido(p["cliente"]): continue
        fv = p.get("fecha_venc")
        if not fv or fv >= hoy: continue
        cli = p["cliente"]
        if cli not in vencidos:
            vencidos[cli] = {"monto": 0, "fecha_venc": fv}
        vencidos[cli]["monto"] += p["total"] or 0
        if fv < vencidos[cli]["fecha_venc"]:
            vencidos[cli]["fecha_venc"] = fv

    if not vencidos:
        st.success("✅ No hay créditos vencidos."); return

    st.warning(f"⚠️ {len(vencidos)} cliente(s) con crédito vencido")
    rows = []
    for cli, info in sorted(vencidos.items(), key=lambda x: x[1]["fecha_venc"]):
        ci = cli_map2.get(cli.lower(), {})
        rows.append({"Cliente": cli, "NIT": ci.get("nit","—"),
                     "Venc.": info["fecha_venc"].strftime("%d/%m/%Y"),
                     "Días vencido": (hoy - info["fecha_venc"]).days,
                     "Monto (Q)": f"Q{info['monto']:,.2f}"})
    df = pd.DataFrame(rows).sort_values("Días vencido", ascending=False)
    st.dataframe(df.reset_index(drop=True), use_container_width=True, hide_index=True)


# ── TAB 5: CRM ────────────────────────────────────────────────────────────────
def _tab_crm(todos, clientes, cli_map_zona, sem_act, año_act):
    hist: dict = {}
    for p in todos:
        if _excluido(p["cliente"]): continue
        cli = p["cliente"]
        if cli not in hist:
            hist[cli] = {"pedidos":[], "total":0, "margen":0, "prods":{}}
        hist[cli]["pedidos"].append(p)
        hist[cli]["total"]  += p["total"]   or 0
        hist[cli]["margen"] += p["margen_q"] or 0
        prod = p["producto"]
        hist[cli]["prods"][prod] = hist[cli]["prods"].get(prod,0) + (p["cantidad"] or 0)

    def _status(pedidos_cli):
        sems = [p["semana"] for p in pedidos_cli if p["año"]==año_act and p["semana"]]
        if not sems: return "🔴 Inactivo"
        diff = sem_act - max(sems)
        if diff <= 0: return "🟢 Activo"
        if diff <= 2: return "🟡 En Riesgo"
        return "🔴 Inactivo"

    filas = []
    for c in clientes:
        if _excluido(c["nombre"]): continue
        info = hist.get(c["nombre"])
        if not info: continue
        pedidos = info["pedidos"]
        sems = sorted({(p["año"],p["semana"]) for p in pedidos if p["semana"]}, reverse=True)
        n_sems = len(sems)
        ticket_avg = info["total"]/n_sems if n_sems else 0
        top_prod = max(info["prods"], key=info["prods"].get) if info["prods"] else "—"
        zona = _zona_de(c["codigo_lugar"]) or "—"
        filas.append({
            "Estado": _status(pedidos), "Cliente": c["nombre"], "Zona": zona,
            "Última Sem": f"Sem {sems[0][1]}/{sems[0][0]}" if sems else "—",
            "Sem. activas": n_sems,
            "Ticket Prom.": f"Q{ticket_avg:,.2f}",
            "Total Hist.": f"Q{info['total']:,.2f}",
            "Margen Hist.": f"Q{info['margen']:,.2f}",
            "Top Producto": top_prod,
        })

    if not filas: st.info("Sin datos."); return
    df_crm = pd.DataFrame(filas)

    fc1, fc2, fc3 = st.columns(3)
    with fc1: f_zona = st.selectbox("Zona", ["Todas"]+list(ZONAS_MAP.keys()), key="crm_z")
    with fc2: f_est  = st.selectbox("Estado", ["Todos","🟢 Activo","🟡 En Riesgo","🔴 Inactivo"], key="crm_e")
    with fc3: f_bus  = st.text_input("Buscar", placeholder="Nombre...", key="crm_b")

    if f_zona != "Todas": df_crm = df_crm[df_crm["Zona"]==f_zona]
    if f_est  != "Todos": df_crm = df_crm[df_crm["Estado"]==f_est]
    if f_bus:             df_crm = df_crm[df_crm["Cliente"].str.lower().str.contains(f_bus.lower())]

    st.markdown(f"**{len(df_crm)} clientes**")
    st.dataframe(df_crm.reset_index(drop=True), use_container_width=True, hide_index=True)

    st.divider()
    cli_sel = st.selectbox("Ver detalle", [""]+list(df_crm["Cliente"]), key="crm_d")
    if cli_sel and cli_sel in hist:
        info = hist[cli_sel]
        cli_obj = next((c for c in clientes if c["nombre"]==cli_sel), {})
        st.markdown(f"#### 👤 {cli_sel}")
        dc1,dc2,dc3,dc4 = st.columns(4)
        dc1.metric("Total hist.", f"Q{info['total']:,.2f}")
        dc2.metric("Margen hist.", f"Q{info['margen']:,.2f}")
        sems_u = {(p["año"],p["semana"]) for p in info["pedidos"] if p["semana"]}
        dc3.metric("Sem. activas", len(sems_u))
        dc4.metric("Crédito", f"{cli_obj.get('credito',0)} días")
        top5 = sorted(info["prods"].items(), key=lambda x: x[1], reverse=True)[:5]
        st.markdown("**Top 5 productos:**")
        for prod, cant in top5:
            st.caption(f"• {prod}: {cant:.1f} uds")
        sems_ord = sorted(sems_u)[-8:]
        sem_data = [{"Semana": f"S{s}/{a}",
                     "Venta": sum(p["total"] or 0 for p in info["pedidos"]
                                  if p["año"]==a and p["semana"]==s)}
                    for a,s in sems_ord]
        if sem_data:
            fig = px.bar(pd.DataFrame(sem_data), x="Semana", y="Venta",
                         color_discrete_sequence=["#2D7A2D"],
                         title="Ventas últimas semanas")
            fig.update_layout(margin=dict(t=40,b=20))
            st.plotly_chart(fig, use_container_width=True)


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def mostrar():
    st.markdown("## 📊 Dashboard — VeggiExpress")

    with st.spinner("Cargando datos..."):
        todos    = leer_pedidos()
        clientes = cargar_clientes()

    cli_map = _build_cli_map(clientes)
    hoy     = date.today()
    sem_act = hoy.isocalendar()[1]
    año_act = hoy.year
    periodos = _periodos(hoy)

    _warning_sin_pedido(todos, cli_map, periodos)

    t1, t2, t3, t4, t5 = st.tabs([
        "📈 Desempeño Actual",
        "🏆 Top Clientes",
        "📦 Top Productos",
        "💳 Créditos Pendientes",
        "👤 CRM Clientes",
    ])
    with t1: _tab_desempeno(todos, cli_map, periodos)
    with t2: _tab_top_clientes(todos, cli_map, periodos)
    with t3: _tab_top_productos(todos, cli_map, periodos)
    with t4: _tab_creditos(todos, clientes)
    with t5: _tab_crm(todos, clientes, cli_map, sem_act, año_act)
