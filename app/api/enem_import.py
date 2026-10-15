from pathlib import Path
import json
import hashlib
from fastapi import APIRouter, HTTPException, Depends
from app.supabase_auth import require_admin
from app.database import SessionLocal
from sqlalchemy import text
from pydantic import BaseModel, Field
from app.services.enem_importer import discover, download_pdf, write_manifest, classify_document, file_identity, validate_pdf_bytes
from scripts.parse_pdf import parse_pdf
from app.services.classifier import classify_question, official_area_for_question_number
from scripts.import_dataset import run as import_dataset_run

router = APIRouter(prefix="/enem-import", tags=["enem-import"], dependencies=[Depends(require_admin)])
BASE_DIR = Path(__file__).resolve().parents[2] / "data" / "enem"

@router.get("/storage-quota")
def storage_quota():
    """Retorna o uso dos documentos importados e a margem operacional."""
    if SessionLocal is None:
        raise HTTPException(503, "Banco não configurado.")
    with SessionLocal() as db:
        row = db.execute(text("SELECT * FROM public.get_exam_import_runtime_quota()")).mappings().first()
    return dict(row) if row else {"used_bytes": 0, "warning_bytes": 419430400, "limit_bytes": 471859200, "remaining_bytes": 471859200, "usage_percent": 0, "status": "ok"}

class DiscoveryRequest(BaseModel):
    year_start:int=Field(2025,ge=1998,le=2026); year_end:int=Field(2026,ge=1998,le=2026); application:str="regular"

class ImportRequest(BaseModel):
    dataset_path: str = "data/enem/prepared_dataset.json"
    dry_run: bool = True

@router.post("/discover")
def discover_files(payload:DiscoveryRequest):
    if payload.year_start>payload.year_end: raise HTTPException(400,"Ano inicial não pode ser maior que o final.")
    items=discover(payload.year_start,payload.year_end,payload.application)
    for item in items:
        kind, special = classify_document(str(item.get("filename") or ""), str(item.get("label") or ""))
        if item.get("document_type") != "catalog":
            item["document_type"] = kind if kind != "outro" else item.get("document_type")
            item["special_version"] = special
            item["identity"] = file_identity(item)
            if special:
                item["status"] = "special"
                item["selectable"] = False
            else:
                item["selectable"] = item.get("status") == "available"
    return {"items":items,"count":len(items),"source":"INEP/RIEP"}

@router.post("/download")
def download_file(item:dict):
    try:
        result=download_pdf(item,BASE_DIR); write_manifest(BASE_DIR,[result]); return result
    except Exception as exc: raise HTTPException(502,f"Não foi possível baixar o arquivo oficial: {exc}")

@router.post("/parse")
def parse_file(payload:dict):
    storage_path=payload.get("storage_path")
    if not storage_path: raise HTTPException(400,"storage_path é obrigatório.")
    path=(BASE_DIR.parent.parent / storage_path).resolve()
    if BASE_DIR.resolve() not in path.parents: raise HTTPException(400,"Caminho fora da área de staging.")
    if not path.exists(): raise HTTPException(404,"PDF não encontrado no staging.")
    kind=payload.get("document_type","caderno")
    if kind not in ("caderno","gabarito"): raise HTTPException(400,"document_type deve ser caderno ou gabarito.")
    try:
        result=parse_pdf(str(path),kind)
        out=path.with_suffix(".parsed.json"); out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        return {"status":"parsed","result":result,"parsed_path":str(out.relative_to(BASE_DIR.parent.parent))}
    except Exception as exc: raise HTTPException(422,f"Falha ao extrair PDF: {exc}")

@router.post("/preflight")
def preflight():
    """Audita o staging antes da preparação: pares, hashes, duplicatas e qualidade."""
    files = list(BASE_DIR.rglob("*.parsed.json")) if BASE_DIR.exists() else []
    groups = {}
    for path in files:
        try: data=json.loads(path.read_text("utf-8"))
        except Exception: continue
        year=data.get("year"); day=data.get("day"); cd=data.get("caderno")
        key=(year,day,cd or path.stem.lower().replace("_parsed", ""))
        groups.setdefault(key,[]).append(data)
    rows=[]
    for key, vals in sorted(groups.items(), key=lambda x:str(x[0])):
        provas=[x for x in vals if x.get("document_type")=="caderno"]
        gab=[x for x in vals if x.get("document_type")=="gabarito"]
        q=sum(x.get("questions_found",0) for x in provas); a=sum(x.get("answers_found",0) for x in gab)
        rows.append({"key":key,"provas":len(provas),"gabaritos":len(gab),"questions":q,"answers":a,
                     "matched_expected": q == a and q > 0,"status":"ready" if provas and gab and q==a else "review"})
    return {"status":"ready" if rows and all(r["status"]=="ready" for r in rows) else ("review" if rows else "empty"),"groups":rows,"count":len(rows)}


@router.get("/manifest")
def manifest():
    path=BASE_DIR/"manifest.json"
    if not path.exists(): return {"items":[],"count":0}
    items=json.loads(path.read_text("utf-8")); return {"items":items,"count":len(items)}


@router.get("/staging")
def staging():
    """Lista artefatos parseados e identifica pares caderno/gabarito."""
    if not BASE_DIR.exists():
        return {"items": [], "count": 0}
    rows = []
    for path in sorted(BASE_DIR.rglob("*.parsed.json")):
        try:
            data = json.loads(path.read_text("utf-8"))
        except Exception:
            continue
        rows.append({
            "path": str(path.relative_to(BASE_DIR.parent.parent)),
            "source_file": data.get("source_file", path.name),
            "document_type": data.get("document_type"),
            "questions_found": data.get("questions_found", 0),
            "answers_found": data.get("answers_found", 0),
            "year": data.get("year"),
            "color": data.get("color"),
            "day": data.get("day"),
        })
    return {"items": rows, "count": len(rows)}


