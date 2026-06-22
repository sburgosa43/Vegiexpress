"""
modulo_produccion.py — Gestión de producción agrícola multicultivo.

Cultivos con variedades, siembras, programa de fertilización (2 aplicaciones),
cálculo de mezcla N-P-K (grado equivalente + libras reales), cosecha por
productos de entrega, y proyección de rendimiento.

Hojas (auto-creadas con datos precargados):
  Produccion              — registro de cada siembra
  ProduccionCultivos      — cultivos + variedades + parámetros
  ProduccionAplicaciones  — dosis congeladas por siembra (1 fila/fertilizante)
  ProduccionFertilizantes — catálogo N-P-K
"""
import streamlit as st
from datetime import date, timedelta
import json, uuid

# ── Claves de hojas ───────────────────────────────────────────────────────────
_K_PROD = "produccion"
_K_CULT = "produccioncultivos"
_K_APLIC = "produccionaplic"
_K_FERT = "produccionfert"

MESES = {1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",
         7:"Jul",8:"Ago",9:"Sep",10:"Oct",11:"Nov",12:"Dic"}

# Temporada lluviosa en Guatemala: junio a octubre
MESES_LLUVIA = {6, 7, 8, 9, 10}


# ── Datos precargados ─────────────────────────────────────────────────────────
_FERT_INICIAL = [
    # Fertilizante, N, P, K
    ["Fertihortaliza 15-8-22", 15, 8, 22],
    ["15-15-15",               15, 15, 15],
    ["15-10-10",               15, 10, 10],
    ["0-0-60",                 0,  0,  60],
    ["21N-24S",                21, 0,  0],
]

_CULT_INICIAL = [
    # Cultivo, Variedad, Dias_Ciclo, Germinacion, Rend_Min, Rend_Max, Productos_Cosecha
    ["Zanahoria Baby", "Mercedes", 88, 0.75, 7, 10,
     "Mini,Zanahoria Baby,Zanahoria Babyr,Zanahoria Babyl"],
    ["Zanahoria Baby", "Crofton",  85, 0.75, 7, 10,
     "Mini,Zanahoria Baby,Zanahoria Babyr,Zanahoria Babyl"],
    ["Zanahoria Baby", "Romance",  90, 0.75, 7, 10,
     "Mini,Zanahoria Baby,Zanahoria Babyr,Zanahoria Babyl"],
]

# Programa de dosis sugerido por cultivo (2 aplicaciones: dia 22-25 y dia 50-55)
# Formato: {cultivo: {app_num: {"dia_desde":, "dia_hasta":, "seca":[(fert,lbs)],
#                                "lluvia":[(fert,lbs)]}}}
_DOSIS_SUGERIDAS = {
    "Zanahoria Baby": {
        1: {"dia_desde": 22, "dia_hasta": 25,
            "seca":   [("21N-24S", 18)],
            "lluvia": [("21N-24S", 10), ("15-10-10", 10)]},
        2: {"dia_desde": 50, "dia_hasta": 55,
            "seca":   [("0-0-60", 12), ("15-10-10", 6)],
            "lluvia": [("0-0-60", 12), ("15-10-10", 6)]},
    },
}


# ── Inicialización de hojas ───────────────────────────────────────────────────
def _ensure_safe(nombre, headers, rows_iniciales=None):
    """ensure_ws tolerante a 'already exists' (cache de workbook desactualizada)."""
    from gsheets import ensure_ws
    try:
        return ensure_ws(nombre, headers, rows_iniciales)
    except Exception as e:
        # Si ya existe (carrera con cache del workbook), no es error real
        if "already exists" in str(e).lower():
            return False
        raise


def _init_hojas():
    """Crea las hojas con datos precargados si no existen.
    Se ejecuta UNA VEZ por sesión (flag en session_state) para no
    consultar Sheets en cada navegación — clave para la velocidad."""
    if st.session_state.get("_prod_hojas_ok"):
        return

    _ensure_safe(_K_FERT,
                 ["Fertilizante", "N", "P", "K"],
                 [[r[0], r[1], r[2], r[3]] for r in _FERT_INICIAL])
    _ensure_safe(_K_CULT,
                 ["Cultivo", "Variedad", "Dias_Ciclo", "Germinacion",
                  "Rend_Min", "Rend_Max", "Productos_Cosecha"],
                 [[r[0], r[1], r[2], r[3], r[4], r[5], r[6]] for r in _CULT_INICIAL])
    _ensure_safe(_K_PROD,
                 ["id_siembra", "variedad", "fecha_siembra", "cantidad_semillas",
                  "lugar", "tablones", "fecha_cosecha_est", "semana_cosecha",
                  "dias_ciclo", "lbs_proyectadas_min", "lbs_proyectadas_max",
                  "lbs_cosechadas_real", "estado", "notas", "cultivo",
                  "cosecha_detalle"])
    _ensure_safe(_K_APLIC,
                 ["id_siembra", "aplicacion", "dia_desde", "dia_hasta",
                  "temporada", "fertilizante", "lbs", "aplicado_real",
                  "fecha_aplicado"])

    st.session_state["_prod_hojas_ok"] = True


# ── Lectores cacheados ────────────────────────────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def _leer_fertilizantes() -> dict:
    """Retorna {nombre: {N, P, K}}."""
    from gsheets import get_all_rows
    out = {}
    for r in get_all_rows(_K_FERT):
        if not r or not r[0]:
            continue
        try:
            out[str(r[0]).strip()] = {
                "N": float(r[1] or 0), "P": float(r[2] or 0), "K": float(r[3] or 0)}
        except (ValueError, IndexError):
            continue
    return out


@st.cache_data(ttl=900, show_spinner=False)
def _leer_cultivos() -> list:
    """Retorna lista de dicts con cultivos y variedades."""
    from gsheets import get_all_rows
    out = []
    for r in get_all_rows(_K_CULT):
        if not r or not r[0]:
            continue
        try:
            out.append({
                "cultivo":   str(r[0]).strip(),
                "variedad":  str(r[1]).strip(),
                "dias_ciclo": int(float(r[2] or 88)),
                "germinacion": float(r[3] or 0.75),
                "rend_min":  float(r[4] or 7),
                "rend_max":  float(r[5] or 10),
                "productos_cosecha": [p.strip() for p in str(r[6] or "").split(",") if p.strip()],
            })
        except (ValueError, IndexError):
            continue
    return out


@st.cache_data(ttl=120, show_spinner=False)
def _leer_siembras() -> list:
    """Retorna lista de siembras con su fila."""
    from gsheets import get_all_rows
    out = []
    for i, r in enumerate(get_all_rows(_K_PROD), start=2):
        if not r or not r[0]:
            continue
        while len(r) < 16:
            r.append("")
        try:
            cosecha_det = json.loads(r[15]) if r[15] else {}
        except (json.JSONDecodeError, TypeError):
            cosecha_det = {}
        out.append({
            "row_num":       i,
            "id_siembra":    str(r[0]),
            "variedad":      str(r[1]),
            "fecha_siembra": _parse_fecha(r[2]),
            "cantidad_semillas": _sf(r[3]),
            "lugar":         str(r[4]),
            "tablones":      _sf(r[5]),
            "fecha_cosecha_est": _parse_fecha(r[6]),
            "semana_cosecha": int(_sf(r[7])) if r[7] else 0,
            "dias_ciclo":    int(_sf(r[8])) if r[8] else 88,
            "lbs_proyectadas_min": _sf(r[9]),
            "lbs_proyectadas_max": _sf(r[10]),
            "lbs_cosechadas_real": _sf(r[11]),
            "estado":        str(r[12] or "Activa"),
            "notas":         str(r[13]),
            "cultivo":       str(r[14]),
            "cosecha_detalle": cosecha_det,
        })
    return out

