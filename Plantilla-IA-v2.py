# ==============================================================================
# BLOQUE 1: CONFIGURACIÓN INICIAL (NO MODIFICAR)
# ==============================================================================
# Variables inyectadas: st, pd, np, random, db, EXAM_ID, is_admin

# 1.1 VALIDACIÓN DE IDENTIDAD
raw_input = st.text_input("Ingresa tu cédula de identidad (sólo números)", max_chars=12).strip()
student_id = "".join(filter(str.isdigit, raw_input))

if not student_id:
    st.info("👋 Ingrese su ID para cargar el examen.")
    st.stop()

# 1.2 VERIFICACIÓN DE ESTADO EN BD
status = db.check_student_status(EXAM_ID, student_id)
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

# 2.1 MATERIAL DE APOYO (Sidebar)
# Usar 'sidebar_area' si existe (inyectado por el sistema), sino st.sidebar
area_visual = locals().get('sidebar_area', st.sidebar)
with area_visual:
    st.header("📚 Material de Apoyo")
    # --- IA: INSERTA AQUÍ FÓRMULAS O TEORÍA RESUMIDA ---
    st.markdown("""
    *Recuerda:*
    - Concepto clave 1...
    - Fórmula importante...
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
with st.form("exam_form"):
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
    
    st.write("") # Espacio
    enviado = st.form_submit_button("🔒 Enviar Respuesta Final", type="primary")

# ==============================================================================
# BLOQUE 3: EVALUACIÓN Y CALIFICACIÓN (NO MODIFICAR)
# ==============================================================================

# Función de calificación estándar del sistema
def calcular_nota_personalizada(intentos_previos, total_aprobados):
    nota_base = 20.0
    cupo_estimado = 30 # Ajustar según tamaño del curso
    
    penalizacion_intentos = intentos_previos * 0.5    
    penalizacion_ranking = total_aprobados * (10.0 / cupo_estimado)
    
    nota_final = nota_base - penalizacion_intentos - penalizacion_ranking    
    return max(nota_final, 10.0) # Nota mínima 10

if enviado:
    # 3.1 VALIDACIÓN
    # Comparación robusta (manejo de tolerancias para floats si es necesario)
    if isinstance(solucion_correcta, (float, np.floating)):
        es_correcto = np.isclose(respuesta_usuario, solucion_correcta, atol=0.01)
    else:
        es_correcto = (respuesta_usuario == solucion_correcta)

    # 3.2 REGISTRO EN BASE DE DATOS
    intentos, nota = db.register_attempt(
        EXAM_ID, 
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
        st.warning(f"Intento #{intentos} registrado.")
        st.info("Revisa la teoría en la barra lateral y vuelve a intentarlo.")
