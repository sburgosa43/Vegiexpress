"""
modulo_gestion.py — Revisar y Modificar Pedidos
Sub-menú: Revisar Pedidos | Modificar Pedido
"""
import streamlit as st
import pandas as pd
from excel_helper import (leer_pedidos, cancelar_pedido, restaurar_pedido,
                           editar_linea)
from data_helper import cargar_productos


# ── FILTROS COMPARTIDOS ───────────────────────────────────────────────────────
def _aplicar_filtros(todos: list, sufijo: str = "") -> dict:
    """
    Renderiza los 5 filtros y retorna pedidos agrupados por Unico.
    sufijo: para evitar key collision entre las dos pestañas.
    """
    años_disp    = sorted({str(p["año"])  for p in todos if p["año"]},  reverse=True)
    sems_disp    = sorted({p["semana"]    for p in todos if p["semana"]})
    fechas_disp  = sorted(
        {p["fecha"].strftime("%d/%m/%Y") for p in todos if p["fecha"]},
        reverse=True,
    )
    clientes_disp = sorted({p["cliente"] for p in todos if p["cliente"]})

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        sel_años = st.multiselect("Año",     años_disp,    key=f"g_años{sufijo}",
                                   placeholder="Todos")
    with c2:
        sel_sems = st.multiselect("Semana",  [str(s) for s in sems_disp],
                                   key=f"g_sems{sufijo}", placeholder="Todas")
    with c3:
        sel_fec  = st.multiselect("Fecha",   fechas_disp,  key=f"g_fec{sufijo}",
                                   placeholder="Todas")
    with c4:
        sel_clis = st.multiselect("Cliente", clientes_disp, key=f"g_clis{sufijo}",
                                   placeholder="Todos")
    with c5:
        sel_est  = st.selectbox("Estado", ["Todos", "Pendiente", "Cancelado"],
                                 key=f"g_est{sufijo}")

    # Aplicar filtros
    f = todos
    if sel_años:
        f = [p for p in f if str(p["año"]) in sel_años]
    if sel_sems:
        f = [p for p in f if str(p["semana"]) in sel_sems]
    if sel_fec:
        f = [p for p in f if p["fecha"] and
             p["fecha"].strftime("%d/%m/%Y") in sel_fec]
    if sel_clis:
        f = [p for p in f if p["cliente"] in sel_clis]

    # Agrupar por Unico
    grupos: dict = {}
    for p in f:
        grupos.setdefault(p["unico"], []).append(p)

    # Filtro de estado
    if sel_est != "Todos":
        grupos = {
            u: ls for u, ls in grupos.items()
            if (sel_est == "Cancelado") == all(l["status"] == "Cancelado" for l in ls)
        }

    return dict(sorted(
        grupos.items(),
        key=lambda x: (x[1][0]["año"] or 0, x[1][0]["semana"] or 0),
        reverse=True,
    ))


def _label_pedido(unico: str, lineas: list) -> str:
    l0 = lineas[0]
    total = sum(l["total"] or 0 for l in lineas)
    est   = "🔴" if all(l["status"] == "Cancelado" for l in lineas) else "🟢"
    fecha = l0["fecha"].strftime("%d/%m/%Y") if l0["fecha"] else "—"
    return (f"{est}  {fecha}  ·  {l0['cliente']}  "
            f"·  Sem {l0['semana']}/{l0['año']}  "
            f"·  {len(lineas)} prod  ·  Q{total:,.2f}")


# ── SUB-MÓDULO: REVISAR PEDIDOS ───────────────────────────────────────────────
def _revisar(todos: list):
    grupos = _aplicar_filtros(todos, sufijo="_rev")

    if not grupos:
        st.warning("No hay pedidos con esos filtros.")
        return

    st.divider()

    # Multiselect de pedidos
    opciones = {u: _label_pedido(u, ls) for u, ls in grupos.items()}
    sel = st.multiselect(
        "Pedidos a revisar (podés elegir más de uno)",
        list(opciones.keys()),
        format_func=lambda u: opciones[u],
        key="rev_sel",
        placeholder="Seleccioná uno o más pedidos...",
    )

    if not sel:
        st.info("Seleccioná al menos un pedido para ver el detalle.")
        return

    for unico in sel:
        lineas = grupos[unico]
        l0     = lineas[0]
        total  = sum(l["total"] or 0 for l in lineas)
        est    = all(l["status"] == "Cancelado" for l in lineas)

        with st.expander(
            f"{'🔴' if est else '🟢'}  **{l0['cliente']}**  ·  "
            f"{l0['fecha'].strftime('%d/%m/%Y') if l0['fecha'] else '—'}  ·  "
            f"Sem {l0['semana']}/{l0['año']}",
            expanded=True,
        ):
            hdr = st.columns([4, 1.2, 1.5, 1.5, 1.5])
            hdr[0].markdown("**Producto**"); hdr[1].markdown("**Cant.**")
            hdr[2].markdown("**Precio**");   hdr[3].markdown("**Total**")
            hdr[4].markdown("**Estado**")
            for l in lineas:
                r = st.columns([4, 1.2, 1.5, 1.5, 1.5])
                r[0].write(l["producto"]); r[1].write(l["cantidad"])
                r[2].write(f"Q{l['precio']:,.2f}" if l["precio"] else "—")
                r[3].write(f"Q{l['total']:,.2f}"  if l["total"]  else "—")
                r[4].write(l["status"])
            st.markdown(
                f"<div style='text-align:right;font-weight:bold'>"
                f"Total: Q{total:,.2f}</div>", unsafe_allow_html=True)


