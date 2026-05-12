"""
modulo_productos.py — CRUD de productos (lista normal y lista Antigua)
"""
import streamlit as st
from excel_helper import leer_productos_con_fila, agregar_producto, editar_producto, eliminar_producto

UNIDADES    = ["Libra","Unidad","Manojo","Caja","Kilo","Onza","Docena","Bandeja",
               "Galon","Paquete","Penca","Red","lbs","libra","1 Onza","4 Onzas",
               "6 Onzas","8 Onzas","12 Onzas","15 Onzas","12 Unidades","10 Unidades","900 gr","390 gr"]
SEGMENTOS   = ["Vegetales","Frutas","Hierbas","Congelados","Abarrotes","Especias",
               "Flores","Granos","Mariscos"]
TIPOS_PROD  = ["Fresco","Proceso","Envasado"]
TIPOS_P2    = ["Premium","Alto","Media Alta","Media","Media Baja","Baja","Sin Segmento"]
COTIZAR_OPC = ["", "s", "n", "Especialidad"]
PROVEEDORES = ["Cenma","Rio","Patojas","Santiago","Super Bueno","Gordian","Vidaurri",
               "Fogliasana","Canche","Carlos","Cristobal","Esquina","Jenny","Machun",
               "Marcelo","Marisco","Nadie","Price","angel","antigua","marcelo"]


def _form_producto(prefill: dict = None, key_prefix: str = "new",
                   es_antigua: bool = False) -> dict | None:
    pf = prefill or {}
    with st.form(key=f"form_prod_{key_prefix}"):
        col1, col2 = st.columns(2)
        with col1:
            nombre = st.text_input("Producto *", value=pf.get("nombre",""))
            unidad = st.selectbox(
                "Unidad de venta",
                UNIDADES,
                index=UNIDADES.index(pf["unidad"]) if pf.get("unidad") in UNIDADES else 0,
            )
            segmento = st.selectbox(
                "Segmento",
                SEGMENTOS,
                index=SEGMENTOS.index(pf["segmento"]) if pf.get("segmento") in SEGMENTOS else 0,
            )
            unidad_despacho = st.number_input("Unidad despacho",
                                               value=int(pf.get("unidad_despacho",1)), min_value=1)
            proveedor = st.selectbox(
                "Proveedor",
                PROVEEDORES,
                index=PROVEEDORES.index(pf["proveedor"]) if pf.get("proveedor") in PROVEEDORES else 0,
            )
        with col2:
            costo  = st.number_input("Costo (Q)", value=float(pf.get("costo",0)), min_value=0.0, step=0.5)
            precio = st.number_input("Precio (Q)", value=float(pf.get("precio",0)), min_value=0.0, step=0.5)
            pesos  = st.number_input("Pesos/Costo referencia",
                                      value=float(pf.get("pesos",0)), min_value=0.0, step=0.1)
            tipo2 = st.selectbox(
                "Segmentación de margen",
                TIPOS_P2,
                index=TIPOS_P2.index(pf["tipo_producto2"]) if pf.get("tipo_producto2") in TIPOS_P2 else 3,
            )
            if not es_antigua:
                tipo1 = st.selectbox(
                    "Tipo de producto",
                    TIPOS_PROD,
                    index=TIPOS_PROD.index(pf["tipo_producto"]) if pf.get("tipo_producto") in TIPOS_PROD else 0,
                )
                cotizar = st.selectbox(
                    "Para cotizar",
                    COTIZAR_OPC,
                    index=COTIZAR_OPC.index(pf["para_cotizar"]) if pf.get("para_cotizar") in COTIZAR_OPC else 0,
                )
                parent = st.text_input("Parent (nombre base)", value=pf.get("parent", pf.get("nombre","")))
                comentario = st.text_input("Comentario", value=pf.get("comentario",""))
            else:
                tipo1 = "Fresco"; cotizar = ""; parent = ""; comentario = ""

        submitted = st.form_submit_button("💾 Guardar", type="primary")
        if submitted:
            if not nombre.strip():
                st.error("El nombre del producto es obligatorio.")
                return None
            if precio <= 0:
                st.error("El precio debe ser mayor a 0.")
                return None
            return {
                "nombre": nombre.strip(), "unidad": unidad,
                "segmento": segmento, "unidad_despacho": unidad_despacho,
                "costo": costo, "precio": precio, "pesos": pesos,
                "proveedor": proveedor, "tipo_producto": tipo1,
                "tipo_producto2": tipo2, "para_cotizar": cotizar,
                "parent": parent or nombre.strip(), "comentario": comentario,
            }
    return None


