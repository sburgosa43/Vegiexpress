"""
modulo_mantenimiento.py — Herramientas de mantenimiento de datos
  Tab 1: Corrección masiva de precios y costos por cliente/producto/período
  Tab 2: Migración de fórmulas → valores en la hoja Pedidos
"""
import streamlit as st
from datetime import date
from excel_helper import (leer_pedidos, preview_correccion_masiva,
                           aplicar_correccion_masiva, migrar_pedidos_a_valores)
from data_helper import cargar_clientes, cargar_productos

MESES_ES = {
    1:"Enero", 2:"Febrero", 3:"Marzo", 4:"Abril",
    5:"Mayo", 6:"Junio", 7:"Julio", 8:"Agosto",
    9:"Septiembre", 10:"Octubre", 11:"Noviembre", 12:"Diciembre",
}


# ── TAB 1: CORRECCIÓN MASIVA ──────────────────────────────────────────────────
def _tab_correccion():
    st.markdown("""
    Corrige el precio y/o costo de un producto específico para un cliente,
    en un rango de fechas determinado. Recalcula automáticamente todas las
    columnas financieras (Total, Margen, IVA, ISR) en cada fila afectada.
    """)
    st.divider()

    # ── Paso 1: Parámetros ────────────────────────────────────────────────────
    st.markdown("#### 1️⃣ Definir el cambio")

    clientes_list = cargar_clientes()
    prods_list    = cargar_productos(False)
    cli_nombres   = sorted([c["nombre"] for c in clientes_list])
    prod_nombres  = sorted([p["nombre"] for p in prods_list])

    c1, c2 = st.columns(2)
    with c1:
        cliente_sel = st.selectbox("Cliente", cli_nombres,
                                    index=None, placeholder="Seleccioná...",
                                    key="mant_cli")
    with c2:
        producto_sel = st.selectbox("Producto", prod_nombres,
                                     index=None, placeholder="Seleccioná...",
                                     key="mant_prod")

    # Checkboxes precio / costo
    st.markdown("**¿Qué querés cambiar?**")
    chk1, chk2 = st.columns(2)
    with chk1:
        cambiar_precio = st.checkbox("Cambiar Precio", key="mant_chk_precio")
        if cambiar_precio:
            nuevo_precio = st.number_input("Nuevo Precio (Q)", min_value=0.01,
                                            step=0.25, key="mant_precio")
        else:
            nuevo_precio = 0.0
            st.caption("Sin Cambio de precio")
    with chk2:
        cambiar_costo = st.checkbox("Cambiar Costo", key="mant_chk_costo")
        if cambiar_costo:
            nuevo_costo = st.number_input("Nuevo Costo (Q)", min_value=0.01,
                                           step=0.25, key="mant_costo")
        else:
            nuevo_costo = 0.0
            st.caption("Sin Cambio de costo")

    # Rango de fechas
    st.markdown("**Rango de fechas (fecha de entrega):**")
    hoy = date.today()
    años_disp = list(range(hoy.year, hoy.year - 5, -1))
    meses_ops = [f"{m:02d} - {MESES_ES[m]}" for m in range(1, 13)]

    rf1, rf2, rf3, rf4 = st.columns(4)
    with rf1:
        desde_mes_lbl = st.selectbox("Desde Mes", meses_ops,
                                      index=0, key="mant_dmes")
        desde_mes = int(desde_mes_lbl[:2])
    with rf2:
        desde_año = st.selectbox("Desde Año", años_disp,
                                  index=1, key="mant_daño")
    with rf3:
        hasta_mes_lbl = st.selectbox("Hasta Mes", meses_ops,
                                      index=11, key="mant_hmes")
        hasta_mes = int(hasta_mes_lbl[:2])
    with rf4:
        hasta_año = st.selectbox("Hasta Año", años_disp,
                                  index=0, key="mant_haño")

    st.divider()

    # ── Paso 2: Preview ───────────────────────────────────────────────────────
    st.markdown("#### 2️⃣ Resumen del impacto")

    if not cliente_sel or not producto_sel:
        st.info("Seleccioná cliente y producto para ver el resumen.")
        return
    if not cambiar_precio and not cambiar_costo:
        st.info("Seleccioná al menos una opción: Cambiar Precio o Cambiar Costo.")
        return

    if st.button("🔍 Ver resumen del impacto", type="secondary"):
        with st.spinner("Analizando pedidos históricos..."):
            preview = preview_correccion_masiva(
                cliente_sel, producto_sel,
                desde_mes, desde_año, hasta_mes, hasta_año,
                nuevo_precio, nuevo_costo,
                cambiar_precio, cambiar_costo,
            )
        st.session_state["mant_preview"] = preview
        st.session_state.pop("mant_confirmar", None)

    preview = st.session_state.get("mant_preview")
    if not preview:
        return

    if preview["total_filas"] == 0:
        st.warning("No se encontraron filas que coincidan con los criterios.")
        st.session_state.pop("mant_preview", None)
        return

    # Mostrar resumen
    dv = preview["delta_ventas"]
    dm = preview["delta_margen"]

    col_r1, col_r2, col_r3 = st.columns(3)
    col_r1.metric("Filas a modificar",  preview["total_filas"])
    col_r2.metric("Impacto en Ventas",
                   f"Q{abs(dv):,.2f}",
                   f"{'▼' if dv<0 else '▲'} {abs(dv):,.2f}",
                   delta_color="inverse" if dv < 0 else "normal")
    col_r3.metric("Impacto en Margen",
                   f"Q{abs(dm):,.2f}",
                   f"{'▼' if dm<0 else '▲'} {abs(dm):,.2f}",
                   delta_color="inverse" if dm < 0 else "normal")

    # Resumen de cambios aplicados
    f0 = preview["filas"][0] if preview["filas"] else {}
    cambios_txt = []
    if cambiar_precio:
        cambios_txt.append(f"Precio: Q{f0.get('p_act',0):,.2f} → Q{nuevo_precio:,.2f}")
    if cambiar_costo:
        cambios_txt.append(f"Costo: Q{f0.get('c_act',0):,.2f} → Q{nuevo_costo:,.2f}")
    st.info(f"**{cliente_sel}** · **{producto_sel}** · "
            f"{MESES_ES[desde_mes]} {desde_año} → {MESES_ES[hasta_mes]} {hasta_año}\n\n"
            f"Cambios: {' | '.join(cambios_txt)}")

    st.divider()

    # ── Paso 3: Confirmar ─────────────────────────────────────────────────────
    st.markdown("#### 3️⃣ Confirmar y aplicar")
    st.error(
        "⚠️ Esta operación **modifica datos históricos** del Excel de forma permanente. "
        "Asegurate de tener un backup antes de continuar.")

    if not st.session_state.get("mant_confirmar"):
        if st.button("🔄 Quiero aplicar esta corrección", type="secondary"):
            st.session_state["mant_confirmar"] = True; st.rerun()
    else:
        st.warning("¿Confirmás la corrección masiva? No se puede deshacer.")
        ca, cb = st.columns(2)
        with ca:
            if st.button("✅ Sí, aplicar corrección", type="primary"):
                with st.spinner("Aplicando corrección y registrando en Historial..."):
                    n = aplicar_correccion_masiva(
                        preview, cliente_sel, producto_sel,
                        nuevo_precio, nuevo_costo,
                        cambiar_precio, cambiar_costo,
                        desde_mes, desde_año, hasta_mes, hasta_año,
                    )
                st.session_state.pop("mant_preview", None)
                st.session_state.pop("mant_confirmar", None)
                st.success(
                    f"✅ {n} fila(s) corregidas. "
                    f"Cambios registrados en la hoja 'Historial Cambios'.")
                st.balloons()
        with cb:
            if st.button("❌ Cancelar"):
                st.session_state.pop("mant_confirmar", None); st.rerun()