# ── SUB-MÓDULO: MODIFICAR PEDIDO ──────────────────────────────────────────────
def _modificar(todos: list):
    grupos = _aplicar_filtros(todos, sufijo="_mod")

    if not grupos:
        st.warning("No hay pedidos con esos filtros.")
        return

    st.divider()

    opciones = {u: _label_pedido(u, ls) for u, ls in grupos.items()}
    sel = st.multiselect(
        "Pedidos a modificar (podés elegir más de uno)",
        list(opciones.keys()),
        format_func=lambda u: opciones[u],
        key="mod_sel",
        placeholder="Seleccioná uno o más pedidos...",
    )

    if not sel:
        st.info("Seleccioná al menos un pedido para modificarlo.")
        return

    # Catálogo de productos para el selectbox
    prods_lista = [""] + [p["nombre"] for p in cargar_productos(False)]

    for unico in sel:
        lineas   = grupos[unico]
        l0       = lineas[0]
        cancelado = all(l["status"] == "Cancelado" for l in lineas)
        total    = sum(l["total"] or 0 for l in lineas)

        with st.expander(
            f"{'🔴' if cancelado else '🟢'}  **{l0['cliente']}**  ·  "
            f"{l0['fecha'].strftime('%d/%m/%Y') if l0['fecha'] else '—'}  ·  "
            f"Sem {l0['semana']}/{l0['año']}  ·  Q{total:,.2f}",
            expanded=True,
        ):
            # ── Acción sobre el pedido completo ───────────────────────────────
            if not cancelado:
                if st.button("🔴 Cancelar pedido completo",
                             key=f"mod_cancel_{unico}", type="secondary"):
                    with st.spinner("Cancelando..."):
                        cancelar_pedido(unico)
                    st.success("Pedido cancelado."); st.rerun()
            else:
                if st.button("🟢 Restaurar a Pendiente",
                             key=f"mod_rest_{unico}", type="secondary"):
                    with st.spinner("Restaurando..."):
                        restaurar_pedido(unico)
                    st.success("Pedido restaurado."); st.rerun()

            # ── Edición línea por línea ───────────────────────────────────────
            if not cancelado:
                st.markdown("**Editar líneas del pedido:**")
                st.caption("El precio aquí es puntual para este pedido "
                           "(descuento o ajuste de costo). No modifica el catálogo.")

                for linea in lineas:
                    uid_l = f"{unico}_{linea['row_num']}"
                    with st.container():
                        st.markdown(f"---\n**{linea['producto']}**")
                        ec1, ec2, ec3, ec4 = st.columns([3, 1.5, 1.5, 1.2])

                        with ec1:
                            prod_nuevo = st.selectbox(
                                "Producto",
                                prods_lista,
                                index=prods_lista.index(linea["producto"])
                                      if linea["producto"] in prods_lista else 0,
                                key=f"mod_prod_{uid_l}",
                            )
                        with ec2:
                            cant_nueva = st.number_input(
                                "Cantidad",
                                min_value=0.0,
                                value=float(linea["cantidad"] or 0),
                                step=0.5,
                                key=f"mod_cant_{uid_l}",
                            )
                        with ec3:
                            precio_nuevo = st.number_input(
                                "Precio (Q)",
                                min_value=0.0,
                                value=float(linea["precio"] or 0),
                                step=0.50,
                                key=f"mod_prec_{uid_l}",
                                help="Precio puntual para este pedido únicamente",
                            )
                        with ec4:
                            st.markdown("&nbsp;", unsafe_allow_html=True)  # spacer
                            if st.button("💾 Guardar",
                                         key=f"mod_save_{uid_l}", type="primary"):
                                cambios = {}
                                if prod_nuevo and prod_nuevo != linea["producto"]:
                                    cambios["nuevo_producto"] = prod_nuevo
                                if cant_nueva != float(linea["cantidad"] or 0):
                                    cambios["nueva_cantidad"] = cant_nueva
                                if precio_nuevo != float(linea["precio"] or 0):
                                    cambios["nuevo_precio"] = precio_nuevo

                                if cambios:
                                    with st.spinner("Guardando..."):
                                        editar_linea(linea["row_num"], **cambios)
                                    st.success("✅ Línea actualizada.")
                                    st.rerun()
                                else:
                                    st.info("No hay cambios para guardar.")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def mostrar():
    st.markdown("## 📋 Gestión de Pedidos")

    with st.spinner("Cargando pedidos..."):
        todos = leer_pedidos()

    if not todos:
        st.info("No hay pedidos registrados aún.")
        return

    tab_rev, tab_mod = st.tabs(["🔍 Revisar Pedidos", "✏️ Modificar Pedido"])

    with tab_rev:
        _revisar(todos)

    with tab_mod:
        _modificar(todos)
