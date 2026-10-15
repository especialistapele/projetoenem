"""Importador local de um dataset ENEM estruturado em JSON.

Formato mínimo:
{
  "exams": [{"year": 2024, "edition": "regular", "color": "azul", "day": 1}],
  "questions": [{"exam": {"year": 2024, "edition": "regular", "color": "azul", "day": 1},
                 "number": 1, "statement_text": "...", "subject": "Biologia",
                 "alternatives": [{"letter":"A","text":"...","is_correct":false}],
                 "topics": ["Ecologia"]}]
}

O importador não apaga dados existentes e é idempotente por prova/questão e por nome
para disciplinas/temas. Use --dry-run antes de gravar.
"""
import argparse
import json
from pathlib import Path

from app.database import SessionLocal
from app.models import Alternative, Exam, KnowledgeArea, Question, QuestionTopic, Subject, Topic


AREA_ALIASES = {
    "Linguagens": ("LC", "Linguagens, Códigos e suas Tecnologias"),
    "Linguagens, Códigos e suas Tecnologias": ("LC", "Linguagens, Códigos e suas Tecnologias"),
    "Ciências Humanas": ("CH", "Ciências Humanas e suas Tecnologias"),
    "Ciências Humanas e suas Tecnologias": ("CH", "Ciências Humanas e suas Tecnologias"),
    "Ciências da Natureza": ("CN", "Ciências da Natureza e suas Tecnologias"),
    "Ciências da Natureza e suas Tecnologias": ("CN", "Ciências da Natureza e suas Tecnologias"),
    "Matemática": ("MT", "Matemática e suas Tecnologias"),
    "Matemática e suas Tecnologias": ("MT", "Matemática e suas Tecnologias"),
    "Redação": ("RED", "Redação"),
}


def normalize_area(area_name):
    label = (area_name or "Não classificada").strip()
    return AREA_ALIASES.get(label, (None, label))


def find_or_create_subject(db, name, area_name="Não classificada"):
    area_code, canonical_name = normalize_area(area_name)
    area = db.query(KnowledgeArea).filter_by(code=area_code).first() if area_code else None
    if not area:
        area = db.query(KnowledgeArea).filter_by(name=canonical_name).first()
    if not area:
        area = KnowledgeArea(name=canonical_name, code=area_code)
        db.add(area)
        db.flush()
    subject = db.query(Subject).filter_by(knowledge_area_id=area.id, name=name).first()
    if not subject:
        subject = Subject(knowledge_area_id=area.id, name=name)
        db.add(subject)
        db.flush()
    return subject


def validate_dataset(payload):
    questions = payload.get("questions", [])
    if not isinstance(questions, list):
        raise ValueError("'questions' deve ser uma lista")
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict) or not str(item.get("statement_text") or "").strip():
            raise ValueError(f"Questão {index}: enunciado ausente.")
        if not str(item.get("area") or "").strip() or not str(item.get("subject") or "").strip():
            raise ValueError(f"Questão {index}: área/disciplina não classificada; revise antes de importar.")
        alternatives = item.get("alternatives", []) or []
        letters = [str(alternative.get("letter") or "").strip().upper() for alternative in alternatives]
        if len(set(letters)) != len(letters):
            raise ValueError(f"Questão {index}: há letras de alternativas duplicadas.")
        if any(letter not in {"A", "B", "C", "D", "E"} for letter in letters):
            raise ValueError(f"Questão {index}: alternativas devem usar letras de A a E.")
        if any(not str(alternative.get("text") or "").strip() for alternative in alternatives):
            raise ValueError(f"Questão {index}: existe alternativa sem texto.")
        correct_count = sum(1 for alternative in alternatives if alternative.get("is_correct") is True)
        if correct_count != 1:
            raise ValueError(f"Questão {index}: esperado exatamente um gabarito correto; encontrado {correct_count}.")
        if len(alternatives) != 5 or set(letters) != {"A", "B", "C", "D", "E"}:
            raise ValueError(f"Questão {index}: esperado o conjunto completo de cinco alternativas A–E; encontrado {len(alternatives)}.")
    return len(questions)


def run(path, dry_run=False):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    exams = payload.get("exams", [])
    questions = payload.get("questions", [])
    validate_dataset(payload)

    db = SessionLocal()
    created = {"exams": 0, "questions": 0, "alternatives": 0, "topics": 0, "links": 0}
    try:
        for exam_data in exams:
            exam = db.query(Exam).filter_by(
                year=exam_data["year"], edition=exam_data.get("edition", "regular"),
                color=exam_data.get("color", "azul"), day=exam_data.get("day")
            ).first()
            if not exam:
                db.add(Exam(**exam_data))
                created["exams"] += 1
        db.flush()

        for item in questions:
            exam_data = item["exam"]
            exam = db.query(Exam).filter_by(
                year=exam_data["year"], edition=exam_data.get("edition", "regular"),
                color=exam_data.get("color", "azul"), day=exam_data.get("day")
            ).first()
            if not exam:
                exam = Exam(year=exam_data["year"], edition=exam_data.get("edition", "regular"),
                            color=exam_data.get("color", "azul"), day=exam_data.get("day"))
                db.add(exam)
                db.flush()
                created["exams"] += 1

            question = db.query(Question).filter_by(exam_id=exam.id, number=item["number"]).first()
            if not question:
                subject = None
                if item.get("subject"):
                    subject = find_or_create_subject(db, item["subject"], item.get("area", "Não classificada"))
                question = Question(exam_id=exam.id, number=item["number"],
                                    subject_id=subject.id if subject else None,
                                    source_text=item.get("source_text"),
                                    statement_text=item["statement_text"])
                db.add(question)
                db.flush()
                created["questions"] += 1

            for alt in item.get("alternatives", []):
                exists = db.query(Alternative).filter_by(question_id=question.id, letter=alt["letter"]).first()
                if not exists:
                    db.add(Alternative(question_id=question.id, **{k: alt[k] for k in ("letter", "text", "is_correct") if k in alt}))
                    created["alternatives"] += 1
                else:
                    # Reimportar um gabarito corrige respostas já existentes sem duplicar alternativas.
                    exists.text = alt.get("text", exists.text)
                    exists.is_correct = bool(alt.get("is_correct", False))

            for topic_name in item.get("topics", []):
                subject_id = question.subject_id
                if not subject_id:
                    continue
                topic = db.query(Topic).filter_by(subject_id=subject_id, name=topic_name).first()
                if not topic:
                    topic = Topic(subject_id=subject_id, name=topic_name)
                    db.add(topic)
                    db.flush()
                    created["topics"] += 1
                link = db.query(QuestionTopic).filter_by(question_id=question.id, topic_id=topic.id).first()
                if not link:
                    db.add(QuestionTopic(question_id=question.id, topic_id=topic.id, relevance=1.0))
                    created["links"] += 1

        if dry_run:
            db.rollback()
        else:
            db.commit()
        summary = {"dry_run": dry_run, "created": created}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return summary
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="dataset JSON")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.file, args.dry_run)
