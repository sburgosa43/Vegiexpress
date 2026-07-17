"""
modulo_mantenimiento.py — Herramientas de mantenimiento y administracion.
"""
import streamlit as st
from datetime import date


# ── TAB 1: Correccion masiva ──────────────────────────────────────────────────
def _tab_correccion():
    """Correccion masiva — productos de la semana actual, precios por nivel de cascada."""
    import datetime, pandas as pd
    from excel_helper  import leer_pedidos, actualizar_precio_semana
    from excel_helper  import leer_productos_con_fila, editar_producto as _edit_prod
    from data_helper   import leer_precios_capa, cargar_clientes
    from data_helper   import guardar_precio_especial, eliminar_precio_especial
    from gsheets       import get_all_rows
    from config        import ZONAS_MAP as _ZM

    st.markdown("#### Correccion Masiva de Precios / Costos")

    # ── Semana, zona y nivel ──────────────────────────────────────────────────
    hoy     = datetime.date.today()
    sem_def = hoy.isocalendar()[1]

    try:
        zonas  = sorted({r[0] for r in get_all_rows("precioszona")  if r and r[0]})
        grupos = sorted({r[0] for r in get_all_rows("preciosgrupo") if r and r[0]})
    except Exception:
        zonas, grupos = [], []

    nivel_opts = (["General"]
                  + [f"Zona: {z}"  for z in zonas]
                  + [f"Grupo: {g}" for g in grupos])

    c1, c2, c3, c4 = st.columns([1, 1, 1.5, 2])
    semana   = c1.number_input("Semana", 1, 53, sem_def,   key="mc3_sem")
    anio     = c2.number_input("Ano",  2020, 2030, hoy.year, key="mc3_anio")
    zona_ped = c3.selectbox("Zona de pedidos",
                             ["Todas"] + [k for k in _ZM if k != "Todas"],
                             key="mc3_zona")
    nivel    = c4.selectbox("Lista a editar", nivel_opts, key="mc3_nivel")

    # ── Leer pedidos de la semana ─────────────────────────────────────────────
    todos    = leer_pedidos()
    clientes = {c["nombre"].lower().strip(): c for c in cargar_clientes()}

    def _en_zona(nom):
        if zona_ped == "Todas": return True
        cli = clientes.get(nom.lower().strip())
        return cli and cli.get("codigo_lugar","") in _ZM.get(zona_ped, [])

    ped_sem = [p for p in todos
               if p["semana"] == semana and p["año"] == anio
               and p["status"] != "Cancelado" and _en_zona(p["cliente"])]

    if not ped_sem:
        st.info(f"Sin pedidos en semana {semana}/{anio}"
                + (f" para {zona_ped}." if zona_ped != "Todas" else "."))
        return

    prods_semana = sorted({p["producto"] for p in ped_sem})
    st.caption(f"**{len(prods_semana)}** productos en pedidos semana {semana}"
               + (f" · {zona_ped}" if zona_ped != "Todas" else "")
               + f"  |  Editando: **{nivel}**")

    # ── Catálogo general ──────────────────────────────────────────────────────
    cat_gen = {p["nombre"]: p for p in leer_productos_con_fila(es_antigua=False)}

    # ── Precios del nivel seleccionado ────────────────────────────────────────
    es_general  = (nivel == "General")
    hoja_nivel  = lista_nivel = None
    precios_niv = {}

    if not es_general:
        hoja_nivel  = "precioszona"  if nivel.startswith("Zona: ")  else "preciosgrupo"
        lista_nivel = nivel[6:]      if nivel.startswith("Zona: ")  else nivel[7:]
        precios_niv = {
            p["producto"]: float(p["precio"] or 0)
            for p in leer_precios_capa(hoja_nivel, lista_nivel)
        }

    # ── Construir filas (solo productos de la semana) ─────────────────────────
    rows = []
    for prod in prods_semana:
        cat = cat_gen.get(prod, {})
        costo_gen  = float(cat.get("costo")  or 0)
        precio_gen = float(cat.get("precio") or 0)
        rn         = cat.get("row_num", 0)

        if es_general:
            rows.append({
                "Producto":    prod,
                "Costo act":   costo_gen,
                "Costo nvo":   costo_gen,
                "P.General":   precio_gen,
                "P.Nuevo":     precio_gen,
                "_rn":         rn,
                "_costo_orig": costo_gen,
                "_precio_orig": precio_gen,
            })
        else:
            p_niv = precios_niv.get(prod)
            rows.append({
                "Producto":   prod,
                "Costo(Gen)": costo_gen,
                "P.General":  precio_gen,
                "P.Act":      p_niv if p_niv is not None else "",
                "P.Nuevo":    p_niv if p_niv is not None else precio_gen,
                "_rn":        rn,
                "_p_act":     p_niv,
                "_p_gen":     precio_gen,
                "_costo":     costo_gen,
            })

    if not rows:
        st.info("Sin productos del catalogo para los pedidos de esta semana.")
        return

    df = pd.DataFrame(rows)

    # ── AG Grid con margenes en vivo ──────────────────────────────────────────
    try:
        from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode

        GREEN = {"backgroundColor": "#E8F5E9"}

        if es_general:
            MG_ACT = JsCode("""function(p){
                var c=p.data['Costo act'],v=p.data['P.General'];
                if(!v||v<=0)return'';
                var m=(1-0.05)*(v-c*1.12)/v*100;
                var b=m>=35?'[+]':(m>=20?'[~]':'[!]');
                return b+' '+m.toFixed(1)+'%';
            }""")
            MG_NEW = JsCode("""function(p){
                var c=p.data['Costo nvo'],v=p.data['P.Nuevo'];
                if(!v||v<=0)return'';
                var ca=p.data['Costo act'],va=p.data['P.General'];
                var ma=(va>0)?(1-0.05)*(va-ca*1.12)/va*100:0;
                var mn=(1-0.05)*(v-c*1.12)/v*100;
                var b=mn>=35?'[+]':(mn>=20?'[~]':'[!]');
                var s=b+' '+mn.toFixed(1)+'%';
                var d=mn-ma;
                if(Math.abs(d)>0.05)s+=d>0?' +'+d.toFixed(1)+'pt':' '+d.toFixed(1)+'pt';
                return s;
            }""")
        else:
            MG_ACT = JsCode("""function(p){
                var c=p.data['Costo(Gen)'];
                var v=p.data['P.Act']||p.data['P.General'];
                if(!v||v<=0)return'';
                var m=(1-0.05)*(v-c*1.12)/v*100;
                var b=m>=35?'[+]':(m>=20?'[~]':'[!]');
                return b+' '+m.toFixed(1)+'%';
            }""")
            MG_NEW = JsCode("""function(p){
                var c=p.data['Costo(Gen)'];
                var v=p.data['P.Nuevo'];
                if(!v||v<=0)return'';
                var vact=p.data['P.Act']||p.data['P.General'];
                var ma=(vact>0)?(1-0.05)*(vact-c*1.12)/vact*100:0;
                var mn=(1-0.05)*(v-c*1.12)/v*100;
                var b=mn>=35?'[+]':(mn>=20?'[~]':'[!]');
                var s=b+' '+mn.toFixed(1)+'%';
                var d=mn-ma;
                if(Math.abs(d)>0.05)s+=d>0?' +'+d.toFixed(1)+'pt':' '+d.toFixed(1)+'pt';
                return s;
            }""")

        MG_STYLE = JsCode("""function(p){
            var c=p.data['Costo nvo']||p.data['Costo(Gen)']||0;
            var v=p.data['P.Nuevo']||0;
            if(!v||v<=0)return{};
            var mn=(1-0.05)*(v-c*1.12)/v*100;
            if(mn>=35)return{color:'#1B5E20',fontWeight:'bold'};
            if(mn>=20)return{color:'#E65100',fontWeight:'bold'};
            return{color:'#B71C1C',fontWeight:'bold'};
        }""")

        vis = [c for c in df.columns if not c.startswith("_")]
        gb  = GridOptionsBuilder.from_dataframe(df[vis])
        gb.configure_default_column(resizable=True, sortable=True, editable=False)
        gb.configure_column("Producto", width=130, pinned="left")

        if es_general:
            gb.configure_column("Costo act", width=85, type=["numericColumn"],
                                valueFormatter="'Q'+value.toFixed(2)")
            gb.configure_column("Costo nvo", width=90, editable=True,
                                type=["numericColumn"],
                                valueFormatter="'Q'+value.toFixed(2)",
                                cellStyle=GREEN)
            gb.configure_column("P.General", width=90, type=["numericColumn"],
                                valueFormatter="'Q'+value.toFixed(2)")
            gb.configure_column("P.Nuevo",   width=90, editable=True,
                                type=["numericColumn"],
                                valueFormatter="'Q'+value.toFixed(2)",
                                cellStyle=GREEN)
        else:
            gb.configure_column("Costo(Gen)", width=85, type=["numericColumn"],
                                valueFormatter="'Q'+value.toFixed(2)")
            gb.configure_column("P.General",  width=85, type=["numericColumn"],
                                valueFormatter="'Q'+value.toFixed(2)")
            gb.configure_column("P.Act",      width=85,
                                valueFormatter="params.value?'Q'+Number(params.value).toFixed(2):'(General)'")
            gb.configure_column("P.Nuevo",    width=90, editable=True,
                                type=["numericColumn"],
                                valueFormatter="'Q'+value.toFixed(2)",
                                cellStyle=GREEN)

        go = gb.build()
        go["columnDefs"].append({"field":"_mga","headerName":"Mg.Act",
                                  "width":95,"valueGetter":MG_ACT})
        go["columnDefs"].append({"field":"_mgn","headerName":"Mg.Nuevo",
                                  "width":130,"valueGetter":MG_NEW,
                                  "cellStyle":MG_STYLE})

        result = AgGrid(
            df[vis],
            gridOptions=go,
            update_mode=GridUpdateMode.VALUE_CHANGED,
            allow_unsafe_jscode=True,
            key=f"mc3_ag_{nivel}_{semana}_{anio}",
            height=min(560, 55 + len(df) * 42),
            fit_columns_on_grid_load=True,
        )
        edited = result["data"]

    except ImportError:
        st.warning("streamlit-aggrid no disponible — tabla basica sin margenes en vivo.")
        vis = [c for c in df.columns if not c.startswith("_")]
        ccfg = {"Producto": st.column_config.TextColumn(disabled=True, width="small")}
        ro = {"disabled": True, "format": "Q%.2f", "width": "small"}
        ed = {"format": "Q%.2f", "step": 0.25, "width": "small"}
        if es_general:
            ccfg["Costo act"]  = st.column_config.NumberColumn("Costo act", **ro)
            ccfg["Costo nvo"]  = st.column_config.NumberColumn("Costo nvo", **ed)
            ccfg["P.General"]  = st.column_config.NumberColumn("P.General", **ro)
            ccfg["P.Nuevo"]    = st.column_config.NumberColumn("P.Nuevo",   **ed)
        else:
            ccfg["Costo(Gen)"] = st.column_config.NumberColumn("Costo(Gen)", **ro)
            ccfg["P.General"]  = st.column_config.NumberColumn("P.General",  **ro)
            ccfg["P.Act"]      = st.column_config.NumberColumn("P.Act",      **ro)
            ccfg["P.Nuevo"]    = st.column_config.NumberColumn("P.Nuevo",    **ed)
        edited = st.data_editor(df[vis], column_config=ccfg,
                                hide_index=True, use_container_width=True,
                                key=f"mc3_ed_{nivel}_{semana}",
                                height=min(560, 60+len(df)*35))

    # ── Detectar cambios ──────────────────────────────────────────────────────
    cambios  = []
    orig_map = {r["Producto"]: r for r in rows}

    for _, row in edited.iterrows():
        prod = row["Producto"]
        orig = orig_map.get(prod, {})

        if es_general:
            c_orig = float(orig.get("_costo_orig",  0) or 0)
            p_orig = float(orig.get("_precio_orig", 0) or 0)
            c_nvo  = float(row.get("Costo nvo",  c_orig) or c_orig)
            p_nvo  = float(row.get("P.Nuevo",    p_orig) or p_orig)
            rn     = int(orig.get("_rn", 0))
            if abs(c_nvo-c_orig)>0.001 or abs(p_nvo-p_orig)>0.001:
                cambios.append({"producto": prod, "row_num": rn,
                                "costo_ant": c_orig, "costo_nuevo": c_nvo,
                                "precio_ant": p_orig, "precio_nuevo": p_nvo,
                                "p_cambia": abs(p_nvo-p_orig)>0.001,
                                "c_cambia": abs(c_nvo-c_orig)>0.001})
        else:
            p_act = orig.get("_p_act")
            p_gen = float(orig.get("_p_gen", 0) or 0)
            p_nvo = float(row.get("P.Nuevo", p_gen) or p_gen)
            base  = p_act if p_act is not None else p_gen
            if abs(p_nvo - base) > 0.001:
                cambios.append({"producto": prod,
                                "precio_ant": base, "precio_nuevo": p_nvo,
                                "p_act_nivel": p_act,
                                "p_cambia": True, "c_cambia": False,
                                "costo_ant": 0, "costo_nuevo": 0,
                                "eliminar": (p_nvo <= 0 and p_act is not None)})

    if not cambios:
        st.info("Sin cambios detectados.")
        return

    st.warning(f"**{len(cambios)}** producto(s) con cambios")

    g1, g2 = st.columns([1, 1])
    upd_ped = g1.checkbox("Actualizar lineas de pedidos semana actual",
                           value=True, key="mc3_upd_ped")

    if st.button(f"Guardar {len(cambios)} cambio(s)", type="primary",
                 key="mc3_guardar"):
        with st.spinner("Guardando..."):
            n_cat = n_ped = 0

            if es_general:
                for ch in cambios:
                    data = {}
                    if ch["c_cambia"]: data["costo"]  = ch["costo_nuevo"]
                    if ch["p_cambia"]: data["precio"] = ch["precio_nuevo"]
                    if data and ch["row_num"]:
                        _edit_prod(ch["row_num"], data, es_antigua=False)
                        n_cat += 1
            else:
                for ch in cambios:
                    if ch.get("eliminar"):
                        eliminar_precio_especial(hoja_nivel, lista_nivel, ch["producto"])
                    else:
                        guardar_precio_especial(hoja_nivel, lista_nivel,
                                               ch["producto"], ch["precio_nuevo"])
                    n_cat += 1

            if upd_ped:
                res = actualizar_precio_semana(cambios, semana, anio,
                                               actualizar_catalogo=False)
                n_ped = res.get("filas_pedidos", 0)

        msg = f"{n_cat} precio(s) actualizados en **{nivel}**"
        if n_ped:
            msg += f" + {n_ped} linea(s) de pedidos semana {semana}"
        st.success(msg)

        for k in list(st.session_state.keys()):
            if k.startswith("mc3_ag_") or k.startswith("mc3_ed_"):
                st.session_state.pop(k, None)
        st.rerun()




