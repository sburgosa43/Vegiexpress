"""
modulo_hogares.py — Pedidos Entrantes (multi-canal: Hogares y Hoteles).
Importa pedidos desde Google Forms. Flujo: leer respuestas → revisar →
confirmar → crear pedidos. Cada canal (ver CANALES) comparte la misma lógica
y solo cambia su formulario de respuestas y su hoja de control de importados.
"""
import streamlit as st
import re, unicodedata, json
from datetime import date, datetime

# ── Configuración de canales de pedidos entrantes ─────────────────────────────
# Cada canal comparte la MISMA lógica de importación; solo cambia su formulario
# de respuestas y la hoja donde se registran los importados. Para agregar un
# canal nuevo (ej. Restaurantes), basta con sumar una entrada aquí.
CANALES = {
    "hogares": {
        "nombre":       "Hogares",
        "icono":        "🏠",
        "form_sheet_id": "1yNaN5m_1-cAeQDizMJRbDgUlQ6yqVcFk5BYvKzTEdiM",
        "hoja_import":  "formimports",         # hoja de control de importados
    },
    "hoteles": {
        "nombre":       "Hoteles",
        "icono":        "🏨",
        "form_sheet_id": "1zKFSLqQhhaBgLuN3JPgPigW9o-iIKrK51Er0-OWm0Jo",
        "hoja_import":  "formimports_hoteles",
    },
}

# ID del Sheet de respuestas del formulario actual (legado — Hogares por defecto)
FORM_SHEET_ID  = CANALES["hogares"]["form_sheet_id"]
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


def _abrir_form_sheet(canal: str = "hogares"):
    """Abre el Sheet de respuestas del canal con la service account.
    Reutiliza el cliente gspread central (gsheets) para usar las mismas
    credenciales que el resto de la app."""
    _form_id = CANALES.get(canal, CANALES["hogares"])["form_sheet_id"]
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
    return gc.open_by_key(_form_id).sheet1


def _get_imported_timestamps(canal: str = "hogares") -> set:
    """Timestamps ya importados (de la hoja de control del canal)."""
    try:
        _ensure_formimports(canal)
        from gsheets import get_all_rows
        hoja = CANALES.get(canal, CANALES["hogares"])["hoja_import"]
        return {str(r[0]).strip() for r in get_all_rows(hoja) if r}
    except Exception:
        return set()


def _ensure_formimports(canal: str = "hogares"):
    """Crea la hoja de control de importados del canal si no existe."""
    from gsheets import ensure_ws
    hoja = CANALES.get(canal, CANALES["hogares"])["hoja_import"]
    try:
        ensure_ws(hoja,
                  ["timestamp", "fecha_import", "cliente", "n_lineas"])
    except Exception as e:
        if "already exists" not in str(e).lower():
            raise


def _registrar_importado(timestamp: str, cliente: str, n_lineas: int,
                         canal: str = "hogares"):
    from gsheets import append_rows
    _ensure_formimports(canal)
    hoja = CANALES.get(canal, CANALES["hogares"])["hoja_import"]
    hoy = date.today().strftime("%d/%m/%Y")
    append_rows(hoja, [[timestamp, hoy, cliente, n_lineas]])


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
def _leer_respuestas(canal: str = "hogares") -> tuple[list[str], list[list]]:
    """Retorna (headers, rows) del sheet de respuestas del canal."""
    try:
        sheet = _abrir_form_sheet(canal)
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
        # Extraer el número aunque venga con texto (ej. "7", "7.5", "10 lb",
        # "7 unidades"). Útil para el campo numérico libre del formulario de
        # hoteles, donde el cliente puede escribir texto extra.
        try:
            cant = float(val)
        except Exception:
            import re as _re
            _mnum = _re.search(r"\d+(?:[.,]\d+)?", val.replace(",", "."))
            if not _mnum:
                continue
            try:
                cant = float(_mnum.group(0).replace(",", "."))
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


