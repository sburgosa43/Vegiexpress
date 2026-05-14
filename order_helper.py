"""
order_helper.py
Escribe nuevas filas de pedido en la hoja 'Pedidos' (Tabla3).

Columnas manuales (escritura directa):
  A: Fecha Entrega  B: Nombre Cliente  C: Cantidad  D: Producto  E: Precio

El precio se escribe como valor estático (no fórmula), lo que permite:
  - Precios personalizados por pedido (descuentos puntuales)
  - Historial de precios congelado al momento del pedido
  - Las demás fórmulas (Total, Costo, Margen, etc.) usan este precio correctamente

El resto de columnas (F-AE) copian las fórmulas de la fila anterior.
"""

from datetime import datetime, date
from copy import copy
import streamlit as st
from drive_helper import cargar_para_escritura, guardar_en_drive

FILE_ID      = st.secrets["EXCEL_FILE_ID"]
HOJA_PEDIDOS = "Pedidos"
NOMBRE_TABLA = "Tabla3"
TOTAL_COLS   = 31   # A hasta AE


def guardar_pedido(nombre_cliente: str, fecha_entrega: date, items: list) -> int:
    """
    Agrega filas a la hoja Pedidos:
      A: Fecha (datetime)
      B: Nombre Cliente
      C: Cantidad
      D: Producto
      E: Precio (valor estático — permite precios personalizados)
      F-AE: Fórmulas copiadas de la fila anterior

    items: lista de dicts con keys: nombre, cantidad, precio, unidad
    Retorna el número de filas agregadas.
    """
    fecha_dt = datetime(fecha_entrega.year, fecha_entrega.month, fecha_entrega.day)

    wb = cargar_para_escritura(FILE_ID)
    ws = wb[HOJA_PEDIDOS]

    primera_fila = ws.max_row + 1
    agregadas    = 0

    for item in items:
        if not item.get("nombre") or (item.get("cantidad") or 0) <= 0:
            continue

        fila_nueva = primera_fila + agregadas
        fila_ref   = fila_nueva - 1

        # ── Cols A-E: valores directos ────────────────────────────────────────
        c_fecha = ws.cell(row=fila_nueva, column=1)
        c_fecha.value         = fecha_dt
        c_fecha.number_format = "dd/mm/yyyy;@"

        ws.cell(row=fila_nueva, column=2).value = nombre_cliente
        ws.cell(row=fila_nueva, column=3).value = item["cantidad"]
        ws.cell(row=fila_nueva, column=4).value = item["nombre"]
        # Precio estático — no fórmula, permite descuentos puntuales
        ws.cell(row=fila_nueva, column=5).value = item["precio"]

        # ── Cols F-AE: copiar fórmulas de la fila anterior ───────────────────
        for col in range(6, TOTAL_COLS + 1):
            src = ws.cell(row=fila_ref,   column=col)
            dst = ws.cell(row=fila_nueva, column=col)
            dst.value         = src.value
            dst.number_format = src.number_format
            if src.font:
                dst.font      = copy(src.font)
                dst.fill      = copy(src.fill)
                dst.border    = copy(src.border)
                dst.alignment = copy(src.alignment)

        agregadas += 1

    if agregadas == 0:
        wb.close()
        return 0

    # ── Expandir Tabla3 ───────────────────────────────────────────────────────
    nueva_ultima = primera_fila + agregadas - 1
    if NOMBRE_TABLA in ws.tables:
        tbl   = ws.tables[NOMBRE_TABLA]
        partes = tbl.ref.split(":")
        col_f  = "".join(c for c in partes[1] if c.isalpha())
        tbl.ref = f"{partes[0]}:{col_f}{nueva_ultima}"

    guardar_en_drive(wb, FILE_ID)
    wb.close()
    return agregadas
