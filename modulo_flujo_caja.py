"""
modulo_flujo_caja.py — Flujo de Caja Semanal
Tabla de 8 semanas (4 pasadas, actual, 3 futuras) con liquidez neta por cliente.
Fase 1: clientes semanales GT/Río.
"""
import streamlit as st
from config import (REGLAS_PAGO as REGLAS, ISR_UMBRAL,
                     ZONA_GT_RIO, excluido_dashboard as _excluido_fc)
_excluido = _excluido_fc  # alias local
import pandas as pd
from datetime import date, timedelta
from excel_helper import leer_pedidos
from data_helper  import cargar_clientes

ZONA_GT_RIO  = ["L01", "L05", "L06"]
ZONA_VEGGI   = ["L03", "L04"]

# ── Reglas de pago editables (viven en la hoja ReglasPago) ────────────────────
_REGLAS_HEADER = ["cliente", "lag", "isr", "desc"]


def _ensure_reglas_sheet():
    """Crea la hoja ReglasPago si no existe y la migra desde config la 1a vez."""
    from gsheets import ensure_ws, get_all_rows, append_rows
    try:
        ensure_ws("reglaspago", _REGLAS_HEADER)
    except Exception as e:
        if "already exists" not in str(e).lower():
            raise
    # Si está vacía, migrar las reglas de config.py
    try:
        filas = get_all_rows("reglaspago")
    except Exception:
        filas = []
    if not filas:
        seed = []
        for cliente, r in REGLAS.items():
            seed.append([cliente, r["lag"],
                         "Sí" if r["isr"] else "No", r["desc"]])
        if seed:
            append_rows("reglaspago", seed)


@st.cache_data(ttl=120, show_spinner=False)
def _cargar_reglas() -> dict:
    """Lee las reglas de pago desde la hoja. Retorna {cliente_lower: {...}}."""
    _ensure_reglas_sheet()
    from gsheets import get_all_rows
    reglas = {}
    for r in get_all_rows("reglaspago"):
        if not r or not r[0]:
            continue
        while len(r) < 4:
            r.append("")
        cliente = str(r[0]).strip().lower()
        try:    lag = int(float(r[1])) if r[1] != "" else 0
        except: lag = 0
        isr = str(r[2]).strip().lower() in ("sí", "si", "yes", "true", "1")
        try:    desc = float(r[3]) if r[3] != "" else 0
        except: desc = 0
        reglas[cliente] = {"lag": lag, "isr": isr, "desc": desc}
    return reglas


def _guardar_reglas(df):
    """Sobrescribe la hoja ReglasPago con el DataFrame editado."""
    from gsheets import ws
    _ensure_reglas_sheet()
    w = ws("reglaspago")
    w.clear()
    filas = [_REGLAS_HEADER]
    for _, row in df.iterrows():
        cli = str(row.get("Cliente", "")).strip()
        if not cli:
            continue
        lag = int(row.get("Rezago (sem)", 0) or 0)
        isr = "Sí" if str(row.get("Agente retenedor (ISR)", "")).strip().lower() \
              in ("sí", "si", "yes", "true", "1") else "No"
        desc = float(row.get("Descuento %", 0) or 0)
        filas.append([cli, lag, isr, desc])
    w.update("A1", filas, value_input_option="USER_ENTERED")
    _cargar_reglas.clear()





def _reglas(cliente_nombre: str) -> dict:
    """Fuente ÚNICA: el tratamiento comercial vive en la ficha del cliente
    (Fase C de centralización). Con fallback automático a config para clientes
    aún no migrados."""
    from data_helper import tratamiento_cliente
    return tratamiento_cliente(cliente_nombre)


def _add_weeks(semana: int, año: int, n: int):
    """Suma n semanas a (semana, año) manejando cambio de año."""
    d = date.fromisocalendar(año, semana, 1) + timedelta(weeks=n)
    iso = d.isocalendar()
    return iso[1], iso[0]


