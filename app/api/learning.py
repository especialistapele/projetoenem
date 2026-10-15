from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy import text, func
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models import Exam, Question, Alternative, QuestionAttempt, StudentTopicPerformance, Topic, QuestionTopic, KnowledgeArea, Program, TopicYearFrequency, Simulation, SimulationQuestion, SimulationAttempt, EssaySubmission, EssayReview, Subject
from app.supabase_auth import get_current_supabase_user, require_admin
from app.services.tri_estimator import estimate

router = APIRouter(prefix="/learning", tags=["learning"])

def uid(user): return user.get("id")


def simulation_exam_year(cycle_year: int, sequence: int) -> int:
    """Sequences 1–3 use the three most recent complete official exams before the cycle year."""
    return cycle_year - sequence


def simulation_readiness_status(target_count: int, generated_count: int) -> str:
    if target_count > 0 and generated_count == target_count:
        return "ready"
    if generated_count == 0:
        return "not_generated"
    return "incomplete"

def require_teacher(authorization: Optional[str] = Header(default=None)):
    user = get_current_supabase_user(authorization)
    role = (user.get("app_metadata") or {}).get("role")
    if role not in ("teacher", "admin"):
        raise HTTPException(403, "Acesso restrito ao professor.")
    return user

class AttemptIn(BaseModel):
    question_id:int
    selected_letter:str=Field(min_length=1,max_length=1)
    seconds_spent:Optional[int]=Field(default=None,ge=0,le=7200)

