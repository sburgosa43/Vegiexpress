"""
app.py — VeggiExpress | Sistema de Gestión
"""
import os
import streamlit as st

st.set_page_config(
    page_title="VeggiExpress",
    page_icon="🥬",
    layout="centered",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container   { padding-top: 0.8rem !important; }
    .stButton > button { width: 100%; height: 2.8rem; font-size:.98rem; border-radius:8px; }
    section[data-testid="stSidebar"] { min-width:210px; max-width:230px; }
</style>
""", unsafe_allow_html=True)

# ── NAVEGACIÓN ────────────────────────────────────────────────────────────────
MENU = [
    "📦 Productos (Nuevos y Mantenimiento)",
    "👥 Clientes (Nuevos y Mantenimiento)",
    "🛒 Nuevo Pedido",
    "📋 Gestión Pedidos (Revisar y Editar)",
    "🚚 Envíos y Facturación Semana",
    "🧮 Cotizador",
]

with st.sidebar:
    if os.path.exists("VeggiExpress-02.png"):
        st.image("VeggiExpress-02.png", use_container_width=True)
    else:
        st.markdown("## 🥬 VeggiExpress")
    st.divider()

    pagina = st.radio("", MENU, key="nav", label_visibility="collapsed")

    st.divider()
    st.caption(
        "💡 **Recordatorio:** revisá costos\n"
        "en Productos antes de ingresar\n"
        "un pedido nuevo."
    )
    st.caption("VeggiExpress · Más fresco, imposible.")

# ── ROUTER ────────────────────────────────────────────────────────────────────
if pagina.startswith("📦"):
    import modulo_productos
    modulo_productos.mostrar()

elif pagina.startswith("👥"):
    import modulo_clientes
    modulo_clientes.mostrar()

elif pagina.startswith("🛒"):
    import modulo_pedidos
    modulo_pedidos.mostrar()

elif pagina.startswith("📋"):
    import modulo_gestion
    modulo_gestion.mostrar()

elif pagina.startswith("🚚"):
    import modulo_envios
    modulo_envios.mostrar()

elif pagina.startswith("🧮"):
    import modulo_cotizador
    modulo_cotizador.mostrar()