def _analisis_top_hoteles():
    """Análisis de productos más vendidos a HOTELES (clientes código L01).
    Ayuda a decidir qué productos poner en el formulario de hoteles y con qué
    cantidades típicas por ticket.
    """
    import pandas as pd
    from collections import Counter
    from excel_helper import leer_pedidos_op as leer_pedidos
    from data_helper import cargar_clientes

    st.markdown("#### 📊 Top productos vendidos a Hoteles")
    st.caption("Análisis de ventas históricas a hoteles (clientes con código "
               "L01). Usá esta información para decidir qué productos incluir en "
               "el formulario y las cantidades típicas por ticket.")

    with st.spinner("Analizando ventas a hoteles..."):
        pedidos = leer_pedidos()
        clientes = cargar_clientes()

    # Identificar hoteles: clientes con código_lugar == L01
    hoteles = {c["nombre"].strip().lower()
               for c in clientes
               if str(c.get("codigo_lugar", "")).strip().upper() == "L01"}

    if not hoteles:
        st.warning("No se encontraron clientes con código L01 (hoteles). "
                   "Verificá que los hoteles tengan ese código en su ficha.")
        return

    st.info(f"🏨 {len(hoteles)} hotel(es) identificado(s) con código L01.")

    # Filtrar pedidos de hoteles (no cancelados)
    ped_hoteles = [p for p in pedidos
                   if p["cliente"].strip().lower() in hoteles
                   and p["status"] != "Cancelado"
                   and float(p.get("cantidad") or 0) > 0]

    if not ped_hoteles:
        st.warning("No hay pedidos históricos de hoteles todavía.")
        return

    # Agregar por producto
    #   semanas_set: en cuántas semanas distintas se vendió
    #   cantidad_total: suma de unidades
    #   tickets: número de pedidos (líneas) que lo incluyeron
    #   cantidades: lista de cantidades por ticket (para moda/promedio)
    analisis = {}
    for p in ped_hoteles:
        prod = p["producto"].strip()
        if not prod:
            continue
        key = prod.lower()
        if key not in analisis:
            analisis[key] = {
                "nombre": prod,
                "unidad": p.get("unidad", ""),
                "semanas": set(),
                "cantidad_total": 0.0,
                "tickets": 0,
                "cantidades": [],
                "hoteles": set(),
            }
        a = analisis[key]
        a["semanas"].add((p["año"], p["semana"]))
        a["cantidad_total"] += float(p["cantidad"])
        a["tickets"] += 1
        a["cantidades"].append(float(p["cantidad"]))
        a["hoteles"].add(p["cliente"].strip().lower())

    # Construir tabla
    filas = []
    for key, a in analisis.items():
        cants = a["cantidades"]
        # Cantidad típica: moda (la más frecuente); si empatan, la menor
        moda = Counter(cants).most_common()
        cant_tipica = moda[0][0] if moda else 0
        promedio = sum(cants) / len(cants) if cants else 0
        # Rango de cantidades (para definir opciones del formulario)
        cant_min = min(cants) if cants else 0
        cant_max = max(cants) if cants else 0
        filas.append({
            "Producto": a["nombre"],
            "Unidad": a["unidad"],
            "Semanas vendido": len(a["semanas"]),
            "N° hoteles": len(a["hoteles"]),
            "Tickets": a["tickets"],
            "Cant. total": round(a["cantidad_total"], 1),
            "Cant. típica": f"{cant_tipica:g}",
            "Cant. promedio": round(promedio, 1),
            "Rango": f"{cant_min:g}–{cant_max:g}",
        })

    # Ordenar por semanas vendido (recurrencia) y luego cantidad total
    filas.sort(key=lambda x: (-x["Semanas vendido"], -x["Cant. total"]))

    df = pd.DataFrame(filas)

    # Resumen
    c1, c2, c3 = st.columns(3)
    c1.metric("Productos distintos", len(filas))
    c2.metric("Pedidos analizados", len(ped_hoteles))
    total_semanas = len({(p["año"], p["semana"]) for p in ped_hoteles})
    c3.metric("Semanas con ventas", total_semanas)

    st.markdown("##### Productos ordenados por recurrencia (semanas vendido)")
    st.caption("**Semanas vendido** = en cuántas semanas distintas se pidió "
               "(recurrencia). **Cant. típica** = la cantidad más frecuente por "
               "ticket (útil para las opciones del formulario). **Rango** = "
               "mínimo–máximo pedido.")
    st.dataframe(df, hide_index=True, use_container_width=True,
                 height=min(700, 60 + len(df) * 35))

    # Descargar como referencia
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Descargar análisis (CSV)", data=csv,
        file_name="top_productos_hoteles.csv", mime="text/csv",
        key="dl_top_hoteles")

    st.caption("💡 Con la columna **Cant. típica** y **Rango** podés decidir si "
               "en el formulario ponés un desplegable con las cantidades más "
               "comunes, o un campo numérico libre.")


