import ssl
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError
from unittest.mock import patch

from app.services.enem_importer import download_pdf, validate_pdf_bytes, _urlopen_verified
from scripts.import_dataset import normalize_area, validate_dataset
from scripts.parse_pdf import infer_metadata, parse_pdf
from app.services.enem_importer import candidate_2025
from app.services.classifier import official_area_for_question_number
from app.api.learning import simulation_readiness_status, simulation_exam_year


class FakeResponse:
    def __init__(self, data, url):
        self.data = data
        self.url = url
        self.headers = {"Content-Length": str(len(data))}
        self.read_once = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def geturl(self):
        return self.url

    def read(self, _size=-1):
        if self.read_once:
            return b""
        self.read_once = True
        return self.data


class EnemImporterTests(unittest.TestCase):
    def test_official_download_uses_verified_certifi_ca_context(self):
        with patch("app.services.enem_importer.urlopen") as mocked:
            _urlopen_verified("https://download.inep.gov.br/test.pdf", timeout=7)
        context = mocked.call_args.kwargs["context"]
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(mocked.call_args.kwargs["timeout"], 7)

    def test_rejects_non_pdf_payload(self):
        valid, reason = validate_pdf_bytes(b"not a pdf" * 2000)
        self.assertFalse(valid)
        self.assertIn("PDF", reason)

    def test_rejects_tiny_pdf_payload(self):
        valid, reason = validate_pdf_bytes(b"%PDF-1.7\nsmall")
        self.assertFalse(valid)
        self.assertIn("pequeno", reason)

    def test_simulations_map_to_three_distinct_official_exam_years(self):
        self.assertEqual(simulation_exam_year(2026, 1), 2025)
        self.assertEqual(simulation_exam_year(2026, 2), 2024)
        self.assertEqual(simulation_exam_year(2026, 3), 2023)

    def test_simulation_readiness_status_never_marks_partial_selection_ready(self):
        self.assertEqual(simulation_readiness_status(180, 0), "not_generated")
        self.assertEqual(simulation_readiness_status(180, 70), "incomplete")
        self.assertEqual(simulation_readiness_status(180, 179), "incomplete")
        self.assertEqual(simulation_readiness_status(180, 180), "ready")
        self.assertEqual(simulation_readiness_status(0, 0), "not_generated")

    def test_official_area_mapping_uses_enem_question_ranges(self):
        self.assertEqual(official_area_for_question_number(1), "Linguagens")
        self.assertEqual(official_area_for_question_number(45), "Linguagens")
        self.assertEqual(official_area_for_question_number(46), "Ciências Humanas")
        self.assertEqual(official_area_for_question_number(90), "Ciências Humanas")
        self.assertEqual(official_area_for_question_number(91), "Ciências da Natureza")
        self.assertEqual(official_area_for_question_number(135), "Ciências da Natureza")
        self.assertEqual(official_area_for_question_number(136), "Matemática")
        self.assertEqual(official_area_for_question_number(180), "Matemática")
        self.assertIsNone(official_area_for_question_number(181))

    def test_2025_candidate_urls_use_official_day_and_booklet_codes(self):
        items = candidate_2025()
        urls = {item["source_url"] for item in items}
        self.assertIn("https://download.inep.gov.br/enem/provas_e_gabaritos/2025_PV_impresso_D1_CD1.pdf", urls)
        self.assertIn("https://download.inep.gov.br/enem/provas_e_gabaritos/2025_GB_impresso_D6_CD7.pdf", urls)
        day_two_blue = next(item for item in items if item["day"] == 2 and item["caderno"] == 7 and item["document_type"] == "caderno")
        self.assertEqual(day_two_blue["color"], "Azul")

    def test_metadata_uses_pdf_cover_for_day_and_color(self):
        metadata = infer_metadata("2025_GB_impresso_D6_CD7.pdf", "ENEM 2025\\n2º dia\\nCADERNO 7\\nAzul")
        self.assertEqual(metadata["year"], 2025)
        self.assertEqual(metadata["day"], 2)
        self.assertEqual(metadata["caderno"], 7)
        self.assertEqual(metadata["color"], "Azul")

    def test_download_rejects_untrusted_host_before_network_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "domínio oficial"):
                download_pdf({
                    "year": 2025,
                    "day": 1,
                    "color": "Azul",
                    "document_type": "caderno",
                    "filename": "2025_PV_D1_CD1_Azul.pdf",
                    "source_url": "https://example.com/2025_PV_D1_CD1_Azul.pdf",
                }, Path(tmp) / "data" / "enem")
            self.assertEqual(list(Path(tmp).rglob("*.pdf")), [])

    def test_download_retries_transient_connection_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base_dir = root / "data" / "enem"
            url = "https://download.inep.gov.br/enem/provas_e_gabaritos/2025_PV_impresso_D1_CD1.pdf"
            data = b"%PDF-1.7\\n" + (b"x" * 11000)
            response = FakeResponse(data, url)
            with patch("app.services.enem_importer.urlopen", side_effect=[URLError("temporary reset"), response]) as mocked, patch("app.services.enem_importer.time.sleep"):
                result = download_pdf({
                    "year": 2025, "day": 1, "color": "Azul", "document_type": "caderno",
                    "filename": "2025_PV_impresso_D1_CD1.pdf", "source_url": url,
                }, base_dir)
            self.assertEqual(mocked.call_count, 2)
            self.assertEqual(result["status"], "downloaded")

    def test_download_returns_project_relative_path_usable_by_parse_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base_dir = root / "data" / "enem"
            url = "https://download.inep.gov.br/enem/provas_e_gabaritos/2025_PV_D1_CD1_Azul.pdf"
            data = b"%PDF-1.7\n" + (b"x" * 11000)
            with patch("app.services.enem_importer.urlopen", return_value=FakeResponse(data, url)):
                result = download_pdf({
                    "year": 2025,
                    "day": 1,
                    "color": "Azul",
                    "document_type": "caderno",
                    "filename": "2025_PV_D1_CD1_Azul.pdf",
                    "source_url": url,
                }, base_dir)
            self.assertTrue(result["storage_path"].startswith("data/enem/"))
            self.assertTrue((root / result["storage_path"]).is_file())

    def test_normalizes_classifier_area_to_existing_official_code(self):
        self.assertEqual(normalize_area("Linguagens"), ("LC", "Linguagens, Códigos e suas Tecnologias"))
        self.assertEqual(normalize_area("Ciências da Natureza"), ("CN", "Ciências da Natureza e suas Tecnologias"))

    def test_dataset_rejects_unclassified_question(self):
        payload = {"questions": [{
            "statement_text": "Enunciado de teste",
            "alternatives": [
                {"letter": "A", "text": "A", "is_correct": True},
                {"letter": "B", "text": "B", "is_correct": False},
            ],
        }]}
        with self.assertRaisesRegex(ValueError, "área/disciplina não classificada"):
            validate_dataset(payload)

    def test_dataset_rejects_incomplete_five_option_question(self):
        payload = {"questions": [{
            "statement_text": "Enunciado de teste",
            "area": "Matemática",
            "subject": "Matemática",
            "alternatives": [
                {"letter": "A", "text": "A", "is_correct": True},
                {"letter": "B", "text": "B", "is_correct": False},
                {"letter": "C", "text": "C", "is_correct": False},
                {"letter": "D", "text": "D", "is_correct": False},
            ],
        }]}
        with self.assertRaisesRegex(ValueError, "cinco alternativas"):
            validate_dataset(payload)

    def test_dataset_rejects_duplicate_alternative_letters(self):
        payload = {"questions": [{
            "statement_text": "Enunciado de teste",
            "area": "Matemática",
            "subject": "Matemática",
            "alternatives": [
                {"letter": "A", "text": "A1", "is_correct": True},
                {"letter": "A", "text": "A2", "is_correct": False},
                {"letter": "C", "text": "C", "is_correct": False},
                {"letter": "D", "text": "D", "is_correct": False},
                {"letter": "E", "text": "E", "is_correct": False},
            ],
        }]}
        with self.assertRaisesRegex(ValueError, "duplicadas"):
            validate_dataset(payload)

    def test_dataset_rejects_incomplete_exam_caderno(self):
        alternatives = [
            {"letter": "A", "text": "A", "is_correct": True},
            {"letter": "B", "text": "B", "is_correct": False},
            {"letter": "C", "text": "C", "is_correct": False},
            {"letter": "D", "text": "D", "is_correct": False},
            {"letter": "E", "text": "E", "is_correct": False},
        ]
        exam = {"year": 2024, "edition": "regular", "color": "azul", "day": 1}
        payload = {"questions": [
            {"exam": exam, "number": number, "statement_text": f"Questão {number}",
             "area": "Matemática", "subject": "Matemática", "alternatives": alternatives}
            for number in range(1, 90)
        ]}
        with self.assertRaisesRegex(ValueError, "caderno incompleto"):
            validate_dataset(payload)

    def test_dataset_accepts_official_day_two_numbering(self):
        alternatives = [
            {"letter": "A", "text": "A", "is_correct": True},
            {"letter": "B", "text": "B", "is_correct": False},
            {"letter": "C", "text": "C", "is_correct": False},
            {"letter": "D", "text": "D", "is_correct": False},
            {"letter": "E", "text": "E", "is_correct": False},
        ]
        exam = {"year": 2025, "edition": "regular", "color": "azul", "day": 2}
        payload = {"questions": [
            {"exam": exam, "number": number, "statement_text": f"Questão {number}",
             "area": "Ciências da Natureza", "subject": "Biologia", "alternatives": alternatives}
            for number in range(91, 181)
        ]}
        self.assertEqual(validate_dataset(payload), 90)

    def test_dataset_rejects_question_without_exactly_one_answer(self):
        payload = {"questions": [{
            "statement_text": "Enunciado de teste",
            "area": "Matemática",
            "subject": "Matemática",
            "alternatives": [
                {"letter": "A", "text": "A", "is_correct": False},
                {"letter": "B", "text": "B", "is_correct": False},
            ],
        }]}
        with self.assertRaisesRegex(ValueError, "exatamente um gabarito correto"):
            validate_dataset(payload)



