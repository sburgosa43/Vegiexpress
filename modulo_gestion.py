"""
modulo_gestion.py — Historial de pedidos, edición y cancelación
UX: Filtros → Tabla resumen → Seleccionar pedido → Ver detalle + acciones
"""
import streamlit as st
import pandas as pd
from excel_helper import leer_pedidos, cancelar_pedido, restaurar_pedido, editar_cantidad_linea


def mostrar():
    st.markdown("## 📋 Gestión de Pedidos")

    # ── Cargar datos ──────────────────────────────────────────────────────────
    with st.spinner("Cargando pedidos..."):
        todos = leer_pedidos()

    if not todos:
        st.info("No hay pedidos registrados aún.")
        return

    # ── FILTROS ───────────────────────────────────────────────────────────────
    st.markdown("#### 🔍 Filtros")
    f1, f2, f3, f4 = st.columns(4)

    clientes_lista = ["Todos"] + sorted({p["cliente"] for p in todos if p["cliente"]})
    años_lista     = ["Todos"] + sorted({str(p["año"]) for p in todos if p["año"]},
                                        reverse=True)

    with f1:
        fil_cliente = st.selectbox("Cliente", clientes_lista, key="g_cli")
    with f2:
        fil_año = st.selectbox("Año", años_lista, key="g_año")
    with f3:
        fil_semana = st.number_input("Semana (0 = todas)", min_value=0,
                                      max_value=53, value=0, step=1, key="g_sem")
    with f4:
        fil_status = st.selectbox("Estado", ["Todos", "Pendiente", "Cancelado"],
                                   key="g_status")

    # ── Aplicar filtros a nivel de línea ──────────────────────────────────────
    filtrados = todos
    if fil_cliente != "Todos":
        filtrados = [p for p in filtrados if p["cliente"] == fil_cliente]
    if fil_año != "Todos":
        filtrados = [p for p in filtrados if str(p["año"]) == fil_año]
    if fil_semana > 0:
        filtrados = [p for p in filtrados if p["semana"] == fil_semana]

    # ── Agrupar por Unico ─────────────────────────────────────────────────────
    grupos: dict = {}
    for p in filtrados:
        u = p["unico"]
        if u not in grupos:
            grupos[u] = []
        grupos[u].append(p)

    # Filtrar por estado del pedido completo
    if fil_status != "Todos":
        grupos_f = {}
        for u, lineas in grupos.items():
            status_g = ("Cancelado"
                        if all(l["status"] == "Cancelado" for l in lineas)
                        else "Pendiente")
            if status_g == fil_status:
                grupos_f[u] = lineas
        grupos = grupos_f

    if not grupos:
        st.warning("No hay pedidos con esos filtros.")
        return

    # Ordenar por fecha descendente
    grupos_ord = sorted(
        grupos.items(),
        key=lambda x: (x[1][0]["año"] or 0, x[1][0]["semana"] or 0,
                        str(x[1][0]["fecha"] or "")),
        reverse=True,
    )

    # ── TABLA RESUMEN ─────────────────────────────────────────────────────────
    st.divider()
    st.markdown(f"**{len(grupos_ord)} pedidos encontrados**")

    resumen_rows = []
    for unico, lineas in grupos_ord:
        l0        = lineas[0]
        total     = sum((l["total"] or 0) for l in lineas)
        status_g  = ("Cancelado"
                     if all(l["status"] == "Cancelado" for l in lineas)
                     else "Pendiente")
        fecha_str = l0["fecha"].strftime("%d/%m/%Y") if l0["fecha"] else "—"
        resumen_rows.append({
            "unico":   unico,
            "Fecha":   fecha_str,
            "Cliente": l0["cliente"],
            "Sem":     f"{l0['semana']}/{l0['año']}",
            "Productos": len(lineas),
            "Total (Q)": f"Q{total:,.2f}",
            "Estado":  "🔴 Cancelado" if status_g == "Cancelado" else "🟢 Pendiente",
        })

    df_res = pd.DataFrame(resumen_rows).drop(columns=["unico"])
    st.dataframe(df_res, use_container_width=True, hide_index=True)

    # ── SELECTOR DE PEDIDO ────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Seleccioná un pedido para ver el detalle")

    opciones_label = {
        unico: (
            f"{lineas[0]['fecha'].strftime('%d/%m/%Y') if lineas[0]['fecha'] else '—'}  "
            f"· {lineas[0]['cliente']}  "
            f"· Sem {lineas[0]['semana']}  "
            f"· {len(lineas)} productos"
        )
        for unico, lineas in grupos_ord
    }

    unico_sel = st.selectbox(
        "Pedido",
        list(opciones_label.keys()),
        format_func=lambda u: opciones_label[u],
        key="g_sel_pedido",
    )

    # ── DETALLE DEL PEDIDO SELECCIONADO ──────────────────────────────────────
    if unico_sel:
        lineas_sel = grupos[unico_sel]
        l0         = lineas_sel[0]
        total_sel  = sum((l["total"] or 0) for l in lineas_sel)
        status_g   = ("Cancelado"
                      if all(l["status"] == "Cancelado" for l in lineas_sel)
                      else "Pendiente")
        color_badge = "🔴 Cancelado" if status_g == "Cancelado" else "🟢 Pendiente"

        st.markdown(f"""
        <div style='background:#f1f8f1;border-left:4px solid #2e7d32;border-radius:6px;
                    padding:10px 16px;margin:8px 0;font-size:.94rem;line-height:1.7'>
        👤 <b>{l0['cliente']}</b> &nbsp;·&nbsp;
        📅 {l0['fecha'].strftime('%d/%m/%Y') if l0['fecha'] else '—'} &nbsp;·&nbsp;
        📌 Semana {l0['semana']}/{l0['año']} &nbsp;·&nbsp;
        {color_badge}
        </div>
        """, unsafe_allow_html=True)

        # Tabla de productos
        st.markdown("**Líneas del pedido:**")
        hdr = st.columns([4, 1.2, 1.5, 1.5, 1.5])
        hdr[0].markdown("**Producto**")
        hdr[1].markdown("**Cant.**")
        hdr[2].markdown("**Precio**")
        hdr[3].markdown("**Total**")
        hdr[4].markdown("**Estado**")

        for l in lineas_sel:
            r = st.columns([4, 1.2, 1.5, 1.5, 1.5])
            r[0].write(l["producto"])
            r[1].write(l["cantidad"])
            r[2].write(f"Q{l['precio']:,.2f}" if l["precio"] else "—")
            r[3].write(f"Q{l['total']:,.2f}"  if l["total"]  else "—")
            r[4].write(l["status"])

        st.markdown(
            f"<div style='text-align:right;font-size:1rem;font-weight:bold;"
            f"margin-top:4px'>Total: Q{total_sel:,.2f}</div>",
            unsafe_allow_html=True,
        )
        st.divider()

        # ── ACCIONES ─────────────────────────────────────────────────────────
        col_acc, col_edit = st.columns([1, 2])

        with col_acc:
            st.markdown("**Acción sobre el pedido:**")
            if status_g == "Pendiente":
                if st.button("🔴 Cancelar pedido completo",
                             key="btn_cancelar", type="secondary"):
                    with st.spinner("Cancelando..."):
                        cancelar_pedido(unico_sel)
                    st.success("✅ Pedido cancelado.")
                    st.rerun()
            else:
                if st.button("🟢 Restaurar a Pendiente",
                             key="btn_restaurar", type="secondary"):
                    with st.spinner("Restaurando..."):
                        restaurar_pedido(unico_sel)
                    st.success("✅ Pedido restaurado.")
                    st.rerun()

        with col_edit:
            if status_g == "Pendiente":
                st.markdown("**Editar cantidad de una línea:**")
                nombres_lineas = [l["producto"] for l in lineas_sel]
                prod_edit = st.selectbox("Producto", nombres_lineas,
                                          key="g_prod_edit")
                linea_e   = next(l for l in lineas_sel if l["producto"] == prod_edit)
                nueva_c   = st.number_input(
                    "Nueva cantidad",
                    min_value=0.0,
                    value=float(linea_e["cantidad"] or 0),
                    step=0.5,
                    key=f"g_cant_{unico_sel}_{prod_edit}",
                )
                if st.button("💾 Guardar cantidad", key="btn_guardar_cant",
                             type="primary"):
                    with st.spinner("Guardando..."):
                        editar_cantidad_linea(linea_e["row_num"], nueva_c)
                    st.success(f"✅ Cantidad actualizada a {nueva_c}.")
                    st.rerun()
            else:
                st.info("Restaurá el pedido para poder editar cantidades.")