# ── TAB 2: Migracion ──────────────────────────────────────────────────────────
def _tab_migracion():
    st.markdown("#### Migracion de Datos")
    st.caption("Herramientas para correccion y migracion de datos historicos.")

    from gsheets import get_all_rows, update_cells
    from excel_helper import leer_pedidos

    # ── Centralización del tratamiento comercial (Fase A) ─────────────────────
    st.markdown("### 🎯 Centralizar tratamiento de clientes (Fase A)")
    st.caption("Agrega columnas de tratamiento (lag de pago, retiene ISR, "
               "descuento %) a la hoja Clientes y migra los valores actuales "
               "desde la configuración. Es seguro: NO pisa valores que ya "
               "hayas ajustado a mano (salvo que fuerces).")

    col_m1, col_m2 = st.columns([2, 1])
    with col_m1:
        forzar = st.checkbox("Forzar (re-escribir incluso celdas ya llenas)",
                             key="mig_trato_forzar",
                             help="Úsalo solo si querés reiniciar todo al valor "
                                  "migrado. Perdés los ajustes manuales.")
    with col_m2:
        if st.button("🎯 Migrar tratamiento", key="mig_trato_btn",
                     type="primary"):
            from data_helper import migrar_trato_clientes
            with st.spinner("Migrando tratamiento de clientes..."):
                try:
                    res = migrar_trato_clientes(forzar=forzar)
                    st.success(
                        f"✅ Migración completa: {res['clientes']} clientes · "
                        f"{res['poblados']} poblados · "
                        f"{res['ya_tenian']} ya tenían valores.")
                    st.info("Revisá la hoja Clientes: ahora cada cliente tiene "
                            "su lag_pago (N), retiene_isr (O) y descuento_pct "
                            "(P). Ajustá los que necesiten trato distinto.")
                except Exception as e:
                    st.error(f"Error en la migración: {type(e).__name__}: {e}")

    st.divider()

    # Verificar columna semana
    st.markdown("**Verificar y completar columna Semana/Año en Pedidos**")
    if st.button("Analizar pedidos sin semana", key="mig_sem"):
        todos = leer_pedidos()
        sin_semana = [p for p in todos if not p.get("semana")]
        st.info(f"{len(sin_semana)} pedidos sin semana registrada")

    st.divider()
    st.markdown("**Agregar columna Unico si falta**")
    if st.button("Verificar columna Unico", key="mig_uni"):
        rows = get_all_rows("pedidos")
        headers = rows[0] if rows else []
        st.info(f"Columnas detectadas: {len(headers)}")


