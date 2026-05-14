"""
modulo_gestion.py — Gestión de Pedidos
Tabs: 📅 Semana Actual | 🔍 Revisar Pedidos | ✏️ Modificar Pedido
"""
import streamlit as st
from datetime import date
from excel_helper import (leer_pedidos, cancelar_pedido, restaurar_pedido, editar_linea)
from data_helper import cargar_productos, cargar_clientes
from pdf_helper import generar_envio, nombre_archivo


# ── FILTROS COMPARTIDOS ───────────────────────────────────────────────────────
def _aplicar_filtros(todos: list, sufijo: str = "") -> dict:
    años_disp     = sorted({str(p["año"])  for p in todos if p["año"]},  reverse=True)
    sems_disp     = sorted({str(p["semana"]) for p in todos if p["semana"]})
    fechas_disp   = sorted({p["fecha"].strftime("%d/%m/%Y") for p in todos if p["fecha"]},
                            reverse=True)
    clientes_disp = sorted({p["cliente"] for p in todos if p["cliente"]})

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        sel_años  = st.multiselect("Año",     años_disp,     key=f"g_años{sufijo}",  placeholder="Todos")
    with c2:
        sel_sems  = st.multiselect("Semana",  sems_disp,     key=f"g_sems{sufijo}",  placeholder="Todas")
    with c3:
        sel_fec   = st.multiselect("Fecha",   fechas_disp,   key=f"g_fec{sufijo}",   placeholder="Todas")
    with c4:
        sel_clis  = st.multiselect("Cliente", clientes_disp, key=f"g_clis{sufijo}",  placeholder="Todos")
    with c5:
        sel_est   = st.selectbox("Estado", ["Todos", "Pendiente", "Cancelado"], key=f"g_est{sufijo}")

    f = todos
    if sel_años:  f = [p for p in f if str(p["año"])     in sel_años]
    if sel_sems:  f = [p for p in f if str(p["semana"])  in sel_sems]
    if sel_fec:   f = [p for p in f if p["fecha"] and p["fecha"].strftime("%d/%m/%Y") in sel_fec]
    if sel_clis:  f = [p for p in f if p["cliente"]      in sel_clis]

    grupos: dict = {}
    for p in f:
        grupos.setdefault(p["unico"], []).append(p)

    if sel_est != "Todos":
        grupos = {
            u: ls for u, ls in grupos.items()
            if (sel_est == "Cancelado") == all(l["status"] == "Cancelado" for l in ls)
        }

    return dict(sorted(grupos.items(),
                        key=lambda x: (x[1][0]["año"] or 0, x[1][0]["semana"] or 0),
                        reverse=True))


def _label(unico, lineas):
    l0 = lineas[0]
    total = sum(l["total"] or 0 for l in lineas)
    est   = "🔴" if all(l["status"] == "Cancelado" for l in lineas) else "🟢"
    f     = l0["fecha"].strftime("%d/%m/%Y") if l0["fecha"] else "—"
    return f"{est}  {f}  ·  {l0['cliente']}  ·  Sem {l0['semana']}/{l0['año']}  ·  {len(lineas)} prod  ·  Q{total:,.2f}"


