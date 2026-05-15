"""
order_helper.py
Escribe filas de pedido en la hoja 'Pedidos' (Tabla3).

Columnas con valor estático (escritura directa):
  A(1):Fecha  B(2):Cliente  C(3):Cantidad  D(4):Producto  E(5):Precio
  M(13):DiaSemana  N(14):Mes  O(15):Semana  P(16):Año
  Z(26):MesN  AA(27):MesNN  AB(28):Unico

El resto (F-L, Q-Y, AC-AE) copia las fórmulas de la fila anterior.
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

# Columnas que se calculan desde la fecha y se escriben como valores estáticos
# key = columna 1-indexed, value = se calcula en guardar_pedido
_STATIC_DATE_COLS = {13, 14, 15, 16, 26, 27, 28}


def _codigo_cliente(wb, nombre_cliente: str) -> str:
    """Busca el código del cliente en la hoja Clientes."""
    if "Clientes" not in wb.sheetnames:
        return "C000"
    ws_cli = wb["Clientes"]
    nombre_lower = nombre_cliente.strip().lower()
    for row in ws_cli.iter_rows(min_row=2, values_only=True):
        if row[0] and str(row[0]).strip().lower() == nombre_lower:
            return str(row[9] or "C000").strip()
    return "C000"


def guardar_pedido(nombre_cliente: str, fecha_entrega: date, items: list) -> int:
    """
    Agrega filas a la hoja Pedidos con todos los campos clave como valores
    estáticos (no fórmulas), evitando el problema de caché vacío en openpyxl.
    """
    fecha_dt  = datetime(fecha_entrega.year, fecha_entrega.month, fecha_entrega.day)
    semana    = fecha_entrega.isocalendar()[1]
    dia_sem   = DIAS_ES[fecha_entrega.weekday()]
    mes       = fecha_entrega.month
    mes_n     = MESES_N[mes - 1]
    mes_nn    = f"{mes:02d}"
    año       = fecha_entrega.year

    wb = cargar_para_escritura(FILE_ID)
    ws = wb[HOJA_PEDIDOS]

    # Obtener código del cliente para generar Unico
    codigo_cli = _codigo_cliente(wb, nombre_cliente)
    unico      = f"{codigo_cli}{fecha_entrega.day:02d}{mes:02d}{semana:02d}{año}"

    # Valores estáticos por columna (1-indexed)
    static_date = {
        13: dia_sem,
        14: mes,
        15: semana,
        16: año,
        26: mes_n,
        27: mes_nn,
        28: unico,
    }

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
        ws.cell(row=fila_nueva, column=5).value = item["precio"]

        # ── Cols F-AE: estáticos (fecha) o fórmula copiada ───────────────────
        for col in range(6, TOTAL_COLS + 1):
            dst = ws.cell(row=fila_nueva, column=col)
            if col in _STATIC_DATE_COLS:
                dst.value = static_date[col]
            else:
                src = ws.cell(row=fila_ref, column=col)
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
        tbl    = ws.tables[NOMBRE_TABLA]
        partes = tbl.ref.split(":")
        col_f  = "".join(c for c in partes[1] if c.isalpha())
        tbl.ref = f"{partes[0]}:{col_f}{nueva_ultima}"

    guardar_en_drive(wb, FILE_ID)
    wb.close()
    return agregadas