# ── TAB 3: Estructura ─────────────────────────────────────────────────────────
def _tab_estructura():
    st.markdown("#### Verificar Google Sheets")
    from gsheets import HOJAS

    if st.button("Verificar conexion a Sheets", key="est_ver"):
        from gsheets import ws as _ws
        hojas_ok = []
        for k, nombre in HOJAS.items():
            try:
                _ws(k)
                hojas_ok.append(f"OK: {nombre}")
            except Exception as e:
                hojas_ok.append(f"ERROR {nombre}: {e}")
        for h in hojas_ok:
            if h.startswith("OK"):
                st.success(h)
            else:
                st.error(h)


# ── TAB 4: Catalogo cliente ───────────────────────────────────────────────────
def _tab_catalogo():
    st.markdown("#### Catalogo de Clientes")
    from data_helper import cargar_clientes
    import pandas as pd

    clientes = cargar_clientes()
    if not clientes:
        st.info("Sin clientes en el catalogo.")
        return

    df = pd.DataFrame([{
        "Nombre":        c.get("nombre",""),
        "Empresa":       c.get("empresa",""),
        "Codigo":        c.get("codigo_lugar",""),
        "Zona":          c.get("zona",""),
    } for c in clientes])
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.caption(f"{len(clientes)} clientes en el catalogo")


