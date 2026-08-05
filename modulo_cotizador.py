"""
modulo_cotizador.py — Cotizador de precios
Calcula precios de venta aplicando IVA (12%) e ISR (5%).

Fórmulas base (las mismas del Listado Productos):
  Precio      = Costo × 1.12 / (1 - Margen% / (1 - ISR%))
  Margen Neto = (1 - ISR%) × (Precio - Costo × 1.12)
  %Margen     = Margen Neto / Precio
  Pto.Equil.  = Costo × 1.12  (menor precio sin perder ni ganar)
"""
import re

import streamlit as st
import pandas as pd

from config import (IVA_RATE, ISR_RATE, IVA_FACTOR, ISR_FACTOR,
                    margen_neto_pct, margen_neto_q, punto_equilibrio)


# ── CÁLCULOS ──────────────────────────────────────────────────────────────────

def _gasto_operativo(cantidad: float, mano_obra: float,
                     empaque: float, transporte: float) -> dict:
    """Gastos TOTALES del pedido → gasto por unidad.

    Los tres montos son del pedido completo, no por unidad: se suman y se
    reparten entre la cantidad cotizada.

    Cantidad en 0 (o gastos en 0) devuelve 0.0 por unidad, y entonces el costo
    real es el costo del producto y el cálculo queda idéntico al de siempre.
    Los gastos son un enriquecimiento opcional, no un requisito.

    `ignorado` marca el caso incómodo: hay gastos cargados pero no hay cantidad
    entre la cual repartirlos. No se descartan en silencio — la pantalla avisa.
    """
    mo    = max(0.0, float(mano_obra  or 0))
    emp   = max(0.0, float(empaque    or 0))
    tra   = max(0.0, float(transporte or 0))
    cant  = float(cantidad or 0)
    total = mo + emp + tra
    return {"cantidad": cant, "mano_obra": mo, "empaque": emp,
            "transporte": tra, "total": total,
            "por_unidad": (total / cant) if cant > 0 else 0.0,
            "ignorado":   total > 0 and cant <= 0}


def _desde_margen_pct(costo: float, margen_pct: float,
                      gastos: dict = None) -> dict | None:
    """Precio dado costo y margen neto deseado en %."""
    denom = 1 - margen_pct / ISR_FACTOR
    if denom <= 0 or costo <= 0:
        return None
    precio = costo * IVA_FACTOR / denom
    return _desglose(costo, precio, gastos)


def _desde_margen_q(costo: float, margen_q: float,
                    gastos: dict = None) -> dict | None:
    """Precio dado costo y margen neto deseado en Q."""
    if costo <= 0:
        return None
    precio = margen_q / ISR_FACTOR + costo * IVA_FACTOR
    return _desglose(costo, precio, gastos)


def _desglose(costo: float, precio: float,
              gastos: dict = None) -> dict | None:
    """Todos los campos derivados dado costo y precio de venta.

    Usa las fórmulas centralizadas de config.py para que un cambio de
    tasa (IVA/ISR) se refleje aquí automáticamente.

    `costo` es el costo unitario REAL: si el llamador incorporó gastos
    operativos, ya vienen adentro. `gastos` NO participa de ningún cálculo —
    solo arrastra el desglose hasta la pantalla, para que el Desglose Completo
    pueda mostrar de dónde sale ese costo sin volver a calcularlo. Con
    gastos=None el resultado es el de siempre, campo por campo.
    """
    if precio <= 0 or costo <= 0:
        return None
    precio_sin_iva = precio / IVA_FACTOR
    iva_amount     = precio - precio_sin_iva          # IVA = Precio - Precio/1.12
    isr_retencion  = precio_sin_iva * ISR_RATE        # ISR = (Precio/1.12) x 5%
    neto_recibido  = precio - isr_retencion           # Neto recibido despues de ISR
    mq             = margen_neto_q(costo, precio)
    mp             = margen_neto_pct(costo, precio)
    pto_eq         = punto_equilibrio(costo)
    sobre_costo    = ((precio - costo) / costo * 100) if costo else 0
    d = {
        "costo":           round(costo, 4),
        "precio":          round(precio, 4),
        "precio_sin_iva":  round(precio_sin_iva, 4),
        "iva_amount":      round(iva_amount, 4),
        "isr_retencion":   round(isr_retencion, 4),
        "neto_recibido":   round(neto_recibido, 4),
        "margen_neto_q":   round(mq, 4),
        "margen_neto_pct": round(mp, 2),
        "pto_equilibrio":  round(pto_eq, 4),
        "sobre_costo":     round(sobre_costo, 2),
        "rentable":        mq > 0,
    }
    if gastos:
        # El `costo` que entró YA es el real. Se guarda abierto para que el
        # Desglose muestre de dónde sale, sin recalcular nada.
        d["gastos"]         = gastos
        d["costo_producto"] = round(costo - gastos["por_unidad"], 4)
        d["gasto_unitario"] = round(gastos["por_unidad"], 4)
    return d


def _precio_cambiado(ajustado: float, sugerido: float) -> bool:
    """¿El usuario movió el precio, o es el sugerido tal cual?

    El input viene redondeado a 2 decimales y el sugerido se guarda con 4, así
    que compararlos con `!=` daba distinto SIEMPRE y el bloque de impacto
    aparecía aunque no se hubiera tocado nada. Media centésima de tolerancia
    alcanza: por debajo de eso no hay diferencia que mostrar.
    """
    return abs(float(ajustado) - float(sugerido)) > 0.005


# ── COMPONENTES UI ────────────────────────────────────────────────────────────

