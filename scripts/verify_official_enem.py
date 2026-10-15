"""Smoke-test official INEP PDFs without importing questions into the database."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.enem_importer import candidate_2025, download_pdf
from scripts.parse_pdf import parse_pdf


TARGETS = {
    ("caderno", 1, 1): ("Linguagens/Humanas", 1, "Azul"),
    ("gabarito", 1, 1): ("Gabarito dia 1", 1, "Azul"),
    ("caderno", 2, 7): ("Natureza/Matemática", 2, "Azul"),
    ("gabarito", 2, 7): ("Gabarito dia 2", 2, "Azul"),
}


def main():
    selected = [
        item for item in candidate_2025()
        if (item["document_type"], item["day"], item["caderno"]) in TARGETS
    ]
    reports = []
    failures = []

    with tempfile.TemporaryDirectory(prefix="enem-official-smoke-") as tmp:
        root = Path(tmp)
        base_dir = root / "data" / "enem"
        for item in selected:
            kind, day, booklet = item["document_type"], item["day"], item["caderno"]
            record = download_pdf(item, base_dir)
            pdf_path = root / record["storage_path"]
            parsed = parse_pdf(str(pdf_path), "gabarito" if kind == "gabarito" else "prova")
            report = {
                "file": item["filename"],
                "day": parsed.get("day"),
                "booklet": parsed.get("caderno"),
                "color": parsed.get("color"),
                "document_type": kind,
            }
            if kind == "caderno":
                diag = parsed.get("diagnostics", {})
                report.update({
                    "questions_found": parsed.get("questions_found", 0),
                    "questions_with_five_alternatives": diag.get("questions_with_5_alternatives", 0),
                    "quality_status": diag.get("quality_status"),
                    "complete_numbering": diag.get("complete_numbering"),
                })
                if parsed.get("questions_found") != 90:
                    failures.append(f"{item['filename']}: esperado 90 questões, encontrado {parsed.get('questions_found')}")
                if diag.get("quality_status") != "ready":
                    failures.append(f"{item['filename']}: parser marcou qualidade como {diag.get('quality_status')}")
                if parsed.get("day") != day or parsed.get("color") != item["color"]:
                    failures.append(f"{item['filename']}: metadados não correspondem à capa oficial")
            else:
                answers = parsed.get("answers_found", 0)
                report["answers_found"] = answers
                if answers < 90:
                    failures.append(f"{item['filename']}: esperado ao menos 90 respostas, encontrado {answers}")
                if parsed.get("day") != day or parsed.get("color") != item["color"]:
                    failures.append(f"{item['filename']}: metadados não correspondem à capa oficial")
            reports.append(report)

    expected_count = len(TARGETS)
    if len(reports) != expected_count:
        failures.append(f"Esperados {expected_count} documentos oficiais; processados {len(reports)}")

    print(json.dumps({"documents": reports, "failures": failures}, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
