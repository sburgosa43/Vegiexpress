"""
data_helper.py — Caché de clientes y productos via Google Sheets.
"""
import streamlit as st
from gsheets import get_all_rows
from excel_helper import _sf, _si

_K_CLI  = "clientes"
_K_PROD = "productos"
_K_ANT  = "antigua"


@st.cache_data(ttl=600, show_spinner=False)
def cargar_clientes() -> list[dict]:
    """Lista completa de clientes desde Sheets."""
    rows = get_all_rows(_K_CLI)
    clientes = []
    for i, row in enumerate(rows, start=2):
        while len(row) < 16: row.append("")
        if not row[0]: continue
        # Tratamiento comercial (columnas N/O/P) — Fase A de centralización.
        # Si están vacías (aún no migrado), quedan como None y los módulos usan
        # su fuente vieja como fallback.
        _lag_raw  = str(row[13]).strip()
        _isr_raw  = str(row[14]).strip()
        _desc_raw = str(row[15]).strip()
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
            # Tratamiento comercial centralizado (None si aún no migrado)
            "lag_pago":     (int(float(_lag_raw)) if _lag_raw not in ("", "None") else None),
            "retiene_isr":  (_isr_raw.lower() in ("sí","si","yes","true","1") if _isr_raw not in ("", "None") else None),
            "descuento_pct":(float(_desc_raw) if _desc_raw not in ("", "None") else None),
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
        while len(row) < 24: row.append("")
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
            "empacado":       str(row[23] if not es_antigua else "").strip(),
            "cotizar":        cotizar,
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


# ── Invalidación central de caché ─────────────────────────────────────────────
def refrescar_datos(pedidos=True, productos=True, clientes=False, precios=True):
    """Invalida las cachés de lectura tras una escritura, para que los cambios
    se reflejen de inmediato SIN necesidad de reboot ni limpiar caché a mano.

    Llamar SIEMPRE después de guardar/editar pedidos, precios o productos.
    Los flags permiten limpiar solo lo necesario (más rápido), pero por
    defecto refresca lo más común (pedidos, productos y precios).
    """
    errores = []

    if pedidos:
        try:
            from excel_helper import leer_pedidos, leer_pedidos_op
            leer_pedidos.clear()
            leer_pedidos_op.clear()
        except Exception as e:
            errores.append(f"pedidos: {e}")

    if productos:
        try:
            from excel_helper import leer_productos_con_fila, costo_ultima_actualizacion
            leer_productos_con_fila.clear()
            costo_ultima_actualizacion.clear()
            cargar_productos.clear()
        except Exception as e:
            errores.append(f"productos: {e}")

    if clientes:
        try:
            cargar_clientes.clear()
        except Exception as e:
            errores.append(f"clientes: {e}")

    if precios:
        try:
            _leer_tabla_precios.clear()
            leer_precios_capa.clear()
        except Exception as e:
            errores.append(f"precios: {e}")

    return errores


# ── FASE A: Centralización del tratamiento comercial en la ficha del cliente ──
# Amplía la hoja Clientes con columnas de tratamiento (lag, ISR, descuento) y
# migra los valores actuales desde config.py. Idempotente: si ya migró, no pisa
# los ajustes que hayas hecho manualmente después.

# Columnas nuevas (índices 0-based en la hoja Clientes):
#   N (13) = lag_pago
#   O (14) = retiene_isr   ("Sí"/"No")
#   P (15) = descuento_pct
_COL_LAG   = 13   # N
_COL_ISR   = 14   # O
_COL_DESC  = 15   # P
_TRATO_HEADERS = {13: "lag_pago", 14: "retiene_isr", 15: "descuento_pct"}

# Lags conocidos de la migración original (config.py + ReglasPago inicial).
# Se migran una sola vez; después se editan desde la ficha del cliente.
_LAGS_MIGRACION = {
    "aldyk": 3, "4 pinos": 1, "nanajuana": 1, "tijax": 1,
    "amis": 1, "hotelito": 0, "sundog": 0,
}


def _trato_migrado_para(nombre: str) -> dict:
    """Calcula el tratamiento comercial inicial de un cliente desde las reglas
    de config.py. Se usa solo en la migración."""
    from config import ISR_EXENTOS, DESCUENTO_15
    n = nombre.lower().strip()

    # ISR: exento si está en la lista → "No" retiene; si no → "Sí"
    retiene_isr = "No" if any(e in n for e in ISR_EXENTOS) else "Sí"

    # Descuento: 15 si está en DESCUENTO_15, si no 0
    descuento = 15 if any(dd in n for dd in DESCUENTO_15) else 0

    # Lag: buscar en el mapa de migración; default 0
    lag = 0
    for key, v in _LAGS_MIGRACION.items():
        if key in n:
            lag = v
            break

    return {"lag_pago": lag, "retiene_isr": retiene_isr, "descuento_pct": descuento}


