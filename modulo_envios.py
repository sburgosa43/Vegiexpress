"""
modulo_envios.py — Envíos y Facturación Semana Actual
Tres zonas: Antigua & Chimal | Guatemala & Santiago | Rio
"""
import streamlit as st
import pandas as pd
import base64
import streamlit.components.v1 as components
from datetime import date
from excel_helper import (leer_pedidos_op as leer_pedidos, cancelar_pedido,
                          restaurar_pedido, guardar_cambios_precio)
from data_helper  import cargar_clientes
from pdf_helper   import generar_envio, nombre_archivo
from config       import (ZONAS_MAP as _ZONAS_CFG, excluido_dashboard, es_hogar,
                           calcular_liquido)

ZONAS_ENVIO = _ZONAS_CFG   # Fuente única: config.py

@st.cache_data(ttl=180, max_entries=80, show_spinner=False)
def _pdf_envio_cached(cliente_info: dict, fecha_ped, lineas_pdf: list,
                      unico: str) -> bytes:
    """PDF de envío CACHEADO. Antes se regeneraba por CADA pedido en CADA
    rerun (~2 PDFs × N pedidos por interacción), acumulando CPU y memoria
    hasta tumbar la app en Streamlit Cloud. La clave incluye las líneas:
    si el pedido cambia, el PDF se regenera solo."""
    from pdf_helper import generar_envio
    return generar_envio(cliente=cliente_info, fecha=fecha_ped,
                         lineas=lineas_pdf, unico=unico)


@st.cache_data(ttl=180, max_entries=80, show_spinner=False)
def _pdf_remision_cached(cliente: str, lineas: list, semana: int,
                         año: int, fecha_str: str) -> bytes:
    """PDF de remisión CACHEADO (mismo motivo que _pdf_envio_cached)."""
    from pdf_helper import generar_remision
    return generar_remision(cliente, lineas, semana, año, fecha_str)


@st.cache_data(ttl=300)
def _get_cli_map():
    try:
        from data_helper import cargar_clientes
        return {c["nombre"].lower().strip(): c for c in cargar_clientes()}
    except Exception:
        return {}

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
    return None  # Sin zona definida — revisar código_lugar del cliente

def _pedido_card(unico: str, lineas: list, cliente_info: dict, sufijo: str):
    l0        = lineas[0]
    cancelado = all(l["status"] == "Cancelado" for l in lineas)
    fecha_ped = l0["fecha"] if l0["fecha"] else date.today()
    total_orig = sum(l["total"] or 0 for l in lineas)

    # Margen Bruto: (precio - costo) x cantidad  |  Margen Neto: formula margen_q
    mb_ped = sum((float(l.get("precio") or 0) - float(l.get("costo") or 0))
                 * float(l.get("cantidad") or 0) for l in lineas)
    mn_ped = sum(float(l.get("margen_q") or 0) for l in lineas)

    # Desglose fiscal sobre el total ORIGINAL (referencia de factura)
    # Mismas reglas que Facturacion Mensual: calcular_liquido maneja ISR/descuento
    liq_ped, isr_ped, desc_ped = calcular_liquido(l0["cliente"], total_orig)
    base_iva = round(total_orig / 1.12, 2)

    with st.expander(
        f"{'🔴' if cancelado else '🟢'}  **{l0['cliente']}**  ·  "
        f"{fecha_ped.strftime('%d/%m/%Y')}  ·  "
        f"{len(lineas)} productos  ·  Q{total_orig:,.2f}",
        expanded=False,
    ):
        extra_txt = ""
        if isr_ped > 0:
            extra_txt = f"ISR: Q{isr_ped:,.2f}  ·  "
        elif desc_ped > 0:
            extra_txt = f"Descuento: Q{desc_ped:,.2f}  ·  "
        _nit = (cliente_info or {}).get("nit") or "—"
        st.markdown(
            f"<div style='background:#2D7A2D;color:white;padding:6px 10px;"
            f"border-radius:4px;font-size:.82rem;font-weight:bold;"
            f"margin:0 0 8px 0'>"
            f"NIT: {_nit}  ·  Total: Q{total_orig:,.2f}  ·  Base IVA: Q{base_iva:,.2f}"
            f"<br><span style='font-weight:normal;font-size:.78rem;opacity:.95'>"
            f"{extra_txt}"
            f"Líquido: Q{liq_ped:,.2f}  ·  "
            f"MB: Q{mb_ped:,.0f}  ·  MN: Q{mn_ped:,.0f}</span></div>",
            unsafe_allow_html=True)

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

        col_save, col_pdf, col_rem, col_acc = st.columns(4)
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
                pdf_bytes = _pdf_envio_cached(cliente_info, fecha_ped,
                                              lineas_pdf, unico)
                st.download_button("📄 Descargar PDF", data=pdf_bytes,
                    file_name=nombre_archivo(l0["cliente"], fecha_ped),
                    mime="application/pdf",
                    key=f"env_pdf_{sufijo}_{unico}", type="primary")
            except Exception as e:
                st.error(f"Error PDF: {e}")

        with col_rem:
            try:
                from pdf_helper import (generar_remision as _gen_rem,
                                        boton_imprimir_html as _btn_imp)
                _lr = [{"producto": l["producto"], "unidad": l.get("unidad",""),
                        "cantidad": float(l.get("cantidad") or 0),
                        "total": round(float(l.get("precio") or 0)*float(l.get("cantidad") or 0),2)}
                       for l in lineas_pdf]
                _rb = _pdf_remision_cached(l0["cliente"], _lr,
                                           int(l0["semana"]), int(l0["año"]),
                                           fecha_ped.strftime("%d/%m/%Y"))
                components.html(
                    _btn_imp(_rb, f"env_{sufijo}_{unico}", "🖨️ Remisión"),
                    height=44)
            except Exception as _e:
                col_rem.caption("Rem: " + str(_e))

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


