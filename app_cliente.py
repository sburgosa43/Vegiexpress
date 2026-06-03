"""
app_cliente.py — Catálogo y pedidos VeggiExpress (app pública para clientes)
URL pública en Streamlit Cloud — sin login requerido.

Deploy en Streamlit Cloud apuntando a este archivo (Advanced Settings → Main file path).
Secrets necesarios: gcp_service_account, EXCEL_FILE_ID, PEDIDOS_SHEET_ID
"""
import streamlit as st
from datetime import date, timedelta

st.set_page_config(
    page_title="VeggiExpress — Pedidos",
    page_icon="🥬",
    layout="centered",
)

# ── Helpers ───────────────────────────────────────────────────────────────────
AREA_ANTIGUA = ["Antigua", "Chimaltenango"]
AREA_GENERAL = ["Guatemala", "Río Dulce"]
TODAS_AREAS  = AREA_ANTIGUA + AREA_GENERAL

MESES_ES = {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",
            7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"}


@st.cache_data(ttl=3600)
def _cargar_clientes():
    try:
        from drive_helper import cargar_para_lectura
        FILE_ID = st.secrets["EXCEL_FILE_ID"]
        wb  = cargar_para_lectura(FILE_ID)
        ws  = wb["Clientes"]
        clis = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row[0]: continue
            nombre = str(row[0]).strip()
            if not nombre: continue
            # Incluir todos los clientes con nombre — sin filtro de estatus
            clis.append({
                "nombre":       nombre,
                "ubicacion":    str(row[2] or "").strip(),
                "codigo_lugar": str(row[10] or "").strip(),
            })
        wb.close()
        return sorted(clis, key=lambda x: x["nombre"])
    except Exception as e:
        st.error(f"Error cargando clientes: {e}")
        return []


@st.cache_data(ttl=3600)
def _cargar_catalogo(es_antigua: bool):
    """Carga catálogo desde Google Sheets — solo productos Para Cotizar."""
    from gsheets import get_all_rows
    k   = "antigua" if es_antigua else "productos"
    col_precio    = 6 if es_antigua else 7   # 0-indexed
    col_para_cot  = 17 if es_antigua else 21
    col_tipo      = 16 if es_antigua else 18

    prods = []
    for row in get_all_rows(k):
        while len(row) < 23: row.append("")
        nombre = str(row[0] or "").strip()
        if not nombre: continue
        para_cot = str(row[col_para_cot] or "").strip().lower()
        if para_cot not in ("si", "sí", "yes", "1", "true"): continue
        try: precio = float(row[col_precio] or 0)
        except: precio = 0.0
        if precio <= 0: continue
        prods.append({
            "nombre":   nombre,
            "unidad":   str(row[1] or "").strip(),
            "tipo":     str(row[col_tipo] or "").strip(),
            "segmento": str(row[2] or "").strip(),
            "precio":   precio,
        })
    return sorted(prods, key=lambda x: (x["tipo"], x["nombre"]))


def _es_antigua(codigo_lugar: str) -> bool:
    return codigo_lugar in ["L03", "L04"]


def _area_a_antigua(area: str) -> bool:
    return area in AREA_ANTIGUA


# ── Header ────────────────────────────────────────────────────────────────────
col_logo, col_tit = st.columns([1, 3])
with col_logo:
    try:
        st.image("VeggiExpress-02.png", use_container_width=True)
    except Exception:
        st.markdown("# 🥬")
with col_tit:
    st.markdown("## Catálogo y Pedidos")
    st.caption("Más fresco, imposible.")

st.divider()

# ── Estado de la sesión ───────────────────────────────────────────────────────
if "paso"        not in st.session_state: st.session_state["paso"] = 1
if "restaurante" not in st.session_state: st.session_state["restaurante"] = None
if "es_nuevo"    not in st.session_state: st.session_state["es_nuevo"] = False
if "area_nueva"  not in st.session_state: st.session_state["area_nueva"] = None
if "es_antigua"  not in st.session_state: st.session_state["es_antigua"] = False
if "carrito"     not in st.session_state: st.session_state["carrito"] = {}

paso = st.session_state["paso"]

# ── PASO 1: Identificación ────────────────────────────────────────────────────
if paso == 1:
    st.markdown("### 👤 ¿Cuál es tu restaurante?")

    clientes = _cargar_clientes()
    nombres  = [c["nombre"] for c in clientes]
    opciones = nombres + ["+ Nuevo cliente / Prospecto"]

    seleccion = st.selectbox("Seleccioná tu restaurante:",
                              opciones, index=None,
                              placeholder="Escribí para buscar...")

    if seleccion == "+ Nuevo cliente / Prospecto":
        st.markdown("**¿De qué área sos?**")
        area_sel = st.selectbox("Área:", TODAS_AREAS, index=None,
                                 placeholder="Seleccioná tu ciudad/área...")
        nombre_nuevo = st.text_input("Tu nombre o nombre del negocio:")

        if area_sel and nombre_nuevo:
            if st.button("Continuar →", type="primary"):
                st.session_state["restaurante"] = nombre_nuevo.strip()
                st.session_state["es_nuevo"]    = True
                st.session_state["area_nueva"]  = area_sel
                st.session_state["es_antigua"]  = _area_a_antigua(area_sel)
                st.session_state["carrito"]     = {}
                st.session_state["paso"]        = 2
                st.rerun()

    elif seleccion:
        cli = next(c for c in clientes if c["nombre"] == seleccion)
        st.info(f"📍 {cli['ubicacion']}")
        if st.button("Continuar →", type="primary"):
            st.session_state["restaurante"] = seleccion
            st.session_state["es_nuevo"]    = False
            st.session_state["area_nueva"]  = None
            st.session_state["es_antigua"]  = _es_antigua(cli["codigo_lugar"])
            st.session_state["carrito"]     = {}
            st.session_state["paso"]        = 2
            st.rerun()

# ── PASO 2: Catálogo con navegación por categorías ───────────────────────────
elif paso == 2:
    nombre_rest = st.session_state["restaurante"]
    antigua     = st.session_state["es_antigua"]
    carrito     = st.session_state["carrito"]

    st.markdown(f"### 🛒 Catálogo para **{nombre_rest}**")
    if st.button("← Cambiar restaurante", key="btn_cambiar_rest"):
        st.session_state["paso"] = 1; st.rerun()

    catalogo = _cargar_catalogo(antigua)

    if not catalogo:
        st.warning("No hay productos disponibles en el catálogo en este momento.")
    else:
        # Agrupar por tipo dinámicamente
        tipos_dict = {}
        for p in catalogo:
            t = p["segmento"].strip() if p.get("segmento") else "Otros"
            if t not in tipos_dict: tipos_dict[t] = []
            tipos_dict[t].append(p)
        categorias = sorted(tipos_dict.keys())

        # Inicializar categoría activa
        if "cat_activa" not in st.session_state or            st.session_state["cat_activa"] not in categorias:
            st.session_state["cat_activa"] = categorias[0]
        cat_actual = st.session_state["cat_activa"]

        # Resumen del carrito
        n_en_carrito = sum(1 for v in carrito.values()
                           if isinstance(v, tuple) and v[0] > 0)
        total_carrito = sum(v[0]*v[2] for v in carrito.values()
                            if isinstance(v, tuple))
        if n_en_carrito:
            st.success(f"🛒 **{n_en_carrito} producto(s) en tu pedido** — "
                       f"Q{total_carrito:,.2f}")

        # ── Botones de categoría (simula pestañas) ────────────────────────────
        # Orden fijo de segmentos; los que no estén en la lista van al final
        ORDEN_SEG = ["Vegetales","Hierbas","Frutas","Congelados","Especias"]
        ICONOS    = {
            "Vegetales":  "🥕",
            "Hierbas":    "🌿",
            "Frutas":     "🍎",
            "Congelados": "🧊",
            "Especias":   "🧂",
        }
        categorias = sorted(
            categorias,
            key=lambda x: ORDEN_SEG.index(x) if x in ORDEN_SEG else len(ORDEN_SEG)
        )
        cat_cols = st.columns(len(categorias))
        for col, cat in zip(cat_cols, categorias):
            icono = ICONOS.get(cat, "📦")
            estilo = "primary" if cat == cat_actual else "secondary"
            if col.button(f"{icono} {cat}", key=f"cat_{cat}",
                          type=estilo, use_container_width=True):
                st.session_state["cat_activa"] = cat; st.rerun()

        st.divider()

        # ── Productos de la categoría activa ─────────────────────────────────
        prods_cat = tipos_dict[cat_actual]
        st.markdown(f"**{ICONOS.get(cat_actual,'📦')} {cat_actual}** "
                    f"— {len(prods_cat)} producto(s)")

        for p in prods_cat:
            c1, c2, c3 = st.columns([4, 1.5, 1.5])
            c1.markdown(
                f"**{p['nombre']}**  \n"
                f"<small style='color:#888'>{p['unidad']} · "
                f"Q{p['precio']:,.2f}</small>",
                unsafe_allow_html=True)
            c2.markdown(
                f"<div style='padding-top:8px;font-size:.9rem;"
                f"font-weight:bold'>Q{p['precio']:,.2f}</div>",
                unsafe_allow_html=True)
            cant_actual = carrito[p["nombre"]][0]                           if p["nombre"] in carrito else 0.0
            val = c3.number_input("", min_value=0.0, step=0.25,
                                   value=float(cant_actual), format="%.2f",
                                   key=f"cant_{p['nombre']}",
                                   label_visibility="collapsed")
            if val > 0:
                carrito[p["nombre"]] = (val, p["unidad"], p["precio"])
            elif p["nombre"] in carrito:
                del carrito[p["nombre"]]

        st.session_state["carrito"] = carrito

        # ── Botones de navegación + confirmar ─────────────────────────────────
        st.divider()
        idx_actual = categorias.index(cat_actual)
        hay_prev   = idx_actual > 0
        hay_next   = idx_actual < len(categorias) - 1
        es_ultima  = not hay_next

        n_items = sum(1 for v in carrito.values()
                      if isinstance(v, tuple) and v[0] > 0)

        # Fila de navegación
        if hay_prev and hay_next:
            bn1, bn2, bn3 = st.columns(3)
            cat_prev = categorias[idx_actual - 1]
            cat_next = categorias[idx_actual + 1]
            if bn1.button(f"← {cat_prev}", key="btn_prev",
                           use_container_width=True):
                st.session_state["cat_activa"] = cat_prev; st.rerun()
            if bn2.button(f"→ {cat_next}", key="btn_next", type="secondary",
                           use_container_width=True):
                st.session_state["cat_activa"] = cat_next; st.rerun()
            with bn3:
                if n_items:
                    if st.button(f"✅ Confirmar ({n_items})", type="primary",
                                  use_container_width=True, key="btn_conf_mid"):
                        st.session_state["paso"] = 3; st.rerun()
                else:
                    st.button("✅ Confirmar", disabled=True,
                               key="btn_conf_mid_dis", use_container_width=True)

        elif hay_prev and not hay_next:
            bn1, bn2 = st.columns(2)
            cat_prev = categorias[idx_actual - 1]
            if bn1.button(f"← {cat_prev}", key="btn_prev2",
                           use_container_width=True):
                st.session_state["cat_activa"] = cat_prev; st.rerun()
            with bn2:
                if n_items:
                    if st.button(f"✅ Confirmar pedido ({n_items})",
                                  type="primary", use_container_width=True,
                                  key="btn_conf_last"):
                        st.session_state["paso"] = 3; st.rerun()
                else:
                    st.button("✅ Confirmar pedido", disabled=True,
                               key="btn_conf_last_dis", use_container_width=True)

        elif not hay_prev and hay_next:
            bn1, bn2 = st.columns(2)
            cat_next = categorias[idx_actual + 1]
            if bn2.button(f"→ {cat_next}", key="btn_next2", type="secondary",
                           use_container_width=True):
                st.session_state["cat_activa"] = cat_next; st.rerun()
            with bn1:
                if n_items:
                    if st.button(f"✅ Confirmar ({n_items})", type="primary",
                                  use_container_width=True, key="btn_conf_first"):
                        st.session_state["paso"] = 3; st.rerun()
                else:
                    st.button("✅ Confirmar", disabled=True,
                               key="btn_conf_first_dis", use_container_width=True)

        else:
            # Solo una categoría
            if n_items:
                if st.button(f"✅ Confirmar pedido ({n_items})",
                              type="primary", use_container_width=True,
                              key="btn_conf_solo"):
                    st.session_state["paso"] = 3; st.rerun()
            else:
                st.info("Agregá al menos un producto para continuar.")

# ── PASO 3: Fecha ─────────────────────────────────────────────────────────────
elif paso == 3:
    st.markdown("### 📅 Fecha de entrega")
    if st.button("← Volver al catálogo"):
        st.session_state["paso"] = 2; st.rerun()

    min_fecha = date.today() + timedelta(hours=48)
    min_fecha = date(min_fecha.year, min_fecha.month, min_fecha.day)

    fecha = st.date_input("¿Cuándo necesitás la entrega?",
                           min_value=min_fecha,
                           value=min_fecha)
    sem   = fecha.isocalendar()[1]
    st.caption(f"📅 Semana {sem} · {fecha.strftime('%A %d de %B de %Y')}")

    notas = st.text_area("Notas o instrucciones adicionales (opcional):",
                          placeholder="Ej: entregar antes del mediodía...")

    st.session_state["fecha_entrega"] = str(fecha)
    st.session_state["semana_entrega"]= sem
    st.session_state["notas"]         = notas

    if st.button("Ver resumen →", type="primary", use_container_width=True):
        st.session_state["paso"] = 4; st.rerun()

# ── PASO 4: Confirmación ──────────────────────────────────────────────────────
elif paso == 4:
    rest   = st.session_state["restaurante"]
    fecha  = st.session_state.get("fecha_entrega", "")
    sem    = st.session_state.get("semana_entrega", "")
    notas  = st.session_state.get("notas", "")
    carrit = st.session_state["carrito"]

    st.markdown(f"### ✅ Confirmar pedido — {rest}")

    st.markdown(f"**📅 Entrega:** {fecha} · Semana {sem}")

    total = 0.0
    for nombre, (cant, unidad, precio) in sorted(carrit.items()):
        sub = cant * precio
        total += sub
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;"
            f"padding:4px 0;border-bottom:1px solid #eee'>"
            f"<span>{nombre} × {cant} {unidad}</span>"
            f"<span><b>Q{sub:,.2f}</b></span></div>",
            unsafe_allow_html=True)

    st.markdown(
        f"<div style='background:#e8f5e9;border-radius:8px;padding:10px;"
        f"text-align:center;margin:12px 0'>"
        f"<b>Total estimado: Q{total:,.2f}</b></div>",
        unsafe_allow_html=True)

    if notas:
        st.caption(f"📝 Notas: {notas}")

    bc, bb = st.columns(2)
    with bc:
        if st.button("← Editar pedido"):
            st.session_state["paso"] = 2; st.rerun()
    with bb:
        if st.button("📤 Enviar pedido", type="primary", use_container_width=True):
            try:
                from sheets_helper import guardar_pedido_cliente
                antigua  = st.session_state["es_antigua"]
                es_nuevo = st.session_state["es_nuevo"]
                area     = st.session_state.get("area_nueva") or \
                           ("Antigua/Chimal" if antigua else "Guatemala/Río")
                lineas   = [
                    {"producto": n, "cantidad": c, "unidad": u,
                     "precio": p, "total": round(c*p, 2)}
                    for n, (c, u, p) in carrit.items()
                ]
                guardar_pedido_cliente(rest, es_nuevo, area,
                                       fecha, sem, lineas)
                st.session_state["paso"] = 5
                st.rerun()
            except Exception as e:
                import traceback
                st.error(f"Error al enviar: {type(e).__name__}: {e}")
                st.code(traceback.format_exc())

# ── PASO 5: Éxito ─────────────────────────────────────────────────────────────
elif paso == 5:
    st.success("🎉 ¡Pedido enviado con éxito!")
    st.markdown(f"""
    Tu pedido fue recibido y está pendiente de confirmación.

    **Restaurante:** {st.session_state['restaurante']}
    **Fecha de entrega:** {st.session_state.get('fecha_entrega', '')}

    Te contactaremos para confirmar.
    """)
    if st.button("📦 Hacer otro pedido", type="primary"):
        for k in ["paso","restaurante","es_nuevo","area_nueva",
                   "es_antigua","carrito","fecha_entrega","semana_entrega","notas"]:
            st.session_state.pop(k, None)
        st.rerun()

st.divider()
st.markdown(
    "<div style='text-align:center;color:#aaa;font-size:.75rem'>"
    "🥬 VeggiExpress · Más fresco, imposible.</div>",
    unsafe_allow_html=True)
