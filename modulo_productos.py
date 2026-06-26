"""
modulo_productos.py — Gestión del catálogo de productos.
5 tabs: Nuevo Producto | Actualizar | Ver Catálogo | Listas de Precios | Validación
Antigua (legado) y Precios Antigua (legado) se mantienen para compatibilidad.
"""
import streamlit as st
import pandas as pd
from excel_helper import (leer_productos_con_fila, agregar_producto,
                          editar_producto, eliminar_producto,
                          guardar_para_cotizar_batch)
from data_helper import (cargar_productos, get_proveedores,
                         guardar_precio_especial, eliminar_precio_especial,
                         leer_precios_capa, limpiar_cache_precios)
from utils import _conf, _show_conf
UNIDADES   = ["Libra","Unidad","Manojo","Caja","Kilo","Onza","Docena","Bandeja",
               "Galon","Paquete","Penca","Red","lbs","libra","1 Onza","4 Onzas",
               "6 Onzas","8 Onzas","12 Onzas","16 Onzas","32 Onzas","Gramo",
               "250 gr","500 gr","1 Kilo","2 Kilos","5 Kilos"]
SEGMENTOS  = ["Vegetales","Frutas","Hierbas","Congelados","Especias","Flores","Otros"]
TIPOS_PROD = ["Fresco","Proceso","Seco","Congelado","Envasado","Otro"]
TIPOS_P2   = ["Premium","Alto","Media Alta","Media","Media Baja","Baja","Sin Segmento"]
COTIZAR_OPC= ["","Si","No"]

GRUPOS_LISTAS = ["Italianos","Chimaltecos","Italianos2","PorQueNo"]
ZONAS_LISTAS  = ["Antigua","Hogares"]
TODAS_CAPAS   = (["Zona " + z for z in ZONAS_LISTAS] +
                 ["Grupo " + g for g in GRUPOS_LISTAS] +
                 ["Cliente (individual)"])

def _proveedores():
    try:    return get_proveedores()
    except: return ["CENMA","Patojas","El Huerto","Productor Directo",
                    "Importado","Otro","Sin Proveedor"]

# ── Helpers de UI ─────────────────────────────────────────────────────────────
def _ref_precios(costo: float, tipo2: str):
    segs = {"Premium":50,"Alto":40,"Media Alta":35,"Media":30,
            "Media Baja":25,"Baja":20,"Sin Segmento":0}
    pct = segs.get(tipo2, 0)
    if costo > 0 and pct > 0:
        sug = round(costo / (1 - pct/100), 2)
        st.caption(f"💡 Precio sugerido ({tipo2} {pct}%): Q{sug:.2f}")

# ── Formulario base de producto ───────────────────────────────────────────────
def _form_campos(kp: str, pf: dict, es_antigua: bool = False) -> dict | None:
    """Renderiza los campos del producto dentro de un st.form ya abierto.
    Retorna dict con datos si se guardó, None si no."""
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
            index=_proveedores().index(pf["proveedor"])
                  if pf.get("proveedor") in _proveedores() else 0,
            key=f"{kp}_prov")
    with col2:
        tipo2 = st.selectbox("Segmentación de margen", TIPOS_P2,
            index=TIPOS_P2.index(pf["tipo_producto2"])
                  if pf.get("tipo_producto2") in TIPOS_P2 else 3,
            key=f"{kp}_tipo2")
        costo = st.number_input("Costo (Q)", value=float(pf.get("costo", 0)),
                                 min_value=0.0, step=0.5, key=f"{kp}_costo")
        _ref_precios(costo, tipo2)
        precio = st.number_input("Precio General (Q) *",
                                  value=float(pf.get("precio", 0)),
                                  min_value=0.0, step=0.5, key=f"{kp}_precio")
        pesos  = st.number_input("Pesos/Costo referencia",
                                  value=float(pf.get("pesos", 0)),
                                  min_value=0.0, step=0.1, key=f"{kp}_pesos")
        if not es_antigua:
            tipo1 = st.selectbox("Tipo de producto", TIPOS_PROD,
                index=TIPOS_PROD.index(pf["tipo_producto"])
                      if pf.get("tipo_producto") in TIPOS_PROD else 0,
                key=f"{kp}_tipo1")
            cotizar = st.selectbox("Para cotizar", COTIZAR_OPC,
                index=COTIZAR_OPC.index(pf["para_cotizar"])
                      if pf.get("para_cotizar") in COTIZAR_OPC else 0,
                key=f"{kp}_cotizar")
            parent = st.text_input("Parent",
                                    value=pf.get("parent", pf.get("nombre","")),
                                    key=f"{kp}_parent")
            comentario = st.text_input("Comentario", value=pf.get("comentario",""),
                                        key=f"{kp}_coment")
        else:
            tipo1 = "Fresco"; cotizar = ""; parent = ""; comentario = ""

    submitted = st.form_submit_button("💾 Guardar", type="primary")
    if submitted:
        if not nombre.strip():
            st.error("El nombre del producto es obligatorio."); return None
        if precio <= 0:
            st.error("El precio General debe ser mayor a 0."); return None
        return {"nombre": nombre.strip(), "unidad": unidad,
                "segmento": segmento, "unidad_despacho": unidad_despacho,
                "costo": costo, "precio": precio, "pesos": pesos,
                "proveedor": proveedor, "tipo_producto": tipo1,
                "tipo_producto2": tipo2, "para_cotizar": cotizar,
                "parent": parent or nombre.strip(), "comentario": comentario}
    return None


