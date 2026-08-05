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
HOJA = {"filas": [], "creada": False, "borrados": [],
        "cabecera": [], "updates": []}

gs = types.ModuleType("gsheets")


def _ensure_ws(nombre, headers, rows=None):
    HOJA["creada"] = True
    if not HOJA["cabecera"]:
        HOJA["cabecera"] = list(headers)
    return True


def _get_all_rows(nombre):
    return [list(r) for r in HOJA["filas"]]        # SIN encabezado


def _append_rows(nombre, rows):
    HOJA["filas"].extend([list(r) for r in rows])


def _delete_rows_range(nombre, desde, hasta):
    HOJA["borrados"].append((desde, hasta))
    del HOJA["filas"][desde - 2:hasta - 1]         # fila 2 == índice 0
    return hasta - desde + 1


class _Hoja:
    """Doble del worksheet, solo lo que usa la migración."""

    def row_values(self, n):
        return list(HOJA["cabecera"])

    def update(self, rango, datos, value_input_option=None):
        HOJA["cabecera"] = list(datos[0])
        HOJA["filas"] = [list(f) for f in datos[1:]]
        HOJA["updates"].append(rango)


gs.ensure_ws = _ensure_ws
gs.get_all_rows = _get_all_rows
gs.append_rows = _append_rows
gs.delete_rows_range = _delete_rows_range
gs.ws = lambda nombre: _Hoja()
sys.modules["gsheets"] = gs

from modulo_scraper import (_cenma_descargar, _cenma_categorias,   # noqa: E402
                            _cenma_guardar, COLS_CENMA,
                            costo_sin_impuestos, sin_impuestos,
                            _derivar_cenma,
                            margen_mercado_pct, _cenma_migrar_hoja)
from config import base_sin_iva, ISR_FACTOR                       # noqa: E402

_COLS_CENMA_V1 = ["Fecha", "Categoría", "Producto", "Descripción",
                  "Precio", "Costo", "SKU", "Mayoreo"]

r = Reporte()
HOY, AYER = "2026-08-05", "2026-08-04"

print("=== 1. Normalización a las columnas de la hoja ===")
p = _cenma_descargar(HOY)
r.check(len(p) == 3, f"tres productos: {len(p)}")
r.check(list(p[0]) == COLS_CENMA, f"columnas: {list(p[0])}")
r.check(p[0]["Fecha"] == HOY, "la fecha viaja en cada fila (es el historial)")
r.check(p[0]["Precio"] == 6.5 and p[0]["Costo Bruto"] == 5.2,
        "precio y costo bruto se guardan como números")
r.check(p[1]["Mayoreo"] == "Sí" and p[0]["Mayoreo"] == "No",
        "es_mayoreo se traduce a Sí/No")
r.check(p[2]["Costo Bruto"] == 0.0 and p[2]["Descripción"] == "",
        "los nulos de la API quedan en 0 / vacío, no en None")
r.check(all(isinstance(x[c], (str, int, float))
            for x in p for c in COLS_CENMA),
        "todo es serializable a una celda del Sheet")

print("\n=== 1b. Costo sin impuestos = costo / 1.12 x 0.95 ===")
r.check(abs(p[0]["Costo sin Impuestos"]
            - round(base_sin_iva(5.2) * ISR_FACTOR, 4)) < 1e-9,
        f"5.20 bruto -> {p[0]['Costo sin Impuestos']} sin impuestos")
r.check(p[0]["Costo sin Impuestos"] < p[0]["Costo Bruto"],
        "siempre queda por debajo del bruto")
r.check(abs(costo_sin_impuestos(112.0) - 100.0 * 0.95) < 1e-6,
        f"Q112 (que traen Q12 de IVA) -> Q{costo_sin_impuestos(112.0)}")
r.check(costo_sin_impuestos(0) == 0.0 and costo_sin_impuestos(None) == 0.0,
        "sin costo no inventa un neto")
r.check(p[2]["Costo sin Impuestos"] == 0.0,
        "un producto sin costo queda en 0, no en negativo ni None")
# Las tasas salen de config: si cambian, esto cambia solo. Se compara contra
# el valor YA redondeado, porque la función devuelve 4 decimales.
r.check(costo_sin_impuestos(100) == round((100 / 1.12) * ISR_FACTOR, 4),
        f"usa base_sin_iva e ISR_FACTOR de config: {costo_sin_impuestos(100)}")
