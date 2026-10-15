from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import QuestionAttempt, StudentTopicPerformance, Question, QuestionTopic, Topic, Exam, Program
from app.supabase_auth import get_current_supabase_user

router = APIRouter(prefix='/student', tags=['student'])

class AttemptIn(BaseModel):
    question_id: int
    selected_letter: str = Field(min_length=1, max_length=1)
    seconds_spent: int | None = Field(default=None, ge=0, le=7200)


def _user_id(user):
    try:
        return user['id']
    except Exception:
        raise HTTPException(401, 'Usuário não autenticado.')


def _refresh_topic_performance(db: Session, user_id: str, topic_id: int):
    attempts = (db.query(QuestionAttempt)
        .join(Question, Question.id == QuestionAttempt.question_id)
        .join(QuestionTopic, QuestionTopic.question_id == Question.id)
        .filter(QuestionAttempt.user_id == user_id, QuestionTopic.topic_id == topic_id).all())
    total = len(attempts)
    correct = sum(1 for a in attempts if a.is_correct)
    accuracy = correct / total if total else 0
    perf = db.query(StudentTopicPerformance).filter_by(user_id=user_id, topic_id=topic_id).first()
    if not perf:
        perf = StudentTopicPerformance(user_id=user_id, topic_id=topic_id)
        db.add(perf)
    perf.attempt_count = total
    perf.correct_count = correct
    perf.accuracy = accuracy
    perf.last_attempt_at = max((a.created_at for a in attempts if a.created_at), default=None)
    return perf



class ProgramSelectionIn(BaseModel):
    program_id: int | None = None

@router.get('/program')
def get_program(db: Session = Depends(get_db), user=Depends(get_current_supabase_user)):
    row=db.execute(__import__('sqlalchemy').text("SELECT program_id FROM public.user_profiles WHERE user_id=:uid"), {'uid':_user_id(user)}).first()
    program_id=row[0] if row else None
    p=db.query(Program).filter_by(id=program_id).first() if program_id else None
    return {'program_id':program_id,'program':{'id':p.id,'name':p.name,'institution':p.institution.name if p.institution else None} if p else None}

@router.put('/program')
def set_program(payload: ProgramSelectionIn, db: Session = Depends(get_db), user=Depends(get_current_supabase_user)):
    uid=_user_id(user)
    if payload.program_id is not None and not db.query(Program).filter_by(id=payload.program_id).first():
        raise HTTPException(404,'Curso não encontrado.')
    db.execute(__import__('sqlalchemy').text("""
        INSERT INTO public.user_profiles (user_id, role, program_id, display_name)
        SELECT u.id,
               CASE WHEN u.raw_app_meta_data->>'role' IN ('admin','teacher','student') THEN u.raw_app_meta_data->>'role' ELSE 'student' END,
               :pid,
               COALESCE(NULLIF(u.raw_user_meta_data->>'display_name',''), NULLIF(split_part(COALESCE(u.email,''),'@',1),''), 'Usuário')
        FROM auth.users u WHERE u.id=:uid
        ON CONFLICT (user_id) DO UPDATE SET program_id=EXCLUDED.program_id, updated_at=now()
    """), {'pid':payload.program_id,'uid':uid})
    db.commit(); return {'program_id':payload.program_id}

@router.post('/attempts')
def record_attempt(payload: AttemptIn, db: Session = Depends(get_db), user=Depends(get_current_supabase_user)):
    uid = _user_id(user)
    q = db.query(Question).filter(Question.id == payload.question_id).first()
    if not q:
        raise HTTPException(404, 'Questão não encontrada.')
    letter = payload.selected_letter.upper()
    correct = any(a.letter.upper() == letter and a.is_correct for a in q.alternatives)
    attempt = QuestionAttempt(user_id=uid, question_id=q.id, selected_letter=letter, is_correct=correct, seconds_spent=payload.seconds_spent)
    db.add(attempt)
    topic_ids = [x.topic_id for x in db.query(QuestionTopic).filter_by(question_id=q.id).all()]
    for topic_id in topic_ids:
        _refresh_topic_performance(db, uid, topic_id)
    db.commit()
    return {'id': attempt.id, 'question_id': q.id, 'is_correct': correct, 'topic_ids': topic_ids}


@router.get('/performance')
def performance(db: Session = Depends(get_db), user=Depends(get_current_supabase_user)):
    uid = _user_id(user)
    rows = db.query(StudentTopicPerformance).filter_by(user_id=uid).order_by(StudentTopicPerformance.accuracy.asc(), StudentTopicPerformance.attempt_count.desc()).all()
    attempts = db.query(QuestionAttempt).filter_by(user_id=uid).count()
    correct = db.query(QuestionAttempt).filter_by(user_id=uid, is_correct=True).count()
    return {'summary': {'attempts': attempts, 'correct': correct, 'accuracy': correct / attempts if attempts else 0}, 'topics': [
        {'topic_id': r.topic_id, 'topic_name': r.topic.name if r.topic else None, 'attempt_count': r.attempt_count, 'correct_count': r.correct_count, 'accuracy': float(r.accuracy or 0), 'last_attempt_at': r.last_attempt_at.isoformat() if r.last_attempt_at else None}
        for r in rows
    ]}


@router.get('/study-plan')
def personalized_study_plan(program_id: int, limit: int = Query(10, ge=1, le=30), db: Session = Depends(get_db), user=Depends(get_current_supabase_user)):
    uid = _user_id(user)
    from app.models import TopicPredictionResult
    predictions = db.query(TopicPredictionResult).filter_by(program_id=program_id).order_by(TopicPredictionResult.rank).limit(100).all()
    result = []
    for p in predictions:
        perf = db.query(StudentTopicPerformance).filter_by(user_id=uid, topic_id=p.topic_id).first()
        accuracy = float(perf.accuracy) if perf else 0.0
        attempts = perf.attempt_count if perf else 0
        gap = 1.0 - accuracy
        personalized = float(p.probability) * (0.55 + 0.45 * gap)
        qrows = (db.query(Question, Exam.year).join(QuestionTopic, QuestionTopic.question_id == Question.id).join(Exam, Exam.id == Question.exam_id)
                 .filter(QuestionTopic.topic_id == p.topic_id).order_by(Exam.year.desc(), Question.number).limit(3).all())
        result.append({'topic_id': p.topic_id, 'topic_name': p.topic.name if p.topic else None, 'prediction_probability': float(p.probability), 'student_accuracy': accuracy, 'attempt_count': attempts, 'knowledge_gap': gap, 'personalized_priority': personalized, 'questions': [{'id': q.id, 'number': q.number, 'year': year, 'statement': q.statement_text[:180] if q.statement_text else ''} for q, year in qrows]})
    result.sort(key=lambda x: x['personalized_priority'], reverse=True)
    for i, item in enumerate(result[:limit], 1):
        item['rank'] = i
        item['recommendation'] = 'Urgente' if item['knowledge_gap'] >= 0.75 else ('Alta' if item['knowledge_gap'] >= 0.45 else 'Manutenção')
    return result[:limit]
