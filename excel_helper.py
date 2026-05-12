"""
excel_helper.py
Operaciones de escritura/modificacion en el Excel:
  - Pedidos: cancelar, restaurar, editar cantidad
  - Clientes: agregar, editar, eliminar
  - Productos: agregar, editar, eliminar (lista normal y Antigua)
"""

import streamlit as st
from drive_helper import cargar_para_lectura, cargar_para_escritura, guardar_en_drive

FILE_ID = st.secrets["EXCEL_FILE_ID"]


def _actualizar_tabla(ws, nombre_tabla: str):
    """Ajusta la referencia de una tabla al max_row actual."""
    if nombre_tabla in ws.tables:
        tbl    = ws.tables[nombre_tabla]
        partes = tbl.ref.split(":")
        inicio = partes[0]
        col_f  = "".join(c for c in partes[1] if c.isalpha())
        tbl.ref = f"{inicio}:{col_f}{ws.max_row}"


# ═══════════════════════════════════════════════════════════════════════════════
# PEDIDOS
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=120, show_spinner="Cargando pedidos...")
def leer_pedidos() -> list[dict]:
    """Lee todos los pedidos con numero de fila para edicion posterior."""
    wb = cargar_para_lectura(FILE_ID)
    ws = wb["Pedidos"]
    pedidos = []
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row[0]:
            continue
        fecha = row[0]
        if hasattr(fecha, "date"):
            fecha = fecha.date()
        pedidos.append({
            "row_num":   i,
            "fecha":     fecha,
            "cliente":   str(row[1]  or ""),
            "cantidad":  row[2],
            "producto":  str(row[3]  or ""),
            "precio":    row[4],
            "total":     row[6],
            "semana":    row[14],
            "año":       row[15],
            "status":    str(row[30] or "Pendiente"),
            "unico":     str(row[27] or ""),
            "direccion": str(row[18] or ""),
        })
    wb.close()
    return pedidos


def cancelar_pedido(unico: str):
    wb = cargar_para_escritura(FILE_ID)
    ws = wb["Pedidos"]
    for fila in ws.iter_rows(min_row=2):
        if str(fila[27].value or "") == unico:
            fila[30].value = "Cancelado"
    guardar_en_drive(wb, FILE_ID)
    wb.close()
    st.cache_data.clear()


def restaurar_pedido(unico: str):
    wb = cargar_para_escritura(FILE_ID)
    ws = wb["Pedidos"]
    for fila in ws.iter_rows(min_row=2):
        if str(fila[27].value or "") == unico:
            fila[30].value = "Pendiente"
    guardar_en_drive(wb, FILE_ID)
    wb.close()
    st.cache_data.clear()


def editar_cantidad_linea(row_num: int, nueva_cantidad: float):
    wb = cargar_para_escritura(FILE_ID)
    ws = wb["Pedidos"]
    ws.cell(row=row_num, column=3).value = nueva_cantidad
    guardar_en_drive(wb, FILE_ID)
    wb.close()
    st.cache_data.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENTES
# ═══════════════════════════════════════════════════════════════════════════════

TABLA_CLIENTES = "Tabla2"


def _siguiente_codigo_cliente() -> str:
    wb = cargar_para_lectura(FILE_ID)
    ws = wb["Clientes"]
    nums = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        cod = str(row[9] or "").strip()
        if cod.upper().startswith("C") and cod[1:].isdigit():
            nums.append(int(cod[1:]))
    wb.close()
    return f"C{(max(nums) + 1) if nums else 1:03d}"


def agregar_cliente(data: dict) -> str:
    codigo = _siguiente_codigo_cliente()
    wb = cargar_para_escritura(FILE_ID)
    ws = wb["Clientes"]
    ws.append([
        data.get("nombre", ""),
        data.get("direccion", ""),
        data.get("ubicacion", ""),
        data.get("telefono", ""),
        data.get("nit", "0"),
        data.get("tipo", "Restaurante"),
        data.get("estatus", "Pendiente"),
        data.get("empresa", data.get("nombre", "")),
        int(data.get("credito", 0)),
        codigo,
        data.get("codigo_lugar", "L05"),
    ])
    _actualizar_tabla(ws, TABLA_CLIENTES)
    guardar_en_drive(wb, FILE_ID)
    wb.close()
    st.cache_data.clear()
    return codigo


def editar_cliente(row_num: int, data: dict):
    wb = cargar_para_escritura(FILE_ID)
    ws = wb["Clientes"]
    mapeo = {
        1: "nombre", 2: "direccion", 3: "ubicacion", 4: "telefono",
        5: "nit",    6: "tipo",      7: "estatus",   8: "empresa",
        9: "credito", 11: "codigo_lugar",
    }
    for col, campo in mapeo.items():
        if campo in data:
            val = int(data[campo]) if campo == "credito" else data[campo]
            ws.cell(row=row_num, column=col).value = val
    guardar_en_drive(wb, FILE_ID)
    wb.close()
    st.cache_data.clear()


