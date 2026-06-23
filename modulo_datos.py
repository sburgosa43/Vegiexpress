"""
modulo_datos.py — Sábana de datos completa.
4 tipos: Pedidos | Gastos | Clientes | Productos
Filtros + totales al pie + descarga CSV/Excel + sync a Sheet.
"""
import streamlit as st
import pandas as pd
import io
from datetime import date

MESES = {1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",
         7:"Jul",8:"Ago",9:"Sep",10:"Oct",11:"Nov",12:"Dic"}

# ── Helpers ───────────────────────────────────────────────────────────────────
def _fq(v): return f"Q{float(v or 0):,.2f}"

def _df_to_excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Datos")
    return buf.getvalue()

def _selectbox_all(label, opciones, key):
    return st.selectbox(label, ["Todos"] + sorted(set(str(o) for o in opciones if o)),
                        key=key)

# ── PEDIDOS ───────────────────────────────────────────────────────────────────
def _sabana_pedidos():
    from excel_helper import leer_pedidos
    from data_helper  import cargar_clientes
    from config       import calcular_liquido, ZONAS_MAP

    todos    = leer_pedidos()
    clientes = {c["nombre"].lower().strip(): c for c in cargar_clientes()}

    # Zona map inversa: codigo → nombre zona
    cod_zona = {}
    for zona, cods in ZONAS_MAP.items():
        for c in cods: cod_zona[c] = zona

    # ── Filtros ────────────────────────────────────────────────────────────────
    f1, f2, f3, f4, f5, f6 = st.columns(6)
    años_disp  = sorted({p["año"]  for p in todos}, reverse=True)
    meses_disp = sorted({p["fecha"].month for p in todos if p["fecha"]})
    año_sel    = f1.selectbox("Año",    años_disp,  key="dat_año")
    mes_sel    = f2.selectbox("Mes", ["Todos"] + [MESES[m] for m in meses_disp],
                               key="dat_mes")
    cli_sel    = _selectbox_all("Cliente", [p["cliente"] for p in todos], f3.empty().__class__)
    cli_sel    = f3.selectbox("Cliente", ["Todos"] + sorted({p["cliente"] for p in todos}),
                               key="dat_cli")
    zona_sel   = f4.selectbox("Zona",   ["Todas"] + list(ZONAS_MAP.keys()), key="dat_zona")
    prod_sel   = f5.selectbox("Producto",["Todos"] + sorted({p["producto"] for p in todos}),
                               key="dat_prod")
    status_sel = f6.selectbox("Status", ["Todos","Pendiente","Entregado","Cancelado"],
                               key="dat_status")

    mes_num = next((k for k,v in MESES.items() if v == mes_sel), None)

    # ── Filtrar ────────────────────────────────────────────────────────────────
    filas = []
    for p in todos:
        if p["año"] != año_sel: continue
        if mes_num and (not p["fecha"] or p["fecha"].month != mes_num): continue
        if cli_sel != "Todos" and p["cliente"] != cli_sel: continue
        if prod_sel != "Todos" and p["producto"] != prod_sel: continue
        if status_sel != "Todos" and p["status"] != status_sel: continue

        cli_d   = clientes.get(p["cliente"].lower().strip(), {})
        cod     = cli_d.get("codigo_lugar","")
        zona    = cod_zona.get(cod, "—")
        if zona_sel != "Todas" and zona != zona_sel: continue

        grupo   = cli_d.get("grupo","")
        precio  = float(p.get("precio") or 0)
        costo   = float(p.get("costo")  or 0)
        cant    = float(p.get("cantidad") or 0)
        total   = float(p.get("total")   or 0)
        mb      = round((precio - costo) * cant, 2)
        mn      = float(p.get("margen_q") or 0)
        base_iv = round(total / 1.12, 2) if total else 0
        liq, isr, desc = calcular_liquido(p["cliente"], total)

        filas.append({
            "Fecha":     p["fecha"].strftime("%d/%m/%Y") if p["fecha"] else "",
            "Sem":       p["semana"],
            "Mes":       MESES.get(p["fecha"].month,"") if p["fecha"] else "",
            "Cliente":   p["cliente"],
            "Zona":      zona,
            "Grupo":     grupo,
            "Producto":  p["producto"],
            "Proveedor": p.get("proveedor",""),
            "Cant":      cant,
            "Precio Q":  precio,
            "Costo Q":   costo,
            "Total Q":   total,
            "MB Q":      mb,
            "MN Q":      mn,
            "Base IVA":  base_iv,
            "ISR Q":     isr,
            "Líquido Q": liq,
            "Status":    p["status"],
        })

    if not filas:
        st.info("Sin datos para los filtros seleccionados.")
        return pd.DataFrame()

    df = pd.DataFrame(filas)

    # Totales al pie
    num_cols = ["Cant","Precio Q","Costo Q","Total Q","MB Q","MN Q",
                "Base IVA","ISR Q","Líquido Q"]
    tot = {c: df[c].sum() for c in num_cols}
    st.dataframe(df, hide_index=True, use_container_width=True,
                 height=min(600, 60 + len(df)*35))

    st.markdown(
        f"<div style='background:#e8f5e9;border-radius:6px;padding:8px 12px;"
        f"font-size:.82rem'>"
        f"<b>{len(df)} líneas</b> · "
        f"Ingreso: <b>{_fq(tot['Total Q'])}</b> · "
        f"MB: <b>{_fq(tot['MB Q'])}</b> · "
        f"MN: <b>{_fq(tot['MN Q'])}</b> · "
        f"Líquido: <b>{_fq(tot['Líquido Q'])}</b>"
        f"</div>", unsafe_allow_html=True)
    return df


