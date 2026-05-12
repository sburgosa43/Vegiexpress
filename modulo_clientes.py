"""
modulo_clientes.py — CRUD de clientes
"""
import streamlit as st
from data_helper  import cargar_clientes
from excel_helper import agregar_cliente, editar_cliente, eliminar_cliente

TIPOS_CLIENTE = ["Restaurante", "Bar", "Hotel", "Procesador", "Cocina", "Otro"]
ESTATUS_OPC   = ["Cliente", "Pendiente"]
LUGARES       = {
    "L01 – Rio Dulce":       "L01",
    "L02 – Monterrico":      "L02",
    "L03 – Antigua":         "L03",
    "L04 – Chimaltenango":   "L04",
    "L05 – Guatemala":       "L05",
    "L06 – Otro":            "L06",
}
LUGAR_KEYS = list(LUGARES.keys())
LUGAR_VALS = list(LUGARES.values())


def _safe_key(texto: str) -> str:
    """Convierte un texto a key seguro para Streamlit (sin espacios ni caracteres raros)."""
    import re
    return re.sub(r"[^a-zA-Z0-9_]", "_", str(texto))


def _form_cliente(prefill: dict = None, key_prefix: str = "new") -> dict | None:
    pf = prefill or {}

    tipo_idx = 0
    if pf.get("tipo"):
        tipos_norm = [t.lower() for t in TIPOS_CLIENTE]
        if pf["tipo"].lower() in tipos_norm:
            tipo_idx = tipos_norm.index(pf["tipo"].lower())

    est_idx = 1
    if pf.get("estatus") and pf["estatus"].lower() in ["cliente","pendiente"]:
        est_idx = 0 if pf["estatus"].lower() == "cliente" else 1

    lugar_actual = pf.get("codigo_lugar", "L05")
    lugar_idx = LUGAR_VALS.index(lugar_actual) if lugar_actual in LUGAR_VALS else 4

    with st.form(key=f"form_cli_{key_prefix}"):
        col1, col2 = st.columns(2)
        with col1:
            nombre    = st.text_input("Nombre *",      value=pf.get("nombre",""))
            empresa   = st.text_input("Empresa",        value=pf.get("empresa",""))
            direccion = st.text_input("Dirección",      value=pf.get("direccion",""))
            ubicacion = st.text_input("Ubicación",      value=pf.get("ubicacion",""))
            telefono  = st.text_input("Teléfono",       value=pf.get("telefono",""))
        with col2:
            nit     = st.text_input("NIT",              value=pf.get("nit","0"))
            tipo    = st.selectbox("Tipo",              TIPOS_CLIENTE, index=tipo_idx)
            estatus = st.selectbox("Estatus",           ESTATUS_OPC,   index=est_idx)
            credito = st.number_input("Días de crédito",
                                       min_value=0, value=int(pf.get("credito",0)), step=1)
            lugar_sel = st.selectbox("Código Lugar", LUGAR_KEYS, index=lugar_idx)

        submitted = st.form_submit_button("💾 Guardar", type="primary")
        if submitted:
            if not nombre.strip():
                st.error("El nombre es obligatorio.")
                return None
            return {
                "nombre":       nombre.strip(),
                "empresa":      empresa.strip() or nombre.strip(),
                "direccion":    direccion.strip(),
                "ubicacion":    ubicacion.strip(),
                "telefono":     telefono.strip(),
                "nit":          nit.strip() or "0",
                "tipo":         tipo,
                "estatus":      estatus,
                "credito":      credito,
                "codigo_lugar": LUGARES[lugar_sel],
            }
    return None


def _cargar_row_map():
    """Lee el Excel una sola vez y retorna {nombre: row_num}."""
    from drive_helper import cargar_para_lectura
    FILE_ID = st.secrets["EXCEL_FILE_ID"]
    wb = cargar_para_lectura(FILE_ID)
    ws = wb["Clientes"]
    rmap = {}
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if row[0]:
            rmap[str(row[0]).strip()] = i
    wb.close()
    return rmap


