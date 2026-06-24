"""
modulo_hogares.py — Importación de pedidos desde Google Form Hogares.
Flujo: leer respuestas → revisar → confirmar → crear pedidos.
"""
import streamlit as st
import re, unicodedata, json
from datetime import date, datetime

# ID del Sheet de respuestas del formulario actual
FORM_SHEET_ID  = "1yNaN5m_1-cAeQDizMJRbDgUlQ6yqVcFk5BYvKzTEdiM"
_HOG_SEL_KEY  = "hog_form_seleccion"   # clave de session_state
_HOG_INIT_KEY = "hog_form_init"
_HOG_VER_KEY  = "hog_form_ver"

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
    """Abre el Sheet de respuestas con la service account.
    Reutiliza el cliente gspread central (gsheets) para usar las mismas
    credenciales que el resto de la app."""
    # Reusar la conexión central — mismas credenciales que toda la app
    try:
        from gsheets import _gc as _gc_central
        gc = _gc_central()
    except Exception:
        # Fallback: crear cliente propio
        import gspread
        from google.oauth2.service_account import Credentials
        SCOPES = ["https://spreadsheets.google.com/feeds",
                  "https://www.googleapis.com/auth/drive",
                  "https://www.googleapis.com/auth/spreadsheets"]
        if "GOOGLE_CREDENTIALS" in st.secrets:
            info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
        elif "gcp_service_account" in st.secrets:
            info = dict(st.secrets["gcp_service_account"])
        else:
            raise RuntimeError("No se encontraron credenciales en st.secrets "
                               "(ni GOOGLE_CREDENTIALS ni gcp_service_account)")
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        gc = gspread.authorize(creds)
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
        _msg = str(e) or type(e).__name__
        st.error(f"Error leyendo formulario: {_msg}")
        # Diagnóstico útil según el tipo de error
        _el = _msg.lower()
        if "permission" in _el or "403" in _el or "does not have" in _el:
            st.warning(
                "El Sheet de respuestas no está compartido con la cuenta de "
                "servicio. Abrí el Sheet de respuestas del formulario → "
                "Compartir → agregá el email de la service account "
                "(client_email en tus credenciales) como **Lector** o **Editor**.")
        elif "not found" in _el or "404" in _el or "unable to open" in _el:
            st.warning(
                f"No se encontró el Sheet con ID `{FORM_SHEET_ID}`. Verificá "
                "que sea el ID del **Sheet de respuestas** (no del formulario). "
                "En el form: Respuestas → ícono de Sheets → copiá el ID de la "
                "URL del Sheet que se abre.")
        elif "secrets" in _el or "credential" in _el:
            st.warning("Problema con las credenciales en st.secrets.")
        else:
            st.warning(f"Tipo de error: {type(e).__name__}. "
                       "Revisá el log en 'Manage app' para más detalle.")
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
    lineas, sin_match, prod_extra = [], [], []
    for i, h in enumerate(headers):
        if _norm(h)[:30] in _SKIP_COLS:
            continue
        # Detectar campo especial Productos Extra
        if _norm(h)[:15] == "productos extra":
            val_extra = str(row[i] if i < len(row) else "").strip()
            if val_extra:
                prod_extra.append(val_extra)
            continue
        # Saltar campo de confirmación
        if "confirmo mi pedido" in h.lower() or "total a pagar" in h.lower():
            continue

        parsed = _parse_col_header(h)
        if not parsed:
            continue
        val = str(row[i] if i < len(row) else "").strip()
        if not val or val in ("0", "—", ""):
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
        "prod_extra": prod_extra,
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
            "unidad":   prod.get("unidad") or "",  # siempre del catálogo, nunca del form
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
    import pandas as pd
    from forms_helper import (crear_formulario, sincronizar_formulario,
                               get_form_id, _productos_hogares,
                               leer_productos_en_form)

    st.markdown("#### Formulario Google Forms — Hogares")
    st.caption("Seleccioná los productos que querés incluir, "
               "luego generá o sincronizá el formulario.")

    # ── Estado activo ─────────────────────────────────────────────────────────
    form_id = get_form_id()
    if form_id:
        form_url = f"https://docs.google.com/forms/d/{form_id}/viewform"
        col_a, col_b, col_c = st.columns([3, 0.8, 0.8])
        col_a.success(f"✅ Formulario activo — "
                      f"[Link para familias]({form_url})")
        if col_b.button("📋 Link", key="hog_copy_link"):
            st.write(f"`{form_url}`")
        if col_c.button("🔀 Cambiar", key="hog_change_form",
                        help="Configurar un formulario diferente"):
            from forms_helper import _save_form_id
            _save_form_id("")
            st.session_state.pop(_HOG_INIT_KEY, None)
            st.rerun()

    # ── Selector de productos ────────────────────────────────────────────────
    todos = _productos_hogares()
    nombres_todos = [p["nombre"] for p in todos]

    # Inicializar con todos seleccionados la primera vez
    if _HOG_INIT_KEY not in st.session_state:
        if form_id:
            try:
                from forms_helper import leer_productos_en_form as _lpf2
                en_form_init = _lpf2(form_id)
                st.session_state[_HOG_SEL_KEY] = {
                    n for n in en_form_init if n in set(nombres_todos)}
            except Exception:
                # 404 o sin acceso — empezar con todos seleccionados
                st.session_state[_HOG_SEL_KEY] = set(nombres_todos)
        else:
            st.session_state[_HOG_SEL_KEY] = set(nombres_todos)
        st.session_state[_HOG_INIT_KEY] = True
    ver = st.session_state.get(_HOG_VER_KEY, 0)

    st.markdown("##### Productos a incluir en el formulario")

    # Botón para recargar selección desde el formulario actual
    if form_id:
        if st.button("🔄 Recargar lista desde el formulario actual",
                     key="hog_reload_form"):
            try:
                from forms_helper import leer_productos_en_form as _lpf
                en_form = _lpf(form_id)
                st.session_state[_HOG_SEL_KEY] = {
                    n for n in en_form if n in set(nombres_todos)}
                st.session_state[_HOG_VER_KEY] = ver + 1
                st.rerun()
            except Exception as e:
                st.error(f"Error leyendo el formulario: {e}")

    # Filtros para la tabla de referencia
    col_f1, col_f2 = st.columns(2)
    seg_f = col_f1.selectbox("Segmento", ["Todos"] +
                              sorted({p["segmento"] for p in todos}),
                              key="hog_seg_filter")
    txt_f = col_f2.text_input("Buscar", placeholder="nombre...",
                               key="hog_txt_filter")

    # Tabla de referencia (read-only) — precios visibles
    prods_vis = [p for p in todos
                 if (seg_f == "Todos" or p["segmento"] == seg_f) and
                    (not txt_f or txt_f.lower() in p["nombre"].lower())]

    sel_actual = st.session_state[_HOG_SEL_KEY]

    ref_df = pd.DataFrame([{
        "Estado":   "📋 En formulario" if p["nombre"] in sel_actual
                    else "➕ No incluido",
        "Segmento": p["segmento"],
        "Producto": p["nombre"],
        "Unidad":   p["unidad"],
        "Q":        p["precio"],
    } for p in prods_vis])

    if not ref_df.empty:
        st.dataframe(ref_df, hide_index=True, use_container_width=True,
                     height=min(320, 60 + len(ref_df)*35))

    st.caption(f"↑ Vista filtrada — {len(sel_actual)} de {len(todos)} "
               f"productos seleccionados en total.")

    # ── Multiselect (fuente de verdad confiable) ──────────────────────────────
    # Usamos multiselect en un expander para no ocupar tanto espacio
    with st.expander("✏️ Editar selección de productos", expanded=False):
        st.caption("Buscá y agregá/quitá productos. "
                   "Los botones de abajo marcan/desmarcan todo.")

        sel_nueva = st.multiselect(
            "Productos incluidos en el formulario",
            options=nombres_todos,
            default=[n for n in nombres_todos if n in sel_actual],
            key=f"hog_multiselect_{ver}",   # version para forzar reset
            label_visibility="collapsed",
        )
        st.session_state[_HOG_SEL_KEY] = set(sel_nueva)

        bc1, bc2 = st.columns(2)
        if bc1.button("☑ Marcar todos", key="hog_sel_all"):
            st.session_state[_HOG_SEL_KEY] = set(nombres_todos)
            st.session_state[_HOG_VER_KEY]      = ver + 1
            st.rerun()
        if bc2.button("☐ Desmarcar todos", key="hog_des_all"):
            st.session_state[_HOG_SEL_KEY] = set()
            st.session_state[_HOG_VER_KEY]      = ver + 1
            st.rerun()

    n_sel = len(st.session_state[_HOG_SEL_KEY])
    st.caption(f"{n_sel} de {len(todos)} productos seleccionados.")

    # ── Título y acciones ─────────────────────────────────────────────────────
    st.divider()
    st.markdown("##### Actualizar formulario")
    st.caption("La app actualiza tu formulario EXISTENTE con los productos "
               "seleccionados y sus precios actuales del catálogo. "
               "El link para las familias **no cambia**.")

    # Campo para ingresar / cambiar el ID del formulario
    if not form_id:
        st.info("📋 Ingresá el ID del formulario que querés usar. "
                "Lo encontrás en la URL: `docs.google.com/forms/d/`**[ID]**`/edit`  ·  "
                "Compartilo con `rio-veggi-app@rio-veggi-app.iam.gserviceaccount.com` "
                "como **Editor** antes de actualizar.")
    fid_input = st.text_input(
        "ID del formulario",
        value=form_id or "",
        placeholder="1FAIpQLSe...",
        key="hog_form_id_input",
        label_visibility="collapsed" if form_id else "visible",
    )

    prods_sel = [p for p in todos
                 if p["nombre"] in st.session_state.get(_HOG_SEL_KEY, set())]

    if st.button("🔄 Actualizar formulario con precios y productos actuales",
                 type="primary",
                 key="hog_actualizar_form",
                 disabled=not fid_input.strip() or not prods_sel):
        with st.spinner(f"Actualizando {len(prods_sel)} productos en el formulario..."):
            try:
                from forms_helper import actualizar_formulario
                res = actualizar_formulario(fid_input.strip(), productos=prods_sel)
                st.success(
                    f"✅ {res['eliminados']} preguntas antiguas eliminadas · "
                    f"{res['agregados']} productos agregados con precios actuales.")
                st.markdown(
                    f"**🔗 Link para familias:** "
                    f"[{res['form_url']}]({res['form_url']})")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
                st.caption("Verificá que el formulario esté compartido con "
                           "rio-veggi-app@rio-veggi-app.iam.gserviceaccount.com "
                           "como Editor.")


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

    # ── Diagnóstico de conexión ───────────────────────────────────────────────
    with st.expander("🔧 Diagnóstico de conexión al formulario", expanded=False):
        st.caption(f"Sheet de respuestas ID: `{FORM_SHEET_ID}`")
        # Mostrar email de la service account (necesario para compartir el Sheet)
        try:
            if "GOOGLE_CREDENTIALS" in st.secrets:
                _info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
            else:
                _info = dict(st.secrets.get("gcp_service_account", {}))
            _email_sa = _info.get("client_email", "(no encontrado)")
            st.caption(f"Cuenta de servicio: `{_email_sa}`")
            st.caption("Este email debe tener acceso de **Lector** al Sheet de "
                       "respuestas (Compartir → agregar este email).")
        except Exception as _ce:
            st.caption(f"No se pudo leer el email de la cuenta: {_ce}")
        if st.button("🔍 Probar conexión", key="hog_test_conn"):
            try:
                _sh = _abrir_form_sheet()
                _vals = _sh.get_all_values()
                st.success(f"✅ Conexión OK — {len(_vals)} fila(s) en el Sheet "
                           f"(incluyendo encabezado).")
                if _vals:
                    st.caption(f"Encabezados detectados: {len(_vals[0])} columnas")
            except Exception as _te:
                st.error(f"❌ Falló: {type(_te).__name__}: {_te}")

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

            # Productos Extra (campo libre)
            if resp.get("prod_extra"):
                st.warning(
                    f"📝 **Productos Extra** (no importados automáticamente):\n"
                    + "\n".join(f"  · {t}" for t in resp["prod_extra"]))

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