@st.cache_data(ttl=120, show_spinner=False)
def _leer_aplicaciones(id_siembra: str = None) -> list:
    """Lee aplicaciones. Si id_siembra, filtra por esa siembra."""
    from gsheets import get_all_rows
    out = []
    for r in get_all_rows(_K_APLIC):
        if not r or not r[0]:
            continue
        while len(r) < 9:
            r.append("")
        if id_siembra and str(r[0]) != id_siembra:
            continue
        out.append({
            "id_siembra":   str(r[0]),
            "aplicacion":   int(_sf(r[1])) if r[1] else 0,
            "dia_desde":    int(_sf(r[2])) if r[2] else 0,
            "dia_hasta":    int(_sf(r[3])) if r[3] else 0,
            "temporada":    str(r[4]),
            "fertilizante": str(r[5]),
            "lbs":          _sf(r[6]),
            "aplicado_real": str(r[7] or "No").strip(),
            "fecha_aplicado": str(r[8]),
        })
    return out


def _eliminar_siembra(id_siembra: str, row_num: int):
    """Elimina una siembra y todas sus aplicaciones de fertilización."""
    from gsheets import delete_rows, get_all_rows, ws
    # Borrar fila de la siembra
    delete_rows(_K_PROD, [row_num])
    # Borrar sus aplicaciones (reescribir hoja sin ellas)
    todas = get_all_rows(_K_APLIC)
    conservar = [r for r in todas if r and str(r[0]) != id_siembra]
    headers = ["id_siembra", "aplicacion", "dia_desde", "dia_hasta",
               "temporada", "fertilizante", "lbs", "aplicado_real",
               "fecha_aplicado"]
    w = ws(_K_APLIC)
    w.clear()
    w.update("A1", [headers] + conservar, value_input_option="USER_ENTERED")
    _leer_siembras.clear()
    _leer_aplicaciones.clear()


def _reescribir_aplicaciones(id_siembra: str, nuevas_filas: list):
    """Borra todas las aplicaciones de una siembra y escribe las nuevas.
    nuevas_filas: lista de listas con las 9 columnas."""
    from gsheets import get_all_rows, ws, append_rows
    # Leer todo, filtrar las de esta siembra, reescribir el resto + nuevas
    todas = get_all_rows(_K_APLIC)
    conservar = [r for r in todas if r and str(r[0]) != id_siembra]

    headers = ["id_siembra", "aplicacion", "dia_desde", "dia_hasta",
               "temporada", "fertilizante", "lbs", "aplicado_real",
               "fecha_aplicado"]
    w = ws(_K_APLIC)
    w.clear()
    data = [headers] + conservar + nuevas_filas
    w.update("A1", data, value_input_option="USER_ENTERED")
    _leer_aplicaciones.clear()



# ── Helpers ───────────────────────────────────────────────────────────────────
def _col_letra(n: int) -> str:
    """Convierte número de columna (1-based) a letra(s) de Excel."""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _sf(v) -> float:
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except (ValueError, AttributeError):
        return 0.0


def _parse_fecha(v):
    if not v:
        return None
    from datetime import datetime
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(v).strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _calc_mezcla(aplicaciones: list, fert_map: dict) -> dict:
    """
    Dada una lista de (fertilizante, lbs), calcula:
      - grado equivalente (Forma A): promedio simple de cada nutriente / n_fert
      - libras reales (Forma B): suma de lbs * %nutriente
    """
    n_fert = len([a for a in aplicaciones if a[1] > 0])
    if n_fert == 0:
        return {"grado": (0, 0, 0), "reales": (0, 0, 0), "total_lbs": 0}

    # Forma A — grado equivalente (promedio simple de los grados)
    sum_n = sum(fert_map.get(f, {}).get("N", 0) for f, lbs in aplicaciones if lbs > 0)
    sum_p = sum(fert_map.get(f, {}).get("P", 0) for f, lbs in aplicaciones if lbs > 0)
    sum_k = sum(fert_map.get(f, {}).get("K", 0) for f, lbs in aplicaciones if lbs > 0)
    grado = (round(sum_n / n_fert, 1), round(sum_p / n_fert, 1), round(sum_k / n_fert, 1))

    # Forma B — libras reales de nutriente
    real_n = sum(lbs * fert_map.get(f, {}).get("N", 0) / 100 for f, lbs in aplicaciones)
    real_p = sum(lbs * fert_map.get(f, {}).get("P", 0) / 100 for f, lbs in aplicaciones)
    real_k = sum(lbs * fert_map.get(f, {}).get("K", 0) / 100 for f, lbs in aplicaciones)
    reales = (round(real_n, 2), round(real_p, 2), round(real_k, 2))

    total_lbs = sum(lbs for _, lbs in aplicaciones if lbs > 0)
    return {"grado": grado, "reales": reales, "total_lbs": total_lbs}




@st.cache_data(ttl=300, show_spinner=False)
def _ventas_por_semana_cultivo() -> dict:
    """
    Suma las ventas (libras/cantidad) de los productos de cosecha por semana/año.
    Retorna {(año, semana): {producto: cantidad}}.
    Lee una sola vez y cachea — usado para rendimiento por cruce de ventas.
    """
    from excel_helper import leer_pedidos
    # Productos de cosecha de todos los cultivos
    cultivos = _leer_cultivos()
    productos_cosecha = set()
    for c in cultivos:
        productos_cosecha.update(p.lower() for p in c["productos_cosecha"])

    out = {}
    for p in leer_pedidos():
        if p["status"] == "Cancelado":
            continue
        prod_l = str(p["producto"]).lower().strip()
        if prod_l not in productos_cosecha:
            continue
        clave = (int(p["año"]), int(p["semana"]))
        out.setdefault(clave, {})
        out[clave][p["producto"]] = out[clave].get(p["producto"], 0) + float(p["cantidad"] or 0)
    return out


def _rendimiento_por_ventas(siembra: dict) -> dict:
    """
    Calcula el rendimiento real estimado de una siembra cruzando con las ventas
    de la semana de cosecha (semana_siembra + ciclo en semanas).
    Retorna {total, detalle, semana_venta, año_venta} o None.
    """
    if not siembra["fecha_siembra"]:
        return None
    # Lag automático por días de ciclo de esta siembra
    semanas_lag = round(siembra["dias_ciclo"] / 7)
    fecha_venta_est = siembra["fecha_siembra"] + timedelta(weeks=semanas_lag)
    año_v, sem_v, _ = fecha_venta_est.isocalendar()

    ventas = _ventas_por_semana_cultivo()
    detalle = ventas.get((año_v, sem_v), {})
    total = sum(detalle.values())
    return {
        "total": total,
        "detalle": detalle,
        "semana_venta": sem_v,
        "año_venta": año_v,
        "semanas_lag": semanas_lag,
    }


