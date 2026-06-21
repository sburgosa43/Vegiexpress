"""
modulo_inicio.py — Hub Principal / Página de Inicio VeggiExpress
"""
import os
import streamlit as st
from datetime import date
from config import excluido_dashboard as _excluido
from excel_helper import leer_pedidos, _sf
from data_helper  import cargar_clientes
from gsheets      import get_all_rows

# Mapas de zonas locales (inicio usa claves sin emoji)
ZONAS_MAP = {
    "Antigua & Chimal":     ["L03", "L04", "L10"],
    "Guatemala & Santiago": ["L05", "L06"],
    "Rio":                  ["L01"],
    "Hogares":              ["L20"],
}
COLORES_ZONA = {
    "Antigua & Chimal":     "#2D7A2D",
    "Guatemala & Santiago": "#8DC63F",
    "Rio":                  "#4A4A4A",
    "Hogares":              "#E65100",
}



# ── Caché de metas (evita llamada a Sheets en cada carga) ────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def _leer_metas_inicio() -> dict:
    metas = {z: 0.0 for z in ZONAS_MAP}
    try:
        for row in get_all_rows("config"):
            if row and len(row) > 1:
                k = str(row[0]).strip()
                if k in ZONAS_MAP:
                    metas[k] = _sf(row[1])
    except Exception:
        pass
    return metas


def _nav(destino):
    st.session_state["_nav_target"] = destino
    st.rerun()


def _kpis() -> dict | None:
    """Carga todos los KPIs de semana actual en una sola pasada."""
    try:
        todos    = leer_pedidos()
        clientes = cargar_clientes()
        hoy      = date.today()
        sem_act  = hoy.isocalendar()[1]
        año_act  = hoy.year
        sem_ant  = sem_act - 1
        año_ant  = año_act
        if sem_ant < 1:
            sem_ant = 52; año_ant -= 1

        # Mapa cliente → zona (en memoria, sin API)
        cli_zona = {}
        for c in clientes:
            for zona, cods in ZONAS_MAP.items():
                if c["codigo_lugar"] in cods:
                    cli_zona[c["nombre"].lower()] = zona
                    break

        # Filtrar pedidos semana actual y anterior
        ped_act = [p for p in todos
                   if p["semana"] == sem_act and p["año"] == año_act
                   and p["status"] != "Cancelado"
                   and not _excluido(p["cliente"])]
        ped_ant = [p for p in todos
                   if p["semana"] == sem_ant and p["año"] == año_ant
                   and p["status"] != "Cancelado"
                   and not _excluido(p["cliente"])]

        # Ventas por zona
        ventas_zona     = {z: 0.0 for z in ZONAS_MAP}
        ventas_zona_ant = {z: 0.0 for z in ZONAS_MAP}
        for p in ped_act:
            z = cli_zona.get(p["cliente"].lower())
            if z: ventas_zona[z] += p.get("total") or 0
        for p in ped_ant:
            z = cli_zona.get(p["cliente"].lower())
            if z: ventas_zona_ant[z] += p.get("total") or 0

        # Metas (cacheadas)
        metas_zona = _leer_metas_inicio()

        # Clientes sin pedido esta semana (compraron la anterior)
        clis_act = {p["cliente"].lower() for p in ped_act}
        sin_ped  = sorted({p["cliente"] for p in ped_ant
                           if p["cliente"].lower() not in clis_act})

        # Flujo Neto Familiar — todo en memoria, sin API extra
        flujo_neto = None
        try:
            from modulo_gastos import _leer_gastos, _ingresos_campo_veggi, _cargar_config
            gcfg    = _cargar_config()
            all_g   = _leer_gastos()
            fn_gas  = lambda g: g["semana"] == sem_act and g["año"] == año_act
            fn_ped  = lambda p: p["semana"] == sem_act and p["año"] == año_act
            inc_op  = _ingresos_campo_veggi(todos, gcfg["campo_clis"], fn_ped)
            gas_op  = sum(g["monto"] for g in all_g
                          if fn_gas(g) and g["categoria"] != "Casa")
            gas_cs  = sum(g["monto"] for g in all_g
                          if fn_gas(g) and g["categoria"] == "Casa")
            gan_op  = sum(inc_op.values()) - gas_op
            flujo_neto = gan_op - gas_cs
        except Exception:
            pass

        return {
            "total":       sum(ventas_zona.values()),
            "por_zona":    ventas_zona,
            "ant_zona":    ventas_zona_ant,
            "metas_zona":  metas_zona,
            "sin_pedido":  sin_ped,
            "flujo_neto":  flujo_neto,
            "sem_act":     sem_act,
            "año_act":     año_act,
        }
    except Exception:
        return None


