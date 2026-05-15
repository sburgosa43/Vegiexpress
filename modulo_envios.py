"""
modulo_envios.py — Envíos y Facturación Semana Actual
Muestra pedidos de la semana en curso divididos por zona.
Permite ajuste de precios, guardado en Excel con historial y generación de PDF.
"""
import streamlit as st
from datetime import date
from excel_helper import leer_pedidos, cancelar_pedido, restaurar_pedido, guardar_cambios_precio
from data_helper import cargar_clientes
from pdf_helper import generar_envio, nombre_archivo


# ── DETECCIÓN DE ZONA ─────────────────────────────────────────────────────────
def _get_cli(nombre: str, mapa_exact: dict, mapa_lower: dict) -> dict:
    return mapa_exact.get(nombre) or mapa_lower.get(nombre.lower(), {})


def _es_antigua_chimal(l0: dict, mapa_exact: dict, mapa_lower: dict) -> bool:
    cli = _get_cli(l0["cliente"], mapa_exact, mapa_lower)
    cz  = cli.get("codigo_lugar", "")
    dir_ped = str(l0.get("direccion", "")).lower()
    return (cz in ("L03", "L04") or "antigua" in dir_ped or "chimal" in dir_ped)


# ── DETALLE DE PEDIDO CON PRECIOS EDITABLES ───────────────────────────────────
def _pedido_card(unico: str, lineas: list, cliente_info: dict, sufijo: str):
    l0        = lineas[0]
    cancelado = all(l["status"] == "Cancelado" for l in lineas)
    fecha_ped = l0["fecha"] if l0["fecha"] else date.today()
    total_orig = sum(l["total"] or 0 for l in lineas)

    with st.expander(
        f"{'🔴' if cancelado else '🟢'}  **{l0['cliente']}**  ·  "
        f"{fecha_ped.strftime('%d/%m/%Y')}  ·  "
        f"{len(lineas)} productos  ·  Q{total_orig:,.2f}",
        expanded=False,
    ):
        st.caption("Ajustá precios si hay descuentos puntuales. "
                   "'Guardar cambios' actualiza el Excel y deja registro en el historial.")

        hdr = st.columns([4, 1.2, 1.8, 1.8])
        hdr[0].markdown("**Producto**")
        hdr[1].markdown("**Cant.**")
        hdr[2].markdown("**Precio (Q)**")
        hdr[3].markdown("**Subtotal**")

        lineas_pdf    = []
        cambios_lista = []
        hay_cambios   = False
        total_ed      = 0.0

        for linea in lineas:
            k          = f"env_{sufijo}_{unico}_{linea['row_num']}"
            precio_exc = float(linea.get("precio_excel") or linea.get("precio") or 0)

            if k not in st.session_state:
                st.session_state[k] = precio_exc

            r = st.columns([4, 1.2, 1.8, 1.8])
            r[0].write(linea["producto"])
            r[1].write(f"{linea['cantidad']}")

            precio_ed = r[2].number_input(
                "", min_value=0.0,
                value=float(st.session_state[k]),
                step=0.25, key=k,
                label_visibility="collapsed",
            )
            diff = precio_ed - precio_exc
            if abs(diff) > 0.001:
                hay_cambios = True
                r[2].caption(f"{'▲' if diff > 0 else '▼'} Q{abs(diff):.2f}")

            sub = float(linea["cantidad"] or 0) * precio_ed
            r[3].markdown(f"<div style='padding-top:8px;font-weight:bold'>"
                           f"Q{sub:,.2f}</div>", unsafe_allow_html=True)
            total_ed += sub

            lineas_pdf.append({**linea, "precio": precio_ed, "total": sub})
            cambios_lista.append({
                "row_num":         linea["row_num"],
                "cliente":         linea["cliente"],
                "producto":        linea["producto"],
                "precio_anterior": precio_exc,
                "precio_nuevo":    precio_ed,
                "semana":          linea["semana"],
                "año":             linea["año"],
                "unico":           unico,
            })

        st.markdown(
            f"<div style='text-align:right;font-weight:bold;margin:4px 0'>"
            f"Total: Q{total_ed:,.2f}</div>", unsafe_allow_html=True)

        if hay_cambios:
            st.caption("⚠️ Hay precios modificados respecto al Excel guardado.")
        st.divider()

        col_save, col_pdf, col_acc = st.columns(3)

        with col_save:
            if st.button(
                "💾 Guardar cambios" if hay_cambios else "✅ Sin cambios",
                key=f"env_save_{sufijo}_{unico}",
                type="primary" if hay_cambios else "secondary",
                disabled=not hay_cambios,
            ):
                with st.spinner("Guardando..."):
                    n = guardar_cambios_precio(cambios_lista)
                for linea in lineas:
                    st.session_state.pop(f"env_{sufijo}_{unico}_{linea['row_num']}", None)
                st.success(f"✅ {n} precio(s) guardado(s).")
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
                    "📄 Descargar PDF",
                    data=pdf_bytes,
                    file_name=nombre_archivo(l0["cliente"], fecha_ped),
                    mime="application/pdf",
                    key=f"env_pdf_{sufijo}_{unico}",
                    type="primary",
                )
            except Exception as e:
                st.error(f"Error PDF: {e}")

        with col_acc:
            if not cancelado:
                if st.button("🔴 Cancelar pedido",
                             key=f"env_can_{sufijo}_{unico}", type="secondary"):
                    with st.spinner("Cancelando..."):
                        cancelar_pedido(unico)
                    st.success("Pedido cancelado."); st.rerun()
            else:
                if st.button("🟢 Restaurar pedido",
                             key=f"env_res_{sufijo}_{unico}", type="secondary"):
                    with st.spinner("Restaurando..."):
                        restaurar_pedido(unico)
                    st.success("Pedido restaurado."); st.rerun()


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def mostrar():
    st.markdown("## 🚚 Envíos y Facturación — Semana Actual")

    with st.spinner("Cargando pedidos..."):
        todos = leer_pedidos()

    hoy        = date.today()
    semana_act = hoy.isocalendar()[1]
    año_act    = hoy.year

    pedidos_sem = [p for p in todos
                   if p["semana"] == semana_act and p["año"] == año_act]

    st.markdown(f"**Semana {semana_act} · {año_act}** — {hoy.strftime('%d/%m/%Y')}")

    if not pedidos_sem:
        st.info(f"No hay pedidos registrados para la semana {semana_act} de {año_act}.")
        return

    # Agrupar por Unico
    grupos: dict = {}
    for p in pedidos_sem:
        grupos.setdefault(p["unico"], []).append(p)

    # Mapa de clientes (insensible a mayúsculas)
    cli_list   = cargar_clientes()
    mapa_exact = {c["nombre"]: c for c in cli_list}
    mapa_lower = {c["nombre"].lower(): c for c in cli_list}

    # Separar por zona
    ant_chim, resto = {}, {}
    for unico, ls in grupos.items():
        if _es_antigua_chimal(ls[0], mapa_exact, mapa_lower):
            ant_chim[unico] = ls
        else:
            resto[unico] = ls

    # Ordenar por fecha descendente
    def _ord(d):
        return dict(sorted(d.items(),
                    key=lambda x: str(x[1][0]["fecha"] or ""), reverse=True))

    ant_chim = _ord(ant_chim)
    resto    = _ord(resto)

    st.markdown(f"{len(grupos)} pedidos · "
                f"{len(ant_chim)} Antigua/Chimal · {len(resto)} Resto")

    tab_ac, tab_re = st.tabs([
        f"🔖 Antigua & Chimal ({len(ant_chim)})",
        f"🌎 Resto ({len(resto)})",
    ])

    with tab_ac:
        if not ant_chim:
            st.info("No hay pedidos de Antigua o Chimal esta semana.")
        for unico, ls in ant_chim.items():
            cli_info = _get_cli(ls[0]["cliente"], mapa_exact, mapa_lower) \
                       or {"nombre": ls[0]["cliente"]}
            _pedido_card(unico, ls, cli_info, sufijo="ac")

    with tab_re:
        if not resto:
            st.info("No hay pedidos del resto de zonas esta semana.")
        for unico, ls in resto.items():
            cli_info = _get_cli(ls[0]["cliente"], mapa_exact, mapa_lower) \
                       or {"nombre": ls[0]["cliente"]}
            _pedido_card(unico, ls, cli_info, sufijo="re")
