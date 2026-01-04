import streamlit as st
import pandas as pd
import numpy as np
import random
import io

# ==============================================================================
# BLOQUE 1: CONFIGURACIÓN INICIAL (NO MODIFICAR)
# ==============================================================================
# Variables inyectadas: st, pd, np, random, db, EXAM_ID, is_admin

# 1.1 VALIDACIÓN DE IDENTIDAD
raw_input = st.text_input("Ingresa tu cédula de identidad (sólo números)", max_chars=12).strip()
student_id = "".join(filter(str.isdigit, raw_input))

if not student_id:
    st.info("Ingrese su cédula para cargar el examen.")
    st.stop()

# 1.2 VERIFICACIÓN DE ESTADO EN BD
status = db.check_student_status(EXAM_ID, student_id)
if status["has_passed"]:
    st.success(f"✅ Examen completado anteriormente. Calificación: {status['score']}")
    st.caption("Nota calculada: 20 - (penalización por fallos) - (factor competitivo)")
    st.stop()

# 1.3 SEMILLA DETERMINISTA (Vital para el Solucionador)
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
area_visual = locals().get('sidebar_area', st.sidebar)
with area_visual:
    st.header("📚 Teoría de Errores")
    st.markdown(rf"""
    **Definiciones Clave:**
    
    1. **Valor Verdadero ($V_v$):** Valor aceptado como exacto o teórico.
    2. **Valor Aproximado ($V_a$):** En este contexto, será el **promedio aritmético** de las mediciones del sensor.
    
    **Fórmulas:**
    
    * **Error Absoluto ($E_a$):**
        $$E_a = |V_v - V_a|$$
    
    * **Error Relativo ($E_r$):**
        $$E_r = \frac{{E_a}}{{|V_v|}}$$
    
    * **Error Porcentual ($E_p$):**
        $$E_p = E_r \times 100\%$$
    
    ---
    *Nota: Utilice todos los decimales posibles durante el cálculo y redondee solo al ingresar la respuesta final (4 decimales).*
    """)

# 2.2 LÓGICA DEL PROBLEMA (Backend)

# --- GENERACIÓN DE DATOS SIMULADOS (Contexto Maracaibo) ---

# Caso 1: Temperatura en Planta de Vapor (Complejo El Tablazo)
vv_c1 = random.uniform(180.0, 220.0) # Grados Celsius
noise_c1 = np.random.normal(0, 1.5, 50) # 50 mediciones
data_c1 = vv_c1 + noise_c1
va_c1 = np.mean(data_c1)

# Caso 2: Voltaje en Paneles Solares (Zona Industrial Sur)
vv_c2 = random.uniform(23.5, 24.5) # Voltios
noise_c2 = np.random.normal(0, 0.8, 40) # 40 mediciones (sensor ruidoso)
data_c2 = vv_c2 + noise_c2
va_c2 = np.mean(data_c2)

# Caso 3: Diámetro de Tubería PVC (Fábrica en San Francisco)
vv_c3 = random.uniform(4.9, 5.1) # Pulgadas
noise_c3 = np.random.normal(0, 0.05, 60) # 60 mediciones (alta precisión)
data_c3 = vv_c3 + noise_c3
va_c3 = np.mean(data_c3)

# Crear DataFrame para descargar
df_final = pd.DataFrame({
    'ID_Muestra': range(1, 151),
    'Sensor_ID': (['TEMP-TABLAZO']*50) + (['VOLT-ZONA-IND']*40) + (['DIAM-SAN-FRAN']*60),
    'Valor_Medido': np.concatenate([data_c1, data_c2, data_c3])
})

# Convertir a CSV en memoria
csv_buffer = io.StringIO()
df_final.to_csv(csv_buffer, index=False)
csv_data = csv_buffer.getvalue()

# --- CÁLCULO DE SOLUCIONES CORRECTAS ---
# Formato de solución: Lista de 12 valores [Media1, Ea1, Er1, Ep1, Media2, Ea2, ... ]

def calc_metrics(real, approx):
    ea = abs(real - approx)
    er = ea / abs(real)
    ep = er * 100
    return [approx, ea, er, ep]

