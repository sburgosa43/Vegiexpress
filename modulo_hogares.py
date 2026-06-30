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
        _ensure_formimports()
        from gsheets import get_all_rows
        return {str(r[0]).strip() for r in get_all_rows("formimports") if r}
    except Exception:
        return set()


def _ensure_formimports():
    """Crea la hoja FormImports si no existe."""
    from gsheets import ensure_ws
    try:
        ensure_ws("formimports",
                  ["timestamp", "fecha_import", "cliente", "n_lineas"])
    except Exception as e:
        if "already exists" not in str(e).lower():
            raise


def _registrar_importado(timestamp: str, cliente: str, n_lineas: int):
    from gsheets import append_rows
    _ensure_formimports()
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
@st.cache_data(ttl=60, show_spinner=False)
def _leer_respuestas() -> tuple[list[str], list[list]]:
    """Retorna (headers, rows) del sheet de respuestas. Cacheado 60s para
    no saturar la cuota de lecturas de Google Sheets."""
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
    """Crea las líneas del pedido en el Sheet de Pedidos.
    Retorna dict con diagnóstico: {filas, items_armados, nombre_cli, detalle}."""
    from order_helper import guardar_pedidos_batch

    nombre_cli = resp["cliente"]["nombre"] if resp["cliente"] else resp["nombre_cli"]

    items = []
    detalle = []
    for l in resp["lineas"]:
        prod    = cat_info.get(l["prod_cat"], {})
        precio, _ = cli_precios_fn(resp["cliente"] or {}, l["prod_cat"])
        if precio <= 0:
            precio = float(prod.get("precio") or 0)
        cant = float(l["cantidad"] or 0)
        items.append({
            "nombre":   l["prod_cat"],
            "unidad":   prod.get("unidad") or "",
            "cantidad": cant,
            "precio":   precio,
            "costo":    float(prod.get("costo") or 0),
        })
        detalle.append(f"{l['prod_cat']} x{cant} @Q{precio:.2f}")

    if not items:
        return {"filas": 0, "items_armados": 0, "nombre_cli": nombre_cli,
                "detalle": detalle, "error": "Sin items (lineas vacías)"}

    try:
        res = guardar_pedidos_batch([{
            "cliente_nombre": nombre_cli,
            "fecha":          fecha_ent,
            "items":          items,
        }])
    except Exception as e:
        return {"filas": 0, "items_armados": len(items), "nombre_cli": nombre_cli,
                "detalle": detalle, "error": f"{type(e).__name__}: {e}"}

    filas = res.get("filas", 0) if isinstance(res, dict) else 0
    if filas > 0:
        _registrar_importado(resp["timestamp"], nombre_cli, len(items))
    return {"filas": filas, "items_armados": len(items), "nombre_cli": nombre_cli,
            "detalle": detalle, "error": None, "res": res}


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
    """Importación de pedidos desde el formulario.

    Flujo limpio:
      1. Leer formulario (respuestas nuevas, no importadas) — cacheado.
      2. Cada pedido se muestra con: checkbox, cliente (auto/manual/crear),
         productos con match, alertas de sin-match, y campo de texto libre
         (productos extra) donde se pueden agregar productos del catálogo.
      3. Botón único "Importar seleccionados" (fuera de las tarjetas).

    Pensado genérico para reutilizar en Hoteles y Restaurantes: solo cambia
    la configuración (FORM_SHEET_ID y las columnas a ignorar).
    """
    from data_helper import cargar_clientes, cli_precio
    from excel_helper import leer_productos_con_fila

    # ── Catálogo y mapa de clientes ───────────────────────────────────────────
    prods_gen = leer_productos_con_fila(es_antigua=False)
    cat_map   = {_norm(p["nombre"]): p["nombre"] for p in prods_gen}
    cat_info  = {p["nombre"]: p for p in prods_gen}
    nombres_catalogo = sorted(p["nombre"] for p in prods_gen)

    clientes = cargar_clientes()
    cli_map  = {c["email"].lower().strip(): c
                for c in clientes if c.get("email")}
    nombres_clientes = sorted(c["nombre"] for c in clientes if c.get("nombre"))

    # ── Procesar importación pendiente (al inicio, fuera de tarjetas) ──────────
    if "hog_do_import" in st.session_state:
        intento = st.session_state.pop("hog_do_import")
        _ejecutar_importacion(intento, cat_info, cli_precio)

    # ── Encabezado y botón de lectura ─────────────────────────────────────────
    st.markdown("### 📥 Importar pedidos del formulario")
    c1, c2 = st.columns([1, 1])
    with c1:
        leer = st.button("🔄 Leer formulario", type="primary",
                         key="hog_leer_form", use_container_width=True)
    with c2:
        if st.button("🧹 Limpiar registro de importados",
                     key="hog_limpiar_imp", use_container_width=True,
                     help="Hace que las respuestas vuelvan a aparecer como nuevas"):
            _limpiar_importados()
            st.success("Registro limpiado. Volvé a leer el formulario.")
            st.cache_data.clear()

    if leer:
        st.session_state["hog_leido"] = True
        # forzar relectura
        _leer_respuestas.clear()

    if not st.session_state.get("hog_leido"):
        st.info("Presioná **Leer formulario** para traer los pedidos nuevos.")
        return

    # ── Leer respuestas ───────────────────────────────────────────────────────
    headers, rows = _leer_respuestas()
    if not headers:
        return  # _leer_respuestas ya mostró el error

    importados = _get_imported_timestamps()
    nuevas = []
    for row in rows:
        resp = _parsear_respuesta(headers, row, cat_map, cli_map)
        if not resp["timestamp"]:
            continue
        if resp["timestamp"] in importados:
            continue
        nuevas.append(resp)

    if not nuevas:
        st.success("✅ No hay pedidos nuevos. Todo está importado.")
        return

    st.caption(f"**{len(nuevas)}** pedido(s) nuevo(s) · "
               f"{len(importados)} ya importado(s)")
    st.divider()

    # ── Fecha de entrega (común a todos) ──────────────────────────────────────
    fecha_ent = st.date_input("📅 Fecha de entrega para los pedidos",
                              value=date.today(), key="hog_fecha_ent")
    st.divider()

    # ── Render de cada pedido ─────────────────────────────────────────────────
    seleccionados = []   # lista de (resp, cliente_final, items_extra)
    for resp in nuevas:
        ts  = resp["timestamp"]
        uid = "".join(ch for ch in ts if ch.isalnum())

        # Estado del cliente
        cli_auto = resp["cliente"]
        # Asignación manual persistida
        asign_key = f"hog_cli_asign_{uid}"
        cli_final = cli_auto
        if cli_final is None and asign_key in st.session_state:
            nom_asign = st.session_state[asign_key]
            cli_final = next((c for c in clientes
                              if c["nombre"] == nom_asign), None)

        # Título de la tarjeta
        nom_cli_disp = (cli_final["nombre"] if cli_final
                        else resp["nombre_cli"] or "—")
        icono = "✅" if cli_final else "⚠️"
        n_match = len(resp["lineas"])
        n_smatch = len(resp["sin_match"])
        n_extra = len(resp["prod_extra"])

        # ── Checkbox de selección (fuera del expander, estable) ──────────────
        col_chk, col_exp = st.columns([1, 11])
        with col_chk:
            sel = st.checkbox("", key=f"hog_sel_{uid}",
                              label_visibility="collapsed")
        with col_exp:
            with st.expander(
                f"{icono} {nom_cli_disp} · {resp['email'] or 'sin email'} · "
                f"{n_match} producto(s)"
                + (f" · ⚠️{n_smatch} sin match" if n_smatch else "")
                + (f" · 📝{n_extra} extra" if n_extra else ""),
                expanded=False):

                # ── Cliente ──────────────────────────────────────────────────
                if cli_auto:
                    st.success(f"👤 Cliente: **{cli_auto['nombre']}** "
                               f"(identificado por email)")
                else:
                    st.warning(
                        f"⚠️ **Cliente no encontrado** para el email "
                        f"`{resp['email'] or '(sin email)'}` "
                        f"(nombre en formulario: {resp['nombre_cli'] or '—'}).")
                    # Asignar manual o crear
                    opciones = ["— elegir cliente —"] + nombres_clientes
                    idx_def = 0
                    if asign_key in st.session_state:
                        nom_prev = st.session_state[asign_key]
                        if nom_prev in nombres_clientes:
                            idx_def = nombres_clientes.index(nom_prev) + 1
                    sel_cli = st.selectbox(
                        "Asignar cliente (por si cambió su email):",
                        opciones, index=idx_def, key=f"hog_selcli_{uid}")
                    if sel_cli != "— elegir cliente —":
                        st.session_state[asign_key] = sel_cli
                        cli_final = next((c for c in clientes
                                          if c["nombre"] == sel_cli), None)
                        if cli_final:
                            st.success(f"✅ Asignado a **{sel_cli}**.")
                    else:
                        st.info("Si el cliente no existe, agregalo en el módulo "
                                "**Clientes** y volvé a leer el formulario.")

                # ── Productos con match ──────────────────────────────────────
                if resp["lineas"]:
                    st.markdown("**Productos del pedido:**")
                    import pandas as pd
                    filas = []
                    for l in resp["lineas"]:
                        prod = cat_info.get(l["prod_cat"], {})
                        precio, _ = cli_precio(cli_final or {}, l["prod_cat"])
                        if precio <= 0:
                            precio = float(prod.get("precio") or 0)
                        filas.append({
                            "Producto": l["prod_cat"],
                            "Cantidad": l["cantidad"],
                            "Unidad": prod.get("unidad", ""),
                            "Precio": f"Q{precio:.2f}",
                        })
                    st.dataframe(pd.DataFrame(filas), hide_index=True,
                                 use_container_width=True)

                # ── Alerta productos sin match ───────────────────────────────
                if resp["sin_match"]:
                    st.error("⚠️ **Productos no encontrados en el catálogo** "
                             "(no se importan hasta agregarlos):")
                    for l in resp["sin_match"]:
                        st.write(f"   • {l['nombre_form']} "
                                 f"(×{l['cantidad']} {l['unidad_form']})")
                    st.caption("Agregá estos productos en **Productos** con el "
                               "nombre exacto del formulario para que hagan match.")

                # ── Productos extra (texto libre) ────────────────────────────
                extra_key = f"hog_extra_items_{uid}"
                if extra_key not in st.session_state:
                    st.session_state[extra_key] = []

                if resp["prod_extra"]:
                    st.markdown("---")
                    st.markdown("**📝 Pedido en texto libre del cliente:**")
                    for txt in resp["prod_extra"]:
                        st.info(f"\"{txt}\"")
                    st.caption("Interpretá el texto y agregá los productos "
                               "del catálogo que correspondan:")

                    ce1, ce2, ce3 = st.columns([3, 1, 1])
                    with ce1:
                        prod_extra_sel = st.selectbox(
                            "Producto del catálogo", ["—"] + nombres_catalogo,
                            key=f"hog_extrasel_{uid}",
                            label_visibility="collapsed")
                    with ce2:
                        cant_extra = st.number_input(
                            "Cant.", min_value=0.0, step=1.0, value=1.0,
                            key=f"hog_extracant_{uid}",
                            label_visibility="collapsed")
                    with ce3:
                        if st.button("➕ Agregar", key=f"hog_extraadd_{uid}",
                                     use_container_width=True):
                            if prod_extra_sel != "—" and cant_extra > 0:
                                st.session_state[extra_key].append(
                                    {"prod_cat": prod_extra_sel,
                                     "cantidad": cant_extra})
                                st.rerun()

                    # Mostrar los productos extra ya agregados
                    if st.session_state[extra_key]:
                        st.markdown("**Agregados de este texto libre:**")
                        for j, ex in enumerate(st.session_state[extra_key]):
                            cx1, cx2 = st.columns([6, 1])
                            with cx1:
                                st.write(f"   • {ex['prod_cat']} ×{ex['cantidad']:g}")
                            with cx2:
                                if st.button("🗑", key=f"hog_extradel_{uid}_{j}"):
                                    st.session_state[extra_key].pop(j)
                                    st.rerun()

        # Si está seleccionado, agregarlo a la lista de importación
        if sel:
            items_extra = st.session_state.get(extra_key, [])
            seleccionados.append((resp, cli_final, items_extra))

    # ── Botón de importar (ÚNICO, fuera de las tarjetas) ──────────────────────
    st.divider()
    n_sel = len(seleccionados)
    # Validar que los seleccionados tengan cliente
    listos = [(r, c, e) for (r, c, e) in seleccionados if c is not None]
    sin_cli = n_sel - len(listos)

    if n_sel == 0:
        st.info("Marcá los pedidos que querés importar con su casilla ☑️.")
    else:
        msg = f"**{n_sel}** pedido(s) seleccionado(s)"
        if sin_cli:
            msg += f" · ⚠️ {sin_cli} sin cliente asignado (no se importarán)"
        st.markdown(msg)
        if listos and st.button(f"📥 Importar {len(listos)} pedido(s)",
                                type="primary", key="hog_importar_btn",
                                use_container_width=True):
            st.session_state["hog_do_import"] = {
                "pedidos": [
                    {"resp": r, "cliente": c, "extra": e, "fecha": fecha_ent}
                    for (r, c, e) in listos
                ]
            }
            st.rerun()


