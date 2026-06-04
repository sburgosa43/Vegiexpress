"""
modulo_inicio.py — Hub Principal / Página de Inicio VeggiExpress
"""
import os
import streamlit as st
from config import excluido_dashboard as _excluido
from datetime import date

# Mapas de zonas locales (inicio usa claves sin emoji)
ZONAS_MAP = {
    "Antigua & Chimal":     ["L03", "L04", "L10"],
    "Guatemala & Santiago": ["L05", "L06"],
    "Rio":                  ["L01"],
}
COLORES_ZONA = {
    "Antigua & Chimal":     "#2D7A2D",
    "Guatemala & Santiago": "#8DC63F",
    "Rio":                  "#4A4A4A",
}
MODULOS = {
    "⚡ Operación": [
        ("📥", "Pedidos Entrantes", "Pedidos recibidos de clientes", "📥 Pedidos Entrantes"),

        ("🛒", "Nuevo Pedido",    "Ingresar pedidos de clientes",    "🛒 Nuevo Pedido"),
        ("📋", "Gestión Pedidos", "Revisar y editar pedidos",        "📋 Gestión Pedidos (Revisar y Editar)"),
        ("🚚", "Envíos Semana",   "Gestionar envíos de la semana",   "🚚 Envíos y Facturación Semana"),
        ("🧾", "Facturación",     "Resumen mensual por cliente",     "🧾 Facturación Mensual"),
    ],
    "📁 Catálogo": [
        ("📦", "Productos",       "Gestionar catálogo y precios",    "📦 Productos (Nuevos y Mantenimiento)"),
        ("👥", "Clientes",        "Gestionar cartera de clientes",   "👥 Clientes (Nuevos y Mantenimiento)"),
    ],
    "💰 Finanzas": [
        ("📦", "Proveedores",     "Lista de compras semanal",        "📦 Pedidos a Proveedores"),
        ("💰", "Flujo de Caja",   "Liquidez semanal y proyecciones", "💰 Flujo de Caja"),
        ("📊", "Dashboard",       "KPIs y análisis de negocio",      "📊 Dashboard"),
    ],
    "🔧 Herramientas": [
        ("🔧", "Mantenimiento",   "Corrección de datos y migraciones","🔧 Mantenimiento"),
        ("🧮", "Cotizador",       "Calcular precios y márgenes",     "🧮 Cotizador"),
    ],
}


def _nav(destino):
    st.session_state["_nav_target"] = destino
    st.rerun()


def _kpis():
    """Carga KPIs de semana actual. Silencia errores si no hay datos."""
    try:
        from excel_helper import leer_pedidos
        from data_helper  import cargar_clientes

        todos    = leer_pedidos()
        clientes = cargar_clientes()
        hoy      = date.today()
        sem_act  = hoy.isocalendar()[1]
        año_act  = hoy.year
        sem_ant  = sem_act - 1
        año_ant  = año_act
        if sem_ant < 1: sem_ant = 52; año_ant -= 1

        cli_zona = {}
        for c in clientes:
            for zona, cods in ZONAS_MAP.items():
                if c["codigo_lugar"] in cods:
                    cli_zona[c["nombre"].lower()] = zona
                    break

        def _excl(n): return _excluido(n)

        ped_act = [p for p in todos
                   if p["semana"]==sem_act and p["año"]==año_act
                   and p["status"]!="Cancelado" and not _excl(p["cliente"])]
        ped_ant = [p for p in todos
                   if p["semana"]==sem_ant and p["año"]==año_ant
                   and p["status"]!="Cancelado" and not _excl(p["cliente"])]

        ventas_zona     = {z: 0.0 for z in ZONAS_MAP}
        ventas_zona_ant = {z: 0.0 for z in ZONAS_MAP}
        for p in ped_act:
            z = cli_zona.get(p["cliente"].lower())
            if z: ventas_zona[z] += p["total"] or 0
        for p in ped_ant:
            z = cli_zona.get(p["cliente"].lower())
            if z: ventas_zona_ant[z] += p["total"] or 0

        # Metas desde Config sheet
        from excel_helper import leer_metas
        metas_raw = leer_metas()   # {"GT + Santiago": X, "Río": Y, ...}

        # Mapear claves Dashboard → ZONAS_MAP
        _META_MAP = {
            "🔖 Antigua & Chimal":     "Antigua + Chimal",
            "🏙️ Guatemala & Santiago": "GT + Santiago",
            "🌊 Río":                  "Río",
        }
        metas_zona = {z: metas_raw.get(_META_MAP.get(z, ""), 0.0)
                      for z in ZONAS_MAP}

        clis_act = {p["cliente"].lower() for p in ped_act}
        sin_ped  = sorted({p["cliente"] for p in ped_ant
                           if p["cliente"].lower() not in clis_act})

        return {
            "total":       sum(ventas_zona.values()),
            "por_zona":    ventas_zona,
            "ant_zona":    ventas_zona_ant,
            "metas_zona":  metas_zona,
            "sin_pedido":  sin_ped,
            "sem_act":     sem_act,
            "año_act":     año_act,
        }
    except Exception:
        return None


