"""
modulo_cotizador.py — Cotizador de precios
Calcula precios de venta aplicando IVA (12%) e ISR (5%).

Fórmulas base (las mismas del Listado Productos):
  Precio      = Costo × 1.12 / (1 - Margen% / (1 - ISR%))
  Margen Neto = (1 - ISR%) × (Precio - Costo × 1.12)
  %Margen     = Margen Neto / Precio
  Pto.Equil.  = Costo × 1.12  (menor precio sin perder ni ganar)
"""
import streamlit as st
import pandas as pd

IVA_RATE = 0.12
ISR_RATE = 0.05


# ── CÁLCULOS ──────────────────────────────────────────────────────────────────

def _desde_margen_pct(costo: float, margen_pct: float) -> dict | None:
    """Precio dado costo y margen neto deseado en %."""
    denom = 1 - margen_pct / 0.95
    if denom <= 0 or costo <= 0:
        return None
    precio = costo * (1 + IVA_RATE) / denom
    return _desglose(costo, precio)


def _desde_margen_q(costo: float, margen_q: float) -> dict | None:
    """Precio dado costo y margen neto deseado en Q."""
    if costo <= 0:
        return None
    precio = margen_q / (1 - ISR_RATE) + costo * (1 + IVA_RATE)
    return _desglose(costo, precio)


def _desglose(costo: float, precio: float) -> dict | None:
    """Todos los campos derivados dado costo y precio de venta."""
    if precio <= 0 or costo <= 0:
        return None
    precio_sin_iva  = precio / 1.12
    iva_amount      = precio - precio_sin_iva         # IVA = Precio - Precio/1.12
    isr_retencion   = precio_sin_iva * 0.05           # ISR = (Precio/1.12) x 0.05
    neto_recibido   = precio - isr_retencion          # Neto recibido despues de ISR
    margen_neto_q   = 0.95 * (precio - costo * 1.12) # Formula acordada
    margen_neto_pct = (margen_neto_q / precio * 100) if precio else 0
    pto_equilibrio  = costo * 1.12                    # Precio x 1.12 = equilibrio
    sobre_costo     = ((precio - costo) / costo * 100) if costo else 0
    return {
        "costo":           round(costo, 4),
        "precio":          round(precio, 4),
        "precio_sin_iva":  round(precio_sin_iva, 4),
        "iva_amount":      round(iva_amount, 4),
        "isr_retencion":   round(isr_retencion, 4),
        "neto_recibido":   round(neto_recibido, 4),
        "margen_neto_q":   round(margen_neto_q, 4),
        "margen_neto_pct": round(margen_neto_pct, 2),
        "pto_equilibrio":  round(pto_equilibrio, 4),
        "sobre_costo":     round(sobre_costo, 2),
        "rentable":        margen_neto_q > 0,
    }


# ── COMPONENTES UI ────────────────────────────────────────────────────────────

