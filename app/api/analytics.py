from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ProgramWeight, Topic, TopicYearFrequency
from app.services.scoring import hybrid_score

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _topic_rows(db: Session, topic_id: int):
    return (
        db.query(TopicYearFrequency)
        .filter(TopicYearFrequency.topic_id == topic_id)
        .order_by(TopicYearFrequency.year)
        .all()
    )


@router.get("/topics/{topic_id}")
def topic_analytics(topic_id: int, db: Session = Depends(get_db)):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Tema não encontrado")
    rows = _topic_rows(db, topic_id)
    _, scores = hybrid_score(rows)
    return {
        "topic_id": topic.id,
        "topic_name": topic.name,
        "years": [{"year": r.year, "question_count": r.question_count} for r in rows],
        **scores,
    }


@router.get("/backtest")
def backtest(
    program_id: int | None = None,
    min_years: int = Query(2, ge=1),
    top_k: int = Query(5, ge=1),
    recency_weight: float = Query(0.35, ge=0, le=1),
    trend_weight: float = Query(0.15, ge=0, le=1),
    recency_decay: float = Query(0.35, gt=0, le=2),
    db: Session = Depends(get_db),
):
    """Backtest leave-one-year-out, comparando baseline histórico e modelo híbrido."""
    if recency_weight + trend_weight > 1:
        raise HTTPException(status_code=400, detail="A soma dos pesos de recência e tendência deve ser <= 1")

    weight_by_area = {}
    if program_id is not None:
        weights = db.query(ProgramWeight).filter(ProgramWeight.program_id == program_id).all()
        if not weights:
            raise HTTPException(status_code=404, detail="Curso sem pesos cadastrados")
        weight_by_area = {w.knowledge_area_id: float(w.weight) for w in weights}

    topics = db.query(Topic).all()
    history = defaultdict(dict)
    for row in db.query(TopicYearFrequency).order_by(TopicYearFrequency.year):
        history[row.topic_id][row.year] = row.question_count
    years = sorted({year for values in history.values() for year in values})

    results = []
    baseline_hits = hybrid_hits = 0
    baseline_precision = hybrid_precision = 0.0
    baseline_recall = hybrid_recall = 0.0
    evaluated = 0

    for target_year in years:
        candidates = []
        for topic in topics:
            prior_years = sorted(year for year in history[topic.id] if year < target_year)
            if len(prior_years) < min_years:
                continue
            prior_rows = [type("Row", (), {"year": year, "question_count": history[topic.id].get(year, 0)})() for year in prior_years]
            baseline = sum(row.question_count for row in prior_rows) / len(prior_rows)
            hybrid, _ = hybrid_score(prior_rows, recency_weight, trend_weight, recency_decay)
            if weight_by_area:
                area_weight = weight_by_area.get(topic.subject.knowledge_area_id, 0.0)
                baseline *= area_weight
                hybrid *= area_weight
            actual = history[topic.id].get(target_year, 0)
            candidates.append((topic.id, baseline, hybrid, actual))

        if not candidates:
            continue
        actual_ids = {item[0] for item in candidates if item[3] > 0}
        if not actual_ids:
            continue
        baseline_top = [item[0] for item in sorted(candidates, key=lambda x: x[1], reverse=True)[:top_k]]
        hybrid_top = [item[0] for item in sorted(candidates, key=lambda x: x[2], reverse=True)[:top_k]]
        baseline_set, hybrid_set = set(baseline_top), set(hybrid_top)

        b_hits = len(actual_ids & baseline_set)
        h_hits = len(actual_ids & hybrid_set)
        baseline_hits += int(b_hits > 0)
        hybrid_hits += int(h_hits > 0)
        baseline_precision += b_hits / max(1, len(baseline_set))
        hybrid_precision += h_hits / max(1, len(hybrid_set))
        baseline_recall += b_hits / max(1, len(actual_ids))
        hybrid_recall += h_hits / max(1, len(actual_ids))
        evaluated += 1
        results.append({
            "year": target_year,
            "actual_topic_ids": sorted(actual_ids),
            "baseline": {"hit": bool(b_hits), "topic_ids": baseline_top},
            "hybrid": {"hit": bool(h_hits), "topic_ids": hybrid_top},
        })

    return {
        "evaluated_years": evaluated,
        "top_k": top_k,
        "model": {
            "recency_weight": recency_weight,
            "trend_weight": trend_weight,
            "recency_decay": recency_decay,
        },
        "baseline": {
            "hit_rate": baseline_hits / evaluated if evaluated else 0.0,
            "precision_at_k": baseline_precision / evaluated if evaluated else 0.0,
            "recall_at_k": baseline_recall / evaluated if evaluated else 0.0,
        },
        "hybrid": {
            "hit_rate": hybrid_hits / evaluated if evaluated else 0.0,
            "precision_at_k": hybrid_precision / evaluated if evaluated else 0.0,
            "recall_at_k": hybrid_recall / evaluated if evaluated else 0.0,
        },
        "results": results,
        "note": "Backtest exploratório. O reservatório atual é pequeno; métricas só ganham valor após ampliar os anos e revisar a classificação dos temas.",
    }


@router.get("/calibrate")
def calibrate(
    top_k: int = Query(5, ge=1, le=20),
    min_years: int = Query(2, ge=1),
    db: Session = Depends(get_db),
):
    """Busca uma combinação simples de pesos que maximize hit rate no reservatório atual."""
    candidates = []
    for rw in [0.20, 0.30, 0.35, 0.40, 0.50]:
        for tw in [0.00, 0.10, 0.15, 0.20, 0.25]:
            if rw + tw > 1:
                continue
            history = defaultdict(dict)
            for row in db.query(TopicYearFrequency).order_by(TopicYearFrequency.year):
                history[row.topic_id][row.year] = row.question_count
            years = sorted({y for h in history.values() for y in h})
            hits = evaluated = 0
            topics = db.query(Topic).all()
            for target_year in years:
                ranked=[]; actual=set()
                for topic in topics:
                    prior=sorted(y for y in history[topic.id] if y < target_year)
                    if len(prior) < min_years: continue
                    rows=[type("Row",(),{"year":y,"question_count":history[topic.id].get(y,0)})() for y in prior]
                    score,_=hybrid_score(rows,rw,tw,0.35)
                    ranked.append((topic.id,score))
                    if history[topic.id].get(target_year,0)>0: actual.add(topic.id)
                if not actual or not ranked: continue
                top={x[0] for x in sorted(ranked,key=lambda x:x[1],reverse=True)[:top_k]}
                hits += bool(actual & top); evaluated += 1
            rate=hits/evaluated if evaluated else 0.0
            candidates.append({"recency_weight":rw,"trend_weight":tw,"hit_rate":rate,"evaluated_years":evaluated})
    candidates.sort(key=lambda x:(x["hit_rate"], -x["trend_weight"]),reverse=True)
    return {"best": candidates[0] if candidates else None, "candidates": candidates, "warning":"Calibração exploratória; reexecute após ampliar o histórico."}