AREAS_LIST = {
    "🌊 Río":     lambda cli, z: z in ("L01", "L02"),
    "🏙️ Guate":  lambda cli, z: z in ("L05", "L06") and z != "L20",
    "🔖 Antigua": lambda cli, z: z == "L03",
    "🔖 Chimal":  lambda cli, z: z == "L04",
    "🏠 Hogares": lambda cli, z: z == "L20" or "veggi hogares" in cli.lower(),
}


def _tab_listados(todos, semana, año):
    from pdf_helper import generar_listado_checklist

    st.markdown("### 📋 Listado de Empaque")
    st.caption("Semana actual — imprimible como checklist de preparación")

    # Cargar mapa cliente → zona
    cli_list = cargar_clientes()
    cli_zona = {c["nombre"].lower(): c["codigo_lugar"] for c in cli_list}

    # Filtro de área
    areas_sel = st.multiselect(
        "Seleccioná área(s):",
        list(AREAS_LIST.keys()),
        default=list(AREAS_LIST.keys()),
        key="list_areas"
    )
    if not areas_sel:
        st.info("Seleccioná al menos un área.")
        return

    # Filtrar pedidos de la semana actual por áreas seleccionadas
    def en_area(p):
        zona = cli_zona.get(p["cliente"].lower(), "")
        return any(AREAS_LIST[a](p["cliente"], zona) for a in areas_sel)

    pedidos = [
        p for p in todos
        if p["semana"] == semana and p["año"] == año
        and p["status"] != "Cancelado"
        and float(p.get("cantidad") or 0) > 0
        and en_area(p)
    ]

    if not pedidos:
        st.warning("Sin pedidos para las áreas seleccionadas.")
        return

    # Agrupar por cliente → lista de productos (ordenados alfabéticamente)
    clientes_dict = {}
    for p in pedidos:
        cli = p["cliente"]
        if cli not in clientes_dict:
            clientes_dict[cli] = []
        clientes_dict[cli].append({
            "cliente":   cli,
            "producto":  p["producto"],
            "unidad":    p.get("unidad",""),
            "cantidad":  float(p.get("cantidad") or 0),
        })
    # Ordenar productos dentro de cada cliente
    for cli in clientes_dict:
        clientes_dict[cli].sort(key=lambda x: x["producto"])

    clientes_ord = sorted(clientes_dict.keys())
    total = sum(len(v) for v in clientes_dict.values())
    st.markdown(f"**{len(clientes_ord)} cliente(s) · {total} línea(s)**")
    area_label = ", ".join(areas_sel)

    # ── Generar PDF ───────────────────────────────────────────────────────────
    # Agrupar por cliente para empaque inteligente
    clientes_grupos = []
    for cli in clientes_ord:
        clientes_grupos.append((cli, clientes_dict[cli]))

    with st.spinner("Generando listado..."):
        pdf_bytes = generar_listado_checklist(
            clientes_grupos, area_label, semana, año)
    pdf_b64 = base64.b64encode(pdf_bytes).decode()

    # Botones
    bc1, bc2 = st.columns(2)

    # Botón descarga PDF
    bc1.download_button(
        "📥 Descargar PDF",
        data=pdf_bytes,
        file_name=f"Listado_Sem{semana}_{año}_{area_label.replace(', ','_')}.pdf",
        mime="application/pdf",
        type="primary",
        use_container_width=True,
        key="dl_listado"
    )

    # Botón imprimir usando el helper unificado (iframe + opción abrir a 100%)
    from pdf_helper import boton_imprimir_html as _btn_imp_lst
    with bc2:
        import streamlit.components.v1 as components
        components.html(
            _btn_imp_lst(pdf_bytes, f"listado_{semana}_{año}",
                         "🖨️ Abrir e imprimir", "#2D7A2D"),
            height=48)

    # ── Vista previa embebida (blob URL) ────────────────────────────────────
    st.markdown("**Vista previa:**")
    import streamlit.components.v1 as components
    preview_html = f"""
    <div id="pdf-container" style="width:100%;height:700px;border:1px solid #ddd;border-radius:4px;">
      <iframe id="pdf-frame" width="100%" height="700px"
              style="border:none;border-radius:4px;"></iframe>
    </div>
    <script>
      (function() {{
        var b64 = '{pdf_b64}';
        var raw = atob(b64);
        var arr = new Uint8Array(raw.length);
        for (var i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
        var blob = new Blob([arr], {{type: 'application/pdf'}});
        var url  = URL.createObjectURL(blob);
        document.getElementById('pdf-frame').src = url;
      }})();
    </script>
    """
    components.html(preview_html, height=720, scrolling=False)


