import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.enem_importer import download_pdf, validate_pdf_bytes
from scripts.import_dataset import normalize_area, validate_dataset


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
    def test_rejects_non_pdf_payload(self):
        valid, reason = validate_pdf_bytes(b"not a pdf" * 2000)
        self.assertFalse(valid)
        self.assertIn("PDF", reason)

    def test_rejects_tiny_pdf_payload(self):
        valid, reason = validate_pdf_bytes(b"%PDF-1.7\\nsmall")
        self.assertFalse(valid)
        self.assertIn("pequeno", reason)

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

    def test_download_returns_project_relative_path_usable_by_parse_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base_dir = root / "data" / "enem"
            url = "https://download.inep.gov.br/enem/provas_e_gabaritos/2025_PV_D1_CD1_Azul.pdf"
            data = b"%PDF-1.7\\n" + (b"x" * 11000)
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


if __name__ == "__main__":
    unittest.main()
