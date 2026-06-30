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

# Reglas vienen de config.py
ZONA_GT_RIO  = ["L01", "L05", "L06"]
ZONA_VEGGI   = ["L03", "L04"]





def _reglas(cliente_nombre: str) -> dict:
    k = cliente_nombre.lower().strip()
    for key, r in REGLAS.items():
        if key in k:
            return r
    return {"lag": 0, "isr": True, "desc": 0}


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

    # Acumular líquido por (cliente, sem_pago, año_pago)
    acumulado = {}   # {(cli, sem_p, año_p): liquido}
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
        liq = _liquido(total, reglas)
        key = (cli, sem_p, año_p)
        acumulado[key] = acumulado.get(key, 0.0) + liq

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


def mostrar():
    st.markdown("## 💰 Flujo de Caja Semanal")
    if st.button("🏠 Inicio", key="btn_home_fc", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

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

    # Diagnóstico: rezago de cobro aplicado a cada cliente
    with st.expander("🔍 Ver rezago de cobro por cliente"):
        st.caption("Verificá que cada cliente tenga el rezago correcto. Si un "
                   "cliente muestra lag 0 pero debería cobrar después, hay que "
                   "agregar su nombre en las reglas de pago (config).")
        diag = []
        for f in filas_f:
            reg = _reglas(f["Cliente"])
            diag.append({
                "Cliente": f["Cliente"],
                "Rezago (semanas)": reg["lag"],
                "ISR": "Sí" if reg["isr"] else "No",
                "Descuento %": reg["desc"],
            })
        diag.sort(key=lambda x: x["Cliente"])
        st.dataframe(pd.DataFrame(diag), hide_index=True,
                     use_container_width=True)

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
