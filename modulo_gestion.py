"""
modulo_gestion.py — Gestión de Pedidos (Revisar y Editar)
"""
import streamlit as st
from datetime import date
from excel_helper import (leer_pedidos, cancelar_pedido, restaurar_pedido,
                          editar_linea, editar_fecha_pedido, eliminar_pedido)
from order_helper import guardar_edicion_pedidos
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
    prods_cat   = {p["nombre"]: p for p in cargar_productos(False)}
    st.divider()

    opciones = {u: _label(u, ls) for u, ls in grupos.items()}
    sel = st.multiselect("Pedidos a modificar", list(opciones.keys()),
                          format_func=lambda u: opciones[u], key="mod_sel",
                          placeholder="Seleccioná uno o más pedidos...")
    if not sel:
        st.info("Seleccioná al menos un pedido."); return

    # Acumular cambios de todos los pedidos seleccionados
    lineas_originales = {}   # row_num → linea original
    total_cambios     = 0

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

            if st.session_state.get(conf_key):
                st.error("⚠️ ¿Eliminar este pedido definitivamente? "
                         "**No se puede deshacer.**")
                ce1, ce2 = st.columns(2)
                with ce1:
                    if st.button("✅ Sí, eliminar", key=f"mod_delok_{unico}",
                                 type="primary"):
                        with st.spinner(): n = eliminar_pedido(unico)
                        st.session_state.pop(conf_key, None)
                        st.success(f"✅ Eliminado ({n} filas)."); st.rerun()
                with ce2:
                    if st.button("❌ Cancelar", key=f"mod_delno_{unico}"):
                        st.session_state.pop(conf_key, None); st.rerun()

            if not canc:
                # Fecha de entrega (sigue guardando individual — es a nivel pedido)
                st.markdown("**Fecha de entrega:**")
                fc1, fc2 = st.columns([2, 1])
                nueva_fec = fc1.date_input("Nueva fecha", value=fped,
                                            key=f"mod_fecha_{unico}")
                if fc2.button("💾 Guardar fecha", key=f"mod_savefec_{unico}"):
                    if nueva_fec != fped:
                        with st.spinner():
                            n = editar_fecha_pedido(unico, nueva_fec)
                        st.success(f"✅ Fecha actualizada ({n} filas)."); st.rerun()
                    else:
                        st.info("La fecha no cambió.")
                st.divider()

                # Líneas — sin botón individual, detecta cambios para la cola
                # Checkbox actualizar catálogo (por pedido)
                upd_cat = st.checkbox("También actualizar precio en catálogo",
                                       key=f"upd_cat_mod_{unico}",
                                       help="Actualiza Listado de Productos")

                hdr = st.columns([3.5, 1.2, 1.5, 1.8, 1.8])
                hdr[0].markdown("**Producto**")
                hdr[1].markdown("**Cantidad**")
                hdr[2].markdown("**Precio (Q)**")
                hdr[3].markdown("**Costo · P.Eq.**")
                hdr[4].markdown("**Margen**")

                cambios_pedido = 0
                for linea in lineas:
                    rn  = linea["row_num"]
                    uid = f"mod_{rn}"
                    lineas_originales[rn] = linea

                    ec1, ec2, ec3 = st.columns([3.5, 1.2, 1.5])
                    prod_nuevo = ec1.selectbox("",  prods_lista,
                        index=(prods_lista.index(linea["producto"])
                               if linea["producto"] in prods_lista else 0),
                        key=f"{uid}_prod", label_visibility="collapsed")
                    cant_nueva = ec2.number_input("", min_value=0.0,
                        value=float(linea["cantidad"] or 0),
                        step=0.5, key=f"{uid}_cant",
                        label_visibility="collapsed")
                    prec_nuevo = ec3.number_input("", min_value=0.0,
                        value=float(linea["precio"] or 0),
                        step=0.25, key=f"{uid}_prec",
                        label_visibility="collapsed")

                    # ── Contexto financiero ───────────────────────────────
                    prod_info = prods_cat.get(prod_nuevo, {})
                    costo_p   = float(prod_info.get("costo", linea.get("costo", 0)) or 0)
                    pto_eq    = round(costo_p * 1.12, 2) if costo_p > 0 else 0
                    margen_p  = round(0.95 * (1 - costo_p * 1.12 / prec_nuevo), 4)                                 if (costo_p > 0 and prec_nuevo > 0) else 0
                    if costo_p > 0:
                        bajo_eq = prec_nuevo > 0 and prec_nuevo < pto_eq
                        c_eq    = "#c62828" if bajo_eq else "#555"
                        c_mg    = "#c62828" if margen_p < 0 else                                   "#e65100" if margen_p < 0.15 else "#2D7A2D"
                        fi1, fi2 = st.columns([3.5, 3.2])
                        fi1.markdown(
                            f"<small style='color:#888'>Costo Q{costo_p:.2f} · "
                            f"<span style='color:{c_eq}'>Eq:Q{pto_eq:.2f}"
                            f"{'  ⚠️ bajo equilibrio' if bajo_eq else ''}</span></small>",
                            unsafe_allow_html=True)
                        fi2.markdown(
                            f"<small style='color:{c_mg}'>"
                            f"Margen: {margen_p*100:.1f}%</small>",
                            unsafe_allow_html=True)

                    # Indicadores de cambio
                    hay_diff = []
                    if prod_nuevo and prod_nuevo != linea["producto"]:
                        hay_diff.append("producto")
                    if abs(cant_nueva - float(linea["cantidad"] or 0)) > 0.001:
                        hay_diff.append("cantidad")
                    if abs(prec_nuevo - float(linea["precio"] or 0)) > 0.001:
                        hay_diff.append("precio")
                    if hay_diff:
                        st.caption(f"📝 {linea['producto']}: cambió {', '.join(hay_diff)}")
                        cambios_pedido += 1
                        total_cambios  += 1

                if cambios_pedido:
                    st.markdown(
                        f"<div style='font-size:.78rem;color:#E65100;margin-top:4px'>"
                        f"📝 {cambios_pedido} cambio(s) pendiente(s) en este pedido"
                        f"</div>", unsafe_allow_html=True)

                # ── Agregar nuevas líneas ─────────────────────────────────────
                st.divider()
                st.markdown("**➕ Agregar productos a este pedido:**")
                key_nv = f"mod_nuevas_{unico}"
                if key_nv not in st.session_state:
                    st.session_state[key_nv] = []
                nuevas_ui = st.session_state[key_nv]

                for jj, nv in enumerate(nuevas_ui):
                    nj1, nj2, nj3, njx = st.columns([3.5, 1.5, 1.5, 0.5])
                    nv["producto"] = nj1.selectbox("",  prods_lista,
                        index=(prods_lista.index(nv.get("producto",""))
                               if nv.get("producto","") in prods_lista else 0),
                        key=f"nv_{unico}_{jj}_prod",
                        label_visibility="collapsed")
                    nv["cantidad"] = nj2.number_input("", min_value=0.0, step=0.5,
                        value=float(nv.get("cantidad", 0.0)),
                        key=f"nv_{unico}_{jj}_cant",
                        label_visibility="collapsed")
                    nv["precio"]   = nj3.number_input("", min_value=0.0, step=0.25,
                        value=float(nv.get("precio", 0.0)),
                        key=f"nv_{unico}_{jj}_prec",
                        label_visibility="collapsed")
                    if njx.button("🗑", key=f"nv_{unico}_{jj}_del"):
                        nuevas_ui.pop(jj)
                        st.session_state[key_nv] = nuevas_ui; st.rerun()

                if st.button("➕ Agregar línea", key=f"addlin_{unico}"):
                    nuevas_ui.append({"producto":"","cantidad":0.0,"precio":0.0})
                    st.session_state[key_nv] = nuevas_ui; st.rerun()

    # ── Botón global de guardado ───────────────────────────────────────────────
    st.divider()

    # Contar nuevas líneas válidas y eliminaciones
    nuevas_validas = sum(
        1 for u in sel
        for nv in st.session_state.get(f"mod_nuevas_{u}", [])
        if nv.get("producto") and float(nv.get("cantidad",0)) > 0
    )
    a_eliminar = sum(
        1 for rn in lineas_originales
        if st.session_state.get(f"del_row_{rn}")
    )
    hay_algo = total_cambios > 0 or nuevas_validas > 0 or a_eliminar > 0

    if hay_algo:
        resumen_parts = []
        if total_cambios:  resumen_parts.append(f"{total_cambios} edición(es)")
        if nuevas_validas: resumen_parts.append(f"{nuevas_validas} línea(s) nueva(s)")
        if a_eliminar:     resumen_parts.append(f"{a_eliminar} a eliminar")
        st.info(f"📝 **{' + '.join(resumen_parts)}** en {len(sel)} pedido(s) "
                f"— se grabarán en un solo ciclo de Drive.")

        if st.button(f"📤 Guardar todo ({' + '.join(resumen_parts)})",
                     type="primary", use_container_width=True):
            # Recopilar ediciones (excluir filas marcadas para eliminar)
            cambios_batch = []
            for rn, linea in lineas_originales.items():
                if st.session_state.get(f"del_row_{rn}"):
                    continue  # Se elimina, no se edita
                uid   = f"mod_{rn}"
                prod_n = st.session_state.get(f"{uid}_prod", linea["producto"])
                cant_n = st.session_state.get(f"{uid}_cant", linea["cantidad"])
                prec_n = st.session_state.get(f"{uid}_prec", linea["precio"])
                cambio = {
                    "row_num":       rn,
                    "_cant_actual":  float(linea["cantidad"] or 0),
                    "_prec_actual":  float(linea["precio"]   or 0),
                    "_costo_actual": float(linea.get("costo", 0) or 0),
                }
                if prod_n and prod_n != linea["producto"]:
                    cambio["producto_nuevo"] = prod_n
                if abs(float(cant_n or 0) - float(linea["cantidad"] or 0)) > 0.001:
                    cambio["cantidad_nueva"] = float(cant_n)
                if abs(float(prec_n or 0) - float(linea["precio"] or 0)) > 0.001:
                    cambio["precio_nuevo"] = float(prec_n)
                if len(cambio) > 4:   # más que solo los 4 campos base
                    cambios_batch.append(cambio)

            # Recopilar filas a eliminar
            filas_eliminar = [rn for rn in lineas_originales
                              if st.session_state.get(f"del_row_{rn}")]

            # Recopilar líneas nuevas
            nuevas_batch = []
            for unico in sel:
                key_nv  = f"mod_nuevas_{unico}"
                nv_list = st.session_state.get(key_nv, [])
                l0      = grupos[unico][0]
                items_nv = []
                for nv in nv_list:
                    if not nv.get("producto") or float(nv.get("cantidad",0)) <= 0:
                        continue
                    prod_info = prods_cat.get(nv["producto"], {})
                    items_nv.append({
                        "nombre":   nv["producto"],
                        "cantidad": nv["cantidad"],
                        "precio":   nv["precio"],
                        "costo":    prod_info.get("costo", 0),
                        "unidad":   prod_info.get("unidad", ""),
                    })
                if items_nv:
                    nuevas_batch.append({
                        "unico":           unico,
                        "cliente_nombre":  l0["cliente"],
                        "fecha":           l0["fecha"] or date.today(),
                        "items":           items_nv,
                    })

            with st.spinner("Guardando en Drive (1 solo ciclo)..."):
                res = guardar_edicion_pedidos(cambios_batch, nuevas_batch,
                                              filas_eliminar)

            # Limpiar session state
            for unico in sel:
                st.session_state.pop(f"mod_nuevas_{unico}", None)
            for rn in list(lineas_originales.keys()):
                st.session_state.pop(f"del_row_{rn}", None)

            partes = []
            if res["ediciones"]:   partes.append(f"{res['ediciones']} edición(es)")
            if res["nuevas_filas"]: partes.append(f"{res['nuevas_filas']} línea(s) nueva(s)")
            if res["eliminadas"]:   partes.append(f"{res['eliminadas']} eliminada(s)")
            st.success(f"✅ {' + '.join(partes)} en 1 ciclo Drive.")
            st.rerun()
    else:
        st.info("Sin cambios ni líneas nuevas detectadas.")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