def _ejecutar_importacion(intento: dict, cat_info: dict, cli_precio_fn):
    """Importa todos los pedidos seleccionados y muestra el resultado."""
    from order_helper import guardar_pedidos_batch
    from excel_helper import leer_pedidos

    cola = []
    resumen = []
    for ped in intento["pedidos"]:
        resp = ped["resp"]
        cli  = ped["cliente"]
        extra = ped["extra"]
        fecha = ped["fecha"]
        nombre_cli = cli["nombre"]

        items = []
        # Productos con match
        for l in resp["lineas"]:
            prod = cat_info.get(l["prod_cat"], {})
            precio, _ = cli_precio_fn(cli, l["prod_cat"])
            if precio <= 0:
                precio = float(prod.get("precio") or 0)
            items.append({
                "nombre":   l["prod_cat"],
                "unidad":   prod.get("unidad") or "",
                "cantidad": float(l["cantidad"] or 0),
                "precio":   precio,
                "costo":    float(prod.get("costo") or 0),
            })
        # Productos extra (del texto libre)
        for ex in extra:
            prod = cat_info.get(ex["prod_cat"], {})
            precio, _ = cli_precio_fn(cli, ex["prod_cat"])
            if precio <= 0:
                precio = float(prod.get("precio") or 0)
            items.append({
                "nombre":   ex["prod_cat"],
                "unidad":   prod.get("unidad") or "",
                "cantidad": float(ex["cantidad"] or 0),
                "precio":   precio,
                "costo":    float(prod.get("costo") or 0),
            })

        if items:
            cola.append({"cliente_nombre": nombre_cli, "fecha": fecha,
                         "items": items, "_ts": resp["timestamp"]})
            resumen.append((nombre_cli, len(items), resp["timestamp"]))

    if not cola:
        st.warning("No había items para importar.")
        return

    try:
        res = guardar_pedidos_batch(
            [{"cliente_nombre": c["cliente_nombre"], "fecha": c["fecha"],
              "items": c["items"]} for c in cola])
    except Exception as e:
        st.error(f"❌ Error al guardar: {type(e).__name__}: {e}")
        return

    filas = res.get("filas", 0) if isinstance(res, dict) else 0
    if filas > 0:
        # Registrar todos como importados
        for nombre_cli, n_items, ts in resumen:
            _registrar_importado(ts, nombre_cli, n_items)
        # Verificar
        leer_pedidos.clear()
        st.success(f"✅ **{len(cola)} pedido(s) importado(s)** "
                   f"({filas} línea(s) en total).")
        for nombre_cli, n_items, _ in resumen:
            st.write(f"   • {nombre_cli}: {n_items} línea(s)")
        st.cache_data.clear()
    else:
        st.warning(f"No se escribió ninguna fila. Respuesta: {res}")


def _limpiar_importados():
    """Vacía la hoja FormImports para reimportar."""
    _ensure_formimports()
    from gsheets import ws
    w = ws("formimports")
    w.clear()
    w.update("A1", [["timestamp", "fecha_import", "cliente", "n_lineas"]],
             value_input_option="USER_ENTERED")
