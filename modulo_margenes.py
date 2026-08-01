"""
modulo_margenes.py — Control de Márgenes por producto.

Reporte de SOLO LECTURA: no escribe nada en el Sheet. Agrega las líneas de
pedido ya vendidas y responde una sola pregunta — cuánto deja cada producto.

    Cantidad = lo vendido            Costo   = Σ(costo  × cantidad)
    Ingreso  = Σ(precio × cantidad)  Bruto   = Ingreso − Costo
                                     Neto    = Σ(margen_neto_q × cantidad)

Usa el costo y el precio GUARDADOS en cada línea, no el catálogo de hoy: así
un producto que cambió de costo la semana pasada sigue mostrando el margen que
realmente dejó, y el reporte no se mueve solo cuando se ajusta el catálogo.

Los porcentajes del total se calculan sobre los totales (Bruto/Ingreso), nunca
promediando los porcentajes de cada fila: un producto de Q5 y otro de Q5,000
no pesan igual.
"""
import streamlit as st
import pandas as pd
from datetime import date, timedelta

from config       import excluido_proveedores as _excluido, margen_neto_q
from data_helper  import mapa_area_grupo
from excel_helper import leer_pedidos_op as leer_pedidos

_fragment = getattr(st, "fragment", None) or getattr(st, "experimental_fragment",
                                                     lambda f: f)

# Columnas del reporte, en orden. Se declaran una sola vez porque las usan la
# tabla, el CSV y el PDF — con tres listas separadas, agregar una columna
# significaba que el papel dejara de coincidir con la pantalla.
COLS = ["Producto", "Cantidad", "Costo (Q)", "Ingreso (Q)",
        "Margen Bruto (Q)", "Bruto %", "Margen Neto (Q)", "Neto %"]


