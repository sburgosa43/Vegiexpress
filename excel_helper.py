"""
excel_helper.py — Acceso a datos via Google Sheets (migrado de Excel/Drive).
Mismas firmas de función que antes — todos los módulos funcionan sin cambios.
"""
import streamlit as st
from sys import intern as _intern
from datetime import date, datetime, timedelta
from gsheets import (ws as _ws, get_all_rows, append_rows,
                     update_cells, update_cell, delete_rows)
from config import HOJA_PEDIDOS, HOJA_CLIENTES, HOJA_PRODUCTOS, HOJA_PRODUCTOS_ANTIGUA

# ── Constantes ─────────────────────────────────────────────────────────────────
DIAS_ES  = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
MESES_N  = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]

# Claves para hojas en gsheets.py
_K_PED  = "pedidos"
_K_CLI  = "clientes"
_K_PROD = "productos"
_K_ANT  = "antigua"
_K_CFG  = "config"
_K_HIST = "historial"

# Columna "Para Cotizar" (1-indexed en Sheets, igual que en Excel)
_PARA_COTIZAR_COL = {False: 22, True: 18}

# Zonas para metas
ZONAS_CONFIG = ["GT + Santiago", "Río", "Antigua + Chimal"]

def _sf(v) -> float:
    """Safe float — maneja vacíos, comas decimales y símbolos de moneda."""
    if v is None or v == "": return 0.0
    if isinstance(v, (int, float)): return float(v)
    s = str(v).strip().replace("Q","").replace("$","").replace(" ","")
    # Manejar formato europeo/centroamericano: 1.234,56 → 1234.56
    if "," in s and "." in s:
        # Si el punto viene antes que la coma: 1.234,56
        if s.index(".") < s.index(","):
            s = s.replace(".","").replace(",",".")
        else:
            s = s.replace(",","")
    elif "," in s:
        s = s.replace(",",".")
    try: return float(s)
    except: return 0.0

def _si(v) -> int:
    """Safe int."""
    try: return int(v or 0)
    except: return 0

def _parse_fecha(v) -> date | None:
    """Parsea fecha desde string (Sheets devuelve strings)."""
    if not v: return None
    if isinstance(v, date): return v
    s = str(v).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y"):
        try: return datetime.strptime(s, fmt).date()
        except: pass
    return None


# ── PEDIDOS ────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, max_entries=1, show_spinner=False)
def leer_pedidos_op() -> list[dict]:
    """Pedidos OPERATIVOS: solo los últimos 12 meses. Los módulos de operación
    diaria (Inicio, Envíos, Proveedores, Flujo de Caja, etc.) no necesitan el
    histórico completo, y cada llamada a leer_pedidos() copia TODA la lista
    (así funciona st.cache_data) — con un histórico creciente, esas copias
    disparaban picos de memoria que tumbaban la app en Streamlit Cloud.
    Esta vista recortada mantiene las copias livianas y acotadas."""
    from datetime import date, timedelta
    corte = date.today() - timedelta(days=365)
    return [p for p in leer_pedidos()
            if p.get("fecha") and p["fecha"] >= corte]


