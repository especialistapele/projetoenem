from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.scoring import hybrid_score
from app.services.predictor import build_prediction, softmax
from app.models import ProgramWeight, Topic, TopicEdge, TopicYearFrequency
from app.supabase_auth import require_admin

router = APIRouter(prefix="/scoring", tags=["scoring"])


@router.get("/priority")
def get_priority_ranking(
    program_id: int,
    recency_weight: float = Query(0.35, ge=0, le=1),
    trend_weight: float = Query(0.15, ge=0, le=1),
    recency_decay: float = Query(0.35, gt=0, le=2),
    db: Session = Depends(get_db),
):
    if recency_weight + trend_weight > 1:
        raise HTTPException(status_code=400, detail="A soma dos pesos de recência e tendência deve ser <= 1")

    weights = db.query(ProgramWeight).filter(ProgramWeight.program_id == program_id).all()
    if not weights:
        raise HTTPException(status_code=404, detail="Nenhum peso cadastrado para este curso")

    weight_by_area = {w.knowledge_area_id: float(w.weight) for w in weights}
    ranking = []
    topics = db.query(Topic).all()
    edge_rows = db.query(TopicEdge).all()
    graph_by_topic = {}
    for edge in edge_rows:
        w = max(0.0, float(edge.weight or 0))
        graph_by_topic[edge.topic_a_id] = graph_by_topic.get(edge.topic_a_id, 0.0) + w
        graph_by_topic[edge.topic_b_id] = graph_by_topic.get(edge.topic_b_id, 0.0) + w
    max_graph = max(graph_by_topic.values(), default=0.0) or 1.0
    for topic in topics:
        area_weight = weight_by_area.get(topic.subject.knowledge_area_id, 0.0)
        rows = (
            db.query(TopicYearFrequency)
            .filter(TopicYearFrequency.topic_id == topic.id)
            .order_by(TopicYearFrequency.year)
            .all()
        )
        normalized_graph = min(1.0, graph_by_topic.get(topic.id, 0.0) / max_graph)
        graph_boost = 0.10 * normalized_graph
        base, components = hybrid_score(rows, recency_weight, trend_weight, recency_decay, graph_boost)
        priority = area_weight * base
        if priority > 0:
            ranking.append({
                "topic_id": topic.id,
                "topic_name": topic.name,
                "subject_id": topic.subject_id,
                "area_weight": area_weight,
                "frequency_score": components["frequency"],
                "recency_score": components["recency"],
                "trend_score": components["trend"],
                "priority": priority,
                "graph_score": normalized_graph,
                "graph_boost": graph_boost,
            })
    ranking.sort(key=lambda x: x["priority"], reverse=True)
    return ranking


@router.post("/predict")
def generate_predictions(
    program_id: int,
    recency_weight: float = Query(0.35, ge=0, le=1),
    trend_weight: float = Query(0.15, ge=0, le=1),
    recency_decay: float = Query(0.35, gt=0, le=2),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    if recency_weight + trend_weight > 1:
        raise HTTPException(status_code=400, detail="A soma dos pesos de recência e tendência deve ser <= 1")
    weights=db.query(ProgramWeight).filter(ProgramWeight.program_id==program_id).all()
    if not weights:
        raise HTTPException(status_code=404, detail="Nenhum peso cadastrado para este curso")
    from app.models import TopicPredictionResult, TopicPredictionExplanation
    area_weights={w.knowledge_area_id:float(w.weight) for w in weights}
    edges=db.query(TopicEdge).all(); graph={}
    for e in edges:
        w=max(0.0,float(e.weight or 0)); graph[e.topic_a_id]=graph.get(e.topic_a_id,0)+w; graph[e.topic_b_id]=graph.get(e.topic_b_id,0)+w
    max_graph=max(graph.values(),default=0) or 1.0
    items=[]
    for topic in db.query(Topic).all():
        area_weight=area_weights.get(topic.subject.knowledge_area_id,0)
        if area_weight<=0: continue
        rows=db.query(TopicYearFrequency).filter(TopicYearFrequency.topic_id==topic.id).order_by(TopicYearFrequency.year).all()
        gs=min(1.0,graph.get(topic.id,0)/max_graph)
        score,factors=build_prediction(rows,area_weight,gs,recency_weight,trend_weight,recency_decay)
        if score>0: items.append({"topic":topic,"score":score,"factors":factors})
    probs=softmax([x["score"] for x in items])
    db.query(TopicPredictionResult).filter(TopicPredictionResult.program_id==program_id).delete(synchronize_session=False)
    for rank,(item,prob) in enumerate(sorted(zip(items,probs),key=lambda x:x[1],reverse=True),1):
        factors=item["factors"]; r=TopicPredictionResult(topic_id=item["topic"].id,program_id=program_id,score=item["score"],probability=prob,rank=rank,model_version="predictor-v2",factors=factors); db.add(r); db.flush()
        explanations=[("frequency",factors["frequency"],"Frequência histórica do tema."),("recency",factors["recency"],"Peso das ocorrências mais recentes."),("trend",factors["trend"],"Variação entre períodos históricos."),("graph",factors["graph_boost"],"Bônus pelas conexões do tema no grafo."),("area_weight",factors["area_weight"],"Peso da área para o curso selecionado.")]
        db.add_all([TopicPredictionExplanation(prediction_id=r.id,factor=f,contribution=c,explanation=e) for f,c,e in explanations])
    db.commit()
    return get_predictions(program_id,db)

@router.get("/predictions")
def get_predictions(program_id:int, limit:int=Query(50,ge=1,le=500), db:Session=Depends(get_db)):
    from app.models import TopicPredictionResult
    rows=db.query(TopicPredictionResult).filter(TopicPredictionResult.program_id==program_id).order_by(TopicPredictionResult.rank).limit(limit).all()
    return [{"prediction_id":r.id,"topic_id":r.topic_id,"topic_name":r.topic.name if r.topic else None,"score":float(r.score),"probability":float(r.probability),"rank":r.rank,"model_version":r.model_version,"factors":r.factors} for r in rows]


@router.get('/study-plan')
def get_study_plan(program_id: int, limit: int = Query(10, ge=1, le=30), db: Session = Depends(get_db)):
    """Transforma as previsões em uma fila prática de estudo, usando questões já existentes."""
    from app.models import QuestionTopic, Question, Exam
    predictions = db.query(TopicPredictionResult).filter(TopicPredictionResult.program_id == program_id).order_by(TopicPredictionResult.rank).limit(limit).all()
    plan=[]
    for p in predictions:
        qrows=(db.query(Question, Exam.year).join(QuestionTopic, QuestionTopic.question_id==Question.id).join(Exam, Exam.id==Question.exam_id)
               .filter(QuestionTopic.topic_id==p.topic_id).order_by(Exam.year.desc(), Question.number).limit(3).all())
        plan.append({'rank':p.rank,'topic_id':p.topic_id,'topic_name':p.topic.name if p.topic else None,'probability':float(p.probability),'recommendation':'Prioridade alta' if p.rank <= 3 else ('Prioridade média' if p.rank <= 7 else 'Revisão'), 'questions':[{'id':q.id,'number':q.number,'year':year,'statement':q.statement_text[:180] if q.statement_text else ''} for q,year in qrows]})
    return plan