def _mostrar_resultado(d: dict, titulo: str = "Resultado"):
    color_card = "#e8f5e9" if d["rentable"] else "#ffebee"
    color_margen = "#2e7d32" if d["rentable"] else "#c62828"
    alerta = "" if d["rentable"] else "⚠️ Este precio está por debajo del punto de equilibrio."

    st.markdown(f"""
    <div style='background:{color_card};border-radius:8px;padding:14px 18px;margin:8px 0'>
        <h4 style='margin:0 0 10px 0'>{titulo}</h4>
        <div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px'>
            <div>
                <div style='font-size:.8rem;color:#555'>Precio de venta (con IVA)</div>
                <div style='font-size:1.5rem;font-weight:bold'>Q{d['precio']:,.4f}</div>
            </div>
            <div>
                <div style='font-size:.8rem;color:#555'>Margen Neto (Q)</div>
                <div style='font-size:1.5rem;font-weight:bold;color:{color_margen}'>
                    Q{d['margen_neto_q']:,.4f}
                </div>
            </div>
            <div>
                <div style='font-size:.8rem;color:#555'>Margen Neto (%)</div>
                <div style='font-size:1.5rem;font-weight:bold;color:{color_margen}'>
                    {d['margen_neto_pct']:.2f}%
                </div>
            </div>
        </div>
        {'<p style="color:#c62828;margin:8px 0 0 0;font-size:.9rem">'+alerta+'</p>' if alerta else ''}
    </div>
    """, unsafe_allow_html=True)

    with st.expander("📊 Desglose completo"):
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Costo de compra",       f"Q{d['costo']:,.4f}")
            st.metric("Precio sin IVA",         f"Q{d['precio_sin_iva']:,.4f}")
            st.metric("IVA (12%)",              f"Q{d['iva_amount']:,.4f}")
            st.metric("ISR (Precio/1.12 × 5%)", f"Q{d['isr_retencion']:,.4f}")
        with c2:
            st.metric("Neto que recibís",       f"Q{d['neto_recibido']:,.4f}")
            st.metric("Margen neto (Q)",        f"Q{d['margen_neto_q']:,.4f}")
            st.metric("Margen neto (%)",        f"{d['margen_neto_pct']:.2f}%")
            st.metric("Punto de equilibrio",    f"Q{d['pto_equilibrio']:,.4f}")
        st.caption(
            f"Markup sobre costo: {d['sobre_costo']:.1f}% · "
            f"Por cada Q100 de venta, tu bolsillo recibe Q{d['margen_neto_pct']:.1f}"
        )


# ── TAB 1: CALCULAR PRECIO ────────────────────────────────────────────────────
def _tab_calcular():
    st.markdown("#### Calculá el precio de venta desde tu costo y margen deseado")

    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        costo = st.number_input("💰 Costo de compra (Q)",
                                 min_value=0.01, value=5.0, step=0.50,
                                 key="cot_costo_c")
    with c2:
        modo_margen = st.radio("Margen deseado en",
                                ["Porcentaje (%)", "Quetzales (Q)"],
                                horizontal=True, key="cot_modo")
    with c3:
        if modo_margen == "Porcentaje (%)":
            margen_val = st.number_input("📈 Margen neto deseado (%)",
                                          min_value=0.0, max_value=94.0,
                                          value=30.0, step=1.0,
                                          key="cot_margen_pct",
                                          help="% del precio de venta que queda como ganancia neta")
        else:
            margen_val = st.number_input("📈 Margen neto deseado (Q por unidad)",
                                          min_value=0.0,
                                          value=2.0, step=0.25,
                                          key="cot_margen_q",
                                          help="Q que querés ganar por cada unidad vendida")

    st.divider()

    # Calcular
    if modo_margen == "Porcentaje (%)":
        resultado = _desde_margen_pct(costo, margen_val / 100)
    else:
        resultado = _desde_margen_q(costo, margen_val)

    if resultado is None:
        st.error("Verificá los valores ingresados. El margen no puede superar el 95%.")
        return

    _mostrar_resultado(resultado, "💡 Precio sugerido")

    # Ajuste manual del precio
    st.divider()
    st.markdown("#### ¿Querés ajustar el precio final?")
    st.caption("Ingresá el precio que pensás cobrar y ves el impacto en tu margen.")

    precio_ajustado = st.number_input(
        "Precio final a cobrar (Q)",
        min_value=0.01,
        value=round(resultado["precio"], 2),
        step=0.25,
        key="cot_precio_ajuste",
    )
    if precio_ajustado != resultado["precio"]:
        d_ajustado = _desglose(costo, precio_ajustado)
        if d_ajustado:
            diff_margen = d_ajustado["margen_neto_q"] - resultado["margen_neto_q"]
            st.markdown(
                f"**Impacto:** margen neto cambia de "
                f"Q{resultado['margen_neto_q']:,.2f} → "
                f"Q{d_ajustado['margen_neto_q']:,.2f} "
                f"({'▲' if diff_margen >= 0 else '▼'} Q{abs(diff_margen):,.2f})"
            )
            _mostrar_resultado(d_ajustado, "📌 Con precio ajustado")


