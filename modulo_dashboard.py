"""
modulo_dashboard.py — Dashboard VeggiExpress
Períodos: Sem Actual | Sem Ant. | MTD | YTD | PYTD
"""
import streamlit as st
import pandas as pd
import plotly.express as px
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
    "Sem Actual": "#2D7A2D",
    "Sem Ant.":   "#8DC63F",
    "MTD":        "#4A9E4A",
    "YTD":        "#1A5C1A",
    "PYTD":       "#AAAAAA",
}
PERIODOS_CORTO = ["Sem Actual", "Sem Ant.", "MTD"]
PERIODOS_LARGO = ["YTD", "PYTD"]
EXCLUIR = ["veggi", "chimalt", "wilson"]


# ── HELPERS ───────────────────────────────────────────────────────────────────
def _excluido(n): return any(x in n.lower() for x in EXCLUIR)
def _zona_de(cod):
    for z, cs in ZONAS_MAP.items():
        if cod in cs: return z
    return None

def _build_cli_map(clientes):
    return {c["nombre"].lower(): {
        "zona": _zona_de(c["codigo_lugar"]),
        "credito": c["credito"], "nit": c["nit"], "nombre": c["nombre"],
    } for c in clientes}

def _periodos(hoy):
    año = hoy.year; sem = hoy.isocalendar()[1]; mes = hoy.month
    sant_n = sem - 1; sant_a = año
    if sant_n < 1: sant_n = 52; sant_a -= 1
    try:    mdp = date(año-1, hoy.month, hoy.day)
    except: mdp = date(año-1, hoy.month, 28)
    return {
        "Sem Actual": lambda p: p["semana"]==sem  and p["año"]==año,
        "Sem Ant.":   lambda p: p["semana"]==sant_n and p["año"]==sant_a,
        "MTD":        lambda p: p["año"]==año and p["fecha"] and p["fecha"].month==mes,
        "YTD":        lambda p: p["año"]==año and p["fecha"] and p["fecha"]<=hoy,
        "PYTD":       lambda p: p["año"]==año-1 and p["fecha"] and p["fecha"]<=mdp,
    }

def _filtrar(todos, fn, cli_map, zona_only=None):
    r = []
    for p in todos:
        if p["status"]=="Cancelado" or _excluido(p["cliente"]): continue
        if not fn(p): continue
        info = cli_map.get(p["cliente"].lower(), {})
        zona = info.get("zona")
        if not zona: continue
        if zona_only and zona != zona_only: continue
        r.append({**p, "zona": zona})
    return r

def _agg_grupo(todos, periodos, cli_map, by="cliente", campo="total", zona_only=None):
    result = {}
    for pnm, fn in periodos.items():
        for p in _filtrar(todos, fn, cli_map, zona_only):
            key = (p[by], p["zona"]) if by=="producto" else p[by]
            if key not in result:
                result[key] = {k: 0 for k in periodos}
                result[key]["zona"]    = p["zona"]
                result[key]["_nombre"] = p[by]
            result[key][pnm] += p[campo] or 0
    return result


# ── COMPONENTES REUTILIZABLES ─────────────────────────────────────────────────
def _html_compacto(filas: list) -> str:
    """
    Genera tabla HTML compacta.
    filas = [{"label": str, "vals": {periodo: valor}, "color": str}]
    """
    html = "<div style='font-size:.78rem'>"
    for fila in filas:
        items = "".join(
            f"<div style='text-align:center;flex:1;min-width:75px'>"
            f"<div style='font-size:.62rem;color:#888;margin-bottom:1px'>{per}</div>"
            f"<div style='font-weight:bold;color:#2D2D2D'>Q{val:,.0f}</div></div>"
            for per, val in fila["vals"].items()
        )
        color_val = fila["color"]
        label_val = fila["label"]
        html += (
            f"<div style='margin:3px 0'>"
            f"<span style='font-size:.7rem;font-weight:bold;"
            f"color:{color_val}'>{label_val}</span>"
            f"<div style='display:flex;gap:3px;flex-wrap:wrap;background:#f5f5f5;"
            f"border-radius:5px;padding:5px 4px;margin-top:2px'>{items}</div></div>"
        )
    html += "</div>"
    return html

