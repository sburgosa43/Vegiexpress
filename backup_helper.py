"""
backup_helper.py — Backup de Pedidos a Google Drive.
Guarda un CSV en la carpeta BACKUP_FOLDER_ID (secrets). El file_id se persiste
en GastosConfig para no depender de búsquedas en Drive (que fallan con service
accounts en carpetas compartidas).
"""
import io
import csv
import json
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


def _drive_service():
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
    return str(fid).strip()


def _get_stored_file_id() -> str | None:
    """file_id guardado en GastosConfig (fila BACKUP_FILE_ID)."""
    try:
        from gsheets import get_all_rows
        for row in get_all_rows("gastosconfig"):
            if row and str(row[0]).strip().upper() == "BACKUP_FILE_ID":
                fid = str(row[1]).strip() if len(row) > 1 else ""
                return fid or None
    except Exception:
        pass
    return None


def _store_file_id(file_id: str) -> None:
    try:
        from gsheets import ws as _ws, get_all_rows
        sheet = _ws("gastosconfig")
        for i, row in enumerate(get_all_rows("gastosconfig"), start=2):
            if row and str(row[0]).strip().upper() == "BACKUP_FILE_ID":
                sheet.update(f"B{i}", [[file_id]])
                return
        sheet.append_rows([["BACKUP_FILE_ID", file_id, "", ""]])
    except Exception:
        pass


def _pedidos_csv() -> bytes:
    from gsheets import ws as _ws
    sheet = _ws("pedidos")
    todas = sheet.get_all_values()
    buf = io.StringIO()
    w   = csv.writer(buf)
    ts  = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    w.writerow([f"# VeggiExpress Backup — {ts}", "", "", "", ""])
    w.writerows(todas)
    return buf.getvalue().encode("utf-8-sig")


def crear_backup(motivo: str = "manual") -> dict:
    """Genera CSV de Pedidos y lo sube a Drive. Devuelve dict con ok/error/detalle."""
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    try:
        service   = _drive_service()
        folder_id = _folder_id()
    except Exception as e:
        return {"ok": False, "error": f"Configuración: {e}"}

    try:
        csv_bytes = _pedidos_csv()
        media     = MediaInMemoryUpload(csv_bytes, mimetype="text/csv", resumable=False)
        file_id   = _get_stored_file_id()

        if file_id:
            try:
                service.files().update(fileId=file_id, media_body=media,
                                       supportsAllDrives=True).execute()
            except Exception:
                file_id = None   # fue borrado; recrear

        if not file_id:
            meta = {"name": BACKUP_FILENAME, "parents": [folder_id]}
            res  = service.files().create(body=meta, media_body=media,
                                          fields="id", supportsAllDrives=True).execute()
            file_id = res["id"]
            _store_file_id(file_id)

        n_filas = max(0, csv_bytes.decode("utf-8-sig").count("\n") - 2)
        link    = f"https://drive.google.com/file/d/{file_id}/view"
        st.session_state["_backup_info"] = {
            "ts": ts, "filas": n_filas, "file_id": file_id,
            "motivo": motivo, "link": link,
        }
        return {"ok": True, "filas": n_filas, "ts": ts,
                "file_id": file_id, "link": link}

    except Exception as e:
        return {"ok": False, "error": str(e)}


def backup_info() -> dict:
    return st.session_state.get("_backup_info", {})


def backup_silencioso(motivo: str = "auto") -> None:
    try:
        crear_backup(motivo=motivo)
    except Exception:
        pass


def get_drive_link() -> str | None:
    info = st.session_state.get("_backup_info", {})
    if info.get("link"):
        return info["link"]
    fid = _get_stored_file_id()
    return f"https://drive.google.com/file/d/{fid}/view" if fid else None


def diagnostico() -> dict:
    """Verifica configuración del backup paso por paso para el usuario."""
    out = {"folder_id": False, "credenciales": False,
           "file_id_guardado": None, "carpeta_accesible": False, "error": None}
    try:
        out["folder_id"] = bool(st.secrets.get("BACKUP_FOLDER_ID", ""))
    except Exception:
        pass
    try:
        _drive_service()
        out["credenciales"] = True
    except Exception as e:
        out["error"] = f"Credenciales: {e}"
        return out
    out["file_id_guardado"] = _get_stored_file_id()
    try:
        service   = _drive_service()
        folder_id = _folder_id()
        service.files().list(q=f"'{folder_id}' in parents and trashed=false",
                             spaces="drive", fields="files(id,name)",
                             includeItemsFromAllDrives=True,
                             supportsAllDrives=True).execute()
        out["carpeta_accesible"] = True
    except Exception as e:
        out["error"] = f"Carpeta: {e}"
    return out
