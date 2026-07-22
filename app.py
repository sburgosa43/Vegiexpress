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
# Menú agrupado en secciones por flujo de trabajo. Cada sección tiene su
# encabezado (en negrita) y sus páginas; los encabezados NO son seleccionables
# (se renderizan aparte del radio). Orden de secciones y páginas según uso.
SECCIONES = [
    ("🔵 OPERACIÓN DIARIA", [
        ("🏠 Inicio",                       "modulo_inicio"),
        ("📥 Ingreso de Pedidos",           "modulo_ingreso"),
        ("📋 Gestión de Pedidos",           "modulo_gestion"),
        ("🛒 Compras a Proveedores",        "modulo_proveedores"),
        ("🚚 Envíos y Facturación Semanal", "modulo_envios"),
        ("🧾 Facturación Mensual",          "modulo_facturacion"),
    ]),
    ("🟡 CATÁLOGOS", [
        ("📦 Productos",                    "modulo_productos"),
        ("👥 Clientes",                     "modulo_clientes"),
    ]),
    ("🟢 ADMINISTRACIÓN", [
        ("💳 Gastos",                       "modulo_gastos"),
        ("🏡 Casa / Personal",              "modulo_casa"),
        ("💰 Flujo de Caja",                "modulo_flujo_caja"),
    ]),
    ("🌱 PRODUCCIÓN", [
        ("🌱 Producción",                   "modulo_produccion"),
    ]),
    ("⚙️ CONFIGURACIÓN", [
        ("📝 Formularios",                  "modulo_formularios"),
        ("🗂️ Datos",                        "modulo_datos"),
        ("🔧 Mantenimiento",                "modulo_mantenimiento"),
    ]),
    ("🟣 ANÁLISIS Y HERRAMIENTAS", [
        ("📊 Dashboard",                    "modulo_dashboard"),
        ("🧮 Cotizador",                    "modulo_cotizador"),
        ("🔍 Precios de Mercado",           "modulo_scraper"),
    ]),
]

# Estructuras derivadas
PAGES  = [(label, mod) for _sec, items in SECCIONES for label, mod in items]
MENU   = [label for label, _ in PAGES]
ROUTES = {label: modulo for label, modulo in PAGES}
_PRIMER_MODULO = MENU[0]

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
            st.session_state["menu_sel"] = target

    # Página activa (persiste entre reruns)
    activa = st.session_state.get("menu_sel", _PRIMER_MODULO)
    if activa not in MENU:
        activa = _PRIMER_MODULO

    # Menú por secciones: encabezado en negrita (no seleccionable) + un botón
    # por página. El botón de la página activa se resalta (primary). Botones en
    # vez de radio → control total, sin estados intermedios raros.
    # Menú por secciones COLAPSABLES. La sección que contiene la página activa
    # se abre automáticamente; las demás quedan plegadas para un menú compacto.
    for _sec_nombre, _items in SECCIONES:
        _labels_sec = [lbl for lbl, _ in _items]
        _tiene_activa = activa in _labels_sec
        with st.expander(f"**{_sec_nombre}**", expanded=_tiene_activa):
            for _lbl, _mod in _items:
                if st.button(_lbl, key=f"nav_{_mod}",
                             use_container_width=True,
                             type=("primary" if _lbl == activa
                                   else "secondary")):
                    st.session_state["menu_sel"] = _lbl
                    st.rerun()

    pagina = activa

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
