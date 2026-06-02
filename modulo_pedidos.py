"""
modulo_pedidos.py — Ingreso de nuevo pedido con cola batch
Flujo: Cola de pedidos en memoria → un solo ciclo Drive al grabar todo.
"""
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from data_helper   import cargar_clientes, cargar_productos
from order_helper  import guardar_pedidos_batch

AVISO_KEY = "costos_revisados"
COLA_KEY  = "cola_pedidos"


def _init():
    for k, v in {"ped_paso":1,"ped_cliente":None,"ped_fecha":date.today(),
                 "ped_lineas":[],"ped_grid":None,"ped_nfilas":15}.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if COLA_KEY not in st.session_state:
        st.session_state[COLA_KEY] = []

def _reset_pedido():
    """Resetea solo el pedido actual, mantiene la cola."""
    for k in ["ped_paso","ped_cliente","ped_fecha","ped_lineas","ped_grid","ped_nfilas"]:
        st.session_state.pop(k, None)
    _init()

def _reset_todo():
    """Resetea pedido actual Y vacía la cola."""
    _reset_pedido()
    st.session_state[COLA_KEY] = []

def _pasos():
    p = st.session_state.ped_paso
    cols = st.columns(3)
    for i, (col, lbl) in enumerate(
            zip(cols, ["👤 Cliente","🛒 Productos","✅ Confirmar"]), 1):
        with col:
            if i == p:   st.markdown(f"**{lbl} ←**")
            elif i < p:  st.markdown(f"~~{lbl}~~ ✔")
            else:         st.markdown(lbl)
    st.divider()