def mostrar():
    # ── Logo centrado ─────────────────────────────────────────────────────────
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

    # ── KPIs ─────────────────────────────────────────────────────────────────
    with st.spinner("Cargando resumen de la semana..."):
        kpis = _kpis()
        cola = st.session_state.get("cola_pedidos", [])

    # Cola pendiente
    if cola:
        total_cola = sum(p["total"] for p in cola)
        col_w, col_btn = st.columns([5, 1])
        col_w.warning(
            f"📋 **Cola: {len(cola)} pedido(s) sin grabar** — "
            f"Q{total_cola:,.0f}")
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

    # Ventas por zona
    if kpis:
        st.markdown(
            f"<div style='font-size:.75rem;font-weight:bold;color:#555;"
            f"margin:8px 0 4px 0'>💰 Venta Semana {kpis['sem_act']} · "
            f"{kpis['año_act']} — Total: Q{kpis['total']:,.0f}</div>",
            unsafe_allow_html=True)

        zcols = st.columns(len(ZONAS_MAP))
        for col, (zona, val) in zip(zcols, kpis["por_zona"].items()):
            color   = COLORES_ZONA[zona]
            meta    = kpis.get("metas_zona", {}).get(zona, 0.0)
            ant     = kpis.get("ant_zona",   {}).get(zona, 0.0)

            # Vs meta
            if meta > 0:
                diff_meta = val - meta
                tri_m  = "▲" if diff_meta >= 0 else "▼"
                col_m  = "#2D7A2D" if diff_meta >= 0 else "#c62828"
                lbl_m  = f"{tri_m} Q{abs(diff_meta):,.0f} vs meta"
            else:
                lbl_m, col_m = "", "#888"

            # Vs semana anterior
            diff_ant = val - ant
            tri_a  = "▲" if diff_ant >= 0 else "▼"
            col_a  = "#2D7A2D" if diff_ant >= 0 else "#c62828"
            lbl_a  = f"{tri_a} Q{abs(diff_ant):,.0f} vs sem. ant."

            col.markdown(
                f"<div style='background:#f5f5f5;border-left:4px solid {color};"
                f"border-radius:6px;padding:8px 12px;text-align:center;"
                f"margin-bottom:4px'>"
                f"<div style='font-size:.62rem;color:#888'>{zona}</div>"
                f"<div style='font-size:.95rem;font-weight:bold'>Q{val:,.0f}</div>"
                + (f"<div style='font-size:.65rem;color:{col_m};font-style:italic'>"
                   f"{lbl_m}</div>" if lbl_m else "")
                + f"<div style='font-size:.65rem;color:{col_a};font-style:italic'>"
                f"{lbl_a}</div>"
                + "</div>",
                unsafe_allow_html=True)

    st.divider()

    # ── Cards de módulos ──────────────────────────────────────────────────────
    for categoria, modulos in MODULOS.items():
        st.markdown(
            f"<div style='font-size:.78rem;font-weight:bold;color:#555;"
            f"letter-spacing:.05rem;margin:8px 0 4px 0'>{categoria}</div>",
            unsafe_allow_html=True)

        cols = st.columns(2)
        for i, (emoji, titulo, desc, nav_key) in enumerate(modulos):
            with cols[i % 2]:
                st.markdown(
                    f"<div style='background:#fafafa;border:1px solid #e8e8e8;"
                    f"border-left:4px solid #2D7A2D;border-radius:8px;"
                    f"padding:10px 14px;margin-bottom:4px'>"
                    f"<div style='font-size:.95rem;font-weight:bold'>"
                    f"{emoji} {titulo}</div>"
                    f"<div style='font-size:.75rem;color:#888;margin-top:2px'>"
                    f"{desc}</div></div>",
                    unsafe_allow_html=True)
                if st.button("Abrir →", key=f"home_{nav_key}",
                             use_container_width=True):
                    _nav(nav_key)

        st.markdown("&nbsp;", unsafe_allow_html=True)

    # ── Pie ───────────────────────────────────────────────────────────────────
    st.divider()
    st.markdown(
        "<div style='text-align:center;color:#aaa;font-size:.8rem'>"
        "🥬 VeggiExpress · Más fresco, imposible.</div>",
        unsafe_allow_html=True)
