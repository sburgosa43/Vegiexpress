"""
Distribución de páginas del Listado de Empaque (pdf_helper).

El bug: había un contador manual de altura que emitía FrameBreak para saltar de
columna. Ese contador solo se reiniciaba en los saltos que emitía él mismo, pero
ReportLab también salta por su cuenta cuando algo no entra — y ahí el contador
seguía sumando. Desincronizado, disparaba saltos con la columna casi vacía: en
el listado real de la semana 31 dejaba ~121 filas libres en 3 páginas, con una
columna entera prácticamente sin usar.

La corrección es dejar que ReportLab reparta entre los dos Frames y quedarse
solo con KeepTogether, que ya evita partir un cliente.

    python tests/test_listado_empaque.py
"""
import re
import sys

from _stubs import Reporte, instalar_streamlit, raiz_repo

raiz_repo()
instalar_streamlit()

try:
    import reportlab  # noqa: F401
except ImportError:
    print("  SALTADA | reportlab no está instalado (pip install reportlab)")
    sys.exit(0)

from pdf_helper import generar_listado_checklist              # noqa: E402

r = Reporte()

# Altura útil de una columna: A4 menos header (24mm+5mm) y pie (12mm).
FH_COL = 841.89 - (29 * 2.8346) - (12 * 2.8346)


def _paginas(pdf: bytes) -> int:
    m = re.findall(rb"/Count\s+(\d+)", pdf)
    return int(m[0]) if m else len(re.findall(rb"/Type\s*/Page[^s]", pdf))


def _filas(cliente, n, prod="Producto"):
    return [{"cliente": cliente, "producto": f"{prod} {i:02d}",
             "unidad": "Libra", "cantidad": float(i + 1)} for i in range(n)]


print("=== 1. Caso real: 8 clientes, 146 líneas ===")
# Reproduce el volumen del listado que mostró el problema.
datos, restante = [], 146
for i in range(8):
    n = min(19, restante) if i < 7 else restante
    datos.append((f"Cliente {i}", _filas(f"Cliente {i}", n)))
    restante -= n
total = sum(len(v) for _, v in datos)
pdf = generar_listado_checklist(datos, "🏠 Hogares", 31, 2026)
pags = _paginas(pdf)
# Alto estimado: una fila ~11pt y un encabezado por cliente ~13pt.
alto = total * 11 + len(datos) * 13
minimo = -(-alto // (FH_COL * 2))
r.check(pdf[:5] == b"%PDF-", "genera un PDF válido")
r.check(pags <= minimo + 1,
        f"{pags} página(s) para {total} líneas (mínimo teórico {minimo:.0f})")
r.check(pags <= 2, f"cabe en 2 páginas, no en 3 como antes ({pags})")

print("\n=== 2. Muchos clientes chicos llenan la página ===")
chicos = [(f"C{i}", _filas(f"C{i}", 4)) for i in range(40)]
p2 = _paginas(generar_listado_checklist(chicos, "Área", 31, 2026))
alto2 = 40 * 4 * 11 + 40 * 13
min2 = -(-alto2 // (FH_COL * 2))
r.check(p2 <= min2 + 1,
        f"40 clientes de 4 líneas -> {p2} página(s) (mínimo {min2:.0f})")

print("\n=== 3. Un cliente más grande que una columna se parte ===")
# Sin partirlo, KeepTogether no podría colocarlo nunca y el PDF se rompería
# o colgaría. Antes lo cubría un tope fijo de 48 filas; ahora se mide la altura.
grande = [("Mayorista", _filas("Mayorista", 200))]
pdf3 = generar_listado_checklist(grande, "Área", 31, 2026)
r.check(pdf3[:5] == b"%PDF-", "200 líneas de un solo cliente no rompen el PDF")
r.check(_paginas(pdf3) >= 2, f"se reparte en varias páginas ({_paginas(pdf3)})")

print("\n=== 4. Nombres largos (fila doble) también se miden ===")
# El tope fijo de filas fallaba acá: 48 filas de nombre largo ocupan el doble
# y se desbordaban. Al medir la altura real, el corte se ajusta solo.
largo = [("Distribuidora Comercial del Altiplano Sociedad Anonima",
          [{"cliente": "Distribuidora Comercial del Altiplano Sociedad Anonima",
            "producto": "Producto con nombre igualmente largo para forzar dos "
                        f"renglones {i:02d}",
            "unidad": "Libra", "cantidad": 1.0} for i in range(120)])]
pdf4 = generar_listado_checklist(largo, "Área", 31, 2026)
r.check(pdf4[:5] == b"%PDF-", "nombres largos no rompen el armado")
r.check(_paginas(pdf4) >= 2, f"se reparte igual ({_paginas(pdf4)} páginas)")

print("\n=== 5. Casos borde ===")
r.check(generar_listado_checklist([], "Área", 31, 2026)[:5] == b"%PDF-",
        "lista vacía genera PDF igual")
r.check(generar_listado_checklist([("Solo", _filas("Solo", 1))],
                                  "Área", 31, 2026)[:5] == b"%PDF-",
        "un cliente con una línea")

r.salir()
