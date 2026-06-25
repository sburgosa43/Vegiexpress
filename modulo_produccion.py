"""
modulo_produccion.py — UI de gestión de producción agrícola.

Solo contiene funciones de presentación (tabs, formularios, widgets).
Toda la lógica de datos y negocio está en produccion_helper.py.
"""
import streamlit as st
from datetime import date, timedelta
import uuid

from utils import _sf, _parse_fecha
from produccion_helper import (
    _K_PROD, _K_CULT, _K_APLIC, _K_FERT,
    MESES, MESES_LLUVIA, _DOSIS_SUGERIDAS,
    _init_hojas,
    _leer_fertilizantes, _leer_cultivos, _leer_siembras, _leer_aplicaciones,
    _eliminar_siembra, _reescribir_aplicaciones,
    _calc_mezcla,
    _ventas_por_semana_cultivo, _ventas_por_semana_prod, _rendimiento_por_ventas,
    _proyectar_lbs, _es_lluvia, _etapa_siembra, _siembras_necesitan_fert,
    _col_letra,
)

# ── SESSION STATE KEYS (prefijo: prod_) ───────────────────────────────────────
# _prod_hojas_ok:           bool   — flag de inicialización de hojas (una vez/sesión)
# prod_fert_{id_siembra}:   bool   — editor de fertilización abierto para esa siembra
# _del_conf_{id_siembra}:   bool   — confirmación de eliminación abierta
# _edit_{id_siembra}:       bool   — panel de edición rápida abierto
# fert_napps_{id}:          int    — cantidad de aplicaciones en editor fertilización
# fert_nlin_{id}_{app}:     int    — cantidad de líneas por aplicación
# (fragment-scoped: el editor @st.fragment maneja sus propias keys internamente)
# ──────────────────────────────────────────────────────────────────────────────

def widget_inicio():
    """Aviso compacto de cosechas próximas + alertas de fertilización."""
    try:
        siembras = _leer_siembras()
    except Exception:
        return

    activas = [s for s in siembras if s["estado"] == "Activa"]
    if not activas:
        return

    hoy = date.today()
    sem_actual = hoy.isocalendar()[1]

    # Cosechas de esta semana y próxima
    cosechas_prox = [s for s in activas
                     if s["fecha_cosecha_est"]
                     and 0 <= (s["fecha_cosecha_est"] - hoy).days <= 14]
    # Fertilización pendiente
    fert_pend = _siembras_necesitan_fert(activas)

    if not cosechas_prox and not fert_pend:
        return

    st.markdown("##### 🌱 Producción")
    if cosechas_prox:
        for s in cosechas_prox[:4]:
            dias = (s["fecha_cosecha_est"] - hoy).days
            cuando = "hoy" if dias == 0 else f"en {dias} día(s)"
            st.caption(f"🥕 **{s['variedad']}** ({s['lugar']}) — "
                       f"cosecha {cuando} · est. "
                       f"{s['lbs_proyectadas_min']:.0f}–{s['lbs_proyectadas_max']:.0f} lbs")
    if fert_pend:
        for s, app, dias in fert_pend[:4]:
            st.caption(f"🧪 **{s['variedad']}** ({s['lugar']}) — "
                       f"toca fertilizar (App {app}, día {dias})")


