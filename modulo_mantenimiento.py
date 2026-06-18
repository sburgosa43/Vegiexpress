"""
modulo_mantenimiento.py — Herramientas de mantenimiento y administracion.
"""
import streamlit as st
from datetime import date


# ── TAB 1: Correccion masiva ──────────────────────────────────────────────────
def _tab_correccion():
    st.markdown("#### Correccion Masiva de Precios / Costos")
    from excel_helper import leer_pedidos, actualizar_precio_semana
    from data_helper  import cargar_productos

    hoy     = date.today()
    sem_def = hoy.isocalendar()[1]

    from data_helper import cargar_clientes
    from config import ZONAS_MAP as _ZM

    c1, c2, c3 = st.columns(3)
    semana = c1.number_input("Semana", 1, 53, sem_def, key="mc_sem")
    anio   = c2.number_input("Año",  2020, 2030, hoy.year, key="mc_anio")

    # Filtro de zona — limita a clientes de la zona seleccionada
    zona_opts = ["Todas"] + [k for k in _ZM.keys() if k != "Todas"]
    zona_sel  = c3.selectbox("Zona", zona_opts, key="mc_zona",
                              help="Filtra a clientes de la zona elegida")

    todos      = leer_pedidos()
    clientes   = {c["nombre"].lower().strip(): c for c in cargar_clientes()}
    prods_map  = {p["nombre"]: p for p in cargar_productos()}

    def _en_zona(cliente_nombre: str) -> bool:
        if zona_sel == "Todas":
            return True
        cli = clientes.get(cliente_nombre.lower().strip())
        if not cli:
            return False
        codigos_zona = _ZM.get(zona_sel, [])
        return cli.get("codigo_lugar", "") in codigos_zona

    pedidos_sem = [p for p in todos
                   if p["semana"] == semana and p["año"] == anio
                   and p["status"] != "Cancelado"
                   and _en_zona(p["cliente"])]

    if not pedidos_sem:
        st.info(f"Sin pedidos activos en semana {semana}/{anio}"
                + (f" para zona {zona_sel}." if zona_sel != "Todas" else "."))
        return

    prods_sem = sorted({p["producto"] for p in pedidos_sem})
    st.caption(f"{len(pedidos_sem)} lineas · {len(prods_sem)} productos distintos")

    import pandas as pd
    rows = []
    for prod in prods_sem:
        lineas = [p for p in pedidos_sem if p["producto"] == prod]
        precio_actual = lineas[0]["precio"] if lineas else 0
        costo_actual  = lineas[0].get("costo", 0) or 0
        rows.append({
            "Producto":   prod,
            "Precio Act": precio_actual,
            "Nuevo Precio": precio_actual,
            "Costo Act":  costo_actual,
            "Nuevo Costo": costo_actual,
        })

    # ── Margen en vivo ───────────────────────────────────────────────────────
    IVA, ISR = 0.12, 0.05

    def _mg(costo, precio):
        if float(precio) <= 0: return 0.0
        return (1 - ISR) * (float(precio) - float(costo) * (1 + IVA)) / float(precio) * 100

    def _mg_txt(mg_nuevo, mg_saved=None):
        badge = "🟢" if mg_nuevo >= 35 else ("🟡" if mg_nuevo >= 20 else "🔴")
        s = f"{badge} {mg_nuevo:.1f}%"
        if mg_saved is not None and abs(mg_nuevo - mg_saved) > 0.05:
            d = mg_nuevo - mg_saved
            s += f"  ↑+{d:.1f}" if d > 0 else f"  ↓{d:.1f}"
        return s

    # Leer edits previos para margen en vivo
    prev_edits = {}
    ed_state = st.session_state.get("mc_editor")
    if isinstance(ed_state, dict):
        prev_edits = ed_state.get("edited_rows", {})

    # Agregar márgenes al DataFrame
    rows_mg = []
    for idx, row in enumerate(rows):
        edits   = prev_edits.get(idx, prev_edits.get(str(idx), {}))
        p_nuevo = float(edits.get("Nuevo Precio", row["Nuevo Precio"]))
        c_nuevo = float(edits.get("Nuevo Costo",  row["Nuevo Costo"]))
        mg_act  = _mg(row["Costo Act"], row["Precio Act"])
        mg_new  = _mg(c_nuevo, p_nuevo)
        rows_mg.append({**row,
                        "Margen Act":   _mg_txt(mg_act),
                        "Nuevo Precio": p_nuevo,
                        "Nuevo Costo":  c_nuevo,
                        "Margen Nuevo": _mg_txt(mg_new, mg_act)})

    df = pd.DataFrame(rows_mg)

    edited = st.data_editor(
        df,
        column_config={
            "Producto":     st.column_config.TextColumn(disabled=True, width="large"),
            "Precio Act":   st.column_config.NumberColumn("Precio Act",  format="Q%.2f", disabled=True),
            "Costo Act":    st.column_config.NumberColumn("Costo Act",   format="Q%.2f", disabled=True),
            "Margen Act":   st.column_config.TextColumn("Margen Act",   disabled=True),
            "Nuevo Precio": st.column_config.NumberColumn("Nuevo Precio", format="Q%.2f", step=0.25),
            "Nuevo Costo":  st.column_config.NumberColumn("Nuevo Costo",  format="Q%.2f", step=0.25),
            "Margen Nuevo": st.column_config.TextColumn("Margen Nuevo", disabled=True),
        },
        hide_index=True, use_container_width=True, key="mc_editor",
        height=min(600, 60 + len(df) * 35),
    )

    cambios = []
    for _, row in edited.iterrows():
        p_cambia = abs(row["Nuevo Precio"] - row["Precio Act"]) > 0.001
        c_cambia = abs(row["Nuevo Costo"]  - row["Costo Act"])  > 0.001
        if p_cambia or c_cambia:
            cambios.append({
                "producto":    row["Producto"],
                "precio_ant":  row["Precio Act"],
                "precio_nuevo": row["Nuevo Precio"],
                "costo_ant":   row["Costo Act"],
                "costo_nuevo": row["Nuevo Costo"],
                "p_cambia": p_cambia,
                "c_cambia": c_cambia,
            })

    if not cambios:
        st.info("Sin cambios detectados.")
        return

    st.warning(f"{len(cambios)} producto(s) con cambios")
    upd_cat = st.checkbox("Actualizar en catalogo (aplica a pedidos futuros)",
                          value=True, key="mc_cat")

    if st.button(f"Aplicar {len(cambios)} cambio(s)", type="primary", key="mc_guardar"):
        with st.spinner("Actualizando..."):
            res = actualizar_precio_semana(cambios, semana, anio,
                                           actualizar_catalogo=upd_cat)
        st.success(f"{res['filas_pedidos']} lineas actualizadas"
                   + (f" + catalogo ({res['prods_catalogo']} campos)" if upd_cat else ""))
        st.rerun()


# ── TAB 2: Migracion ──────────────────────────────────────────────────────────
def _tab_migracion():
    st.markdown("#### Migracion de Datos")
    st.caption("Herramientas para correccion y migracion de datos historicos.")

    from gsheets import get_all_rows, update_cells
    from excel_helper import leer_pedidos

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

    t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs([
        "Correccion Masiva",
        "Migracion de Datos",
        "Estructura Sheets",
        "Catalogo Cliente",
        "Cache",
        "Renombrar Clientes",
        "Proveedores",
        "Backup Drive",
    ])
    with t1: _tab_correccion()
    with t2: _tab_migracion()
    with t3: _tab_estructura()
    with t4: _tab_catalogo()
    with t5: _tab_cache()
    with t6: _tab_renombrar()
    with t7: _tab_proveedores()
    with t8: _tab_backup()
