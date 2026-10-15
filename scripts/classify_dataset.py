"""Classifica um JSON extraído pelo parser sem alterar o banco.

Uso: python scripts/classify_dataset.py prova_extracted.json --out prova_classified.json
"""
import argparse, json
from pathlib import Path
from app.services.classifier import classify_question

parser = argparse.ArgumentParser()
parser.add_argument("file")
parser.add_argument("--out", default=None)
args = parser.parse_args()

payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
for q in payload.get("questions", []):
    result = classify_question(q.get("statement_text", ""))
    q["classification"] = result

out = args.out or f"{Path(args.file).stem}_classified.json"
Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Classificação concluída: {out}")
