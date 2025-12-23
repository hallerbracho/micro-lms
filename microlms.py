import streamlit as st
import libsql_experimental as libsql
import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta, timezone  # <--- SE AGREGARON LIBRERÍAS DE TIEMPO

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


# --- VISUALIZACIÓN PARA PROFESORES ---
if is_admin:
    st.warning(f"VISTA DOCENTE - Solución correcta: {solucion}")
# -------------------------------------


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
    Crea una conexión persistente a Turso. 
    """
    url = st.secrets["TURSO_DB_URL"]
    token = st.secrets["TURSO_AUTH_TOKEN"]
    return libsql.connect(database=url, auth_token=token)

class DatabaseManager:
    def __init__(self):
        self._init_db()

    def _get_conn(self):
        return get_db_connection()

    def _get_ve_time(self):
        """Retorna la hora actual en UTC-4 (Venezuela) en formato string SQL"""
        # Obtenemos UTC actual y restamos 4 horas
        ve_time = datetime.now(timezone.utc) - timedelta(hours=4)
        return ve_time.strftime('%Y-%m-%d %H:%M:%S')

    def _init_db(self):
        conn = self._get_conn()
        
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
        st.error("🚫 El examen solicitado no existe o no está disponible.")
        if st.button("Volver al Inicio"):
            st.query_params.clear()
            st.rerun()
        return

    # Determinamos si es admin basándonos en la sesión actual
    is_admin_user = st.session_state.get('auth', False)
    
    context = {
        'st': st,
        'pd': pd,
        'np': np,
        'random': random,
        'db': db_manager,
        'EXAM_ID': exam_id,
        'datetime': datetime,
        'is_admin': is_admin_user  # <--- NUEVA VARIABLE INYECTADA
    }
    
    try:
        exec(source_code, context)
    except Exception as e:
        st.error("🚨 Error interno en la ejecución del examen.")
        with st.expander("Detalles para el profesor"):
            st.code(str(e))

def render_admin_panel():
    st.title("Panel de Control Docente")
    
    if not st.session_state.get('auth'):
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

    st.caption("Modo Administrador Activo (Hora VE)")
    if st.button("Cerrar Sesión"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    tab_editor, tab_grades = st.tabs(["📝 Gestión de Exámenes", "📊 Libro de Notas"])

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
            exam_id_input = st.text_input("ID del Examen (ej: parcial_1)", value=st.session_state.get('current_exam_id', ""))
            st.session_state['current_exam_id'] = exam_id_input
        else:
            exam_id_input = selection
            st.info(f"Editando examen: **{exam_id_input}**")

        new_code = st.text_area("Código Python", height=450, key="editor_area")

        c1, c2, c3 = st.columns([1, 1, 2])
        
        with c1:
            if st.button("💾 Guardar", type="primary"):
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
                if st.button("🗑️ Eliminar"):
                    db_manager.delete_exam(selection)
                    st.toast("Examen eliminado")
                    st.session_state['last_selection'] = None
                    st.rerun()
        
        with c3:
            if selection != "➕ Crear Nuevo...":
                link = f"/?eval={selection}"
                st.code(link, language="text")
                st.caption("Comparte este link con los alumnos")

    with tab_grades:
        if st.button("🔄 Refrescar Tabla"):
            st.rerun()
            
        df = db_manager.get_all_grades()
        if not df.empty:
            filtro_exam = st.multiselect("Filtrar por Examen", df['exam_id'].unique())
            if filtro_exam:
                df = df[df['exam_id'].isin(filtro_exam)]
            
            st.dataframe(
                df, 
                use_container_width=True,
                column_config={
                    "is_correct": st.column_config.CheckboxColumn("Aprobado"),
                    "score": st.column_config.ProgressColumn("Nota", min_value=0, max_value=20, format="%.2f"),
                    "last_updated": st.column_config.DatetimeColumn("Fecha (VE)", format="DD/MM HH:mm")
                }
            )
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Descargar CSV", csv, "notas_ve.csv", "text/csv")
        else:
            st.info("No hay registros aún.")

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
    
