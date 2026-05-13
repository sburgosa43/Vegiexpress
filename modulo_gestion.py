"""
modulo_gestion.py — Historial de pedidos, edición y cancelación
"""
import streamlit as st
from datetime import date
from excel_helper import leer_pedidos, cancelar_pedido, restaurar_pedido, editar_cantidad_linea


def mostrar():
    st.markdown("## 📋 Gestión de Pedidos")

    with st.spinner("Cargando pedidos..."):
        todos = leer_pedidos()

    if not todos:
        st.info("No hay pedidos registrados aún.")
        return

    # ── FILTROS ───────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)

    clientes_lista = ["Todos"] + sorted({p["cliente"] for p in todos if p["cliente"]})
    with c1:
        fil_cliente = st.selectbox("Cliente", clientes_lista, key="g_cli")
    with c2:
        fil_fecha = st.date_input("Fecha entrega", value=None, key="g_fecha")
    with c3:
        fil_semana = st.number_input("Semana (0=todas)", min_value=0,
                                      max_value=53, value=0, step=1, key="g_sem")
    with c4:
        años_lista = ["Todos"] + sorted({str(p["año"]) for p in todos if p["año"]}, reverse=True)
        fil_año = st.selectbox("Año", años_lista, key="g_año")
    with c5:
        fil_status = st.selectbox("Estado", ["Todos", "Pendiente", "Cancelado"], key="g_st")

    # ── Aplicar filtros ───────────────────────────────────────────────────────
    filtrados = todos
    if fil_cliente != "Todos":
        filtrados = [p for p in filtrados if p["cliente"] == fil_cliente]
    if fil_fecha:
        filtrados = [p for p in filtrados if p["fecha"] == fil_fecha]
    if fil_semana > 0:
        filtrados = [p for p in filtrados if p["semana"] == fil_semana]
    if fil_año != "Todos":
        filtrados = [p for p in filtrados if str(p["año"]) == fil_año]

    # Agrupar por Unico
    grupos: dict = {}
    for p in filtrados:
        grupos.setdefault(p["unico"], []).append(p)

    if fil_status != "Todos":
        grupos = {
            u: ls for u, ls in grupos.items()
            if (fil_status == "Cancelado") == all(l["status"] == "Cancelado" for l in ls)
        }

    if not grupos:
        st.warning("No hay pedidos con esos filtros.")
        return

    grupos_ord = sorted(
        grupos.items(),
        key=lambda x: (x[1][0]["año"] or 0, x[1][0]["semana"] or 0),
        reverse=True,
    )

    # ── SELECTOR ─────────────────────────────────────────────────────────────
    st.divider()
    opciones = {
        unico: (
            f"{ls[0]['fecha'].strftime('%d/%m/%Y') if ls[0]['fecha'] else '—'}"
            f"  ·  {ls[0]['cliente']}"
            f"  ·  Sem {ls[0]['semana']}/{ls[0]['año']}"
            f"  ·  {len(ls)} productos"
            f"  ·  {'🔴 Cancelado' if all(l['status']=='Cancelado' for l in ls) else '🟢 Pendiente'}"
        )
        for unico, ls in grupos_ord
    }

    unico_sel = st.selectbox(
        "Seleccioná un pedido",
        list(opciones.keys()),
        format_func=lambda u: opciones[u],
        key="g_sel",
    )

    # ── DETALLE ───────────────────────────────────────────────────────────────
    if not unico_sel:
        return

    lineas_sel = grupos[unico_sel]
    l0         = lineas_sel[0]
    total_sel  = sum((l["total"] or 0) for l in lineas_sel)
    cancelado  = all(l["status"] == "Cancelado" for l in lineas_sel)

    st.markdown(f"""
    <div style='background:#f1f8f1;border-left:4px solid #2e7d32;border-radius:6px;
                padding:8px 14px;margin:6px 0;font-size:.93rem'>
    👤 <b>{l0['cliente']}</b> &nbsp;·&nbsp;
    📅 {l0['fecha'].strftime('%d/%m/%Y') if l0['fecha'] else '—'} &nbsp;·&nbsp;
    Semana {l0['semana']}/{l0['año']} &nbsp;·&nbsp;
    {'🔴 Cancelado' if cancelado else '🟢 Pendiente'}
    </div>""", unsafe_allow_html=True)

    # Tabla compacta de productos
    hdr = st.columns([4, 1.2, 1.5, 1.5])
    hdr[0].markdown("**Producto**"); hdr[1].markdown("**Cant.**")
    hdr[2].markdown("**Precio**");   hdr[3].markdown("**Total**")
    for l in lineas_sel:
        r = st.columns([4, 1.2, 1.5, 1.5])
        r[0].write(l["producto"])
        r[1].write(l["cantidad"])
        r[2].write(f"Q{l['precio']:,.2f}" if l["precio"] else "—")
        r[3].write(f"Q{l['total']:,.2f}"  if l["total"]  else "—")

    st.markdown(
        f"<div style='text-align:right;font-weight:bold;margin:4px 0'>"
        f"Total: Q{total_sel:,.2f}</div>", unsafe_allow_html=True)
    st.divider()

    # ── ACCIONES ─────────────────────────────────────────────────────────────
    col_acc, col_edit = st.columns([1, 2])

    with col_acc:
        st.markdown("**Acción:**")
        if not cancelado:
            if st.button("🔴 Cancelar pedido", key="btn_cancel", type="secondary"):
                with st.spinner("Cancelando..."):
                    cancelar_pedido(unico_sel)
                st.success("Pedido cancelado."); st.rerun()
        else:
            if st.button("🟢 Restaurar pedido", key="btn_rest", type="secondary"):
                with st.spinner("Restaurando..."):
                    restaurar_pedido(unico_sel)
                st.success("Pedido restaurado."); st.rerun()

    with col_edit:
        if not cancelado:
            st.markdown("**Editar cantidad:**")
            prod_edit = st.selectbox("Producto", [l["producto"] for l in lineas_sel],
                                      key="g_pe")
            linea_e   = next(l for l in lineas_sel if l["producto"] == prod_edit)
            nueva_c   = st.number_input("Cantidad", min_value=0.0,
                                         value=float(linea_e["cantidad"] or 0),
                                         step=0.5, key=f"g_nc_{unico_sel}")
            if st.button("💾 Guardar", key="btn_gc", type="primary"):
                with st.spinner("Guardando..."):
                    editar_cantidad_linea(linea_e["row_num"], nueva_c)
                st.success(f"Cantidad actualizada a {nueva_c}."); st.rerun()
        else:
            st.info("Restaurá el pedido para editar cantidades.")
