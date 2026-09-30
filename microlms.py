# -*- coding: utf-8 -*-
"""
MicroLMS - Plataforma Ligera de Evaluaciones Paramétricas
Motor de evaluación determinista, analítica docente y CMS de exámenes.
"""

from datetime import datetime, timedelta, timezone
import hmac
import inspect
import math
import random
import threading
import types
from typing import Any, Dict, List, Optional, Tuple

import altair as alt
import libsql_experimental as libsql
import numpy as np
import pandas as pd
import streamlit as st

# ==============================================================================
# 1. CONFIGURACIÓN, CONSTANTES Y ESTILOS
# ==============================================================================

st.set_page_config(
    layout="centered",
    page_title="Plataforma de Evaluación",
    page_icon="🎓",
    initial_sidebar_state="auto"
)

# Zona Horaria Oficial: Venezuela (UTC-4)
TZ_VENEZUELA = timezone(timedelta(hours=-4))

# Cerrojo reentrante para concurrencia segura (lectura/escritura) entre hilos
DB_LOCK = threading.RLock()

ST_STYLE = """
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stApp { background-color: #ffffff; color: #111111; }
    
    div[data-testid="stTextArea"] textarea { 
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important; 
        font-size: 13px !important;
        line-height: 1.5 !important;
        background-color: #1e1e1e !important;
        color: #d4d4d4 !important;
        border-radius: 6px;
    }
    
    .stButton>button { 
        border-radius: 6px; 
        font-weight: 500;
        width: 100%; 
        transition: all 0.2s ease-in-out;
    }
    
    section[data-testid="stSidebar"] {
        width: 420px !important;
    }
        
    .block-container {
        max-width: 850px !important;
        padding-top: 2rem !important;
        padding-bottom: 3rem !important;
    }
</style>
"""
st.markdown(ST_STYLE, unsafe_allow_html=True)

DEFAULT_TEMPLATE = '''# --- PLANTILLA DE EVALUACIÓN DETERMINISTA ---
# Variables provistas en el entorno:
# st, pd, np, random, db, EXAM_ID, is_admin, sidebar_area, datetime

st.title("Evaluación Interactiva")

student_id = st.text_input("Ingrese su Cédula o Identificador:", max_chars=12).strip()
if not student_id:
    st.info("Ingrese su identificación para generar sus parámetros individuales.")
    st.stop()

status = db.check_student_status(EXAM_ID, student_id)
if status["has_passed"]:
    st.success(f"Evaluación completada con éxito. Calificación: **{status['score']:.2f} pts**")
    st.stop()

seed_val = int("".join(filter(str.isdigit, student_id)) or 0)
random.seed(seed_val)
np.random.seed(seed_val)

num_a = random.randint(10, 50)
num_b = random.randint(5, 25)
solucion = {"rendimiento": float(num_a * num_b)}
respuesta = solucion

st.markdown(f"""
### Pregunta de Aplicación
Un sistema opera bajo una tasa de carga de **{num_a} unidades** con factor multiplicador base **{num_b}**.
Determine el rendimiento total resultante.
""")

with st.form("exam_form", enter_to_submit=False):
    resp_u = st.number_input("Respuesta calculada:", step=0.01, format="%.2f")
    enviado = st.form_submit_button("Entregar Evaluación", type="primary")

if enviado:
    es_correcto = abs(resp_u - solucion["rendimiento"]) <= 0.05
    raw_val = 20.0 if es_correcto else 5.0
    intentos, nota = db.register_attempt(EXAM_ID, student_id, es_correcto, raw_score=raw_val)
    if es_correcto:
        st.success(f"Entrega asentada. Nota: **{nota:.2f} / 20.00 pts** (Intentos: {intentos})")
        st.rerun()
    else:
        st.error(f"Valor incorrecto. Intento {intentos} registrado.")
'''

# ==============================================================================
# 2. CAPA DE BASE DE DATOS (Turso / LibSQL)
# ==============================================================================

def is_connection_active(conn) -> bool:
    try:
        conn.execute("SELECT 1")
        return True
    except Exception:
        return False

