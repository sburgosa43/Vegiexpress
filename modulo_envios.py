"""
modulo_envios.py — Envíos y Facturación Semana Actual
Tres zonas: Antigua & Chimal | Guatemala & Santiago | Rio
"""
import streamlit as st
from datetime import date
from excel_helper import leer_pedidos, cancelar_pedido, restaurar_pedido, guardar_cambios_precio
from data_helper import cargar_clientes
from pdf_helper import generar_envio, nombre_archivo

ZONAS_ENVIO = {
    "🔖 Antigua & Chimal":      ["L03", "L04"],
    "🏙️ Guatemala & Santiago":  ["L05", "L06"],
    "🌊 Rio":                   ["L01"],
}

def _zona_de(codigo: str) -> str | None:
    for zona, codigos in ZONAS_ENVIO.items():
        if codigo in codigos:
            return zona
    return None

def _get_cli(nombre: str, mapa_exact: dict, mapa_lower: dict) -> dict:
    return mapa_exact.get(nombre) or mapa_lower.get(nombre.lower(), {})

def _detectar_zona(l0: dict, mapa_exact: dict, mapa_lower: dict) -> str | None:
    cli   = _get_cli(l0["cliente"], mapa_exact, mapa_lower)
    zona  = _zona_de(cli.get("codigo_lugar", ""))
    if zona: return zona
    # Fallback por texto de dirección
    dir_l = str(l0.get("direccion", "")).lower()
    if "antigua" in dir_l:   return "🔖 Antigua & Chimal"
    if "chimal"  in dir_l:   return "🔖 Antigua & Chimal"
    if "rio"     in dir_l:   return "🌊 Rio"
    return None

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
        st.caption("Ajustá precios si hay descuentos. "
                   "'Guardar' actualiza el Excel y registra en historial.")

        hdr = st.columns([4, 1.2, 1.8, 1.8])
        hdr[0].markdown("**Producto**"); hdr[1].markdown("**Cant.**")
        hdr[2].markdown("**Precio (Q)**"); hdr[3].markdown("**Subtotal**")

        lineas_pdf = []; cambios = []; hay_cambios = False; total_ed = 0.0

        for linea in sorted(lineas, key=lambda x: x["producto"]):
            k         = f"env_{sufijo}_{unico}_{linea['row_num']}"
            precio_xl = float(linea.get("precio_excel") or linea.get("precio") or 0)
            if k not in st.session_state:
                st.session_state[k] = precio_xl

            r = st.columns([4, 1.2, 1.8, 1.8])
            r[0].write(linea["producto"]); r[1].write(f"{linea['cantidad']}")
            precio_ed = r[2].number_input("", min_value=0.0,
                value=float(st.session_state[k]), step=0.25, key=k,
                label_visibility="collapsed")
            diff = precio_ed - precio_xl
            if abs(diff) > 0.001:
                hay_cambios = True
                r[2].caption(f"{'▲' if diff>0 else '▼'} Q{abs(diff):.2f}")
            sub = float(linea["cantidad"] or 0) * precio_ed
            r[3].markdown(f"<div style='padding-top:8px;font-weight:bold'>"
                          f"Q{sub:,.2f}</div>", unsafe_allow_html=True)
            total_ed += sub
            lineas_pdf.append({**linea, "precio": precio_ed, "total": sub})
            cambios.append({"row_num": linea["row_num"], "cliente": linea["cliente"],
                            "producto": linea["producto"], "precio_anterior": precio_xl,
                            "precio_nuevo": precio_ed, "semana": linea["semana"],
                            "año": linea["año"], "unico": unico})

        st.markdown(f"<div style='text-align:right;font-weight:bold;margin:4px 0'>"
                    f"Total: Q{total_ed:,.2f}</div>", unsafe_allow_html=True)
        if hay_cambios:
            st.caption("⚠️ Hay precios modificados.")
        st.divider()

        col_save, col_pdf, col_acc = st.columns(3)
        with col_save:
            if st.button("💾 Guardar cambios" if hay_cambios else "✅ Sin cambios",
                         key=f"env_save_{sufijo}_{unico}",
                         type="primary" if hay_cambios else "secondary",
                         disabled=not hay_cambios):
                with st.spinner("Guardando..."):
                    n = guardar_cambios_precio(cambios)
                for linea in lineas:
                    st.session_state.pop(f"env_{sufijo}_{unico}_{linea['row_num']}", None)
                st.success(f"✅ {n} precio(s) guardado(s)."); st.rerun()

        with col_pdf:
            try:
                pdf_bytes = generar_envio(cliente=cliente_info, fecha=fecha_ped,
                                          lineas=lineas_pdf, unico=unico)
                st.download_button("📄 Descargar PDF", data=pdf_bytes,
                    file_name=nombre_archivo(l0["cliente"], fecha_ped),
                    mime="application/pdf",
                    key=f"env_pdf_{sufijo}_{unico}", type="primary")
            except Exception as e:
                st.error(f"Error PDF: {e}")

        with col_acc:
            if not cancelado:
                if st.button("🔴 Cancelar", key=f"env_can_{sufijo}_{unico}",
                             type="secondary"):
                    with st.spinner(): cancelar_pedido(unico)
                    st.success("Cancelado."); st.rerun()
            else:
                if st.button("🟢 Restaurar", key=f"env_res_{sufijo}_{unico}",
                             type="secondary"):
                    with st.spinner(): restaurar_pedido(unico)
                    st.success("Restaurado."); st.rerun()