def mostrar():
    st.markdown("## 👥 Clientes")

    clientes = cargar_clientes()
    tab_lista, tab_nuevo = st.tabs(["📋 Lista de clientes", "➕ Nuevo cliente"])

    # ── TAB: LISTA ────────────────────────────────────────────────────────────
    with tab_lista:
        if not clientes:
            st.info("No hay clientes registrados.")
        else:
            busqueda = st.text_input("🔍 Buscar", placeholder="Nombre, empresa o zona...")
            lista_f  = (
                [c for c in clientes
                 if busqueda.lower() in c["nombre"].lower()
                 or busqueda.lower() in c["empresa"].lower()
                 or busqueda.lower() in c["codigo_lugar"].lower()]
                if busqueda else clientes
            )
            st.markdown(f"**{len(lista_f)} clientes**")
            st.divider()

            # Cargar row_map una sola vez para toda la lista
            if "cli_row_map" not in st.session_state:
                st.session_state.cli_row_map = _cargar_row_map()
            row_map = st.session_state.cli_row_map

            for idx, c in enumerate(lista_f):
                # Key única basada en índice + código del cliente
                uid      = f"{idx}_{_safe_key(c.get('codigo', '') or c['nombre'])}"
                row_num  = row_map.get(c["nombre"])
                badge    = "🟢" if c["activo"] else "🟡"
                modo_key = f"modo_cli_{uid}"
                if modo_key not in st.session_state:
                    st.session_state[modo_key] = "ver"

                with st.expander(
                    f"{badge} **{c['nombre']}** · {c['empresa']} · "
                    f"{c['codigo_lugar']} · {c.get('codigo','')}",
                    expanded=False,
                ):
                    st.caption(
                        f"📍 {c['direccion']} · 🏷️ {c['tipo']} · "
                        f"💳 NIT: {c['nit']} · 📅 Crédito: {c['credito']} días"
                    )

                    col_e, col_d = st.columns(2)
                    with col_e:
                        if st.button("✏️ Editar", key=f"btn_e_{uid}"):
                            st.session_state[modo_key] = "editar"
                            st.rerun()
                    with col_d:
                        if st.button("🗑️ Eliminar", key=f"btn_d_{uid}",
                                     type="secondary"):
                            st.session_state[modo_key] = "confirmar"
                            st.rerun()

                    # ── Formulario de edición ─────────────────────────────────
                    if st.session_state[modo_key] == "editar":
                        st.divider()
                        if not row_num:
                            st.warning("No se encontró la fila en el Excel. "
                                       "Recargá la página e intentá de nuevo.")
                        else:
                            datos = _form_cliente(prefill=c, key_prefix=f"e_{uid}")
                            if datos:
                                with st.spinner("Guardando..."):
                                    editar_cliente(row_num, datos)
                                    st.session_state.cli_row_map = _cargar_row_map()
                                st.success("✅ Cliente actualizado.")
                                st.session_state[modo_key] = "ver"
                                st.rerun()

                    # ── Confirmación de borrado ───────────────────────────────
                    if st.session_state[modo_key] == "confirmar":
                        st.error(
                            f"⚠️ ¿Eliminar a **{c['nombre']}**? "
                            "Esta acción no se puede deshacer."
                        )
                        cc1, cc2 = st.columns(2)
                        with cc1:
                            if st.button("✅ Sí, eliminar",
                                         key=f"btn_yes_{uid}", type="primary"):
                                if not row_num:
                                    st.error("Fila no encontrada.")
                                else:
                                    with st.spinner("Eliminando..."):
                                        eliminar_cliente(row_num)
                                        st.session_state.cli_row_map = _cargar_row_map()
                                    st.success("Cliente eliminado.")
                                    st.session_state[modo_key] = "ver"
                                    st.rerun()
                        with cc2:
                            if st.button("❌ Cancelar", key=f"btn_no_{uid}"):
                                st.session_state[modo_key] = "ver"
                                st.rerun()

    # ── TAB: NUEVO CLIENTE ────────────────────────────────────────────────────
    with tab_nuevo:
        st.markdown("#### Agregar nuevo cliente")
        datos = _form_cliente(key_prefix="nuevo")
        if datos:
            with st.spinner("Guardando..."):
                codigo = agregar_cliente(datos)
                # Refrescar el row_map
                if "cli_row_map" in st.session_state:
                    del st.session_state["cli_row_map"]
            st.success(
                f"✅ Cliente **{datos['nombre']}** creado con código **{codigo}**."
            )
