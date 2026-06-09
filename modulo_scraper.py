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
def mostrar():
    # Navegacion coherente con el resto de modulos
    if st.button("Inicio", key="btn_home_scraper", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()

    st.markdown("## 🔍 Precios La Torre")
    st.caption("Frutas, Verduras y Complementos · latorre.com.gt")
    st.divider()

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
