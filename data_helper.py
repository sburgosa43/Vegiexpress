"""
config.py — Configuración centralizada de VeggiExpress
Todas las constantes de negocio en un solo lugar.
"""

# ── Zonas geográficas ─────────────────────────────────────────────────────────
ZONAS_MAP = {
    "🔖 Antigua & Chimal":     ["L03", "L04", "L10"],
    "🏙️ Guatemala & Santiago": ["L05", "L06"],
    "🌊 Río":                  ["L01", "L02"],
    "🏠 Hogares":              ["L20"],
}

COLORES_ZONA = {
    "🔖 Antigua & Chimal":     "#2D7A2D",
    "🏙️ Guatemala & Santiago": "#8DC63F",
    "🌊 Río":                  "#4A4A4A",
    "🏠 Hogares":              "#E65100",
}

# Para Dashboard (análisis)
ZONAS_DASH = {
    "Todas":            ["L01", "L02", "L03", "L04", "L20", "L05", "L06"],
    "GT + Santiago":    ["L05", "L06"],
    "Río":              ["L01", "L02"],
    "Hogares":          ["L20"],
    "Antigua + Chimal": ["L03", "L04"],
}

COLORES_ZONA_RUTAS = {
    "GT + Santiago":    "#2D7A2D",
    "Río":              "#8DC63F",
    "Antigua + Chimal": "#F5A623",
}

# Subgrupos operativos
ZONA_GT_RIO = ["L01", "L05", "L06"]   # Sergio
ZONA_VEGGI  = ["L03", "L04", "L10"]    # Esposa

# ── Clientes a excluir de reportes ───────────────────────────────────────────
# "veggi" captura "veggi hogares" por substring
EXCLUIR_DASHBOARD   = ["wilson"]   # Hogares ya no se excluye — es zona propia
EXCLUIR_PROVEEDORES = ["wilson"]

def es_hogar(nombre: str, clientes_map: dict = None) -> bool:
    """Detecta si un cliente es del canal Hogares.
    Criterio 1: nombre histórico 'veggi hogares' (compatibilidad).
    Criterio 2: codigo_lugar L20 o tipo Hogar (clientes nuevos).
    """
    if "veggi hogares" in str(nombre).lower(): return True
    if clientes_map:
        cli = clientes_map.get(str(nombre).lower().strip(), {})
        return (cli.get("codigo_lugar","") == "L20" or
                cli.get("tipo","").lower() == "hogar")
    return False


def excluido_dashboard(nombre: str, clientes_map: dict = None) -> bool:
    """Excluye wilson. Hogares ya NO se excluye — aparece como zona propia."""
    n = nombre.lower()
    if "wilson" in n: return True
    return False

def excluido_proveedores(nombre: str) -> bool:
    n = nombre.lower()
    return any(x in n for x in EXCLUIR_PROVEEDORES)

# ── Reglas ISR ────────────────────────────────────────────────────────────────
ISR_UMBRAL = 2800.0          # Factura mínima para aplicar ISR

# Clientes exentos de ISR
ISR_EXENTOS = ["4 pinos", "sundog", "hotelito", "amis"]

# Clientes con descuento del 15% sobre la factura (en lugar de ISR)
DESCUENTO_15 = ["hotelito", "amis"]

def aplica_isr(cliente_nombre: str, total: float) -> bool:
    """¿Corresponde aplicar retención ISR a esta factura?"""
    n = cliente_nombre.lower()
    if total < ISR_UMBRAL:
        return False
    return not any(e in n for e in ISR_EXENTOS)

def descuento_factura(cliente_nombre: str) -> float:
    """Retorna el porcentaje de descuento sobre la factura (0 o 15)."""
    n = cliente_nombre.lower()
    return 15.0 if any(d in n for d in DESCUENTO_15) else 0.0

def calcular_liquido(cliente_nombre: str, total: float) -> tuple:
    """
    Retorna (liquido, isr, descuento) para un cliente y total de factura.
    """
    desc_pct = descuento_factura(cliente_nombre)
    if desc_pct > 0:
        desc_q = round(total * desc_pct / 100, 2)
        return round(total - desc_q, 2), 0.0, desc_q
    if aplica_isr(cliente_nombre, total):
        isr = round(total / 1.12 * 0.05, 2)
        return round(total - isr, 2), isr, 0.0
    return round(total, 2), 0.0, 0.0

# ── Reglas de pago por cliente ────────────────────────────────────────────────
# lag: semanas entre entrega y pago
REGLAS_PAGO = {
    "rodrigo":   {"lag": 3, "isr": True,  "desc": 0},
    "4 pinos":   {"lag": 1, "isr": False, "desc": 0},
    "nanajuana": {"lag": 1, "isr": True,  "desc": 0},
    "tijax":     {"lag": 1, "isr": True,  "desc": 0},
    "amis":      {"lag": 1, "isr": False, "desc": 15},
    "hotelito":  {"lag": 0, "isr": False, "desc": 15},
    "sundog":    {"lag": 0, "isr": False, "desc": 0},
}

def reglas_cliente(nombre: str) -> dict:
    k = nombre.lower().strip()
    for key, r in REGLAS_PAGO.items():
        if key in k:
            return r
    return {"lag": 0, "isr": True, "desc": 0}

# ── Hojas Excel ───────────────────────────────────────────────────────────────
HOJA_PEDIDOS          = "Pedidos"
HOJA_CLIENTES         = "Clientes"
HOJA_PRODUCTOS        = "Listado Productos"
HOJA_PRODUCTOS_ANTIGUA= "Listado Productos Antigua"
HOJA_CONFIG           = "Config"
HOJA_HISTORIAL        = "Historial Cambios"


# ── Constantes fiscales y de margen ───────────────────────────────────────────
# Centralizadas aquí para que un cambio de tasa se refleje en toda la app.
IVA_RATE = 0.12          # Impuesto al Valor Agregado (12%)
ISR_RATE = 0.05          # Retención ISR (5%)
IVA_FACTOR = 1 + IVA_RATE     # 1.12 — multiplicador de costo con IVA
ISR_FACTOR = 1 - ISR_RATE     # 0.95 — factor neto tras retención ISR

def margen_neto_pct(costo: float, precio: float) -> float:
    """Margen neto en % según fórmula acordada: ISR_FACTOR·(1 - costo·IVA_FACTOR/precio)·100."""
    if not precio or precio <= 0:
        return 0.0
    return ISR_FACTOR * (1 - costo * IVA_FACTOR / precio) * 100

def margen_neto_q(costo: float, precio: float) -> float:
    """Margen neto en Quetzales: ISR_FACTOR·(precio - costo·IVA_FACTOR)."""
    return ISR_FACTOR * (precio - costo * IVA_FACTOR)

def punto_equilibrio(costo: float) -> float:
    """Precio mínimo sin ganar ni perder: costo·IVA_FACTOR."""
    return costo * IVA_FACTOR
