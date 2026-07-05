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
    ("Antigua",  lambda cli, z: z in ["L03","L04","L10"] or "chimalt" in cli.lower()),
    ("Río",      lambda cli, z: z in ["L01","L02"]),
    ("Hogares",  lambda cli, z: z == "L20" or "veggi hogares" in cli.lower()),
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


# Compat: st.fragment (>=1.37) o experimental_fragment (1.33+)
_fragment = getattr(st, "fragment", None) or \
            getattr(st, "experimental_fragment", None) or (lambda f: f)


@_fragment
def _editores_fragment(sel_prov, base_dfs, prod_map, todas_areas,
                        semana, año, reset_n):
    """Editores de A Comprar + totales EN VIVO, aislados en un fragmento:
    cada edicion solo reejecuta este bloque (rapido), no toda la pagina."""
    total_est_global  = 0.0
    global_area_costs = {}   # {area: costo_demanda_total}

    for prov in sel_prov:
        base_df = base_dfs[prov]
        color   = "#E65100" if "SIN PROVEEDOR" in prov else "#2D7A2D"

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

        total_col = "Total" if "Total" in base_df.columns else "Pedido"
        vis_cols  = ["Producto","Unidad"] + \
                    [a for a in todas_areas if a in base_df.columns] + \
                    [c2 for c2 in [total_col,"A Comprar"]
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

        # ── Snapshot estable (dentro del fragmento no hay interferencias) ──
        ed_key  = f"de_{prov}_{semana}_{año}_{reset_n}"
        src_key = f"src_{ed_key}"
        if ed_key not in st.session_state or src_key not in st.session_state:
            st.session_state[src_key] = base_df[vis_cols].copy()

        edited = st.data_editor(
            st.session_state[src_key],
            column_config=col_cfg,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            key=ed_key,
        )

        # Persistencia unidireccional editor → base_df (session_state)
        if "A Comprar" in edited.columns:
            base_df["A Comprar"] = edited["A Comprar"].values

        # ── Costo por área (demanda × costo, siempre visible) ───────────────
        est_prov   = 0.0
        area_costs = {}
        for i, row in base_df.iterrows():
            try:   _c = float(row["_costo"] or 0)
            except: _c = 0.0
            if _c <= 0:
                continue
            # Demanda por área → costo atribuible (Opción A)
            for an in todas_areas:
                if an in row.index:
                    qty = float(row[an] or 0)
                    if qty > 0:
                        area_costs[an] = area_costs.get(an, 0) + qty * _c
            # Estimado A Comprar (solo si hay valor)
            val = str(edited.loc[i, "A Comprar"] or "")
            ok, pend, n = _val_comprar(val)
            if ok and not pend:
                est_prov += n * _c

        if area_costs or est_prov > 0:
            area_parts = " &nbsp;·&nbsp; ".join(
                f"<b>{an}:</b> Q{v:,.0f}"
                for an, v in area_costs.items() if v > 0
            )
            est_txt = (f" &nbsp;·&nbsp; <b>A Comprar estimado: Q{est_prov:,.2f}</b>"
                       if est_prov > 0 else "")
            st.markdown(
                f"<div style='text-align:right;font-size:.78rem;"
                f"color:{color};margin:2px 0 6px 0'>"
                + area_parts + est_txt + "</div>",
                unsafe_allow_html=True)
            total_est_global += est_prov
            for an, v in area_costs.items():
                global_area_costs[an] = global_area_costs.get(an, 0) + v

    # ── BANNER GLOBAL — siempre visible si hay demanda ───────────────────────
    if global_area_costs:
        area_line = "  &nbsp;|&nbsp;  ".join(
            f"<b>{an}:</b> Q{v:,.0f}"
            for an, v in global_area_costs.items() if v > 0
        )
        est_global_txt = (f"<br><span style='font-size:.8rem;color:#388e3c'>"
                          f"<b>💰 A Comprar estimado: Q{total_est_global:,.2f}</b></span>"
                          if total_est_global > 0 else "")
        st.markdown(
            f"<div style='background:#e8f5e9;border-radius:8px;"
            f"padding:10px;text-align:center;margin:8px 0'>"
            f"<b>📦 Necesidad semana por área</b>"
            f"<br><span style='font-size:.85rem'>{area_line}</span>"
            + est_global_txt
            + "</div>", unsafe_allow_html=True)


def _tab_por_area(semana: int, año: int, prod_map: dict):
    """Desglose de compras necesarias por área — Río / Antigua / Hogares."""
    from excel_helper import leer_pedidos
    from data_helper  import cargar_clientes

    AREAS = {
        "🌊 Río":     (["L01"],       "#1565C0"),
        "🔖 Antigua": (["L03","L04"], "#2E7D32"),
        "🏠 Hogares": (["L20"],       "#E65100"),
    }

    todos  = leer_pedidos()
    clis   = cargar_clientes()
    cli_z  = {c["nombre"].lower().strip(): c.get("codigo_lugar","")
               for c in clis}

    ped_sem = [p for p in todos
               if p["semana"] == semana and p["año"] == año
               and p["status"] != "Cancelado"]

    if not ped_sem:
        st.info(f"Sin pedidos activos en semana {semana}/{año}.")
        return

    totales_area = {}
    grand_total  = 0.0

    for area_nom, (codigos, color) in AREAS.items():
        lineas = [p for p in ped_sem
                  if cli_z.get(p["cliente"].lower().strip(),"") in codigos]
        if not lineas:
            continue

        # Agregar cantidad por producto
        agg = {}
        for l in lineas:
            prod = l["producto"].strip()
            cant = float(l.get("cantidad") or 0)
            if cant <= 0: continue
            pi = prod_map.get(prod.lower(), {})
            if prod not in agg:
                agg[prod] = {
                    "cantidad": 0.0,
                    "costo":    float(pi.get("costo") or l.get("costo") or 0),
                    "unidad":   pi.get("unidad",""),
                    "proveedor":l.get("proveedor",""),
                }
            agg[prod]["cantidad"] += cant

        if not agg:
            continue

        filas, total_area = [], 0.0
        for prod, d in sorted(agg.items()):
            sub = round(d["cantidad"] * d["costo"], 2)
            total_area += sub
            filas.append({
                "Producto":   prod,
                "Proveedor":  d["proveedor"],
                "Unidad":     d["unidad"],
                "Cantidad":   d["cantidad"],
                "Costo Q":    d["costo"],
                "Subtotal Q": sub,
            })
        grand_total += total_area
        totales_area[area_nom] = total_area

        # Card por área
        st.markdown(
            f"<div style='background:{color};color:white;padding:6px 14px;"
            f"border-radius:6px;font-weight:bold;font-size:.95rem;"
            f"margin:12px 0 4px 0'>"
            f"{area_nom} &nbsp;·&nbsp; "
            f"<span style='font-weight:normal'>"
            f"Total insumo: Q{total_area:,.2f}</span></div>",
            unsafe_allow_html=True)

        df = pd.DataFrame(filas)
        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Cantidad":   st.column_config.NumberColumn(format="%.2f"),
                "Costo Q":    st.column_config.NumberColumn(format="%.2f"),
                "Subtotal Q": st.column_config.NumberColumn(format="%.2f"),
            },
            height=min(400, 60 + len(df)*35),
        )

        # Descarga por área
        csv = df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            f"⬇️ CSV {area_nom.split()[1]}",
            data=csv,
            file_name=f"compras_{area_nom.split()[1]}_S{semana}_{año}.csv",
            mime="text/csv",
            key=f"dl_area_{area_nom}_{semana}",
        )

    # ── Resumen global ────────────────────────────────────────────────────────
    if totales_area:
        st.divider()
        cols_r = st.columns(len(totales_area) + 1)
        for i, (area, tot) in enumerate(totales_area.items()):
            pct = tot / grand_total * 100 if grand_total else 0
            cols_r[i].metric(area, f"Q{tot:,.0f}", f"{pct:.0f}%")
        cols_r[-1].metric("**TOTAL SEMANA**", f"Q{grand_total:,.0f}")


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
            "empacado":      str(p.get("empacado", "") or "").strip(),
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

        # DataFrame de Patojas (proceso) — misma estructura, tabla aparte
        patojas_rows = []
        for k, v in sorted(por_patojas.items()):
            row = {"Producto": k[0], "Unidad": k[1]}
            for an in todas_areas:
                row[an] = round(v.get(an, 0), 2) if v.get(an, 0) else 0
            row["Total"] = round(v["total"], 1)
            patojas_rows.append(row)
        patojas_df = pd.DataFrame(patojas_rows)

        st.session_state[base_key]                        = base_dfs
        st.session_state[f"prov_prodmap_v3_{semana}_{año}"] = prod_map
        st.session_state[f"prov_areas_v3_{semana}_{año}"]   = todas_areas
        st.session_state[f"prov_resumen_v3_{semana}_{año}"] = resumen_tp
        st.session_state[f"prov_alerta_v3_{semana}_{año}"]  = sin_detalle
        st.session_state[f"prov_patojas_v3_{semana}_{año}"] = patojas_df

    # ── Recuperar del estado ──────────────────────────────────────────────────
    base_dfs    = st.session_state[base_key]
    prod_map    = st.session_state.get(f"prov_prodmap_v3_{semana}_{año}", {})
    todas_areas = st.session_state.get(f"prov_areas_v3_{semana}_{año}", [])
    resumen_tp  = st.session_state.get(f"prov_resumen_v3_{semana}_{año}", {})
    sin_detalle = st.session_state.get(f"prov_alerta_v3_{semana}_{año}", [])
    patojas_df  = st.session_state.get(f"prov_patojas_v3_{semana}_{año}", pd.DataFrame())
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

    # ── Alerta: costos desactualizados (>30 dias o sin registro) ─────────────
    try:
        from excel_helper import costo_ultima_actualizacion
        from datetime import date as _date
        _ult = costo_ultima_actualizacion()
        _hoy = _date.today()
        _prods_semana = set()
        for _dfp in base_dfs.values():
            for _, _r in _dfp.iterrows():
                _prods_semana.add(str(_r["Producto"]).strip())

        _viejos = []
        for _pr in sorted(_prods_semana):
            _f = _ult.get(_pr.lower())
            if _f is None:
                _viejos.append((_pr, None))
            elif (_hoy - _f).days > 30:
                _viejos.append((_pr, (_hoy - _f).days))

        if _viejos:
            with st.expander(
                    f"⚠️ {len(_viejos)} producto(s) con costo desactualizado "
                    f"(>30 dias o sin registro)", expanded=False):
                st.caption("El costo se registra al editarlo en Productos o en "
                           "Correccion Masiva. Sin registro = nunca actualizado "
                           "desde que existe el log.")
                _rows_v = [{"Producto": _pr,
                            "Ultima actualizacion":
                                f"hace {_d} dias" if _d else "sin registro"}
                           for _pr, _d in _viejos]
                import pandas as _pd
                st.dataframe(_pd.DataFrame(_rows_v), hide_index=True,
                             use_container_width=True,
                             height=min(300, 60 + len(_rows_v)*35))
    except Exception:
        pass

    # ══ TABS PRINCIPALES ══════════════════════════════════════════════════════
    tab_apedir, tab_resumen, tab_area, tab_patojas = st.tabs(
        ["📦 A Pedir", "📊 Resumen por Tipo", "📍 Por Área", "👷 Patojas"])

    with tab_area:
        _tab_por_area(semana, año, prod_map)

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
                for _k in [k for k in st.session_state
                           if str(k).startswith(("de_", "src_de_"))]:
                    st.session_state.pop(_k, None)
                st.session_state[reset_key] = reset_n + 1
                st.rerun()

            # Editores + totales en vivo, aislados en fragmento (rapido)
            _editores_fragment(sel_prov, base_dfs, prod_map, todas_areas,
                                semana, año, reset_n)

            st.divider()
            if st.button("🗑 Limpiar todo", type="secondary",
                         key="limpiar_abajo"):
                for _p, _df in base_dfs.items():
                    if "A Comprar" in _df.columns:
                        _df["A Comprar"] = ""
                for _k in [k for k in st.session_state
                           if str(k).startswith(("de_", "src_de_"))]:
                    st.session_state.pop(_k, None)
                st.session_state[reset_key] = reset_n + 1
                st.rerun()

            st.divider()

            # ── Vista imprimible HTML (todos los proveedores, sin valores) ────
            def _html_imprimible():
                rows_html = ""
                for _prov in sel_prov:
                    _df = base_dfs.get(_prov)
                    if _df is None or _df.empty: continue
                    rows_html += (
                        f"<h2 style='page-break-before:always;margin:0 0 4px 0;"
                        f"font-size:15px'>📦 {_prov} — Semana {semana}/{año}</h2>"
                        "<table><tr><th style='text-align:left'>Producto</th>"
                        "<th>Unidad</th><th>Antigua</th>"
                        "<th>Río</th><th>Hogares</th><th>Total</th>"
                        "<th style='min-width:70px'>A Comprar</th></tr>")
                    for _, r in _df.iterrows():
                        def _v(a):
                            try: v = float(r.get(a, 0) or 0)
                            except Exception: v = 0
                            return f"{v:g}" if v > 0 else "—"
                        rows_html += (
                            f"<tr><td style='text-align:left'>{r['Producto']}</td>"
                            f"<td>{r['Unidad']}</td>"
                            f"<td>{_v('Antigua')}</td>"
                            f"<td>{_v('Río')}</td><td>{_v('Hogares')}</td>"
                            f"<td><b>{_v('Total')}</b></td><td></td></tr>")
                    rows_html += "</table>"
                return f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<title>Lista de Compras S{semana}/{año}</title><style>
