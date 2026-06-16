"""
modulo_hogares.py — Importación de pedidos desde Google Form Hogares.
Flujo: leer respuestas → revisar → confirmar → crear pedidos.
"""
import streamlit as st
import re, unicodedata, json
from datetime import date, datetime

# ID del Sheet de respuestas del formulario actual
FORM_SHEET_ID = "1QZX-KmaBK9k41vxsve9IFsKqgigK9rb5cBVUc3snnUk"

# Columnas no-producto del formulario (se ignoran al buscar productos)
_SKIP_COLS = {
    "marca temporal", "nombre y apellido", "dirección de entrega",
    "dirección de correo electrónico", "correo electrónico",
    "método de pago", "teléfono contacto", "telefono contacto",
    "mi pedido está listo", "puntuación", "productos extra",
    "veggipack", "fruitpack", "ponchePack", "fiambrepack",
    "nombre y apellido2",
}

MESES = {1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",
         7:"Jul",8:"Ago",9:"Sep",10:"Oct",11:"Nov",12:"Dic"}


# ── Helpers ────────────────────────────────────────────────────────────────────
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii","ignore").decode()
    return " ".join(s.lower().split())


def _parse_col_header(h: str) -> dict | None:
    """'Tomate (Libra) - Q.5.00' → {nombre, unidad, precio}"""
    m = re.match(r'^(.+?)\s*\((.+?)\)\s*[-–]\s*Q[.\s]*([\d.,]+)', h.strip())
    if m:
        try:
            precio = float(m.group(3).replace(",",".").strip())
            return {"nombre": m.group(1).strip(),
                    "unidad": m.group(2).strip(),
                    "precio": precio}
        except Exception:
            pass
    return None


def _abrir_form_sheet():
    """Abre el Sheet de respuestas con la service account."""
    import gspread
    from google.oauth2.service_account import Credentials

    SCOPES = ["https://spreadsheets.google.com/feeds",
              "https://www.googleapis.com/auth/drive"]
    if "GOOGLE_CREDENTIALS" in st.secrets:
        info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    else:
        info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    gc    = gspread.authorize(creds)
    return gc.open_by_key(FORM_SHEET_ID).sheet1


def _get_imported_timestamps() -> set:
    """Timestamps ya importados (de la hoja FormImports)."""
    try:
        from gsheets import get_all_rows
        return {str(r[0]).strip() for r in get_all_rows("formimports") if r}
    except Exception:
        return set()


def _registrar_importado(timestamp: str, cliente: str, n_lineas: int):
    from gsheets import append_rows
    hoy = date.today().strftime("%d/%m/%Y")
    append_rows("formimports", [[timestamp, hoy, cliente, n_lineas]])


def _match_producto(nombre_form: str, cat_map: dict) -> tuple[str | None, str]:
    """
    Intenta matchear nombre del formulario con el catálogo.
    Retorna (nombre_catalogo, tipo_match) | (None, "sin match")
    """
    nf = _norm(nombre_form)
    if nf in cat_map:
        return cat_map[nf], "exacto"
    # Coincidencia parcial — el nombre del form está contenido en el catálogo o viceversa
    for k, v in cat_map.items():
        if nf in k or k in nf:
            return v, "parcial"
    return None, "sin match"


# ── Leer y parsear respuestas ─────────────────────────────────────────────────
def _leer_respuestas() -> tuple[list[str], list[list]]:
    """Retorna (headers, rows) del sheet de respuestas."""
    try:
        sheet = _abrir_form_sheet()
        todas = sheet.get_all_values()
        if not todas:
            return [], []
        return todas[0], todas[1:]
    except Exception as e:
        st.error(f"Error leyendo formulario: {e}")
        return [], []


