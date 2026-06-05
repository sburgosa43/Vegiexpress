"""
drive_helper.py — Google Drive API helpers con retry logic
"""
import io
import time
import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from google.oauth2.service_account import Credentials
import openpyxl

SCOPES = ["https://www.googleapis.com/auth/drive"]


def _get_service():
    import json
    if "GOOGLE_CREDENTIALS" in st.secrets:
        info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    else:
        info = dict(st.secrets["gcp_service_account"])
    creds   = Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _download_bytes(service, file_id: str, retries: int = 3) -> bytes:
    """Descarga un archivo de Drive con reintentos automáticos."""
    last_err = None
    for attempt in range(retries):
        try:
            req  = service.files().get_media(fileId=file_id)
            buf  = io.BytesIO()
            dl   = MediaIoBaseDownload(buf, req)
            done = False
            while not done:
                _, done = dl.next_chunk()
            return buf.getvalue()
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # backoff: 1s, 2s
    raise ConnectionError(
        f"Drive: no se pudo descargar tras {retries} intentos: {last_err}")


def cargar_para_lectura(file_id: str) -> openpyxl.Workbook:
    """Descarga el Excel y lo abre en modo lectura."""
    svc   = _get_service()
    data  = _download_bytes(svc, file_id)
    return openpyxl.load_workbook(io.BytesIO(data), data_only=True)


def cargar_para_escritura(file_id: str) -> openpyxl.Workbook:
    """Descarga el Excel y lo abre en modo escritura (conserva fórmulas)."""
    svc   = _get_service()
    data  = _download_bytes(svc, file_id)
    return openpyxl.load_workbook(io.BytesIO(data))


def guardar_en_drive(wb: openpyxl.Workbook, file_id: str,
                     retries: int = 3) -> None:
    """Sube el workbook modificado de vuelta a Drive con reintentos."""
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    svc      = _get_service()
    media    = MediaIoBaseUpload(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        resumable=True,
    )
    last_err = None
    for attempt in range(retries):
        try:
            buf.seek(0)
            svc.files().update(fileId=file_id, media_body=media).execute()
            return
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise ConnectionError(
        f"Drive: no se pudo subir tras {retries} intentos: {last_err}")
