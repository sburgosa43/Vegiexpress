"""
backup_helper.py — Backup automático de Pedidos a Google Drive.
Guarda un CSV en la carpeta compartida definida en BACKUP_FOLDER_ID (secrets).
El archivo se sobreescribe siempre con el mismo nombre.
"""
import io
import csv
import time
import streamlit as st
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

BACKUP_FILENAME = "VeggiExpress_Pedidos_Backup.csv"
SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

import json


def _drive_service():
    """Construye el cliente de Drive API con las credenciales del service account."""
    if "GOOGLE_CREDENTIALS" in st.secrets:
        info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    else:
        info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _folder_id() -> str:
    fid = st.secrets.get("BACKUP_FOLDER_ID", "")
    if not fid:
        raise ValueError("BACKUP_FOLDER_ID no está configurado en Streamlit Secrets.")
    return fid


def _pedidos_csv() -> bytes:
    """Genera el CSV de Pedidos en memoria y retorna los bytes."""
    from gsheets import ws as _ws
    sheet = _ws("pedidos")
    todas = sheet.get_all_values()   # incluye encabezado

    buf = io.StringIO()
    w   = csv.writer(buf)
    # Primera fila: timestamp de backup
    ts  = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    w.writerow([f"# VeggiExpress Backup — {ts}", "", "", "", ""])
    w.writerows(todas)
    return buf.getvalue().encode("utf-8-sig")   # utf-8-sig = Excel-friendly BOM


def _find_existing_file(service, folder_id: str) -> str | None:
    """Busca el archivo de backup en la carpeta. Retorna file_id o None."""
    q = (f"name='{BACKUP_FILENAME}' "
         f"and '{folder_id}' in parents "
         f"and trashed=false")
    res = service.files().list(q=q, spaces="drive",
                                fields="files(id,name)",
                                includeItemsFromAllDrives=True,
                                supportsAllDrives=True).execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None


def crear_backup(motivo: str = "manual") -> dict:
    """
    Genera CSV de Pedidos y lo sube a Drive.
    Sobreescribe si ya existe, crea si no.
    Retorna {"filas": N, "url": "...", "ts": "..."}
    """
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    try:
        service   = _drive_service()
        folder_id = _folder_id()
        csv_bytes = _pedidos_csv()
        media     = MediaInMemoryUpload(csv_bytes, mimetype="text/csv", resumable=False)

        file_id = _find_existing_file(service, folder_id)

        if file_id:
            # Actualizar archivo existente
            service.files().update(
                fileId=file_id,
                media_body=media,
                supportsAllDrives=True
            ).execute()
        else:
            # Crear nuevo archivo
            meta = {
                "name":    BACKUP_FILENAME,
                "parents": [folder_id],
            }
            result = service.files().create(
                body=meta,
                media_body=media,
                fields="id",
                supportsAllDrives=True
            ).execute()
            file_id = result["id"]

        # Contar filas (sin la fila de timestamp)
        n_filas = csv_bytes.decode("utf-8-sig").count("\n") - 2

        # Guardar meta del último backup en session_state
        st.session_state["_backup_info"] = {
            "ts":      ts,
            "filas":   n_filas,
            "file_id": file_id,
            "motivo":  motivo,
        }

        return {"ok": True, "filas": n_filas, "ts": ts, "file_id": file_id}

    except Exception as e:
        return {"ok": False, "error": str(e)}


def backup_info() -> dict:
    """Retorna info del último backup de esta sesión."""
    return st.session_state.get("_backup_info", {})


def backup_silencioso(motivo: str = "auto") -> None:
    """
    Ejecuta backup sin interrumpir el flujo.
    Llama antes de operaciones destructivas.
    """
    try:
        crear_backup(motivo=motivo)
    except Exception:
        pass  # backup silencioso nunca bloquea la operación principal


def get_drive_link() -> str | None:
    """
    Retorna el link directo al archivo de backup en Drive.
    None si no existe todavia.
    """
    try:
        service   = _drive_service()
        folder_id = _folder_id()
        file_id   = _find_existing_file(service, folder_id)
        if file_id:
            return f"https://drive.google.com/file/d/{file_id}/view"
        return None
    except Exception:
        return None
