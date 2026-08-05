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
    "gastosconfig":  "GastosConfig",
    "precioszona":   "PreciosZona",
    "preciosgrupo":  "PreciosGrupo",
    "preciosclient": "PreciosCliente",
    "datoscompletos": "DatosCompletos",
    "formimports":    "FormImports",
    "backup":       "Pedidos_Backup",
    "produccion":         "Produccion",
    "produccioncultivos": "ProduccionCultivos",
    "produccionaplic":    "ProduccionAplicaciones",
    "produccionfert":     "ProduccionFertilizantes",
    "reglaspago":         "ReglasPago",
    "formimports_hoteles": "FormImports_Hoteles",
    "compras_temp":       "ComprasTemporal",
    "compras_hist":       "ComprasHistorico",
    "precios_cenma":      "Precios Cenma",
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


@st.cache_resource(show_spinner=False)
def _ws_cached(nombre: str):
    """Handle del worksheet, cacheado por hoja.

    Resolver el worksheet cuesta un viaje a la API (hay que traer la metadata
    del spreadsheet) que antes se pagaba en CADA lectura. El handle se puede
    cachear con seguridad: el refresh del token vive en las credenciales de
    _gc(), no acá.

    Nunca llamar directo — usar ws(), que agrega el retry. Y si se invalida
    _gc, hay que invalidar esto también: ver clear_ws_cache().
    """
    return _wb().worksheet(HOJAS[nombre])


def ws(nombre: str):
    """Retorna un worksheet por nombre clave, con retry."""
    last_err = None
    for attempt in range(3):
        try:
            return _ws_cached(nombre)
        except Exception as e:
            last_err = e
            # El handle cacheado pudo quedar apuntando a un cliente muerto o a
            # una hoja renombrada; se descarta todo para re-resolver.
            clear_ws_cache()
            if isinstance(e, KeyError):
                break          # nombre de hoja inexistente: reintentar no sirve
            time.sleep(2 ** attempt)
    raise ConnectionError(f"No se pudo acceder a '{HOJAS.get(nombre, nombre)}': {last_err}")


def get_all_rows(nombre: str) -> list[list]:
    """Lee todas las filas (sin encabezado) con retry."""
    last_err = None
    for attempt in range(3):
        try:
            vals = ws(nombre).get_all_values()
            return vals[1:] if vals else []
        except Exception as e:
            last_err = e
            clear_ws_cache()
            time.sleep(2 ** attempt)
    raise ConnectionError(f"Error leyendo '{nombre}': {last_err}")


def get_all_records_ws(nombre: str) -> list[dict]:
    """Lee todos los registros como dicts."""
    for attempt in range(3):
        try:
            return ws(nombre).get_all_records()
        except Exception as e:
            if attempt < 2:
                clear_ws_cache()
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
                clear_ws_cache()
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
                clear_ws_cache()
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
                clear_ws_cache()
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
                    # Invalidar ANTES de re-pedir el handle: si no, ws() devuelve
                    # el mismo objeto cacheado que acaba de fallar.
                    clear_ws_cache()
                    sheet = ws(nombre)
                    time.sleep(1)
                else:
                    raise


def delete_rows_range(nombre: str, desde: int, hasta: int) -> int:
    """Elimina el bloque de filas [desde, hasta] (1-indexed) en UNA llamada.

    delete_rows() borra de a una: para un bloque de cientos de filas serían
    cientos de llamadas a la API. Usar esta cuando las filas son contiguas —
    el llamador tiene que haberlo verificado, porque acá se borra el rango
    entero sin mirar el contenido.
    """
    if desde < 2 or hasta < desde:
        return 0
    sheet = ws(nombre)
    for attempt in range(3):
        try:
            sheet.delete_rows(desde, hasta)
            return hasta - desde + 1
        except Exception:
            if attempt < 2:
                clear_ws_cache()
                sheet = ws(nombre)
                time.sleep(1)
            else:
                raise
    return 0


def cell_value(nombre: str, row: int, col: int):
    """Lee una celda individual."""
    return ws(nombre).cell(row, col).value


def clear_ws_cache():
    """Limpia el caché para forzar reconexión.

    Limpia AMBOS niveles y en este orden: los worksheets cacheados guardan una
    referencia al cliente de _gc(), así que limpiar solo _gc dejaría handles
    apuntando a un cliente muerto.
    """
    _ws_cached.clear()
    _gc.clear()


def ensure_ws(nombre: str, headers: list, rows_iniciales: list = None) -> bool:
    """
    Garantiza que la hoja exista. Si no existe, la crea con encabezados
    y filas iniciales opcionales. Retorna True si la creó, False si ya existia.
    nombre: clave en HOJAS. headers: lista de encabezados (fila 1).
    """
    real = HOJAS.get(nombre, nombre)
    wb = _wb()
    try:
        wb.worksheet(real)
        return False  # ya existe
    except Exception:
        pass
    # Crear
    ncols = max(len(headers), 4)
    nrows = max(len(rows_iniciales or []) + 5, 20)
    nueva = wb.add_worksheet(title=real, rows=nrows, cols=ncols)
    data = [headers]
    if rows_iniciales:
        data.extend(rows_iniciales)
    nueva.update(f"A1", data, value_input_option="USER_ENTERED")
    # La hoja acaba de nacer: invalidar para que ws(nombre) la re-resuelva en
    # vez de arrastrar un intento fallido previo.
    clear_ws_cache()
    return True
