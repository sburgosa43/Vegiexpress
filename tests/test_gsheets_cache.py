"""
Caché del handle de worksheet en gsheets.py.

ws() resolvía el worksheet contra la API en cada lectura. Se cachea el handle,
y lo delicado pasa a ser la invalidación: los worksheets guardan una referencia
al cliente de _gc(), así que limpiar solo _gc dejaría handles apuntando a un
cliente muerto.

    python tests/test_gsheets_cache.py
"""
import sys
import types

from _stubs import Reporte, instalar_streamlit, raiz_repo

raiz_repo()
instalar_streamlit(cache_resource_real=True)

# ── Doble de gspread que cuenta llamadas y permite forzar fallos ──────────────
CONT   = {"authorize": 0, "open": 0, "worksheet": 0, "get_all_values": 0}
FALLAR = {"worksheet": 0, "get_all_values": 0, "delete_rows": 0}


class _APIError(Exception):
    pass


class _WS:
    def __init__(self, titulo):
        self.titulo = titulo

    def get_all_values(self):
        CONT["get_all_values"] += 1
        if FALLAR["get_all_values"] > 0:
            FALLAR["get_all_values"] -= 1
            raise _APIError("fallo de lectura simulado")
        return [["h1", "h2"], ["a", "b"], ["c", "d"]]

    def delete_rows(self, row):
        if FALLAR["delete_rows"] > 0:
            FALLAR["delete_rows"] -= 1
            raise _APIError("fallo de borrado simulado")
        return True


class _WB:
    def worksheet(self, titulo):
        CONT["worksheet"] += 1
        if FALLAR["worksheet"] > 0:
            FALLAR["worksheet"] -= 1
            raise _APIError("fallo al resolver worksheet")
        return _WS(titulo)


class _Client:
    def open_by_key(self, key):
        CONT["open"] += 1
        return _WB()


def _authorize(creds):
    CONT["authorize"] += 1
    return _Client()


gspread = types.ModuleType("gspread")
gspread.exceptions = types.SimpleNamespace(APIError=_APIError)
gspread.authorize = _authorize
sys.modules["gspread"] = gspread

goa = types.ModuleType("google.oauth2.service_account")
goa.Credentials = types.SimpleNamespace(
    from_service_account_info=lambda info, scopes: object())
sys.modules["google"] = types.ModuleType("google")
sys.modules["google.oauth2"] = types.ModuleType("google.oauth2")
sys.modules["google.oauth2.service_account"] = goa

import time
time.sleep = lambda s: None          # sin esperas reales en los reintentos

import gsheets                                            # noqa: E402

r = Reporte()

print("=== 1. El handle se resuelve UNA vez para N lecturas ===")
for _ in range(5):
    gsheets.get_all_rows("pedidos")
r.check(CONT["worksheet"] == 1,
        f"5 lecturas -> worksheet() resuelto {CONT['worksheet']} vez(ces)")
r.check(CONT["get_all_values"] == 5, "las 5 lecturas de datos sí ocurrieron")

print("\n=== 2. Hojas distintas se cachean por separado ===")
antes = CONT["worksheet"]
gsheets.get_all_rows("clientes")
gsheets.get_all_rows("clientes")
r.check(CONT["worksheet"] == antes + 1, "otra hoja -> 1 resolución nueva, no 2")

print("\n=== 3. Un fallo invalida AMBOS niveles y re-resuelve ===")
CONT.update(worksheet=0, open=0)
FALLAR["get_all_values"] = 1
filas = gsheets.get_all_rows("pedidos")
r.check(filas == [["a", "b"], ["c", "d"]], "tras el retry devuelve los datos")
r.check(CONT["worksheet"] >= 1, "el worksheet se volvió a resolver")
r.check(CONT["open"] >= 1, "el spreadsheet también se re-abrió")

print("\n=== 4. delete_rows re-pide el handle tras invalidar ===")
gsheets.clear_ws_cache()
CONT.update(worksheet=0)
FALLAR["delete_rows"] = 1
gsheets.delete_rows("pedidos", [5])
r.check(CONT["worksheet"] == 2,
        f"handle re-resuelto, no reusado ({CONT['worksheet']} resoluciones)")

print("\n=== 5. clear_ws_cache() limpia los dos niveles ===")
gsheets.get_all_rows("pedidos")
CONT.update(worksheet=0, open=0)
gsheets.clear_ws_cache()
gsheets.get_all_rows("pedidos")
r.check(CONT["worksheet"] == 1, "worksheet re-resuelto tras clear")
r.check(CONT["open"] == 1, "spreadsheet re-abierto tras clear")

print("\n=== 6. Hoja inexistente: no reintenta en vano ===")
CONT.update(worksheet=0)
try:
    gsheets.ws("hoja_que_no_existe")
    r.check(False, "debía lanzar ConnectionError")
except ConnectionError:
    r.check(CONT["worksheet"] == 0, "KeyError corta el retry sin pegarle a la API")
except Exception as e:
    r.check(False, f"lanzó {type(e).__name__} en vez de ConnectionError")

r.salir()
