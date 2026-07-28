"""
_stubs.py — Dobles compartidos para las pruebas.

La app depende de streamlit y gspread, que no hacen falta —ni conviene tener—
para probar lógica de negocio. Acá se registran módulos falsos en sys.modules
ANTES de importar el código real, para que las pruebas corran con solo Python
instalado y sin credenciales de Google.

Uso, siempre como PRIMERA importación del test:

    from _stubs import instalar_streamlit, raiz_repo
    instalar_streamlit()
"""
import os
import sys
import types


def raiz_repo() -> str:
    """Ruta del repo (carpeta padre de tests/), y la deja en sys.path."""
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if raiz not in sys.path:
        sys.path.insert(0, raiz)
    return raiz


def _decorador_transparente(*args, **kwargs):
    """Imita @st.cache_data / @st.cache_resource: no cachea, solo devuelve."""
    def deco(fn):
        return fn
    if len(args) == 1 and callable(args[0]) and not kwargs:
        return deco(args[0])
    return deco


def _cache_resource_real(*dargs, **dkw):
    """@st.cache_resource CON memoria y .clear(), para probar invalidación."""
    def deco(fn):
        store = {}
        def wrapper(*a, **k):
            clave = (a, tuple(sorted(k.items())))
            if clave not in store:
                store[clave] = fn(*a, **k)
            return store[clave]
        wrapper.clear = store.clear
        return wrapper
    if len(dargs) == 1 and callable(dargs[0]) and not dkw:
        return deco(dargs[0])
    return deco


def instalar_streamlit(cache_resource_real: bool = False):
    """Registra un streamlit falso en sys.modules y lo devuelve.

    cache_resource_real=True memoiza de verdad — necesario solo para las
    pruebas que verifican el caché de gsheets.
    """
    st = types.ModuleType("streamlit")
    st.cache_data = _decorador_transparente
    st.cache_resource = (_cache_resource_real if cache_resource_real
                         else _decorador_transparente)
    st.session_state = {}
    st.secrets = {"gcp_service_account": {"stub": True}}
    for nombre in ("warning", "error", "info", "success", "markdown", "caption",
                   "write", "divider", "stop", "rerun", "spinner", "form",
                   "checkbox", "number_input", "selectbox", "text_input"):
        setattr(st, nombre, lambda *a, **k: None)
    st.columns = lambda *a, **k: [
        types.SimpleNamespace(write=lambda *a, **k: None,
                              markdown=lambda *a, **k: None)
        for _ in range(12)]
    sys.modules["streamlit"] = st
    return st


class Reporte:
    """Acumula resultados y decide el código de salida del proceso."""

    def __init__(self):
        self.fallos = []

    def check(self, condicion, mensaje):
        print(("  OK   " if condicion else "  FALLA") + " | " + mensaje)
        if not condicion:
            self.fallos.append(mensaje)

    def salir(self):
        print()
        print("TODO OK" if not self.fallos
              else f"{len(self.fallos)} FALLA(S): {self.fallos}")
        sys.exit(1 if self.fallos else 0)


def por_fila(updates: list) -> dict:
    """Agrupa updates de gsheets por número de fila: {fila: {columna: valor}}."""
    d = {}
    for u in updates:
        col, fila = u["range"][0], int(u["range"][1:])
        d.setdefault(fila, {})[col] = u["values"][0][0]
    return d