# ── TAB 5: Cache ─────────────────────────────────────────────────────────────
def _tab_cache():
    st.markdown("#### Limpiar Cache")
    st.caption("Fuerza recarga de datos desde Google Sheets en la proxima accion.")

    col1, col2, col3 = st.columns(3)

    if col1.button("Limpiar Pedidos", key="cc_ped"):
        from excel_helper import leer_pedidos
        leer_pedidos.clear()
        from excel_helper import leer_pedidos_op as _lpo
        _lpo.clear()
        st.success("Cache de pedidos limpiado.")

    if col2.button("Limpiar Clientes", key="cc_cli"):
        from data_helper import cargar_clientes
        cargar_clientes.clear()
        st.success("Cache de clientes limpiado.")

    if col3.button("Limpiar Productos", key="cc_prod"):
        from data_helper import cargar_productos
        cargar_productos.clear()
        st.success("Cache de productos limpiado.")

    st.divider()
    if st.button("Limpiar TODO el cache", type="primary", key="cc_all"):
        from excel_helper import leer_pedidos
        from data_helper  import cargar_clientes, cargar_productos
        from gsheets      import _gc
        leer_pedidos.clear()
        from excel_helper import leer_pedidos_op as _lpo
        _lpo.clear()
        cargar_clientes.clear()
        cargar_productos.clear()
        _gc.clear()
        st.success("Todo el cache limpiado. La proxima accion lee datos frescos.")


