"""
order_helper.py — Guardar y editar pedidos via Google Sheets.
"""
import streamlit as st
from datetime import date, datetime, timedelta
from gsheets import append_rows, update_cells, get_all_rows
from excel_helper import leer_pedidos, leer_pedidos_op, DIAS_ES, MESES_N, _sf
from config import margen_neto_q, margen_neto_frac, iva_incluido

_K_PED = "pedidos"

TOTAL_COLS = 31


def _clear_pedidos_cache():
    """Invalida la caché tras escribir pedidos. Usa el refresco central para
    que también se refresquen precios (evita el bug de precios inconsistentes
    al editar/agregar líneas)."""
    leer_pedidos.clear()
    leer_pedidos_op.clear()
    try:
        from data_helper import refrescar_datos
        refrescar_datos(pedidos=True, productos=False, clientes=False, precios=True)
    except Exception:
        pass


def _calcular(precio: float, costo: float, cant: float) -> dict:
    if precio <= 0:
        return dict(total=0, total_costo=0, margen_q=0,
                    margen_pct=0, iva=0, isr=0)
    return {
        "total":       round(precio * cant, 4),
        "total_costo": round(costo  * cant, 4),
        "margen_q":    round(margen_neto_q(costo, precio) * cant, 4),
        # OJO: margen_pct acá es una FRACCIÓN (0–1), no un porcentaje.
        "margen_pct":  round(margen_neto_frac(costo, precio), 4)
                       if precio > 0 else 0,
        "iva":         round(iva_incluido(precio) * cant, 4),
        "isr":         0,
    }


# ── Escritura coherente de líneas de pedido ───────────────────────────────────
# Layout de Pedidos: E=Precio F=Costo G=Total H=TotalCosto I=MargenQ J=Margen%
# K=IVA. Estas funciones son la fuente ÚNICA de cómo queda escrita una línea
# cuando cambia su costo o su precio. Todas las rutas que tocan pedidos pasan
# por acá, así ninguna puede volver a dejar la fila incoherente consigo misma.

def semana_en_curso(hoy: date = None) -> tuple:
    """(lunes, domingo) de la semana en curso — la semana ISO, como rango.

    Se expresa en fechas y no como (nro_semana, año) porque ese par se rompe en
    el cambio de año: la columna Semana guardada combina semana ISO con año
    CALENDARIO, así que el 31/12 y el 01/01 de la MISMA semana ISO quedan con
    años distintos y comparar por número deja media semana afuera.
    """
    hoy = hoy or date.today()
    lunes = hoy - timedelta(days=hoy.weekday())
    return lunes, lunes + timedelta(days=6)


def celdas_linea(row_num: int, cantidad: float, precio: float, costo: float,
                 *, escribir_precio: bool = False) -> list:
    """Updates de UNA línea de pedido, con todos los derivados coherentes.

    `precio` y `costo` son los valores que van a QUEDAR en la fila; el llamador
    ya resolvió cuál corresponde. E solo se escribe si escribir_precio=True —
    por defecto no, para no pisar precios negociados por cliente/grupo/zona
    (ver data_helper.cli_precio). F, G, H, I, J y K se recalculan siempre sobre
    esos dos valores, que es lo que garantiza que la fila cierre consigo misma.
    """
    fin = _calcular(precio, costo, cantidad)
    ups = []
    if escribir_precio:
        ups.append({"range": f"E{row_num}", "values": [[precio]]})
    ups += [
        {"range": f"F{row_num}", "values": [[costo]]},
        {"range": f"G{row_num}", "values": [[fin["total"]]]},
        {"range": f"H{row_num}", "values": [[fin["total_costo"]]]},
        {"range": f"I{row_num}", "values": [[fin["margen_q"]]]},
        {"range": f"J{row_num}", "values": [[fin["margen_pct"]]]},
        {"range": f"K{row_num}", "values": [[fin["iva"]]]},
    ]
    return ups


