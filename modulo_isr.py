"""
modulo_isr.py — ISR mensual a pagar.

Reporte de SOLO LECTURA: no escribe nada en el Sheet.

    Base        = Σ (total_del_pedido / 1.12) de los clientes que APLICAN
    ISR total   = 5% × min(Base, 30,000) + 7% × max(0, Base − 30,000)
    Ya retenido = 5% × Σ (total / 1.12) de los que APLICAN **y** RETIENEN
    A pagar     = ISR total − Ya retenido

Los dos campos del cliente son INDEPENDIENTES y no simétricos:

  · "Aplica ISR" decide quién entra a la Base.
  · "Retiene ISR" solo sirve para descontar, y únicamente en clientes que
    además aplican. Un cliente que retiene pero NO aplica queda totalmente
    afuera: no suma a la Base ni su retención se descuenta.

Nada se asume. Un cliente sin el dato cargado va a `pendientes` y un nombre de
pedido que no existe en el catálogo va a `sin_match`; ninguno de los dos entra
al cálculo, y los dos se muestran en pantalla para poder auditarlos.

Sin lógica de estados: los pedidos cancelados se borran de la hoja.
"""
import streamlit as st
import pandas as pd
from datetime import date

from config       import base_sin_iva, excluido_proveedores as _excluido
from excel_helper import leer_pedidos_op as leer_pedidos

# ── Parámetros fiscales ───────────────────────────────────────────────────────
# Nombrados para que se vean y se puedan cambiar en un solo lugar. El tramo se
# evalúa sobre la base MENSUAL total, no por cliente ni por factura.
ISR_TRAMO_LIMITE = 30000.0
ISR_TASA_BAJA    = 0.05
ISR_TASA_ALTA    = 0.07

# Columnas de la hoja Clientes (0-based, tal como las devuelve get_all_rows,
# que YA viene sin encabezado).
_COL_NOMBRE  = 0    # A
_COL_RETIENE = 14   # O
_COL_APLICA  = 16   # Q

_VAL_SI = ("sí", "si", "s", "yes", "y", "true", "verdadero", "1", "x")
_VAL_NO = ("no", "n", "false", "falso", "0")

MESES_ES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
            "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def _tri(valor) -> bool:
    """'Sí'/'No'/vacío → True/False/None.

    Un valor que no se reconoce devuelve None (pendiente), NO False. En un
    cálculo fiscal un dato que no se entiende tiene que verse, no asumirse:
    si alguien escribe "Pendiente" o "?" en la celda, eso no es un "No".
    """
    t = str(valor if valor is not None else "").strip().lower()
    if not t:
        return None
    if t in _VAL_SI:
        return True
    if t in _VAL_NO:
        return False
    return None


def _celda(row: list, i: int):
    """Celda i de una fila, o '' si la fila viene corta.

    Sheets recorta las celdas vacías del final, así que un cliente sin nada en
    la Q puede llegar con una fila de 15 elementos.
    """
    return row[i] if len(row) > i else ""


@st.cache_data(ttl=600, show_spinner=False)
def leer_clientes_isr() -> dict:
    """{nombre_lower: {'nombre', 'aplica', 'retiene'}} desde la hoja Clientes.

    Lee la hoja directo en vez de usar data_helper.cargar_clientes porque esa
    hace `while len(row) < 16` y corta en la columna P: no ve la Q, que es
    donde vive aplica_isr. get_all_rows ya está cacheado, así que esto no suma
    una llamada a la red.

    DEUDA CONOCIDA: cuando este módulo encuentre su lugar en la app, aplica_isr
    debería subir a cargar_clientes y esta función desaparecer. Vive acá para
    no tocar módulos existentes todavía.
    """
    from gsheets import get_all_rows
    out = {}
    for row in get_all_rows("clientes"):          # ya viene sin encabezado
        nombre = str(_celda(row, _COL_NOMBRE) or "").strip()
        if not nombre:
            continue
        out[nombre.lower()] = {
            "nombre":  nombre,
            "aplica":  _tri(_celda(row, _COL_APLICA)),
            "retiene": _tri(_celda(row, _COL_RETIENE)),
        }
    return out


