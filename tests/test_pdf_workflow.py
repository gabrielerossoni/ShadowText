import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from censura_privacy.document_io import read_document
from censura_privacy.engine import Span
from censura_privacy.watcher import process_for_censura, process_for_riunione


class StaticEmailDetector:
    def detect(self, text: str) -> list[Span]:
        value = "test@example.com"
        start = text.index(value)
        return [
            Span(
                label="private_email",
                start=start,
                end=start + len(value),
                text=value,
            )
        ]


class FailingDetector:
    def detect(self, text: str) -> list[Span]:
        raise AssertionError("slow detector should not be called for fast PDF mode")


class PdfWorkflowTests(unittest.TestCase):
    def test_censor_and_restore_keep_pdf_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            censura = root / "Censura"
            dati = root / "Dati"
            riunione = root / "Riunione"
            censura.mkdir()
            dati.mkdir()
            riunione.mkdir()

            source = censura / "nota.pdf"
            _write_test_pdf(source, "Contatto: test@example.com")

            redacted = process_for_censura(
                source,
                data_dir=dati,
                detector=StaticEmailDetector(),
            )

            self.assertIsNotNone(redacted)
            assert redacted is not None
            self.assertFalse(source.exists())
            self.assertTrue((dati / "Originali" / "nota.pdf").exists())
            self.assertEqual(redacted.name, "nota.censurato.pdf")
            self.assertTrue(redacted.read_bytes().startswith(b"%PDF"))
            self.assertIn("EMAIL_00001", _read_pdf_text(redacted))
            self.assertNotIn("test@example.com", _read_pdf_text(redacted))

            riunione_file = riunione / redacted.name
            riunione_file.write_bytes(redacted.read_bytes())
            restored = process_for_riunione(riunione_file, data_dir=dati)

            self.assertIsNotNone(restored)
            assert restored is not None
            self.assertEqual(restored.name, "nota.ripristinato.pdf")
            self.assertFalse(riunione_file.exists())
            self.assertTrue(restored.read_bytes().startswith(b"%PDF"))
            self.assertIn("test@example.com", _read_pdf_text(restored))
            self.assertNotIn("EMAIL_00001", _read_pdf_text(restored))

    def test_pdf_redaction_preserves_page_count_and_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            censura = root / "Censura"
            dati = root / "Dati"
            censura.mkdir()
            dati.mkdir()

            source = censura / "custom.pdf"
            _write_two_page_custom_pdf(source)
            original_sizes = _page_sizes(source)

            redacted = process_for_censura(
                source,
                data_dir=dati,
                detector=StaticEmailDetector(),
            )

            self.assertIsNotNone(redacted)
            assert redacted is not None
            self.assertEqual(redacted.name, "custom.censurato.pdf")
            self.assertEqual(_page_sizes(redacted), original_sizes)
            self.assertEqual(len(PdfReader(str(redacted)).pages), 2)

    def test_pdf_text_extraction_reads_pdf_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "nota.pdf"
            _write_test_pdf(source, "Contatto: test@example.com")

            document = read_document(source)

            self.assertEqual(document.output_suffix, ".pdf")
            self.assertIn("test@example.com", document.text)

    def test_fast_pdf_mode_skips_slow_detector(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            censura = root / "Censura"
            dati = root / "Dati"
            censura.mkdir()
            dati.mkdir()
            source = censura / "nota.pdf"
            _write_test_pdf(source, "Contatto: test@example.com")

            redacted = process_for_censura(
                source,
                data_dir=dati,
                detector=FailingDetector(),
                fast_pdf=True,
            )

            self.assertIsNotNone(redacted)
            assert redacted is not None
            self.assertIn("EMAIL_00001", _read_pdf_text(redacted))


def _write_test_pdf(path: Path, text: str) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.drawString(72, 760, text)
    pdf.save()


def _write_two_page_custom_pdf(path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=(320, 480))
    pdf.drawString(40, 420, "Contatto: test@example.com")
    pdf.showPage()
    pdf.setPageSize((640, 360))
    pdf.drawString(40, 300, "Seconda pagina senza dati")
    pdf.save()


def _read_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _page_sizes(path: Path) -> list[tuple[float, float]]:
    reader = PdfReader(str(path))
    return [
        (float(page.mediabox.width), float(page.mediabox.height))
        for page in reader.pages
    ]


if __name__ == "__main__":
    unittest.main()