def _proyectar_lbs(semillas: float, germinacion: float,
                   rend_min: float, rend_max: float) -> tuple:
    """Plantas = semillas * germinacion. Lbs = plantas / rend (zanahorias/lb)."""
    plantas = semillas * germinacion
    lbs_max = round(plantas / rend_min, 1) if rend_min > 0 else 0  # menos z/lb = más lbs
    lbs_min = round(plantas / rend_max, 1) if rend_max > 0 else 0
    return lbs_min, lbs_max


def _es_lluvia(fecha) -> bool:
    return fecha and fecha.month in MESES_LLUVIA


@st.cache_data(ttl=300, show_spinner=False)
def _ventas_por_semana_prod(productos_cosecha: tuple) -> dict:
    """Ventas de productos de cosecha por (año, semana, producto).
    Retorna {(año, semana): {producto: lbs}}. Cacheado (1 sola lectura de pedidos)."""
    from excel_helper import leer_pedidos
    prods_map = {p.lower().strip(): p for p in productos_cosecha}
    acum = {}
    for p in leer_pedidos():
        if p["status"] == "Cancelado":
            continue
        pl = p["producto"].lower().strip()
        if pl in prods_map:
            clave = (p["año"], p["semana"])
            nombre = prods_map[pl]
            acum.setdefault(clave, {})
            acum[clave][nombre] = acum[clave].get(nombre, 0) + p["cantidad"]
    return acum


def _rendimiento_por_ventas(siembra: dict, productos_cosecha: list) -> dict:
    """Rendimiento teórico cruzando ventas. Lag automático = días ciclo → semanas.
    Lo vendido en (semana_siembra + lag) es el rendimiento de esa siembra.
    Retorna detalle por producto + total + semana de venta."""
    if not siembra["fecha_siembra"]:
        return {"total": 0, "detalle": {}, "semana_venta": 0,
                "año_venta": 0, "semanas_lag": 0}

    lag_sem = round(siembra["dias_ciclo"] / 7)
    fecha_venta_est = siembra["fecha_siembra"] + timedelta(days=siembra["dias_ciclo"])
    año_v, sem_v, _ = fecha_venta_est.isocalendar()

    ventas = _ventas_por_semana_prod(tuple(productos_cosecha))
    detalle = ventas.get((año_v, sem_v), {})
    total = sum(detalle.values())

    return {"total": total, "detalle": detalle, "semana_venta": sem_v,
            "año_venta": año_v, "semanas_lag": lag_sem}


def _etapa_siembra(siembra: dict) -> tuple:
    """Retorna (dias_transcurridos, etapa_texto, color)."""
    if not siembra["fecha_siembra"]:
        return 0, "Sin fecha", "#999999"
    dias = (date.today() - siembra["fecha_siembra"]).days
    ciclo = siembra["dias_ciclo"]
    if dias < 0:
        return dias, "Programada", "#2196F3"
    elif dias < 22:
        return dias, "Germinación / inicio", "#8DC63F"
    elif dias <= 25:
        return dias, "App 1 — fertilizar", "#E65100"
    elif dias < 50:
        return dias, "Desarrollo vegetativo", "#2D7A2D"
    elif dias <= 55:
        return dias, "App 2 — fertilizar", "#E65100"
    elif dias < ciclo:
        return dias, "Engrosamiento raíz", "#2D7A2D"
    else:
        return dias, "Lista para cosecha", "#B71C1C"


def _siembras_necesitan_fert(siembras: list) -> list:
    """Retorna siembras en ventana de fertilización (para alertas)."""
    alertas = []
    for s in siembras:
        if s["estado"] != "Activa" or not s["fecha_siembra"]:
            continue
        dias = (date.today() - s["fecha_siembra"]).days
        if 22 <= dias <= 25:
            alertas.append((s, 1, dias))
        elif 50 <= dias <= 55:
            alertas.append((s, 2, dias))
    return alertas


# ── Widget para Inicio ────────────────────────────────────────────────────────
def widget_inicio():
    """Aviso compacto de cosechas próximas + alertas de fertilización."""
    try:
        siembras = _leer_siembras()
    except Exception:
        return

    activas = [s for s in siembras if s["estado"] == "Activa"]
    if not activas:
        return

    hoy = date.today()
    sem_actual = hoy.isocalendar()[1]

    # Cosechas de esta semana y próxima
    cosechas_prox = [s for s in activas
                     if s["fecha_cosecha_est"]
                     and 0 <= (s["fecha_cosecha_est"] - hoy).days <= 14]
    # Fertilización pendiente
    fert_pend = _siembras_necesitan_fert(activas)

    if not cosechas_prox and not fert_pend:
        return

    st.markdown("##### 🌱 Producción")
    if cosechas_prox:
        for s in cosechas_prox[:4]:
            dias = (s["fecha_cosecha_est"] - hoy).days
            cuando = "hoy" if dias == 0 else f"en {dias} día(s)"
            st.caption(f"🥕 **{s['variedad']}** ({s['lugar']}) — "
                       f"cosecha {cuando} · est. "
                       f"{s['lbs_proyectadas_min']:.0f}–{s['lbs_proyectadas_max']:.0f} lbs")
    if fert_pend:
        for s, app, dias in fert_pend[:4]:
            st.caption(f"🧪 **{s['variedad']}** ({s['lugar']}) — "
                       f"toca fertilizar (App {app}, día {dias})")