# ── Vista: Nueva Siembra ──────────────────────────────────────────────────────
def _tab_nueva_siembra():
    cultivos = _leer_cultivos()
    fert_map = _leer_fertilizantes()

    if not cultivos:
        st.warning("No hay cultivos configurados. Revisá la pestaña Cultivos.")
        return

    nombres_cultivo = sorted({c["cultivo"] for c in cultivos})

    c1, c2 = st.columns(2)
    cultivo_sel = c1.selectbox("Cultivo", nombres_cultivo, key="ns_cultivo")
    variedades = [c for c in cultivos if c["cultivo"] == cultivo_sel]
    var_nombres = [c["variedad"] for c in variedades]
    var_sel = c2.selectbox("Variedad", var_nombres, key="ns_variedad")

    cult = next(c for c in variedades if c["variedad"] == var_sel)

    st.caption(f"Ciclo: **{cult['dias_ciclo']} días** · "
               f"Germinación: **{cult['germinacion']*100:.0f}%** · "
               f"Rendimiento: **{cult['rend_min']}–{cult['rend_max']} zanahorias/lb**")

    # Datos de la siembra
    d1, d2, d3 = st.columns(3)
    fecha_siembra = d1.date_input("Fecha de siembra", value=date.today(),
                                   key="ns_fecha")
    semillas = d2.number_input("Cantidad de semillas", min_value=0,
                                value=100000, step=10000, key="ns_semillas")
    tablones = d3.number_input("Tablones sembrados", min_value=0.0,
                                value=0.0, step=1.0, key="ns_tablones")

    e1, e2 = st.columns(2)
    lugar = e1.text_input("Lugar", placeholder="Terreno / parcela...",
                           key="ns_lugar")
    # Fecha cosecha auto-calculada (solo lectura — se ajusta en Siembras Activas)
    fecha_cosecha = fecha_siembra + timedelta(days=cult["dias_ciclo"])
    e2.markdown(
        f"<div style='padding-top:4px'><small style='color:#888'>"
        f"Fecha cosecha estimada</small><br>"
        f"<b style='font-size:1.05rem'>{fecha_cosecha.strftime('%d/%m/%Y')}</b>"
        f"<br><small style='color:#aaa'>(calculada: siembra + "
        f"{cult['dias_ciclo']} días · ajustable luego)</small></div>",
        unsafe_allow_html=True)

    # Proyección
    lbs_min, lbs_max = _proyectar_lbs(semillas, cult["germinacion"],
                                       cult["rend_min"], cult["rend_max"])
    st.info(f"📊 Proyección: **{lbs_min:.0f} – {lbs_max:.0f} lbs** "
            f"({semillas*cult['germinacion']:.0f} plantas estimadas)")

    notas = st.text_input("Notas", key="ns_notas",
                          placeholder="Observaciones de la siembra...")

    # ── Programa de fertilización (editable) ──────────────────────────────────
    st.divider()
    st.markdown("##### 🧪 Programa de fertilización (2 aplicaciones)")
    es_lluvia = _es_lluvia(fecha_siembra)
    st.caption(f"Temporada detectada: **{'Lluviosa' if es_lluvia else 'Seca'}** "
               f"(según mes de siembra). Las dosis sugeridas se cargan abajo "
               f"y podés ajustarlas.")

    dosis_cult = _DOSIS_SUGERIDAS.get(cultivo_sel, {})
    fert_opts = sorted(fert_map.keys())
    aplicaciones_data = {}

    for app_num in (1, 2):
        app_cfg = dosis_cult.get(app_num, {})
        dia_d = app_cfg.get("dia_desde", 22 if app_num == 1 else 50)
        dia_h = app_cfg.get("dia_hasta", 25 if app_num == 1 else 55)
        sugeridas = app_cfg.get("lluvia" if es_lluvia else "seca", [])

        with st.expander(f"Aplicación {app_num} — Día {dia_d}–{dia_h}",
                         expanded=True):
            n_lineas = st.number_input(
                f"Número de fertilizantes en App {app_num}",
                min_value=1, max_value=6,
                value=max(len(sugeridas), 1),
                key=f"ns_n_app{app_num}")
            lineas_app = []
            for i in range(int(n_lineas)):
                fc1, fc2 = st.columns([2, 1])
                # Pre-cargar sugerencia si existe
                if i < len(sugeridas):
                    fert_def, lbs_def = sugeridas[i]
                    idx_def = fert_opts.index(fert_def) if fert_def in fert_opts else 0
                else:
                    idx_def, lbs_def = 0, 0.0
                fert = fc1.selectbox(f"Fertilizante {i+1}", fert_opts,
                                      index=idx_def,
                                      key=f"ns_fert_{app_num}_{i}",
                                      label_visibility="collapsed")
                lbs = fc2.number_input(f"Lbs {i+1}", min_value=0.0,
                                        value=float(lbs_def), step=1.0,
                                        key=f"ns_lbs_{app_num}_{i}",
                                        label_visibility="collapsed")
                lineas_app.append((fert, lbs))

            # Cálculo de mezcla en vivo
            mezcla = _calc_mezcla(lineas_app, fert_map)
            g = mezcla["grado"]
            r = mezcla["reales"]
            st.caption(
                f"**Grado equivalente:** {g[0]}-{g[1]}-{g[2]}  ·  "
                f"**Nutriente real:** N {r[0]:.1f} · P {r[1]:.1f} · "
                f"K {r[2]:.1f} lbs  ·  Total mezcla: {mezcla['total_lbs']:.0f} lbs")
            aplicaciones_data[app_num] = {
                "dia_desde": dia_d, "dia_hasta": dia_h,
                "temporada": "Lluviosa" if es_lluvia else "Seca",
                "lineas": lineas_app,
            }

    # ── Guardar ───────────────────────────────────────────────────────────────
    st.divider()
    if st.button("🌱 Registrar siembra", type="primary", key="ns_guardar"):
        if not lugar.strip():
            st.error("Indicá el lugar de la siembra.")
            return
        from gsheets import append_rows

        id_siembra = f"S{date.today().strftime('%y%m%d')}_{str(uuid.uuid4())[:4].upper()}"
        semana_cos = fecha_cosecha.isocalendar()[1]

        with st.spinner("Guardando siembra..."):
            # Fila principal
            append_rows(_K_PROD, [[
                id_siembra, var_sel,
                fecha_siembra.strftime("%d/%m/%Y"), semillas, lugar.strip(),
                tablones, fecha_cosecha.strftime("%d/%m/%Y"), semana_cos,
                cult["dias_ciclo"], lbs_min, lbs_max, "", "Activa",
                notas.strip(), cultivo_sel, "",
            ]])

            # Aplicaciones congeladas (Opción B)
            filas_aplic = []
            for app_num, app_data in aplicaciones_data.items():
                for fert, lbs in app_data["lineas"]:
                    if lbs > 0:
                        filas_aplic.append([
                            id_siembra, app_num,
                            app_data["dia_desde"], app_data["dia_hasta"],
                            app_data["temporada"], fert, lbs, "No", "",
                        ])
            if filas_aplic:
                append_rows(_K_APLIC, filas_aplic)

        _leer_siembras.clear()
        st.success(f"✅ Siembra **{id_siembra}** registrada — "
                   f"{var_sel} en {lugar}. Cosecha estimada: "
                   f"{fecha_cosecha.strftime('%d/%m/%Y')}.")
        st.rerun()


