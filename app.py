"""
app.py — Rio Veggi | Sistema de Gestión
Navegación principal entre módulos.
"""
import streamlit as st

st.set_page_config(
    page_title="Rio Veggi",
    page_icon="🥬",
    layout="centered",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container   { padding-top: 0.8rem !important; }
    .stButton > button { width: 100%; height: 2.8rem; font-size: .98rem; border-radius: 8px; }
    section[data-testid="stSidebar"] { min-width: 200px; max-width: 220px; }
</style>
""", unsafe_allow_html=True)

# ── NAVEGACIÓN ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🥬 Rio Veggi")
    st.divider()
    pagina = st.radio(
        "Módulo",
        ["🛒 Nuevo Pedido", "📋 Gestión Pedidos", "👥 Clientes", "📦 Productos"],
        key="nav",
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("v2.0 · Rio Veggi App")

# ── ROUTER ────────────────────────────────────────────────────────────────────
if pagina == "🛒 Nuevo Pedido":
    import modulo_pedidos
    modulo_pedidos.mostrar()

elif pagina == "📋 Gestión Pedidos":
    import modulo_gestion
    modulo_gestion.mostrar()

elif pagina == "👥 Clientes":
    import modulo_clientes
    modulo_clientes.mostrar()

elif pagina == "📦 Productos":
    import modulo_productos
    modulo_productos.mostrar()