# ── Vista: Nueva Siembra ──────────────────────────────────────────────────────
def _tab_nueva_siembra():
    cultivos = _leer_cultivos()
    fert_map = _leer_fertilizantes()

    if not cultivos:
        st.warning("No hay cultivos configurados. Revisá la pestaña Cultivos.")
        return

    nombres_cultivo = sorted({c["cultivo"] for c in cultivos})

    c1, c2 = st.columns(2)
    cultivo_sel = c1.selectbox("Cultivo", nombres_cultivo, key="ns_cultivo")
    variedades = [c for c in cultivos if c["cultivo"] == cultivo_sel]
    var_nombres = [c["variedad"] for c in variedades]
    var_sel = c2.selectbox("Variedad", var_nombres, key="ns_variedad")

    cult = next(c for c in variedades if c["variedad"] == var_sel)

    st.caption(f"Ciclo: **{cult['dias_ciclo']} días** · "
               f"Germinación: **{cult['germinacion']*100:.0f}%** · "
               f"Rendimiento: **{cult['rend_min']}–{cult['rend_max']} zanahorias/lb**")

    # Datos de la siembra
    d1, d2, d3 = st.columns(3)
    fecha_siembra = d1.date_input("Fecha de siembra", value=date.today(),
                                   key="ns_fecha")
    semillas = d2.number_input("Cantidad de semillas", min_value=0,
                                value=100000, step=10000, key="ns_semillas")
    tablones = d3.number_input("Tablones sembrados", min_value=0.0,
                                value=0.0, step=1.0, key="ns_tablones")

    e1, e2 = st.columns(2)
    lugar = e1.text_input("Lugar", placeholder="Terreno / parcela...",
                           key="ns_lugar")
    # Fecha cosecha auto-calculada (solo lectura — se ajusta en Siembras Activas)
    fecha_cosecha = fecha_siembra + timedelta(days=cult["dias_ciclo"])
    e2.markdown(
        f"<div style='padding-top:4px'><small style='color:#888'>"
        f"Fecha cosecha estimada</small><br>"
        f"<b style='font-size:1.05rem'>{fecha_cosecha.strftime('%d/%m/%Y')}</b>"
        f"<br><small style='color:#aaa'>(calculada: siembra + "
        f"{cult['dias_ciclo']} días · ajustable luego)</small></div>",
        unsafe_allow_html=True)

    # Proyección
    lbs_min, lbs_max = _proyectar_lbs(semillas, cult["germinacion"],
                                       cult["rend_min"], cult["rend_max"])
    st.info(f"📊 Proyección: **{lbs_min:.0f} – {lbs_max:.0f} lbs** "
            f"({semillas*cult['germinacion']:.0f} plantas estimadas)")

    notas = st.text_input("Notas", key="ns_notas",
                          placeholder="Observaciones de la siembra...")

    # ── Programa de fertilización (editable) ──────────────────────────────────
    st.divider()
    st.markdown("##### 🧪 Programa de fertilización (2 aplicaciones)")
    es_lluvia = _es_lluvia(fecha_siembra)
    st.caption(f"Temporada detectada: **{'Lluviosa' if es_lluvia else 'Seca'}** "
               f"(según mes de siembra). Las dosis sugeridas se cargan abajo "
               f"y podés ajustarlas.")

    dosis_cult = _DOSIS_SUGERIDAS.get(cultivo_sel, {})
    fert_opts = sorted(fert_map.keys())
    aplicaciones_data = {}

    for app_num in (1, 2):
        app_cfg = dosis_cult.get(app_num, {})
        dia_d = app_cfg.get("dia_desde", 22 if app_num == 1 else 50)
        dia_h = app_cfg.get("dia_hasta", 25 if app_num == 1 else 55)
        sugeridas = app_cfg.get("lluvia" if es_lluvia else "seca", [])

        with st.expander(f"Aplicación {app_num} — Día {dia_d}–{dia_h}",
                         expanded=True):
            n_lineas = st.number_input(
                f"Número de fertilizantes en App {app_num}",
                min_value=1, max_value=6,
                value=max(len(sugeridas), 1),
                key=f"ns_n_app{app_num}")
            lineas_app = []
            for i in range(int(n_lineas)):
                fc1, fc2 = st.columns([2, 1])
                # Pre-cargar sugerencia si existe
                if i < len(sugeridas):
                    fert_def, lbs_def = sugeridas[i]
                    idx_def = fert_opts.index(fert_def) if fert_def in fert_opts else 0
                else:
                    idx_def, lbs_def = 0, 0.0
                fert = fc1.selectbox(f"Fertilizante {i+1}", fert_opts,
                                      index=idx_def,
                                      key=f"ns_fert_{app_num}_{i}",
                                      label_visibility="collapsed")
                lbs = fc2.number_input(f"Lbs {i+1}", min_value=0.0,
                                        value=float(lbs_def), step=1.0,
                                        key=f"ns_lbs_{app_num}_{i}",
                                        label_visibility="collapsed")
                lineas_app.append((fert, lbs))

            # Cálculo de mezcla en vivo
            mezcla = _calc_mezcla(lineas_app, fert_map)
            g = mezcla["grado"]
            r = mezcla["reales"]
            st.caption(
                f"**Grado equivalente:** {g[0]}-{g[1]}-{g[2]}  ·  "
                f"**Nutriente real:** N {r[0]:.1f} · P {r[1]:.1f} · "
                f"K {r[2]:.1f} lbs  ·  Total mezcla: {mezcla['total_lbs']:.0f} lbs")
            aplicaciones_data[app_num] = {
                "dia_desde": dia_d, "dia_hasta": dia_h,
                "temporada": "Lluviosa" if es_lluvia else "Seca",
                "lineas": lineas_app,
            }

    # ── Guardar ───────────────────────────────────────────────────────────────
    st.divider()
    if st.button("🌱 Registrar siembra", type="primary", key="ns_guardar"):
        if not lugar.strip():
            st.error("Indicá el lugar de la siembra.")
            return
        from gsheets import append_rows

        id_siembra = f"S{date.today().strftime('%y%m%d')}_{str(uuid.uuid4())[:4].upper()}"
        semana_cos = fecha_cosecha.isocalendar()[1]

        with st.spinner("Guardando siembra..."):
            # Fila principal
            append_rows(_K_PROD, [[
                id_siembra, var_sel,
                fecha_siembra.strftime("%d/%m/%Y"), semillas, lugar.strip(),
                tablones, fecha_cosecha.strftime("%d/%m/%Y"), semana_cos,
                cult["dias_ciclo"], lbs_min, lbs_max, "", "Activa",
                notas.strip(), cultivo_sel, "",
            ]])

            # Aplicaciones congeladas (Opción B)
            filas_aplic = []
            for app_num, app_data in aplicaciones_data.items():
                for fert, lbs in app_data["lineas"]:
                    if lbs > 0:
                        filas_aplic.append([
                            id_siembra, app_num,
                            app_data["dia_desde"], app_data["dia_hasta"],
                            app_data["temporada"], fert, lbs, "No", "",
                        ])
            if filas_aplic:
                append_rows(_K_APLIC, filas_aplic)

        _leer_siembras.clear()
        st.success(f"✅ Siembra **{id_siembra}** registrada — "
                   f"{var_sel} en {lugar}. Cosecha estimada: "
                   f"{fecha_cosecha.strftime('%d/%m/%Y')}.")
        st.rerun()