body{{font-family:Helvetica,Arial,sans-serif;font-size:11px;margin:14px}}
table{{border-collapse:collapse;width:100%;margin-bottom:14px}}
th,td{{border:1px solid #333;padding:3px 5px;text-align:center;font-size:11px}}
th{{background:#eee}}
h2:first-of-type{{page-break-before:auto !important}}
@media print{{ h2{{page-break-before:always}} h2:first-of-type{{page-break-before:auto}} }}
</style></head><body>
<p style='font-size:10px;color:#666'>VeggiExpress · Lista de necesidades ·
Imprimir: Ctrl+P (o Compartir → Imprimir en el teléfono)</p>
{rows_html}</body></html>"""

            st.download_button(
                "🖨 Vista imprimible (HTML — todos los proveedores)",
                data=_html_imprimible().encode("utf-8"),
                file_name=f"Lista_Compras_S{semana}_{año}.html",
                mime="text/html",
                key=f"html_print_{semana}_{año}",
                help="Abrilo en el navegador y usa Ctrl+P para imprimir o guardar")

            st.divider()
            st.markdown("**📄 Descargar PDF por proveedor:**")
            st.caption("📋 Lista = todas las líneas (A Comprar vacío) · "
                       "📄 PDF = solo líneas con valor ingresado.")

            for prov in sel_prov:
                if prov not in base_dfs: continue

                items_pdf      = []   # solo lineas con valor (PDF actual)
                items_completa = []   # TODAS las lineas, A Comprar vacio (para anotar a mano)
                for i, row in base_dfs[prov].iterrows():
                    base_item = {
                        "producto":  row["Producto"],
                        "unidad":    row["Unidad"],
                        "cantidad":  float(row["Total"]),
                    }
                    for _a in ["Antigua","Río","Hogares"]:
                        base_item[_a] = float(row[_a]) if _a in row.index else 0.0

                    items_completa.append({**base_item, "a_comprar": ""})

                    val = str(row.get("A Comprar", "") or "")
                    ok, pend, n = _val_comprar(val)
                    if ok:
                        items_pdf.append({**base_item,
                                          "a_comprar": "P" if pend else f"{n:g}"})

                import base64
                import streamlit.components.v1 as _cpv
                col_lbl, col_full, col_p, col_d = st.columns([2.4, 0.9, 0.8, 0.8])

                # PDF Lista Completa: todas las lineas, columna A Comprar vacia
                if items_completa:
                    try:
                        pdf_full = generar_lista_compras_proveedor(
                            prov, items_completa, semana, año)
                        nomf = "".join(ch for ch in prov
                                       if ch.isalnum() or ch == "_")
                        col_full.download_button(
                            "📋 Lista", data=pdf_full,
                            file_name=f"Lista_{nomf}_S{semana}.pdf",
                            mime="application/pdf",
                            key=f"pdf_full_{prov}_{semana}_{año}",
                            help="Lista completa con A Comprar vacio para anotar a mano",
                            use_container_width=True)
                    except Exception:
                        pass
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
                        from pdf_helper import boton_imprimir_html as _btn_imp
                        with col_p:
                            _cpv.html(
                                _btn_imp(pdf_bytes, f"prov_{nom}_{semana}_{año}",
                                         "🖨️ Imprimir", "#2D7A2D"),
                                height=44)
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


    # ══ TAB PATOJAS (proceso: Patojas + Proceso + Sí) ═══════════════════════
    with tab_patojas:
        st.markdown(f"**👷 Patojas — Semana {semana}/{año}**")
        st.caption("Productos de proceso (Patojas + Proceso + Empacado=Sí). "
                   "Esta tabla es de referencia del trabajo de las Patojas y "
                   "**NO suma** al total de compras a proveedores. El costo del "
                   "insumo ya se cuenta en las compras; la mano de obra va en "
                   "Gastos.")

        if patojas_df is None or patojas_df.empty:
            st.info("No hay productos de proceso (Patojas + Proceso + Sí) esta "
                    "semana.")
        else:
            # Mostrar la tabla (cantidades por área + total), sin info financiera
            st.dataframe(patojas_df, hide_index=True, use_container_width=True)

            # Impresión — igual que las demás tablas, sin info financiera
            items_patojas = []
            for _, row in patojas_df.iterrows():
                item = {
                    "producto": row["Producto"],
                    "unidad":   row["Unidad"],
                    "cantidad": float(row["Total"]),
                }
                for _a in todas_areas:
                    item[_a] = float(row[_a]) if _a in row.index else 0
                items_patojas.append(item)

            if items_patojas:
                try:
                    pdf_pat = generar_lista_compras_proveedor(
                        "Patojas", items_patojas, semana, año)
                    cpa1, cpa2 = st.columns(2)
                    from pdf_helper import boton_imprimir_html as _btn_imp_pat
                    import streamlit.components.v1 as _cpv2
                    with cpa1:
                        _cpv2.html(
                            _btn_imp_pat(pdf_pat, f"patojas_{semana}_{año}",
                                         "🖨️ Imprimir", "#2D7A2D"),
                            height=44)
                    with cpa2:
                        st.download_button(
                            "📥 PDF Patojas", data=pdf_pat,
                            file_name=f"Patojas_S{semana}_{año}.pdf",
                            mime="application/pdf",
                            key=f"dl_patojas_{semana}_{año}",
                            use_container_width=True)
                except Exception as e:
                    st.error(f"Error al generar PDF: {e}")
