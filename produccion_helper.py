"""
produccion_helper.py — Logica de negocio del modulo de Produccion.
Maneja siembras, cultivos, fertilizantes y aplicaciones via Google Sheets.
Auto-crea las 4 hojas con datos precargados la primera vez.
"""
import streamlit as st
from datetime import date, datetime, timedelta
from gsheets import get_all_rows, append_rows, update_cells, ensure_ws, ws
from utils import _sf, _parse_fecha

# ── Nombres de hojas (claves en HOJAS) ────────────────────────────────────────
_K_SIEMBRA = "produccion"
_K_CULTIVO = "produccioncultivos"
_K_APLIC   = "produccionaplic"
_K_FERT    = "produccionfert"


# ── Encabezados ───────────────────────────────────────────────────────────────
_HDR_SIEMBRA = [
    "id_siembra", "variedad", "fecha_siembra", "cantidad_semillas", "lugar",
    "tablones", "fecha_cosecha_est", "semana_cosecha", "dias_ciclo",
    "lbs_proyectadas_min", "lbs_proyectadas_max", "lbs_cosechadas_real",
    "estado", "notas", "cultivo", "germinacion", "rend_min", "rend_max",
    "fecha_cosecha_real",
]
_HDR_CULTIVO = [
    "cultivo", "variedad", "dias_ciclo", "germinacion",
    "rend_min", "rend_max", "productos_cosecha",
]
_HDR_APLIC = [
    "id_siembra", "aplicacion", "dia_desde", "dia_hasta",
    "fertilizante", "libras", "fecha_aplicacion_est", "aplicado",
]
_HDR_FERT = ["fertilizante", "N", "P", "K"]


# ── Datos precargados ─────────────────────────────────────────────────────────
_SEED_CULTIVOS = [
    # cultivo, variedad, dias_ciclo, germinacion, rend_min, rend_max, productos_cosecha
    ["Zanahoria Baby", "Mercedes", 88, 0.75, 7, 10,
     "Mini,Zanahoria Baby,Zanahoria Babyr,Zanahoria Babyl"],
    ["Zanahoria Baby", "Crofton", 85, 0.75, 7, 10,
     "Mini,Zanahoria Baby,Zanahoria Babyr,Zanahoria Babyl"],
    ["Zanahoria Baby", "Romance", 90, 0.75, 7, 10,
     "Mini,Zanahoria Baby,Zanahoria Babyr,Zanahoria Babyl"],
]

_SEED_FERT = [
    # fertilizante, N, P, K
    ["15-15-15", 15, 15, 15],
    ["15-8-22", 15, 8, 22],
    ["0-0-60", 0, 0, 60],
    ["21N-24S", 21, 0, 0],
    ["15-10-10", 15, 10, 10],
    ["Fertihortaliza 15-8-22", 15, 8, 22],
]

# Programa sugerido por cultivo: (aplicacion, dia_desde, dia_hasta, fert, libras)
# Solo 2 aplicaciones (sin dia 0), segun lo acordado.
_SEED_DOSIS = {
    "Zanahoria Baby": [
        (1, 22, 25, "21N-24S", 18),
        (2, 50, 55, "0-0-60", 12),
        (2, 50, 55, "15-10-10", 6),
    ],
}


# ── Inicializacion (auto-crea hojas) ──────────────────────────────────────────
def inicializar_hojas() -> dict:
    """Crea las 4 hojas de produccion si no existen, con datos precargados."""
    creadas = {}
    creadas["cultivos"] = ensure_ws(_K_CULTIVO, _HDR_CULTIVO, _SEED_CULTIVOS)
    creadas["fert"]     = ensure_ws(_K_FERT, _HDR_FERT, _SEED_FERT)
    creadas["aplic"]    = ensure_ws(_K_APLIC, _HDR_APLIC, [])
    # La hoja Produccion ya existe (la creo el usuario), pero garantizamos headers
    creadas["siembra"]  = ensure_ws(_K_SIEMBRA, _HDR_SIEMBRA, [])
    return creadas

# ── Lecturas cacheadas ────────────────────────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def cargar_cultivos() -> list:
    rows = get_all_rows(_K_CULTIVO)
    out = []
    for r in rows:
        while len(r) < 7:
            r.append("")
        if not r[0]:
            continue
        out.append({
            "cultivo":   str(r[0]).strip(),
            "variedad":  str(r[1]).strip(),
            "dias_ciclo": int(_sf(r[2])) or 88,
            "germinacion": _sf(r[3]) or 0.75,
            "rend_min":  _sf(r[4]) or 7,
            "rend_max":  _sf(r[5]) or 10,
            "productos_cosecha": [p.strip() for p in str(r[6]).split(",") if p.strip()],
        })
    return out


@st.cache_data(ttl=120, show_spinner=False)
def cargar_fertilizantes() -> list:
    rows = get_all_rows(_K_FERT)
    out = []
    for r in rows:
        while len(r) < 4:
            r.append("")
        if not r[0]:
            continue
        out.append({
            "fertilizante": str(r[0]).strip(),
            "N": _sf(r[1]), "P": _sf(r[2]), "K": _sf(r[3]),
        })
    return out