def eliminar_cliente(row_num: int):
    wb = cargar_para_escritura(FILE_ID)
    ws = wb["Clientes"]
    ws.delete_rows(row_num)
    _actualizar_tabla(ws, TABLA_CLIENTES)
    guardar_en_drive(wb, FILE_ID)
    wb.close()
    st.cache_data.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# PRODUCTOS
# ═══════════════════════════════════════════════════════════════════════════════

_PROD_CFG = {
    False: {   # Lista normal
        "hoja":  "Listado Productos",
        "tabla": "LIstPreciosProd",
        # columnas manuales col(1-indexed): campo_data
        "manual": {
            1:"nombre", 2:"unidad", 3:"segmento", 4:"unidad_despacho",
            6:"costo",  8:"precio", 15:"proveedor", 16:"pesos",
            19:"tipo_producto", 20:"parent", 21:"tipo_producto2",
            22:"para_cotizar",  23:"comentario",
        },
        # columnas con formula (copiar de fila anterior)
        "formulas": [7, 9, 10, 11, 12, 13, 17, 18],
    },
    True: {    # Lista Antigua
        "hoja":  "Listado Productos Antigua",
        "tabla": "Tabla29",
        "manual": {
            1:"nombre", 2:"unidad", 3:"segmento", 4:"unidad_despacho",
            6:"costo",  7:"precio", 13:"proveedor", 14:"pesos",
            17:"tipo_producto2",
        },
        "formulas": [8, 9, 10, 11, 12, 15, 16],
    },
}


def agregar_producto(data: dict, es_antigua: bool = False):
    cfg = _PROD_CFG[es_antigua]
    wb  = cargar_para_escritura(FILE_ID)
    ws  = wb[cfg["hoja"]]
    ref = ws.max_row
    new = ref + 1

    for col, campo in cfg["manual"].items():
        ws.cell(row=new, column=col).value = data.get(campo, "")

    for col in cfg["formulas"]:
        src = ws.cell(row=ref, column=col)
        dst = ws.cell(row=new, column=col)
        dst.value         = src.value
        dst.number_format = src.number_format

    _actualizar_tabla(ws, cfg["tabla"])
    guardar_en_drive(wb, FILE_ID)
    wb.close()
    st.cache_data.clear()


def editar_producto(row_num: int, data: dict, es_antigua: bool = False):
    cfg = _PROD_CFG[es_antigua]
    wb  = cargar_para_escritura(FILE_ID)
    ws  = wb[cfg["hoja"]]
    for col, campo in cfg["manual"].items():
        if campo in data:
            ws.cell(row=row_num, column=col).value = data[campo]
    guardar_en_drive(wb, FILE_ID)
    wb.close()
    st.cache_data.clear()


def eliminar_producto(row_num: int, es_antigua: bool = False):
    cfg = _PROD_CFG[es_antigua]
    wb  = cargar_para_escritura(FILE_ID)
    ws  = wb[cfg["hoja"]]
    ws.delete_rows(row_num)
    _actualizar_tabla(ws, cfg["tabla"])
    guardar_en_drive(wb, FILE_ID)
    wb.close()
    st.cache_data.clear()


def leer_productos_con_fila(es_antigua: bool = False) -> list[dict]:
    """Lee productos con numero de fila para edicion/borrado."""
    cfg = _PROD_CFG[es_antigua]
    wb  = cargar_para_lectura(FILE_ID)
    ws  = wb[cfg["hoja"]]
    col_precio = 7 if es_antigua else 8   # 1-indexed
    productos  = []
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row[0]:
            continue
        productos.append({
            "row_num":       i,
            "nombre":        str(row[0]  or ""),
            "unidad":        str(row[1]  or ""),
            "segmento":      str(row[2]  or ""),
            "unidad_despacho": row[3] or 1,
            "costo":         float(row[5] or 0),
            "precio":        float(row[col_precio - 1] or 0),
            "proveedor":     str(row[12] if es_antigua else row[14] or ""),
            "tipo_producto": str(row[16] if es_antigua else row[18] or ""),
            "tipo_producto2": str(row[16] if es_antigua else row[20] or ""),
            "parent":        str(row[19] or row[0] or "") if not es_antigua else str(row[0] or ""),
            "para_cotizar":  str(row[21] or "") if not es_antigua else "",
            "comentario":    str(row[22] or "") if not es_antigua else "",
            "pesos":         float(row[15] if es_antigua else row[15] or 0),
        })
    wb.close()
    return productos
