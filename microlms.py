import streamlit as st
import libsql_experimental as libsql
import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta, timezone  # <--- SE AGREGARON LIBRERÍAS DE TIEMPO
import types
import scipy

# ==============================================================================
# 1. CONFIGURACIÓN Y ESTILOS
# ==============================================================================
#st.set_page_config(layout="wide", page_title="Plataforma de Evaluación", page_icon="🎓")
st.set_page_config(layout="centered", page_title="Plataforma de Evaluación", page_icon="🎓")

ST_STYLE = """
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stApp { background-color: #ffffff; color: #111111; }
    
    /* --- ESTILO TIPO IDE PARA EL TEXTAREA --- */
    div[data-testid="stTextArea"] textarea { 
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important; 
        font-size: 12px !important;  /* Fuente más pequeña */
        line-height: 1.5 !important;
        background-color: #1e1e1e !important; /* Fondo oscuro tipo VS Code */
        color: #d4d4d4 !important; /* Texto claro */
    }
    
    .stButton>button { border-radius: 4px; border: 1px solid #ccc; width: 100%; }
    .stButton>button:hover { border-color: #333; color: #333; }
    
    section[data-testid="stSidebar"] {
            width: 440px !important; # Set the width to your desired value            
        }
        
    .block-container {
        max-width: 800px !important; /* <--- AJUSTA ESTE VALOR (ej. 800px, 1000px, 60%) */
        padding-top: 3rem !important;
        padding-bottom: 3rem !important;
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

# Función auxiliar para chequear si la conexión sigue viva
def is_connection_active(conn):
    try:
        # Intentamos una consulta ultra-rápida
        conn.execute("SELECT 1")
        return True
    except Exception:
        # Si falla (por stream not found u otro), devolvemos False
        return False

# Usamos validate en lugar de (o junto con) ttl
@st.cache_resource(validate=is_connection_active)
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
            student_name TEXT,
            student_list_n INTEGER,
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
    # Índices para optimizar búsquedas frecuentes
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_exam_correct 
        ON grades(exam_id, is_correct)
    """)
    conn.commit()
    # -----------------------------------------------------------------------------
    
    return conn

@st.cache_data(ttl=60)  # <--- Cachear por 1 minuto
def get_cached_all_grades():
    # Usamos el manager global
    return db_manager.get_all_grades()

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

    def register_attempt(self, exam_id: str, student_id: str, is_correct: bool, score_func=None, **kwargs):
        conn = self._get_conn()
        
        # --- NUEVAS VARIABLES EXTRAÍDAS ---
        student_name = kwargs.get('student_name', 'N/A')
        student_list_n = kwargs.get('student_list_n', 0)
        
        # 1. Fallos previos
        res_fail = conn.execute("SELECT attempts FROM grades WHERE exam_id=? AND student_id=?", (exam_id, student_id)).fetchone()
        prev_failures = res_fail[0] if res_fail else 0
        
        # 2. Factor Z (Aprobados globales)
        res_pass = conn.execute("SELECT COUNT(*) FROM grades WHERE exam_id=? AND is_correct=1", (exam_id,)).fetchone()
        passed_count = res_pass[0] if res_pass else 0
        
        # 3. Cálculo de Nota
        score = 0
        if is_correct:
            # --- LÓGICA DE APROBADOS (10 a 20 pts) ---
            if score_func:
                try:
                    score = score_func(prev_failures, passed_count)
                except TypeError:
                    score = score_func(prev_failures)
            else:
                MATRICULA_ESTIMADA = 25 
                posicion = passed_count / MATRICULA_ESTIMADA
                
                if posicion <= 0.15:    # Top 15% 
                    nota_base = 20.0
                elif posicion <= 0.35:  # Siguiente 20%
                    nota_base = 18.0
                elif posicion <= 0.80:  # El grueso del grupo
                    nota_base = 15.0
                else:                   # Rezagados
                    nota_base = 12.0
                    
                castigo_error = prev_failures * 0.25
                score = max(10.0, min(nota_base - castigo_error, 20.0)) 
        else:
            # --- LÓGICA: Campana de Gauss (0 a 9 pts) para reprobados ---
            rng = random.Random(student_id)
            mu = 4.5      
            sigma = 2.0   
            nota_reprobado = rng.gauss(mu, sigma)
            score = max(0.0, min(9.0, nota_reprobado))
            
        # 4. Upsert con HORA VENEZUELA y Lógica de Preservación
        increment = 0 if is_correct else 1
        current_time_ve = self._get_ve_time() 
        
        conn.execute("""
            INSERT INTO grades (exam_id, student_id, attempts, is_correct, score, last_updated, student_name, student_list_n)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(exam_id, student_id) DO UPDATE SET
                attempts = attempts + excluded.attempts,
                
                -- Si ya aprobó alguna vez, se queda aprobado (MAX)
                is_correct = MAX(grades.is_correct, excluded.is_correct),
                
                score = CASE 
                    WHEN excluded.is_correct THEN excluded.score  -- Nuevo aprobado: Actualizar nota
                    WHEN grades.is_correct THEN grades.score      -- Ya aprobado antes: Mantener nota
                    ELSE excluded.score                           -- Reprobado: Guardar nota Gaussiana (0-9)
                END,
                
                last_updated = excluded.last_updated,
                
                -- Actualizamos el nombre y el nro de lista siempre a su última versión
                student_name = excluded.student_name,
                student_list_n = excluded.student_list_n
        """, (exam_id, student_id, increment, is_correct, score, current_time_ve, student_name, student_list_n))
        conn.commit()
        
        return prev_failures + increment, score

    def get_all_grades(self):
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM grades ORDER BY last_updated DESC")
        cols = [d[0] for d in cursor.description]
        return pd.DataFrame(cursor.fetchall(), columns=cols)

    def get_leaderboard_data(self, exam_id: str):
        conn = self._get_conn()
        # SQL hace el filtrado y ordenamiento directamente
        cursor = conn.execute("""
            SELECT student_id, score, attempts, last_updated 
            FROM grades 
            WHERE exam_id=? AND is_correct=1 
            ORDER BY score DESC, last_updated ASC
        """, (exam_id,))
        
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

