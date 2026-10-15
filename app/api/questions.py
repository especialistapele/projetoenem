from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Alternative, Question, QuestionTopic

router = APIRouter(prefix="/questions", tags=["questions"])

def _question_public(question: Question):
    return {
        "id": question.id,
        "exam_id": question.exam_id,
        "subject_id": question.subject_id,
        "number": question.number,
        "statement_text": question.statement_text,
        "exam": question.exam,
        "alternatives": [
            {"id": a.id, "letter": a.letter, "text": a.text}
            for a in question.alternatives
        ],
    }


@router.get("")
def list_questions(
    year: int | None = None,
    subject_id: int | None = None,
    topic_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Question).options(joinedload(Question.exam), joinedload(Question.alternatives))
    if subject_id:
        query = query.filter(Question.subject_id == subject_id)
    if year:
        query = query.join(Question.exam).filter_by(year=year)
    if topic_id:
        query = query.join(QuestionTopic, QuestionTopic.question_id == Question.id).filter(QuestionTopic.topic_id == topic_id)
    total = query.order_by(None).count()
    items = query.order_by(Question.id).offset(offset).limit(limit).all()
    return {"total": total, "limit": limit, "offset": offset, "items": [_question_public(q) for q in items]}


@router.get("/search")
def search_questions(term: str = Query(..., min_length=2), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    sql = text("""
        SELECT q.id, q.exam_id, q.number, q.statement_text,
               e.year, e.color,
               ts_rank(q.search_vector, plainto_tsquery('portuguese', :term)) AS rank
        FROM questions q
        JOIN exams e ON e.id = q.exam_id
        WHERE q.search_vector @@ plainto_tsquery('portuguese', :term)
        ORDER BY rank DESC, e.year DESC, q.number
        LIMIT :limit
    """)
    result = db.execute(sql, {"term": term, "limit": limit})
    return [dict(row._mapping) for row in result]


@router.get("/{question_id}")
def get_question(question_id: int, db: Session = Depends(get_db)):
    question = (
        db.query(Question)
        .options(joinedload(Question.exam), joinedload(Question.alternatives))
        .filter(Question.id == question_id)
        .first()
    )
    if not question:
        raise HTTPException(status_code=404, detail="Questão não encontrada")
    topics = db.query(QuestionTopic).filter(QuestionTopic.question_id == question_id).all()
    return {"question": _question_public(question), "topics": topics}