# ── Vista: Siembras Activas ───────────────────────────────────────────────────
def _tab_siembras_activas():
    siembras = _leer_siembras()
    fert_map = _leer_fertilizantes()
    activas = [s for s in siembras if s["estado"] == "Activa"]

    if not activas:
        st.info("No hay siembras activas. Creá una en la pestaña Nueva Siembra.")
        return

    # Alertas de fertilización arriba
    alertas = _siembras_necesitan_fert(activas)
    if alertas:
        st.warning(f"🧪 **{len(alertas)} siembra(s)** en ventana de fertilización:")
        for s, app, dias in alertas:
            st.caption(f"  · {s['variedad']} ({s['lugar']}) — App {app}, día {dias}")
        st.divider()

    st.caption(f"{len(activas)} siembra(s) activa(s)")

    # Lectura cacheada de TODAS las aplicaciones (1 sola vez por render)
    todas_aplic = _leer_aplicaciones()

    for s in sorted(activas, key=lambda x: x["fecha_siembra"] or date.today()):
        dias, etapa, color = _etapa_siembra(s)
        cosecha_str = (s["fecha_cosecha_est"].strftime("%d/%m/%Y")
                       if s["fecha_cosecha_est"] else "—")

        with st.expander(
            f"🥕 {s['variedad']} · {s['lugar']} · Día {dias} · {etapa}",
            expanded=False
        ):
            st.markdown(
                f"<div style='background:{color};color:white;padding:5px 10px;"
                f"border-radius:4px;font-size:.82rem;margin-bottom:6px'>"
                f"<b>{etapa}</b> · Día {dias} de {s['dias_ciclo']} · "
                f"Cosecha est.: {cosecha_str}</div>",
                unsafe_allow_html=True)

            m1, m2, m3 = st.columns(3)
            m1.metric("Semillas", f"{s['cantidad_semillas']:,.0f}")
            m2.metric("Tablones", f"{s['tablones']:.0f}")
            m3.metric("Proyección",
                      f"{s['lbs_proyectadas_min']:.0f}–{s['lbs_proyectadas_max']:.0f} lbs")

            # Aplicaciones de esta siembra (desde lectura cacheada)
            mias = [a for a in todas_aplic if a["id_siembra"] == s["id_siembra"]]
            if mias:
                st.markdown("**Programa de fertilización:**")
                apps_nums = sorted({a["aplicacion"] for a in mias})
                for app_num in apps_nums:
                    app_lineas = [(a["fertilizante"], a["lbs"])
                                  for a in mias if a["aplicacion"] == app_num]
                    if not app_lineas:
                        continue
                    mezcla = _calc_mezcla(app_lineas, fert_map)
                    g, rr = mezcla["grado"], mezcla["reales"]
                    detalle = " + ".join(f"{f} {l:.0f}lb" for f, l in app_lineas if l > 0)
                    a0 = next((a for a in mias if a["aplicacion"] == app_num), None)
                    dia_info = f"Día {a0['dia_desde']}–{a0['dia_hasta']}" if a0 else ""
                    aplicado = a0 and a0["aplicado_real"].strip().lower() in ("sí", "si")
                    chk = "✅" if aplicado else "⏳"
                    st.caption(
                        f"{chk} **App {app_num}** ({dia_info}): {detalle}  →  "
                        f"Grado {g[0]}-{g[1]}-{g[2]} · "
                        f"Real N{rr[0]:.1f} P{rr[1]:.1f} K{rr[2]:.1f}")

            if s["notas"]:
                st.caption(f"📝 {s['notas']}")

            # ── Editar siembra ────────────────────────────────────────────────
            st.divider()
            _edit_key = f"prod_edit_{s['id_siembra']}"
            ce1, ce2 = st.columns(2)
            if ce1.button("✏️ Editar datos", key=f"btn_edit_{s['id_siembra']}",
                          use_container_width=True):
                st.session_state[_edit_key] = not st.session_state.get(_edit_key, False)
            _del_key = f"prod_del_{s['id_siembra']}"
            if ce2.button("🗑️ Eliminar siembra", key=f"btn_del_{s['id_siembra']}",
                          use_container_width=True):
                st.session_state[_del_key] = True

            # Confirmación de eliminación
            if st.session_state.get(_del_key, False):
                st.error(f"¿Eliminar definitivamente la siembra **{s['variedad']} "
                         f"· {s['lugar']}**? Se borrarán también sus aplicaciones "
                         f"de fertilización.")
                dc1, dc2 = st.columns(2)
                if dc1.button("✅ Sí, eliminar", key=f"del_ok_{s['id_siembra']}",
                              type="primary", use_container_width=True):
                    with st.spinner("Eliminando..."):
                        _eliminar_siembra(s["id_siembra"], s["row_num"])
                    st.session_state.pop(_del_key, None)
                    st.success("Siembra eliminada.")
                    st.rerun()
                if dc2.button("Cancelar", key=f"del_no_{s['id_siembra']}",
                              use_container_width=True):
                    st.session_state.pop(_del_key, None)
                    st.rerun()

            if st.session_state.get(_edit_key, False):
                # NOTA: fuera de st.form para que la fecha de cosecha recalcule en vivo
                st.markdown("**Editar siembra**")
                ec1, ec2 = st.columns(2)
                nv_fecha_siembra = ec1.date_input(
                    "Fecha de siembra",
                    value=s["fecha_siembra"] or date.today(),
                    key=f"ed_fs_{s['id_siembra']}")
                nv_semillas = ec2.number_input(
                    "Cantidad de semillas", min_value=0,
                    value=int(s["cantidad_semillas"]), step=10000,
                    key=f"ed_sem_{s['id_siembra']}")
                ec3, ec4 = st.columns(2)
                nv_lugar = ec3.text_input(
                    "Lugar", value=s["lugar"],
                    key=f"ed_lug_{s['id_siembra']}")
                nv_tablones = ec4.number_input(
                    "Tablones", min_value=0.0,
                    value=float(s["tablones"]), step=1.0,
                    key=f"ed_tab_{s['id_siembra']}")
                ec5, ec6 = st.columns(2)
                nv_dias = ec5.number_input(
                    "Días de ciclo", min_value=1,
                    value=int(s["dias_ciclo"]), step=1,
                    key=f"ed_dias_{s['id_siembra']}")

                # Fecha cosecha: recalcula EN VIVO desde siembra + días (fuera del form)
                _auto_cos = nv_fecha_siembra + timedelta(days=int(nv_dias))
                _usar_auto = ec6.checkbox(
                    "Recalcular cosecha automáticamente",
                    value=True, key=f"ed_auto_{s['id_siembra']}",
                    help="Activado: cosecha = siembra + días de ciclo. "
                         "Desactivá para ajustar manual (adelantos/atrasos).")
                if _usar_auto:
                    nv_fecha_cosecha = _auto_cos
                    ec6.markdown(
                        f"<small style='color:#2D7A2D'>Cosecha estimada: "
                        f"<b>{_auto_cos.strftime('%d/%m/%Y')}</b></small>",
                        unsafe_allow_html=True)
                else:
                    nv_fecha_cosecha = ec6.date_input(
                        "Fecha cosecha (manual)",
                        value=s["fecha_cosecha_est"] or _auto_cos,
                        key=f"ed_fc_{s['id_siembra']}")

                nv_notas = st.text_input(
                    "Notas", value=s["notas"],
                    key=f"ed_not_{s['id_siembra']}")

                if st.button("💾 Guardar cambios", type="primary",
                             key=f"ed_save_{s['id_siembra']}",
                             use_container_width=True):
                    from gsheets import update_cells
                    cultivos = _leer_cultivos()
                    cult_s = next((c for c in cultivos
                                   if c["variedad"] == s["variedad"]), None)
                    if cult_s:
                        lmin, lmax = _proyectar_lbs(
                            nv_semillas, cult_s["germinacion"],
                            cult_s["rend_min"], cult_s["rend_max"])
                    else:
                        lmin, lmax = s["lbs_proyectadas_min"], s["lbs_proyectadas_max"]
                    sem_cos = nv_fecha_cosecha.isocalendar()[1]
                    rn = s["row_num"]
                    with st.spinner("Guardando cambios..."):
                        update_cells(_K_PROD, [
                            {"range": f"{_col_letra(3)}{rn}",  "values": [[nv_fecha_siembra.strftime("%d/%m/%Y")]]},
                            {"range": f"{_col_letra(4)}{rn}",  "values": [[nv_semillas]]},
                            {"range": f"{_col_letra(5)}{rn}",  "values": [[nv_lugar.strip()]]},
                            {"range": f"{_col_letra(6)}{rn}",  "values": [[nv_tablones]]},
                            {"range": f"{_col_letra(7)}{rn}",  "values": [[nv_fecha_cosecha.strftime("%d/%m/%Y")]]},
                            {"range": f"{_col_letra(8)}{rn}",  "values": [[sem_cos]]},
                            {"range": f"{_col_letra(9)}{rn}",  "values": [[int(nv_dias)]]},
                            {"range": f"{_col_letra(10)}{rn}", "values": [[lmin]]},
                            {"range": f"{_col_letra(11)}{rn}", "values": [[lmax]]},
                            {"range": f"{_col_letra(14)}{rn}", "values": [[nv_notas.strip()]]},
                        ])
                    _leer_siembras.clear()
                    st.session_state[_edit_key] = False
                    st.success("✅ Siembra actualizada.")
                    st.rerun()

            # ── Editar fertilización ──────────────────────────────────────────
            _fert_key = f"prod_fert_{s['id_siembra']}"
            if st.button("🧪 Editar fertilización", key=f"btn_fert_{s['id_siembra']}"):
                st.session_state[_fert_key] = not st.session_state.get(_fert_key, False)

            if st.session_state.get(_fert_key, False):
                _editor_fertilizacion(s, fert_map)