def _tab_formulario_hoteles():
    """Gestión del formulario Google Forms de Hoteles: seleccionar productos y
    sincronizar el formulario con los precios actuales del catálogo general."""
    import pandas as pd
    from forms_helper import (get_form_id, _productos_hoteles,
                               actualizar_formulario, leer_productos_en_form)

    # Claves de session_state propias del canal hoteles
    SEL_KEY  = "hot_form_seleccion"
    INIT_KEY = "hot_form_init"
    VER_KEY  = "hot_form_ver"

    st.markdown("#### 🏨 Formulario Google Forms — Hoteles")
    st.caption("Seleccioná los productos que querés incluir y sincronizá el "
               "formulario con los precios actuales del catálogo general "
               "(Listado Productos).")

    # ── Estado del formulario activo ──────────────────────────────────────────
    form_id = get_form_id("hoteles")
    if form_id:
        form_url = f"https://docs.google.com/forms/d/{form_id}/viewform"
        col_a, col_b, col_c = st.columns([3, 0.8, 0.8])
        col_a.success(f"✅ Formulario activo — [Link para hoteles]({form_url})")
        if col_b.button("📋 Link", key="hot_copy_link"):
            st.write(f"`{form_url}`")
        if col_c.button("🔀 Cambiar", key="hot_change_form",
                        help="Configurar un formulario diferente"):
            from forms_helper import _save_form_id
            _save_form_id("", "hoteles")
            st.session_state.pop(INIT_KEY, None)
            st.rerun()

    # ── Selector de productos ─────────────────────────────────────────────────
    todos = _productos_hoteles()
    nombres_todos = [p["nombre"] for p in todos]

    if not todos:
        st.warning("No hay productos con precio en el catálogo general.")
        return

    # Inicializar selección
    if INIT_KEY not in st.session_state:
        if form_id:
            try:
                en_form_init = leer_productos_en_form(form_id)
                st.session_state[SEL_KEY] = {
                    n for n in en_form_init if n in set(nombres_todos)}
            except Exception:
                st.session_state[SEL_KEY] = set(nombres_todos)
        else:
            st.session_state[SEL_KEY] = set(nombres_todos)
        st.session_state[INIT_KEY] = True
    ver = st.session_state.get(VER_KEY, 0)

    st.markdown("##### Productos a incluir en el formulario")
    st.caption("💡 Usá la pestaña **📊 Top Hoteles** para decidir qué productos "
               "conviene ofrecer según lo más vendido.")

    if form_id:
        if st.button("🔄 Recargar lista desde el formulario actual",
                     key="hot_reload_form"):
            try:
                en_form = leer_productos_en_form(form_id)
                st.session_state[SEL_KEY] = {
                    n for n in en_form if n in set(nombres_todos)}
                st.session_state[VER_KEY] = ver + 1
                st.rerun()
            except Exception as e:
                st.error(f"Error leyendo el formulario: {e}")

    # Filtros de referencia
    col_f1, col_f2 = st.columns(2)
    seg_f = col_f1.selectbox("Segmento", ["Todos"] +
                              sorted({p["segmento"] for p in todos}),
                              key="hot_seg_filter")
    txt_f = col_f2.text_input("Buscar", placeholder="nombre...",
                               key="hot_txt_filter")

    prods_vis = [p for p in todos
                 if (seg_f == "Todos" or p["segmento"] == seg_f) and
                    (not txt_f or txt_f.lower() in p["nombre"].lower())]

    sel_actual = st.session_state[SEL_KEY]

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

    # Editor de selección
    with st.expander("✏️ Editar selección de productos", expanded=False):
        sel_nueva = st.multiselect(
            "Productos incluidos en el formulario",
            options=nombres_todos,
            default=[n for n in nombres_todos if n in sel_actual],
            key=f"hot_multiselect_{ver}",
            label_visibility="collapsed",
        )
        st.session_state[SEL_KEY] = set(sel_nueva)

        bc1, bc2 = st.columns(2)
        if bc1.button("☑ Marcar todos", key="hot_sel_all"):
            st.session_state[SEL_KEY] = set(nombres_todos)
            st.session_state[VER_KEY] = ver + 1
            st.rerun()
        if bc2.button("☐ Desmarcar todos", key="hot_des_all"):
            st.session_state[SEL_KEY] = set()
            st.session_state[VER_KEY] = ver + 1
            st.rerun()

    n_sel = len(st.session_state[SEL_KEY])
    st.caption(f"{n_sel} de {len(todos)} productos seleccionados.")

    # ── Sincronizar formulario ────────────────────────────────────────────────
    st.divider()
    st.markdown("##### Actualizar formulario")
    st.caption("La app actualiza tu formulario EXISTENTE con los productos "
               "seleccionados y sus precios actuales del catálogo. "
               "El link para los hoteles **no cambia**.")

    if not form_id:
        st.info("📋 Ingresá el ID del formulario de hoteles. Lo encontrás en la "
                "URL: `docs.google.com/forms/d/`**[ID]**`/edit`  ·  "
                "Compartilo con la cuenta de servicio como **Editor** antes de "
                "actualizar.")
    fid_input = st.text_input(
        "ID del formulario de hoteles",
        value=form_id or "",
        placeholder="1FAIpQLSe...",
        key="hot_form_id_input",
        label_visibility="collapsed" if form_id else "visible",
    )

    prods_sel = [p for p in todos
                 if p["nombre"] in st.session_state.get(SEL_KEY, set())]

    if st.button("🔄 Actualizar formulario de hoteles con precios actuales",
                 type="primary", key="hot_actualizar_form",
                 disabled=not fid_input.strip() or not prods_sel):
        with st.spinner(f"Actualizando {len(prods_sel)} productos..."):
            try:
                res = actualizar_formulario(fid_input.strip(),
                                            productos=prods_sel,
                                            tipo_cantidad="numerico")
                # Guardar el form_id del canal hoteles
                from forms_helper import _save_form_id
                _save_form_id(fid_input.strip(), "hoteles")
                st.success(
                    f"✅ {res['eliminados']} preguntas antiguas eliminadas · "
                    f"{res['agregados']} productos agregados con precios actuales.")
                st.markdown(
                    f"**🔗 Link para hoteles:** "
                    f"[{res['form_url']}]({res['form_url']})")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
                st.caption("Verificá que el formulario esté compartido con la "
                           "cuenta de servicio como Editor.")


