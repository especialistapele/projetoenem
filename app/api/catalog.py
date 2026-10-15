from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import KnowledgeArea, Subject
from sqlalchemy import text

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/areas")
def list_areas(db: Session = Depends(get_db)):
    return db.query(KnowledgeArea).order_by(KnowledgeArea.id).all()


@router.get("/subjects")
def list_subjects(area_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(Subject)
    if area_id:
        query = query.filter(Subject.knowledge_area_id == area_id)
    return query.order_by(Subject.name).all()

@router.get("/taxonomy")
def taxonomy(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT tv.code AS taxonomy_version, ka.code AS area_code, ka.name AS area,
               c.code AS competency_code, c.name AS competency,
               sd.code AS skill_code, sd.description AS skill_description,
               sd.source_status AS source_status
        FROM public.taxonomy_versions tv
        JOIN public.competencies c ON c.taxonomy_version_id = tv.id
        JOIN public.knowledge_areas ka ON ka.id = c.knowledge_area_id
        LEFT JOIN public.skill_definitions sd ON sd.competency_id = c.id
        ORDER BY ka.code, c.code, sd.code
    """)).mappings().all()
    return [dict(row) for row in rows]


@router.get("/taxonomy/summary")
def taxonomy_summary(db: Session = Depends(get_db)):
    row = db.execute(__import__('sqlalchemy').text("""
        SELECT
          (SELECT count(*) FROM knowledge_areas WHERE code IN ('LC','CH','CN','MT')) AS areas,
          (SELECT count(*) FROM competencies) AS competencies,
          (SELECT count(*) FROM skill_definitions) AS skills,
          (SELECT count(*) FROM knowledge_objects) AS knowledge_objects
    """)).mappings().one()
    return dict(row)
