"""
order_helper.py
Escribe nuevas filas de pedido en la hoja 'Pedidos' (Tabla3).

IMPORTANTE: La mayoria de columnas tienen formulas Excel (VLOOKUP).
Solo se escriben manualmente los 4 campos de entrada:
  A: Fecha Entrega  |  B: Nombre Cliente  |  C: Cantidad  |  D: Producto
Las demas columnas copian la formula de la fila anterior y Excel recalcula todo.
"""

from datetime import datetime, date
import streamlit as st
from drive_helper import cargar_para_escritura, guardar_en_drive

FILE_ID      = st.secrets["EXCEL_FILE_ID"]

# Formula correcta para columna Precio (col E):
# VLOOKUP en lista normal usa columna 8 = "Precio" (manual)
# VLOOKUP en lista Antigua usa columna 7 = "Precio" (esa lista no tiene Precio Impuestos)
_PRECIO_FORMULA = (
    '=+IF(OR(Tabla3[[#This Row],[Direccion]]="Chimal",'
    'Tabla3[[#This Row],[Direccion]]="Antigua"),'
    'IFERROR(VLOOKUP(Tabla3[[#This Row],[Producto]],Tabla29[#All],7,0),0),'
    'IFERROR(VLOOKUP(Tabla3[[#This Row],[Producto]],'
    'LIstPreciosProd[[Producto]:[Precio Sin IVA]],8,0),0))'
)

HOJA_PEDIDOS = "Pedidos"
NOMBRE_TABLA = "Tabla3"
TOTAL_COLS   = 31   # A hasta AE


def guardar_pedido(nombre_cliente: str, fecha_entrega: date, items: list) -> int:
    """
    Agrega filas a la tabla 'Pedidos':
      - Escribe los 4 campos manuales (Fecha, Cliente, Cantidad, Producto)
      - Copia las formulas de la fila anterior para el resto de columnas
      - Expande la referencia de Tabla3

    Parametros
    ----------
    nombre_cliente : nombre exacto del cliente (como aparece en la tabla Clientes)
    fecha_entrega  : fecha Python
    items          : lista de dicts con {"nombre": str, "cantidad": float}

    Retorna el numero de filas agregadas.
    """
    # Convertir date a datetime (formato que usa Excel/openpyxl)
    fecha_dt = datetime(fecha_entrega.year, fecha_entrega.month, fecha_entrega.day)

    wb = cargar_para_escritura(FILE_ID)
    ws = wb[HOJA_PEDIDOS]

    primera_fila_nueva = ws.max_row + 1
    filas_agregadas    = 0

    for item in items:
        nombre_prod = item["nombre"]
        cantidad    = item["cantidad"]

        if not nombre_prod or cantidad <= 0:
            continue

        fila_actual  = primera_fila_nueva + filas_agregadas
        fila_formula = fila_actual - 1   # fila de referencia para copiar formulas

        # ── Col A: Fecha Entrega ──────────────────────────────────────────────
        c_fecha = ws.cell(row=fila_actual, column=1)
        c_fecha.value         = fecha_dt
        c_fecha.number_format = "dd/mm/yyyy;@"

        # ── Col B: Nombre Cliente ─────────────────────────────────────────────
        ws.cell(row=fila_actual, column=2).value = nombre_cliente

        # ── Col C: Cantidad ───────────────────────────────────────────────────
        ws.cell(row=fila_actual, column=3).value = cantidad

        # ── Col D: Producto ───────────────────────────────────────────────────
        ws.cell(row=fila_actual, column=4).value = nombre_prod

        # ── Cols E-AE: copiar formulas de la fila anterior ───────────────────
        for col in range(5, TOTAL_COLS + 1):
            celda_ref   = ws.cell(row=fila_formula, column=col)
            celda_nueva = ws.cell(row=fila_actual,  column=col)

            if col == 5:
                # Col E (Precio): escribir formula corregida (col 8 = Precio manual)
                celda_nueva.value = _PRECIO_FORMULA
            else:
                # Resto: copiar formula tal cual (Tabla3[#This Row] = siempre fila actual)
                celda_nueva.value = celda_ref.value

            celda_nueva.number_format = celda_ref.number_format
            if celda_ref.font:
                from copy import copy
                celda_nueva.font      = copy(celda_ref.font)
                celda_nueva.fill      = copy(celda_ref.fill)
                celda_nueva.border    = copy(celda_ref.border)
                celda_nueva.alignment = copy(celda_ref.alignment)

        filas_agregadas += 1

    if filas_agregadas == 0:
        wb.close()
        return 0

    # ── Expandir la referencia de Tabla3 ─────────────────────────────────────
    nueva_ultima_fila = primera_fila_nueva + filas_agregadas - 1
    if NOMBRE_TABLA in ws.tables:
        tbl = ws.tables[NOMBRE_TABLA]
        # Mantener la columna inicial/final, solo actualizar la fila final
        # Formato actual: "A1:AE275" → "A1:AE{nueva_ultima_fila}"
        partes = tbl.ref.split(":")
        inicio = partes[0]  # ej: "A1"
        # Extraer la letra de columna de la referencia final
        col_final = "".join(c for c in partes[1] if c.isalpha())  # ej: "AE"
        tbl.ref   = f"{inicio}:{col_final}{nueva_ultima_fila}"

    guardar_en_drive(wb, FILE_ID)
    wb.close()
    return filas_agregadas