r.check(costo_sin_impuestos(100) == round(base_sin_iva(100) * ISR_FACTOR, 4),
        "y coincide con base_sin_iva de config, no con un 1.12 a mano")

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
HOJA["cabecera"] = list(COLS_CENMA)
def _fila(fecha, nom, sku):
    d = {"Fecha": fecha, "Categoría": "Verduras", "Producto": nom,
         "Descripción": "", "Precio": 1, "Costo Bruto": 1,
         "SKU": sku, "Mayoreo": "No"}
    return [_derivar_cenma(dict(d)).get(c, "") for c in COLS_CENMA]

HOJA["filas"].extend([_fila(HOY, "A", "1"), _fila(AYER, "B", "2"),
                      _fila(HOY, "C", "3")])
try:
    _cenma_guardar(p, HOY)
    r.check(False, "debió negarse a borrar un rango que incluye otra fecha")
except RuntimeError as e:
    r.check("no están juntas" in str(e), f"corta con un error claro: {e}")
r.check(HOJA["borrados"] == [], "y NO borró nada")
r.check(len(HOJA["filas"]) == 3, "la hoja quedó como estaba")

print("\n=== 9. Migración del layout viejo ===")
# «Costo sin Impuestos» se insertó DESPUÉS de «Costo Bruto», no al final. En una
# hoja ya escrita eso correría SKU y Mayoreo un lugar en cada fila y el
# historial quedaría corrupto sin que se note.
HOJA["filas"].clear(); HOJA["borrados"].clear(); HOJA["updates"].clear()
HOJA["cabecera"] = list(_COLS_CENMA_V1)
HOJA["filas"].extend([
    [AYER, "Verduras", "Tomate", "Libra", 6.5, 5.2, "101", "No"],
    [AYER, "Frutas",   "Banano", "",     3.25, 2.8, "102", "Sí"],
])
n = _cenma_migrar_hoja()
r.check(n == 2, f"migró las 2 filas existentes: {n}")
r.check(HOJA["cabecera"] == COLS_CENMA, f"cabecera nueva: {HOJA['cabecera']}")
# Los índices salen del NOMBRE, no escritos a mano: la próxima columna que se
# agregue en el medio no debe romper ni la prueba ni, sobre todo, la migración.
IX = {c: COLS_CENMA.index(c) for c in COLS_CENMA}
f0 = HOJA["filas"][0]
r.check(len(f0) == len(COLS_CENMA),
        f"cada fila pasa a {len(COLS_CENMA)} columnas: {len(f0)}")
r.check(f0[IX["Costo Bruto"]] == 5.2,
        "el «Costo» viejo se renombra a «Costo Bruto»")
r.check(abs(f0[IX["Costo sin Impuestos"]] - sin_impuestos(5.2)) < 1e-9,
        f"costo neto del costo que ya estaba: {f0[IX['Costo sin Impuestos']]}")
r.check(abs(f0[IX["Precio sin Impuestos"]] - sin_impuestos(6.5)) < 1e-9,
        f"precio neto del precio que ya estaba: {f0[IX['Precio sin Impuestos']]}")
r.check(f0[IX["Margen CENMA %"]] == margen_mercado_pct(6.5, 5.2),
        f"margen recalculado: {f0[IX['Margen CENMA %']]}%")
r.check(f0[IX["SKU"]] == "101" and f0[IX["Mayoreo"]] == "No",
        "SKU y Mayoreo NO se corrieron: siguen en su lugar")
r.check(HOJA["filas"][1][IX["SKU"]] == "102"
        and HOJA["filas"][1][IX["Mayoreo"]] == "Sí",
        "y en la segunda fila tampoco")

print("\n=== 9b. Migrar es idempotente y no adivina ===")
r.check(_cenma_migrar_hoja() == 0, "con la cabecera al día no hace nada")
HOJA["cabecera"] = ["Otra", "Cosa"]
try:
    _cenma_migrar_hoja()
    r.check(False, "debió cortar ante una cabecera desconocida")
except RuntimeError as e:
    r.check("no reconozco" in str(e), f"corta con un error claro: {str(e)[:60]}...")
r.check(HOJA["cabecera"] == ["Otra", "Cosa"],
        "y no reescribe una hoja que no entiende")

r.salir()
