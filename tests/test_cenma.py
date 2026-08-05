"""
Scraper de CENMA + hoja «Precios Cenma».

La API vieja del marketplace devuelve 404: el sitio se reconstruyó. Peor que
el 404 fue que `except Exception: break` lo tragaba, así que un endpoint caído
se veía igual que un catálogo vacío. De ahí el orden de lo que se prueba acá:

  - un fallo LEVANTA en vez de devolver una lista vacía;
  - el catálogo se normaliza a las columnas de la hoja;
  - las categorías salen de los datos, no de una constante;
  - el reemplazo por fecha borra SOLO las filas de esa fecha, y se planta si
    no están contiguas en vez de arrasar con un bloque ajeno.

Sin red: requests y gsheets están doblados.

    python tests/test_cenma.py
"""
import sys
import types

from _stubs import Reporte, instalar_streamlit, raiz_repo

raiz_repo()
instalar_streamlit()

# ── Doble de requests ────────────────────────────────────────────────────────
RESP = {"ok": True, "productos": [
    {"categoria": "Verduras", "nombre": "Tomate Libras", "precio": 6.5,
     "costo": 5.2, "sku": "101", "descripcion": "Libra", "es_mayoreo": False},
    {"categoria": "Frutas", "nombre": "Banano Libras", "precio": 3.25,
     "costo": 2.8, "sku": "102", "descripcion": "", "es_mayoreo": True},
    {"categoria": "Cafe", "nombre": "Café Molido", "precio": 40.0,
     "costo": None, "sku": "", "descripcion": None, "es_mayoreo": False},
]}
ESTADO = {"json": RESP, "http": 200, "raise": None}


class _Resp:
    status_code = 200

    def raise_for_status(self):
        if ESTADO["http"] >= 400:
            raise RuntimeError(f"{ESTADO['http']} Client Error")

    def json(self):
        return ESTADO["json"]


req = types.ModuleType("requests")
req.Session = lambda: types.SimpleNamespace(headers={}, get=lambda *a, **k: _Resp())


def _get(*a, **k):
    if ESTADO["raise"]:
        raise ESTADO["raise"]
    return _Resp()


req.get = _get
req.post = _get
req.RequestException = RuntimeError
sys.modules["requests"] = req

bs4 = types.ModuleType("bs4")
bs4.BeautifulSoup = lambda *a, **k: None
sys.modules["bs4"] = bs4

# ── Doble del Sheet ──────────────────────────────────────────────────────────
HOJA = {"filas": [], "creada": False, "borrados": []}

gs = types.ModuleType("gsheets")


def _ensure_ws(nombre, headers, rows=None):
    HOJA["creada"] = True
    return True


def _get_all_rows(nombre):
    return [list(r) for r in HOJA["filas"]]        # SIN encabezado


def _append_rows(nombre, rows):
    HOJA["filas"].extend([list(r) for r in rows])


def _delete_rows_range(nombre, desde, hasta):
    HOJA["borrados"].append((desde, hasta))
    del HOJA["filas"][desde - 2:hasta - 1]         # fila 2 == índice 0
    return hasta - desde + 1


gs.ensure_ws = _ensure_ws
gs.get_all_rows = _get_all_rows
gs.append_rows = _append_rows
gs.delete_rows_range = _delete_rows_range
sys.modules["gsheets"] = gs

from modulo_scraper import (_cenma_descargar, _cenma_categorias,   # noqa: E402
                            _cenma_guardar, COLS_CENMA)

r = Reporte()
HOY, AYER = "2026-08-05", "2026-08-04"

print("=== 1. Normalización a las columnas de la hoja ===")
p = _cenma_descargar(HOY)
r.check(len(p) == 3, f"tres productos: {len(p)}")
r.check(list(p[0]) == COLS_CENMA, f"columnas: {list(p[0])}")
r.check(p[0]["Fecha"] == HOY, "la fecha viaja en cada fila (es el historial)")
r.check(p[0]["Precio"] == 6.5 and p[0]["Costo"] == 5.2,
        "precio y costo se guardan como números")
r.check(p[1]["Mayoreo"] == "Sí" and p[0]["Mayoreo"] == "No",
        "es_mayoreo se traduce a Sí/No")
r.check(p[2]["Costo"] == 0.0 and p[2]["Descripción"] == "",
        "los nulos de la API quedan en 0 / vacío, no en None")
r.check(all(isinstance(x[c], (str, int, float))
            for x in p for c in COLS_CENMA),
        "todo es serializable a una celda del Sheet")

