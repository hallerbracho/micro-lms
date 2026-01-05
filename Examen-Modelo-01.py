import io

# ==============================================================================
# BLOQUE 1: CONFIGURACIÓN INICIAL (NO MODIFICAR)
# ==============================================================================
# Variables inyectadas: st, pd, np, random, db, EXAM_ID, is_admin

# 1.1 VALIDACIÓN DE IDENTIDAD
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
EXAMEN_SECCION_ID = f"{EXAM_ID}_{seccion_elegida}"

if not esta_abierta:
    if is_admin:
        st.toast(f"⚠️ {seccion_elegida}: Cerrada a estudiantes (Modo Previsualización)", icon="🔒")
        st.caption(f"🔒 **NOTA:** La {seccion_elegida} está cerrada. Los alumnos verán pantalla de bloqueo.")
    else:
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

# 1.3 SEMILLA DETERMINISTA
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
area_visual = locals().get('sidebar_area', st.sidebar)
with area_visual:    
    st.image("https://uru.edu/wp-content/uploads/2023/02/uru-logo-maracaibo.png")
    st.subheader("Sistema de evaluación contínua")
    st.markdown("Prof. Haller Bracho")
    st.html("Escuela de Telecomunicaciones<br>Facultad de Ingeniería<br>Universidad Rafael Urdaneta")    
    st.caption("**Todas** las actividades han sido generadas automáticamente por la IA y revisadas por el profesor siguiendo el enfoque _human-in-the-loop_.")
        
    st.markdown("""
    **Instrucciones Google Colab/Sheets:**
    1. Descargue el archivo `.csv` generado.
    2. Súbalo a Google Drive o ábralo localmente en Excel.
    3. Use fórmulas (`=PROMEDIO`, `=ABS`) o Python (`pandas`) para procesar los datos masivos.
    
    [![Resolver en Google Colab](https://img.shields.io/badge/Resolver_en-Google_Colab-blue)](https://colab.new) | [![Resolver en Google Sheets](https://img.shields.io/badge/Resolver_en-Google_Sheets-green)](https://sheets.new)
    """)

# 2.2 LÓGICA DEL PROBLEMA (Backend)

# --- GENERACIÓN DE DATOS MASIVOS (Scenario: El Tablazo) ---
st.subheader("Calibración de Sensores en Planta de Olefinas - El Tablazo", divider="gray")
st.markdown("""
El departamento de mantenimiento predictivo en el **Complejo Petroquímico Ana María Campos** ha realizado una auditoría masiva de sensores.
Se le suministra un archivo con miles de lecturas crudas. Su tarea es calcular los errores fundamentales comparando el **Promedio de las mediciones** ($V_{medido}$) contra el **Valor Estándar de Calibración** ($V_{real}$).
""")

# Definir valores reales (Standards) aleatorios pero realistas
std_presion = random.randint(1200, 1500) # PSI
std_temp = random.randint(450, 600)      # Grados C
std_flujo = random.randint(80, 120)      # L/min

# Generar Dataset ruidoso
n_rows = 500
data = {
    "Lectura_ID": [f"L-{i:04d}" for i in range(n_rows)],
    "Presion_PSI_PlantaA": np.random.normal(std_presion + random.uniform(-15, 15), 5.5, n_rows).round(2),
    "Temp_C_HornoB": np.random.normal(std_temp + random.uniform(-8, 8), 2.1, n_rows).round(2),
    "Flujo_Lmin_TuberiaC": np.random.normal(std_flujo + random.uniform(-2, 2), 0.8, n_rows).round(2)
}
df = pd.DataFrame(data)

# Crear archivo descargable
csv_buffer = io.StringIO()
df.to_csv(csv_buffer, index=False)
csv_data = csv_buffer.getvalue()

st.download_button(
    label="📥 Descargar Dataset de Lecturas (CSV)",
    data=csv_data,
    file_name=f"audit_tablazo_{student_id}.csv",
    mime="text/csv",
    type="secondary"
)

# --- CÁLCULO DE LA SOLUCIÓN CORRECTA ---
# Ejercicio 1: Presión
mean_presion = df["Presion_PSI_PlantaA"].mean()
e_abs_1 = abs(std_presion - mean_presion)
e_rel_1 = e_abs_1 / std_presion
e_por_1 = e_rel_1 * 100

# Ejercicio 2: Temperatura
mean_temp = df["Temp_C_HornoB"].mean()
e_abs_2 = abs(std_temp - mean_temp)
e_rel_2 = e_abs_2 / std_temp
e_por_2 = e_rel_2 * 100

# Ejercicio 3: Flujo
mean_flujo = df["Flujo_Lmin_TuberiaC"].mean()
e_abs_3 = abs(std_flujo - mean_flujo)
e_rel_3 = e_abs_3 / std_flujo
e_por_3 = e_rel_3 * 100

# Guardar soluciones en diccionario
soluciones = {
    "e1": [mean_presion, e_abs_1, e_rel_1, e_por_1],
    "e2": [mean_temp, e_abs_2, e_rel_2, e_por_2],
    "e3": [mean_flujo, e_abs_3, e_rel_3, e_por_3]
}

# 2.3 INTERFAZ DE USUARIO (Frontend)
st.info("Para el valor medido ($V_m$), calcule el **promedio aritmético** de todos los datos de la columna correspondiente en el archivo CSV. **Verifique** que ha completado las 3 pestañas **antes** de enviar.")

