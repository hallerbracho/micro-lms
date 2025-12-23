# --- INICIO DE PLANTILLA ---
# Variables inyectadas: st, pd, np, random, db, EXAM_ID, student_id (si ya fue ingresado)

# 1. VALIDACIÓN
student_id = st.text_input("Ingrese su Cédula / ID", max_chars=12).strip()
if not student_id:
    st.warning("Ingrese su ID para comenzar.")
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

titulo = "Pregunta de Ejemplo"
a = random.randint(1, 10)
b = random.randint(1, 10)
solucion = a + b

st.subheader(f"{titulo}",divider=True)
st.info(f"¿Cuánto es {a} + {b}?")

if is_admin:
    st.warning(f"VISTA DOCENTE - Solución correcta: {solucion}") #Visualización para profesores

respuesta = st.number_input("Respuesta:", step=0.01)

########################################################################################


# 3. EVALUACIÓN
if st.button("Enviar"):
    es_correcto = (respuesta == solucion)
    intentos, nota = db.register_attempt(EXAM_ID, student_id, es_correcto)
    
    if es_correcto:
        #st.balloons()
        st.success(f"¡Correcto! Nota: {nota}")
    else:
        st.error("Incorrecto.")

