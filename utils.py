"""
utils.py — Utilidades compartidas de VeggiExpress.

Centraliza funciones que antes estaban duplicadas en múltiples módulos:
  _sf, _si, _parse_fecha  → conversiones seguras de tipos
  _conf, _show_conf       → mensajes de confirmación via session_state

Regla: este archivo NO importa ningún módulo del proyecto para evitar
ciclos. Puede importar stdlib y streamlit.
"""
from __future__ import annotations

import streamlit as st
from calendar import monthrange
from datetime import date, datetime


# ── Conversiones seguras de tipos ─────────────────────────────────────────────

def _sf(v) -> float:
    """
    Safe float — maneja vacíos, símbolos de moneda (Q, $) y separador de miles.

    La hoja usa formato guatemalteco: la COMA separa miles y el PUNTO es el
    decimal (1,500.50). Por eso la coma siempre se descarta.

    Ojo: una versión anterior trataba la coma suelta como decimal, así que
    "1,500" devolvía 1.5 en vez de 1500. Si alguna vez la hoja pasara a
    formato europeo (1.500,50), esta función habría que revisarla.
    """
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = (str(v).strip()
         .replace("Q", "").replace("$", "").replace(" ", "")
         .replace(",", ""))
    try:
        return float(s)
    except (ValueError, AttributeError):
        return 0.0


def _si(v) -> int:
    """Safe int — convierte cualquier valor a int, retorna 0 en caso de error."""
    try:
        return int(float(str(v).replace(",", "").strip() or 0))
    except (ValueError, TypeError):
        return 0


def _parse_fecha(v) -> date | None:
    """
    Parsea fecha desde string (Google Sheets devuelve strings).
    Intenta múltiples formatos comunes.
    """
    if not v:
        return None
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            pass
    return None


# ── Períodos: mes calendario y rango libre ────────────────────────────────────
# Viven acá —y no en pdf_helper— para que la pantalla, el PDF y las pruebas
# usen la MISMA definición de período. Un mes es un rango como cualquier otro:
# el modo Mes de Facturación es solo el atajo que calcula sus dos bordes.

MESES_ES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre",
            "Diciembre"]


def rango_mes(mes: int, año: int) -> tuple[date, date]:
    """(primer día, último día) de ese mes, ambos incluidos."""
    return date(año, mes, 1), date(año, mes, monthrange(año, mes)[1])


def es_mes_completo(desde: date, hasta: date) -> bool:
    """El rango cubre exactamente un mes calendario, ni un día de más ni de
    menos. Del 01/07 al 30/07 NO lo es: le falta el 31."""
    return (desde, hasta) == rango_mes(desde.month, desde.year)


def etiqueta_periodo(desde: date, hasta: date) -> str:
    """Cómo se nombra un período en pantalla y en el PDF.

    Dice 'Julio 2026' SOLO si el rango es julio entero; en cualquier otro caso
    muestra las fechas reales. Un documento que se le manda al cliente no puede
    encabezarse con un mes que no corresponde al recorte que tiene adentro.
    """
    if es_mes_completo(desde, hasta):
        return f"{MESES_ES[desde.month - 1]} {desde.year}"
    return f"del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}"


# ── Mensajes de confirmación via session_state ────────────────────────────────

def _conf(key: str, msg: str) -> None:
    """
    Guarda un mensaje de éxito/confirmación en session_state para
    mostrarlo en el próximo render (patrón post-rerun).
    """
    st.session_state[f"_conf_{key}"] = msg


def _show_conf(key: str) -> None:
    """
    Muestra y consume el mensaje de confirmación guardado por _conf().
    El mensaje desaparece en el siguiente ciclo (se consume al leerlo).
    """
    msg = st.session_state.pop(f"_conf_{key}", None)
    if msg:
        st.success(msg)
