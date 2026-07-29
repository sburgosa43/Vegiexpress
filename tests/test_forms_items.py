"""
Lectura y actualización quirúrgica de los Google Forms de pedidos.

En el formulario cada producto es una PREGUNTA y el dato vive en su título
("Ajo (Red) - Q.6.50"); el desplegable interno es la cantidad, no una lista de
productos.

Lo que se protege acá:
  · que la lectura NO pierda productos en silencio (era la causa del bug),
  · que lo ambiguo se reporte en vez de adivinarse,
  · que un cambio de precio sea un updateItem y no un borrar+crear, para no
    dejar huérfanas las respuestas históricas (se mapean por questionId).

    python tests/test_forms_items.py
"""
import sys
import types

from _stubs import Reporte, instalar_streamlit, raiz_repo

raiz_repo()
instalar_streamlit()

import forms_helper as fh                                  # noqa: E402

r = Reporte()

# ── Dobles del servicio de Forms ─────────────────────────────────────────────
ENVIADO = []          # requests que se mandaron a batchUpdate


def _svc_con(items, fallar_lectura=False):
    class _Forms:
        def get(self, formId=None):
            class _Ex:
                def execute(_s):
                    if fallar_lectura:
                        raise RuntimeError("403 sin permiso")
                    return {"items": items}
            return _Ex()

        def batchUpdate(self, formId=None, body=None):
            class _Ex:
                def execute(_s):
                    ENVIADO.extend(body.get("requests", []))
                    return {}
            return _Ex()

    return types.SimpleNamespace(forms=lambda: _Forms())


def _q(item_id, titulo):
    return {"itemId": item_id, "title": titulo,
            "questionItem": {"question": {"questionId": "q" + item_id}}}


ITEMS = [
    {"itemId": "pb1", "title": "Vegetales", "pageBreakItem": {}},
    _q("i1", "Ajo (Red) - Q.6.50"),
    _q("i2", "Cilantro - Q.3.00"),               # sin unidad: antes se perdía
    _q("i3", "Tomate Cherry (Caja 250g) - Q.8.75"),
    _q("i4", "Aguacate (Und)"),                   # sin precio -> raro
    _q("i5", "Productos Extra"),                  # estructura, se ignora
    {"itemId": "pb2", "title": "Para finalizar", "pageBreakItem": {}},
    _q("i6", "Mi pedido está listo, he seleccionado los productos"),
]

print("=== 1. El patrón lee los formatos reales ===")
CASOS = [
    ("Ajo (Red) - Q.6.50",                 "Ajo",             "Red",       6.50),
    ("Cilantro - Q.3.00",                  "Cilantro",        "",          3.00),
    ("Tomate Cherry (Caja 250g) - Q.8.75", "Tomate Cherry",   "Caja 250g", 8.75),
    ("Papa (Lb) – Q.5,50",                 "Papa",            "Lb",        5.50),
    ("Zanahoria (Lb) - Q 4.25",            "Zanahoria",       "Lb",        4.25),
    ("Mango (Und) - Q6",                   "Mango",           "Und",       6.00),
    ("Brocoli - Rizado (Lb) - Q.9.00",     "Brocoli - Rizado", "Lb",       9.00),
]
for titulo, nom, und, pre in CASOS:
    d = fh.parsear_titulo(titulo)
    r.check(d is not None and d["nombre"] == nom and d["unidad"] == und
            and abs(d["precio"] - pre) < 1e-9,
            f"{titulo!r} -> {nom!r} / {und!r} / {pre}")

print("\n=== 2. Lo ambiguo o ilegible NO se adivina ===")
for titulo in ["Aguacate (Und)", "Producto sin nada", "Papa (Lb) - Q.",
               "Melon (Und) - Q.1,5,7"]:
    r.check(fh.parsear_titulo(titulo) is None,
            f"{titulo!r} -> None (va a revisión manual)")
r.check(fh._precio_desde_texto("1,250.00") == 1250.0,
        "1,250.00 -> 1250.00 (coma de miles con decimales)")
r.check(fh._precio_desde_texto("6,50") == 6.50,
        "6,50 -> 6.50 (coma decimal)")
r.check(fh._precio_desde_texto("1,250") is None,
        "1,250 es ambiguo (¿1250 o 1.25?) -> None, no se adivina")

print("\n=== 3. Ida y vuelta título ↔ datos ===")
for nom, und, pre in [("Ajo", "Red", 6.5), ("Cilantro", "", 3.0),
                      ("Brocoli - Rizado", "Lb", 9.0)]:
    t = fh.titulo_de(nom, und, pre)
    d = fh.parsear_titulo(t)
    r.check(d and d["nombre"] == nom and d["unidad"] == und
            and abs(d["precio"] - pre) < 1e-9,
            f"{t!r} vuelve a leerse igual")

