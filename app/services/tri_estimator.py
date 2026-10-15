from math import exp
from sqlalchemy import text


def _p(theta, a, b, c):
    z = max(-35.0, min(35.0, a * (theta - b)))
    return c + (1.0 - c) / (1.0 + exp(-z))


def estimate(db, user_id: str):
    rows = db.execute(text('''
      SELECT qa.is_correct, COALESCE(tp.discrimination_a, 1.0) a,
             COALESCE(tp.difficulty_b, COALESCE(q.difficulty_estimate, 0)) b,
             COALESCE(tp.guessing_c, 0.20) c,
             ka.id area_id, ka.name area_name
      FROM public.question_attempts qa
      JOIN public.questions q ON q.id=qa.question_id
      LEFT JOIN public.subjects s ON s.id=q.subject_id
      LEFT JOIN public.knowledge_areas ka ON ka.id=s.knowledge_area_id
      LEFT JOIN public.item_tri_parameters tp ON tp.question_id=q.id
      WHERE qa.user_id=:uid
      ORDER BY qa.created_at
    '''), {'uid': user_id}).mappings().all()
    by_area={}
    for r in rows:
        key=r['area_id'] or 0
        by_area.setdefault(key, {'area_id':r['area_id'],'area_name':r['area_name'] or 'Sem área','items':[]})['items'].append(r)
    out=[]
    for item in by_area.values():
        theta=0.0
        for _ in range(12):
            grad=hess=0.0
            for r in item['items']:
                p=_p(theta,float(r['a']),float(r['b']),float(r['c']))
                # Stable Newton step for Bernoulli log-likelihood.
                d=float(r['a'])*(p-float(r['c']))/(1-float(r['c'])) if p>float(r['c']) else 0.0
                v=max(p*(1-p),1e-5)
                x=1.0 if r['is_correct'] else 0.0
                grad += float(r['a'])*(x-p)/v * (1-float(r['c']))
                hess -= float(r['a'])**2 / v * (1-float(r['c']))
            if abs(hess)<1e-8: break
            step=grad/hess
            theta=max(-4,min(4,theta-step))
            if abs(step)<1e-4: break
        # Educational scale only: maps theta approximately to a 300-900 band.
        score=500 + theta*100
        accuracy=sum(1 for r in item['items'] if r['is_correct'])/len(item['items'])
        out.append({'area_id':item['area_id'],'area_name':item['area_name'],'theta':round(theta,4),'estimated_score':round(max(200,min(900,score)),1),'accuracy':round(accuracy,4),'item_count':len(item['items']),'model_version':'tri-estimate-v1'})
    return {'model':'TRI 3PL estimativa','official_score':False,'note':'Estimativa pedagógica; não reproduz nem substitui a nota oficial do ENEM. Parâmetros sem calibração oficial são estimados.','areas':out}
