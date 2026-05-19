"""
modulo_gestion.py — Gestión de Pedidos (Revisar y Editar)
"""
import streamlit as st
from datetime import date
from excel_helper import (leer_pedidos, cancelar_pedido, restaurar_pedido,
                          editar_linea, editar_fecha_pedido, eliminar_pedido)
from data_helper import cargar_clientes, cargar_productos
from pdf_helper import generar_envio, nombre_archivo
from excel_helper import guardar_cambios_precio


MESES_LABEL = {
    1:"01-Ene", 2:"02-Feb", 3:"03-Mar", 4:"04-Abr",
    5:"05-May", 6:"06-Jun", 7:"07-Jul", 8:"08-Ago",
    9:"09-Sep", 10:"10-Oct", 11:"11-Nov", 12:"12-Dic",
}


def _aplicar_filtros(todos: list, sufijo: str = "") -> dict:
    from datetime import date, timedelta

    # ── Filtro base: últimos 3 meses por defecto ──────────────────────────────
    cutoff     = date.today() - timedelta(days=90)
    ver_todo   = st.checkbox("📅 Ver historial completo",
                              value=False, key=f"g_hist{sufijo}")
    base       = todos if ver_todo else [
        p for p in todos if p["fecha"] and p["fecha"] >= cutoff
    ]
    if not ver_todo and base:
        st.caption(f"Mostrando últimos 90 días ({cutoff.strftime('%d/%m/%Y')} → hoy).")

    # ── Opciones disponibles en el rango actual ───────────────────────────────
    clientes_disp = sorted({p["cliente"]  for p in base if p["cliente"]})
    años_disp     = sorted({str(p["año"]) for p in base if p["año"]}, reverse=True)
    meses_nums    = sorted({p["fecha"].month for p in base if p["fecha"]})
    meses_disp    = [MESES_LABEL[m] for m in meses_nums]
    sems_disp     = sorted({str(p["semana"]) for p in base if p["semana"]})
    fechas_disp   = sorted(
        {p["fecha"].strftime("%d/%m/%Y") for p in base if p["fecha"]}, reverse=True)

    # ── Filtros: Cliente | Año | Mes | Semana | Fecha ─────────────────────────
    r1c1, r1c2, r1c3 = st.columns(3)
    r2c1, r2c2, r2c3 = st.columns(3)

    with r1c1: sel_clis = st.multiselect("Cliente", clientes_disp,
                                          key=f"g_clis{sufijo}", placeholder="Todos")
    with r1c2: sel_años = st.multiselect("Año",     años_disp,
                                          key=f"g_años{sufijo}", placeholder="Todos")
    with r1c3: sel_mes  = st.multiselect("Mes",     meses_disp,
                                          key=f"g_mes{sufijo}",  placeholder="Todos")
    with r2c1: sel_sems = st.multiselect("Semana",  sems_disp,
                                          key=f"g_sems{sufijo}", placeholder="Todas")
    with r2c2: sel_fec  = st.multiselect("Fecha",   fechas_disp,
                                          key=f"g_fec{sufijo}",  placeholder="Todas")
    with r2c3: sel_est  = st.selectbox("Estado", ["Todos","Pendiente","Cancelado"],
                                        key=f"g_est{sufijo}")

    # Convertir selección de mes a números
    sel_mes_nums = {k for k, v in MESES_LABEL.items() if v in sel_mes}

    # ── Aplicar filtros ───────────────────────────────────────────────────────
    f = base
    if sel_clis:     f = [p for p in f if p["cliente"]     in sel_clis]
    if sel_años:     f = [p for p in f if str(p["año"])    in sel_años]
    if sel_mes_nums: f = [p for p in f if p["fecha"] and p["fecha"].month in sel_mes_nums]
    if sel_sems:     f = [p for p in f if str(p["semana"]) in sel_sems]
    if sel_fec:      f = [p for p in f if p["fecha"] and
                          p["fecha"].strftime("%d/%m/%Y") in sel_fec]

    grupos: dict = {}
    for p in f:
        grupos.setdefault(p["unico"], []).append(p)

    if sel_est != "Todos":
        grupos = {u: ls for u, ls in grupos.items()
                  if (sel_est == "Cancelado") == all(l["status"] == "Cancelado" for l in ls)}

    return dict(sorted(grupos.items(),
                key=lambda x: (x[1][0]["año"] or 0, x[1][0]["semana"] or 0),
                reverse=True))


def _label(unico, lineas):
    l0    = lineas[0]
    total = sum(l["total"] or 0 for l in lineas)
    est   = "🔴" if all(l["status"] == "Cancelado" for l in lineas) else "🟢"
    f     = l0["fecha"].strftime("%d/%m/%Y") if l0["fecha"] else "—"
    return f"{est}  {f}  ·  {l0['cliente']}  ·  Sem {l0['semana']}/{l0['año']}  ·  {len(lineas)} prod  ·  Q{total:,.2f}"