def mostrar():
    st.markdown("## 🚚 Envíos y Facturación")
    # Botón de regreso al Inicio
    if st.button("🏠 Inicio", key="btn_home_env", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()


    with st.spinner("Cargando..."):
        todos    = leer_pedidos()
        cli_list = cargar_clientes()

    hoy        = date.today()
    sem_hoy    = hoy.isocalendar()[1]
    año_hoy    = hoy.year

    # ── Selector de semana (default: semana actual) ──────────────────────────
    # Se listan las semanas que tienen pedidos, más reciente primero; la actual
    # queda seleccionada por defecto aunque aún no tenga pedidos.
    semanas_disp = sorted({(p["año"], p["semana"]) for p in todos}, reverse=True)
    if (año_hoy, sem_hoy) not in semanas_disp:
        semanas_disp = [(año_hoy, sem_hoy)] + semanas_disp

    def _fmt_sem(t):
        a, s = t
        return (f"Semana {s} · {a}"
                + ("  (actual)" if (a, s) == (año_hoy, sem_hoy) else ""))

    idx_def = semanas_disp.index((año_hoy, sem_hoy)) \
        if (año_hoy, sem_hoy) in semanas_disp else 0
    sel = st.selectbox("📅 Semana a mostrar:", semanas_disp, index=idx_def,
                       format_func=_fmt_sem, key="env_semana_sel")
    año_act, sem_act = sel[0], sel[1]

    pedidos_sem = [p for p in todos
                   if p["semana"] == sem_act and p["año"] == año_act]

    if not pedidos_sem:
        st.info(f"No hay pedidos para la semana {sem_act} · {año_act}."); return

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
    # Add Listados as extra tab
    tab_labels = [f"{z} ({len(por_zona[z])})" for z in ZONAS_ENVIO] + ["📋 Listados", "🖨️ Impresión Masiva"]
    all_tabs   = st.tabs(tab_labels)
    envio_tabs = all_tabs[:-2]
    tab_list   = all_tabs[-2]
    tab_masiva = all_tabs[-1]

    for tab, zona in zip(envio_tabs, ZONAS_ENVIO):
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

    # ── TAB LISTADOS ──────────────────────────────────────────────────────────
    with tab_list:
        _tab_listados(todos, sem_act, año_act)

    with tab_masiva:
        _tab_impresion_masiva(todos, cli_list, sem_act, año_act)


# ── IMPRESIÓN MASIVA ───────────────────────────────────────────────────────────
def _tab_impresion_masiva(todos: list, cli_list: list, sem_def: int, año_def: int):
    """PDFs individuales por cliente para un área y semana — impresión masiva."""
    import streamlit.components.v1 as components
    from pdf_helper import generar_envio, nombre_archivo

    st.markdown("### 🖨️ Impresión Masiva por Área")
    st.caption("Un PDF por cliente · filtrá por semana y área · imprimí o descargá individualmente")

    # ── Filtros ────────────────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns(3)
    semana  = fc1.number_input("Semana", 1, 53, sem_def, key="im_sem")
    año     = fc2.number_input("Año", 2020, 2030, año_def, key="im_año")
    zonas   = list(ZONAS_ENVIO.keys())
    area    = fc3.selectbox("Área", zonas, key="im_area")

    # ── Filtrar pedidos ────────────────────────────────────────────────────────
    codigos_zona = ZONAS_ENVIO[area]
    cli_map  = {c["nombre"]: c for c in cli_list}
    cli_zona = {c["nombre"].lower(): c["codigo_lugar"] for c in cli_list}

    pedidos_sem = [
        p for p in todos
        if p["semana"] == semana and p["año"] == año
        and p["status"] != "Cancelado"
        and float(p.get("cantidad") or 0) > 0
        and cli_zona.get(p["cliente"].lower(), "") in codigos_zona
    ]

    if not pedidos_sem:
        st.info(f"Sin pedidos activos en {area} para semana {semana}/{año}.")
        return

    # Agrupar por cliente
    por_cliente = {}
    for p in pedidos_sem:
        cli = p["cliente"]
        if cli not in por_cliente:
            por_cliente[cli] = []
        por_cliente[cli].append(p)

    st.divider()
    total_lineas = sum(len(v) for v in por_cliente.values())
    st.markdown(f"**{len(por_cliente)} cliente(s) · {total_lineas} línea(s) en {area}**")

    # ── Selector de clientes ───────────────────────────────────────────────────
    sel_clis = st.multiselect(
        "Clientes a imprimir:",
        sorted(por_cliente.keys()),
        default=sorted(por_cliente.keys()),
        key="im_sel_clis",
    )

    if not sel_clis:
        st.info("Seleccioná al menos un cliente.")
        return

    st.divider()

    # ── PDF por cliente ────────────────────────────────────────────────────────
    for cli_nombre in sorted(sel_clis):
        peds = por_cliente[cli_nombre]
        fechas   = [p["fecha"] for p in peds if p["fecha"]]
        fecha_ent = max(fechas) if fechas else None
        cli_info = cli_map.get(cli_nombre, {
            "nombre": cli_nombre, "empresa": cli_nombre,
            "direccion": "", "nit": "CF", "telefono": "",
        })

        lineas = sorted([{
            "producto": p["producto"],
            "cantidad": float(p.get("cantidad") or 0),
            "unidad":   p.get("unidad", ""),
            "precio":   float(p.get("precio") or 0),
            "total":    round(float(p.get("precio") or 0) *
                              float(p.get("cantidad") or 0), 2),
        } for p in peds], key=lambda x: x["producto"])

        total_cli = sum(l["total"] for l in lineas)

        # Generar PDF
        try:
            unico    = peds[0].get("unico", "") if peds else ""
            pdf_bytes = _pdf_envio_cached(cli_info, fecha_ent, lineas, unico)
            pdf_b64   = base64.b64encode(pdf_bytes).decode()
            nom_safe  = "".join(ch for ch in cli_nombre if ch.isalnum() or ch == "_")
            filename  = f"Envio_{nom_safe}_S{semana}_{año}.pdf"

            col_info, col_print, col_dl = st.columns([4, 1, 1])
            col_info.markdown(
                f"**{cli_nombre}** · {len(lineas)} línea(s) · "
                f"Q{total_cli:,.2f} · "
                f"{fecha_ent.strftime('%d/%m/%Y') if fecha_ent else f'Sem {semana}'}"
            )

            # Botón imprimir — usa el helper unificado (data URL, sin blob:
            # que en Chrome imprime hojas en blanco)
            from pdf_helper import boton_imprimir_html as _btn_imp_masivo
            with col_print:
                components.html(
                    _btn_imp_masivo(pdf_bytes,
                                    f"masivo_{nom_safe}_{semana}_{año}",
                                    "🖨️ Imprimir"),
                    height=44)

            col_dl.download_button(
                "📥 PDF",
                data=pdf_bytes,
                file_name=filename,
                mime="application/pdf",
                key=f"im_dl_{nom_safe}_{semana}_{año}",
                use_container_width=True,
            )

        except Exception as e:
            st.error(f"{cli_nombre}: Error generando PDF — {e}")