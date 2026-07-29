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
_HOT_KEY = "HOT_FORM_ID"

def _key_canal(canal):
    return _HOT_KEY if canal == "hoteles" else _HOG_KEY


def get_form_id(canal: str = "hogares") -> str | None:
    _key = _key_canal(canal)
    try:
        from gsheets import get_all_rows
        for row in get_all_rows("gastosconfig"):
            if row and str(row[0]).strip().upper() == _key:
                v = str(row[1]).strip() if len(row) > 1 else ""
                return v or None
    except Exception:
        pass
    return None


def _save_form_id(form_id: str, canal: str = "hogares") -> None:
    _key = _key_canal(canal)
    try:
        from gsheets import ws as _ws, get_all_rows
        sheet = _ws("gastosconfig")
        for i, row in enumerate(get_all_rows("gastosconfig"), start=2):
            if row and str(row[0]).strip().upper() == _key:
                sheet.update(f"B{i}", [[form_id]])
                return
        sheet.append_rows([[_key, form_id, "", ""]])
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


def _productos_hoteles() -> list[dict]:
    """Productos para el formulario de Hoteles. Usa el precio del catálogo
    general (Listado Productos), que es el que manejan Hoteles/Río — no una
    lista de precios especial."""
    from excel_helper import leer_productos_con_fila

    prods_gen = leer_productos_con_fila(es_antigua=False)
    result = []
    for p in prods_gen:
        if not p.get("nombre") or not p.get("unidad"):
            continue
        # Precio base del catálogo general
        precio = float(p.get("precio") or 0)
        if precio <= 0:
            continue
        result.append({
            "nombre":   p["nombre"],
            "unidad":   p["unidad"],
            "segmento": p.get("segmento", "Otros"),
            "precio":   precio,
        })
    return sorted(result, key=lambda x: (x["segmento"], x["nombre"]))


# ── Lectura del formulario como fuente de verdad ─────────────────────────────
# En el formulario, CADA PRODUCTO ES UNA PREGUNTA y el dato vive en su título:
#     "{nombre} ({unidad}) - Q.{precio}"        ej: "Ajo (Red) - Q.6.50"
# El desplegable que hay dentro de cada pregunta es la CANTIDAD (1-6), no una
# lista de productos.
#
# El patrón es tolerante a propósito: la unidad es opcional (hay títulos como
# "Cilantro - Q.3.00"), acepta guion normal/medio/largo, y Q. / Q / Q espacio.
# Lo que no calza NO se fuerza ni se descarta: se devuelve aparte para que lo
# revise una persona.
import re as _re

_PAT_ITEM = _re.compile(
    r"^\s*(?P<nombre>.+?)"                       # nombre
    r"(?:\s*\((?P<unidad>[^()]*)\))?"            # (unidad) — opcional
    r"\s*[-–—]\s*"                     # - – —
    r"Q\s*\.?\s*(?P<precio>[\d.,]+)\s*$"         # Q.6.50 / Q 6,50 / Q6.50
)

# Formas de precio que se aceptan sin adivinar. Cualquier otra cosa va a
# "raro": preferimos avisar antes que interpretar mal un número de dinero.
_PRE_PUNTO = _re.compile(r"^\d+\.\d{1,2}$")           # 6.50   (el que escribe la app)
_PRE_MILES = _re.compile(r"^\d{1,3}(?:,\d{3})+\.\d{1,2}$")  # 1,250.00
_PRE_COMA  = _re.compile(r"^\d+,\d{1,2}$")            # 6,50   (coma decimal)
_PRE_ENTERO = _re.compile(r"^\d+$")                   # 6


def _precio_desde_texto(txt: str):
    """Precio como float, o None si el formato es ambiguo.

    No usa _sf a propósito: acá la coma es ambigua ("6,50" es 6.50 pero
    "1,250" es mil doscientos cincuenta) y en dinero preferimos devolver None
    y pedir revisión manual antes que elegir mal.
    """
    t = (txt or "").strip()
    if _PRE_PUNTO.match(t) or _PRE_ENTERO.match(t):
        return float(t)
    if _PRE_MILES.match(t):
        return float(t.replace(",", ""))
    if _PRE_COMA.match(t):
        return float(t.replace(",", "."))
    return None


def parsear_titulo(titulo: str):
    """{'nombre','unidad','precio'} del título de una pregunta, o None."""
    m = _PAT_ITEM.match(titulo or "")
    if not m:
        return None
    precio = _precio_desde_texto(m.group("precio"))
    if precio is None:
        return None
    return {"nombre": (m.group("nombre") or "").strip(),
            "unidad": (m.group("unidad") or "").strip(),
            "precio": precio}


def titulo_de(nombre: str, unidad: str, precio: float) -> str:
    """Título de la pregunta. Único lugar donde se arma el formato."""
    und = f" ({unidad.strip()})" if str(unidad or "").strip() else ""
    return f"{str(nombre).strip()}{und} - Q.{float(precio):.2f}"


