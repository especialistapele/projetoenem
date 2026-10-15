from typing import Optional
import json, urllib.request, urllib.error
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import get_db
from app.config import settings
from app.supabase_auth import require_admin

router = APIRouter(prefix='/admin', tags=['admin'])

class UserCreateIn(BaseModel):
    email: str
    password: str = Field(min_length=8)
    role: str = Field(pattern='^(admin|teacher|student)$')
    display_name: str = ''
    program_id: Optional[int] = None

class AssignmentIn(BaseModel):
    student_id: str
    active: bool = True

def admin_headers():
    if not settings.supabase_service_role_key:
        raise HTTPException(503, 'SUPABASE_SERVICE_ROLE_KEY não configurada no .env local.')
    return {'apikey': settings.supabase_service_role_key, 'Authorization': 'Bearer '+settings.supabase_service_role_key, 'Content-Type':'application/json'}

def supabase_admin(path, payload):
    req=urllib.request.Request(settings.supabase_url.rstrip('/')+path, headers=admin_headers(), data=json.dumps(payload).encode(), method='POST')
    try:
        with urllib.request.urlopen(req, timeout=15) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body=e.read().decode(errors='ignore')
        raise HTTPException(e.code, body[:500])

@router.get('/users')
def list_users(_=Depends(require_admin), db:Session=Depends(get_db)):
    rows=db.execute(text("""SELECT p.user_id,p.role,p.program_id,p.display_name,p.created_at,u.email
      FROM public.user_profiles p JOIN auth.users u ON u.id=p.user_id ORDER BY p.created_at DESC""")).mappings().all()
    return [dict(r) for r in rows]

@router.post('/users')
def create_user(payload:UserCreateIn, _=Depends(require_admin), db:Session=Depends(get_db)):
    u=supabase_admin('/auth/v1/admin/users', {'email':payload.email,'password':payload.password,'email_confirm':True,'app_metadata':{'role':payload.role},'user_metadata':{'display_name':payload.display_name}})
    uid=u.get('id')
    if not uid: raise HTTPException(502,'Supabase não retornou o ID do usuário.')
    db.execute(text("""INSERT INTO public.user_profiles(user_id,role,program_id,display_name) VALUES (:uid,:role,:program,:name)
      ON CONFLICT(user_id) DO UPDATE SET role=EXCLUDED.role,program_id=EXCLUDED.program_id,display_name=EXCLUDED.display_name,updated_at=now()"""), {'uid':uid,'role':payload.role,'program':payload.program_id,'name':payload.display_name or payload.email})
    db.commit(); return {'id':uid,'email':payload.email,'role':payload.role,'program_id':payload.program_id}


@router.get('/overview')
def admin_overview(_=Depends(require_admin), db:Session=Depends(get_db)):
    def one(sql): return db.execute(text(sql)).scalar() or 0
    return {
      'users': {'total': one("SELECT COUNT(*) FROM public.user_profiles"), 'students': one("SELECT COUNT(*) FROM public.user_profiles WHERE role='student'"), 'teachers': one("SELECT COUNT(*) FROM public.user_profiles WHERE role='teacher'"), 'admins': one("SELECT COUNT(*) FROM public.user_profiles WHERE role='admin'")},
      'assignments': {'active': one("SELECT COUNT(*) FROM public.teacher_students WHERE active"), 'teachers_with_students': one("SELECT COUNT(DISTINCT teacher_id) FROM public.teacher_students WHERE active")},
      'content': {'exams': one("SELECT COUNT(*) FROM public.exams"), 'questions': one("SELECT COUNT(*) FROM public.questions"), 'topics': one("SELECT COUNT(*) FROM public.topics"), 'classified': one("SELECT COUNT(*) FROM public.question_classification_candidates WHERE status='accepted'")},
      'learning': {'attempts': one("SELECT COUNT(*) FROM public.question_attempts"), 'simulations': one("SELECT COUNT(*) FROM public.simulations"), 'simulation_answers': one("SELECT COUNT(*) FROM public.simulation_attempts WHERE user_id IS NOT NULL"), 'essays': one("SELECT COUNT(*) FROM public.essay_submissions"), 'pending_essays': one("SELECT COUNT(*) FROM public.essay_submissions WHERE status='pending'"), 'reviewed_essays': one("SELECT COUNT(*) FROM public.essay_submissions WHERE status='reviewed'")},
      'tri': {'items_with_parameters': one("SELECT COUNT(*) FROM public.item_tri_parameters"), 'calibrated_items': one("SELECT COUNT(*) FROM public.item_tri_parameters WHERE calibration_status='calibrated'"), 'estimated_items': one("SELECT COUNT(*) FROM public.item_tri_parameters WHERE calibration_status='estimated'")}
    }

