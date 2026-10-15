import tempfile
import unittest
from pathlib import Path

from app.services.enem_importer import download_pdf, validate_pdf_bytes


class EnemImporterTests(unittest.TestCase):
    def test_rejects_non_pdf_payload(self):
        valid, reason = validate_pdf_bytes(b"not a pdf" * 2000)
        self.assertFalse(valid)
        self.assertIn("PDF", reason)

    def test_rejects_tiny_pdf_payload(self):
        valid, reason = validate_pdf_bytes(b"%PDF-1.7\nsmall")
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
                    "filename": "prova.pdf",
                    "source_url": "https://example.com/prova.pdf",
                }, Path(tmp))
            self.assertEqual(list(Path(tmp).rglob("*.pdf")), [])


if __name__ == "__main__":
    unittest.main()
