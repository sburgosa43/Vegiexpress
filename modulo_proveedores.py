"""
modulo_proveedores.py — Lista de Compras a Proveedores
- Proveedor desde catálogo GENERAL únicamente (no Antigua)
- data_editor por proveedor con navegación Tab/Enter
- Costo estimado solo en pantalla
- Botón limpiar + PDF por selección
"""
import streamlit as st
import pandas as pd
from datetime import date
from excel_helper import leer_pedidos
from data_helper  import cargar_productos
from pdf_helper   import generar_lista_compras

EXCLUIR_CLIENTES = ["veggi", "chimalt", "wilson"]


def _excluido(n):
    return any(x in n.lower() for x in EXCLUIR_CLIENTES)


def _val_comprar(v: str):
    """Retorna (es_valido, es_pendiente, cantidad_float)."""
    v = str(v or "").strip()
    if not v or v == "0": return False, False, 0.0
    if v.upper() == "P":  return True,  True,  0.0
    try:
        n = float(v.replace(",", "."))
        return (n > 0), False, n
    except ValueError:
        return False, False, 0.0


def mostrar():
    st.markdown("## 📦 Pedidos a Proveedores")
    if st.button("🏠 Inicio", key="btn_home_prov", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    # ── Selector de semana ────────────────────────────────────────────────────
    hoy     = date.today()
    sem_hoy = hoy.isocalendar()[1]
    año_hoy = hoy.year

    c1, c2, c3 = st.columns(3)
    semana = c1.number_input("Semana", min_value=1, max_value=53,
                              value=sem_hoy, step=1, key="prov_sem")
    año    = c2.selectbox("Año", list(range(año_hoy, año_hoy - 3, -1)),
                          key="prov_año")
    with c3:
        st.markdown("&nbsp;")
        cargar = st.button("🔍 Cargar semana", type="primary",
                           use_container_width=True)

    datos_key  = f"prov_datos_{semana}_{año}"
    df_key     = f"prov_df_{semana}_{año}"
    reset_key  = f"prov_reset_{semana}_{año}"

    if cargar:
        st.session_state.pop(datos_key, None)
        st.session_state.pop(df_key, None)
        st.session_state[reset_key] = st.session_state.get(reset_key, 0) + 1

    # ── Carga de datos ────────────────────────────────────────────────────────
    if not st.session_state.get(datos_key) and not cargar:
        st.info("Seleccioná la semana y hacé clic en **Cargar semana**.")
        return

    if not st.session_state.get(datos_key):
        with st.spinner("Cargando pedidos y catálogo..."):
            todos   = leer_pedidos()
            # SOLO catálogo general para proveedor
            catalog = cargar_productos(False)

        prod_map = {p["nombre"].lower(): {
            "proveedor": p.get("proveedor", "").strip(),
            "costo":     float(p.get("costo", 0)),
        } for p in catalog}

        pedidos_sem = [p for p in todos
                       if p["semana"] == semana and p["año"] == año
                       and p["status"] != "Cancelado"
                       and float(p.get("cantidad") or 0) > 0
                       and not _excluido(p["cliente"])]

        if not pedidos_sem:
            st.warning(f"No hay pedidos activos para semana {semana}/{año}.")
            return

        # Agregar por proveedor → producto
        por_prov = {}
        for p in pedidos_sem:
            info     = prod_map.get(p["producto"].lower(), {})
            prov     = info.get("proveedor", "") or "SIN PROVEEDOR"
            prod     = p["producto"]
            cant     = float(p["cantidad"])
            unidad   = p.get("unidad", "")
            costo_c  = info.get("costo", 0)

            if prov not in por_prov:
                por_prov[prov] = {}
            key = (prod, unidad, costo_c)
            por_prov[prov][key] = por_prov[prov].get(key, 0) + cant

        # Convertir a DataFrames
        dfs = {}
        for prov in sorted(por_prov.keys()):
            rows = [{"Producto":  k[0],
                     "Unidad":    k[1],
                     "Pedido":    round(v, 1),
                     "A Comprar": "",
                     "_costo":    k[2]}
                    for k, v in sorted(por_prov[prov].items())]
            dfs[prov] = pd.DataFrame(rows)

        st.session_state[datos_key] = dfs

    dfs      = st.session_state[datos_key]
    reset_n  = st.session_state.get(reset_key, 0)
    provs    = list(dfs.keys())

    # ── Multi-select ──────────────────────────────────────────────────────────
    st.markdown(f"**Semana {semana}/{año} — {len(provs)} proveedor(es)**")
    sel_prov = st.multiselect("Proveedores a incluir en PDF:",
                               provs, default=provs, key="prov_ms")
    st.divider()

    # ── Botón limpiar (antes) ─────────────────────────────────────────────────
    if st.button("🗑 Limpiar todo lo ingresado", type="secondary"):
        for prov in dfs:
            dfs[prov]["A Comprar"] = ""
        st.session_state[datos_key] = dfs
        st.session_state[reset_key] = reset_n + 1
        st.rerun()

    # ── Sección por proveedor ─────────────────────────────────────────────────
    total_est_global = 0.0

    for prov in provs:
        df = dfs[prov].copy()
        color = "#2D7A2D" if prov != "SIN PROVEEDOR" else "#E65100"
        st.markdown(
            f"<div style='background:{color};color:white;padding:6px 12px;"
            f"border-radius:6px;font-weight:bold;font-size:.9rem;"
            f"margin:10px 0 4px 0'>📦 {prov}</div>",
            unsafe_allow_html=True)

        edited = st.data_editor(
            df[["Producto", "Unidad", "Pedido", "A Comprar"]],
            column_config={
                "Producto":  st.column_config.TextColumn(
                    "Producto",  disabled=True, width="large"),
                "Unidad":    st.column_config.TextColumn(
                    "Unidad",   disabled=True, width="small"),
                "Pedido":    st.column_config.NumberColumn(
                    "Pedido",   disabled=True, width="small", format="%.1f"),
                "A Comprar": st.column_config.TextColumn(
                    "A Comprar", width="small",
                    help="Número a comprar, P = Pendiente, 0 = No imprimir"),
            },
            hide_index=True,
            use_container_width=True,
            key=f"de_{prov}_{semana}_{año}_{reset_n}",
            num_rows="fixed",
        )

        # Actualizar DataFrame con los valores editados
        dfs[prov]["A Comprar"] = edited["A Comprar"]

        # Costo estimado del proveedor
        est_prov = 0.0
        for i, row in df.iterrows():
            val = str(edited.loc[i, "A Comprar"] or "")
            ok, pend, n = _val_comprar(val)
            if ok and not pend and float(row["_costo"]) > 0:
                est_prov += n * float(row["_costo"])

        if est_prov > 0:
            st.markdown(
                f"<div style='text-align:right;font-size:.8rem;"
                f"color:{color};margin:2px 0 4px 0'>"
                f"<b>Estimado {prov}: Q{est_prov:,.2f}</b>"
                f" <span style='color:#aaa;font-size:.7rem'>"
                f"(solo pantalla)</span></div>",
                unsafe_allow_html=True)
            total_est_global += est_prov

    st.session_state[datos_key] = dfs

    # Total global
    if total_est_global > 0:
        st.markdown(
            f"<div style='background:#e8f5e9;border-radius:8px;"
            f"padding:10px;text-align:center;margin:8px 0'>"
            f"<b>💰 Estimado total semana: Q{total_est_global:,.2f}</b>"
            f"<br><small style='color:#888'>Solo pantalla — no se imprime</small>"
            f"</div>", unsafe_allow_html=True)

    st.divider()

    # ── PDF + botón limpiar (después) ─────────────────────────────────────────
    bp, bl = st.columns(2)

    with bl:
        if st.button("🗑 Limpiar todo", type="secondary",
                     use_container_width=True, key="limpiar_abajo"):
            for prov in dfs:
                dfs[prov]["A Comprar"] = ""
            st.session_state[datos_key] = dfs
            st.session_state[reset_key] = reset_n + 1
            st.rerun()

    with bp:
        if not sel_prov:
            st.info("Seleccioná al menos un proveedor.")
        elif st.button(f"📄 Generar PDF ({len(sel_prov)} prov.)",
                       type="primary", use_container_width=True):
            datos_pdf = {}
            for prov in sel_prov:
                df_p = dfs[prov]
                items_pdf = []
                for _, row in df_p.iterrows():
                    val = str(row["A Comprar"] or "")
                    ok, pend, n = _val_comprar(val)
                    if not ok: continue
                    items_pdf.append({
                        "producto":  row["Producto"],
                        "unidad":    row["Unidad"],
                        "cantidad":  float(row["Pedido"]),
                        "a_comprar": "P" if pend else f"{n:g}",
                    })
                if items_pdf:
                    datos_pdf[prov] = items_pdf

            if not datos_pdf:
                st.warning("No hay líneas con cantidad ingresada.")
            else:
                with st.spinner("Generando PDF..."):
                    pdf_bytes = generar_lista_compras(datos_pdf, semana, año)
                st.download_button(
                    "📥 Descargar PDF",
                    data=pdf_bytes,
                    file_name=f"Compras_Sem{semana}_{año}.pdf",
                    mime="application/pdf",
                    key="prov_dl", type="primary",
                    use_container_width=True)