# ── TAB 1: Nuevo Producto ─────────────────────────────────────────────────────
def _tab_nuevo():
    _show_conf("nuevo_prod")
    st.markdown("#### Nuevo Producto")
    st.caption("Completá los datos básicos y marcá las zonas/grupos donde "
               "el precio difiere del General.")

    kp = "nuevo_g"
    with st.form(key=f"form_prod_{kp}"):
        datos = _form_campos(kp, {})

        st.divider()
        st.markdown("**Precios especiales (opcional)**")
        st.caption("Marcá solo donde el precio difiere del General. "
                   "El resto de zonas usará el Precio General.")

        z1, z2 = st.columns(2)
        chk_ant = z1.checkbox("Zona Antigua", key=f"{kp}_chk_ant")
        p_ant   = z1.number_input("Precio Antigua (Q)", min_value=0.0, step=0.5,
                                   key=f"{kp}_p_ant") if chk_ant else 0.0
        chk_hog = z2.checkbox("Zona Hogares", key=f"{kp}_chk_hog")
        p_hog   = z2.number_input("Precio Hogares (Q)", min_value=0.0, step=0.5,
                                   key=f"{kp}_p_hog") if chk_hog else 0.0

        g1, g2 = st.columns(2)
        chk_ital  = g1.checkbox("Grupo Italianos",   key=f"{kp}_chk_ital")
        p_ital    = g1.number_input("Precio Italianos (Q)",  min_value=0.0, step=0.5,
                                     key=f"{kp}_p_ital")  if chk_ital  else 0.0
        chk_chim  = g1.checkbox("Grupo Chimaltecos", key=f"{kp}_chk_chim")
        p_chim    = g1.number_input("Precio Chimaltecos (Q)", min_value=0.0, step=0.5,
                                     key=f"{kp}_p_chim")  if chk_chim  else 0.0
        chk_ital2 = g2.checkbox("Grupo Italianos2",  key=f"{kp}_chk_ital2")
        p_ital2   = g2.number_input("Precio Italianos2 (Q)", min_value=0.0, step=0.5,
                                     key=f"{kp}_p_ital2") if chk_ital2 else 0.0
        chk_pq    = g2.checkbox("Grupo PorQueNo",    key=f"{kp}_chk_pq")
        p_pq      = g2.number_input("Precio PorQueNo (Q)",   min_value=0.0, step=0.5,
                                     key=f"{kp}_p_pq")    if chk_pq    else 0.0

    if datos:
        with st.spinner("Guardando..."):
            agregar_producto(datos, es_antigua=False)
            nom = datos["nombre"]
            if chk_ant  and p_ant  > 0: guardar_precio_especial("precioszona",  "Antigua",     nom, p_ant)
            if chk_hog  and p_hog  > 0: guardar_precio_especial("precioszona",  "Hogares",     nom, p_hog)
            if chk_ital and p_ital > 0: guardar_precio_especial("preciosgrupo", "Italianos",   nom, p_ital)
            if chk_chim and p_chim > 0: guardar_precio_especial("preciosgrupo", "Chimaltecos", nom, p_chim)
            if chk_ital2 and p_ital2 > 0: guardar_precio_especial("preciosgrupo","Italianos2", nom, p_ital2)
            if chk_pq   and p_pq   > 0: guardar_precio_especial("preciosgrupo", "PorQueNo",    nom, p_pq)
            limpiar_cache_precios()
        _conf("nuevo_prod", f"✅ {datos['nombre']} creado correctamente.")
        st.rerun()


