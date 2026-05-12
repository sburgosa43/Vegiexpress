"""
modulo_clientes.py — CRUD de clientes
"""
import streamlit as st
from data_helper  import cargar_clientes
from excel_helper import agregar_cliente, editar_cliente, eliminar_cliente

TIPOS_CLIENTE  = ["Restaurante", "Bar", "Hotel", "Procesador", "Cocina", "Otro"]
ESTATUS_OPC    = ["Cliente", "Pendiente"]
LUGARES        = {
    "L01 – Rio Dulce": "L01", "L02 – Monterrico": "L02",
    "L03 – Antigua":   "L03", "L04 – Chimaltenango": "L04",
    "L05 – Guatemala": "L05", "L06 – Otro": "L06",
}

def _form_cliente(prefill: dict = None, key_prefix: str = "new") -> dict | None:
    """Formulario reutilizable para crear/editar un cliente."""
    pf = prefill or {}
    with st.form(key=f"form_cli_{key_prefix}"):
        col1, col2 = st.columns(2)
        with col1:
            nombre    = st.text_input("Nombre *",       value=pf.get("nombre",""))
            empresa   = st.text_input("Empresa",        value=pf.get("empresa",""))
            direccion = st.text_input("Dirección",      value=pf.get("direccion",""))
            ubicacion = st.text_input("Ubicación",      value=pf.get("ubicacion",""))
            telefono  = st.text_input("Teléfono",       value=pf.get("telefono",""))
        with col2:
            nit     = st.text_input("NIT",              value=pf.get("nit","0"))
            tipo    = st.selectbox("Tipo",              TIPOS_CLIENTE,
                                    index=TIPOS_CLIENTE.index(pf["tipo"])
                                    if pf.get("tipo") in TIPOS_CLIENTE else 0)
            estatus = st.selectbox("Estatus",           ESTATUS_OPC,
                                    index=ESTATUS_OPC.index(pf["estatus"])
                                    if pf.get("estatus") in ESTATUS_OPC else 1)
            credito = st.number_input("Días de crédito", min_value=0,
                                       value=int(pf.get("credito", 0)), step=1)
            lugar_actual = pf.get("codigo_lugar","L05")
            lugar_label  = next((k for k,v in LUGARES.items() if v == lugar_actual),
                                 list(LUGARES.keys())[4])
            lugar_sel    = st.selectbox("Código Lugar",  list(LUGARES.keys()),
                                         index=list(LUGARES.keys()).index(lugar_label))

        submitted = st.form_submit_button("💾 Guardar", type="primary")
        if submitted:
            if not nombre.strip():
                st.error("El nombre es obligatorio.")
                return None
            return {
                "nombre": nombre.strip(), "empresa": empresa.strip() or nombre.strip(),
                "direccion": direccion.strip(), "ubicacion": ubicacion.strip(),
                "telefono": telefono.strip(), "nit": nit.strip() or "0",
                "tipo": tipo, "estatus": estatus, "credito": credito,
                "codigo_lugar": LUGARES[lugar_sel],
            }
    return None


def mostrar():
    st.markdown("## 👥 Clientes")

    clientes = cargar_clientes()

    tab_lista, tab_nuevo = st.tabs(["📋 Lista de clientes", "➕ Nuevo cliente"])

    # ── TAB: LISTA ────────────────────────────────────────────────────────────
    with tab_lista:
        if not clientes:
            st.info("No hay clientes registrados.")
        else:
            busqueda = st.text_input("🔍 Buscar", placeholder="Nombre o empresa...")
            lista_f  = [c for c in clientes
                        if busqueda.lower() in c["nombre"].lower()
                        or busqueda.lower() in c["empresa"].lower()] \
                       if busqueda else clientes

            st.markdown(f"**{len(lista_f)} clientes**")
            st.divider()

            # Mostrar cada cliente en un expander
            # Pre-cargar los clientes con row_num
            from drive_helper import cargar_para_lectura
            from streamlit import secrets
            FILE_ID = secrets["EXCEL_FILE_ID"]
            import openpyxl
            wb_tmp  = cargar_para_lectura(FILE_ID)
            ws_tmp  = wb_tmp["Clientes"]
            row_map = {}
            for i, row in enumerate(ws_tmp.iter_rows(min_row=2, values_only=True), start=2):
                if row[0]:
                    row_map[str(row[0]).strip()] = i
            wb_tmp.close()

            for c in lista_f:
                row_num = row_map.get(c["nombre"])
                badge   = "🟢" if c["activo"] else "🟡"
                with st.expander(
                    f"{badge} {c['nombre']} · {c['empresa']} · {c['codigo_lugar']}",
                    expanded=False,
                ):
                    st.markdown(
                        f"📍 {c['direccion']} · 🏷️ {c['tipo']} · "
                        f"💳 NIT: {c['nit']} · 📅 Crédito: {c['credito']} días · "
                        f"📌 Cod: {c['codigo']}"
                    )

                    modo_key = f"modo_{c['nombre']}"
                    if modo_key not in st.session_state:
                        st.session_state[modo_key] = "ver"

                    col_e, col_d = st.columns(2)
                    with col_e:
                        if st.button("✏️ Editar", key=f"btn_edit_{c['nombre']}"):
                            st.session_state[modo_key] = "editar"
                            st.rerun()
                    with col_d:
                        if st.button("🗑️ Eliminar", key=f"btn_del_{c['nombre']}",
                                     type="secondary"):
                            st.session_state[modo_key] = "confirmar_borrado"
                            st.rerun()

                    # Formulario de edición
                    if st.session_state[modo_key] == "editar" and row_num:
                        st.divider()
                        datos = _form_cliente(prefill=c, key_prefix=f"edit_{c['nombre']}")
                        if datos:
                            with st.spinner("Guardando..."):
                                editar_cliente(row_num, datos)
                            st.success("✅ Cliente actualizado.")
                            st.session_state[modo_key] = "ver"
                            st.rerun()

                    # Confirmación de borrado
                    if st.session_state[modo_key] == "confirmar_borrado" and row_num:
                        st.error(f"⚠️ ¿Eliminar a **{c['nombre']}**? Esta acción no se puede deshacer.")
                        cc1, cc2 = st.columns(2)
                        with cc1:
                            if st.button("✅ Sí, eliminar", key=f"confirm_del_{c['nombre']}",
                                         type="primary"):
                                with st.spinner("Eliminando..."):
                                    eliminar_cliente(row_num)
                                st.success("Cliente eliminado.")
                                st.session_state[modo_key] = "ver"
                                st.rerun()
                        with cc2:
                            if st.button("❌ Cancelar", key=f"cancel_del_{c['nombre']}"):
                                st.session_state[modo_key] = "ver"
                                st.rerun()

    # ── TAB: NUEVO CLIENTE ────────────────────────────────────────────────────
    with tab_nuevo:
        st.markdown("#### Agregar nuevo cliente")
        datos = _form_cliente(key_prefix="nuevo")
        if datos:
            with st.spinner("Guardando..."):
                codigo = agregar_cliente(datos)
            st.success(f"✅ Cliente **{datos['nombre']}** creado con código **{codigo}**.")
