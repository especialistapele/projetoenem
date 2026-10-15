from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

Base = declarative_base()

engine = None
SessionLocal = None
_database_init_error = None

if settings.database_url:
    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    except Exception as exc:
        _database_init_error = str(exc)



def get_db():
    if SessionLocal is None:
        raise RuntimeError(
            "DATABASE_URL não configurada. Informe a connection string do Supabase no arquivo .env."
        )
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def database_status():
    return {"configured": bool(settings.database_url), "available": SessionLocal is not None, "init_error": _database_init_error}
