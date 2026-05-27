"""
modulo_proveedores.py — Lista de Compras a Proveedores
- Proveedor desde catálogo GENERAL únicamente
- data_editor con baseline FIJO — persiste valores correctamente
- Multi-select por proveedor + PDF individual por proveedor
"""
import streamlit as st
import pandas as pd
from datetime import date
from excel_helper import leer_pedidos
from data_helper  import cargar_productos, cargar_clientes
from pdf_helper   import generar_lista_compras_proveedor

EXCLUIR_CLIENTES = ["wilson"]

AREAS_PROV = [
    ("Ant-Chim", lambda cli, z: z in ["L03","L04"] and "chimalt" not in cli.lower()),
    ("Chimalt",  lambda cli, z: "chimalt" in cli.lower()),
    ("GT-Stgo",  lambda cli, z: z in ["L05","L06"]),
    ("Río",      lambda cli, z: z == "L01"),
]


def _get_area(cliente: str, zona: str) -> str:
    for nombre, filtro in AREAS_PROV:
        if filtro(cliente, zona):
            return nombre
    return "Otro"


def _excluido(n):
    return any(x in n.lower() for x in EXCLUIR_CLIENTES)


def _val_comprar(v):
    v = str(v or "").strip()
    if not v:            return False, False, 0.0
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

    base_key  = f"prov_base_{semana}_{año}"
    reset_key = f"prov_reset_{semana}_{año}"

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
            "proveedor":    p.get("proveedor", "").strip(),
            "costo":        float(p.get("costo", 0)),
            "tipo_producto": p.get("tipo_producto", ""),
        } for p in catalog}

        # Mapa cliente → zona
        cli_list = cargar_clientes()
        cli_zona = {c["nombre"].lower(): c["codigo_lugar"] for c in cli_list}

        pedidos_sem = [p for p in todos
                       if p["semana"] == semana and p["año"] == año
                       and p["status"] != "Cancelado"
                       and float(p.get("cantidad") or 0) > 0
                       and not _excluido(p["cliente"])]

        if not pedidos_sem:
            st.warning(f"No hay pedidos activos para semana {semana}/{año}.")
            return

        por_prov    = {}
        sin_detalle = []
        # Para tab Proceso
        proceso_data = {}

        for p in pedidos_sem:
            info   = prod_map.get(p["producto"].lower(), {})
            prov   = info.get("proveedor", "").strip()
            prod   = p["producto"]
            cant   = float(p["cantidad"])
            unidad = p.get("unidad", "")
            costo  = info.get("costo", 0.0)
            tipo_p = info.get("tipo_producto", "")
            zona_c = cli_zona.get(p["cliente"].lower(), "")
            area   = _get_area(p["cliente"], zona_c)

            if not prov:
                prov = "⚠️ SIN PROVEEDOR"
                sin_detalle.append({"producto": prod, "cliente": p["cliente"],
                                    "cantidad": cant, "unidad": unidad})

            if prov not in por_prov:
                por_prov[prov] = {}
            key = (prod, unidad, costo)
            if key not in por_prov[prov]:
                por_prov[prov][key] = {"total": 0.0}
            por_prov[prov][key]["total"] += cant
            por_prov[prov][key][area] = por_prov[prov][key].get(area, 0) + cant

            # Acumular para Proceso
            if tipo_p.lower() == "proceso":
                pkey = (prod, unidad)
                if pkey not in proceso_data:
                    proceso_data[pkey] = {"total": 0.0}
                proceso_data[pkey]["total"] += cant
                proceso_data[pkey][area] = proceso_data[pkey].get(area, 0) + cant

        # Detectar áreas con datos
        todas_areas = []
        for a_name, _ in AREAS_PROV:
            for prov_d in por_prov.values():
                for kd in prov_d.values():
                    if kd.get(a_name, 0) > 0:
                        if a_name not in todas_areas:
                            todas_areas.append(a_name)
                        break

        # DataFrames FIJOS con columnas de área
        base_dfs = {}
        for prov in sorted(por_prov.keys()):
            rows = []
            for k, v in sorted(por_prov[prov].items()):
                row = {
                    "Producto":  k[0],
                    "Unidad":    k[1],
                }
                for area_n in todas_areas:
                    val_a = v.get(area_n, 0)
                    row[area_n] = round(val_a, 2) if val_a else 0
                row["Pedido"]    = round(v["total"], 1)
                row["A Comprar"] = ""
                row["_costo"]    = k[2]
                rows.append(row)
            base_dfs[prov] = pd.DataFrame(rows)

        st.session_state[base_key]                       = base_dfs
        st.session_state[f"prov_alerta_{semana}_{año}"] = sin_detalle
        st.session_state[f"prov_areas_{semana}_{año}"]  = todas_areas
        st.session_state[f"prov_proceso_{semana}_{año}"]= proceso_data

    base_dfs     = st.session_state[base_key]
    sin_detalle  = st.session_state.get(f"prov_alerta_{semana}_{año}", [])
    todas_areas  = st.session_state.get(f"prov_areas_{semana}_{año}", [])
    proceso_data = st.session_state.get(f"prov_proceso_{semana}_{año}", {})
    reset_n      = st.session_state.get(reset_key, 0)
    provs        = list(base_dfs.keys())

    # ── Alerta sin proveedor ──────────────────────────────────────────────────
    if sin_detalle:
        with st.expander(
            f"⚠️ {len(sin_detalle)} producto(s) sin proveedor — revisá el catálogo",
            expanded=False):
            h = st.columns([3, 2, 1.5, 1])
            h[0].markdown("**Producto**"); h[1].markdown("**Cliente**")
            h[2].markdown("**Cantidad**"); h[3].markdown("**Unidad**")
            for d in sin_detalle:
                r = st.columns([3, 2, 1.5, 1])
                r[0].write(d["producto"]); r[1].write(d["cliente"])
                r[2].write(f"{d['cantidad']:,.1f}"); r[3].write(d["unidad"])
        st.caption("Actualizá el proveedor en 📦 Productos.")

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

    # ── data_editors por proveedor (baseline FIJO) ────────────────────────────
    edited_results   = {}
    total_est_global = 0.0

    for prov in sel_prov:
        base_df = base_dfs[prov]
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
            key=f"de_{prov}_{semana}_{año}_{reset_n}",
        )

        edited_results[prov] = edited

        # Total estimado del proveedor (solo pantalla)
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

    # Total global
    if total_est_global > 0:
        st.markdown(
            f"<div style='background:#e8f5e9;border-radius:8px;"
            f"padding:10px;text-align:center;margin:8px 0'>"
            f"<b>💰 Estimado total semana: Q{total_est_global:,.2f}</b>"
            f"<br><small style='color:#888'>Solo pantalla — no se imprime</small>"
            f"</div>", unsafe_allow_html=True)

    st.divider()

    # ── Botón limpiar (abajo) ─────────────────────────────────────────────────
    if st.button("🗑 Limpiar todo", type="secondary",
                 key="limpiar_abajo"):
        st.session_state[reset_key] = reset_n + 1
        st.rerun()

    st.divider()

    # ── PDF individual por proveedor ──────────────────────────────────────────
    st.markdown("**📄 Descargar PDF por proveedor:**")
    st.caption("Solo se incluyen las líneas con valor en 'A Comprar'.")

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

        col_lbl, col_btn = st.columns([3, 1])
        col_lbl.markdown(
            f"<div style='padding-top:6px'>📦 <b>{prov}</b> "
            f"— {len(items_pdf)} línea(s)</div>",
            unsafe_allow_html=True)

        if items_pdf:
            try:
                pdf_bytes = generar_lista_compras_proveedor(
                    prov, items_pdf, semana, año)
                nombre_prov = "".join(
                    ch for ch in prov if ch.isalnum() or ch == "_")
                col_btn.download_button(
                    "📥 PDF",
                    data=pdf_bytes,
                    file_name=f"Compras_{nombre_prov}_Sem{semana}_{año}.pdf",
                    mime="application/pdf",
                    key=f"dl_{prov}_{semana}_{año}",
                    type="primary",
                    use_container_width=True)
            except Exception as e:
                col_btn.error(f"Error: {e}")
        else:
            col_btn.button("📥 PDF", disabled=True,
                           key=f"dl_dis_{prov}_{semana}_{año}",
                           help="Ingresá cantidades primero",
                           use_container_width=True)


    # ══ TAB PROCESO (por área) ════════════════════════════════════════════════
    st.divider()
    with st.expander("⚙️ **Resumen Proceso (por área)**", expanded=False):
        if proceso_data:
            proc_rows = []
            proc_areas = []
            for a_n, _ in AREAS_PROV:
                for pk_data in proceso_data.values():
                    if pk_data.get(a_n, 0) > 0:
                        if a_n not in proc_areas: proc_areas.append(a_n)
                        break
            for (prod, unidad), vals in sorted(proceso_data.items()):
                row = {"Producto": prod, "Unidad": unidad}
                for a_n in proc_areas:
                    row[a_n] = round(vals.get(a_n, 0), 2) if vals.get(a_n, 0) else 0
                row["Total"] = round(vals["total"], 1)
                proc_rows.append(row)
            if proc_rows:
                st.markdown(f"**Productos Tipo Proceso — Semana {semana}/{año}**")
                df_proc = pd.DataFrame(proc_rows)
                st.dataframe(df_proc, hide_index=True, use_container_width=True)
            else:
                st.info("Sin productos tipo Proceso en esta semana.")
        else:
            st.info("Sin datos de Proceso. Verificá Tipo Producto en el catálogo.")