# ── Pedidos pegados desde WhatsApp ────────────────────────────────────────────
# Unidades reconocidas en el texto (singular y plural, con abreviaturas)
_WA_UNIDADES = {
    "caja": "caja", "cajas": "caja",
    "manojo": "manojo", "manojos": "manojo",
    "onz": "onz", "onza": "onz", "onzas": "onz", "oz": "onz",
    "lb": "lb", "lbs": "lb", "libra": "lb", "libras": "lb",
    "bolsa": "bolsa", "bolsas": "bolsa",
    "bandeja": "bandeja", "bandejas": "bandeja",
    "docena": "docena", "docenas": "docena",
    "unidad": "unidad", "unidades": "unidad", "u": "unidad", "un": "unidad",
    "qq": "qq", "quintal": "qq", "quintales": "qq",
    "kg": "kg", "kilo": "kg", "kilos": "kg",
    "saco": "saco", "sacos": "saco",
    "red": "red", "redes": "red",
    "cubeta": "cubeta", "cubetas": "cubeta",
    "bote": "bote", "botes": "bote",
    "libreta": "libreta", "libretas": "libreta",
}


def _parsear_texto_whatsapp(texto: str) -> list[dict]:
    """Convierte un listado libre (pegado de WhatsApp) en líneas estructuradas.

    Reconoce patrones como:
      "2 cajas de aguacates"  → cant=2, unidad=caja, producto=aguacates
      "5 romanas"             → cant=5, unidad="", producto=romanas
      "12 onz de arrugula"    → cant=12, unidad=onz, producto=arrugula
      "2 bandejas d flores"   → tolera "d" en vez de "de"

    Líneas sin cantidad inicial (saludos, etc.) se ignoran.
    """
    def _limpiar_unidad(u: str) -> str:
        """Normaliza el token de unidad: quita puntos, emoji y mapea."""
        u = re.sub(r"[^\wáéíóúü]", "", _norm(u))
        return _WA_UNIDADES.get(u, "")

    lineas = []
    for raw in (texto or "").splitlines():
        l = raw.strip()
        if not l:
            continue

        cant, unidad, producto_txt = None, "", ""

        # ── Formato A: "CANTIDAD [UNIDAD] [de] PRODUCTO" ──────────────────────
        # (ej. "2 cajas de aguacates", "5 romanas")
        m_a = re.match(r"^(\d+(?:[.,]\d+)?)\s+(.*)$", l)
        if m_a:
            cant  = float(m_a.group(1).replace(",", "."))
            tokens = m_a.group(2).strip().split()
            if tokens:
                u = _limpiar_unidad(tokens[0])
                if u:
                    unidad = u
                    tokens = tokens[1:]
                    if tokens and _norm(tokens[0]) in ("de", "d"):
                        tokens = tokens[1:]
            producto_txt = " ".join(tokens).strip(" .")

        # ── Formato B: "PRODUCTO[.] CANTIDAD [UNIDAD]" ────────────────────────
        # (ej. "Cebolla.  2 lbs", "Apio. 1 u.", "Culantro. 1 🫱")
        if cant is None:
            m_b = re.match(
                r"^([^\d]{2,45}?)[.\s]+(\d+(?:[.,]\d+)?)\s*(\S*)\s*$", l)
            if m_b and not l.rstrip().endswith(":"):
                producto_txt = m_b.group(1).strip(" .")
                cant   = float(m_b.group(2).replace(",", "."))
                unidad = _limpiar_unidad(m_b.group(3))

        # ── Formato C: "PRODUCTO media/medio LIBRA" (cantidad en palabras) ────
        # (ej. "Te de tilo media libra.")
        if cant is None:
            m_c = re.match(
                r"^(.+?)\s+med(?:ia|io)\s+(libra|lb|kilo|kg)\.?\s*$",
                l, re.IGNORECASE)
            if m_c:
                producto_txt = m_c.group(1).strip(" .")
                cant   = 0.5
                unidad = _limpiar_unidad(m_c.group(2))

        if cant is None or not producto_txt:
            continue   # saludo, despedida o línea sin cantidad

        lineas.append({
            "original": l,
            "cantidad": cant,
            "unidad":   unidad,
            "producto_txt": producto_txt,
        })
    return lineas