@st.cache_resource(validate=is_connection_active)
def get_db_connection():
    url = st.secrets.get("TURSO_DB_URL")
    token = st.secrets.get("TURSO_AUTH_TOKEN")
    
    if not url or not token:
        st.error("Faltan las credenciales TURSO_DB_URL y/o TURSO_AUTH_TOKEN en st.secrets.")
        st.stop()
        
    conn = libsql.connect(database=url, auth_token=token)
    
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
    except Exception:
        pass
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS grades (
            exam_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            attempts INTEGER DEFAULT 0,
            score REAL DEFAULT 0,
            is_correct BOOLEAN DEFAULT 0,
            last_updated TIMESTAMP,
            student_name TEXT,
            student_list_n INTEGER,
            PRIMARY KEY (exam_id, student_id)
        )
    """)

    for col_def in ["student_name TEXT", "student_list_n INTEGER"]:
        try:
            conn.execute(f"ALTER TABLE grades ADD COLUMN {col_def}")
        except Exception:
            pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS exams (
            exam_id TEXT PRIMARY KEY,
            source_code TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_grades_exam_correct 
        ON grades(exam_id, is_correct)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_grades_exam_date 
        ON grades(exam_id, last_updated)
    """)
    conn.commit()
    return conn


class DatabaseManager:
    @staticmethod
    def _get_conn():
        return get_db_connection()

    @staticmethod
    def get_ve_time_str() -> str:
        return datetime.now(TZ_VENEZUELA).strftime('%Y-%m-%d %H:%M:%S')

    def check_student_status(self, exam_id: str, student_id: str) -> Dict[str, Any]:
        conn = self._get_conn()
        with DB_LOCK:
            row = conn.execute(
                "SELECT score, is_correct, attempts FROM grades WHERE exam_id=? AND student_id=?", 
                (exam_id, student_id)
            ).fetchone()
        
        if row:
            return {
                "has_passed": bool(row[1]), 
                "score": float(row[0]),
                "attempts": int(row[2])
            }
        return {"has_passed": False, "score": 0.0, "attempts": 0}

    def register_attempt(
        self, 
        exam_id: str, 
        student_id: str, 
        is_correct: bool, 
        raw_score: Optional[float] = None, 
        score_func: Optional[Any] = None,
        student_name: Optional[str] = None,
        student_list_n: Optional[int] = None,
        **kwargs
    ) -> Tuple[int, float]:
        conn = self._get_conn()
        
        with DB_LOCK:
            res = conn.execute(
                "SELECT attempts, score, is_correct FROM grades WHERE exam_id=? AND student_id=?", 
                (exam_id, student_id)
            ).fetchone()
            
            prev_attempts = res[0] if res else 0
            prev_score = float(res[1]) if res else 0.0
            already_passed = bool(res[2]) if res else False
            
            current_attempts = prev_attempts + 1

            score = 0.0
            if score_func and callable(score_func):
                try:
                    sig = inspect.signature(score_func)
                    params_count = len(sig.parameters)
                    if params_count >= 3:
                        score = float(score_func(current_attempts, is_correct, raw_score))
                    elif params_count == 2:
                        score = float(score_func(current_attempts, is_correct))
                    else:
                        score = float(score_func(current_attempts))
                except Exception:
                    score = prev_score
            else:            
                # Fallback Gaussiano Probit de Blom
                r_val = float(raw_score) if raw_score is not None else (20.0 if is_correct else 7.0)
                if r_val > 20.0:
                    r_val = (r_val / 100.0) * 20.0
                r_val = max(0.0, min(20.0, r_val))
                
                p = (r_val + 0.375) / 20.75
                a = 0.147
                x = max(-0.999999, min(0.999999, 2.0 * p - 1.0))
                w = math.log(1.0 - x * x)
                t1 = 2.0 / (math.pi * a) + w / 2.0
                z_raw = math.sqrt(2.0) * (1.0 if x >= 0 else -1.0) * math.sqrt(math.sqrt(max(0.0, t1 * t1 - w / a)) - t1)
                
                att = max(1, int(current_attempts))
                pen_z = 0.30 * math.sqrt(math.log(att)) if att > 1 else 0.0
                z_max = 2.09114
                
                if is_correct or r_val >= 10.0:
                    z_eff = max(0.0, z_raw - pen_z)
                    score = 9.50 + ((19.50 - 9.50) / z_max) * z_eff
                    score = float(np.clip(score, 9.50, 19.50))
                else:
                    z_eff = min(0.0, z_raw - pen_z)
                    score = 9.40 + ((9.40 - 0.50) / z_max) * z_eff
                    score = float(np.clip(score, 0.50, 9.40))

            # Garantía: se preserva siempre la mejor calificación obtenida
            final_score = max(prev_score, score)
            new_passed = 1 if (already_passed or is_correct) else 0
            current_time_ve = self.get_ve_time_str()

            conn.execute("""
                INSERT INTO grades (exam_id, student_id, attempts, is_correct, score, last_updated, student_name, student_list_n)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(exam_id, student_id) DO UPDATE SET
                    attempts = attempts + 1,
                    is_correct = MAX(grades.is_correct, excluded.is_correct),
                    score = excluded.score,
                    last_updated = excluded.last_updated,
                    student_name = COALESCE(excluded.student_name, grades.student_name),
                    student_list_n = COALESCE(excluded.student_list_n, grades.student_list_n)
            """, (exam_id, student_id, 1, new_passed, round(final_score, 2), current_time_ve, student_name, student_list_n))
            conn.commit()

        return current_attempts, round(final_score, 2)

    def get_all_grades(self) -> pd.DataFrame:
        conn = self._get_conn()
        with DB_LOCK:
            cursor = conn.execute("SELECT * FROM grades ORDER BY last_updated DESC")
            cols = [d[0] for d in cursor.description]
            data = cursor.fetchall()
        return pd.DataFrame(data, columns=cols)

    def get_leaderboard_data(self, exam_id: str) -> pd.DataFrame:
        conn = self._get_conn()
        with DB_LOCK:
            cursor = conn.execute("""
                SELECT student_id, score, attempts, last_updated, student_name, student_list_n 
                FROM grades 
                WHERE exam_id=? AND is_correct=1 
                ORDER BY score DESC, attempts ASC, last_updated ASC
            """, (exam_id,))
            cols = [d[0] for d in cursor.description]
            data = cursor.fetchall()
        return pd.DataFrame(data, columns=cols)

    def get_exam_list(self) -> List[str]:
        conn = self._get_conn()
        with DB_LOCK:
            rows = conn.execute("SELECT exam_id FROM exams ORDER BY created_at DESC").fetchall()
        return [r[0] for r in rows]

    def get_exam_code(self, exam_id: str) -> Optional[str]:
        conn = self._get_conn()
        with DB_LOCK:
            row = conn.execute("SELECT source_code FROM exams WHERE exam_id=?", (exam_id,)).fetchone()
        return row[0] if row else None

    def save_exam(self, exam_id: str, code: str) -> None:
        conn = self._get_conn()
        current_time_ve = self.get_ve_time_str()
        with DB_LOCK:
            conn.execute("""
                INSERT INTO exams (exam_id, source_code, created_at) VALUES (?, ?, ?)
                ON CONFLICT(exam_id) DO UPDATE SET 
                    source_code = excluded.source_code,
                    created_at = excluded.created_at
            """, (exam_id, code, current_time_ve))
            conn.commit()
        get_cached_exam_code.clear()

    def delete_exam(self, exam_id: str) -> None:
        conn = self._get_conn()
        with DB_LOCK:
            conn.execute("DELETE FROM exams WHERE exam_id=?", (exam_id,))
            conn.commit()
        get_cached_exam_code.clear()
        get_cached_all_grades.clear()
        get_cached_leaderboard_view.clear()