def _editor_fertilizacion(s, fert_map):
    """Editor de aplicaciones de fertilización de una siembra (editar/agregar/eliminar)."""
    st.markdown("**Editar fertilización** — corregí, agregá o eliminá aplicaciones.")

    sid = s["id_siembra"]
    aplic = _leer_aplicaciones(sid)
    fert_opts = sorted(fert_map.keys())

    # Agrupar por número de aplicación
    apps_existentes = sorted({a["aplicacion"] for a in aplic})

    # Estado de cuántas aplicaciones mostrar (permite agregar nuevas)
    _n_apps_key = f"fert_napps_{sid}"
    if _n_apps_key not in st.session_state:
        st.session_state[_n_apps_key] = max(len(apps_existentes), 2)

    n_apps = st.session_state[_n_apps_key]

    # Acumulador para N-P-K total de la siembra
    total_n = total_p = total_k = 0.0
    nuevas_filas = []

    for app_num in range(1, int(n_apps) + 1):
        lineas_prev = [a for a in aplic if a["aplicacion"] == app_num]
        # Defaults de ventana
        if lineas_prev:
            dia_d = lineas_prev[0]["dia_desde"]
            dia_h = lineas_prev[0]["dia_hasta"]
            temp  = lineas_prev[0]["temporada"]
            aplicado_prev = lineas_prev[0]["aplicado_real"]
            fecha_prev = lineas_prev[0]["fecha_aplicado"]
        else:
            # Aplicación extra nueva
            dia_d, dia_h = (22, 25) if app_num == 1 else \
                           (50, 55) if app_num == 2 else (0, 0)
            temp = "Seca"
            aplicado_prev, fecha_prev = "No", ""

        with st.expander(f"Aplicación {app_num}" +
                         (f" (Día {dia_d}–{dia_h})" if dia_d else " (extra)"),
                         expanded=True):
            # Ventana de días (editable)
            wc1, wc2, wc3 = st.columns(3)
            nv_dia_d = wc1.number_input("Día desde", min_value=0, max_value=200,
                                         value=int(dia_d),
                                         key=f"fe_dd_{sid}_{app_num}")
            nv_dia_h = wc2.number_input("Día hasta", min_value=0, max_value=200,
                                         value=int(dia_h),
                                         key=f"fe_dh_{sid}_{app_num}")
            nv_temp = wc3.selectbox("Temporada", ["Seca", "Lluviosa", "Extra"],
                                     index=["Seca","Lluviosa","Extra"].index(temp)
                                           if temp in ["Seca","Lluviosa","Extra"] else 0,
                                     key=f"fe_tmp_{sid}_{app_num}")

            # Fertilizantes de esta aplicación
            _n_lin_key = f"fert_nlin_{sid}_{app_num}"
            if _n_lin_key not in st.session_state:
                st.session_state[_n_lin_key] = max(len(lineas_prev), 1)
            n_lin = st.session_state[_n_lin_key]

            lineas_app = []
            for i in range(int(n_lin)):
                lc1, lc2 = st.columns([2, 1])
                if i < len(lineas_prev):
                    f_def = lineas_prev[i]["fertilizante"]
                    l_def = lineas_prev[i]["lbs"]
                    idx_def = fert_opts.index(f_def) if f_def in fert_opts else 0
                else:
                    idx_def, l_def = 0, 0.0
                fert = lc1.selectbox(f"Fertilizante {i+1}", fert_opts,
                                      index=idx_def,
                                      key=f"fe_f_{sid}_{app_num}_{i}",
                                      label_visibility="collapsed")
                lbs = lc2.number_input(f"Lbs {i+1}", min_value=0.0,
                                        value=float(l_def), step=1.0,
                                        key=f"fe_l_{sid}_{app_num}_{i}",
                                        label_visibility="collapsed")
                lineas_app.append((fert, lbs))

            bc1, bc2 = st.columns(2)
            if bc1.button(f"+ Fertilizante", key=f"fe_addlin_{sid}_{app_num}"):
                st.session_state[_n_lin_key] = int(n_lin) + 1
                st.rerun()
            if int(n_lin) > 1 and bc2.button(f"− Quitar último",
                                              key=f"fe_dellin_{sid}_{app_num}"):
                st.session_state[_n_lin_key] = int(n_lin) - 1
                st.rerun()

            # Mezcla en vivo
            mezcla = _calc_mezcla(lineas_app, fert_map)
            g, rr = mezcla["grado"], mezcla["reales"]
            st.caption(f"**Grado:** {g[0]}-{g[1]}-{g[2]} · "
                       f"**Real:** N {rr[0]:.1f} · P {rr[1]:.1f} · K {rr[2]:.1f} lbs")
            total_n += rr[0]; total_p += rr[1]; total_k += rr[2]

            # Registro de aplicación real
            rc1, rc2 = st.columns([1, 2])
            ya_aplicado = rc1.checkbox("Ya aplicado",
                                        value=(aplicado_prev.lower() in ("sí","si")),
                                        key=f"fe_ap_{sid}_{app_num}")
            from datetime import datetime
            fecha_def = None
            if fecha_prev:
                try:
                    fecha_def = datetime.strptime(fecha_prev, "%d/%m/%Y").date()
                except ValueError:
                    fecha_def = None
            fecha_aplic = ""
            if ya_aplicado:
                fa = rc2.date_input("Fecha aplicada",
                                     value=fecha_def or date.today(),
                                     key=f"fe_fa_{sid}_{app_num}")
                fecha_aplic = fa.strftime("%d/%m/%Y")

            # Acumular filas para guardar
            for fert, lbs in lineas_app:
                if lbs > 0:
                    nuevas_filas.append([
                        sid, app_num, nv_dia_d, nv_dia_h, nv_temp,
                        fert, lbs, "Sí" if ya_aplicado else "No", fecha_aplic,
                    ])

    # Botones globales
    st.divider()
    gc1, gc2, gc3 = st.columns(3)
    if gc1.button("➕ Agregar aplicación", key=f"fe_addapp_{sid}"):
        st.session_state[_n_apps_key] = int(n_apps) + 1
        st.rerun()
    if int(n_apps) > 1 and gc2.button("➖ Quitar última aplicación",
                                       key=f"fe_delapp_{sid}"):
        st.session_state[_n_apps_key] = int(n_apps) - 1
        st.rerun()

    # N-P-K total de la siembra
    st.info(f"📊 **N-P-K total de la siembra** (todas las aplicaciones): "
            f"N {total_n:.1f} · P {total_p:.1f} · K {total_k:.1f} lbs reales")

    if gc3.button("💾 Guardar fertilización", type="primary",
                  key=f"fe_save_{sid}"):
        with st.spinner("Guardando fertilización..."):
            _reescribir_aplicaciones(sid, nuevas_filas)
        # Limpiar estado de edición
        for k in list(st.session_state.keys()):
            if k.startswith(f"fert_nlin_{sid}") or k == f"fert_napps_{sid}":
                st.session_state.pop(k, None)
        st.session_state[f"prod_fert_{sid}"] = False
        st.success("✅ Fertilización actualizada.")
        st.rerun()


