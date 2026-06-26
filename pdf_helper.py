"""
pdf_helper.py — Facade de compatibilidad hacia atrás.

Todos los módulos de la app importan desde aquí igual que antes.
La implementación real está en los sub-módulos especializados:

  pdf_base.py        → constantes, estilos, helpers compartidos
  pdf_envio.py       → generar_envio, nombre_archivo
  pdf_facturacion.py → generar_facturacion_mensual, nombre_archivo_fact/factura
  pdf_cotizacion.py  → generar_cotizacion, generar_cotizacion_formal
  pdf_proveedores.py → generar_lista_compras_proveedor, generar_listado_checklist
  pdf_remision.py    → generar_remision
  pdf_base.py        → boton_imprimir_html

Para importar desde un módulo UI:
  from pdf_helper import generar_envio, nombre_archivo    ← sigue funcionando
"""

# ── Re-exportar todo desde los sub-módulos ────────────────────────────────────
from pdf_base import (
    _s, _p, _S, _logo_proporcional, boton_imprimir_html, nombre_archivo,
    VERDE_OSC, VERDE_LIM, GRIS_CARB, GRIS_CLR, GRIS_TAB, BLANCO,
    LOGO_PATH, PAGE_W, PAGE_H, CONTENT_W, _MESES_ES, MESES_ES,
)

from pdf_envio       import generar_envio
from pdf_facturacion import (generar_facturacion_mensual,
                              nombre_archivo_fact, nombre_archivo_factura)
from pdf_cotizacion  import generar_cotizacion, generar_cotizacion_formal
from pdf_proveedores import (generar_lista_compras_proveedor,
                              generar_listado_checklist)
from pdf_remision    import generar_remision

__all__ = [
    # base
    "_s", "_p", "_S", "_logo_proporcional", "boton_imprimir_html",
    "nombre_archivo", "VERDE_OSC", "VERDE_LIM", "GRIS_CARB",
    "GRIS_CLR", "GRIS_TAB", "BLANCO", "LOGO_PATH",
    "PAGE_W", "PAGE_H", "CONTENT_W", "_MESES_ES", "MESES_ES",
    # envio
    "generar_envio",
    # facturacion
    "generar_facturacion_mensual", "nombre_archivo_fact", "nombre_archivo_factura",
    # cotizacion
    "generar_cotizacion", "generar_cotizacion_formal",
    # proveedores
    "generar_lista_compras_proveedor", "generar_listado_checklist",
    # remision
    "generar_remision",
]
