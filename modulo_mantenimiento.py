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

    c1, c2 = st.columns(2)
    semana = c1.number_input("Semana", 1, 53, sem_def, key="mc_sem")
    anio   = c2.number_input("Año",  2020, 2030, hoy.year, key="mc_anio")

    todos = leer_pedidos()
    prods_map = {p["nombre"]: p for p in cargar_productos()}

    pedidos_sem = [p for p in todos
                   if p["semana"] == semana and p["año"] == anio
                   and p["status"] != "Cancelado"]

    if not pedidos_sem:
        st.info(f"Sin pedidos activos en semana {semana}/{anio}.")
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

    df = pd.DataFrame(rows)
    edited = st.data_editor(
        df,
        column_config={
            "Producto":   st.column_config.TextColumn(disabled=True),
            "Precio Act": st.column_config.NumberColumn(format="Q%.2f", disabled=True),
            "Nuevo Precio": st.column_config.NumberColumn(format="Q%.2f", step=0.25),
            "Costo Act":  st.column_config.NumberColumn(format="Q%.2f", disabled=True),
            "Nuevo Costo": st.column_config.NumberColumn(format="Q%.2f", step=0.25),
        },
        hide_index=True, use_container_width=True, key="mc_editor"
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
        "martin":  "Tierra Fria",
        "rodrigo": "Aldyk",
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
                upd_cli.append({"range": f"B{rn}", "values": [[nuevo]]})
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


# ── TAB 7: Recuperar fechas ────────────────────────────────────────────────────
def _tab_recuperar_fechas():
    st.markdown("#### Recuperar Fechas Sobreescritas")
    st.error("Este tab corrige el error de renombrado: restaura fechas en columna A "
             "y escribe los nombres nuevos en columna B.")

    MAPA = {
        "aldyk":       ("Aldyk",       "Rodrigo"),
        "tierra fria": ("Tierra Fria", "Martin"),
    }

    from gsheets import update_cells, ws as _ws
    from datetime import date as _date
    import time

    if st.button("Ver filas a recuperar", key="rec_preview"):
        sheet = _ws("pedidos")
        all_rows = sheet.get_all_values()
        hits = []
        for i, row in enumerate(all_rows[1:], start=2):
            if not row: continue
            col_a = str(row[0]).strip().lower()
            if col_a in MAPA:
                hits.append({
                    "row_num": i,
                    "col_a":   str(row[0]).strip(),
                    "col_b":   str(row[1]).strip() if len(row) > 1 else "",
                    "semana":  str(row[14]).strip() if len(row) > 14 else "",
                    "anio":    str(row[15]).strip() if len(row) > 15 else "",
                })
        st.session_state["rec_hits"] = hits

    hits = st.session_state.get("rec_hits")
    if hits is not None:
        st.markdown(f"**{len(hits)} fila(s) con fecha sobreescrita:**")
        for h in hits[:8]:
            st.markdown(f"  Fila {h['row_num']}: ColA={h['col_a']} "
                        f"Sem={h['semana']} Anio={h['anio']}")
        if len(hits) > 8:
            st.caption(f"... y {len(hits)-8} mas")

        if not hits:
            st.success("No se encontraron filas con fechas sobreescritas.")
            return

        st.divider()
        st.warning(f"Se van a restaurar {len(hits)} fechas y corregir nombres.")

        if st.button(f"Recuperar {len(hits)} filas", type="primary", key="rec_exec"):
            upd = []
            for h in hits:
                nombre_en_a = h["col_a"].lower()
                if nombre_en_a not in MAPA: continue
                nuevo_nombre, _ = MAPA[nombre_en_a]
                try:
                    sem = int(h["semana"])
                    anio = int(h["anio"])
                    fecha_rec = _date.fromisocalendar(anio, sem, 1).strftime("%d/%m/%Y")
                except Exception:
                    fecha_rec = "01/01/2025"
                rn = h["row_num"]
                upd.append({"range": f"A{rn}", "values": [[fecha_rec]]})
                upd.append({"range": f"B{rn}", "values": [[nuevo_nombre]]})

            with st.spinner(f"Restaurando {len(upd)} celdas..."):
                for i in range(0, len(upd), 100):
                    update_cells("pedidos", upd[i:i+100])
                    time.sleep(0.3)

            from excel_helper import leer_pedidos
            leer_pedidos.clear()
            st.success(f"{len(hits)} filas recuperadas.")
            st.session_state.pop("rec_hits", None)
            st.caption("Las fechas son el lunes de cada semana (aproximacion).")
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
    st.divider()

    if st.button("Crear Backup Ahora", type="primary", key="bk_crear"):
        with st.spinner("Subiendo a Drive..."):
            res = crear_backup(motivo="manual desde Mantenimiento")
        if res.get("ok"):
            st.success(f"Backup guardado - {res['filas']} filas - {res['ts']}")
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
        "Recuperar Fechas",
        "Backup Drive",
    ])
    with t1: _tab_correccion()
    with t2: _tab_migracion()
    with t3: _tab_estructura()
    with t4: _tab_catalogo()
    with t5: _tab_cache()
    with t6: _tab_renombrar()
    with t7: _tab_recuperar_fechas()
    with t8: _tab_backup()