# ── Vista: Cosecha / Cierre ───────────────────────────────────────────────────
def _tab_cosecha():
    siembras = _leer_siembras()
    cultivos = _leer_cultivos()
    activas = [s for s in siembras if s["estado"] == "Activa"]

    if not activas:
        st.info("No hay siembras activas para cosechar.")
        return

    # Mapa cultivo → productos cosecha
    prod_cosecha_map = {}
    for c in cultivos:
        prod_cosecha_map.setdefault(c["cultivo"], c["productos_cosecha"])

    opts = {f"{s['variedad']} · {s['lugar']} · "
            f"siembra {s['fecha_siembra'].strftime('%d/%m') if s['fecha_siembra'] else '?'}"
            : s for s in activas}
    sel = st.selectbox("Siembra a cerrar", list(opts.keys()), key="cos_sel")
    s = opts[sel]

    dias, etapa, color = _etapa_siembra(s)
    st.caption(f"Día {dias} de {s['dias_ciclo']} · {etapa} · "
               f"Proyección: {s['lbs_proyectadas_min']:.0f}–"
               f"{s['lbs_proyectadas_max']:.0f} lbs")

    # Productos de cosecha de este cultivo
    productos = prod_cosecha_map.get(s["cultivo"], [])
    if not productos:
        productos = ["Mini", "Zanahoria Baby", "Zanahoria Babyr", "Zanahoria Babyl"]

    # ── Rendimiento estimado por ventas (cruce semana siembra → semana venta) ──
    rend_ventas = _rendimiento_por_ventas(s, productos)
    sugeridos = {}
    if rend_ventas and rend_ventas["total"] > 0:
        sugeridos = rend_ventas["detalle"]
        st.success(
            f"💡 **Rendimiento estimado por ventas:** "
            f"{rend_ventas['total']:.0f} lbs vendidas en semana "
            f"{rend_ventas['semana_venta']}/{rend_ventas['año_venta']} "
            f"(lag {rend_ventas['semanas_lag']} sem). "
            f"Se cargan abajo como sugerencia — podés ajustarlos.")

    st.markdown("##### 🥕 Libras cosechadas por producto")
    st.caption("Valores sugeridos desde ventas. Editá si pesaste en campo.")
    detalle = {}
    total_real = 0.0
    cols = st.columns(min(len(productos), 4))
    for i, prod in enumerate(productos):
        col = cols[i % len(cols)]
        val_sug = float(sugeridos.get(prod, 0))
        lbs = col.number_input(prod, min_value=0.0, value=val_sug, step=1.0,
                                key=f"cos_{s['id_siembra']}_{i}")
        detalle[prod] = lbs
        total_real += lbs

    st.markdown(f"### Total real: **{total_real:.1f} lbs**")

    # Comparación vs proyección
    if total_real > 0:
        prom_proy = (s["lbs_proyectadas_min"] + s["lbs_proyectadas_max"]) / 2
        if prom_proy > 0:
            acierto = total_real / prom_proy * 100
            color_ac = "#2D7A2D" if 85 <= acierto <= 115 else "#E65100"
            st.markdown(
                f"<div style='background:{color_ac};color:white;padding:8px;"
                f"border-radius:6px;text-align:center'>"
                f"<b>Acierto vs proyección: {acierto:.0f}%</b><br>"
                f"<small>Real {total_real:.0f} lbs vs proyectado "
                f"{prom_proy:.0f} lbs</small></div>",
                unsafe_allow_html=True)

        # Mix de productos
        st.caption("**Mix de cosecha:** " + " · ".join(
            f"{p}: {l/total_real*100:.0f}%" for p, l in detalle.items() if l > 0))

    # Días reales
    if s["fecha_siembra"]:
        dias_reales = (date.today() - s["fecha_siembra"]).days
        st.caption(f"Días reales de ciclo: **{dias_reales}** "
                   f"(teórico: {s['dias_ciclo']})")

    if st.button("✅ Cerrar cosecha", type="primary", key="cos_cerrar",
                 disabled=total_real <= 0):
        from gsheets import update_cells
        dias_reales = ((date.today() - s["fecha_siembra"]).days
                       if s["fecha_siembra"] else s["dias_ciclo"])
        with st.spinner("Cerrando cosecha..."):
            rn = s["row_num"]
            update_cells(_K_PROD, [
                {"range": f"{_col_letra(12)}{rn}", "values": [[round(total_real, 1)]]},
                {"range": f"{_col_letra(13)}{rn}", "values": [["Cosechada"]]},
                {"range": f"{_col_letra(9)}{rn}",  "values": [[dias_reales]]},
                {"range": f"{_col_letra(16)}{rn}", "values": [[json.dumps(detalle)]]},
            ])
        _leer_siembras.clear()
        st.success(f"✅ Cosecha cerrada — {total_real:.1f} lbs totales.")
        st.rerun()


# ── Vista: Proyección ─────────────────────────────────────────────────────────
def _tab_proyeccion():
    siembras = _leer_siembras()
    activas = [s for s in siembras if s["estado"] == "Activa"]

    if not activas:
        st.info("No hay siembras activas.")
        return

    hoy = date.today()
    import pandas as pd

    rows = []
    for s in sorted(activas, key=lambda x: x["fecha_cosecha_est"] or date.max):
        if not s["fecha_cosecha_est"]:
            continue
        dias_falta = (s["fecha_cosecha_est"] - hoy).days
        rows.append({
            "Variedad":  s["variedad"],
            "Lugar":     s["lugar"],
            "Cosecha":   s["fecha_cosecha_est"].strftime("%d/%m/%Y"),
            "Semana":    s["semana_cosecha"],
            "En días":   dias_falta,
            "Lbs mín":   s["lbs_proyectadas_min"],
            "Lbs máx":   s["lbs_proyectadas_max"],
        })

    if not rows:
        st.info("Sin proyecciones de cosecha.")
        return

    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True)

    # Totales próximas 4 semanas
    sem_actual = hoy.isocalendar()[1]
    prox = [s for s in activas
            if s["fecha_cosecha_est"]
            and 0 <= (s["fecha_cosecha_est"] - hoy).days <= 28]
    if prox:
        tmin = sum(s["lbs_proyectadas_min"] for s in prox)
        tmax = sum(s["lbs_proyectadas_max"] for s in prox)
        st.success(f"📊 Próximas 4 semanas: **{tmin:.0f} – {tmax:.0f} lbs** "
                   f"en {len(prox)} cosecha(s)")


