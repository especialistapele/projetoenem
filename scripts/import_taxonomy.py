"""Importa a Matriz de Referência oficial do ENEM para a taxonomia do banco.

O texto é extraído do PDF oficial em tempo de execução. A importação é idempotente,
preserva IDs e só grava quando dry_run=False.
"""
from __future__ import annotations

import argparse
import io
import re
from typing import Any

import pdfplumber
from sqlalchemy.orm import Session
from urllib.request import Request

from app.database import SessionLocal
from app.models import Competency, KnowledgeArea, SkillDefinition, TaxonomyVersion
from app.services.enem_importer import _urlopen_verified, validate_pdf_bytes

SOURCE_URL = "https://download.inep.gov.br/enem/outros_documentos/enem_matriz_referencia.pdf"
TAXONOMY_CODE = "enem-matriz-referencia-inep"
TAXONOMY_NAME = "Matriz de Referência do ENEM — INEP"
MAX_PDF_BYTES = 20 * 1024 * 1024

AREA_HEADERS = (
    ("LC", "Linguagens, Códigos e suas Tecnologias"),
    ("CH", "Ciências Humanas e suas Tecnologias"),
    ("CN", "Ciências da Natureza e suas Tecnologias"),
    ("MT", "Matemática e suas Tecnologias"),
)
EXPECTED_COMPETENCIES = {"LC": 9, "CH": 6, "CN": 8, "MT": 7}
EXPECTED_SKILLS_PER_AREA = 30
COMPETENCY_RE = re.compile(r"Competência\\s+de\\s+área\\s*(\\d+)\\s*(?:[-–—:]\\s*)?", re.I)
SKILL_RE = re.compile(r"(?<![A-Za-z])H\\s*(\\d{1,2})\\s*[–—-]\\s*", re.I)


def _clean(value: str) -> str:
    value = re.sub(r"\\s+", " ", value or "")
    return value.strip(" \\t\\r\\n-–—:;.")


def extract_matrix_text(pdf_bytes: bytes) -> str:
    valid, reason = validate_pdf_bytes(pdf_bytes)
    if not valid:
        raise ValueError(reason)
    pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    text = "\\n".join(pages)
    if len(text.strip()) < 5000:
        raise ValueError("O PDF oficial não forneceu texto suficiente para extrair a matriz.")
    return text


def _area_sections(text: str) -> dict[str, str]:
    patterns = {
        "LC": re.compile(r"(?im)^\\s*(?:Matriz de Referência de\\s+)?Linguagens,\\s*Códigos e suas Tecnologias\\s*$"),
        "CH": re.compile(r"(?im)^\\s*(?:Matriz de Referência de\\s+)?Ciências Humanas e suas Tecnologias\\s*$"),
        "CN": re.compile(r"(?im)^\\s*(?:Matriz de Referência de\\s+)?Ciências da Natureza e suas Tecnologias\\s*$"),
        "MT": re.compile(r"(?im)^\\s*(?:Matriz de Referência de\\s+)?Matemática e suas Tecnologias\\s*$"),
    }
    matches = []
    for code, pattern in patterns.items():
        matches.extend((m.start(), m.end(), code) for m in pattern.finditer(text))
    matches.sort()
    sections = {code: [] for code, _ in AREA_HEADERS}
    current = None
    cursor = 0
    for start, end, code in matches:
        if current is not None:
            sections[current].append(text[cursor:start])
        current = code
        cursor = end
    if current is not None:
        sections[current].append(text[cursor:])
    return {code: "\\n".join(chunks) for code, chunks in sections.items()}


def parse_matrix_text(text: str) -> dict[str, Any]:
    sections = _area_sections(text)
    parsed: dict[str, Any] = {"areas": []}
    for area_code, area_name in AREA_HEADERS:
        section = sections.get(area_code, "")
        competency_matches = list(COMPETENCY_RE.finditer(section))
        competencies = []
        seen_competencies = set()
        for index, match in enumerate(competency_matches):
            comp_number = int(match.group(1))
            start = match.end()
            end = competency_matches[index + 1].start() if index + 1 < len(competency_matches) else len(section)
            body = section[start:end]
            skill_matches = list(SKILL_RE.finditer(body))
            name_end = skill_matches[0].start() if skill_matches else len(body)
            name = _clean(body[:name_end])
            if not name:
                continue
            skills = []
            seen_skills = set()
            for skill_index, skill_match in enumerate(skill_matches):
                skill_start = skill_match.end()
                skill_end = skill_matches[skill_index + 1].start() if skill_index + 1 < len(skill_matches) else len(body)
                description = _clean(body[skill_start:skill_end])
                skill_number = int(skill_match.group(1))
                if 1 <= skill_number <= 30 and description and skill_number not in seen_skills:
                    skills.append({"code": f"H{skill_number}", "description": description})
                    seen_skills.add(skill_number)
            key = (comp_number, name)
            if key not in seen_competencies:
                competencies.append({
                    "code": f"C{comp_number}",
                    "name": name,
                    "skills": skills,
                })
                seen_competencies.add(key)
        parsed["areas"].append({"code": area_code, "name": area_name, "competencies": competencies})

    issues = []
    if len([area for area in parsed["areas"] if area["competencies"]]) != 4:
        issues.append("A matriz não contém as quatro áreas do conhecimento.")
    for area in parsed["areas"]:
        expected_competencies = EXPECTED_COMPETENCIES[area["code"]]
        if len(area["competencies"]) != expected_competencies:
            issues.append(f"{area['code']}: esperadas {expected_competencies} competências; extraídas {len(area['competencies'])}.")
        skill_codes = {skill["code"] for competency in area["competencies"] for skill in competency["skills"]}
        if len(skill_codes) != EXPECTED_SKILLS_PER_AREA or skill_codes != {f"H{i}" for i in range(1, 31)}:
            issues.append(f"{area['code']}: esperadas habilidades H1–H30; extraídas {len(skill_codes)} códigos distintos.")
        if any(not competency["skills"] for competency in area["competencies"]):
            issues.append(f"{area['code']}: há competência sem habilidades associadas.")
    parsed["diagnostics"] = {
        "competencies": sum(len(area["competencies"]) for area in parsed["areas"]),
        "skills": sum(len(competency["skills"]) for area in parsed["areas"] for competency in area["competencies"]),
        "valid": not issues,
        "issues": issues,
    }
    if issues:
        raise ValueError("Matriz extraída incompleta ou ambígua: " + " ".join(issues))
    return parsed