# --- INICIO NUEVO BLOQUE DE CACHÉ ---
@st.cache_data(show_spinner=False, ttl=300) 
def get_cached_exam_code(exam_id):
    """
    Recupera el código del examen y lo guarda en memoria por 5 minutos (300 seg).
    Si 30 estudiantes entran a la vez, solo la primera petición va a la BD.
    Las otras 29 se sirven instantáneamente desde la RAM.
    """
    return db_manager.get_exam_code(exam_id)
# --- FIN NUEVO BLOQUE DE CACHÉ ---

# ==============================================================================
# 3. LÓGICA DE INTERFAZ (Admin vs Estudiante)
# ==============================================================================

def execute_exam(exam_id):
    """Carga el código desde BD y lo ejecuta en un entorno seguro"""
    source_code = get_cached_exam_code(exam_id)
    #source_code = db_manager.get_exam_code(exam_id)
    
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

# ==============================================================================
# REEMPLAZAR LA CLASE SilentStreamlit ANTIGUA POR ESTA VERSIÓN MEJORADA
# ==============================================================================

# ==============================================================================
# CLASE MOCK SESSION STATE (Para soportar notación de punto .clave)
# ==============================================================================
class MockSessionState(dict):
    """
    Simula el comportamiento híbrido de st.session_state:
    Funciona como diccionario (state['key']) y como objeto (state.key).
    """
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"'MockSessionState' object has no attribute '{key}'")

    def __setattr__(self, key, value):
        self[key] = value

# ==============================================================================
# REEMPLAZAR LA CLASE SilentStreamlit POR ESTA VERSIÓN CORREGIDA
# ==============================================================================

