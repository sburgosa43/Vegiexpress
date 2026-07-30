"""
Ningún módulo usa un nombre que no esté definido ni importado.

Existe por un bug real: al reemplazar dos funciones de modulo_hogares.py con un
corte por posición de texto, se borró de paso la constante _WA_UNIDADES que
estaba entre ellas. El archivo seguía compilando —Python no valida los nombres
hasta ejecutarlos— y el error salió recién en producción, al pegar un pedido de
WhatsApp:

    NameError: name '_WA_UNIDADES' is not defined

`python -m py_compile` NO detecta esto. Este chequeo sí, y en todo el repo de
una sola pasada.

    python tests/test_nombres_definidos.py
"""
import ast
import builtins
import io
import pathlib

from _stubs import Reporte, raiz_repo

RAIZ = pathlib.Path(raiz_repo())
INTEGRADOS = set(dir(builtins))


def _nombres_faltantes(ruta: pathlib.Path) -> list:
    """Nombres leídos en el archivo que no están definidos en ninguna parte.

    Es una aproximación deliberadamente permisiva: junta TODO lo que el archivo
    define en cualquier ámbito (módulo, función, comprensión, except, global) y
    lo compara contra lo que lee. No distingue ámbitos, así que no detecta un
    nombre definido en otra función — pero tampoco da falsos positivos, que es
    lo que haría que nadie corriera el test.
    """
    arbol = ast.parse(io.open(ruta, encoding="utf-8").read())
    disponibles = set(INTEGRADOS)
    for n in ast.walk(arbol):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                disponibles.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            disponibles.add(n.name)
        elif isinstance(n, ast.arg):
            disponibles.add(n.arg)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            disponibles.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            disponibles.add(n.name)
        elif isinstance(n, ast.Global):
            disponibles.update(n.names)
    leidos = {n.id for n in ast.walk(arbol)
              if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    return sorted(leidos - disponibles)


r = Reporte()

archivos = sorted(RAIZ.glob("*.py"))
print(f"=== Revisando {len(archivos)} archivos del repo ===")

con_problemas = {}
for ruta in archivos:
    faltan = _nombres_faltantes(ruta)
    if faltan:
        con_problemas[ruta.name] = faltan

for nombre, faltan in con_problemas.items():
    print(f"  {nombre}: {', '.join(faltan)}")

r.check(not con_problemas,
        f"{len(archivos)} archivos sin nombres indefinidos"
        if not con_problemas
        else f"{len(con_problemas)} archivo(s) con nombres indefinidos")

print("\n=== El chequeo detecta el caso que se nos escapó ===")
_roto = RAIZ / "tests" / "_tmp_roto.py"
_roto.write_text("def f():\n    return _CONSTANTE_QUE_BORRE\n", encoding="utf-8")
try:
    detectado = _nombres_faltantes(_roto)
    r.check(detectado == ["_CONSTANTE_QUE_BORRE"],
            f"detecta una constante borrada: {detectado}")
finally:
    _roto.unlink(missing_ok=True)

r.salir()