db_manager = DatabaseManager()

# ==============================================================================
# 3. CACHÉS DE RENDIMIENTO
# ==============================================================================

@st.cache_data(ttl=60, show_spinner=False)
def get_cached_all_grades() -> pd.DataFrame:
    return db_manager.get_all_grades()

@st.cache_data(ttl=300, show_spinner=False)
def get_cached_exam_code(exam_id: str) -> Optional[str]:
    return db_manager.get_exam_code(exam_id)

@st.cache_data(ttl=30, show_spinner=False)
def get_cached_leaderboard_view(exam_id: str) -> pd.DataFrame:
    df_exam = db_manager.get_leaderboard_data(exam_id)
    if df_exam.empty:
        return pd.DataFrame()

    df_exam['Posición'] = [f"#{i + 1}" for i in range(len(df_exam))]
    
    def mask_id(sid: Any) -> str:
        s = str(sid).strip()
        return "••••" + s[-4:] if len(s) > 4 else s

    df_exam['Estudiante'] = df_exam['student_id'].apply(mask_id)
    return df_exam[['Posición', 'Estudiante', 'score', 'attempts', 'last_updated']]

# ==============================================================================
# 4. SIMULADOR HEADLESS (Mock de Streamlit para el Solucionador)
# ==============================================================================