def _dos_graficos(df_rows, x_col, titulo_corto, titulo_largo):
    """Renderiza dos gráficos: corto plazo y largo plazo."""
    df = pd.DataFrame(df_rows)
    if df.empty: return

    gc, gl = st.columns(2)
    for col_g, periodos_sel, titulo in [
        (gc, PERIODOS_CORTO, titulo_corto),
        (gl, PERIODOS_LARGO, titulo_largo),
    ]:
        df_sel = df[df["Período"].isin(periodos_sel)]
        if df_sel.empty:
            col_g.caption(f"Sin datos — {titulo}"); continue
        fig = px.bar(df_sel, x=x_col, y="Valor", color="Período",
                     barmode="group", title=titulo,
                     color_discrete_map=COLORES_PERIODO,
                     text_auto=".2s")
        fig.update_traces(textposition="outside")
        fig.update_layout(margin=dict(t=40,b=50,l=10,r=10),
                          legend=dict(orientation="h", y=-0.25),
                          xaxis_tickangle=-25)
        col_g.plotly_chart(fig, use_container_width=True)


# ── WARNING ───────────────────────────────────────────────────────────────────
def _warning_sin_pedido(todos, cli_map, periodos):
    act = {p["cliente"].lower() for p in _filtrar(todos, periodos["Sem Actual"], cli_map)}
    ant = {p["cliente"]         for p in _filtrar(todos, periodos["Sem Ant."],   cli_map)}
    sin = sorted({c for c in ant if c.lower() not in act})
    if sin:
        st.warning("⚠️ **Sin pedido esta semana (compraron la anterior):** " +
                   "  ·  ".join(f"**{c}**" for c in sin))


# ── TAB 1: DESEMPEÑO ──────────────────────────────────────────────────────────
def _tab_desempeno(todos, cli_map, periodos, campo, label_campo):

    # Metas
    with st.expander("⚙️ Metas semanales por zona (Q)", expanded=False):
        mc = st.columns(len(ZONAS_MAP))
        for col, zona in zip(mc, ZONAS_MAP):
            k = f"meta_{zona}"
            if k not in st.session_state: st.session_state[k] = 0.0
            st.session_state[k] = col.number_input(
                zona, min_value=0.0, step=100.0,
                value=float(st.session_state[k]), key=f"inp_{k}")

    st.divider()

    # ── KPIs globales compactos ───────────────────────────────────────────────
    vals_global = {
        pnm: sum(p[campo] or 0 for p in _filtrar(todos, fn, cli_map))
        for pnm, fn in periodos.items()
    }
    # Margen % solo para semana actual
    v_act = vals_global["Sem Actual"]
    v_ant = vals_global["Sem Ant."]
    delta_txt = f"{'▲' if v_act>=v_ant else '▼'} Q{abs(v_act-v_ant):,.0f} vs sem ant."

    st.markdown(
        f"<div style='font-size:.7rem;color:#666;margin-bottom:2px'>"
        f"{label_campo} total &nbsp;·&nbsp; {delta_txt}</div>",
        unsafe_allow_html=True)
    st.markdown(_html_compacto([{
        "label": "Global", "vals": vals_global, "color": "#2D7A2D"
    }]), unsafe_allow_html=True)

    meta_total = sum(st.session_state.get(f"meta_{z}", 0) for z in ZONAS_MAP)
    if meta_total > 0 and campo == "total":
        pct = min(v_act / meta_total, 1.0)
        st.progress(pct, text=f"Q{v_act:,.0f} / Meta Q{meta_total:,.0f} ({pct*100:.1f}%)")

    st.divider()

    # ── Detalle por zona (compacto, misma tipografía) ─────────────────────────
    st.markdown(f"<div style='font-size:.75rem;font-weight:bold;color:#555;"
                f"margin-bottom:4px'>Detalle por zona</div>", unsafe_allow_html=True)

    filas_zona = []
    for zona in ZONAS_MAP:
        vals_z = {pnm: sum(p[campo] or 0
                           for p in _filtrar(todos, fn, cli_map, zona_only=zona))
                  for pnm, fn in periodos.items()}
        filas_zona.append({"label": zona, "vals": vals_z,
                            "color": COLORES_ZONA[zona]})
        meta_z = st.session_state.get(f"meta_{zona}", 0)
        v_z    = vals_z["Sem Actual"]
        if meta_z > 0 and campo == "total":
            filas_zona[-1]["meta_txt"] = (
                f"Meta: Q{v_z:,.0f} / Q{meta_z:,.0f} "
                f"({min(v_z/meta_z,1)*100:.1f}%)")
            filas_zona[-1]["meta_pct"] = min(v_z / meta_z, 1.0)

    st.markdown(_html_compacto(filas_zona), unsafe_allow_html=True)

    for f in filas_zona:
        if "meta_pct" in f:
            st.progress(f["meta_pct"], text=f.get("meta_txt",""))

    st.divider()

    # ── Dos gráficos: corto y largo plazo ─────────────────────────────────────
    rows = []
    for zona in ZONAS_MAP:
        for pnm, fn in periodos.items():
            val = sum(p[campo] or 0
                      for p in _filtrar(todos, fn, cli_map, zona_only=zona))
            rows.append({"Zona": zona, "Período": pnm, "Valor": val})

    _dos_graficos(rows, "Zona",
                  f"{label_campo} — Sem Actual / Sem Ant. / MTD",
                  f"{label_campo} — YTD vs PYTD")


