"""
modulo_proveedores.py — Lista de Compras a Proveedores
Agrega pedidos de la semana seleccionada por proveedor y genera PDF compacto.
"""
import streamlit as st
from datetime import date
from excel_helper import leer_pedidos
from pdf_helper   import generar_lista_compras


def mostrar():
    st.markdown("## 📦 Pedidos a Proveedores")
    if st.button("🏠 Inicio", key="btn_home_prov", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    st.markdown("Agrega los pedidos de clientes por proveedor para generar "
                "tu lista de compra semanal.")

    # Selectores de semana
    hoy     = date.today()
    sem_act = hoy.isocalendar()[1]
    año_act = hoy.year

    c1, c2, c3 = st.columns(3)
    with c1:
        semana = st.number_input("Semana", min_value=1, max_value=53,
                                  value=sem_act, step=1, key="prov_sem")
    with c2:
        año = st.selectbox("Año",
                            list(range(año_act, año_act - 3, -1)),
                            key="prov_año")
    with c3:
        st.markdown("&nbsp;")
        generar = st.button("🔍 Generar lista", type="primary",
                             use_container_width=True)

    if not generar:
        st.info("Seleccioná la semana y hacé clic en **Generar lista**.")
        return

    with st.spinner("Cargando pedidos..."):
        todos = leer_pedidos()

    pedidos_sem = [p for p in todos
                   if p["semana"] == semana and p["año"] == año
                   and p["status"] != "Cancelado"
                   and p["cantidad"] and p["cantidad"] > 0]

    if not pedidos_sem:
        st.warning(f"No hay pedidos activos para la semana {semana}/{año}.")
        return

    # Agregar por proveedor → producto → cantidad
    por_proveedor: dict = {}
    sin_proveedor: list = []

    for p in pedidos_sem:
        prov = str(p.get("proveedor", "")).strip()
        prod = p["producto"]
        cant = float(p["cantidad"] or 0)
        uni  = p["unidad"]

        if not prov:
            sin_proveedor.append(p)
            continue

        if prov not in por_proveedor:
            por_proveedor[prov] = {}

        key = (prod, uni)
        if key not in por_proveedor[prov]:
            por_proveedor[prov][key] = 0.0
        por_proveedor[prov][key] += cant

    # Convertir a lista de dicts para el PDF
    por_proveedor_lista = {}
    for prov, prods in sorted(por_proveedor.items()):
        por_proveedor_lista[prov] = [
            {"producto": prod, "unidad": uni, "cantidad": cant}
            for (prod, uni), cant in sorted(prods.items())
        ]

    # Resumen en pantalla
    total_items = sum(len(v) for v in por_proveedor_lista.values())
    st.success(f"**Semana {semana}/{año}** — "
               f"{len(por_proveedor_lista)} proveedor(es) · "
               f"{total_items} producto(s) distintos")

    for prov, items in sorted(por_proveedor_lista.items()):
        color = "#2D7A2D"
        st.markdown(
            f"<div style='border-left:4px solid {color};padding:3px 10px;"
            f"border-radius:4px;font-weight:bold;font-size:.88rem;"
            f"margin:8px 0 4px 0'>📦 {prov}</div>",
            unsafe_allow_html=True)
        hdr = st.columns([4, 1.5, 1.5, 1.5])
        hdr[0].markdown("**Producto**"); hdr[1].markdown("**Unidad**")
        hdr[2].markdown("**Cantidad**"); hdr[3].markdown("**A Comprar**")
        for item in items:
            r = st.columns([4, 1.5, 1.5, 1.5])
            r[0].write(item["producto"]); r[1].write(item["unidad"])
            r[2].write(f"{item['cantidad']:,.1f}"); r[3].write("________")

    if sin_proveedor:
        with st.expander(f"⚠️ Sin proveedor asignado ({len(sin_proveedor)} líneas)",
                         expanded=False):
            for p in sin_proveedor:
                st.write(f"• {p['producto']} — {p['cantidad']} {p['unidad']}")
        st.caption("Asigná proveedor en Módulo Productos para incluirlos en la lista.")

    st.divider()

    # PDF
    if st.button("📄 Generar PDF de Lista de Compras", type="primary",
                 use_container_width=True):
        with st.spinner("Generando PDF..."):
            pdf_bytes = generar_lista_compras(por_proveedor_lista, semana, año)
        nombre = f"ListaCompras_Sem{semana}_{año}.pdf"
        st.download_button("📥 Descargar PDF", data=pdf_bytes,
                            file_name=nombre, mime="application/pdf",
                            key="prov_dl", type="primary",
                            use_container_width=True)