def _mostrar_resultado(d: dict, titulo: str = "Resultado"):
    color_card = "#e8f5e9" if d["rentable"] else "#ffebee"
    color_margen = "#2e7d32" if d["rentable"] else "#c62828"
    alerta = "" if d["rentable"] else "⚠️ Este precio está por debajo del punto de equilibrio."

    st.markdown(f"""
    <div style='background:{color_card};border-radius:8px;padding:14px 18px;margin:8px 0'>
        <h4 style='margin:0 0 10px 0'>{titulo}</h4>
        <div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px'>
            <div>
                <div style='font-size:.8rem;color:#555'>Precio de venta (con IVA)</div>
                <div style='font-size:1.5rem;font-weight:bold'>Q{d['precio']:,.4f}</div>
            </div>
            <div>
                <div style='font-size:.8rem;color:#555'>Margen Neto (Q)</div>
                <div style='font-size:1.5rem;font-weight:bold;color:{color_margen}'>
                    Q{d['margen_neto_q']:,.4f}
                </div>
            </div>
            <div>
                <div style='font-size:.8rem;color:#555'>Margen Neto (%)</div>
                <div style='font-size:1.5rem;font-weight:bold;color:{color_margen}'>
                    {d['margen_neto_pct']:.2f}%
                </div>
            </div>
        </div>
        {'<p style="color:#c62828;margin:8px 0 0 0;font-size:.9rem">'+alerta+'</p>' if alerta else ''}
    </div>
    """, unsafe_allow_html=True)

    with st.expander("📊 Desglose completo"):
        _g = d.get("gastos")
        if _g:
            # De dónde sale el costo unitario real, para que se vea cuánto
            # pesa cada gasto en el margen.
            g1, g2, g3 = st.columns(3)
            g1.metric("Costo del producto", f"Q{d['costo_producto']:,.4f}")
            g2.metric("+ Gasto operativo / unidad",
                      f"Q{d['gasto_unitario']:,.4f}")
            g3.metric("= Costo unitario real", f"Q{d['costo']:,.4f}")
            st.caption(
                f"Gastos del pedido: Mano de obra Q{_g['mano_obra']:,.2f} · "
                f"Empaque Q{_g['empaque']:,.2f} · "
                f"Transporte Q{_g['transporte']:,.2f} "
                f"= **Q{_g['total']:,.2f}** entre {_g['cantidad']:,.2f} "
                f"unidad(es).")
            st.divider()

        c1, c2 = st.columns(2)
        with c1:
            st.metric("Costo unitario real" if _g else "Costo de compra",
                      f"Q{d['costo']:,.4f}")
            st.metric("Precio sin IVA",         f"Q{d['precio_sin_iva']:,.4f}")
            st.metric("IVA (12%)",              f"Q{d['iva_amount']:,.4f}")
            st.metric("ISR (Precio/1.12 × 5%)", f"Q{d['isr_retencion']:,.4f}")
        with c2:
            st.metric("Neto que recibís",       f"Q{d['neto_recibido']:,.4f}")
            st.metric("Margen neto (Q)",        f"Q{d['margen_neto_q']:,.4f}")
            st.metric("Margen neto (%)",        f"{d['margen_neto_pct']:.2f}%")
            st.metric("Punto de equilibrio",    f"Q{d['pto_equilibrio']:,.4f}")
        st.caption(
            f"Markup sobre costo: {d['sobre_costo']:.1f}% · "
            f"Por cada Q100 de venta, tu bolsillo recibe Q{d['margen_neto_pct']:.1f}"
        )


# ── TAB 1: CALCULAR PRECIO ────────────────────────────────────────────────────
def _tab_calcular():
    st.markdown("#### Calculá el precio de venta desde tu costo y margen deseado")

    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        costo = st.number_input("💰 Costo de compra (Q)",
                                 min_value=0.01, value=5.0, step=0.50,
                                 key="cot_costo_c")
    with c2:
        modo_margen = st.radio("Margen deseado en",
                                ["Porcentaje (%)", "Quetzales (Q)"],
                                horizontal=True, key="cot_modo")
    with c3:
        if modo_margen == "Porcentaje (%)":
            margen_val = st.number_input("📈 Margen neto deseado (%)",
                                          min_value=0.0, max_value=94.0,
                                          value=30.0, step=1.0,
                                          key="cot_margen_pct",
                                          help="% del precio de venta que queda como ganancia neta")
        else:
            margen_val = st.number_input("📈 Margen neto deseado (Q por unidad)",
                                          min_value=0.0,
                                          value=2.0, step=0.25,
                                          key="cot_margen_q",
                                          help="Q que querés ganar por cada unidad vendida")

    # ── Gastos operativos del pedido (opcional) ──────────────────────────────
    # Van ANTES del resultado a propósito: el precio sugerido y el margen que
    # se muestran abajo ya los tienen adentro.
    st.markdown("##### 🚚 Gastos operativos del pedido *(opcional)*")
    st.caption("Los tres son TOTALES del pedido completo, no por unidad. Se "
               "reparten entre la cantidad para obtener el costo unitario "
               "real. Dejalos en 0 y el cálculo funciona como siempre.")
    q1, q2, q3, q4 = st.columns(4)
    cantidad = q1.number_input("📦 Cantidad a cotizar", min_value=0.0,
                               value=0.0, step=1.0, key="cot_gop_cant",
                               help="Unidades del pedido entre las que se "
                                    "reparten los gastos.")
    mo_tot  = q2.number_input("👷 Mano de obra (Q)", min_value=0.0, value=0.0,
                              step=10.0, key="cot_gop_mo")
    emp_tot = q3.number_input("📦 Empaque (Q)", min_value=0.0, value=0.0,
                              step=10.0, key="cot_gop_emp")
    tra_tot = q4.number_input("🚚 Transporte (Q)", min_value=0.0, value=0.0,
                              step=10.0, key="cot_gop_tra")

    gastos     = _gasto_operativo(cantidad, mo_tot, emp_tot, tra_tot)
    costo_real = costo + gastos["por_unidad"]

    if gastos["ignorado"]:
        st.warning(f"⚠️ Cargaste **Q{gastos['total']:,.2f}** de gastos pero la "
                   f"cantidad está en 0, así que **no se están aplicando**. "
                   f"Poné la cantidad del pedido para repartirlos.")
    elif gastos["total"] > 0:
        st.info(f"Costo unitario real: **Q{costo:,.4f}** del producto + "
                f"**Q{gastos['por_unidad']:,.4f}** de gastos "
                f"= **Q{costo_real:,.4f}**")

    st.divider()

    # Calcular — con el costo unitario REAL, que es lo único que cambia
    # respecto de antes. Las fórmulas son las mismas.
    _g = gastos if gastos["por_unidad"] > 0 else None
    if modo_margen == "Porcentaje (%)":
        resultado = _desde_margen_pct(costo_real, margen_val / 100, _g)
    else:
        resultado = _desde_margen_q(costo_real, margen_val, _g)

    if resultado is None:
        st.error("Verificá los valores ingresados. El margen no puede superar el 95%.")
        return

    _mostrar_resultado(resultado, "💡 Precio sugerido")

    # Ajuste manual del precio
    st.divider()
    st.markdown("#### ¿Querés ajustar el precio final?")
    st.caption("Ingresá el precio que pensás cobrar y ves el impacto en tu margen.")

    # El valor por defecto es el precio sugerido, y ese precio cambia cuando
    # cambian el costo o el margen. Streamlit IGNORA `value` si la key ya tiene
    # estado: con una key fija el campo se quedaba con el precio sugerido VIEJO
    # y el "Impacto" comparaba contra un número que ya no correspondía.
    # Versionar la key hace que una sugerencia nueva sea un widget nuevo.
    _sug = round(resultado["precio"], 2)
    if st.session_state.get("cot_sug_prev") != _sug:
        st.session_state["cot_sug_prev"] = _sug
        st.session_state["cot_ajuste_gen"] = st.session_state.get(
            "cot_ajuste_gen", 0) + 1
    precio_ajustado = st.number_input(
        "Precio final a cobrar (Q)",
        min_value=0.01,
        value=_sug,
        step=0.25,
        key=f"cot_precio_ajuste_g{st.session_state.get('cot_ajuste_gen', 0)}",
    )
    if _precio_cambiado(precio_ajustado, resultado["precio"]):
        d_ajustado = _desglose(costo_real, precio_ajustado, _g)
        if d_ajustado:
            diff_margen = d_ajustado["margen_neto_q"] - resultado["margen_neto_q"]
            st.markdown(
                f"**Impacto:** margen neto cambia de "
                f"Q{resultado['margen_neto_q']:,.2f} → "
                f"Q{d_ajustado['margen_neto_q']:,.2f} "
                f"({'▲' if diff_margen >= 0 else '▼'} Q{abs(diff_margen):,.2f})"
            )
            _mostrar_resultado(d_ajustado, "📌 Con precio ajustado")


