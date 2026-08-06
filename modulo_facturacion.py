"""
modulo_facturacion.py — Resumen de facturación por cliente
Acumula todos los envíos del período seleccionado (un mes calendario o un
rango libre de fechas), desglose por semana y subtotal por producto, con PDF
descargable por cliente.
"""
import streamlit as st
import pandas as pd
from datetime import date
from excel_helper import leer_pedidos
from data_helper  import cargar_clientes
from pdf_helper   import (generar_facturacion_mensual,
                           nombre_archivo_factura)
from utils        import MESES_ES, etiqueta_periodo, rango_mes
from config       import (ZONAS_MAP, COLORES_ZONA, ISR_UMBRAL,
                           calcular_liquido, excluido_dashboard, base_sin_iva)

# Excluir mismos clientes que el dashboard

# ZONAS_MAP y COLORES_ZONA vienen de config.py
# _excluido eliminado — todos los clientes aparecen en facturación

def _zona_cliente(c: dict) -> str:
    for zona, cods in ZONAS_MAP.items():
        if c.get("codigo_lugar","") in cods:
            return zona
    return "Sin zona"


def _construir_datos(pedidos: list, desde: date, hasta: date) -> dict:
    """
    Agrupa los pedidos del período por cliente → semana → líneas.
    Retorna dict: {cliente: {por_semana: {semana: {fecha, lineas}}, total}}

    Filtra por rango con los dos bordes INCLUIDOS. El modo Mes de la pantalla
    entra por acá igual que el rango libre, con desde/hasta calculados por
    utils.rango_mes: una sola lógica de filtrado y agrupación para los dos.
    """
    resultado = {}

    for p in pedidos:
        if p["status"] == "Cancelado":          continue
        if not p["fecha"]:                      continue
        if not (desde <= p["fecha"] <= hasta):  continue
        if not p["producto"]:                   continue

        cli  = p["cliente"]
        sem  = p["semana"] or p["fecha"].isocalendar()[1]

        if cli not in resultado:
            resultado[cli] = {"por_semana": {}, "total": 0.0}

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
        resultado[cli]["total"] += total_linea

    # Ordenar semanas y líneas de forma ascendente por fecha y producto
    for cli in resultado:
        for sem in resultado[cli]["por_semana"]:
            resultado[cli]["por_semana"][sem]["lineas"].sort(
                key=lambda x: (x.get("fecha") or date.min, x["producto"]))

    return resultado


def _clave_periodo(desde: date, hasta: date) -> str:
    """Sufijo de key de widget. Dos períodos distintos no pueden compartir key
    o Streamlit le sirve al segundo el estado (y el PDF) del primero."""
    return f"{desde:%Y%m%d}_{hasta:%Y%m%d}"


def _card_cliente(cli_nombre: str, datos_cli: dict,
                   cliente_info: dict, desde: date, hasta: date):
    """Muestra el expander de un cliente con desglose semanal y PDF."""
    total = datos_cli["total"]
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
            base_sem = round(base_sin_iva(sub_sem), 2)
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
        base_iva  = round(base_sin_iva(total), 2)
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
            clave = _clave_periodo(desde, hasta)
            pdf_bytes = generar_facturacion_mensual(
                cliente=cliente_info,
                desde=desde, hasta=hasta,
                por_semana=datos_cli["por_semana"],
            )
            _cf1, _cf2 = st.columns(2)
            with _cf1:
                st.download_button(
                    label="📄 Descargar PDF de Facturación",
                    data=pdf_bytes,
                    file_name=nombre_archivo_factura(cli_nombre, desde, hasta),
                    mime="application/pdf",
                    key=f"fact_pdf_{cli_nombre}_{clave}",
                    type="primary",
                    use_container_width=True,
                )
            with _cf2:
                from pdf_helper import boton_imprimir_html as _btn_imp_fac
                import streamlit.components.v1 as _cpv_fac
                _cpv_fac.html(
                    _btn_imp_fac(pdf_bytes,
                                 f"fac_{cli_nombre}_{clave}",
                                 "🖨️ Imprimir"),
                    height=44)
        except Exception as e:
            st.error(f"Error generando PDF: {e}")