# ── TAB 2: TOP CLIENTES ───────────────────────────────────────────────────────
def _tab_top_clientes(todos, cli_map, periodos, campo, label_campo):
    agg = _agg_grupo(todos, periodos, cli_map, by="cliente", campo=campo)
    if not agg:
        st.info("Sin datos."); return

    df_all = pd.DataFrame([
        {"cliente": v["_nombre"], "zona": v["zona"],
         **{p: v[p] for p in periodos}}
        for v in agg.values()
    ])

    for zona in ZONAS_MAP:
        color  = COLORES_ZONA[zona]
        top_n  = 5 if zona in ("Antigua & Chimal", "Rio") else 3
        df_z   = df_all[df_all["zona"]==zona].nlargest(top_n, "YTD")

        st.markdown(
            f"<div style='border-left:4px solid {color};padding:3px 10px;"
            f"margin:8px 0 4px 0;border-radius:4px;font-weight:bold;"
            f"font-size:.85rem'>{zona} — Top {top_n} {label_campo}</div>",
            unsafe_allow_html=True)

        if df_z.empty:
            st.caption("Sin datos."); continue

        # Tabla compacta
        cols_show = ["cliente"] + list(periodos.keys())
        df_show = df_z[cols_show].copy()
        df_show.columns = ["Cliente"] + list(periodos.keys())
        for col in periodos.keys():
            df_show[col] = df_show[col].apply(lambda x: f"Q{x:,.2f}")
        st.dataframe(df_show.reset_index(drop=True),
                     use_container_width=True, hide_index=True)

        # Dos gráficos
        rows = []
        for _, row in df_z.iterrows():
            for per in periodos:
                rows.append({"Cliente": row["cliente"][:20],
                              "Período": per, "Valor": row[per]})
        _dos_graficos(rows, "Cliente",
                      f"Sem / MTD — {zona}",
                      f"YTD vs PYTD — {zona}")

        st.divider()