print("\n=== 2. Un fallo LEVANTA; no devuelve lista vacía ===")
# Era el bug de fondo: `except Exception: break` hacía que un 404 se viera
# igual que un catálogo sin productos.
for etiqueta, cambio in (
        ("HTTP 404",          {"http": 404}),
        ("ok=False",          {"json": {"ok": False}}),
        ("sin productos",     {"json": {"ok": True, "productos": []}}),
        ("conexión caída",    {"raise": RuntimeError("timeout")})):
    ESTADO.update({"json": RESP, "http": 200, "raise": None})
    ESTADO.update(cambio)
    try:
        _cenma_descargar(HOY)
        r.check(False, f"{etiqueta}: debió levantar y no levantó")
    except Exception as e:
        r.check(True, f"{etiqueta}: levanta {type(e).__name__}")
ESTADO.update({"json": RESP, "http": 200, "raise": None})

print("\n=== 3. Las categorías salen de los DATOS ===")
# El sitio ya renombró las suyas (Verdura -> Verduras) y agregó Cafe. Con una
# lista fija, una categoría nueva quedaría invisible.
r.check(_cenma_categorias(p) == ["Cafe", "Frutas", "Verduras"],
        f"categorías detectadas: {_cenma_categorias(p)}")
r.check("Cafe" in _cenma_categorias(p),
        "incluye una que la constante vieja no tenía")
r.check(_cenma_categorias([]) == [], "sin productos no inventa categorías")

print("\n=== 4. Primera captura: crea la hoja y escribe ===")
res = _cenma_guardar(p, HOY)
r.check(HOJA["creada"], "se aseguró la hoja «Precios Cenma»")
r.check(res == {"escritas": 3, "reemplazadas": 0}, f"resumen: {res}")
r.check(len(HOJA["filas"]) == 3, f"filas en la hoja: {len(HOJA['filas'])}")
r.check(HOJA["filas"][0][0] == HOY, "la fecha va en la columna A")

print("\n=== 5. Capturar de nuevo el MISMO día reemplaza, no duplica ===")
res2 = _cenma_guardar(p, HOY)
r.check(res2["reemplazadas"] == 3, f"reemplazó 3: {res2}")
r.check(len(HOJA["filas"]) == 3,
        f"sigue habiendo 3 filas, no 6: {len(HOJA['filas'])}")
r.check(HOJA["borrados"][-1] == (2, 4), f"borró el rango 2-4: {HOJA['borrados'][-1]}")

print("\n=== 6. Otro día se ACUMULA: es historial ===")
HOJA["filas"].clear(); HOJA["borrados"].clear()
_cenma_guardar([{**x, "Fecha": AYER} for x in p], AYER)
_cenma_guardar(p, HOY)
r.check(len(HOJA["filas"]) == 6, f"6 filas: {len(HOJA['filas'])}")
r.check(HOJA["borrados"] == [], "no se borró nada del día anterior")
_fechas = [f[0] for f in HOJA["filas"]]
r.check(_fechas == [AYER] * 3 + [HOY] * 3, f"conviven las dos fechas: {_fechas}")

print("\n=== 7. Recapturar hoy NO toca las filas de ayer ===")
res3 = _cenma_guardar(p, HOY)
r.check(res3["reemplazadas"] == 3, "reemplaza solo las de hoy")
r.check(len(HOJA["filas"]) == 6, f"siguen 6 filas: {len(HOJA['filas'])}")
r.check([f[0] for f in HOJA["filas"]][:3] == [AYER] * 3,
        "las de ayer quedan intactas")

print("\n=== 8. Filas de una fecha NO contiguas: se planta ===")
# Si alguien editó la hoja a mano y las filas de una fecha quedaron partidas,
# borrar de min a max se llevaría puesto un bloque de otra fecha.
HOJA["filas"].clear(); HOJA["borrados"].clear()
HOJA["filas"].extend([[HOY, "Verduras", "A", "", 1, 1, "1", "No"],
                      [AYER, "Verduras", "B", "", 1, 1, "2", "No"],
                      [HOY, "Verduras", "C", "", 1, 1, "3", "No"]])
try:
    _cenma_guardar(p, HOY)
    r.check(False, "debió negarse a borrar un rango que incluye otra fecha")
except RuntimeError as e:
    r.check("no están juntas" in str(e), f"corta con un error claro: {e}")
r.check(HOJA["borrados"] == [], "y NO borró nada")
r.check(len(HOJA["filas"]) == 3, "la hoja quedó como estaba")

r.salir()