# ── Vista: Siembras Activas ───────────────────────────────────────────────────
def _tab_siembras_activas():
    siembras = _leer_siembras()
    fert_map = _leer_fertilizantes()
    activas = [s for s in siembras if s["estado"] == "Activa"]

    if not activas:
        st.info("No hay siembras activas. Creá una en la pestaña Nueva Siembra.")
        return

    # Alertas de fertilización arriba
    alertas = _siembras_necesitan_fert(activas)
    if alertas:
        st.warning(f"🧪 **{len(alertas)} siembra(s)** en ventana de fertilización:")
        for s, app, dias in alertas:
            st.caption(f"  · {s['variedad']} ({s['lugar']}) — App {app}, día {dias}")
        st.divider()

    st.caption(f"{len(activas)} siembra(s) activa(s)")

    # Lectura cacheada de TODAS las aplicaciones (1 sola vez por render)
    todas_aplic = _leer_aplicaciones()

    for s in sorted(activas, key=lambda x: x["fecha_siembra"] or date.today()):
        dias, etapa, color = _etapa_siembra(s)
        cosecha_str = (s["fecha_cosecha_est"].strftime("%d/%m/%Y")
                       if s["fecha_cosecha_est"] else "—")

        _fs_txt = s['fecha_siembra'].strftime('%d/%m/%Y') if s['fecha_siembra'] else '—'
        with st.expander(
            f"🥕 {s['variedad']} · {s['lugar']} · Siembra {_fs_txt} · "
            f"Día {dias} · {etapa}",
            expanded=False
        ):
            st.markdown(
                f"<div style='background:{color};color:white;padding:5px 10px;"
                f"border-radius:4px;font-size:.82rem;margin-bottom:6px'>"
                f"<b>{etapa}</b> · Día {dias} de {s['dias_ciclo']} · "
                f"Cosecha est.: {cosecha_str}</div>",
                unsafe_allow_html=True)

            m1, m2, m3 = st.columns(3)
            m1.metric("Semillas", f"{s['cantidad_semillas']:,.0f}")
            m2.metric("Tablones", f"{s['tablones']:.0f}")
            m3.metric("Proyección",
                      f"{s['lbs_proyectadas_min']:.0f}–{s['lbs_proyectadas_max']:.0f} lbs")

            # Aplicaciones de esta siembra (desde lectura cacheada)
            mias = [a for a in todas_aplic if a["id_siembra"] == s["id_siembra"]]
            if mias:
                st.markdown("**Programa de fertilización:**")
                apps_nums = sorted({a["aplicacion"] for a in mias})
                for app_num in apps_nums:
                    app_lineas = [(a["fertilizante"], a["lbs"])
                                  for a in mias if a["aplicacion"] == app_num]
                    if not app_lineas:
                        continue
                    mezcla = _calc_mezcla(app_lineas, fert_map)
                    g, rr = mezcla["grado"], mezcla["reales"]
                    detalle = " + ".join(f"{f} {l:.0f}lb" for f, l in app_lineas if l > 0)
                    a0 = next((a for a in mias if a["aplicacion"] == app_num), None)
                    dia_info = f"Día {a0['dia_desde']}–{a0['dia_hasta']}" if a0 else ""
                    aplicado = a0 and a0["aplicado_real"].strip().lower() in ("sí", "si")
                    chk = "✅" if aplicado else "⏳"
                    st.caption(
                        f"{chk} **App {app_num}** ({dia_info}): {detalle}  →  "
                        f"Grado {g[0]}-{g[1]}-{g[2]} · "
                        f"Real N{rr[0]:.1f} P{rr[1]:.1f} K{rr[2]:.1f}")

            if s["notas"]:
                st.caption(f"📝 {s['notas']}")

            # ── Editar siembra ────────────────────────────────────────────────
            st.divider()
            _edit_key = f"prod_edit_{s['id_siembra']}"
            ce1, ce2 = st.columns(2)
            if ce1.button("✏️ Editar datos", key=f"btn_edit_{s['id_siembra']}",
                          use_container_width=True):
                st.session_state[_edit_key] = not st.session_state.get(_edit_key, False)
            _del_key = f"prod_del_{s['id_siembra']}"
            if ce2.button("🗑️ Eliminar siembra", key=f"btn_del_{s['id_siembra']}",
                          use_container_width=True):
                st.session_state[_del_key] = True

            # Confirmación de eliminación
            if st.session_state.get(_del_key, False):
                st.error(f"¿Eliminar definitivamente la siembra **{s['variedad']} "
                         f"· {s['lugar']}**? Se borrarán también sus aplicaciones "
                         f"de fertilización.")
                dc1, dc2 = st.columns(2)
                if dc1.button("✅ Sí, eliminar", key=f"del_ok_{s['id_siembra']}",
                              type="primary", use_container_width=True):
                    with st.spinner("Eliminando..."):
                        _eliminar_siembra(s["id_siembra"], s["row_num"])
                    st.session_state.pop(_del_key, None)
                    st.success("Siembra eliminada.")
                    st.rerun()
                if dc2.button("Cancelar", key=f"del_no_{s['id_siembra']}",
                              use_container_width=True):
                    st.session_state.pop(_del_key, None)
                    st.rerun()

            if st.session_state.get(_edit_key, False):
                # NOTA: fuera de st.form para que la fecha de cosecha recalcule en vivo
                st.markdown("**Editar siembra**")
                ec1, ec2 = st.columns(2)
                nv_fecha_siembra = ec1.date_input(
                    "Fecha de siembra",
                    value=s["fecha_siembra"] or date.today(),
                    key=f"ed_fs_{s['id_siembra']}")
                nv_semillas = ec2.number_input(
                    "Cantidad de semillas", min_value=0,
                    value=int(s["cantidad_semillas"]), step=10000,
                    key=f"ed_sem_{s['id_siembra']}")
                ec3, ec4 = st.columns(2)
                nv_lugar = ec3.text_input(
                    "Lugar", value=s["lugar"],
                    key=f"ed_lug_{s['id_siembra']}")
                nv_tablones = ec4.number_input(
                    "Tablones", min_value=0.0,
                    value=float(s["tablones"]), step=1.0,
                    key=f"ed_tab_{s['id_siembra']}")
                ec5, ec6 = st.columns(2)
                nv_dias = ec5.number_input(
                    "Días de ciclo", min_value=1,
                    value=int(s["dias_ciclo"]), step=1,
                    key=f"ed_dias_{s['id_siembra']}")

                # Fecha cosecha: recalcula EN VIVO desde siembra + días (fuera del form)
                _auto_cos = nv_fecha_siembra + timedelta(days=int(nv_dias))
                _usar_auto = ec6.checkbox(
                    "Recalcular cosecha automáticamente",
                    value=True, key=f"ed_auto_{s['id_siembra']}",
                    help="Activado: cosecha = siembra + días de ciclo. "
                         "Desactivá para ajustar manual (adelantos/atrasos).")
                if _usar_auto:
                    nv_fecha_cosecha = _auto_cos
                    ec6.markdown(
                        f"<small style='color:#2D7A2D'>Cosecha estimada: "
                        f"<b>{_auto_cos.strftime('%d/%m/%Y')}</b></small>",
                        unsafe_allow_html=True)
                else:
                    nv_fecha_cosecha = ec6.date_input(
                        "Fecha cosecha (manual)",
                        value=s["fecha_cosecha_est"] or _auto_cos,
                        key=f"ed_fc_{s['id_siembra']}")

                nv_notas = st.text_input(
                    "Notas", value=s["notas"],
                    key=f"ed_not_{s['id_siembra']}")

                if st.button("💾 Guardar cambios", type="primary",
                             key=f"ed_save_{s['id_siembra']}",
                             use_container_width=True):
                    from gsheets import update_cells
                    cultivos = _leer_cultivos()
                    cult_s = next((c for c in cultivos
                                   if c["variedad"] == s["variedad"]), None)
                    if cult_s:
                        lmin, lmax = _proyectar_lbs(
                            nv_semillas, cult_s["germinacion"],
                            cult_s["rend_min"], cult_s["rend_max"])
                    else:
                        lmin, lmax = s["lbs_proyectadas_min"], s["lbs_proyectadas_max"]
                    sem_cos = nv_fecha_cosecha.isocalendar()[1]
                    rn = s["row_num"]
                    with st.spinner("Guardando cambios..."):
                        update_cells(_K_PROD, [
                            {"range": f"{_col_letra(3)}{rn}",  "values": [[nv_fecha_siembra.strftime("%d/%m/%Y")]]},
                            {"range": f"{_col_letra(4)}{rn}",  "values": [[nv_semillas]]},
                            {"range": f"{_col_letra(5)}{rn}",  "values": [[nv_lugar.strip()]]},
                            {"range": f"{_col_letra(6)}{rn}",  "values": [[nv_tablones]]},
                            {"range": f"{_col_letra(7)}{rn}",  "values": [[nv_fecha_cosecha.strftime("%d/%m/%Y")]]},
                            {"range": f"{_col_letra(8)}{rn}",  "values": [[sem_cos]]},
                            {"range": f"{_col_letra(9)}{rn}",  "values": [[int(nv_dias)]]},
                            {"range": f"{_col_letra(10)}{rn}", "values": [[lmin]]},
                            {"range": f"{_col_letra(11)}{rn}", "values": [[lmax]]},
                            {"range": f"{_col_letra(14)}{rn}", "values": [[nv_notas.strip()]]},
                        ])
                    _leer_siembras.clear()
                    st.session_state[_edit_key] = False
                    st.success("✅ Siembra actualizada.")
                    st.rerun()

            # ── Editar fertilización ──────────────────────────────────────────
            _fert_key = f"prod_fert_{s['id_siembra']}"
            if st.button("🧪 Editar fertilización", key=f"btn_fert_{s['id_siembra']}"):
                st.session_state[_fert_key] = not st.session_state.get(_fert_key, False)

            if st.session_state.get(_fert_key, False):
                _editor_fertilizacion(s, fert_map)





