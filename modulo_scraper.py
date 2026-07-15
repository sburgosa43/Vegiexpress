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
# CENMA — API directa (adaptado del script scraping_cenma_v6 de Sergio)
# ══════════════════════════════════════════════════════════════════════════════
_CENMA_API = "https://www.cenma.com.gt/api/get_products_for_category"
_CENMA_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://www.cenma.com.gt",
    "Referer": "https://www.cenma.com.gt/",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"),
    "base_version": "2",
    "device_type": "3",
    "timezone": "America/Guatemala",
    "language": "es",
}
_CENMA_USER_ID        = 1472667
_CENMA_MARKETPLACE_ID = "eab6628bd3634360a0b41e4f24b97a71"
_CENMA_MKT_USER_ID    = 958678
_CENMA_CATEGORIAS = {
    "Verdura":         11284143,
    "Fruta":           11284144,
    "Hierbas y Hojas": 11284145,
    "Granos":          11284146,
    "Especias":        11284147,
    "Abarroteria":     11284148,
    "Otros":           11284149,
    "Mayoreo":         11284150,
}


def _cenma_categoria(categoria: str, category_id: int,
                     max_paginas: int = 20) -> list:
    """Descarga una categoría de Cenma paginando la API (con pausa
    respetuosa y tope de páginas para proteger memoria/tiempo)."""
    import time as _t
    from datetime import datetime as _dt
    todos, page, limit = [], 1, 25
    while page <= max_paginas:
        payload = {
            "date_time": _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "domain_name": "www.cenma.com.gt",
            "dual_user_key": 0,
            "language": "es",
            "limit": limit,
            "marketplace_reference_id": _CENMA_MARKETPLACE_ID,
            "marketplace_user_id": _CENMA_MKT_USER_ID,
            "offset": (page - 1) * limit,
            "page_no": page,
            "parent_category_id": category_id,
            "user_id": _CENMA_USER_ID,
        }
        try:
            resp = requests.post(_CENMA_API, json=payload,
                                 headers=_CENMA_HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            break
        if data.get("status") != 200:
            break
        pagina = data.get("data", [])
        if not pagina:
            break
        for p in pagina:
            todos.append({
                "Categoría":   categoria,
                "Producto":    p.get("name", "Sin nombre"),
                "Precio":      p.get("price", 0),
                "Precio base": p.get("product_base_price", 0),
            })
        if len(pagina) < limit:
            break
        page += 1
        _t.sleep(0.5)   # pausa respetuosa con el sitio
    return todos


def _tab_cenma():
    st.caption("Mercado CENMA / CENDEC · cenma.com.gt · vía API directa")

    if "cenma_prods" not in st.session_state:
        st.session_state.cenma_prods = []
        st.session_state.cenma_captura = None

    cats_sel = st.multiselect(
        "Categorías a capturar:",
        list(_CENMA_CATEGORIAS.keys()),
        default=["Verdura", "Fruta", "Hierbas y Hojas"],
        key="cenma_cats",
        help="Menos categorías = captura más rápida y liviana.")

    col_b, col_i = st.columns([2, 3])
    iniciar = col_b.button("▶ Capturar precios Cenma", type="primary",
                           use_container_width=True,
                           disabled=not cats_sel)
    with col_i:
        if st.session_state.cenma_captura:
            st.success(f"Última captura: **{st.session_state.cenma_captura}**"
                       f" · {len(st.session_state.cenma_prods)} productos")
        else:
            st.info("Sin captura en esta sesión.")

    if iniciar:
        bar = st.progress(0, text="Iniciando...")
        todos = []
        for i, cat in enumerate(cats_sel):
            bar.progress((i) / len(cats_sel),
                         text=f"Descargando {cat}...")
            todos += _cenma_categoria(cat, _CENMA_CATEGORIAS[cat])
        bar.progress(1.0, text="Completado")
        from datetime import datetime as _dt
        st.session_state.cenma_prods = todos
        st.session_state.cenma_captura = _dt.now().strftime("%d/%m/%Y %H:%M")
        st.rerun()

    prods = st.session_state.cenma_prods
    if prods:
        import pandas as pd
        df = pd.DataFrame(prods)
        # Filtro rápido
        filtro = st.text_input("Buscar producto:", key="cenma_filtro",
                               placeholder="tomate, brócoli...")
        if filtro:
            df = df[df["Producto"].str.contains(filtro, case=False, na=False)]
        st.dataframe(df, hide_index=True, use_container_width=True,
                     height=min(500, 60 + len(df) * 35))
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 Descargar CSV", data=csv,
                           file_name=f"precios_cenma_{st.session_state.cenma_captura or ''}.csv".replace("/", "-").replace(":", ""),
                           mime="text/csv", key="cenma_csv")


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