def _tab_remision(todos: list):
    """Remisión por cliente — single-select, imprimir + vista previa."""
    import base64
    import streamlit.components.v1 as components
    from pdf_helper import generar_remision
    from datetime   import date

    st.markdown("### 📄 Remisión")

    # ── Filtros ────────────────────────────────────────────────────────────
    hoy     = date.today()
    sem_def = hoy.isocalendar()[1]
    año_def = hoy.year

    fc1, fc2, fc3, fc4 = st.columns(4)
    semana   = fc1.number_input("Semana", 1, 53, sem_def, key="rem_sem")
    año      = fc2.number_input("Año", 2020, 2030, año_def, key="rem_año")

    pedidos_sem = [
        p for p in todos
        if p["semana"] == semana and p["año"] == año
        and p["status"] != "Cancelado"
        and float(p.get("cantidad") or 0) > 0
    ]

    clientes_disp = sorted({p["cliente"] for p in pedidos_sem})
    if not clientes_disp:
        st.info(f"Sin pedidos activos para semana {semana}/{año}.")
        return

    cli_sel  = fc3.selectbox("Cliente", clientes_disp, key="rem_cli")
    status_f = fc4.selectbox("Status", ["Todos","Pendiente","Entregado"],
                              key="rem_status")

    # ── Pedidos del cliente seleccionado ───────────────────────────────────
    pedidos_cli = [
        p for p in pedidos_sem
        if p["cliente"] == cli_sel
        and (status_f == "Todos" or p["status"] == status_f)
    ]

    if not pedidos_cli:
        st.info("Sin pedidos con esos filtros.")
        return

    fechas    = [p["fecha"] for p in pedidos_cli if p["fecha"]]
    fecha_str = max(fechas).strftime("%d/%m/%Y") if fechas else f"Sem {semana}"

    lineas = [{
        "producto": p["producto"],
        "unidad":   p.get("unidad", ""),
        "cantidad": float(p.get("cantidad") or 0),
        "total":    round(float(p.get("precio") or 0) *
                          float(p.get("cantidad") or 0), 2),
    } for p in sorted(pedidos_cli, key=lambda x: x["producto"])]

    total_cli = sum(l["total"] for l in lineas)
    st.caption(f"{cli_sel} · {len(lineas)} línea(s) · "
               f"Total: Q{total_cli:,.2f} · Entrega: {fecha_str}")

    # ── Generar PDF ────────────────────────────────────────────────────────
    try:
        pdf_bytes = generar_remision(cli_sel, lineas, semana, año, fecha_str)
    except Exception as e:
        st.error(f"Error generando PDF: {e}")
        return

    pdf_b64  = base64.b64encode(pdf_bytes).decode()
    nom_file = "".join(ch for ch in cli_sel if ch.isalnum() or ch=="_")

    # ── Botones ────────────────────────────────────────────────────────────
    bb1, bb2 = st.columns(2)

    # Botón imprimir directo (nueva pestaña, sin descarga)
    html_print = f"""
    <script>
    function imprimirRemision() {{
        var b64  = '{pdf_b64}';
        var raw  = atob(b64);
        var arr  = new Uint8Array(raw.length);
        for (var i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
        var blob = new Blob([arr], {{type:'application/pdf'}});
        var url  = URL.createObjectURL(blob);
        var win  = window.open(url, '_blank');
        win.onload = function() {{ win.print(); }};
    }}
    </script>
    <button onclick="imprimirRemision()" style="
        background:#2D7A2D;color:white;border:none;border-radius:6px;
        padding:8px 16px;font-size:14px;cursor:pointer;width:100%;
        font-family:sans-serif">🖨️ Imprimir</button>
    """
    with bb1:
        components.html(html_print, height=48)

    bb2.download_button(
        "📥 Descargar PDF",
        data=pdf_bytes,
        file_name=f"Remision_{nom_file}_Sem{semana}_{año}.pdf",
        mime="application/pdf",
        key=f"rem_dl_{cli_sel}_{semana}_{año}",
        use_container_width=True,
    )

    # ── Vista previa con PDF.js (evita bloqueo de Chrome) ───────────────
    st.markdown("**Vista previa:**")
    components.html(
        f"""
        <div id="pdf-container" style="width:100%;height:700px;
             border:1px solid #ddd;border-radius:4px;overflow:hidden;">
          <canvas id="pdf-canvas" style="width:100%;"></canvas>
        </div>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
        <script>
        pdfjsLib.GlobalWorkerOptions.workerSrc =
          'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

        var b64 = '{pdf_b64}';
        var raw = atob(b64);
        var arr = new Uint8Array(raw.length);
        for (var i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);

        var loadTask = pdfjsLib.getDocument({{data: arr}});
        loadTask.promise.then(function(pdf) {{
          var container = document.getElementById('pdf-container');
          container.innerHTML = '';
          for (var p = 1; p <= pdf.numPages; p++) {{
            (function(pageNum) {{
              pdf.getPage(pageNum).then(function(page) {{
                var vp  = page.getViewport({{scale: 1.5}});
                var cvs = document.createElement('canvas');
                cvs.width  = vp.width;
                cvs.height = vp.height;
                cvs.style.width  = '100%';
                cvs.style.display= 'block';
                cvs.style.marginBottom = '4px';
                container.appendChild(cvs);
                page.render({{canvasContext: cvs.getContext('2d'), viewport: vp}});
              }});
            }})(p);
          }}
        }});
        </script>
        """,
        height=720,
        scrolling=True,
    )