class PdfParserCompletenessTests(unittest.TestCase):
    @staticmethod
    def make_exam(count=90, duplicate_first=False, start=1):
        blocks = []
        numbers = list(range(start, start + count))
        if duplicate_first:
            numbers.insert(1, start)
        for number in numbers:
            blocks.append(
                f"QUESTÃO {number} Enunciado da questão {number}\n"
                "A) Alternativa A\nB) Alternativa B\nC) Alternativa C\n"
                "D) Alternativa D\nE) Alternativa E"
            )
        return "\n".join(blocks)

    def test_parser_accepts_complete_booklet_with_inline_headers(self):
        text = self.make_exam(90)
        with patch("scripts.parse_pdf.extract_raw_pages", return_value=[text]):
            result = parse_pdf("2025_PV_D1_CD1_Azul.pdf")
        self.assertEqual(result["questions_found"], 90)
        self.assertEqual(result["questions"][0]["statement_text"], "Enunciado da questão 1")
        self.assertEqual(result["diagnostics"]["quality_status"], "ready")
        self.assertTrue(result["diagnostics"]["complete_numbering"])

    def test_parser_accepts_day_two_question_numbers_91_to_180(self):
        text = self.make_exam(90, start=91)
        with patch("scripts.parse_pdf.extract_raw_pages", return_value=[text]):
            result = parse_pdf("2025_PV_D2_CD1_Azul.pdf")
        self.assertEqual(result["questions_found"], 90)
        self.assertEqual(result["questions"][0]["number"], 91)
        self.assertEqual(result["questions"][-1]["number"], 180)
        self.assertEqual(result["diagnostics"]["quality_status"], "ready")

    def test_parser_marks_incomplete_booklet_for_review(self):
        text = self.make_exam(89)
        with patch("scripts.parse_pdf.extract_raw_pages", return_value=[text]):
            result = parse_pdf("2025_PV_D1_CD1_Azul.pdf")
        self.assertEqual(result["questions_found"], 89)
        self.assertEqual(result["diagnostics"]["quality_status"], "review")
        self.assertFalse(result["diagnostics"]["complete_numbering"])

    def test_parser_detects_duplicate_question_headers(self):
        text = self.make_exam(90, duplicate_first=True)
        with patch("scripts.parse_pdf.extract_raw_pages", return_value=[text]):
            result = parse_pdf("2025_PV_D1_CD1_Azul.pdf")
        self.assertTrue(result["diagnostics"]["duplicate_numbers"])
        self.assertEqual(result["diagnostics"]["quality_status"], "review")


if __name__ == "__main__":
    unittest.main()
