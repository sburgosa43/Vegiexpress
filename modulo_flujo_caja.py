"""
modulo_flujo_caja.py — Flujo de Caja Semanal
Tabla de 8 semanas (4 pasadas, actual, 3 futuras) con liquidez neta por cliente.
Fase 1: clientes semanales GT/Río.
"""
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from excel_helper import leer_pedidos
from data_helper  import cargar_clientes

# ── Configuración de clientes especiales ─────────────────────────────────────
# lag: semanas entre entrega y pago
# isr: aplica ISR si factura ≥ Q2,800
# desc: descuento % sobre factura (en lugar de ISR)
REGLAS = {
    "rodrigo":   {"lag": 3, "isr": True,  "desc": 0},
    "4 pinos":   {"lag": 1, "isr": False, "desc": 0},
    "nanajuana": {"lag": 1, "isr": True,  "desc": 0},
    "tijax":     {"lag": 1, "isr": True,  "desc": 0},
    "amis":      {"lag": 1, "isr": False, "desc": 15},
    "hotelito":  {"lag": 0, "isr": False, "desc": 15},
    "sundog":    {"lag": 0, "isr": False, "desc": 0},
}
ISR_UMBRAL   = 2800.0
ZONA_GT_RIO  = ["L01", "L05", "L06"]
ZONA_VEGGI   = ["L03", "L04"]
EXCLUIR      = ["veggi", "chimalt", "wilson"]


def _excluido(n): return any(x in n.lower() for x in EXCLUIR)


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


def _ventana_8(hoy: date):
    """Retorna lista de 8 (semana, año): 4 pasadas, actual, 3 futuras."""
    sem_act = hoy.isocalendar()[1]
    año_act = hoy.year
    return [_add_weeks(sem_act, año_act, i) for i in range(-4, 4)]


def _proyeccion(todos: list, cliente_lower: str,
                sem_entrega: int, año_entrega: int) -> float:
    """Promedio de las últimas 4 semanas + mismas 4 del año anterior / 8."""
    ref = {}
    for i in range(1, 5):
        s, a = _add_weeks(sem_entrega, año_entrega, -i)
        ref[(s, a)] = 0.0
        ref[(s, a - 1)] = 0.0   # mismo período año anterior

    for p in todos:
        if p["cliente"].lower() != cliente_lower: continue
        if p["status"] == "Cancelado": continue
        k = (p["semana"], p["año"])
        if k in ref:
            ref[k] += float(p["total"] or 0)

    return round(sum(ref.values()) / 8, 2)