# ── TAB 2: VERIFICAR MARGEN ───────────────────────────────────────────────────
def _tab_verificar():
    st.markdown("#### Dado un costo y un precio, ¿cuánto ganás?")

    c1, c2 = st.columns(2)
    with c1:
        costo  = st.number_input("💰 Costo de compra (Q)",
                                  min_value=0.01, value=5.0, step=0.50,
                                  key="cot_costo_v")
    with c2:
        precio = st.number_input("🏷️ Precio de venta (Q, con IVA)",
                                  min_value=0.01, value=8.0, step=0.25,
                                  key="cot_precio_v")

    st.divider()

    resultado = _desglose(costo, precio)
    if resultado:
        _mostrar_resultado(resultado, "📊 Análisis de margen")

        if precio < resultado["pto_equilibrio"]:
            st.error(
                f"⚠️ Estás vendiendo por debajo del punto de equilibrio "
                f"(Q{resultado['pto_equilibrio']:,.4f}). "
                f"Perdés Q{abs(resultado['margen_neto_q']):,.4f} por unidad."
            )
        elif resultado["margen_neto_pct"] < 15:
            st.warning(
                f"El margen del {resultado['margen_neto_pct']:.1f}% "
                f"es bajo. Considerá subir el precio."
            )


# ── TAB 3: COMPARAR ESCENARIOS ────────────────────────────────────────────────
def _tab_escenarios():
    st.markdown("#### Tabla de precios para distintos márgenes con el mismo costo")

    costo = st.number_input("💰 Costo de compra (Q)",
                             min_value=0.01, value=5.0, step=0.50,
                             key="cot_costo_e")

    margenes = [10, 15, 20, 25, 30, 35, 40, 45, 50]

    filas = []
    for m in margenes:
        d = _desde_margen_pct(costo, m / 100)
        if d:
            filas.append({
                "Margen %":        f"{m}%",
                "Precio venta (Q)": f"Q{d['precio']:,.2f}",
                "Precio s/IVA":    f"Q{d['precio_sin_iva']:,.2f}",
                "IVA (Q)":         f"Q{d['iva_amount']:,.2f}",
                "ISR ret. (Q)":    f"Q{d['isr_retencion']:,.2f}",
                "Margen neto (Q)": f"Q{d['margen_neto_q']:,.2f}",
                "Pto. Equilibrio": f"Q{d['pto_equilibrio']:,.2f}",
            })

    if filas:
        df = pd.DataFrame(filas)
        st.dataframe(df, use_container_width=True, hide_index=True,
                     column_config={
                         "Margen %":         st.column_config.TextColumn(width="small"),
                         "Precio venta (Q)": st.column_config.TextColumn(width="medium"),
                         "Precio s/IVA":     st.column_config.TextColumn(width="medium"),
                         "IVA (Q)":          st.column_config.TextColumn(width="medium"),
                         "ISR ret. (Q)":     st.column_config.TextColumn(width="medium"),
                         "Margen neto (Q)":  st.column_config.TextColumn(width="medium"),
                         "Pto. Equilibrio":  st.column_config.TextColumn(width="medium"),
                     })
        st.caption(
            f"Costo base: Q{costo:.2f} · "
            f"Punto de equilibrio: Q{punto_equilibrio(costo):.4f} · "
            f"IVA 12% · ISR 5%"
        )

    # Margen personalizado
    st.divider()
    st.markdown("#### Calculá con un margen específico")
    m_custom = st.slider("Margen neto deseado (%)", 1, 90, 30, key="cot_slider")
    d_custom = _desde_margen_pct(costo, m_custom / 100)
    if d_custom:
        cc1, cc2, cc3, cc4 = st.columns(4)
        cc1.metric("Precio de venta",   f"Q{d_custom['precio']:,.4f}")
        cc2.metric("Margen neto (Q)",   f"Q{d_custom['margen_neto_q']:,.4f}")
        cc3.metric("Neto que recibís",  f"Q{d_custom['neto_recibido']:,.4f}")
        cc4.metric("Precio sin IVA",    f"Q{d_custom['precio_sin_iva']:,.4f}")



