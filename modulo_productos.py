"""
modulo_productos.py — Gestión del catálogo de productos.
5 tabs: Nuevo Producto | Actualizar | Ver Catálogo | Listas de Precios | Validación
Antigua (legado) y Precios Antigua (legado) se mantienen para compatibilidad.
"""
import streamlit as st
import pandas as pd
from excel_helper import (leer_productos_con_fila, agregar_producto,
                          editar_producto, editar_productos_batch,
                          eliminar_producto, guardar_para_cotizar_batch)
from data_helper import (cargar_productos, get_proveedores,
                         guardar_precio_especial, eliminar_precio_especial,
                         leer_precios_capa, limpiar_cache_precios)

# ── Constantes ────────────────────────────────────────────────────────────────
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
    """Proveedores del catálogo, con lista de respaldo si la hoja no responde.

    El respaldo evita que el formulario quede inutilizable, pero se avisa: si
    falla en silencio, se asigna un proveedor de una lista fija y desactualizada
    sin que nadie se entere.
    """
    try:
        return get_proveedores()
    except Exception as e:
        st.warning(f"No se pudo leer la lista de proveedores ({e}). "
                   "Se muestra una lista de respaldo, que puede estar "
                   "desactualizada.")
        return ["CENMA", "Patojas", "El Huerto", "Productor Directo",
                "Importado", "Otro", "Sin Proveedor"]

# ── Helpers de UI ─────────────────────────────────────────────────────────────
from utils import _conf, _show_conf

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
                key=f"{kp}_cotizar",
                help="«No» lo saca del Cotizador y de los reportes que "
                     "filtran por catálogo. Vacío o «Si» lo dejan visible.")
            if str(cotizar).strip().lower() == "no":
                st.caption("⚠️ Con **Para cotizar = No** este producto no va a "
                           "aparecer en el Cotizador. Sí vas a poder usarlo en "
                           "pedidos.")
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
def _propagar_precios_pedidos(ediciones: list) -> dict:
    """Propaga costo y precio del catálogo a los pedidos de la SEMANA EN CURSO.

    La regla y la escritura viven en order_helper.propagar_costo_semana, que es
    la ruta compartida por todos los caminos que cambian costos. Acá solo se
    traduce la lista de ediciones a los dos mapas que espera.

    Esta pestaña edita el LISTADO GENERAL, así que el precio nuevo se manda
    para que se propague a las líneas cuyo precio sale de ese listado. Las de
    clientes con precio de cliente/grupo/zona no se tocan: esos se editan en
    Lista de Precios Especiales y su propia lista manda.

    Sin esto, un cambio de precio no llegaba a Envíos ni Facturación, que se
    calculan sobre el precio.

    Devuelve {"lineas": int, "precios": int, "especiales": int}.
    """
    from order_helper import propagar_costo_semana

    nuevos_costos, nuevos_precios = {}, {}
    for ed in ediciones:
        nombre = str(ed["data"].get("nombre", "")).strip()
        if not nombre:
            continue
        k = nombre.lower()
        nuevos_costos[k] = float(ed["data"].get("costo") or 0)
        p_ant = float(ed.get("precio_ant") or 0)
        p_nue = float(ed["data"].get("precio") or 0)
        # Hace falta conocer el precio ANTERIOR para afirmar que cambió. Si el
        # llamador no lo pasa, no se propaga precio: solo costo.
        if p_ant > 0 and p_nue > 0 and abs(p_nue - p_ant) > 0.001:
            nuevos_precios[k] = p_nue
    return propagar_costo_semana(nuevos_costos, nuevos_precios=nuevos_precios)


