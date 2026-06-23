"""
forms_helper.py — Creación y sincronización de formularios Google Forms.
Requiere: Google Forms API + Drive API habilitadas en el proyecto.
"""
import json
import streamlit as st

_FORM_SEL_KEY   = "hog_form_seleccion"
_FORM_ORDER_KEY = "hog_form_orden"


# ── Credenciales ──────────────────────────────────────────────────────────────
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


# ── Productos Hogares para el formulario ──────────────────────────────────────
def _productos_hogares() -> list[dict]:
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


# ── Leer productos en formulario actual ──────────────────────────────────────
def leer_productos_en_form(form_id: str) -> set:
    import re as _re
    svc  = _forms_svc()
    form = svc.forms().get(formId=form_id).execute()
    _pat = _re.compile(r"^(.+?)\s*\(.+?\)\s*[-\u2013]\s*Q[.\s]*[\d.,]+")
    nombres = set()
    for item in form.get("items", []):
        if "questionItem" not in item:
            continue
        m = _pat.match(item.get("title", ""))
        if m:
            nombres.add(m.group(1).strip())
    return nombres


# ── Actualizar formulario (con secciones por segmento y dropdowns 1-6) ────────
def actualizar_formulario(form_id: str,
                          titulo:    str  = None,
                          productos: list = None) -> dict:
    """
    Limpia preguntas de producto + page breaks del formulario y agrega los actuales.
    Estructura:
      Página 1: Info del cliente
      Sección por segmento: page break + dropdown 1-6 por producto
      Última sección: Productos Extra (texto libre) + Confirmación (radio)
    """
    import re as _re, time

    prods = productos if productos is not None else _productos_hogares()
    svc   = _forms_svc()

    DESC_SECCION = (
        "Por favor, antes de pasar a la siguiente sección, "
        "verifica las cantidades de cada producto que quieres."
    )
    OPTS_CANT = [{"value": str(i)} for i in range(1, 7)]   # 1, 2, 3, 4, 5, 6

    # ── Paso 1: leer estructura actual ────────────────────────────────────────
    form  = svc.forms().get(formId=form_id).execute()
    items = form.get("items", [])

    # ── Paso 2: detectar items a eliminar ─────────────────────────────────────
    _pat = _re.compile(r"^.+?\s*\(.+?\)\s*[-\u2013]\s*Q[.\s]*[\d.,]+")
    _SKIP_TITLES = {
        "productos extra", "mi pedido está listo", "mi pedido esta listo",
        "para finalizar",
    }
    del_indices = sorted([
        i for i, item in enumerate(items)
        if ("questionItem" in item and _pat.match(item.get("title", "")))
        or "textItem"      in item
        or "pageBreakItem" in item
        or item.get("title", "").lower().strip() in _SKIP_TITLES
    ], reverse=True)

    if del_indices:
        del_reqs = [{"deleteItem": {"location": {"index": idx}}}
                    for idx in del_indices]
        for i in range(0, len(del_reqs), 50):
            svc.forms().batchUpdate(
                formId=form_id,
                body={"requests": del_reqs[i:i+50]}
            ).execute()
            time.sleep(0.5)

    # ── Paso 3: re-leer para saber cuántos items base quedan ──────────────────
    form2  = svc.forms().get(formId=form_id).execute()
    n_base = len(form2.get("items", []))

    # ── Paso 4: agrupar por segmento ─────────────────────────────────────────
    from collections import defaultdict as _dd
    seg_prods = _dd(list)
    for p in prods:
        seg_prods[p["segmento"]].append(p)

    _SEG_ORD = ["Vegetales","Frutas","Hierbas","Congelados","Especias","Flores","Otros"]
    segmentos = [s for s in _SEG_ORD if s in seg_prods] + \
                [s for s in seg_prods if s not in _SEG_ORD]

    # ── Paso 5: construir requests ────────────────────────────────────────────
    add_reqs = []
    pos = n_base

    for seg in segmentos:
        # Page break = nueva sección con título del segmento
        add_reqs.append({"createItem": {
            "item": {
                "title":         seg,
                "description":   DESC_SECCION,
                "pageBreakItem": {}
            },
            "location": {"index": pos}
        }})
        pos += 1

        for p in seg_prods[seg]:
            nombre_p = f"{p['nombre']} ({p['unidad']}) - Q.{p['precio']:.2f}"
            add_reqs.append({"createItem": {
                "item": {
                    "title": nombre_p,
                    "questionItem": {"question": {
                        "required": False,
                        "choiceQuestion": {
                            "type":    "DROP_DOWN",
                            "options": OPTS_CANT,
                        }
                    }}
                },
                "location": {"index": pos}
            }})
            pos += 1

    # Sección final
    add_reqs.append({"createItem": {
        "item": {
            "title":         "Para finalizar",
            "description":   "Revisá tu pedido antes de confirmar.",
            "pageBreakItem": {}
        },
        "location": {"index": pos}
    }})
    pos += 1

    # Productos Extra — texto libre largo
    add_reqs.append({"createItem": {
        "item": {
            "title": "Productos Extra",
            "questionItem": {"question": {
                "required": False,
                "textQuestion": {"paragraph": True}
            }}
        },
        "location": {"index": pos}
    }})
    pos += 1

    # Confirmación — radio requerido
    add_reqs.append({"createItem": {
        "item": {
            "title": (
                "Mi pedido está listo, he seleccionado los productos "
                "y cantidades que quiero. Mi total a pagar me lo "
                "enviarán por Whatsapp."
            ),
            "questionItem": {"question": {
                "required": True,
                "choiceQuestion": {
                    "type":    "RADIO",
                    "options": [{"value": "Confirmo mi pedido"}]
                }
            }}
        },
        "location": {"index": pos}
    }})
    pos += 1

    # ── Paso 6: ejecutar en bloques ───────────────────────────────────────────
    BLOQUE = 50
    for i in range(0, len(add_reqs), BLOQUE):
        svc.forms().batchUpdate(
            formId=form_id,
            body={"requests": add_reqs[i:i+BLOQUE]}
        ).execute()
        time.sleep(0.5)

    _save_form_id(form_id)
    return {
        "form_url":   f"https://docs.google.com/forms/d/{form_id}/viewform",
        "edit_url":   f"https://docs.google.com/forms/d/{form_id}/edit",
        "eliminados": len(del_indices),
        "agregados":  len(add_reqs),
    }


# ── Alias de compatibilidad ───────────────────────────────────────────────────
def crear_formulario(titulo: str = "Pedidos Veggi Hogares",
                     productos: list = None) -> dict:
    form_id = get_form_id()
    if not form_id:
        raise ValueError(
            "No hay formulario configurado. "
            "Ingresá el ID del formulario primero.")
    return actualizar_formulario(form_id, titulo=titulo, productos=productos)


# ── Sincronizar (alias de actualizar) ────────────────────────────────────────
def sincronizar_formulario(form_id: str) -> dict:
    return actualizar_formulario(form_id)


# ── Leer respuestas via Forms API ─────────────────────────────────────────────
def leer_respuestas_api(form_id: str) -> tuple[dict, list]:
    svc  = _forms_svc()
    form = svc.forms().get(formId=form_id).execute()
    q_map = {}
    for item in form.get("items", []):
        if "questionItem" in item:
            q_id = item["questionItem"]["question"].get("questionId")
            if q_id:
                q_map[q_id] = item.get("title", "")
    all_resp, page_token = [], None
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