# ── HISTÓRICO POR ÁREA (solo lectura) ─────────────────────────────────────────
# Nada de acá escribe. Es la misma lectura que hace la pestaña del mes, pero
# sobre un rango de fechas libre y agregada por área en vez de por cliente.
#
# El área sale de data_helper.mapa_area_grupo, la misma fuente que usan el
# reporte de Compras y Control de Márgenes. _zona_cliente (arriba) aplica el
# mismo criterio pero cliente por cliente; acá hace falta el mapa completo.

COLS_HIST = ["Período", "Cliente", "Venta (Q)", "Compra (Q)", "IVA (Q)",
             "ISR (Q)", "Margen Bruto (Q)", "Margen Neto (Q)"]

_GRANULARIDAD = ["Mes", "Semana", "Sin período (todo el rango)"]


def _periodo_de(p: dict, granularidad: str) -> str:
    """Etiqueta de período de una línea. Con 'Sin período' todas caen en la
    misma etiqueta, así el mismo agregador sirve para el total del rango."""
    if granularidad == "Semana":
        return f"{p['año']}-S{int(p['semana'] or 0):02d}"
    if granularidad == "Mes":
        return p["fecha"].strftime("%Y-%m")
    return "Todo el rango"


def agregar_historico(pedidos: list, mapa: dict, desde: date, hasta: date,
                      areas: tuple = (), granularidad: str = "Mes"):
    """Una fila por cliente y período. El área es el FILTRO, no una columna.

        Venta  = Σ(precio × cantidad)   — el mismo 'total' que factura el módulo
        Compra = Σ(costo  × cantidad)
        IVA    = el IVA contenido en la venta (config.iva_incluido)
        ISR    = retención real, ver abajo
        Bruto  = Venta − Compra
        Neto   = Σ margen_neto_q(costo, precio) × cantidad

    Bruto y Neto son las mismas definiciones que usa Control de Márgenes, para
    que los dos reportes no den números distintos de lo mismo.

    Usa el precio y el costo GUARDADOS en cada línea, no el catálogo de hoy:
    un histórico tiene que mostrar lo que pasó, no lo que costaría hoy.

    El ISR NO es un 5% plano: hay clientes exentos y un umbral de Q2,800 que se
    evalúa POR FACTURA, y la factura es semanal. Por eso la venta se acumula
    también por semana y calcular_liquido se aplica a cada una — igual que en
    la pestaña del mes. Aplicarlo al total del período inflaría el ISR de
    clientes que facturan poco cada semana pero mucho en el mes.

    Sin lógica de estados: los pedidos cancelados se borran de la hoja, así que
    filtrar por status sería una regla que nunca se cumple.
    """
    from config import iva_incluido, margen_neto_q

    acc = {}
    for p in pedidos:
        f = p.get("fecha")
        if not f or not (desde <= f <= hasta):
            continue
        if not str(p.get("producto", "") or "").strip():
            continue
        cli = str(p.get("cliente", "") or "").strip()
        if not cli:
            continue
        area = mapa.get(cli.lower(), {}).get("area", "Sin área")
        if areas and area not in areas:
            continue

        cant  = float(p.get("cantidad") or 0)
        costo = float(p.get("costo") or 0)
        prec  = float(p.get("precio") or 0)
        venta = float(p.get("total") or 0)

        a = acc.setdefault((_periodo_de(p, granularidad), cli),
                           {"v": 0.0, "c": 0.0, "ne": 0.0, "sem": {}})
        a["v"]  += venta
        a["c"]  += costo * cant
        a["ne"] += margen_neto_q(costo, prec) * cant
        k_sem = f"{p.get('año')}-{p.get('semana')}"
        a["sem"][k_sem] = a["sem"].get(k_sem, 0.0) + venta

    filas = []
    for (per, cli), v in acc.items():
        isr = sum(calcular_liquido(cli, sub)[1] for sub in v["sem"].values())
        filas.append({
            "Período":          per,
            "Cliente":          cli,
            "Venta (Q)":        round(v["v"], 2),
            "Compra (Q)":       round(v["c"], 2),
            "IVA (Q)":          round(iva_incluido(v["v"]), 2),
            "ISR (Q)":          round(isr, 2),
            "Margen Bruto (Q)": round(v["v"] - v["c"], 2),
            "Margen Neto (Q)":  round(v["ne"], 2),
        })
    df = pd.DataFrame(filas, columns=COLS_HIST)
    if not df.empty:
        # Período descendente y, dentro de cada uno, el cliente que más vendió
        # primero: es el orden en que se lee un reporte de facturación.
        df = df.sort_values(["Período", "Venta (Q)"], ascending=[False, False],
                            ignore_index=True)
    return df


