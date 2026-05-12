"""
data_helper.py — Lectura de catálogos (clientes y productos) con caché.
"""
import streamlit as st
from drive_helper import cargar_para_lectura

FILE_ID = st.secrets["EXCEL_FILE_ID"]


@st.cache_data(ttl=600, show_spinner="Cargando clientes...")
def cargar_clientes() -> list[dict]:
    wb = cargar_para_lectura(FILE_ID)
    ws = wb["Clientes"]
    clientes = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[0]:
            continue
        codigo_lugar = str(row[10] or "").strip()
        estatus      = str(row[6]  or "").strip()
        clientes.append({
            "nombre":       str(row[0]).strip(),
            "direccion":    str(row[1] or "").strip(),
            "ubicacion":    str(row[2] or "").strip(),
            "telefono":     str(row[3] or "").strip(),
            "nit":          str(row[4] or "0").strip(),
            "tipo":         str(row[5] or "").strip(),
            "estatus":      estatus,
            "empresa":      str(row[7] or row[0]).strip(),
            "credito":      int(row[8]) if row[8] else 0,
            "codigo":       str(row[9] or "").strip(),
            "codigo_lugar": codigo_lugar,
            "es_antigua":   codigo_lugar == "L03",
            "activo":       estatus.lower() == "cliente",
        })
    wb.close()
    return sorted(clientes, key=lambda c: c["nombre"])


@st.cache_data(ttl=600, show_spinner="Cargando productos...")
def cargar_productos(es_antigua: bool = False) -> list[dict]:
    """
    Lista normal : Precio en col 8 (índice 7)
    Lista Antigua: Precio en col 7 (índice 6) — no tiene columna 'Precio Impuestos'
    """
    hoja      = "Listado Productos Antigua" if es_antigua else "Listado Productos"
    idx_precio = 6 if es_antigua else 7   # índice 0-based
    wb = cargar_para_lectura(FILE_ID)
    ws = wb[hoja]
    productos = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[0]:
            continue
        precio = float(row[idx_precio] or 0)
        if precio <= 0:
            continue
        costo   = float(row[5] or 0)
        cotizar = str(row[21] or "") if not es_antigua else ""
        productos.append({
            "nombre":          str(row[0]).strip(),
            "unidad":          str(row[1]  or "").strip(),
            "segmento":        str(row[2]  or "").strip(),
            "unidad_despacho": int(row[3]) if row[3] else 1,
            "costo":           costo,
            "precio":          precio,
            "precio_sin_iva":  float(row[15] if es_antigua else row[17] or 0),
            "proveedor":       str(row[12] if es_antigua else row[14] or "").strip(),
            "tipo_producto":   str(row[16] if es_antigua else row[18] or "").strip(),
            "parent":          str(row[0]  if es_antigua else row[19] or row[0]).strip(),
            "tipo_producto2":  str(row[16] if es_antigua else row[20] or "").strip(),
            "para_cotizar":    cotizar,
            "comentario":      str(row[22] or "") if not es_antigua else "",
            "es_especialidad": cotizar.upper() == "ESPECIALIDAD",
        })
    wb.close()
    return sorted(productos, key=lambda p: p["nombre"])