def _parsear_respuesta(headers: list, row: list,
                       cat_map: dict, cli_map: dict) -> dict:
    """Convierte una fila del formulario en un dict estructurado."""
    # Encontrar columnas clave
    def _find(keywords):
        for i, h in enumerate(headers):
            hn = h.lower().strip()
            if any(k in hn for k in keywords):
                return str(row[i] if i < len(row) else "").strip()
        return ""

    timestamp  = _find(["marca temporal"])
    nombre_cli = _find(["nombre y apellido"])
    direccion  = _find(["dirección de entrega", "direccion de entrega"])
    pago       = _find(["método de pago", "metodo de pago"])
    email      = _find(["correo electrónico", "correo electronico",
                         "dirección de correo"])
    telefono   = _find(["teléfono", "telefono"])

    # Match cliente por email
    cli = None
    email_l = email.lower().strip()
    if email_l:
        cli = cli_map.get(email_l)

    # Parsear productos
    lineas, sin_match = [], []
    for i, h in enumerate(headers):
        if _norm(h)[:30] in _SKIP_COLS:
            continue
        parsed = _parse_col_header(h)
        if not parsed:
            continue
        val = str(row[i] if i < len(row) else "").strip()
        if not val or val == "0":
            continue
        try:
            cant = float(val)
        except Exception:
            continue
        if cant <= 0:
            continue

        prod_cat, match_tipo = _match_producto(parsed["nombre"], cat_map)
        entry = {
            "nombre_form": parsed["nombre"],
            "unidad_form": parsed["unidad"],
            "cantidad":    cant,
            "prod_cat":    prod_cat,
            "match":       match_tipo,
        }
        if prod_cat:
            lineas.append(entry)
        else:
            sin_match.append(entry)

    return {
        "timestamp": timestamp, "nombre_cli": nombre_cli,
        "direccion": direccion, "pago": pago,
        "email": email, "telefono": telefono,
        "cliente": cli,
        "lineas": lineas, "sin_match": sin_match,
    }


# ── Importar pedido confirmado ────────────────────────────────────────────────
def _importar_pedido(resp: dict, fecha_ent: date,
                     cat_info: dict, cli_precios_fn):
    """Crea las líneas del pedido en el Sheet de Pedidos."""
    from order_helper import guardar_pedidos_batch
    import uuid

    nombre_cli = resp["cliente"]["nombre"] if resp["cliente"] else resp["nombre_cli"]
    unico      = f"HOG_{fecha_ent.strftime('%Y%m%d')}_{str(uuid.uuid4())[:6].upper()}"

    items = []
    for l in resp["lineas"]:
        prod    = cat_info.get(l["prod_cat"], {})
        precio, _ = cli_precios_fn(resp["cliente"] or {}, l["prod_cat"])
        if precio <= 0:
            precio = float(prod.get("precio") or 0)
        items.append({
            "nombre":   l["prod_cat"],
            "unidad":   prod.get("unidad", l["unidad_form"]),
            "cantidad": l["cantidad"],
            "precio":   precio,
            "costo":    float(prod.get("costo") or 0),
        })

    guardar_pedidos_batch(nombre_cli, fecha_ent, items, unico=unico)
    _registrar_importado(resp["timestamp"], nombre_cli, len(items))
    return len(items)


