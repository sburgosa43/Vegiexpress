"""
drive_helper.py
Maneja la conexión con Google Drive para descargar y subir el archivo Excel.
"""

import io
import json
import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import openpyxl

SCOPES = ["https://www.googleapis.com/auth/drive"]
MIMETYPE_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _get_service():
    """
    Crea el cliente de Google Drive.
    Acepta credenciales en dos formatos en Streamlit Secrets:
      Formato A: GOOGLE_CREDENTIALS = '''{ ...json completo... }'''
      Formato B: [gcp_service_account] con campos separados
    """
    secrets = st.secrets

    # Formato A: JSON completo como string
    if "GOOGLE_CREDENTIALS" in secrets:
        raw = secrets["GOOGLE_CREDENTIALS"]
        if isinstance(raw, dict):
            info = dict(raw)
        else:
            info = json.loads(str(raw))

    # Formato B: seccion TOML [gcp_service_account]
    elif "gcp_service_account" in secrets:
        info = dict(secrets["gcp_service_account"])

    else:
        raise ValueError(
            "Credenciales no encontradas.\n"
            "Revisa los Secrets en Streamlit Cloud:\n"
            "Necesitas GOOGLE_CREDENTIALS o [gcp_service_account]."
        )

    # Reparar \\n escapados en private_key (problema frecuente en Streamlit)
    if "private_key" in info and "\\n" in info["private_key"]:
        info["private_key"] = info["private_key"].replace("\\n", "\n")

    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _download_bytes(file_id: str) -> io.BytesIO:
    """Descarga el archivo de Drive y retorna un BytesIO."""
    service = _get_service()
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buffer.seek(0)
    return buffer


def cargar_para_lectura(file_id: str) -> openpyxl.Workbook:
    """Descarga el Excel y lo abre para LECTURA (valores, no formulas)."""
    buf = _download_bytes(file_id)
    return openpyxl.load_workbook(buf, data_only=True, read_only=True)


def cargar_para_escritura(file_id: str) -> openpyxl.Workbook:
    """Descarga el Excel y lo abre para ESCRITURA (preserva formulas)."""
    buf = _download_bytes(file_id)
    return openpyxl.load_workbook(buf, data_only=False)


def guardar_en_drive(wb: openpyxl.Workbook, file_id: str):
    """Sube el workbook modificado de vuelta a Google Drive."""
    service = _get_service()
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    media = MediaIoBaseUpload(buffer, mimetype=MIMETYPE_XLSX, resumable=True)
    service.files().update(fileId=file_id, media_body=media).execute()