def _load_parsed(path: Path):
    return json.loads(path.read_text("utf-8"))


def _metadata_from_path(path: Path, data: dict):
    parts = path.parts
    year = data.get("year")
    day = data.get("day")
    color = data.get("color")
    for i, part in enumerate(parts):
        if part.isdigit() and 1998 <= int(part) <= 2026:
            year = year or int(part)
        if part.startswith("dia_"):
            try: day = day or int(part.split("_", 1)[1])
            except ValueError: pass
        if part.lower() in {"azul", "amarelo", "branco", "rosa", "cinza"}:
            color = color or part.capitalize()
    if not color and data.get("caderno") is not None:
        color = {1: "Azul", 2: "Amarelo", 3: "Branco", 4: "Rosa", 5: "Cinza"}.get(int(data["caderno"]))
    return year, day, color


@router.post("/prepare")
def prepare_dataset():
    """Consolida cadernos + gabaritos parseados em um JSON pronto para revisão/importação."""
    files = list(BASE_DIR.rglob("*.parsed.json")) if BASE_DIR.exists() else []
    notebooks = {}
    keys = {}
    for path in files:
        try: data = _load_parsed(path)
        except Exception: continue
        year, day, color = _metadata_from_path(path, data)
        key = (year, day, (color or "").lower())
        typ = data.get("document_type")
        if data.get("special_version"):
            continue
        if typ in ("caderno", "prova"):
            notebooks[key] = (path, data)
        elif typ == "gabarito":
            keys[key] = (path, data)

    questions = []
    groups = []
    for key, (path, notebook) in sorted(notebooks.items(), key=lambda x: str(x[0])):
        year, day, color_code = key
        answer_data = keys.get(key, (None, {}))[1]
        answers = answer_data.get("answers", {}) or {}
        items = notebook.get("questions", []) or []
        group = {"year": year, "day": day, "color": color_code,
                 "questions": len(items), "answers": len(answers),
                 "matched_answers": 0, "unclassified_questions": 0,
                 "status": "ready" if answers else "review"}
        for q in items:
            text = q.get("statement_text", "")
            number = int(q.get("number"))
            cls = classify_question(text)
            official_area = official_area_for_question_number(number)
            if official_area:
                # A faixa numérica é fonte mais confiável para a área do que palavras-chave.
                # Se o classificador sugerir outra área, mantém a área oficial e exige revisão da disciplina.
                if cls.get("area") != official_area:
                    cls["subject"] = None
                    cls["confidence"] = 0.0
                    cls["method"] = "official_question_number"
                cls["area"] = official_area
            if not cls.get("area") or not cls.get("subject"):
                group["unclassified_questions"] += 1
            answer = answers.get(str(number), answers.get(number))
            alts = []
            for alt in q.get("alternatives", []) or []:
                a = dict(alt)
                a["is_correct"] = bool(answer and a.get("letter", "").upper() == str(answer).upper())
                alts.append(a)
            if answer and sum(1 for alt in alts if alt["is_correct"]) == 1:
                group["matched_answers"] += 1
            questions.append({
                "exam": {"year": year, "edition": "regular", "color": str(color_code or "azul").lower(), "day": day},
                "number": number,
                "area": cls.get("area"),
                "subject": cls.get("subject"),
                "statement_text": text,
                "alternatives": alts,
                "topics": [],
                "classification": cls,
            })
        if group["matched_answers"] != len(items) or group["unclassified_questions"] > 0 or any(
            len(q.get("alternatives", []) or []) != 5 for q in items
        ):
            group["status"] = "review"
        groups.append(group)

    payload = {"exams": [{"year": g["year"], "edition": "regular", "color": str(g.get("color") or "azul").lower(), "day": g["day"]}
                          for g in groups],
               "questions": questions,
               "groups": groups,
               "diagnostics": {"groups": len(groups), "questions": len(questions),
                               "questions_with_answer": sum(1 for q in questions if any(a.get("is_correct") for a in q["alternatives"])),
                               "questions_without_answer": sum(1 for q in questions if not any(a.get("is_correct") for a in q["alternatives"])),
                               "questions_unclassified": sum(1 for q in questions if not q.get("area") or not q.get("subject"))}}
    out = BASE_DIR / "prepared_dataset.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "prepared", "path": str(out.relative_to(BASE_DIR.parent.parent)), **payload["diagnostics"], "groups": groups}


@router.post("/import")
def import_prepared(payload: ImportRequest):
    """Importa o lote preparado; por padrão executa dry-run para segurança."""
    rel = payload.dataset_path
    path = (BASE_DIR.parent.parent / rel).resolve()
    if BASE_DIR.resolve() not in path.parents or not path.exists():
        raise HTTPException(400, "Dataset preparado não encontrado no staging.")
    dry_run = payload.dry_run
    try:
        summary = import_dataset_run(str(path), dry_run=dry_run)
        return {"status": "dry_run" if dry_run else "imported", "dataset_path": rel, "summary": summary}
    except Exception as exc:
        raise HTTPException(422, f"Falha na importação: {exc}")

@router.post("/cleanup-processed")
def cleanup_processed():
    """Remove arquivos temporários já processados; nunca apaga dados estruturados."""
    import shutil
    removed = 0
    if BASE_DIR.exists():
        for path in BASE_DIR.rglob("*.pdf"):
            # Só remove o PDF quando o parser já produziu o artefato correspondente.
            if not path.with_suffix(".parsed.json").is_file():
                continue
            try:
                path.unlink(); removed += 1
            except OSError:
                pass
    return {"removed_files": removed, "message": "Área temporária limpa."}