def _mostrar_lista(es_antigua: bool):
    lbl = "Antigua" if es_antigua else "General"
    productos = leer_productos_con_fila(es_antigua=es_antigua)

    busqueda = st.text_input(f"🔍 Buscar en lista {lbl}",
                              placeholder="Nombre o segmento...",
                              key=f"busq_prod_{lbl}")
    filtrados = [p for p in productos
                 if busqueda.lower() in p["nombre"].lower()
                 or busqueda.lower() in p["segmento"].lower()] \
                if busqueda else productos

    st.markdown(f"**{len(filtrados)} productos**")

    # Mostrar en tabla compacta con acciones
    for prod in filtrados:
        modo_key = f"modo_prod_{lbl}_{prod['nombre']}"
        if modo_key not in st.session_state:
            st.session_state[modo_key] = "ver"

        with st.expander(
            f"**{prod['nombre']}** · {prod['unidad']} · "
            f"Costo Q{prod['costo']:.2f} · Precio Q{prod['precio']:.2f} · "
            f"{prod['segmento']}",
            expanded=False,
        ):
            st.caption(
                f"Proveedor: {prod['proveedor']} · "
                f"Tipo: {prod['tipo_producto']} · "
                f"Margen: {prod['tipo_producto2']}"
                + (f" · Cotizar: {prod['para_cotizar']}" if not es_antigua else "")
            )

            col_e, col_d = st.columns(2)
            with col_e:
                if st.button("✏️ Editar", key=f"e_{lbl}_{prod['nombre']}"):
                    st.session_state[modo_key] = "editar"; st.rerun()
            with col_d:
                if st.button("🗑️ Eliminar", key=f"d_{lbl}_{prod['nombre']}",
                             type="secondary"):
                    st.session_state[modo_key] = "confirmar"; st.rerun()

            if st.session_state[modo_key] == "editar":
                st.divider()
                datos = _form_producto(prefill=prod,
                                       key_prefix=f"edit_{lbl}_{prod['nombre']}",
                                       es_antigua=es_antigua)
                if datos:
                    with st.spinner("Guardando..."):
                        editar_producto(prod["row_num"], datos, es_antigua)
                    st.success("✅ Producto actualizado.")
                    st.session_state[modo_key] = "ver"; st.rerun()

            if st.session_state[modo_key] == "confirmar":
                st.error(f"⚠️ ¿Eliminar **{prod['nombre']}**? No se puede deshacer.")
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("✅ Sí, eliminar",
                                 key=f"confirm_d_{lbl}_{prod['nombre']}", type="primary"):
                        with st.spinner("Eliminando..."):
                            eliminar_producto(prod["row_num"], es_antigua)
                        st.success("Producto eliminado.")
                        st.session_state[modo_key] = "ver"; st.rerun()
                with cc2:
                    if st.button("❌ Cancelar", key=f"cancel_d_{lbl}_{prod['nombre']}"):
                        st.session_state[modo_key] = "ver"; st.rerun()


def mostrar():
    st.markdown("## 📦 Productos")

    tab_general, tab_antigua, tab_nuevo_g, tab_nuevo_a = st.tabs([
        "📋 Lista General",
        "🔖 Lista Antigua",
        "➕ Nuevo (General)",
        "➕ Nuevo (Antigua)",
    ])

    with tab_general:
        _mostrar_lista(es_antigua=False)

    with tab_antigua:
        st.caption("Precios especiales para clientes de Antigua (L03)")
        _mostrar_lista(es_antigua=True)

    with tab_nuevo_g:
        st.markdown("#### Agregar producto a la lista general")
        datos = _form_producto(key_prefix="nuevo_g", es_antigua=False)
        if datos:
            with st.spinner("Guardando..."):
                agregar_producto(datos, es_antigua=False)
            st.success(f"✅ **{datos['nombre']}** agregado a la lista general.")

    with tab_nuevo_a:
        st.markdown("#### Agregar producto a la lista Antigua")
        st.caption("Ingresá el mismo nombre exacto que en la lista general para que los VLOOKUP funcionen.")
        datos = _form_producto(key_prefix="nuevo_a", es_antigua=True)
        if datos:
            with st.spinner("Guardando..."):
                agregar_producto(datos, es_antigua=True)
            st.success(f"✅ **{datos['nombre']}** agregado a la lista Antigua.")