def _tab_whatsapp():
    """Pestaña: pegar un listado de WhatsApp y convertirlo en pedido."""
    from data_helper import cargar_clientes, cargar_productos, cli_precio

    st.markdown("#### 📱 Pegar pedido de WhatsApp")
    st.caption("Pegá el listado tal como te lo mandó el cliente. El sistema "
               "reconoce cantidades, unidades y productos contra tu catálogo. "
               "Las líneas dudosas quedan para que las corrijás antes de "
               "importar.")

    # 1. Cliente y fecha
    clientes = [c for c in cargar_clientes() if c.get("activo", True)]
    nombres_cli = [c["nombre"] for c in clientes]
    c1, c2 = st.columns(2)
    cli_sel = c1.selectbox("Cliente:", [""] + nombres_cli, key="wa_cliente")
    fecha_ent = c2.date_input("Fecha de entrega:", value=date.today(),
                              key="wa_fecha")

    # 2. Texto pegado
    texto = st.text_area("Listado del cliente:", height=220, key="wa_texto",
                         placeholder="2 cajas de aguacates\n5 romanas\n"
                                     "3 manojos de kale\n...")

    if st.button("🔍 Analizar listado", key="wa_analizar",
                 disabled=not texto.strip()):
        lineas = _parsear_texto_whatsapp(texto)
        if not lineas:
            st.warning("No encontré líneas con cantidades en el texto.")
        else:
            # Match contra el catálogo
            catalogo = cargar_productos(False, solo_catalogo=False)
            cat_map  = {_norm(p["nombre"]): p["nombre"] for p in catalogo}
            for ln in lineas:
                prod_cat, tipo = _match_producto(ln["producto_txt"], cat_map)
                ln["prod_cat"] = prod_cat
                ln["match"]    = tipo
            st.session_state["wa_lineas"] = lineas
        st.rerun()

    # 3. Revisión de resultados
    lineas = st.session_state.get("wa_lineas", [])
    if lineas:
        n_ok  = sum(1 for l in lineas if l.get("prod_cat"))
        n_sin = len(lineas) - n_ok
        if n_sin:
            st.warning(f"✅ {n_ok} reconocidos · ⚠️ {n_sin} sin reconocer — "
                       "asignalos manualmente abajo o dejalos en blanco para "
                       "omitirlos.")
        else:
            st.success(f"✅ Los {n_ok} productos fueron reconocidos.")

        catalogo = cargar_productos(False, solo_catalogo=False)
        nombres_cat = [""] + sorted(p["nombre"] for p in catalogo)

        st.markdown("**Revisá y corregí antes de importar:**")
        hdr = st.columns([2.2, 0.8, 0.8, 2.2])
        for h, lbl in zip(hdr, ["Texto original", "Cant.", "Unidad",
                                 "Producto del catálogo"]):
            h.markdown(f"**{lbl}**")

        for i, ln in enumerate(lineas):
            r = st.columns([2.2, 0.8, 0.8, 2.2])
            icono = "✅" if ln.get("prod_cat") else "⚠️"
            r[0].markdown(f"{icono} {ln['original'][:42]}")
            ln["cantidad"] = r[1].number_input(
                "c", value=float(ln["cantidad"]), min_value=0.0, step=1.0,
                key=f"wa_cant_{i}", label_visibility="collapsed")
            r[2].markdown(ln["unidad"] or "—")
            idx_def = (nombres_cat.index(ln["prod_cat"])
                       if ln.get("prod_cat") in nombres_cat else 0)
            ln["prod_cat"] = r[3].selectbox(
                "p", nombres_cat, index=idx_def,
                key=f"wa_prod_{i}", label_visibility="collapsed") or None

        # 4. Importar
        st.divider()
        items_validos = [l for l in lineas
                         if l.get("prod_cat") and l["cantidad"] > 0]
        if st.button(f"📥 Importar pedido ({len(items_validos)} línea(s))",
                     type="primary", key="wa_importar",
                     disabled=not cli_sel or not items_validos):
            cli = next((c for c in clientes if c["nombre"] == cli_sel), {})
            cat_info = {p["nombre"]: p
                        for p in cargar_productos(False, solo_catalogo=False)}
            items = []
            for l in items_validos:
                prod = cat_info.get(l["prod_cat"], {})
                precio, _ = cli_precio(cli, l["prod_cat"])
                items.append({
                    "nombre":   l["prod_cat"],
                    "unidad":   prod.get("unidad") or l["unidad"] or "",
                    "cantidad": float(l["cantidad"]),
                    "precio":   precio,
                    "costo":    float(prod.get("costo") or 0),
                })
            from order_helper import guardar_pedidos_batch
            with st.spinner("Creando pedido..."):
                try:
                    res = guardar_pedidos_batch([{
                        "cliente_nombre": cli_sel,
                        "fecha": fecha_ent,
                        "items": items,
                    }])
                    filas = res.get("filas", 0) if isinstance(res, dict) else 0
                    st.success(f"✅ Pedido creado para **{cli_sel}** con "
                               f"{filas or len(items)} línea(s), entrega "
                               f"{fecha_ent.strftime('%d/%m/%Y')}.")
                    # Limpiar para el siguiente pegado
                    for _k in ("wa_lineas", "wa_texto"):
                        st.session_state.pop(_k, None)
                    for _k in list(st.session_state.keys()):
                        if isinstance(_k, str) and _k.startswith(
                                ("wa_cant_", "wa_prod_")):
                            st.session_state.pop(_k, None)
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al crear el pedido: "
                             f"{type(e).__name__}: {e}")


