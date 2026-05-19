"""
order_helper.py — Escritura de pedidos al Excel (individual y batch)

guardar_pedido()        → 1 pedido → 1 ciclo Drive (compatibilidad)
guardar_pedidos_batch() → N pedidos → 1 solo ciclo Drive (óptimo)
"""
from datetime import datetime, date
from copy import copy
import streamlit as st
from drive_helper import cargar_para_escritura, guardar_en_drive

FILE_ID      = st.secrets["EXCEL_FILE_ID"]
HOJA_PEDIDOS = "Pedidos"
NOMBRE_TABLA = "Tabla3"
TOTAL_COLS   = 31

DIAS_ES = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
MESES_N = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
_COLS_ESTATICAS = {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,26,27,28,31}


def _calcular(precio, costo, cant):
    if precio <= 0:
        return dict(total=0, total_costo=0, margen_q=0, margen_pct=0, iva=0, isr=0)
    return {
        "total":       round(precio * cant, 4),
        "total_costo": round(costo  * cant, 4),
        "margen_q":    round(0.95 * (precio - costo * 1.12) * cant, 4),
        "margen_pct":  round(0.95 * (1 - costo * 1.12 / precio), 4),
        "iva":         round((precio - precio / 1.12) * cant, 4),
        "isr":         round(precio / 1.12 * 0.05 * cant, 4),
    }


def _codigo_cliente(wb, nombre: str) -> str:
    if "Clientes" not in wb.sheetnames: return "C000"
    ws = wb["Clientes"]
    nl = nombre.strip().lower()
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] and str(row[0]).strip().lower() == nl:
            return str(row[9] or "C000").strip()
    return "C000"


def _escribir_pedido_en_ws(ws, wb, nombre_cliente: str,
                            fecha_entrega: date, items: list) -> int:
    """
    Escribe las filas de UN pedido en el ws dado.
    No hace upload — llamar guardar_en_drive() externamente.
    Retorna número de filas escritas.
    """
    fecha_dt = datetime(fecha_entrega.year, fecha_entrega.month, fecha_entrega.day)
    semana   = fecha_entrega.isocalendar()[1]
    año      = fecha_entrega.year
    mes      = fecha_entrega.month
    cod      = _codigo_cliente(wb, nombre_cliente)
    unico    = f"{cod}{fecha_entrega.day:02d}{mes:02d}{semana:02d}{año}"

    static_fecha = {
        13: DIAS_ES[fecha_entrega.weekday()],
        14: mes, 15: semana, 16: año,
        26: MESES_N[mes - 1], 27: f"{mes:02d}",
        28: unico, 31: "Pendiente",
    }

    primera = ws.max_row + 1
    agr     = 0

    for item in items:
        if not item.get("nombre") or (item.get("cantidad") or 0) <= 0:
            continue
        precio = float(item.get("precio", 0))
        costo  = float(item.get("costo",  0))
        cant   = float(item["cantidad"])
        fin    = _calcular(precio, costo, cant)
        fila   = primera + agr
        ref    = fila - 1

        def w(col, val, fmt=None):
            c = ws.cell(row=fila, column=col)
            c.value = val
            if fmt: c.number_format = fmt

        w(1,  fecha_dt, "dd/mm/yyyy;@")
        w(2,  nombre_cliente); w(3, cant); w(4, item["nombre"]); w(5, precio)
        w(6,  costo);          w(7, fin["total"]); w(8, fin["total_costo"])
        w(9,  fin["margen_q"]); w(10, fin["margen_pct"])
        w(11, fin["iva"]);     w(12, fin["isr"])
        for col, val in static_fecha.items():
            ws.cell(row=fila, column=col).value = val
        ws.cell(row=fila, column=17).value = item.get("unidad", "")

        for col in range(18, TOTAL_COLS + 1):
            if col in _COLS_ESTATICAS: continue
            src = ws.cell(row=ref, column=col)
            dst = ws.cell(row=fila, column=col)
            dst.value = src.value; dst.number_format = src.number_format
            if src.font:
                dst.font = copy(src.font); dst.fill = copy(src.fill)
                dst.border = copy(src.border); dst.alignment = copy(src.alignment)
        agr += 1

    return agr


def _expandir_tabla(ws, n_filas_nuevas: int):
    if n_filas_nuevas <= 0: return
    nueva_ult = ws.max_row
    if NOMBRE_TABLA in ws.tables:
        tbl    = ws.tables[NOMBRE_TABLA]
        partes = tbl.ref.split(":")
        col_f  = "".join(c for c in partes[1] if c.isalpha())
        tbl.ref = f"{partes[0]}:{col_f}{nueva_ult}"


# ── API PÚBLICA ────────────────────────────────────────────────────────────────
def guardar_pedido(nombre_cliente: str, fecha_entrega: date, items: list) -> int:
    """Graba 1 pedido (un ciclo Drive). Mantiene compatibilidad."""
    wb  = cargar_para_escritura(FILE_ID)
    ws  = wb[HOJA_PEDIDOS]
    agr = _escribir_pedido_en_ws(ws, wb, nombre_cliente, fecha_entrega, items)
    if agr:
        _expandir_tabla(ws, agr)
        guardar_en_drive(wb, FILE_ID)
        st.cache_data.clear()
    wb.close()
    return agr


def guardar_pedidos_batch(cola: list) -> dict:
    """
    Graba N pedidos en UN SOLO ciclo de Drive.
    cola: lista de dicts {cliente_nombre, fecha, items}
    Retorna: {pedidos: int, filas: int}
    """
    if not cola:
        return {"pedidos": 0, "filas": 0}

    wb          = cargar_para_escritura(FILE_ID)
    ws          = wb[HOJA_PEDIDOS]
    total_filas = 0

    for pedido in cola:
        n = _escribir_pedido_en_ws(
            ws, wb,
            pedido["cliente_nombre"],
            pedido["fecha"],
            pedido["items"],
        )
        total_filas += n

    if total_filas:
        _expandir_tabla(ws, total_filas)
        guardar_en_drive(wb, FILE_ID)
        st.cache_data.clear()

    wb.close()
    return {"pedidos": len(cola), "filas": total_filas}