# ── COMPONENTE COMPARTIDO: LINEAS EDITABLES + PDF ─────────────────────────────
def _pedido_detalle(unico: str, lineas: list, clientes_map: dict,
                     sufijo: str, expanded: bool = False):
    """
    Expander con líneas editables de precio, guardado en Excel con historial y PDF.
    - precio_excel: precio actual en Excel (base para detectar cambios)
    - precio:       precio del catálogo (referencia visual)
    """
    from excel_helper import guardar_cambios_precio

    l0           = lineas[0]
    total_orig   = sum(l["total"] or 0 for l in lineas)
    cancelado    = all(l["status"] == "Cancelado" for l in lineas)
    fecha_ped    = l0["fecha"] if l0["fecha"] else date.today()
    cliente_info = clientes_map.get(l0["cliente"], {"nombre": l0["cliente"]})

    label_exp = (
        f"{'🔴' if cancelado else '🟢'}  **{l0['cliente']}**  ·  "
        f"{fecha_ped.strftime('%d/%m/%Y')}  ·  "
        f"Sem {l0['semana']}/{l0['año']}  ·  "
        f"{len(lineas)} productos  ·  Q{total_orig:,.2f}"
    )

    with st.expander(label_exp, expanded=expanded):
        # Encabezado tabla: mostrar precio catálogo vs precio Excel vs editable
        hdr = st.columns([4, 1.2, 1.6, 1.6, 1.6])
        hdr[0].markdown("**Producto**")
        hdr[1].markdown("**Cant.**")
        hdr[2].markdown("**Cat.**")
        hdr[3].markdown("**Precio (Q)**")
        hdr[4].markdown("**Subtotal**")

        lineas_pdf     = []
        cambios_lista  = []
        total_ed       = 0.0
        hay_cambios    = False

        for linea in lineas:
            k            = f"sa_p_{sufijo}_{unico}_{linea['row_num']}"
            precio_excel = float(linea.get("precio_excel") or linea.get("precio") or 0)
            precio_cat   = float(linea.get("precio") or 0)

            # Inicializar con el precio actual del Excel
            if k not in st.session_state:
                st.session_state[k] = precio_excel

            r = st.columns([4, 1.2, 1.6, 1.6, 1.6])
            r[0].write(linea["producto"])
            r[1].write(f"{linea['cantidad']}")
            r[2].markdown(
                f"<div style='padding-top:8px;color:#888;font-size:.85rem'>"
                f"Q{precio_cat:,.2f}</div>", unsafe_allow_html=True)

            precio_ed = r[3].number_input(
                "", min_value=0.0,
                value=float(st.session_state[k]),
                step=0.25, key=k,
                label_visibility="collapsed",
            )

            # Indicador visual de cambio respecto al Excel
            if abs(precio_ed - precio_excel) > 0.001:
                hay_cambios = True
                diff = precio_ed - precio_excel
                r[3].caption(f"{'▲' if diff > 0 else '▼'} Q{abs(diff):.2f} vs Excel")

            sub = float(linea["cantidad"] or 0) * precio_ed
            r[4].markdown(f"<div style='padding-top:8px;font-weight:bold'>"
                           f"Q{sub:,.2f}</div>", unsafe_allow_html=True)
            total_ed += sub

            lineas_pdf.append({**linea, "precio": precio_ed, "total": sub})
            cambios_lista.append({
                "row_num":         linea["row_num"],
                "cliente":         linea["cliente"],
                "producto":        linea["producto"],
                "precio_anterior": precio_excel,
                "precio_nuevo":    precio_ed,
                "semana":          linea["semana"],
                "año":             linea["año"],
                "unico":           unico,
            })

        st.markdown(
            f"<div style='text-align:right;font-weight:bold;margin:4px 0'>"
            f"Total: Q{total_ed:,.2f}</div>", unsafe_allow_html=True)

        if hay_cambios:
            st.caption("⚠️ Hay precios modificados respecto al Excel. "
                       "Guardá para actualizar el Excel y dejar registro en el historial.")
        st.divider()

        # ── Botones de acción ─────────────────────────────────────────────────
        col_save, col_pdf, col_acc = st.columns([2, 2, 2])

        with col_save:
            btn_label = "💾 Guardar cambios" if hay_cambios else "✅ Sin cambios"
            if st.button(btn_label, key=f"save_{sufijo}_{unico}",
                          type="primary" if hay_cambios else "secondary",
                          disabled=not hay_cambios):
                with st.spinner("Guardando en Excel y registrando historial..."):
                    n = guardar_cambios_precio(cambios_lista)
                st.success(f"✅ {n} precio(s) guardado(s). Historial actualizado.")
                st.rerun()

        with col_pdf:
            try:
                pdf_bytes = generar_envio(
                    cliente=cliente_info,
                    fecha=fecha_ped,
                    lineas=lineas_pdf,
                    unico=unico,
                )
                st.download_button(
                    label="📄 Descargar PDF",
                    data=pdf_bytes,
                    file_name=nombre_archivo(l0["cliente"], fecha_ped),
                    mime="application/pdf",
                    key=f"dl_{sufijo}_{unico}",
                    type="primary",
                )
            except Exception as e:
                st.error(f"Error generando PDF: {e}")

        with col_acc:
            if not cancelado:
                if st.button("🔴 Cancelar pedido", key=f"can_{sufijo}_{unico}",
                             type="secondary"):
                    with st.spinner("Cancelando..."):
                        cancelar_pedido(unico)
                    st.success("Pedido cancelado."); st.rerun()
            else:
                if st.button("🟢 Restaurar pedido", key=f"res_{sufijo}_{unico}",
                             type="secondary"):
                    with st.spinner("Restaurando..."):
                        restaurar_pedido(unico)
                    st.success("Pedido restaurado."); st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: SEMANA ACTUAL