# ── UI principal ───────────────────────────────────────────────────────────────
def _tab_formulario():
    """Tab para crear/sincronizar el formulario Google Forms."""
    from forms_helper import (crear_formulario, sincronizar_formulario,
                               get_form_id, _productos_hogares)

    st.markdown("#### Formulario Google Forms — Hogares")
    st.caption("Crea y mantiene actualizado el formulario que usan las familias "
               "para hacer sus pedidos.")

    form_id = get_form_id()

    if form_id:
        form_url = f"https://docs.google.com/forms/d/{form_id}/viewform"
        edit_url = f"https://docs.google.com/forms/d/{form_id}/edit"
        st.success(f"✅ Formulario activo")
        st.markdown(f"**Link para familias:** [Abrir formulario]({form_url})")
        st.caption(f"Link de edición: {edit_url}")
        st.divider()

        # Preview de productos
        prods = _productos_hogares()
        st.markdown(f"**{len(prods)} productos** se incluirán en el formulario:")
        import pandas as pd
        df = pd.DataFrame([{
            "Segmento": p["segmento"],
            "Producto": p["nombre"],
            "Unidad":   p["unidad"],
            "Precio Q": p["precio"],
        } for p in prods])
        st.dataframe(df, hide_index=True, use_container_width=True,
                     height=min(400, 60+len(df)*35))

        st.divider()
        st.markdown("**Sincronizar catálogo con el formulario**")
        st.caption("Actualiza los precios y agrega productos nuevos. "
                   "No elimina productos existentes para no perder respuestas.")
        if st.button("🔄 Sincronizar precios y productos", type="primary",
                     key="hog_sync_form"):
            with st.spinner("Sincronizando..."):
                try:
                    res = sincronizar_formulario(form_id)
                    st.success(
                        f"✅ Sincronización completa — "
                        f"Actualizados: {res['actualizados']} · "
                        f"Nuevos: {res['agregados']} · "
                        f"Sin cambio: {res['sin_cambio']}")
                except Exception as e:
                    st.error(f"Error: {e}")

    else:
        st.info("Todavía no hay un formulario creado. "
                "Crea uno nuevo con el botón de abajo.")
        prods = _productos_hogares()
        st.markdown(f"Se crearán **{len(prods)} preguntas** de productos, "
                    f"agrupadas por segmento.")

    st.divider()
    titulo_f = st.text_input("Título del formulario",
                              value="Pedidos Veggi Hogares",
                              key="hog_form_titulo")
    accion = "Actualizar formulario existente" if form_id else "Crear formulario nuevo"
    if st.button(f"📋 {accion}", type="primary" if not form_id else "secondary",
                 key="hog_crear_form"):
        with st.spinner("Creando formulario en Google Forms..."):
            try:
                res = crear_formulario(titulo=titulo_f)
                st.success(
                    f"✅ Formulario creado con {res['n_productos']} productos.")
                st.markdown(
                    f"**Link para familias:** 🔗 [{res['form_url']}]({res['form_url']})")
                st.caption(
                    f"Link de edición: {res['edit_url']}")
                st.rerun()
            except Exception as e:
                st.error(f"Error creando formulario: {e}")