# --- USO DE FORMULARIO ---
with st.form("exam_form", enter_to_submit=False):
    
    tabs = st.tabs(["Ejercicio 1: Presión", "Ejercicio 2: Temperatura", "Ejercicio 3: Flujo"])
    
    # --- TAB 1 ---
    with tabs[0]:
        st.markdown(f"**Estándar de Calibración (Valor Real):** $V_r = {std_presion}$ PSI")
        #st.latex(r"E_p = \left| \frac{V_r - V_m}{V_r} \right| \times 100")
        
        c1, c2 = st.columns(2)
        with c1:
            u_mean_1 = st.number_input("Promedio calculado ($V_m$):", format="%.4f", key="u_m1")
            u_abs_1 = st.number_input("Error Absoluto ($E_a$):", format="%.4f", key="u_ea1")
        with c2:
            u_rel_1 = st.number_input("Error Relativo ($E_r$):", format="%.6f", key="u_er1")
            u_por_1 = st.number_input("Error Porcentual ($E_p$):", format="%.4f", key="u_ep1")

    # --- TAB 2 ---
    with tabs[1]:
        st.markdown(f"**Estándar de Calibración (Valor Real):** $V_r = {std_temp}$ °C")
        #st.latex(r"E_r = \frac{E_a}{V_r}")
        
        c3, c4 = st.columns(2)
        with c3:
            u_mean_2 = st.number_input("Promedio calculado ($V_m$):", format="%.4f", key="u_m2")
            u_abs_2 = st.number_input("Error Absoluto ($E_a$):", format="%.4f", key="u_ea2")
        with c4:
            u_rel_2 = st.number_input("Error Relativo ($E_r$):", format="%.6f", key="u_er2")
            u_por_2 = st.number_input("Error Porcentual ($E_p$):", format="%.4f", key="u_ep2")

    # --- TAB 3 ---
    with tabs[2]:
        st.markdown(f"**Estándar de Calibración (Valor Real):** $V_r = {std_flujo}$ L/min")
        #st.latex(r"E_a = | V_r - V_m |")
        
        c5, c6 = st.columns(2)
        with c5:
            u_mean_3 = st.number_input("Promedio calculado ($V_m$):", format="%.4f", key="u_m3")
            u_abs_3 = st.number_input("Error Absoluto ($E_a$):", format="%.4f", key="u_ea3")
        with c6:
            u_rel_3 = st.number_input("Error Relativo ($E_r$):", format="%.6f", key="u_er3")
            u_por_3 = st.number_input("Error Porcentual ($E_p$):", format="%.4f", key="u_ep3")

    #st.write("") 
    #st.warning("Verifique que ha completado las 3 pestañas antes de enviar.")
    enviado = st.form_submit_button("Enviar Evaluación Completa", type="primary")

# ==============================================================================
# BLOQUE 3: EVALUACIÓN Y CALIFICACIÓN (CORREGIDO)
# ==============================================================================

def calcular_nota_personalizada(intentos_previos, aprobados_antes=0):
    # CORRECCIÓN: Accedemos explícitamente a la clave "matricula"
    MATRICULA_ESTIMADA = CONFIG_SECCIONES[seccion_elegida]["matricula"]
    
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
    
    st.session_state['zona_alcanzada'] = f"{zona} ({seccion_elegida})" 
    
    return max(10.0, min(nota_final, 20.0))

if enviado:
    # 3.1 VALIDACIÓN
    user_inputs = {
        "e1": [u_mean_1, u_abs_1, u_rel_1, u_por_1],
        "e2": [u_mean_2, u_abs_2, u_rel_2, u_por_2],
        "e3": [u_mean_3, u_abs_3, u_rel_3, u_por_3]
    }
    
    errores_detectados = []
    
    # Validamos cada ejercicio con tolerancia
    for key in ["e1", "e2", "e3"]:
        vals_correctos = soluciones[key]
        vals_usuario = user_inputs[key]
        
        # Tolerancias: Promedio (0.05), Abs (0.05), Rel (0.001), Porc (0.1)
        tolerancias = [0.05, 0.05, 0.001, 0.1] 
        
        if not np.allclose(vals_usuario, vals_correctos, atol=tolerancias):
            if key == "e1": errores_detectados.append("Ejercicio 1 (Presión)")
            if key == "e2": errores_detectados.append("Ejercicio 2 (Temperatura)")
            if key == "e3": errores_detectados.append("Ejercicio 3 (Flujo)")

    es_correcto = (len(errores_detectados) == 0)

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
        st.success(f"¡EXCELENTE TRABAJO! Has validado correctamente la calibración.")
        st.markdown(f"""
        ### Nota Obtenida: {nota:.2f} / 20
        *Intentos realizados: {intentos}*
        """)
        st.caption("Nota calculada: 20 - (penalización por fallos) - (factor competitivo)")
    else:
        st.error(f"❌ Se encontraron discrepancias en los resultados.")
        with st.expander("Informe de Errores"):
            st.warning(f"Intento #{intentos} registrado.")
            st.write("Debes revisar los cálculos en las siguientes secciones:")
            for err in errores_detectados:
                st.markdown(f"- **{err}**: Verifica si estás usando el promedio correcto o si el error relativo está bien escalado.")
            st.info("Recuerda: Error Absoluto es magnitud, Error Relativo es decimal, Error Porcentual lleva %.")

