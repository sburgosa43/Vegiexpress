"""
sheets_helper.py — Google Sheets para pedidos pendientes de clientes.
Usa la misma cuenta de servicio que Drive.
"""
import streamlit as st

SHEET_NAME_PEDIDOS = "Pedidos_Entrantes"
HEADERS = [
    "Timestamp", "Restaurante", "Es_Nuevo", "Area",
    "Fecha_Entrega", "Semana", "Producto", "Cantidad",
    "Unidad", "Precio", "Total", "Status", "Notas",
]


def _get_client():
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)


def _get_sheet():
    gc        = _get_client()
    sheet_id  = st.secrets["PEDIDOS_SHEET_ID"]
    wb        = gc.open_by_key(sheet_id)
    try:
        ws = wb.worksheet(SHEET_NAME_PEDIDOS)
    except Exception:
        ws = wb.add_worksheet(SHEET_NAME_PEDIDOS, rows=1000, cols=len(HEADERS))
        ws.append_row(HEADERS)
    return ws


def guardar_pedido_cliente(restaurante: str, es_nuevo: bool, area: str,
                            fecha_entrega: str, semana: int,
                            lineas: list) -> int:
    """
    Guarda las líneas de un pedido del cliente en el Google Sheet.
    lineas: [{producto, cantidad, unidad, precio, total}]
    """
    from datetime import datetime
    ws  = _get_sheet()
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for l in lineas:
        rows.append([
            ts, restaurante, "Sí" if es_nuevo else "No", area,
            fecha_entrega, semana,
            l["producto"], l["cantidad"], l["unidad"],
            l["precio"], l["total"],
            "Pendiente", "",
        ])
    ws.append_rows(rows, value_input_option="USER_ENTERED")
    return len(rows)


def leer_pedidos_entrantes() -> list:
    """Lee todos los pedidos del Google Sheet. Retorna lista de dicts."""
    try:
        ws   = _get_sheet()
        data = ws.get_all_records()
        return data
    except Exception as e:
        return []


def actualizar_status(row_indices: list, nuevo_status: str):
    """Actualiza el status de las filas indicadas (1-indexed, incluyendo header)."""
    ws = _get_sheet()
    STATUS_COL = HEADERS.index("Status") + 1  # 1-indexed
    for ri in row_indices:
        ws.update_cell(ri, STATUS_COL, nuevo_status)