def _liquido(total: float, reglas: dict) -> float:
    """Calcula el líquido a recibir según reglas del cliente."""
    if reglas["desc"] > 0:
        return round(total * (1 - reglas["desc"] / 100), 2)
    if reglas["isr"] and total >= ISR_UMBRAL:
        isr = total * 0.05 / 1.12
        return round(total - isr, 2)
    return round(total, 2)


def _ventana_13(hoy: date):
    """Retorna lista de 13 (semana, año): centrada para ver ~3 meses.
    Tomamos 4 pasadas, la actual, y 8 futuras (cubre los pagos diferidos)."""
    sem_act = hoy.isocalendar()[1]
    año_act = hoy.year
    return [_add_weeks(sem_act, año_act, i) for i in range(-4, 9)]


def _construir_tabla_pivote(todos: list, clientes: list, ventana: list):
    """Construye la tabla pivote de ingresos (líquido) por cliente y semana DE PAGO.

    Para cada pedido: se toma su semana de entrega, se aplica el lag del cliente
    para obtener la semana de pago, y se acumula el líquido en esa semana.

    Retorna:
      filas: lista de dicts {cliente, area, (sem,año): valor, ...}
      ventana: las (sem,año) en orden (columnas)
    """
    cli_zona = {c["nombre"].lower(): c.get("codigo_lugar", "") for c in clientes}
    cli_grupo = {c["nombre"].lower(): (c.get("grupo", "") or c.get("zona", "") or "")
                 for c in clientes}

    ventana_set = set(ventana)

    # Paso 1: acumular el TOTAL BRUTO por (cliente, sem_pago, año_pago).
    # Facturamos CONSOLIDADO por semana, así que primero sumamos todos los
    # pedidos del cliente en esa semana de pago, y DESPUÉS aplicamos ISR/desc
    # sobre el total consolidado (no pedido por pedido). Esto es clave: el
    # umbral de ISR (Q2,800) se evalúa sobre la factura semanal completa.
    bruto = {}   # {(cli, sem_p, año_p): total_bruto}
    for p in todos:
        if p["status"] == "Cancelado":
            continue
        if not p["fecha"]:
            continue
        if _excluido(p["cliente"]):
            continue
        cli = p["cliente"]
        reglas = _reglas(cli)
        lag = reglas["lag"]
        sem_p, año_p = _add_weeks(p["semana"], p["año"], lag)
        if (sem_p, año_p) not in ventana_set:
            continue
        total = float(p["total"] or 0)
        key = (cli, sem_p, año_p)
        bruto[key] = bruto.get(key, 0.0) + total

    # Paso 2: aplicar ISR/descuento sobre el total consolidado de cada semana.
    acumulado = {}   # {(cli, sem_p, año_p): liquido}
    for key, total_semana in bruto.items():
        cli = key[0]
        reglas = _reglas(cli)
        acumulado[key] = _liquido(total_semana, reglas)

    # Agrupar por cliente
    clientes_con_datos = sorted({k[0] for k in acumulado.keys()})
    filas = []
    for cli in clientes_con_datos:
        zona = cli_zona.get(cli.lower(), "")
        area = _nombre_area(zona)
        fila = {"Cliente": cli, "Área": area, "_zona": zona}
        for (sem, año) in ventana:
            fila[(sem, año)] = acumulado.get((cli, sem, año), 0.0)
        filas.append(fila)

    return filas


def _nombre_area(zona: str) -> str:
    """Traduce código de zona a nombre de área legible."""
    z = (zona or "").upper().strip()
    if z in ("L05", "L06"):
        return "Campo (Río)"
    if z in ("L01",):
        return "Hoteles"
    if z in ("L03", "L04"):
        return "VeggiExpress"
    if z in ("L20",):
        return "Hogares"
    return "Otros"


