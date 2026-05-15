"""
modulo_pedidos.py — Ingreso de nuevo pedido (wizard 4 pasos)
"""
import streamlit as st
import pandas as pd
from datetime import date
from data_helper  import cargar_clientes, cargar_productos
from order_helper import guardar_pedido

AVISO_KEY = "costos_revisados"


def _init():
    for k, v in {"ped_paso":1,"ped_cliente":None,"ped_fecha":date.today(),
                 "ped_lineas":[],"ped_grid":None,"ped_nfilas":15,"ped_n":0}.items():
        if k not in st.session_state:
            st.session_state[k] = v

def _reset():
    for k in ["ped_paso","ped_cliente","ped_fecha","ped_lineas",
              "ped_grid","ped_nfilas","ped_n"]:
        st.session_state.pop(k, None)
    _init()

def _pasos():
    p = st.session_state.ped_paso
    cols = st.columns(3)
    for i, (col, lbl) in enumerate(zip(cols,["👤 Cliente","🛒 Productos","✅ Confirmar"]),1):
        with col:
            if i==p:      st.markdown(f"**{lbl} ←**")
            elif i<p:     st.markdown(f"~~{lbl}~~ ✔")
            else:         st.markdown(lbl)
    st.divider()

# ── AVISO DE COSTOS ───────────────────────────────────────────────────────────
def _aviso_costos() -> bool:
    """
    Muestra el aviso de revisión de costos la primera vez por sesión.
    Retorna True si el usuario ya confirmó, False si debe confirmar primero.
    """
    if st.session_state.get(AVISO_KEY):
        # Ya confirmado — mostrar pequeño recordatorio con opción de re-ver
        estado = "sin cambios" if st.session_state[AVISO_KEY] == "sin_cambios" else "con cambios"
        col_r, col_btn = st.columns([5, 1])
        col_r.caption(f"✔️ Costos verificados ({estado}) · "
                      "¿Necesitás revisar de nuevo?")
        if col_btn.button("🔄", help="Ver aviso de costos", key="reset_aviso"):
            del st.session_state[AVISO_KEY]
            st.rerun()
        return True

    # ── Aviso principal ───────────────────────────────────────────────────────
    st.markdown("""
    <div style='background:#fff8e1;border:1px solid #f9a825;border-left:5px solid #f9a825;
                border-radius:8px;padding:18px 22px;margin:12px 0'>
        <div style='font-size:1.1rem;font-weight:bold;margin-bottom:10px'>
            ⚠️ Antes de ingresar el pedido
        </div>
        <div style='font-size:.95rem;line-height:1.7'>
            Revisá si hubo <b>variaciones en los costos de compra</b> desde tu última
            visita al proveedor.<br>
            Si hay cambios, actualizalos en <b>📦 Productos</b> antes de continuar.
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📦 Ir a Productos", type="secondary", use_container_width=True):
            st.session_state["nav"] = "📦 Productos (Nuevos y Mantenimiento)"
            st.rerun()
    with col2:
        if st.button("✅ No hay cambios,
continuar", type="primary",
                     use_container_width=True):
            st.session_state[AVISO_KEY] = "sin_cambios"
            st.rerun()
    with col3:
        if st.button("✔️ Ya actualicé,
continuar", type="primary",
                     use_container_width=True):
            st.session_state[AVISO_KEY] = "con_cambios"
            st.rerun()

    return False

# ── PASO 1 ────────────────────────────────────────────────────────────────────
def _paso1():
    st.subheader("👤 Cliente y fecha")
    clientes  = cargar_clientes()
    ver_todos = st.checkbox("Incluir pendientes", value=False)
    lista     = clientes if ver_todos else [c for c in clientes if c["activo"]]
    nombre    = st.selectbox("Cliente", [c["nombre"] for c in lista],
                              index=None, placeholder="Escribí para buscar...")
    if nombre:
        c = next(x for x in lista if x["nombre"] == nombre)
        st.markdown(
            f"<div style='background:#f1f8f1;border-left:4px solid #2e7d32;border-radius:6px;"
            f"padding:10px 14px;font-size:.93rem;line-height:1.6'>"
            f"📍 <b>{c['direccion']}</b> · 🏢 {c['empresa']} · 💳 NIT: {c['nit']}<br>"
            f"🏷️ {c['tipo']} · 📅 Crédito: {c['credito']} días · 📌 {c['codigo_lugar']}"
            f"{'&nbsp;🔖 <b>Precios Antigua</b>' if c['es_antigua'] else ''}"
            f"</div>", unsafe_allow_html=True)
        fecha = st.date_input("📅 Fecha de entrega", value=date.today(), min_value=date.today())
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
        extra = pd.DataFrame({"Producto":[""]*(n-len(st.session_state.ped_grid)),
                              "Cantidad":[0.0]*(n-len(st.session_state.ped_grid))})
        st.session_state.ped_grid = pd.concat([st.session_state.ped_grid, extra],
                                               ignore_index=True)

    editado = st.data_editor(
        st.session_state.ped_grid,
        column_config={
            "Producto": st.column_config.SelectboxColumn(
                "Producto", options=nombres, required=False, width="large"),
            "Cantidad": st.column_config.NumberColumn(
                "Cantidad", min_value=0.0, step=0.5, format="%.1f", width="small"),
        },
        num_rows="fixed", use_container_width=True, hide_index=False,
        key="ped_grid_editor",
    )

    # Warning de productos sin costo
    validas   = [r for _, r in editado.iterrows() if r["Producto"] and r["Cantidad"] > 0]
    sin_costo = [r["Producto"] for r in validas
                 if r["Producto"] in prod_dict and prod_dict[r["Producto"]]["costo"] <= 0]
    if sin_costo:
        st.warning(f"⚠️ Sin costo definido: **{', '.join(sin_costo)}**. "
                   "Actualizalos en 📦 Productos.")

    c1, c2, c3 = st.columns([2, 2, 3])
    with c1:
        if st.button("+ 5 líneas"):
            st.session_state.ped_grid   = editado
            st.session_state.ped_nfilas = len(editado) + 5
            st.rerun()
    with c2:
        if st.button("+ 10 líneas"):
            st.session_state.ped_grid   = editado
            st.session_state.ped_nfilas = len(editado) + 10
            st.rerun()
    with c3:
        if st.button("🗑 Limpiar", type="secondary"):
            st.session_state.ped_grid   = None
            st.session_state.ped_nfilas = 15
            st.rerun()

    if validas:
        total_est = sum(r["Cantidad"] * prod_dict[r["Producto"]]["precio"]
                        for r in validas if r["Producto"] in prod_dict)
        st.markdown(
            f"<div style='background:#e8f5e9;border-radius:8px;padding:10px;"
            f"text-align:center;margin:8px 0'>"
            f"<b>{len(validas)} productos</b> · Total estimado: <b>Q{total_est:,.2f}</b>"
            f"</div>", unsafe_allow_html=True)

    st.divider()
    bc, bx, bn = st.columns(3)
    with bc:
        if st.button("← Cambiar cliente", type="secondary"):
            st.session_state.ped_grid = editado
            st.session_state.ped_paso = 1
            st.rerun()
    with bx:
        if st.button("❌ Cancelar pedido", type="secondary"):
            _reset()
            st.rerun()
    with bn:
        if st.button("Revisar y Confirmar →", type="primary"):
            lineas = []
            for r in validas:
                p = prod_dict.get(r["Producto"])
                if p:
                    lineas.append({
                        "nombre":   r["Producto"],
                        "cantidad": r["Cantidad"],
                        "precio":   p["precio"],
                        "costo":    p["costo"],    # incluir costo del catálogo
                        "unidad":   p["unidad"],
                    })
            if not lineas:
                st.warning("Agregá al menos un producto con cantidad > 0.")
            else:
                st.session_state.ped_grid   = editado
                st.session_state.ped_lineas = lineas
                st.session_state.ped_paso   = 3
                st.rerun()

# ── PASO 3 ────────────────────────────────────────────────────────────────────
def _paso3():
    c      = st.session_state.ped_cliente
    fec    = st.session_state.ped_fecha
    lineas = st.session_state.ped_lineas

    st.subheader("✅ Confirmar y ajustar precios")
    st.markdown(
        f"<div style='background:#f1f8f1;border-left:4px solid #2e7d32;border-radius:6px;"
        f"padding:10px 14px;font-size:.93rem;line-height:1.6'>"
        f"👤 <b>{c['nombre']}</b> — {c['empresa']}<br>"
        f"📅 <b>{fec.strftime('%d/%m/%Y')}</b> · Sem {fec.isocalendar()[1]} · "
        f"Crédito {c['credito']} días · NIT: {c['nit']}"
        f"</div>", unsafe_allow_html=True)
    st.caption("Los precios vienen del catálogo. Podés ajustar cualquiera solo para este pedido.")
    st.divider()

    # Warning si hay productos sin costo
    sin_costo = [l["nombre"] for l in lineas if float(l.get("costo", 0)) <= 0]
    if sin_costo:
        st.warning(f"⚠️ Sin costo definido: **{', '.join(sin_costo)}**. "
                   "El margen no se calculará correctamente.")

    hdr = st.columns([3.5, 1, 1.8, 1.8, 1.5])
    hdr[0].markdown("**Producto**"); hdr[1].markdown("**Cant.**")
    hdr[2].markdown("**Catálogo**"); hdr[3].markdown("**A cobrar**"); hdr[4].markdown("**Subtotal**")

    total        = 0
    precios_fin  = []

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
        total += sub
        precios_fin.append(precio_ed)

    st.divider()
    st.markdown(
        f"<div style='background:#e8f5e9;border-radius:8px;padding:12px;text-align:center'>"
        f"<b>{len(lineas)} productos · Total: Q{total:,.2f}</b></div>",
        unsafe_allow_html=True)
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
            _reset(); st.rerun()
    with bn:
        if st.button("💾 Guardar en Excel", type="primary"):
            items_fin = [{**l, "precio": precios_fin[i]} for i, l in enumerate(lineas)]
            with st.spinner("Guardando en Google Drive..."):
                try:
                    n = guardar_pedido(nombre_cliente=c["nombre"],
                                       fecha_entrega=fec, items=items_fin)
                    for i in range(len(lineas)):
                        st.session_state.pop(f"ped_p3_{i}", None)
                    st.session_state.ped_n    = n
                    st.session_state.ped_paso = 4
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ {e}")

# ── PASO 4 ────────────────────────────────────────────────────────────────────
def _paso4():
    c   = st.session_state.ped_cliente
    fec = st.session_state.ped_fecha
    n   = st.session_state.ped_n
    tot = sum(l["cantidad"] * l["precio"] for l in st.session_state.ped_lineas)
    st.success("### 🎉 ¡Pedido guardado!")
    st.balloons()
    st.markdown(f"**{c['nombre']}** · {fec.strftime('%d/%m/%Y')} · {n} filas guardadas")
    st.info("📊 Refrescá las tablas dinámicas en Excel (Datos → Actualizar todo).")
    if st.button("➕ Nuevo pedido", type="primary"):
        _reset(); st.rerun()

# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def mostrar():
    st.markdown("## 🛒 Nuevo Pedido")
    _init()
    if not _aviso_costos():
        return
    p = st.session_state.ped_paso
    if p in (1, 2, 3): _pasos()
    if   p == 1: _paso1()
    elif p == 2: _paso2()
    elif p == 3: _paso3()
    elif p == 4: _paso4()