# ── TAB 2: Actualizar Producto ────────────────────────────────────────────────
@st.fragment
def _tab_actualizar(es_antigua: bool = False):
    """
    Editor de precios/costos con st.form.
    Dentro de un form NO hay reruns mientras el usuario edita,
    por lo que es imposible que los valores se reseteen.
    Solo al presionar "Guardar" se ejecuta el submit y se procesan cambios.
    """
    lbl = "Antigua" if es_antigua else "General"
    _show_conf("prod_upd")

    todos = leer_productos_con_fila(es_antigua=es_antigua)

    # ── Filtros FUERA del form (pueden cambiar sin afectar el form) ───────────
    f1, f2, f3 = st.columns(3)
    txt_f  = f1.text_input("Buscar", placeholder="nombre...",
                            key=f"upd_txt_{lbl}", label_visibility="collapsed")
    seg_f  = f2.selectbox("Segmento", ["Todos"] +
                           sorted({p.get("segmento","") for p in todos if p.get("segmento","")}),
                           key=f"upd_seg_{lbl}")
    prov_f = f3.selectbox("Proveedor", ["Todos"] +
                           sorted({p.get("proveedor","") for p in todos if p.get("proveedor","")}),
                           key=f"upd_prov_{lbl}")

    filtrados = [p for p in todos
                 if (not txt_f or txt_f.lower() in p["nombre"].lower())
                 and (seg_f  == "Todos" or p.get("segmento","")  == seg_f)
                 and (prov_f == "Todos" or p.get("proveedor","") == prov_f)]

    st.caption(f"{len(filtrados)} de {len(todos)} productos  ·  "
               "Editá los valores y presioná **Guardar** al terminar.")

    if not filtrados:
        st.info("Sin productos con esos filtros.")
        return

    # ── Margen neto: (1-ISR) * (precio - costo*(1+IVA)) / precio * 100 ─────────
    IVA, ISR = 0.12, 0.05
    def _mg(costo, precio):
        if precio <= 0: return 0.0
        return (1 - ISR) * (precio - costo * (1 + IVA)) / precio * 100

    def _mg_badge(mg):
        b = "🟢" if mg >= 35 else ("🟡" if mg >= 20 else "🔴")
        return f"{b} {mg:.1f}%"

    # ── FORM: ningún widget dispara rerun hasta el submit ────────────────────
    # value=ps funciona correctamente dentro de un form porque no hay reruns
    # intermedios que puedan resetear el widget al valor original.
    # Margen actual se muestra como referencia — el delta se calcula al guardar.
    COL_W = [2.8, 1.1, 1.5, 1.1, 1.5, 1.4]
    with st.form(key=f"form_precios_{lbl}"):
        h = st.columns(COL_W)
        for col, txt in zip(h, ["**Producto**", "**Precio act**", "**Precio nuevo**",
                                  "**Costo act**", "**Costo nuevo**", "**Margen act**"]):
            col.markdown(txt)
        st.divider()

        inputs = {}
        for p in filtrados:
            ps  = float(p.get("precio") or 0)
            cs  = float(p.get("costo")  or 0)
            mg  = _mg(cs, ps)
            row = st.columns(COL_W)
            row[0].write(p["nombre"])
            row[1].markdown(f"<small>Q {ps:.2f}</small>", unsafe_allow_html=True)
            row[3].markdown(f"<small>Q {cs:.2f}</small>", unsafe_allow_html=True)
            row[5].markdown(f"<small>{_mg_badge(mg)}</small>", unsafe_allow_html=True)
            p_nuevo = row[2].number_input(
                "", value=ps, min_value=0.0, step=0.25, format="%.2f",
                key=f"fp_{lbl}_{p['row_num']}", label_visibility="collapsed")
            c_nuevo = row[4].number_input(
                "", value=cs, min_value=0.0, step=0.25, format="%.2f",
                key=f"fc_{lbl}_{p['row_num']}", label_visibility="collapsed")
            inputs[p["row_num"]] = (p, p_nuevo, c_nuevo, ps, cs)

        st.divider()
        from datetime import date as _d
        _sem = _d.today().isocalendar()[1]
        _año = _d.today().year
        upd_peds = st.checkbox(
            f"📅 Aplicar también a pedidos de la semana {_sem}/{_año}",
            value=True, key=f"upd_peds_chk_{lbl}")

        submitted = st.form_submit_button(
            "💾 Guardar cambios", type="primary", use_container_width=True)

    # ── Procesar submit (fuera del with form) ─────────────────────────────────
    if submitted:
        cambios = [
            (p, c_nuevo, p_nuevo, ps, cs)
            for rn, (p, p_nuevo, c_nuevo, ps, cs) in inputs.items()
            if abs(p_nuevo - ps) > 0.001 or abs(c_nuevo - cs) > 0.001
        ]
        if not cambios:
            st.info("Sin cambios detectados.")
        else:
            # Mostrar preview de margen ANTES de guardar
            n = len(cambios)
            for p, c_new, p_new, cs_orig, ps_orig in cambios:
                mg_old = _mg(cs_orig, ps_orig)
                mg_new = _mg(c_new,   p_new)
                delta  = mg_new - mg_old
                arrow  = ("↑" if delta > 0.05 else ("↓" if delta < -0.05 else "→"))
                color  = ("green" if delta > 0.05 else ("red" if delta < -0.05 else "gray"))
                st.markdown(
                    f"<small>**{p['nombre']}** — "
                    f"Precio: Q{ps_orig:.2f}→Q{p_new:.2f} · "
                    f"Costo: Q{cs_orig:.2f}→Q{c_new:.2f} · "
                    f"Margen: {_mg_badge(mg_old)} "
                    f"<span style='color:{color}'>{arrow} {mg_new:.1f}% "
                    f"({'+' if delta>=0 else ''}{delta:.1f}pp)</span></small>",
                    unsafe_allow_html=True)
            st.divider()
            for p, c_new, p_new, cs_orig, ps_orig in cambios:
                with st.spinner(f"Guardando {p['nombre']}..."):
                    editar_producto(p["row_num"],
                                    {**p, "costo": c_new, "precio": p_new},
                                    es_antigua)
                if abs(c_new - cs_orig) > 0.001:
                    _cascade_parent(p["nombre"], c_new, todos)

            extra = ""
            if upd_peds:
                from excel_helper import actualizar_precio_semana
                cambios_sem = [{
                    "producto":    p["nombre"],
                    "precio_nuevo": p_new,  "precio_ant":   ps_orig,
                    "costo_nuevo":  c_new,  "costo_ant":    cs_orig,
                    "p_cambia": abs(p_new - ps_orig) > 0.001,
                    "c_cambia": abs(c_new - cs_orig) > 0.001,
                } for p, c_new, p_new, cs_orig, ps_orig in cambios]
                with st.spinner(f"Actualizando pedidos semana {_sem}/{_año}..."):
                    res = actualizar_precio_semana(
                        cambios_sem, _sem, _año, actualizar_catalogo=False)
                extra = f" · {res['filas_pedidos']} fila(s) de pedidos actualizadas"

            _conf("prod_upd", f"✅ {n} producto(s) actualizados{extra}.")
            st.rerun(scope="app")

    # ── Edición completa ──────────────────────────────────────────────────────
    st.divider()
    with st.expander("✏️ Edición completa — nombre, proveedor, unidad, parent...",
                     expanded=False):
        sk_busq = f"busq_completa_{lbl}"
        sk_sel  = f"sel_completa_{lbl}"
        with st.form(key=f"form_busq_completa_{lbl}"):
            b1, b2 = st.columns([4,1])
            txt = b1.text_input("Buscar producto", placeholder="Escribí el nombre...",
                                 value=st.session_state.get(sk_busq,""))
            buscar = b2.form_submit_button("🔍 Buscar", use_container_width=True)
        if buscar:
            st.session_state[sk_busq] = txt.strip()
            st.session_state.pop(sk_sel, None)
            st.rerun()
        busqueda = st.session_state.get(sk_busq, "")
        if not busqueda:
            st.info("Escribí el nombre para buscarlo.")
        else:
            matches = [p for p in todos if busqueda.lower() in p["nombre"].lower()]
            if not matches:
                st.warning(f"No se encontraron productos con '{busqueda}'.")
            else:
                nombres = [p["nombre"] for p in matches]
                sel     = st.selectbox("Seleccioná:", nombres, key=sk_sel)
                prod    = next(p for p in matches if p["nombre"] == sel)
                _mostrar_info_precios(prod["nombre"])
                kp = f"upd_comp_{prod['row_num']}"
                with st.form(key=f"form_comp_{kp}"):
                    datos = _form_campos(kp, prod, es_antigua=es_antigua)
                if datos:
                    costo_cambio = abs(float(datos.get("costo",0))
                                       - float(prod.get("costo",0))) > 0.001
                    with st.spinner("Guardando..."):
                        editar_producto(prod["row_num"], datos, es_antigua)
                    if costo_cambio:
                        _cascade_parent(datos["nombre"], float(datos["costo"]), todos)
                    _conf("prod_upd", f"Producto actualizado: {datos['nombre']}")
                    st.rerun()


