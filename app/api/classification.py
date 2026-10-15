from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Question
from app.services.classifier import classify_question
from app.supabase_auth import require_admin

router = APIRouter(prefix="/classification", tags=["classification"])

class ClassificationInput(BaseModel):
    text: str = Field(min_length=3)

@router.post("/preview")
def preview(payload: ClassificationInput):
    return classify_question(payload.text)

@router.get("/coverage")
def coverage(db: Session = Depends(get_db)):
    questions = db.query(Question).all()
    classified = 0
    high_confidence = 0
    for q in questions:
        result = classify_question(q.statement_text)
        if result["subject"]:
            classified += 1
        if result["confidence"] >= 0.70:
            high_confidence += 1
    total = len(questions)
    return {"total_questions": total, "classified": classified, "classification_rate": classified / total if total else 0.0, "high_confidence": high_confidence, "high_confidence_rate": high_confidence / total if total else 0.0, "mode": "heuristic_auditavel"}

@router.post("/generate-candidates")
def generate_candidates(limit: int = Query(1000, ge=1, le=10000), db: Session = Depends(get_db), _admin=Depends(require_admin)):
    questions = db.query(Question).order_by(Question.id).limit(limit).all()
    created = 0
    for q in questions:
        result = classify_question(q.statement_text)
        status = "accepted" if result["confidence"] >= 0.85 else ("review" if result["confidence"] >= 0.60 else "pending")
        exists = db.execute(text("SELECT 1 FROM public.question_classification_candidates WHERE question_id=:qid AND classifier_version=:v LIMIT 1"), {"qid": q.id, "v": "heuristic-v1"}).first()
        if exists:
            continue
        db.execute(text("""INSERT INTO public.question_classification_candidates
            (question_id, area, discipline, confidence, classifier_version, status, evidence)
            VALUES (:qid,:area,:discipline,:confidence,:version,:status,cast(:evidence AS jsonb))"""), {
            "qid": q.id, "area": result.get("area"), "discipline": result.get("subject"),
            "confidence": result.get("confidence", 0), "version": "heuristic-v1", "status": status,
            "evidence": '{"keywords": ' + __import__('json').dumps(result.get('keywords', []), ensure_ascii=False) + '}'
        })
        created += 1
    db.commit()
    return {"processed": len(questions), "created": created}

@router.get("/candidates")
def candidates(status: str | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db), _admin=Depends(require_admin)):
    where = "WHERE c.status=:status" if status else ""
    params = {"limit": limit, "offset": offset}
    if status: params["status"] = status
    rows = db.execute(text(f"""SELECT c.id, c.question_id, left(q.statement_text, 700) AS statement,
        c.area, c.discipline, c.competency, c.skill, c.topic_id, c.confidence,
        c.classifier_version, c.status, c.evidence, c.created_at
        FROM public.question_classification_candidates c
        JOIN public.questions q ON q.id=c.question_id {where}
        ORDER BY c.confidence DESC, c.id DESC LIMIT :limit OFFSET :offset"""), params).mappings().all()
    total = db.execute(text(f"SELECT count(*) FROM public.question_classification_candidates c {where}"), params).scalar_one()
    return {"items": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}

class CandidateDecision(BaseModel):
    status: str = Field(pattern="^(accepted|rejected|review|pending)$")

@router.patch("/candidates/{candidate_id}")
def decide_candidate(candidate_id: int, payload: CandidateDecision, db: Session = Depends(get_db), admin=Depends(require_admin)):
    row = db.execute(text("SELECT id, question_id, area, discipline, competency, skill, topic_id FROM public.question_classification_candidates WHERE id=:id"), {"id": candidate_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Candidato não encontrado.")
    db.execute(text("UPDATE public.question_classification_candidates SET status=:status, reviewed_at=now(), reviewed_by=:uid WHERE id=:id"), {"status": payload.status, "uid": admin.get("id"), "id": candidate_id})
    if payload.status == "accepted":
        db.execute(text("""UPDATE public.questions SET subject_id=(SELECT id FROM public.subjects WHERE name=:discipline LIMIT 1),
            taxonomy_skill_id=(SELECT id FROM public.skill_definitions WHERE name=:skill LIMIT 1)
            WHERE id=:qid"""), {"discipline": row["discipline"], "skill": row["skill"], "qid": row["question_id"]})
    db.commit()
    return {"ok": True, "candidate_id": candidate_id, "status": payload.status}