@st.fragment
def _editor_fertilizacion(s, fert_map):
    """Editor de aplicaciones de fertilización de una siembra (editar/agregar/eliminar)."""
    st.markdown("**Editar fertilización** — corregí, agregá o eliminá aplicaciones.")

    sid = s["id_siembra"]
    aplic = _leer_aplicaciones(sid)
    fert_opts = sorted(fert_map.keys())

    # Agrupar por número de aplicación
    apps_existentes = sorted({a["aplicacion"] for a in aplic})

    # Estado de cuántas aplicaciones mostrar (permite agregar nuevas)
    _n_apps_key = f"fert_napps_{sid}"
    if _n_apps_key not in st.session_state:
        st.session_state[_n_apps_key] = max(len(apps_existentes), 2)

    n_apps = st.session_state[_n_apps_key]

    # Acumulador para N-P-K total de la siembra
    total_n = total_p = total_k = 0.0
    nuevas_filas = []

    for app_num in range(1, int(n_apps) + 1):
        lineas_prev = [a for a in aplic if a["aplicacion"] == app_num]
        # Defaults de ventana
        if lineas_prev:
            dia_d = lineas_prev[0]["dia_desde"]
            dia_h = lineas_prev[0]["dia_hasta"]
            temp  = lineas_prev[0]["temporada"]
            aplicado_prev = lineas_prev[0]["aplicado_real"]
            fecha_prev = lineas_prev[0]["fecha_aplicado"]
        else:
            # Aplicación extra nueva
            dia_d, dia_h = (22, 25) if app_num == 1 else \
                           (50, 55) if app_num == 2 else (0, 0)
            temp = "Seca"
            aplicado_prev, fecha_prev = "No", ""

        with st.expander(f"Aplicación {app_num}" +
                         (f" (Día {dia_d}–{dia_h})" if dia_d else " (extra)"),
                         expanded=True):
            # Ventana de días (editable)
            wc1, wc2, wc3 = st.columns(3)
            nv_dia_d = wc1.number_input("Día desde", min_value=0, max_value=200,
                                         value=int(dia_d),
                                         key=f"fe_dd_{sid}_{app_num}")
            nv_dia_h = wc2.number_input("Día hasta", min_value=0, max_value=200,
                                         value=int(dia_h),
                                         key=f"fe_dh_{sid}_{app_num}")
            nv_temp = wc3.selectbox("Temporada", ["Seca", "Lluviosa", "Extra"],
                                     index=["Seca","Lluviosa","Extra"].index(temp)
                                           if temp in ["Seca","Lluviosa","Extra"] else 0,
                                     key=f"fe_tmp_{sid}_{app_num}")

            # Fertilizantes de esta aplicación
            _n_lin_key = f"fert_nlin_{sid}_{app_num}"
            if _n_lin_key not in st.session_state:
                st.session_state[_n_lin_key] = max(len(lineas_prev), 1)
            n_lin = st.session_state[_n_lin_key]

            lineas_app = []
            for i in range(int(n_lin)):
                lc1, lc2 = st.columns([2, 1])
                if i < len(lineas_prev):
                    f_def = lineas_prev[i]["fertilizante"]
                    l_def = lineas_prev[i]["lbs"]
                    idx_def = fert_opts.index(f_def) if f_def in fert_opts else 0
                else:
                    idx_def, l_def = 0, 0.0
                fert = lc1.selectbox(f"Fertilizante {i+1}", fert_opts,
                                      index=idx_def,
                                      key=f"fe_f_{sid}_{app_num}_{i}",
                                      label_visibility="collapsed")
                lbs = lc2.number_input(f"Lbs {i+1}", min_value=0.0,
                                        value=float(l_def), step=1.0,
                                        key=f"fe_l_{sid}_{app_num}_{i}",
                                        label_visibility="collapsed")
                lineas_app.append((fert, lbs))

            bc1, bc2 = st.columns(2)
            if bc1.button(f"+ Fertilizante", key=f"fe_addlin_{sid}_{app_num}"):
                st.session_state[_n_lin_key] = int(n_lin) + 1
                st.rerun()
            if int(n_lin) > 1 and bc2.button(f"− Quitar último",
                                              key=f"fe_dellin_{sid}_{app_num}"):
                st.session_state[_n_lin_key] = int(n_lin) - 1
                st.rerun()

            # Mezcla en vivo
            mezcla = _calc_mezcla(lineas_app, fert_map)
            g, rr = mezcla["grado"], mezcla["reales"]
            st.caption(f"**Grado:** {g[0]}-{g[1]}-{g[2]} · "
                       f"**Real:** N {rr[0]:.1f} · P {rr[1]:.1f} · K {rr[2]:.1f} lbs")
            total_n += rr[0]; total_p += rr[1]; total_k += rr[2]

            # Registro de aplicación real
            rc1, rc2 = st.columns([1, 2])
            ya_aplicado = rc1.checkbox("Ya aplicado",
                                        value=(aplicado_prev.lower() in ("sí","si")),
                                        key=f"fe_ap_{sid}_{app_num}")
            from datetime import datetime
            fecha_def = None
            if fecha_prev:
                try:
                    fecha_def = datetime.strptime(fecha_prev, "%d/%m/%Y").date()
                except ValueError:
                    fecha_def = None
            fecha_aplic = ""
            if ya_aplicado:
                fa = rc2.date_input("Fecha aplicada",
                                     value=fecha_def or date.today(),
                                     key=f"fe_fa_{sid}_{app_num}")
                fecha_aplic = fa.strftime("%d/%m/%Y")

            # Acumular filas para guardar
            for fert, lbs in lineas_app:
                if lbs > 0:
                    nuevas_filas.append([
                        sid, app_num, nv_dia_d, nv_dia_h, nv_temp,
                        fert, lbs, "Sí" if ya_aplicado else "No", fecha_aplic,
                    ])

    # Botones globales
    st.divider()
    gc1, gc2, gc3 = st.columns(3)
    if gc1.button("➕ Agregar aplicación", key=f"fe_addapp_{sid}"):
        st.session_state[_n_apps_key] = int(n_apps) + 1
        st.rerun()
    if int(n_apps) > 1 and gc2.button("➖ Quitar última aplicación",
                                       key=f"fe_delapp_{sid}"):
        st.session_state[_n_apps_key] = int(n_apps) - 1
        st.rerun()

    # N-P-K total de la siembra
    st.info(f"📊 **N-P-K total de la siembra** (todas las aplicaciones): "
            f"N {total_n:.1f} · P {total_p:.1f} · K {total_k:.1f} lbs reales")

    if gc3.button("💾 Guardar fertilización", type="primary",
                  key=f"fe_save_{sid}"):
        with st.spinner("Guardando fertilización..."):
            _reescribir_aplicaciones(sid, nuevas_filas)
        # Limpiar estado de edición
        for k in list(st.session_state.keys()):
            if k.startswith(f"fert_nlin_{sid}") or k == f"fert_napps_{sid}":
                st.session_state.pop(k, None)
        st.session_state[f"prod_fert_{sid}"] = False
        st.success("✅ Fertilización actualizada.")
        st.rerun(scope="app")   # reruna toda la app para cerrar el editor