# ── GASTOS ────────────────────────────────────────────────────────────────────
def _sabana_gastos():
    from modulo_gastos import _leer_gastos
    gastos = _leer_gastos()

    f1,f2,f3,f4,f5 = st.columns(5)
    años   = sorted({g["fecha"].year for g in gastos if g["fecha"]}, reverse=True)
    año_s  = f1.selectbox("Año", años, key="dg_año")
    mes_s  = f2.selectbox("Mes", ["Todos"]+[MESES[m] for m in range(1,13)], key="dg_mes")
    cat_s  = f3.selectbox("Categoría",
                          ["Todas"]+sorted({g["categoria"] for g in gastos}), key="dg_cat")
    area_s = f4.selectbox("Área",
                          ["Todas"]+sorted({g["area"] for g in gastos if g["area"]}),
                          key="dg_area")
    prov_s = f5.selectbox("Proveedor",
                          ["Todos"]+sorted({g["proveedor"] for g in gastos if g["proveedor"]}),
                          key="dg_prov")

    mes_num = next((k for k,v in MESES.items() if v == mes_s), None)
    filas = []
    for g in gastos:
        if not g["fecha"] or g["fecha"].year != año_s: continue
        if mes_num and g["fecha"].month != mes_num: continue
        if cat_s  != "Todas"  and g["categoria"]  != cat_s:  continue
        if area_s != "Todas"  and g["area"]        != area_s: continue
        if prov_s != "Todos"  and g["proveedor"]   != prov_s: continue
        filas.append({
            "Fecha":       g["fecha"].strftime("%d/%m/%Y"),
            "Sem":         g.get("semana",""),
            "Mes":         MESES.get(g["fecha"].month,""),
            "Categoría":   g["categoria"],
            "SubCat":      g["subcat"],
            "Área":        g["area"],
            "Frecuencia":  g.get("frecuencia",""),
            "Proveedor":   g["proveedor"],
            "Concepto":    g["concepto"],
            "Monto Q":     float(g["monto"] or 0),
        })

    if not filas:
        st.info("Sin gastos para los filtros."); return pd.DataFrame()

    df = pd.DataFrame(filas)
    st.dataframe(df, hide_index=True, use_container_width=True,
                 height=min(600, 60+len(df)*35))
    tot = df["Monto Q"].sum()
    st.markdown(
        f"<div style='background:#e8f5e9;border-radius:6px;padding:8px 12px;"
        f"font-size:.82rem'><b>{len(df)} registros</b> · "
        f"Total: <b>{_fq(tot)}</b></div>", unsafe_allow_html=True)
    return df


# ── CLIENTES ──────────────────────────────────────────────────────────────────
def _sabana_clientes():
    from data_helper import cargar_clientes
    from config      import ZONAS_MAP

    cod_zona = {}
    for zona, cods in ZONAS_MAP.items():
        for c in cods: cod_zona[c] = zona

    clientes = cargar_clientes()
    f1,f2,f3,f4 = st.columns(4)
    zona_s = f1.selectbox("Zona",   ["Todas"]+list(ZONAS_MAP.keys()), key="dc_zona")
    tipo_s = f2.selectbox("Tipo",   ["Todos"]+sorted({c["tipo"] for c in clientes}),
                           key="dc_tipo")
    est_s  = f3.selectbox("Estatus",["Todos","Cliente","Pendiente","Inactivo"],
                           key="dc_est")
    grp_s  = f4.selectbox("Grupo",  ["Todos"]+sorted({c.get("grupo","") for c in clientes
                                                       if c.get("grupo","")}), key="dc_grp")
    filas = []
    for c in clientes:
        cod  = c.get("codigo_lugar","")
        zona = cod_zona.get(cod,"—")
        if zona_s != "Todas"  and zona != zona_s: continue
        if tipo_s != "Todos"  and c["tipo"] != tipo_s: continue
        if est_s  != "Todos"  and c["estatus"] != est_s: continue
        if grp_s  != "Todos"  and c.get("grupo","") != grp_s: continue
        filas.append({
            "Nombre":   c["nombre"],
            "Tipo":     c["tipo"],
            "Zona":     zona,
            "Código":   cod,
            "Grupo":    c.get("grupo",""),
            "Estatus":  c["estatus"],
            "Empresa":  c.get("empresa",""),
            "NIT":      c.get("nit",""),
            "Crédito":  "Sí" if c.get("credito") else "No",
        })
    if not filas:
        st.info("Sin clientes para los filtros."); return pd.DataFrame()
    df = pd.DataFrame(filas)
    st.dataframe(df, hide_index=True, use_container_width=True,
                 height=min(600, 60+len(df)*35))
    st.caption(f"{len(df)} clientes")
    return df