# ── TAB 2: VERIFICAR MARGEN ───────────────────────────────────────────────────
def _tab_verificar():
    st.markdown("#### Dado un costo y un precio, ¿cuánto ganás?")

    c1, c2 = st.columns(2)
    with c1:
        costo  = st.number_input("💰 Costo de compra (Q)",
                                  min_value=0.01, value=5.0, step=0.50,
                                  key="cot_costo_v")
    with c2:
        precio = st.number_input("🏷️ Precio de venta (Q, con IVA)",
                                  min_value=0.01, value=8.0, step=0.25,
                                  key="cot_precio_v")

    st.divider()

    resultado = _desglose(costo, precio)
    if resultado:
        _mostrar_resultado(resultado, "📊 Análisis de margen")

        if precio < resultado["pto_equilibrio"]:
            st.error(
                f"⚠️ Estás vendiendo por debajo del punto de equilibrio "
                f"(Q{resultado['pto_equilibrio']:,.4f}). "
                f"Perdés Q{abs(resultado['margen_neto_q']):,.4f} por unidad."
            )
        elif resultado["margen_neto_pct"] < 15:
            st.warning(
                f"El margen del {resultado['margen_neto_pct']:.1f}% "
                f"es bajo. Considerá subir el precio."
            )


# ── TAB 3: COMPARAR ESCENARIOS ────────────────────────────────────────────────
def _tab_escenarios():
    st.markdown("#### Tabla de precios para distintos márgenes con el mismo costo")

    costo = st.number_input("💰 Costo de compra (Q)",
                             min_value=0.01, value=5.0, step=0.50,
                             key="cot_costo_e")

    margenes = [10, 15, 20, 25, 30, 35, 40, 45, 50]

    filas = []
    for m in margenes:
        d = _desde_margen_pct(costo, m / 100)
        if d:
            filas.append({
                "Margen %":        f"{m}%",
                "Precio venta (Q)": f"Q{d['precio']:,.2f}",
                "Precio s/IVA":    f"Q{d['precio_sin_iva']:,.2f}",
                "IVA (Q)":         f"Q{d['iva_amount']:,.2f}",
                "ISR ret. (Q)":    f"Q{d['isr_retencion']:,.2f}",
                "Margen neto (Q)": f"Q{d['margen_neto_q']:,.2f}",
                "Pto. Equilibrio": f"Q{d['pto_equilibrio']:,.2f}",
            })

    if filas:
        df = pd.DataFrame(filas)
        st.dataframe(df, use_container_width=True, hide_index=True,
                     column_config={
                         "Margen %":         st.column_config.TextColumn(width="small"),
                         "Precio venta (Q)": st.column_config.TextColumn(width="medium"),
                         "Precio s/IVA":     st.column_config.TextColumn(width="medium"),
                         "IVA (Q)":          st.column_config.TextColumn(width="medium"),
                         "ISR ret. (Q)":     st.column_config.TextColumn(width="medium"),
                         "Margen neto (Q)":  st.column_config.TextColumn(width="medium"),
                         "Pto. Equilibrio":  st.column_config.TextColumn(width="medium"),
                     })
        st.caption(
            f"Costo base: Q{costo:.2f} · "
            f"Punto de equilibrio: Q{costo * 1.12:.4f} · "
            f"IVA 12% · ISR 5%"
        )

    # Margen personalizado
    st.divider()
    st.markdown("#### Calculá con un margen específico")
    m_custom = st.slider("Margen neto deseado (%)", 1, 90, 30, key="cot_slider")
    d_custom = _desde_margen_pct(costo, m_custom / 100)
    if d_custom:
        cc1, cc2, cc3, cc4 = st.columns(4)
        cc1.metric("Precio de venta",   f"Q{d_custom['precio']:,.4f}")
        cc2.metric("Margen neto (Q)",   f"Q{d_custom['margen_neto_q']:,.4f}")
        cc3.metric("Neto que recibís",  f"Q{d_custom['neto_recibido']:,.4f}")
        cc4.metric("Precio sin IVA",    f"Q{d_custom['precio_sin_iva']:,.4f}")



