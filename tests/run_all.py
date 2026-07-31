"""
Corre todas las pruebas y devuelve exit code 0 solo si pasan todas.

    python tests/run_all.py

Cada prueba se lanza en su PROPIO proceso a propósito: todas registran módulos
falsos (streamlit, gspread, excel_helper...) en sys.modules, así que compartir
intérprete haría que una pise los dobles de la otra.

No requieren dependencias: corren con Python pelado, sin streamlit, sin gspread
y sin credenciales de Google.
"""
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))

PRUEBAS = [
    "test_nombres_definidos.py",
    "test_gsheets_cache.py",
    "test_propagacion_costo.py",
    "test_rutas_costo.py",
    "test_reporte_compras.py",
    "test_reporte_compras_pdf.py",
    "test_forms_items.py",
    "test_apedir_comprar.py",
    "test_listado_empaque.py",
]


def main() -> int:
    entorno = dict(os.environ, PYTHONIOENCODING="utf-8")
    fallaron = []
    for nombre in PRUEBAS:
        # flush antes de cada subproceso: si no, los print del padre quedan en
        # buffer y la salida aparece desordenada respecto de la de los hijos.
        print("=" * 72, flush=True)
        print(f"  {nombre}", flush=True)
        print("=" * 72, flush=True)
        res = subprocess.run([sys.executable, os.path.join(AQUI, nombre)],
                             cwd=AQUI, env=entorno)
        if res.returncode != 0:
            fallaron.append(nombre)
        print(flush=True)

    print("=" * 72, flush=True)
    if fallaron:
        print(f"FALLARON {len(fallaron)}/{len(PRUEBAS)}: {', '.join(fallaron)}",
              flush=True)
        return 1
    print(f"PASARON las {len(PRUEBAS)} pruebas", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
