"""
modulo_pedidos_entrantes.py — Revisión y aprobación de pedidos del catálogo cliente.
"""
import streamlit as st
import pandas as pd
from datetime import date


def mostrar():
    st.markdown("## 📥 Pedidos Entrantes")
    if st.button("🏠 Inicio", key="btn_home_pe", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    try:
        from sheets_helper import leer_pedidos_entrantes, actualizar_status
    except Exception as e:
        st.error(f"Error conectando con Google Sheets: {e}")
        st.info("Verificá que PEDIDOS_SHEET_ID esté configurado en Secrets.")
        return

    with st.spinner("Cargando pedidos entrantes..."):
        pedidos = leer_pedidos_entrantes()

    if not pedidos:
        st.info("No hay pedidos entrantes en este momento.")
        return

    df = pd.DataFrame(pedidos)

    # Filtros
    col1, col2 = st.columns(2)
    status_filter = col1.selectbox("Estado", ["Pendiente", "Confirmado",
                                               "Rechazado", "Todos"],
                                    key="pe_status")
    rest_filter   = col2.selectbox("Restaurante",
                                    ["Todos"] + sorted(df["Restaurante"].unique().tolist()),
                                    key="pe_rest")

    filtrado = df.copy()
    if status_filter != "Todos":
        filtrado = filtrado[filtrado["Status"] == status_filter]
    if rest_filter != "Todos":
        filtrado = filtrado[filtrado["Restaurante"] == rest_filter]

    if filtrado.empty:
        st.info("Sin pedidos con esos filtros.")
        return

    # Agrupar por pedido (Timestamp + Restaurante)
    grupos = filtrado.groupby(["Timestamp", "Restaurante", "Fecha_Entrega",
                                "Area", "Status"], sort=False)

    st.markdown(f"**{len(grupos)} pedido(s) encontrado(s)**")

    for (ts, rest, fecha, area, status), grupo in grupos:
        total = (grupo["Cantidad"] * grupo["Precio"]).sum()
        color = {"Pendiente": "#FFF3CD", "Confirmado": "#D4EDDA",
                 "Rechazado": "#F8D7DA"}.get(status, "#F5F5F5")
        icono = {"Pendiente": "⏳", "Confirmado": "✅",
                 "Rechazado": "❌"}.get(status, "📋")

        with st.expander(
            f"{icono} **{rest}** · {fecha} · {area} · "
            f"Q{total:,.2f} · {status}",
            expanded=(status == "Pendiente")
        ):
            # Tabla de productos
            df_show = grupo[["Producto", "Cantidad", "Unidad", "Precio"]].copy()
            df_show["Total"] = df_show["Cantidad"] * df_show["Precio"]
            df_show["Total"] = df_show["Total"].apply(lambda x: f"Q{x:,.2f}")
            df_show["Precio"]= df_show["Precio"].apply(lambda x: f"Q{x:,.2f}")
            st.dataframe(df_show, hide_index=True, use_container_width=True,
                         column_config={
                             "Producto":  st.column_config.TextColumn(width="large"),
                             "Cantidad":  st.column_config.NumberColumn(width="small"),
                             "Unidad":    st.column_config.TextColumn(width="small"),
                             "Precio":    st.column_config.TextColumn(width="small"),
                             "Total":     st.column_config.TextColumn(width="small"),
                         })

            notas = grupo["Notas"].iloc[0] if "Notas" in grupo.columns else ""
            if notas:
                st.caption(f"📝 {notas}")

            # Botones de acción (solo si pendiente)
            if status == "Pendiente":
                ba, br, bp = st.columns(3)

                with ba:
                    if st.button("✅ Aprobar", key=f"apr_{ts}_{rest}",
                                 type="primary"):
                        # Obtener índices en el Sheet (1-indexed, +1 por header)
                        indices = (grupo.index + 2).tolist()  # +2: header+0-index
                        with st.spinner("Actualizando..."):
                            actualizar_status(indices, "Confirmado")
                        st.success("✅ Pedido confirmado.")
                        st.rerun()

                with br:
                    if st.button("❌ Rechazar", key=f"rch_{ts}_{rest}",
                                 type="secondary"):
                        indices = (grupo.index + 2).tolist()
                        with st.spinner("Actualizando..."):
                            actualizar_status(indices, "Rechazado")
                        st.warning("❌ Pedido rechazado.")
                        st.rerun()

                with bp:
                    st.caption(f"Recibido: {ts[:16]}")
