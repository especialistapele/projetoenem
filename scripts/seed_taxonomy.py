"""Cria a taxonomia ENEM v1 no PostgreSQL de forma idempotente."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import KnowledgeArea, Subject
from app.services.taxonomy import AREAS, iter_skills
from sqlalchemy import text


def main():
    with SessionLocal() as db:
        version = db.execute(text("SELECT id FROM taxonomy_versions WHERE code='ENEM-MR-2009-V1'")).scalar_one_or_none()
        if version is None:
            raise RuntimeError("Execute sql/002_taxonomy_v1.sql antes do seed.")

        area_ids = {}
        for code, data in AREAS.items():
            area = db.query(KnowledgeArea).filter(KnowledgeArea.code == code).one_or_none()
            if area is None:
                area = KnowledgeArea(name=data["name"], code=code)
                db.add(area)
                db.flush()
            area_ids[code] = area.id
            for subject_name in data["subjects"]:
                exists = db.query(Subject).filter(Subject.knowledge_area_id == area.id, Subject.name == subject_name).one_or_none()
                if not exists:
                    db.add(Subject(knowledge_area_id=area.id, name=subject_name))

        db.flush()
        inserted_comp = 0
        inserted_skill = 0
        for area_code, data in AREAS.items():
            for number, (name, skill_range) in data["competencies"].items():
                code = f"C{number}"
                comp_id = db.execute(text("""
                    INSERT INTO competencies (taxonomy_version_id, knowledge_area_id, code, name)
                    VALUES (:v, :a, :c, :n)
                    ON CONFLICT (taxonomy_version_id, knowledge_area_id, code)
                    DO UPDATE SET name = EXCLUDED.name
                    RETURNING id
                """), {"v": version, "a": area_ids[area_code], "c": code, "n": name}).scalar_one()
                inserted_comp += 1
                for h in skill_range:
                    result = db.execute(text("""
                        INSERT INTO skill_definitions (competency_id, code, description, source_status)
                        VALUES (:c, :h, NULL, 'official_code_pending_description_sync')
                        ON CONFLICT (competency_id, code) DO NOTHING
                        RETURNING id
                    """), {"c": comp_id, "h": f"H{h}"}).scalar_one_or_none()
                    if result:
                        inserted_skill += 1

        db.commit()
        total = db.execute(text("SELECT count(*) FROM skill_definitions")).scalar_one()
        print({"competencies_processed": inserted_comp, "skills_inserted": inserted_skill, "skills_total": total})


if __name__ == "__main__":
    main()