# ── TAB 6: Renombrar clientes ─────────────────────────────────────────────────
def _tab_renombrar():
    st.markdown("#### Renombrar Clientes")
    st.caption("Actualiza el nombre en Clientes y en todos los Pedidos historicos.")

    RENOMBRES = {
        "martin":       "Tierra Fria",
        "rodrigo":      "Aldyk",
        "chimalt":      "Veggi Hogares",
        "veggi":        "Veggi Hogares",
    }

    from gsheets     import get_all_rows, update_cells
    from excel_helper import leer_pedidos
    from data_helper  import cargar_clientes
    import time

    st.markdown("**Cambios configurados:**")
    for viejo, nuevo in RENOMBRES.items():
        st.markdown(f"- `{viejo.capitalize()}` → **{nuevo}**")

    st.divider()

    if st.button("Ver filas a cambiar", key="ren_preview"):
        with st.spinner("Buscando..."):
            rows_cli = get_all_rows("clientes")
            hits_cli = [(i+2, str(row[0]).strip())
                        for i, row in enumerate(rows_cli)
                        if row and str(row[0]).strip().lower() in RENOMBRES]
            todos    = leer_pedidos()
            hits_ped = [(p["row_num"], p["cliente"])
                        for p in todos
                        if p["cliente"].strip().lower() in RENOMBRES]
        st.session_state["ren_cli"] = hits_cli
        st.session_state["ren_ped"] = hits_ped

    hits_cli = st.session_state.get("ren_cli")
    hits_ped = st.session_state.get("ren_ped")

    if hits_cli is not None and hits_ped is not None:
        st.markdown(f"**Clientes:** {len(hits_cli)} fila(s)")
        for rn, nombre in hits_cli:
            st.markdown(f"  Fila {rn}: `{nombre}` → **{RENOMBRES.get(nombre.lower(), '?')}**")
        st.markdown(f"**Pedidos:** {len(hits_ped)} linea(s)")
        for rn, cli in hits_ped[:5]:
            st.markdown(f"  Fila {rn}: `{cli}` → **{RENOMBRES.get(cli.strip().lower(), '?')}**")
        if len(hits_ped) > 5:
            st.caption(f"... y {len(hits_ped)-5} mas")

        total = len(hits_cli) + len(hits_ped)
        if total == 0:
            st.info("No se encontraron registros con esos nombres.")
            return

        st.divider()
        st.warning(f"Se van a modificar {len(hits_cli)} cliente(s) y "
                   f"{len(hits_ped)} linea(s) de pedidos.")

        if st.button(f"Confirmar y renombrar ({total} filas)",
                     type="primary", key="ren_exec"):
            # Auto-backup antes de ejecutar
            with st.spinner("Creando backup previo..."):
                try:
                    from backup_helper import backup_silencioso
                    backup_silencioso(motivo="auto antes de renombrar")
                except Exception:
                    pass

            upd_cli, upd_ped = [], []
            for rn, nombre in hits_cli:
                nuevo = RENOMBRES.get(nombre.lower(), nombre)
                upd_cli.append({"range": f"A{rn}", "values": [[nuevo]]})
            for rn, cli in hits_ped:
                nuevo = RENOMBRES.get(cli.strip().lower(), cli)
                upd_ped.append({"range": f"B{rn}", "values": [[nuevo]]})

            with st.spinner("Actualizando Clientes..."):
                if upd_cli:
                    update_cells("clientes", upd_cli)
            with st.spinner(f"Actualizando {len(upd_ped)} lineas de Pedidos..."):
                for i in range(0, len(upd_ped), 100):
                    update_cells("pedidos", upd_ped[i:i+100])
                    time.sleep(0.5)

            leer_pedidos.clear()
            from excel_helper import leer_pedidos_op as _lpo
            _lpo.clear()
            cargar_clientes.clear()
            st.success(f"Renombrado completo: {len(upd_cli)} cliente(s) + "
                       f"{len(upd_ped)} pedido(s) actualizados.")
            st.session_state.pop("ren_cli", None)
            st.session_state.pop("ren_ped", None)
            st.rerun()




# ── TAB 8: Backup ─────────────────────────────────────────────────────────────
def _tab_backup():
    st.markdown("#### Backup a Google Drive")

    try:
        from backup_helper import crear_backup, backup_info, BACKUP_FILENAME
    except Exception as e:
        st.error(f"Error cargando backup_helper: {e}")
        return

    info = backup_info()
    if info:
        st.success(f"Ultimo backup: {info.get('ts','?')} "
                   f"- {info.get('filas',0)} filas "
                   f"- Motivo: {info.get('motivo','?')}")
    else:
        st.info(f"El archivo se guarda como {BACKUP_FILENAME} en tu carpeta de Drive.")

    st.caption("El backup sobreescribe siempre el mismo archivo. "
               "Se ejecuta automaticamente antes de operaciones destructivas.")
    # ── Diagnóstico ───────────────────────────────────────────────────────────
    with st.expander("🔧 Diagnóstico del backup", expanded=False):
        if st.button("Verificar configuración", key="bk_diag"):
            from backup_helper import diagnostico
            d = diagnostico()
            st.write("**BACKUP_FOLDER_ID en Secrets:**",
                     "✅ Sí" if d["folder_id"] else "❌ Falta")
            st.write("**Credenciales válidas:**",
                     "✅ Sí" if d["credenciales"] else "❌ No")
            st.write("**Carpeta accesible:**",
                     "✅ Sí" if d["carpeta_accesible"] else "❌ No — ¿compartiste la carpeta con el service account?")
            if d["file_id_guardado"]:
                st.write(f"**Backup previo registrado:** ✅ "
                         f"[ver archivo](https://drive.google.com/file/d/{d['file_id_guardado']}/view)")
            else:
                st.write("**Backup previo registrado:** ⚠️ Ninguno — "
                         "nunca se ha creado un backup exitoso.")
            if d["error"]:
                st.error(f"Detalle del error: {d['error']}")

    st.divider()

    # Link directo al archivo en Drive
    from backup_helper import get_drive_link
    drive_link = get_drive_link()
    if drive_link:
        st.markdown(f"[📂 Ver archivo en Drive]({drive_link})", unsafe_allow_html=False)

    if st.button("Crear Backup Ahora", type="primary", key="bk_crear"):
        with st.spinner("Subiendo a Drive..."):
            res = crear_backup(motivo="manual desde Mantenimiento")
        if res.get("ok"):
            st.success(f"Backup guardado - {res['filas']} filas - {res['ts']}")
            link = get_drive_link()
            if link:
                st.markdown(f"[📂 Abrir en Drive]({link})")
        else:
            st.error(f"Error: {res.get('error','desconocido')}")
        st.rerun()

    st.divider()
    st.markdown("**Restaurar desde backup**")
    st.error("PELIGROSO: sobreescribe todos los pedidos actuales.")

    import io
    import pandas as pd

    uploaded = st.file_uploader(
        "Subi el CSV de backup para restaurar",
        type=["csv"], key="bk_upload",
        help=f"Descarga {BACKUP_FILENAME} de tu Drive y subilo aqui"
    )

    if uploaded:
        try:
            content = uploaded.read().decode("utf-8-sig")
            lines   = content.splitlines()
            data_lines = [l for l in lines if not l.startswith("#")]
            joined  = "\n".join(data_lines)
            df      = pd.read_csv(io.StringIO(joined),
                                  header=0, dtype=str).fillna("")
            st.info(f"Archivo: {len(df)} filas")

            if st.checkbox("Entiendo que se sobreescriben todos los pedidos",
                           key="bk_confirm"):
                if st.button("Restaurar", type="secondary", key="bk_restore"):
                    from gsheets import ws as _ws
                    import time
                    sheet = _ws("pedidos")
                    sheet.clear()
                    rows = [df.columns.tolist()] + df.values.tolist()
                    for i in range(0, len(rows), 200):
                        sheet.append_rows(rows[i:i+200],
                                          value_input_option="USER_ENTERED")
                        time.sleep(0.3)
                    from excel_helper import leer_pedidos
                    leer_pedidos.clear()
                    from excel_helper import leer_pedidos_op as _lpo
                    _lpo.clear()
                    st.success(f"{len(df)} filas restauradas.")
                    st.rerun()
        except Exception as e:
            st.error(f"Error leyendo CSV: {e}")