def mostrar():
    st.markdown("## 📥 Pedidos Entrantes")
    if st.button("Inicio", key="btn_home_pe", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    tab_imp, tab_wa, tab_form_hog, tab_form_hot, tab_top = st.tabs(
        ["📥 Importar", "📱 WhatsApp", "🏠 Formulario Hogares",
         "🏨 Formulario Hoteles", "📊 Top Hoteles"])

    with tab_imp:
        # Selector de canal con botones
        st.markdown("#### ¿Qué pedidos querés importar?")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🏠 Importar Hogares", key="pe_canal_hogares",
                         use_container_width=True,
                         type="primary" if st.session_state.get("pe_canal", "hogares") == "hogares" else "secondary"):
                st.session_state["pe_canal"] = "hogares"
                st.rerun()
        with c2:
            if st.button("🏨 Importar Hoteles", key="pe_canal_hoteles",
                         use_container_width=True,
                         type="primary" if st.session_state.get("pe_canal") == "hoteles" else "secondary"):
                st.session_state["pe_canal"] = "hoteles"
                st.rerun()
        st.divider()
        canal = st.session_state.get("pe_canal", "hogares")
        _tab_importar(canal)

    with tab_wa:
        _tab_whatsapp()

    with tab_form_hog:
        _tab_formulario()   # formulario de Hogares (sistema Google Forms actual)

    with tab_form_hot:
        _tab_formulario_hoteles()

    with tab_top:
        _analisis_top_hoteles()