# ── PRODUCTOS ─────────────────────────────────────────────────────────────────
def _sabana_productos():
    from excel_helper import leer_productos_con_fila
    prods = leer_productos_con_fila(es_antigua=False)
    f1,f2,f3 = st.columns(3)
    seg_s  = f1.selectbox("Segmento", ["Todos"]+sorted({p.get("segmento","")
                          for p in prods if p.get("segmento","")}), key="dp_seg")
    prov_s = f2.selectbox("Proveedor",["Todos"]+sorted({p.get("proveedor","")
                          for p in prods if p.get("proveedor","")}), key="dp_prov")
    txt_s  = f3.text_input("Buscar nombre", key="dp_txt")

    filas = []
    for p in prods:
        if seg_s  != "Todos" and p.get("segmento","") != seg_s:  continue
        if prov_s != "Todos" and p.get("proveedor","") != prov_s: continue
        if txt_s  and txt_s.lower() not in p["nombre"].lower(): continue
        filas.append({
            "Producto":  p["nombre"],
            "Segmento":  p.get("segmento",""),
            "Unidad":    p.get("unidad",""),
            "Costo Q":   float(p.get("costo") or 0),
            "Precio Q":  float(p.get("precio") or 0),
            "Proveedor": p.get("proveedor",""),
            "Parent":    p.get("parent",""),
            "Tipo":      p.get("tipo_producto",""),
        })
    if not filas:
        st.info("Sin productos para los filtros."); return pd.DataFrame()
    df = pd.DataFrame(filas)
    st.dataframe(df, hide_index=True, use_container_width=True,
                 height=min(600, 60+len(df)*35))
    st.caption(f"{len(df)} productos")
    return df


# ── SYNC AL SHEET ─────────────────────────────────────────────────────────────
def _sync_sheet(df: pd.DataFrame, hoja: str = "datoscompletos"):
    """Sobreescribe la hoja DatosCompletos con el DataFrame actual."""
    from gsheets import ws as _ws
    try:
        sheet = _ws(hoja)
        sheet.clear()
        header = df.columns.tolist()
        rows   = [header] + [[str(v) for v in row] for row in df.values]
        sheet.update("A1", rows)
        return True, len(df)
    except Exception as e:
        return False, str(e)


# ── MOSTRAR ────────────────────────────────────────────────────────────────────
def mostrar():
    st.markdown("## 🗂️ Datos")
    if st.button("Inicio", key="btn_home_dat", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    tipo = st.radio("Tipo de datos",
                    ["📦 Pedidos","💸 Gastos","👤 Clientes","🛒 Productos"],
                    horizontal=True, key="dat_tipo")
    st.divider()

    df = pd.DataFrame()
    if tipo == "📦 Pedidos":
        df = _sabana_pedidos()
    elif tipo == "💸 Gastos":
        df = _sabana_gastos()
    elif tipo == "👤 Clientes":
        df = _sabana_clientes()
    elif tipo == "🛒 Productos":
        df = _sabana_productos()

    if df is not None and not df.empty:
        st.divider()
        d1, d2, d3 = st.columns(3)

        # CSV
        csv = df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        d1.download_button("⬇️ Descargar CSV", data=csv,
                           file_name=f"VeggiExpress_{tipo.split()[-1]}_{date.today()}.csv",
                           mime="text/csv", key="dat_csv")

        # Excel
        d2.download_button("⬇️ Descargar Excel",
                           data=_df_to_excel(df),
                           file_name=f"VeggiExpress_{tipo.split()[-1]}_{date.today()}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="dat_xlsx")

        # Sync al Sheet
        if d3.button("🔄 Sincronizar al Sheet", key="dat_sync",
                     help="Sobreescribe la hoja 'DatosCompletos' con la vista actual"):
            with st.spinner("Sincronizando..."):
                ok, res = _sync_sheet(df)
            if ok:
                st.success(f"✅ {res} filas escritas en 'DatosCompletos'.")
            else:
                st.error(f"Error: {res}")