# ── Vista: Cosecha / Cierre ───────────────────────────────────────────────────
def _tab_cosecha():
    siembras = _leer_siembras()
    cultivos = _leer_cultivos()
    # Mostrar activas Y cosechadas (para poder ver/ajustar libras ya cerradas)
    disponibles = [s for s in siembras if s["estado"] in ("Activa", "Cosechada")]

    if not disponibles:
        st.info("No hay siembras para cosechar.")
        return

    # Filtro para enfocar
    ver_filtro = st.radio("Mostrar:", ["Activas", "Cosechadas", "Todas"],
                          horizontal=True, key="cos_filtro")
    if ver_filtro == "Activas":
        lista = [s for s in disponibles if s["estado"] == "Activa"]
    elif ver_filtro == "Cosechadas":
        lista = [s for s in disponibles if s["estado"] == "Cosechada"]
    else:
        lista = disponibles

    if not lista:
        st.info(f"No hay siembras {ver_filtro.lower()}.")
        return

    # Mapa cultivo → productos cosecha
    prod_cosecha_map = {}
    for c in cultivos:
        prod_cosecha_map.setdefault(c["cultivo"], c["productos_cosecha"])

    def _et(s):
        marca = "✅" if s["estado"] == "Cosechada" else "🌱"
        return (f"{marca} {s['variedad']} · {s['lugar']} · "
                f"siembra {s['fecha_siembra'].strftime('%d/%m/%Y') if s['fecha_siembra'] else '?'}"
                + (f" · {s['lbs_cosechadas_real']:.0f} lbs" if s["estado"]=="Cosechada" else ""))

    opts = {_et(s): s for s in lista}
    sel = st.selectbox("Siembra", list(opts.keys()), key="cos_sel")
    s = opts[sel]

    if s["estado"] == "Cosechada":
        st.info(f"Esta siembra ya fue cosechada con "
                f"**{s['lbs_cosechadas_real']:.0f} lbs** totales. "
                f"Podés ver el detalle abajo y reajustar si hace falta.")

    dias, etapa, color = _etapa_siembra(s)
    st.caption(f"Día {dias} de {s['dias_ciclo']} · {etapa} · "
               f"Proyección: {s['lbs_proyectadas_min']:.0f}–"
               f"{s['lbs_proyectadas_max']:.0f} lbs")

    # Productos de cosecha de este cultivo
    productos = prod_cosecha_map.get(s["cultivo"], [])
    if not productos:
        productos = ["Mini", "Zanahoria Baby", "Zanahoria Babyr", "Zanahoria Babyl"]

    # ── Valores precargados ───────────────────────────────────────────────────
    # Prioridad: 1) cosecha ya guardada, 2) estimado por ventas
    sugeridos = {}
    if s.get("cosecha_detalle"):
        sugeridos = s["cosecha_detalle"]   # ya cosechada: mostrar lo guardado
    rend_ventas = _rendimiento_por_ventas(s, productos)
    if not sugeridos and rend_ventas and rend_ventas["total"] > 0:
        sugeridos = rend_ventas["detalle"]
    if rend_ventas and rend_ventas["total"] > 0 and s["estado"] == "Activa":
        st.success(
            f"💡 **Rendimiento estimado por ventas:** "
            f"{rend_ventas['total']:.0f} lbs vendidas en semana "
            f"{rend_ventas['semana_venta']}/{rend_ventas['año_venta']} "
            f"(lag {rend_ventas['semanas_lag']} sem). "
            f"Se cargan abajo como sugerencia — podés ajustarlos.")

    st.markdown("##### 🥕 Libras cosechadas por producto")
    st.caption("Valores sugeridos desde ventas. Editá si pesaste en campo.")
    detalle = {}
    total_real = 0.0
    cols = st.columns(min(len(productos), 4))
    for i, prod in enumerate(productos):
        col = cols[i % len(cols)]
        val_sug = float(sugeridos.get(prod, 0))
        lbs = col.number_input(prod, min_value=0.0, value=val_sug, step=1.0,
                                key=f"cos_{s['id_siembra']}_{i}")
        detalle[prod] = lbs
        total_real += lbs

    st.markdown(f"### Total real: **{total_real:.1f} lbs**")

    # Comparación vs proyección
    if total_real > 0:
        prom_proy = (s["lbs_proyectadas_min"] + s["lbs_proyectadas_max"]) / 2
        if prom_proy > 0:
            acierto = total_real / prom_proy * 100
            color_ac = "#2D7A2D" if 85 <= acierto <= 115 else "#E65100"
            st.markdown(
                f"<div style='background:{color_ac};color:white;padding:8px;"
                f"border-radius:6px;text-align:center'>"
                f"<b>Acierto vs proyección: {acierto:.0f}%</b><br>"
                f"<small>Real {total_real:.0f} lbs vs proyectado "
                f"{prom_proy:.0f} lbs</small></div>",
                unsafe_allow_html=True)

        # Mix de productos
        st.caption("**Mix de cosecha:** " + " · ".join(
            f"{p}: {l/total_real*100:.0f}%" for p, l in detalle.items() if l > 0))

    # Días reales
    if s["fecha_siembra"]:
        dias_reales = (date.today() - s["fecha_siembra"]).days
        st.caption(f"Días reales de ciclo: **{dias_reales}** "
                   f"(teórico: {s['dias_ciclo']})")

    _btn_cos_lbl = ("💾 Actualizar cosecha" if s["estado"] == "Cosechada"
                    else "✅ Cerrar cosecha")
    if st.button(_btn_cos_lbl, type="primary", key="cos_cerrar",
                 disabled=total_real <= 0):
        from gsheets import update_cells
        dias_reales = ((date.today() - s["fecha_siembra"]).days
                       if s["fecha_siembra"] else s["dias_ciclo"])
        _accion = "Actualizando" if s["estado"] == "Cosechada" else "Cerrando"
        with st.spinner(f"{_accion} cosecha..."):
            rn = s["row_num"]
            update_cells(_K_PROD, [
                {"range": f"{_col_letra(12)}{rn}", "values": [[round(total_real, 1)]]},
                {"range": f"{_col_letra(13)}{rn}", "values": [["Cosechada"]]},
                {"range": f"{_col_letra(9)}{rn}",  "values": [[dias_reales]]},
                {"range": f"{_col_letra(16)}{rn}", "values": [[json.dumps(detalle)]]},
            ])
        _leer_siembras.clear()
        _verbo = "actualizada" if s["estado"] == "Cosechada" else "cerrada"
        st.success(f"✅ Cosecha {_verbo} — {total_real:.1f} lbs totales.")
        st.rerun()


