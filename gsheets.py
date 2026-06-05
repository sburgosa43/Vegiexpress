"""
gsheets.py — Capa de acceso a Google Sheets con retry automático.
"""
import json
import time
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1mldwwbCY3F0Bxy6gqu7qwWkuhiEGmwlby_bL1YBh_hg"

HOJAS = {
    "pedidos":    "Pedidos",
    "clientes":   "Clientes",
    "productos":  "Listado Productos",
    "antigua":    "Listado Productos Antigua",
    "config":     "Config",
    "historial":  "Historial Cambios",
    "gastos":       "Gastos",
    "gastosconfig": "GastosConfig",
    "backup":       "Pedidos_Backup",
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


def _wb():
    """
    Abre el Spreadsheet con retry automático y backoff para 429.
    NO se cachea para evitar tokens expirados — _gc() ya está cacheado.
    """
    last_err = None
    for attempt in range(4):
        try:
            return _gc().open_by_key(SHEET_ID)
        except gspread.exceptions.APIError as e:
            last_err = e
            status = getattr(e.response, "status_code", 0) if hasattr(e, "response") else 0
            if attempt < 3:
                _gc.clear()
                # 429 rate limit → esperar más
                wait = 15 if status == 429 else 2 ** attempt
                time.sleep(wait)
        except Exception as e:
            last_err = e
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise ConnectionError(f"No se pudo conectar a Google Sheets: {last_err}")


def ws(nombre: str):
    """Retorna un worksheet por nombre clave, con retry."""
    last_err = None
    for attempt in range(3):
        try:
            return _wb().worksheet(HOJAS[nombre])
        except gspread.exceptions.APIError as e:
            last_err = e
            _gc.clear()
            time.sleep(2 ** attempt)
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise ConnectionError(f"No se pudo acceder a '{HOJAS[nombre]}': {last_err}")


def get_all_rows(nombre: str) -> list[list]:
    """Lee todas las filas (sin encabezado) con retry."""
    last_err = None
    for attempt in range(3):
        try:
            vals = ws(nombre).get_all_values()
            return vals[1:] if vals else []
        except Exception as e:
            last_err = e
            _gc.clear()
            time.sleep(2 ** attempt)
    raise ConnectionError(f"Error leyendo '{nombre}': {last_err}")


def get_all_records_ws(nombre: str) -> list[dict]:
    """Lee todos los registros como dicts."""
    for attempt in range(3):
        try:
            return ws(nombre).get_all_records()
        except Exception as e:
            if attempt < 2:
                _gc.clear()
                time.sleep(2 ** attempt)
    return []


def append_rows(nombre: str, rows: list[list]) -> None:
    """Agrega múltiples filas al final de la hoja."""
    for attempt in range(3):
        try:
            ws(nombre).append_rows(rows, value_input_option="USER_ENTERED")
            return
        except Exception as e:
            if attempt < 2:
                _gc.clear()
                time.sleep(2 ** attempt)
            else:
                raise


def update_cells(nombre: str, updates: list[dict]) -> None:
    """
    Actualiza múltiples celdas en un solo request.
    updates: [{"range": "E2", "values": [[value]]}, ...]
    """
    if not updates:
        return
    for attempt in range(3):
        try:
            ws(nombre).batch_update(updates, value_input_option="USER_ENTERED")
            return
        except Exception as e:
            if attempt < 2:
                _gc.clear()
                time.sleep(2 ** attempt)
            else:
                raise


def update_cell(nombre: str, row: int, col: int, value) -> None:
    """Actualiza una celda individual (row y col son 1-indexed)."""
    for attempt in range(3):
        try:
            ws(nombre).update_cell(row, col, value)
            return
        except Exception as e:
            if attempt < 2:
                _gc.clear()
                time.sleep(2 ** attempt)
            else:
                raise


def delete_rows(nombre: str, row_indices: list[int]) -> None:
    """Elimina filas (1-indexed) en orden descendente."""
    sheet = ws(nombre)
    for row in sorted(row_indices, reverse=True):
        for attempt in range(3):
            try:
                sheet.delete_rows(row)
                break
            except Exception as e:
                if attempt < 2:
                    _gc.clear()
                    sheet = ws(nombre)
                    time.sleep(1)
                else:
                    raise


def cell_value(nombre: str, row: int, col: int):
    """Lee una celda individual."""
    return ws(nombre).cell(row, col).value


def clear_ws_cache():
    """Limpia el caché para forzar reconexión."""
    _gc.clear()