# ── TAB 2: MIGRACIÓN ──────────────────────────────────────────────────────────
def _tab_migracion():
    st.markdown("""
    Convierte todas las fórmulas de la hoja **Pedidos** a valores estáticos.
    Equivalente a *Copiar → Pegado Especial → Solo Valores* en Excel.

    **Resultado:** el Excel queda 100% libre de fórmulas en la hoja Pedidos.
    Todos los cálculos futuros los hace la app directamente.

    **⚠️ Importante:** realizá esta operación solo si tenés un backup del Excel.
    """)
    st.divider()

    confirm_key = "mant_confirm_migracion"
    if not st.session_state.get(confirm_key):
        if st.button("🔄 Quiero convertir fórmulas a valores", type="secondary"):
            st.session_state[confirm_key] = True; st.rerun()
    else:
        st.warning("⚠️ ¿Confirmás? Se modificará la hoja Pedidos de tu Excel.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Sí, ejecutar migración", type="primary"):
                with st.spinner("Migrando... puede tardar 30-60 segundos..."):
                    try:
                        resultado = migrar_pedidos_a_valores()
                        st.success(
                            f"✅ Migración completada: "
                            f"**{resultado['filas']} filas** procesadas, "
                            f"**{resultado['celdas']} fórmulas** convertidas.")
                        st.session_state.pop(confirm_key, None)
                    except Exception as e:
                        st.error(f"❌ Error: {e}")
                        st.session_state.pop(confirm_key, None)
        with c2:
            if st.button("❌ Cancelar"):
                st.session_state.pop(confirm_key, None); st.rerun()


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def mostrar():
    st.markdown("## 🔧 Mantenimiento")
    if st.button("🏠 Inicio", key="btn_home_mant", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    t1, t2, t3 = st.tabs([
        "🔧 Corrección Masiva de Precios / Costos",
        "⚙️ Migración de Datos",
        "📋 Estructura del Excel",
    ])
    with t1: _tab_correccion()
    with t2: _tab_migracion()
    with t3: _tab_estructura()


# ── TAB 3: ESTRUCTURA DEL EXCEL ──────────────────────────────────────────────
def _tab_estructura():
    st.markdown("""
    Lee la estructura completa del Excel: hojas, tablas, columnas y tipo de contenido
    (valores estáticos vs fórmulas). Útil para planificar la separación de datos.
    """)
    st.divider()

    if st.button("📖 Leer estructura del Excel", type="primary"):
        from drive_helper import cargar_para_lectura
        import streamlit as st

        FILE_ID = st.secrets["EXCEL_FILE_ID"]

        with st.spinner("Descargando y analizando Excel..."):
            wb = cargar_para_lectura(FILE_ID)

        st.success(f"✅ Excel leído — {len(wb.sheetnames)} hojas encontradas")
        st.divider()

        for hoja in wb.sheetnames:
            ws = wb[hoja]
            n_filas = ws.max_row
            n_cols  = ws.max_column

            # Tablas en la hoja
            tablas = list(ws.tables.keys()) if ws.tables else []

            # Encabezados (fila 1)
            headers = []
            for col in range(1, n_cols + 1):
                val = ws.cell(row=1, column=col).value
                if val:
                    headers.append(str(val))

            # Detectar qué columnas tienen fórmulas (muestra de fila 2)
            cols_formula = []
            cols_valor   = []
            if n_filas > 1:
                for col in range(1, n_cols + 1):
                    cell = ws.cell(row=2, column=col)
                    if isinstance(cell.value, str) and cell.value.startswith("="):
                        h = headers[col-1] if col-1 < len(headers) else f"Col{col}"
                        cols_formula.append(h)
                    elif cell.value is not None:
                        h = headers[col-1] if col-1 < len(headers) else f"Col{col}"
                        cols_valor.append(h)

            with st.expander(
                f"**{hoja}** — {n_filas:,} filas × {n_cols} cols"
                + (f" — Tablas: {', '.join(tablas)}" if tablas else ""),
                expanded=False,
            ):
                if headers:
                    st.markdown("**Columnas:**")
                    st.code(", ".join(headers), language=None)
                if tablas:
                    st.markdown(f"**Tablas Excel:** `{'`, `'.join(tablas)}`")
                if cols_valor:
                    st.markdown(
                        f"**✅ Valores estáticos ({len(cols_valor)}):** "
                        f"{', '.join(cols_valor[:15])}"
                        + (" ..." if len(cols_valor) > 15 else ""))
                if cols_formula:
                    st.markdown(
                        f"**⚙️ Columnas con fórmulas ({len(cols_formula)}):** "
                        f"{', '.join(cols_formula[:15])}"
                        + (" ..." if len(cols_formula) > 15 else ""))
                if not headers:
                    st.caption("Hoja vacía o sin encabezados en fila 1.")

        wb.close()