def _fecha_de_timestamp(ts: str):
    """Convierte la marca temporal del formulario (varios formatos posibles)
    en una fecha. Devuelve None si no se puede parsear."""
    from datetime import datetime
    ts = str(ts or "").strip()
    if not ts:
        return None
    for fmt in ("%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%m/%d/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(ts, fmt).date()
        except ValueError:
            continue
    return None


def _tab_importar(canal: str = "hogares"):
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
        _ejecutar_importacion(intento, cat_info, cli_precio, canal)

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
            _limpiar_importados(canal)
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
    headers, rows = _leer_respuestas(canal)
    if not headers:
        return  # _leer_respuestas ya mostró el error

    importados = _get_imported_timestamps(canal)

    # ── Filtro por antigüedad ────────────────────────────────────────────────
    # Evita que respuestas de semanas pasadas (ej. que se manejaron por otra
    # vía y nunca se marcaron como importadas) sigan apareciendo para siempre.
    from datetime import date, timedelta
    _hoy = date.today()
    _ini_semana = _hoy - timedelta(days=_hoy.weekday())   # lunes de esta semana
    _opciones_ant = {
        "Solo esta semana": _ini_semana,
        "Últimos 7 días":   _hoy - timedelta(days=7),
        "Últimos 14 días":  _hoy - timedelta(days=14),
        "Todas":            None,
    }
    _sel_ant = st.selectbox(
        "📆 Mostrar respuestas de:", list(_opciones_ant.keys()), index=0,
        key=f"imp_antiguedad_{canal}",
        help="Las respuestas más viejas que este rango se ocultan. Cambiá a "
             "'Todas' si necesitás importar un pedido atrasado.")
    _corte = _opciones_ant[_sel_ant]

    nuevas = []
    _ocultas_viejas = 0
    for row in rows:
        resp = _parsear_respuesta(headers, row, cat_map, cli_map)
        if not resp["timestamp"]:
            continue
        if resp["timestamp"] in importados:
            continue
        # Filtro de antigüedad
        if _corte is not None:
            _f = _fecha_de_timestamp(resp["timestamp"])
            if _f is not None and _f < _corte:
                _ocultas_viejas += 1
                continue
        nuevas.append(resp)

    if not nuevas:
        if _ocultas_viejas:
            st.success(f"✅ No hay pedidos nuevos en el rango elegido. "
                       f"({_ocultas_viejas} respuesta(s) más antigua(s) "
                       f"oculta(s) — cambiá el filtro a 'Todas' para verlas.)")
        else:
            st.success("✅ No hay pedidos nuevos. Todo está importado.")
        return

    _cap = (f"**{len(nuevas)}** pedido(s) nuevo(s) · "
            f"{len(importados)} ya importado(s)")
    if _ocultas_viejas:
        _cap += f" · {_ocultas_viejas} antiguo(s) oculto(s)"
    st.caption(_cap)
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


def _ejecutar_importacion(intento: dict, cat_info: dict, cli_precio_fn, canal: str = "hogares"):
    """Importa todos los pedidos seleccionados y muestra el resultado."""
    from order_helper import guardar_pedidos_batch
    from excel_helper import leer_pedidos_op as leer_pedidos

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
        from excel_helper import leer_pedidos as _lp_full
        leer_pedidos.clear()      # vista operativa (12 meses)
        _lp_full.clear()          # lista completa
        st.success(f"✅ **{len(cola)} pedido(s) importado(s)** "
                   f"({filas} línea(s) en total).")
        for nombre_cli, n_items, _ in resumen:
            st.write(f"   • {nombre_cli}: {n_items} línea(s)")
        st.cache_data.clear()
    else:
        st.warning(f"No se escribió ninguna fila. Respuesta: {res}")


def _limpiar_importados(canal: str = "hogares"):
    """Vacía la hoja de control de importados del canal para reimportar."""
    _ensure_formimports(canal)
    from gsheets import ws
    hoja = CANALES.get(canal, CANALES["hogares"])["hoja_import"]
    w = ws(hoja)
    w.clear()
    w.update("A1", [["timestamp", "fecha_import", "cliente", "n_lineas"]],
             value_input_option="USER_ENTERED")
