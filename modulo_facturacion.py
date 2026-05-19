"""
modulo_facturacion.py — Resumen mensual de facturación por cliente
Acumula todos los envíos del mes seleccionado, desglose por semana
y subtotal por producto, con PDF descargable por cliente.
"""
import streamlit as st
from datetime import date
from excel_helper import leer_pedidos
from data_helper  import cargar_clientes
from pdf_helper   import (generar_facturacion_mensual,
                           nombre_archivo_factura, MESES_ES)

# Excluir mismos clientes que el dashboard
EXCLUIR = ["veggi", "chimalt", "wilson"]

def _excluido(nombre): return any(x in nombre.lower() for x in EXCLUIR)


def _construir_datos(pedidos: list, mes: int, año: int) -> dict:
    """
    Agrupa los pedidos del mes por cliente → semana → líneas.
    Retorna dict: {cliente: {semana: {fecha, lineas}, total_mes}}
    """
    resultado = {}

    for p in pedidos:
        if p["status"] == "Cancelado": continue
        if not p["fecha"]:             continue
        if p["fecha"].month != mes:    continue
        if p["fecha"].year  != año:    continue
        if _excluido(p["cliente"]):    continue
        if not p["producto"]:          continue

        cli  = p["cliente"]
        sem  = p["semana"] or p["fecha"].isocalendar()[1]

        if cli not in resultado:
            resultado[cli] = {"por_semana": {}, "total_mes": 0.0}

        if sem not in resultado[cli]["por_semana"]:
            resultado[cli]["por_semana"][sem] = {
                "fecha":  p["fecha"],
                "lineas": [],
            }

        # Usar la fecha más temprana de esa semana como referencia
        if p["fecha"] < resultado[cli]["por_semana"][sem]["fecha"]:
            resultado[cli]["por_semana"][sem]["fecha"] = p["fecha"]

        total_linea = float(p["total"] or
                            float(p["precio"] or 0) * float(p["cantidad"] or 0))
        resultado[cli]["por_semana"][sem]["lineas"].append({
            "producto": p["producto"],
            "cantidad": p["cantidad"],
            "unidad":   p["unidad"],
            "precio":   p["precio"],
            "total":    total_linea,
        })
        resultado[cli]["total_mes"] += total_linea

    # Ordenar líneas de cada semana por nombre de producto
    for cli in resultado:
        for sem in resultado[cli]["por_semana"]:
            resultado[cli]["por_semana"][sem]["lineas"].sort(
                key=lambda x: x["producto"])

    return resultado


def _card_cliente(cli_nombre: str, datos_cli: dict,
                   cliente_info: dict, mes: int, año: int):
    """Muestra el expander de un cliente con desglose semanal y PDF."""
    total = datos_cli["total_mes"]
    iva   = round(total * 0.12 / 1.12, 2)
    isr   = round(total * 0.05 / 1.12, 2)
    sems  = len(datos_cli["por_semana"])

    with st.expander(
        f"**{cli_nombre}**  ·  {sems} semana(s)  ·  "
        f"Total: **Q{total:,.2f}**",
        expanded=False,
    ):
        # Detalle por semana
        for sem_num in sorted(datos_cli["por_semana"].keys()):
            bloque     = datos_cli["por_semana"][sem_num]
            fecha_sem  = bloque["fecha"]
            lineas_sem = bloque["lineas"]
            sub_sem    = sum(l["total"] for l in lineas_sem)

            st.markdown(
                f"<div style='background:#2D7A2D;color:white;padding:4px 10px;"
                f"border-radius:4px;font-size:.82rem;font-weight:bold;"
                f"margin:8px 0 4px 0'>"
                f"Semana {sem_num} · {fecha_sem.strftime('%d/%m/%Y')} · "
                f"Subtotal: Q{sub_sem:,.2f}</div>",
                unsafe_allow_html=True)

            hdr = st.columns([4, 1.2, 1.5, 1.5])
            hdr[0].markdown("**Producto**"); hdr[1].markdown("**Cant.**")
            hdr[2].markdown("**Precio**");   hdr[3].markdown("**Total**")

            for l in lineas_sem:
                r = st.columns([4, 1.2, 1.5, 1.5])
                r[0].write(l["producto"])
                r[1].write(f"{l['cantidad']:g} {l['unidad']}")
                r[2].write(f"Q{l['precio']:,.2f}")
                r[3].write(f"Q{l['total']:,.2f}")

        st.divider()

        # Resumen por producto
        st.markdown("**Resumen por producto:**")
        prod_agg = {}
        for sem in datos_cli["por_semana"].values():
            for l in sem["lineas"]:
                prod = l["producto"]
                if prod not in prod_agg:
                    prod_agg[prod] = {"cantidad": 0, "total": 0.0,
                                       "unidad": l["unidad"]}
                prod_agg[prod]["cantidad"] += l["cantidad"]
                prod_agg[prod]["total"]    += l["total"]

        hdr2 = st.columns([4, 1.5, 1.5])
        hdr2[0].markdown("**Producto**")
        hdr2[1].markdown("**Unidades**")
        hdr2[2].markdown("**Total**")
        for prod, agg in sorted(prod_agg.items()):
            r2 = st.columns([4, 1.5, 1.5])
            r2[0].write(prod)
            r2[1].write(f"{agg['cantidad']:,.1f} {agg['unidad']}")
            r2[2].write(f"Q{agg['total']:,.2f}")

        st.divider()

        # Totales
        tc1, tc2, tc3 = st.columns(3)
        tc1.metric("Total del mes", f"Q{total:,.2f}")
        tc2.metric("IVA (12%)",     f"Q{iva:,.2f}")
        tc3.metric("ISR retenido",  f"Q{isr:,.2f}")

        st.markdown(
            f"<div style='background:#e8f5e9;border-radius:8px;padding:10px;"
            f"text-align:center;margin:8px 0'>"
            f"<b>TOTAL A FACTURAR: Q{total:,.2f}</b></div>",
            unsafe_allow_html=True)

        # PDF
        try:
            pdf_bytes = generar_facturacion_mensual(
                cliente=cliente_info,
                mes=mes, año=año,
                por_semana=datos_cli["por_semana"],
            )
            st.download_button(
                label="📄 Descargar PDF de Facturación",
                data=pdf_bytes,
                file_name=nombre_archivo_factura(cli_nombre, mes, año),
                mime="application/pdf",
                key=f"fact_pdf_{cli_nombre}_{mes}_{año}",
                type="primary",
            )
        except Exception as e:
            st.error(f"Error generando PDF: {e}")


