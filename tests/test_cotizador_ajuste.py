"""
Cotizador → Calcular Precio: el campo "Precio final a cobrar".

Dos capas del mismo defecto:

1. La key del widget era fija. Streamlit IGNORA `value` cuando la key ya tiene
   estado, así que al cambiar el costo o el margen el campo se quedaba con el
   precio sugerido VIEJO y el bloque "Impacto" comparaba contra un número que
   ya no correspondía. Se arregla versionando la key.

2. La comparación era `precio_ajustado != resultado["precio"]`, entre un input
   redondeado a 2 decimales y un sugerido guardado con 4: daba distinto SIEMPRE
   y el bloque de impacto salía aunque no se hubiera tocado nada.

Acá se prueba (2), que es lógica pura. Lo de la key se verifica leyendo el
código: necesita un runtime de Streamlit y no hay forma honesta de simularlo
con estos dobles — lo que sí se pincha es que la key NO sea constante.

    python tests/test_cotizador_ajuste.py
"""
import ast
import os
import sys

from _stubs import Reporte, instalar_streamlit, raiz_repo

RAIZ = raiz_repo()
instalar_streamlit()

from modulo_cotizador import _precio_cambiado, _desde_margen_pct   # noqa: E402

r = Reporte()

print("=== 1. El sugerido tal cual NO cuenta como cambio ===")
d = _desde_margen_pct(5.0, 0.30)
sug = d["precio"]
r.check(not _precio_cambiado(round(sug, 2), sug),
        f"el input redondeado a 2 decimales ({round(sug, 2)}) no difiere del "
        f"sugerido ({sug})")
r.check(not _precio_cambiado(sug, sug), "idéntico tampoco")

print("\n=== 2. Un cambio real sí se detecta ===")
r.check(_precio_cambiado(round(sug, 2) + 0.25, sug), "subir 25 centavos")
r.check(_precio_cambiado(round(sug, 2) - 0.25, sug), "bajarlo también")
r.check(_precio_cambiado(sug + 0.01, sug), "un centavo ya es un cambio")

print("\n=== 3. La tolerancia es media centésima ===")
r.check(not _precio_cambiado(sug + 0.004, sug),
        "0.004 es ruido de redondeo, no un cambio")
r.check(_precio_cambiado(sug + 0.006, sug), "0.006 sí")

print("\n=== 4. Casos borde ===")
r.check(not _precio_cambiado(0.0, 0.0), "dos ceros no difieren")
r.check(_precio_cambiado(10, 5), "acepta enteros")

print("\n=== 5. La key del widget no puede ser constante ===")
# Si vuelve a ser un literal fijo, el campo se queda con el precio viejo. Se
# revisa el AST en vez del texto para no depender del formato.
_src = open(os.path.join(RAIZ, "modulo_cotizador.py"), encoding="utf-8").read()
_fn = next(n for n in ast.parse(_src).body
           if isinstance(n, ast.FunctionDef) and n.name == "_tab_calcular")
_keys = [kw.value for nodo in ast.walk(_fn)
         if isinstance(nodo, ast.Call)
         for kw in nodo.keywords if kw.arg == "key"]
_ajuste = [k for k in _keys
           if (isinstance(k, ast.Constant) and "precio_ajuste" in str(k.value))
           or (isinstance(k, ast.JoinedStr)
               and any(isinstance(v, ast.Constant) and "precio_ajuste" in str(v.value)
                       for v in k.values))]
r.check(len(_ajuste) == 1, f"hay una sola key de ajuste: {len(_ajuste)}")
r.check(isinstance(_ajuste[0], ast.JoinedStr),
        "la key se arma con un f-string (lleva la generación), no es un "
        "literal fijo")

r.salir()
