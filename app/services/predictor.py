from math import exp
from app.services.scoring import calculate_components


def softmax(scores, temperature=1.0):
    if not scores:
        return []
    t=max(0.05,float(temperature))
    m=max(scores)
    vals=[exp((s-m)/t) for s in scores]
    total=sum(vals) or 1.0
    return [v/total for v in vals]


def build_prediction(rows, area_weight, graph_score, recency_weight=0.35, trend_weight=0.15, recency_decay=0.35):
    frequency, recency, trend=calculate_components(rows, recency_decay)
    positive_trend=max(0.0,trend)
    base=((1-recency_weight-trend_weight)*frequency + recency_weight*recency + trend_weight*positive_trend)
    graph_boost=0.10*max(0.0,min(1.0,graph_score))
    score=max(0.0,float(area_weight))*base*(1+graph_boost)
    return score,{"frequency":frequency,"recency":recency,"trend":trend,"area_weight":float(area_weight),"graph_score":float(graph_score),"graph_boost":graph_boost,"base_score":base}