@st.cache_data(ttl=60, show_spinner=False)
def cargar_siembras() -> list:
    rows = get_all_rows(_K_SIEMBRA)
    out = []
    for i, r in enumerate(rows, start=2):
        while len(r) < 19:
            r.append("")
        if not r[0]:
            continue
        out.append({
            "row_num":    i,
            "id_siembra": str(r[0]).strip(),
            "variedad":   str(r[1]).strip(),
            "fecha_siembra": _parse_fecha(r[2]),
            "cantidad_semillas": _sf(r[3]),
            "lugar":      str(r[4]).strip(),
            "tablones":   _sf(r[5]),
            "fecha_cosecha_est": _parse_fecha(r[6]),
            "semana_cosecha": int(_sf(r[7])) if r[7] else 0,
            "dias_ciclo": int(_sf(r[8])) or 88,
            "lbs_proy_min": _sf(r[9]),
            "lbs_proy_max": _sf(r[10]),
            "lbs_real":   _sf(r[11]),
            "estado":     str(r[12]).strip() or "Activa",
            "notas":      str(r[13]).strip(),
            "cultivo":    str(r[14]).strip() or "Zanahoria Baby",
            "germinacion": _sf(r[15]) or 0.75,
            "rend_min":   _sf(r[16]) or 7,
            "rend_max":   _sf(r[17]) or 10,
            "fecha_cosecha_real": _parse_fecha(r[18]),
        })
    return out


@st.cache_data(ttl=60, show_spinner=False)
def cargar_aplicaciones(id_siembra: str = None) -> list:
    rows = get_all_rows(_K_APLIC)
    out = []
    for i, r in enumerate(rows, start=2):
        while len(r) < 8:
            r.append("")
        if not r[0]:
            continue
        if id_siembra and str(r[0]).strip() != id_siembra:
            continue
        out.append({
            "row_num":    i,
            "id_siembra": str(r[0]).strip(),
            "aplicacion": int(_sf(r[1])),
            "dia_desde":  int(_sf(r[2])),
            "dia_hasta":  int(_sf(r[3])),
            "fertilizante": str(r[4]).strip(),
            "libras":     _sf(r[5]),
            "fecha_est":  _parse_fecha(r[6]),
            "aplicado":   str(r[7]).strip().lower() in ("si", "sí", "true", "1", "x"),
        })
    return out


# ── Calculos N-P-K de mezcla (Formas A y B) ───────────────────────────────────
def calcular_mezcla(items: list, fert_map: dict) -> dict:
    """
    items: [{"fertilizante": str, "libras": float}, ...]
    fert_map: {nombre: {"N":.., "P":.., "K":..}}

    Retorna:
      grado_equivalente (Forma A): promedio simple de los % ÷ num fertilizantes
      nutrientes_reales (Forma B): libras reales de cada nutriente aportadas
      total_libras
    """
    n_count = len([x for x in items if x.get("libras", 0) > 0])
    suma_N = suma_P = suma_K = 0.0      # para Forma A (suma de grados)
    real_N = real_P = real_K = 0.0      # para Forma B (libras reales)
    total_libras = 0.0

    for it in items:
        lbs = float(it.get("libras", 0) or 0)
        if lbs <= 0:
            continue
        f = fert_map.get(it["fertilizante"], {"N": 0, "P": 0, "K": 0})
        suma_N += f["N"]; suma_P += f["P"]; suma_K += f["K"]
        real_N += lbs * f["N"] / 100.0
        real_P += lbs * f["P"] / 100.0
        real_K += lbs * f["K"] / 100.0
        total_libras += lbs

    grado = {
        "N": round(suma_N / n_count, 1) if n_count else 0,
        "P": round(suma_P / n_count, 1) if n_count else 0,
        "K": round(suma_K / n_count, 1) if n_count else 0,
    }
    reales = {
        "N": round(real_N, 2),
        "P": round(real_P, 2),
        "K": round(real_K, 2),
    }
    return {
        "grado_equivalente": grado,
        "nutrientes_reales": reales,
        "total_libras": round(total_libras, 1),
    }


# ── Proyeccion de libras ──────────────────────────────────────────────────────
def proyectar_libras(semillas: float, germinacion: float,
                     rend_min: float, rend_max: float) -> tuple:
    """
    Plantas = semillas × germinacion
    Lbs min = plantas / rend_max  (mas zanahorias/lb = menos libras)
    Lbs max = plantas / rend_min
    """
    plantas = semillas * germinacion
    lbs_min = plantas / rend_max if rend_max > 0 else 0
    lbs_max = plantas / rend_min if rend_min > 0 else 0
    return round(lbs_min, 1), round(lbs_max, 1)


