"""
modulo_proveedores.py — Lista de Compras a Proveedores
Tab 1: A Pedir  — tablas por proveedor con columnas por área
Tab 2: Resumen  — productos por Tipo Producto (Proceso/Fresco) con desglose por área
"""
import streamlit as st
from config import excluido_proveedores as _excluido_cfg
_excluido = _excluido_cfg  # alias local
import pandas as pd
from datetime import date
from excel_helper import leer_pedidos
from data_helper  import cargar_productos, cargar_clientes
from pdf_helper   import generar_lista_compras_proveedor

# EXCLUIR_CLIENTES viene de config.py

AREAS_PROV = [
    ("Ant-Chim", lambda cli, z: z in ["L03","L04"] and "chimalt" not in cli.lower() and z != "L10"),
    ("Chimalt",  lambda cli, z: z == "L10" or "chimalt" in cli.lower()),
    ("GT-Stgo",  lambda cli, z: z in ["L05","L06"]),
    ("Río",      lambda cli, z: z == "L01"),
]




def _get_area(cliente, zona):
    for nombre, fn in AREAS_PROV:
        if fn(cliente, zona): return nombre
    return "Otro"


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

    base_key  = f"prov_base_v3_{semana}_{año}"
    reset_key = f"prov_reset_{semana}_{año}"

    if cargar:
        st.session_state.pop(base_key, None)
        st.session_state[reset_key] = st.session_state.get(reset_key, 0) + 1

    # ── Carga de datos ────────────────────────────────────────────────────────
    if not st.session_state.get(base_key):
        if not cargar:
            st.info("Seleccioná la semana y hacé clic en **Cargar semana**.")
            return

        with st.spinner("Cargando pedidos y catálogo..."):
            todos    = leer_pedidos()
            catalog  = cargar_productos(False, solo_catalogo=False)
            cli_list = cargar_clientes()

        prod_map = {p["nombre"].lower(): {
            "proveedor":     p.get("proveedor", "").strip(),
            "costo":         float(p.get("costo") or 0),
            "tipo_producto": str(p.get("tipo_producto", "") or "").strip(),
        } for p in catalog}

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
        resumen_tp  = {}   # {tipo_producto: {(prod,unidad): {area: qty, total: qty}}}
        sin_detalle = []

        for p in pedidos_sem:
            info   = prod_map.get(str(p["producto"]).strip().lower(), {})
            prov   = info.get("proveedor", "").strip() or "⚠️ SIN PROVEEDOR"
            prod   = p["producto"]
            cant   = float(p["cantidad"])
            unidad = p.get("unidad", "")
            costo  = info.get("costo", 0.0)
            tipo_p = info.get("tipo_producto", "") or "Sin Tipo"
            zona_c = cli_zona.get(p["cliente"].lower(), "")
            area   = _get_area(p["cliente"], zona_c)

            if prov == "⚠️ SIN PROVEEDOR":
                sin_detalle.append({"producto": prod, "cliente": p["cliente"],
                                    "cantidad": cant, "unidad": unidad})

            # Por proveedor
            if prov not in por_prov: por_prov[prov] = {}
            key = (prod, unidad, costo)
            if key not in por_prov[prov]:
                por_prov[prov][key] = {"total": 0.0}
            por_prov[prov][key]["total"] += cant
            por_prov[prov][key][area] = por_prov[prov][key].get(area, 0) + cant

            # Por tipo de producto (para Resumen)
            if tipo_p not in resumen_tp: resumen_tp[tipo_p] = {}
            pkey = (prod, unidad)
            if pkey not in resumen_tp[tipo_p]:
                resumen_tp[tipo_p][pkey] = {"total": 0.0}
            resumen_tp[tipo_p][pkey]["total"] += cant
            resumen_tp[tipo_p][pkey][area] = \
                resumen_tp[tipo_p][pkey].get(area, 0) + cant

        # Detectar áreas con datos
        todas_areas = []
        for a_name, _ in AREAS_PROV:
            for pd_dict in por_prov.values():
                for kd in pd_dict.values():
                    if kd.get(a_name, 0) > 0:
                        if a_name not in todas_areas:
                            todas_areas.append(a_name)
                        break

        # DataFrames base (FIJOS) por proveedor
        base_dfs = {}
        for prov in sorted(por_prov.keys()):
            rows = []
            for k, v in sorted(por_prov[prov].items()):
                row = {"Producto": k[0], "Unidad": k[1]}
                for an in todas_areas:
                    row[an] = round(v.get(an, 0), 2) if v.get(an, 0) else 0
                row["Total"]      = round(v["total"], 1)
                row["A Comprar"]  = ""
                row["_costo"]     = k[2]
                rows.append(row)
            base_dfs[prov] = pd.DataFrame(rows)

        st.session_state[base_key]                        = base_dfs
        st.session_state[f"prov_prodmap_v3_{semana}_{año}"] = prod_map
        st.session_state[f"prov_areas_v3_{semana}_{año}"]   = todas_areas
        st.session_state[f"prov_resumen_v3_{semana}_{año}"] = resumen_tp
        st.session_state[f"prov_alerta_v3_{semana}_{año}"]  = sin_detalle

    # ── Recuperar del estado ──────────────────────────────────────────────────
    base_dfs    = st.session_state[base_key]
    prod_map    = st.session_state.get(f"prov_prodmap_v3_{semana}_{año}", {})
    todas_areas = st.session_state.get(f"prov_areas_v3_{semana}_{año}", [])
    resumen_tp  = st.session_state.get(f"prov_resumen_v3_{semana}_{año}", {})
    sin_detalle = st.session_state.get(f"prov_alerta_v3_{semana}_{año}", [])
    reset_n     = st.session_state.get(reset_key, 0)
    provs       = list(base_dfs.keys())

    # ── Alerta sin proveedor ──────────────────────────────────────────────────
    if sin_detalle:
        with st.expander(
            f"⚠️ {len(sin_detalle)} producto(s) sin proveedor",
            expanded=False):
            h = st.columns([3, 2, 1.5, 1])
            for lbl, hd in zip(h, ["Producto","Cliente","Cantidad","Unidad"]):
                lbl.markdown(f"**{hd}**")
            for d in sin_detalle:
                r = st.columns([3, 2, 1.5, 1])
                r[0].write(d["producto"]); r[1].write(d["cliente"])
                r[2].write(f"{d['cantidad']:,.1f}"); r[3].write(d["unidad"])
        st.caption("Actualizá el proveedor en 📦 Productos.")

    # ══ TABS PRINCIPALES ══════════════════════════════════════════════════════
    tab_apedir, tab_resumen = st.tabs(["📦 A Pedir", "📊 Resumen por Tipo"])

    # ─────────────────────────────────────────────────────────────────────────
    with tab_resumen:
        st.markdown(f"**Semana {semana}/{año} — desglose por tipo de producto y área**")

        tipos_disponibles = sorted(resumen_tp.keys())
        if not tipos_disponibles:
            st.info("Sin datos.")
        else:
            filtro_tipo = st.selectbox(
                "Filtrar por tipo:",
                ["Todos"] + tipos_disponibles,
                key="res_tipo_filter"
            )
            tipos_ver = tipos_disponibles if filtro_tipo == "Todos" \
                        else [filtro_tipo]

            for tipo in tipos_ver:
                datos = resumen_tp[tipo]
                st.markdown(f"#### {tipo}")
                rows_r = []
                res_areas = [a for a in todas_areas
                             if any(v.get(a, 0) > 0
                                    for v in datos.values())]
                for (prod, unidad), vals in sorted(datos.items()):
                    row = {"Producto": prod, "Unidad": unidad}
                    for an in res_areas:
                        row[an] = round(vals.get(an, 0), 2) if vals.get(an, 0) else 0
                    row["Total"] = round(vals["total"], 1)
                    rows_r.append(row)
                if rows_r:
                    st.dataframe(pd.DataFrame(rows_r),
                                 hide_index=True,
                                 use_container_width=True)

    # ─────────────────────────────────────────────────────────────────────────
    with tab_apedir:
        n_ok = sum(1 for p in provs if "SIN PROVEEDOR" not in p)
        st.markdown(f"**Semana {semana}/{año} — {n_ok} proveedor(es) · "
                    f"{len(provs)} grupo(s)**")

        sel_prov = st.multiselect(
            "Seleccioná proveedores:",
            provs, default=provs, key="prov_ms")

        if not sel_prov:
            st.info("Seleccioná al menos un proveedor.")
        else:
            if st.button("🗑 Limpiar todo lo ingresado",
                         type="secondary", key="limpiar_arriba"):
                for _p, _df in base_dfs.items():
                    if "A Comprar" in _df.columns:
                        _df["A Comprar"] = ""
                st.session_state[reset_key] = reset_n + 1
                st.rerun()

            edited_results   = {}
            total_est_global = 0.0

            for prov in sel_prov:
                base_df = base_dfs[prov]
                color   = "#E65100" if "SIN PROVEEDOR" in prov else "#2D7A2D"

                # Total potencial: costo × cantidad_total de todos los items
                total_col_name = "Total" if "Total" in base_df.columns else "Pedido"
                total_costo_prov = sum(
                    prod_map.get(str(r.get("Producto","")).lower(), {}).get("costo", 0)
                    * float(r.get(total_col_name, 0) or 0)
                    for _, r in base_df.iterrows()
                )
                costo_lbl = (f" &nbsp;·&nbsp; Total potencial: "
                             f"<span style='background:rgba(255,255,255,.25);"
                             f"padding:2px 8px;border-radius:4px'>"
                             f"Q{total_costo_prov:,.0f}</span>"
                             if total_costo_prov > 0 else "")

                st.markdown(
                    f"<div style='background:{color};color:white;"
                    f"padding:6px 12px;border-radius:6px;font-weight:bold;"
                    f"font-size:.9rem;margin:10px 0 4px 0'>"
                    f"📦 {prov}{costo_lbl}</div>",
                    unsafe_allow_html=True)

                # Columnas visibles: areas + Total/Pedido + A Comprar
                total_col = "Total" if "Total" in base_df.columns else "Pedido"
                vis_cols  = ["Producto","Unidad"] +                             [a for a in todas_areas if a in base_df.columns] +                             [c2 for c2 in [total_col,"A Comprar"]
                             if c2 in base_df.columns]

                col_cfg = {
                    "Producto":  st.column_config.TextColumn(
                        "Producto",  disabled=True, width="medium"),
                    "Unidad":    st.column_config.TextColumn(
                        "Unidad",   disabled=True, width="small"),
                    total_col:   st.column_config.NumberColumn(
                        total_col,  disabled=True, width="small", format="%.1f"),
                    "A Comprar": st.column_config.TextColumn(
                        "A Comprar", width="small",
                        help="Cantidad, P=Pendiente, vacío=no imprimir"),
                }
                for an in todas_areas:
                    if an in base_df.columns:
                        col_cfg[an] = st.column_config.NumberColumn(
                            an, disabled=True, width="small", format="%.2f")

                edited = st.data_editor(
                    base_df[vis_cols],
                    column_config=col_cfg,
                    hide_index=True,
                    use_container_width=True,
                    num_rows="fixed",
                    key=f"de_{prov}_{semana}_{año}_{reset_n}",
                )
                edited_results[prov] = edited

                # ── Persistir ediciones a session_state ──────────────────────
                # base_dfs vive en session_state; al mutar el DataFrame aqui,
                # los valores de "A Comprar" sobreviven reruns y navegacion.
                if "A Comprar" in edited.columns:
                    base_df["A Comprar"] = edited["A Comprar"].values

                # Total estimado (pantalla)
                est_prov = 0.0
                for i, row in base_df.iterrows():
                    val = str(edited.loc[i, "A Comprar"] or "")
                    ok, pend, n = _val_comprar(val)
                    try:
                        _c = float(row["_costo"] or 0)
                    except:
                        _c = 0.0
                    if ok and not pend and _c > 0:
                        est_prov += n * _c
                if est_prov > 0:
                    st.markdown(
                        f"<div style='text-align:right;font-size:.8rem;"
                        f"color:{color};margin:2px 0 6px 0'>"
                        f"<b>Estimado {prov}: Q{est_prov:,.2f}</b> "
                        f"<span style='color:#aaa;font-size:.7rem'>"
                        f"(solo pantalla)</span></div>",
                        unsafe_allow_html=True)
                    total_est_global += est_prov

            if total_est_global > 0:
                st.markdown(
                    f"<div style='background:#e8f5e9;border-radius:8px;"
                    f"padding:10px;text-align:center;margin:8px 0'>"
                    f"<b>💰 Estimado total semana: Q{total_est_global:,.2f}</b>"
                    f"<br><small style='color:#888'>Solo pantalla</small>"
                    f"</div>", unsafe_allow_html=True)

            st.divider()
            if st.button("🗑 Limpiar todo", type="secondary",
                         key="limpiar_abajo"):
                for _p, _df in base_dfs.items():
                    if "A Comprar" in _df.columns:
                        _df["A Comprar"] = ""
                st.session_state[reset_key] = reset_n + 1
                st.rerun()

            st.divider()
            st.markdown("**📄 Descargar PDF por proveedor:**")
            st.caption("Solo líneas con valor en 'A Comprar'.")

            for prov in sel_prov:
                edited = edited_results.get(prov)
                if edited is None: continue

                items_pdf = []
                for i, row in base_dfs[prov].iterrows():
                    val = str(edited.loc[i, "A Comprar"] or "")
                    ok, pend, n = _val_comprar(val)
                    if not ok: continue
                    item = {
                        "producto":  row["Producto"],
                        "unidad":    row["Unidad"],
                        "cantidad":  float(row["Total"]),
                        "a_comprar": "P" if pend else f"{n:g}",
                    }
                    for _a in ["Ant-Chim","Chimalt","GT-Stgo","Río"]:
                        item[_a] = float(row[_a]) if _a in row.index else 0.0
                    items_pdf.append(item)

                import base64
                import streamlit.components.v1 as _cpv
                col_lbl, col_p, col_d = st.columns([3, 0.8, 0.8])
                col_lbl.markdown(
                    f"<div style='padding-top:6px'>📦 <b>{prov}</b> "
                    f"— {len(items_pdf)} línea(s)</div>",
                    unsafe_allow_html=True)

                if items_pdf:
                    try:
                        pdf_bytes = generar_lista_compras_proveedor(
                            prov, items_pdf, semana, año)
                        nom = "".join(ch for ch in prov
                                      if ch.isalnum() or ch == "_")
                        _b64 = base64.b64encode(pdf_bytes).decode()
                        _html_print = f"""
<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
<script>
pdfjsLib.GlobalWorkerOptions.workerSrc='https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
function imprimirProv_{nom}(){{
  var raw=atob('{_b64}');
  var arr=new Uint8Array(raw.length);
  for(var i=0;i<raw.length;i++) arr[i]=raw.charCodeAt(i);
  var blob=new Blob([arr],{{type:'application/pdf'}});
  var url=URL.createObjectURL(blob);
  var w=window.open(url,'_blank');
  w.onload=function(){{w.print();}};
}}
</script>
<button onclick="imprimirProv_{nom}()" style="
  background:#2D7A2D;color:white;border:none;border-radius:6px;
  padding:6px 10px;font-size:12px;cursor:pointer;width:100%;
  font-family:sans-serif">🖨️ Imprimir</button>"""
                        with col_p:
                            _cpv.html(_html_print, height=40)
                        col_d.download_button(
                            "📥 PDF", data=pdf_bytes,
                            file_name=f"Compras_{nom}_Sem{semana}_{año}.pdf",
                            mime="application/pdf",
                            key=f"dl_{prov}_{semana}_{año}",
                            type="primary",
                            use_container_width=True)
                    except Exception as e:
                        col_d.error(f"Error: {e}")
                else:
                    col_d.button("📥 PDF", disabled=True,
                                   key=f"dl_dis_{prov}_{semana}_{año}",
                                   help="Ingresá cantidades primero",
                                   use_container_width=True)