# ── AVISO DE COSTOS ───────────────────────────────────────────────────────────
def _aviso_costos() -> bool:
    if st.session_state.get(AVISO_KEY):
        estado = st.session_state[AVISO_KEY]
        col_r, col_btn = st.columns([5, 1])
        col_r.caption(f"✔️ Costos verificados ({estado.replace('_', ' ')}) · "
                      "¿Necesitás revisar de nuevo?")
        if col_btn.button("🔄", help="Ver aviso de costos", key="reset_aviso"):
            del st.session_state[AVISO_KEY]; st.rerun()
        return True

    st.markdown("""
    <div style='background:#fff8e1;border:1px solid #f9a825;border-left:5px solid #f9a825;
                border-radius:8px;padding:18px 22px;margin:12px 0'>
        <div style='font-size:1.05rem;font-weight:bold;margin-bottom:8px'>
            ⚠️ Antes de ingresar el pedido
        </div>
        <div style='font-size:.95rem;line-height:1.7;color:#555'>
            Verificá si hubo <b>variaciones en los costos de compra</b>
            desde tu última visita al proveedor.<br>
            Si hay cambios, actualizalos en <b>📦 Productos</b> antes de continuar.
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("📦 Ir a Productos a revisar costos", type="secondary"):
        st.session_state["_nav_target"] = "📦 Productos (Nuevos y Mantenimiento)"
        st.rerun()

    st.markdown("&nbsp;")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ No hay cambios, continuar",
                     type="primary", use_container_width=True):
            st.session_state[AVISO_KEY] = "sin_cambios"; st.rerun()
    with c2:
        if st.button("✔️ Ya actualicé costos, continuar",
                     type="primary", use_container_width=True):
            st.session_state[AVISO_KEY] = "con_cambios"; st.rerun()
    return False

# ── COLA (vista compacta) ─────────────────────────────────────────────────────
def _mostrar_cola_compacta():
    cola = st.session_state.get(COLA_KEY, [])
    if not cola: return
    total_cola = sum(p["total"] for p in cola)
    st.info(
        f"📋 **Cola: {len(cola)} pedido(s) — Q{total_cola:,.2f} total**  "
        f"_(no grabados al Excel aún)_"
    )

# ── PASO 1 ────────────────────────────────────────────────────────────────────
def _paso1():
    st.subheader("👤 Cliente y fecha")
    clientes  = cargar_clientes()
    ver_todos = st.checkbox("Incluir inactivos", value=False)
    lista     = clientes if ver_todos else [c for c in clientes if c["activo"]]
    nombre    = st.selectbox("Cliente", [c["nombre"] for c in lista],
                              index=None, placeholder="Escribí para buscar...")
    if nombre:
        c = next(x for x in lista if x["nombre"] == nombre)
        st.markdown(
            f"<div style='background:#f1f8f1;border-left:4px solid #2e7d32;"
            f"border-radius:6px;padding:10px 14px;font-size:.93rem;line-height:1.6'>"
            f"📍 <b>{c['direccion']}</b> · 🏢 {c['empresa']} · 💳 NIT: {c['nit']}<br>"
            f"🏷️ {c['tipo']} · 📅 Crédito: {c['credito']} días · 📌 {c['codigo_lugar']}"
            f"{'&nbsp;🔖 <b>Precios Antigua</b>' if c['es_antigua'] else ''}"
            f"</div>", unsafe_allow_html=True)

        fecha = st.date_input(
            "📅 Fecha de entrega", value=date.today(),
            min_value=date.today() - timedelta(days=30))
        if fecha < date.today():
            st.caption("📅 Fecha en el pasado — asegurate que sea correcta.")
        st.caption(f"Semana {fecha.isocalendar()[1]} · {fecha.strftime('%A %d/%m/%Y')}")

        if st.button("Continuar → Agregar Productos", type="primary"):
            st.session_state.ped_cliente = c
            st.session_state.ped_fecha   = fecha
            st.session_state.ped_grid    = None
            st.session_state.ped_nfilas  = 15
            st.session_state.ped_paso    = 2
            st.rerun()
    else:
        st.info("Seleccioná un cliente para continuar.")

# ── PASO 2 ────────────────────────────────────────────────────────────────────
def _paso2():
    c   = st.session_state.ped_cliente
    fec = st.session_state.ped_fecha
    st.subheader(f"🛒 Productos — {c['nombre']}")
    st.caption(f"📅 {fec.strftime('%d/%m/%Y')} · 📍 {c['direccion']}"
               + (" · 🔖 Precios Antigua" if c["es_antigua"] else ""))

    prods     = cargar_productos(es_antigua=c["es_antigua"])
    prod_dict = {p["nombre"]: p for p in prods}
    nombres   = [""] + [p["nombre"] for p in prods]
    n         = st.session_state.ped_nfilas

    if st.session_state.ped_grid is None:
        st.session_state.ped_grid = pd.DataFrame(
            {"Producto":[""] * n, "Cantidad":[0.0] * n})
    elif len(st.session_state.ped_grid) < n:
        extra = pd.DataFrame({
            "Producto": [""] * (n - len(st.session_state.ped_grid)),
            "Cantidad": [0.0] * (n - len(st.session_state.ped_grid)),
        })
        st.session_state.ped_grid = pd.concat(
            [st.session_state.ped_grid, extra], ignore_index=True)

    editado = st.data_editor(
        st.session_state.ped_grid,
        column_config={
            "Producto": st.column_config.SelectboxColumn(
                "Producto", options=nombres, required=False, width="medium"),
            "Cantidad": st.column_config.NumberColumn(
                "Cantidad", min_value=0.0, step=0.5, format="%.1f", width="small"),
        },
        num_rows="fixed", use_container_width=True,
        hide_index=False, key="ped_grid_editor",
    )

    validas   = [r for _, r in editado.iterrows()
                 if r["Producto"] and r["Cantidad"] > 0]
    sin_costo = [r["Producto"] for r in validas
                 if r["Producto"] in prod_dict
                 and prod_dict[r["Producto"]]["costo"] <= 0]
    if sin_costo:
        st.warning(f"⚠️ Sin costo: **{', '.join(sin_costo)}** — "
                   "actualizalos en 📦 Productos.")

    c1, c2, c3 = st.columns([2, 2, 3])
    with c1:
        if st.button("+ 5 líneas"):
            st.session_state.ped_grid   = editado
            st.session_state.ped_nfilas = len(editado) + 5; st.rerun()
    with c2:
        if st.button("+ 10 líneas"):
            st.session_state.ped_grid   = editado
            st.session_state.ped_nfilas = len(editado) + 10; st.rerun()
    with c3:
        if st.button("🗑 Limpiar", type="secondary"):
            st.session_state.ped_grid   = None
            st.session_state.ped_nfilas = 15; st.rerun()

    if validas:
        total_est = sum(r["Cantidad"] * prod_dict[r["Producto"]]["precio"]
                        for r in validas if r["Producto"] in prod_dict)
        st.markdown(
            f"<div style='background:#e8f5e9;border-radius:8px;padding:10px;"
            f"text-align:center;margin:8px 0'>"
            f"<b>{len(validas)} productos</b> · "
            f"Total estimado: <b>Q{total_est:,.2f}</b></div>",
            unsafe_allow_html=True)

    st.divider()
    bc, bx, bn = st.columns(3)
    with bc:
        if st.button("← Cambiar cliente", type="secondary"):
            st.session_state.ped_grid = editado
            st.session_state.ped_paso = 1; st.rerun()
    with bx:
        if st.button("❌ Cancelar pedido", type="secondary"):
            _reset_pedido(); st.rerun()
    with bn:
        if st.button("Revisar y Confirmar →", type="primary"):
            lineas = []
            for r in validas:
                p = prod_dict.get(r["Producto"])
                if p:
                    lineas.append({"nombre": r["Producto"],
                                   "cantidad": r["Cantidad"],
                                   "precio": p["precio"],
                                   "costo":  p["costo"],
                                   "unidad": p["unidad"]})
            if not lineas:
                st.warning("Agregá al menos un producto con cantidad > 0.")
            else:
                st.session_state.ped_grid   = editado
                st.session_state.ped_lineas = lineas
                st.session_state.ped_paso   = 3; st.rerun()

# ── PASO 3 ────────────────────────────────────────────────────────────────────
def _paso3():
    c      = st.session_state.ped_cliente
    fec    = st.session_state.ped_fecha
    lineas = st.session_state.ped_lineas

    st.subheader("✅ Confirmar y ajustar precios")
    st.markdown(
        f"<div style='background:#f1f8f1;border-left:4px solid #2e7d32;"
        f"border-radius:6px;padding:10px 14px;font-size:.93rem;line-height:1.6'>"
        f"👤 <b>{c['nombre']}</b> — {c['empresa']}<br>"
        f"📅 <b>{fec.strftime('%d/%m/%Y')}</b> · "
        f"Sem {fec.isocalendar()[1]} · Crédito {c['credito']} días</div>",
        unsafe_allow_html=True)
    st.caption("Podés ajustar precios solo para este pedido. "
               "Al agregar a la cola el pedido queda pendiente de grabar.")
    st.divider()

    sin_costo = [l["nombre"] for l in lineas if float(l.get("costo", 0)) <= 0]
    if sin_costo:
        st.warning(f"⚠️ Sin costo definido: **{', '.join(sin_costo)}**")

    hdr = st.columns([3.5, 1, 1.8, 1.8, 1.5])
    hdr[0].markdown("**Producto**"); hdr[1].markdown("**Cant.**")
    hdr[2].markdown("**Catálogo**"); hdr[3].markdown("**A cobrar**")
    hdr[4].markdown("**Subtotal**")

    total = 0; precios_fin = []
    for i, l in enumerate(lineas):
        k = f"ped_p3_{i}"
        if k not in st.session_state:
            st.session_state[k] = float(l["precio"])
        r = st.columns([3.5, 1, 1.8, 1.8, 1.5])
        r[0].write(l["nombre"])
        r[1].write(f"{l['cantidad']} {l['unidad']}")
        r[2].markdown(f"<div style='padding-top:8px;color:#888;font-size:.85rem'>"
                      f"Q{l['precio']:,.2f}</div>", unsafe_allow_html=True)
        precio_ed = r[3].number_input("", min_value=0.0,
                                       value=float(st.session_state[k]),
                                       step=0.25, key=k,
                                       label_visibility="collapsed")
        diff = precio_ed - float(l["precio"])
        if abs(diff) > 0.001:
            r[3].caption(f"{'▲' if diff>0 else '▼'} Q{abs(diff):.2f}")
        sub = l["cantidad"] * precio_ed
        r[4].markdown(f"<div style='padding-top:8px;font-weight:bold'>"
                      f"Q{sub:,.2f}</div>", unsafe_allow_html=True)
        total += sub; precios_fin.append(precio_ed)

    st.divider()
    st.markdown(
        f"<div style='background:#e8f5e9;border-radius:8px;padding:12px;"
        f"text-align:center'><b>{len(lineas)} productos · "
        f"Total: Q{total:,.2f}</b></div>", unsafe_allow_html=True)
    st.divider()

    bc, bx, bn = st.columns(3)
    with bc:
        if st.button("← Editar productos", type="secondary"):
            for i in range(len(lineas)):
                st.session_state.pop(f"ped_p3_{i}", None)
            st.session_state.ped_paso = 2; st.rerun()
    with bx:
        if st.button("❌ Cancelar pedido", type="secondary"):
            for i in range(len(lineas)):
                st.session_state.pop(f"ped_p3_{i}", None)
            _reset_pedido(); st.rerun()
    with bn:
        if st.button("➕ Agregar a cola", type="primary"):
            items_fin = [{**l, "precio": precios_fin[i]}
                         for i, l in enumerate(lineas)]
            cola = st.session_state.get(COLA_KEY, [])
            cola.append({
                "id":              len(cola),
                "cliente_nombre":  c["nombre"],
                "fecha":           fec,
                "items":           items_fin,
                "total":           total,
                "display":         f"{c['nombre']} — "
                                   f"{fec.strftime('%d/%m/%Y')} — "
                                   f"Q{total:,.0f}",
            })
            st.session_state[COLA_KEY] = cola
            for i in range(len(lineas)):
                st.session_state.pop(f"ped_p3_{i}", None)
            st.session_state.ped_paso = 4; st.rerun()

# ── PASO 4: COLA ──────────────────────────────────────────────────────────────
def _paso4():
    cola = st.session_state.get(COLA_KEY, [])
    st.success(f"✅ Pedido agregado a la cola.")

    st.markdown(f"### 📋 Cola de pedidos ({len(cola)})")
    st.caption("Los pedidos NO están grabados en Excel aún. "
               "Podés seguir ingresando o grabarlos todos de una vez.")

    for i, pedido in enumerate(cola):
        c1, c2 = st.columns([6, 1])
        c1.markdown(f"✅ **{pedido['display']}**")
        if c2.button("🗑", key=f"del_{pedido['id']}_{i}",
                     help="Quitar de la cola"):
            cola.pop(i)
            st.session_state[COLA_KEY] = cola; st.rerun()

    st.divider()
    total_cola = sum(p["total"] for p in cola)
    st.markdown(
        f"<div style='background:#e8f5e9;border-radius:8px;padding:10px;"
        f"text-align:center;margin:8px 0'>"
        f"<b>{len(cola)} pedido(s) en cola · "
        f"Q{total_cola:,.2f} total</b></div>",
        unsafe_allow_html=True)
    st.divider()

    ba, bg = st.columns(2)
    with ba:
        if st.button("➕ Ingresar otro pedido", type="secondary",
                     use_container_width=True):
            _reset_pedido(); st.rerun()

    with bg:
        lbl = f"📤 Grabar {len(cola)} pedido(s) al Excel"
        if st.button(lbl, type="primary", use_container_width=True,
                     disabled=len(cola) == 0):
            with st.spinner(f"Grabando {len(cola)} pedidos en Drive..."):
                try:
                    res = guardar_pedidos_batch(cola)
                    st.session_state[COLA_KEY] = []
                    st.balloons()
                    st.success(
                        f"🎉 {res['pedidos']} pedido(s) grabados "
                        f"({res['filas']} filas) — "
                        f"un solo ciclo de Drive."
                    )
                    st.info("📊 Refrescá tablas dinámicas en Excel "
                            "(Datos → Actualizar todo).")
                    _reset_pedido()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al grabar: {e}")

# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def mostrar():
    st.markdown("## 🛒 Nuevo Pedido")
    # Botón de regreso al Inicio
    if st.button("🏠 Inicio", key="btn_home_ped", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    _init()

    if not _aviso_costos():
        return

    _mostrar_cola_compacta()

    p = st.session_state.ped_paso
    if p in (1, 2, 3): _pasos()

    if   p == 1: _paso1()
    elif p == 2: _paso2()
    elif p == 3: _paso3()
    elif p == 4: _paso4()