def mostrar():
    st.markdown("## 🧾 Facturación Mensual")

    with st.spinner("Cargando pedidos..."):
        todos    = leer_pedidos()
        cli_list = cargar_clientes()

    cli_map = {c["nombre"]: c for c in cli_list}

    # ── Selectores ────────────────────────────────────────────────────────────
    hoy = date.today()
    meses_disp = [(m, f"{MESES_ES[m]} {y}")
                  for y in range(hoy.year, hoy.year - 2, -1)
                  for m in range(12, 0, -1)
                  if (y, m) <= (hoy.year, hoy.month)]

    s1, s2, s3 = st.columns(3)
    with s1:
        mes_sel_lbl = st.selectbox(
            "Mes", [lbl for _, lbl in meses_disp],
            index=0, key="fact_mes")
        mes_sel = next(m for m, lbl in meses_disp if lbl == mes_sel_lbl)
        año_sel = int(mes_sel_lbl.split()[-1])

    with s2:
        clientes_disp = sorted({
            p["cliente"] for p in todos
            if p["fecha"] and p["fecha"].month == mes_sel
            and p["fecha"].year == año_sel
            and p["status"] != "Cancelado"
            and not _excluido(p["cliente"])
        })
        cli_filtro = st.selectbox(
            "Cliente", ["Todos"] + clientes_disp, key="fact_cli")

    with s3:
        st.markdown("&nbsp;")
        st.markdown(
            f"<div style='padding-top:28px;font-size:.85rem;color:#555'>"
            f"Período: <b>{MESES_ES[mes_sel]} {año_sel}</b></div>",
            unsafe_allow_html=True)

    st.divider()

    # ── Construir datos ───────────────────────────────────────────────────────
    datos = _construir_datos(todos, mes_sel, año_sel)

    if cli_filtro != "Todos":
        datos = {k: v for k, v in datos.items() if k == cli_filtro}

    if not datos:
        st.info(f"No hay pedidos para {MESES_ES[mes_sel]} {año_sel}.")
        return

    # ── Resumen global del mes ────────────────────────────────────────────────
    total_global = sum(v["total_mes"] for v in datos.values())
    st.markdown(
        f"<div style='background:#e8f5e9;border-radius:8px;padding:10px;"
        f"text-align:center;margin:4px 0 12px 0'>"
        f"<b>{len(datos)} cliente(s)  ·  "
        f"Total del mes: Q{total_global:,.2f}</b></div>",
        unsafe_allow_html=True)

    # ── Cards por cliente (orden por total desc) ──────────────────────────────
    for cli_nombre, datos_cli in sorted(datos.items(),
                                         key=lambda x: x[1]["total_mes"],
                                         reverse=True):
        cliente_info = cli_map.get(cli_nombre, {"nombre": cli_nombre})
        _card_cliente(cli_nombre, datos_cli, cliente_info, mes_sel, año_sel)
