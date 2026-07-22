"""
modulo_formularios.py — Mantenimiento de Formularios.

Configuración de los Google Forms de pedidos y el análisis Top Hoteles, que
antes vivían dentro de "Pedidos Entrantes". Se separan porque son tareas de
configuración (se tocan rara vez), no de operación diaria.

  🏠 Formulario Hogares  → crear/sincronizar el form de Hogares
  🏨 Formulario Hoteles  → crear/sincronizar el form de Hoteles
  📊 Top Hoteles         → análisis de qué ofrecer a cada hotel

Reutiliza las funciones ya existentes en modulo_hogares (no reimplementa).
"""
import streamlit as st


def mostrar():
    st.markdown("## 📝 Formularios")
    if st.button("🏠 Inicio", key="btn_home_forms", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.caption("Configuración de los formularios de pedidos y análisis de "
               "hoteles. Estas herramientas se usan de vez en cuando, no a "
               "diario.")
    st.divider()

    import modulo_hogares as _mh
    tab_hog, tab_hot, tab_top = st.tabs([
        "🏠 Formulario Hogares",
        "🏨 Formulario Hoteles",
        "📊 Top Hoteles",
    ])

    with tab_hog:
        _mh._tab_formulario()

    with tab_hot:
        _mh._tab_formulario_hoteles()

    with tab_top:
        _mh._analisis_top_hoteles()
