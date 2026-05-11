"""
app.py — Rio Veggi | Ingreso de Pedidos
Interfaz web para ingresar pedidos de clientes.
Funciona en computadora y celular Android.
"""

import streamlit as st
from datetime import date
from data_helper import cargar_clientes, cargar_productos
from order_helper import guardar_pedido

# ── CONFIGURACIÓN ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Pedidos · Rio Veggi",
    page_icon="🥬",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# CSS para que se vea bien en celular y computadora
st.markdown("""
<style>
    /* Botones grandes y fáciles de tocar */
    .stButton > button {
        width: 100%;
        height: 3rem;
        font-size: 1.05rem;
        border-radius: 8px;
    }
    /* Tarjeta de resumen del cliente */
    .cliente-card {
        background: #f0f9f0;
        border-left: 4px solid #2e7d32;
        border-radius: 6px;
        padding: 12px 16px;
        margin: 8px 0;
        font-size: 0.95rem;
    }
    /* Fila de producto en el carrito */
    .producto-row {
        background: #fafafa;
        border: 1px solid #e0e0e0;
        border-radius: 6px;
        padding: 8px 12px;
        margin: 4px 0;
    }
    /* Caja del total */
    .total-card {
        background: #e8f5e9;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
        margin: 12px 0;
    }
    /* Indicador de pasos */
    .step-active { color: #2e7d32; font-weight: bold; }
    .step-done   { color: #aaa; text-decoration: line-through; }
    .step-todo   { color: #888; }
    /* Quitar padding excesivo en móvil */
    .block-container { padding-top: 1rem !important; }
</style>
""", unsafe_allow_html=True)


# ── SESSION STATE ─────────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "paso":           1,
        "cliente":        None,
        "fecha_entrega":  date.today(),
        "lineas":          [],       # lista de dicts por línea de pedido
        "guardado_ok":    False,
        "filas_guardadas": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def _reset():
    for k in ["paso", "cliente", "fecha_entrega", "lineas", "guardado_ok", "filas_guardadas"]:
        del st.session_state[k]
    _init_state()

_init_state()


# ── INDICADOR DE PASOS ────────────────────────────────────────────────────────
def _mostrar_pasos():
    paso = st.session_state.paso
    pasos = ["👤 Cliente", "🛒 Productos", "✅ Confirmar"]
    cols = st.columns(3)
    for i, (col, label) in enumerate(zip(cols, pasos), start=1):
        with col:
            if i == paso:
                st.markdown(f"<span class='step-active'>{label}</span>", unsafe_allow_html=True)
            elif i < paso:
                st.markdown(f"<span class='step-done'>{label} ✔</span>", unsafe_allow_html=True)
            else:
                st.markdown(f"<span class='step-todo'>{label}</span>", unsafe_allow_html=True)
    st.divider()


# ── PASO 1: CLIENTE Y FECHA ───────────────────────────────────────────────────
def _paso_cliente():
    st.subheader("👤 ¿Para quién es el pedido?")

    clientes = cargar_clientes()
    todos    = [c["nombre"] for c in clientes]
    activos  = [c["nombre"] for c in clientes if c["activo"]]

    mostrar_todos = st.checkbox("Mostrar clientes pendientes también", value=False)
    opciones = todos if mostrar_todos else activos

    nombre_sel = st.selectbox(
        "Seleccionar cliente",
        opciones,
        index=None,
        placeholder="Escribe para buscar...",
    )

    if nombre_sel:
        cliente = next(c for c in clientes if c["nombre"] == nombre_sel)

        st.markdown(f"""
        <div class='cliente-card'>
            📍 <b>Dirección:</b> {cliente['direccion']}<br>
            🏢 <b>Empresa:</b> {cliente['empresa']}<br>
            💳 <b>NIT:</b> {cliente['nit']}<br>
            🏷️ <b>Tipo:</b> {cliente['tipo']} &nbsp;|&nbsp;
            📅 <b>Crédito:</b> {cliente['credito']} días &nbsp;|&nbsp;
            📌 <b>Zona:</b> {cliente['codigo_lugar']}
            {" &nbsp;🔖 <b>Precio Antigua</b>" if cliente['es_antigua'] else ""}
        </div>
        """, unsafe_allow_html=True)

        fecha = st.date_input(
            "📅 Fecha de entrega",
            value=date.today(),
            min_value=date.today(),
        )
        semana = fecha.isocalendar()[1]
        st.caption(f"Semana {semana} · {fecha.strftime('%A %d de %B %Y')}")

        if st.button("Continuar → Agregar Productos", type="primary"):
            st.session_state.cliente       = cliente
            st.session_state.fecha_entrega = fecha
            st.session_state.paso          = 2
            st.rerun()
    else:
        st.info("Seleccioná un cliente para continuar.")


