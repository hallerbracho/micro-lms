import streamlit as st
import libsql_experimental as libsql
import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta, timezone  # <--- SE AGREGARON LIBRERÍAS DE TIEMPO
import types

# ==============================================================================
# 1. CONFIGURACIÓN Y ESTILOS
# ==============================================================================
st.set_page_config(layout="centered", page_title="Plataforma de Evaluación", page_icon="🎓")

ST_STYLE = """
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stApp { background-color: #ffffff; color: #111111; }
    textarea { font-family: 'Courier New', Courier, monospace !important; background-color: #f8f9fa !important; }
    .stButton>button { border-radius: 4px; border: 1px solid #ccc; width: 100%; }
    .stButton>button:hover { border-color: #333; color: #333; }
    
    section[data-testid="stSidebar"] {
            width: 430px !important; # Set the width to your desired value 
        }
        
</style>
"""
st.markdown(ST_STYLE, unsafe_allow_html=True)

# Plantilla por defecto para nuevos exámenes

DEFAULT_TEMPLATE = """# --- INICIO DE PLANTILLA ---
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

# 2. CONTENIDO (MODIFICAR AQUÍ)
titulo = "Pregunta de Ejemplo"
a = random.randint(1, 10)
b = random.randint(1, 10)
solucion = a + b

st.markdown(f"## {titulo}")

st.info(f"¿Cuánto es {a} + {b}?")

respuesta = st.number_input("Respuesta:", step=0.0001)

# 3. EVALUACIÓN
if st.button("Enviar"):
    es_correcto = (respuesta == solucion)
    intentos, nota = db.register_attempt(EXAM_ID, student_id, es_correcto)
    
    if es_correcto:
        #st.balloons()
        st.success(f"¡Correcto! Nota: {nota}")
    else:
        st.error("Incorrecto.")
"""


# ==============================================================================
# 2. CAPA DE DATOS (Turso / LibSQL)
# ==============================================================================

@st.cache_resource
def get_db_connection():
    """
    Crea una conexión persistente a Turso e inicializa las tablas UNA SOLA VEZ.
    """
    url = st.secrets["TURSO_DB_URL"]
    token = st.secrets["TURSO_AUTH_TOKEN"]
    conn = libsql.connect(database=url, auth_token=token)
    
    # --- BLOQUE MOVIDO: Se ejecuta solo la primera vez que arranca el servidor ---
    # Tabla de Notas (Grades)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS grades (
            exam_id TEXT,
            student_id TEXT,
            attempts INTEGER DEFAULT 0,
            score REAL DEFAULT 0,
            is_correct BOOLEAN DEFAULT 0,
            last_updated TIMESTAMP,
            PRIMARY KEY (exam_id, student_id)
        )
    """)
    
    # Tabla de Exámenes (Source Code Storage)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS exams (
            exam_id TEXT PRIMARY KEY,
            source_code TEXT,
            created_at TIMESTAMP
        )
    """)
    conn.commit()
    # -----------------------------------------------------------------------------
    
    return conn

