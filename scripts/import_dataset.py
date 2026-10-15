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


def find_or_create_subject(db, name, area_name="Não classificada"):
    area = db.query(KnowledgeArea).filter_by(name=area_name).first()
    if not area:
        area = KnowledgeArea(name=area_name)
        db.add(area)
        db.flush()
    subject = db.query(Subject).filter_by(knowledge_area_id=area.id, name=name).first()
    if not subject:
        subject = Subject(knowledge_area_id=area.id, name=name)
        db.add(subject)
        db.flush()
    return subject


def run(path, dry_run=False):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    exams = payload.get("exams", [])
    questions = payload.get("questions", [])
    if not isinstance(questions, list):
        raise ValueError("'questions' deve ser uma lista")

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
        print(json.dumps({"dry_run": dry_run, "created": created}, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="dataset JSON")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.file, args.dry_run)
