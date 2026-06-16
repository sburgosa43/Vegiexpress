"""
forms_helper.py — Creación y sincronización de formularios Google Forms.
Requiere: Google Forms API + Drive API habilitadas en el proyecto.
"""
import json
import streamlit as st

# ── Credenciales con scopes de Forms ──────────────────────────────────────────
def _creds():
    from google.oauth2.service_account import Credentials
    SCOPES = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/forms.body",
        "https://www.googleapis.com/auth/forms.responses.readonly",
    ]
    if "GOOGLE_CREDENTIALS" in st.secrets:
        info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    else:
        info = dict(st.secrets["gcp_service_account"])
    return Credentials.from_service_account_info(info, scopes=SCOPES)


def _forms_svc():
    from googleapiclient.discovery import build
    return build("forms", "v1", credentials=_creds(), cache_discovery=False)


def _drive_svc():
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=_creds(), cache_discovery=False)


# ── Config: form_id persiste en GastosConfig ──────────────────────────────────
_HOG_KEY = "HOG_FORM_ID"


def get_form_id() -> str | None:
    try:
        from gsheets import get_all_rows
        for row in get_all_rows("gastosconfig"):
            if row and str(row[0]).strip().upper() == _HOG_KEY:
                v = str(row[1]).strip() if len(row) > 1 else ""
                return v or None
    except Exception:
        pass
    return None


def _save_form_id(form_id: str) -> None:
    try:
        from gsheets import ws as _ws, get_all_rows
        sheet = _ws("gastosconfig")
        for i, row in enumerate(get_all_rows("gastosconfig"), start=2):
            if row and str(row[0]).strip().upper() == _HOG_KEY:
                sheet.update(f"B{i}", [[form_id]])
                return
        sheet.append_rows([[_HOG_KEY, form_id, "", ""]])
    except Exception:
        pass


# ── Obtener productos Hogares para el formulario ───────────────────────────────
def _productos_hogares() -> list[dict]:
    """Retorna TODOS los productos con precio Hogares, ordenados por segmento."""
    from excel_helper import leer_productos_con_fila
    from data_helper  import leer_precios_capa

    prods_gen = leer_productos_con_fila(es_antigua=False)
    precios_h = {p["producto"].lower(): p["precio"]
                 for p in leer_precios_capa("precioszona", "Hogares")}

    result = []
    for p in prods_gen:
        if not p.get("nombre") or not p.get("unidad"):
            continue
        precio = precios_h.get(p["nombre"].lower()) or float(p.get("precio") or 0)
        if precio <= 0:
            continue
        result.append({
            "nombre":   p["nombre"],
            "unidad":   p["unidad"],
            "segmento": p.get("segmento", "Otros"),
            "precio":   precio,
        })
    return sorted(result, key=lambda x: (x["segmento"], x["nombre"]))


# Keys para persistir seleccion del formulario en session_state
_FORM_SEL_KEY = "hog_form_seleccion"
_FORM_ORDER_KEY = "hog_form_orden"


# ── Crear formulario nuevo ─────────────────────────────────────────────────────
def crear_formulario(titulo: str = "Pedidos Veggi Hogares",
                     productos: list = None) -> dict:
    """
    Crea un formulario Google Forms con los productos Hogares actuales.
    Retorna {form_id, form_url, edit_url, n_productos}.
    """
    import time
    prods = productos if productos is not None else _productos_hogares()
    svc   = _forms_svc()

    # 1. Crear formulario — solo title (sin documentTitle que causa errores)
    for intento in range(3):
        try:
            form    = svc.forms().create(body={
                "info": {"title": titulo}
            }).execute()
            break
        except Exception as e:
            if intento == 2: raise
            time.sleep(2 ** intento)
    form_id = form["formId"]

    # 2. Construir preguntas — solo questionItem (más compatible)
    reqs = []
    idx  = 0

    def _text_item(titulo_q, req=False):
        return {"createItem": {
            "item": {
                "title": titulo_q,
                "questionItem": {"question": {
                    "required": req,
                    "textQuestion": {"paragraph": False}
                }}
            },
            "location": {"index": idx}
        }}

    # Campos de info del cliente
    for titulo_q, req in [
        ("Nombre y apellido",    True),
        ("Correo electrónico",   True),
        ("Dirección de entrega", True),
        ("Teléfono de contacto", False),
    ]:
        reqs.append({"createItem": {
            "item": {
                "title": titulo_q,
                "questionItem": {"question": {
                    "required": req,
                    "textQuestion": {"paragraph": False}
                }}
            },
            "location": {"index": idx}
        }})
        idx += 1

    # Método de pago
    reqs.append({"createItem": {
        "item": {
            "title": "Método de pago",
            "questionItem": {"question": {
                "required": True,
                "choiceQuestion": {
                    "type": "RADIO",
                    "options": [{"value": "Efectivo"},
                                {"value": "Transferencia"}]
                }
            }}
        },
        "location": {"index": idx}
    }})
    idx += 1

    # Productos (sin pageBreak ni textItem — mayor compatibilidad)
    for p in prods:
        nombre_p = (f"{p['nombre']} ({p['unidad']}) "
                    f"- Q.{p['precio']:.2f}")
        reqs.append({"createItem": {
            "item": {
                "title": nombre_p,
                "questionItem": {"question": {
                    "required": False,
                    "textQuestion": {"paragraph": False}
                }}
            },
            "location": {"index": idx}
        }})
        idx += 1

    # 3. Batch update en bloques de 50 (evita timeouts)
    BLOQUE = 50
    for i in range(0, len(reqs), BLOQUE):
        svc.forms().batchUpdate(
            formId=form_id,
            body={"requests": reqs[i:i+BLOQUE]}
        ).execute()
        if i + BLOQUE < len(reqs):
            time.sleep(0.5)

    # 4. Compartir públicamente
    try:
        _drive_svc().permissions().create(
            fileId=form_id,
            body={"type": "anyone", "role": "reader"},
            supportsAllDrives=True
        ).execute()
    except Exception:
        pass   # compartir puede fallar si ya tiene permiso

    # 5. Guardar form_id
    _save_form_id(form_id)

    return {
        "form_id":     form_id,
        "form_url":    f"https://docs.google.com/forms/d/{form_id}/viewform",
        "edit_url":    f"https://docs.google.com/forms/d/{form_id}/edit",
        "n_productos": len(prods),
    }