@st.cache_data(ttl=600, show_spinner=False)
def leer_pedidos() -> list[dict]:
    rows   = get_all_rows(_K_PED)
    result = []
    for i, row in enumerate(rows, start=2):
        while len(row) < 31: row.append("")
        if not row[0]: continue

        fecha = _parse_fecha(row[0])
        if not fecha: continue

        precio_xl = _sf(row[4])
        costo     = _sf(row[5])
        cantidad  = _sf(row[2])
        total_xl  = _sf(row[6])

        if precio_xl <= 0 and total_xl > 0 and cantidad > 0:
            precio_xl = round(total_xl / cantidad, 4)

        total_final = round(precio_xl * cantidad, 2)

        try: semana_val = int(_sf(row[14])) or fecha.isocalendar()[1]
        except: semana_val = fecha.isocalendar()[1]

        try: año_val = int(_sf(row[15])) or fecha.year
        except: año_val = fecha.year

        unico_val = str(row[27] or "").strip()
        if not unico_val and fecha and row[1]:
            unico_val = f"_fbk_{str(row[1]).strip()}_{año_val}_{semana_val}_{fecha.strftime('%d%m')}"

        fvenc = _parse_fecha(row[20]) if len(row) > 20 else None

        margen_q = round(0.95 * (precio_xl - costo * 1.12) * cantidad, 2) \
                   if precio_xl > 0 else 0.0

        result.append({
            "row_num":    i,
            "fecha":      fecha,
            "cliente":    _intern(str(row[1]  or "")),
            "cantidad":   cantidad,
            "producto":   _intern(str(row[3]  or "")),
            "precio":     precio_xl,
            "precio_excel": precio_xl,
            "costo":      costo,
            "total":      total_final,
            "margen_q":   margen_q,
            "semana":     semana_val,
            "año":        año_val,
            "status":     _intern(str(row[30] or "Pendiente")),
            "unico":      unico_val,
            "direccion":  _intern(str(row[18] or "")),
            "unidad":     _intern(str(row[16] or "")),
            "proveedor":  _intern(str(row[17] or "")),
            "fecha_venc": fvenc,
        })
    return result


def cancelar_pedido(unico: str) -> int:
    pedidos = leer_pedidos()
    upd = []
    for p in pedidos:
        if p["unico"] == unico and p["status"] != "Cancelado":
            upd.append({"range": f"AE{p['row_num']}", "values": [["Cancelado"]]})
    if upd:
        update_cells(_K_PED, upd)
        leer_pedidos.clear()
    return len(upd)


def restaurar_pedido(unico: str) -> int:
    pedidos = leer_pedidos()
    upd = []
    for p in pedidos:
        if p["unico"] == unico and p["status"] == "Cancelado":
            upd.append({"range": f"AE{p['row_num']}", "values": [["Pendiente"]]})
    if upd:
        update_cells(_K_PED, upd)
        leer_pedidos.clear()
    return len(upd)


def eliminar_pedido(unico: str) -> int:
    pedidos = leer_pedidos()
    rows_to_delete = [p["row_num"] for p in pedidos if p["unico"] == unico]
    if rows_to_delete:
        delete_rows(_K_PED, rows_to_delete)
        leer_pedidos.clear()
    return len(rows_to_delete)


def editar_linea(row_num: int, campo: str, valor) -> None:
    COL_MAP = {"cantidad": "C", "precio": "E", "costo": "F", "status": "AE"}
    col = COL_MAP.get(campo)
    if col:
        update_cells(_K_PED, [{"range": f"{col}{row_num}", "values": [[valor]]}])
        leer_pedidos.clear()


def editar_fecha_pedido(unico: str, nueva_fecha: date) -> int:
    pedidos = leer_pedidos()
    upd = []
    fecha_str = nueva_fecha.strftime("%d/%m/%Y")
    sem = nueva_fecha.isocalendar()[1]
    año = nueva_fecha.year
    mes = nueva_fecha.month
    dia_es = DIAS_ES[nueva_fecha.weekday()]

    # Si el pedido usa un unico de FALLBACK (generado desde la fecha en cada
    # lectura, prefijo "_fbk_"), al cambiar la fecha ese unico cambiaría y el
    # pedido "desaparecería" de las vistas agrupadas. Fix: escribir un unico
    # REAL y estable en la columna AB para que deje de depender de la fecha.
    unico_estable = None
    if unico.startswith("_fbk_"):
        import time as _time
        unico_estable = f"FIX{nueva_fecha.day:02d}{mes:02d}{sem:02d}{año}" \
                        f"{int(_time.time()) % 10000}"

    cols_por_fila = 5 + (1 if unico_estable else 0)
    for p in pedidos:
        if p["unico"] == unico:
            rn = p["row_num"]
            upd += [
                {"range": f"A{rn}", "values": [[fecha_str]]},
                {"range": f"M{rn}", "values": [[dia_es]]},
                {"range": f"N{rn}", "values": [[mes]]},
                {"range": f"O{rn}", "values": [[sem]]},
                {"range": f"P{rn}", "values": [[año]]},
            ]
            if unico_estable:
                upd.append({"range": f"AB{rn}", "values": [[unico_estable]]})
    if upd:
        update_cells(_K_PED, upd)
        leer_pedidos.clear()
    return len(upd) // cols_por_fila


