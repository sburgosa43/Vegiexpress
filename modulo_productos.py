"""
modulo_productos.py — Gestión del catálogo de productos
Tabs: Nuevo General | Nuevo Antigua | Actualización General |
      Actualización Antigua | Precios General | Precios Antigua
"""
import streamlit as st

def _conf(key: str, msg: str):
    """Guarda mensaje de confirmación para mostrar en el próximo render."""
    st.session_state[f"_conf_{key}"] = msg

def _show_conf(key: str):
    """Muestra y consume el mensaje de confirmación (desaparece en siguiente acción)."""
    msg = st.session_state.pop(f"_conf_{key}", None)
    if msg:
        st.success(msg)

import pandas as pd
from excel_helper import (leer_productos_con_fila, agregar_producto,
                          editar_producto, eliminar_producto,
                          guardar_para_cotizar_batch)

UNIDADES   = ["Libra","Unidad","Manojo","Caja","Kilo","Onza","Docena","Bandeja",
               "Galon","Paquete","Penca","Red","lbs","libra","1 Onza","4 Onzas",
               "6 Onzas","8 Onzas","12 Onzas","16 Onzas","32 Onzas","Gramo",
               "250 gr","500 gr","1 Kilo","2 Kilos","5 Kilos"]
SEGMENTOS  = ["Vegetales","Frutas","Hierbas","Congelados","Especias","Flores","Otros"]
TIPOS_PROD = ["Fresco","Proceso","Seco","Congelado","Envasado","Otro"]
TIPOS_P2   = ["Premium","Alto","Media Alta","Media","Media Baja","Baja","Sin Segmento"]
def _proveedores():
    try:
        from data_helper import get_proveedores
        return get_proveedores()
    except Exception:
        return ["CENMA","Patojas","El Huerto","Productor Directo",
                "Importado","Otro","Sin Proveedor"]
COTIZAR_OPC= ["","Si","No"]

SEGS_PCT   = {"Premium":50,"Alto":40,"Media Alta":35,"Media":30,
              "Media Baja":25,"Baja":20,"Sin Segmento":0}


# ── Columnas fijas para todas las tablas ──────────────────────────────────────
COL_CFG_LISTA = {
    "Producto":     st.column_config.TextColumn("Producto",      disabled=True, width="medium"),
    "Unidad":       st.column_config.TextColumn("Unidad",        disabled=True, width="small"),
    "Costo":        st.column_config.NumberColumn("Costo",       disabled=True,
                     format="Q%.2f", width="small"),
    "Precio":       st.column_config.NumberColumn("Precio",      disabled=True,
                     format="Q%.2f", width="small"),
    "P.Equilibrio": st.column_config.NumberColumn("P.Equilibrio",disabled=True,
                     format="Q%.2f", width="small"),
    "En Catálogo":  st.column_config.CheckboxColumn("En Catálogo ✅", width="small"),
}


def _ref_precios(costo: float, tipo2: str):
    """Muestra referencia de P.Equilibrio y Precio Impuestos calculados."""
    seg_pct = SEGS_PCT.get(tipo2, 0) / 100
    pto_eq  = round(costo * 1.12, 2) if costo > 0 else 0
    p_imp   = round(costo / (1 - seg_pct / 0.95) * 1.12, 2) \
              if (costo > 0 and seg_pct > 0) else 0
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
        f"<b>P. con Impuestos:</b> {'Q'+f'{p_imp:,.2f}' if p_imp else '—'}<br>"
        f"<span style='color:#888;font-size:.72rem'>"
        f"{'Margen '+str(int(seg_pct*100))+'%' if p_imp else 'Seleccioná segmento'}</span>"
        f"</div>", unsafe_allow_html=True)


