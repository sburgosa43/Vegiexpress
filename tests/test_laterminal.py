"""
Scraper de Mercado La Terminal (Ecwid) + hoja «Precios La Terminal».

El sitio NO trae los productos en el HTML: los dibuja Ecwid con JS. Pero el JS
se los pide a la API pública de Ecwid, que responde por HTTP normal — así que
no hace falta navegador. 306 productos en ~8 s con un pico de 7 MB.

Lo que se protege acá:
  - el token público se LEE del sitio, no queda fijo: Ecwid puede rotarlo;
  - se prueba token por token, porque la página trae varios y no todos sirven;
  - se usa defaultDisplayedPrice y NO `price`, que es el base y no coincide
    con lo que ve el cliente;
  - los booleanos van en minúscula ("true"), o la API responde 400;
  - un fallo LEVANTA en vez de devolver una lista vacía.

Sin red: requests y gsheets están doblados.

    python tests/test_laterminal.py
"""
import sys
import types

from _stubs import Reporte, instalar_streamlit, raiz_repo

raiz_repo()
instalar_streamlit()

# El HTML de la tienda trae varios tokens; solo el segundo sirve para el
# catálogo, para que la prueba obligue a recorrerlos y no a tomar el primero.
HTML = ('<script>var a="public_AAAAAAAAAAAAAAAAAAAAAAAAAAAA";</script>'
        '<script>var b="public_BBBBBBBBBBBBBBBBBBBBBBBBBBBB";</script>')
TOKEN_OK = "public_BBBBBBBBBBBBBBBBBBBBBBBBBBBB"

CATS = {"items": [{"id": 1, "name": "verduras"}, {"id": 2, "name": "frutas"}]}
PRODS = [
    {"name": "Tomate", "subtitle": "Libra", "price": 9,
     "defaultDisplayedPrice": 12.38, "sku": "T1", "inStock": True,
     "defaultCategoryId": 1, "categoryIds": [1]},
    {"name": "Banano", "subtitle": "Unidad", "price": 3.5,
     "defaultDisplayedPrice": 4.81, "sku": "B1", "inStock": False,
     "defaultCategoryId": 2, "categoryIds": [2]},
    {"name": "Huérfano", "subtitle": "", "price": 1,
     "defaultDisplayedPrice": 2.0, "sku": "", "inStock": True,
     "defaultCategoryId": 99, "categoryIds": []},
]
LLAMADAS = []
ESTADO = {"falla": None}


class _R:
    def __init__(self, code=200, js=None, text=""):
        self.status_code, self._js, self.text = code, js, text
        self.ok = code < 400
        self.content = b"x" * 10

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"{self.status_code} Client Error")

    def json(self):
        return self._js


def _get(url, headers=None, params=None, timeout=None):
    LLAMADAS.append({"url": url, "params": dict(params or {}),
                     "auth": (headers or {}).get("Authorization", "")})
    if ESTADO["falla"]:
        raise ESTADO["falla"]
    if "mercadolaterminalonline" in url:
        return _R(200, text=HTML)
    tok = (headers or {}).get("Authorization", "").replace("Bearer ", "")
    if tok != TOKEN_OK:
        return _R(403)
    # La API rechaza booleanos con mayúscula. isinstance y no `v in (True,
    # False)`: en Python 0 == False, así que eso rechazaba offset=0.
    for k, v in (params or {}).items():
        if isinstance(v, bool):
            return _R(400)
    if url.endswith("/categories"):
        return _R(200, js=CATS)
    off = int((params or {}).get("offset", 0))
    return _R(200, js={"items": PRODS[off:off + 100], "total": len(PRODS),
                       "count": len(PRODS)})


req = types.ModuleType("requests")
req.get = _get
req.post = _get
req.Session = lambda: types.SimpleNamespace(headers={}, get=_get)
req.RequestException = RuntimeError
sys.modules["requests"] = req

bs4 = types.ModuleType("bs4")
bs4.BeautifulSoup = lambda *a, **k: None
sys.modules["bs4"] = bs4

HOJA = {"filas": [], "cabecera": [], "creada": False, "borrados": []}
gs = types.ModuleType("gsheets")
gs.ensure_ws = lambda n, h, r=None: (HOJA.__setitem__("creada", True),
                                     HOJA["cabecera"] or
                                     HOJA.__setitem__("cabecera", list(h)))
gs.get_all_rows = lambda n: [list(f) for f in HOJA["filas"]]
gs.append_rows = lambda n, rows: HOJA["filas"].extend([list(r) for r in rows])


def _del(n, desde, hasta):
    HOJA["borrados"].append((desde, hasta))
    del HOJA["filas"][desde - 2:hasta - 1]
    return hasta - desde + 1