def propagar_costo_semana(nuevos_costos: dict, hoy: date = None) -> int:
    """Aplica el costo nuevo a TODAS las líneas de la semana en curso.

    nuevos_costos: {nombre_producto_en_minúsculas: costo}. Todas las líneas de
    esos productos con fecha entre lunes y domingo de la semana en curso quedan
    con el costo nuevo, incluidas las de días anteriores de esa misma semana.

    El precio de venta NO se toca; los derivados se recalculan con el precio
    que ya tenía cada línea.

    Devuelve la cantidad de líneas actualizadas.
    """
    if not nuevos_costos:
        return 0

    lunes, domingo = semana_en_curso(hoy)
    updates, afectados = [], 0

    for p in leer_pedidos():
        prod_l = str(p.get("producto", "")).strip().lower()
        if prod_l not in nuevos_costos:
            continue
        fecha = p.get("fecha")
        if not fecha or not (lunes <= fecha <= domingo):
            continue
        updates += celdas_linea(
            p["row_num"], float(p.get("cantidad") or 0),
            float(p.get("precio") or 0),              # el de la LÍNEA
            float(nuevos_costos[prod_l]))
        afectados += 1

    if updates:
        update_cells("pedidos", updates)
        try:
            from data_helper import refrescar_datos
            _errs = refrescar_datos(pedidos=True, productos=False,
                                    clientes=False, precios=True)
            if _errs:
                st.warning("Los pedidos se actualizaron, pero no se pudo "
                           f"refrescar parte de la caché: {'; '.join(_errs)}")
        except Exception as e:
            st.warning(f"Los pedidos se actualizaron, pero no se pudo refrescar "
                       f"la caché ({e}). Recargá la página para verlos.")
    return afectados


def _codigo_cliente(nombre: str) -> str:
    rows = get_all_rows("clientes")
    for row in rows:
        if str(row[0] or "").strip().lower() == nombre.strip().lower():
            return str(row[9] if len(row) > 9 else "XX")
    return "XX"


def _build_row(nombre_cliente: str, fecha_entrega: date,
               item: dict, unico: str) -> list:
    """Construye la fila completa de 31 columnas para Pedidos en Sheets."""
    precio = _sf(item.get("precio", 0))
    costo  = _sf(item.get("costo",  0))
    cant   = _sf(item.get("cantidad", 0))
    fin    = _calcular(precio, costo, cant)

    mes = fecha_entrega.month
    row = [""] * TOTAL_COLS

    row[0]  = fecha_entrega.strftime("%d/%m/%Y")   # A: Fecha
    row[1]  = nombre_cliente                         # B: Cliente
    row[2]  = cant                                   # C: Cantidad
    row[3]  = item.get("nombre", "")                 # D: Producto
    row[4]  = precio                                 # E: Precio
    row[5]  = costo                                  # F: Costo
    row[6]  = fin["total"]                           # G: Total
    row[7]  = fin["total_costo"]                     # H: TotalCosto
    row[8]  = fin["margen_q"]                        # I: MargenQ
    row[9]  = fin["margen_pct"]                      # J: Margen%
    row[10] = fin["iva"]                             # K: IVA
    row[11] = fin["isr"]                             # L: ISR
    row[12] = DIAS_ES[fecha_entrega.weekday()]       # M: DiaSemana
    row[13] = mes                                    # N: Mes
    row[14] = fecha_entrega.isocalendar()[1]         # O: Semana
    row[15] = fecha_entrega.year                     # P: Año
    row[16] = item.get("unidad", "")                 # Q: Unidad
    # R-Y: campos opcionales, dejar vacíos
    row[25] = MESES_N[mes - 1]                      # Z: MesN
    row[26] = f"{mes:02d}"                           # AA: MesNN
    row[27] = unico                                  # AB: Unico
    row[30] = "Pendiente"                            # AE: Status
    return row


def guardar_pedido(nombre_cliente: str, fecha_entrega: date,
                   items: list) -> dict:
    return guardar_pedidos_batch([{
        "cliente_nombre": nombre_cliente,
        "fecha":          fecha_entrega,
        "items":          items,
    }])


