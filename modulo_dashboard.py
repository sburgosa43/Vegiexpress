"""
modulo_dashboard.py — Dashboard de Desempeño VeggiExpress
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
from excel_helper import leer_pedidos
from data_helper import cargar_clientes

# ── CONFIGURACIÓN ─────────────────────────────────────────────────────────────
ZONAS_MAP = {
    "Antigua & Chimal": ["L03", "L04"],
    "Guatemala & Santiago": ["L05", "L06"],
    "Rio": ["L01"],   # L02 Monterrico: pendiente definición
}
COLORES_ZONA = {
    "Antigua & Chimal":      "#2D7A2D",
    "Guatemala & Santiago":  "#8DC63F",
    "Rio":                   "#4A4A4A",
}
EXCLUIR = ["veggi", "chimalt"]

def _excluido(nombre: str) -> bool:
    n = nombre.lower()
    return any(x in n for x in EXCLUIR)

def _zona_de(codigo_lugar: str) -> str | None:
    for zona, codigos in ZONAS_MAP.items():
        if codigo_lugar in codigos:
            return zona
    return None

def _build_cli_map(clientes: list) -> dict:
    """nombre_lower → {zona, codigo_lugar, credito, nit}"""
    m = {}
    for c in clientes:
        m[c["nombre"].lower()] = {
            "zona":         _zona_de(c["codigo_lugar"]),
            "codigo_lugar": c["codigo_lugar"],
            "credito":      c["credito"],
            "nit":          c["nit"],
            "nombre":       c["nombre"],
        }
    return m

def _filtrar_semana(todos, semana, año, cli_map):
    result = []
    for p in todos:
        if p["semana"] != semana or p["año"] != año:
            continue
        if p["status"] == "Cancelado":
            continue
        if _excluido(p["cliente"]):
            continue
        info = cli_map.get(p["cliente"].lower(), {})
        zona = info.get("zona")
        if not zona:
            continue
        result.append({**p, "zona": zona})
    return result

def _sem_anterior(semana, año):
    if semana <= 1:
        return 52, año - 1
    return semana - 1, año

def _df(pedidos):
    if not pedidos:
        return pd.DataFrame()
    return pd.DataFrame(pedidos)

# ── WARNING: CLIENTES SIN PEDIDO ──────────────────────────────────────────────
def _warning_sin_pedido(act, ant):
    clis_act = {p["cliente"].lower() for p in act}
    clis_ant = {p["cliente"].lower() for p in ant}
    sin = sorted({p["cliente"] for p in ant if p["cliente"].lower() not in clis_act})
    if not sin:
        return
    lista = "  ·  ".join(f"**{c}**" for c in sin)
    st.warning(
        f"⚠️ {len(sin)} cliente(s) compraron la semana pasada "
        f"pero **aún no tienen pedido esta semana:**\n\n{lista}"
    )

# ── TAB 1: DESEMPEÑO ──────────────────────────────────────────────────────────
def _tab_desempeno(act, ant, sem_act, año_act):

    # ── Metas por zona ────────────────────────────────────────────────────────
    with st.expander("⚙️ Configurar metas semanales (Q)", expanded=False):
        cols = st.columns(len(ZONAS_MAP))
        for col, zona in zip(cols, ZONAS_MAP):
            key = f"meta_{zona}"
            if key not in st.session_state:
                st.session_state[key] = 0.0
            st.session_state[key] = col.number_input(
                zona, min_value=0.0, step=100.0,
                value=float(st.session_state[key]), key=f"inp_{key}")

    if not act and not ant:
        st.info("No hay pedidos para esta semana."); return

    df_act = _df(act)
    df_ant = _df(ant)

    total_act  = df_act["total"].sum()    if not df_act.empty else 0
    total_ant  = df_ant["total"].sum()    if not df_ant.empty else 0
    margen_act = df_act["margen_q"].sum() if not df_act.empty else 0
    margen_ant = df_ant["margen_q"].sum() if not df_ant.empty else 0
    meta_total = sum(st.session_state.get(f"meta_{z}", 0) for z in ZONAS_MAP)

    st.divider()
    st.markdown(f"### Semana {sem_act} · {año_act}")

    # ── KPIs globales ─────────────────────────────────────────────────────────
    k1, k2, k3 = st.columns(3)
    delta_v = f"Q{total_act - total_ant:+,.2f} vs sem anterior"
    delta_m = f"Q{margen_act - margen_ant:+,.2f} vs sem anterior"
    k1.metric("💰 Total Vendido",   f"Q{total_act:,.2f}", delta_v)
    k2.metric("📈 Margen Neto",     f"Q{margen_act:,.2f}", delta_m)
    pct_m = (margen_act / total_act * 100) if total_act else 0
    k3.metric("% Margen Neto",     f"{pct_m:.1f}%")

    # ── Barra de progreso vs meta ─────────────────────────────────────────────
    if meta_total > 0:
        pct = min(total_act / meta_total, 1.0)
        st.markdown(f"**Progreso vs Meta semanal total: Q{meta_total:,.2f}**")
        st.progress(pct, text=f"Q{total_act:,.2f} de Q{meta_total:,.2f} — {pct*100:.1f}%")

    st.divider()

    # ── Métricas y progreso por zona ──────────────────────────────────────────
    st.markdown("#### Por zona")
    for zona in ZONAS_MAP:
        v_act = df_act[df_act["zona"]==zona]["total"].sum()    if not df_act.empty else 0
        v_ant = df_ant[df_ant["zona"]==zona]["total"].sum()    if not df_ant.empty else 0
        m_act = df_act[df_act["zona"]==zona]["margen_q"].sum() if not df_act.empty else 0
        m_ant = df_ant[df_ant["zona"]==zona]["margen_q"].sum() if not df_ant.empty else 0
        meta_z = st.session_state.get(f"meta_{zona}", 0)

        color = COLORES_ZONA[zona]
        st.markdown(
            f"<div style='border-left:4px solid {color};padding:4px 10px;"
            f"margin:4px 0;border-radius:4px'><b>{zona}</b></div>",
            unsafe_allow_html=True)

        zc1, zc2, zc3 = st.columns(3)
        zc1.metric("Venta",  f"Q{v_act:,.2f}", f"Q{v_act-v_ant:+,.2f}")
        zc2.metric("Margen", f"Q{m_act:,.2f}", f"Q{m_act-m_ant:+,.2f}")
        pct_z = (m_act/v_act*100) if v_act else 0
        zc3.metric("% Margen", f"{pct_z:.1f}%")

        if meta_z > 0:
            pz = min(v_act / meta_z, 1.0)
            st.progress(pz, text=f"Q{v_act:,.2f} / Q{meta_z:,.2f} ({pz*100:.1f}%)")

    st.divider()

    # ── Gráficos de shares ────────────────────────────────────────────────────
    if not df_act.empty:
        shares_v = df_act.groupby("zona")["total"].sum().reset_index()
        shares_m = df_act.groupby("zona")["margen_q"].sum().reset_index()

        gc1, gc2 = st.columns(2)
        with gc1:
            st.markdown("**Share Ventas por Zona**")
            fig = px.pie(shares_v, values="total", names="zona", hole=0.45,
                         color="zona", color_discrete_map=COLORES_ZONA)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(showlegend=False, margin=dict(t=20,b=20,l=0,r=0))
            st.plotly_chart(fig, use_container_width=True)
        with gc2:
            st.markdown("**Share Margen Neto por Zona**")
            fig2 = px.pie(shares_m, values="margen_q", names="zona", hole=0.45,
                          color="zona", color_discrete_map=COLORES_ZONA)
            fig2.update_traces(textposition="inside", textinfo="percent+label")
            fig2.update_layout(showlegend=False, margin=dict(t=20,b=20,l=0,r=0))
            st.plotly_chart(fig2, use_container_width=True)

# ── TAB 2: TOP CLIENTES ───────────────────────────────────────────────────────
def _tab_top_clientes(act, ant):
    if not act:
        st.info("No hay pedidos esta semana."); return

    df_act = _df(act)
    df_ant = _df(ant)

    # Agregar por cliente
    def _agg(df):
        if df.empty: return pd.DataFrame(columns=["cliente","zona","venta","margen"])
        g = df.groupby(["cliente","zona"]).agg(
            venta=("total","sum"), margen=("margen_q","sum")).reset_index()
        return g

    agg_act = _agg(df_act)
    agg_ant = _agg(df_ant)

    for zona in ZONAS_MAP:
        color = COLORES_ZONA[zona]
        st.markdown(
            f"<div style='border-left:4px solid {color};padding:4px 10px;"
            f"margin:8px 0 4px 0;border-radius:4px;font-weight:bold'>{zona}</div>",
            unsafe_allow_html=True)

        zona_act = agg_act[agg_act["zona"]==zona].nlargest(3,"venta")
        zona_ant = agg_ant[agg_ant["zona"]==zona].set_index("cliente") \
                   if not agg_ant.empty else pd.DataFrame()

        if zona_act.empty:
            st.caption("Sin pedidos esta semana."); continue

        hdr = st.columns([3, 1.5, 1.5, 1.5, 1.5])
        hdr[0].markdown("**Cliente**"); hdr[1].markdown("**Venta**")
        hdr[2].markdown("**vs Ant.**"); hdr[3].markdown("**Margen**")
        hdr[4].markdown("**% Mg**")

        for _, row in zona_act.iterrows():
            v_ant = zona_ant.loc[row["cliente"],"venta"] \
                    if not zona_ant.empty and row["cliente"] in zona_ant.index else 0
            r = st.columns([3, 1.5, 1.5, 1.5, 1.5])
            r[0].write(row["cliente"])
            r[1].write(f"Q{row['venta']:,.2f}")
            delta = row["venta"] - v_ant
            r[2].write(f"{'▲' if delta>=0 else '▼'} Q{abs(delta):,.2f}")
            r[3].write(f"Q{row['margen']:,.2f}")
            pct = (row["margen"]/row["venta"]*100) if row["venta"] else 0
            r[4].write(f"{pct:.1f}%")

# ── TAB 3: TOP PRODUCTOS ──────────────────────────────────────────────────────
def _tab_top_productos(act):
    if not act:
        st.info("No hay pedidos esta semana."); return

    df = _df(act)
    zona_sel = st.selectbox("Filtrar por zona",
                             ["Todas"] + list(ZONAS_MAP.keys()),
                             key="dash_zona_prod")
    if zona_sel != "Todas":
        df = df[df["zona"] == zona_sel]

    agg = df.groupby("producto").agg(
        unidades=("cantidad","sum"),
        venta=("total","sum"),
        margen=("margen_q","sum")
    ).reset_index()

    st.divider()
    tab_u, tab_v, tab_m = st.tabs(["📦 Unidades", "💰 Q Venta", "📈 Margen Neto"])

    with tab_u:
        top = agg.nlargest(10,"unidades")[["producto","unidades","venta","margen"]]
        top.columns = ["Producto","Unidades","Q Venta","Q Margen"]
        st.dataframe(top.reset_index(drop=True), use_container_width=True, hide_index=True)
        fig = px.bar(top.head(10), x="Producto", y="Unidades",
                     color_discrete_sequence=["#2D7A2D"])
        fig.update_layout(xaxis_tickangle=-35, margin=dict(t=20,b=80))
        st.plotly_chart(fig, use_container_width=True)

    with tab_v:
        top = agg.nlargest(10,"venta")[["producto","unidades","venta","margen"]]
        top.columns = ["Producto","Unidades","Q Venta","Q Margen"]
        st.dataframe(top.reset_index(drop=True), use_container_width=True, hide_index=True)
        fig = px.bar(top.head(10), x="Producto", y="Q Venta",
                     color_discrete_sequence=["#8DC63F"])
        fig.update_layout(xaxis_tickangle=-35, margin=dict(t=20,b=80))
        st.plotly_chart(fig, use_container_width=True)

    with tab_m:
        top = agg.nlargest(10,"margen")[["producto","unidades","venta","margen"]]
        top.columns = ["Producto","Unidades","Q Venta","Q Margen"]
        st.dataframe(top.reset_index(drop=True), use_container_width=True, hide_index=True)
        fig = px.bar(top.head(10), x="Producto", y="Q Margen",
                     color_discrete_sequence=["#4A4A4A"])
        fig.update_layout(xaxis_tickangle=-35, margin=dict(t=20,b=80))
        st.plotly_chart(fig, use_container_width=True)

# ── TAB 4: CRÉDITOS PENDIENTES ────────────────────────────────────────────────
def _tab_creditos(todos, clientes):
    hoy  = date.today()
    cli_map = {c["nombre"].lower(): c for c in clientes}

    # Agrupar pedidos por cliente: sumar totales con vencimiento pasado
    vencidos: dict = {}
    for p in todos:
        if p["status"] == "Cancelado": continue
        if _excluido(p["cliente"]):    continue
        fv = p.get("fecha_venc")
        if not fv or fv >= hoy:        continue   # no vencido

        cli = p["cliente"]
        if cli not in vencidos:
            vencidos[cli] = {"monto": 0, "fecha_venc": fv, "dias": 0}
        vencidos[cli]["monto"] += p["total"] or 0
        if fv < vencidos[cli]["fecha_venc"]:
            vencidos[cli]["fecha_venc"] = fv

    if not vencidos:
        st.success("✅ No hay créditos vencidos actualmente.")
        return

    st.warning(f"⚠️ {len(vencidos)} cliente(s) con crédito vencido")

    rows = []
    for cli, info in sorted(vencidos.items(), key=lambda x: x[1]["fecha_venc"]):
        dias = (hoy - info["fecha_venc"]).days
        cli_info = cli_map.get(cli.lower(), {})
        rows.append({
            "Cliente":      cli,
            "NIT":          cli_info.get("nit","—"),
            "Venc.":        info["fecha_venc"].strftime("%d/%m/%Y"),
            "Días vencido": dias,
            "Monto (Q)":    f"Q{info['monto']:,.2f}",
        })

    df = pd.DataFrame(rows).sort_values("Días vencido", ascending=False)
    st.dataframe(df.reset_index(drop=True), use_container_width=True, hide_index=True)

# ── TAB 5: CRM CLIENTES ───────────────────────────────────────────────────────
def _tab_crm(todos, clientes, cli_map_zona, sem_act, año_act):
    hoy = date.today()

    # Construir historial por cliente
    hist: dict = {}
    for p in todos:
        if _excluido(p["cliente"]): continue
        cli = p["cliente"]
        if cli not in hist:
            hist[cli] = {"pedidos": [], "total": 0, "margen": 0, "prods": {}}
        hist[cli]["pedidos"].append(p)
        hist[cli]["total"]  += p["total"] or 0
        hist[cli]["margen"] += p["margen_q"] or 0
        prod = p["producto"]
        hist[cli]["prods"][prod] = hist[cli]["prods"].get(prod, 0) + (p["cantidad"] or 0)

    def _status(pedidos_cli):
        semanas = [p["semana"] for p in pedidos_cli
                   if p["año"] == año_act and p["semana"]]
        if not semanas: return "⚫ Inactivo"
        max_sem = max(semanas)
        diff = sem_act - max_sem
        if diff <= 0:  return "🟢 Activo"
        if diff <= 2:  return "🟡 En Riesgo"
        return "🔴 Inactivo"

    # Construir tabla CRM
    filas = []
    for c in clientes:
        if _excluido(c["nombre"]): continue
        info = hist.get(c["nombre"], {"pedidos":[],"total":0,"margen":0,"prods":{}})
        pedidos = info["pedidos"]
        if not pedidos: continue   # nunca ha comprado

        # Semanas únicas con pedidos
        sems_unicas = sorted({(p["año"], p["semana"]) for p in pedidos
                               if p["semana"]}, reverse=True)
        ultima_sem = sems_unicas[0][1] if sems_unicas else 0
        ultimo_año = sems_unicas[0][0] if sems_unicas else 0
        n_sems     = len(sems_unicas)
        ticket_avg = info["total"] / n_sems if n_sems else 0
        top_prod   = max(info["prods"], key=info["prods"].get) if info["prods"] else "—"
        zona       = _zona_de(c["codigo_lugar"]) or "—"
        status     = _status(pedidos)

        filas.append({
            "Estado":       status,
            "Cliente":      c["nombre"],
            "Zona":         zona,
            "Última Sem.":  f"Sem {ultima_sem}/{ultimo_año}" if ultima_sem else "—",
            "Sem. compradas": n_sems,
            "Ticket Prom.": f"Q{ticket_avg:,.2f}",
            "Total Hist.":  f"Q{info['total']:,.2f}",
            "Margen Hist.": f"Q{info['margen']:,.2f}",
            "Top Producto": top_prod,
        })

    if not filas:
        st.info("No hay datos de clientes."); return

    df_crm = pd.DataFrame(filas)

    # Filtros
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        f_zona = st.selectbox("Zona", ["Todas"] + list(ZONAS_MAP.keys()), key="crm_zona")
    with fc2:
        f_est  = st.selectbox("Estado", ["Todos","🟢 Activo","🟡 En Riesgo","🔴 Inactivo"], key="crm_est")
    with fc3:
        f_bus  = st.text_input("Buscar cliente", placeholder="Nombre...", key="crm_bus")

    if f_zona != "Todas": df_crm = df_crm[df_crm["Zona"] == f_zona]
    if f_est  != "Todos": df_crm = df_crm[df_crm["Estado"] == f_est]
    if f_bus:             df_crm = df_crm[df_crm["Cliente"].str.lower().str.contains(f_bus.lower())]

    st.markdown(f"**{len(df_crm)} clientes**")
    st.dataframe(df_crm.reset_index(drop=True), use_container_width=True, hide_index=True)

    # Detalle de cliente
    st.divider()
    cli_sel = st.selectbox("Ver detalle de cliente",
                            [""] + list(df_crm["Cliente"]), key="crm_det")
    if cli_sel and cli_sel in hist:
        info    = hist[cli_sel]
        pedidos = info["pedidos"]
        cli_obj = next((c for c in clientes if c["nombre"] == cli_sel), {})

        st.markdown(f"#### 👤 {cli_sel}")
        dc1, dc2, dc3, dc4 = st.columns(4)
        dc1.metric("Total histórico",  f"Q{info['total']:,.2f}")
        dc2.metric("Margen histórico", f"Q{info['margen']:,.2f}")
        sems_u = {(p["año"],p["semana"]) for p in pedidos if p["semana"]}
        dc3.metric("Semanas compradas", len(sems_u))
        dc4.metric("Crédito", f"{cli_obj.get('credito',0)} días")

        # Top 5 productos
        top5 = sorted(info["prods"].items(), key=lambda x: x[1], reverse=True)[:5]
        st.markdown("**Top 5 productos:**")
        for prod, cant in top5:
            st.caption(f"• {prod}: {cant:.1f} unidades")

        # Últimas 8 semanas
        sems_ord = sorted(sems_u, reverse=True)[:8]
        sem_data = []
        for (a, s) in sorted(sems_ord):
            v = sum(p["total"] or 0 for p in pedidos
                    if p["año"]==a and p["semana"]==s)
            sem_data.append({"Semana": f"Sem {s}/{a}", "Venta": v})
        if sem_data:
            df_hist = pd.DataFrame(sem_data)
            fig = px.bar(df_hist, x="Semana", y="Venta",
                         color_discrete_sequence=["#2D7A2D"],
                         title="Ventas últimas semanas")
            fig.update_layout(margin=dict(t=40,b=40))
            st.plotly_chart(fig, use_container_width=True)

# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def mostrar():
    st.markdown("## 📊 Dashboard — Desempeño VeggiExpress")

    with st.spinner("Cargando datos..."):
        todos    = leer_pedidos()
        clientes = cargar_clientes()

    cli_map_zona = _build_cli_map(clientes)

    hoy     = date.today()
    sem_act = hoy.isocalendar()[1]
    año_act = hoy.year
    sem_ant, año_ant = _sem_anterior(sem_act, año_act)

    pedidos_act = _filtrar_semana(todos, sem_act, año_act, cli_map_zona)
    pedidos_ant = _filtrar_semana(todos, sem_ant, año_ant, cli_map_zona)

    # ── Warning clientes sin pedido ───────────────────────────────────────────
    _warning_sin_pedido(pedidos_act, pedidos_ant)

    # ── Tabs ──────────────────────────────────────────────────────────────────
    t1, t2, t3, t4, t5 = st.tabs([
        "📈 Desempeño Actual",
        "🏆 Top Clientes",
        "📦 Top Productos",
        "💳 Créditos Pendientes",
        "👤 CRM Clientes",
    ])

    with t1: _tab_desempeno(pedidos_act, pedidos_ant, sem_act, año_act)
    with t2: _tab_top_clientes(pedidos_act, pedidos_ant)
    with t3: _tab_top_productos(pedidos_act)
    with t4: _tab_creditos(todos, clientes)
    with t5: _tab_crm(todos, clientes, cli_map_zona, sem_act, año_act)
