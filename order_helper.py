"""
order_helper.py — Guardar y editar pedidos via Google Sheets.
"""
import streamlit as st
from datetime import date, datetime
from gsheets import append_rows, update_cells, get_all_rows
from excel_helper import leer_pedidos, DIAS_ES, MESES_N, _sf

_K_PED = "pedidos"

TOTAL_COLS = 31


def _clear_pedidos_cache():
    leer_pedidos.clear()


def _calcular(precio: float, costo: float, cant: float) -> dict:
    if precio <= 0:
        return dict(total=0, total_costo=0, margen_q=0,
                    margen_pct=0, iva=0, isr=0)
    return {
        "total":       round(precio * cant, 4),
        "total_costo": round(costo  * cant, 4),
        "margen_q":    round(0.95 * (precio - costo * 1.12) * cant, 4),
        "margen_pct":  round(0.95 * (1 - costo * 1.12 / precio), 4)
                       if precio > 0 else 0,
        "iva":         round((precio - precio / 1.12) * cant, 4),
        "isr":         0,
    }


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
        if "cantidad_nueva" in ch or "precio_nuevo" in ch:
            cant  = _sf(ch.get("cantidad_nueva", 0))
            prec  = _sf(ch.get("precio_nuevo",  0))
            cost  = _sf(ch.get("costo_nuevo",   0))
            fin   = _calcular(prec, cost, cant)
            if "cantidad_nueva" in ch:
                upd += [
                    {"range": f"C{rn}", "values": [[cant]]},
                    {"range": f"G{rn}", "values": [[fin["total"]]]},
                    {"range": f"H{rn}", "values": [[fin["total_costo"]]]},
                    {"range": f"I{rn}", "values": [[fin["margen_q"]]]},
                    {"range": f"J{rn}", "values": [[fin["margen_pct"]]]},
                ]
            if "precio_nuevo" in ch:
                upd.append({"range": f"E{rn}", "values": [[prec]]})
            if "costo_nuevo" in ch:
                upd.append({"range": f"F{rn}", "values": [[cost]]})

    if upd:
        update_cells(_K_PED, upd)

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
        "cambios":   len(cambios),
        "nuevas":    filas_nuevas,
        "eliminadas":filas_elim,
    }