# ── MOSTRAR ────────────────────────────────────────────────────────────────────
def _tab_proveedores():
    """Tab: mantenimiento de proveedores — ver, renombrar."""
    st.markdown("#### Proveedores")
    st.caption("Lista dinamica leida del catalogo de productos. "
               "Para agregar un proveedor nuevo, asignalo a un producto en "
               "Productos → Actualizar.")

    from excel_helper import leer_productos_con_fila
    from gsheets      import update_cells
    from data_helper  import get_proveedores
    import time

    # Leer todos los productos de ambos catalogos
    prods_gen = leer_productos_con_fila(False)
    prods_ant = leer_productos_con_fila(True)
    todos_prods = prods_gen + prods_ant

    proveedores = get_proveedores()

    if not proveedores or proveedores == ["Sin Proveedor"]:
        st.info("No hay proveedores en el catalogo todavia.")
        return

    # Tabla de proveedores con conteo de productos
    from collections import Counter
    conteo = Counter(
        p.get("proveedor","").strip()
        for p in todos_prods
        if p.get("proveedor","").strip()
    )
    import pandas as pd
    df_prov = pd.DataFrame([
        {"Proveedor": prov, "Productos asignados": conteo.get(prov, 0)}
        for prov in sorted(proveedores)
    ])
    st.dataframe(df_prov, hide_index=True, use_container_width=True)

    st.divider()
    st.markdown("**Renombrar proveedor**")
    st.caption("Actualiza el nombre en todos los productos del catalogo General y Antigua.")

    p1, p2 = st.columns(2)
    viejo = p1.selectbox("Proveedor a renombrar", proveedores, key="ren_prov_viejo")
    nuevo = p2.text_input("Nuevo nombre", key="ren_prov_nuevo",
                           placeholder="Nombre correcto del proveedor")

    affected_gen = [p for p in prods_gen
                    if p.get("proveedor","").strip().lower() == viejo.strip().lower()]
    affected_ant = [p for p in prods_ant
                    if p.get("proveedor","").strip().lower() == viejo.strip().lower()]
    total = len(affected_gen) + len(affected_ant)

    if total > 0:
        st.caption(f"{total} producto(s) seran actualizados "
                   f"({len(affected_gen)} General · {len(affected_ant)} Antigua)")

    # Tambien contar pedidos historicos con ese proveedor (columna R)
    from excel_helper import leer_pedidos
    pedidos_all  = leer_pedidos()
    affected_ped = [p for p in pedidos_all
                    if p.get("proveedor","").strip().lower() == viejo.strip().lower()]
    if affected_ped:
        st.caption(f"+ {len(affected_ped)} linea(s) de pedidos historicos "
                   f"tambien seran actualizadas")

    incluir_hist = st.checkbox(
        "Actualizar tambien el historial de Pedidos",
        value=True, key="ren_prov_hist",
        help="Renombra el proveedor en todas las lineas historicas de pedidos")

    if st.button("Renombrar proveedor", type="primary", key="ren_prov_exec",
                 disabled=not nuevo.strip() or not (total or affected_ped)):
        nuevo_n = nuevo.strip()

        # Backup automatico antes de tocar Pedidos
        if incluir_hist and affected_ped:
            try:
                from backup_helper import backup_silencioso
                backup_silencioso(motivo="auto antes de renombrar proveedor")
            except Exception:
                pass

        upd_gen = [{"range": f"O{p['row_num']}", "values": [[nuevo_n]]}
                   for p in affected_gen]
        upd_ant = [{"range": f"M{p['row_num']}", "values": [[nuevo_n]]}
                   for p in affected_ant]
        upd_ped = [{"range": f"R{p['row_num']}", "values": [[nuevo_n]]}
                   for p in affected_ped] if incluir_hist else []

        with st.spinner(f"Actualizando {total} productos"
                        + (f" y {len(upd_ped)} pedidos..." if upd_ped else "...")):
            if upd_gen:
                update_cells("productos", upd_gen)
                time.sleep(0.3)
            if upd_ant:
                update_cells("antigua", upd_ant)
                time.sleep(0.3)
            for i in range(0, len(upd_ped), 100):
                update_cells("pedidos", upd_ped[i:i+100])
                time.sleep(0.5)

        get_proveedores.clear()
        if upd_ped:
            leer_pedidos.clear()
            from excel_helper import leer_pedidos_op as _lpo
            _lpo.clear()
        st.success(f"'{viejo}' renombrado a '{nuevo_n}' — "
                   f"{total} producto(s)"
                   + (f" + {len(upd_ped)} pedido(s) historicos." if upd_ped else "."))
        st.rerun()


