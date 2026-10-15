from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Topic, TopicEdge, TopicYearFrequency

router = APIRouter(prefix="/topics", tags=["topics"])


@router.get("")
def list_topics(subject_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(Topic)
    if subject_id:
        query = query.filter(Topic.subject_id == subject_id)
    return query.order_by(Topic.name).all()


@router.get("/{topic_id}")
def get_topic(topic_id: int, db: Session = Depends(get_db)):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Tema não encontrado")
    return topic


@router.get("/{topic_id}/edges")
def get_topic_edges(topic_id: int, db: Session = Depends(get_db)):
    edges = db.query(TopicEdge).filter(or_(TopicEdge.topic_a_id == topic_id, TopicEdge.topic_b_id == topic_id)).order_by(TopicEdge.weight.desc()).all()
    return edges


@router.get("/{topic_id}/frequency")
def get_topic_frequency(topic_id: int, db: Session = Depends(get_db)):
    freq = db.query(TopicYearFrequency).filter(TopicYearFrequency.topic_id == topic_id).order_by(TopicYearFrequency.year).all()
    if not freq:
        raise HTTPException(status_code=404, detail="Sem dados de frequência para este tema ainda")
    return freq


@router.get("/{topic_id}/impact")
def get_topic_impact(topic_id: int, db: Session = Depends(get_db)):
    """Retorna a força relativa das conexões do tema no grafo."""
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Tema não encontrado")
    edges = db.query(TopicEdge).filter(or_(TopicEdge.topic_a_id == topic_id, TopicEdge.topic_b_id == topic_id)).all()
    total_weight = sum(float(e.weight or 0) for e in edges)
    return {
        "topic_id": topic_id,
        "connections": len(edges),
        "total_weight": round(total_weight, 3),
        "neighbors": [
            {"topic_id": e.topic_b_id if e.topic_a_id == topic_id else e.topic_a_id,
             "edge_type": e.edge_type, "weight": float(e.weight or 0)}
            for e in sorted(edges, key=lambda x: float(x.weight or 0), reverse=True)
        ],
    }
