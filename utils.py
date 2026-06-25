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
from datetime import date, datetime


# ── Conversiones seguras de tipos ─────────────────────────────────────────────

def _sf(v) -> float:
    """
    Safe float — maneja vacíos, comas decimales, separadores de miles
    y símbolos de moneda (Q, $).

    Soporta formato centroamericano: 1.234,56  →  1234.56
    """
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("Q", "").replace("$", "").replace(" ", "")
    # Formato europeo/centroamericano: punto como miles, coma como decimal
    if "," in s and "." in s:
        if s.index(".") < s.index(","):   # 1.234,56
            s = s.replace(".", "").replace(",", ".")
        else:                              # 1,234.56
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
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
