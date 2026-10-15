"""Network smoke test against official INEP PDFs; never connects to or writes to the database."""
import json
import tempfile
from pathlib import Path
from urllib.request import Request

from app.services.enem_importer import candidate_official_cycle, download_pdf
from scripts.import_taxonomy import SOURCE_URL, extract_matrix_text, parse_matrix_text, _urlopen_verified
from scripts.parse_pdf import parse_pdf


def main():
    with tempfile.TemporaryDirectory(prefix="enem-official-smoke-") as tmp:
        base_dir = Path(tmp) / "data" / "enem"
        selected = candidate_official_cycle()
        report = {"source": "INEP regular exams 2023–2025", "files": []}
        parsed_by_year_day = {}
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
            parsed_by_year_day.setdefault((item["year"], item["day"]), {})[kind] = parsed

        for year in (2023, 2024, 2025):
          for day in (1, 2):
            exam = parsed_by_year_day[(year, day)]["caderno"]
            key = parsed_by_year_day[(year, day)]["gabarito"]
            expected = set(range(1, 91)) if day == 1 else set(range(91, 181))
            question_numbers = {q["number"] for q in exam.get("questions", [])}
            answer_numbers = {int(number) for number in (key.get("answers") or {})}
            if len(question_numbers) != 90 or question_numbers != expected:
                raise SystemExit(f"{year}, dia {day}: numeração/quantidade de questões inválida: {len(question_numbers)}.")
            if len(answer_numbers) != 90 or answer_numbers != expected:
                raise SystemExit(f"{year}, dia {day}: gabarito não corresponde à numeração da prova: {len(answer_numbers)} respostas.")
            if (exam.get("diagnostics") or {}).get("quality_status") != "ready":
                raise SystemExit(f"{year}, dia {day}: parser marcou a prova para revisão.")
            report.setdefault("days_validated", []).append({"year": year, "day": day})

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