# ── Vista: Proyección ─────────────────────────────────────────────────────────
def _tab_proyeccion():
    siembras = _leer_siembras()
    activas = [s for s in siembras if s["estado"] == "Activa"]

    if not activas:
        st.info("No hay siembras activas.")
        return

    hoy = date.today()
    import pandas as pd

    rows = []
    for s in sorted(activas, key=lambda x: x["fecha_cosecha_est"] or date.max):
        if not s["fecha_cosecha_est"]:
            continue
        dias_falta = (s["fecha_cosecha_est"] - hoy).days
        rows.append({
            "Variedad":  s["variedad"],
            "Lugar":     s["lugar"],
            "Cosecha":   s["fecha_cosecha_est"].strftime("%d/%m/%Y"),
            "Semana":    s["semana_cosecha"],
            "En días":   dias_falta,
            "Lbs mín":   s["lbs_proyectadas_min"],
            "Lbs máx":   s["lbs_proyectadas_max"],
        })

    if not rows:
        st.info("Sin proyecciones de cosecha.")
        return

    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True)

    # Totales próximas 4 semanas
    sem_actual = hoy.isocalendar()[1]
    prox = [s for s in activas
            if s["fecha_cosecha_est"]
            and 0 <= (s["fecha_cosecha_est"] - hoy).days <= 28]
    if prox:
        tmin = sum(s["lbs_proyectadas_min"] for s in prox)
        tmax = sum(s["lbs_proyectadas_max"] for s in prox)
        st.success(f"📊 Próximas 4 semanas: **{tmin:.0f} – {tmax:.0f} lbs** "
                   f"en {len(prox)} cosecha(s)")


