"""
modulo_pedidos.py — Ingreso de nuevo pedido (wizard 4 pasos)
"""
import streamlit as st
import pandas as pd
from datetime import date
from data_helper  import cargar_clientes, cargar_productos
from order_helper import guardar_pedido


def _init():
    defaults = {
        "ped_paso": 1, "ped_cliente": None,
        "ped_fecha": date.today(), "ped_lineas": [],
        "ped_grid": None, "ped_nfilas": 15,
        "ped_guardado_n": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def _reset():
    for k in ["ped_paso","ped_cliente","ped_fecha","ped_lineas",
              "ped_grid","ped_nfilas","ped_guardado_n"]:
        if k in st.session_state:
            del st.session_state[k]
    _init()

def _pasos():
    paso   = st.session_state.ped_paso
    labels = ["👤 Cliente", "🛒 Productos", "✅ Confirmar"]
    cols   = st.columns(3)
    for i, (col, lbl) in enumerate(zip(cols, labels), 1):
        with col:
            if i == paso:
                st.markdown(f"**{lbl} ←**")
            elif i < paso:
                st.markdown(f"~~{lbl}~~ ✔")
            else:
                st.markdown(lbl)
    st.divider()

# ── PASO 1 ────────────────────────────────────────────────────────────────────
def _paso1():
    st.subheader("👤 Cliente y fecha")
    clientes = cargar_clientes()
    ver_todos = st.checkbox("Incluir clientes pendientes", value=False)
    lista = clientes if ver_todos else [c for c in clientes if c["activo"]]

    nombre = st.selectbox("Cliente", [c["nombre"] for c in lista],
                          index=None, placeholder="Escribí para buscar...")
    if nombre:
        c = next(x for x in lista if x["nombre"] == nombre)
        st.markdown(f"""
        <div style='background:#f1f8f1;border-left:4px solid #2e7d32;border-radius:6px;
                    padding:10px 14px;margin:6px 0;font-size:.93rem;line-height:1.6'>
        📍 <b>{c['direccion']}</b> · 🏢 {c['empresa']} · 💳 NIT: {c['nit']}<br>
        🏷️ {c['tipo']} · 📅 Crédito: {c['credito']} días · 📌 {c['codigo_lugar']}
        {"&nbsp;🔖 <b>Precios Antigua</b>" if c['es_antigua'] else ""}
        </div>""", unsafe_allow_html=True)
        fecha  = st.date_input("📅 Fecha de entrega", value=date.today(), min_value=date.today())
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
            {"Producto": [""] * n, "Cantidad": [0.0] * n})
    elif len(st.session_state.ped_grid) < n:
        extra = pd.DataFrame(
            {"Producto": [""] * (n - len(st.session_state.ped_grid)),
             "Cantidad": [0.0] * (n - len(st.session_state.ped_grid))})
        st.session_state.ped_grid = pd.concat(
            [st.session_state.ped_grid, extra], ignore_index=True)

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

    validas = [r for _, r in editado.iterrows() if r["Producto"] and r["Cantidad"] > 0]
    if validas:
        total_est = sum(r["Cantidad"] * prod_dict[r["Producto"]]["precio"]
                        for r in validas if r["Producto"] in prod_dict)
        st.markdown(
            f"<div style='background:#e8f5e9;border-radius:8px;padding:12px;"
            f"text-align:center;margin:10px 0'>"
            f"<b>{len(validas)} productos</b> · Total estimado: <b>Q{total_est:,.2f}</b>"
            f"</div>", unsafe_allow_html=True)

    st.divider()
    bc, bn = st.columns(2)
    with bc:
        if st.button("← Cambiar cliente", type="secondary"):
            st.session_state.ped_grid = editado
            st.session_state.ped_paso = 1
            st.rerun()
    with bn:
        if st.button("Revisar y Confirmar →", type="primary"):
            lineas = []
            for r in validas:
                p = prod_dict.get(r["Producto"])
                if p:
                    lineas.append({"nombre": r["Producto"], "cantidad": r["Cantidad"],
                                   "precio": p["precio"], "unidad": p["unidad"]})
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
    st.subheader("✅ Confirmar pedido")
    st.markdown(
        f"<div style='background:#f1f8f1;border-left:4px solid #2e7d32;border-radius:6px;"
        f"padding:10px 14px;font-size:.93rem;line-height:1.6'>"
        f"👤 <b>{c['nombre']}</b> — {c['empresa']}<br>"
        f"📅 <b>{fec.strftime('%d/%m/%Y')}</b> · Semana {fec.isocalendar()[1]} · "
        f"Crédito {c['credito']} días<br>"
        f"📍 {c['direccion']} · NIT: {c['nit']}"
        f"</div>", unsafe_allow_html=True)
    st.divider()

    hdr = st.columns([4, 1, 1.5])
    hdr[0].markdown("**Producto**"); hdr[1].markdown("**Cant.**"); hdr[2].markdown("**Precio est.**")
    total = 0
    for l in lineas:
        sub = l["cantidad"] * l["precio"]
        r   = st.columns([4, 1, 1.5])
        r[0].write(l["nombre"]); r[1].write(f"{l['cantidad']} {l['unidad']}"); r[2].write(f"Q{sub:,.2f}")
        total += sub

    st.divider()
    st.markdown(
        f"<div style='background:#e8f5e9;border-radius:8px;padding:12px;text-align:center'>"
        f"<b>{len(lineas)} productos</b> · Total estimado <b>Q{total:,.2f}</b><br>"
        f"<small>El precio final lo calculan las fórmulas de Excel al abrir el archivo</small>"
        f"</div>", unsafe_allow_html=True)
    st.divider()

    bc, bn = st.columns(2)
    with bc:
        if st.button("← Editar", type="secondary"):
            st.session_state.ped_paso = 2; st.rerun()
    with bn:
        if st.button("💾 Guardar en Excel", type="primary"):
            with st.spinner("Guardando en Google Drive..."):
                try:
                    n = guardar_pedido(nombre_cliente=c["nombre"],
                                       fecha_entrega=fec, items=lineas)
                    st.session_state.ped_guardado_n = n
                    st.session_state.ped_paso       = 4
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ {e}")

# ── PASO 4 ────────────────────────────────────────────────────────────────────
def _paso4():
    c  = st.session_state.ped_cliente
    fec = st.session_state.ped_fecha
    n  = st.session_state.ped_guardado_n
    st.success("### 🎉 ¡Pedido guardado!")
    st.balloons()
    st.markdown(f"**{c['nombre']}** · {fec.strftime('%d/%m/%Y')} · {n} filas guardadas")
    st.info("📊 Acordate de refrescar las tablas dinámicas en Excel (Datos → Actualizar todo).")
    if st.button("➕ Nuevo pedido", type="primary"):
        _reset(); st.rerun()

# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def mostrar():
    st.markdown("## 🛒 Nuevo Pedido")
    _init()
    p = st.session_state.ped_paso
    if p in (1, 2, 3): _pasos()
    if   p == 1: _paso1()
    elif p == 2: _paso2()
    elif p == 3: _paso3()
    elif p == 4: _paso4()