def mostrar():
    # ── Logo centrado ──────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if os.path.exists("VeggiExpress-02.png"):
            st.image("VeggiExpress-02.png", use_container_width=True)
        else:
            st.markdown(
                "<h1 style='text-align:center;color:#2D7A2D'>🥬 VeggiExpress</h1>",
                unsafe_allow_html=True)

    hoy = date.today()
    st.markdown(
        f"<div style='text-align:center;color:#777;font-size:.9rem;"
        f"margin:-8px 0 16px 0'>"
        f"Semana {hoy.isocalendar()[1]}  ·  "
        f"{hoy.strftime('%A %d de %B %Y')}"
        f"</div>", unsafe_allow_html=True)

    st.divider()

    # ── KPIs (1 solo bloque, todo cacheado o en memoria) ──────────────────────
    with st.spinner("Cargando resumen..."):
        kpis = _kpis()
        cola = st.session_state.get("cola_pedidos", [])

    # Cola pendiente
    if cola:
        total_cola = sum(p["total"] for p in cola)
        col_w, col_btn = st.columns([5, 1])
        col_w.warning(
            f"📋 **Cola: {len(cola)} pedido(s) sin grabar** — Q{total_cola:,.0f}")
        if col_btn.button("📤 Ir a grabar", key="home_cola"):
            _nav("🛒 Nuevo Pedido")

    # Clientes sin pedido
    if kpis and kpis["sin_pedido"]:
        col_a, col_b = st.columns([5, 1])
        col_a.warning(
            f"⚠️ **{len(kpis['sin_pedido'])} cliente(s) sin pedido esta semana "
            f"(compraron la anterior):**  " +
            "  ·  ".join(f"**{c}**" for c in kpis["sin_pedido"]))
        if col_b.button("📋 Ver pedidos", key="home_sinped"):
            _nav("📋 Gestión Pedidos (Revisar y Editar)")

    # Ventas por zona + triangulitos
    if kpis:
        st.markdown(
            f"<div style='font-size:.75rem;font-weight:bold;color:#555;"
            f"margin:8px 0 4px 0'>💰 Venta Semana {kpis['sem_act']} · "
            f"{kpis['año_act']} — Total: Q{kpis['total']:,.0f}</div>",
            unsafe_allow_html=True)

        zcols = st.columns(len(ZONAS_MAP))
        for col, (zona, val) in zip(zcols, kpis["por_zona"].items()):
            color = COLORES_ZONA[zona]
            meta  = kpis["metas_zona"].get(zona, 0.0)
            ant   = kpis["ant_zona"].get(zona, 0.0)

            if meta > 0:
                diff_m = val - meta
                lbl_m  = f"{'▲' if diff_m>=0 else '▼'} Q{abs(diff_m):,.0f} vs meta (Q{meta:,.0f})"
                col_m  = "#2D7A2D" if diff_m >= 0 else "#c62828"
            else:
                lbl_m, col_m = "⚙️ meta no configurada", "#aaa"

            diff_a = val - ant
            lbl_a  = f"{'▲' if diff_a>=0 else '▼'} Q{abs(diff_a):,.0f} vs sem. ant."
            col_a  = "#2D7A2D" if diff_a >= 0 else "#c62828"

            col.markdown(
                f"<div style='background:#f5f5f5;border-left:4px solid {color};"
                f"border-radius:6px;padding:8px 12px;text-align:center;margin-bottom:4px'>"
                f"<div style='font-size:.62rem;color:#888'>{zona}</div>"
                f"<div style='font-size:.95rem;font-weight:bold'>Q{val:,.0f}</div>"
                f"<div style='font-size:.65rem;color:{col_m};font-style:italic'>{lbl_m}</div>"
                f"<div style='font-size:.65rem;color:{col_a};font-style:italic'>{lbl_a}</div>"
                f"</div>",
                unsafe_allow_html=True)

        # Flujo Neto Familiar
        fn = kpis.get("flujo_neto")
        if fn is not None:
            _col = "#2D7A2D" if fn >= 0 else "#c62828"
            st.markdown(
                f"<div style='background:#f5f5f5;border-left:4px solid {_col};"
                f"border-radius:6px;padding:8px 16px;margin:6px 0;"
                f"display:flex;justify-content:space-between;align-items:center'>"
                f"<span style='font-size:.75rem;color:#555'>💰 Flujo Neto Familiar — Semana actual</span>"
                f"<span style='font-size:1.1rem;font-weight:bold;color:{_col}'>"
                f"{'✅' if fn>=0 else '⚠️'} Q{fn:,.0f}</span></div>",
                unsafe_allow_html=True)

    # ── Último backup ──────────────────────────────────────────────
    _bk = st.session_state.get("_backup_info", {})
    if _bk:
        st.caption(f"💾 Último backup: {_bk.get('ts','—')} · {_bk.get('filas',0)} filas")

    st.divider()

    # ── Cards de módulos ───────────────────────────────────────────────────────
    def _card(col, emoji, titulo, desc, nav_key, btn_key):
        with col:
            st.markdown(
                f"<div style='background:#fafafa;border:1px solid #e8e8e8;"
                f"border-left:4px solid #2D7A2D;border-radius:8px;"
                f"padding:10px 14px;margin-bottom:4px'>"
                f"<div style='font-size:.95rem;font-weight:bold'>{emoji} {titulo}</div>"
                f"<div style='font-size:.75rem;color:#888;margin-top:2px'>{desc}</div></div>",
                unsafe_allow_html=True)
            if st.button("Abrir →", key=btn_key, use_container_width=True):
                _nav(nav_key)

    def _seccion(titulo, items):
        st.markdown(
            f"<div style='font-size:.78rem;font-weight:bold;color:#555;"
            f"letter-spacing:.05rem;margin:8px 0 4px 0'>{titulo}</div>",
            unsafe_allow_html=True)
        # Render rows of 2
        for row_start in range(0, len(items), 2):
            row_items = items[row_start:row_start + 2]
            cols = st.columns(2)
            for j, (emoji, tit, desc, nk, bk) in enumerate(row_items):
                _card(cols[j], emoji, tit, desc, nk, bk)
        st.markdown("&nbsp;", unsafe_allow_html=True)

    # ── Widget de Producción (cosechas + alertas fertilización) ────────────────
    try:
        from modulo_produccion import widget_inicio as _prod_widget
        _prod_widget()
    except Exception:
        pass

    _seccion("⚡ Operación", [
        ("📥", "Pedidos Entrantes",  "Pedidos recibidos de clientes",      "📥 Pedidos Entrantes",                    "b00"),
        ("🛒", "Nuevo Pedido",       "Ingresar pedidos de clientes",        "🛒 Nuevo Pedido",                          "b01"),
        ("📋", "Gestión Pedidos",    "Revisar y editar pedidos",            "📋 Gestión Pedidos (Revisar y Editar)",    "b02"),
        ("🚚", "Envíos Semana",      "Gestionar envíos de la semana",       "🚚 Envíos y Facturación Semana",           "b03"),
        ("🧾", "Facturación",        "Resumen mensual por cliente",         "🧾 Facturación Mensual",                   "b04"),
    ])
    _seccion("📁 Catálogo", [
        ("📦", "Productos",          "Gestionar catálogo y precios",        "📦 Productos (Nuevos y Mantenimiento)",    "b05"),
        ("👥", "Clientes",           "Gestionar cartera de clientes",       "👥 Clientes (Nuevos y Mantenimiento)",     "b06"),
    ])
    _seccion("💰 Finanzas", [
        ("📦", "Proveedores",        "Lista de compras semanal",            "📦 Pedidos a Proveedores",                 "b07"),
        ("💰", "Flujo de Caja",      "Liquidez semanal y proyecciones",     "💰 Flujo de Caja",                         "b08"),
        ("💳", "Gastos",             "Gastos operativos y personales",      "💳 Gastos",                                "b09"),
        ("📊", "Dashboard",          "KPIs y análisis de negocio",          "📊 Dashboard",                             "b10"),
    ])
    _seccion("🌱 Producción", [
        ("🌱", "Producción",         "Siembras, cosechas y fertilización",  "🌱 Producción",                            "b13"),
    ])
    _seccion("🔧 Herramientas", [
        ("🔧", "Mantenimiento",      "Corrección de datos y migraciones",   "🔧 Mantenimiento",                         "b11"),
        ("🧮", "Cotizador",          "Calcular precios y márgenes",         "🧮 Cotizador",                             "b12"),
    ])

    # ── Pie ────────────────────────────────────────────────────────────────────
    st.divider()
    st.markdown(
        "<div style='text-align:center;color:#aaa;font-size:.8rem'>"
        "🥬 VeggiExpress · Más fresco, imposible.</div>",
        unsafe_allow_html=True)