def totales_historico(df) -> dict:
    """Totales de la tabla. Los % se recalculan sobre los totales — promediar
    los porcentajes de las filas daría un margen que no es el real."""
    if df.empty:
        return {k: 0.0 for k in ("venta", "compra", "iva", "isr", "bruto",
                                 "bruto_pct", "neto", "neto_pct")}
    venta = float(df["Venta (Q)"].sum())
    bruto = float(df["Margen Bruto (Q)"].sum())
    neto  = float(df["Margen Neto (Q)"].sum())
    return {"venta":     venta,
            "compra":    float(df["Compra (Q)"].sum()),
            "iva":       float(df["IVA (Q)"].sum()),
            "isr":       float(df["ISR (Q)"].sum()),
            "bruto":     bruto,
            # Sin venta no hay porcentaje que calcular: devolver 0 evita
            # dividir por cero y no inventa un margen.
            "bruto_pct": round(bruto / venta * 100, 1) if venta else 0.0,
            "neto":      neto,
            "neto_pct":  round(neto / venta * 100, 1) if venta else 0.0}


def _rango_historico(atajo: str, hoy: date, pedidos: list) -> tuple:
    """(desde, hasta) de cada atajo. 'Todo' arranca en el pedido más viejo que
    haya en la hoja, no en una fecha fija que envejezca sola."""
    from datetime import timedelta
    if atajo == "Este año":
        return date(hoy.year, 1, 1), hoy
    if atajo == "Últimos 12 meses":
        return hoy - timedelta(days=365), hoy
    if atajo == "Todo":
        fechas = [p["fecha"] for p in pedidos if p.get("fecha")]
        return (min(fechas) if fechas else hoy), hoy
    return hoy - timedelta(days=90), hoy          # Personalizado: 3 meses