class EssayIn(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    content_text:str=Field(min_length=50)

class ReviewIn(BaseModel):
    score:float=Field(ge=0,le=1000)
    competency_1:float=Field(ge=0,le=200)
    competency_2:float=Field(ge=0,le=200)
    competency_3:float=Field(ge=0,le=200)
    competency_4:float=Field(ge=0,le=200)
    competency_5:float=Field(ge=0,le=200)
    strengths:str=""
    improvements:str=""
    feedback:str=""

@router.get("/programs")
def learning_programs(db:Session=Depends(get_db)):
    return [{"id":p.id,"name":p.name,"institution":p.institution.name if p.institution else None} for p in db.query(Program).options(joinedload(Program.institution)).order_by(Program.name).all()]

@router.post("/attempts")
def answer_question(payload:AttemptIn, user=Depends(get_current_supabase_user), db:Session=Depends(get_db)):
    q=db.query(Question).options(joinedload(Question.alternatives)).filter(Question.id==payload.question_id).first()
    if not q: raise HTTPException(404,"Questão não encontrada")
    letter=payload.selected_letter.upper()
    if not any(a.letter.upper()==letter for a in q.alternatives): raise HTTPException(422,"Alternativa inválida para esta questão")
    correct=next((a.is_correct for a in q.alternatives if a.letter.upper()==letter),False)
    attempt=QuestionAttempt(user_id=uid(user),question_id=q.id,selected_letter=letter,is_correct=bool(correct),seconds_spent=payload.seconds_spent)
    db.add(attempt)
    topics=db.query(QuestionTopic).filter(QuestionTopic.question_id==q.id).all()
    for qt in topics:
        perf=db.query(StudentTopicPerformance).filter_by(user_id=uid(user),topic_id=qt.topic_id).first()
        if not perf:
            perf=StudentTopicPerformance(user_id=uid(user),topic_id=qt.topic_id,attempt_count=0,correct_count=0,accuracy=0)
            db.add(perf)
        perf.attempt_count += 1; perf.correct_count += int(bool(correct)); perf.accuracy=perf.correct_count/perf.attempt_count; perf.last_attempt_at=datetime.now(timezone.utc)
    db.commit()
    return {"question_id":q.id,"selected_letter":letter,"is_correct":bool(correct),"correct_letter":next((a.letter for a in q.alternatives if a.is_correct),None)}

@router.get("/simulations")
def simulations(db:Session=Depends(get_db)):
    rows=db.query(Simulation).order_by(Simulation.cycle_year,Simulation.sequence).all()
    result = []
    for s in rows:
        generated = db.query(SimulationQuestion).filter_by(simulation_id=s.id).count()
        result.append({
            "id": s.id, "cycle_year": s.cycle_year, "sequence": s.sequence,
            "title": s.title, "scheduled_at": s.scheduled_at.isoformat() if s.scheduled_at else None,
            "question_count": s.question_count, "generated_question_count": generated,
            "status": simulation_readiness_status(s.question_count, generated),
            "stored_status": s.status,
        })
    return result

@router.post("/simulations/seed")
def seed_simulations(user=Depends(require_admin), db:Session=Depends(get_db)):
    year=datetime.now().year
    created=[]
    for seq in (1,2,3):
        s=db.query(Simulation).filter_by(cycle_year=year,sequence=seq).first()
        if not s:
            s=Simulation(cycle_year=year,sequence=seq,title=f"Simulado {seq} — ciclo {year}",question_count=180,status="scheduled")
            db.add(s); created.append(seq)
    db.commit(); return {"created":created,"cycle_year":year}

@router.get("/simulations/{simulation_id}")
def simulation_detail(simulation_id:int, db:Session=Depends(get_db)):
    s=db.query(Simulation).filter(Simulation.id==simulation_id).first()
    if not s: raise HTTPException(404,"Simulado não encontrado")
    qs=(db.query(SimulationQuestion).filter_by(simulation_id=simulation_id).order_by(SimulationQuestion.position).all())
    return {"id":s.id,"title":s.title,"question_count":s.question_count,"generated_questions":len(qs),"questions":[q.question_id for q in qs]}

@router.post("/simulations/{simulation_id}/generate")
def generate_simulation(simulation_id:int,user=Depends(require_admin),db:Session=Depends(get_db)):
    s=db.query(Simulation).filter_by(id=simulation_id).first()
    if not s: raise HTTPException(404,"Simulado não encontrado")
    existing_count = db.query(SimulationQuestion).filter_by(simulation_id=simulation_id).count()
    if existing_count == s.question_count and existing_count > 0:
        return {"status": "already_generated", "questions": existing_count}
    if existing_count:
        raise HTTPException(
            409,
            f"Seleção parcial encontrada: {existing_count}/{s.question_count} questões. "
            "O simulado não será marcado como pronto; revise a seleção existente."
        )
    # Each simulation uses a distinct official exam year: sequence 1=previous year,
    # sequence 2=two years back, sequence 3=three years back.
    exam_year = simulation_exam_year(s.cycle_year, s.sequence)
    areas=db.query(KnowledgeArea).filter(KnowledgeArea.code.in_(["LC","CH","CN","MT"])).order_by(KnowledgeArea.id).all()
    if len(areas) != 4:
        raise HTTPException(409,"Taxonomia de áreas incompleta; importe as quatro áreas oficiais antes de gerar simulados.")
    selected=[]
    for area in areas:
        day = 1 if area.code in ("LC", "CH") else 2
        color = "azul" if day == 1 or exam_year >= 2025 else "amarelo"
        ids=[r[0] for r in db.query(Question.id)
             .join(Exam, Question.exam_id==Exam.id)
             .join(Subject, Question.subject_id==Subject.id)
             .join(Alternative, Alternative.question_id==Question.id)
             .filter(
                 Exam.year==exam_year,
                 Exam.edition=="regular",
                 Exam.day==day,
                 Exam.color.ilike(color),
                 Subject.knowledge_area_id==area.id,
             )
             .group_by(Question.id)
             .having(func.count(Alternative.id)==5, func.count(Alternative.id).filter(Alternative.is_correct.is_(True))==1)
             .order_by(Question.number)
             .limit(45).all()]
        selected.extend(ids)
    selected=list(dict.fromkeys(selected))[:min(180, s.question_count)]
    if len(selected)<s.question_count:
        raise HTTPException(409,f"Banco insuficiente para um simulado completo: {len(selected)}/{s.question_count} questões classificadas disponíveis.")
    for idx,qid in enumerate(selected,1): db.add(SimulationQuestion(simulation_id=simulation_id,question_id=qid,position=idx))
    s.status="ready"; db.commit(); return {"status":"ready","questions":len(selected)}

@router.get("/essays")
def my_essays(user=Depends(get_current_supabase_user),db:Session=Depends(get_db)):
    rows=db.query(EssaySubmission).filter_by(user_id=uid(user)).order_by(EssaySubmission.submitted_at.desc()).all()
    return [{"id":e.id,"title":e.title,"submitted_at":e.submitted_at.isoformat(),"status":e.status,"score":e.review.score if e.review else None,"reviewed_at":e.review.reviewed_at.isoformat() if e.review and e.review.reviewed_at else None} for e in rows]

@router.post("/essays")
def submit_essay(payload:EssayIn,user=Depends(get_current_supabase_user),db:Session=Depends(get_db)):
    month=datetime.now(timezone.utc).strftime("%Y-%m")
    exists=db.query(EssaySubmission).filter(EssaySubmission.user_id==uid(user),func.to_char(EssaySubmission.submitted_at,'YYYY-MM')==month).first()
    if exists: raise HTTPException(409,"Você já enviou uma redação neste mês.")
    e=EssaySubmission(user_id=uid(user),title=payload.title,content_text=payload.content_text,status="pending")
    db.add(e);db.commit();db.refresh(e);return {"id":e.id,"status":e.status,"deadline":e.submitted_at.replace(tzinfo=timezone.utc).isoformat()}

@router.get("/teacher/essays")
def teacher_essays(status:Optional[str]=None,user=Depends(require_teacher),db:Session=Depends(get_db)):
    q=db.query(EssaySubmission).order_by(EssaySubmission.submitted_at.asc())
    role=(user.get('app_metadata') or {}).get('role')
    if role != 'admin':
        q=q.filter(text("essay_submissions.user_id IN (SELECT student_id FROM public.teacher_students WHERE teacher_id = :tid AND active = true)")).params(tid=uid(user))
    if status:q=q.filter(EssaySubmission.status==status)
    rows=q.limit(200).all();return [{"id":e.id,"user_id":e.user_id,"title":e.title,"submitted_at":e.submitted_at.isoformat(),"status":e.status,"deadline_days":max(0,7-(datetime.now(timezone.utc)-e.submitted_at.replace(tzinfo=timezone.utc)).days)} for e in rows]

@router.get("/teacher/essays/{essay_id}")
def teacher_essay(essay_id:int,user=Depends(require_teacher),db:Session=Depends(get_db)):
    e=db.query(EssaySubmission).filter_by(id=essay_id).first()
    if not e: raise HTTPException(404,"Redação não encontrada")
    role=(user.get('app_metadata') or {}).get('role')
    if role != 'admin':
        assigned=db.execute(text("SELECT 1 FROM public.teacher_students WHERE teacher_id=:tid AND student_id=:sid AND active=true"),{'tid':uid(user),'sid':e.user_id}).first()
        if not assigned: raise HTTPException(403,"Você não tem vínculo ativo com este estudante.")
    review={k:v for k,v in e.review.__dict__.items() if not k.startswith('_')} if e.review else None
    return {"id":e.id,"user_id":e.user_id,"title":e.title,"content_text":e.content_text,"submitted_at":e.submitted_at.isoformat(),"status":e.status,"review":review}

@router.post("/teacher/essays/{essay_id}/review")
def review_essay(essay_id:int,payload:ReviewIn,user=Depends(require_teacher),db:Session=Depends(get_db)):
    e=db.query(EssaySubmission).filter_by(id=essay_id).first()
    if not e: raise HTTPException(404,"Redação não encontrada")
    role=(user.get('app_metadata') or {}).get('role')
    if role != 'admin':
        assigned=db.execute(text("SELECT 1 FROM public.teacher_students WHERE teacher_id=:tid AND student_id=:sid AND active=true"),{'tid':uid(user),'sid':e.user_id}).first()
        if not assigned: raise HTTPException(403,"Você não tem vínculo ativo com este estudante.")
    r=e.review or EssayReview(essay_id=e.id)
    r.reviewer_id=uid(user);r.score=payload.score;r.competency_1=payload.competency_1;r.competency_2=payload.competency_2;r.competency_3=payload.competency_3;r.competency_4=payload.competency_4;r.competency_5=payload.competency_5;r.strengths=payload.strengths;r.improvements=payload.improvements;r.feedback=payload.feedback;r.reviewed_at=datetime.now(timezone.utc)
    if not e.review: db.add(r)
    e.status="reviewed";db.commit();return {"status":"reviewed","essay_id":e.id,"score":r.score}

@router.get("/simulations/{simulation_id}/questions")
def simulation_questions(simulation_id:int, user=Depends(get_current_supabase_user), db:Session=Depends(get_db)):
    rows=(db.query(SimulationQuestion, Question)
          .join(Question, Question.id==SimulationQuestion.question_id)
          .filter(SimulationQuestion.simulation_id==simulation_id)
          .order_by(SimulationQuestion.position).all())
    return [{"position":a.position,"question_id":q.id,"number":q.number,"statement_text":q.statement_text,"alternatives":[{"letter":x.letter,"text":x.text} for x in q.alternatives]} for a,q in rows]

class SimulationAnswerIn(BaseModel):
    question_id:int
    selected_letter:str=Field(min_length=1,max_length=1)
    seconds_spent:Optional[int]=Field(default=None,ge=0,le=7200)

@router.post("/simulations/{simulation_id}/answer")
def simulation_answer(simulation_id:int,payload:SimulationAnswerIn,user=Depends(get_current_supabase_user),db:Session=Depends(get_db)):
    membership=db.query(SimulationQuestion).filter_by(simulation_id=simulation_id,question_id=payload.question_id).first()
    if not membership: raise HTTPException(404,"Questão não pertence a este simulado")
    q=db.query(Question).options(joinedload(Question.alternatives)).filter_by(id=payload.question_id).first()
    if not q: raise HTTPException(404,"Questão não encontrada")
    letter=payload.selected_letter.upper()
    if not any(x.letter.upper()==letter for x in q.alternatives): raise HTTPException(422,"Alternativa inválida para esta questão")
    correct=next((x.is_correct for x in q.alternatives if x.letter.upper()==letter),False)
    a=db.query(SimulationAttempt).filter_by(simulation_id=simulation_id,question_id=payload.question_id,user_id=uid(user)).first()
    if not a:
        a=SimulationAttempt(simulation_id=simulation_id,question_id=payload.question_id,position=membership.position,user_id=uid(user))
        db.add(a)
    a.selected_letter=letter;a.is_correct=bool(correct);a.seconds_spent=payload.seconds_spent;a.answered_at=datetime.now(timezone.utc)
    db.commit();return {"is_correct":bool(correct)}

@router.get("/simulations/{simulation_id}/result")
def simulation_result(simulation_id:int,user=Depends(get_current_supabase_user),db:Session=Depends(get_db)):
    s=db.query(Simulation).filter_by(id=simulation_id).first()
    if not s: raise HTTPException(404,"Simulado não encontrado")
    rows=db.query(SimulationAttempt).filter_by(simulation_id=simulation_id,user_id=uid(user)).all()
    total=len(rows);correct=sum(bool(x.is_correct) for x in rows)
    area_rows=db.execute(text("""SELECT ka.id, ka.name, COUNT(sa.id) total, COUNT(sa.id) FILTER (WHERE sa.is_correct) correct
      FROM simulation_attempts sa JOIN questions q ON q.id=sa.question_id JOIN subjects su ON su.id=q.subject_id JOIN knowledge_areas ka ON ka.id=su.knowledge_area_id
      WHERE sa.simulation_id=:sid AND sa.user_id=:uid GROUP BY ka.id,ka.name ORDER BY ka.id"""),{"sid":simulation_id,"uid":uid(user)}).fetchall()
    breakdown=[{"area_id":r[0],"area":r[1],"total":r[2],"correct":r[3],"accuracy":(r[3]/r[2]) if r[2] else 0} for r in area_rows]
    comp_rows=db.execute(text("""SELECT c.code,c.name,COUNT(sa.id) total,COUNT(sa.id) FILTER (WHERE sa.is_correct) correct
      FROM simulation_attempts sa JOIN questions q ON q.id=sa.question_id JOIN competencies c ON c.id=q.taxonomy_competency_id
      WHERE sa.simulation_id=:sid AND sa.user_id=:uid GROUP BY c.code,c.name ORDER BY c.code"""),{"sid":simulation_id,"uid":uid(user)}).fetchall()
    competencies=[{"code":r[0],"name":r[1],"total":r[2],"correct":r[3],"accuracy":(r[3]/r[2]) if r[2] else 0} for r in comp_rows]
    # TRI 3PL estimativa por área, usando parâmetros estimados quando disponíveis.
    tri_rows=db.execute(text("""SELECT ka.id area_id,ka.name area_name,sa.is_correct,
      COALESCE(tp.discrimination_a,1.0) a,COALESCE(tp.difficulty_b,COALESCE(q.difficulty_estimate,0)) b,COALESCE(tp.guessing_c,0.20) c
      FROM simulation_attempts sa JOIN questions q ON q.id=sa.question_id JOIN subjects su ON su.id=q.subject_id JOIN knowledge_areas ka ON ka.id=su.knowledge_area_id
      LEFT JOIN item_tri_parameters tp ON tp.question_id=q.id WHERE sa.simulation_id=:sid AND sa.user_id=:uid"""),{"sid":simulation_id,"uid":uid(user)}).mappings().all()
    from app.services.tri_estimator import _p
    tri_areas=[]
    for area_id,items in __import__('itertools').groupby(sorted(tri_rows,key=lambda x:x['area_id']),key=lambda x:x['area_id']):
        items=list(items);theta=0.0
        for _ in range(15):
            grad=hess=0.0
            for r in items:
                aa,bb,cc=float(r['a']),float(r['b']),float(r['c']);pp=_p(theta,aa,bb,cc);xx=1 if r['is_correct'] else 0;vv=max(pp*(1-pp),1e-5)
                grad+=aa*(xx-pp)*(1-cc)/vv;hess-=aa*aa*(1-cc)/vv
            if abs(hess)<1e-8:break
            step=grad/hess;theta=max(-4,min(4,theta-step))
            if abs(step)<1e-4:break
        tri_areas.append({"area_id":area_id,"area_name":items[0]['area_name'],"theta":round(theta,4),"estimated_score":round(max(200,min(900,500+theta*100)),1),"item_count":len(items)})
    estimated_score=round(sum(x['estimated_score'] for x in tri_areas)/len(tri_areas),1) if tri_areas else None
    return {"simulation_id":simulation_id,"title":s.title,"answered":total,"correct":correct,"accuracy":(correct/total if total else 0),"estimated_score":estimated_score,"score_note":"TRI 3PL estimativa pedagógica; não é a nota oficial TRI do ENEM.","areas":breakdown,"tri_areas":tri_areas,"competencies":competencies}

@router.get("/dashboard/history")
def dashboard_history(user=Depends(get_current_supabase_user),db:Session=Depends(get_db)):
    sims=db.query(Simulation).order_by(Simulation.cycle_year,Simulation.sequence).all()
    sim_out=[]
    for s in sims:
        rows=db.query(SimulationAttempt).filter_by(simulation_id=s.id,user_id=uid(user)).all(); total=len(rows); correct=sum(bool(x.is_correct) for x in rows)
        sim_out.append({"sequence":s.sequence,"title":s.title,"answered":total,"correct":correct,"accuracy":correct/total if total else 0,"estimated_score":round(300+(correct/total)*400,1) if total else None,"score_note":"Estimativa linear simplificada para acompanhamento; não representa a nota oficial TRI do ENEM."})
    essays=db.query(EssaySubmission).options(joinedload(EssaySubmission.review)).filter_by(user_id=uid(user)).order_by(EssaySubmission.submitted_at).all()
    essay_out=[{"title":e.title,"submitted_at":e.submitted_at.isoformat(),"score":float(e.review.score) if e.review else None,"status":e.status} for e in essays]
    return {"simulations":sim_out,"essays":essay_out}

# --- Ciclo diagnóstico e prioridades (Fase avançada) ---
class ProficiencyStartInV2(BaseModel):
    question_count: int = Field(default=40, ge=10, le=180)

class ProficiencyAnswerInV2(BaseModel):
    question_id: int
    selected_letter: str = Field(min_length=1, max_length=1)

class PriorityCompleteInV2(BaseModel):
    completed: bool = True

@router.post("/proficiency/start")
def start_proficiency_v2(payload: ProficiencyStartInV2, user=Depends(get_current_supabase_user), db:Session=Depends(get_db)):
    from app.models import ProficiencyAssessment, ProficiencyAssessmentItem
    uidv=uid(user)
    active=db.query(ProficiencyAssessment).filter_by(user_id=uidv,status='in_progress').first()
    if active:
        items=db.query(ProficiencyAssessmentItem).filter_by(assessment_id=active.id).order_by(ProficiencyAssessmentItem.position).all()
        return {"assessment_id":active.id,"status":"in_progress","question_count":len(items),"items":[{"position":i.position,"question_id":i.question_id} for i in items]}
    a=ProficiencyAssessment(user_id=uidv,title='Teste de proficiência inicial',status='in_progress',question_count=0)
    db.add(a);db.flush()
    qids=[r[0] for r in db.query(Question.id).join(Alternative, Alternative.question_id==Question.id).group_by(Question.id)
          .having(func.count(Alternative.id)>=2, func.count(Alternative.id).filter(Alternative.is_correct.is_(True))==1)
          .order_by(func.random()).limit(payload.question_count).all()]
    if not qids:
        db.rollback()
        raise HTTPException(409,'Não há questões com alternativas e gabarito válidos para iniciar o diagnóstico.')
    for pos,qid in enumerate(qids,1): db.add(ProficiencyAssessmentItem(assessment_id=a.id,question_id=qid,position=pos))
    a.question_count=len(qids);db.commit()
    return {"assessment_id":a.id,"status":a.status,"question_count":a.question_count,"items":[{"position":i.position,"question_id":i.question_id} for i in db.query(ProficiencyAssessmentItem).filter_by(assessment_id=a.id).order_by(ProficiencyAssessmentItem.position).all()]}

@router.get("/proficiency/{assessment_id}/questions")
def proficiency_questions_v2(assessment_id:int,user=Depends(get_current_supabase_user),db:Session=Depends(get_db)):
    from app.models import ProficiencyAssessment, ProficiencyAssessmentItem
    a=db.query(ProficiencyAssessment).filter_by(id=assessment_id,user_id=uid(user)).first()
    if not a: raise HTTPException(404,'Teste não encontrado.')
    rows=(db.query(ProficiencyAssessmentItem,Question).join(Question,Question.id==ProficiencyAssessmentItem.question_id)
          .filter(ProficiencyAssessmentItem.assessment_id==assessment_id).order_by(ProficiencyAssessmentItem.position).all())
    return [{"position":i.position,"question_id":q.id,"number":q.number,"statement_text":q.statement_text,
             "selected_letter":i.selected_letter,"alternatives":[{"letter":x.letter,"text":x.text} for x in q.alternatives]}
            for i,q in rows]

@router.post("/proficiency/{assessment_id}/answer")
def proficiency_answer_v2(assessment_id:int,payload:ProficiencyAnswerInV2,user=Depends(get_current_supabase_user),db:Session=Depends(get_db)):
    from app.models import ProficiencyAssessment, ProficiencyAssessmentItem
    a=db.query(ProficiencyAssessment).filter_by(id=assessment_id,user_id=uid(user)).first()
    if not a: raise HTTPException(404,'Teste não encontrado.')
    item=db.query(ProficiencyAssessmentItem).filter_by(assessment_id=assessment_id,question_id=payload.question_id).first()
    if not item: raise HTTPException(404,'Questão não pertence ao teste.')
    q=db.query(Question).options(joinedload(Question.alternatives)).filter_by(id=payload.question_id).first()
    letter=payload.selected_letter.upper()
    if not any(x.letter.upper()==letter for x in q.alternatives): raise HTTPException(422,'Alternativa inválida para esta questão.')
    correct=any(x.letter.upper()==letter and x.is_correct for x in q.alternatives)
    item.selected_letter=letter;item.is_correct=bool(correct);item.answered_at=datetime.now(timezone.utc);db.commit()
    answered=db.query(ProficiencyAssessmentItem).filter_by(assessment_id=assessment_id).filter(ProficiencyAssessmentItem.selected_letter.isnot(None)).count()
    return {"is_correct":bool(correct),"answered":answered,"total":a.question_count}

def _calculate_assessment_result(db,user_id,assessment_id):
    from app.models import ProficiencyAssessmentItem, ProficiencyResult
    rows=db.execute(text('''SELECT i.is_correct, COALESCE(tp.discrimination_a,1.0) a,
      COALESCE(tp.difficulty_b,COALESCE(q.difficulty_estimate,0)) b, COALESCE(tp.guessing_c,0.20) c,
      ka.id area_id,ka.name area_name
      FROM proficiency_assessment_items i JOIN questions q ON q.id=i.question_id
      LEFT JOIN subjects su ON su.id=q.subject_id LEFT JOIN knowledge_areas ka ON ka.id=su.knowledge_area_id
      LEFT JOIN item_tri_parameters tp ON tp.question_id=q.id WHERE i.assessment_id=:aid'''),{'aid':assessment_id}).mappings().all()
    by={}
    for r in rows: by.setdefault(r['area_id'] or 0,[]).append(r)
    from app.services.tri_estimator import _p
    out=[]
    for area_id,items in by.items():
        theta=0.0
        for _ in range(20):
            grad=hess=0.0
            for r in items:
                aa,bb,cc=float(r['a']),float(r['b']),float(r['c']); p=_p(theta,aa,bb,cc); x=1 if r['is_correct'] else 0; v=max(p*(1-p),1e-5)
                grad += aa*(x-p)*(1-cc)/v; hess -= aa*aa*(1-cc)/v
            if abs(hess)<1e-8: break
            step=grad/hess; theta=max(-4,min(4,theta-step))
            if abs(step)<1e-4: break
        acc=sum(bool(x['is_correct']) for x in items)/len(items)
        out.append({"area_id":area_id,"area_name":items[0]['area_name'] or 'Sem área',"theta":round(theta,4),
                    "estimated_score":round(max(200,min(900,500+theta*100)),1),"accuracy":round(acc,4),
                    "item_count":len(items),"model_version":"tri-estimate-v1"})
    db.query(ProficiencyResult).filter_by(assessment_id=assessment_id).delete(synchronize_session=False)
    for x in out:
        db.add(ProficiencyResult(assessment_id=assessment_id,user_id=user_id,knowledge_area_id=x['area_id'] or None,
                                 theta=x['theta'],estimated_score=x['estimated_score'],item_count=x['item_count'],accuracy=x['accuracy']))
    return {"assessment_id":assessment_id,"status":"completed","official_score":False,
            "note":"TRI estimativa pedagógica; não é a nota oficial do ENEM.","areas":out}

@router.post("/proficiency/{assessment_id}/finish")
def finish_proficiency_v2(assessment_id:int,user=Depends(get_current_supabase_user),db:Session=Depends(get_db)):
    from app.models import ProficiencyAssessment, ProficiencyAssessmentItem
    a=db.query(ProficiencyAssessment).filter_by(id=assessment_id,user_id=uid(user)).first()
    if not a: raise HTTPException(404,'Teste não encontrado.')
    items=db.query(ProficiencyAssessmentItem).filter_by(assessment_id=assessment_id).all()
    if not items or any(i.selected_letter is None for i in items): raise HTTPException(409,'Responda todas as questões antes de finalizar.')
    a.status='completed';a.completed_at=datetime.now(timezone.utc)
    result=_calculate_assessment_result(db,uid(user),assessment_id);db.commit();return result

@router.get("/proficiency/estimate")
def proficiency_estimate_v2(user=Depends(get_current_supabase_user),db:Session=Depends(get_db)):
    return estimate(db,uid(user))

@router.get("/priorities")
def learning_priorities_v2(limit:int=Query(15,ge=1,le=50),user=Depends(get_current_supabase_user),db:Session=Depends(get_db)):
    from app.models import StudyPriority
    rows=db.query(StudyPriority).filter_by(user_id=uid(user)).order_by(StudyPriority.completed.asc(),StudyPriority.priority_score.desc()).limit(limit).all()
    return [{"id":r.id,"topic_id":r.topic_id,"topic_name":r.topic.name if r.topic else None,
             "priority_score":float(r.priority_score),"priority_level":r.priority_level,"rationale":r.rationale,"completed":r.completed} for r in rows]

@router.post("/priorities/rebuild")
def rebuild_priorities_v2(user=Depends(get_current_supabase_user),db:Session=Depends(get_db)):
    from app.models import StudyPriority
    uidv=uid(user); perfs={x.topic_id:x for x in db.query(StudentTopicPerformance).filter_by(user_id=uidv).all()}
    topics=db.query(Topic).all(); changed=0
    for t in topics:
        p=perfs.get(t.id); acc=float(p.accuracy) if p else 0.0; attempts=p.attempt_count if p else 0
        freq=db.query(func.coalesce(func.sum(TopicYearFrequency.question_count),0)).filter_by(topic_id=t.id).scalar() or 0
        score=(1-acc)*0.7 + min(float(freq)/20,1)*0.3
        level='urgent' if score>=0.75 else ('high' if score>=0.5 else ('mastered' if acc>=0.85 and attempts>=3 else 'medium'))
        row=db.query(StudyPriority).filter_by(user_id=uidv,topic_id=t.id).first()
        if not row: row=StudyPriority(user_id=uidv,topic_id=t.id);db.add(row)
        row.priority_score=score;row.priority_level=level;row.rationale=f'Domínio atual: {acc:.0%}; tentativas: {attempts}; incidência histórica: {int(freq)} questões.';row.updated_at=datetime.now(timezone.utc);changed+=1
    db.commit();return {"status":"rebuilt","count":changed}

@router.patch("/priorities/{priority_id}")
def complete_priority_v2(priority_id:int,payload:PriorityCompleteInV2,user=Depends(get_current_supabase_user),db:Session=Depends(get_db)):
    from app.models import StudyPriority
    r=db.query(StudyPriority).filter_by(id=priority_id,user_id=uid(user)).first()
    if not r: raise HTTPException(404,'Prioridade não encontrada.')
    r.completed=payload.completed;r.updated_at=datetime.now(timezone.utc);db.commit();return {"id":r.id,"completed":r.completed}

@router.get("/cognitive-map")
def cognitive_map(user=Depends(get_current_supabase_user),db:Session=Depends(get_db)):
    """Mapa leve da Teia Cognitiva: área -> disciplina -> conteúdo + domínio/prioridade."""
    uidv=uid(user)
    perfs={x.topic_id:x for x in db.query(StudentTopicPerformance).filter_by(user_id=uidv).all()}
    nodes=[]
    for area in db.query(KnowledgeArea).order_by(KnowledgeArea.id).all():
        area_node={"id":f"area-{area.id}","type":"area","name":area.name,"children":[]}
        for subject in db.query(Subject).filter_by(knowledge_area_id=area.id).order_by(Subject.name).all():
            subj={"id":f"subject-{subject.id}","type":"subject","name":subject.name,"children":[]}
            for topic in db.query(Topic).filter_by(subject_id=subject.id).order_by(Topic.name).all():
                perf=perfs.get(topic.id); acc=float(perf.accuracy) if perf else 0.0; attempts=perf.attempt_count if perf else 0
                priority=(1-acc) if attempts else 0.5
                level='urgent' if priority>=0.75 else ('high' if priority>=0.5 else ('mastered' if acc>=0.85 and attempts>=3 else 'medium'))
                subj["children"].append({"id":f"topic-{topic.id}","topic_id":topic.id,"type":"topic","name":topic.name,"accuracy":round(acc,4),"attempts":attempts,"priority":round(priority,4),"priority_level":level})
            area_node["children"].append(subj)
        nodes.append(area_node)
    return {"model":"cognitive-map-v1","nodes":nodes,"note":"Domínio baseado no histórico disponível; prioridades são recalculadas conforme novas respostas."}
