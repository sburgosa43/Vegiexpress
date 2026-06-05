"""
config.py — Configuración centralizada de VeggiExpress
Todas las constantes de negocio en un solo lugar.
"""

# ── Zonas geográficas ─────────────────────────────────────────────────────────
ZONAS_MAP = {
    "🔖 Antigua & Chimal":     ["L03", "L04", "L10"],
    "🏙️ Guatemala & Santiago": ["L05", "L06"],
    "🌊 Río":                  ["L01", "L02"],
}

COLORES_ZONA = {
    "🔖 Antigua & Chimal":     "#2D7A2D",
    "🏙️ Guatemala & Santiago": "#8DC63F",
    "🌊 Río":                  "#4A4A4A",
}

# Para Dashboard (análisis)
ZONAS_DASH = {
    "Todas":            ["L01", "L02", "L03", "L04", "L05", "L06"],
    "GT + Santiago":    ["L05", "L06"],
    "Río":              ["L01", "L02"],
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
EXCLUIR_DASHBOARD   = ["veggi hogares", "wilson"]
EXCLUIR_PROVEEDORES = ["wilson"]

def excluido_dashboard(nombre: str) -> bool:
    n = nombre.lower()
    return any(x in n for x in EXCLUIR_DASHBOARD)

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
