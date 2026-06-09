"""
app.py — VeggiExpress | Sistema de Gestión
"""
import os
import importlib
import streamlit as st

st.set_page_config(
    page_title="VeggiExpress",
    page_icon="🥬",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container   { padding-top: 0.8rem !important; }
    .stButton > button { width: 100%; height: 2.8rem; font-size:.98rem; border-radius:8px; }
    section[data-testid="stSidebar"] { min-width:210px; max-width:230px; }
</style>
""", unsafe_allow_html=True)

# ── MENÚ Y RUTAS ──────────────────────────────────────────────────────────────
PAGES = [
    ("🏠 Inicio",                               "modulo_inicio"),
    ("🛒 Nuevo Pedido",                         "modulo_pedidos"),
    ("📋 Gestión Pedidos (Revisar y Editar)",   "modulo_gestion"),
    ("📦 Productos (Nuevos y Mantenimiento)",   "modulo_productos"),
    ("📦 Pedidos a Proveedores",                "modulo_proveedores"),
    ("🚚 Envíos y Facturación Semana",          "modulo_envios"),
    ("🧾 Facturación Mensual",                  "modulo_facturacion"),
    ("💳 Gastos",                               "modulo_gastos"),
    ("📊 Dashboard",                            "modulo_dashboard"),
    ("🏡 Casa / Personal",                      "modulo_casa"),
    ("💰 Flujo de Caja",                        "modulo_flujo_caja"),
    ("📥 Pedidos Entrantes",                    "modulo_pedidos_entrantes"),
    ("🔧 Mantenimiento",                        "modulo_mantenimiento"),
    ("👥 Clientes (Nuevos y Mantenimiento)",    "modulo_clientes"),
    ("🧮 Cotizador",                            "modulo_cotizador"),
    ("🔍 Precios La Torre",                     "modulo_scraper"),
]

MENU   = [label  for label, _      in PAGES]
ROUTES = {label: modulo for label, modulo in PAGES}

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    if os.path.exists("VeggiExpress-02.png"):
        st.image("VeggiExpress-02.png", use_container_width=True)
    else:
        st.markdown("## 🥬 VeggiExpress")
    st.divider()

    if "_nav_target" in st.session_state:
        target = st.session_state.pop("_nav_target")
        if target in MENU:
            st.session_state["nav"] = target

    pagina = st.radio("", MENU, key="nav", label_visibility="collapsed")

    st.divider()
    st.caption(
        "💡 **Recordatorio:** revisá costos\n"
        "en Productos antes de ingresar\n"
        "un pedido nuevo."
    )
    st.caption("VeggiExpress · Más fresco, imposible.")

# ── ROUTER ────────────────────────────────────────────────────────────────────
modulo_nombre = ROUTES.get(pagina)
if modulo_nombre:
    importlib.import_module(modulo_nombre).mostrar()
