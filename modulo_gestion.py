"""
modulo_gestion.py — Gestión de Pedidos (Revisar y Editar)
"""
import streamlit as st
from datetime import date
from excel_helper import (leer_pedidos, cancelar_pedido, restaurar_pedido, editar_linea)
from data_helper import cargar_clientes, cargar_productos
from pdf_helper import generar_envio, nombre_archivo
from excel_helper import guardar_cambios_precio


def _aplicar_filtros(todos: list, sufijo: str = "") -> dict:
    años_disp     = sorted({str(p["año"])  for p in todos if p["año"]},  reverse=True)
    sems_disp     = sorted({str(p["semana"]) for p in todos if p["semana"]})
    fechas_disp   = sorted({p["fecha"].strftime("%d/%m/%Y") for p in todos if p["fecha"]},
                            reverse=True)
    clientes_disp = sorted({p["cliente"] for p in todos if p["cliente"]})

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: sel_años = st.multiselect("Año",     años_disp,     key=f"g_años{sufijo}", placeholder="Todos")
    with c2: sel_sems = st.multiselect("Semana",  sems_disp,     key=f"g_sems{sufijo}", placeholder="Todas")
    with c3: sel_fec  = st.multiselect("Fecha",   fechas_disp,   key=f"g_fec{sufijo}",  placeholder="Todas")
    with c4: sel_clis = st.multiselect("Cliente", clientes_disp, key=f"g_clis{sufijo}", placeholder="Todos")
    with c5: sel_est  = st.selectbox("Estado", ["Todos", "Pendiente", "Cancelado"], key=f"g_est{sufijo}")

    f = todos
    if sel_años:  f = [p for p in f if str(p["año"])    in sel_años]
    if sel_sems:  f = [p for p in f if str(p["semana"]) in sel_sems]
    if sel_fec:   f = [p for p in f if p["fecha"] and p["fecha"].strftime("%d/%m/%Y") in sel_fec]
    if sel_clis:  f = [p for p in f if p["cliente"]     in sel_clis]

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
            if not canc:
                if st.button("🔴 Cancelar pedido completo", key=f"mod_can_{unico}", type="secondary"):
                    with st.spinner(): cancelar_pedido(unico)
                    st.success("Cancelado."); st.rerun()
            else:
                if st.button("🟢 Restaurar a Pendiente", key=f"mod_res_{unico}", type="secondary"):
                    with st.spinner(): restaurar_pedido(unico)
                    st.success("Restaurado."); st.rerun()

            if not canc:
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