def guardar_pedidos_batch(cola: list) -> dict:
    """Graba N pedidos en UN SOLO request a Sheets."""
    if not cola:
        return {"pedidos": 0, "filas": 0}

    total_filas = 0
    all_rows    = []

    for pedido in cola:
        nombre   = pedido["cliente_nombre"]
        fecha    = pedido["fecha"]
        items    = pedido["items"]

        # Si viene un "unico" explícito (ej. al agregar líneas a un pedido YA
        # existente), respetarlo para que la línea se agrupe con ese pedido.
        # Solo generamos uno nuevo cuando NO se pasa (pedido nuevo de cero).
        unico = pedido.get("unico")
        if not unico:
            cod   = _codigo_cliente(nombre)
            mes   = fecha.month
            sem   = fecha.isocalendar()[1]
            unico = f"{cod}{fecha.day:02d}{mes:02d}{sem:02d}{fecha.year}"

        for item in items:
            if not item.get("nombre") or _sf(item.get("cantidad")) <= 0:
                continue
            all_rows.append(_build_row(nombre, fecha, item, unico))
            total_filas += 1

    if all_rows:
        append_rows(_K_PED, all_rows)
        _clear_pedidos_cache()

    return {"pedidos": len(cola), "filas": total_filas}


def guardar_edicion_pedidos(cambios: list,
                              nuevas: list = None,
                              filas_eliminar: list = None) -> dict:
    """
    Edita, agrega y elimina líneas de pedidos en un solo ciclo.
    cambios:         [{row_num, producto_nuevo, cantidad_nueva, precio_nuevo, ...}]
    nuevas:          [{unico, cliente_nombre, fecha, items}]
    filas_eliminar:  [row_num, ...]
    """
    upd = []

    # ── Editar líneas existentes ──────────────────────────────────────────────
    for ch in cambios:
        rn = ch["row_num"]
        if "producto_nuevo" in ch:
            upd.append({"range": f"D{rn}", "values": [[ch["producto_nuevo"]]]})
        if "unidad_nueva" in ch:
            upd.append({"range": f"Q{rn}", "values": [[ch["unidad_nueva"]]]})
        if "cantidad_nueva" in ch or "precio_nuevo" in ch or "costo_nuevo" in ch:
            cant  = _sf(ch.get("cantidad_nueva") or ch.get("_cant_actual", 0))
            prec  = _sf(ch.get("precio_nuevo")   or ch.get("_prec_actual", 0))
            cost  = _sf(ch.get("costo_nuevo")    or ch.get("_costo_actual", 0))
            fin   = _calcular(prec, cost, cant)
            # Los TOTALES se recalculan SIEMPRE que cambie cantidad, precio o
            # costo (antes solo con cantidad → total desactualizado al cambiar
            # precio, y Facturación sumaba montos viejos).
            if "cantidad_nueva" in ch:
                upd.append({"range": f"C{rn}", "values": [[cant]]})
            if "precio_nuevo" in ch:
                upd.append({"range": f"E{rn}", "values": [[prec]]})
            if "costo_nuevo" in ch:
                upd.append({"range": f"F{rn}", "values": [[cost]]})
            upd += [
                {"range": f"G{rn}", "values": [[fin["total"]]]},
                {"range": f"H{rn}", "values": [[fin["total_costo"]]]},
                {"range": f"I{rn}", "values": [[fin["margen_q"]]]},
                {"range": f"J{rn}", "values": [[fin["margen_pct"]]]},
            ]

    if upd:
        try:
            update_cells(_K_PED, upd)
        except Exception as e:
            raise RuntimeError(f"Error al guardar en Sheets: {e}") from e

    # ── Agregar líneas nuevas ─────────────────────────────────────────────────
    filas_nuevas = 0
    if nuevas:
        res = guardar_pedidos_batch(nuevas)
        filas_nuevas = res.get("filas", 0)

    # ── Eliminar filas ────────────────────────────────────────────────────────
    filas_elim = 0
    if filas_eliminar:
        from gsheets import delete_rows
        delete_rows(_K_PED, filas_eliminar)
        filas_elim = len(filas_eliminar)

    if upd or filas_nuevas or filas_elim:
        _clear_pedidos_cache()

    return {
        "ediciones":   len(cambios),
        "nuevas_filas":filas_nuevas,
        "eliminadas":  filas_elim,
    }
