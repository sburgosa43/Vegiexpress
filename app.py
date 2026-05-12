"""
app.py - Rio Veggi | Ingreso de Pedidos
Interfaz web multi-usuario para ingresar pedidos al Excel en Google Drive.
"""

import streamlit as st
import pandas as pd
from datetime import date
from data_helper import cargar_clientes, cargar_productos
from order_helper import guardar_pedido

# ── CONFIGURACION ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Pedidos · Rio Veggi",
    page_icon="🥬",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .block-container { padding-top: 1rem !important; }
    .stButton > button  { width: 100%; height: 3rem; font-size: 1rem; border-radius: 8px; }
    .step-active { color: #2e7d32; font-weight: bold; font-size: 1.05rem; }
    .step-done   { color: #aaa;    text-decoration: line-through; }
    .step-todo   { color: #999;    font-size: 1rem; }
    .card {
        background: #f1f8f1;
        border-left: 4px solid #2e7d32;
        border-radius: 6px;
        padding: 10px 14px;
        margin: 6px 0;
        font-size: 0.93rem;
        line-height: 1.6;
    }
    .total-card {
        background: #e8f5e9;
        border-radius: 8px;
        padding: 14px;
        text-align: center;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)


# ── SESSION STATE ─────────────────────────────────────────────────────────────
_DEFAULTS = {
    "paso":            1,
    "cliente":         None,
    "fecha_entrega":   date.today(),
    "lineas":          [],
    "grid_data":       None,   # DataFrame del grid de productos
    "filas_grid":      15,     # cuantas filas muestra el grid
    "guardado_ok":     False,
    "filas_guardadas": 0,
}

def _init():
    for k, v in _DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v

def _reset():
    for k in list(_DEFAULTS.keys()):
        st.session_state[k] = _DEFAULTS[k]
    # Limpiar el grid tambien
    if "grid_data" in st.session_state:
        del st.session_state["grid_data"]

_init()


# ── INDICADOR DE PASOS ────────────────────────────────────────────────────────
def _pasos():
    paso   = st.session_state.paso
    labels = ["👤 Cliente", "🛒 Productos", "✅ Confirmar"]
    cols   = st.columns(3)
    for i, (col, label) in enumerate(zip(cols, labels), 1):
        with col:
            if i == paso:
                st.markdown(f"<span class='step-active'>{label} ←</span>", unsafe_allow_html=True)
            elif i < paso:
                st.markdown(f"<span class='step-done'>{label} ✔</span>", unsafe_allow_html=True)
            else:
                st.markdown(f"<span class='step-todo'>{label}</span>", unsafe_allow_html=True)
    st.divider()


# ═══════════════════════════════════════════════════════════════════════════════
# PASO 1 — CLIENTE Y FECHA
# ═══════════════════════════════════════════════════════════════════════════════
def _paso_cliente():
    st.subheader("👤 ¿Para quién es el pedido?")

    clientes      = cargar_clientes()
    activos       = [c for c in clientes if c["activo"]]
    todos         = clientes

    ver_todos     = st.checkbox("Incluir clientes pendientes", value=False)
    lista         = todos if ver_todos else activos
    nombres       = [c["nombre"] for c in lista]

    nombre_sel = st.selectbox(
        "Cliente",
        nombres,
        index=None,
        placeholder="Escribí para buscar...",
    )

    if nombre_sel:
        cliente = next(c for c in lista if c["nombre"] == nombre_sel)

        st.markdown(f"""
        <div class='card'>
            📍 <b>Dirección:</b> {cliente['direccion']}<br>
            🏢 <b>Empresa:</b> {cliente['empresa']} &nbsp;|&nbsp;
            💳 <b>NIT:</b> {cliente['nit']}<br>
            🏷️ <b>Tipo:</b> {cliente['tipo']} &nbsp;|&nbsp;
            📅 <b>Crédito:</b> {cliente['credito']} días &nbsp;|&nbsp;
            📌 <b>Zona:</b> {cliente['codigo_lugar']}
            {"&nbsp;🔖 <b>Precio Antigua</b>" if cliente['es_antigua'] else ""}
        </div>
        """, unsafe_allow_html=True)

        fecha  = st.date_input("📅 Fecha de entrega", value=date.today(), min_value=date.today())
        semana = fecha.isocalendar()[1]
        st.caption(f"Semana {semana} · {fecha.strftime('%A %d/%m/%Y')}")

        if st.button("Continuar → Agregar Productos", type="primary"):
            st.session_state.cliente       = cliente
            st.session_state.fecha_entrega = fecha
            # Resetear grid al cambiar cliente
            st.session_state.grid_data = None
            st.session_state.filas_grid = 15
            st.session_state.paso = 2
            st.rerun()
    else:
        st.info("Seleccioná un cliente para continuar.")


# ═══════════════════════════════════════════════════════════════════════════════
# PASO 2 — GRILLA DE PRODUCTOS (15 lineas por defecto)
# ═══════════════════════════════════════════════════════════════════════════════
def _paso_productos():
    cliente = st.session_state.cliente
    fecha   = st.session_state.fecha_entrega

    st.subheader(f"🛒 Productos para {cliente['nombre']}")
    st.caption(
        f"📅 {fecha.strftime('%d/%m/%Y')} · "
        f"📍 {cliente['direccion']}"
        + (" · 🔖 Precios Antigua" if cliente["es_antigua"] else "")
    )

    # Cargar catalogo
    productos  = cargar_productos(es_antigua=cliente["es_antigua"])
    prod_dict  = {p["nombre"]: p for p in productos}
    nombres_p  = [""] + [p["nombre"] for p in productos]

    n_filas = st.session_state.filas_grid

    # Inicializar o recuperar el DataFrame del grid
    if st.session_state.grid_data is None:
        st.session_state.grid_data = pd.DataFrame({
            "Producto":   [""] * n_filas,
            "Cantidad":   [0.0] * n_filas,
        })
    elif len(st.session_state.grid_data) < n_filas:
        # Agregar filas extra si el usuario pidio mas
        extra_n = n_filas - len(st.session_state.grid_data)
        extra   = pd.DataFrame({"Producto": [""] * extra_n, "Cantidad": [0.0] * extra_n})
        st.session_state.grid_data = pd.concat(
            [st.session_state.grid_data, extra], ignore_index=True
        )

    st.markdown("**Completá el pedido** — dejá en blanco las filas que no uses:")

    # ── GRILLA ────────────────────────────────────────────────────────────────
    editado = st.data_editor(
        st.session_state.grid_data,
        column_config={
            "Producto": st.column_config.SelectboxColumn(
                "Producto",
                options=nombres_p,
                required=False,
                width="large",
            ),
            "Cantidad": st.column_config.NumberColumn(
                "Cantidad",
                min_value=0.0,
                step=0.5,
                format="%.1f",
                width="small",
            ),
        },
        num_rows="fixed",
        use_container_width=True,
        hide_index=False,
        key="grid_editor",
    )

    # ── BOTONES ───────────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns([2, 2, 3])

    with col1:
        if st.button("+ 5 líneas", help="Agregar 5 filas más al pedido"):
            st.session_state.grid_data  = editado
            st.session_state.filas_grid = len(editado) + 5
            st.rerun()

    with col2:
        if st.button("+ 10 líneas", help="Agregar 10 filas más al pedido"):
            st.session_state.grid_data  = editado
            st.session_state.filas_grid = len(editado) + 10
            st.rerun()

    with col3:
        if st.button("🗑 Limpiar todo", type="secondary"):
            st.session_state.grid_data  = None
            st.session_state.filas_grid = 15
            st.rerun()

    st.divider()

    # ── VISTA PREVIA DEL TOTAL ─────────────────────────────────────────────────
    lineas_validas = [
        row for _, row in editado.iterrows()
        if row["Producto"] and row["Cantidad"] > 0
    ]

    if lineas_validas:
        total_est = sum(
            row["Cantidad"] * prod_dict[row["Producto"]]["precio"]
            for row in lineas_validas
            if row["Producto"] in prod_dict
        )
        st.markdown(
            f"<div class='total-card'>"
            f"<b>{len(lineas_validas)} productos</b> · "
            f"Total estimado: <b>Q{total_est:,.2f}</b>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── NAVEGACION ─────────────────────────────────────────────────────────────
    c_back, c_next = st.columns(2)

    with c_back:
        if st.button("← Cambiar cliente", type="secondary"):
            st.session_state.grid_data = editado
            st.session_state.paso = 1
            st.rerun()

    with c_next:
        if st.button("Revisar y Confirmar →", type="primary"):
            # Procesar filas validas
            lineas = []
            for row in lineas_validas:
                prod = prod_dict.get(row["Producto"])
                if prod:
                    lineas.append({
                        "nombre":   row["Producto"],
                        "cantidad": row["Cantidad"],
                        "precio":   prod["precio"],   # referencia visual, Excel recalcula
                        "unidad":   prod["unidad"],
                    })

            if not lineas:
                st.warning("⚠️ Completá al menos un producto con cantidad mayor a 0.")
            else:
                st.session_state.grid_data = editado
                st.session_state.lineas    = lineas
                st.session_state.paso      = 3
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# PASO 3 — CONFIRMACION Y GUARDADO
# ═══════════════════════════════════════════════════════════════════════════════
def _paso_confirmar():
    cliente = st.session_state.cliente
    fecha   = st.session_state.fecha_entrega
    lineas  = st.session_state.lineas

    st.subheader("✅ Confirmar Pedido")

    st.markdown(f"""
    <div class='card'>
        👤 <b>{cliente['nombre']}</b> — {cliente['empresa']}<br>
        📅 Entrega: <b>{fecha.strftime('%d/%m/%Y')}</b>
        (Semana {fecha.isocalendar()[1]}) &nbsp;|&nbsp;
        📅 Crédito: {cliente['credito']} días<br>
        📍 {cliente['direccion']} &nbsp;|&nbsp; NIT: {cliente['nit']}
    </div>
    """, unsafe_allow_html=True)

    st.divider()
    st.markdown("**Detalle del pedido:**")

    # Encabezado de tabla
    h = st.columns([4, 1, 1.5])
    h[0].markdown("**Producto**")
    h[1].markdown("**Cant.**")
    h[2].markdown("**Precio est.**")

    total_est = 0
    for linea in lineas:
        r = st.columns([4, 1, 1.5])
        r[0].write(linea["nombre"])
        r[1].write(f"{linea['cantidad']} {linea['unidad']}")
        precio_est = linea["precio"] * linea["cantidad"]
        r[2].write(f"Q{precio_est:,.2f}")
        total_est += precio_est

    st.divider()
    st.markdown(
        f"<div class='total-card'>"
        f"<b>{len(lineas)} productos</b> · Total estimado: <b>Q{total_est:,.2f}</b><br>"
        f"<small>⚠️ El precio final lo calcula Excel con sus fórmulas al abrir el archivo</small>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.divider()
    c1, c2 = st.columns(2)

    with c1:
        if st.button("← Editar productos", type="secondary"):
            st.session_state.paso = 2
            st.rerun()

    with c2:
        if st.button("💾 Guardar en Excel", type="primary"):
            with st.spinner("⏳ Guardando en Google Drive..."):
                try:
                    n = guardar_pedido(
                        nombre_cliente = cliente["nombre"],
                        fecha_entrega  = fecha,
                        items          = lineas,
                    )
                    st.session_state.filas_guardadas = n
                    st.session_state.guardado_ok     = True
                    st.session_state.paso            = 4
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al guardar: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# PASO 4 — EXITO
# ═══════════════════════════════════════════════════════════════════════════════
def _paso_exito():
    cliente = st.session_state.cliente
    fecha   = st.session_state.fecha_entrega
    lineas  = st.session_state.lineas
    n       = st.session_state.filas_guardadas

    st.success(f"### 🎉 ¡Pedido guardado exitosamente!")
    st.balloons()

    st.markdown(f"""
    <div class='card'>
        👤 <b>{cliente['nombre']}</b><br>
        📅 Entrega: {fecha.strftime('%d/%m/%Y')}<br>
        🛒 {len(lineas)} productos · {n} filas escritas en Excel
    </div>
    """, unsafe_allow_html=True)

    st.info(
        "📊 **Siguiente paso:** Abrí el Excel en Drive y hacé "
        "**Datos → Actualizar todo** para refrescar las tablas dinámicas."
    )

    st.divider()
    if st.button("➕ Ingresar otro pedido", type="primary"):
        _reset()
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    st.markdown("## 🥬 Rio Veggi — Pedidos")

    if st.session_state.paso in (1, 2, 3):
        _pasos()

    if   st.session_state.paso == 1: _paso_cliente()
    elif st.session_state.paso == 2: _paso_productos()
    elif st.session_state.paso == 3: _paso_confirmar()
    elif st.session_state.paso == 4: _paso_exito()

if __name__ == "__main__":
    main()