def _tab_historico(todos: list):
    """Venta y compra por área sobre un rango libre de fechas."""
    from data_helper import mapa_area_grupo

    hoy = date.today()
    st.caption("Venta y compra por área sobre el histórico completo. Usa el "
               "precio y el costo guardados en cada línea; no recalcula nada "
               "ni modifica el Sheet.")

    a1, a2, a3 = st.columns([2.2, 1.1, 1.1])
    atajo = a1.radio("Rango", ["Este año", "Últimos 12 meses", "Todo",
                               "Personalizado"], horizontal=True,
                     key="hist_atajo")
    d_def, h_def = _rango_historico(atajo, hoy, todos)
    if atajo == "Personalizado":
        desde = a2.date_input("Desde", value=d_def, key="hist_desde")
        hasta = a3.date_input("Hasta", value=h_def, key="hist_hasta")
    else:
        desde, hasta = d_def, h_def
        a2.markdown(f"<small>Desde<br><b>{desde:%d/%m/%Y}</b></small>",
                    unsafe_allow_html=True)
        a3.markdown(f"<small>Hasta<br><b>{hasta:%d/%m/%Y}</b></small>",
                    unsafe_allow_html=True)

    if desde > hasta:
        st.error("El 'Desde' es posterior al 'Hasta'.")
        return

    # Áreas presentes en el rango, no todas las de ZONAS_MAP: ofrecer filtrar
    # por un área sin ventas en el período elegido no diría nada.
    mapa = mapa_area_grupo()
    disp = sorted({mapa.get(str(p.get("cliente", "") or "").strip().lower(),
                            {}).get("area", "Sin área")
                   for p in todos
                   if p.get("fecha") and desde <= p["fecha"] <= hasta
                   and str(p.get("cliente", "") or "").strip()})
    f1, f2 = st.columns([2, 1])
    sel_area = f1.multiselect("Área", disp, key="hist_area",
                              help="Vacío = todas las áreas del período.")
    gran     = f2.selectbox("Ver por", _GRANULARIDAD, key="hist_gran")

    df = agregar_historico(todos, mapa, desde, hasta, tuple(sel_area), gran)
    if df.empty:
        st.info("No hay pedidos para ese rango y esas áreas.")
        return

    # Los porcentajes viven acá arriba y en el TOTAL de abajo, no en la tabla:
    # un % por fila se lee como si todas pesaran igual, y no es así.
    t = totales_historico(df)
    m1, m2, m3 = st.columns(3)
    m1.metric("Venta",        f"Q{t['venta']:,.2f}")
    m2.metric("Compra",       f"Q{t['compra']:,.2f}")
    m3.metric("Margen Bruto", f"Q{t['bruto']:,.2f}",
              f"{t['bruto_pct']:.1f}%", delta_color="off")
    m4, m5, m6 = st.columns(3)
    m4.metric("IVA",          f"Q{t['iva']:,.2f}")
    m5.metric("ISR retenido", f"Q{t['isr']:,.2f}")
    m6.metric("Margen Neto",  f"Q{t['neto']:,.2f}",
              f"{t['neto_pct']:.1f}%", delta_color="off")

    _num = st.column_config.NumberColumn
    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config={c: _num(format="%.2f") for c in
                                ("Venta (Q)", "Compra (Q)", "IVA (Q)",
                                 "ISR (Q)", "Margen Bruto (Q)",
                                 "Margen Neto (Q)")})
    st.caption(f"**TOTAL: Venta Q{t['venta']:,.2f} · Compra "
               f"Q{t['compra']:,.2f} · IVA Q{t['iva']:,.2f} · ISR "
               f"Q{t['isr']:,.2f} · Bruto Q{t['bruto']:,.2f} "
               f"({t['bruto_pct']:.1f}%) · Neto Q{t['neto']:,.2f} "
               f"({t['neto_pct']:.1f}%)** — {len(df)} fila(s), "
               f"{desde:%d/%m/%Y} a {hasta:%d/%m/%Y}")
    st.caption("El ISR se calcula por factura semanal, respetando exentos y el "
               f"umbral de Q{ISR_UMBRAL:,.0f} — no es un 5% plano sobre el "
               "total del período.")

    # Texto de los filtros aplicados: va al PDF para que un reporte impreso
    # nunca sea ambiguo sobre qué recorte representa.
    filtros_txt = (f"Área: {', '.join(sel_area)}" if sel_area
                   else "sin filtros (todas las áreas)")
    filtros_txt += f" · Ver por: {gran}"

    b1, b2 = st.columns(2)
    csv_df = pd.concat([df, pd.DataFrame([{
        "Período": "TOTAL", "Cliente": "",
        "Venta (Q)": round(t["venta"], 2), "Compra (Q)": round(t["compra"], 2),
        "IVA (Q)": round(t["iva"], 2), "ISR (Q)": round(t["isr"], 2),
        "Margen Bruto (Q)": round(t["bruto"], 2),
        "Margen Neto (Q)": round(t["neto"], 2)}])], ignore_index=True)
    b1.download_button(
        "📥 Descargar CSV",
        data=csv_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"historico_area_{desde:%Y%m%d}_{hasta:%Y%m%d}.csv",
        mime="text/csv", key="hist_csv", use_container_width=True)

    with b2:
        if st.button("🖨 Preparar impresión", key="hist_pdf",
                     use_container_width=True):
            import streamlit.components.v1 as components
            from pdf_helper import (generar_reporte_historico,
                                    boton_imprimir_html)
            with st.spinner("Generando PDF..."):
                pdf = generar_reporte_historico(df.to_dict("records"), desde,
                                                hasta, filtros_txt, t)
            components.html(boton_imprimir_html(pdf, "rephistorico",
                                                label="🖨 Abrir e imprimir"),
                            height=60)


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

    # Los pedidos se leen una vez y se pasan a cada pestaña: leer_pedidos
    # recorre el histórico completo y hacerlo dos veces por render no aporta.
    t_mes, t_hist = st.tabs(["🧾 Facturación del mes",
                             "📊 Histórico por Área"])
    with t_mes:
        _tab_mes(todos, cli_list)
    with t_hist:
        _tab_historico(todos)