class MockSessionState(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"'MockSessionState' no posee el atributo '{key}'")

    def __setattr__(self, key, value):
        self[key] = value


class SilentStreamlit:
    def __init__(self, student_id: str):
        self.fixed_input = str(student_id)
        self.secrets = st.secrets
        self.session_state = MockSessionState()
        self.session_state.user_session = {
            "verified": True,
            "id": self.fixed_input,
            "section": "SIMULACION"
        }

    @property
    def sidebar(self):
        return self

    def container(self, **kwargs): return self
    def columns(self, spec, **kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [self] * count
    def tabs(self, tabs_list, **kwargs): return [self] * len(tabs_list)
    def expander(self, *args, **kwargs): return self
    def form(self, *args, **kwargs): return self
    def status(self, *args, **kwargs): return self
    def chat_message(self, *args, **kwargs): return self

    def text_input(self, label, **kwargs):
        l_lower = label.lower()
        if any(term in l_lower for term in ["id", "cédula", "cedula", "identificación"]):
            return self.fixed_input
        return "Valor_Simulado"

    def number_input(self, label, **kwargs): return 1.0
    def slider(self, label, min_value=0, max_value=100, **kwargs): return min_value
    def radio(self, label, options, **kwargs): return options[0] if options else None
    def selectbox(self, label, options, **kwargs): return options[0] if options else None
    def multiselect(self, label, options, **kwargs): return [options[0]] if options else []
    def checkbox(self, label, **kwargs): return False
    def toggle(self, label, **kwargs): return False
    def button(self, label, **kwargs): return False
    def form_submit_button(self, label="Submit", **kwargs): return False

    def stop(self): pass
    def rerun(self): pass
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): pass
    def __iter__(self): yield self
    def __getattr__(self, name): return lambda *args, **kwargs: self


class MockDB:
    def check_student_status(self, exam_id, student_id):
        return {"has_passed": False, "score": 0.0, "attempts": 0}
    def register_attempt(self, *args, **kwargs):
        return 1, 19.50

# ==============================================================================
# 5. MOTOR DE EJECUCIÓN DEL EXAMEN
# ==============================================================================

def execute_exam(exam_id: str):
    source_code = get_cached_exam_code(exam_id)
    
    if not source_code:
        st.error("La evaluacion solicitada no existe o ha sido dada de baja.")
        if st.button("Volver al Inicio"):
            st.query_params.clear()
            st.rerun()
        return

    is_admin_user = bool(st.session_state.get('auth', False))
    
    with st.sidebar:
        contenedor_sidebar = st.container()
    
    execution_context = {
        'st': st,
        'pd': pd,
        'np': np,
        'random': random,
        'db': db_manager,
        'EXAM_ID': exam_id,
        'datetime': datetime,
        'is_admin': is_admin_user,
        'sidebar_area': contenedor_sidebar
    }
    
    try:
        exec(source_code, execution_context)
    except Exception as e:
        st.error("Se produjo un error al ejecutar la evaluacion.")
        if is_admin_user:
            with st.expander("Detalles del Error (Docente)"):
                st.exception(e)