# ── KEYS DE LA GRILLA ─────────────────────────────────────────────────────────
# Las keys de fila tienen la forma "cot_<campo>_g<generacion>_<indice>".
#
# Por qué la generación: no alcanza con borrar la key de session_state para que
# un widget vuelva a tomar su `index=`/`value=`. En el rerun, Streamlit reaplica
# los widget states que el navegador reenvía para los widgets que siguen
# montados, así que la key borrada reaparece con el valor viejo y la fila queda
# en blanco. Cambiando la generación, las keys son OTRAS: para Streamlit son
# widgets nuevos, sin estado previo, y sí toman el valor de la grilla.
#
# El sufijo numérico además distingue estas keys de las de las otras pestañas
# (cot_costo_c / _v / _e, los inputs de Calcular / Verificar / Comparar), que
# nunca deben borrarse desde acá.
_CAMPOS_FILA = ("prod", "prec", "spec", "vol", "costo", "del")
_RE_KEY_FILA = re.compile(r"^cot_(?:" + "|".join(_CAMPOS_FILA) + r")_g\d+_\d+$")


def _es_key_fila(k) -> bool:
    """True si la key pertenece a una fila de la grilla."""
    return isinstance(k, str) and _RE_KEY_FILA.match(k) is not None


def _kfila(campo: str, i: int) -> str:
    """Key del widget para el campo `campo` de la fila `i`, en la generación
    actual. Usar SIEMPRE esto en vez de armar la key a mano."""
    return f"cot_{campo}_g{st.session_state.get('cot_gen', 0)}_{i}"


def _nueva_generacion():
    """Invalida las keys de widget de todas las filas.

    Llamar después de repoblar o reordenar la grilla, para que los inputs tomen
    el producto y el precio nuevos en vez del valor que reenvía el navegador."""
    st.session_state["cot_gen"] = st.session_state.get("cot_gen", 0) + 1
    for k in [k for k in st.session_state if _es_key_fila(k)]:
        st.session_state.pop(k, None)