def mostrar():
    st.markdown("## Mantenimiento")
    if st.button("Inicio", key="btn_home_mant", type="secondary"):
        st.session_state["_nav_target"] = "Inicio"
        st.rerun()
    st.divider()

    t1, t2, t3, t4, t5, t6, t7, t8, t9, t10 = st.tabs([
        "Correccion Masiva",
        "Migracion de Datos",
        "Estructura Sheets",
        "Catalogo Cliente",
        "Cache",
        "Renombrar Clientes",
        "Proveedores",
        "Backup Drive",
        "🔗 Reparar Pedidos",
        "📏 Unidades",
    ])
    with t1: _tab_correccion()
    with t2: _tab_migracion()
    with t3: _tab_estructura()
    with t4: _tab_catalogo()
    with t5: _tab_cache()
    with t6: _tab_renombrar()
    with t7: _tab_proveedores()
    with t8: _tab_backup()
    with t9: _tab_reparar_pedidos()
    with t10: _tab_unidades()


def _tab_reparar_pedidos():
    """Detecta y une pedidos del mismo cliente y fecha que quedaron separados
    (con códigos únicos distintos) por el bug de agregar líneas."""
    import streamlit as st
    from excel_helper import leer_pedidos
    from collections import defaultdict

    st.markdown("### 🔗 Reparar pedidos divididos")
    st.caption("Detecta pedidos del mismo cliente y misma fecha de entrega que "
               "quedaron separados en dos (por el bug de agregar productos). "
               "Al unirlos, todas las líneas quedan bajo un solo pedido.")

    if st.button("🔍 Buscar pedidos divididos", key="btn_buscar_div"):
        st.session_state["_buscar_div"] = True

    if not st.session_state.get("_buscar_div"):
        return

    pedidos = leer_pedidos()
    # Agrupar por (cliente, fecha) → set de unicos
    por_cli_fecha = defaultdict(lambda: defaultdict(list))
    for p in pedidos:
        if p["status"] == "Cancelado":
            continue
        cli = p["cliente"].strip().lower()
        fec = p["fecha"]
        if not cli or not fec:
            continue
        por_cli_fecha[(cli, fec)][p["unico"]].append(p)

    # Encontrar los que tienen MÁS de un unico (divididos)
    divididos = []
    for (cli, fec), unicos in por_cli_fecha.items():
        if len(unicos) > 1:
            nombre_real = unicos[list(unicos.keys())[0]][0]["cliente"]
            divididos.append({
                "cliente": nombre_real,
                "fecha": fec,
                "unicos": unicos,
            })

    if not divididos:
        st.success("✅ No se encontraron pedidos divididos. Todo está correcto.")
        return

    st.warning(f"Se encontraron **{len(divididos)}** pedido(s) dividido(s):")

    for idx, d in enumerate(divididos):
        fecha_str = d["fecha"].strftime("%d/%m/%Y") if d["fecha"] else "—"
        with st.expander(f"⚠️ {d['cliente']} · {fecha_str} · "
                         f"{len(d['unicos'])} pedidos separados", expanded=True):
            # Mostrar las líneas de cada unico
            unicos_list = list(d["unicos"].items())
            # El unico "principal" será el primero (normalmente el original)
            unico_destino = unicos_list[0][0]

            for u, lineas in unicos_list:
                marca = "🎯 (destino)" if u == unico_destino else "→ se unirá"
                st.markdown(f"**Código `{u}`** {marca}")
                for l in lineas:
                    st.write(f"   • {l['producto']} ×{l['cantidad']:g} "
                             f"@ Q{l['precio']:.2f}")

            # Selector de cuál código conservar
            opciones_codigo = [u for u, _ in unicos_list]
            destino = st.selectbox(
                "¿Bajo qué código unir todas las líneas?",
                opciones_codigo, index=0,
                key=f"destino_{idx}",
                help="Normalmente el primero (el pedido original)")

            if st.button(f"🔗 Unir en un solo pedido",
                         key=f"unir_{idx}", type="primary"):
                _unir_pedidos(d["unicos"], destino)
                st.success(f"✅ Pedidos de {d['cliente']} unidos bajo el código "
                           f"`{destino}`. Recargá para ver el cambio.")
                leer_pedidos.clear()
                from excel_helper import leer_pedidos_op as _lpo
                _lpo.clear()
                st.cache_data.clear()