# ── REVISAR ───────────────────────────────────────────────────────────────────
def _revisar(todos):
    grupos = _aplicar_filtros(todos, "_rev")
    if not grupos:
        st.warning("No hay pedidos con esos filtros."); return

    cli_list   = cargar_clientes()
    mapa_exact = {c["nombre"]: c for c in cli_list}
    mapa_lower = {c["nombre"].lower(): c for c in cli_list}

    st.divider()
    opciones = {u: _label(u, ls) for u, ls in grupos.items()}
    sel = st.multiselect("Pedidos a revisar", list(opciones.keys()),
                          format_func=lambda u: opciones[u], key="rev_sel",
                          placeholder="Seleccioná uno o más pedidos...")
    if not sel:
        st.info("Seleccioná al menos un pedido."); return

    for unico in sel:
        lineas = grupos[unico]
        l0     = lineas[0]
        total  = sum(l["total"] or 0 for l in lineas)
        canc   = all(l["status"] == "Cancelado" for l in lineas)
        cli    = mapa_exact.get(l0["cliente"]) or mapa_lower.get(l0["cliente"].lower(), {"nombre": l0["cliente"]})
        fped   = l0["fecha"] if l0["fecha"] else date.today()

        with st.expander(
            f"{'🔴' if canc else '🟢'}  **{l0['cliente']}**  ·  "
            f"{fped.strftime('%d/%m/%Y')}  ·  Sem {l0['semana']}/{l0['año']}  ·  Q{total:,.2f}",
            expanded=True,
        ):
            hdr = st.columns([4, 1.2, 1.5, 1.5, 1.5])
            hdr[0].markdown("**Producto**"); hdr[1].markdown("**Cant.**")
            hdr[2].markdown("**Precio**");   hdr[3].markdown("**Total**"); hdr[4].markdown("**Estado**")
            for l in lineas:
                r = st.columns([4, 1.2, 1.5, 1.5, 1.5])
                r[0].write(l["producto"]); r[1].write(l["cantidad"])
                r[2].write(f"Q{l['precio']:,.2f}"); r[3].write(f"Q{l['total']:,.2f}")
                r[4].write(l["status"])
            st.markdown(f"<div style='text-align:right;font-weight:bold'>Total: Q{total:,.2f}</div>",
                         unsafe_allow_html=True)
            # PDF desde revisar
            try:
                pdf_bytes = generar_envio(cliente=cli, fecha=fped, lineas=lineas, unico=unico)
                st.download_button("📄 Descargar PDF", data=pdf_bytes,
                                    file_name=nombre_archivo(l0["cliente"], fped),
                                    mime="application/pdf", key=f"rev_pdf_{unico}")
            except Exception as e:
                st.error(f"Error PDF: {e}")