def _rango_atajo(atajo: str, hoy: date) -> tuple:
    """(desde, hasta) de cada atajo. 'Esta semana' sale de order_helper para no
    tener otra definición de semana conviviendo con la de propagación."""
    if atajo == "Esta semana":
        from order_helper import semana_en_curso
        return semana_en_curso(hoy)
    if atajo == "Este mes":
        ini = hoy.replace(day=1)
        return ini, (ini + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    if atajo == "Mes pasado":
        fin_ant = hoy.replace(day=1) - timedelta(days=1)
        return fin_ant.replace(day=1), fin_ant
    return hoy - timedelta(days=30), hoy       # Personalizado: default 30 días


def _lineas(desde: date, hasta: date):
    """Líneas vendidas del rango, con área y proveedor resueltos.

    Generador: recorre el resultado ya cacheado de leer_pedidos_op sin
    materializar una copia del histórico.

    El área sale de data_helper.mapa_area_grupo, la misma fuente que usa el
    reporte de Compras — si cada pantalla resolviera el área por su cuenta, los
    dos reportes mostrarían totales distintos para la misma área.
    """
    mapa = mapa_area_grupo()
    for p in leer_pedidos():            # 12 meses, cacheado
        f = p.get("fecha")
        if not f or not (desde <= f <= hasta):
            continue
        cli = str(p.get("cliente", "") or "").strip()
        if not cli or _excluido(cli):
            continue
        prod = str(p.get("producto", "") or "").strip()
        if not prod:
            continue
        yield {
            "area":      mapa.get(cli.lower(), {}).get("area", "Sin área"),
            "proveedor": str(p.get("proveedor", "") or "").strip() or "Sin proveedor",
            "producto":  prod,
            "cantidad":  float(p.get("cantidad") or 0),
            "costo":     float(p.get("costo") or 0),
            "precio":    float(p.get("precio") or 0),
        }


@st.cache_data(ttl=300, max_entries=4, show_spinner=False)
def _opciones(desde: date, hasta: date) -> dict:
    """Áreas y proveedores presentes en el rango, para poblar los filtros."""
    ar, pv = set(), set()
    for l in _lineas(desde, hasta):
        ar.add(l["area"]); pv.add(l["proveedor"])
    return {"areas": sorted(ar), "proveedores": sorted(pv)}


def _pct(valor: float, ingreso: float) -> float:
    """Margen como % del ingreso. Sin ingreso no hay porcentaje que calcular:
    devolver 0 evita una división por cero y no inventa un margen."""
    return round(valor / ingreso * 100, 1) if ingreso else 0.0


@st.cache_data(ttl=300, max_entries=8, show_spinner=False)
def agregar_margenes(desde: date, hasta: date,
                     areas: tuple, provs: tuple) -> pd.DataFrame:
    """Una fila por producto con cantidad, costo, ingreso y ambos márgenes.

    Recibe solo primitivas y devuelve el DataFrame ya agregado — nunca la lista
    cruda, para que el caché no retenga el histórico de pedidos en memoria.
    """
    acc = {}
    for l in _lineas(desde, hasta):
        if areas and l["area"]      not in areas: continue
        if provs and l["proveedor"] not in provs: continue
        cant = l["cantidad"]
        a = acc.setdefault(l["producto"], {"c": 0.0, "co": 0.0, "in": 0.0,
                                           "ne": 0.0})
        a["c"]  += cant
        a["co"] += l["costo"]  * cant
        a["in"] += l["precio"] * cant
        # El neto se acumula línea por línea: la fórmula no es lineal en los
        # totales, así que aplicarla al costo y precio sumados daría otro número.
        a["ne"] += margen_neto_q(l["costo"], l["precio"]) * cant

    filas = []
    for prod, v in acc.items():
        bruto = v["in"] - v["co"]
        filas.append({
            "Producto":         prod,
            "Cantidad":         round(v["c"], 2),
            "Costo (Q)":        round(v["co"], 2),
            "Ingreso (Q)":      round(v["in"], 2),
            "Margen Bruto (Q)": round(bruto, 2),
            "Bruto %":          _pct(bruto, v["in"]),
            "Margen Neto (Q)":  round(v["ne"], 2),
            "Neto %":           _pct(v["ne"], v["in"]),
        })
    df = pd.DataFrame(filas, columns=COLS)
    if not df.empty:
        df = df.sort_values("Margen Neto (Q)", ascending=False, ignore_index=True)
    return df


def totales(df: pd.DataFrame) -> dict:
    """Totales de la tabla. Los % se recalculan sobre los totales — promediar
    los porcentajes de las filas daría un número que no es el margen real."""
    if df.empty:
        return {k: 0.0 for k in ("cantidad", "costo", "ingreso", "bruto",
                                 "bruto_pct", "neto", "neto_pct")}
    ing   = float(df["Ingreso (Q)"].sum())
    bruto = float(df["Margen Bruto (Q)"].sum())
    neto  = float(df["Margen Neto (Q)"].sum())
    return {"cantidad":  float(df["Cantidad"].sum()),
            "costo":     float(df["Costo (Q)"].sum()),
            "ingreso":   ing,
            "bruto":     bruto,
            "bruto_pct": _pct(bruto, ing),
            "neto":      neto,
            "neto_pct":  _pct(neto, ing)}


def mostrar():
    st.markdown("## 📈 Control de Márgenes")
    if st.button("🏠 Inicio", key="btn_home_marg", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()
    _reporte()


@_fragment
def _reporte():
    hoy = date.today()
    st.caption("Rentabilidad por producto sobre lo vendido. Usa el costo y el "
               "precio guardados en cada línea de pedido: no recalcula nada ni "
               "modifica el Sheet.")

    a1, a2, a3 = st.columns([2, 1.2, 1.2])
    atajo = a1.radio("Rango", ["Esta semana", "Este mes", "Mes pasado",
                               "Personalizado"], horizontal=True,
                     key="marg_atajo")
    d_def, h_def = _rango_atajo(atajo, hoy)
    if atajo == "Personalizado":
        desde = a2.date_input("Desde", value=d_def, key="marg_desde")
        hasta = a3.date_input("Hasta", value=h_def, key="marg_hasta")
    else:
        desde, hasta = d_def, h_def
        a2.markdown(f"<small>Desde<br><b>{desde:%d/%m/%Y}</b></small>",
                    unsafe_allow_html=True)
        a3.markdown(f"<small>Hasta<br><b>{hasta:%d/%m/%Y}</b></small>",
                    unsafe_allow_html=True)

    if desde > hasta:
        st.error("El 'Desde' es posterior al 'Hasta'.")
        return

    # leer_pedidos_op solo trae 12 meses. Se recorta y se avisa, en vez de
    # pasar a leer_pedidos (histórico completo): la app ya se cayó por memoria.
    limite = hoy - timedelta(days=365)
    if desde < limite:
        st.warning(f"El reporte cubre los últimos 12 meses. El rango se "
                   f"recorta desde el {limite:%d/%m/%Y}.")
        desde = limite

    op = _opciones(desde, hasta)
    f1, f2 = st.columns(2)
    sel_area = f1.multiselect("Área",      op["areas"],       key="marg_area")
    sel_prov = f2.multiselect("Proveedor", op["proveedores"], key="marg_prov")

    df = agregar_margenes(desde, hasta, tuple(sel_area), tuple(sel_prov))
    if df.empty:
        st.info("Sin líneas de pedido para esos filtros.")
        return

    t = totales(df)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ingreso",      f"Q{t['ingreso']:,.2f}")
    m2.metric("Costo",        f"Q{t['costo']:,.2f}")
    m3.metric("Margen Bruto", f"Q{t['bruto']:,.2f}", f"{t['bruto_pct']:.1f}%",
              delta_color="off")
    m4.metric("Margen Neto",  f"Q{t['neto']:,.2f}",  f"{t['neto_pct']:.1f}%",
              delta_color="off")

    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config={
                     "Cantidad":         st.column_config.NumberColumn(format="%.2f"),
                     "Costo (Q)":        st.column_config.NumberColumn(format="%.2f"),
                     "Ingreso (Q)":      st.column_config.NumberColumn(format="%.2f"),
                     "Margen Bruto (Q)": st.column_config.NumberColumn(format="%.2f"),
                     "Bruto %":          st.column_config.NumberColumn(format="%.1f%%"),
                     "Margen Neto (Q)":  st.column_config.NumberColumn(format="%.2f"),
                     "Neto %":           st.column_config.NumberColumn(format="%.1f%%"),
                 })
    st.caption(f"**TOTAL: Ingreso Q{t['ingreso']:,.2f} · Costo "
               f"Q{t['costo']:,.2f} · Bruto Q{t['bruto']:,.2f} "
               f"({t['bruto_pct']:.1f}%) · Neto Q{t['neto']:,.2f} "
               f"({t['neto_pct']:.1f}%)** — {len(df)} producto(s), "
               f"{desde:%d/%m/%Y} a {hasta:%d/%m/%Y}")

    if (df["Margen Neto (Q)"] < 0).any():
        _n = int((df["Margen Neto (Q)"] < 0).sum())
        st.warning(f"⚠️ {_n} producto(s) con margen neto negativo: se está "
                   f"vendiendo por debajo del punto de equilibrio "
                   f"(costo × 1.12).")

    # Filtros aplicados: van al PDF para que un reporte impreso nunca sea
    # ambiguo sobre qué recorte representa.
    _partes = [f"{lbl}: {', '.join(v)}"
               for lbl, v in (("Área", sel_area), ("Proveedor", sel_prov)) if v]
    filtros_txt = " · ".join(_partes) or "sin filtros (todas las áreas)"

    b1, b2 = st.columns(2)
    csv_df = pd.concat([df, pd.DataFrame([{
        "Producto": "TOTAL",
        "Cantidad": round(t["cantidad"], 2), "Costo (Q)": round(t["costo"], 2),
        "Ingreso (Q)": round(t["ingreso"], 2),
        "Margen Bruto (Q)": round(t["bruto"], 2), "Bruto %": t["bruto_pct"],
        "Margen Neto (Q)": round(t["neto"], 2), "Neto %": t["neto_pct"],
    }])], ignore_index=True)
    b1.download_button(
        "📥 Descargar CSV",
        data=csv_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"margenes_{desde:%Y%m%d}_{hasta:%Y%m%d}.csv",
        mime="text/csv", key="marg_csv", use_container_width=True)

    with b2:
        if st.button("🖨 Preparar impresión", key="marg_pdf",
                     use_container_width=True):
            import streamlit.components.v1 as components
            from pdf_helper import generar_reporte_margenes, boton_imprimir_html
            with st.spinner("Generando PDF..."):
                pdf = generar_reporte_margenes(df.to_dict("records"), desde,
                                               hasta, filtros_txt, t)
            components.html(boton_imprimir_html(pdf, "repmargenes",
                                                label="🖨 Abrir e imprimir"),
                            height=60)
