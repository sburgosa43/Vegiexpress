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
        st.dataframe(df, use_container_width=True, hide_index=True)
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


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def mostrar():
    st.markdown("## 🧮 Cotizador de Precios")
    st.caption("IVA 12% · ISR 5% · Fórmulas según Listado de Productos")

    tab1, tab2, tab3 = st.tabs([
        "💡 Calcular Precio",
        "🔍 Verificar Margen",
        "📊 Comparar Escenarios",
    ])

    with tab1: _tab_calcular()
    with tab2: _tab_verificar()
    with tab3: _tab_escenarios()