def _tab_flujo():
    with st.spinner("Calculando flujo de caja..."):
        todos    = leer_pedidos()
        clientes = cargar_clientes()

    hoy     = date.today()
    ventana = _ventana_13(hoy)
    sem_act, año_act = ventana[4]

    st.caption(f"Ingresos líquidos (después de ISR/descuentos) por **semana de "
               f"pago**, aplicando el rezago de cobro de cada cliente. "
               f"Semana actual: **{sem_act}/{año_act}**. "
               f"Vista de 13 semanas (~3 meses).")

    filas = _construir_tabla_pivote(todos, clientes, ventana)

    if not filas:
        st.info("No hay ingresos proyectados en la ventana de 13 semanas.")
        return

    # ── Filtro por área ───────────────────────────────────────────────────────
    areas_disp = sorted({f["Área"] for f in filas})
    sel_areas = st.multiselect("Filtrar por área", areas_disp,
                               default=areas_disp, key="fc_areas")
    filas_f = [f for f in filas if f["Área"] in sel_areas]

    if not filas_f:
        st.info("No hay datos para las áreas seleccionadas.")
        return

    # ── Construir DataFrame pivote ────────────────────────────────────────────
    import pandas as pd

    # Etiquetas de columnas de semana
    col_labels = {}
    for (sem, año) in ventana:
        col_labels[(sem, año)] = f"S{sem}"
        if (sem, año) == (sem_act, año_act):
            col_labels[(sem, año)] = f"S{sem}*"   # marca semana actual

    # Ordenar filas por área y luego cliente
    filas_f.sort(key=lambda f: (f["Área"], f["Cliente"]))

    # Armar registros
    registros = []
    for f in filas_f:
        reg = {"Área": f["Área"], "Cliente": f["Cliente"]}
        total_fila = 0.0
        for (sem, año) in ventana:
            v = f.get((sem, año), 0.0)
            reg[col_labels[(sem, año)]] = v
            total_fila += v
        reg["TOTAL"] = total_fila
        registros.append(reg)

    df = pd.DataFrame(registros)

    # Fila de totales por columna
    fila_total = {"Área": "", "Cliente": "TOTAL"}
    for (sem, año) in ventana:
        lbl = col_labels[(sem, año)]
        fila_total[lbl] = df[lbl].sum()
    fila_total["TOTAL"] = df["TOTAL"].sum()
    df = pd.concat([df, pd.DataFrame([fila_total])], ignore_index=True)

    # Formato de moneda para mostrar
    col_semanas = [col_labels[(s, a)] for (s, a) in ventana] + ["TOTAL"]
    df_fmt = df.copy()
    for c in col_semanas:
        df_fmt[c] = df_fmt[c].apply(lambda v: f"Q{v:,.0f}" if v and v != 0 else "")

    st.dataframe(df_fmt, hide_index=True, use_container_width=True)
    st.caption("La columna con * es la semana actual. "
               "Los valores son el líquido a recibir cada semana de pago.")

    # ── Resumen: total por área ───────────────────────────────────────────────
    st.divider()
    st.markdown("### 📊 Total por área (13 semanas)")
    por_area = {}
    for f in filas_f:
        a = f["Área"]
        tot = sum(f.get((s, an), 0.0) for (s, an) in ventana)
        por_area[a] = por_area.get(a, 0.0) + tot
    cols = st.columns(len(por_area) if por_area else 1)
    for i, (a, tot) in enumerate(sorted(por_area.items())):
        cols[i].metric(a, f"Q{tot:,.0f}")
    st.metric("**TOTAL GENERAL**", f"Q{sum(por_area.values()):,.0f}")

    # ── Resumen mes móvil: área × 4 semanas (N, N+1, N+2, N+3) ────────────────
    st.divider()
    st.markdown("### 📅 Resumen mes móvil por área (4 semanas)")
    # Las 4 semanas del mes móvil: actual y 3 siguientes
    # ventana[4] es la semana actual; ventana[4:8] son N, N+1, N+2, N+3
    mes_movil = ventana[4:8]
    col_lbl_mm = {(s, a): f"S{s}" for (s, a) in mes_movil}

    # Acumular por área y semana
    areas_orden = sorted({f["Área"] for f in filas_f})
    registros_mm = []
    for area in areas_orden:
        reg = {"Área": area}
        total_area = 0.0
        for (s, a) in mes_movil:
            v = sum(f.get((s, a), 0.0) for f in filas_f if f["Área"] == area)
            reg[col_lbl_mm[(s, a)]] = v
            total_area += v
        reg["TOTAL"] = total_area
        registros_mm.append(reg)

    df_mm = pd.DataFrame(registros_mm)
    # Fila de total por semana
    fila_tot_mm = {"Área": "TOTAL"}
    for (s, a) in mes_movil:
        lbl = col_lbl_mm[(s, a)]
        fila_tot_mm[lbl] = df_mm[lbl].sum() if lbl in df_mm else 0.0
    fila_tot_mm["TOTAL"] = df_mm["TOTAL"].sum() if "TOTAL" in df_mm else 0.0
    df_mm = pd.concat([df_mm, pd.DataFrame([fila_tot_mm])], ignore_index=True)

    # Formato moneda
    cols_mm = [col_lbl_mm[(s, a)] for (s, a) in mes_movil] + ["TOTAL"]
    df_mm_fmt = df_mm.copy()
    for c in cols_mm:
        df_mm_fmt[c] = df_mm_fmt[c].apply(
            lambda v: f"Q{v:,.0f}" if v and v != 0 else "")
    st.dataframe(df_mm_fmt, hide_index=True, use_container_width=True)
    sem_ini = mes_movil[0][0]
    sem_fin = mes_movil[-1][0]
    st.caption(f"Ingresos proyectados de la semana {sem_ini} a la {sem_fin} "
               f"(mes móvil), por área. Total por área (fila) y por semana (columna).")