# ── COTIZACIÓN DE PRECIOS ─────────────────────────────────────────────────────
def _cotizacion():
    from datetime import date, timedelta
    from data_helper import cargar_productos
    from pdf_helper  import generar_cotizacion

    st.markdown("Generá un PDF de cotización para prospectar clientes o "
                "comunicar cambios de precios.")
    st.divider()

    # Vigencia
    v1, v2 = st.columns(2)
    with v1:
        desde = st.date_input("Vigente desde", value=date.today(), key="cot_desde")
    with v2:
        hasta = st.date_input("Vigente hasta",
                               value=date.today() + timedelta(days=30),
                               key="cot_hasta")

    st.divider()

    # Quién cotiza
    COTIZADORES = {
        "Andrea Castillo Sanabria": "Tel. 59306817",
        "Sergio Burgos Alburez":    "Tel. 58749679",
    }
    cotizador_nombre = st.selectbox("Elaborado por:", list(COTIZADORES.keys()),
                                     key="cot_quien")
    cotizador_tel    = COTIZADORES[cotizador_nombre]

    st.divider()
    st.markdown("**Productos a cotizar** — seleccioná y ajustá el precio:")

    SEGS = {"Premium":50,"Alto":40,"Media Alta":35,"Media":30,
            "Media Baja":25,"Baja":20,"Sin Segmento":0}

    prods      = cargar_productos(False)
    prod_dict  = {p["nombre"]: p for p in prods}
    nombres    = [""] + sorted([p["nombre"] for p in prods])
    n_filas    = st.session_state.get("cot_nfilas", 15)

    # Init grilla
    if "cot_grilla" not in st.session_state:
        st.session_state["cot_grilla"] = [
            {"producto":"","precio_cotizar":0.0} for _ in range(n_filas)]
    elif len(st.session_state["cot_grilla"]) < n_filas:
        while len(st.session_state["cot_grilla"]) < n_filas:
            st.session_state["cot_grilla"].append({"producto":"","precio_cotizar":0.0})

    grilla = st.session_state["cot_grilla"]
    lineas_pdf = []

    # Encabezado
    hdr = st.columns([2.4, 0.9, 0.9, 1.0, 1.0, 1.2, 0.85, 0.95, 0.9, 0.9])
    for h, lbl in zip(hdr, ["Producto","Unidad","Costo","Pto. Eq.","P. Imp.",
                              "Precio Cotizar","Margen %","Margen Q","IVA/u","ISR/u"]):
        h.markdown(f"<small><b>{lbl}</b></small>", unsafe_allow_html=True)

    for i, fila in enumerate(grilla):
        k_prod = f"cot_prod_{i}"
        k_prec = f"cot_prec_{i}"

        r = st.columns([2.4, 0.9, 0.9, 1.0, 1.0, 1.2, 0.85, 0.95, 0.9, 0.9])
        prod_sel = r[0].selectbox("", nombres,
            index=(nombres.index(fila["producto"]) if fila["producto"] in nombres else 0),
            key=k_prod, label_visibility="collapsed")

        if prod_sel and prod_sel in prod_dict:
            p      = prod_dict[prod_sel]
            costo  = float(p.get("costo", 0))
            seg    = SEGS.get(p.get("tipo_producto2",""), 0) / 100
            pto_eq = round(costo * 1.12, 2) if costo else 0
            p_imp  = round(costo / (1 - seg/0.95) * 1.12, 2) if seg > 0 and costo else 0

            if k_prec not in st.session_state:
                st.session_state[k_prec] = float(p.get("precio", 0))

            def _ref(col, txt):
                col.markdown(
                    f"<div style='padding-top:8px;font-size:.78rem;color:#888'>"
                    f"{txt}</div>", unsafe_allow_html=True)

            r[1].markdown(
                f"<div style='padding-top:8px;font-size:.82rem'>"
                f"{p.get('unidad','')}</div>", unsafe_allow_html=True)
            _ref(r[2], f"Q{costo:,.2f}" if costo else "—")
            _ref(r[3], f"Q{pto_eq:,.2f}" if pto_eq else "—")
            _ref(r[4], f"Q{p_imp:,.2f}"  if p_imp  else "—")

            precio_ed = r[5].number_input("", min_value=0.0,
                value=float(st.session_state[k_prec]),
                step=0.25, key=k_prec, label_visibility="collapsed")

            # Cálculos por unidad en tiempo real
            if precio_ed > 0 and costo > 0:
                margen_pct = round(0.95 * (1 - costo * 1.12 / precio_ed) * 100, 1)
                margen_q   = round(0.95 * (precio_ed - costo * 1.12), 2)
                iva_u      = round(precio_ed - precio_ed / 1.12, 2)
                isr_u      = round(precio_ed / 1.12 * 0.05, 2)
                color_m    = "#2D7A2D" if margen_pct >= 20 else "#E65100"
                _ref(r[6], f"<span style='color:{color_m}'><b>{margen_pct}%</b></span>")
                _ref(r[7], f"<span style='color:{color_m}'>Q{margen_q:,.2f}</span>")
                _ref(r[8], f"Q{iva_u:,.2f}")
                _ref(r[9], f"Q{isr_u:,.2f}")
            elif precio_ed > 0:
                for col in r[6:]: _ref(col, "—")
            else:
                for col in r[6:]: col.write("")

            grilla[i] = {"producto": prod_sel, "precio_cotizar": precio_ed}

            if precio_ed > 0:
                lineas_pdf.append({"producto": prod_sel,
                                   "unidad":   p.get("unidad",""),
                                   "precio_cotizar": precio_ed})
        else:
            grilla[i] = {"producto":"","precio_cotizar":0.0}
            for col in r[1:]: col.write("")

    st.session_state["cot_grilla"] = grilla

    # Botones de fila
    ba, bb, bc = st.columns(3)
    with ba:
        if st.button("+ 5 líneas", key="cot_add5"):
            st.session_state["cot_nfilas"] = n_filas + 5; st.rerun()
    with bb:
        if st.button("+ 10 líneas", key="cot_add10"):
            st.session_state["cot_nfilas"] = n_filas + 10; st.rerun()
    with bc:
        if st.button("🗑 Limpiar grilla", key="cot_clear", type="secondary"):
            st.session_state.pop("cot_grilla", None)
            st.session_state["cot_nfilas"] = 15
            for i in range(50):
                st.session_state.pop(f"cot_prod_{i}", None)
                st.session_state.pop(f"cot_prec_{i}", None)
            st.rerun()

    st.divider()

    if lineas_pdf:
        st.success(f"**{len(lineas_pdf)} producto(s)** listos para el PDF.")

        notas_cot = st.text_area(
            "",
            placeholder="Ej: Precios sin IVA · Precios sujetos a cambio · "
                        "Disponibilidad sujeta a programa de siembra...",
            height=90,
            key="cot_notas",
            label_visibility="collapsed",
        )

        if st.button("📄 Generar PDF de Cotización", type="primary"):
            with st.spinner("Generando PDF..."):
                pdf_bytes = generar_cotizacion(lineas_pdf, desde, hasta,
                                       cotizador=cotizador_nombre,
                                       cotizador_tel=cotizador_tel,
                                       notas=notas_cot)
            nombre = f"Cotizacion_VeggiExpress_{desde.strftime('%d%m%Y')}.pdf"
            st.download_button("📥 Descargar PDF", data=pdf_bytes,
                file_name=nombre, mime="application/pdf",
                key="cot_dl", type="primary")
    else:
        st.info("Seleccioná al menos un producto para generar la cotización.")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def mostrar():
    st.markdown("## 🧮 Cotizador de Precios")
    if st.button("🏠 Inicio", key="btn_home_cot", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    st.caption("IVA 12% · ISR 5% · Fórmulas según Listado de Productos")

    tab1, tab2, tab3, tab4 = st.tabs([
        "💡 Calcular Precio",
        "🔍 Verificar Margen",
        "📊 Comparar Escenarios",
        "📋 Cotización de Precios",
    ])

    with tab1: _tab_calcular()
    with tab2: _tab_verificar()
    with tab3: _tab_escenarios()
    with tab4: _cotizacion()
