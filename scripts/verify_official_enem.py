"""Network smoke test against official INEP PDFs; never connects to or writes to the database."""
import json
import tempfile
from pathlib import Path
from urllib.request import Request

from app.services.enem_importer import candidate_2025, download_pdf
from scripts.import_taxonomy import SOURCE_URL, extract_matrix_text, parse_matrix_text, _urlopen_verified
from scripts.parse_pdf import parse_pdf


def main():
    with tempfile.TemporaryDirectory(prefix="enem-official-smoke-") as tmp:
        base_dir = Path(tmp) / "data" / "enem"
        selected = [
            item for item in candidate_2025()
            if (item["day"] == 1 and item["caderno"] == 1)
            or (item["day"] == 2 and item["caderno"] == 7)
        ]
        report = {"source": "INEP 2025 regular blue booklets", "files": []}
        parsed_by_day = {}
        for item in selected:
            record = download_pdf(item, base_dir)
            pdf_path = (base_dir.parent.parent / record["storage_path"]).resolve()
            kind = "gabarito" if item["document_type"] == "gabarito" else "caderno"
            parsed = parse_pdf(str(pdf_path), kind)
            row = {
                "filename": item["filename"],
                "day": item["day"],
                "document_type": kind,
                "status": record["status"],
                "questions_found": parsed.get("questions_found"),
                "answers_found": parsed.get("answers_found"),
                "quality_status": (parsed.get("diagnostics") or {}).get("quality_status"),
            }
            report["files"].append(row)
            parsed_by_day.setdefault(item["day"], {})[kind] = parsed

        for day in (1, 2):
            exam = parsed_by_day[day]["caderno"]
            key = parsed_by_day[day]["gabarito"]
            expected = set(range(1, 91)) if day == 1 else set(range(91, 181))
            question_numbers = {q["number"] for q in exam.get("questions", [])}
            answer_numbers = {int(number) for number in (key.get("answers") or {})}
            if len(question_numbers) != 90 or question_numbers != expected:
                raise SystemExit(f"Dia {day}: numeração/quantidade de questões inválida: {len(question_numbers)}.")
            if len(answer_numbers) != 90 or answer_numbers != expected:
                raise SystemExit(f"Dia {day}: gabarito não corresponde à numeração da prova: {len(answer_numbers)} respostas.")
            if (exam.get("diagnostics") or {}).get("quality_status") != "ready":
                raise SystemExit(f"Dia {day}: parser marcou a prova para revisão.")
            report.setdefault("days_validated", []).append(day)

    request = Request(SOURCE_URL, headers={"User-Agent": "ENEM-Predict/1.0"})
    with _urlopen_verified(request, timeout=45) as response:
        matrix_bytes = response.read(20 * 1024 * 1024 + 1)
    if len(matrix_bytes) > 20 * 1024 * 1024:
        raise SystemExit("PDF da matriz excedeu o limite de 20 MB.")
    matrix = parse_matrix_text(extract_matrix_text(matrix_bytes))
    report["taxonomy"] = matrix["diagnostics"]
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