# ── Guardar nueva siembra ─────────────────────────────────────────────────────
def guardar_siembra(datos: dict, aplicaciones: list) -> str:
    """
    Crea la siembra + sus aplicaciones congeladas.
    datos: dict con campos de la siembra.
    aplicaciones: [{"aplicacion","dia_desde","dia_hasta","fertilizante","libras"}]
    Retorna el id_siembra generado.
    """
    siembras = cargar_siembras()
    # Generar ID secuencial
    nums = [int(s["id_siembra"].replace("S", "")) for s in siembras
            if s["id_siembra"].startswith("S") and s["id_siembra"][1:].isdigit()]
    next_n = (max(nums) + 1) if nums else 1
    sid = f"S{next_n:03d}"

    fs = datos["fecha_siembra"]
    fc = datos["fecha_cosecha_est"]
    fila = [
        sid,
        datos["variedad"],
        fs.strftime("%d/%m/%Y"),
        datos["cantidad_semillas"],
        datos["lugar"],
        datos["tablones"],
        fc.strftime("%d/%m/%Y"),
        fc.isocalendar()[1],
        datos["dias_ciclo"],
        datos["lbs_proy_min"],
        datos["lbs_proy_max"],
        "",                       # lbs_cosechadas_real (vacio hasta cosecha)
        "Activa",
        datos.get("notas", ""),
        datos["cultivo"],
        datos["germinacion"],
        datos["rend_min"],
        datos["rend_max"],
        "",                       # fecha_cosecha_real
    ]
    append_rows(_K_SIEMBRA, [fila])

    # Aplicaciones congeladas
    filas_aplic = []
    for a in aplicaciones:
        if float(a.get("libras", 0) or 0) <= 0:
            continue
        dia_aplic = fs + timedelta(days=int(a["dia_desde"]))
        filas_aplic.append([
            sid, a["aplicacion"], a["dia_desde"], a["dia_hasta"],
            a["fertilizante"], a["libras"],
            dia_aplic.strftime("%d/%m/%Y"), "No",
        ])
    if filas_aplic:
        append_rows(_K_APLIC, filas_aplic)

    cargar_siembras.clear()
    cargar_aplicaciones.clear()
    return sid


# ── Registrar cosecha ─────────────────────────────────────────────────────────
def registrar_cosecha(row_num: int, lbs_total: float,
                      fecha_real: date) -> None:
    """Actualiza lbs reales, fecha real y estado=Cosechada."""
    updates = [
        {"range": f"L{row_num}", "values": [[lbs_total]]},
        {"range": f"M{row_num}", "values": [["Cosechada"]]},
        {"range": f"S{row_num}", "values": [[fecha_real.strftime("%d/%m/%Y")]]},
    ]
    update_cells(_K_SIEMBRA, updates)
    cargar_siembras.clear()


# ── Marcar aplicacion como hecha ──────────────────────────────────────────────
def marcar_aplicado(row_num: int, aplicado: bool = True) -> None:
    update_cells(_K_APLIC, [
        {"range": f"H{row_num}", "values": [["Si" if aplicado else "No"]]},
    ])
    cargar_aplicaciones.clear()


# ── Etapa fenologica ──────────────────────────────────────────────────────────
def etapa_siembra(siembra: dict, hoy: date = None) -> dict:
    """Calcula dias transcurridos, etapa y si toca fertilizar."""
    hoy = hoy or date.today()
    fs = siembra["fecha_siembra"]
    if not fs:
        return {"dias": 0, "etapa": "?", "pct": 0, "alerta_fert": False}
    dias = (hoy - fs).days
    ciclo = siembra["dias_ciclo"]
    pct = min(100, round(dias / ciclo * 100)) if ciclo else 0

    if dias < 22:
        etapa = "Germinacion / Establecimiento"
    elif dias < 50:
        etapa = "Desarrollo vegetativo"
    elif dias < ciclo:
        etapa = "Engrosamiento de raiz"
    else:
        etapa = "Lista para cosecha"

    return {"dias": dias, "etapa": etapa, "pct": pct}


# ── Siembras que necesitan fertilizacion esta semana ──────────────────────────
def fertilizaciones_pendientes(hoy: date = None) -> list:
    """Retorna aplicaciones cuya ventana cae en los proximos 7 dias y no aplicadas."""
    hoy = hoy or date.today()
    siembras = {s["id_siembra"]: s for s in cargar_siembras()
                if s["estado"] == "Activa"}
    aplics = cargar_aplicaciones()
    pendientes = []
    for a in aplics:
        if a["aplicado"]:
            continue
        s = siembras.get(a["id_siembra"])
        if not s or not s["fecha_siembra"]:
            continue
        ventana_ini = s["fecha_siembra"] + timedelta(days=a["dia_desde"])
        ventana_fin = s["fecha_siembra"] + timedelta(days=a["dia_hasta"] + 3)
        if ventana_ini - timedelta(days=3) <= hoy <= ventana_fin:
            pendientes.append({**a, "siembra": s,
                               "ventana_ini": ventana_ini,
                               "ventana_fin": ventana_fin})
    return pendientes


# ── Cosechas proyectadas de la semana ─────────────────────────────────────────
def cosechas_semana(semana: int = None, año: int = None) -> list:
    hoy = date.today()
    semana = semana or hoy.isocalendar()[1]
    año = año or hoy.year
    out = []
    for s in cargar_siembras():
        if s["estado"] != "Activa":
            continue
        fc = s["fecha_cosecha_est"]
        if fc and fc.isocalendar()[1] == semana and fc.year == año:
            out.append(s)
    return out