def _unir_pedidos(unicos: dict, destino: str):
    """Reescribe el código único (columna AB) de todas las líneas al destino."""
    from gsheets import update_cells
    updates = []
    for u, lineas in unicos.items():
        if u == destino:
            continue
        for l in lineas:
            rn = l["row_num"]
            # Columna AB (índice 27, 0-based) = código único
            updates.append({"range": f"AB{rn}", "values": [[destino]]})
    if updates:
        update_cells("pedidos", updates)


def _tab_unidades():
    """Diagnóstico y corrección de unidades inconsistentes: el mismo producto
    con unidades distintas en los pedidos (parte la demanda en A Pedir) o
    con unidad diferente a la del catálogo actual."""
    from data_helper import cargar_productos

    st.markdown("#### 📏 Unidades inconsistentes")
    st.caption("El mismo producto con unidades distintas se parte en varias "
               "filas en A Pedir y confunde el consolidado de compras. Acá "
               "podés detectarlo y corregirlo.")

    if st.button("🔎 Escanear pedidos activos", key="uni_scan"):
        from excel_helper import leer_pedidos as _lp
        todos = _lp()
        # Solo pedidos no cancelados de las últimas ~8 semanas
        from datetime import date, timedelta
        corte = date.today() - timedelta(days=56)
        activos = [p for p in todos
                   if p.get("fecha") and p["fecha"] >= corte
                   and p.get("status") != "Cancelado"]

        # Unidad del catálogo (fuente de verdad)
        cat = {p["nombre"].strip().lower(): p
               for p in cargar_productos(False, solo_catalogo=False)}

        # Agrupar: producto → unidad → filas
        por_prod = {}
        for p in activos:
            prod = str(p.get("producto", "")).strip()
            und  = str(p.get("unidad", "")).strip() or "(sin unidad)"
            por_prod.setdefault(prod, {}).setdefault(und, []).append(p)

        problemas = []
        for prod, unds in sorted(por_prod.items()):
            und_cat = str(cat.get(prod.lower(), {}).get("unidad", "")).strip()
            if len(unds) > 1:
                problemas.append({"producto": prod, "unidades": unds,
                                  "und_catalogo": und_cat,
                                  "tipo": "mixto"})
            elif und_cat and list(unds.keys())[0] != und_cat:
                problemas.append({"producto": prod, "unidades": unds,
                                  "und_catalogo": und_cat,
                                  "tipo": "difiere_catalogo"})
        st.session_state["uni_problemas"] = problemas
        st.rerun()

    problemas = st.session_state.get("uni_problemas")
    if problemas is None:
        return
    if not problemas:
        st.success("✅ Sin inconsistencias: cada producto usa una sola unidad "
                   "y coincide con el catálogo.")
        return

    st.warning(f"Se encontraron **{len(problemas)}** producto(s) con "
               "inconsistencias en pedidos de las últimas 8 semanas.")

    for i, pb in enumerate(problemas):
        etiqueta = ("unidades MEZCLADAS" if pb["tipo"] == "mixto"
                    else "difiere del catálogo")
        with st.expander(f"⚠️ {pb['producto']} — {etiqueta} · catálogo: "
                         f"'{pb['und_catalogo'] or '—'}'"):
            for und, filas in sorted(pb["unidades"].items()):
                clientes = sorted({f["cliente"] for f in filas})[:6]
                st.markdown(
                    f"- **{und}**: {len(filas)} línea(s) · clientes: "
                    f"{', '.join(clientes)}{'…' if len(pb['unidades'][und]) > 6 else ''}")

            und_cat = pb["und_catalogo"]
            if not und_cat:
                st.info("Este producto no está en el catálogo (o no tiene "
                        "unidad definida) — corregí primero el catálogo.")
                continue

            # Corrección: cambiar las filas que NO usan la unidad del catálogo
            filas_mal = [f for und, fs in pb["unidades"].items()
                         if und != und_cat for f in fs]
            if not filas_mal:
                continue
            st.markdown(f"**Corregir {len(filas_mal)} línea(s) → "
                        f"'{und_cat}'** (la unidad del catálogo)")
            factor = st.number_input(
                "Factor de conversión de cantidades (multiplica la cantidad "
                "al cambiar la unidad; dejá 1 si no aplica):",
                min_value=0.0, value=1.0, step=0.5, key=f"uni_factor_{i}",
                help="Ej.: docena → unidad = 12. Las cantidades se "
                     "multiplican por este factor.")
            if st.button(f"✅ Corregir '{pb['producto']}'", key=f"uni_fix_{i}"):
                from gsheets import update_cells
                upd = []
                for f in filas_mal:
                    rn = f["row_num"]
                    upd.append({"range": f"Q{rn}", "values": [[und_cat]]})
                    if factor and factor != 1.0:
                        nueva_cant = round(float(f["cantidad"] or 0) * factor, 2)
                        upd.append({"range": f"C{rn}",
                                    "values": [[nueva_cant]]})
                with st.spinner("Corrigiendo..."):
                    try:
                        update_cells("pedidos", upd)
                        from excel_helper import leer_pedidos as _lp2, \
                            leer_pedidos_op as _lpo2
                        _lp2.clear(); _lpo2.clear()
                        st.success(f"✅ {len(filas_mal)} línea(s) corregidas a "
                                   f"'{und_cat}'"
                                   + (f" (cantidades ×{factor:g})"
                                      if factor != 1.0 else "") + ".")
                        st.session_state.pop("uni_problemas", None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
