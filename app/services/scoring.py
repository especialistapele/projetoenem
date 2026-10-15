from math import exp


def build_year_series(rows):
    """Converte linhas (year, question_count) em série contínua, preenchendo anos ausentes com zero."""
    if not rows:
        return []
    values = {int(r.year): int(r.question_count) for r in rows}
    first, last = min(values), max(values)
    return [(year, values.get(year, 0)) for year in range(first, last + 1)]


def calculate_components(rows, recency_decay=0.35):
    series = build_year_series(rows)
    if not series:
        return 0.0, 0.0, 0.0

    counts = [count for _, count in series]
    frequency = sum(counts) / len(counts)
    latest_year = series[-1][0]
    recency_weights = [exp(-recency_decay * (latest_year - year)) for year, _ in series]
    denominator = sum(recency_weights) or 1.0
    recency = sum(count * weight for (_, count), weight in zip(series, recency_weights)) / denominator

    if len(series) >= 2:
        split = max(1, len(series) // 2)
        older = sum(counts[:split]) / split
        recent = sum(counts[split:]) / max(1, len(counts) - split)
        trend = recent - older
    else:
        trend = 0.0

    return frequency, recency, trend


def hybrid_score(rows, recency_weight=0.35, trend_weight=0.15, recency_decay=0.35, graph_boost=0.0):
    frequency, recency, trend = calculate_components(rows, recency_decay=recency_decay)
    trend_positive = max(0.0, trend)
    base = (
        (1 - recency_weight - trend_weight) * frequency
        + recency_weight * recency
        + trend_weight * trend_positive
    )
    final_score = base * (1.0 + max(0.0, graph_boost))
    return final_score, {
        "frequency": frequency,
        "recency": recency,
        "trend": trend,
        "graph_boost": max(0.0, graph_boost),
        "base_score": base,
    }