def mostrar():
    st.markdown("## 🏠 Hogares")
    if st.button("Inicio", key="btn_home_hog", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    tab_imp, tab_form = st.tabs(["📥 Importar Pedidos", "📋 Formulario"])
    with tab_imp:
        _tab_importar()
    with tab_form:
        _tab_formulario()

def _tab_importar():
    from data_helper import cargar_clientes, cargar_productos, cli_precio
    from excel_helper import leer_productos_con_fila
    # ── Preparar catálogo y mapa de clientes ──────────────────────────────────
    prods_gen  = leer_productos_con_fila(es_antigua=False)
    # cat_map: nombre_normalizado → nombre_exacto
    cat_map    = {_norm(p["nombre"]): p["nombre"] for p in prods_gen}
    # cat_info: nombre_exacto → dict de producto
    cat_info   = {p["nombre"]: p for p in prods_gen}
    # cli_map: email_lower → cliente_dict
    clientes   = cargar_clientes()
    cli_map    = {c["email"]: c for c in clientes if c.get("email")}

    # ── Parámetros de importación ─────────────────────────────────────────────
    c1, c2 = st.columns(2)
    fecha_ent = c1.date_input("📅 Fecha de entrega", value=date.today(),
                               key="hog_fecha")
    semana    = fecha_ent.isocalendar()[1]
    año       = fecha_ent.year
    c2.metric("Semana", f"{semana} / {año}")

    st.divider()
    if not st.button("🔄 Leer formulario", type="primary", key="hog_leer"):
        st.info("Elegí la fecha de entrega y presioná 'Leer formulario'.")
        return

    # ── Leer respuestas ───────────────────────────────────────────────────────
    with st.spinner("Leyendo respuestas del formulario..."):
        headers, rows = _leer_respuestas()
        ya_importados = _get_imported_timestamps()

    if not rows:
        st.warning("Sin respuestas en el formulario.")
        return

    nuevas = [r for r in rows
              if r and str(r[0]).strip() not in ya_importados]

    st.success(f"**{len(nuevas)}** respuesta(s) nuevas · "
               f"{len(rows)-len(nuevas)} ya importadas (omitidas)")

    if not nuevas:
        st.info("Todo está al día — sin pedidos pendientes de importar.")
        return

    st.divider()
    # ── Tarjeta por respuesta ─────────────────────────────────────────────────
    for idx, row in enumerate(nuevas):
        resp = _parsear_respuesta(headers, row, cat_map, cli_map)
        ts   = resp["timestamp"]

        # Header de la tarjeta
        cli_ok = resp["cliente"] is not None
        email_disp = resp["email"] or "sin email"
        nombre_disp = (resp["cliente"]["nombre"] if cli_ok
                       else resp["nombre_cli"] or "Desconocido")
        icono = "✅" if cli_ok else "⚠️"

        with st.expander(
            f"{icono} {nombre_disp} · {email_disp} · "
            f"{len(resp['lineas'])} producto(s)",
            expanded=True
        ):
            # Info del cliente
            if cli_ok:
                st.caption(f"👤 Cliente registrado: **{nombre_disp}** · "
                           f"📍 {resp['direccion']} · 💳 {resp['pago']}")
            else:
                st.warning("Email no encontrado en la base de clientes. "
                           "Asigná manualmente:")
                nombres_cli = ["— seleccionar —"] + \
                              sorted(c["nombre"] for c in clientes
                                     if c.get("tipo","").lower() == "hogar")
                sel = st.selectbox("Cliente", nombres_cli,
                                   key=f"hog_cli_{idx}")
                if sel != "— seleccionar —":
                    resp["cliente"] = next(
                        (c for c in clientes if c["nombre"] == sel), None)

            # Tabla de productos
            if resp["lineas"]:
                import pandas as pd
                filas_df = []
                for l in resp["lineas"]:
                    prod = cat_info.get(l["prod_cat"], {})
                    precio_c, fuente = cli_precio(
                        resp["cliente"] or {}, l["prod_cat"])
                    if precio_c <= 0:
                        precio_c = float(prod.get("precio") or 0)
                    filas_df.append({
                        "Formulario":  l["nombre_form"],
                        "→ Catálogo":  l["prod_cat"],
                        "Match":       l["match"],
                        "Cant":        l["cantidad"],
                        "Precio Q":    precio_c,
                        "Total Q":     round(precio_c * l["cantidad"], 2),
                    })
                df = pd.DataFrame(filas_df)
                total_est = df["Total Q"].sum()
                st.dataframe(df, hide_index=True, use_container_width=True)
                st.markdown(
                    f"<div style='text-align:right;font-size:.85rem;"
                    f"font-weight:bold;color:#2D7A2D'>"
                    f"Total estimado: Q{total_est:,.2f}</div>",
                    unsafe_allow_html=True)

            # Sin match
            if resp["sin_match"]:
                with st.expander(
                    f"⚠️ {len(resp['sin_match'])} producto(s) sin match "
                    f"en el catálogo", expanded=False
                ):
                    for l in resp["sin_match"]:
                        st.write(f"  · {l['nombre_form']} "
                                 f"× {l['cantidad']} {l['unidad_form']}")
                    st.caption("Estos NO se importan. Si deben estar, "
                               "agregá el producto al catálogo con el "
                               "nombre exacto del formulario.")

            # Botones
            b1, b2 = st.columns(2)
            if b1.button("✅ Importar pedido", type="primary",
                         key=f"hog_imp_{idx}",
                         disabled=not resp["lineas"] or resp["cliente"] is None):
                with st.spinner("Guardando..."):
                    n = _importar_pedido(resp, fecha_ent, cat_info, cli_precio)
                st.success(f"✅ {n} línea(s) importadas para "
                           f"{resp['cliente']['nombre']}.")
                st.rerun()

            if b2.button("⏭️ Omitir", key=f"hog_skip_{idx}",
                         help="Marca como procesada sin crear pedido"):
                _registrar_importado(ts, resp["nombre_cli"] or "omitido", 0)
                st.rerun()

    st.divider()
    st.caption(f"Sheet del formulario: `{FORM_SHEET_ID}`")
