"""
modulo_gestion.py — Historial de pedidos, edicion de cantidades, cancelacion
"""
import streamlit as st
import pandas as pd
from excel_helper import leer_pedidos, cancelar_pedido, restaurar_pedido, editar_cantidad_linea


def mostrar():
    st.markdown("## 📋 Gestión de Pedidos")

    pedidos = leer_pedidos()
    if not pedidos:
        st.info("No hay pedidos registrados aún.")
        return

    # ── FILTROS ───────────────────────────────────────────────────────────────
    with st.expander("🔍 Filtros", expanded=True):
        col1, col2, col3 = st.columns(3)

        clientes_unicos = sorted({p["cliente"] for p in pedidos if p["cliente"]})
        with col1:
            filtro_cliente = st.selectbox("Cliente", ["Todos"] + clientes_unicos,
                                          key="gest_cli")
        años_unicos = sorted({p["año"] for p in pedidos if p["año"]}, reverse=True)
        with col2:
            filtro_año = st.selectbox("Año", ["Todos"] + [str(a) for a in años_unicos],
                                      key="gest_año")
        with col3:
            filtro_status = st.selectbox("Estado", ["Todos", "Pendiente", "Cancelado"],
                                         key="gest_status")

    # Aplicar filtros
    filtrados = pedidos
    if filtro_cliente != "Todos":
        filtrados = [p for p in filtrados if p["cliente"] == filtro_cliente]
    if filtro_año != "Todos":
        filtrados = [p for p in filtrados if str(p["año"]) == filtro_año]
    if filtro_status != "Todos":
        filtrados = [p for p in filtrados if p["status"] == filtro_status]

    if not filtrados:
        st.warning("No hay pedidos con esos filtros.")
        return

    # ── AGRUPAR POR UNICO (= pedido completo) ─────────────────────────────────
    grupos: dict = {}
    for p in filtrados:
        u = p["unico"]
        if u not in grupos:
            grupos[u] = []
        grupos[u].append(p)

    # Ordenar por fecha descendente
    grupos_ordenados = sorted(
        grupos.items(),
        key=lambda x: x[1][0]["fecha"] if x[1][0]["fecha"] else "",
        reverse=True,
    )

    st.markdown(f"**{len(grupos_ordenados)} pedidos encontrados**")
    st.divider()

    # ── MOSTRAR CADA PEDIDO ───────────────────────────────────────────────────
    for unico, lineas in grupos_ordenados:
        linea0    = lineas[0]
        fecha_str = linea0["fecha"].strftime("%d/%m/%Y") if linea0["fecha"] else "—"
        total_est = sum((l["total"] or 0) for l in lineas)
        status_g  = "Cancelado" if all(l["status"] == "Cancelado" for l in lineas) else "Pendiente"
        color     = "#ffebee" if status_g == "Cancelado" else "#f1f8f1"
        badge     = "🔴 Cancelado" if status_g == "Cancelado" else "🟢 Pendiente"

        with st.expander(
            f"{fecha_str} · **{linea0['cliente']}** · "
            f"Sem {linea0['semana']}/{linea0['año']} · "
            f"{len(lineas)} productos · Q{total_est:,.2f} · {badge}",
            expanded=False,
        ):
            # Detalle de lineas
            hdr = st.columns([3.5, 1, 1.5, 1.5, 1.5])
            hdr[0].markdown("**Producto**")
            hdr[1].markdown("**Cant.**")
            hdr[2].markdown("**Precio**")
            hdr[3].markdown("**Total**")
            hdr[4].markdown("**Estado**")

            for linea in lineas:
                cols = st.columns([3.5, 1, 1.5, 1.5, 1.5])
                cols[0].write(linea["producto"])
                cols[1].write(linea["cantidad"])
                cols[2].write(f"Q{linea['precio']:,.2f}" if linea["precio"] else "—")
                cols[3].write(f"Q{linea['total']:,.2f}" if linea["total"] else "—")
                cols[4].write(linea["status"])

            st.divider()

            # ── Editar cantidad (solo si pendiente) ───────────────────────────
            if status_g == "Pendiente":
                with st.expander("✏️ Editar cantidad de una línea"):
                    nombres_prods = [l["producto"] for l in lineas]
                    prod_sel = st.selectbox("Producto a editar", nombres_prods,
                                            key=f"edit_prod_{unico}")
                    linea_sel = next(l for l in lineas if l["producto"] == prod_sel)
                    nueva_cant = st.number_input(
                        "Nueva cantidad",
                        min_value=0.0,
                        value=float(linea_sel["cantidad"] or 0),
                        step=0.5,
                        key=f"edit_cant_{unico}_{prod_sel}",
                    )
                    if st.button("💾 Guardar cantidad", key=f"save_cant_{unico}"):
                        with st.spinner("Guardando..."):
                            editar_cantidad_linea(linea_sel["row_num"], nueva_cant)
                        st.success(f"✅ Cantidad actualizada a {nueva_cant}")
                        st.rerun()

            # ── Acciones del pedido ───────────────────────────────────────────
            col_a, col_b = st.columns(2)
            with col_a:
                if status_g == "Pendiente":
                    if st.button("🔴 Cancelar pedido", key=f"cancel_{unico}",
                                 type="secondary"):
                        with st.spinner("Cancelando..."):
                            cancelar_pedido(unico)
                        st.success("Pedido cancelado.")
                        st.rerun()
                else:
                    if st.button("🟢 Restaurar pedido", key=f"restore_{unico}",
                                 type="secondary"):
                        with st.spinner("Restaurando..."):
                            restaurar_pedido(unico)
                        st.success("Pedido restaurado a Pendiente.")
                        st.rerun()