def _form_producto(prefill: dict = None, key_prefix: str = "new",
                   es_antigua: bool = False) -> dict | None:
    pf = prefill or {}
    kp = key_prefix   # keys explicitos: evita contaminacion de estado entre productos
    with st.form(key=f"form_prod_{kp}"):
        col1, col2 = st.columns(2)
        with col1:
            nombre = st.text_input("Producto *", value=pf.get("nombre",""),
                                    key=f"{kp}_nombre")
            unidad = st.selectbox("Unidad de venta", UNIDADES,
                index=UNIDADES.index(pf["unidad"]) if pf.get("unidad") in UNIDADES else 0,
                key=f"{kp}_unidad")
            segmento = st.selectbox("Segmento", SEGMENTOS,
                index=SEGMENTOS.index(pf["segmento"]) if pf.get("segmento") in SEGMENTOS else 0,
                key=f"{kp}_segmento")
            unidad_despacho = st.number_input("Unidad despacho",
                value=int(pf.get("unidad_despacho", 1)), min_value=1,
                key=f"{kp}_udesp")
            proveedor = st.selectbox("Proveedor", _proveedores(),
                index=_proveedores().index(pf["proveedor"]) if pf.get("proveedor") in _proveedores() else 0,
                key=f"{kp}_prov")
        with col2:
            tipo2 = st.selectbox("Segmentación de margen", TIPOS_P2,
                index=TIPOS_P2.index(pf["tipo_producto2"]) if pf.get("tipo_producto2") in TIPOS_P2 else 3,
                key=f"{kp}_tipo2")
            costo  = st.number_input("Costo (Q)", value=float(pf.get("costo", 0)),
                                      min_value=0.0, step=0.5, key=f"{kp}_costo")
            _ref_precios(costo, tipo2)
            precio = st.number_input("Precio (Q)", value=float(pf.get("precio", 0)),
                                      min_value=0.0, step=0.5, key=f"{kp}_precio")
            pesos  = st.number_input("Pesos/Costo referencia",
                                      value=float(pf.get("pesos", 0)),
                                      min_value=0.0, step=0.1, key=f"{kp}_pesos")
            if not es_antigua:
                tipo1    = st.selectbox("Tipo de producto", TIPOS_PROD,
                    index=TIPOS_PROD.index(pf["tipo_producto"]) if pf.get("tipo_producto") in TIPOS_PROD else 0,
                    key=f"{kp}_tipo1")
                cotizar  = st.selectbox("Para cotizar", COTIZAR_OPC,
                    index=COTIZAR_OPC.index(pf["para_cotizar"]) if pf.get("para_cotizar") in COTIZAR_OPC else 0,
                    key=f"{kp}_cotizar")
                parent   = st.text_input("Parent", value=pf.get("parent", pf.get("nombre","")),
                                          key=f"{kp}_parent")
                comentario=st.text_input("Comentario", value=pf.get("comentario",""),
                                          key=f"{kp}_coment")
            else:
                tipo1 = "Fresco"; cotizar = ""; parent = ""; comentario = ""

        submitted = st.form_submit_button("💾 Guardar", type="primary")
        if submitted:
            if not nombre.strip():
                st.error("El nombre del producto es obligatorio."); return None
            if precio <= 0:
                st.error("El precio debe ser mayor a 0."); return None
            return {
                "nombre": nombre.strip(), "unidad": unidad,
                "segmento": segmento, "unidad_despacho": unidad_despacho,
                "costo": costo, "precio": precio, "pesos": pesos,
                "proveedor": proveedor, "tipo_producto": tipo1,
                "tipo_producto2": tipo2, "para_cotizar": cotizar,
                "parent": parent or nombre.strip(), "comentario": comentario,
            }
    return None


def _actualizar_producto(es_antigua: bool):
    """Tab Actualizacion: busca un producto y edita todos sus campos."""
    lbl      = "Antigua" if es_antigua else "General"
    sk_busq  = f"busq_confirmada_{lbl}"
    sk_sel   = f"upd_sel_{lbl}"
    productos = leer_productos_con_fila(es_antigua=es_antigua)

    # ── Paso 1: Busqueda en form propio ───────────────────────────────────────
    # Al usar st.form aqui, presionar Enter en la busqueda NO interfiere
    # con el formulario de edicion que viene despues.
    with st.form(key=f"form_busq_{lbl}"):
        b1, b2 = st.columns([4, 1])
        txt = b1.text_input("Buscar producto",
                             placeholder="Escribi el nombre...",
                             value=st.session_state.get(sk_busq, ""))
        buscar = b2.form_submit_button("🔍 Buscar", use_container_width=True)

    if buscar:
        st.session_state[sk_busq] = txt.strip()
        st.session_state.pop(sk_sel, None)   # reset seleccion al buscar de nuevo
        st.rerun()

    busqueda = st.session_state.get(sk_busq, "")
    if not busqueda:
        st.info("Escribi el nombre del producto para buscarlo.")
        return

    filtrados = [p for p in productos if busqueda.lower() in p["nombre"].lower()]
    if not filtrados:
        st.warning(f"No se encontraron productos con '{busqueda}'.")
        return

    # ── Paso 2: Seleccion del producto ────────────────────────────────────────
    nombres = [p["nombre"] for p in filtrados]
    sel     = st.selectbox("Selecciona el producto:", nombres, key=sk_sel)
    prod    = next(p for p in filtrados if p["nombre"] == sel)

    st.caption(f"Fila {prod['row_num']} · "
               f"Costo: Q{prod['costo']:.2f} · Precio: Q{prod['precio']:.2f}")
    st.divider()

    # ── Paso 3: Formulario de edicion ─────────────────────────────────────────
    # key_prefix incluye row_num para que cada producto tenga su propio form
    datos = _form_producto(prefill=prod, key_prefix=f"upd_{prod['row_num']}",
                           es_antigua=es_antigua)
    if datos:
        with st.spinner("Guardando..."):
            editar_producto(prod["row_num"], datos, es_antigua)
        # Limpiar busqueda y estado del form para empezar de cero
        st.session_state.pop(sk_busq, None)
        st.session_state.pop(sk_sel,  None)
        _kp = f"upd_{prod['row_num']}"
        for _k in [k for k in st.session_state if k.startswith(f"{_kp}_")]:
            st.session_state.pop(_k, None)
        _conf("prod_upd", f"Producto actualizado: {datos['nombre']}")
        st.rerun()

    # ── Eliminar producto ─────────────────────────────────────────────────────
    st.divider()
    with st.expander(f"🗑️ Eliminar '{prod['nombre']}' del listado {lbl}",
                     expanded=False):
        st.error("Esta acción elimina la fila del catálogo de forma permanente. "
                 "Los pedidos históricos NO se modifican.")
        conf_del = st.checkbox(
            f"Confirmo que quiero eliminar '{prod['nombre']}'",
            key=f"del_conf_{lbl}_{prod['row_num']}")
        if st.button("🗑️ Eliminar producto", type="secondary",
                     key=f"del_exec_{lbl}_{prod['row_num']}",
                     disabled=not conf_del):
            with st.spinner("Eliminando..."):
                eliminar_producto(prod["row_num"], es_antigua)
            st.session_state.pop(sk_busq, None)
            st.session_state.pop(sk_sel,  None)
            _conf("prod_upd", f"Producto eliminado: {prod['nombre']}")
            st.rerun()


