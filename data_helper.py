"""
data_helper.py — Caché de clientes y productos via Google Sheets.
"""
import streamlit as st
from gsheets import get_all_rows
from utils import _sf, _si

_K_CLI  = "clientes"
_K_PROD = "productos"
_K_ANT  = "antigua"


@st.cache_data(ttl=600, show_spinner=False)
def cargar_clientes() -> list[dict]:
    """Lista completa de clientes desde Sheets."""
    rows = get_all_rows(_K_CLI)
    clientes = []
    for i, row in enumerate(rows, start=2):
        while len(row) < 13: row.append("")
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
            "credito":      _si(row[8]),
            "codigo":       str(row[9]  or ""),
            "codigo_lugar": str(row[10] or "L05"),
            "activo":       str(row[6] or "").strip().lower() != "inactivo",
            "es_antigua":   str(row[10] or "L05").strip() in ("L03", "L04"),
            "grupo":        str(row[11] or "").strip(),
            "email":        str(row[12] or "").strip().lower(),
        })
    return clientes


@st.cache_data(ttl=600, show_spinner=False)
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
        # Si solo_catalogo: incluir Si/Sí/yes y vacíos, excluir solo "no"
        if solo_catalogo and cotizar in ("no",): continue

        try: precio = _sf(row[col_p])
        except: precio = 0.0
        if solo_catalogo and precio <= 0: continue

        prods.append({
            "nombre":   nombre,
            "unidad":   str(row[1]  or ""),
            "segmento": str(row[2]  or ""),
            "costo":    _sf(row[5]),
            "precio":   precio,
            "proveedor":      str(row[14] if not es_antigua else row[8] or "").strip(),
            "tipo_producto":  str(row[18] if not es_antigua else "" or "").strip(),
            "tipo_producto2": str(row[20] if not es_antigua else row[10] or "").strip(),
        })
    return prods


@st.cache_data(ttl=300, show_spinner=False)
def get_proveedores() -> list[str]:
    """Lista dinamica de proveedores unicos del catalogo de productos."""
    from excel_helper import leer_productos_con_fila
    prods = leer_productos_con_fila(False) + leer_productos_con_fila(True)
    found = sorted({p.get("proveedor","").strip()
                    for p in prods if p.get("proveedor","").strip()})
    if "Sin Proveedor" not in found:
        found.append("Sin Proveedor")
    return found


# ── CASCADA DE PRECIOS (4 niveles) ────────────────────────────────────────────
_HOJAS_PRECIOS = {
    "zona":    "precioszona",
    "grupo":   "preciosgrupo",
    "cliente": "preciosclient",
}

@st.cache_data(ttl=120, show_spinner=False)
def _leer_tabla_precios(hoja: str) -> dict:
    """
    Lee una hoja de precios y retorna dict:
      {(lista_lower, producto_lower): precio_float}
    """
    from gsheets import ws as _ws
    result = {}
    try:
        rows = _ws(hoja).get_all_values()
        for row in rows[1:]:          # skip header
            if len(row) < 3: continue
            lista = str(row[0]).strip()
            prod  = str(row[1]).strip()
            try:
                precio = float(str(row[2]).replace(",","").strip() or 0)
            except Exception:
                continue
            if lista and prod and precio > 0:
                result[(lista.lower(), prod.lower())] = precio
    except Exception:
        pass
    return result