def _ajuste_precios():
    """Actualiza precios de productos en pedidos de la semana actual + catálogo."""
    import pandas as pd
    from datetime import date
    from excel_helper import leer_productos_semana, actualizar_precio_semana

    hoy     = date.today()
    sem_def = hoy.isocalendar()[1]
    año_def = hoy.year

    c1, c2 = st.columns(2)
    semana  = c1.number_input("Semana", min_value=1, max_value=53,
                               value=sem_def, key="ajp_sem")
    año     = c2.number_input("Año", min_value=2020, max_value=2030,
                               value=año_def, key="ajp_año")

    if st.button("🔍 Cargar productos de esta semana",
                 type="primary", key="ajp_cargar"):
        st.session_state["ajp_data"]        = leer_productos_semana(semana, año)
        st.session_state["ajp_sem_cargada"] = semana
        st.session_state["ajp_año_cargado"] = año

    data = st.session_state.get("ajp_data")
    if not data:
        st.info("Cargá una semana para ver los productos con pedidos activos.")
        return

    sem_cargada = st.session_state.get("ajp_sem_cargada")
    año_cargado = st.session_state.get("ajp_año_cargado")
    st.markdown(f"**Semana {sem_cargada}/{año_cargado} — "
                f"{len(data)} producto(s) con pedidos activos**")
    st.caption("Modificá el 'Precio Nuevo' y guardá. "
               "Se actualiza en todos los pedidos de la semana Y en el catálogo.")

    df = pd.DataFrame([{
        "Producto":     d["producto"],
        "Costo Actual": d["costo"],
        "Costo Nuevo":  d["costo"],
        "Precio Actual":d["precio_actual"],
        "Precio Nuevo": d["precio_actual"],
        "Pedidos":      d["n_pedidos"],
        "Clientes":     d["clientes"],
    } for d in data])

    edited = st.data_editor(
        df,
        column_config={
            "Producto":     st.column_config.TextColumn(disabled=True, width="medium"),
            "Costo Actual": st.column_config.NumberColumn(disabled=True,
                             format="Q%.2f", width="small"),
            "Costo Nuevo":  st.column_config.NumberColumn(
                             format="Q%.2f", width="small",
                             help="Modificá aquí el nuevo costo"),
            "Precio Actual":st.column_config.NumberColumn(disabled=True,
                             format="Q%.2f", width="small"),
            "Precio Nuevo": st.column_config.NumberColumn(
                             format="Q%.2f", width="small",
                             help="Modificá aquí el nuevo precio"),
            "Pedidos":      st.column_config.NumberColumn(disabled=True,
                             width="small"),
            "Clientes":     st.column_config.TextColumn(disabled=True,
                             width="medium"),
        },
        hide_index=True,
        use_container_width=True,
        key="ajp_editor",
    )

    # Detectar cambios de precio y/o costo
    cambios = []
    for i, row in edited.iterrows():
        precio_nuevo = float(row["Precio Nuevo"] or 0)
        precio_act   = float(df.iloc[i]["Precio Actual"])
        costo_nuevo  = float(row["Costo Nuevo"]  or 0)
        costo_act    = float(df.iloc[i]["Costo Actual"])
        p_cambia = abs(precio_nuevo - precio_act) > 0.001 and precio_nuevo > 0
        c_cambia = abs(costo_nuevo  - costo_act)  > 0.001 and costo_nuevo  > 0
        if p_cambia or c_cambia:
            cambios.append({
                "producto":    row["Producto"],
                "precio_nuevo":precio_nuevo if p_cambia else precio_act,
                "precio_ant":  precio_act,
                "costo_nuevo": costo_nuevo  if c_cambia else costo_act,
                "costo_ant":   costo_act,
                "p_cambia":    p_cambia,
                "c_cambia":    c_cambia,
            })

    if cambios:
        st.warning(f"⚠️ {len(cambios)} producto(s) con precio modificado:")
        for ch in cambios:
            linea = f"- **{ch['producto']}**:"
            if ch["p_cambia"]:
                linea += f" Precio Q{ch['precio_ant']:,.2f}→Q{ch['precio_nuevo']:,.2f}"
            if ch["c_cambia"]:
                linea += f" · Costo Q{ch['costo_ant']:,.2f}→Q{ch['costo_nuevo']:,.2f}"
            st.markdown(linea)

        if st.button(f"💾 Aplicar {len(cambios)} cambio(s)",
                     type="primary", key="ajp_guardar"):
            with st.spinner("Actualizando pedidos y catálogo..."):
                res = actualizar_precio_semana(cambios, sem_cargada, año_cargado)
            st.success(
                f"✅ {res['filas_pedidos']} fila(s) de pedidos actualizadas · "
                f"{res['prods_catalogo']} producto(s) en catálogo actualizados.")
            st.session_state.pop("ajp_data", None)
            st.rerun()
    else:
        st.info("Sin cambios de precio detectados.")


def mostrar():
    st.markdown("## 📋 Gestión de Pedidos")
    # Botón de regreso al Inicio
    if st.button("🏠 Inicio", key="btn_home_ges", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    with st.spinner("Cargando..."):
        todos = leer_pedidos()
    if not todos:
        st.info("No hay pedidos registrados."); return

    tab_rev, tab_mod, tab_prec, tab_rem = st.tabs(["🔍 Revisar Pedidos", "✏️ Editar Pedidos", "💲 Ajuste Precio y Costo", "📄 Remisión"])
    with tab_rev: _revisar(todos)
    with tab_mod: _modificar(todos)
    with tab_prec: _ajuste_precios()
    with tab_rem: _tab_remision(todos)

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
