"""
modulo_proveedores.py — Lista de Compras a Proveedores
- Proveedor desde catálogo GENERAL únicamente
- data_editor con baseline FIJO (no se sincroniza) — persiste valores correctamente
- Alerta de productos sin proveedor
- Costo estimado solo en pantalla
- Multi-select + PDF por selección
"""
import streamlit as st
import pandas as pd
from datetime import date
from excel_helper import leer_pedidos
from data_helper  import cargar_productos
from pdf_helper   import generar_lista_compras

EXCLUIR_CLIENTES = ["wilson"]


def _excluido(n):
    return any(x in n.lower() for x in EXCLUIR_CLIENTES)


def _val_comprar(v):
    v = str(v or "").strip()
    if not v:           return False, False, 0.0
    if v.upper() == "P": return True,  True,  0.0
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

    base_key  = f"prov_base_{semana}_{año}"   # DataFrames FIJOS, nunca cambian
    reset_key = f"prov_reset_{semana}_{año}"  # Contador para limpiar editors

    if cargar:
        st.session_state.pop(base_key, None)
        st.session_state[reset_key] = st.session_state.get(reset_key, 0) + 1

    # ── Carga inicial ─────────────────────────────────────────────────────────
    if not st.session_state.get(base_key):
        if not cargar:
            st.info("Seleccioná la semana y hacé clic en **Cargar semana**.")
            return

        with st.spinner("Cargando pedidos y catálogo..."):
            todos   = leer_pedidos()
            catalog = cargar_productos(False)   # Solo catálogo GENERAL

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
        por_prov    = {}
        sin_detalle = []   # Para la alerta

        for p in pedidos_sem:
            info   = prod_map.get(p["producto"].lower(), {})
            prov   = info.get("proveedor", "").strip()
            prod   = p["producto"]
            cant   = float(p["cantidad"])
            unidad = p.get("unidad", "")
            costo  = info.get("costo", 0.0)

            if not prov:
                prov = "⚠️ SIN PROVEEDOR"
                sin_detalle.append({
                    "producto": prod,
                    "cliente":  p["cliente"],
                    "cantidad": cant,
                    "unidad":   unidad,
                })

            if prov not in por_prov:
                por_prov[prov] = {}
            key = (prod, unidad, costo)
            por_prov[prov][key] = por_prov[prov].get(key, 0) + cant

        # Construir DataFrames FIJOS con A Comprar siempre vacío
        base_dfs = {}
        for prov in sorted(por_prov.keys()):
            rows = [{"Producto":  k[0],
                     "Unidad":    k[1],
                     "Pedido":    round(v, 1),
                     "A Comprar": "",
                     "_costo":    k[2]}
                    for k, v in sorted(por_prov[prov].items())]
            base_dfs[prov] = pd.DataFrame(rows)

        st.session_state[base_key]              = base_dfs
        st.session_state[f"prov_alerta_{semana}_{año}"] = sin_detalle

    base_dfs    = st.session_state[base_key]
    sin_detalle = st.session_state.get(f"prov_alerta_{semana}_{año}", [])
    reset_n     = st.session_state.get(reset_key, 0)
    provs       = list(base_dfs.keys())

    # ── Alerta sin proveedor ──────────────────────────────────────────────────
    if sin_detalle:
        with st.expander(
            f"⚠️ {len(sin_detalle)} producto(s) sin proveedor asignado — "
            f"revisá el catálogo", expanded=False):
            h = st.columns([3, 2, 1.5, 1])
            h[0].markdown("**Producto**"); h[1].markdown("**Cliente**")
            h[2].markdown("**Cantidad**"); h[3].markdown("**Unidad**")
            for d in sin_detalle:
                r = st.columns([3, 2, 1.5, 1])
                r[0].write(d["producto"]); r[1].write(d["cliente"])
                r[2].write(f"{d['cantidad']:,.1f}"); r[3].write(d["unidad"])
        st.caption("Actualizá el proveedor en 📦 Productos para que aparezcan "
                   "en la lista correcta.")

    # ── Multi-select ──────────────────────────────────────────────────────────
    n_ok = sum(1 for p in provs if "SIN PROVEEDOR" not in p)
    st.markdown(f"**Semana {semana}/{año} — {n_ok} proveedor(es) · "
                f"{len(provs)} grupo(s) total**")

    sel_prov = st.multiselect(
        "Seleccioná proveedores a visualizar / incluir en PDF:",
        provs, default=provs, key="prov_ms")
    st.divider()

    if not sel_prov:
        st.info("Seleccioná al menos un proveedor.")
        return

    # ── Botón limpiar (arriba) ────────────────────────────────────────────────
    if st.button("🗑 Limpiar todo lo ingresado", type="secondary",
                 key="limpiar_arriba"):
        st.session_state[reset_key] = reset_n + 1
        st.rerun()

    # ── data_editors por proveedor ────────────────────────────────────────────
    # CLAVE: pasamos siempre el DataFrame BASE (A Comprar vacío).
    # El data_editor mantiene todos los valores editados via su key interna.
    # NO sincronizamos de vuelta — eso era el bug.

    edited_results = {}   # Recolectamos los resultados de cada editor
    total_est_global = 0.0

    for prov in sel_prov:
        base_df = base_dfs[prov]   # Siempre el mismo, nunca cambia
        color   = "#E65100" if "SIN PROVEEDOR" in prov else "#2D7A2D"

        st.markdown(
            f"<div style='background:{color};color:white;padding:6px 12px;"
            f"border-radius:6px;font-weight:bold;font-size:.9rem;"
            f"margin:10px 0 4px 0'>📦 {prov}</div>",
            unsafe_allow_html=True)

        edited = st.data_editor(
            base_df[["Producto", "Unidad", "Pedido", "A Comprar"]],
            column_config={
                "Producto":  st.column_config.TextColumn(
                    "Producto",   disabled=True, width="large"),
                "Unidad":    st.column_config.TextColumn(
                    "Unidad",    disabled=True, width="small"),
                "Pedido":    st.column_config.NumberColumn(
                    "Pedido",    disabled=True, width="small", format="%.1f"),
                "A Comprar": st.column_config.TextColumn(
                    "A Comprar", width="small",
                    help="Cantidad a comprar, P = Pendiente, vacío = no imprimir"),
            },
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            key=f"de_{prov}_{semana}_{año}_{reset_n}",  # reset_n cambia solo con Limpiar
        )

        edited_results[prov] = edited   # Guardar resultado actual

        # Costo estimado en pantalla (no en PDF)
        est_prov = 0.0
        for i, row in base_df.iterrows():
            val = str(edited.loc[i, "A Comprar"] or "")
            ok, pend, n = _val_comprar(val)
            if ok and not pend and float(row["_costo"]) > 0:
                est_prov += n * float(row["_costo"])

        if est_prov > 0:
            st.markdown(
                f"<div style='text-align:right;font-size:.8rem;color:{color};"
                f"margin:2px 0 6px 0'><b>Estimado {prov}: "
                f"Q{est_prov:,.2f}</b> "
                f"<span style='color:#aaa;font-size:.7rem'>(solo pantalla)</span>"
                f"</div>", unsafe_allow_html=True)
            total_est_global += est_prov

    # Total global estimado
    if total_est_global > 0:
        st.markdown(
            f"<div style='background:#e8f5e9;border-radius:8px;"
            f"padding:10px;text-align:center;margin:8px 0'>"
            f"<b>💰 Estimado total semana: Q{total_est_global:,.2f}</b>"
            f"<br><small style='color:#888'>Solo pantalla — no se imprime</small>"
            f"</div>", unsafe_allow_html=True)

    st.divider()

    # ── Acciones ──────────────────────────────────────────────────────────────
    bl, bp = st.columns(2)

    with bl:
        if st.button("🗑 Limpiar todo", type="secondary",
                     use_container_width=True, key="limpiar_abajo"):
            st.session_state[reset_key] = reset_n + 1
            st.rerun()

    with bp:
        if st.button(f"📄 Generar PDF ({len(sel_prov)} prov.)",
                     type="primary", use_container_width=True):
            datos_pdf = {}
            for prov in sel_prov:
                edited = edited_results.get(prov)
                if edited is None: continue
                items_pdf = []
                for i, row in base_dfs[prov].iterrows():
                    val = str(edited.loc[i, "A Comprar"] or "")
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
                st.warning("No hay líneas con valor ingresado. "
                           "Completá la columna 'A Comprar'.")
            else:
                with st.spinner("Generando PDF..."):
                    pdf_bytes = generar_lista_compras(datos_pdf, semana, año)
                st.download_button(
                    "📥 Descargar PDF",
                    data=pdf_bytes,
                    file_name=f"Compras_Sem{semana}_{año}.pdf",
                    mime="application/pdf",
                    key="prov_dl",
                    type="primary",
                    use_container_width=True)
