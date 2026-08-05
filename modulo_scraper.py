"""
modulo_scraper.py — Precios de Mercado
VeggiExpress · consulta precios en La Torre (latorre.com.gt)
Dependencias: requests, beautifulsoup4, lxml
"""

import re
import time
import logging
from datetime import datetime
from dataclasses import dataclass, field, asdict

import requests
from bs4 import BeautifulSoup
import streamlit as st

# ── Configuracion ─────────────────────────────────────────────────────────────
_BASE_URL  = "https://www.latorre.com.gt"
_CATEGORIA = "/frutas-verduras-y-complementos"
_DELAY     = 1.5
_TIMEOUT   = 15
_MAX_PAG   = 20

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-GT,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
}

log = logging.getLogger("modulo_scraper")


# ── Modelo de datos ───────────────────────────────────────────────────────────
@dataclass
class _Producto:
    nombre:        str
    cantidad:      str
    precio:        float
    precio_normal: float
    en_oferta:     bool
    url:           str
    capturado:     str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M")
    )

    @property
    def descuento_pct(self) -> float:
        if not self.en_oferta or self.precio_normal == 0:
            return 0.0
        return round((1 - self.precio / self.precio_normal) * 100, 1)


# ── Scraping (privado) ────────────────────────────────────────────────────────
def _parsear_precio(texto: str) -> float:
    m = re.search(r"[\d,]+\.?\d*", texto.replace(",", ""))
    return float(m.group()) if m else 0.0


def _parsear_card(card) -> "_Producto | None":
    try:
        href = card.get("href", "")
        if not href.endswith("/p"):
            return None
        url = _BASE_URL + href if href.startswith("/") else href

        h3 = card.find("h3")
        if not h3:
            return None
        nombre = h3.get_text(strip=True)

        textos = [
            t.strip() for t in card.stripped_strings
            if t.strip() and t.strip() != nombre
        ]
        texto_completo = " ".join(textos)
        en_oferta = "Ofertas Publicadas" in texto_completo

        valores = [
            _parsear_precio(p)
            for p in re.findall(r"Q\s*[\d,]+\.?\d*", texto_completo)
            if _parsear_precio(p) > 0
        ]
        if not valores:
            return None

        if en_oferta and len(valores) >= 2:
            precio        = min(valores[:2])
            precio_normal = max(valores[:2])
        else:
            precio = precio_normal = valores[0]

        skip = {"Ofertas Publicadas", "Gana más stickers", "30% Des. Exclusivo Online"}
        cantidad = "—"
        for t in textos:
            if t in skip or re.search(r"Q\s*[\d]", t) or t == nombre:
                continue
            cantidad = t
            break

        return _Producto(nombre=nombre, cantidad=cantidad, precio=precio,
                         precio_normal=precio_normal, en_oferta=en_oferta, url=url)
    except Exception:
        return None