# ── Sincronizar precios en formulario existente ───────────────────────────────
def sincronizar_formulario(form_id: str) -> dict:
    """
    Actualiza los precios de productos existentes en el formulario.
    NO elimina preguntas — actualiza solo los títulos que matcheen.
    Retorna {actualizados, agregados, sin_cambio}.
    """
    prods    = _productos_hogares()
    prod_map = {p["nombre"].lower(): p for p in prods}
    svc      = _forms_svc()

    # Leer formulario actual
    form    = svc.forms().get(formId=form_id).execute()
    items   = form.get("items", [])

    requests   = []
    actualizados = 0
    sin_cambio   = 0
    nombres_en_form = set()

    import re as _re

    for item in items:
        if "questionItem" not in item:
            continue
        titulo = item.get("title", "")
        # Detectar si es pregunta de producto: "Nombre (Unidad) - Q.precio"
        m = _re.match(r'^(.+?)\s*\((.+?)\)\s*[-–]\s*Q[.\s]*([\d.,]+)', titulo)
        if not m:
            continue
        nombre_f = m.group(1).strip().lower()
        nombres_en_form.add(nombre_f)
        prod = prod_map.get(nombre_f)
        if not prod:
            continue
        nuevo_titulo = (f"{prod['nombre']} ({prod['unidad']}) "
                        f"- Q.{prod['precio']:.2f}")
        if nuevo_titulo == titulo:
            sin_cambio += 1
            continue
        # Actualizar título
        requests.append({"updateItem": {
            "item": {
                "itemId": item["itemId"],
                "title":  nuevo_titulo,
                "questionItem": item["questionItem"]
            },
            "updateMask": "title",
            "location":   {"index": item.get("index", 0)}
        }})
        actualizados += 1

    # Agregar productos nuevos (no estaban en el formulario)
    agregados = 0
    nuevos = [p for p in prods if p["nombre"].lower() not in nombres_en_form]
    for p in nuevos:
        titulo_prod = f"{p['nombre']} ({p['unidad']}) - Q.{p['precio']:.2f}"
        requests.append({"createItem": {
            "item": {"title": titulo_prod, "questionItem": {"question": {
                "required": False,
                "textQuestion": {"paragraph": False}
            }}},
            "location": {"index": len(items) + agregados}
        }})
        agregados += 1

    if requests:
        svc.forms().batchUpdate(
            formId=form_id, body={"requests": requests}
        ).execute()

    return {"actualizados": actualizados,
            "agregados":    agregados,
            "sin_cambio":   sin_cambio}


# ── Leer respuestas desde Forms API ───────────────────────────────────────────
def leer_respuestas_api(form_id: str) -> tuple[dict, list]:
    """
    Lee respuestas directamente via Forms API.
    Retorna (q_map, responses).
    q_map: {questionId → title}
    """
    svc  = _forms_svc()
    form = svc.forms().get(formId=form_id).execute()

    q_map = {}
    for item in form.get("items", []):
        if "questionItem" in item:
            q_id = item["questionItem"]["question"].get("questionId")
            if q_id:
                q_map[q_id] = item.get("title", "")

    all_resp = []
    page_token = None
    while True:
        params = {"formId": form_id}
        if page_token:
            params["pageToken"] = page_token
        result = svc.forms().responses().list(**params).execute()
        all_resp.extend(result.get("responses", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return q_map, all_resp
