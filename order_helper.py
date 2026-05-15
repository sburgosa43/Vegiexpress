"""
order_helper.py — Escribe filas de pedido en la hoja 'Pedidos' (Tabla3).

Columnas A-L se escriben como valores estáticos calculados en Python.
Columnas M-AE: fecha-derivadas (estáticas) o fórmulas copiadas de la fila anterior.

Fórmulas financieras (col E-L):
  E: Precio         → ingresado por usuario
  F: Costo          → del catálogo (o modificado por usuario)
  G: Total          = Precio × Cantidad
  H: Total Costo    = Costo × Cantidad
  I: Margen Neto Q  = 0.95 × (Precio − Costo × 1.12) × Cantidad
  J: % Margen Neto  = 0.95 × (1 − Costo × 1.12 / Precio)
  K: IVA Q          = (Precio − Precio/1.12) × Cantidad
  L: ISR Q          = (Precio/1.12 × 0.05) × Cantidad
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

# Columnas escritas como valor estático (no copian fórmula)
_COLS_ESTATICAS = {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,26,27,28,31}


def _calcular(precio: float, costo: float, cantidad: float) -> dict:
    """Calcula campos financieros E-L de una línea."""
    if precio <= 0:
        return {"total":0,"total_costo":0,"margen_q":0,
                "margen_pct":0,"iva":0,"isr":0}
    total       = round(precio * cantidad, 4)
    total_costo = round(costo  * cantidad, 4)
    margen_q    = round(0.95 * (precio - costo * 1.12) * cantidad, 4)
    margen_pct  = round(0.95 * (1 - costo * 1.12 / precio), 4)
    iva         = round((precio - precio / 1.12) * cantidad, 4)
    isr         = round((precio / 1.12 * 0.05) * cantidad, 4)
    return {"total":total,"total_costo":total_costo,"margen_q":margen_q,
            "margen_pct":margen_pct,"iva":iva,"isr":isr}


def _codigo_cliente(wb, nombre: str) -> str:
    if "Clientes" not in wb.sheetnames:
        return "C000"
    ws = wb["Clientes"]
    nl = nombre.strip().lower()
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] and str(row[0]).strip().lower() == nl:
            return str(row[9] or "C000").strip()
    return "C000"


def guardar_pedido(nombre_cliente: str, fecha_entrega: date, items: list) -> int:
    fecha_dt = datetime(fecha_entrega.year, fecha_entrega.month, fecha_entrega.day)
    semana   = fecha_entrega.isocalendar()[1]
    año      = fecha_entrega.year
    mes      = fecha_entrega.month

    wb  = cargar_para_escritura(FILE_ID)
    ws  = wb[HOJA_PEDIDOS]
    cod = _codigo_cliente(wb, nombre_cliente)
    unico = f"{cod}{fecha_entrega.day:02d}{mes:02d}{semana:02d}{año}"

    static_fecha = {
        13: DIAS_ES[fecha_entrega.weekday()],
        14: mes,
        15: semana,
        16: año,
        26: MESES_N[mes - 1],
        27: f"{mes:02d}",
        28: unico,
        31: "Pendiente",
    }

    primera = ws.max_row + 1
    agr     = 0

    for item in items:
        if not item.get("nombre") or (item.get("cantidad") or 0) <= 0:
            continue

        precio  = float(item.get("precio", 0))
        costo   = float(item.get("costo",  0))
        cant    = float(item["cantidad"])
        fin     = _calcular(precio, costo, cant)
        fila    = primera + agr
        ref     = fila - 1

        # Cols A-L: valores estáticos
        def w(col, val, fmt=None):
            c = ws.cell(row=fila, column=col)
            c.value = val
            if fmt: c.number_format = fmt

        w(1,  fecha_dt, "dd/mm/yyyy;@")
        w(2,  nombre_cliente)
        w(3,  cant)
        w(4,  item["nombre"])
        w(5,  precio)
        w(6,  costo)
        w(7,  fin["total"])
        w(8,  fin["total_costo"])
        w(9,  fin["margen_q"])
        w(10, fin["margen_pct"])
        w(11, fin["iva"])
        w(12, fin["isr"])
        # Fecha-derivadas
        for col, val in static_fecha.items():
            ws.cell(row=fila, column=col).value = val
        # Unidad (col 17) desde el item
        ws.cell(row=fila, column=17).value = item.get("unidad", "")

        # Cols 18-25 y 29-30: copiar fórmulas de la fila anterior
        for col in range(18, TOTAL_COLS + 1):
            if col in _COLS_ESTATICAS:
                continue
            src = ws.cell(row=ref, column=col)
            dst = ws.cell(row=fila, column=col)
            dst.value         = src.value
            dst.number_format = src.number_format
            if src.font:
                dst.font      = copy(src.font)
                dst.fill      = copy(src.fill)
                dst.border    = copy(src.border)
                dst.alignment = copy(src.alignment)

        agr += 1

    if agr == 0:
        wb.close()
        return 0

    # Expandir Tabla3
    nueva_ult = primera + agr - 1
    if NOMBRE_TABLA in ws.tables:
        tbl    = ws.tables[NOMBRE_TABLA]
        partes = tbl.ref.split(":")
        col_f  = "".join(c for c in partes[1] if c.isalpha())
        tbl.ref = f"{partes[0]}:{col_f}{nueva_ult}"

    guardar_en_drive(wb, FILE_ID)
    wb.close()
    return agr