# ── TAB 3: TOP PRODUCTOS ──────────────────────────────────────────────────────
def _tab_top_productos(todos, cli_map, periodos, campo, label_campo):
    zona_f = st.selectbox("Zona", ["Todas"]+list(ZONAS_MAP.keys()), key="topprod_zona")
    zona_only = zona_f if zona_f != "Todas" else None

    agg = _agg_grupo(todos, periodos, cli_map, by="producto",
                     campo=campo, zona_only=zona_only)
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
    for col in periodos.keys():
        if campo == "cantidad":
            df_show[col] = df_show[col].apply(lambda x: f"{x:,.1f}")
        else:
            df_show[col] = df_show[col].apply(lambda x: f"Q{x:,.2f}")
    st.dataframe(df_show.reset_index(drop=True),
                 use_container_width=True, hide_index=True)

    # Dos gráficos Top 5
    st.markdown("**Gráfico Top 5**")
    df_t5 = df_top.head(5)
    rows = []
    for _, row in df_t5.iterrows():
        for per in periodos:
            rows.append({"Producto": row["producto"][:18],
                          "Período": per, "Valor": row[per]})
    _dos_graficos(rows, "Producto",
                  f"Sem / MTD — {label_campo}",
                  f"YTD vs PYTD — {label_campo}")


# ── TAB 4: CRÉDITOS ───────────────────────────────────────────────────────────
def _tab_creditos(todos, clientes):
    hoy = date.today()
    cli_map2 = {c["nombre"].lower(): c for c in clientes}
    vencidos: dict = {}
    for p in todos:
        if p["status"]=="Cancelado" or _excluido(p["cliente"]): continue
        fv = p.get("fecha_venc")
        if not fv or fv >= hoy: continue
        cli = p["cliente"]
        if cli not in vencidos: vencidos[cli] = {"monto": 0, "fecha_venc": fv}
        vencidos[cli]["monto"] += p["total"] or 0
        if fv < vencidos[cli]["fecha_venc"]: vencidos[cli]["fecha_venc"] = fv

    if not vencidos:
        st.success("✅ No hay créditos vencidos."); return
    st.warning(f"⚠️ {len(vencidos)} cliente(s) con crédito vencido")
    rows = []
    for cli, info in sorted(vencidos.items(), key=lambda x: x[1]["fecha_venc"]):
        ci = cli_map2.get(cli.lower(), {})
        rows.append({"Cliente": cli, "NIT": ci.get("nit","—"),
                     "Venc.": info["fecha_venc"].strftime("%d/%m/%Y"),
                     "Días": (hoy - info["fecha_venc"]).days,
                     "Monto (Q)": f"Q{info['monto']:,.2f}"})
    df = pd.DataFrame(rows).sort_values("Días", ascending=False)
    st.dataframe(df.reset_index(drop=True), use_container_width=True, hide_index=True)