# ── Vista: Historial (siembras cosechadas) ────────────────────────────────────
def _tab_historial():
    siembras = _leer_siembras()
    cerradas = [s for s in siembras if s["estado"] != "Activa"]

    if not cerradas:
        st.info("No hay siembras cerradas todavía. Las cosechadas aparecerán acá.")
        return

    st.caption(f"{len(cerradas)} siembra(s) cerrada(s)")

    import pandas as pd
    rows = []
    for s in cerradas:
        prom_proy = (s["lbs_proyectadas_min"] + s["lbs_proyectadas_max"]) / 2
        acierto = (s["lbs_cosechadas_real"] / prom_proy * 100) if prom_proy > 0 else 0
        rows.append({
            "Variedad":   s["variedad"],
            "Lugar":      s["lugar"],
            "Siembra":    s["fecha_siembra"].strftime("%d/%m/%Y") if s["fecha_siembra"] else "—",
            "Cosecha":    s["fecha_cosecha_est"].strftime("%d/%m/%Y") if s["fecha_cosecha_est"] else "—",
            "Real (lbs)": s["lbs_cosechadas_real"],
            "Proyectado": round(prom_proy, 0),
            "Acierto %":  round(acierto, 0),
            "Estado":     s["estado"],
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True)

    st.divider()
    st.markdown("##### Gestionar siembra cerrada")
    opts = {f"{s['variedad']} · {s['lugar']} · "
            f"{s['fecha_siembra'].strftime('%d/%m/%Y') if s['fecha_siembra'] else '?'} "
            f"({s['estado']})": s for s in cerradas}
    sel = st.selectbox("Seleccioná una siembra cerrada", list(opts.keys()),
                       key="hist_sel")
    s = opts[sel]

    # Detalle de cosecha
    if s["cosecha_detalle"]:
        st.markdown("**Detalle de cosecha:**")
        det = s["cosecha_detalle"]
        total = sum(det.values()) if det else 0
        cols = st.columns(min(len(det), 4))
        for i, (prod, lbs) in enumerate(det.items()):
            cols[i % len(cols)].metric(prod, f"{lbs:.0f} lbs")
        if total > 0:
            st.caption("**Mix:** " + " · ".join(
                f"{p}: {l/total*100:.0f}%" for p, l in det.items() if l > 0))

    # Reabrir
    h1, h2 = st.columns(2)
    if h1.button("🔄 Reabrir (volver a Activa)", key=f"hist_reopen_{s['id_siembra']}",
                 use_container_width=True,
                 help="Vuelve a marcar la siembra como Activa para corregir o re-cosechar."):
        from gsheets import update_cells
        rn = s["row_num"]
        with st.spinner("Reabriendo..."):
            update_cells(_K_PROD, [
                {"range": f"{_col_letra(13)}{rn}", "values": [["Activa"]]},
            ])
        _leer_siembras.clear()
        st.success(f"✅ Siembra reabierta — vuelve a aparecer en Siembras Activas.")
        st.rerun()

    if h2.button("🗑️ Eliminar definitivamente", key=f"hist_del_{s['id_siembra']}",
                 use_container_width=True):
        st.session_state[f"hist_delconf_{s['id_siembra']}"] = True

    if st.session_state.get(f"hist_delconf_{s['id_siembra']}", False):
        st.error(f"¿Eliminar definitivamente **{s['variedad']} · {s['lugar']}**? "
                 f"Se borra el registro y sus aplicaciones.")
        dc1, dc2 = st.columns(2)
        if dc1.button("✅ Sí, eliminar", key=f"hist_delok_{s['id_siembra']}",
                      type="primary", use_container_width=True):
            with st.spinner("Eliminando..."):
                _eliminar_siembra(s["id_siembra"], s["row_num"])
            st.session_state.pop(f"hist_delconf_{s['id_siembra']}", None)
            st.success("Siembra eliminada.")
            st.rerun()
        if dc2.button("Cancelar", key=f"hist_delno_{s['id_siembra']}",
                      use_container_width=True):
            st.session_state.pop(f"hist_delconf_{s['id_siembra']}", None)
            st.rerun()


# ── Vista: Configuración (cultivos, fertilizantes) ────────────────────────────
def _tab_config():
    import pandas as pd
    st.markdown("##### 🌾 Cultivos y Variedades")
    st.caption("Editá ciclo, germinación, rendimiento y productos de cosecha. "
               "Agregá variedades o cultivos nuevos.")

    cultivos = _leer_cultivos()
    df_cult = pd.DataFrame([{
        "Cultivo": c["cultivo"], "Variedad": c["variedad"],
        "Dias_Ciclo": c["dias_ciclo"], "Germinacion": c["germinacion"],
        "Rend_Min": c["rend_min"], "Rend_Max": c["rend_max"],
        "Productos_Cosecha": ",".join(c["productos_cosecha"]),
    } for c in cultivos])
    st.caption("**Rend_Min** = zanahorias/lb máximo (raíz más chica, menos libras) · "
               "**Rend_Max** = zanahorias/lb mínimo (raíz más grande, más libras)")

    edited_cult = st.data_editor(df_cult, num_rows="dynamic",
                                  hide_index=True, use_container_width=True,
                                  key="cfg_cult")
    if st.button("💾 Guardar cultivos", key="cfg_save_cult"):
        from gsheets import ws
        with st.spinner("Guardando..."):
            data = [["Cultivo", "Variedad", "Dias_Ciclo", "Germinacion",
                     "Rend_Min", "Rend_Max", "Productos_Cosecha"]]
            for _, r in edited_cult.iterrows():
                if str(r["Cultivo"]).strip():
                    data.append([r["Cultivo"], r["Variedad"], r["Dias_Ciclo"],
                                 r["Germinacion"], r["Rend_Min"], r["Rend_Max"],
                                 r["Productos_Cosecha"]])
            w = ws(_K_CULT)
            w.clear()
            w.update("A1", data, value_input_option="USER_ENTERED")
        _leer_cultivos.clear()
        st.success("✅ Cultivos actualizados.")
        st.rerun()

    st.divider()
    st.markdown("##### 🧪 Fertilizantes (N-P-K)")
    fert_map = _leer_fertilizantes()
    df_fert = pd.DataFrame([{
        "Fertilizante": k, "N": v["N"], "P": v["P"], "K": v["K"]
    } for k, v in fert_map.items()])

    edited_fert = st.data_editor(df_fert, num_rows="dynamic",
                                  hide_index=True, use_container_width=True,
                                  key="cfg_fert")
    if st.button("💾 Guardar fertilizantes", key="cfg_save_fert"):
        from gsheets import ws
        with st.spinner("Guardando..."):
            data = [["Fertilizante", "N", "P", "K"]]
            for _, r in edited_fert.iterrows():
                if str(r["Fertilizante"]).strip():
                    data.append([r["Fertilizante"], r["N"], r["P"], r["K"]])
            w = ws(_K_FERT)
            w.clear()
            w.update("A1", data, value_input_option="USER_ENTERED")
        _leer_fertilizantes.clear()
        st.success("✅ Fertilizantes actualizados.")
        st.rerun()


# ── Entry point ───────────────────────────────────────────────────────────────
def mostrar():
    st.markdown("## 🌱 Producción Agrícola")
    if st.button("🏠 Inicio", key="btn_home_prod", type="secondary"):
        st.session_state["_nav_target"] = "🏠 Inicio"
        st.rerun()
    st.divider()

    # Crear hojas si no existen — solo una vez por sesión (evita 4 lecturas/render)
    if not st.session_state.get("_prod_hojas_ok"):
        try:
            _init_hojas()
            st.session_state["_prod_hojas_ok"] = True
        except Exception as e:
            st.error(f"Error inicializando hojas: {e}")
            return

    tabs = st.tabs([
        "🌱 Nueva Siembra",
        "📋 Siembras Activas",
        "🥕 Cosecha / Cierre",
        "📊 Proyección",
        "📚 Historial",
        "⚙️ Configuración",
    ])
    with tabs[0]: _tab_nueva_siembra()
    with tabs[1]: _tab_siembras_activas()
    with tabs[2]: _tab_cosecha()
    with tabs[3]: _tab_proyeccion()
    with tabs[4]: _tab_historial()
    with tabs[5]: _tab_config()
