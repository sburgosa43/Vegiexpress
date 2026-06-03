"""
data_helper.py — Caché de clientes y productos via Google Sheets.
"""
import streamlit as st
from gsheets import get_all_rows

_K_CLI  = "clientes"
_K_PROD = "productos"
_K_ANT  = "antigua"


@st.cache_resource
def cargar_clientes() -> list[dict]:
    """Lista completa de clientes desde Sheets."""
    rows = get_all_rows(_K_CLI)
    clientes = []
    for i, row in enumerate(rows, start=2):
        while len(row) < 11: row.append("")
        if not row[0]: continue
        clientes.append({
            "row_num":      i,
            "nombre":       str(row[0]  or ""),
            "direccion":    str(row[1]  or ""),
            "ubicacion":    str(row[2]  or ""),
            "telefono":     str(row[3]  or ""),
            "nit":          str(row[4]  or "0"),
            "tipo":         str(row[5]  or "Restaurante"),
            "estatus":      str(row[6]  or "Pendiente"),
            "empresa":      str(row[7]  or row[0] or ""),
            "credito":      int(float(row[8] or 0)),
            "codigo":       str(row[9]  or ""),
            "codigo_lugar": str(row[10] or "L05"),
            "activo":       str(row[6] or "").strip().lower() != "inactivo",
            "es_antigua":   str(row[10] or "L05").strip() in ("L03", "L04"),
        })
    return clientes


@st.cache_resource
def cargar_productos(es_antigua: bool = False,
                     solo_catalogo: bool = True) -> list[dict]:
    """Productos para catálogo (app de pedidos y cotizador)."""
    k     = _K_ANT if es_antigua else _K_PROD
    rows  = get_all_rows(k)
    col_p = 6 if es_antigua else 7   # 0-indexed precio

    prods = []
    for row in rows:
        while len(row) < 23: row.append("")
        nombre    = str(row[0] or "").strip()
        cotizar   = str(row[21] if not es_antigua else
                        (row[17] if len(row) > 17 else "") or "").strip().lower()
        if not nombre: continue
        if solo_catalogo and cotizar not in ("si", "sí", "yes", "1"): continue

        try: precio = float(row[col_p] or 0)
        except: precio = 0.0
        if precio <= 0: continue

        prods.append({
            "nombre":   nombre,
            "unidad":   str(row[1]  or ""),
            "segmento": str(row[2]  or ""),
            "costo":    float(row[5] or 0),
            "precio":   precio,
            "proveedor":str(row[14] if not es_antigua else row[8] or ""),
            "tipo_producto2": str(row[20] if not es_antigua else row[10] or ""),
        })
    return prods
