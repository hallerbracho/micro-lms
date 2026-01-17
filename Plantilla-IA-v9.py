# ==============================================================================
# 🛑 BLOQUE 1: INFRAESTRUCTURA Y CONFIGURACIÓN (IA: NO MODIFICAR)
# ==============================================================================
# Variables inyectadas por el entorno: st, pd, np, random, db, EXAM_ID, is_admin
import requests
from datetime import datetime

# --- 1.1 CONFIGURACIÓN DE CURSO Y BADGES ---
CONFIG_SECCIONES = {
    "URU C (Lunes)":   {"matricula": 20, "abierta": False},  
    "URU E (Jueves)":  {"matricula": 20, "abierta": False}, 
    "URU D (Viernes)":    {"matricula": 20,  "abierta": True}    
}

BADGE_CONFIG = {
    "course_name": "Fundamentos de Python para Ingeniería", # <--- CAMBIAR NOMBRE CURSO
    "min_score_for_badge": 18.5,
    "skills": ["Pensamiento Computacional", "Python 3", "Algoritmia"],    
    "instructor": "Prof. Haller Bracho"
}

# --- 1.2 MOTOR DE CALIFICACIÓN (NO TOCAR) ---
def calcular_nota_personalizada(intentos_previos, aprobados_antes):
    try: config = CONFIG_SECCIONES.get(st.session_state.user_session["section"], {}); matricula_ref = max(config.get("matricula", 25), 1)
    except: matricula_ref = 25
    percentil = (aprobados_antes + 1) / matricula_ref
    
    if percentil <= 0.10: base = 20.0
    elif percentil <= 0.30: base = 17.5
    elif percentil <= 0.70: base = 15.5
    elif percentil <= 0.90: base = 13.5
    else: base = 11.5
    
    if intentos_previos <= 1 and percentil > 0.70: base = 17.5 if intentos_previos == 0 else 15.5
    techo = {0: 20.0, 1: 19.6, 2: 18.7}.get(intentos_previos, 17.4 if intentos_previos <=4 else 12.0)
    return max(10.0, min(round(min(base, techo) - (intentos_previos * 0.10), 2), 20.0))

# --- 1.3 SIDEBAR Y LOGIN (PERSISTENTE) ---
area_visual = locals().get('sidebar_area', st.sidebar)
with area_visual:
    st.subheader("EXAMEN DE CERTIFICACIÓN TÉCNICA", divider="blue")
    
    # Badge oficial
    st.markdown("""
    [![Unidad de Validación Técnica](https://img.shields.io/badge/UNIDAD_DE_VALIDACIÓN_TÉCNICA-ACADEMIA_TEC-0078D4?style=for-the-badge&logo=azure-devops&logoColor=white)](https://academiatec.haller.com.ve)
    """)
    
    st.markdown("""
    Entorno de **simulación computacional** diseñado para auditar habilidades técnicas en tiempo real bajo estándares de la industria.
    """)

    #with st.container(border=False):
    st.info("""
    **Academia TEC** es una iniciativa *EdTech* dedicada a la validación de competencias **STEM** *(Science, Technology, Engineering, Mathematics)*.
    
    El **objetivo** que persigue es el de mitigar la brecha entre la formación universitaria teórica y la demanda práctica de la **Industria 4.0**.
    """)

    st.markdown("""
    Mediante evaluaciones basadas en **casos reales**, validamos las **competencias críticas** requeridas para integrarse con éxito en entornos de **alta** exigencia técnica.
    """)
    
    #st.divider()
    st.caption(f"© {datetime.now().year} [Academia TEC](https://academiatec.haller.com.ve). Todos los derechos reservados. Validando el talento que impulsa la transformación digital.")

if "user_session" not in st.session_state:
    st.session_state.user_session = {"verified": False, "id": "", "section": ""}

if not st.session_state.user_session["verified"]:
    st.markdown("#### Acceso a la evaluación")
    with st.container(border=True):
        c1, c2 = st.columns([1, 2])
        sec_sel = c1.selectbox("Grupo/Sección", list(CONFIG_SECCIONES.keys()), index=None)
        id_sel = c2.text_input("Cédula", max_chars=12).strip()
        
        if st.button("Iniciar Sesión", type="primary", use_container_width=False):
            if sec_sel and id_sel:
                student_id_clean = "".join(filter(str.isdigit, id_sel))
                if not CONFIG_SECCIONES[sec_sel]["abierta"] and not is_admin:
                    st.error("⛔ Sección cerrada."); st.stop()
                st.session_state.user_session = {"verified": True, "id": student_id_clean, "section": sec_sel}
                st.rerun()
            else: st.warning("Datos incompletos.")
    st.stop()

# Recuperar datos de sesión
student_id = st.session_state.user_session["id"]
seccion_elegida = st.session_state.user_session["section"]
EXAMEN_SECCION_ID = f"{EXAM_ID}_{seccion_elegida}"

# Semilla Determinista
try: seed_val = int(student_id[-6:]) if len(student_id) > 0 else 42
except: seed_val = 42
random.seed(seed_val); np.random.seed(seed_val)

# Verificar Estado DB
status = db.check_student_status(EXAMEN_SECCION_ID, student_id)
nota_actual = status['score']
ha_aprobado = status['has_passed']