# ── PASO 2: PRODUCTOS ─────────────────────────────────────────────────────────
def _paso_productos():
    cliente = st.session_state.cliente
    fecha   = st.session_state.fecha_entrega

    st.subheader(f"🛒 Productos para {cliente['nombre']}")
    st.caption(f"📅 Entrega: {fecha.strftime('%d/%m/%Y')} · 📍 {cliente['direccion']}")

    if cliente["es_antigua"]:
        st.info("🔖 Aplicando **lista de precios Antigua** para este cliente.")

    productos    = cargar_productos(es_antigua=cliente["es_antigua"])
    nombres_prod = [p["nombre"] for p in productos]

    # ── Formulario para agregar producto ──────────────────────────────────────
    with st.expander("➕ Agregar producto al pedido", expanded=True):
        prod_sel = st.selectbox(
            "Producto",
            nombres_prod,
            index=None,
            placeholder="Escribe para buscar...",
            key="sel_producto",
        )

        if prod_sel:
            prod = next(p for p in productos if p["nombre"] == prod_sel)

            col1, col2 = st.columns(2)
            with col1:
                cantidad = st.number_input(
                    f"Cantidad ({prod['unidad']})",
                    min_value=0.0,
                    value=1.0,
                    step=0.5,
                    key="cant_input",
                )
            with col2:
                precio = st.number_input(
                    "Precio unitario (Q)",
                    min_value=0.0,
                    value=float(prod["precio"]),
                    step=0.50,
                    key="precio_input",
                    help="Podés ajustar el precio manualmente si lo necesitás",
                )

            # Info del producto
            info_parts = [f"💰 Costo: Q{prod['costo']:.2f}"]
            if prod["proveedor"]:
                info_parts.append(f"🏭 {prod['proveedor']}")
            if prod["comentario"]:
                info_parts.append(f"📝 {prod['comentario']}")
            if prod["es_especialidad"]:
                info_parts.append("⭐ Especialidad")
            st.caption(" · ".join(info_parts))

            if cantidad > 0:
                subtotal = cantidad * precio
                st.markdown(f"**Subtotal: Q{subtotal:,.2f}**")

            agregar_disabled = (cantidad <= 0 or precio <= 0)
            if st.button("➕ Agregar al pedido", type="primary", disabled=agregar_disabled):
                nuevo_item = {
                    "nombre":          prod_sel,
                    "unidad":          prod["unidad"],
                    "segmento":        prod["segmento"],
                    "costo":           prod["costo"],
                    "precio":          precio,
                    "cantidad":        cantidad,
                    "proveedor":       prod["proveedor"],
                    "parent":          prod["parent"],
                    "unidad_despacho": prod["unidad_despacho"],
                }
                st.session_state.lineas.append(nuevo_item)
                st.rerun()

    # ── Lista del pedido actual ───────────────────────────────────────────────
    st.divider()
    items = st.session_state.lineas

    if items:
        st.markdown("#### 📋 Pedido actual")

        total_venta = 0
        total_costo = 0

        for i, item in enumerate(items):
            subtotal     = item["cantidad"] * item["precio"]
            costo_linea  = item["cantidad"] * item["costo"]
            total_venta += subtotal
            total_costo += costo_linea

            c1, c2, c3, c4, c5 = st.columns([3, 1.2, 1.2, 1.5, 0.6])
            c1.write(f"**{item['nombre']}**")
            c2.write(f"{item['cantidad']} {item['unidad']}")
            c3.write(f"Q{item['precio']:.2f}")
            c4.write(f"**Q{subtotal:,.2f}**")
            if c5.button("🗑", key=f"del_{i}", help="Quitar"):
                st.session_state.lineas.pop(i)
                st.rerun()

        # Total
        margen_bruto = total_venta - total_costo
        pct_margen   = (margen_bruto / total_venta * 100) if total_venta else 0

        st.markdown(f"""
        <div class='total-card'>
            <h3>Total del Pedido: Q{total_venta:,.2f}</h3>
            <small>Costo: Q{total_costo:,.2f} · Margen bruto: Q{margen_bruto:,.2f} ({pct_margen:.1f}%)</small>
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("← Cambiar cliente", type="secondary"):
                st.session_state.paso = 1
                st.rerun()
        with col2:
            if st.button("Revisar y Confirmar →", type="primary"):
                st.session_state.paso = 3
                st.rerun()
    else:
        st.info("Agregá al menos un producto para continuar.")
        if st.button("← Volver", type="secondary"):
            st.session_state.paso = 1
            st.rerun()


# ── PASO 3: CONFIRMACIÓN Y GUARDADO ──────────────────────────────────────────
def _paso_confirmar():
    cliente = st.session_state.cliente
    fecha   = st.session_state.fecha_entrega
    items   = st.session_state.lineas

    st.subheader("✅ Confirmar Pedido")

    # Resumen cliente
    st.markdown(f"""
    <div class='cliente-card'>
        👤 <b>{cliente['nombre']}</b> — {cliente['empresa']}<br>
        💳 NIT: {cliente['nit']} &nbsp;|&nbsp;
        📍 {cliente['direccion']}<br>
        📅 Entrega: <b>{fecha.strftime('%d/%m/%Y')}</b>
        (Semana {fecha.isocalendar()[1]}) &nbsp;|&nbsp;
        📋 Crédito: {cliente['credito']} días
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # Tabla de productos
    st.markdown("**Detalle del pedido:**")
    h = st.columns([3.5, 1, 1.2, 1.2, 1.5])
    h[0].markdown("**Producto**")
    h[1].markdown("**Cant.**")
    h[2].markdown("**Precio**")
    h[3].markdown("**Costo**")
    h[4].markdown("**Subtotal**")

    total_venta = total_costo = 0
    for item in items:
        subtotal    = item["cantidad"] * item["precio"]
        costo_linea = item["cantidad"] * item["costo"]
        total_venta += subtotal
        total_costo += costo_linea

        r = st.columns([3.5, 1, 1.2, 1.2, 1.5])
        r[0].write(item["nombre"])
        r[1].write(f"{item['cantidad']} {item['unidad']}")
        r[2].write(f"Q{item['precio']:.2f}")
        r[3].write(f"Q{item['costo']:.2f}")
        r[4].write(f"**Q{subtotal:,.2f}**")

    st.divider()

    # Métricas finales
    margen_bruto = total_venta - total_costo
    pct_margen   = (margen_bruto / total_venta * 100) if total_venta else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("💰 Total Venta",    f"Q{total_venta:,.2f}")
    c2.metric("📦 Total Costo",    f"Q{total_costo:,.2f}")
    c3.metric("📈 Margen Bruto",   f"Q{margen_bruto:,.2f}",
              delta=f"{pct_margen:.1f}%")

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Editar productos", type="secondary"):
            st.session_state.paso = 2
            st.rerun()
    with col2:
        if st.button("💾 Guardar Pedido en Excel", type="primary"):
            with st.spinner("⏳ Guardando en Google Drive..."):
                try:
                    n = guardar_pedido(cliente, fecha, items)
                    st.session_state.filas_guardadas = n
                    st.session_state.guardado_ok     = True
                    st.session_state.paso            = 4
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al guardar: {e}")
                    st.caption("Verificá tu conexión a internet e intentá de nuevo.")


# ── PASO 4: ÉXITO ─────────────────────────────────────────────────────────────
def _paso_exito():
    cliente = st.session_state.cliente
    fecha   = st.session_state.fecha_entrega
    items   = st.session_state.lineas
    n       = st.session_state.filas_guardadas
    total   = sum(i["cantidad"] * i["precio"] for i in items)

    st.success("### 🎉 ¡Pedido guardado exitosamente!")
    st.balloons()

    st.markdown(f"""
    <div class='cliente-card'>
        👤 <b>{cliente['nombre']}</b><br>
        📅 Entrega: {fecha.strftime('%d/%m/%Y')}<br>
        🛒 {len(items)} productos · {n} líneas guardadas<br>
        💰 Total: <b>Q{total:,.2f}</b>
    </div>
    """, unsafe_allow_html=True)

    st.info(
        "⚠️ **Recordatorio:** Abrí el Excel y **actualizá las tablas dinámicas** "
        "(Datos → Actualizar todo) para ver el nuevo pedido en tus reportes."
    )

    st.divider()
    if st.button("➕ Ingresar otro pedido", type="primary"):
        _reset()
        st.rerun()


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    # Logo y título
    st.markdown("## 🥬 Rio Veggi — Pedidos")

    # Indicador de pasos (solo en pasos 1-3)
    if st.session_state.paso in (1, 2, 3):
        _mostrar_pasos()

    # Router de pasos
    if   st.session_state.paso == 1: _paso_cliente()
    elif st.session_state.paso == 2: _paso_productos()
    elif st.session_state.paso == 3: _paso_confirmar()
    elif st.session_state.paso == 4: _paso_exito()

if __name__ == "__main__":
    main()