# ── Vista: Historial (siembras cosechadas) ────────────────────────────────────
def _tab_historial():
    siembras = _leer_siembras()
    cerradas = [s for s in siembras if s["estado"] != "Activa"]

    if not cerradas:
        st.info("No hay siembras cerradas todavía. Las cosechadas aparecerán acá.")
        return

    st.caption(f"{len(cerradas)} siembra(s) cerrada(s)")

    import pandas as pd
    rows = []
    for s in cerradas:
        prom_proy = (s["lbs_proyectadas_min"] + s["lbs_proyectadas_max"]) / 2
        acierto = (s["lbs_cosechadas_real"] / prom_proy * 100) if prom_proy > 0 else 0
        rows.append({
            "Variedad":   s["variedad"],
            "Lugar":      s["lugar"],
            "Siembra":    s["fecha_siembra"].strftime("%d/%m/%Y") if s["fecha_siembra"] else "—",
            "Cosecha":    s["fecha_cosecha_est"].strftime("%d/%m/%Y") if s["fecha_cosecha_est"] else "—",
            "Real (lbs)": s["lbs_cosechadas_real"],
            "Proyectado": round(prom_proy, 0),
            "Acierto %":  round(acierto, 0),
            "Estado":     s["estado"],
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True)

    st.divider()
    st.markdown("##### Gestionar siembra cerrada")
    opts = {f"{s['variedad']} · {s['lugar']} · "
            f"{s['fecha_siembra'].strftime('%d/%m/%Y') if s['fecha_siembra'] else '?'} "
            f"({s['estado']})": s for s in cerradas}
    sel = st.selectbox("Seleccioná una siembra cerrada", list(opts.keys()),
                       key="hist_sel")
    s = opts[sel]

    # Detalle de cosecha
    if s["cosecha_detalle"]:
        st.markdown("**Detalle de cosecha:**")
        det = s["cosecha_detalle"]
        total = sum(det.values()) if det else 0
        cols = st.columns(min(len(det), 4))
        for i, (prod, lbs) in enumerate(det.items()):
            cols[i % len(cols)].metric(prod, f"{lbs:.0f} lbs")
        if total > 0:
            st.caption("**Mix:** " + " · ".join(
                f"{p}: {l/total*100:.0f}%" for p, l in det.items() if l > 0))

    # Reabrir
    h1, h2 = st.columns(2)
    if h1.button("🔄 Reabrir (volver a Activa)", key=f"hist_reopen_{s['id_siembra']}",
                 use_container_width=True,
                 help="Vuelve a marcar la siembra como Activa para corregir o re-cosechar."):
        from gsheets import update_cells
        rn = s["row_num"]
        with st.spinner("Reabriendo..."):
            update_cells(_K_PROD, [
                {"range": f"{_col_letra(13)}{rn}", "values": [["Activa"]]},
            ])
        _leer_siembras.clear()
        st.success(f"✅ Siembra reabierta — vuelve a aparecer en Siembras Activas.")
        st.rerun()

    if h2.button("🗑️ Eliminar definitivamente", key=f"hist_del_{s['id_siembra']}",
                 use_container_width=True):
        st.session_state[f"hist_delconf_{s['id_siembra']}"] = True

    if st.session_state.get(f"hist_delconf_{s['id_siembra']}", False):
        st.error(f"¿Eliminar definitivamente **{s['variedad']} · {s['lugar']}**? "
                 f"Se borra el registro y sus aplicaciones.")
        dc1, dc2 = st.columns(2)
        if dc1.button("✅ Sí, eliminar", key=f"hist_delok_{s['id_siembra']}",
                      type="primary", use_container_width=True):
            with st.spinner("Eliminando..."):
                _eliminar_siembra(s["id_siembra"], s["row_num"])
            st.session_state.pop(f"hist_delconf_{s['id_siembra']}", None)
            st.success("Siembra eliminada.")
            st.rerun()
        if dc2.button("Cancelar", key=f"hist_delno_{s['id_siembra']}",
                      use_container_width=True):
            st.session_state.pop(f"hist_delconf_{s['id_siembra']}", None)
            st.rerun()


# ── Vista: Configuración (cultivos, fertilizantes) ────────────────────────────
def _tab_config():
    import pandas as pd
    st.markdown("##### 🌾 Cultivos y Variedades")
    st.caption("Editá ciclo, germinación, rendimiento y productos de cosecha. "
               "Agregá variedades o cultivos nuevos.")

    cultivos = _leer_cultivos()
    df_cult = pd.DataFrame([{
        "Cultivo": c["cultivo"], "Variedad": c["variedad"],
        "Dias_Ciclo": c["dias_ciclo"], "Germinacion": c["germinacion"],
        "Rend_Min": c["rend_min"], "Rend_Max": c["rend_max"],
        "Productos_Cosecha": ",".join(c["productos_cosecha"]),
    } for c in cultivos])

    edited_cult = st.data_editor(df_cult, num_rows="dynamic",
                                  hide_index=True, use_container_width=True,
                                  key="cfg_cult")
    if st.button("💾 Guardar cultivos", key="cfg_save_cult"):
        from gsheets import ws
        with st.spinner("Guardando..."):
            data = [["Cultivo", "Variedad", "Dias_Ciclo", "Germinacion",
                     "Rend_Min", "Rend_Max", "Productos_Cosecha"]]
            for _, r in edited_cult.iterrows():
                if str(r["Cultivo"]).strip():
                    data.append([r["Cultivo"], r["Variedad"], r["Dias_Ciclo"],
                                 r["Germinacion"], r["Rend_Min"], r["Rend_Max"],
                                 r["Productos_Cosecha"]])
            w = ws(_K_CULT)
            w.clear()
            w.update("A1", data, value_input_option="USER_ENTERED")
        _leer_cultivos.clear()
        st.success("✅ Cultivos actualizados.")
        st.rerun()

    st.divider()
    st.markdown("##### 🧪 Fertilizantes (N-P-K)")
    fert_map = _leer_fertilizantes()
    df_fert = pd.DataFrame([{
        "Fertilizante": k, "N": v["N"], "P": v["P"], "K": v["K"]
    } for k, v in fert_map.items()])

    edited_fert = st.data_editor(df_fert, num_rows="dynamic",
                                  hide_index=True, use_container_width=True,
                                  key="cfg_fert")
    if st.button("💾 Guardar fertilizantes", key="cfg_save_fert"):
        from gsheets import ws
        with st.spinner("Guardando..."):
            data = [["Fertilizante", "N", "P", "K"]]
            for _, r in edited_fert.iterrows():
                if str(r["Fertilizante"]).strip():
                    data.append([r["Fertilizante"], r["N"], r["P"], r["K"]])
            w = ws(_K_FERT)
            w.clear()
            w.update("A1", data, value_input_option="USER_ENTERED")
        _leer_fertilizantes.clear()
        st.success("✅ Fertilizantes actualizados.")
        st.rerun()


# ── Entry point ───────────────────────────────────────────────────────────────
def mostrar():
    st.markdown("## 🌱 Producción Agrícola")
    if st.button("🏠 Inicio", key="btn_home_prod", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    # Crear hojas si no existen — solo una vez por sesión (evita 4 lecturas/render)
    if not st.session_state.get("_prod_hojas_ok"):
        try:
            _init_hojas()
            st.session_state["_prod_hojas_ok"] = True
        except Exception as e:
            st.error(f"Error inicializando hojas: {e}")
            return

    tabs = st.tabs([
        "🌱 Nueva Siembra",
        "📋 Siembras Activas",
        "🥕 Cosecha / Cierre",
        "📊 Proyección",
        "📚 Historial",
        "⚙️ Configuración",
    ])
    with tabs[0]: _tab_nueva_siembra()
    with tabs[1]: _tab_siembras_activas()
    with tabs[2]: _tab_cosecha()
    with tabs[3]: _tab_proyeccion()
    with tabs[4]: _tab_historial()
    with tabs[5]: _tab_config()
