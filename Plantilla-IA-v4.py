# ==============================================================================
# BLOQUE 1: CONFIGURACIÓN INICIAL (NO MODIFICAR)
# ==============================================================================
# Variables inyectadas: st, pd, np, random, db, EXAM_ID, is_admin

# 1.1 VALIDACIÓN DE IDENTIDAD
# Define aquí las secciones y su matrícula estimada para la curva competitiva
CONFIG_SECCIONES = {
    "Sección A (Lunes)": {"matricula": 35, "abierta": True},  
    "Sección B (Jueves)": {"matricula": 28, "abierta": False}, 
    "Sección C (Viernes)": {"matricula": 40, "abierta": False}
}

col_sec, col_id = st.columns([1, 2])
with col_id:
    raw_input = st.text_input("Ingresa tu **cédula de identidad** (sólo números)", max_chars=12).strip()
    student_id = "".join(filter(str.isdigit, raw_input))

with col_sec:
    opciones = list(CONFIG_SECCIONES.keys())
    seccion_elegida = st.selectbox("Selecciona tu **Sección**", opciones, placeholder="Elige...", index=None)

if not seccion_elegida:
    st.info("Ingrese su **cédula** y su **sección** para cargar el examen.")
    st.stop()

# Recuperar configuración de la sección elegida
info_seccion = CONFIG_SECCIONES[seccion_elegida]
esta_abierta = info_seccion["abierta"]
MATRICULA_ESTIMADA = info_seccion["matricula"]


# --- TRUCO CLAVE: ID VIRTUAL ---
# Esto crea un examen "único" en la BD para cada sección (ej: "Parcial1_Sección A")
# Así los contadores de aprobados y rankings se mantienen separados.
EXAMEN_SECCION_ID = f"{EXAM_ID}_{seccion_elegida}"


if not esta_abierta:
    # Si eres ADMIN (Profesor), te dejamos pasar pero te avisamos
    if is_admin:
        st.toast(f"⚠️ {seccion_elegida}: Cerrada a estudiantes (Modo Previsualización)", icon="🔒")
        st.caption(f"🔒 **NOTA:** La {seccion_elegida} está cerrada. Los alumnos verán pantalla de bloqueo.")
    else:
        # Si es ESTUDIANTE, lo bloqueamos aquí mismo
        st.warning(f"🔒 La evaluación para la **{seccion_elegida}** no está habilitada en este momento.")
        st.info("Por favor espere instrucciones del profesor.")
        st.stop()
        

if (not student_id) or (not seccion_elegida):
    st.info("Ingrese su **cédula** y su **sección** para cargar el examen.")
    st.stop()

# 1.2 VERIFICACIÓN DE ESTADO EN BD
status = db.check_student_status(EXAMEN_SECCION_ID, student_id)

if status["has_passed"]:
    st.success(f"✅ Examen completado anteriormente. Calificación: {status['score']}")
    st.caption("Nota calculada: 20 - (penalización por fallos) - (factor competitivo)")
    st.stop()

# 1.3 SEMILLA DETERMINISTA (Vital para el Solucionador)
# Esto asegura que el profesor vea las mismas variables que el alumno
try:
    seed_val = int(student_id[-6:]) if len(student_id) > 0 else 0
except:
    seed_val = 42
random.seed(seed_val)
np.random.seed(seed_val)

# ==============================================================================
# BLOQUE 2: GENERACIÓN DE CONTENIDO (IA: MODIFICAR AQUÍ)
# ==============================================================================

# 2.1 INFORMACIÓN GENERAL (Sidebar)
# Usar 'sidebar_area' si existe (inyectado por el sistema), sino st.sidebar
area_visual = locals().get('sidebar_area', st.sidebar)
with area_visual:    
        
    st.image("https://uru.edu/wp-content/uploads/2023/02/uru-logo-maracaibo.png")
    #st.image("https://luz.unir.edu.ve/wp-content/uploads/2024/04/escudo-Hor-gris-1024x427-1.png")
    st.subheader("Sistema de evaluación contínua")
    st.markdown("Prof. Haller Bracho")
    #st.html("<p>Departamento de Matemática<br>Facultad Experimental de Ciencias<br>La Universidad del Zulia</p>")    
    st.html("<p>Escuela de Telecomunicaciones<br>Facultad de Ingeniería<br>Universidad Rafael Urdaneta</p>")    
    #fecha2 = st.date_input("Calendario escolar", value="today", format="DD/MM/YYYY", width="stretch")
    st.caption("**Todas** las actividades han sido generadas automáticamente por la IA y revisadas por el profesor siguiendo el enfoque _human-in-the-loop_.")
        
    st.markdown("""
    (IA: REDACTA AQUÍ MUY BREVEMENTE COMO USAR LAS HERRRAMIENTAS GOOGLE COLAB Y/O GOOGLE SHEETS).
    
    [![Resolver en Google Colab](https://img.shields.io/badge/Resolver_en-Google_Colab-blue)](https://colab.new) | [![Resolver en Google Sheets](https://img.shields.io/badge/Resolver_en-Google_Sheets-green)](https://sheets.new)
    
    """)
    # ---------------------------------------------------