sol_c1 = calc_metrics(vv_c1, va_c1)
sol_c2 = calc_metrics(vv_c2, va_c2)
sol_c3 = calc_metrics(vv_c3, va_c3)

# Concatenamos todo en una sola lista para validar
solucion_correcta = sol_c1 + sol_c2 + sol_c3

# 2.3 INTERFAZ DE USUARIO (Frontend)
st.subheader("Evaluación de Propagación de Errores - Datos Masivos", divider="gray")

st.markdown(rf"""
Bienvenido, Ingeniero. Se han desplegado sensores prototipo en tres ubicaciones clave del estado Zulia. 
Su tarea es descargar el registro de datos crudos (Raw Data), procesarlos para encontrar el valor experimental promedio y determinar la calidad de la medición respecto al valor teórico de ficha técnica.

**Instrucciones:**
1. Descargue el archivo `sensor_data_zulia.csv`.
2. Filtre y procese los datos para cada sensor.
3. Calcule el **Promedio (Valor Aproximado)** de las mediciones.
4. Compare contra el **Valor Teórico ($V_v$)** indicado en cada pestaña.
""")

# Botón de Descarga
st.download_button(
    label="📥 Descargar Dataset de Sensores (.csv)",
    data=csv_data,
    file_name=f"sensor_data_{student_id}.csv",
    mime="text/csv",
    type="secondary"
)

#st.divider()

# --- USO DE FORMULARIO ÚNICO ---
with st.form("exam_form", enter_to_submit=False):
    st.write("Ingrese sus cálculos con una precisión de al menos **4 decimales**.")
    
    tabs = st.tabs(["Planta El Tablazo", "Zona Industrial", "Fábrica San Francisco"])
    
    # --- PESTAÑA 1 ---
    with tabs[0]:
        st.info(rf"**Sensor:** TEMP-TABLAZO (Temperatura). **Valor Teórico ($V_v$):** {vv_c1:.4f} °C")
        c1, c2 = st.columns(2)
        r1_media = c1.number_input("Promedio Calculado ($V_a$):", format="%.4f", key="r1_m")
        r1_ea = c2.number_input("Error Absoluto ($E_a$):", format="%.4f", key="r1_ea")
        r1_er = c1.number_input("Error Relativo ($E_r$):", format="%.6f", key="r1_er")
        r1_ep = c2.number_input("Error Porcentual ($E_p$):", format="%.4f", key="r1_ep")

    # --- PESTAÑA 2 ---
    with tabs[1]:
        st.info(rf"**Sensor:** VOLT-ZONA-IND (Voltaje). **Valor Teórico ($V_v$):** {vv_c2:.4f} V")
        c1, c2 = st.columns(2)
        r2_media = c1.number_input("Promedio Calculado ($V_a$):", format="%.4f", key="r2_m")
        r2_ea = c2.number_input("Error Absoluto ($E_a$):", format="%.4f", key="r2_ea")
        r2_er = c1.number_input("Error Relativo ($E_r$):", format="%.6f", key="r2_er")
        r2_ep = c2.number_input("Error Porcentual ($E_p$):", format="%.4f", key="r2_ep")

    # --- PESTAÑA 3 ---
    with tabs[2]:
        st.info(rf"**Sensor:** DIAM-SAN-FRAN (Diámetro). **Valor Teórico ($V_v$):** {vv_c3:.4f} in")
        c1, c2 = st.columns(2)
        r3_media = c1.number_input("Promedio Calculado ($V_a$):", format="%.4f", key="r3_m")
        r3_ea = c2.number_input("Error Absoluto ($E_a$):", format="%.4f", key="r3_ea")
        r3_er = c1.number_input("Error Relativo ($E_r$):", format="%.6f", key="r3_er")
        r3_ep = c2.number_input("Error Porcentual ($E_p$):", format="%.4f", key="r3_ep")
    
    st.write("") 
    # Recopilar respuesta del usuario en una lista ordenada igual que la solución
    respuesta_usuario = [
        r1_media, r1_ea, r1_er, r1_ep,
        r2_media, r2_ea, r2_er, r2_ep,
        r3_media, r3_ea, r3_er, r3_ep
    ]
    
    enviado = st.form_submit_button("Enviar Respuesta Final", type="primary")

