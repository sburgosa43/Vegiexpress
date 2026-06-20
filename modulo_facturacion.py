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
from config       import (ZONAS_MAP, COLORES_ZONA, ISR_UMBRAL,
                           calcular_liquido, excluido_dashboard)

# Excluir mismos clientes que el dashboard

# ZONAS_MAP y COLORES_ZONA vienen de config.py
# _excluido eliminado — todos los clientes aparecen en facturación

def _zona_cliente(c: dict) -> str:
    for zona, cods in ZONAS_MAP.items():
        if c.get("codigo_lugar","") in cods:
            return zona
    return "Sin zona"


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
            "fecha":    p["fecha"],
            "cantidad": p["cantidad"],
            "unidad":   p["unidad"],
            "precio":   p["precio"],
            "total":    total_linea,
        })
        resultado[cli]["total_mes"] += total_linea

    # Ordenar semanas y líneas de forma ascendente por fecha y producto
    for cli in resultado:
        for sem in resultado[cli]["por_semana"]:
            resultado[cli]["por_semana"][sem]["lineas"].sort(
                key=lambda x: (x.get("fecha") or date.min, x["producto"]))

    return resultado


def _card_cliente(cli_nombre: str, datos_cli: dict,
                   cliente_info: dict, mes: int, año: int):
    """Muestra el expander de un cliente con desglose semanal y PDF."""
    total = datos_cli["total_mes"]
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

            liq_sem, isr_sem, desc_sem = calcular_liquido(cli_nombre, sub_sem)
            base_sem = round(sub_sem / 1.12, 2)
            if desc_sem > 0:
                isr_txt = f"Desc.15%: Q{desc_sem:,.2f}  ·  "
            elif isr_sem > 0:
                isr_txt = f"ISR: Q{isr_sem:,.2f}  ·  "
            else:
                isr_txt = ""
            st.markdown(
                f"<div style='background:#2D7A2D;color:white;padding:6px 10px;"
                f"border-radius:4px;font-size:.82rem;font-weight:bold;"
                f"margin:8px 0 4px 0'>"
                f"Semana {sem_num} · {fecha_sem.strftime('%d/%m/%Y')} · "
                f"NIT: {(cliente_info or {}).get('nit') or '—'} · "
                f"Subtotal: Q{sub_sem:,.2f}"
                f"<br><span style='font-weight:normal;font-size:.75rem;opacity:.9'>"
                f"Base IVA: Q{base_sem:,.2f}  ·  "
                f"{isr_txt}"
                f"Líquido: Q{liq_sem:,.2f}</span></div>",
                unsafe_allow_html=True)

            hdr = st.columns([3, 1.5, 1.2, 1.5, 1.5])
            hdr[0].markdown("**Producto**"); hdr[1].markdown("**Fecha**")
            hdr[2].markdown("**Cant.**");    hdr[3].markdown("**Precio**")
            hdr[4].markdown("**Total**")

            for l in lineas_sem:
                r = st.columns([3, 1.5, 1.2, 1.5, 1.5])
                r[0].write(l["producto"])
                fecha_l = l.get("fecha")
                r[1].write(fecha_l.strftime("%d/%m/%Y") if fecha_l else "—")
                r[2].write(f"{l['cantidad']:g} {l['unidad']}")
                r[3].write(f"Q{l['precio']:,.2f}")
                r[4].write(f"Q{l['total']:,.2f}")

            # Boton Remision por semana
            try:
                from pdf_helper import generar_remision as _gen_rem
                _lineas_rem = [{"producto": l["producto"],
                                "unidad":   l.get("unidad",""),
                                "cantidad": float(l.get("cantidad") or 0),
                                "total":    float(l.get("total") or 0)}
                               for l in lineas_sem]
                _fecha_rem  = fecha_sem.strftime("%d/%m/%Y")
                _rem_bytes  = _gen_rem(cli_nombre, _lineas_rem,
                                       int(sem_num), int(año), _fecha_rem)
                _nom_rem    = f"Remision_{cli_nombre.replace(' ','_')}_Sem{sem_num}.pdf"
                st.download_button(f"🖨️ Remisión Sem {sem_num}",
                    data=_rem_bytes, file_name=_nom_rem,
                    mime="application/pdf",
                    key=f"fac_rem_{cli_nombre}_{sem_num}_{año}",
                    type="secondary")
            except Exception as _re:
                st.caption(f"Remision error: {_re}")

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

        # Totales con fórmulas fiscales correctas
        base_iva  = round(total / 1.12, 2)                          # Base sin IVA
        liq_total, isr_ret, desc_ret = calcular_liquido(cli_nombre, total)
        isr_ret   = isr_ret  # ya calculado con exenciones
        liquido   = round(total - isr_ret, 2)                       # Líquido a recibir

        tc1, tc2, tc3, tc4 = st.columns(4)
        tc1.metric("Total a Facturar",  f"Q{total:,.2f}")
        tc2.metric("Base sin IVA",      f"Q{base_iva:,.2f}",
                   help="Valor Factura / 1.12")
        tc3.metric("ISR a Retener",     f"Q{isr_ret:,.2f}",
                   delta="Solo si factura ≥ Q2,500" if total >= 2500 else "No aplica (< Q2,500)",
                   delta_color="off",
                   help="Base sin IVA × 5% (solo si factura ≥ Q2,500)")
        tc4.metric("Líquido a Recibir", f"Q{liquido:,.2f}",
                   help="Total Factura − ISR retenido")

        st.markdown(
            f"<div style='background:#e8f5e9;border-radius:8px;padding:10px;"
            f"text-align:center;margin:8px 0'>"
            f"<b>TOTAL A FACTURAR: Q{total:,.2f}"
            f"{'  |  ISR: Q' + f'{isr_ret:,.2f}' if isr_ret > 0 else ''}"
            f"  |  LÍQUIDO: Q{liquido:,.2f}</b></div>",
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
    # Botón de regreso al Inicio
    if st.button("🏠 Inicio", key="btn_home_fac", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()


    with st.spinner("Cargando pedidos..."):
        todos    = leer_pedidos()
        cli_list = cargar_clientes()

    # ── Alerta Rodrigo ────────────────────────────────────────────────────────
    hoy      = date.today()
    sem_act  = hoy.isocalendar()[1]
    año_act  = hoy.year
    # Rodrigo paga N+3, por lo tanto esta semana se factura N-3
    from datetime import timedelta
    d_ent    = date.fromisocalendar(año_act, sem_act, 1) - timedelta(weeks=3)
    iso_ent  = d_ent.isocalendar()
    sem_rod  = iso_ent[1]; año_rod = iso_ent[0]
    rod_total = sum(
        float(p["total"] or 0) for p in todos
        if "rodrigo" in p["cliente"].lower()
        and p["semana"] == sem_rod and p["año"] == año_rod
        and p["status"] != "Cancelado"
    )
    if rod_total > 0:
        st.info(
            f"📅 **Rodrigo** — Esta semana (Sem {sem_act}) "
            f"facturá los pedidos de la **Semana {sem_rod}/{año_rod}** · "
            f"Total: Q{rod_total:,.2f}"
        )
    elif sem_rod > 0:
        st.info(
            f"📅 **Rodrigo** — Esta semana (Sem {sem_act}) "
            f"corresponde facturar **Semana {sem_rod}/{año_rod}** "
            f"(sin pedidos registrados en esa semana)"
        )

    cli_map       = {c["nombre"]: c for c in cli_list}
    cli_map_lower = {c["nombre"].lower(): c for c in cli_list}

    def _get_cli_info(nombre):
        return cli_map.get(nombre) or cli_map_lower.get(nombre.lower(), {})

    # ── Selectores ────────────────────────────────────────────────────────────
    hoy = date.today()
    meses_disp = [(m, f"{MESES_ES[m-1]} {y}")
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

    # ── Organizar por zona ────────────────────────────────────────────────────
    por_zona = {z: {} for z in ZONAS_MAP}
    sin_zona = {}
    for cli_nombre, datos_cli in datos.items():
        cli_obj = _get_cli_info(cli_nombre)
        zona    = _zona_cliente(cli_obj)
        if zona in por_zona:
            por_zona[zona][cli_nombre] = datos_cli
        else:
            sin_zona[cli_nombre] = datos_cli

    tabs_labels = [f"{z} ({len(v)})" for z, v in por_zona.items() if v]
    if sin_zona:
        tabs_labels.append(f"⚠️ Sin zona ({len(sin_zona)})")

    if not tabs_labels:
        st.info("No hay pedidos para este período.")
        return

    tabs = st.tabs(tabs_labels)
    tab_idx = 0

    for zona, grupo in por_zona.items():
        if not grupo:
            continue
        with tabs[tab_idx]:
            tab_idx += 1
            color    = COLORES_ZONA[zona]
            total_z  = sum(v["total_mes"] for v in grupo.values())
            st.markdown(
                f"<div style='border-left:4px solid {color};padding:3px 10px;"
                f"border-radius:4px;margin-bottom:8px'>"
                f"<b>{zona}</b> — {len(grupo)} cliente(s) — "
                f"Total: Q{total_z:,.2f}</div>",
                unsafe_allow_html=True)
            for cli_nombre, datos_cli in sorted(grupo.items(),
                                                 key=lambda x: x[1]["total_mes"],
                                                 reverse=True):
                cliente_info = _get_cli_info(cli_nombre) or {"nombre": cli_nombre}
                _card_cliente(cli_nombre, datos_cli, cliente_info, mes_sel, año_sel)

    if sin_zona:
        with tabs[tab_idx]:
            for cli_nombre, datos_cli in sorted(sin_zona.items(),
                                                 key=lambda x: x[1]["total_mes"],
                                                 reverse=True):
                cliente_info = cli_map.get(cli_nombre, {"nombre": cli_nombre})
                _card_cliente(cli_nombre, datos_cli, cliente_info, mes_sel, año_sel)