class DatabaseManager:
    def __init__(self):
        # Ya no hace falta inicializar la DB aquí, se hace en la conexión
        pass

    def _get_conn(self):
        return get_db_connection()

    def _get_ve_time(self):
        """Retorna la hora actual en UTC-4 (Venezuela) en formato string SQL"""
        # Obtenemos UTC actual y restamos 4 horas
        ve_time = datetime.now(timezone.utc) - timedelta(hours=4)
        return ve_time.strftime('%Y-%m-%d %H:%M:%S')

    # --- MÉTODOS DE ESTUDIANTE ---
    def check_student_status(self, exam_id: str, student_id: str):
        conn = self._get_conn()
        row = conn.execute(
            "SELECT score FROM grades WHERE exam_id=? AND student_id=? AND is_correct=1", 
            (exam_id, student_id)
        ).fetchone()
        if row:
            return {"has_passed": True, "score": row[0]}
        return {"has_passed": False, "score": 0}

    def register_attempt(self, exam_id: str, student_id: str, is_correct: bool, score_func=None):
        conn = self._get_conn()
        
        # 1. Fallos previos
        res_fail = conn.execute("SELECT attempts FROM grades WHERE exam_id=? AND student_id=?", (exam_id, student_id)).fetchone()
        prev_failures = res_fail[0] if res_fail else 0
        
        # 2. Factor Z (Aprobados globales)
        res_pass = conn.execute("SELECT COUNT(*) FROM grades WHERE exam_id=? AND is_correct=1", (exam_id,)).fetchone()
        passed_count = res_pass[0] if res_pass else 0
        
        # 3. Cálculo de Nota
        score = 0
        if is_correct:
            if score_func:
                try:
                    score = score_func(prev_failures, passed_count)
                except TypeError:
                    score = score_func(prev_failures)
            else:
                z_penalty = passed_count * 0.20
                score = max(20 - (prev_failures * 1.0) - z_penalty, 10) 
        
        # 4. Upsert con HORA VENEZUELA
        increment = 0 if is_correct else 1
        current_time_ve = self._get_ve_time() # Hora UTC-4
        
        conn.execute("""
            INSERT INTO grades (exam_id, student_id, attempts, is_correct, score, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(exam_id, student_id) DO UPDATE SET
                attempts = attempts + excluded.attempts,
                is_correct = excluded.is_correct,
                score = CASE WHEN excluded.is_correct THEN excluded.score ELSE grades.score END,
                last_updated = excluded.last_updated
        """, (exam_id, student_id, increment, is_correct, score, current_time_ve))
        conn.commit()
        
        return prev_failures + increment, score

    def get_all_grades(self):
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM grades ORDER BY last_updated DESC")
        cols = [d[0] for d in cursor.description]
        return pd.DataFrame(cursor.fetchall(), columns=cols)

    # --- MÉTODOS DE GESTIÓN DE EXÁMENES (CMS) ---
    def get_exam_list(self):
        conn = self._get_conn()
        rows = conn.execute("SELECT exam_id FROM exams ORDER BY created_at DESC").fetchall()
        return [r[0] for r in rows]

    def get_exam_code(self, exam_id):
        conn = self._get_conn()
        row = conn.execute("SELECT source_code FROM exams WHERE exam_id=?", (exam_id,)).fetchone()
        return row[0] if row else None

    def save_exam(self, exam_id, code):
        conn = self._get_conn()
        current_time_ve = self._get_ve_time() # Hora UTC-4
        
        conn.execute("""
            INSERT INTO exams (exam_id, source_code, created_at) VALUES (?, ?, ?)
            ON CONFLICT(exam_id) DO UPDATE SET 
                source_code = excluded.source_code,
                created_at = excluded.created_at
        """, (exam_id, code, current_time_ve))
        conn.commit()

    def delete_exam(self, exam_id):
        conn = self._get_conn()
        conn.execute("DELETE FROM exams WHERE exam_id=?", (exam_id,))
        conn.commit()

db_manager = DatabaseManager()

# ==============================================================================
# 3. LÓGICA DE INTERFAZ (Admin vs Estudiante)
# ==============================================================================

def execute_exam(exam_id):
    """Carga el código desde BD y lo ejecuta en un entorno seguro"""
    source_code = db_manager.get_exam_code(exam_id)
    
    if not source_code:
        st.error("El examen solicitado no existe o no está disponible.")
        if st.button("Volver al Inicio"):
            st.query_params.clear()
            st.rerun()
        return

    # Determinamos si es admin basándonos en la sesión actual
    is_admin_user = st.session_state.get('auth', False)
    
    with st.sidebar:
        
        contenedor_teoria = st.container()        
    
    context = {
        'st': st,
        'pd': pd,
        'np': np,
        'random': random,
        'db': db_manager,
        'EXAM_ID': exam_id,
        'datetime': datetime,
        'is_admin': is_admin_user,  # <--- NUEVA VARIABLE INYECTADA
        'sidebar_area': contenedor_teoria
    }
    
    try:
        exec(source_code, context)
    except Exception as e:
        st.error("🚨 Error interno en la ejecución del examen.")
        with st.expander("Detalles para el profesor"):
            st.code(str(e))