def editar_cambios_batch(cambios: list) -> int:
    """
    cambios: [{row_num, cantidad_nueva, precio_nuevo, total_nuevo,
               total_costo_nuevo, margen_q_nuevo, margen_pct_nuevo}]
    """
    upd = []
    for ch in cambios:
        rn = ch["row_num"]
        if "producto_nuevo" in ch:
            upd.append({"range": f"D{rn}", "values": [[ch["producto_nuevo"]]]})
        if "cantidad_nueva" in ch:
            upd.append({"range": f"C{rn}", "values": [[ch["cantidad_nueva"]]]})
        if "precio_nuevo" in ch:
            upd.append({"range": f"E{rn}", "values": [[ch["precio_nuevo"]]]})
        if "total_nuevo" in ch:
            upd.append({"range": f"G{rn}", "values": [[ch["total_nuevo"]]]})
    if upd:
        update_cells(_K_PED, upd)
        leer_pedidos.clear()
    return len(cambios)


def guardar_cambios_precio(cambios: list, actualizar_catalogo: bool = False) -> int:
    upd_ped = []
    reales  = []
    for ch in cambios:
        precio_ant = _sf(ch.get("precio_anterior", 0))
        precio_nvo = _sf(ch.get("precio_nuevo", 0))
        if abs(precio_nvo - precio_ant) < 0.001: continue
        reales.append(ch)
        rn = ch["row_num"]
        upd_ped.append({"range": f"E{rn}", "values": [[precio_nvo]]})

    if upd_ped:
        update_cells(_K_PED, upd_ped)

    if actualizar_catalogo and reales:
        prod_map = {c["producto"]: _sf(c["precio_nuevo"]) for c in reales}
        _actualizar_precio_catalogo(prod_map)

    if upd_ped:
        leer_pedidos.clear()
    return len(reales)


def _actualizar_precio_catalogo(precio_map: dict,
                                    costo_map:  dict = None) -> int:
    """Actualiza precio Y costo en Listado Productos y Listado Antigua."""
    costo_map = costo_map or {}
    total = 0
    # General: precio=col H(8), costo=col F(6)
    # Antigua: precio=col G(7), costo=col F(6)
    for k_hoja, col_prec, col_cost in [(_K_PROD, "H", "F"), (_K_ANT, "G", "F")]:
        rows = get_all_rows(k_hoja)
        upd  = []
        for i, row in enumerate(rows, start=2):
            prod = str(row[0] if row else "").strip()
            if prod in precio_map:
                upd.append({"range": f"{col_prec}{i}",
                            "values": [[precio_map[prod]]]})
            if prod in costo_map and costo_map[prod] > 0:
                upd.append({"range": f"{col_cost}{i}",
                            "values": [[costo_map[prod]]]})
        if upd:
            update_cells(k_hoja, upd)
            total += len(upd)
    leer_productos_con_fila.clear()
    try:
        from data_helper import cargar_productos
        cargar_productos.clear()
    except Exception:
        pass
    if costo_map:
        _log_costo_actualizado({p: v for p, v in costo_map.items() if v > 0})
    return total


# ── LOG DE COSTOS (sheet Historial Cambios) ───────────────────────────────────
def _log_costo_actualizado(costo_map: dict) -> None:
    """Registra fecha de actualizacion de costo por producto.
    Formato fila: Fecha | COSTO | producto | costo_nuevo"""
    if not costo_map: return
    try:
        from datetime import date as _d
        hoy  = _d.today().strftime("%d/%m/%Y")
        rows = [[hoy, "COSTO", prod, val] for prod, val in costo_map.items()]
        append_rows(_K_HIST, rows)
        costo_ultima_actualizacion.clear()
    except Exception:
        pass  # el log nunca debe bloquear la operacion principal


