"""Classificação heurística local de questões ENEM.

Não substitui um modelo NLP treinado. Serve como camada determinística e auditável
para acelerar a classificação inicial de grandes lotes e gerar candidatos para revisão.
"""
import re
import unicodedata

RULES = {
    "Matemática": {
        "Matemática": ["função", "probabilidade", "estatística", "geometria", "porcentagem", "matriz", "equação", "gráfico", "logaritmo", "progressão"],
    },
    "Ciências da Natureza": {
        "Biologia": ["célula", "dna", "gene", "ecossistema", "ecologia", "fotossíntese", "cadeia alimentar", "evolução", "vírus", "bactéria"],
        "Química": ["reação química", "mol", "ácido", "base", "ph", "oxidação", "redução", "solução", "química", "hidrocarboneto"],
        "Física": ["velocidade", "aceleração", "força", "energia", "potência", "circuito", "resistência elétrica", "onda", "óptica", "pressão"],
    },
    "Ciências Humanas": {
        "História": ["revolução", "escravidão", "império", "república", "colonização", "ditadura", "guerra", "industrialização", "idade média"],
        "Geografia": ["território", "urbanização", "migração", "clima", "relevo", "população", "globalização", "cartografia", "agricultura"],
        "Filosofia": ["filosofia", "ética", "epistemologia", "platão", "aristóteles", "sócrates", "kant", "nietzsche"],
        "Sociologia": ["sociedade", "cultura", "classe social", "desigualdade", "cidadania", "trabalho", "poder", "movimentos sociais"],
    },
    "Linguagens": {
        "Língua Portuguesa": ["texto", "linguagem", "metáfora", "narrador", "poema", "literatura", "gênero textual", "argumentação", "variação linguística"],
        "Artes": ["arte", "pintura", "música", "cinema", "fotografia", "obra de arte", "artista"],
        "Educação Física": ["esporte", "atividade física", "corpo", "dança", "jogo", "saúde"],
    },
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def classify_question(text: str) -> dict:
    normalized = normalize(text)
    candidates = []
    for area, subjects in RULES.items():
        for subject, keywords in subjects.items():
            hits = [kw for kw in keywords if normalize(kw) in normalized]
            if hits:
                candidates.append((len(hits), area, subject, hits))
    candidates.sort(reverse=True)
    if not candidates:
        return {"area": None, "subject": None, "confidence": 0.0, "keywords": []}
    score, area, subject, hits = candidates[0]
    confidence = min(0.95, 0.35 + score * 0.12)
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        confidence = min(confidence, 0.55)
    return {"area": area, "subject": subject, "confidence": round(confidence, 3), "keywords": hits}



def official_area_for_question_number(number: int) -> str | None:
    """Infere a área pela numeração oficial das questões objetivas do ENEM."""
    try:
        n = int(number)
    except (TypeError, ValueError):
        return None
    if 1 <= n <= 45:
        return "Linguagens"
    if 46 <= n <= 90:
        return "Ciências Humanas"
    if 91 <= n <= 135:
        return "Ciências da Natureza"
    if 136 <= n <= 180:
        return "Matemática"
    return None