# ==============================================================================
# CLASES AUXILIARES PARA EL SOLUCIONADOR (Agregar antes de render_admin_panel)
# ==============================================================================

# ==============================================================================
# CLASES AUXILIARES (Actualizar esta sección al inicio del script)
# ==============================================================================

class SilentStreamlit:
    """Simula ser 'st' para ejecutar el examen sin interfaz gráfica."""
    def __init__(self, fixed_input):
        self.fixed_input = str(fixed_input)
        self.secrets = st.secrets
        self.session_state = {} 
        
    @property
    def sidebar(self):
        # Cuando el código pida 'st.sidebar', devolvemos 'self' 
        # para que el 'with st.sidebar:' funcione (no hace nada, pero no da error).
        return self
        
    def container(self):
        # Cuando el código pida 'st.container()', también devolvemos 'self'
        return self

    def text_input(self, label, **kwargs):
        return self.fixed_input
    
    def number_input(self, label, **kwargs):
        return 0 
        
    def columns(self, spec, **kwargs):
        # CORRECCIÓN: Detectar si 'spec' es un entero o una lista [1, 2]
        count = spec if isinstance(spec, int) else len(spec)
        return [self] * count
        
    def tabs(self, tabs_list, **kwargs):
        return [self] * len(tabs_list)

    def stop(self):
        pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def __iter__(self):
        # Permite iterar sobre columnas si el código hace: for col in st.columns(2):
        yield self

    def __getattr__(self, name):
        # Atrapa cualquier otro método (latex, map, image, etc) y no hace nada
        return lambda *args, **kwargs: self
        

class MockDB:
    """Simula la BD para forzar que el examen se ejecute (ignora si ya aprobó)."""
    def check_student_status(self, exam_id, student_id):
        # Siempre dice que NO ha aprobado para que el código calcule la solución
        return {"has_passed": False, "score": 0}
        
    def register_attempt(self, *args, **kwargs):
        return 0, 0



# ==============================================================================
# REEMPLAZAR LA FUNCIÓN render_admin_panel COMPLETA CON ESTA VERSIÓN
# ==============================================================================