@st.cache_data(ttl=300, show_spinner=False)
def costo_ultima_actualizacion() -> dict:
    """{producto_lower: date} — ultima fecha de actualizacion de costo."""
    from datetime import datetime as _dt
    result = {}
    try:
        rows = get_all_rows(_K_HIST)
        for row in rows:
            if len(row) < 3: continue
            if str(row[1]).strip().upper() != "COSTO": continue
            try:
                f = _dt.strptime(str(row[0]).strip(), "%d/%m/%Y").date()
            except Exception:
                continue
            prod = str(row[2]).strip().lower()
            if prod and (prod not in result or f > result[prod]):
                result[prod] = f
    except Exception:
        pass
    return result


# ── CORRECCIÓN MASIVA ──────────────────────────────────────────────────────────
def preview_correccion_masiva(patron: str, campo: str, valor_nuevo) -> list:
    pedidos = leer_pedidos()
    return [p for p in pedidos
            if patron.lower() in p["producto"].lower()
            and p["status"] != "Cancelado"]


def aplicar_correccion_masiva(patron: str, campo: str, valor_nuevo,
                               actualizar_catalogo: bool = False) -> int:
    pedidos  = leer_pedidos()
    afectados = [p for p in pedidos
                 if patron.lower() in p["producto"].lower()
                 and p["status"] != "Cancelado"]
    COL = {"precio": "E", "costo": "F"}
    col = COL.get(campo)
    if not col or not afectados: return 0

    upd = [{"range": f"{col}{p['row_num']}", "values": [[valor_nuevo]]}
           for p in afectados]
    update_cells(_K_PED, upd)

    if actualizar_catalogo and campo == "precio":
        productos_unicos = {p["producto"] for p in afectados}
        prod_map = {prod: _sf(valor_nuevo) for prod in productos_unicos}
        _actualizar_precio_catalogo(prod_map)

    leer_pedidos.clear()
    return len(afectados)


# ── PRECIO / COSTO POR SEMANA ──────────────────────────────────────────────────
def leer_productos_semana(semana: int, año: int) -> list:
    todos = leer_pedidos()
    agg   = {}
    for p in todos:
        if p["semana"] != semana or p["año"] != año: continue
        if p["status"] == "Cancelado": continue
        prod = p["producto"]
        if prod not in agg:
            agg[prod] = {"producto": prod, "precio_actual": _sf(p["precio"]),
                         "costo": _sf(p["costo"]), "n_pedidos": 0,
                         "clientes": set()}
        agg[prod]["n_pedidos"] += 1
        agg[prod]["clientes"].add(p["cliente"])
    for v in agg.values():
        v["clientes"] = ", ".join(sorted(v["clientes"]))
    return sorted(agg.values(), key=lambda x: x["producto"])


def actualizar_precio_semana(cambios: list, semana: int, año: int,
                                actualizar_catalogo: bool = True) -> dict:
    todos      = leer_pedidos()
    precio_map = {c["producto"]: _sf(c["precio_nuevo"]) for c in cambios
                  if c.get("p_cambia")}
    costo_map  = {c["producto"]: _sf(c["costo_nuevo"])  for c in cambios
                  if c.get("c_cambia")}
    # Para filas de pedidos actualizar siempre precio y costo
    prod_all   = {c["producto"] for c in cambios}

    upd = []
    for p in todos:
        prod = p["producto"]
        if prod not in prod_all: continue
        if p["semana"] != semana or p["año"] != año: continue
        rn = p["row_num"]
        if prod in precio_map:
            upd.append({"range": f"E{rn}", "values": [[precio_map[prod]]]})
        if prod in costo_map and costo_map[prod] > 0:
            upd.append({"range": f"F{rn}", "values": [[costo_map[prod]]]})

    filas_ped = len(upd)
    prods_cat = 0
    if upd:
        update_cells(_K_PED, upd)
        leer_pedidos.clear()
    if actualizar_catalogo and (precio_map or costo_map):
        prods_cat = _actualizar_precio_catalogo(precio_map, costo_map)

    return {"filas_pedidos": filas_ped, "prods_catalogo": prods_cat}