gs.delete_rows_range = _del
gs.ws = lambda n: types.SimpleNamespace(
    row_values=lambda i: list(HOJA["cabecera"]),
    update=lambda rng, datos, value_input_option=None: (
        HOJA.__setitem__("cabecera", list(datos[0])),
        HOJA.__setitem__("filas", [list(f) for f in datos[1:]])))
sys.modules["gsheets"] = gs

from modulo_scraper import (_laterminal_descargar, _lt_categorias,  # noqa: E402
                            _lt_token, _lt_tokens_del_sitio,
                            _guardar_precios, COLS_LATERMINAL,
                            sin_impuestos)

r = Reporte()
HOY, AYER = "2026-08-05", "2026-08-04"

print("=== 1. El token se LEE del sitio, no está fijo ===")
toks = _lt_tokens_del_sitio()
r.check(toks == ["public_AAAAAAAAAAAAAAAAAAAAAAAAAAAA", TOKEN_OK],
        f"encuentra los dos, en orden y sin repetir: {len(toks)}")
r.check(_lt_token() == TOKEN_OK,
        "prueba uno por uno y se queda con el que la API acepta")
r.check(any("mercadolaterminalonline" in c["url"] for c in LLAMADAS),
        "para eso pidió el HTML de la tienda")

print("\n=== 2. Descarga y normalización ===")
LLAMADAS.clear()
p = _laterminal_descargar(HOY)
r.check(len(p) == 3, f"tres productos: {len(p)}")
r.check(list(p[0]) == COLS_LATERMINAL, f"columnas: {list(p[0])}")
r.check(p[0]["Precio"] == 12.38,
        f"usa defaultDisplayedPrice (12.38), NO price (9): {p[0]['Precio']}")
r.check(p[1]["Precio"] == 4.81, "y en el segundo también")
r.check(p[0]["Unidad"] == "Libra", "subtitle es la unidad")
r.check(p[0]["Categoría"] == "verduras" and p[1]["Categoría"] == "frutas",
        "categoryId se traduce a nombre")
r.check(p[2]["Categoría"] == "Sin categoría",
        "una categoría desconocida no rompe ni deja el id crudo")
r.check(p[1]["Disponible"] == "No" and p[0]["Disponible"] == "Sí",
        "inStock se traduce a Sí/No")
r.check(abs(p[0]["Precio sin Impuestos"] - sin_impuestos(12.38)) < 1e-9,
        f"neto de IVA e ISR: {p[0]['Precio sin Impuestos']}")
r.check(all(isinstance(x[c], (str, int, float))
            for x in p for c in COLS_LATERMINAL),
        "todo serializable a una celda del Sheet")

print("\n=== 3. Los booleanos van en minúscula (si no, 400) ===")
_pp = [c["params"] for c in LLAMADAS
       if "products" in c["url"] and "offset" in c["params"]]
r.check(_pp and _pp[0].get("enabled") == "true",
        f"enabled se manda como 'true', no True: {_pp[0].get('enabled')!r}")
r.check(not any(isinstance(v, bool) for pr in _pp for v in pr.values()),
        "ningún parámetro viaja como booleano de Python")

print("\n=== 4. Un fallo LEVANTA ===")
for etiqueta, falla in (("conexión caída", RuntimeError("timeout")),):
    ESTADO["falla"] = falla
    try:
        _laterminal_descargar(HOY)
        r.check(False, f"{etiqueta}: debió levantar")
    except Exception as e:
        r.check(True, f"{etiqueta}: levanta {type(e).__name__}")
ESTADO["falla"] = None

print("\n=== 5. Sin costo: la hoja no lleva columnas de costo ni margen ===")
r.check(not any("Costo" in c or "Margen" in c for c in COLS_LATERMINAL),
        f"columnas: {COLS_LATERMINAL}")
r.check("Precio sin Impuestos" in COLS_LATERMINAL,
        "pero sí el neto, que es lo comparable entre mercados")

print("\n=== 6. Guardado con historial, igual que Cenma ===")
res = _guardar_precios("precios_laterminal", COLS_LATERMINAL, p, HOY)
r.check(HOJA["creada"], "se aseguró la hoja")
r.check(res == {"escritas": 3, "reemplazadas": 0}, f"resumen: {res}")
res2 = _guardar_precios("precios_laterminal", COLS_LATERMINAL, p, HOY)
r.check(res2["reemplazadas"] == 3 and len(HOJA["filas"]) == 3,
        f"recapturar el mismo día reemplaza: {len(HOJA['filas'])} filas")
_guardar_precios("precios_laterminal", COLS_LATERMINAL,
                 [{**x, "Fecha": AYER} for x in p], AYER)
r.check(len(HOJA["filas"]) == 6, f"otro día acumula: {len(HOJA['filas'])}")

print("\n=== 7. Categorías desde los datos ===")
r.check(_lt_categorias(p) == ["Sin categoría", "frutas", "verduras"],
        f"{_lt_categorias(p)}")

r.salir()