def _construir_tabla(todos: list, clientes: list, ventana: list):
    """
    Construye dict: {cliente_nombre: {(sem_pago, año_pago): (liquido, es_proyeccion)}}
    Solo para clientes en zona GT/Río.
    """
    # Mapa cliente → zona
    cli_zona = {c["nombre"].lower(): c["codigo_lugar"] for c in clientes}

    # Agrupar pedidos reales por (cliente, sem_entrega, año_entrega)
    entregas = {}  # {(cli_lower, sem, año): total_factura}
    for p in todos:
        if p["status"] == "Cancelado": continue
        if not p["fecha"]: continue
        if _excluido(p["cliente"]): continue
        zona = cli_zona.get(p["cliente"].lower(), "")
        if zona not in ZONA_GT_RIO: continue
        k = (p["cliente"], p["semana"], p["año"])
        entregas[k] = entregas.get(k, 0) + float(p["total"] or 0)

    # Semanas de pago en la ventana (set para búsqueda rápida)
    ventana_set = set(ventana)
    sem_act, año_act = ventana[4]  # índice 4 = semana actual

    # Construir resultado
    resultado = {}  # {cli: {(sem_pago, año_pago): (liquido, es_proj)}}

    clientes_gt_rio = {
        p["cliente"] for p in todos
        if cli_zona.get(p["cliente"].lower(), "") in ZONA_GT_RIO
        and not _excluido(p["cliente"])
    }

    for cli in clientes_gt_rio:
        reglas   = _reglas(cli)
        lag      = reglas["lag"]
        cli_low  = cli.lower()

        if cli not in resultado:
            resultado[cli] = {}

        # Pedidos reales
        for (c, sem, año), total in entregas.items():
            if c != cli: continue
            sem_p, año_p = _add_weeks(sem, año, lag)
            if (sem_p, año_p) not in ventana_set: continue
            liq = _liquido(total, reglas)
            resultado[cli][(sem_p, año_p)] = (liq, False)

        # Proyección para semanas futuras sin datos reales
        for i, (sem_p, año_p) in enumerate(ventana):
            if i <= 4: continue  # solo futuras (índices 5,6,7)
            if (sem_p, año_p) in resultado[cli]: continue
            sem_ent, año_ent = _add_weeks(sem_p, año_p, -lag)
            proy = _proyeccion(todos, cli_low, sem_ent, año_ent)
            if proy > 0:
                liq = _liquido(proy, reglas)
                resultado[cli][(sem_p, año_p)] = (liq, True)

    return resultado


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
    ventana = _ventana_8(hoy)
    sem_act, año_act = ventana[4]

    tabla = _construir_tabla(todos, clientes, ventana)

    # ── Tabla resumen semana actual ──────────────────────────────────────────
    cli_zona_map = {c["nombre"].lower(): c["codigo_lugar"] for c in clientes}

    # Recopilar pagos de esta semana con zona y lag
    pagos_sem = {}   # {cli_nombre: (liquido, lag, zona)}
    for cli, semanas_pago in tabla.items():
        if (sem_act, año_act) in semanas_pago:
            liq, _ = semanas_pago[(sem_act, año_act)]
            reg     = _reglas(cli)
            zona    = cli_zona_map.get(cli.lower(), "")
            pagos_sem[cli] = (liq, reg["lag"], zona)

    if pagos_sem:
        # Ordenar: Campo (L05/L06) primero, luego Hoteles (L01)
        def _orden(cli):
            z = pagos_sem[cli][2]
            return (0 if z in ["L05","L06"] else 1, cli)

        clis_ord = sorted(pagos_sem.keys(), key=_orden)

        def fmtQ(v): return f"Q{v:,.0f}" if v > 0 else ""

        def _sum_zona(filtro_lag, filtro_zona):
            return sum(
                v for cli, (v, lag, z) in pagos_sem.items()
                if filtro_lag(lag) and filtro_zona(z)
            )

        # Totales rápidos para mostrar arriba
        tot_campo   = sum(v for cli,(v,lag,z) in pagos_sem.items() if z in ["L05","L06"])
        tot_hoteles = sum(v for cli,(v,lag,z) in pagos_sem.items() if z == "L01")
        tot_gral    = tot_campo + tot_hoteles

        # Mini resumen al inicio
        mc, mh, mg = st.columns(3)
        mc.metric("🌾 Total Campo",   f"Q{tot_campo:,.0f}")
        mh.metric("🏨 Total Hoteles", f"Q{tot_hoteles:,.0f}")
        mg.metric("💰 Total Semana",  f"Q{tot_gral:,.0f}")
        st.divider()

        # Construir tabla con Total Campo y Total Hoteles como columnas
        cols_display = clis_ord + ["Total Campo", "Total Hoteles", "TOTAL"]

        def build_row(filtro_lag_fn):
            row = {}
            t_campo = t_hotel = 0.0
            for cli in clis_ord:
                liq, lag, zona = pagos_sem[cli]
                if filtro_lag_fn(lag):
                    row[cli] = fmtQ(liq)
                    if zona in ["L05","L06"]: t_campo += liq
                    elif zona == "L01":       t_hotel += liq
                else:
                    row[cli] = ""
            row["Total Campo"]   = fmtQ(t_campo)
            row["Total Hoteles"] = fmtQ(t_hotel)
            row["TOTAL"]         = fmtQ(t_campo + t_hotel)
            return row

        filas = {}
        filas["Contado"] = build_row(lambda lag: lag == 0)
        filas["Crédito"] = build_row(lambda lag: lag > 0)

        # Fila TOTAL (suma de contado + crédito por columna)
        fila_tot = {}
        for cli in clis_ord:
            liq, lag, zona = pagos_sem[cli]
            fila_tot[cli] = fmtQ(liq)
        fila_tot["Total Campo"]   = fmtQ(tot_campo)
        fila_tot["Total Hoteles"] = fmtQ(tot_hoteles)
        fila_tot["TOTAL"]         = fmtQ(tot_gral)
        filas["TOTAL"] = fila_tot

        df_sem = pd.DataFrame(filas, index=cols_display).T
        df_sem.index.name = f"Semana {sem_act}/{año_act}"
        st.markdown(f"#### 💸 Pagos esperados — Semana {sem_act}/{año_act}")
        st.dataframe(df_sem, use_container_width=True)
        st.divider()

    # ── Tabla ─────────────────────────────────────────────────────────────────
    col_labels = []
    for i, (s, a) in enumerate(ventana):
        marca = " ★" if i == 4 else (" ~" if i > 4 else "")
        col_labels.append(f"Sem {s}\n{a}{marca}")

    # Construir DataFrame
    clientes_orden = sorted(tabla.keys(),
                             key=lambda c: (REGLAS.get(c.lower().split()[0],
                                            {"lag":0})["lag"], c),
                             reverse=True)

    rows = []
    for cli in clientes_orden:
        row = {"Cliente": cli}
        for s_lbl, (s, a) in zip(col_labels, ventana):
            if (s, a) in tabla[cli]:
                liq, es_proy = tabla[cli][(s, a)]
                row[s_lbl] = f"Q{liq:,.0f}{'~' if es_proy else ''}"
            else:
                row[s_lbl] = ""
        rows.append(row)

    # Fila totales
    total_row = {"Cliente": "**TOTAL GT/Río**"}
    total_global = 0.0
    for s_lbl, (s, a) in zip(col_labels, ventana):
        tot = sum(
            tabla[cli][(s, a)][0]
            for cli in tabla if (s, a) in tabla[cli]
        )
        total_global += tot
        total_row[s_lbl] = f"**Q{tot:,.0f}**" if tot > 0 else ""
    rows.append(total_row)

    if rows:
        df = pd.DataFrame(rows).set_index("Cliente")
        st.markdown(f"#### 🇬🇹 GT / Río — Sergio  ·  "
                    f"Total ventana: **Q{total_global:,.0f}**")
        st.caption("★ semana actual  · ~ proyección basada en historial")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Sin datos para el período seleccionado.")

    # ── Veggi ─────────────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### 🌿 Veggi — Esposa")
    st.info("Fase 2 en desarrollo — ciclos mensuales (Antigua, Chimal, Chimalt)")

    # ── Leyenda ISR ───────────────────────────────────────────────────────────
    st.divider()
    with st.expander("📋 Reglas aplicadas por cliente", expanded=False):
        reglas_txt = []
        for cli_key, r in REGLAS.items():
            lag_txt  = f"pago N+{r['lag']}" if r['lag'] > 0 else "contado"
            isr_txt  = "sin ISR" if not r["isr"] else f"ISR si ≥ Q{ISR_UMBRAL:,.0f}"
            desc_txt = f" · descuento {r['desc']}%" if r["desc"] else ""
            reglas_txt.append(f"**{cli_key.title()}**: {lag_txt} · {isr_txt}{desc_txt}")
        for t in reglas_txt:
            st.markdown(f"- {t}")
        st.markdown(f"- **Resto de clientes**: contado · ISR si ≥ Q{ISR_UMBRAL:,.0f}")