def leer_productos_semana_precios(semana: int, año: int) -> list:
    return leer_productos_semana(semana, año)


# ── CLIENTES ───────────────────────────────────────────────────────────────────
def _siguiente_codigo_cliente() -> str:
    rows = get_all_rows(_K_CLI)
    max_n = 0
    for row in rows:
        cod = str(row[9] if len(row) > 9 else "")
        if cod.startswith("C") and cod[1:].isdigit():
            max_n = max(max_n, int(cod[1:]))
    return f"C{max_n + 1:03d}"


def agregar_cliente(data: dict) -> str:
    codigo = _siguiente_codigo_cliente()
    # Normalizar retiene_isr a "Sí"/"No"
    _isr = data.get("retiene_isr", "Sí")
    _isr = "Sí" if (_isr is True or str(_isr).lower() in ("sí","si","yes","true","1")) else "No"
    row = [
        data.get("nombre",      ""),      # A
        data.get("direccion",   ""),      # B
        data.get("ubicacion",   ""),      # C
        data.get("telefono",    ""),      # D
        data.get("nit",         "0"),     # E
        data.get("tipo",        "Restaurante"),  # F
        data.get("estatus",     "Pendiente"),    # G
        data.get("empresa",     data.get("nombre", "")),  # H
        int(data.get("credito", 0)),      # I
        codigo,                            # J
        data.get("codigo_lugar","L05"),   # K
        data.get("grupo",        ""),      # L
        data.get("email",        ""),      # M
        int(data.get("lag_pago", 0) or 0),        # N
        _isr,                                       # O
        float(data.get("descuento_pct", 0) or 0),  # P
    ]
    append_rows(_K_CLI, [row])
    try:
        from data_helper import cargar_clientes
        cargar_clientes.clear()
    except Exception:
        pass
    return codigo


def editar_cliente(row_num: int, data: dict) -> None:
    mapeo = {
        "A": "nombre",    "B": "direccion", "C": "ubicacion",
        "D": "telefono",  "E": "nit",       "F": "tipo",
        "G": "estatus",   "H": "empresa",   "I": "credito",
        "K": "codigo_lugar",
        # Tratamiento comercial centralizado (Fase B)
        "N": "lag_pago",  "O": "retiene_isr", "P": "descuento_pct",
    }
    upd = []
    for col, campo in mapeo.items():
        if campo in data:
            if campo == "credito":
                val = int(data[campo])
            elif campo == "lag_pago":
                val = int(data[campo] or 0)
            elif campo == "descuento_pct":
                val = float(data[campo] or 0)
            elif campo == "retiene_isr":
                # Normalizar a "Sí"/"No"
                v = data[campo]
                val = "Sí" if (v is True or str(v).lower() in ("sí","si","yes","true","1")) else "No"
            else:
                val = data[campo]
            upd.append({"range": f"{col}{row_num}", "values": [[val]]})
    if upd:
        update_cells(_K_CLI, upd)
    # Invalidación correcta: clientes (no productos)
    try:
        from data_helper import cargar_clientes
        cargar_clientes.clear()
    except Exception:
        pass


def eliminar_cliente(row_num: int) -> None:
    delete_rows(_K_CLI, [row_num])
    # Limpieza dirigida: solo caches de productos (no todo el cache global)
    leer_productos_con_fila.clear()
    try:
        from data_helper import cargar_productos, get_proveedores
        cargar_productos.clear()
        get_proveedores.clear()
    except Exception:
        pass


