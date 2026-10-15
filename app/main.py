from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text, inspect

from app.api import analytics, catalog, classification, programs, questions, scoring, topics, enem_import, model_admin, student, learning, admin
from app.database import SessionLocal, database_status
from app.config import settings
from app.supabase_auth import get_current_supabase_user
from app.models import Exam, Question, Topic, Alternative, QuestionTopic, TopicEdge, TopicYearFrequency, Program

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="Sistema de Análise Histórica do ENEM",
    description="Motor de previsão de temas prováveis por área e curso, baseado no histórico disponível.",
    version="0.8.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(questions.router)
app.include_router(topics.router)
app.include_router(scoring.router)
app.include_router(programs.router)
app.include_router(catalog.router)
app.include_router(analytics.router)
app.include_router(classification.router)
app.include_router(enem_import.router)
app.include_router(model_admin.router)
app.include_router(student.router)
app.include_router(learning.router)
app.include_router(admin.router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/api/health")
def health():
    db_ok = False
    if SessionLocal is not None:
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
                db_ok = True
        except Exception:
            pass
    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "supabase_configured": bool(settings.supabase_url and settings.supabase_anon_key),
        "database_driver": database_status(),
        "version": app.version,
    }


@app.get("/api/auth/me")
def auth_me(user=__import__("fastapi").Depends(get_current_supabase_user)):
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "role": (user.get("app_metadata") or {}).get("role"),
        "user_metadata": user.get("user_metadata") or {},
    }


@app.get("/api/stats")
def stats():
    if SessionLocal is None:
        return {"exams": 0, "questions": 0, "topics": 0, "database": False}
    try:
        with SessionLocal() as db:
            return {"exams": db.query(Exam).count(), "questions": db.query(Question).count(), "topics": db.query(Topic).count(), "database": True}
    except Exception as exc:
        return {"exams": 0, "questions": 0, "topics": 0, "database": False, "error": str(exc)[:300]}


@app.get("/api/diagnostics")
def diagnostics():
    """Diagnóstico operacional do banco e da estrutura exigida pela aplicação."""
    if SessionLocal is None:
        return {"status": "degraded", "database": False, "error": "DATABASE_URL não configurada", "checks": {}}
    checks = {}
    required_tables = {
        "exams": Exam, "questions": Question, "alternatives": Alternative,
        "topics": Topic, "question_topics": QuestionTopic,
        "topic_edges": TopicEdge, "topic_year_frequency": TopicYearFrequency,
        "programs": Program,
    }
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            inspector = inspect(db.get_bind())
            existing = set(inspector.get_table_names())
            checks["missing_tables"] = sorted(set(required_tables) - existing)
            checks["existing_required_tables"] = sorted(set(required_tables) & existing)
            for name, model in required_tables.items():
                checks[name] = db.query(model).count() if name in existing else None
            checks["year_frequency_coverage"] = bool(checks.get("topic_year_frequency"))
            checks["ranking_inputs"] = (
                checks.get("topics", 0) > 0 and checks["year_frequency_coverage"]
            )
        status = "ok" if not checks["missing_tables"] else "degraded"
        return {"status": status, "database": True, "checks": checks}
    except Exception as exc:
        return {"status": "degraded", "database": False, "error": str(exc)[:500], "checks": checks}


@app.get("/", include_in_schema=False)
def root():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"status": "ok", "docs": "/docs"}
