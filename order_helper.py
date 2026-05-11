"""
order_helper.py
Genera las filas del pedido y las escribe en la hoja 'Ped 22-24'.
"""

from datetime import date, timedelta
import streamlit as st
from drive_helper import cargar_para_escritura, guardar_en_drive

FILE_ID      = st.secrets["EXCEL_FILE_ID"]
HOJA_PEDIDOS = "Ped 22-24"

# Tablas de traducción
DIAS_ES   = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES_N   = ["ene", "feb", "mar", "abr", "may", "jun",
             "jul", "ago", "sep", "oct", "nov", "dic"]


# ── UTILIDADES DE FECHA ───────────────────────────────────────────────────────

def _fecha_a_serial(d: date) -> int:
    """Convierte fecha Python al número serial de Excel (días desde 30-dic-1899)."""
    return (d - date(1899, 12, 30)).days


def _generar_unico(codigo_cliente: str, fecha: date, semana: int) -> str:
    """
    Genera el código único del pedido.
    Formato: {CódigoCliente}{Día:02}{Mes:02}{Semana:02}{Año}
    Ejemplo: C0212705212022
    """
    return (
        f"{codigo_cliente}"
        f"{fecha.day:02d}"
        f"{fecha.month:02d}"
        f"{semana:02d}"
        f"{fecha.year}"
    )


# ── CÁLCULOS FINANCIEROS ──────────────────────────────────────────────────────

def _calcular_fila(cantidad: float, precio: float, costo: float) -> dict:
    """
    Calcula los campos financieros de una línea de pedido.

    Basado en las fórmulas observadas en la hoja Ped 22-24:
      IVA       = precio_unitario / 1.12   (base imponible sin IVA)
      ISR       = precio_unitario / 1.15   (base para retención ISR)
      Total     = cantidad × precio
      TotalCost = cantidad × costo
      Margen%   = 0.95 × (1 − costo×1.12/precio)
      Margen    = Margen% × Total
    """
    total       = round(cantidad * precio, 2)
    total_costo = round(cantidad * costo,  2)
    iva         = round(precio / 1.12, 4) if precio else 0
    isr         = round(precio / 1.15, 4) if precio else 0
    margen_pct  = round(0.95 * (1 - (costo * 1.12 / precio)), 4) if precio else 0
    margen      = round(margen_pct * total, 2)

    return {
        "total":       total,
        "total_costo": total_costo,
        "margen":      margen,
        "margen_pct":  margen_pct,
        "iva":         iva,
        "isr":         isr,
    }


# ── GUARDADO DEL PEDIDO ───────────────────────────────────────────────────────

def guardar_pedido(cliente: dict, fecha_entrega: date, items: list) -> int:
    """
    Descarga el Excel, agrega las filas del pedido a 'Ped 22-24'
    y sube el archivo actualizado a Drive.

    Retorna la cantidad de filas agregadas.
    """
    # ── Datos del encabezado del pedido
    semana         = fecha_entrega.isocalendar()[1]
    unico          = _generar_unico(cliente["codigo"], fecha_entrega, semana)
    dia_semana     = DIAS_ES[fecha_entrega.weekday()]
    mes_numero     = fecha_entrega.month
    mes_n          = MESES_N[mes_numero - 1]
    mes_nn         = f"{mes_numero:02d}"
    fecha_serial   = _fecha_a_serial(fecha_entrega)

    fecha_venc        = fecha_entrega + timedelta(days=cliente["credito"])
    fecha_venc_serial = _fecha_a_serial(fecha_venc)
    dias_venc         = fecha_venc_serial - _fecha_a_serial(date.today())

    # ── Descargar y abrir el Excel
    wb = cargar_para_escritura(FILE_ID)
    ws = wb[HOJA_PEDIDOS]

    filas_agregadas = 0
    for item in items:
        calcs = _calcular_fila(item["cantidad"], item["precio"], item["costo"])

        # Orden exacto de columnas en 'Ped 22-24':
        # Fecha Entrega | Nombre Cliente | Cantidad | Producto | Precio | Costo |
        # Total | Total Costo | Margen | Margen % | IVA | ISR |
        # Dia Semana | Mes | Semana | Año | Unidad de Medida | Proveedor |
        # Direccion | NIT | Fecha Vencimiento | Dias Vencimiento |
        # Empresa | Tipo | Segmento | Mes N | Mes NN |
        # Unico | Parent | Unidad Despacho | Status
        fila = [
            fecha_serial,               # Fecha Entrega (serial Excel)
            cliente["nombre"],          # Nombre Cliente
            item["cantidad"],           # Cantidad
            item["nombre"],             # Producto
            item["precio"],             # Precio unitario
            item["costo"],              # Costo unitario
            calcs["total"],             # Total
            calcs["total_costo"],       # Total Costo
            calcs["margen"],            # Margen (Q)
            calcs["margen_pct"],        # Margen %
            calcs["iva"],               # IVA (base sin IVA)
            calcs["isr"],               # ISR (base retención)
            dia_semana,                 # Dia Semana
            mes_numero,                 # Mes (número)
            semana,                     # Semana del año
            fecha_entrega.year,         # Año
            item["unidad"],             # Unidad de Medida
            item["proveedor"],          # Proveedor
            cliente["direccion"],       # Direccion
            cliente["nit"],             # NIT
            fecha_venc_serial,          # Fecha Vencimiento (serial Excel)
            dias_venc,                  # Dias Vencimiento
            cliente["empresa"],         # Empresa
            cliente["tipo"],            # Tipo (Restaurante, Bar, etc.)
            item["segmento"],           # Segmento
            mes_n,                      # Mes N (ene, feb...)
            mes_nn,                     # Mes NN (01, 02...)
            unico,                      # Código Unico del pedido
            item["parent"],             # Parent (nombre base del producto)
            item["unidad_despacho"],    # Unidad Despacho
            "Pendiente",                # Status
        ]
        ws.append(fila)
        filas_agregadas += 1

    # ── Subir de vuelta a Drive
    guardar_en_drive(wb, FILE_ID)
    wb.close()

    return filas_agregadas
