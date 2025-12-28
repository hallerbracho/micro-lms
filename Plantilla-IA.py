# --- INICIO DE PLANTILLA ---
# Variables inyectadas: st, pd, np, random, db, EXAM_ID, student_id (si ya fue ingresado)

# 1. VALIDACIÓN
raw_input = st.text_input("Ingresa tu cédula de identidad (sólo números)", max_chars=12)
student_id = "".join(filter(str.isdigit, raw_input))

if not student_id:
    st.warning("Ingrese su Cédula para comenzar.")
    st.stop()

# Verificar estado
status = db.check_student_status(EXAM_ID, student_id)
if status["has_passed"]:
    st.success(f"✅ Examen completado. Calificación: {status['score']}")
    st.stop()

# Semilla determinista
seed_val = int("".join(filter(str.isdigit, student_id)) or 0)
random.seed(seed_val)


########################################################################################
# 2. CONTENIDO (MODIFICAR AQUÍ)

area_visual = locals().get('sidebar_area', st.sidebar)

# Python intenta entrar en el contexto del objeto
with area_visual: 
    st.write("Formulario")
    # Colocar aquí una breve "cheat sheet" con la teoría necesaria para resolver el ejercicio.

titulo = "Pregunta de Ejemplo"
a = random.randint(1, 10)
b = random.randint(1, 10)
solucion = a + b

st.subheader(f"{titulo}",divider=True)
st.info(f"¿Cuánto es {a} + {b}?")

respuesta = st.number_input("Respuesta:", step=0.01)

########################################################################################

# 3. EVALUACIÓN

def calcular_nota_personalizada(intentos_previos, total_aprobados): # NO MODIFICAR ESTA FUNCIÓN 
    
    nota_base = 20.0
    inscritos = 25
    penalizacion_por_intento = intentos_previos * 0.5    
    penalizacion_por_ranking = total_aprobados * (10 / inscritos)
    
    nota_final = nota_base - penalizacion_por_intento - penalizacion_por_ranking    
    
    return max(nota_final, 10)


if st.button("Enviar"):
    es_correcto = (respuesta == solucion)
    
    intentos, nota = db.register_attempt(
        EXAM_ID, 
        student_id, 
        es_correcto, 
        score_func=calcular_nota_personalizada
    )
    
    if es_correcto:        
        st.success(f"¡Correcto! Nota: {nota}")
        st.caption("Calculada de la siguiente manera: 20 - (penalización por fallos) - (factor competitivo)") 
    else:
        st.error("Incorrecto.")