# ==============================================================================
# BLOQUE 3: EVALUACIÓN Y CALIFICACIÓN (NO MODIFICAR)
# ==============================================================================

# Función de calificación estándar del sistema
def calcular_nota_personalizada(intentos_previos, aprobados_antes):
    # Ajustar según matrícula promedio de tus secciones
    MATRICULA_ESTIMADA = 25    # AJUSTAR PARA CADA SECCIÓN
    
    # Calcular percentil de llegada (0.0 = Primero, 1.0 = Último)
    posicion = aprobados_antes / MATRICULA_ESTIMADA
    
    # A. Asignación de Zonas (Competencia por Velocidad/Eficiencia)
    if posicion <= 0.15:    # Top 15% 
        nota_base = 20.0
        zona = "Élite"
    elif posicion <= 0.35:  # Siguiente 20%
        nota_base = 18.0
        zona = "Destacada"
    elif posicion <= 0.80:  # El grueso del grupo (45%)
        nota_base = 15.0
        zona = "Estándar"
    else:                   # Los últimos 20%
        nota_base = 12.0
        zona = "Rezagada"
        
    # B. Penalización por Precisión (AJUSTADO A 0.25)
    # Se perdona el error humano leve. Se necesita fallar 4 veces para perder 1 punto.
    castigo_error = intentos_previos * 0.25
    
    nota_final = nota_base - castigo_error
    
    # Guardamos la zona en sesión para feedback visual
    st.session_state['zona_alcanzada'] = zona
    
    # Límites: Piso de 10 si responde bien, Techo de 20
    return max(10.0, min(nota_final, 20.0))
    

if enviado:
    # 3.1 VALIDACIÓN
    # Comparación robusta para listas de flotantes
    try:
        # Tolerancia estricta para asegurar precisión en los cálculos (0.5%)
        # Convertimos ambas listas a arrays de numpy para comparación vectorizada
        arr_usuario = np.array(respuesta_usuario, dtype=float)
        arr_solucion = np.array(solucion_correcta, dtype=float)
        
        # Usamos relative tolerance (rtol) del 0.1% y absoluta (atol) pequeña
        es_correcto = np.allclose(arr_usuario, arr_solucion, rtol=0.001, atol=0.001)
        
    except Exception as e:
        es_correcto = False

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
        
        # --- FEEDBACK DETALLADO DE ERRORES (CUSTOM) ---
        # Calculamos diferencias para dar pistas sin dar la respuesta
        try:
            diffs = np.abs(np.array(respuesta_usuario) - np.array(solucion_correcta))
            # Índices de los 3 casos
            labels = ["El Tablazo (Temp)", "Zona Ind. (Voltaje)", "San Francisco (Diámetro)"]
            
            st.markdown("##### Diagnóstico de Errores:")
            
            for i in range(3):
                offset = i * 4
                # Revisamos si el bloque de 4 valores tiene error
                if not np.allclose(arr_usuario[offset:offset+4], arr_solucion[offset:offset+4], rtol=0.001, atol=0.001):
                    errores_detectados = []
                    if not np.isclose(arr_usuario[offset], arr_solucion[offset], rtol=0.001): errores_detectados.append("Promedio")
                    if not np.isclose(arr_usuario[offset+1], arr_solucion[offset+1], rtol=0.001): errores_detectados.append("Error Absoluto")
                    if not np.isclose(arr_usuario[offset+2], arr_solucion[offset+2], rtol=0.001): errores_detectados.append("Error Relativo")
                    if not np.isclose(arr_usuario[offset+3], arr_solucion[offset+3], rtol=0.001): errores_detectados.append("Error %")
                    
                    st.warning(f"⚠️ **{labels[i]}**: Revisa tus cálculos en: {', '.join(errores_detectados)}.")
                    if "Promedio" in errores_detectados:
                        st.caption("💡 Pista: Si el promedio está mal, todos los errores estarán mal. Verifica el filtro de datos en el CSV.")
        except:
            pass
            
        st.warning(f"Intento #{intentos} registrado.")
        st.info("Revisa la teoría en la barra lateral y vuelve a intentarlo.")