def import_taxonomy(db: Session, parsed: dict[str, Any], dry_run: bool = True) -> dict[str, Any]:
    if not parsed.get("diagnostics", {}).get("valid"):
        raise ValueError("A matriz precisa passar pela validação antes da importação.")
    version = db.query(TaxonomyVersion).filter_by(code=TAXONOMY_CODE).first()
    if not version:
        version = TaxonomyVersion(
            code=TAXONOMY_CODE,
            name=TAXONOMY_NAME,
            source_url=SOURCE_URL,
            notes="Extraída automaticamente do PDF oficial do INEP; códigos e descrições preservados.",
        )
        db.add(version)
        db.flush()
    else:
        version.name = TAXONOMY_NAME
        version.source_url = SOURCE_URL
        version.notes = "Extraída automaticamente do PDF oficial do INEP; códigos e descrições preservados."

    counts = {"areas": 0, "competencies_created": 0, "competencies_updated": 0, "skills_created": 0, "skills_updated": 0}
    for area_data in parsed["areas"]:
        area = db.query(KnowledgeArea).filter_by(code=area_data["code"]).first()
        if not area:
            area = db.query(KnowledgeArea).filter_by(name=area_data["name"]).first()
        if not area:
            area = KnowledgeArea(code=area_data["code"], name=area_data["name"])
            db.add(area)
            db.flush()
        elif not area.code:
            area.code = area_data["code"]
        counts["areas"] += 1

        for comp_data in area_data["competencies"]:
            comp = db.query(Competency).filter_by(
                taxonomy_version_id=version.id,
                knowledge_area_id=area.id,
                code=comp_data["code"],
            ).first()
            if not comp:
                comp = Competency(
                    taxonomy_version_id=version.id,
                    knowledge_area_id=area.id,
                    code=comp_data["code"],
                    name=comp_data["name"],
                )
                db.add(comp)
                db.flush()
                counts["competencies_created"] += 1
            else:
                comp.name = comp_data["name"]
                counts["competencies_updated"] += 1

            for skill_data in comp_data["skills"]:
                skill = db.query(SkillDefinition).filter_by(
                    competency_id=comp.id,
                    code=skill_data["code"],
                ).first()
                if not skill:
                    db.add(SkillDefinition(
                        competency_id=comp.id,
                        code=skill_data["code"],
                        description=skill_data["description"],
                        source_status="official",
                    ))
                    counts["skills_created"] += 1
                else:
                    skill.description = skill_data["description"]
                    skill.source_status = "official"
                    counts["skills_updated"] += 1

    db.flush()
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return {
        "status": "dry_run" if dry_run else "imported",
        "source_url": SOURCE_URL,
        "diagnostics": parsed["diagnostics"],
        "counts": counts,
        "message": "Nenhuma alteração foi gravada." if dry_run else "Taxonomia oficial gravada e confirmada no banco.",
    }


def run_import(db: Session, dry_run: bool = True) -> dict[str, Any]:
    request = Request(SOURCE_URL, headers={"User-Agent": "ENEM-Predict/1.0"})
    with _urlopen_verified(request, timeout=45) as response:
        raw = response.read(MAX_PDF_BYTES + 1)
    if len(raw) > MAX_PDF_BYTES:
        raise ValueError("O PDF da matriz excede o limite de 20 MB.")
    text = extract_matrix_text(raw)
    parsed = parse_matrix_text(text)
    return import_taxonomy(db, parsed, dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa a taxonomia oficial da Matriz de Referência do ENEM.")
    parser.add_argument("--apply", action="store_true", help="Grava no banco; sem esta opção apenas valida e simula.")
    args = parser.parse_args()
    if SessionLocal is None:
        raise RuntimeError("Banco não configurado. Verifique DATABASE_URL/Supabase no backend.")
    with SessionLocal() as db:
        result = run_import(db, dry_run=not args.apply)
        print(result)


if __name__ == "__main__":
    main()