def calcular_isr(pedidos: list, clientes: dict, mes: int, año: int) -> dict:
    """El cálculo completo del mes. Función pura: no lee ni escribe nada.

    pedidos:  líneas de pedido (leer_pedidos_op)
    clientes: lo que devuelve leer_clientes_isr()
    """
    # Paso 1: facturación sin IVA por cliente, del mes pedido.
    facturado, desconocidos = {}, {}
    for p in pedidos:
        f = p.get("fecha")
        if not f or f.month != mes or f.year != año:
            continue
        nombre = str(p.get("cliente", "") or "").strip()
        if not nombre or _excluido(nombre):
            continue
        base = base_sin_iva(float(p.get("total") or 0))
        clave = nombre.lower()
        if clave in clientes:
            facturado[clave] = facturado.get(clave, 0.0) + base
        else:
            # No está en el catálogo: no se adivina si aplica. Se reporta.
            desconocidos[nombre] = desconocidos.get(nombre, 0.0) + base

    # Paso 2: separar según los dos campos.
    base_total = ya_retenido = 0.0
    detalle, pendientes = [], []
    for clave, monto in facturado.items():
        c = clientes[clave]
        aplica, retiene = c["aplica"], c["retiene"]

        if aplica is None or retiene is None:
            pendientes.append({
                "Cliente": c["nombre"],
                "Aplica ISR":  _etiqueta(aplica),
                "Retiene ISR": _etiqueta(retiene),
                "Facturado sin IVA (Q)": round(monto, 2),
            })
        if aplica is not True:
            # No aplica (o falta el dato): fuera de la Base. Su retención NO se
            # descuenta aunque retenga — los campos no son simétricos.
            continue

        base_total += monto
        if retiene is True:
            ya_retenido += ISR_TASA_BAJA * monto

    # Paso 3: el tramo se aplica sobre la base TOTAL del mes.
    isr_total = (ISR_TASA_BAJA * min(base_total, ISR_TRAMO_LIMITE)
                 + ISR_TASA_ALTA * max(0.0, base_total - ISR_TRAMO_LIMITE))

    # Paso 4: detalle por cliente. El aporte al ISR se PRORRATEA por la
    # participación de cada uno en la base, porque el tramo de Q30,000 se
    # calcula sobre el total del mes y no existe un ISR "por cliente".
    for clave, monto in sorted(facturado.items(),
                               key=lambda kv: -kv[1]):
        c = clientes[clave]
        aplica, retiene = c["aplica"], c["retiene"]
        en_base = (aplica is True)
        aporte  = (isr_total * monto / base_total) if (en_base and base_total) else 0.0
        detalle.append({
            "Cliente":     c["nombre"],
            "Aplica ISR":  _etiqueta(aplica),
            "Retiene ISR": _etiqueta(retiene),
            "Facturado sin IVA (Q)": round(monto, 2),
            "Aporte ISR (Q)":        round(aporte, 2),
            "Ya retenido (Q)":       round(ISR_TASA_BAJA * monto, 2)
                                     if (en_base and retiene is True) else 0.0,
        })

    return {
        "base":        round(base_total, 2),
        "isr_total":   round(isr_total, 2),
        "ya_retenido": round(ya_retenido, 2),
        "a_pagar":     round(isr_total - ya_retenido, 2),
        "detalle":     detalle,
        "pendientes":  sorted(pendientes, key=lambda d: -d["Facturado sin IVA (Q)"]),
        "sin_match":   sorted(({"Cliente": n, "Facturado sin IVA (Q)": round(v, 2)}
                               for n, v in desconocidos.items()),
                              key=lambda d: -d["Facturado sin IVA (Q)"]),
    }


def _etiqueta(v) -> str:
    """True/False/None → texto para la tabla. None se ve, no se disfraza."""
    return "Sí" if v is True else ("No" if v is False else "— sin dato")


def meses_disponibles(pedidos: list) -> list:
    """[(año, mes)] con pedidos, del más reciente al más viejo."""
    vistos = {(p["fecha"].year, p["fecha"].month)
              for p in pedidos if p.get("fecha")}
    return sorted(vistos, reverse=True)


