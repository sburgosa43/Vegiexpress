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
# Menú agrupado en secciones por flujo de trabajo. Los encabezados de sección
# (con prefijo "—") son separadores visuales NO seleccionables: sirven para
# orientar al usuario, no navegan a ningún módulo. Dentro de cada sección el
# orden es por frecuencia de uso.
_SEP = "sep"   # marca de separador (no es un módulo)

PAGES = [
    ("—— 🔵 OPERACIÓN DIARIA ——",               _SEP),
    ("🏠 Inicio",                               "modulo_inicio"),
    ("📥 Ingreso de Pedidos",                   "modulo_ingreso"),
    ("📋 Gestión de Pedidos",                   "modulo_gestion"),
    ("🛒 Compras a Proveedores",                "modulo_proveedores"),
    ("🚚 Envíos y Facturación Semanal",         "modulo_envios"),

    ("—— 🟢 ADMINISTRACIÓN ——",                 _SEP),
    ("🧾 Facturación Mensual",                  "modulo_facturacion"),
    ("💳 Gastos",                               "modulo_gastos"),
    ("🏡 Casa / Personal",                      "modulo_casa"),
    ("💰 Flujo de Caja",                        "modulo_flujo_caja"),

    ("—— 🟡 CATÁLOGOS ——",                      _SEP),
    ("📦 Productos",                            "modulo_productos"),
    ("👥 Clientes",                             "modulo_clientes"),

    ("—— 🟣 ANÁLISIS Y HERRAMIENTAS ——",        _SEP),
    ("📊 Dashboard",                            "modulo_dashboard"),
    ("🧮 Cotizador",                            "modulo_cotizador"),
    ("🔍 Precios de Mercado",                   "modulo_scraper"),

    ("—— 🌱 PRODUCCIÓN ——",                     _SEP),
    ("🌱 Producción",                           "modulo_produccion"),

    ("—— ⚙️ CONFIGURACIÓN ——",                  _SEP),
    ("📝 Formularios",                          "modulo_formularios"),
    ("🗂️ Datos",                                "modulo_datos"),
    ("🔧 Mantenimiento",                        "modulo_mantenimiento"),
]

MENU   = [label  for label, _      in PAGES]
ROUTES = {label: modulo for label, modulo in PAGES}
# Etiquetas que son separadores (no navegan)
SEPARADORES = {label for label, modulo in PAGES if modulo == _SEP}
# Primer módulo real (destino por defecto si cae en un separador)
_PRIMER_MODULO = next(label for label, m in PAGES if m != _SEP)

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

    # Índice inicial en "🏠 Inicio" (no en el primer separador)
    _idx_ini = MENU.index("🏠 Inicio") if "🏠 Inicio" in MENU else 0
    pagina = st.radio("Menú", MENU, index=_idx_ini, key="nav",
                      label_visibility="collapsed")

    # Si el usuario tocó un encabezado de sección (separador), no navegar:
    # volver a la última página real visitada (o el primer módulo).
    if pagina in SEPARADORES:
        pagina = st.session_state.get("_ultima_pagina", _PRIMER_MODULO)
    else:
        st.session_state["_ultima_pagina"] = pagina

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

# Liberar memoria de objetos transitorios del render (copias de caché, PDFs,
# DataFrames). En Streamlit Cloud la memoria es limitada y el GC por defecto
# puede demorar en recoger ciclos — esto mantiene el proceso liviano.
import gc as _gc
_gc.collect()