def _mostrar_info_precios(nombre_prod: str):
    """Muestra precios especiales existentes para el producto (solo lectura)."""
    info = []
    for hoja, listas in [("precioszona", ZONAS_LISTAS),
                          ("preciosgrupo", GRUPOS_LISTAS)]:
        for lista in listas:
            filas = leer_precios_capa(hoja, lista)
            match = next((f for f in filas
                          if f["producto"].lower() == nombre_prod.lower()), None)
            if match:
                info.append(f"**{lista}:** Q{match['precio']:.2f}")
    if info:
        with st.expander(f"💰 Precios especiales ({len(info)} lista(s))", expanded=False):
            for i in info: st.write(f"  · {i}")
            st.caption("Para editar, ir a 🏷️ Listas de Precios.")


def _cascade_parent(nombre: str, costo_nuevo: float, todos: list):
    """Detecta hijos y permite actualizar su costo en el acto."""
    hijos = [p for p in todos
             if p.get("parent","").strip().lower() == nombre.strip().lower()
             and p["nombre"].strip().lower() != nombre.strip().lower()]
    if not hijos: return

    st.warning(f"⚠️ **{nombre}** tiene {len(hijos)} producto(s) hijo(s). "
               f"Definí el costo de cada uno (no es proporcional — puede incluir "
               f"empaque u otros) o cerrá para hacerlo después.")

    with st.form(key=f"cascade_{nombre.replace(' ','_')}"):
        costos_hijos = {}
        for h in hijos:
            c1, c2 = st.columns([3, 1])
            c1.write(f"**{h['nombre']}** (costo actual: Q{h['costo']:.2f})")
            costos_hijos[h["row_num"]] = c2.number_input(
                "Nuevo costo Q", value=float(h["costo"]),
                min_value=0.0, step=0.5,
                key=f"cas_{h['row_num']}")

        c_ap, c_sk = st.columns(2)
        aplicar = c_ap.form_submit_button("Aplicar a hijos", type="primary")
        c_sk.form_submit_button("Omitir por ahora", type="secondary")

    if aplicar:
        with st.spinner("Actualizando hijos..."):
            for h in hijos:
                nuevo_c = costos_hijos[h["row_num"]]
                editar_producto(h["row_num"], {**h, "costo": nuevo_c},
                                es_antigua=False)
        st.success(f"Costos de {len(hijos)} hijo(s) actualizados.")