def _fetch_pagina(session: requests.Session, pagina: int):
    params = {"page": pagina} if pagina > 1 else {}
    try:
        r = session.get(_BASE_URL + _CATEGORIA, params=params,
                        headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except requests.RequestException as e:
        log.warning(f"Pagina {pagina} fallo: {e}")
        return None


def _scrape(progress_bar, status_txt) -> list:
    session = requests.Session()
    session.headers.update(_HEADERS)
    try:
        session.get(_BASE_URL, timeout=_TIMEOUT)
        time.sleep(0.5)
    except Exception:
        pass

    todos, vistos = [], set()
    for pag in range(1, _MAX_PAG + 1):
        pct = min(int((pag / 13) * 95), 95)
        progress_bar.progress(pct, text=f"Pagina {pag} · {len(todos)} productos...")
        status_txt.caption(f"Descargando pagina {pag} de latorre.com.gt...")

        soup = _fetch_pagina(session, pag)
        if soup is None:
            break

        nuevos = []
        for card in soup.select("a[href$='/p']"):
            p = _parsear_card(card)
            if p:
                clave = p.nombre.lower().strip()
                if clave not in vistos:
                    vistos.add(clave)
                    nuevos.append(p)
        todos.extend(nuevos)
        if not nuevos:
            break
        time.sleep(_DELAY)

    progress_bar.progress(100, text="Listo!")
    status_txt.empty()
    return todos


def _a_csv_bytes(productos: list) -> bytes:
    import io, csv
    buf    = io.StringIO()
    campos = ["nombre","cantidad","precio","precio_normal",
              "en_oferta","descuento_pct","url","capturado"]
    w = csv.DictWriter(buf, fieldnames=campos)
    w.writeheader()
    for p in productos:
        fila = asdict(p)
        fila["descuento_pct"] = p.descuento_pct
        w.writerow({k: fila[k] for k in campos})
    return buf.getvalue().encode("utf-8-sig")


# ── Punto de entrada ──────────────────────────────────────────────────────────
def _tab_latorre():
    st.caption("Frutas, Verduras y Complementos · latorre.com.gt")

    # Estado de sesion
    if "lt_productos" not in st.session_state:
        st.session_state.lt_productos = []
    if "lt_captura" not in st.session_state:
        st.session_state.lt_captura = None

    productos = st.session_state.lt_productos

    # Boton de captura
    col_btn, col_info = st.columns([2, 3])
    with col_btn:
        iniciar = st.button("▶ Capturar precios", type="primary",
                            use_container_width=True,
                            help="~313 productos · aprox. 1-2 minutos")
    with col_info:
        if st.session_state.lt_captura:
            st.success(f"Ultima captura: **{st.session_state.lt_captura}** · "
                       f"{len(productos)} productos")
        else:
            st.info("Sin captura en esta sesion.")

    # Ejecucion del scraping
    if iniciar:
        bar = st.progress(0, text="Iniciando...")
        txt = st.empty()
        try:
            productos = _scrape(bar, txt)
            st.session_state.lt_productos = productos
            st.session_state.lt_captura   = datetime.now().strftime("%Y-%m-%d %H:%M")
            st.success(f"{len(productos)} productos capturados.")
            st.rerun()
        except Exception as e:
            bar.empty()
            st.error(f"Error al capturar: {e}")
            return

    if not productos:
        st.caption("Presiona **Capturar precios** para obtener los datos.")
        return

    # Metricas
    en_oferta = [p for p in productos if p.en_oferta]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total",      len(productos))
    m2.metric("En oferta",  len(en_oferta))
    m3.metric("Precio min", f"Q{min(p.precio for p in productos):.2f}")
    m4.metric("Precio max", f"Q{max(p.precio for p in productos):.2f}")

    st.divider()

    # Filtros
    fc1, fc2, fc3 = st.columns([3, 1, 2])
    buscar      = fc1.text_input("Buscar", placeholder="ej. zanahoria, aguacate...",
                                  label_visibility="collapsed")
    solo_oferta = fc2.checkbox("Solo ofertas")
    precios     = [p.precio for p in productos]
    rango       = fc3.slider("Precio Q", min_value=min(precios), max_value=max(precios),
                              value=(min(precios), max(precios)),
                              label_visibility="collapsed")

    # Aplicar filtros
    resultado = productos
    if buscar:
        resultado = [p for p in resultado if buscar.lower() in p.nombre.lower()]
    if solo_oferta:
        resultado = [p for p in resultado if p.en_oferta]
    resultado = [p for p in resultado if rango[0] <= p.precio <= rango[1]]

    st.caption(f"{len(resultado)} de {len(productos)} productos")

    filas = [{
        "Nombre":           p.nombre,
        "Cantidad":         p.cantidad,
        "Precio Q":         f"Q{p.precio:.2f}",
        "Precio Normal Q":  f"Q{p.precio_normal:.2f}" if p.en_oferta else "—",
        "Oferta":           "✅" if p.en_oferta else "",
        "Descuento":        f"{p.descuento_pct:.0f}%" if p.en_oferta else "—",
    } for p in resultado]

    st.dataframe(filas, use_container_width=True, height=500)

    st.divider()
    st.download_button(
        label="⬇ Descargar CSV",
        data=_a_csv_bytes(resultado),
        file_name=f"latorre_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )


# ══════════════════════════════════════════════════════════════════════════════
# CENMA — cenma.com.gt
#
# La API vieja (/api/get_products_for_category del marketplace) devuelve 404:
# el sitio se reconstruyó entero y con él se fueron el endpoint, el payload de
# marketplace y los IDs numéricos de categoría. El front actual pide el
# catálogo completo a su backend en Railway, en UNA sola llamada.
#
# Antes: hasta 8 categorías x 20 páginas con pausas ≈ 160 requests.
# Ahora: 1 request, ~200 KB, todo el catálogo.
# ══════════════════════════════════════════════════════════════════════════════
_CENMA_API_BASE  = "https://la-terminal-production.up.railway.app"
_CENMA_PROVEEDOR = "101"          # catálogo por defecto del sitio público
_CENMA_HEADERS = {
    "Accept": "application/json",
    "Origin":  "https://www.cenma.com.gt",
    "Referer": "https://www.cenma.com.gt/",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"),
}

# Columnas de la hoja «Precios Cenma». Se declaran una sola vez porque las usan
# la tabla, el CSV y la escritura al Sheet.
COLS_CENMA = ["Fecha", "Categoría", "Producto", "Descripción",
              "Precio", "Costo Bruto", "Costo sin Impuestos", "SKU", "Mayoreo"]

# Layout anterior, para poder migrar una hoja que ya se haya escrito.
_COLS_CENMA_V1 = ["Fecha", "Categoría", "Producto", "Descripción",
                  "Precio", "Costo", "SKU", "Mayoreo"]


def costo_sin_impuestos(costo_bruto: float) -> float:
    """Costo neto de IVA e ISR.

        costo / 1.12 x 0.95

    base_sin_iva quita el 12% que el monto ya trae incluido; ISR_FACTOR (0.95)
    descuenta la retención del 5% sobre esa base. Las dos salen de config para
    que un cambio de tasa se refleje acá solo.

    OJO con qué es el «Costo Bruto»: es el campo `costo` que devuelve la API de
    CENMA, un dato por producto de SU sistema. Medido sobre el catálogo, la
    relación precio/costo va de 1.10 a 1.20 (mediana 1.176), y en el 54% de los
    productos es exactamente precio x 0.85. O sea que es un dato real y no una
    fórmula, pero no sabemos qué significa en su contabilidad.
    """
    from config import base_sin_iva, ISR_FACTOR
    return round(base_sin_iva(float(costo_bruto or 0)) * ISR_FACTOR, 4)


def _cenma_descargar(fecha: str = None) -> list:
    """Catálogo completo de Cenma. UNA llamada.

    LEVANTA la excepción si algo falla, a propósito. La versión anterior hacía
    `except Exception: break` y devolvía una lista vacía, así que un endpoint
    caído se veía exactamente igual que un catálogo sin productos — por eso el
    scraper "no funcionaba" sin decir nada.
    """
    from datetime import datetime as _dt
    fecha = fecha or _dt.now().strftime("%Y-%m-%d")
    url = f"{_CENMA_API_BASE}/api/productos?proveedor={_CENMA_PROVEEDOR}"

    resp = requests.get(url, headers=_CENMA_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"La API respondió ok={data.get('ok')!r}. "
                           f"Puede que haya vuelto a cambiar.")
    crudos = data.get("productos") or []
    if not crudos:
        raise RuntimeError("La API respondió sin productos.")

    out = []
    for p in crudos:
        _costo = _sf_num(p.get("costo"))
        out.append({
            "Fecha":       fecha,
            "Categoría":   str(p.get("categoria") or "Sin categoría").strip(),
            "Producto":    str(p.get("nombre") or "Sin nombre").strip(),
            "Descripción": str(p.get("descripcion") or "").strip(),
            "Precio":      _sf_num(p.get("precio")),
            "Costo Bruto": _costo,
            "Costo sin Impuestos": costo_sin_impuestos(_costo),
            "SKU":         str(p.get("sku") or "").strip(),
            "Mayoreo":     "Sí" if p.get("es_mayoreo") else "No",
        })
    return out


def _sf_num(v) -> float:
    try:
        return round(float(v or 0), 4)
    except (TypeError, ValueError):
        return 0.0


def _cenma_categorias(prods: list) -> list:
    """Categorías presentes, sacadas de los DATOS y no de una constante.

    El sitio ya renombró las suyas una vez (Verdura → Verduras) y agregó
    Embutidos y Cafe. Con una lista fija en el código, cualquier categoría
    nueva quedaría invisible y una renombrada dejaría de traer nada.
    """
    return sorted({p["Categoría"] for p in prods if p["Categoría"]})


def _cenma_migrar_hoja() -> int:
    """Lleva la hoja al layout actual si quedó con el anterior.

    «Costo sin Impuestos» se insertó DESPUÉS de «Costo Bruto», no al final. En
    una hoja ya escrita eso correría SKU y Mayoreo un lugar en cada fila vieja
    y el historial quedaría corrupto sin que se note. Así que si el encabezado
    es el viejo, se reescribe la hoja entera calculando la columna nueva a
    partir del costo que ya estaba.

    Devuelve cuántas filas migró. Si el encabezado no es ninguno de los dos
    conocidos, se corta: mejor un error que reescribir a ciegas.
    """
    from gsheets import ws, get_all_rows
    from utils import _sf

    hoja = ws("precios_cenma")
    cab = [str(c).strip() for c in hoja.row_values(1)]
    if cab == COLS_CENMA:
        return 0
    if cab != _COLS_CENMA_V1:
        raise RuntimeError(
            f"La hoja «Precios Cenma» tiene un encabezado que no reconozco:\n"
            f"{cab}\n\nEsperaba {COLS_CENMA} o el anterior {_COLS_CENMA_V1}. "
            f"No se toca nada — revisala a mano.")

    filas = get_all_rows("precios_cenma")
    nuevas = []
    for f in filas:
        f = list(f) + [""] * (len(_COLS_CENMA_V1) - len(f))
        fe, cat, prod, desc, precio, costo, sku, may = f[:8]
        nuevas.append([fe, cat, prod, desc, precio, costo,
                       costo_sin_impuestos(_sf(costo)), sku, may])
    hoja.update("A1", [COLS_CENMA] + nuevas, value_input_option="USER_ENTERED")
    return len(nuevas)


def _cenma_guardar(prods: list, fecha: str) -> dict:
    """Escribe en la hoja «Precios Cenma», reemplazando las filas de ESA fecha.

    Historial: cada captura queda con su fecha para poder comparar precios en
    el tiempo. Capturar dos veces el mismo día no duplica — se reemplaza.

    El borrado por rango solo se hace si las filas de esa fecha están
    CONTIGUAS. Si no lo están (alguien editó la hoja a mano, por ejemplo), se
    corta con un error en vez de borrar un bloque que incluya otras fechas.
    """
    from gsheets import (ensure_ws, get_all_rows, append_rows,
                         delete_rows_range)

    ensure_ws("precios_cenma", COLS_CENMA)
    _cenma_migrar_hoja()
    filas = get_all_rows("precios_cenma")        # ya viene SIN encabezado
    # start=2 porque la fila 1 es el encabezado y get_all_rows la descarta.
    idx = [i for i, r in enumerate(filas, start=2)
           if r and str(r[0]).strip() == fecha]

    reemplazadas = 0
    if idx:
        ini, fin = min(idx), max(idx)
        if (fin - ini + 1) != len(idx):
            raise RuntimeError(
                f"Las filas del {fecha} no están juntas en la hoja "
                f"(filas {ini} a {fin}, {len(idx)} con esa fecha). No se borra "
                f"nada para no tocar otras fechas — revisá la hoja a mano.")
        reemplazadas = delete_rows_range("precios_cenma", ini, fin)

    append_rows("precios_cenma",
                [[p[c] for c in COLS_CENMA] for p in prods])
    return {"escritas": len(prods), "reemplazadas": reemplazadas}


def _tab_cenma():
    from datetime import datetime as _dt
    import pandas as pd

    st.caption("Mercado CENMA / CENDEC · cenma.com.gt · catálogo completo en "
               "una sola llamada")

    if "cenma_prods" not in st.session_state:
        st.session_state.cenma_prods = []
        st.session_state.cenma_captura = None
        st.session_state.cenma_fecha = None

    col_b, col_i = st.columns([2, 3])
    iniciar = col_b.button("▶ Capturar precios Cenma", type="primary",
                           use_container_width=True)
    with col_i:
        if st.session_state.cenma_captura:
            st.success(f"Última captura: **{st.session_state.cenma_captura}**"
                       f" · {len(st.session_state.cenma_prods)} productos")
        else:
            st.info("Sin captura en esta sesión.")

    if iniciar:
        fecha = _dt.now().strftime("%Y-%m-%d")
        try:
            with st.spinner("Descargando el catálogo..."):
                st.session_state.cenma_prods = _cenma_descargar(fecha)
            st.session_state.cenma_captura = _dt.now().strftime("%d/%m/%Y %H:%M")
            st.session_state.cenma_fecha = fecha
            st.rerun()
        except Exception as e:
            # Visible y con el detalle: si el sitio vuelve a cambiar, que se
            # sepa por qué en vez de ver una tabla vacía.
            st.error(f"**No se pudo capturar:** {type(e).__name__}: {e}\n\n"
                     f"Si esto se repite, es probable que el sitio haya "
                     f"cambiado otra vez su API. No se modificó nada.")
            return

    prods = st.session_state.cenma_prods
    if not prods:
        return

    cats = _cenma_categorias(prods)
    _def = [c for c in cats
            if c.lower() in ("verduras", "frutas", "hierbas y hojas")]
    cats_sel = st.multiselect(
        "Categorías", cats, default=_def or cats, key="cenma_cats",
        help="Filtra la tabla y decide qué se guarda en el Sheet.")

    df = pd.DataFrame([p for p in prods
                       if not cats_sel or p["Categoría"] in cats_sel],
                      columns=COLS_CENMA)

    filtro = st.text_input("Buscar producto:", key="cenma_filtro",
                           placeholder="tomate, brócoli...")
    if filtro:
        df = df[df["Producto"].str.contains(filtro, case=False, na=False)]

    st.caption(f"**{len(df)}** de {len(prods)} productos del catálogo · "
               f"{len(cats)} categorías disponibles")
    st.dataframe(df, hide_index=True, use_container_width=True,
                 height=min(500, 60 + len(df) * 35))

    b1, b2 = st.columns(2)
    b1.download_button(
        "📥 Descargar CSV", data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"precios_cenma_{st.session_state.cenma_fecha or ''}.csv",
        mime="text/csv", key="cenma_csv", use_container_width=True)

    with b2:
        # Se guarda lo FILTRADO por categoría, no el buscador: el texto libre es
        # para mirar en pantalla, y guardar solo lo que quedó de una búsqueda
        # dejaría la hoja con un recorte que después nadie recuerda.
        a_guardar = [p for p in prods
                     if not cats_sel or p["Categoría"] in cats_sel]
        if st.button(f"💾 Guardar {len(a_guardar)} en «Precios Cenma»",
                     use_container_width=True, key="cenma_save",
                     disabled=not a_guardar):
            try:
                with st.spinner("Escribiendo en el Sheet..."):
                    res = _cenma_guardar(a_guardar,
                                         st.session_state.cenma_fecha)
                _msg = f"✅ {res['escritas']} fila(s) guardadas."
                if res["reemplazadas"]:
                    _msg += (f" Se reemplazaron {res['reemplazadas']} de una "
                             f"captura anterior del mismo día.")
                st.success(_msg)
            except Exception as e:
                st.error(f"No se pudo guardar: {type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# MERCADO LA TERMINAL — intento con requests (el sitio renderiza con JS;
# el script original usa Playwright/Chromium, inviable en Streamlit Cloud
# por memoria. Acá se intenta extraer el JSON inline que las tiendas Ecwid
# a veces incluyen en el HTML inicial).
# ══════════════════════════════════════════════════════════════════════════════
def _laterminal_intento() -> tuple[list, str]:
    """Intenta extraer productos del HTML estático. Retorna (productos, msg)."""
    import re as _re, json as _json
    url = "https://www.mercadolaterminalonline.com/products"
    try:
        r = requests.get(url, timeout=20, headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36")})
        r.raise_for_status()
    except Exception as e:
        return [], f"No se pudo acceder al sitio: {e}"

    html = r.text
    productos = []

    # Intento 1: cards renderizadas server-side
    soup = BeautifulSoup(html, "html.parser")
    for card in soup.select("div[data-product-id]"):
        t = card.select_one("a.grid-product__title")
        s = card.select_one("div.grid-product__subtitle")
        p = card.select_one("div.grid-product__price")
        if t:
            productos.append({
                "Producto":     (t.get("title") or t.get_text() or "").strip(),
                "Presentación": (s.get_text().strip() if s else ""),
                "Precio":       (p.get_text().strip() if p else ""),
            })
    if productos:
        return productos, ""

    # Intento 2: JSON inline de Ecwid en <script>
    for pat in (r'window\.ec\s*=\s*(\{.*?\});',
                r'"items"\s*:\s*(\[.*?\])\s*[,}]'):
        mjs = _re.search(pat, html, _re.DOTALL)
        if mjs:
            try:
                data = _json.loads(mjs.group(1))
                items = data if isinstance(data, list) else \
                        data.get("storefront", {}).get("products", [])
                for it in items:
                    if isinstance(it, dict) and it.get("name"):
                        productos.append({
                            "Producto":     it.get("name", ""),
                            "Presentación": it.get("subtitle", ""),
                            "Precio":       it.get("defaultDisplayedPriceFormatted",
                                                   it.get("price", "")),
                        })
                if productos:
                    return productos, ""
            except Exception:
                continue

    return [], ("El sitio no incluye los productos en el HTML inicial "
                "(los dibuja con JavaScript). Este sitio requiere un navegador "
                "para capturarse, lo cual no es viable en Streamlit Cloud por "
                "consumo de memoria. Seguí usando tu script local de "
                "Playwright para este sitio.")


def _tab_laterminal():
    st.caption("Mercado La Terminal Online · mercadolaterminalonline.com")

    if "lter_prods" not in st.session_state:
        st.session_state.lter_prods = []
        st.session_state.lter_captura = None

    col_b, col_i = st.columns([2, 3])
    iniciar = col_b.button("▶ Intentar captura", type="primary",
                           use_container_width=True,
                           help="Este sitio usa JavaScript; la captura sin "
                                "navegador puede no ser posible.")
    with col_i:
        if st.session_state.lter_captura:
            st.success(f"Última captura: **{st.session_state.lter_captura}** "
                       f"· {len(st.session_state.lter_prods)} productos")
        else:
            st.info("Sin captura en esta sesión.")

    if iniciar:
        with st.spinner("Intentando capturar sin navegador..."):
            prods, msg = _laterminal_intento()
        if prods:
            from datetime import datetime as _dt
            st.session_state.lter_prods = prods
            st.session_state.lter_captura = _dt.now().strftime("%d/%m/%Y %H:%M")
            st.rerun()
        else:
            st.warning(msg)

    prods = st.session_state.lter_prods
    if prods:
        import pandas as pd
        df = pd.DataFrame(prods)
        st.dataframe(df, hide_index=True, use_container_width=True,
                     height=min(500, 60 + len(df) * 35))
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 Descargar CSV", data=csv,
                           file_name="precios_laterminal.csv",
                           mime="text/csv", key="lter_csv")


# ══════════════════════════════════════════════════════════════════════════════
def mostrar():
    if st.button("Inicio", key="btn_home_scraper", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()

    st.markdown("## 🔍 Precios de Mercado")
    st.caption("Captura de precios de referencia de sitios del mercado "
               "guatemalteco. Cada pestaña es un sitio.")
    st.divider()

    tab_lt, tab_cen, tab_ter = st.tabs(
        ["🏪 La Torre", "🥬 Cenma", "🛒 La Terminal"])
    with tab_lt:
        _tab_latorre()
    with tab_cen:
        _tab_cenma()
    with tab_ter:
        _tab_laterminal()