# ==============================================================================
# 6. PANEL DOCENTE Y ADMINISTRATIVO
# ==============================================================================

def check_admin_auth() -> bool:
    if st.session_state.get('auth', False):
        return True

    st.header("Panel de Control Docente", divider=True)
    admin_secret = st.secrets.get("ADMIN_PASSWORD")
    
    if not admin_secret:
        st.error("No se ha definido ADMIN_PASSWORD en los secretos de la aplicacion.")
        return False

    with st.form("admin_login_form"):
        pwd = st.text_input("Contraseña de Acceso", type="password")
        submitted = st.form_submit_button("Ingresar", type="primary")
        
        if submitted:
            if hmac.compare_digest(pwd, admin_secret):
                st.session_state['auth'] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
    return False


def render_admin_panel():
    if not check_admin_auth():
        return

    with st.sidebar:
        st.header("Sesion Docente", divider=True)
        st.caption(f"Hora Local: {db_manager.get_ve_time_str()} (VE)")
        if st.button("Cerrar Sesion", type="secondary"):
            st.session_state.clear()
            st.rerun()

    tab_dash, tab_grades, tab_cms, tab_solver = st.tabs([
        "Dashboard", 
        "Calificaciones", 
        "Editor de Evaluaciones", 
        "Solucionador Determinista"
    ])

    with tab_dash:
        df = get_cached_all_grades()
        
        if df.empty:
            st.info("No hay datos de calificaciones disponibles.")
        else:
            c_ref, c_filter = st.columns([1, 3], vertical_alignment="bottom")
            with c_ref:
                if st.button("Refrescar"):
                    get_cached_all_grades.clear()
                    st.rerun()
            with c_filter:
                examenes = list(df['exam_id'].unique())
                seleccion_dash = st.multiselect(
                    "Filtrar evaluaciones", 
                    options=examenes, 
                    placeholder="Todas las evaluaciones incluidas",
                    label_visibility="collapsed"
                )

            df_view = df[df['exam_id'].isin(seleccion_dash)].copy() if seleccion_dash else df.copy()
            df_view['score'] = pd.to_numeric(df_view['score'], errors='coerce').fillna(0.0)
            df_view['attempts'] = pd.to_numeric(df_view['attempts'], errors='coerce').fillna(0)
            df_view['last_updated'] = pd.to_datetime(df_view['last_updated'], errors='coerce')

            total_unicos = df_view['student_id'].nunique()
            aprobados_df = df_view[df_view['is_correct'] == 1]
            aprobados_unicos = aprobados_df['student_id'].nunique()
            pendientes = total_unicos - aprobados_unicos
            
            tasa_aprobacion = (aprobados_unicos / total_unicos * 100) if total_unicos > 0 else 0.0
            promedio_global = df_view['score'].mean() if not df_view.empty else 0.0
            promedio_aprobados = aprobados_df['score'].mean() if not aprobados_df.empty else 0.0
            promedio_intentos = aprobados_df['attempts'].mean() if not aprobados_df.empty else 0.0

            sub_kpi, sub_charts, sub_report = st.tabs(["Metricas Clave", "Graficos", "Diagnostico"])
            
            with sub_kpi:
                c1, c2 = st.columns(2)
                c1.metric("Estudiantes Evaluados", total_unicos, delta=f"{len(df_view)} registros")
                c2.metric("Pendientes por Aprobar", pendientes, delta=f"{aprobados_unicos} aprobados")
                
                c3, c4, c5 = st.columns(3)
                c3.metric("Tasa de Aprobacion", f"{tasa_aprobacion:.1f}%")
                c4.metric("Promedio Global", f"{promedio_global:.2f} pts", delta=f"Aprobados: {promedio_aprobados:.2f}")
                c5.metric("Intentos Promedio", f"{promedio_intentos:.1f}")

            with sub_charts:
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    st.markdown("**Distribucion de Notas**")
                    hist_data = pd.DataFrame(index=range(21))
                    reprobados = df_view[df_view['score'] < 9.5]['score'].round().astype(int).value_counts()
                    aprobados = df_view[df_view['score'] >= 9.5]['score'].round().astype(int).value_counts()
                    hist_data['Reprobados'] = reprobados
                    hist_data['Aprobados'] = aprobados
                    hist_data = hist_data.fillna(0)
                    st.bar_chart(hist_data, color=["#FF4B4B", "#2ECC71"], stack=True)

                with col_g2:
                    st.markdown("**Actividad de Entrega**")
                    if not df_view['last_updated'].isna().all():
                        df_view['dia'] = df_view['last_updated'].dt.date
                        st.line_chart(df_view.groupby('dia').size())

                st.markdown("**Relacion Intentos vs. Calificacion Final**")
                df_view['Estado'] = np.where(df_view['is_correct'] == 1, 'Aprobado', 'Reprobado')
                scatter_chart = alt.Chart(df_view).mark_circle(size=140).encode(
                    x=alt.X('attempts:Q', title='Intentos Realizados'),
                    y=alt.Y('score:Q', title='Nota Obtenida (0-20)', scale=alt.Scale(domain=[0, 20])),
                    color=alt.Color('Estado:N', scale=alt.Scale(domain=['Aprobado', 'Reprobado'], range=['#2ECC71', '#FF4B4B'])),
                    tooltip=[
                        alt.Tooltip('student_id:N', title='ID'),
                        alt.Tooltip('score:Q', title='Nota', format='.2f'),
                        alt.Tooltip('attempts:Q', title='Intentos')
                    ]
                ).interactive()
                st.altair_chart(scatter_chart, use_container_width=True)

            with sub_report:
                st.subheader("Diagnostico de Rendimiento", divider=True)
                en_riesgo = df_view[(df_view['score'] < 9.5) & (df_view['attempts'] >= 3)]
                destacados = df_view[(df_view['score'] >= 18.0) & (df_view['attempts'] == 1)]
                
                r1, r2 = st.columns(2)
                with r1:
                    st.error(f"En Riesgo: {len(en_riesgo)}")
                    st.caption("Reprobados con intentos agotados o maximos.")
                    if not en_riesgo.empty:
                        st.dataframe(en_riesgo[['student_id', 'student_name', 'attempts', 'score']], hide_index=True)
                with r2:
                    st.success(f"Cuadro de Honor: {len(destacados)}")
                    st.caption("Calificacion >= 18.00 al primer intento.")
                    if not destacados.empty:
                        st.dataframe(destacados[['student_id', 'student_name', 'score']], hide_index=True)

    with tab_grades:
        df_all = get_cached_all_grades()
        
        c_btn, c_csv, c_f_exam, c_f_id = st.columns([1.2, 0.6, 2, 2], vertical_alignment="top")
        
        with c_btn:
            if st.button("Actualizar", key="btn_refresh_grades"):
                get_cached_all_grades.clear()
                st.rerun()
                
        with c_csv:
            if not df_all.empty:
                csv_bytes = df_all.to_csv(index=False).encode('utf-8-sig')
                st.download_button("Descargar CSV", data=csv_bytes, file_name="calificaciones.csv", mime="text/csv")
                
        with c_f_exam:
            f_exam = st.multiselect("Filtrar Examen", df_all['exam_id'].unique() if not df_all.empty else [], label_visibility="collapsed", placeholder="Examen...")
        
        with c_f_id:
            f_id = st.text_input("Filtrar Cedula/Nombre", placeholder="Buscar Cedula o Nombre...", label_visibility="collapsed")

        if not df_all.empty:
            df_filtered = df_all.copy()
            if f_exam:
                df_filtered = df_filtered[df_filtered['exam_id'].isin(f_exam)]
            if f_id:
                df_filtered = df_filtered[
                    df_filtered['student_id'].astype(str).str.contains(f_id, case=False, na=False) |
                    df_filtered['student_name'].astype(str).str.contains(f_id, case=False, na=False)
                ]

            columnas_orden = ['student_list_n', 'student_id', 'student_name', 'score', 'is_correct', 'attempts', 'last_updated', 'exam_id']
            cols_disponibles = [c for c in columnas_orden if c in df_filtered.columns] + [c for c in df_filtered.columns if c not in columnas_orden]
            df_display = df_filtered[cols_disponibles].sort_values(by=['exam_id', 'student_list_n'], ascending=[True, True])

            st.dataframe(
                df_display,
                use_container_width=True,
                column_config={
                    "student_list_n": st.column_config.NumberColumn("N°", width="small", format="%d"),
                    "student_id": st.column_config.TextColumn("Cedula"),
                    "student_name": st.column_config.TextColumn("Apellidos y Nombres"),
                    "is_correct": st.column_config.CheckboxColumn("Aprobado"),
                    "score": st.column_config.ProgressColumn("Nota (0-20)", min_value=0, max_value=20, format="%.2f"),
                    "attempts": st.column_config.NumberColumn("Intentos", format="%d"),
                    "last_updated": st.column_config.DatetimeColumn("Ultima Entrega", format="DD/MM/YYYY hh:mm a")
                },
                hide_index=True
            )
        else:
            st.info("No se han registrado entregas en el sistema.")

    with tab_cms:
        lista_examenes = db_manager.get_exam_list()
        opciones_cms = ["Crear Nuevo..."] + lista_examenes
        
        col_s, col_i = st.columns([1, 1], vertical_alignment="bottom")
        with col_s:
            sel_exam = st.selectbox("Seleccionar Evaluacion", opciones_cms)
            
        if st.session_state.get('cms_last_selection') != sel_exam:
            if sel_exam == "Crear Nuevo...":
                st.session_state['cms_code'] = DEFAULT_TEMPLATE
                st.session_state['cms_id'] = ""
            else:
                st.session_state['cms_code'] = db_manager.get_exam_code(sel_exam) or ""
                st.session_state['cms_id'] = sel_exam
            st.session_state['cms_last_selection'] = sel_exam

        with col_i:
            if sel_exam == "Crear Nuevo...":
                nuevo_id = st.text_input("Identificador Unico (slug)", value=st.session_state.get('cms_id', "")).strip()
                st.session_state['cms_id'] = nuevo_id
            else:
                st.info(f"Editando: **{sel_exam}**")

        codigo_editado = st.text_area("Codigo Fuente (Python)", value=st.session_state.get('cms_code', ""), height=380)

        c_guardar, c_borrar, c_prev, c_rank = st.columns([2, 2, 3, 2])
        
        with c_guardar:
            if st.button("Guardar", type="primary"):
                id_destino = st.session_state.get('cms_id', "").strip()
                if not id_destino:
                    st.error("Debe especificar un ID para la evaluacion.")
                else:
                    db_manager.save_exam(id_destino, codigo_editado)
                    st.success(f"Evaluacion '{id_destino}' guardada exitosamente.")
                    st.session_state['cms_last_selection'] = id_destino
                    st.rerun()

        with c_borrar:
            if sel_exam != "Crear Nuevo...":
                with st.popover("Eliminar"):
                    st.warning(f"Confirma la eliminacion definitiva de '{sel_exam}'?")
                    if st.button("Confirmar Eliminacion", type="primary"):
                        db_manager.delete_exam(sel_exam)
                        st.session_state['cms_last_selection'] = None
                        st.rerun()

        with c_prev:
            if sel_exam != "Crear Nuevo...":
                st.link_button("Abrir Examen", f"/?eval={sel_exam}")

        with c_rank:
            if sel_exam != "Crear Nuevo...":
                st.link_button("Ranking", f"/?ranking={sel_exam}")

    with tab_solver:
        st.subheader("Simulador Headless Docente", divider=True)
        st.caption("Audita la semilla y respuestas esperadas de un estudiante.")
        
        col_sol_e, col_sol_s = st.columns(2)
        with col_sol_e:
            sol_exam_id = st.selectbox("Evaluacion", db_manager.get_exam_list(), key="solver_exam")
        with col_sol_s:
            sol_student_id = st.text_input("Cedula / Identificador", key="solver_student").strip()

        if st.button("Calcular Parametros y Respuestas", type="primary"):
            if not sol_exam_id or not sol_student_id:
                st.warning("Seleccione una evaluacion e ingrese una identificacion valida.")
            else:
                raw_code = db_manager.get_exam_code(sol_exam_id)
                if not raw_code:
                    st.error("No se encontro el codigo del examen.")
                else:
                    lineas = [l for l in raw_code.split('\n') if not l.strip().startswith(("import streamlit", "from streamlit"))]
                    codigo_limpio = "\n".join(lineas)
                    
                    mock_st = SilentStreamlit(sol_student_id)
                    mock_db = MockDB()
                    
                    builtins_ignorar = {
                        'st', 'pd', 'np', 'random', 'db', 'EXAM_ID', 
                        'datetime', 'is_admin', 'sidebar_area', '__builtins__'
                    }
                    
                    solver_env = {
                        'st': mock_st,
                        'pd': pd,
                        'np': np,
                        'random': random,
                        'db': mock_db,
                        'EXAM_ID': sol_exam_id,
                        'datetime': datetime,
                        'is_admin': True,
                        'sidebar_area': mock_st
                    }

                    try:
                        exec(codigo_limpio, solver_env)
                        
                        st.divider()
                        st.markdown(f"#### Resultados generados para: `{sol_student_id}`")
                        
                        claves_prioritarias = ['solucion', 'solution', 'respuesta', 'result', 'answer']
                        encontradas = False
                        for clave in claves_prioritarias:
                            if clave in solver_env:
                                st.success(f"**{clave}**: `{solver_env[clave]}`")
                                encontradas = True
                                break
                                
                        variables_generadas = {}
                        for k, v in solver_env.items():
                            if k.startswith('_') or k in builtins_ignorar:
                                continue
                            if isinstance(v, (types.ModuleType, types.FunctionType, type)):
                                continue
                            variables_generadas[k] = v
                            
                        with st.expander("Inspeccionar todas las variables de memoria", expanded=not encontradas):
                            st.json(variables_generadas)
                            
                    except Exception as err:
                        st.error(f"Error durante la simulacion: {err}")
                        with st.expander("Ver traza"):
                            st.exception(err)

