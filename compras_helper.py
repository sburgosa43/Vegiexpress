"""
compras_helper.py — Control de compras a proveedores (compra neta).

Dos niveles:
  1. TEMPORAL (borrador): las cantidades "A Comprar" se guardan en la hoja
     ComprasTemporal para no perderlas y poder armar la compra en varias
     sesiones (persiste en Sheets).
  2. DEFINITIVO (histórico): al confirmar, se registra en ComprasHistorico con
     fecha, semana, proveedor, producto, costo, total y el costo repartido por
     área (proporcional a la demanda de cada área).

Solo aplica a proveedores de compra neta (NO Patojas, que es proceso).
"""
import streamlit as st
from datetime import date

_TEMP_HEADER = ["semana", "año", "proveedor", "producto", "unidad",
                "a_comprar", "costo_unit", "actualizado", "areas"]

_HIST_HEADER = ["fecha_compra", "semana", "año", "proveedor", "producto",
                "unidad", "cantidad", "costo_unit", "total",
                "area", "cant_area", "costo_area"]


def _ensure_temp():
    from gsheets import ensure_ws
    try:
        ensure_ws("compras_temp", _TEMP_HEADER)
    except Exception as e:
        if "already exists" not in str(e).lower():
            raise


def _ensure_hist():
    from gsheets import ensure_ws
    try:
        ensure_ws("compras_hist", _HIST_HEADER)
    except Exception as e:
        if "already exists" not in str(e).lower():
            raise


# ── TEMPORAL (borrador) ───────────────────────────────────────────────────────
def guardar_temporal(semana: int, año: int, items: list,
                     areas: list | None = None) -> int:
    """Guarda el borrador de la compra (cantidades A Comprar) para esta semana.
    Sobrescribe el borrador anterior de la misma semana/año. Si se pasa
    `areas` (filtro de áreas activo al armar la compra), se persiste para
    restaurarlo al retomar el borrador.

    items: [{"proveedor","producto","unidad","a_comprar","costo_unit"}, ...]
    """
    _ensure_temp()
    from gsheets import get_all_rows, ws

    # Leer todo, quitar las filas de esta semana/año, y reescribir
    rows = get_all_rows("compras_temp")
    conservar = []
    for r in rows:
        if not r or len(r) < 3:
            continue
        try:
            r_sem = int(float(r[0])); r_año = int(float(r[1]))
        except Exception:
            continue
        if r_sem == semana and r_año == año:
            continue   # descartar el borrador viejo de esta semana
        conservar.append(r)

    hoy = date.today().strftime("%d/%m/%Y %H:%M")
    areas_str = "|".join(areas) if areas else ""
    nuevas = []
    for it in items:
        ac = float(it.get("a_comprar") or 0)
        if ac <= 0:
            continue
        nuevas.append([
            semana, año, it.get("proveedor", ""), it.get("producto", ""),
            it.get("unidad", ""), ac, float(it.get("costo_unit") or 0), hoy,
            areas_str,
        ])

    # Reescribir la hoja completa
    w = ws("compras_temp")
    w.clear()
    todo = [_TEMP_HEADER] + conservar + nuevas
    w.update("A1", todo, value_input_option="USER_ENTERED")
    return len(nuevas)


def cargar_temporal(semana: int, año: int) -> tuple[dict, list]:
    """Carga el borrador guardado de una semana/año.
    Retorna ({(proveedor, producto): a_comprar}, areas_del_filtro).
    areas_del_filtro es [] si el borrador no guardó filtro (compatibilidad)."""
    _ensure_temp()
    from gsheets import get_all_rows
    result, areas = {}, []
    for r in get_all_rows("compras_temp"):
        if not r or len(r) < 6:
            continue
        try:
            r_sem = int(float(r[0])); r_año = int(float(r[1]))
        except Exception:
            continue
        if r_sem != semana or r_año != año:
            continue
        prov = str(r[2]).strip()
        prod = str(r[3]).strip()
        try:
            ac = float(r[5])
        except Exception:
            ac = 0
        if ac > 0:
            result[(prov, prod)] = ac
        # Filtro de áreas guardado (columna 9, si existe)
        if not areas and len(r) > 8 and str(r[8]).strip():
            areas = [a for a in str(r[8]).split("|") if a.strip()]
    return result, areas


# ── DEFINITIVO (histórico) ────────────────────────────────────────────────────
def guardar_definitivo(semana: int, año: int, compras: list) -> dict:
    """Registra la compra definitiva en ComprasHistorico, con el costo repartido
    por área proporcional a la demanda de cada área.

    compras: [{
        "proveedor","producto","unidad","cantidad","costo_unit",
        "areas": {area: demanda_de_esa_area, ...}
    }, ...]

    El reparto: costo_area = costo_total * (demanda_area / demanda_total).
    Si la demanda total es 0, no reparte (queda todo sin área).
    Retorna {"filas": N, "total": Q}.
    """
    _ensure_hist()
    from gsheets import append_rows

    hoy = date.today().strftime("%d/%m/%Y")
    filas = []
    total_general = 0.0

    for c in compras:
        cant   = float(c.get("cantidad") or 0)
        costo  = float(c.get("costo_unit") or 0)
        if cant <= 0:
            continue
        total = round(cant * costo, 2)
        total_general += total
        areas = c.get("areas", {}) or {}
        demanda_total = sum(float(v or 0) for v in areas.values())

        if demanda_total > 0:
            # Una fila por área, con el costo repartido proporcionalmente
            for area, dem in areas.items():
                dem = float(dem or 0)
                if dem <= 0:
                    continue
                frac = dem / demanda_total
                cant_area  = round(cant * frac, 2)
                costo_area = round(total * frac, 2)
                filas.append([
                    hoy, semana, año, c.get("proveedor", ""),
                    c.get("producto", ""), c.get("unidad", ""),
                    cant, costo, total, area, cant_area, costo_area,
                ])
        else:
            # Sin demanda por área → una fila sin reparto
            filas.append([
                hoy, semana, año, c.get("proveedor", ""),
                c.get("producto", ""), c.get("unidad", ""),
                cant, costo, total, "(sin área)", cant, total,
            ])

    if filas:
        append_rows("compras_hist", filas)

    return {"filas": len(filas), "total": round(total_general, 2)}


def limpiar_temporal(semana: int, año: int) -> None:
    """Borra el borrador de una semana (tras guardar definitivo)."""
    _ensure_temp()
    from gsheets import get_all_rows, ws
    rows = get_all_rows("compras_temp")
    conservar = []
    for r in rows:
        if not r or len(r) < 3:
            continue
        try:
            r_sem = int(float(r[0])); r_año = int(float(r[1]))
        except Exception:
            continue
        if r_sem == semana and r_año == año:
            continue
        conservar.append(r)
    w = ws("compras_temp")
    w.clear()
    w.update("A1", [_TEMP_HEADER] + conservar, value_input_option="USER_ENTERED")