# ══════════════════════════════════════════════════════════════════════════════
def _semana_actual(todos: list):
    hoy           = date.today()
    semana_act    = hoy.isocalendar()[1]
    año_act       = hoy.year

    pedidos_sem   = [p for p in todos
                     if p["semana"] == semana_act and p["año"] == año_act]

    st.markdown(
        f"**Semana {semana_act} de {año_act}** · "
        f"{hoy.strftime('%d/%m/%Y')}"
    )

    if not pedidos_sem:
        st.info(f"No hay pedidos registrados para la semana {semana_act}.")
        return

    # Agrupar y cargar clientes
    grupos: dict = {}
    for p in pedidos_sem:
        grupos.setdefault(p["unico"], []).append(p)

    clientes_map = {c["nombre"]: c for c in cargar_clientes()}

    # Separar por zona usando dos métodos para mayor cobertura:
    # 1) codigo_lugar del cliente (L03=Antigua, L04=Chimal)
    # 2) campo Direccion del pedido (igual que la fórmula Excel: "Antigua" o "Chimal")
    ant_chim, resto = {}, {}
    for unico, ls in grupos.items():
        l0 = ls[0]
        # Método 1: tabla de clientes
        cz  = clientes_map.get(l0["cliente"], {}).get("codigo_lugar", "")
        # Método 2: Direccion guardada en el pedido
        dir_ped = str(l0.get("direccion", "")).lower()
        es_ac   = (cz in ("L03", "L04") or
                   "antigua" in dir_ped or
                   "chimal"  in dir_ped)
        (ant_chim if es_ac else resto)[unico] = ls

    # Ordenar por fecha descendente
    def _ord(d):
        return dict(sorted(d.items(),
                    key=lambda x: str(x[1][0]["fecha"] or ""), reverse=True))

    ant_chim = _ord(ant_chim)
    resto    = _ord(resto)

    st.markdown(
        f"{len(grupos)} pedidos  ·  "
        f"{len(ant_chim)} Antigua/Chimal  ·  {len(resto)} Resto"
    )

    tab_ac, tab_re = st.tabs([
        f"🔖 Antigua & Chimal ({len(ant_chim)})",
        f"🌎 Resto ({len(resto)})",
    ])

    with tab_ac:
        if not ant_chim:
            st.info("No hay pedidos de Antigua o Chimal esta semana.")
        else:
            for unico, ls in ant_chim.items():
                _pedido_detalle(unico, ls, clientes_map, sufijo="ac")

    with tab_re:
        if not resto:
            st.info("No hay pedidos del resto de zonas esta semana.")
        else:
            for unico, ls in resto.items():
                _pedido_detalle(unico, ls, clientes_map, sufijo="re")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: REVISAR PEDIDOS
