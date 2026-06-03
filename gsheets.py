"""
gsheets.py — Capa de acceso a Google Sheets (reemplaza drive_helper + openpyxl)
"""
import json
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1mldwwbCY3F0Bxy6gqu7qwWkuhiEGmwlby_bL1YBh_hg"

HOJAS = {
    "pedidos":    "Pedidos",
    "clientes":   "Clientes",
    "productos":  "Listado Productos",
    "antigua":    "Listado Antigua",
    "config":     "Config",
    "historial":  "Historial Cambios",
}

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


@st.cache_resource
def _gc():
    """Conexión gspread autenticada y cacheada."""
    if "GOOGLE_CREDENTIALS" in st.secrets:
        info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    else:
        info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_resource
def _wb():
    """Spreadsheet cacheado."""
    return _gc().open_by_key(SHEET_ID)


def ws(nombre: str):
    """Retorna un worksheet por nombre clave."""
    return _wb().worksheet(HOJAS[nombre])


def get_all_rows(nombre: str) -> list[list]:
    """Lee todas las filas (sin encabezado) como listas de strings."""
    vals = ws(nombre).get_all_values()
    return vals[1:] if vals else []   # skip header row 1


def get_all_records_ws(nombre: str) -> list[dict]:
    """Lee todos los registros como dicts usando el encabezado de fila 1."""
    return ws(nombre).get_all_records()


def append_rows(nombre: str, rows: list[list]) -> None:
    """Agrega múltiples filas al final de la hoja."""
    ws(nombre).append_rows(rows, value_input_option="USER_ENTERED")


def update_cells(nombre: str, updates: list[dict]) -> None:
    """
    Actualiza múltiples celdas en un solo request.
    updates: [{"range": "E2", "values": [[value]]}, ...]
    """
    ws(nombre).batch_update(updates, value_input_option="USER_ENTERED")


def update_cell(nombre: str, row: int, col: int, value) -> None:
    """Actualiza una celda individual (row y col son 1-indexed)."""
    ws(nombre).update_cell(row, col, value)


def delete_rows(nombre: str, row_indices: list[int]) -> None:
    """Elimina filas (1-indexed). Debe hacerse en orden descendente."""
    sheet = ws(nombre)
    for row in sorted(row_indices, reverse=True):
        sheet.delete_rows(row)


def cell_value(nombre: str, row: int, col: int):
    """Lee una celda individual."""
    return ws(nombre).cell(row, col).value


def clear_ws_cache():
    """Limpia el caché del workbook para forzar reconexión."""
    _wb.clear()
    _gc.clear()
