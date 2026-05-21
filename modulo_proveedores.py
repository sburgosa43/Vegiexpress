"""
modulo_proveedores.py — Lista de Compras a Proveedores
- Proveedor desde catálogo (no desde pedidos)
- Columna editable "A Comprar" (número o "P" de pendiente)
- Costo estimado solo en pantalla
- Multi-select por proveedor + PDF consolidado
"""
import streamlit as st
from datetime import date
from excel_helper import leer_pedidos
from data_helper  import cargar_productos
from pdf_helper   import generar_lista_compras

EXCLUIR_CLIENTES = ["veggi", "chimalt", "wilson"]


def _excluido(nombre):
    return any(x in nombre.lower() for x in EXCLUIR_CLIENTES)


def _val_comprar(v: str):
    """Interpreta el valor de A Comprar. Retorna (es_valido, es_pendiente, cantidad)."""
    if not v or v.strip() == "" or v.strip() == "0":
        return False, False, 0.0
    if v.strip().upper() == "P":
        return True, True, 0.0
    try:
        n = float(v.strip().replace(",", "."))
        return (n > 0), False, n
    except ValueError:
        return False, False, 0.0


def mostrar():
    st.markdown("## 📦 Pedidos a Proveedores")
    if st.button("🏠 Inicio", key="btn_home_prov", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    # ── Selector de semana ────────────────────────────────────────────────────
    hoy     = date.today()
    sem_hoy = hoy.isocalendar()[1]
    año_hoy = hoy.year

    c1, c2, c3 = st.columns(3)
    semana = c1.number_input("Semana", min_value=1, max_value=53,
                              value=sem_hoy, step=1, key="prov_sem")
    año    = c2.selectbox("Año", list(range(año_hoy, año_hoy-3, -1)), key="prov_año")
    with c3:
        st.markdown("&nbsp;")
        cargar = st.button("🔍 Cargar semana", type="primary",
                           use_container_width=True)

    # Llave de estado para esta semana
    state_key = f"compras_{semana}_{año}"

    if cargar:
        # Reset A Comprar al cambiar de semana
        st.session_state.pop(state_key, None)
        st.session_state["prov_datos"] = None

    # ── Carga de datos ────────────────────────────────────────────────────────
    if cargar or st.session_state.get("prov_datos"):
        if cargar or not st.session_state.get("prov_datos"):
            with st.spinner("Cargando pedidos y catálogo..."):
                todos   = leer_pedidos()
                catalog = cargar_productos(False)
                catalog_ant = cargar_productos(True)

            # Mapa producto → {proveedor, costo} desde catálogo (case-insensitive)
            prod_map = {}
            for p in catalog + catalog_ant:
                prod_map[p["nombre"].lower()] = {
                    "proveedor": p.get("proveedor",""),
                    "costo":     float(p.get("costo",0)),
                }

            # Filtrar pedidos de la semana
            pedidos_sem = [p for p in todos
                           if p["semana"] == semana and p["año"] == año
                           and p["status"] != "Cancelado"
                           and float(p.get("cantidad") or 0) > 0
                           and not _excluido(p["cliente"])]

            if not pedidos_sem:
                st.warning(f"No hay pedidos activos para la semana {semana}/{año}.")
                return

            # Agregar por proveedor → producto (proveedor desde catálogo)
            por_prov = {}
            sin_prov = {}

            for p in pedidos_sem:
                info_cat  = prod_map.get(p["producto"].lower(), {})
                prov      = info_cat.get("proveedor","").strip()
                prod      = p["producto"]
                cant      = float(p["cantidad"])
                unidad    = p.get("unidad","")
                costo_cat = info_cat.get("costo", 0)

                dest = por_prov if prov else sin_prov
                if not prov: prov = "SIN PROVEEDOR"

                if prov not in dest:
                    dest[prov] = {}
                key = (prod, unidad, costo_cat)
                dest[prov][key] = dest[prov].get(key, 0) + cant

            # Convertir a lista ordenada
            def _to_list(d):
                return {
                    prov: [{"producto": k[0], "unidad": k[1],
                            "costo": k[2], "cantidad": v}
                           for k, v in sorted(items.items())]
                    for prov, items in sorted(d.items())
                }

            datos = {**_to_list(por_prov)}
            if sin_prov:
                datos.update(_to_list(sin_prov))

            st.session_state["prov_datos"] = datos
            if state_key not in st.session_state:
                st.session_state[state_key] = {}

        datos = st.session_state["prov_datos"]
        compras = st.session_state.setdefault(state_key, {})

        proveedores = list(datos.keys())

        # ── Multi-select de proveedores ───────────────────────────────────────
        st.markdown(f"**{len(proveedores)} proveedor(es) · Semana {semana}/{año}**")
        sel_prov = st.multiselect(
            "Seleccioná proveedores para incluir en el PDF:",
            proveedores, default=proveedores, key="prov_multisel")
        st.divider()

        # ── Sección por proveedor ─────────────────────────────────────────────
        total_gasto_est = 0.0

        for prov in proveedores:
            items = datos[prov]
            color = "#2D7A2D" if prov != "SIN PROVEEDOR" else "#E65100"

            # Header del proveedor
            st.markdown(
                f"<div style='background:{color};color:white;padding:6px 12px;"
                f"border-radius:6px;font-weight:bold;font-size:.9rem;"
                f"margin:10px 0 4px 0'>📦 {prov}</div>",
                unsafe_allow_html=True)

            # Encabezado columnas
            h = st.columns([3.5, 1.2, 1.3, 1.5, 2.0])
            for col, txt in zip(h, ["Producto","Unidad","Pedido",
                                     "A Comprar","Est. Costo"]):
                col.markdown(f"<small><b>{txt}</b></small>",
                             unsafe_allow_html=True)

            gasto_prov = 0.0
            for i, item in enumerate(items):
                prod      = item["producto"]
                unidad    = item["unidad"]
                cant_ped  = item["cantidad"]
                costo_cat = item["costo"]
                ck        = f"{prov}||{prod}"

                r = st.columns([3.5, 1.2, 1.3, 1.5, 2.0])
                r[0].write(prod)
                r[1].write(unidad)
                r[2].write(f"{cant_ped:,.1f}")

                val_prev = compras.get(ck, "")
                val = r[3].text_input("", value=val_prev,
                                      placeholder="cant / P",
                                      key=f"cin_{state_key}_{prov}_{i}",
                                      label_visibility="collapsed")
                compras[ck] = val

                valido, pendiente, n = _val_comprar(val)
                if valido and not pendiente and costo_cat > 0:
                    est = n * costo_cat
                    gasto_prov   += est
                    total_gasto_est += est
                    r[4].markdown(
                        f"<div style='padding-top:6px;font-size:.82rem'>"
                        f"Q{est:,.2f}</div>", unsafe_allow_html=True)
                elif pendiente:
                    r[4].markdown(
                        "<div style='padding-top:6px;font-size:.82rem;"
                        "color:#E65100'>Pendiente</div>", unsafe_allow_html=True)

            if gasto_prov > 0:
                st.markdown(
                    f"<div style='text-align:right;font-size:.8rem;"
                    f"color:#2D7A2D;margin:2px 0 6px 0'>"
                    f"<b>Estimado {prov}: Q{gasto_prov:,.2f}</b></div>",
                    unsafe_allow_html=True)

        st.session_state[state_key] = compras

        # Total estimado global
        if total_gasto_est > 0:
            st.markdown(
                f"<div style='background:#e8f5e9;border-radius:8px;"
                f"padding:10px;text-align:center;margin:8px 0'>"
                f"<b>💰 Estimado total de compras: Q{total_gasto_est:,.2f}</b>"
                f"<br><small style='color:#888'>Solo pantalla — no se imprime</small>"
                f"</div>", unsafe_allow_html=True)

        st.divider()

        # ── Generador de PDF ──────────────────────────────────────────────────
        if not sel_prov:
            st.info("Seleccioná al menos un proveedor para generar el PDF.")
            return

        if st.button(f"📄 Generar PDF ({len(sel_prov)} proveedor(es))",
                     type="primary", use_container_width=True):
            # Construir datos para PDF filtrando por selección y A Comprar
            datos_pdf = {}
            for prov in sel_prov:
                items_pdf = []
                for item in datos[prov]:
                    prod = item["producto"]
                    ck   = f"{prov}||{prod}"
                    val  = compras.get(ck, "")
                    valido, pendiente, n = _val_comprar(val)
                    if not valido: continue
                    items_pdf.append({
                        "producto":   item["producto"],
                        "unidad":     item["unidad"],
                        "cantidad":   item["cantidad"],
                        "a_comprar":  "P" if pendiente else f"{n:g}",
                    })
                if items_pdf:
                    datos_pdf[prov] = items_pdf

            if not datos_pdf:
                st.warning("No hay líneas con cantidad ingresada. "
                           "Completá la columna 'A Comprar'.")
                return

            with st.spinner("Generando PDF compacto..."):
                pdf_bytes = generar_lista_compras(datos_pdf, semana, año)

            nombre = f"Compras_Sem{semana}_{año}.pdf"
            st.download_button("📥 Descargar PDF",
                               data=pdf_bytes, file_name=nombre,
                               mime="application/pdf",
                               key="prov_dl", type="primary",
                               use_container_width=True)