def _tab_actualizar(es_antigua: bool = False):
    """Tabla inline con data_editor — Actual vs Nuevo + Margen en vivo."""
    import pandas as pd
    lbl = "Antigua" if es_antigua else "General"
    _show_conf("prod_upd")

    todos = leer_productos_con_fila(es_antigua=es_antigua)

    # ── Filtros ───────────────────────────────────────────────────────────────
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

    st.caption(f"{len(filtrados)} de {len(todos)} productos")

    # ── Margen ────────────────────────────────────────────────────────────────
    from config import IVA_FACTOR, ISR_FACTOR
    IVA, ISR = 0.12, 0.05  # legacy locals (helpers de config disponibles)

    def _mg(costo, precio):
        if precio <= 0: return 0.0
        return (1 - ISR) * (precio - costo * (1 + IVA)) / precio * 100

    def _mg_txt(mg_nuevo, mg_saved=None):
        badge = "🟢" if mg_nuevo >= 35 else ("🟡" if mg_nuevo >= 20 else "🔴")
        s = f"{badge} {mg_nuevo:.1f}%"
        if mg_saved is not None and abs(mg_nuevo - mg_saved) > 0.05:
            delta = mg_nuevo - mg_saved
            s += f"  ↑+{delta:.1f}" if delta > 0 else f"  ↓{delta:.1f}"
        return s

    # ── Editor de precios/costos dentro de st.form ────────────────────────────
    # Usar st.form evita el bug de "guardar 2-3 veces": las ediciones NO
    # disparan rerun en cada Enter; se acumulan y se envían TODAS juntas al
    # presionar el botón de guardar. El guardado es en BATCH (un solo request).
    import pandas as pd

    rows = []
    for idx, p in enumerate(filtrados):
        cs = float(p.get("costo")  or 0)
        ps = float(p.get("precio") or 0)
        rows.append({
            "Producto":      p["nombre"],
            "Unidad":        p.get("unidad", ""),
            "Precio Act":    ps,
            "Costo Act":     cs,
            "Margen Act":    _mg_txt(_mg(cs, ps)),
            "Precio Nuevo":  ps,   # arranca = actual
            "Costo Nuevo":   cs,   # arranca = actual
        })
    df = pd.DataFrame(rows)

    if df.empty:
        st.info("No hay productos que coincidan con los filtros.")
        return

    ED_KEY = f"upd_ed_{lbl}"
    with st.form(key=f"form_precios_{lbl}"):
        st.caption("Editá Precio Nuevo y/o Costo Nuevo de los productos que "
                   "necesites, y presioná **Guardar cambios** una sola vez.")
        edited = st.data_editor(
            df,
            key=ED_KEY,
            column_config={
                "Producto":     st.column_config.TextColumn("Producto",    disabled=True),
                "Unidad":       st.column_config.TextColumn("Unidad",      disabled=True),
                "Precio Act":   st.column_config.NumberColumn("Precio Act", disabled=True, format="Q%.2f"),
                "Costo Act":    st.column_config.NumberColumn("Costo Act",  disabled=True, format="Q%.2f"),
                "Margen Act":   st.column_config.TextColumn("Margen Act",  disabled=True),
                "Precio Nuevo": st.column_config.NumberColumn("Precio Nuevo", format="%.2f", min_value=0.0),
                "Costo Nuevo":  st.column_config.NumberColumn("Costo Nuevo",  format="%.2f", min_value=0.0),
            },
            hide_index=True,
            use_container_width=True,
            height=min(600, 60 + len(df) * 35),
        )
        guardar = st.form_submit_button("💾 Guardar cambios", type="primary")

    if guardar:
        # Detectar cambios comparando con los valores originales
        ediciones = []
        cascadas  = []
        for idx, row in edited.iterrows():
            p = filtrados[idx]
            cs_orig = float(p.get("costo")  or 0)
            ps_orig = float(p.get("precio") or 0)
            c_new   = float(row["Costo Nuevo"]  or 0)
            p_new   = float(row["Precio Nuevo"] or 0)
            if abs(c_new - cs_orig) > 0.001 or abs(p_new - ps_orig) > 0.001:
                ediciones.append({
                    "row_num": p["row_num"],
                    "data": {**p, "costo": c_new, "precio": p_new},
                    # El precio viejo del catálogo: la propagación lo necesita
                    # para distinguir las líneas que lo usaban de las que
                    # tienen precio negociado.
                    "precio_ant": ps_orig,
                })
                if abs(c_new - cs_orig) > 0.001:
                    cascadas.append((p["nombre"], c_new))

        if not ediciones:
            st.info("No detecté cambios para guardar.")
        else:
            n = len(ediciones)
            with st.spinner(f"Guardando {n} producto(s)..."):
                try:
                    editar_productos_batch(ediciones, es_antigua)
                    # Cascada de costo a productos hijos
                    for nombre, c_new in cascadas:
                        _cascade_parent(nombre, c_new, todos)
                    # Propagar el costo a los pedidos de la semana en curso
                    _res = _propagar_precios_pedidos(ediciones)
                    n_lineas = _res["lineas"]
                    n_precios = _res["precios"]
                except Exception as e:
                    st.error(f"❌ Error al guardar: {type(e).__name__}: {e}")
                    st.stop()
            # El conteo real, no un "y reflejados" que aparecía igual con 0.
            if n_lineas:
                _msg = (f"✅ {n} producto(s) actualizados · {n_lineas} línea(s) "
                        f"de pedido de esta semana con el costo nuevo")
                if n_precios:
                    _msg += f" · {n_precios} también con el precio nuevo"
                if _res.get("especiales"):
                    _msg += (f" · {_res['especiales']} con precio de "
                             f"cliente/grupo/zona quedaron intactas")
                _conf("prod_upd", _msg + ".")
            else:
                _conf("prod_upd",
                      f"✅ {n} producto(s) actualizados · no había líneas de "
                      f"pedido de esta semana para actualizar.")
            st.rerun()

    # Recalculo manual: al guardar ya se propaga lo que cambiaste, pero esto
    # reaplica TODO por si alguna vez no se aplicó.
    st.divider()
    from order_helper import widget_recalcular_semana
    widget_recalcular_semana(f"recalc_upd_{lbl}")

    # ── Edición completa (expander) ───────────────────────────────────────────
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
                    _msg = f"Producto actualizado: {datos['nombre']}"
                    if costo_cambio:
                        # Este camino no propagaba nada: el costo cambiaba en el
                        # catálogo y los pedidos de la semana quedaban viejos.
                        from order_helper import propagar_costo_semana
                        _k = str(datos["nombre"]).strip().lower()
                        _p_ant = float(prod.get("precio") or 0)
                        _p_nue = float(datos.get("precio") or 0)
                        _pr = ({_k: _p_nue}
                               if _p_nue > 0 and abs(_p_nue - _p_ant) > 0.001
                               else None)
                        _n = propagar_costo_semana(
                            {_k: float(datos.get("costo") or 0)},
                            nuevos_precios=_pr)["lineas"]
                        _msg += (f" · {_n} línea(s) de pedido de esta semana "
                                 f"con el costo nuevo" if _n else
                                 " · sin pedidos de esta semana para propagar")
                        _cascade_parent(datos["nombre"],
                                        float(datos["costo"]), todos)
                    _conf("prod_upd", _msg)
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
            costos_nuevos = {}
            for h in hijos:
                nuevo_c = costos_hijos[h["row_num"]]
                editar_producto(h["row_num"], {**h, "costo": nuevo_c},
                                es_antigua=False)
                costos_nuevos[str(h["nombre"]).strip().lower()] = float(nuevo_c or 0)
            # Los hijos tampoco propagaban: su costo cambiaba solo en el catálogo.
            from order_helper import propagar_costo_semana
            n_lineas = propagar_costo_semana(costos_nuevos)["lineas"]
        msg = f"Costos de {len(hijos)} hijo(s) actualizados."
        msg += (f" {n_lineas} línea(s) de pedido de esta semana quedaron "
                f"con el costo nuevo." if n_lineas else
                " Sin pedidos de esta semana para propagar.")
        st.success(msg)


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
    def _propagar_nivel(hoja, lista, producto, precio):
        """Aplica el precio a los pedidos de la SEMANA EN CURSO de los clientes
        de ese nivel. No toca semanas pasadas: el historial queda como está."""
        try:
            from order_helper import propagar_precio_nivel
            return propagar_precio_nivel(producto, precio, hoja, lista)
        except Exception as e:
            st.warning(f"El precio se guardó, pero no se pudo aplicar a los "
                       f"pedidos de esta semana ({e}).")
            return 0

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
                _n = _propagar_nivel(hoja, lista, f["producto"], nuevo_p)
                st.success(
                    f"Q{nuevo_p:.2f} guardado para {f['producto']}."
                    + (f" · {_n} línea(s) de pedido de esta semana actualizadas."
                       if _n else
                       " · sin pedidos de esta semana para actualizar."))
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
            _na = _propagar_nivel(hoja, lista, prod_add, precio_add)
            st.success(
                f"'{prod_add}' ({gen_map.get(prod_add.lower(),{}).get('unidad','')}) "
                f"agregado a {lista} con Q{precio_add:.2f}."
                + (f" · {_na} línea(s) de pedido de esta semana actualizadas."
                   if _na else
                   " · sin pedidos de esta semana para actualizar."))
            st.rerun()


    st.divider()
    from order_helper import widget_recalcular_semana
    widget_recalcular_semana("recalc_listas")