def cli_precio(cliente: dict, producto_nombre: str) -> tuple[float, str]:
    """
    Cascada 4 niveles: cliente → grupo → zona → general.
    Retorna (precio, fuente).
    """
    prod_lower = producto_nombre.lower().strip()
    if not prod_lower:
        return 0.0, "general"

    cod        = str(cliente.get("codigo_lugar", "") or "").strip()
    grupo      = str(cliente.get("grupo", "") or "").strip()
    nombre_cli = str(cliente.get("nombre", "") or "").strip()

    # Zona key para PreciosZona
    zona_key = None
    if cod == "L20":
        zona_key = "hogares"
    elif cod in ("L03", "L04"):
        zona_key = "antigua"

    tab_cli  = _leer_tabla_precios("preciosclient")
    tab_grp  = _leer_tabla_precios("preciosgrupo")
    tab_zona = _leer_tabla_precios("precioszona")

    # 1. Cliente individual
    if nombre_cli:
        v = tab_cli.get((nombre_cli.lower(), prod_lower))
        if v: return float(v), "cliente"

    # 2. Grupo
    if grupo:
        v = tab_grp.get((grupo.lower(), prod_lower))
        if v: return float(v), "grupo"

    # 3. Zona
    if zona_key:
        v = tab_zona.get((zona_key, prod_lower))
        if v: return float(v), "zona"

    # 4. General — catálogo
    try:
        from excel_helper import leer_productos_con_fila
        es_ant = cliente.get("es_antigua", False)
        for p in leer_productos_con_fila(es_antigua=bool(es_ant)):
            if p["nombre"].lower().strip() == prod_lower:
                return float(p.get("precio") or 0), "general"
    except Exception:
        pass

    return 0.0, "general"


def limpiar_cache_precios():
    """Limpia caches de todas las tablas de precios especiales."""
    _leer_tabla_precios.clear()


# ── ESCRITURA EN TABLAS DE PRECIOS ESPECIALES ─────────────────────────────────
_GRUPOS_VALIDOS = {"italianos","chimaltecos","italianos2","porqueno"}
_ZONAS_VALIDAS  = {"antigua","hogares"}

def guardar_precio_especial(hoja_key: str, lista: str,
                             producto: str, precio: float) -> bool:
    """
    Agrega o actualiza una fila en PreciosZona/Grupo/Cliente.
    hoja_key: 'precioszona' | 'preciosgrupo' | 'preciosclient'
    Retorna True si OK.
    """
    from gsheets import ws as _ws, get_all_rows
    try:
        sheet = _ws(hoja_key)
        rows  = get_all_rows(hoja_key)
        lista_l = lista.strip().lower()
        prod_l  = producto.strip().lower()
        for i, row in enumerate(rows, start=2):
            if len(row) < 2: continue
            if (str(row[0]).strip().lower() == lista_l and
                    str(row[1]).strip().lower() == prod_l):
                sheet.update(f"C{i}", [[precio]])
                _leer_tabla_precios.clear()
                return True
        sheet.append_rows([[lista.strip(), producto.strip(), precio]])
        _leer_tabla_precios.clear()
        return True
    except Exception:
        return False


def eliminar_precio_especial(hoja_key: str, lista: str,
                              producto: str) -> bool:
    """Elimina la fila de precio especial para lista+producto."""
    from gsheets import ws as _ws, delete_rows, get_all_rows
    try:
        rows  = get_all_rows(hoja_key)
        lista_l = lista.strip().lower()
        prod_l  = producto.strip().lower()
        to_del = []
        for i, row in enumerate(rows, start=2):
            if len(row) < 2: continue
            if (str(row[0]).strip().lower() == lista_l and
                    str(row[1]).strip().lower() == prod_l):
                to_del.append(i)
        if to_del:
            delete_rows(hoja_key, to_del)
            _leer_tabla_precios.clear()
            return True
        return False
    except Exception:
        return False


@st.cache_data(ttl=120, show_spinner=False)
def leer_precios_capa(hoja_key: str, lista: str) -> list[dict]:
    """Retorna [{producto, precio}] para una capa dada."""
    from gsheets import ws as _ws
    result = []
    try:
        rows = _ws(hoja_key).get_all_values()[1:]
        lista_l = lista.strip().lower()
        for row in rows:
            if len(row) < 3: continue
            if str(row[0]).strip().lower() != lista_l: continue
            try:
                precio = float(str(row[2]).replace(",","").strip() or 0)
            except Exception:
                continue
            if row[1].strip() and precio > 0:
                result.append({"producto": row[1].strip(), "precio": precio})
    except Exception:
        pass
    return result
