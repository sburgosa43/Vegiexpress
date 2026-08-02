"""
modulo_mantenimiento.py — Herramientas de mantenimiento y administracion.
"""
import streamlit as st
from datetime import date

from config import IVA_FACTOR, ISR_FACTOR


def _js_margen(c: str, v: str) -> str:
    """Expresión JavaScript del margen neto en %, para las variables `c` (costo)
    y `v` (precio) del renderer de AgGrid.

    Los renderers corren en el navegador, así que no pueden llamar a
    config.margen_neto_pct. Se inyectan las tasas para que la fórmula del JS no
    quede desincronizada de la de Python si cambia el IVA o el ISR.
    """
    return f"({ISR_FACTOR}*({v}-{c}*{IVA_FACTOR})/{v}*100)"


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

    # Correccion Masiva se movio a Productos -> Actualizar Precios Masivo y
    # Actualizar Costos Masivo: aquella filtraba por pertenencia a la zona y le
    # pisaba el precio a los clientes con precio individual negociado.
    t1, t2, t3, t4, t5, t6, t7, t8, t9 = st.tabs([
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
    with t1: _tab_migracion()
    with t2: _tab_estructura()
    with t3: _tab_catalogo()
    with t4: _tab_cache()
    with t5: _tab_renombrar()
    with t6: _tab_proveedores()
    with t7: _tab_backup()
    with t8: _tab_reparar_pedidos()
    with t9: _tab_unidades()


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
