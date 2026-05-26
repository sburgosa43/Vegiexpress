"""
modulo_dashboard.py — Dashboard VeggiExpress
Períodos: Sem Actual | Sem Ant. | MTD | YTD | PYTD
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
from excel_helper import leer_pedidos, leer_metas, guardar_metas
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

    # Metas — persisten en hoja Config del Excel
    with st.expander("⚙️ Metas semanales por zona (Q) — se guardan automáticamente",
                     expanded=False):
        mc = st.columns(len(ZONAS_MAP))
        nuevas_metas = {}
        for col, zona in zip(mc, ZONAS_MAP):
            k = f"meta_{zona}"
            nuevas_metas[zona] = col.number_input(
                zona, min_value=0.0, step=100.0,
                value=float(st.session_state.get(k, 0.0)), key=f"inp_{k}")
        if st.button("💾 Guardar metas", type="primary"):
            with st.spinner("Guardando metas en Excel..."):
                guardar_metas(nuevas_metas)
            for zona, val in nuevas_metas.items():
                st.session_state[f"meta_{zona}"] = val
            st.success("✅ Metas guardadas.")

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

    for zona in ZONAS_MAP:
        color  = COLORES_ZONA[zona]
        vals_z = {pnm: sum(p[campo] or 0
                           for p in _filtrar(todos, fn, cli_map, zona_only=zona))
                  for pnm, fn in periodos.items()}
        v_act  = vals_z["Sem Actual"]
        v_ant  = vals_z["Sem Ant."]
        delta  = v_act - v_ant
        signo  = "▲" if delta >= 0 else "▼"
        delta_txt = f"{signo} Q{abs(delta):,.0f} vs sem ant."

        # Nombre de zona con delta
        st.markdown(
            f"<div style='border-left:4px solid {color};padding:3px 10px;"
            f"margin:6px 0 2px 0;border-radius:4px'>"
            f"<span style='font-size:.82rem;font-weight:bold'>{zona}</span>"
            f"&nbsp;&nbsp;<span style='font-size:.7rem;"
            f"color:{'#2D7A2D' if delta>=0 else '#C0392B'}'>{delta_txt}</span>"
            f"</div>", unsafe_allow_html=True)

        # Valores compactos
        st.markdown(_html_compacto([{"label":"", "vals": vals_z, "color": color}]),
                    unsafe_allow_html=True)

        # Barra vs meta
        meta_z = st.session_state.get(f"meta_{zona}", 0)
        if meta_z > 0 and campo == "total":
            pz = min(v_act / meta_z, 1.0)
            st.progress(pz,
                text=f"Q{v_act:,.0f} / Meta Q{meta_z:,.0f} ({pz*100:.1f}%)")

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
def _tab_creditos():
    st.markdown("### 💰 Flujo de Caja Semanal")
    st.info(
        "Este módulo fue movido a su propio espacio para mayor comodidad. "
        "Accedé desde el menú lateral o desde el botón de abajo."
    )
    if st.button("💰 Ir a Flujo de Caja", type="primary"):
        st.session_state["_nav_target"] = "💰 Flujo de Caja"
        st.rerun()


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
    # Botón de regreso al Inicio
    if st.button("🏠 Inicio", key="btn_home_dash", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()


    with st.spinner("Cargando datos..."):
        todos    = leer_pedidos()
        clientes = cargar_clientes()
        # Cargar metas persistentes (una vez por sesión)
        if not any(f"meta_{z}" in st.session_state for z in ZONAS_MAP):
            metas_guardadas = leer_metas()
            for zona, val in metas_guardadas.items():
                st.session_state[f"meta_{zona}"] = val

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
        "📈 Desempeño",
        "📊 Evolución Semanal",
        "🥧 Shares",
        "📅 Comparativo",
        "👤 CRM",
    ])
    with t1: _tab_desempeno(todos, cli_map, periodos, campo, metric)
    with t2: _tab_evolucion(todos, clientes)
    with t3: _tab_shares(todos, clientes)
    with t4: _tab_comparativo(todos, clientes)
    with t5: _tab_crm(todos, clientes, sem_act, año_act)


# ══════════════════════════════════════════════════════════════════════════════
# NUEVAS TABS: EVOLUCIÓN SEMANAL | SHARES | COMPARATIVO ANUAL
# ══════════════════════════════════════════════════════════════════════════════

ZONAS_DASH = {
    "Todas":           ["L01", "L03", "L04", "L05", "L06"],
    "GT + Santiago":   ["L05", "L06"],
    "Río":             ["L01"],
    "Antigua + Chimal":["L03", "L04"],
}
COLORES_ZONA_RUTAS = {
    "GT + Santiago":    "#2D7A2D",
    "Río":              "#8DC63F",
    "Antigua + Chimal": "#F5A623",
}


def _cli_zona_map(clientes):
    return {c["nombre"].lower(): c["codigo_lugar"] for c in clientes}


def _get_zona_nombre(cod):
    for z, cs in ZONAS_DASH.items():
        if z == "Todas": continue
        if cod in cs: return z
    return None


def _filtrar_pedidos(todos, zona_sel, czmap):
    codigos = ZONAS_DASH.get(zona_sel, [])
    return [
        p for p in todos
        if not _excluido(p["cliente"])
        and p["status"] != "Cancelado"
        and czmap.get(p["cliente"].lower(), "") in codigos
        and float(p["total"] or 0) > 0
    ]


def _val(p, var):
    return float(p["total"] or 0) if var == "Ventas" else float(p["margen_q"] or 0)


def _quarter_num(mes):
    return (mes - 1) // 3 + 1


def _quarter_label(q, año):
    return f"Q{q}-{str(año)[2:]}"


def _top10_resto(items_dict, n=10):
    """Retorna {nombre: valor} con top N + 'Otros'."""
    sorted_items = sorted(items_dict.items(), key=lambda x: x[1], reverse=True)
    top    = dict(sorted_items[:n])
    otros  = sum(v for _, v in sorted_items[n:])
    if otros > 0:
        top["Otros"] = otros
    return top


# ── TAB EVOLUCIÓN SEMANAL ─────────────────────────────────────────────────────
def _tab_evolucion(todos, clientes):
    import plotly.graph_objects as go
    from datetime import date, timedelta

    czmap = _cli_zona_map(clientes)
    hoy   = date.today()

    c1, c2, c3 = st.columns(3)
    var      = c1.selectbox("Variable", ["Ventas", "Margen Neto"],
                             key="ev_var")
    rutas_op = list(ZONAS_DASH.keys())[1:]   # excluir "Todas"
    rutas_sel= c2.multiselect("Rutas", rutas_op,
                               default=rutas_op, key="ev_rutas")
    semanas_n= c3.slider("Últimas N semanas", 8, 52, 26, key="ev_sem")

    # Construir series por zona y semana
    zona_data = {z: {} for z in rutas_op}
    for p in todos:
        if _excluido(p["cliente"]) or p["status"] == "Cancelado": continue
        cod  = czmap.get(p["cliente"].lower(), "")
        zona = _get_zona_nombre(cod)
        if not zona: continue
        key  = (p["semana"], p["año"])
        zona_data[zona][key] = zona_data[zona].get(key, 0) + _val(p, var)

    # Últimas N semanas
    sem_act = hoy.isocalendar()[1]; año_act = hoy.year
    semanas = []
    for i in range(semanas_n - 1, -1, -1):
        d   = date.fromisocalendar(año_act, sem_act, 1) - timedelta(weeks=i)
        iso = d.isocalendar()
        semanas.append((iso[1], iso[0]))

    labels = [f"Sem {s}\n{a}" for s, a in semanas]

    fig = go.Figure()
    for zona in rutas_sel:
        y_vals = [zona_data[zona].get((s, a), 0) for s, a in semanas]
        fig.add_trace(go.Scatter(
            x=labels, y=y_vals, name=zona, mode="lines+markers",
            line=dict(color=COLORES_ZONA_RUTAS.get(zona, "#888"), width=2),
            marker=dict(size=5),
        ))

    var_lbl = "Q" if var == "Ventas" else "Q Margen"
    fig.update_layout(
        title=f"Evolución Semanal — {var}",
        xaxis_title="Semana", yaxis_title=var_lbl,
        hovermode="x unified", height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)


# ── TAB SHARES ────────────────────────────────────────────────────────────────
def _tab_shares(todos, clientes):
    import plotly.express as px
    import plotly.graph_objects as go
    from datetime import date

    czmap = _cli_zona_map(clientes)
    hoy   = date.today()
    sem_act = hoy.isocalendar()[1]; año_act = hoy.year
    q_act   = _quarter_num(hoy.month)

    c1, c2, c3, c4 = st.columns(4)
    var      = c1.selectbox("Variable", ["Ventas", "Margen Neto"], key="sh_var")
    zona_sel = c2.selectbox("Zona", list(ZONAS_DASH.keys()), key="sh_zona")
    dim      = c3.selectbox("Ver por", ["Clientes", "Productos"], key="sh_dim")
    periodo  = c4.selectbox("Período",
                             ["YTD", "Trimestre Actual", "Último Mes"],
                             key="sh_per")

    # Filtrar por período
    def en_periodo(p):
        if not p["fecha"]: return False
        f = p["fecha"]
        if periodo == "YTD":
            return f.year == año_act
        if periodo == "Trimestre Actual":
            return f.year == año_act and _quarter_num(f.month) == q_act
        if periodo == "Último Mes":
            return f.year == año_act and f.month == hoy.month
        return False

    pedidos = [p for p in _filtrar_pedidos(todos, zona_sel, czmap)
               if en_periodo(p)]

    # Agregación
    agg = {}
    for p in pedidos:
        key = p["cliente"] if dim == "Clientes" else p["producto"]
        agg[key] = agg.get(key, 0) + _val(p, var)

    top = _top10_resto(agg)

    # ── Pie chart ─────────────────────────────────────────────────────────────
    if top:
        col_pie, col_tabla = st.columns([1.4, 1])
        with col_pie:
            fig_pie = px.pie(
                values=list(top.values()),
                names=list(top.keys()),
                title=f"Share de {dim} — {periodo} · {zona_sel}",
                hole=0.35,
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            fig_pie.update_layout(height=380, showlegend=True)
            st.plotly_chart(fig_pie, use_container_width=True)

        # ── Tabla crecimiento vs año anterior ─────────────────────────────────
        with col_tabla:
            st.markdown(f"**Variación vs año anterior ({dim})**")

            # Mismo período año anterior
            def en_periodo_ant(p):
                if not p["fecha"]: return False
                f = p["fecha"]
                if periodo == "YTD":
                    return f.year == año_act - 1
                if periodo == "Trimestre Actual":
                    return f.year == año_act - 1 and _quarter_num(f.month) == q_act
                if periodo == "Último Mes":
                    return f.year == año_act - 1 and f.month == hoy.month
                return False

            ped_ant = [p for p in _filtrar_pedidos(todos, zona_sel, czmap)
                       if en_periodo_ant(p)]
            agg_ant = {}
            for p in ped_ant:
                key = p["cliente"] if dim == "Clientes" else p["producto"]
                agg_ant[key] = agg_ant.get(key, 0) + _val(p, var)

            rows_tabla = []
            for nombre in list(top.keys())[:10]:
                act = agg.get(nombre, 0)
                ant = agg_ant.get(nombre, 0)
                if ant > 0:
                    var_pct = (act - ant) / ant * 100
                    icono   = "🟢" if var_pct >= 0 else "🔴"
                    var_txt = f"{icono} {var_pct:+.1f}%"
                else:
                    var_txt = "✨ Nuevo"
                rows_tabla.append({
                    dim[:-1]:  nombre[:22],
                    "Actual":  f"Q{act:,.0f}",
                    "Ant.":    f"Q{ant:,.0f}" if ant else "—",
                    "Var.":    var_txt,
                })
            if rows_tabla:
                import pandas as pd
                st.dataframe(pd.DataFrame(rows_tabla), hide_index=True,
                             use_container_width=True)
    else:
        st.info("Sin datos para el período y zona seleccionados.")


# ── TAB COMPARATIVO ANUAL ─────────────────────────────────────────────────────
def _tab_comparativo(todos, clientes):
    import plotly.graph_objects as go
    import plotly.express as px
    from datetime import date
    import pandas as pd

    czmap   = _cli_zona_map(clientes)
    hoy     = date.today()
    año_act = hoy.year
    sem_act = hoy.isocalendar()[1]
    mes_act = hoy.month
    q_act   = _quarter_num(mes_act)

    c1, c2, c3 = st.columns(3)
    var      = c1.selectbox("Variable", ["Ventas", "Margen Neto"], key="cp_var")
    zona_sel = c2.selectbox("Zona", list(ZONAS_DASH.keys()), key="cp_zona")
    dim      = c3.selectbox("Ver por", ["Clientes", "Productos"], key="cp_dim")

    pedidos = _filtrar_pedidos(todos, zona_sel, czmap)

    st.divider()

    # ── Gráfico 1: Años — YTD vs PYTD vs PY ──────────────────────────────────
    st.markdown("#### 📅 Comparativo por Año")

    def ytd_filter(p, año):
        if not p["fecha"]: return False
        f = p["fecha"]
        return f.year == año and (
            f < hoy.replace(year=año) if año < año_act else f <= hoy)

    def full_year(p, año):
        return p["fecha"] and p["fecha"].year == año

    # Agregar por nombre para top10
    def agg_pedidos(ped_list):
        agg = {}
        for p in ped_list:
            key = p["cliente"] if dim == "Clientes" else p["producto"]
            agg[key] = agg.get(key, 0) + _val(p, var)
        return agg

    ytd_data  = agg_pedidos([p for p in pedidos if ytd_filter(p, año_act)])
    pytd_data = agg_pedidos([p for p in pedidos if ytd_filter(p, año_act-1)])
    py_data   = agg_pedidos([p for p in pedidos if full_year(p, año_act-1)])

    top_names = list(_top10_resto(ytd_data).keys())

    fig_años = go.Figure()
    for lbl, data, color in [
        (f"YTD {año_act}",   ytd_data,  "#2D7A2D"),
        (f"PYTD {año_act-1}",pytd_data, "#8DC63F"),
        (f"PY {año_act-1}",  py_data,   "#CCCCCC"),
    ]:
        fig_años.add_trace(go.Bar(
            name=lbl,
            x=top_names,
            y=[data.get(n, 0) for n in top_names],
            marker_color=color,
        ))
    fig_años.update_layout(
        barmode="group", height=380,
        title=f"YTD vs PYTD vs Año Anterior — {dim}",
        xaxis_tickangle=-30,
    )
    st.plotly_chart(fig_años, use_container_width=True)

    st.divider()

    # ── Gráfico 2: Últimos 5 trimestres (apilado por cliente/producto) ────────
    st.markdown("#### 📊 Últimos 5 Trimestres")

    def _5_quarters():
        qs = []
        q, a = q_act, año_act
        for _ in range(5):
            qs.append((q, a))
            q -= 1
            if q < 1: q = 4; a -= 1
        return list(reversed(qs))

    quarters = _5_quarters()
    q_labels = [_quarter_label(q, a) for q, a in quarters]

    def agg_quarter(p):
        if not p["fecha"]: return None
        return (_quarter_num(p["fecha"].month), p["fecha"].year)

    # Agregar por (nombre, quarter)
    q_data = {}  # {nombre: {qlabel: valor}}
    for p in pedidos:
        qk = agg_quarter(p)
        if not qk or qk not in quarters: continue
        ql  = _quarter_label(*qk)
        key = p["cliente"] if dim == "Clientes" else p["producto"]
        if key not in q_data: q_data[key] = {}
        q_data[key][ql] = q_data[key].get(ql, 0) + _val(p, var)

    # Top 10 por total
    totales = {k: sum(v.values()) for k, v in q_data.items()}
    top_q   = list(_top10_resto(totales, 9).keys())
    # Agregar "Otros"
    otros_q = {}
    for ql in q_labels:
        otros_q[ql] = sum(v.get(ql, 0) for k, v in q_data.items() if k not in top_q[:-1])
    q_data["Otros"] = otros_q

    fig_q = go.Figure()
    colores_q = px.colors.qualitative.Set2
    for i, nombre in enumerate(top_q):
        if nombre not in q_data: continue
        fig_q.add_trace(go.Bar(
            name=nombre[:20],
            x=q_labels,
            y=[q_data[nombre].get(ql, 0) for ql in q_labels],
            marker_color=colores_q[i % len(colores_q)],
        ))
    fig_q.update_layout(
        barmode="stack", height=400,
        title=f"Últimos 5 Trimestres — {dim} · {zona_sel}",
    )
    st.plotly_chart(fig_q, use_container_width=True)

    st.divider()

    # ── Gráfico 3: Últimos 12 meses (apilado) ────────────────────────────────
    st.markdown("#### 📆 Últimos 12 Meses")

    from datetime import date as dt_
    def _12_months():
        meses = []
        m, a = mes_act, año_act
        for _ in range(12):
            meses.append((m, a))
            m -= 1
            if m < 1: m = 12; a -= 1
        return list(reversed(meses))

    meses12 = _12_months()
    MESES_N = ["","Ene","Feb","Mar","Abr","May","Jun",
               "Jul","Ago","Sep","Oct","Nov","Dic"]
    m_labels = [f"{MESES_N[m]}-{str(a)[2:]}" for m, a in meses12]

    # Agregar por (nombre, mes)
    m_data = {}
    for p in pedidos:
        if not p["fecha"]: continue
        mk  = (p["fecha"].month, p["fecha"].year)
        if mk not in meses12: continue
        ml  = f"{MESES_N[mk[0]]}-{str(mk[1])[2:]}"
        key = p["cliente"] if dim == "Clientes" else p["producto"]
        if key not in m_data: m_data[key] = {}
        m_data[key][ml] = m_data[key].get(ml, 0) + _val(p, var)

    totales_m = {k: sum(v.values()) for k, v in m_data.items()}
    top_m     = list(_top10_resto(totales_m, 9).keys())
    otros_m   = {ml: sum(v.get(ml, 0) for k, v in m_data.items()
                         if k not in top_m[:-1])
                 for ml in m_labels}
    m_data["Otros"] = otros_m

    fig_m = go.Figure()
    for i, nombre in enumerate(top_m):
        if nombre not in m_data: continue
        fig_m.add_trace(go.Bar(
            name=nombre[:20],
            x=m_labels,
            y=[m_data[nombre].get(ml, 0) for ml in m_labels],
            marker_color=colores_q[i % len(colores_q)],
        ))
    fig_m.update_layout(
        barmode="stack", height=400,
        title=f"Últimos 12 Meses — {dim} · {zona_sel}",
    )
    st.plotly_chart(fig_m, use_container_width=True)