# ── Pantalla ──────────────────────────────────────────────────────────────────
def mostrar():
    st.markdown("## 🧾 ISR Mensual a Pagar")
    if st.button("🏠 Inicio", key="btn_home_isr", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    st.caption(f"Base sin IVA × tramos: {ISR_TASA_BAJA:.0%} hasta "
               f"Q{ISR_TRAMO_LIMITE:,.0f} y {ISR_TASA_ALTA:.0%} sobre el "
               f"excedente, menos lo que ya retuvieron los clientes. "
               f"Solo lectura: no modifica el Sheet.")

    with st.spinner("Cargando pedidos..."):
        pedidos  = leer_pedidos()
        clientes = leer_clientes_isr()

    disp = meses_disponibles(pedidos)
    if not disp:
        st.info("No hay pedidos cargados.")
        return

    etiquetas = [f"{MESES_ES[m - 1]} {a}" for a, m in disp]
    sel = st.selectbox("Mes", etiquetas, index=0, key="isr_mes")
    año, mes = disp[etiquetas.index(sel)]

    res = calcular_isr(pedidos, clientes, mes, año)

    if res["base"] <= 0:
        st.info(f"Ningún cliente con «Aplica ISR = Sí» facturó en "
                f"{MESES_ES[mes - 1]} {año}.")

    m1, m2, m3 = st.columns(3)
    m1.metric("Base facturada (sin IVA)", f"Q{res['base']:,.2f}")
    m2.metric("ISR total calculado",      f"Q{res['isr_total']:,.2f}")
    m3.metric("Ya retenido",              f"Q{res['ya_retenido']:,.2f}")

    _color = "#c62828" if res["a_pagar"] > 0 else "#2D7A2D"
    st.markdown(
        f"<div style='background:#e8f5e9;border-left:6px solid {_color};"
        f"border-radius:8px;padding:14px 18px;margin:10px 0'>"
        f"<div style='font-size:.85rem;color:#555'>A PAGAR "
        f"({MESES_ES[mes - 1]} {año})</div>"
        f"<div style='font-size:2.1rem;font-weight:700;color:{_color}'>"
        f"Q{res['a_pagar']:,.2f}</div></div>",
        unsafe_allow_html=True)

    if res["base"] > ISR_TRAMO_LIMITE:
        _exc = res["base"] - ISR_TRAMO_LIMITE
        st.caption(f"La base pasó el tramo: Q{ISR_TRAMO_LIMITE:,.2f} al "
                   f"{ISR_TASA_BAJA:.0%} y Q{_exc:,.2f} al "
                   f"{ISR_TASA_ALTA:.0%}.")

    # ── Detalle auditable ────────────────────────────────────────────────────
    st.markdown("#### Detalle por cliente")
    df = pd.DataFrame(res["detalle"])
    if df.empty:
        st.info("Sin facturación en el mes.")
        return
    _num = st.column_config.NumberColumn
    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config={c: _num(format="%.2f") for c in
                                ("Facturado sin IVA (Q)", "Aporte ISR (Q)",
                                 "Ya retenido (Q)")})
    st.caption(f"El **Aporte ISR** está prorrateado por la participación de "
               f"cada cliente en la base — el tramo de Q{ISR_TRAMO_LIMITE:,.0f} "
               f"se calcula sobre el total del mes, no por cliente. La suma de "
               f"la columna da el ISR total.")

    if res["pendientes"]:
        st.warning(f"⚠️ **{len(res['pendientes'])} cliente(s) sin el dato "
                   f"cargado.** No entran al cálculo. Completá «Aplica ISR» y "
                   f"«Retiene ISR» en la ficha del cliente y volvé a mirar "
                   f"este número.")
        st.dataframe(pd.DataFrame(res["pendientes"]),
                     use_container_width=True, hide_index=True)

    if res["sin_match"]:
        _t = sum(d["Facturado sin IVA (Q)"] for d in res["sin_match"])
        st.warning(f"⚠️ **{len(res['sin_match'])} nombre(s) en pedidos que no "
                   f"están en el catálogo de Clientes** (Q{_t:,.2f} sin IVA). "
                   f"No entran al cálculo: puede ser un nombre mal escrito.")
        st.dataframe(pd.DataFrame(res["sin_match"]),
                     use_container_width=True, hide_index=True)

    # ── Exportación e impresión ──────────────────────────────────────────────
    filtros = f"{MESES_ES[mes - 1]} {año}"
    b1, b2 = st.columns(2)
    csv_df = pd.concat([df, pd.DataFrame([{
        "Cliente": "TOTAL", "Aplica ISR": "", "Retiene ISR": "",
        "Facturado sin IVA (Q)": res["base"],
        "Aporte ISR (Q)":        res["isr_total"],
        "Ya retenido (Q)":       res["ya_retenido"]}])], ignore_index=True)
    b1.download_button(
        "📥 Descargar CSV",
        data=csv_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"isr_{año}{mes:02d}.csv", mime="text/csv",
        key="isr_csv", use_container_width=True)

    with b2:
        if st.button("🖨 Preparar impresión", key="isr_pdf",
                     use_container_width=True):
            import streamlit.components.v1 as components
            from pdf_helper import generar_pdf_reporte, boton_imprimir_html
            _ini = date(año, mes, 1)
            _fin = (date(año + (mes == 12), (mes % 12) + 1, 1)
                    - __import__("datetime").timedelta(days=1))
            with st.spinner("Generando PDF..."):
                pdf = generar_pdf_reporte(
                    "ISR Mensual a Pagar",
                    ["Cliente", "Aplica", "Retiene", "Facturado s/IVA (Q)",
                     "Aporte ISR (Q)", "Ya retenido (Q)"],
                    [[d["Cliente"], d["Aplica ISR"], d["Retiene ISR"],
                      f"{d['Facturado sin IVA (Q)']:,.2f}",
                      f"{d['Aporte ISR (Q)']:,.2f}",
                      f"{d['Ya retenido (Q)']:,.2f}"] for d in res["detalle"]],
                    _ini, _fin, filtros_txt=filtros,
                    fila_total=["TOTAL", "", "", f"{res['base']:,.2f}",
                                f"{res['isr_total']:,.2f}",
                                f"{res['ya_retenido']:,.2f}"],
                    anchos=[0.28, 0.10, 0.10, 0.18, 0.17, 0.17],
                    alinear_der=(3, 4, 5),
                    pie=f"A PAGAR: Q{res['a_pagar']:,.2f}")
            components.html(boton_imprimir_html(pdf, "repisr",
                                                label="🖨 Abrir e imprimir"),
                            height=60)