def _tab_costos_masivo():
    """Aplica un costo al HISTORIAL de pedidos, en el rango de fechas elegido.

    Es la única herramienta que toca semanas pasadas: todo lo demás está acotado
    a la semana en curso a propósito. Existe para corregir costos mal cargados,
    y por eso arranca filtrando productos de PROCESO, cuyo costo sale de una
    receta y es estable. En producto fresco el costo varía cada semana, así que
    sobrescribir el histórico borraría el costo real de esa semana en vez de
    corregir un error.
    """
    from datetime import date, timedelta
    from order_helper import (diferencias_costo_historico,
                              aplicar_costo_historico, semana_en_curso)

    st.markdown("#### Actualizar Costos Masivo")
    st.caption("Aplica un costo a los pedidos YA INGRESADOS del rango que "
               "elijas. Pensado para corregir costos mal cargados en productos "
               "de proceso, cuyo costo es estable.")
    st.warning("⚠️ Esto modifica pedidos de semanas pasadas, incluidas las ya "
               "facturadas. **No hay deshacer**: si algo sale mal, la única "
               "salida es restaurar el Sheet desde el historial de versiones "
               "de Google. Revisá la vista previa antes de aplicar.")

    todos = leer_productos_con_fila(es_antigua=False)
    tipos = sorted({str(p.get("tipo_producto", "") or "").strip()
                    for p in todos if str(p.get("tipo_producto", "") or "").strip()})

    # ── Qué productos ────────────────────────────────────────────────────────
    f1, f2 = st.columns([1, 2])
    tipo_sel = f1.multiselect(
        "Tipo de producto", tipos,
        default=[t for t in tipos if t.lower() == "proceso"],
        key="cm_tipos",
        help="Arranca en Proceso porque su costo es estable. Podés cambiarlo, "
             "pero en producto fresco el costo real varía cada semana.")

    candidatos = [p for p in todos
                  if not tipo_sel
                  or str(p.get("tipo_producto", "") or "").strip() in tipo_sel]
    nombres = sorted(p["nombre"] for p in candidatos)
    prods_sel = f2.multiselect("Productos a actualizar", nombres,
                               key="cm_prods",
                               placeholder="Elegí uno o más productos...")

    if not prods_sel:
        st.info("Seleccioná al menos un producto.")
        return

    # ── Qué costo aplicar ────────────────────────────────────────────────────
    st.markdown("**Costo a aplicar** — por defecto el del catálogo; podés "
                "cambiarlo si el correcto es otro.")
    cat = {p["nombre"]: p for p in candidatos}
    costos = {}
    for i, nom in enumerate(prods_sel):
        c1, c2, c3 = st.columns([2.5, 1, 1])
        c1.markdown(f"<div style='padding-top:8px'>{nom}</div>",
                    unsafe_allow_html=True)
        _cat = float(cat.get(nom, {}).get("costo", 0) or 0)
        c2.markdown(f"<div style='padding-top:8px;color:#666;font-size:.85rem'>"
                    f"catálogo: Q{_cat:.2f}</div>", unsafe_allow_html=True)
        costos[nom.strip().lower()] = c3.number_input(
            "Costo Q", value=_cat, min_value=0.0, step=0.25,
            key=f"cm_costo_{i}", label_visibility="collapsed")

    # ── Rango de fechas ──────────────────────────────────────────────────────
    lunes, domingo = semana_en_curso()
    d1, d2 = st.columns(2)
    desde = d1.date_input("Desde", value=lunes, key="cm_desde")
    hasta = d2.date_input("Hasta", value=domingo, key="cm_hasta")
    if desde > hasta:
        st.error("El 'Desde' es posterior al 'Hasta'.")
        return
    if desde < lunes:
        st.caption(f"⚠️ El rango incluye semanas anteriores a la actual "
                   f"({desde:%d/%m/%Y} → {hasta:%d/%m/%Y}).")

    # ── Vista previa ─────────────────────────────────────────────────────────
    K = "cm_difs"
    if st.button("🔍 Ver qué cambiaría", key="cm_ver", type="primary"):
        with st.spinner("Revisando pedidos del rango..."):
            st.session_state[K] = diferencias_costo_historico(
                costos, desde, hasta)

    difs = st.session_state.get(K)
    if difs is None:
        return
    if not difs:
        st.success("Ninguna línea cambiaría: los pedidos del rango ya tienen "
                   "esos costos.")
        return

    _ma = sum(d["Margen actual"] for d in difs)
    _mn = sum(d["Margen nuevo"] for d in difs)
    m1, m2, m3 = st.columns(3)
    m1.metric("Líneas a modificar", f"{len(difs):,}")
    m2.metric("Margen actual",  f"Q{_ma:,.2f}")
    m3.metric("Margen después", f"Q{_mn:,.2f}", delta=f"Q{_mn - _ma:,.2f}")

    st.dataframe(pd.DataFrame(difs).drop(columns=["row_num"]),
                 use_container_width=True, hide_index=True)
    st.caption(f"Rango: {desde:%d/%m/%Y} a {hasta:%d/%m/%Y} · "
               f"el precio de cada línea NO se modifica, solo el costo y los "
               f"derivados.")

    b1, b2 = st.columns(2)
    if b1.button(f"✅ Aplicar a {len(difs)} línea(s)", type="primary",
                 key="cm_ok", use_container_width=True):
        with st.spinner("Actualizando pedidos..."):
            n = aplicar_costo_historico(difs)
        st.session_state.pop(K, None)
        st.success(f"{n} línea(s) actualizadas.")
        st.rerun()
    if b2.button("Cancelar", key="cm_no", use_container_width=True):
        st.session_state.pop(K, None)
        st.rerun()