class SilentStreamlit:
    """
    Simula ser 'st' para ejecutar el examen sin interfaz gráfica.
    Devuelve tipos de datos compatibles para evitar TypeErrors durante la simulación.
    """
    def __init__(self, fixed_input):
        self.fixed_input = str(fixed_input)
        self.secrets = st.secrets
        
        # --- CORRECCIÓN CLAVE AQUÍ ---
        # 1. Usamos MockSessionState en vez de un dict normal para permitir .user_session
        self.session_state = MockSessionState()
        
        # 2. INYECCIÓN DE SESIÓN:
        # Pre-llenamos los datos para que la Plantilla v9 crea que ya estamos logueados.
        # Esto evita que el script se detenga en la pantalla de login.
        self.session_state.user_session = {
            "verified": True,
            "id": self.fixed_input,
            "section": "ACADEMIA TEC" # Sección por defecto para simulaciones
        }
        
    # --- PROPIEDADES DE LAYOUT ---
    @property
    def sidebar(self):
        return self
        
    def container(self, **kwargs):
        return self

    def columns(self, spec, **kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [self] * count
        
    def tabs(self, tabs_list, **kwargs):
        return [self] * len(tabs_list)
        
    def expander(self, label, **kwargs):
        return self
        
    def form(self, key, **kwargs):
        return self

    # --- WIDGETS DE ENTRADA (Manejo de Tipos de Datos) ---

    def text_input(self, label, **kwargs):
        # Si el label sugiere que es el ID, devolvemos el ID fijo.
        label_lower = label.lower()
        if "id" in label_lower or "cédula" in label_lower or "cedula" in label_lower:
            return self.fixed_input
        # Si pide nombre para el badge, devolvemos un nombre falso
        if "nombre" in label_lower:
            return "Estudiante Simulado"
        return "dummy_text"
    
    def number_input(self, label, **kwargs):
        return 1.0 
    
    def slider(self, label, min_value=0, max_value=100, **kwargs):
        return min_value

    def radio(self, label, options, **kwargs):
        return options[0] if options else None

    def selectbox(self, label, options, **kwargs):
        return options[0] if options else None
        
    def multiselect(self, label, options, **kwargs):
        return [options[0]] if options else []

    def checkbox(self, label, **kwargs):
        return False
        
    def button(self, label, **kwargs):
        # Importante: devolver False para botones de acción (como Login o Emitir Badge)
        # para que no intenten ejecutar lógica externa, EXCEPTO si es form_submit
        return False 

    def date_input(self, label, **kwargs):
        from datetime import date
        return date.today()

    def time_input(self, label, **kwargs):
        from datetime import datetime
        return datetime.now().time()
        
    def file_uploader(self, label, **kwargs):
        return None
        
    def form_submit_button(self, label="Submit", **kwargs):
        # Simulamos que el botón de enviar respuesta SIEMPRE se presiona
        # para forzar el cálculo de validación
        return True
        
    # --- MÉTODOS DE SALIDA (No hacen nada) ---
    def markdown(self, *args, **kwargs): pass
    def title(self, *args, **kwargs): pass
    def header(self, *args, **kwargs): pass
    def subheader(self, *args, **kwargs): pass
    def caption(self, *args, **kwargs): pass
    def code(self, *args, **kwargs): pass
    def write(self, *args, **kwargs): pass
    def info(self, *args, **kwargs): pass
    def success(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass
    def json(self, *args, **kwargs): pass
    def metric(self, *args, **kwargs): pass
    def toast(self, *args, **kwargs): pass
    def balloons(self, *args, **kwargs): pass
    def spinner(self, *args, **kwargs): return self 
    def link_button(self, *args, **kwargs): pass

    # --- CONTROL DE FLUJO ---
    def stop(self):
        # Ignoramos stop() para que el script siga corriendo y revele las variables
        pass
    
    def rerun(self):
        pass
    
    # --- CONTEXT MANAGERS ---
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def __iter__(self):
        yield self

    def __getattr__(self, name):
        # Catch-all para cualquier cosa que se nos haya olvidado
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
        
        # --- CAMBIO: Definimos 2 columnas (proporción 1 a 2) ---
        col_sel, col_inp = st.columns([4, 5], vertical_alignment="bottom")
        
        with col_sel:
            selection = st.selectbox("Seleccionar Examen", options)
        
        # Lógica de actualización de estado (se mantiene igual, pero fuera de las cols visuales)
        if st.session_state.get('last_selection') != selection:
            if selection == "➕ Crear Nuevo...":
                st.session_state['editor_area'] = DEFAULT_TEMPLATE
                st.session_state['current_exam_id'] = ""
            else:
                code_from_db = db_manager.get_exam_code(selection)
                st.session_state['editor_area'] = code_from_db
                st.session_state['current_exam_id'] = selection
            
            st.session_state['last_selection'] = selection

        with col_inp:
            if selection == "➕ Crear Nuevo...":
                exam_id_input = st.text_input("ID del Examen (ej: ex1-mn-sec-A-2026A)", value=st.session_state.get('current_exam_id', ""))
                st.session_state['current_exam_id'] = exam_id_input
            else:
                exam_id_input = selection
                st.info(f"Editando examen: **{exam_id_input}**")
            
        new_code = st.text_area("Código Python", height=350, key="editor_area")

        

        c1, c2, c3, c4 = st.columns([2, 2, 4, 2])
        
        with c1:
            if st.button("Guardar", type="primary"):
                target_id = st.session_state.get('current_exam_id', "").strip()
                if not target_id:
                    st.error("Debe ingresar un ID para el examen")
                else:
                    db_manager.save_exam(target_id, new_code)
                    get_cached_exam_code.clear() 
                    st.success(f"¡Examen '{target_id}' guardado!")
                    st.session_state['last_selection'] = target_id
                    st.rerun()

        with c2:
            if selection != "➕ Crear Nuevo...":
                # --- MODIFICACIÓN: Confirmación con Popover ---
                with st.popover("Eliminar", help="Borrar este examen permanentemente"):
                    st.markdown(f"¿Estás seguro de borrar **{selection}**?")
                    st.warning("Esta acción no se puede deshacer.")
                    
                    if st.button("Sí, borrar definitivamente", type="primary"):
                        db_manager.delete_exam(selection)
                        st.toast(f"Examen '{selection}' eliminado correctamente", icon="🗑️")
                        st.session_state['last_selection'] = None
                        st.rerun()
        
        with c3:
            if selection != "➕ Crear Nuevo...":
                link = f"/?eval={selection}"
                #st.code(link, language="text")
                st.link_button("Previsualizar Examen", link)
                
        with c4:
            if selection != "➕ Crear Nuevo...":
                link_rank = f"/?ranking={selection}"
                st.link_button("Ranking", link_rank, type="secondary")

    # --------------------------------------------------------------------------
    # PESTAÑA 2: TABLA DE NOTAS
    # --------------------------------------------------------------------------
    with tab_grades:    
        
        # 1. Función auxiliar cacheada para el CSV
        @st.cache_data(show_spinner=False)
        def convert_df_to_csv(dataframe):
            return dataframe.to_csv(index=False).encode('utf-8')            
        
        @st.fragment
        def render_grades_table():
            # 1. Cargar datos
            df = get_cached_all_grades()
            
            # 2. Preparar el CSV con la data completa antes de renderizar botones
            # 2. Generar CSV de forma inteligente (Solo recalcula si el df cambió)
            csv_data = convert_df_to_csv(df) if not df.empty else None
            #csv_data = df.to_csv(index=False).encode('utf-8') if not df.empty else None

            # 3. Layout de 4 columnas: [Refrescar] [CSV] [Filtro Examen] [Filtro Cédula] <--- CAMBIO AQUÍ
            c_refresh, c_csv, c_filter_exam, c_filter_id = st.columns([1.2, 0.6, 2.1, 2.1], vertical_alignment="top")
            
            with c_refresh:
                st.button("Refrescar Tabla", width="stretch")
            
            with c_csv:
                if csv_data:
                    st.download_button(
                        label="📥",
                        data=csv_data,
                        file_name="notas_ve.csv",
                        mime="text/csv",
                        help="Descargar todo en CSV",
                        width="stretch"
                    )
            
            with c_filter_exam:
                if not df.empty:
                    filtro_exam = st.multiselect(
                        "Filtrar por Examen", 
                        df['exam_id'].unique(), 
                        label_visibility="collapsed", 
                        placeholder="Filtrar por examen..."
                    )
                else:
                    filtro_exam = []

            # --- NUEVO BLOQUE PARA CÉDULA ---
            with c_filter_id:
                filtro_cedula = st.text_input(
                    "Filtrar por Cédula", 
                    placeholder="🔍 Buscar Cédula...", 
                    label_visibility="collapsed"
                )
            # --------------------------------

            # 4. Renderizado de la tabla
            if not df.empty:
                # Aplicamos filtro de EXAMEN
                if filtro_exam:
                    df = df[df['exam_id'].isin(filtro_exam)]
                
                # --- APLICAMOS FILTRO DE CÉDULA ---
                if filtro_cedula:
                    # Convierte a string y busca coincidencia parcial (case insensitive)
                    df = df[df['student_id'].astype(str).str.contains(filtro_cedula, case=False, na=False)]
                # ----------------------------------
                
                st.dataframe(
                    df, 
                    width='stretch',
                    column_config={
                        "is_correct": st.column_config.CheckboxColumn("Aprobado", width="content"),
                        "score": st.column_config.ProgressColumn("Nota", min_value=0, max_value=20, format="%.2f", width="content"),
                        "last_updated": st.column_config.DatetimeColumn("Fecha (VE)", format="DD/MM/YYYY hh:mm a", width="content")
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
            df = get_cached_all_grades()
            
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
            
            # A. Promedio Global (Toda la sección, incluyendo reprobados gauss)
            if not df_view.empty:
                promedio_global = df_view['score'].mean()
            else:
                promedio_global = 0

            # B. Promedio solo de los que aprobaron (Para comparar)
            if not df_aprobados.empty:
                promedio_aprobados = df_aprobados['score'].mean()
                promedio_intentos = df_aprobados['attempts'].mean() # Intentos hasta lograr el éxito
            else:
                promedio_aprobados = 0
                promedio_intentos = 0
            
            tasa_exito_real = (len(set_aprobados) / total_unicos) if total_unicos > 0 else 0

            # --- VISUALIZACIÓN DE KPIs ---
            # ==================================================================
            
            subtab_kpi, subtab_graphs, subtab_report = st.tabs(["📊 Métricas Clave", "📈 Gráficas Detalladas", "Informe de Resultados"])

            # --- SUBPESTAÑA 1: KPIs ---
            with subtab_kpi:
                #st.write("") # Espaciador
                c1, c2 = st.columns(2)
                c1.metric("Total Estudiantes Únicos", total_unicos, delta=f"{total_registros} registros totales", delta_color="off", border=True)
                c2.metric("Estudiantes Sin Aprobar", total_sin_aprobar, delta=f"{len(set_aprobados)} ya aprobaron", border=True)
                
                # st.write("") # Espaciador

                c3, c4, c5, c6 = st.columns(4)
                
                # METRICA 1: % Aprobación
                # Delta: Cantidad física de estudiantes que faltan.
                # Lógica: Si el % es bajo, el delta te dice exactamente cuánto trabajo falta.
                c3.metric(
                    "% Aprobación Real", 
                    f"{tasa_exito_real:.1%}", 
                    delta=f"{total_sin_aprobar} pendientes",
                    delta_color="off", # Gris neutro (informativo)
                    border=True
                )
                
                # METRICA 2: Nota Promedio (Ya la habíamos ajustado)
                c4.metric(
                    "Nota Promedio Global", 
                    f"{promedio_global:.2f} pts", 
                    delta=f"Aprobados: {promedio_aprobados:.2f}",
                    delta_color="off",
                    border=True
                )
                
                # METRICA 3: Intentos Promedio
                # Delta: Diferencia contra el ideal (1 intento).
                # Lógica: Si el promedio es 3.5, el delta será "+2.5 vs Ideal". 
                # Color "inverse": Si el número sube (es positivo), se pone rojo (malo).
                diff_ideal = promedio_intentos - 1.0
                c5.metric(
                    "Intentos Promedio", 
                    f"{promedio_intentos:.1f}", 
                    delta=f"+{diff_ideal:.1f} vs Ideal",
                    delta_color="inverse", # Rojo si es positivo (más intentos es "peor")
                    border=True
                )
                
                # Calcular Eficiencia Global
                # Suma total de puntos del salón / Suma total de intentos del salón
                total_puntos = df_view['score'].sum()
                total_intentos = df_view['attempts'].sum()
                
                if total_intentos > 0:
                    eficiencia = total_puntos / total_intentos
                else:
                    eficiencia = 0

                # Visualizar (Asumiendo que creas una columna c6 o usas una existente)
                BASE_CALIDAD = 10.0 
                diff_eficiencia = eficiencia - BASE_CALIDAD

                # Asumiendo que has creado la columna c6, o la agregas en una nueva fila
                # c3, c4, c5, c6 = st.columns(4) <--- Asegúrate de cambiar esto arriba
                
                c6.metric(
                    "Eficiencia", 
                    f"{eficiencia:.1f}", 
                    delta=f"{diff_eficiencia:+.1f} vs Base (10)",
                    delta_color="normal", # Verde si es > 10, Rojo si es < 10
                    help="Indica cuántos puntos reales gana el salón por cada clic/intento gastado. Menos de 10 indica mucha adivinanza.", border=True
                )

            # --- SUBPESTAÑA 2: GRÁFICOS ---
            with subtab_graphs:
                # st.write("") # Espaciador
                col_g1, col_g2 = st.columns(2)
                
                with col_g1:
                    st.markdown("**Distribución Global de Notas (0 - 20)**")
                    if not df_view.empty:
                        # 1. Crear estructura base (Eje X de 0 a 20)
                        chart_data = pd.DataFrame(index=range(21))
                        
                        # 2. Separar notas y redondear
                        # Notas < 9.5 se consideran reprobadas (columna 0-9)
                        notas_reprobados = df_view[df_view['score'] < 9.5]['score'].round(0).astype(int)
                        # Notas >= 9.5 se consideran aprobadas (columna 10-20)
                        notas_aprobados = df_view[df_view['score'] >= 9.5]['score'].round(0).astype(int)
                        
                        # 3. Llenar conteos
                        chart_data['Reprobados'] = notas_reprobados.value_counts()
                        chart_data['Aprobados'] = notas_aprobados.value_counts()
                        
                        # Rellenar con 0 donde no haya estudiantes (limpieza visual)
                        chart_data = chart_data.fillna(0)
                        
                        # 4. Graficar con colores semánticos
                        # Color 1 (Reprobados): Rojo suave (#FF4B4B)
                        # Color 2 (Aprobados): Verde éxito (#4CAF50)
                        st.bar_chart(chart_data, color=["#FF4B4B", "#4CAF50"], stack=True)
                        
                        # Datos extra textuales
                        min_nota = df_view['score'].min()
                        max_nota = df_view['score'].max()
                        st.caption(f"Rango de notas registrado: {min_nota:.1f} - {max_nota:.1f}")
                    else:
                        st.caption("Sin datos para mostrar.")

                with col_g2:
                    st.markdown("**Actividad Reciente**")
                    if not df_view.empty:
                        df_view['fecha_dia'] = df_view['last_updated'].dt.date
                        actividad = df_view.groupby('fecha_dia').size()
                        st.line_chart(actividad)
                        
                #st.write("") # Espaciador vertical
                st.subheader("Análisis de Comportamiento (Esfuerzo vs. Nota)", divider=True)
                
                if not df_view.empty:
                    import altair as alt # Asegúrate de que esto no de error, st ya lo trae
                    
                    # Preparamos los datos para que el gráfico se vea lindo
                    # Creamos una columna de "Estado" para el color
                    df_chart = df_view.copy()
                    df_chart['Estado'] = df_chart['is_correct'].apply(lambda x: "Aprobado" if x else "Reprobado")
                    
                    # Definimos el Gráfico
                    chart = alt.Chart(df_chart).mark_circle(size=200).encode(
                        # Eje X: Intentos
                        x=alt.X('attempts', title='Cantidad de Intentos'),
                        
                        # Eje Y: Nota
                        y=alt.Y('score', title='Nota Obtenida', scale=alt.Scale(domain=[0, 20])),
                        
                        # Color según si aprobó o no
                        color=alt.Color('Estado', scale=alt.Scale(domain=['Aprobado', 'Reprobado'], range=['#4CAF50', '#FF4B4B'])),
                        
                        # TOOLTIP: ¡Esto es lo mejor! Al pasar el mouse ves quién es
                        tooltip=[
                            alt.Tooltip('student_id', title='Cédula'),
                            alt.Tooltip('score', title='Nota', format='.2f'),
                            alt.Tooltip('attempts', title='Intentos'),
                            alt.Tooltip('last_updated', title='Último Acceso', format='%d/%m %H:%M')
                        ]
                    ) # Permite hacer zoom y pan
                    
                    st.altair_chart(chart, width="stretch")
                    
                    st.info("""
                    **Cómo leer esta gráfica:**
                    - 🟢 **Arriba a la Izquierda:** (Pocos intentos, Nota alta) → **Estudiantes Excelentes**.
                    - 🟢 **Arriba a la Derecha:** (Muchos intentos, Nota alta) → **Persistentes / Fuerza Bruta**.
                    - 🟢 **Abajo a la Derecha:** (Muchos intentos, Nota baja) → **Estudiantes Frustrados (Ayudar urgente)**.
                    """)
                    
            with subtab_report:
                #st.write(" ")
                st.subheader("Diagnóstico Automático del Curso", divider=True)
                
                if df_view.empty:
                    st.info("No hay datos suficientes para generar el informe.")
                else:
                    # --- 1. CÁLCULOS INTERNOS PARA EL INFORME ---
                    # Recalculamos eficiencia localmente por si acaso
                    sum_score = df_view['score'].sum()
                    sum_try = df_view['attempts'].sum()
                    eff_report = (sum_score / sum_try) if sum_try > 0 else 0
                    
                    # Segmentación de Estudiantes
                    # A. LUCHADORES: Reprobados con muchos intentos (> 3) -> Necesitan ayuda
                    struggling = df_view[(df_view['score'] < 9.5) & (df_view['attempts'] > 3)]
                    
                    # B. ADIVINADORES: Aprobados pero con eficiencia baja (> 4 intentos) -> Fuerza bruta
                    guessers = df_view[(df_view['score'] >= 9.5) & (df_view['attempts'] > 4)]
                    
                    # C. ÉLITE: Aprobados con nota excelente (>=19) en 1 intento -> Eximibles/Monitores
                    elite = df_view[(df_view['score'] >= 19.0) & (df_view['attempts'] == 1)]

                    # --- 2. GENERACIÓN DEL TEXTO ---
                    
                    # A. ESTADO DE SALUD DEL EXAMEN
                    if tasa_exito_real >= 0.80:
                        estado = "🟢 ÓPTIMO"
                        msg_estado = "La gran mayoría del curso ha dominado el tema."
                    elif tasa_exito_real >= 0.50:
                        estado = "🟡 REGULAR"
                        msg_estado = "Hay una división clara en el grupo. Se requiere repaso."
                    else:
                        estado = "🟡 CRÍTICO"
                        msg_estado = "La mayoría no ha logrado los objetivos mínimos."

                    # B. ANÁLISIS DE DIFICULTAD
                    if promedio_intentos < 1.5:
                        dificultad = "Baja (Posiblemente trivial)"
                    elif promedio_intentos < 3.0:
                        dificultad = "Moderada (Esperada)"
                    else:
                        dificultad = "Alta (Posible frustración)"

                    # --- 3. RENDERIZADO DEL REPORTE ---
                    
                    # Tarjeta de Resumen
                    with st.container(border=True):
                        c_inf1, c_inf2 = st.columns(2)
                        c_inf1.markdown(f"**Estado General:** {estado}")
                        c_inf1.caption(msg_estado)
                        
                        c_inf2.markdown(f"**Dificultad Percibida:** {dificultad}")
                        if eff_report < 10:
                            c_inf2.caption("⚠️ Baja eficiencia: Muchos intentos fallidos por punto ganado.")
                        else:
                            c_inf2.caption("✅ Alta eficiencia: Respuestas precisas.")

                    #st.divider()

                    # Listas de Acción (Actionable Insights)
                    c_act1, c_act2, c_act3 = st.columns(3)
                    
                    with c_act1:
                        st.markdown("**Atención Prioritaria**")
                        st.caption("Estudiantes que intentan mucho pero no logran aprobar (Frustración).")
                        if not struggling.empty:
                            st.error(f"{len(struggling)} Estudiantes")
                            with st.expander("Ver lista"):
                                st.dataframe(struggling[['student_id', 'attempts', 'score']], hide_index=True)
                        else:
                            st.success("Ninguno detectado.")

                    with c_act2:
                        st.markdown("**Posible Adivinanza**")
                        st.caption("Aprobaron por persistencia, no necesariamente por conocimiento.")
                        if not guessers.empty:
                            st.warning(f"{len(guessers)} Estudiantes")
                            with st.expander("Ver lista"):
                                st.dataframe(guessers[['student_id', 'attempts', 'score']], hide_index=True)
                        else:
                            st.success("Bajo nivel de adivinanza.")

                    with c_act3:
                        st.markdown("**Cuadro de Honor**")
                        st.caption("Puntaje perfecto (o casi perfecto) al primer intento.")
                        if not elite.empty:
                            st.info(f"{len(elite)} Estudiantes")
                            with st.expander("Ver lista"):
                                st.dataframe(elite[['student_id', 'score']], hide_index=True)
                        else:
                            st.caption("Nadie (aún).")

                    # Conclusión Final
                    #st.write("")
                    txt_conclusion = f"""
                    **Conclusión:**  
                    El curso tiene una eficiencia de **{eff_report:.1f}** puntos por intento. 
                    Se recomienda contactar a los **{len(struggling)}** estudiantes en riesgo y felicitar a los **{len(elite)}** de alto rendimiento.
                    """
                    st.info(txt_conclusion, icon="🤖")

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
# OPTIMIZACIÓN: CACHÉ DEL RANKING (microlms.py)
# ==============================================================================

# La base de datos "descansa" durante 59 segundos de cada minuto.
@st.cache_data(ttl=60, show_spinner=False) 
def get_cached_leaderboard_view(exam_id):
    """
    Procesa y ordena el ranking delegando el peso a SQL.
    """
    df_exam = db_manager.get_leaderboard_data(exam_id)
    
    if df_exam.empty:
        return pd.DataFrame()

    # Asignar Posiciones
    df_exam['Rank'] = range(1, len(df_exam) + 1)
    
    def get_medal(rank):
        if rank <= 50: return f"{rank}"
        return str(rank)
    
    df_exam['Posición'] = df_exam['Rank'].apply(get_medal)
    
    # Censurar IDs
    def mask_id(sid):
        s = str(sid)
        return "•" * (len(s) - 4) + s[-4:] if len(s) > 4 else s
        
    df_exam['Estudiante'] = df_exam['student_id'].apply(mask_id)
    
    # Retornar columnas limpias
    cols_show = ['Posición', 'Estudiante', 'score', 'attempts']
    return df_exam[cols_show]
    

def render_public_leaderboard(exam_id):
    st.markdown(f"##### 🏆 Ranking: {exam_id}")
    
    # Consumimos la caché de 60s
    df_view = get_cached_leaderboard_view(exam_id)
    
    if df_view.empty:
        st.info("⏳ Esperando resultados... (Actualización cada minuto)")
        if st.button("Probar suerte"):
            get_cached_leaderboard_view.clear()
            st.rerun()
        return

    st.dataframe(
        df_view,
        hide_index=True,
        width='stretch',
        column_config={
            "score": st.column_config.ProgressColumn(
                "Nota", 
                format="%.2f", 
                min_value=0, 
                max_value=20,
            ),
            "attempts": st.column_config.NumberColumn("Intentos", format="%d")
            #"Hora": "Llegada (VE)"
        },
        height=600
    )
    
    # Mensaje técnico actualizado
    st.caption(f"⚡ Datos cacheados (Se actualizan cada 60 segundos). Última carga: {datetime.now().strftime('%H:%M:%S')}")
    
    # Botón manual de refresco
    if st.button("Actualizar Tabla"):
        st.rerun()
        


# ==============================================================================
# 4. ENRUTADOR PRINCIPAL
# ==============================================================================
def main():
    # Obtener parámetros de la URL
    query_params = st.query_params
    
    # RUTA 1: Hacer Examen (?eval=ID)
    if "eval" in query_params:
        exam_id = query_params["eval"]
        execute_exam(exam_id)
        
    # RUTA 2: Ver Ranking Público (?ranking=ID)  <--- NUEVA RUTA
    elif "ranking" in query_params:
        exam_id = query_params["ranking"]
        # Limpiamos sidebar para vista "Kiosco"
        st.set_page_config(layout="centered", page_title=f"Ranking {exam_id}", page_icon="🏆")
        
        # Inyectamos CSS para ocultar menú de hamburguesa en modo público (opcional)
        st.markdown("""
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            </style>
            """, unsafe_allow_html=True)
            
        render_public_leaderboard(exam_id)
        
    # RUTA 3: Panel Admin (Sin parámetros)
    else:
        render_admin_panel()

if __name__ == "__main__":
    main()
    