# ── PRODUCTOS ──────────────────────────────────────────────────────────────────
_PROD_COLS = {
    False: {  # Lista General (columnas 1-indexed → letras)
        "A":"nombre", "B":"unidad",   "C":"segmento",      "D":"unidad_despacho",
        "F":"costo",  "H":"precio",   "O":"proveedor",     "P":"pesos",
        "S":"tipo_producto", "T":"parent", "U":"tipo_producto2",
        "V":"para_cotizar",  "W":"comentario",
    },
    True: {   # Lista Antigua
        "A":"nombre", "B":"unidad",   "C":"segmento",      "D":"unidad_despacho",
        "F":"costo",  "G":"precio",   "M":"proveedor",     "J":"pesos",
        "K":"tipo_producto2", "R":"para_cotizar",
    },
}


@st.cache_data(ttl=300, show_spinner=False)
def leer_productos_con_fila(es_antigua: bool = False) -> list[dict]:
    k     = _K_ANT if es_antigua else _K_PROD
    rows  = get_all_rows(k)
    col_p = 6 if es_antigua else 7   # 0-indexed: G=6, H=7
    productos = []
    for i, row in enumerate(rows, start=2):
        while len(row) < 23: row.append("")
        if not row[0]: continue
        productos.append({
            "row_num":        i,
            "nombre":         str(row[0]  or ""),
            "unidad":         str(row[1]  or ""),
            "segmento":       str(row[2]  or ""),
            "unidad_despacho": _si(row[3]) or 1,
            "costo":          _sf(row[5]),
            "precio":         _sf(row[col_p]),
            "proveedor":      str(row[14] if not es_antigua else row[12] or ""),
            "pesos":          _sf(row[15] if not es_antigua else row[9]),
            "tipo_producto":  str(row[18] if not es_antigua else "" or ""),
            "empacado":       str(row[23] if not es_antigua and len(row) > 23 else "").strip(),
            "tipo_producto2": str(row[20] if not es_antigua else row[10] or ""),
            "parent":         str(row[19] if not es_antigua else row[0] or ""),
            "para_cotizar":   str(row[21] if not es_antigua else
                                  (row[17] if len(row) > 17 else "") or ""),
            "comentario":     str(row[22] if not es_antigua else ""),
        })
    return productos


def agregar_producto(data: dict, es_antigua: bool = False) -> None:
    k    = _K_ANT if es_antigua else _K_PROD
    cols = _PROD_COLS[es_antigua]
    # Build row (max column: W=23 for general, R=18 for antigua)
    max_col = 23 if not es_antigua else 18
    row = [""] * max_col
    for col_letter, campo in cols.items():
        idx = ord(col_letter) - ord("A")
        val = data.get(campo, "")
        if campo == "unidad_despacho": val = int(val or 1)
        row[idx] = val
    append_rows(k, [row])
    # Limpieza dirigida: solo caches de productos (no todo el cache global)
    leer_productos_con_fila.clear()
    try:
        from data_helper import cargar_productos, get_proveedores
        cargar_productos.clear()
        get_proveedores.clear()
    except Exception:
        pass


def editar_producto(row_num: int, data: dict, es_antigua: bool = False) -> None:
    k    = _K_ANT if es_antigua else _K_PROD
    cols = _PROD_COLS[es_antigua]
    upd  = []
    for col_letter, campo in cols.items():
        if campo in data:
            val = int(data[campo] or 1) if campo == "unidad_despacho" else data[campo]
            upd.append({"range": f"{col_letter}{row_num}", "values": [[val]]})
    if upd:
        update_cells(k, upd)
    if "costo" in data and data.get("nombre"):
        _log_costo_actualizado({data["nombre"]: _sf(data["costo"])})
    # Limpieza dirigida: solo caches de productos (no todo el cache global)
    leer_productos_con_fila.clear()
    try:
        from data_helper import cargar_productos, get_proveedores
        cargar_productos.clear()
        get_proveedores.clear()
    except Exception:
        pass