def _tab_reglas():
    """Mantenimiento de las reglas de pago por cliente (editable)."""
    st.markdown("### ⚙️ Reglas de pago por cliente")
    st.caption("Editá el rezago de cobro, si el cliente retiene ISR, y el "
               "descuento de cada uno. Estos valores alimentan el cálculo del "
               "flujo de caja. Guardá para aplicar los cambios.")

    reglas_map = _cargar_reglas()
    rows = []
    for cli, r in sorted(reglas_map.items()):
        rows.append({
            "Cliente": cli,
            "Rezago (sem)": r["lag"],
            "Agente retenedor (ISR)": "Sí" if r["isr"] else "No",
            "Descuento %": r["desc"],
        })
    df = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Cliente", "Rezago (sem)", "Agente retenedor (ISR)", "Descuento %"])

    edited = st.data_editor(
        df,
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",   # permite agregar y eliminar filas
        column_config={
            "Cliente": st.column_config.TextColumn(
                "Cliente", help="Nombre (o parte) del cliente como aparece en pedidos"),
            "Rezago (sem)": st.column_config.NumberColumn(
                "Rezago (sem)", min_value=0, max_value=12, step=1,
                help="Semanas de rezago entre entrega y cobro"),
            "Agente retenedor (ISR)": st.column_config.SelectboxColumn(
                "Agente retenedor (ISR)", options=["Sí", "No"],
                help="Sí = retiene ISR en facturas ≥ Q2,800 (ese ISR no entra al flujo)"),
            "Descuento %": st.column_config.NumberColumn(
                "Descuento %", min_value=0, max_value=100, step=1,
                help="Descuento fijo que aplica el cliente (ej. comisión)"),
        },
        key="reglas_editor",
    )

    if st.button("💾 Guardar reglas", type="primary", key="guardar_reglas_btn"):
        try:
            _guardar_reglas(edited)
            st.success("✅ Reglas guardadas. El flujo de caja ya usa los nuevos "
                       "valores.")
            st.cache_data.clear()
        except Exception as e:
            st.error(f"Error al guardar: {type(e).__name__}: {e}")

    st.info("ℹ️ El umbral de ISR es Q2,800 por factura consolidada (fijo). "
            "Clientes que NO retienen (Sí→No en ISR) reciben el total sin "
            "descuento de ISR, sin importar el monto.")


def mostrar():
    st.markdown("## 💰 Flujo de Caja Semanal")
    if st.button("🏠 Inicio", key="btn_home_fc", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    tab_flujo, tab_reglas = st.tabs(["📊 Flujo de Caja", "⚙️ Reglas de Pago"])
    with tab_flujo:
        _tab_flujo()
    with tab_reglas:
        _tab_reglas()
