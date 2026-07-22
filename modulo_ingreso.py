"""
modulo_ingreso.py — Ingreso de Pedidos (unificado).

Reúne en un solo módulo los cuatro métodos de ingreso de pedidos que antes
vivían separados en "Pedidos Entrantes" (modulo_hogares) y "Nuevo Pedido"
(modulo_pedidos):

  ✍️ Ingreso Manual        → paso a paso (de modulo_pedidos)
  📋 Importar Formularios  → Google Forms Hogares/Hoteles (de modulo_hogares)
  📱 WhatsApp              → pegar texto libre (de modulo_hogares)
  📄 Desde Excel           → pegar o subir archivo (de modulo_pedidos)

Este módulo NO reimplementa la lógica: importa y orquesta las funciones que
ya existen y están probadas en los módulos originales. Así la fusión es de
navegación, sin riesgo de romper el comportamiento interno de cada método.
"""
import streamlit as st


def mostrar():
    st.markdown("## 📥 Ingreso de Pedidos")
    if st.button("🏠 Inicio", key="btn_home_ingreso", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.caption("Elegí el método para ingresar pedidos. Todos crean pedidos "
               "en el mismo lugar; solo cambia la forma de capturarlos.")
    st.divider()

    tab_manual, tab_form, tab_wa, tab_excel = st.tabs([
        "✍️ Ingreso Manual",
        "📋 Importar Formularios",
        "📱 WhatsApp",
        "📄 Desde Excel",
    ])

    # ── Ingreso Manual (de modulo_pedidos) ───────────────────────────────────
    with tab_manual:
        import modulo_pedidos as _mp
        _mp._init()
        if _mp._aviso_costos():
            _mp._mostrar_cola_compacta()
            p = st.session_state.ped_paso
            if   p == 1: _mp._paso1()
            elif p == 2: _mp._paso2()
            elif p == 3: _mp._paso3()
            elif p == 4: _mp._paso4()

    # ── Importar desde Formularios Google (de modulo_hogares) ─────────────────
    with tab_form:
        import modulo_hogares as _mh
        st.markdown("#### ¿Qué pedidos querés importar?")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🏠 Importar Hogares", key="ing_canal_hogares",
                         use_container_width=True,
                         type=("primary"
                               if st.session_state.get("pe_canal", "hogares")
                               == "hogares" else "secondary")):
                st.session_state["pe_canal"] = "hogares"
                st.rerun()
        with c2:
            if st.button("🏨 Importar Hoteles", key="ing_canal_hoteles",
                         use_container_width=True,
                         type=("primary"
                               if st.session_state.get("pe_canal") == "hoteles"
                               else "secondary")):
                st.session_state["pe_canal"] = "hoteles"
                st.rerun()
        st.divider()
        canal = st.session_state.get("pe_canal", "hogares")
        _mh._tab_importar(canal)

    # ── WhatsApp (de modulo_hogares) ─────────────────────────────────────────
    with tab_wa:
        import modulo_hogares as _mh
        _mh._tab_whatsapp()

    # ── Desde Excel (de modulo_pedidos) ──────────────────────────────────────
    with tab_excel:
        import modulo_pedidos as _mp
        _mp._importar_pedidos()