@router.get('/teachers')
def teachers(_=Depends(require_admin), db:Session=Depends(get_db)):
    return [dict(r) for r in db.execute(text("""SELECT p.user_id,p.display_name,u.email,COUNT(ts.student_id) FILTER (WHERE ts.active) AS student_count
      FROM public.user_profiles p JOIN auth.users u ON u.id=p.user_id LEFT JOIN public.teacher_students ts ON ts.teacher_id=p.user_id
      WHERE p.role='teacher' GROUP BY p.user_id,p.display_name,u.email ORDER BY p.display_name,u.email""")).mappings().all()]

@router.get('/teachers/{teacher_id}/students')
def teacher_students(teacher_id:str, _=Depends(require_admin), db:Session=Depends(get_db)):
    return [dict(r) for r in db.execute(text("""SELECT p.user_id,p.display_name,u.email,ts.active,ts.assigned_at
      FROM public.teacher_students ts JOIN public.user_profiles p ON p.user_id=ts.student_id JOIN auth.users u ON u.id=p.user_id
      WHERE ts.teacher_id=:tid ORDER BY p.display_name,u.email"""), {'tid':teacher_id}).mappings().all()]

@router.post('/teachers/{teacher_id}/students')
def assign_student(teacher_id:str, payload:AssignmentIn, _=Depends(require_admin), db:Session=Depends(get_db)):
    teacher=db.execute(text("SELECT role FROM public.user_profiles WHERE user_id=:id"),{'id':teacher_id}).scalar()
    student=db.execute(text("SELECT role FROM public.user_profiles WHERE user_id=:id"),{'id':payload.student_id}).scalar()
    if teacher!='teacher': raise HTTPException(400,'Usuário indicado não é professor.')
    if student!='student': raise HTTPException(400,'Usuário indicado não é aluno.')
    db.execute(text("""INSERT INTO public.teacher_students(teacher_id,student_id,active) VALUES (:t,:s,:a)
      ON CONFLICT(teacher_id,student_id) DO UPDATE SET active=EXCLUDED.active"""), {'t':teacher_id,'s':payload.student_id,'a':payload.active})
    db.commit(); return {'teacher_id':teacher_id,'student_id':payload.student_id,'active':payload.active}

@router.delete('/teachers/{teacher_id}/students/{student_id}')
def unassign_student(teacher_id:str,student_id:str,_=Depends(require_admin),db:Session=Depends(get_db)):
    db.execute(text("UPDATE public.teacher_students SET active=false WHERE teacher_id=:t AND student_id=:s"),{'t':teacher_id,'s':student_id});db.commit();return {'active':False}

@router.get('/dashboard')
def admin_dashboard(_=Depends(require_admin), db:Session=Depends(get_db)):
    def scalar(sql): return db.execute(text(sql)).scalar() or 0
    recent_imports=[]
    try:
        recent_imports=[dict(r) for r in db.execute(text("SELECT id,year,edition,color,day FROM public.exams ORDER BY id DESC LIMIT 10")).mappings().all()]
    except Exception: pass
    return {
      'summary': {
        'users': scalar("SELECT COUNT(*) FROM public.user_profiles"),
        'students': scalar("SELECT COUNT(*) FROM public.user_profiles WHERE role='student'"),
        'teachers': scalar("SELECT COUNT(*) FROM public.user_profiles WHERE role='teacher'"),
        'admins': scalar("SELECT COUNT(*) FROM public.user_profiles WHERE role='admin'"),
        'questions': scalar("SELECT COUNT(*) FROM public.questions"),
        'exams': scalar("SELECT COUNT(*) FROM public.exams"),
        'topics': scalar("SELECT COUNT(*) FROM public.topics"),
        'attempts': scalar("SELECT COUNT(*) FROM public.question_attempts"),
        'simulations': scalar("SELECT COUNT(*) FROM public.simulations"),
        'essays_pending': scalar("SELECT COUNT(*) FROM public.essay_submissions WHERE status='pending'"),
        'essays_reviewed': scalar("SELECT COUNT(*) FROM public.essay_submissions WHERE status='reviewed'"),
        'tri_estimated': scalar("SELECT COUNT(*) FROM public.item_tri_parameters WHERE calibration_status='estimated'"),
        'tri_calibrated': scalar("SELECT COUNT(*) FROM public.item_tri_parameters WHERE calibration_status='calibrated'"),
      },
      'teacher_load': [dict(r) for r in db.execute(text("""SELECT p.user_id,p.display_name,u.email,COUNT(ts.student_id) FILTER (WHERE ts.active) student_count
        FROM public.user_profiles p JOIN auth.users u ON u.id=p.user_id LEFT JOIN public.teacher_students ts ON ts.teacher_id=p.user_id
        WHERE p.role='teacher' GROUP BY p.user_id,p.display_name,u.email ORDER BY student_count DESC,p.display_name""")).mappings().all()],
      'recent_exams': recent_imports,
    }