# ══════════════════════════════════════════════════════════════════════════════
def _revisar(todos: list):
    grupos = _aplicar_filtros(todos, sufijo="_rev")
    if not grupos:
        st.warning("No hay pedidos con esos filtros.")
        return

    clientes_map = {c["nombre"]: c for c in cargar_clientes()}
    st.divider()

    opciones = {u: _label(u, ls) for u, ls in grupos.items()}
    sel = st.multiselect(
        "Pedidos a revisar",
        list(opciones.keys()),
        format_func=lambda u: opciones[u],
        key="rev_sel",
        placeholder="Seleccioná uno o más pedidos...",
    )

    if not sel:
        st.info("Seleccioná al menos un pedido para ver el detalle.")
        return

    for unico in sel:
        _pedido_detalle(unico, grupos[unico], clientes_map,
                         sufijo="rv", expanded=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: MODIFICAR PEDIDO
# ══════════════════════════════════════════════════════════════════════════════
def _modificar(todos: list):
    grupos = _aplicar_filtros(todos, sufijo="_mod")
    if not grupos:
        st.warning("No hay pedidos con esos filtros.")
        return

    clientes_map = {c["nombre"]: c for c in cargar_clientes()}
    prods_lista  = [""] + [p["nombre"] for p in cargar_productos(False)]
    st.divider()

    opciones = {u: _label(u, ls) for u, ls in grupos.items()}
    sel = st.multiselect(
        "Pedidos a modificar",
        list(opciones.keys()),
        format_func=lambda u: opciones[u],
        key="mod_sel",
        placeholder="Seleccioná uno o más pedidos...",
    )

    if not sel:
        st.info("Seleccioná al menos un pedido para modificarlo.")
        return

    for unico in sel:
        lineas    = grupos[unico]
        l0        = lineas[0]
        cancelado = all(l["status"] == "Cancelado" for l in lineas)
        total     = sum(l["total"] or 0 for l in lineas)

        with st.expander(
            f"{'🔴' if cancelado else '🟢'}  **{l0['cliente']}**  ·  "
            f"{l0['fecha'].strftime('%d/%m/%Y') if l0['fecha'] else '—'}  ·  "
            f"Sem {l0['semana']}/{l0['año']}  ·  Q{total:,.2f}",
            expanded=True,
        ):
            if not cancelado:
                if st.button("🔴 Cancelar pedido completo",
                             key=f"mod_can_{unico}", type="secondary"):
                    with st.spinner("Cancelando..."):
                        cancelar_pedido(unico)
                    st.success("Pedido cancelado."); st.rerun()
            else:
                if st.button("🟢 Restaurar a Pendiente",
                             key=f"mod_res_{unico}", type="secondary"):
                    with st.spinner("Restaurando..."):
                        restaurar_pedido(unico)
                    st.success("Pedido restaurado."); st.rerun()

            if not cancelado:
                st.markdown("**Editar líneas:**")
                st.caption("El precio editado aquí SE GUARDA en el Excel "
                           "(solo para este pedido).")

                for linea in lineas:
                    uid_l = f"{unico}_{linea['row_num']}"
                    st.markdown(f"---\n**{linea['producto']}**")
                    ec1, ec2, ec3, ec4 = st.columns([3, 1.5, 1.5, 1.2])

                    with ec1:
                        prod_nuevo = ec1.selectbox(
                            "Producto",
                            prods_lista,
                            index=(prods_lista.index(linea["producto"])
                                   if linea["producto"] in prods_lista else 0),
                            key=f"mod_prod_{uid_l}",
                        )
                    cant_nueva   = ec2.number_input("Cantidad",   min_value=0.0,
                                                     value=float(linea["cantidad"] or 0),
                                                     step=0.5, key=f"mod_cant_{uid_l}")
                    precio_nuevo = ec3.number_input("Precio (Q)", min_value=0.0,
                                                     value=float(linea["precio"] or 0),
                                                     step=0.25, key=f"mod_prec_{uid_l}",
                                                     help="Solo afecta este pedido")
                    ec4.markdown("&nbsp;", unsafe_allow_html=True)
                    if ec4.button("💾", key=f"mod_save_{uid_l}",
                                   help="Guardar cambios en Excel"):
                        cambios = {}
                        if prod_nuevo   and prod_nuevo  != linea["producto"]:  cambios["nuevo_producto"] = prod_nuevo
                        if cant_nueva  != float(linea["cantidad"] or 0):       cambios["nueva_cantidad"] = cant_nueva
                        if precio_nuevo != float(linea["precio"]   or 0):       cambios["nuevo_precio"]   = precio_nuevo
                        if cambios:
                            with st.spinner("Guardando..."):
                                editar_linea(linea["row_num"], **cambios)
                            st.success("✅ Línea actualizada."); st.rerun()
                        else:
                            st.info("Sin cambios.")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
def mostrar():
    st.markdown("## 📋 Gestión de Pedidos")

    with st.spinner("Cargando pedidos..."):
        todos = leer_pedidos()

    if not todos:
        st.info("No hay pedidos registrados aún.")
        return

    tab_sa, tab_rev, tab_mod = st.tabs([
        "📅 Semana Actual",
        "🔍 Revisar Pedidos",
        "✏️ Modificar Pedido",
    ])

    with tab_sa:  _semana_actual(todos)
    with tab_rev: _revisar(todos)
    with tab_mod: _modificar(todos)