def render_admin_panel():
    if not st.session_state.get('auth'):
        st.header("Panel de Control Docente", divider=True)
        pwd = st.text_input("Contraseña de Administrador", type="password")
        if st.button("Acceder", type="primary"):
            try:
                if pwd == st.secrets["ADMIN_PASSWORD"]:
                    st.session_state['auth'] = True
                    st.rerun()
                else:
                    st.toast("Contraseña incorrecta", icon="❌")
            except KeyError:
                st.error("Error: Configure ADMIN_PASSWORD en st.secrets")
        return

    # 2. MENU LATERAL (Sidebar) - Solo visible cuando es admin
    with st.sidebar:
        st.header("Panel de Control", divider=True)
        st.caption("Modo Administrador Activo (Hora VE)")
        
        if st.button("Cerrar Sesión"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # --- AHORA SON 3 PESTAÑAS ---
    tab_dashboard, tab_grades, tab_editor, tab_solver = st.tabs(["Dashboard", "Registro de calificaciones", "Editor de evaluaciones", " Respuestas"])
    #tab_dashboard, tab_grades, tab_editor = st.tabs(["Dashboard Docente", "Libro de Notas", "Gestión de Exámenes"])

    # --------------------------------------------------------------------------
    # PESTAÑA 1: EDITOR
    # --------------------------------------------------------------------------
    with tab_editor:
        exam_ids = db_manager.get_exam_list()
        options = ["➕ Crear Nuevo..."] + exam_ids
        
        selection = st.selectbox("Seleccionar Examen", options)
        
        if st.session_state.get('last_selection') != selection:
            if selection == "➕ Crear Nuevo...":
                st.session_state['editor_area'] = DEFAULT_TEMPLATE
                st.session_state['current_exam_id'] = ""
            else:
                code_from_db = db_manager.get_exam_code(selection)
                st.session_state['editor_area'] = code_from_db
                st.session_state['current_exam_id'] = selection
            
            st.session_state['last_selection'] = selection

        if selection == "➕ Crear Nuevo...":
            exam_id_input = st.text_input("ID del Examen (ej: ex1-mn-sec-A-2026A)", value=st.session_state.get('current_exam_id', ""))
            st.session_state['current_exam_id'] = exam_id_input
        else:
            exam_id_input = selection
            st.info(f"Editando examen: **{exam_id_input}**")
            
        new_code = st.text_area("Código Python", height=450, key="editor_area")

        

        c1, c2, c3 = st.columns([1, 1, 2])
        
        with c1:
            if st.button("Guardar", type="primary"):
                target_id = st.session_state.get('current_exam_id', "").strip()
                if not target_id:
                    st.error("Debe ingresar un ID para el examen")
                else:
                    db_manager.save_exam(target_id, new_code)
                    st.success(f"¡Examen '{target_id}' guardado!")
                    st.session_state['last_selection'] = target_id
                    st.rerun()

        with c2:
            if selection != "➕ Crear Nuevo...":
                if st.button("Eliminar"):
                    db_manager.delete_exam(selection)
                    st.toast("Examen eliminado")
                    st.session_state['last_selection'] = None
                    st.rerun()
        
        with c3:
            if selection != "➕ Crear Nuevo...":
                link = f"/?eval={selection}"
                st.code(link, language="text")
                st.link_button("Previsualizar Examen", link)

    # --------------------------------------------------------------------------
    # PESTAÑA 2: TABLA DE NOTAS
    # --------------------------------------------------------------------------
    with tab_grades:
        
        @st.fragment
        def render_grades_table():
            # 1. Cargar datos
            df = db_manager.get_all_grades()
            
            # 2. Preparar el CSV con la data completa antes de renderizar botones
            # (Nota: Descarga la data completa, independiente del filtro visual)
            csv_data = df.to_csv(index=False).encode('utf-8') if not df.empty else None

            # 3. Layout de 3 columnas: [Refrescar] [CSV] [Filtro]
            # Ajustamos los anchos: Botón texto (1.5), Botón icono (0.5), Filtro (4)
            c_refresh, c_csv, c_filter = st.columns([1.4, 0.6, 4], vertical_alignment="top")
            
            with c_refresh:
                st.button("Refrescar Tabla", use_container_width=True)
            
            with c_csv:
                if csv_data:
                    st.download_button(
                        label="📥",
                        data=csv_data,
                        file_name="notas_ve.csv",
                        mime="text/csv",
                        help="Descargar todo en CSV",
                        use_container_width=True
                    )
            
            with c_filter:
                if not df.empty:
                    filtro_exam = st.multiselect(
                        "Filtrar por Examen", 
                        df['exam_id'].unique(), 
                        label_visibility="collapsed", 
                        placeholder="Filtrar por examen..."
                    )
                else:
                    filtro_exam = []

            # 4. Renderizado de la tabla
            if not df.empty:
                # Aplicamos el filtro solo visualmente a la tabla
                if filtro_exam:
                    df = df[df['exam_id'].isin(filtro_exam)]
                
                st.dataframe(
                    df, 
                    width='stretch',
                    column_config={
                        "is_correct": st.column_config.CheckboxColumn("Aprobado"),
                        "score": st.column_config.ProgressColumn("Nota", min_value=0, max_value=20, format="%.2f"),
                        "last_updated": st.column_config.DatetimeColumn("Fecha (VE)", format="DD/MM HH:mm")
                    }
                )
            else:
                st.info("No hay registros aún.")

        # Llamamos a la función decorada
        render_grades_table()

    # --------------------------------------------------------------------------
    # PESTAÑA 3: DASHBOARD DOCENTE (NUEVO)
    # --------------------------------------------------------------------------
    with tab_dashboard:
        
        @st.fragment
        def render_dashboard_content():
            # 1. Cargar datos PRIMERO para poder llenar el selector
            df = db_manager.get_all_grades()
            
            if df.empty:
                st.info("No hay suficientes datos para mostrar el dashboard.")
                if st.button("Reintentar"): st.rerun()
                return 

            # 2. Configuración del Header (Botón + Selector en la misma fila)
            # Usamos vertical_alignment="bottom" para alinear el botón con el input
            c_btn, c_sel = st.columns([1, 3], vertical_alignment="bottom")

            with c_btn:
                if st.button("Actualizar métricas"):
                    pass 

            with c_sel:
                lista_examenes = list(df['exam_id'].unique())
                seleccion_dash = st.multiselect(
                    "Filtrar Dashboard", 
                    lista_examenes,
                    default=None,
                    placeholder="Seleccionar Exámenes para Análisis...",
                    label_visibility="collapsed"  # Ocultamos la etiqueta para que quede limpio
                )
            
            #st.divider() 
            
            # --- LÓGICA DE FILTRADO ---
            if seleccion_dash:
                df_view = df[df['exam_id'].isin(seleccion_dash)].copy()
            else:
                df_view = df.copy()

            # Asegurar tipos de datos para cálculos
            df_view['score'] = pd.to_numeric(df_view['score'])
            df_view['attempts'] = pd.to_numeric(df_view['attempts'])
            df_view['last_updated'] = pd.to_datetime(df_view['last_updated'])

            # --- 1. CÁLCULOS DE POBLACIÓN (Set Theory) ---
            set_todos = set(df_view['student_id'])
            set_aprobados = set(df_view[df_view['is_correct'] == True]['student_id'])
            set_sin_aprobar = set_todos - set_aprobados
            
            total_unicos = len(set_todos)
            total_sin_aprobar = len(set_sin_aprobar)
            total_registros = len(df_view)

            # --- 2. CÁLCULOS DE RENDIMIENTO ---
            df_aprobados = df_view[df_view['is_correct'] == True]
            
            if not df_aprobados.empty:
                promedio_nota = df_aprobados['score'].mean()
                promedio_intentos = df_aprobados['attempts'].mean()
            else:
                promedio_nota = 0
                promedio_intentos = 0
            
            tasa_exito_real = (len(set_aprobados) / total_unicos) if total_unicos > 0 else 0

            # --- VISUALIZACIÓN DE KPIs ---
            c1, c2 = st.columns(2)
            c1.metric("Total Estudiantes Únicos", total_unicos, delta=f"{total_registros} registros totales", delta_color="off", border=True)
            c2.metric("Estudiantes Sin Aprobar", total_sin_aprobar, delta=f"{len(set_aprobados)} ya aprobaron", border=True)
            
            st.write("") # Espaciador

            c3, c4, c5 = st.columns(3)
            c3.metric("% Aprobación Real", f"{tasa_exito_real:.1%}", border=True)
            c4.metric("Nota Promedio", f"{promedio_nota:.2f} pts", border=True)
            c5.metric("Intentos Promedio", f"{promedio_intentos:.1f}", border=True)

            #st.divider()

            # --- GRÁFICOS ---
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.markdown("**Distribución de Notas (Aprobados)**")
                if not df_aprobados.empty:
                    notas_redondeadas = df_aprobados['score'].round(0).astype(int)
                    conteo_notas = notas_redondeadas.value_counts().sort_index()
                    st.bar_chart(conteo_notas, color="#4CAF50")
                else:
                    st.caption("Sin datos.")

            with col_g2:
                st.markdown("**Actividad Reciente**")
                if not df_view.empty:
                    df_view['fecha_dia'] = df_view['last_updated'].dt.date
                    actividad = df_view.groupby('fecha_dia').size()
                    st.line_chart(actividad)

        # Ejecutamos la función decorada
        render_dashboard_content()
            
    # --------------------------------------------------------------------------
    # PESTAÑA 4: RESPUESTAS (NUEVA FUNCIONALIDAD)
    # --------------------------------------------------------------------------
    with tab_solver:
        
        @st.fragment
        def render_solver_content():
            st.subheader("Simulador de Soluciones", divider=True)
            st.info("Esta herramienta revela todas las variables generadas por el examen para una cédula específica.")
            
            c_sol1, c_sol2 = st.columns(2)
            
            with c_sol1:
                # Al cambiar el examen, solo recarga este fragmento
                exam_to_solve = st.selectbox("Elegir Examen", db_manager.get_exam_list(), key="solver_select")
            
            with c_sol2:
                # Al escribir la cédula, solo recarga este fragmento
                student_target = st.text_input("Cédula / ID Estudiante", key="solver_input")
                
            if st.button("🔍 Calcular Solución", type="primary"):
                if not exam_to_solve or not student_target:
                    st.error("Seleccione un examen e ingrese una cédula.")
                    return # Salimos de la función sin error global

                raw_code = db_manager.get_exam_code(exam_to_solve)
                
                if not raw_code:
                    st.error("El código del examen está vacío.")
                else:
                    # 1. Sanitización (Quitar imports de streamlit)
                    lines = raw_code.split('\n')
                    safe_lines = [
                        line for line in lines 
                        if not line.strip().startswith("import streamlit") 
                        and not line.strip().startswith("from streamlit")
                    ]
                    cleaned_code = "\n".join(safe_lines)

                    # 2. Preparar entorno (Simulamos ST y DB)
                    silent_st = SilentStreamlit(student_target)
                    mock_db = MockDB()
                    
                    # Contexto inicial (variables que inyectamos nosotros)
                    base_context_keys = {
                        'st', 'pd', 'np', 'random', 'db', 'EXAM_ID', 'datetime', 
                        'is_admin', '__builtins__'
                    }
                    
                    context_solver = {
                        'st': silent_st,
                        'pd': pd,
                        'np': np,
                        'random': random,
                        'db': mock_db,
                        'EXAM_ID': exam_to_solve,
                        'datetime': datetime,
                        'is_admin': True
                    }
                    
                    try:
                        # 3. Ejecutar
                        exec(cleaned_code, context_solver)
                        
                        st.divider()
                        st.markdown(f"#### Variables encontradas para: `{student_target}`")
                        
                        # 4. Busqueda Prioritaria (Variables de respuesta común)
                        priority_vars = ['solucion', 'solution', 'respuesta', 'result', 'answer']
                        found_priority = False
                        
                        for var in priority_vars:
                            if var in context_solver:
                                val = context_solver[var]
                                st.success(f"🎯 **{var}**: {val}")
                                found_priority = True
                        
                        if not found_priority:
                            st.caption("Mostrando todas las variables generadas:")

                        # 5. Filtrado Inteligente de Variables (Muestra TODO lo que no sea basura)
                        results_found = {}
                        for k, v in context_solver.items():
                            # Ignorar variables internas (_) o las que inyectamos nosotros
                            if k.startswith('_') or k in base_context_keys:
                                continue
                            
                            # Ignorar Módulos, Funciones y Clases (solo queremos datos)
                            if isinstance(v, (types.ModuleType, types.FunctionType, type)):
                                continue
                                
                            results_found[k] = v

                        # Mostrar resultado limpio en JSON/Diccionario
                        if results_found:
                            st.json(results_found)
                        else:
                            st.warning("El script se ejecutó pero no generó variables nuevas visibles.")
                            
                    except Exception as e:
                        st.error("Error ejecutando la simulación:")
                        st.error(str(e))
                        with st.expander("Ver código ejecutado"):
                            st.code(cleaned_code)

        # Ejecutar el fragmento
        render_solver_content()
                        

# ==============================================================================
# 4. ENRUTADOR PRINCIPAL
# ==============================================================================
def main():
    query_params = st.query_params
    exam_id = query_params.get("eval")

    if exam_id:
        execute_exam(exam_id)
    else:
        render_admin_panel()

if __name__ == "__main__":
    main()
    