# ── TAB 3: Ver Catálogo ───────────────────────────────────────────────────────
def _tab_catalogo():
    st.markdown("#### Catálogo General (solo lectura)")
    prods = leer_productos_con_fila(es_antigua=False)
    if not prods:
        st.info("Sin productos en el catálogo.")
        return

    filtro = st.text_input("Filtrar", placeholder="nombre, segmento...",
                            label_visibility="collapsed", key="cat_filtro")
    if filtro:
        prods = [p for p in prods if filtro.lower() in p["nombre"].lower()
                 or filtro.lower() in p.get("segmento","").lower()]

    df = pd.DataFrame([{
        "Producto":  p["nombre"],
        "Unidad":    p["unidad"],
        "Segmento":  p["segmento"],
        "Costo Q":   p["costo"],
        "Precio Q":  p["precio"],
        "Proveedor": p.get("proveedor",""),
        "Parent":    p.get("parent",""),
    } for p in prods])
    st.dataframe(df, hide_index=True, use_container_width=True,
                 height=min(600, 60+len(df)*35))
    st.caption(f"{len(df)} productos")


# ── TAB 4: Listas de Precios ──────────────────────────────────────────────────
def _tab_listas():
    st.markdown("#### Listas de Precios Especiales")
    st.caption("Precio General al lado del especial para comparar. "
               "Los productos sin fila en esta lista usan el precio General.")

    capa = st.selectbox("Capa a editar", TODAS_CAPAS, key="lp_capa")
    if capa.startswith("Zona "):
        hoja, lista = "precioszona",  capa.replace("Zona ","")
    elif capa.startswith("Grupo "):
        hoja, lista = "preciosgrupo", capa.replace("Grupo ","")
    else:
        hoja, lista = "preciosclient", ""
        st.info("La lista de clientes individuales está vacía por ahora. "
                "Podés agregar un cliente escribiendo su nombre exacto.")

    # Mapa completo: nombre → {precio, unidad}
    gen_prods  = leer_productos_con_fila(es_antigua=False)
    gen_map    = {p["nombre"].lower(): p for p in gen_prods}
    gen_names  = [p["nombre"] for p in gen_prods]
    # Opciones de selectbox con unidad visible
    gen_opts   = ["—"] + [f"{p['nombre']}  ({p['unidad']})" for p in gen_prods]
    gen_nombre_de_opt = {f"{p['nombre']}  ({p['unidad']})": p["nombre"]
                         for p in gen_prods}

    filas = leer_precios_capa(hoja, lista)

    if filas:
        st.markdown(f"**{lista}** — {len(filas)} producto(s) con precio especial")
        # Cabecera de columnas
        hh1, hh2, hh3, hh4, hh5 = st.columns([2.8, 1, 1.2, 1.2, 0.8])
        hh1.caption("Producto");  hh2.caption("Unidad")
        hh3.caption("General Q"); hh4.caption("Precio lista")
        for f in filas:
            pi      = gen_map.get(f["producto"].lower(), {})
            gen_ref = float(pi.get("precio", 0) or 0)
            unidad  = pi.get("unidad", "—")
            c1, c2, c3, c4, c5 = st.columns([2.8, 1, 1.2, 1.2, 0.8])
            c1.write(f["producto"])
            c2.caption(unidad)
            c3.caption(f"Q{gen_ref:.2f}" if gen_ref else "⚠️")
            nuevo_p = c4.number_input("Q", value=float(f["precio"]),
                                       min_value=0.0, step=0.5,
                                       label_visibility="collapsed",
                                       key=f"lp_{lista}_{f['producto']}")
            col_save, col_del = c5.columns(2)
            if col_save.button("💾", key=f"lp_s_{lista}_{f['producto']}",
                               help="Guardar"):
                guardar_precio_especial(hoja, lista, f["producto"], nuevo_p)
                limpiar_cache_precios()
                st.success(f"Q{nuevo_p:.2f} guardado para {f['producto']}.")
                st.rerun()
            if col_del.button("🗑️", key=f"lp_d_{lista}_{f['producto']}",
                              help="Quitar de esta lista"):
                eliminar_precio_especial(hoja, lista, f["producto"])
                limpiar_cache_precios()
                st.rerun()
    else:
        st.info(f"Sin precios especiales en {lista} todavía.")

    st.divider()
    st.markdown("**Agregar producto a esta lista**")
    a1, a2, a3 = st.columns([3.5, 1.5, 1])
    opt_add    = a1.selectbox("Producto (unidad)", gen_opts, key="lp_add_prod")
    prod_add   = gen_nombre_de_opt.get(opt_add, "")
    # Mostrar precio General como referencia al seleccionar
    if prod_add:
        _pi = gen_map.get(prod_add.lower(), {})
        a1.caption(f"Unidad: {_pi.get('unidad','—')} · "
                   f"Precio General: Q{float(_pi.get('precio',0)):.2f}")
    precio_add = a2.number_input("Precio Q", min_value=0.0, step=0.5,
                                  key="lp_add_precio")
    if a3.button("➕ Agregar", key="lp_add_btn"):
        if not prod_add:
            st.warning("Seleccioná un producto.")
        elif precio_add <= 0:
            st.warning("El precio debe ser mayor a 0.")
        else:
            guardar_precio_especial(hoja, lista, prod_add, precio_add)
            limpiar_cache_precios()
            st.success(f"'{prod_add}' ({gen_map.get(prod_add.lower(),{}).get('unidad','')}) "
                       f"agregado a {lista} con Q{precio_add:.2f}.")
            st.rerun()