# ==============================================================================
# 7. TABLA PÚBLICA DE POSICIONES (LEADERBOARD)
# ==============================================================================

def render_public_leaderboard(exam_id: str):
    st.markdown(f"## Cuadro de Honor: `{exam_id}`")
    st.caption("Resultados oficiales ordenados por calificacion, eficiencia de intentos y orden de entrega.")
    
    df_view = get_cached_leaderboard_view(exam_id)
    
    if df_view.empty:
        st.info("Aun no hay aprobados registrados en esta evaluacion.")
        if st.button("Actualizar"):
            get_cached_leaderboard_view.clear()
            st.rerun()
        return

    st.dataframe(
        df_view,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Posición": st.column_config.TextColumn("Posicion", width="small"),
            "Estudiante": st.column_config.TextColumn("Identificacion"),
            "score": st.column_config.ProgressColumn("Calificacion", min_value=0, max_value=20, format="%.2f"),
            "attempts": st.column_config.NumberColumn("Intentos", format="%d"),
            "last_updated": st.column_config.DatetimeColumn("Fecha Entrega", format="DD/MM/YYYY hh:mm a")
        }
    )
    
    c_info, c_btn = st.columns([3, 1], vertical_alignment="center")
    with c_info:
        st.caption(f"Ultima sincronizacion: {datetime.now(TZ_VENEZUELA).strftime('%H:%M:%S')} (Hora VE)")
    with c_btn:
        if st.button("Actualizar", key="btn_refresh_leaderboard"):
            get_cached_leaderboard_view.clear()
            st.rerun()

# ==============================================================================
# 8. ENRUTADOR PRINCIPAL (SPA Router)
# ==============================================================================

def main():
    params = st.query_params
    
    if "eval" in params:
        execute_exam(params["eval"])
    elif "ranking" in params:
        render_public_leaderboard(params["ranking"])
    else:
        render_admin_panel()

if __name__ == "__main__":
    main()