def migrar_trato_clientes(forzar: bool = False) -> dict:
    """Amplía la hoja Clientes con columnas de tratamiento y migra los valores.

    - Agrega encabezados en N1/O1/P1 si faltan.
    - Para cada cliente, si la celda de tratamiento está VACÍA, la puebla con el
      valor migrado. Si ya tiene valor (porque lo ajustaste), NO lo pisa —salvo
      forzar=True.

    Retorna {"clientes": N, "poblados": M, "ya_tenian": K}.
    """
    from gsheets import get_all_rows, update_cells

    rows = get_all_rows(_K_CLI)
    if not rows:
        return {"clientes": 0, "poblados": 0, "ya_tenian": 0, "error": "hoja vacía"}

    # 1. Asegurar encabezados de las columnas nuevas (fila 1)
    updates = []
    # get_all_rows normalmente NO incluye la fila de encabezado; la escribimos directo
    for col_idx, header in _TRATO_HEADERS.items():
        col_letter = _idx_a_letra(col_idx)
        updates.append({"range": f"{col_letter}1", "values": [[header]]})

    # 2. Poblar cada cliente
    poblados = 0
    ya_tenian = 0
    fila = 2  # los datos empiezan en la fila 2
    for row in rows:
        if not row or not row[0]:
            fila += 1
            continue
        # Asegurar longitud
        while len(row) <= _COL_DESC:
            row.append("")

        nombre = str(row[0])
        trato = _trato_migrado_para(nombre)

        # lag_pago (N)
        if forzar or str(row[_COL_LAG]).strip() == "":
            updates.append({"range": f"N{fila}",
                            "values": [[trato["lag_pago"]]]})
            _poblo = True
        else:
            _poblo = False
        # retiene_isr (O)
        if forzar or str(row[_COL_ISR]).strip() == "":
            updates.append({"range": f"O{fila}",
                            "values": [[trato["retiene_isr"]]]})
            _poblo = True
        # descuento_pct (P)
        if forzar or str(row[_COL_DESC]).strip() == "":
            updates.append({"range": f"P{fila}",
                            "values": [[trato["descuento_pct"]]]})
            _poblo = True

        if _poblo:
            poblados += 1
        else:
            ya_tenian += 1
        fila += 1

    if updates:
        update_cells(_K_CLI, updates)   # con reintentos incorporados
        cargar_clientes.clear()

    return {"clientes": fila - 2, "poblados": poblados, "ya_tenian": ya_tenian}


def _idx_a_letra(idx0: int) -> str:
    """Convierte índice 0-based a letra de columna (0→A, 13→N)."""
    n = idx0 + 1
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


# ── FASE C: Fuente única del tratamiento comercial ────────────────────────────
def tratamiento_cliente(nombre: str) -> dict:
    """Fuente ÚNICA del tratamiento comercial de un cliente. Lee de la ficha
    del cliente (columnas N/O/P migradas). Si el cliente aún no tiene datos
    en la ficha (None), cae al fallback de config.py para no romper nada.

    Retorna: {"lag": int, "isr": bool, "desc": float}
    donde isr=True significa que el cliente RETIENE ISR (agente retenedor).
    """
    n = (nombre or "").strip().lower()

    # 1. Buscar en la ficha del cliente
    for c in cargar_clientes():
        cn = c["nombre"].strip().lower()
        # match por nombre contenido (igual criterio que las reglas viejas)
        if cn == n or cn in n or n in cn:
            lag  = c.get("lag_pago")
            isr  = c.get("retiene_isr")
            desc = c.get("descuento_pct")
            # Si la ficha tiene los datos migrados, usarlos
            if lag is not None and isr is not None:
                return {
                    "lag":  int(lag),
                    "isr":  bool(isr),
                    "desc": float(desc) if desc is not None else 0.0,
                }
            break  # encontró el cliente pero sin datos → fallback

    # 2. Fallback a config.py (clientes aún no migrados)
    try:
        from config import ISR_EXENTOS, DESCUENTO_15, REGLAS_PAGO
        lag = 0
        for key, r in REGLAS_PAGO.items():
            if key in n:
                lag = r["lag"]
                break
        isr  = not any(e in n for e in ISR_EXENTOS)
        desc = 15.0 if any(dd in n for dd in DESCUENTO_15) else 0.0
        return {"lag": lag, "isr": isr, "desc": desc}
    except Exception:
        return {"lag": 0, "isr": True, "desc": 0.0}