# ── TAB 5: Validación (ya existía) ────────────────────────────────────────────
def _tab_validacion():
    import unicodedata
    from collections import defaultdict

    st.markdown("#### Validación de Catálogo")
    st.caption("Detecta nombres similares, productos sin proveedor/costo, "
               "y precios en zona/grupo apuntando a productos inexistentes.")

    prods_gen = leer_productos_con_fila(es_antigua=False)
    prods_ant = leer_productos_con_fila(es_antigua=True)

    def _norm(s):
        s = unicodedata.normalize("NFKD",str(s or "")).encode("ascii","ignore").decode()
        return " ".join(s.lower().split())

    st.markdown("##### Nombres similares en General")
    grupos = defaultdict(list)
    for p in prods_gen: grupos[_norm(p["nombre"])].append(p["nombre"])
    dups = {k:v for k,v in grupos.items() if len(set(v))>1}
    if dups:
        for _, variantes in dups.items():
            st.warning(f"⚠️ Posible duplicado: {' | '.join(sorted(set(variantes)))}")
    else:
        st.success("Sin nombres similares en General.")

    st.markdown("##### Productos de Antigua sin coincidencia exacta en General")
    nombres_gen      = {p["nombre"] for p in prods_gen}
    nombres_gen_norm = {_norm(p["nombre"]): p["nombre"] for p in prods_gen}
    mismatches = []
    for p in prods_ant:
        if p["nombre"] not in nombres_gen:
            mismatches.append((p["nombre"], nombres_gen_norm.get(_norm(p["nombre"]))))
    if mismatches:
        for n, sug in mismatches[:30]:
            if sug: st.warning(f"⚠️ Antigua: \"{n}\" → ¿debería ser \"{sug}\"?")
            else:   st.info(f"ℹ️ Antigua: \"{n}\" sin equivalente en General")
    else:
        st.success("Todos los productos de Antigua existen en General.")

    st.markdown("##### Productos sin proveedor o sin costo")
    sin_prov  = [p["nombre"] for p in prods_gen if not p.get("proveedor","").strip()]
    sin_costo = [p["nombre"] for p in prods_gen
                 if not p.get("costo") or float(p.get("costo",0))<=0]
    if sin_prov:
        with st.expander(f"⚠️ {len(sin_prov)} sin proveedor", expanded=False):
            for n in sin_prov: st.write(f"  · {n}")
    if sin_costo:
        with st.expander(f"⚠️ {len(sin_costo)} sin costo", expanded=False):
            for n in sin_costo: st.write(f"  · {n}")
    if not sin_prov and not sin_costo:
        st.success("Todos los productos tienen proveedor y costo.")

    st.markdown("##### Tablas de Precios vs Catálogo General")
    try:
        from gsheets import ws as _ws
        for hoja_nombre in ["PreciosZona","PreciosGrupo","PreciosCliente"]:
            try:
                rows = _ws(hoja_nombre.lower()).get_all_values()[1:]
            except Exception:
                continue
            huerfanos = []
            for r in rows:
                if len(r) < 2: continue
                prod = r[1].strip()
                if prod and prod not in nombres_gen:
                    sug = nombres_gen_norm.get(_norm(prod))
                    huerfanos.append((r[0], prod, sug))
            if huerfanos:
                with st.expander(f"⚠️ {hoja_nombre}: {len(huerfanos)} producto(s) "
                                  f"inexistentes en General", expanded=True):
                    for lista, p, sug in huerfanos[:20]:
                        msg = f"  · [{lista}] \"{p}\""
                        if sug: msg += f" → ¿{sug}?"
                        st.write(msg)
            else:
                st.success(f"{hoja_nombre}: todas las filas son válidas.")
    except Exception as e:
        st.info(f"Hojas de precios especiales no disponibles ({e}).")


# ── MOSTRAR ────────────────────────────────────────────────────────────────────
def mostrar():
    _show_conf("nuevo_prod")
    st.markdown("## 📦 Productos")
    if st.button("Inicio", key="btn_home_prod", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    tab_np, tab_upd, tab_cat, tab_lp, tab_val = st.tabs([
        "➕ Nuevo Producto",
        "✏️ Actualizar Producto",
        "📋 Ver Catálogo",
        "🏷️ Listas de Precios",
        "🔍 Validación",
    ])
    with tab_np:  _tab_nuevo()
    with tab_upd: _tab_actualizar(es_antigua=False)
    with tab_cat: _tab_catalogo()
    with tab_lp:  _tab_listas()
    with tab_val: _tab_validacion()
