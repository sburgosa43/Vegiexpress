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


@st.cache_data(ttl=600)
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


@st.cache_data(ttl=600)
def _cargar_catalogo(es_antigua: bool):
    from drive_helper import cargar_para_lectura
    FILE_ID = st.secrets["EXCEL_FILE_ID"]
    wb   = cargar_para_lectura(FILE_ID)
    hoja = "Listado Productos Antigua" if es_antigua else "Listado Productos"
    ws   = wb[hoja]
    prods = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[0]: continue
        # Para Cotizar: col 22 (idx 21) general, col 18 (idx 17) antigua
        para_cot_idx = 17 if es_antigua else 21
        para_cot = str(row[para_cot_idx] if len(row) > para_cot_idx else "").strip().lower()
        if para_cot not in ["si", "sí", "yes", "1", "true"]: continue
        col_precio = 6 if es_antigua else 7   # 0-indexed
        prods.append({
            "nombre":   str(row[0]).strip(),
            "unidad":   str(row[1] or "").strip(),
            "tipo":     str(row[16] if es_antigua else row[18] or "").strip(),
            "precio":   float(row[col_precio] or 0),
        })
    wb.close()
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

# ── PASO 2: Catálogo ──────────────────────────────────────────────────────────
elif paso == 2:
    nombre_rest = st.session_state["restaurante"]
    antigua     = st.session_state["es_antigua"]
    carrito     = st.session_state["carrito"]

    st.markdown(f"### 🛒 Catálogo para **{nombre_rest}**")
    if st.button("← Cambiar restaurante"):
        st.session_state["paso"] = 1; st.rerun()

    catalogo = _cargar_catalogo(antigua)

    if not catalogo:
        st.warning("No hay productos disponibles en el catálogo en este momento.")
    else:
        # Agrupar por tipo
        tipos = {}
        for p in catalogo:
            t = p["tipo"] or "Otros"
            if t not in tipos: tipos[t] = []
            tipos[t].append(p)

        n_en_carrito = sum(1 for v in carrito.values() if v > 0)
        if n_en_carrito:
            st.success(f"🛒 {n_en_carrito} producto(s) en tu pedido")

        for tipo, prods in sorted(tipos.items()):
            st.markdown(f"**{tipo}**")
            for p in prods:
                c1, c2, c3 = st.columns([4, 1.5, 1.5])
                c1.markdown(f"{p['nombre']}  \n"
                            f"<small style='color:#888'>{p['unidad']} · "
                            f"Q{p['precio']:,.2f}</small>",
                            unsafe_allow_html=True)
                c2.markdown(f"<div style='padding-top:8px;font-size:.9rem;"
                            f"font-weight:bold'>Q{p['precio']:,.2f}</div>",
                            unsafe_allow_html=True)
                key = f"cant_{p['nombre']}"
                val = c3.number_input("", min_value=0, step=1,
                                       value=carrito.get(p["nombre"], 0),
                                       key=key, label_visibility="collapsed")
                if val > 0:
                    carrito[p["nombre"]] = (val, p["unidad"], p["precio"])
                elif p["nombre"] in carrito:
                    del carrito[p["nombre"]]

        st.session_state["carrito"] = carrito

        st.divider()
        n_items = sum(1 for v in carrito.values())
        total   = sum(v[0]*v[2] for v in carrito.values())

        if n_items:
            st.markdown(
                f"<div style='background:#e8f5e9;border-radius:8px;"
                f"padding:10px;text-align:center'>"
                f"<b>{n_items} producto(s) · Total estimado: Q{total:,.2f}</b>"
                f"</div>", unsafe_allow_html=True)
            if st.button("Continuar a fecha de entrega →", type="primary",
                          use_container_width=True):
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
                st.error(f"Error al enviar: {e}. Por favor intentá de nuevo.")

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