# ESTRUCTURA DE PESTAÑAS
tab_exam, tab_cert = st.tabs(["📝 Evaluación Práctica", "🎖️ Certificación Digital"])

# ==============================================================================
# ✅ BLOQUE 2: ZONA DE EXAMEN (IA: TRABAJA AQUÍ - MODIFICA ESTA SECCIÓN)
# ==============================================================================

with tab_exam:
    if ha_aprobado:
        st.success("✅ Examen completado.")
        c_score, c_msg = st.columns(2)
        c_score.metric("Nota Final", f"{nota_actual:.2f} / 20", border=True)
        if nota_actual >= BADGE_CONFIG["min_score_for_badge"]:
            c_msg.success("¡Elegible para Badge! Ve a la pestaña 'Certificación'.")
        else:
            c_msg.warning(f"Nota para Badge: {BADGE_CONFIG['min_score_for_badge']}")
    
    else:
        # ----------------------------------------------------------------------
        # 2.1 INICIO LÓGICA DEL EJERCICIO (IA)
        # ----------------------------------------------------------------------
        
        tema_ejercicio = "Cálculo de Potencia (Ejemplo)"
        
        # 1. Variables Aleatorias (Deterministas)
        voltaje = random.randint(110, 220)
        resistencia = random.randint(10, 50)
        
        # 2. Cálculo de Solución Exacta
        solucion_correcta = (voltaje ** 2) / resistencia
        
        # 3. Interfaz (Enunciado + Formulario)
        st.subheader(tema_ejercicio)
        st.info(f"Determine la potencia si **V = {voltaje}V** y **R = {resistencia}Ω**.")
        
        with st.form("exam_form"):
            # Widget de entrada (IA: Elige el adecuado)
            respuesta_usuario = st.number_input("Potencia (Watts):", step=0.1)
            enviar_btn = st.form_submit_button("Enviar Respuesta", type="primary")

        # ----------------------------------------------------------------------
        # 2.2 VALIDACIÓN Y REGISTRO (IA: Solo ajusta la tolerancia si es necesario)
        # ----------------------------------------------------------------------
        if enviar_btn:
            # Validación
            if isinstance(solucion_correcta, (float, np.floating)):
                es_correcto = np.isclose(respuesta_usuario, solucion_correcta, atol=0.5)
            else:
                es_correcto = (str(respuesta_usuario).strip().lower() == str(solucion_correcta).strip().lower())
            
            # Registro DB (No tocar)
            intentos, nota = db.register_attempt(EXAMEN_SECCION_ID, student_id, es_correcto, score_func=calcular_nota_personalizada)
            
            if es_correcto:
                st.toast("¡Correcto!", icon="🎉"); st.rerun()
            else:
                st.error("❌ Respuesta incorrecta."); st.caption(f"Intento #{intentos}")

# ==============================================================================
# 🛑 BLOQUE 3: GESTIÓN DE BADGES (IA: PROHIBIDO MODIFICAR)
# ==============================================================================

with tab_cert:
    st.markdown("#### Gestión de Credenciales Profesionales")
    
    if not ha_aprobado:
        st.info("🔒 Completa primero la evaluación práctica.")
    elif nota_actual < BADGE_CONFIG["min_score_for_badge"]:
        st.error(f"⛔ Tu calificación ({nota_actual:.2f}) no alcanza el mínimo para certificación ({BADGE_CONFIG['min_score_for_badge']}).")
    else:
        st.success("✨ ¡Felicidades! Eres elegible para certificación.")
        with st.container(border=True):
            st.markdown(f"**Badge:** {BADGE_CONFIG['course_name']}")
            c_name, c_btn = st.columns([3, 1], vertical_alignment="bottom")
            full_name = c_name.text_input("Tu Nombre Completo", placeholder="Ej: Rafael Urdaneta").strip().title()
            
            if c_btn.button("🎖️ Emitir", type="primary", use_container_width=True):
                if len(full_name) < 5:
                    st.toast("⚠️ Ingresa un nombre válido.", icon="⚠️")
                else:
                    with st.spinner("Conectando con Blockchain/API..."):
                        try:
                            payload = {
                                "student_id": student_id, "student_name": full_name,
                                "course_id": EXAM_ID, "course_name": BADGE_CONFIG["course_name"],
                                "skills": BADGE_CONFIG["skills"], "instructor": BADGE_CONFIG.get("instructor", "Academia TEC")
                            }
                            # URL Segura desde Secrets
                            base_url = st.secrets.get('BADGE_WORKER_URL', '').strip().rstrip("/")
                            if not base_url: raise Exception("BADGE_WORKER_URL no configurado en secrets.")
                            
                            r = requests.post(f"{base_url}/issue", json=payload, headers={"Authorization": f"Bearer {st.secrets.get('BADGE_API_KEY', '')}"}, timeout=20)
                            
                            if r.status_code == 200:
                                url_badge = r.json()['url']
                                st.balloons()
                                st.success("¡Certificación emitida!")
                                st.link_button("👉 Ver Credencial y Añadir a LinkedIn", url_badge, type="primary")
                            else:
                                st.error(f"Error de emisión: {r.text}")
                        except Exception as e:
                            st.error(f"Error de conexión: {str(e)}")
                            
