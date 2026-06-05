"""
sheets_helper.py — Pedidos entrantes de clientes (migrado a gspread).
Reemplaza la implementación anterior que usaba la API directa de Sheets.
"""
import streamlit as st
from datetime import datetime
from gsheets import get_all_rows, append_rows, update_cells

PEDIDOS_SHEET_KEY = "pedidos_entrantes_clientes"  # clave separada de gsheets

# Sheet ID de pedidos entrantes (diferente al Sheet principal)
import json

def _get_client():
    import gspread
    from google.oauth2.service_account import Credentials
    SCOPES = ["https://spreadsheets.google.com/feeds",
              "https://www.googleapis.com/auth/drive"]
    if "GOOGLE_CREDENTIALS" in st.secrets:
        info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    else:
        info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_resource
def _get_sheet():
    sheet_id = st.secrets.get("PEDIDOS_SHEET_ID", "")
    if not sheet_id:
        return None
    gc = _get_client()
    return gc.open_by_key(sheet_id).sheet1


def guardar_pedido_cliente(data: dict) -> bool:
    """Guarda un pedido de cliente en el Sheet de pedidos entrantes."""
    try:
        ws = _get_sheet()
        if not ws:
            return False
        row = [
            datetime.now().strftime("%d/%m/%Y %H:%M"),
            data.get("restaurante", ""),
            data.get("es_nuevo", "No"),
            data.get("area", ""),
            data.get("fecha_entrega", ""),
            data.get("semana", ""),
            data.get("producto", ""),
            data.get("cantidad", ""),
            data.get("unidad", ""),
            data.get("notas", ""),
            "Pendiente",
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")
        _get_sheet.clear()
        return True
    except Exception as e:
        st.error(f"Error guardando pedido: {e}")
        return False


def leer_pedidos_entrantes() -> list[dict]:
    """Lee todos los pedidos entrantes del Sheet."""
    try:
        ws = _get_sheet()
        if not ws:
            return []
        rows = ws.get_all_records()
        result = []
        for i, row in enumerate(rows, start=2):
            result.append({
                "row_num":    i,
                "timestamp":  str(row.get("Timestamp", "")),
                "restaurante":str(row.get("Restaurante", "")),
                "es_nuevo":   str(row.get("Es_Nuevo", "")),
                "area":       str(row.get("Area", "")),
                "fecha":      str(row.get("Fecha_Entrega", "")),
                "semana":     str(row.get("Semana", "")),
                "producto":   str(row.get("Producto", "")),
                "cantidad":   str(row.get("Cantidad", "")),
                "unidad":     str(row.get("Unidad", "")),
                "notas":      str(row.get("Notas", "")),
                "status":     str(row.get("Status", "Pendiente")),
            })
        return result
    except Exception as e:
        st.warning(f"Error leyendo pedidos entrantes: {e}")
        return []


def actualizar_status(row_num: int, nuevo_status: str) -> bool:
    """Actualiza el status de un pedido entrante."""
    try:
        ws = _get_sheet()
        if not ws:
            return False
        # Status suele estar en la última columna — ajustar si cambia
        headers = ws.row_values(1)
        col_status = headers.index("Status") + 1 if "Status" in headers else 11
        ws.update_cell(row_num, col_status, nuevo_status)
        _get_sheet.clear()
        return True
    except Exception as e:
        st.warning(f"Error actualizando status: {e}")
        return False
