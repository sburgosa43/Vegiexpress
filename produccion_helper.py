"""
produccion_helper.py — Capa de datos y lógica de negocio de Producción.

Contiene TODA la lógica que NO es UI:
  - Constantes y datos de inicialización (fertilizantes, cultivos, dosis)
  - Lectores cacheados desde Google Sheets
  - Escritura: crear, editar, eliminar siembras y aplicaciones
  - Cálculos agronómicos: mezcla N-P-K, proyección de libras, rendimiento
  - Clasificación: etapa de siembra, alerta de fertilización

Importado exclusivamente por modulo_produccion.py.
"""
import streamlit as st
from datetime import date, timedelta
from utils import _sf, _parse_fecha
import json
import uuid

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
    ["Zanahoria Baby", "Mercedes", 88, 0.75, 10, 7,
     "Mini,Zanahoria Baby,Zanahoria Babyr,Zanahoria Babyl"],
    ["Zanahoria Baby", "Crofton",  85, 0.75, 10, 7,
     "Mini,Zanahoria Baby,Zanahoria Babyr,Zanahoria Babyl"],
    ["Zanahoria Baby", "Romance",  90, 0.75, 10, 7,
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
                   rend_a: float, rend_b: float) -> tuple:
    """Plantas = semillas * germinacion. Lbs = plantas / (zanahorias por libra).
    Robusto al orden: el MENOR valor de zanahorias/lb (raíz grande) da MÁS libras;
    el MAYOR (raíz chica) da MENOS libras. Así no importa cómo se nombren las
    columnas Rend_Min / Rend_Max — el cálculo siempre es correcto."""
    plantas = semillas * germinacion
    z_lb = [v for v in (rend_a, rend_b) if v and v > 0]
    if not z_lb:
        return 0.0, 0.0
    z_bajo, z_alto = min(z_lb), max(z_lb)
    lbs_max = round(plantas / z_bajo, 1)   # menos zanahorias/lb = más libras
    lbs_min = round(plantas / z_alto, 1)   # más zanahorias/lb = menos libras
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
