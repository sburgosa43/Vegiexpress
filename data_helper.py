"""
data_helper.py
Lee clientes y productos del Excel en Drive.
Los datos se cachean 10 minutos para no descargar el archivo en cada interacción.
"""

import streamlit as st
from drive_helper import cargar_para_lectura

FILE_ID = st.secrets["EXCEL_FILE_ID"]


# ── CLIENTES ──────────────────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner="Cargando clientes...")
def cargar_clientes() -> list[dict]:
    """
    Lee la hoja 'Clientes' y retorna lista de clientes activos.

    Columnas esperadas (índice base 0):
    0:Nombre  1:Direccion  2:Ubicación  3:Telefono  4:Nit
    5:Tipo    6:Estatus    7:Empresa    8:Credito   9:Codigo  10:Codigo Lugar
    """
    wb = cargar_para_lectura(FILE_ID)
    ws = wb["Clientes"]

    clientes = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        nombre = row[0]
        estatus = str(row[6] or "").strip().lower()

        # Solo clientes activos con nombre
        if not nombre:
            continue

        codigo_lugar = str(row[10] or "").strip()

        clientes.append({
            "nombre":       str(nombre).strip(),
            "direccion":    str(row[1] or "").strip(),
            "ubicacion":    str(row[2] or "").strip(),
            "telefono":     str(row[3] or "").strip(),
            "nit":          str(row[4] or "0").strip(),
            "tipo":         str(row[5] or "").strip(),
            "estatus":      str(row[6] or "").strip(),
            "empresa":      str(row[7] or nombre).strip(),
            "credito":      int(row[8]) if row[8] else 0,
            "codigo":       str(row[9] or "").strip(),
            "codigo_lugar": codigo_lugar,
            # L03 = Antigua → usa lista de precios Antigua
            "es_antigua":   codigo_lugar == "L03",
            "activo":       estatus == "cliente",
        })

    wb.close()
    return sorted(clientes, key=lambda c: c["nombre"])


# ── PRODUCTOS ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner="Cargando productos...")
def cargar_productos(es_antigua: bool = False) -> list[dict]:
    """
    Lee la hoja de productos correspondiente y retorna lista de productos activos.

    Hoja normal:   'Listado Productos'
    Hoja Antigua:  'Listado Productos Antigua'

    Columnas esperadas (índice base 0):
    0:Producto        1:Unidad          2:Segmento      3:Unidad Despacho
    4:Cantidad        5:Costo           6:Precio Imp.   7:Precio (manual)
    8:Precio Sug.     9:Sug vs Precio   10:Pto. Equil.  11:Margen
    12:Margen Neto    13:%Margen        14:Proveedor    15:Pesos
    16:Precio Sin IVA 17:Precio s/IVA   18:Tipo Prod    19:Parent
    20:Tipo Prod2     21:Para Cotizar   22:Comentario
    """
    hoja = "Listado Productos Antigua" if es_antigua else "Listado Productos"
    wb = cargar_para_lectura(FILE_ID)
    ws = wb[hoja]

    productos = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        nombre = row[0]
        if not nombre:
            continue

        # Filtrar productos marcados como "N" (no cotizar)
        cotizar = str(row[21] or "").strip().upper()
        if cotizar == "N":
            continue

        precio = float(row[7] or 0)
        costo  = float(row[5] or 0)
        if precio <= 0:
            continue  # Sin precio no se puede vender

        productos.append({
            "nombre":          str(nombre).strip(),
            "unidad":          str(row[1] or "").strip(),
            "segmento":        str(row[2] or "").strip(),
            "unidad_despacho": int(row[3]) if row[3] else 1,
            "costo":           costo,
            "precio":          precio,
            "precio_sin_iva":  float(row[17] or 0),
            "proveedor":       str(row[14] or "").strip(),
            "pesos":           float(row[15] or 0),
            "tipo_producto":   str(row[18] or "").strip(),
            "parent":          str(row[19] or nombre).strip(),
            "tipo_producto2":  str(row[20] or "").strip(),
            "para_cotizar":    cotizar,
            "comentario":      str(row[22] or "").strip(),
            "es_especialidad": cotizar == "ESPECIALIDAD",
        })

    wb.close()
    return sorted(productos, key=lambda p: p["nombre"])
