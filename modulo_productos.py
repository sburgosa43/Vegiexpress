"""
modulo_productos.py — CRUD de productos (lista normal y lista Antigua)
"""
import streamlit as st
from excel_helper import (leer_productos_con_fila, agregar_producto,
                          editar_producto, eliminar_producto,
                          guardar_para_cotizar_batch)

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
            tipo2 = st.selectbox(
                "Segmentación de margen",
                TIPOS_P2,
                index=TIPOS_P2.index(pf["tipo_producto2"]) if pf.get("tipo_producto2") in TIPOS_P2 else 3,
            )
            costo  = st.number_input("Costo (Q)", value=float(pf.get("costo",0)), min_value=0.0, step=0.5)

            # Referencia de precios calculada en tiempo real
            SEGS = {"Premium":50,"Alto":40,"Media Alta":35,"Media":30,
                    "Media Baja":25,"Baja":20,"Sin Segmento":0}
            seg_pct = SEGS.get(tipo2, 0) / 100
            pto_eq  = round(costo * 1.12, 2) if costo > 0 else 0
            p_imp   = round(costo/(1-seg_pct/0.95)*1.12, 2) if (costo>0 and seg_pct>0) else 0
            ri1, ri2 = st.columns(2)
            ri1.markdown(
                f"<div style='background:#f0f8f0;border-radius:6px;"
                f"padding:6px 10px;font-size:.82rem;margin-bottom:6px'>"
                f"<b>Pto. Equilibrio:</b> {'Q'+f'{pto_eq:,.2f}' if pto_eq else '—'}<br>"
                f"<span style='color:#888;font-size:.72rem'>Costo × 1.12</span>"
                f"</div>", unsafe_allow_html=True)
            ri2.markdown(
                f"<div style='background:#f0f8f0;border-radius:6px;"
                f"padding:6px 10px;font-size:.82rem;margin-bottom:6px'>"
                f"<b>P. Impuestos:</b> {'Q'+f'{p_imp:,.2f}' if p_imp else '—'}<br>"
                f"<span style='color:#888;font-size:.72rem'>"
                f"{'Margen '+str(int(seg_pct*100))+'%' if p_imp else 'Seleccioná segmento'}</span>"
                f"</div>", unsafe_allow_html=True)

            precio = st.number_input("Precio (Q)", value=float(pf.get("precio",0)), min_value=0.0, step=0.5)
            pesos  = st.number_input("Pesos/Costo referencia",
                                      value=float(pf.get("pesos",0)), min_value=0.0, step=0.1)

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
    import pandas as pd
    lbl = "Antigua" if es_antigua else "General"
    productos = leer_productos_con_fila(es_antigua=es_antigua)

    busqueda = st.text_input(f"🔍 Buscar en lista {lbl}",
                              placeholder="Nombre o segmento...",
                              key=f"busq_prod_{lbl}")
    filtrados = [p for p in productos
                 if busqueda.lower() in p["nombre"].lower()
                 or busqueda.lower() in p["segmento"].lower()] \
                if busqueda else productos

    # ── Tabla con checkbox Para Cotizar ──────────────────────────────────────
    st.markdown(f"**{len(filtrados)} productos** · "
                f"Activá el ✅ para que aparezca en el catálogo de clientes:")

    df = pd.DataFrame([{
        "row_num":       p["row_num"],
        "Producto":      p["nombre"],
        "Unidad":        p["unidad"],
        "Tipo":          p["tipo_producto"],
        "Costo":         p["costo"],
        "Precio":        p["precio"],
        "En Catálogo":   p["para_cotizar"].strip().lower() in ["si","sí","yes","1","true"],
    } for p in filtrados])

    reset_key = f"reset_lista_{lbl}"
    edited = st.data_editor(
        df.drop(columns=["row_num"]),
        column_config={
            "Producto":    st.column_config.TextColumn("Producto",    disabled=True, width="large"),
            "Unidad":      st.column_config.TextColumn("Unidad",      disabled=True, width="small"),
            "Tipo":        st.column_config.TextColumn("Tipo",        disabled=True, width="medium"),
            "Costo":       st.column_config.NumberColumn("Costo",     disabled=True, format="Q%.2f", width="small"),
            "Precio":      st.column_config.NumberColumn("Precio",    disabled=True, format="Q%.2f", width="small"),
            "En Catálogo": st.column_config.CheckboxColumn("En Catálogo ✅", width="small"),
        },
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        key=f"ed_lista_{lbl}_{st.session_state.get(reset_key, 0)}",
    )

    if st.button(f"💾 Guardar cambios de catálogo ({lbl})",
                 type="primary", key=f"save_cotizar_{lbl}"):
        cambios = {}
        for i, (_, row_ed) in enumerate(edited.iterrows()):
            if i < len(df):
                rn  = int(df.iloc[i]["row_num"])
                val = bool(row_ed["En Catálogo"])
                if val != df.iloc[i]["En Catálogo"]:
                    cambios[rn] = val
        if cambios:
            with st.spinner(f"Guardando {len(cambios)} cambio(s)..."):
                guardar_para_cotizar_batch(cambios, es_antigua)
            st.session_state[reset_key] = st.session_state.get(reset_key, 0) + 1
            st.success(f"✅ {len(cambios)} producto(s) actualizados en catálogo.")
            st.rerun()
        else:
            st.info("Sin cambios detectados.")

    st.divider()
    st.markdown(f"**{len(filtrados)} productos**")

    # Mostrar en tabla compacta con acciones
    for idx, prod in enumerate(filtrados):
        # Key única: índice + lbl para evitar duplicados por nombre igual
        uid      = f"{lbl}_{idx}"
        modo_key = f"modo_prod_{uid}"
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
                if st.button("✏️ Editar", key=f"e_{uid}"):
                    st.session_state[modo_key] = "editar"; st.rerun()
            with col_d:
                if st.button("🗑️ Eliminar", key=f"d_{uid}", type="secondary"):
                    st.session_state[modo_key] = "confirmar"; st.rerun()

            if st.session_state[modo_key] == "editar":
                st.divider()
                datos = _form_producto(prefill=prod,
                                       key_prefix=f"edit_{uid}",
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
                    if st.button("✅ Sí, eliminar", key=f"yes_{uid}", type="primary"):
                        with st.spinner("Eliminando..."):
                            eliminar_producto(prod["row_num"], es_antigua)
                        st.success("Producto eliminado.")
                        st.session_state[modo_key] = "ver"; st.rerun()
                with cc2:
                    if st.button("❌ Cancelar", key=f"no_{uid}"):
                        st.session_state[modo_key] = "ver"; st.rerun()


def mostrar():
    st.markdown("## 📦 Productos")
    # Botón de regreso al Inicio
    if st.button("🏠 Inicio", key="btn_home_prod", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()


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