def leer_items_form(form_id: str) -> dict:
    """Lee el formulario y devuelve sus productos.

    {"ok":   [{item_id, index, nombre, unidad, precio, titulo}, ...],
     "raro": [{item_id, index, titulo}, ...]}

    "raro" son las preguntas que parecen de producto pero cuyo título no se
    pudo interpretar. NO se descartan en silencio: la UI las muestra aparte.

    Lanza la excepción de la API si el formulario no se puede leer. El
    llamador NO debe convertir ese fallo en "seleccionar todo el catálogo",
    que era justamente lo que hacía perder la lista.
    """
    svc  = _forms_svc()
    form = svc.forms().get(formId=form_id).execute()

    # Títulos que son parte de la estructura, no productos.
    _ESTRUCTURA = ("productos extra", "para finalizar")
    _PREF_CONF  = ("mi pedido está listo", "mi pedido esta listo")

    ok, raro = [], []
    for idx, item in enumerate(form.get("items", [])):
        if "questionItem" not in item:
            continue                       # page breaks, texto, etc.
        titulo = item.get("title", "") or ""
        t = titulo.lower().strip()
        if t in _ESTRUCTURA or any(t.startswith(p) for p in _PREF_CONF):
            continue
        base = {"item_id": item.get("itemId", ""), "index": idx,
                "titulo": titulo}
        datos = parsear_titulo(titulo)
        if datos:
            ok.append({**base, **datos})
        else:
            raro.append(base)
    return {"ok": ok, "raro": raro}


# ── Actualización quirúrgica ─────────────────────────────────────────────────
def aplicar_cambios_form(form_id: str,
                         actualizar: list = None,
                         agregar:    list = None,
                         quitar:     list = None,
                         tipo_cantidad: str = "dropdown") -> dict:
    """Aplica solo los cambios pedidos, sin reconstruir el formulario.

    actualizar: [{"item_id", "index", "nombre", "unidad", "precio"}]
    agregar:    [{"nombre", "unidad", "precio"}]
    quitar:     [{"item_id", "index"}]

    Se hace en este orden porque los índices se desplazan: primero los
    updates (los índices siguen válidos), después los borrados de mayor a
    menor índice, y al final los agregados.

    Actualizar en el lugar preserva el questionId de cada pregunta. Eso
    importa más de lo que parece: las respuestas se mapean por questionId
    (ver leer_respuestas_api), así que borrar y recrear deja las respuestas
    históricas apuntando a preguntas que ya no existen.
    """
    import time
    svc = _forms_svc()
    actualizar = actualizar or []
    agregar    = agregar    or []
    quitar     = quitar     or []
    reqs = []

    # 1. Updates — solo el título, que es donde vive nombre/unidad/precio.
    for it in actualizar:
        reqs.append({"updateItem": {
            "item": {"itemId": it["item_id"],
                     "title": titulo_de(it["nombre"], it.get("unidad", ""),
                                        it["precio"])},
            "location":   {"index": it["index"]},
            "updateMask": "title",
        }})

    # 2. Borrados, de mayor a menor índice.
    for it in sorted(quitar, key=lambda x: x["index"], reverse=True):
        reqs.append({"deleteItem": {"location": {"index": it["index"]}}})

    # 3. Agregados al final (antes de nada más re-leemos el tamaño).
    if agregar:
        form = svc.forms().get(formId=form_id).execute()
        pos  = len(form.get("items", [])) - len(quitar)
        for p in agregar:
            if tipo_cantidad == "numerico":
                pregunta = {"required": False,
                            "textQuestion": {"paragraph": False}}
            else:
                pregunta = {"required": False,
                            "choiceQuestion": {
                                "type": "DROP_DOWN",
                                "options": [{"value": str(i)}
                                            for i in range(1, 7)]}}
            reqs.append({"createItem": {
                "item": {"title": titulo_de(p["nombre"], p.get("unidad", ""),
                                            p["precio"]),
                         "questionItem": {"question": pregunta}},
                "location": {"index": pos},
            }})
            pos += 1

    for i in range(0, len(reqs), 50):
        svc.forms().batchUpdate(
            formId=form_id, body={"requests": reqs[i:i + 50]}).execute()
        time.sleep(0.5)

    return {"actualizados": len(actualizar), "agregados": len(agregar),
            "quitados": len(quitar), "requests": len(reqs),
            "form_url": f"https://docs.google.com/forms/d/{form_id}/viewform"}


# ── Actualizar formulario (con secciones por segmento y dropdowns 1-6) ────────
def actualizar_formulario(form_id: str,
                          titulo:    str  = None,
                          productos: list = None,
                          tipo_cantidad: str = "dropdown") -> dict:
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
        "productos extra", "para finalizar",
    }
    # Prefijos de títulos a eliminar (coincidencia por comienzo, no exacta):
    # la pregunta de confirmación tiene un título largo que empieza así.
    _SKIP_PREFIXES = (
        "mi pedido está listo", "mi pedido esta listo",
    )

    def _es_confirmacion(titulo: str) -> bool:
        t = titulo.lower().strip()
        return (t in _SKIP_TITLES
                or any(t.startswith(pref) for pref in _SKIP_PREFIXES))

    del_indices = sorted([
        i for i, item in enumerate(items)
        if ("questionItem" in item and _pat.match(item.get("title", "")))
        or "textItem"      in item
        or "pageBreakItem" in item
        or _es_confirmacion(item.get("title", ""))
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
            if tipo_cantidad == "numerico":
                # Campo de texto corto con validación numérica: el cliente
                # escribe la cantidad que quiera (útil para hoteles).
                pregunta = {
                    "required": False,
                    "textQuestion": {"paragraph": False},
                }
            else:
                # Desplegable con opciones fijas (1-6) — Hogares
                pregunta = {
                    "required": False,
                    "choiceQuestion": {
                        "type":    "DROP_DOWN",
                        "options": OPTS_CANT,
                    }
                }
            add_reqs.append({"createItem": {
                "item": {
                    "title": nombre_p,
                    "questionItem": {"question": pregunta}
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