def _tab_mes(todos: list, cli_list: list):
    """Lo que el módulo hace desde siempre: un mes, por cliente y por zona."""
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

    modo = st.radio("Período", ["Mes", "Rango de fechas"], horizontal=True,
                    key="fact_modo",
                    help="Mes: un mes calendario completo, como siempre. "
                         "Rango: cualquier par de fechas, con los dos bordes "
                         "incluidos.")

    if modo == "Mes":
        s1, s2, s3 = st.columns(3)
        with s1:
            mes_sel_lbl = st.selectbox(
                "Mes", [lbl for _, lbl in meses_disp],
                index=0, key="fact_mes")
            mes_sel = next(m for m, lbl in meses_disp if lbl == mes_sel_lbl)
            año_sel = int(mes_sel_lbl.split()[-1])
        desde, hasta = rango_mes(mes_sel, año_sel)
    else:
        s1a, s1b, s2, s3 = st.columns(4)
        # Arranca en el mes en curso hasta hoy: un rango válido de entrada, y
        # el usuario mueve solo el borde que le interesa.
        ini_def, _ = rango_mes(hoy.month, hoy.year)
        desde = s1a.date_input("Desde", value=ini_def, key="fact_desde")
        hasta = s1b.date_input("Hasta", value=hoy,     key="fact_hasta")

        if not desde or not hasta:
            st.info("Elegí las dos fechas del rango.")
            return
        if desde > hasta:
            st.error("El 'Desde' es posterior al 'Hasta'.")
            return

    periodo_txt = etiqueta_periodo(desde, hasta)
    # 'en Julio 2026' / 'del 20/07/2026 al 10/08/2026': la etiqueta del mes
    # necesita preposición, la del rango ya la trae puesta.
    periodo_frase = f"en {periodo_txt}" if modo == "Mes" else periodo_txt

    with s2:
        clientes_disp = sorted({
            p["cliente"] for p in todos
            if p["fecha"] and desde <= p["fecha"] <= hasta
            and p["status"] != "Cancelado"
            })
        cli_filtro = st.selectbox(
            "Cliente", ["Todos"] + clientes_disp, key="fact_cli")

    with s3:
        st.markdown("&nbsp;")
        st.markdown(
            f"<div style='padding-top:28px;font-size:.85rem;color:#555'>"
            f"Período: <b>{periodo_txt}</b></div>",
            unsafe_allow_html=True)

    if modo != "Mes":
        st.caption("Un rango libre puede cortar una semana por la mitad: el "
                   "subtotal y el ISR de esa semana se calculan solo sobre las "
                   "entregas que caen dentro del rango, no sobre la factura "
                   "semanal completa.")

    st.divider()

    # ── Construir datos ───────────────────────────────────────────────────────
    datos = _construir_datos(todos, desde, hasta)

    if cli_filtro != "Todos":
        datos = {k: v for k, v in datos.items() if k == cli_filtro}

    if not datos:
        st.info(f"No hay pedidos {periodo_frase}.")
        return

    # ── Resumen global del período ────────────────────────────────────────────
    total_global = sum(v["total"] for v in datos.values())
    st.markdown(
        f"<div style='background:#e8f5e9;border-radius:8px;padding:10px;"
        f"text-align:center;margin:4px 0 12px 0'>"
        f"<b>{len(datos)} cliente(s)  ·  "
        f"Total {'del mes' if modo == 'Mes' else 'del período'}: "
        f"Q{total_global:,.2f}</b></div>",
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
            total_z  = sum(v["total"] for v in grupo.values())
            st.markdown(
                f"<div style='border-left:4px solid {color};padding:3px 10px;"
                f"border-radius:4px;margin-bottom:8px'>"
                f"<b>{zona}</b> — {len(grupo)} cliente(s) — "
                f"Total: Q{total_z:,.2f}</div>",
                unsafe_allow_html=True)
            for cli_nombre, datos_cli in sorted(grupo.items(),
                                                 key=lambda x: x[1]["total"],
                                                 reverse=True):
                cliente_info = _get_cli_info(cli_nombre) or {"nombre": cli_nombre}
                _card_cliente(cli_nombre, datos_cli, cliente_info, desde, hasta)

    if sin_zona:
        with tabs[tab_idx]:
            for cli_nombre, datos_cli in sorted(sin_zona.items(),
                                                 key=lambda x: x[1]["total"],
                                                 reverse=True):
                cliente_info = cli_map.get(cli_nombre, {"nombre": cli_nombre})
                _card_cliente(cli_nombre, datos_cli, cliente_info, desde, hasta)