# ── TAB 5: CRM ────────────────────────────────────────────────────────────────
def _tab_crm(todos, clientes, sem_act, año_act):
    hist: dict = {}
    for p in todos:
        if _excluido(p["cliente"]): continue
        cli = p["cliente"]
        if cli not in hist:
            hist[cli] = {"pedidos":[], "total":0, "margen":0, "prods":{}}
        hist[cli]["pedidos"].append(p)
        hist[cli]["total"]  += p["total"]    or 0
        hist[cli]["margen"] += p["margen_q"] or 0
        prod = p["producto"]
        hist[cli]["prods"][prod] = hist[cli]["prods"].get(prod,0) + (p["cantidad"] or 0)

    def _status(peds):
        sems = [p["semana"] for p in peds if p["año"]==año_act and p["semana"]]
        if not sems: return "🔴 Inactivo"
        d = sem_act - max(sems)
        if d <= 0: return "🟢 Activo"
        if d <= 2: return "🟡 En Riesgo"
        return "🔴 Inactivo"

    filas = []
    for c in clientes:
        if _excluido(c["nombre"]): continue
        info = hist.get(c["nombre"])
        if not info: continue
        peds  = info["pedidos"]
        sems  = sorted({(p["año"],p["semana"]) for p in peds if p["semana"]}, reverse=True)
        n     = len(sems)
        zona  = _zona_de(c["codigo_lugar"]) or "—"
        filas.append({
            "Estado": _status(peds), "Cliente": c["nombre"], "Zona": zona,
            "Última Sem": f"Sem {sems[0][1]}/{sems[0][0]}" if sems else "—",
            "Sem. activas": n,
            "Ticket Prom.": f"Q{info['total']/n:,.2f}" if n else "Q0",
            "Total Hist.": f"Q{info['total']:,.2f}",
            "Margen Hist.": f"Q{info['margen']:,.2f}",
            "Top Producto": max(info["prods"], key=info["prods"].get) if info["prods"] else "—",
        })

    if not filas: st.info("Sin datos."); return
    df = pd.DataFrame(filas)

    fc1, fc2, fc3 = st.columns(3)
    with fc1: f_z = st.selectbox("Zona",   ["Todas"]+list(ZONAS_MAP.keys()), key="crm_z")
    with fc2: f_e = st.selectbox("Estado", ["Todos","🟢 Activo","🟡 En Riesgo","🔴 Inactivo"], key="crm_e")
    with fc3: f_b = st.text_input("Buscar", placeholder="Nombre...", key="crm_b")

    if f_z != "Todas": df = df[df["Zona"]==f_z]
    if f_e != "Todos": df = df[df["Estado"]==f_e]
    if f_b:            df = df[df["Cliente"].str.lower().str.contains(f_b.lower())]

    st.markdown(f"**{len(df)} clientes**")
    st.dataframe(df.reset_index(drop=True), use_container_width=True, hide_index=True)

    st.divider()
    cli_sel = st.selectbox("Ver detalle", [""]+list(df["Cliente"]), key="crm_d")
    if cli_sel and cli_sel in hist:
        info = hist[cli_sel]; cli_obj = next((c for c in clientes if c["nombre"]==cli_sel), {})
        st.markdown(f"#### 👤 {cli_sel}")
        d1,d2,d3,d4 = st.columns(4)
        d1.metric("Total hist.", f"Q{info['total']:,.2f}")
        d2.metric("Margen hist.", f"Q{info['margen']:,.2f}")
        sems_u = {(p["año"],p["semana"]) for p in info["pedidos"] if p["semana"]}
        d3.metric("Sem. activas", len(sems_u))
        d4.metric("Crédito", f"{cli_obj.get('credito',0)} días")
        top5 = sorted(info["prods"].items(), key=lambda x: x[1], reverse=True)[:5]
        st.markdown("**Top 5 productos:**")
        for prod, cant in top5: st.caption(f"• {prod}: {cant:.1f} uds")
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

    cli_map  = _build_cli_map(clientes)
    hoy      = date.today()
    sem_act  = hoy.isocalendar()[1]
    año_act  = hoy.year
    periodos = _periodos(hoy)

    _warning_sin_pedido(todos, cli_map, periodos)

    # ── Toggle de métrica: aplica a TODOS los tabs ────────────────────────────
    metric = st.radio("Métrica",
                       ["Q Venta", "Q Margen Neto", "Unidades"],
                       horizontal=True, key="dash_metric")
    campo = {"Q Venta": "total", "Q Margen Neto": "margen_q",
             "Unidades": "cantidad"}[metric]

    st.divider()

    t1, t2, t3, t4, t5 = st.tabs([
        "📈 Desempeño Actual",
        "🏆 Top Clientes",
        "📦 Top Productos",
        "💳 Créditos Pendientes",
        "👤 CRM Clientes",
    ])
    with t1: _tab_desempeno(todos, cli_map, periodos, campo, metric)
    with t2: _tab_top_clientes(todos, cli_map, periodos, campo, metric)
    with t3: _tab_top_productos(todos, cli_map, periodos, campo, metric)
    with t4: _tab_creditos(todos, clientes)
    with t5: _tab_crm(todos, clientes, sem_act, año_act)