def editar_productos_batch(ediciones: list, es_antigua: bool = False) -> int:
    """Edita VARIOS productos en UN SOLO request a Sheets (evita el bug de
    'guardar 2-3 veces' por escrituras fila-por-fila con reruns intermedios).

    ediciones: [{"row_num": int, "data": {campo: valor, ...}}, ...]
    Retorna la cantidad de productos actualizados.
    """
    if not ediciones:
        return 0
    k    = _K_ANT if es_antigua else _K_PROD
    cols = _PROD_COLS[es_antigua]
    upd  = []
    costos_log = {}
    for ed in ediciones:
        rn   = ed["row_num"]
        data = ed["data"]
        for col_letter, campo in cols.items():
            if campo in data:
                val = (int(data[campo] or 1) if campo == "unidad_despacho"
                       else data[campo])
                upd.append({"range": f"{col_letter}{rn}", "values": [[val]]})
        if "costo" in data and data.get("nombre"):
            costos_log[data["nombre"]] = _sf(data["costo"])

    if upd:
        update_cells(k, upd)   # UN solo request para todos los productos
    if costos_log:
        _log_costo_actualizado(costos_log)

    # Invalidación de caché
    leer_productos_con_fila.clear()
    try:
        from data_helper import refrescar_datos
        refrescar_datos(pedidos=False, productos=True, clientes=False, precios=True)
    except Exception:
        pass
    return len(ediciones)


def eliminar_producto(row_num: int, es_antigua: bool = False) -> None:
    k = _K_ANT if es_antigua else _K_PROD
    delete_rows(k, [row_num])
    # Limpieza dirigida: solo caches de productos (no todo el cache global)
    leer_productos_con_fila.clear()
    try:
        from data_helper import cargar_productos, get_proveedores
        cargar_productos.clear()
        get_proveedores.clear()
    except Exception:
        pass


def guardar_para_cotizar_batch(cambios: dict, es_antigua: bool) -> None:
    k      = _K_ANT if es_antigua else _K_PROD
    col    = "R" if es_antigua else "V"
    upd    = []
    for row_num, val in cambios.items():
        cell_val = "Si" if val else ""
        upd.append({"range": f"{col}{row_num}", "values": [[cell_val]]})
    if upd:
        update_cells(k, upd)
    leer_productos_con_fila.clear()
    try:
        from data_helper import cargar_productos
        cargar_productos.clear()
    except Exception:
        pass


# ── METAS (Config sheet) ───────────────────────────────────────────────────────
def leer_metas() -> dict:
    metas = {z: 0.0 for z in ZONAS_CONFIG}
    try:
        rows = get_all_rows(_K_CFG)
        for row in rows:
            if row and str(row[0]) in ZONAS_CONFIG:
                metas[str(row[0])] = _sf(row[1] if len(row) > 1 else 0)
    except Exception:
        pass
    return metas


def guardar_metas(metas: dict) -> None:
    rows = get_all_rows(_K_CFG)
    zona_rows = {str(r[0]): i+2 for i, r in enumerate(rows) if r}
    upd = []
    new_rows = []
    for zona, val in metas.items():
        if zona in zona_rows:
            upd.append({"range": f"B{zona_rows[zona]}", "values": [[val]]})
        else:
            new_rows.append([zona, val])
    if upd:      update_cells(_K_CFG, upd)
    if new_rows: append_rows(_K_CFG, new_rows)


# ── FUNCIONES LEGACY (compatibilidad) ─────────────────────────────────────────
def migrar_pedidos_a_valores(): pass   # Ya no aplica con Sheets
def _actualizar_tabla(*args, **kwargs): pass
def editar_cantidad_linea(row_num, cant): editar_linea(row_num, "cantidad", cant)

# Alias para orden_helper
FILE_ID = None  # Ya no se usa — mantenido por compatibilidad de imports


# ── FUNCIONES LEGACY DE MANTENIMIENTO ─────────────────────────────────────────
def agregar_col_para_cotizar_antigua() -> str:
    """Migración legacy — ya no aplica con Google Sheets."""
    return "ok"


def limpiar_para_cotizar(es_antigua: bool = False) -> int:
    """Limpia valores 'Para Cotizar' en blanco. Sheets lo maneja automáticamente."""
    return 0