print("\n=== 4. leer_items_form separa ok / raro y no pierde nada ===")
fh._forms_svc = lambda: _svc_con(ITEMS)
datos = fh.leer_items_form("FID")
nombres = [i["nombre"] for i in datos["ok"]]
r.check(nombres == ["Ajo", "Cilantro", "Tomate Cherry"], f"ok = {nombres}")
r.check("Cilantro" in nombres,
        "el producto SIN unidad se lee (antes se perdía en silencio)")
r.check([i["titulo"] for i in datos["raro"]] == ["Aguacate (Und)"],
        "el ilegible va a 'raro', no se descarta")
r.check(all(i["item_id"] for i in datos["ok"]),
        "cada producto conserva su item_id (necesario para actualizar)")
r.check(datos["ok"][0]["index"] == 1,
        f"guarda el índice real en el formulario ({datos['ok'][0]['index']})")
_titulos = [i["titulo"] for i in datos["ok"] + datos["raro"]]
r.check("Productos Extra" not in _titulos
        and not any(t.lower().startswith("mi pedido") for t in _titulos),
        "las preguntas de estructura no se confunden con productos")

print("\n=== 5. Un fallo de lectura NO se traga ===")
fh._forms_svc = lambda: _svc_con(ITEMS, fallar_lectura=True)
try:
    fh.leer_items_form("FID")
    r.check(False, "debía propagar el error")
except RuntimeError:
    r.check(True, "propaga el error en vez de devolver una lista vacía o todo")
fh._forms_svc = lambda: _svc_con(ITEMS)

print("\n=== 6. Cambiar un precio es updateItem, NO borrar+crear ===")
ENVIADO.clear()
res = fh.aplicar_cambios_form(
    "FID",
    actualizar=[{"item_id": "i1", "index": 1, "nombre": "Ajo",
                 "unidad": "Red", "precio": 7.25}])
tipos = [k for req in ENVIADO for k in req]
r.check(tipos == ["updateItem"], f"solo updateItem, sin delete/create: {tipos}")
_u = ENVIADO[0]["updateItem"]
r.check(_u["item"]["itemId"] == "i1", "apunta al item_id existente")
r.check(_u["item"]["title"] == "Ajo (Red) - Q.7.25",
        f"título nuevo: {_u['item']['title']!r}")
r.check(_u["updateMask"] == "title", "updateMask acotado al título")
r.check(res["actualizados"] == 1 and res["agregados"] == 0
        and res["quitados"] == 0, f"resumen: {res}")

print("\n=== 7. Agregar y quitar ===")
ENVIADO.clear()
fh.aplicar_cambios_form(
    "FID",
    agregar=[{"nombre": "Fresa", "unidad": "Lb", "precio": 15.0}],
    quitar=[{"item_id": "i2", "index": 2}, {"item_id": "i3", "index": 3}])
tipos = [k for req in ENVIADO for k in req]
r.check(tipos.count("deleteItem") == 2 and tipos.count("createItem") == 1,
        f"2 borrados + 1 alta: {tipos}")
_idx_del = [req["deleteItem"]["location"]["index"]
            for req in ENVIADO if "deleteItem" in req]
r.check(_idx_del == sorted(_idx_del, reverse=True),
        f"los borrados van de mayor a menor índice: {_idx_del}")
_c = [req["createItem"] for req in ENVIADO if "createItem" in req][0]
r.check(_c["item"]["title"] == "Fresa (Lb) - Q.15.00",
        f"alta con el formato correcto: {_c['item']['title']!r}")
r.check("choiceQuestion" in _c["item"]["questionItem"]["question"],
        "Hogares: la cantidad es desplegable")

ENVIADO.clear()
fh.aplicar_cambios_form("FID", agregar=[{"nombre": "Fresa", "unidad": "Lb",
                                         "precio": 15.0}],
                        tipo_cantidad="numerico")
_c = [req["createItem"] for req in ENVIADO if "createItem" in req][0]
r.check("textQuestion" in _c["item"]["questionItem"]["question"],
        "Hoteles: la cantidad es campo numérico")

print("\n=== 8. Sin cambios no se manda nada ===")
ENVIADO.clear()
res = fh.aplicar_cambios_form("FID")
r.check(ENVIADO == [], "ningún request si no hay cambios")
r.check(res["requests"] == 0, f"resumen coherente: {res['requests']}")

r.salir()