def _precios_tabla(es_antigua: bool):
    """Tab Precios: tabla limpia con columnas fijas y checkbox de catálogo."""
    lbl      = "Antigua" if es_antigua else "General"
    productos = leer_productos_con_fila(es_antigua=es_antigua)

    busqueda = st.text_input(f"🔍 Filtrar", placeholder="Nombre o segmento...",
                              key=f"prec_busq_{lbl}")
    filtrados = [p for p in productos
                 if busqueda.lower() in p["nombre"].lower()
                 or busqueda.lower() in p.get("segmento","").lower()] \
                if busqueda else productos

    st.caption(f"{len(filtrados)} producto(s) · Activá ✅ para mostrar en la app de pedidos")

    df = pd.DataFrame([{
        "row_num":      p["row_num"],
        "Producto":     p["nombre"],
        "Unidad":       p["unidad"],
        "Costo":        p["costo"],
        "Precio":       p["precio"],
        "P.Equilibrio": round(p["costo"] * 1.12, 2) if p["costo"] > 0 else 0,
        "En Catálogo":  p["para_cotizar"].strip().lower() in ["si","sí","yes","1","true"],
    } for p in filtrados])

    reset_key = f"reset_prec_{lbl}"
    edited = st.data_editor(
        df.drop(columns=["row_num"]),
        column_config=COL_CFG_LISTA,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        key=f"ed_prec_{lbl}_{st.session_state.get(reset_key, 0)}",
    )

    if st.button(f"💾 Guardar cambios de catálogo",
                 type="primary", key=f"save_cat_{lbl}"):
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
            _conf("precios_upd", f"✅ Precios guardados — {len(cambios)} producto(s) actualizados.")
            st.rerun()
        else:
            st.info("Sin cambios detectados.")


def mostrar():
    _show_conf("prod_upd")
    _show_conf("precios_upd")
    st.markdown("## 📦 Productos")
    if st.button("🏠 Inicio", key="btn_home_prod", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    (tab_ng, tab_na, tab_ug, tab_ua,
     tab_pg, tab_pa) = st.tabs([
        "➕ Nuevo General",
        "➕ Nuevo Antigua",
        "✏️ Actualización General",
        "✏️ Actualización Antigua",
        "📋 Precios General",
        "📋 Precios Antigua",
    ])

    with tab_ng:
        st.markdown("#### Agregar producto — Lista General")
        datos = _form_producto(key_prefix="nuevo_g", es_antigua=False)
        if datos:
            with st.spinner("Guardando..."):
                agregar_producto(datos, es_antigua=False)
            st.success(f"✅ **{datos['nombre']}** agregado a la lista general.")

    with tab_na:
        st.markdown("#### Agregar producto — Lista Antigua")
        st.caption("Usá el mismo nombre exacto que en la lista general.")
        datos = _form_producto(key_prefix="nuevo_a", es_antigua=True)
        if datos:
            with st.spinner("Guardando..."):
                agregar_producto(datos, es_antigua=True)
            st.success(f"✅ **{datos['nombre']}** agregado a la lista Antigua.")

    with tab_ug:
        st.markdown("#### Actualizar producto — Lista General")
        _actualizar_producto(es_antigua=False)

    with tab_ua:
        st.markdown("#### Actualizar producto — Lista Antigua")
        _actualizar_producto(es_antigua=True)

    with tab_pg:
        st.markdown("#### Precios y catálogo — Lista General")
        _precios_tabla(es_antigua=False)

    with tab_pa:
        st.markdown("#### Precios y catálogo — Lista Antigua")
        _precios_tabla(es_antigua=True)