# ── MODIFICAR ─────────────────────────────────────────────────────────────────
def _modificar(todos):
    grupos = _aplicar_filtros(todos, "_mod")
    if not grupos:
        st.warning("No hay pedidos con esos filtros."); return

    prods_lista = [""] + [p["nombre"] for p in cargar_productos(False)]
    st.divider()

    opciones = {u: _label(u, ls) for u, ls in grupos.items()}
    sel = st.multiselect("Pedidos a modificar", list(opciones.keys()),
                          format_func=lambda u: opciones[u], key="mod_sel",
                          placeholder="Seleccioná uno o más pedidos...")
    if not sel:
        st.info("Seleccioná al menos un pedido."); return

    for unico in sel:
        lineas = grupos[unico]
        l0     = lineas[0]
        canc   = all(l["status"] == "Cancelado" for l in lineas)
        total  = sum(l["total"] or 0 for l in lineas)
        fped   = l0["fecha"] if l0["fecha"] else date.today()

        with st.expander(
            f"{'🔴' if canc else '🟢'}  **{l0['cliente']}**  ·  "
            f"{fped.strftime('%d/%m/%Y')}  ·  Sem {l0['semana']}/{l0['año']}  ·  Q{total:,.2f}",
            expanded=True,
        ):
            conf_key = f"confirm_elim_{unico}"
            if not canc:
                if st.button("🔴 Cancelar pedido completo",
                             key=f"mod_can_{unico}", type="secondary"):
                    with st.spinner(): cancelar_pedido(unico)
                    st.success("Cancelado."); st.rerun()
            else:
                bc2, bd2 = st.columns(2)
                with bc2:
                    if st.button("🟢 Restaurar a Pendiente",
                                 key=f"mod_res_{unico}", type="secondary"):
                        with st.spinner(): restaurar_pedido(unico)
                        st.success("Restaurado."); st.rerun()
                with bd2:
                    if st.button("🗑️ Eliminar pedido",
                                 key=f"mod_del_{unico}", type="secondary"):
                        st.session_state[conf_key] = True; st.rerun()

            # Confirmación de eliminación
            if st.session_state.get(conf_key):
                st.error("⚠️ ¿Eliminar este pedido definitivamente del Excel? "
                         "**No se puede deshacer.**")
                ce1, ce2 = st.columns(2)
                with ce1:
                    if st.button("✅ Sí, eliminar", key=f"mod_delok_{unico}",
                                 type="primary"):
                        with st.spinner("Eliminando..."):
                            n = eliminar_pedido(unico)
                        st.session_state.pop(conf_key, None)
                        st.success(f"✅ Pedido eliminado ({n} filas).")
                        st.rerun()
                with ce2:
                    if st.button("❌ Cancelar", key=f"mod_delno_{unico}"):
                        st.session_state.pop(conf_key, None); st.rerun()

            if not canc:
                # ── Editar fecha de entrega ───────────────────────────────────
                st.markdown("**Fecha de entrega:**")
                fc1, fc2 = st.columns([2, 1])
                nueva_fec = fc1.date_input(
                    "Nueva fecha", value=fped,
                    key=f"mod_fecha_{unico}")
                if fc2.button("💾 Guardar fecha", key=f"mod_savefec_{unico}"):
                    if nueva_fec != fped:
                        with st.spinner("Guardando fecha..."):
                            n = editar_fecha_pedido(unico, nueva_fec)
                        st.success(f"✅ Fecha actualizada en {n} filas.")
                        st.rerun()
                    else:
                        st.info("La fecha no cambió.")
                st.divider()

                # ── Editar líneas ─────────────────────────────────────────────
                st.markdown("**Editar líneas** (precio se guarda solo en este pedido):")
                for linea in lineas:
                    uid = f"{unico}_{linea['row_num']}"
                    st.markdown(f"---\n**{linea['producto']}**")
                    ec1, ec2, ec3, ec4 = st.columns([3, 1.5, 1.5, 1.2])
                    prod_nuevo  = ec1.selectbox("Producto", prods_lista,
                                                index=(prods_lista.index(linea["producto"])
                                                       if linea["producto"] in prods_lista else 0),
                                                key=f"mod_prod_{uid}")
                    cant_nueva  = ec2.number_input("Cantidad", min_value=0.0,
                                                   value=float(linea["cantidad"] or 0),
                                                   step=0.5, key=f"mod_cant_{uid}")
                    prec_nuevo  = ec3.number_input("Precio (Q)", min_value=0.0,
                                                   value=float(linea["precio"] or 0),
                                                   step=0.25, key=f"mod_prec_{uid}")
                    ec4.markdown("&nbsp;", unsafe_allow_html=True)
                    if ec4.button("💾", key=f"mod_save_{uid}", help="Guardar en Excel"):
                        cambios = {}
                        if prod_nuevo and prod_nuevo != linea["producto"]: cambios["nuevo_producto"] = prod_nuevo
                        if cant_nueva != float(linea["cantidad"] or 0):   cambios["nueva_cantidad"] = cant_nueva
                        if prec_nuevo != float(linea["precio"]   or 0):   cambios["nuevo_precio"]   = prec_nuevo
                        if cambios:
                            with st.spinner(): editar_linea(linea["row_num"], **cambios)
                            st.success("✅ Actualizado."); st.rerun()
                        else:
                            st.info("Sin cambios.")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def mostrar():
    st.markdown("## 📋 Gestión de Pedidos")
    with st.spinner("Cargando..."):
        todos = leer_pedidos()
    if not todos:
        st.info("No hay pedidos registrados."); return

    tab_rev, tab_mod = st.tabs(["🔍 Revisar Pedidos", "✏️ Editar Pedidos"])
    with tab_rev: _revisar(todos)
    with tab_mod: _modificar(todos)

    # ── MIGRACIÓN (operación única) ───────────────────────────────────────────
    st.divider()
    with st.expander("⚙️ Migración de datos — Convertir fórmulas a valores", expanded=False):
        st.markdown("""
        **¿Qué hace esto?**
        Reemplaza todas las fórmulas VLOOKUP de la hoja **Pedidos** con sus valores
        calculados estáticos. Es el equivalente a *Pegado Especial → Solo Valores* en Excel.

        **Resultado:** el Excel queda 100% libre de fórmulas en la hoja Pedidos.
        Todos los cálculos futuros los hace la app directamente.

        **⚠️ Importante:** hacelo solo si tenés el backup de tu Excel guardado.
        Esta operación no se puede deshacer desde la app.
        """)

        confirm_key = "confirm_migracion"
        if not st.session_state.get(confirm_key):
            if st.button("🔄 Quiero convertir fórmulas a valores", type="secondary"):
                st.session_state[confirm_key] = True
                st.rerun()
        else:
            st.warning("⚠️ ¿Confirmás? Se modificará la hoja Pedidos de tu Excel.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Sí, ejecutar migración", type="primary"):
                    from excel_helper import migrar_pedidos_a_valores
                    with st.spinner("Migrando... puede tardar 30-60 segundos..."):
                        try:
                            resultado = migrar_pedidos_a_valores()
                            st.success(
                                f"✅ Migración completada: "
                                f"**{resultado['filas']} filas** procesadas, "
                                f"**{resultado['celdas']} fórmulas** convertidas a valores."
                            )
                            st.session_state[confirm_key] = False
                        except Exception as e:
                            st.error(f"❌ Error: {e}")
                            st.session_state[confirm_key] = False
            with c2:
                if st.button("❌ Cancelar", type="secondary"):
                    st.session_state[confirm_key] = False
                    st.rerun()