# ── COTIZACIÓN DE PRECIOS ─────────────────────────────────────────────────────
def _cotizacion():
    from datetime import date, timedelta
    from data_helper import cargar_productos
    from pdf_helper  import generar_cotizacion, generar_cotizacion_formal

    # ── Selector de tipo ──────────────────────────────────────────────────────
    tipo = st.radio("Tipo de cotizacion:",
                    ["📋 Simple", "🏢 Formal / Empresarial"],
                    horizontal=True, key="cot_tipo")
    is_formal = tipo.startswith("🏢")

    # ── Selector de listado de precios ──────────────────────────────────────
    # El listado elegido define el PRECIO DEFAULT de cada producto. Útil cuando
    # el cliente potencial es de un área con precios ya definidos. Los precios
    # siguen siendo editables por línea; si un producto no está en el listado
    # elegido, cae al precio del Listado General.
    from modulo_productos import ZONAS_LISTAS, GRUPOS_LISTAS
    LISTADOS = (["Listado General"] +
                [f"Zona {z}" for z in ZONAS_LISTAS] +
                [f"Grupo {g}" for g in GRUPOS_LISTAS])

    listado_sel = st.selectbox(
        "📋 Listado de precios a cargar:", LISTADOS, key="cot_listado",
        help="Define el precio inicial de cada producto. Podés ajustar "
             "cualquier precio individualmente después.")

    # Al CAMBIAR de listado, resetear los precios ya cargados en las filas
    # para que tomen el default del listado nuevo.
    _prev_listado   = st.session_state.get("cot_listado_prev")
    _listado_cambio = _prev_listado != listado_sel
    if _listado_cambio:
        # Invalidar las keys de fila para que los precios se recalculen desde
        # la capa nueva (incluida la primera elección, para que los precios
        # SIEMPRE se apliquen sobre restos de sesión). La especificación y el
        # volumen no se pierden: viven en cot_grilla, no en las keys.
        _nueva_generacion()
    st.session_state["cot_listado_prev"] = listado_sel

    # Mapa de precios de la capa elegida (vacío si es el Listado General)
    _precios_capa = {}
    if listado_sel != "Listado General":
        from data_helper import leer_precios_capa
        if listado_sel.startswith("Zona "):
            _hoja, _lista = "precioszona", listado_sel[5:]
        else:
            _hoja, _lista = "preciosgrupo", listado_sel[6:]
        try:
            _precios_capa = {e["producto"].strip().lower(): float(e["precio"])
                             for e in leer_precios_capa(_hoja, _lista)}
        except Exception:
            _precios_capa = {}
        if _precios_capa:
            st.caption(f"✓ {len(_precios_capa)} producto(s) con precio en "
                       f"**{listado_sel}** — el resto usa el precio general.")
        else:
            st.warning(f"El listado **{listado_sel}** no tiene precios "
                       "cargados; se usarán los precios del Listado General.")

    def _precio_listado(p: dict) -> float:
        """Precio default del producto según el listado elegido, con fallback
        al precio del catálogo general."""
        _pl = _precios_capa.get(p["nombre"].strip().lower())
        return float(_pl) if _pl else float(p.get("precio", 0))

    # ── Carga de la grilla desde el listado ──────────────────────────────────
    def _nombres_del_listado() -> list[str]:
        """Productos que corresponden al listado elegido, en orden A-Z."""
        from data_helper import cargar_productos as _cp
        _cat = {p["nombre"].strip().lower(): p
                for p in _cp(False, solo_catalogo=False)
                if p.get("cotizar", "") != "no"}
        if listado_sel == "Listado General":
            return sorted(p["nombre"] for p in _cat.values()
                          if float(p.get("precio") or 0) > 0)
        return sorted(_cat[n]["nombre"] for n in _precios_capa if n in _cat)

    def _poblar_grilla(nombres_cargar: list[str]):
        """Deja la grilla con exactamente esos productos y reinicia las keys de
        fila para que tomen el producto y el precio del listado nuevo."""
        st.session_state["cot_grilla"] = [
            {"producto": n, "precio_cotizar": 0.0,
             "especificacion": "", "volumen_semanal": 0.0}
            for n in nombres_cargar]
        st.session_state["cot_nfilas"] = len(nombres_cargar)
        _nueva_generacion()

    def _grilla_vacia() -> bool:
        """True si todavía no hay ningún producto elegido. Mira la grilla y
        también las keys de widget, que son la fuente de verdad en el rerun."""
        if any(str(f.get("producto", "")).strip()
               for f in st.session_state.get("cot_grilla", [])):
            return False
        return not any(str(v or "").strip()
                       for k, v in st.session_state.items()
                       if _es_key_fila(k) and k.startswith("cot_prod_"))

    # Al elegir un listado específico, cargar sus productos automáticamente.
    # Solo si la grilla está vacía: nunca pisa una cotización ya empezada, y
    # nunca autocarga el catálogo entero desde "Listado General".
    if (_listado_cambio and listado_sel != "Listado General"
            and _grilla_vacia()):
        _auto = _nombres_del_listado()
        if _auto:
            _poblar_grilla(_auto)
            st.session_state["cot_autocargado"] = listado_sel
            st.rerun()

    if st.session_state.pop("cot_autocargado", None) == listado_sel:
        st.success(f"✓ Se cargaron los {len(st.session_state.get('cot_grilla', []))} "
                   f"producto(s) de **{listado_sel}** con sus precios. "
                   f"Quitá los que no necesités con el botón ✖.")

    # ── Cargar listado / Limpiar ─────────────────────────────────────────────
    _cbl1, _cbl2 = st.columns(2)
    with _cbl2:
        if st.button("🗑 Nueva cotización (limpiar todo)",
                     key="cot_limpiar_todo", use_container_width=True,
                     help="Vacía la grilla y todos los campos para empezar "
                          "una cotización desde cero."):
            for _k in list(st.session_state.keys()):
                if isinstance(_k, str) and _k.startswith(
                        ("cot_grilla", "cot_nfilas",
                         "cot_dirigida", "cot_notas")):
                    st.session_state.pop(_k, None)
            _nueva_generacion()
            st.rerun()

    with _cbl1:
        _cargar_click = st.button(
            "📥 Cargar todos los productos del listado",
            key="cot_cargar_listado", use_container_width=True,
            help="Llena la grilla con los productos del listado elegido y "
                 "sus precios. Quitá los que no necesités con el botón ✖.")

    if _cargar_click:
        _nombres_cargar = _nombres_del_listado()
        if not _nombres_cargar:
            st.warning("El listado elegido no tiene productos para cargar.")
        else:
            _poblar_grilla(_nombres_cargar)
            st.session_state["cot_autocargado"] = listado_sel
            st.rerun()

    # Si la grilla quedó vacía, decir explícitamente cómo llenarla: elegir el
    # listado solo fija el precio default, no carga los productos.
    if _grilla_vacia():
        st.info("La grilla está vacía. Apretá **📥 Cargar todos los productos "
                "del listado** para llenarla con los productos de "
                f"**{listado_sel}**, o elegilos uno por uno más abajo.")

    st.divider()

    # Vigencia
    v1, v2 = st.columns(2)
    with v1:
        desde = v1.date_input("Vigente desde", value=date.today(), key="cot_desde")
    with v2:
        hasta = v2.date_input("Vigente hasta",
                               value=date.today() + timedelta(days=30),
                               key="cot_hasta")

    # Cotizador + numero
    COTIZADORES = {
        "Andrea Castillo Sanabria": "Tel. 59306817",
        "Sergio Burgos Alburez":    "Tel. 58749679",
    }
    cx1, cx2 = st.columns(2)
    cotizador_nombre = cx1.selectbox("Elaborado por:", list(COTIZADORES.keys()),
                                      key="cot_quien")
    cotizador_tel    = COTIZADORES[cotizador_nombre]

    if is_formal:
        num_cot = cx2.text_input("No. Cotizacion",
                                  value=f"VX-{desde.strftime('%Y%m%d')}-001",
                                  key="cot_num")
    else:
        # Cotización simple: destinatario (aparece en el encabezado del PDF)
        dirigida_a = cx2.text_input("Dirigida a:",
                                     placeholder="Nombre del cliente / empresa",
                                     key="cot_dirigida")
    st.divider()

    # ── Campos extra para cotizacion formal ───────────────────────────────────
    if is_formal:
        ef1, ef2 = st.columns(2)
        empresa_dest = ef1.text_input("Empresa destinataria",
                                       placeholder="PRALCASA / Nombre de la empresa",
                                       key="cot_empresa")
        atencion_dest = ef2.text_input("A la atencion de",
                                        placeholder="Nombre del contacto",
                                        key="cot_atencion")

        # Costo de transporte (se diluye por libras, fuera del margen)
        tf1, tf2 = st.columns([1, 2])
        flete_total = tf1.number_input(
            "Costo de transporte (Q)", min_value=0.0, value=0.0, step=50.0,
            key="cot_flete",
            help="Se reparte entre las libras cotizadas y se diluye en el "
                 "precio. No afecta el margen del producto.")
        if flete_total > 0:
            tf2.caption("El flete se prorratea por volumen entre todos los "
                        "productos y se integra al precio final. El margen "
                        "mostrado sigue siendo solo del producto.")

        CUERPO_DEFAULT = (
            "Estimado equipo,\n\n"
            "Por medio de la presente, nos es grato presentar nuestra "
            "cotizacion de productos frescos conforme a sus requerimientos. "
            "VeggiExpress se especializa en la distribucion de frutas y "
            "vegetales frescos de alta calidad, garantizando consistencia "
            "en volumen, calidad certificada y puntualidad en la entrega.\n\n"
            "A continuacion el detalle de productos cotizados:"
        )
        cuerpo_texto = st.text_area("Cuerpo de la cotizacion",
                                     value=st.session_state.get("cot_cuerpo",
                                                                  CUERPO_DEFAULT),
                                     height=130, key="cot_cuerpo_area")
        st.session_state["cot_cuerpo"] = cuerpo_texto
        st.divider()

    st.markdown("**Productos a cotizar** — selecciona y ajusta el precio:")

    SEGS = {"Premium":50,"Alto":40,"Media Alta":35,"Media":30,
            "Media Baja":25,"Baja":20,"Sin Segmento":0}

    # Universo completo (sin filtro de precio>0): un producto puede tener
    # precio SOLO en una capa (ej. Antigua) y precio general 0 — igual debe
    # poder cotizarse. Se respeta la marca explícita "no cotizar".
    prods      = [p for p in cargar_productos(False, solo_catalogo=False)
                  if p.get("cotizar", "") != "no"]
    prod_dict  = {p["nombre"]: p for p in prods}
    nombres    = [""] + sorted([p["nombre"] for p in prods])
    n_filas    = st.session_state.get("cot_nfilas", 5)

    # Init grilla
    if "cot_grilla" not in st.session_state:
        st.session_state["cot_grilla"] = [
            {"producto":"","precio_cotizar":0.0,
             "especificacion":"","volumen_semanal":0.0} for _ in range(n_filas)]
    elif len(st.session_state["cot_grilla"]) < n_filas:
        while len(st.session_state["cot_grilla"]) < n_filas:
            st.session_state["cot_grilla"].append(
                {"producto":"","precio_cotizar":0.0,
                 "especificacion":"","volumen_semanal":0.0})

    grilla = st.session_state["cot_grilla"]
    lineas_pdf = []

    # Encabezado — diferente por tipo
    if is_formal:
        hdr = st.columns([1.4, 1.0, 0.6, 0.65, 0.7, 0.65, 0.7, 0.6, 0.65, 0.7, 0.35])
        for h, lbl in zip(hdr, ["Producto","Espec.","Vol","Costo","C+Flete",
                                  "Pto.Eq","Precio","Mg%","MgQ","P.Final",""]):
            h.markdown(f"<small><b>{lbl}</b></small>", unsafe_allow_html=True)
    else:
        hdr = st.columns([2.4, 0.9, 0.9, 1.0, 1.0, 1.2, 0.85, 0.95, 0.9, 0.9, 0.35])
        for h, lbl in zip(hdr, ["Producto","Unidad","Costo","Pto. Eq.","P. Imp.",
                                  "Precio Cotizar","Margen %","Margen Q","IVA/u","ISR/u"]):
            h.markdown(f"<small><b>{lbl}</b></small>", unsafe_allow_html=True)

    # Pre-cálculo del flete por libra (formal): leer volúmenes ya guardados
    # en session_state para distribuir el flete EN VIVO en cada línea.
    flete_total_pre = st.session_state.get("cot_flete", 0.0) if is_formal else 0.0
    flete_x_lb_pre = 0.0
    if is_formal and flete_total_pre > 0:
        _vol_total_pre = 0.0
        for _j in range(n_filas):
            _vj = st.session_state.get(_kfila("vol", _j), 0.0)
            try:
                _vol_total_pre += float(_vj or 0)
            except (ValueError, TypeError):
                pass
        if _vol_total_pre > 0:
            flete_x_lb_pre = flete_total_pre / _vol_total_pre

    for i, fila in enumerate(grilla):
        k_prod = _kfila("prod",  i)
        k_prec = _kfila("prec",  i)
        k_spec = _kfila("spec",  i)
        k_vol  = _kfila("vol",   i)

        def _ref(col, txt):
            col.markdown(
                f"<div style='padding-top:8px;font-size:.78rem;color:#888'>"
                f"{txt}</div>", unsafe_allow_html=True)

        # ── Columnas según modo ───────────────────────────────────────────────
        if is_formal:
            r = st.columns([1.4, 1.0, 0.6, 0.65, 0.7, 0.65, 0.7, 0.6, 0.65, 0.7, 0.35])
        else:
            r = st.columns([2.4, 0.9, 0.9, 1.0, 1.0, 1.2, 0.85, 0.95, 0.9, 0.9, 0.35])

        prod_sel = r[0].selectbox("", nombres,
            index=(nombres.index(fila["producto"]) if fila["producto"] in nombres else 0),
            key=k_prod, label_visibility="collapsed")

        # Botón para eliminar esta fila (conserva las ediciones de las demás)
        if r[10].button("✖", key=_kfila("del", i),
                        help="Quitar esta fila de la cotización"):
            _nueva_grilla = []
            for _j in range(len(grilla)):
                if _j == i:
                    continue
                _nueva_grilla.append({
                    "producto": st.session_state.get(_kfila("prod", _j),
                                    grilla[_j].get("producto", "")),
                    "precio_cotizar": float(st.session_state.get(
                        _kfila("prec", _j),
                        grilla[_j].get("precio_cotizar", 0.0)) or 0),
                    "especificacion": st.session_state.get(_kfila("spec", _j),
                                    grilla[_j].get("especificacion", "")),
                    "volumen_semanal": float(st.session_state.get(
                        _kfila("vol", _j),
                        grilla[_j].get("volumen_semanal", 0.0)) or 0),
                    "costo_editado": float(st.session_state.get(
                        _kfila("costo", _j),
                        grilla[_j].get("costo_editado", 0.0)) or 0),
                })
            st.session_state["cot_grilla"] = _nueva_grilla
            st.session_state["cot_nfilas"] = max(len(_nueva_grilla), 1)
            _nueva_generacion()
            st.rerun()

        if prod_sel and prod_sel in prod_dict:
            p      = prod_dict[prod_sel]
            costo  = float(p.get("costo", 0))
            seg    = SEGS.get(p.get("tipo_producto2",""), 0) / 100
            pto_eq = round(punto_equilibrio(costo), 2) if costo else 0
            p_imp  = round(costo / (1 - seg/ISR_FACTOR) * IVA_FACTOR, 2) if seg > 0 and costo else 0

            if k_prec not in st.session_state:
                _pg = float(fila.get("precio_cotizar", 0) or 0)
                st.session_state[k_prec] = _pg if _pg > 0 else _precio_listado(p)

            if is_formal:
                # Formal 10 cols: r[0]=prod r[1]=spec r[2]=vol r[3]=costo
                #   r[4]=costo+flete r[5]=ptoEq r[6]=precio r[7]=mg% r[8]=mgQ r[9]=pFinal
                # OPCION A: el flete entra como COSTO. Margen y Pto.Eq se calculan
                # sobre (costo + flete). El precio ingresado es el precio FINAL.
                especif = r[1].text_input("", value=fila.get("especificacion",""),
                                           key=k_spec, label_visibility="collapsed",
                                           placeholder="Especificacion")
                vol_sem = r[2].number_input("", value=float(fila.get("volumen_semanal",0)),
                                             min_value=0.0, step=100.0, key=k_vol,
                                             label_visibility="collapsed")
                # Costo editable — default del catálogo, NO se guarda en ningún lado
                k_costo = _kfila("costo", i)
                if k_costo not in st.session_state:
                    st.session_state[k_costo] = float(costo)
                costo_ed = r[3].number_input("", min_value=0.0,
                    value=float(st.session_state[k_costo]),
                    step=0.25, key=k_costo, label_visibility="collapsed")
                # Costo + flete (la base real sobre la que se calcula todo)
                costo_total = costo_ed + flete_x_lb_pre
                _ref(r[4], f"Q{costo_total:,.2f}")
                # Punto de equilibrio sobre costo+flete
                pto_eq = round(costo_total * IVA_FACTOR, 2) if costo_total else 0
                _ref(r[5], f"Q{pto_eq:,.2f}" if pto_eq else "—")
                # Precio FINAL editable (ya incluye todo)
                precio_ed = r[6].number_input("", min_value=0.0,
                    value=float(st.session_state[k_prec]),
                    step=0.25, key=k_prec, label_visibility="collapsed")
                # Margen NETO sobre costo+flete (el flete es parte del costo)
                if precio_ed > 0 and costo_total > 0:
                    mp = round(margen_neto_pct(costo_total, precio_ed), 1)
                    mq = round(margen_neto_q(costo_total, precio_ed), 2)
                    col_m = "#2D7A2D" if mp >= 20 else "#E65100"
                    _ref(r[7], f"<span style='color:{col_m}'><b>{mp}%</b></span>")
                    _ref(r[8], f"<span style='color:{col_m}'>Q{mq:,.2f}</span>")
                else:
                    r[7].write(""); r[8].write("")
                # Precio Final = el precio ingresado (ya tiene todo dentro)
                _ref(r[9], f"<b>Q{precio_ed:,.2f}</b>" if precio_ed > 0 else "—")

                grilla[i] = {"producto": prod_sel, "precio_cotizar": precio_ed,
                              "especificacion": especif, "volumen_semanal": vol_sem,
                              "costo_editado": costo_ed}


            else:
                # Simple: r[1]=unidad, r[2]=costo, r[3]=pto_eq, r[4]=p_imp,
                #         r[5]=precio, r[6]=mg%, r[7]=mgQ, r[8]=IVA, r[9]=ISR
                r[1].markdown(f"<div style='padding-top:8px;font-size:.82rem'>"
                              f"{p.get('unidad','')}</div>", unsafe_allow_html=True)
                _ref(r[2], f"Q{costo:,.2f}" if costo else "—")
                _ref(r[3], f"Q{pto_eq:,.2f}" if pto_eq else "—")
                _ref(r[4], f"Q{p_imp:,.2f}"  if p_imp  else "—")

                precio_ed = r[5].number_input("", min_value=0.0,
                    value=float(st.session_state[k_prec]),
                    step=0.25, key=k_prec, label_visibility="collapsed")

                if precio_ed > 0 and costo > 0:
                    mp  = round(margen_neto_pct(costo, precio_ed), 1)
                    mq  = round(margen_neto_q(costo, precio_ed), 2)
                    iva = round(precio_ed - precio_ed / IVA_FACTOR, 2)
                    isr = round(precio_ed / IVA_FACTOR * ISR_RATE, 2)
                    col = "#2D7A2D" if mp >= 20 else "#E65100"
                    _ref(r[6], f"<span style='color:{col}'><b>{mp}%</b></span>")
                    _ref(r[7], f"<span style='color:{col}'>Q{mq:,.2f}</span>")
                    _ref(r[8], f"Q{iva:,.2f}")
                    _ref(r[9], f"Q{isr:,.2f}")
                elif precio_ed > 0:
                    for col in r[6:]: _ref(col, "—")
                else:
                    for col in r[6:]: col.write("")

                # La vista simple no edita especificación / volumen / costo.
                # Se conservan los valores que ya tenía la fila en vez de
                # ponerlos en cero, para no perder los datos de la cotización
                # formal al alternar entre "Simple" y "Formal".
                grilla[i] = {"producto": prod_sel, "precio_cotizar": precio_ed,
                              "especificacion":  fila.get("especificacion", ""),
                              "volumen_semanal": fila.get("volumen_semanal", 0.0),
                              "costo_editado":   fila.get("costo_editado", 0.0)}

            if precio_ed > 0:
                lineas_pdf.append({
                    "producto":        prod_sel,
                    "unidad":          p.get("unidad",""),
                    "precio_cotizar":  precio_ed,
                    "especificacion":  grilla[i].get("especificacion",""),
                    "volumen_semanal": grilla[i].get("volumen_semanal", 0.0),
                    "costo_editado":   grilla[i].get("costo_editado", 0.0),
                })
        else:
            # El selector quedó vacío. Hay dos motivos posibles y se tratan
            # distinto:
            #   1. El usuario vació la fila a propósito → se limpia (esperado).
            #   2. El producto guardado ya no está en el catálogo (renombrado,
            #      marcado "no cotizar", o refresco del caché de 600s). Ahí el
            #      selectbox cae a index 0 sin que nadie lo haya tocado, y
            #      limpiar la fila perdería la línea en silencio. Se conserva
            #      el dato y se avisa; la fila queda fuera del PDF hasta que se
            #      resuelva, y se puede quitar con ✖.
            _guardado = str(fila.get("producto", "")).strip()
            if _guardado and _guardado not in nombres:
                _ref(r[1], f"<span style='color:#c62828'>⚠️ «{_guardado}» ya "
                           f"no está disponible en el catálogo</span>")
                for col in r[2:10]: col.write("")
            else:
                grilla[i] = {"producto":"","precio_cotizar":0.0,
                              "especificacion":"","volumen_semanal":0.0}
                for col in r[1:]: col.write("")
    st.session_state["cot_grilla"] = grilla

    # Botones de fila
    ba, bb, bc = st.columns(3)
    with ba:
        if st.button("+ 5 líneas", key="cot_add5"):
            st.session_state["cot_nfilas"] = n_filas + 5; st.rerun()
    with bb:
        if st.button("+ 10 líneas", key="cot_add10"):
            st.session_state["cot_nfilas"] = n_filas + 10; st.rerun()
    with bc:
        if st.button("🗑 Limpiar grilla", key="cot_clear", type="secondary"):
            st.session_state.pop("cot_grilla", None)
            st.session_state["cot_nfilas"] = 15
            _nueva_generacion()
            st.rerun()

    st.divider()

    # ── Flete (solo formal) ───────────────────────────────────────────────────
    # OPCION A: el flete ya está DENTRO del costo de cada línea (costo + flete),
    # y el precio ingresado ya es el final. NO se vuelve a sumar aquí — solo se
    # informa el prorrateo. El precio_cotizar de cada línea YA es el precio final.
    flete_total = st.session_state.get("cot_flete", 0.0) if is_formal else 0.0
    flete_x_lb = 0.0
    if is_formal and flete_total > 0 and lineas_pdf:
        total_vol = sum(float(l.get("volumen_semanal", 0)) for l in lineas_pdf)
        if total_vol > 0:
            flete_x_lb = flete_total / total_vol
            st.info(f"🚛 **Flete Q{flete_total:,.2f}** repartido entre "
                    f"{total_vol:,.0f} lbs = **+Q{flete_x_lb:.3f}/lb** de costo. "
                    f"Ya incluido en la columna C+Flete; tu margen se calcula "
                    f"sobre costo+flete y el precio final lo cubre todo.")
        elif flete_total > 0:
            st.warning("Para prorratear el flete, ingresá el volumen semanal "
                       "(lbs) de cada producto.")

    if lineas_pdf:
        st.success(f"**{len(lineas_pdf)} producto(s)** listos para el PDF.")

        if is_formal:
            st.markdown("**Observaciones adicionales** (aparecen arriba de las "
                        "condiciones en el PDF, respetando párrafos):")
            notas_cot = st.text_area(
                "Observaciones",
                placeholder="Ej: Entrega sujeta a programa semanal acordado.\n\n"
                            "Certificados de calidad disponibles a solicitud.",
                height=100,
                key="cot_notas_formal",
                label_visibility="collapsed",
            )

            # Condiciones generales — editable, precargada
            from pdf_helper import _MESES_ES as _MES  # para fecha en español
            _cond_default = (
                "Moneda: Quetzales guatemaltecos (GTQ), precios sin IVA.\n"
                "Calidad: Productos frescos de primera calidad, seleccionados y calibrados.\n"
                "Entrega: Sujeto a programa y volumen acordado con el cliente.\n"
                "Empaque: Segun especificacion del cliente o estandar VeggiExpress.\n"
                f"Validez de la cotizacion: {hasta.day} de "
                f"{_MES.get(hasta.month, '')} de {hasta.year}.\n"
                "Precios sujetos a variacion por condiciones de mercado fuera "
                "del periodo de vigencia."
            )
            st.markdown("**Condiciones generales** (editables, aparecen al final):")
            condiciones_cot = st.text_area(
                "Condiciones",
                value=st.session_state.get("cot_condiciones", _cond_default),
                height=140, key="cot_cond_area",
                label_visibility="collapsed",
                help="Una condición por línea. Se muestran con viñetas en el PDF.")
            st.session_state["cot_condiciones"] = condiciones_cot

            # Checkboxes de totales en la tabla del PDF
            tc1, tc2 = st.columns(2)
            mostrar_total_col = tc1.checkbox(
                "Mostrar columna 'Total por producto' en PDF",
                value=False, key="cot_tot_col")
            mostrar_total_fila = tc2.checkbox(
                "Mostrar fila 'Total semanal' en PDF",
                value=False, key="cot_tot_fila")
        else:
            notas_cot = st.text_area(
                "",
                placeholder="Ej: Precios sin IVA · Precios sujetos a cambio · "
                            "Disponibilidad sujeta a programa de siembra...",
                height=90,
                key="cot_notas",
                label_visibility="collapsed",
            )

        btn_lbl = "📄 Generar Cotizacion Formal" if is_formal else "📄 Generar PDF"
        if st.button(btn_lbl, type="primary"):
            with st.spinner("Generando PDF..."):
                # Productos en orden alfabético A-Z en el PDF (ambos tipos)
                lineas_pdf.sort(key=lambda l: str(l.get("producto","")).lower())
                if is_formal:
                    pdf_bytes = generar_cotizacion_formal(
                        lineas_pdf, desde, hasta,
                        empresa=st.session_state.get("cot_empresa",""),
                        atencion=st.session_state.get("cot_atencion",""),
                        cuerpo=st.session_state.get("cot_cuerpo",""),
                        cotizador=cotizador_nombre,
                        cotizador_tel=cotizador_tel,
                        num_cot=st.session_state.get("cot_num","VX-001"),
                        notas=notas_cot,
                        condiciones_txt=st.session_state.get("cot_condiciones",""),
                        mostrar_total_col=st.session_state.get("cot_tot_col", False),
                        mostrar_total_fila=st.session_state.get("cot_tot_fila", False),
                    )
                    nombre = (f"Cotizacion_Formal_VeggiExpress_"
                              f"{st.session_state.get('cot_num','').replace('-','_')}.pdf")
                else:
                    pdf_bytes = generar_cotizacion(lineas_pdf, desde, hasta,
                                           cotizador=cotizador_nombre,
                                           cotizador_tel=cotizador_tel,
                                           notas=notas_cot,
                                           dirigida_a=st.session_state.get(
                                               "cot_dirigida", ""))
                    nombre = f"Cotizacion_VeggiExpress_{desde.strftime('%d%m%Y')}.pdf"
            st.download_button("📥 Descargar PDF", data=pdf_bytes,
                file_name=nombre, mime="application/pdf",
                key="cot_dl", type="primary")
    else:
        st.info("Seleccioná al menos un producto para generar la cotización.")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def mostrar():
    st.markdown("## 🧮 Cotizador de Precios")
    if st.button("🏠 Inicio", key="btn_home_cot", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    st.caption("IVA 12% · ISR 5% · Fórmulas según Listado de Productos")

    tab1, tab2, tab3, tab4 = st.tabs([
        "💡 Calcular Precio",
        "🔍 Verificar Margen",
        "📊 Comparar Escenarios",
        "📋 Cotización de Precios",
    ])

    with tab1: _tab_calcular()
    with tab2: _tab_verificar()
    with tab3: _tab_escenarios()
    with tab4: _cotizacion()