# ── TAB: Actualizar Precios Masivo ────────────────────────────────────────────
def _listas_de_precio() -> list:
    """Opciones del selector, leídas de las HOJAS y no de una constante.

    Devuelve [(etiqueta, hoja_key, lista)]. Las listas especiales se crean en el
    Sheet sin tocar código, así que hardcodearlas dejaría el selector viejo el
    día que se agregue una.
    """
    from gsheets import get_all_rows
    opciones = [("General (catálogo)", "general", "")]
    for hoja, titulo in (("precioszona", "Zona"), ("preciosgrupo", "Grupo")):
        try:
            # get_all_rows YA devuelve las filas sin encabezado (hace vals[1:]),
            # así que acá NO se vuelve a recortar: hacerlo se comía la primera
            # lista de cada hoja.
            vistas, filas = set(), get_all_rows(hoja)
            for row in filas:
                nom = str(row[0]).strip() if row and len(row) else ""
                if nom and nom.lower() not in vistas:
                    vistas.add(nom.lower())
                    opciones.append((f"{titulo}: {nom}", hoja, nom))
        except Exception as e:
            st.warning(f"No se pudo leer «{hoja}» ({e}). "
                       f"Sus listas no aparecen en el selector.")
    return opciones


def _tab_precios_masivo():
    """Aplica un precio al HISTORIAL de pedidos, por lista y rango de fechas.

    Reemplaza la Corrección Masiva que vivía en Mantenimiento. La diferencia que
    importa: aquella filtraba por pertenencia (todo cliente de la zona), y por
    eso le pisaba el precio a quien tenía uno individual negociado. Acá el
    alcance lo decide la cascada — ver data_helper.alcanzado_por_nivel.
    """
    from datetime import date
    from order_helper import (diferencias_precio_historico,
                              aplicar_precio_historico, clientes_alcanzados,
                              semana_en_curso)

    st.markdown("#### Actualizar Precios Masivo")
    st.caption("Aplica un precio a los pedidos YA INGRESADOS del rango que "
               "elijas, solo a los clientes a quienes esa lista les da el "
               "precio hoy.")
    st.warning("⚠️ Esto modifica pedidos de semanas pasadas, incluidas las ya "
               "facturadas. **No hay deshacer**: si algo sale mal, la única "
               "salida es restaurar el Sheet desde el historial de versiones "
               "de Google. Revisá la vista previa antes de aplicar.")

    todos = leer_productos_con_fila(es_antigua=False)
    tipos = sorted({str(p.get("tipo_producto", "") or "").strip()
                    for p in todos if str(p.get("tipo_producto", "") or "").strip()})

    # ── Qué productos y de qué lista ─────────────────────────────────────────
    f1, f2 = st.columns([1, 2])
    tipo_sel = f1.multiselect("Tipo de producto", tipos, key="pm_tipos",
                              help="Vacío = todos los tipos.")
    candidatos = [p for p in todos
                  if not tipo_sel
                  or str(p.get("tipo_producto", "") or "").strip() in tipo_sel]
    prods_sel = f2.multiselect(
        "Productos a actualizar", sorted(p["nombre"] for p in candidatos),
        key="pm_prods", placeholder="Elegí uno o más productos...")

    opciones = _listas_de_precio()
    etiqueta = st.selectbox("Lista de precio", [o[0] for o in opciones],
                            key="pm_lista",
                            help="Determina a qué clientes les llega el "
                                 "cambio. General alcanza solo a quienes no "
                                 "tienen ninguna lista especial.")
    _, hoja_key, lista = next(o for o in opciones if o[0] == etiqueta)

    if not prods_sel:
        st.info("Seleccioná al menos un producto.")
        return

    # ── A quién alcanza ──────────────────────────────────────────────────────
    # Se muestra ANTES de pedir el precio: si la lista no alcanza a nadie, no
    # tiene sentido seguir. Pasaba en silencio con las zonas que existen en la
    # hoja pero que config.ZONA_LISTA_CODIGOS no mapea a ningún codigo_lugar.
    alcance = {p: clientes_alcanzados(p, hoja_key, lista) for p in prods_sel}
    total_alc = sorted({c for v in alcance.values() for c in v})
    if not total_alc:
        st.error(
            f"**«{etiqueta}» no le está dando el precio a ningún cliente** "
            f"para esos productos, así que este cambio no tocaría nada.\n\n"
            f"Puede ser porque todos sus clientes tienen un precio más "
            f"específico (individual o de grupo) que manda sobre esta lista, "
            f"o porque es una lista de zona sin códigos de lugar asignados en "
            f"la configuración.")
        return
    with st.expander(f"👥 Alcanza a {len(total_alc)} cliente(s) — ver cuáles"):
        for p in prods_sel:
            st.markdown(f"**{p}** — {len(alcance[p])}: "
                        + (", ".join(alcance[p]) if alcance[p] else "_ninguno_"))

    # ── Qué precio aplicar ───────────────────────────────────────────────────
    st.markdown("**Precio a aplicar** — por defecto el del catálogo general; "
                "cambialo al que corresponde a esta lista.")
    cat = {p["nombre"]: p for p in candidatos}
    precios = {}
    for i, nom in enumerate(prods_sel):
        c1, c2, c3 = st.columns([2.5, 1, 1])
        c1.markdown(f"<div style='padding-top:8px'>{nom}</div>",
                    unsafe_allow_html=True)
        _cat = float(cat.get(nom, {}).get("precio", 0) or 0)
        c2.markdown(f"<div style='padding-top:8px;color:#666;font-size:.85rem'>"
                    f"catálogo: Q{_cat:.2f}</div>", unsafe_allow_html=True)
        precios[nom.strip().lower()] = c3.number_input(
            "Precio Q", value=_cat, min_value=0.0, step=0.25,
            key=f"pm_precio_{i}", label_visibility="collapsed")

    # ── Rango de fechas ──────────────────────────────────────────────────────
    lunes, domingo = semana_en_curso()
    d1, d2 = st.columns(2)
    desde = d1.date_input("Desde", value=lunes, key="pm_desde")
    hasta = d2.date_input("Hasta", value=domingo, key="pm_hasta")
    if desde > hasta:
        st.error("El 'Desde' es posterior al 'Hasta'.")
        return
    if desde < lunes:
        st.caption(f"⚠️ El rango incluye semanas anteriores a la actual "
                   f"({desde:%d/%m/%Y} → {hasta:%d/%m/%Y}).")

    # ── Vista previa ─────────────────────────────────────────────────────────
    K = "pm_difs"
    if st.button("🔍 Ver qué cambiaría", key="pm_ver", type="primary"):
        with st.spinner("Revisando pedidos del rango..."):
            st.session_state[K] = diferencias_precio_historico(
                precios, hoja_key, lista, desde, hasta)

    difs = st.session_state.get(K)
    if difs is None:
        return
    if not difs:
        st.success("Ninguna línea cambiaría: los pedidos del rango ya tienen "
                   "esos precios para esta lista.")
        return

    _ta = sum(d["Total actual"] for d in difs)
    _tn = sum(d["Total nuevo"]  for d in difs)
    _ma = sum(d["Margen actual"] for d in difs)
    _mn = sum(d["Margen nuevo"]  for d in difs)
    m1, m2, m3 = st.columns(3)
    m1.metric("Líneas a modificar", f"{len(difs):,}")
    m2.metric("Facturado", f"Q{_tn:,.2f}", delta=f"Q{_tn - _ta:,.2f}")
    m3.metric("Margen",    f"Q{_mn:,.2f}", delta=f"Q{_mn - _ma:,.2f}")

    st.dataframe(pd.DataFrame(difs).drop(columns=["row_num"]),
                 use_container_width=True, hide_index=True)
    st.caption(f"Lista: **{etiqueta}** · Rango: {desde:%d/%m/%Y} a "
               f"{hasta:%d/%m/%Y} · el costo de cada línea NO se modifica, "
               f"solo el precio y los derivados.")
    if _tn != _ta:
        st.caption("Cambia lo facturado de esos pedidos. Si alguno ya se "
                   "cobró, la factura emitida y el Sheet van a discrepar.")

    b1, b2 = st.columns(2)
    if b1.button(f"✅ Aplicar a {len(difs)} línea(s)", type="primary",
                 key="pm_ok", use_container_width=True):
        with st.spinner("Actualizando pedidos..."):
            n = aplicar_precio_historico(difs)
        st.session_state.pop(K, None)
        st.success(f"{n} línea(s) actualizadas.")
        st.rerun()
    if b2.button("Cancelar", key="pm_no", use_container_width=True):
        st.session_state.pop(K, None)
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

    tab_upd, tab_cm, tab_pm, tab_np, tab_cat, tab_lp, tab_val = st.tabs([
        "✏️ Actualizar Precios",
        "🧮 Actualizar Costos Masivo",
        "🏷️ Actualizar Precios Masivo",
        "➕ Nuevo Producto",
        "📋 Ver Catálogo",
        "🏷️ Lista de Precios Especiales",
        "🔍 Validación",
    ])
    with tab_upd: _tab_actualizar(es_antigua=False)
    with tab_cm:  _tab_costos_masivo()
    with tab_pm:  _tab_precios_masivo()
    with tab_np:  _tab_nuevo()
    with tab_cat: _tab_catalogo()
    with tab_lp:  _tab_listas()
    with tab_val: _tab_validacion()
