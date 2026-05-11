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
    """Crea el cliente de Google Drive usando las credenciales del Service Account."""
    info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
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
    """
    Descarga el Excel y lo abre para LECTURA.
    Usa data_only=True para obtener valores calculados (no fórmulas).
    Usa read_only=True para mayor velocidad.
    """
    buf = _download_bytes(file_id)
    return openpyxl.load_workbook(buf, data_only=True, read_only=True)


def cargar_para_escritura(file_id: str) -> openpyxl.Workbook:
    """
    Descarga el Excel y lo abre para ESCRITURA.
    Preserva fórmulas y estructura del archivo original.
    Solo se usa justo antes de guardar un pedido.
    """
    buf = _download_bytes(file_id)
    return openpyxl.load_workbook(buf, data_only=False)


def guardar_en_drive(wb: openpyxl.Workbook, file_id: str):
    """
    Sube el workbook modificado de vuelta a Google Drive,
    reemplazando el archivo existente (mismo file_id).
    """
    service = _get_service()
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    media = MediaIoBaseUpload(buffer, mimetype=MIMETYPE_XLSX, resumable=True)
    service.files().update(fileId=file_id, media_body=media).execute()
