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
# Cada entry: (label visible en sidebar, nombre del módulo Python)
# Separar display de lógica evita bugs por emojis o cambios de nombre.

PAGES = [
    ("🏠 Inicio",                               "modulo_inicio"),
    ("📥 Pedidos Entrantes",                    "modulo_pedidos_entrantes"),
    ("📦 Productos (Nuevos y Mantenimiento)",   "modulo_productos"),
    ("👥 Clientes (Nuevos y Mantenimiento)",    "modulo_clientes"),
    ("🛒 Nuevo Pedido",                         "modulo_pedidos"),
    ("📋 Gestión Pedidos (Revisar y Editar)",   "modulo_gestion"),
    ("🚚 Envíos y Facturación Semana",          "modulo_envios"),
    ("🧾 Facturación Mensual",                  "modulo_facturacion"),
    ("📦 Pedidos a Proveedores",                "modulo_proveedores"),
    ("💰 Flujo de Caja",                        "modulo_flujo_caja"),
    ("💳 Gastos",                               "modulo_gastos"),
    ("🏡 Casa / Personal",                      "modulo_casa"),
    ("📊 Dashboard",                            "modulo_dashboard"),
    ("🔧 Mantenimiento",                        "modulo_mantenimiento"),
    ("🧮 Cotizador",                            "modulo_cotizador"),
]

# Diccionario label → módulo para routing exacto y sin ambigüedad
MENU   = [label  for label, _      in PAGES]
ROUTES = {label: modulo for label, modulo in PAGES}

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    if os.path.exists("VeggiExpress-02.png"):
        st.image("VeggiExpress-02.png", use_container_width=True)
    else:
        st.markdown("## 🥬 VeggiExpress")
    st.divider()

    # Navegación programática (botones "Inicio" dentro de cada módulo)
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
# Lookup exacto por label — ningún emoji ni startswith puede causar ambigüedad.
modulo_nombre = ROUTES.get(pagina)
if modulo_nombre:
    importlib.import_module(modulo_nombre).mostrar()