def mostrar():
    st.markdown("## 🚚 Envíos y Facturación — Semana Actual")

    with st.spinner("Cargando..."):
        todos    = leer_pedidos()
        cli_list = cargar_clientes()

    hoy        = date.today()
    sem_act    = hoy.isocalendar()[1]
    año_act    = hoy.year

    pedidos_sem = [p for p in todos
                   if p["semana"] == sem_act and p["año"] == año_act]

    st.markdown(f"**Semana {sem_act} · {año_act}** — {hoy.strftime('%d/%m/%Y')}")

    if not pedidos_sem:
        st.info(f"No hay pedidos para la semana {sem_act}."); return

    # Agrupar por Unico
    grupos: dict = {}
    for p in pedidos_sem:
        grupos.setdefault(p["unico"], []).append(p)

    # Mapas de clientes
    mapa_exact = {c["nombre"]: c for c in cli_list}
    mapa_lower = {c["nombre"].lower(): c for c in cli_list}

    # Separar por zona
    por_zona: dict = {z: {} for z in ZONAS_ENVIO}
    sin_zona = {}
    for unico, ls in grupos.items():
        zona = _detectar_zona(ls[0], mapa_exact, mapa_lower)
        if zona and zona in por_zona:
            por_zona[zona][unico] = ls
        else:
            sin_zona[unico] = ls

    # Ordenar por fecha desc
    def _ord(d):
        return dict(sorted(d.items(),
                    key=lambda x: str(x[1][0]["fecha"] or ""), reverse=True))

    por_zona = {z: _ord(v) for z, v in por_zona.items()}

    # Resumen
    total_peds = sum(len(v) for v in por_zona.values())
    resumen    = " · ".join(f"{z}: {len(v)}" for z, v in por_zona.items() if v)
    st.markdown(f"{total_peds} pedidos — {resumen}")

    # Tabs por zona
    tabs = st.tabs([f"{z} ({len(por_zona[z])})" for z in ZONAS_ENVIO])

    for tab, zona in zip(tabs, ZONAS_ENVIO):
        with tab:
            grupo_zona = por_zona[zona]
            sufijo     = zona[:2].strip()
            if not grupo_zona:
                st.info(f"No hay pedidos para {zona} esta semana.")
                continue
            for unico, ls in grupo_zona.items():
                cli_info = _get_cli(ls[0]["cliente"], mapa_exact, mapa_lower) \
                           or {"nombre": ls[0]["cliente"]}
                _pedido_card(unico, ls, cli_info, sufijo=sufijo)

    # Pedidos sin zona identificada
    if sin_zona:
        with st.expander(f"⚠️ Sin zona identificada ({len(sin_zona)})", expanded=False):
            for unico, ls in _ord(sin_zona).items():
                cli_info = _get_cli(ls[0]["cliente"], mapa_exact, mapa_lower) \
                           or {"nombre": ls[0]["cliente"]}
                _pedido_card(unico, ls, cli_info, sufijo="sz")