# 2.2 LÓGICA DEL PROBLEMA (Backend)
# --- IA: GENERA AQUÍ LAS VARIABLES ALEATORIAS Y LA SOLUCIÓN ---

# Ejemplo: Generación de pregunta
tema = "Pregunta Generada por IA"
var_a = random.randint(5, 50)
var_b = random.randint(2, 10)

# CÁLCULO DE LA SOLUCIÓN CORRECTA (Antes de mostrar nada)
# Importante: Definir el tipo de dato exacto (int, float, str, o lista)
solucion_correcta = var_a * var_b 

# Opciones (si fuera selección simple)
# correcta_str = "Opción A"
# distractores = ["Opción B", "Opción C"]
# opciones = distractores + [correcta_str]
# random.shuffle(opciones)
# solucion_correcta = correcta_str

# --------------------------------------------------------------

# 2.3 INTERFAZ DE USUARIO (Frontend)
st.subheader(tema, divider="gray")

# --- USO DE FORMULARIO (OBLIGATORIO PARA EVITAR RECARGAS) ---
with st.form("exam_form", enter_to_submit=False):
    st.write(f"Resuelva el siguiente problema considerando las variables asignadas:")
    
    # Enunciado dinámico
    st.info(f"Calcule el producto de **{var_a}** y **{var_b}**.")
    
    # --- IA: ELIGE EL WIDGET ADECUADO ---
    # Opción A: Numérico (Asegurar step y formato si es decimal)
    respuesta_usuario = st.number_input("Su respuesta:", step=1, format="%d")
    
    # Opción B: Selección Simple (Descomentar si se usa)
    # respuesta_usuario = st.radio("Seleccione:", options=opciones)
    
    # Opción C: Texto (Normalizar siempre a minúsculas/strip)
    # respuesta_usuario = st.text_input("Respuesta:").strip().lower()
    
    # Otras opciones: st.multiselect, st.slider, st.selectbox, st.toggle, st.select_slider, st.segmented_control, st.pills, st.checkbox, etc.
    
    st.write("") # Espacio
    enviado = st.form_submit_button("Enviar Respuesta Final", type="primary")

# ==============================================================================
# BLOQUE 3: EVALUACIÓN Y CALIFICACIÓN (NO MODIFICAR)
# ==============================================================================

# Función de calificación estándar del sistema
# BLOQUE 3: EVALUACIÓN Y CALIFICACIÓN
def calcular_nota_personalizada(intentos_previos, aprobados_antes):
    # --- CAMBIO: Obtiene la matrícula específica de la sección seleccionada arriba ---
    MATRICULA_ESTIMADA = CONFIG_SECCIONES[seccion_elegida] 
    
    # Evitar división por cero si la config está mal
    if MATRICULA_ESTIMADA < 1: MATRICULA_ESTIMADA = 25
    
    # Calcular percentil de llegada (0.0 = Primero, 1.0 = Último)
    posicion = aprobados_antes / MATRICULA_ESTIMADA   
        
    if posicion <= 0.15:    
        nota_base = 20.0
        zona = "Élite"
    elif posicion <= 0.35:
        nota_base = 18.0
        zona = "Destacada"
    elif posicion <= 0.80:
        nota_base = 15.0
        zona = "Estándar"
    else:
        nota_base = 12.0
        zona = "Rezagada"
        
    castigo_error = intentos_previos * 0.25
    nota_final = nota_base - castigo_error
    
    st.session_state['zona_alcanzada'] = f"{zona} ({seccion_elegida})" # Feedback visual
    
    return max(10.0, min(nota_final, 20.0))
    

if enviado:
    # 3.1 VALIDACIÓN
    # Comparación robusta (manejo de tolerancias para floats si es necesario)
    if isinstance(solucion_correcta, (float, np.floating)):
        es_correcto = np.isclose(respuesta_usuario, solucion_correcta, atol=0.01)
    else:
        es_correcto = (respuesta_usuario == solucion_correcta)

    # 3.2 REGISTRO EN BASE DE DATOS
    intentos, nota = db.register_attempt(
        EXAMEN_SECCION_ID, 
        student_id, 
        es_correcto, 
        score_func=calcular_nota_personalizada
    )
    
    # 3.3 FEEDBACK AL ESTUDIANTE
    if es_correcto:
        st.balloons()
        st.success(f"¡CORRECTO! Has aprobado.")
        st.markdown(f"""
        ### Nota Obtenida: {nota:.2f} / 20
        *Intentos realizados: {intentos}*
        """)
        st.caption("Nota calculada: 20 - (penalización por fallos) - (factor competitivo)")
    else:
        st.error(f"❌ Respuesta incorrecta.")
        with st.expander("Revisa las observaciones e intenta de nuevo"):
            st.warning(f"Intento #{intentos} registrado.")
            st.info("Revisa la teoría en la barra lateral y vuelve a intentarlo.")

