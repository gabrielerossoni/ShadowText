import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from shadow_text.document_io import read_document
from shadow_text.engine import RedactionEntry, Span
from shadow_text.pdf_redaction import _find_ocr_rect
from shadow_text.watcher import process_for_censura, process_for_riunione


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


class CountingDetector:
    def __init__(self) -> None:
        self.calls = 0

    def detect(self, text: str) -> list[Span]:
        self.calls += 1
        value = "test@example.com"
        start = text.index(value)
        return [Span(label="private_email", start=start, end=start + len(value), text=value)]


class RepeatedIbanDetector:
    def detect(self, text: str) -> list[Span]:
        value = "IT60X0542811101000000123456"
        spans: list[Span] = []
        cursor = 0
        while True:
            start = text.find(value, cursor)
            if start == -1:
                return spans
            spans.append(Span(label="iban", start=start, end=start + len(value), text=value))
            cursor = start + len(value)


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

    def test_pdf_always_uses_configured_detector(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            censura = root / "Censura"
            dati = root / "Dati"
            censura.mkdir()
            dati.mkdir()
            source = censura / "nota.pdf"
            _write_test_pdf(source, "Contatto: test@example.com")
            detector = CountingDetector()

            redacted = process_for_censura(
                source,
                data_dir=dati,
                detector=detector,
            )

            self.assertIsNotNone(redacted)
            assert redacted is not None
            self.assertEqual(detector.calls, 1)
            self.assertIn("EMAIL_00001", _read_pdf_text(redacted))

    def test_pdf_repeated_iban_gets_distinct_redactions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            censura = root / "Censura"
            dati = root / "Dati"
            censura.mkdir()
            dati.mkdir()
            source = censura / "iban.pdf"
            iban = "IT60X0542811101000000123456"
            _write_multiline_pdf(
                source,
                [
                    f"Primo IBAN: {iban}",
                    f"Secondo IBAN: {iban}",
                    f"Terzo IBAN: {iban}",
                    f"Quarto IBAN: {iban}",
                    f"Quinto IBAN: {iban}",
                ],
            )

            redacted = process_for_censura(
                source,
                data_dir=dati,
                detector=RepeatedIbanDetector(),
            )

            self.assertIsNotNone(redacted)
            assert redacted is not None
            text = _read_pdf_text(redacted)
            self.assertNotIn(iban, text)
            for index in range(1, 6):
                self.assertIn(f"IBAN_{index:05d}", text)

    def test_ocr_tokens_can_locate_redaction_rect(self):
        tokens = [
            {"text": "Mario", "start": 0, "end": 5, "page_index": 0, "x0": 10, "y0": 20, "x1": 40, "y1": 32},
            {"text": "Rossi", "start": 6, "end": 11, "page_index": 0, "x0": 45, "y0": 20, "x1": 80, "y1": 32},
        ]
        entry = RedactionEntry(
            label="private_person",
            tag="PERSONA_00001",
            value="Mario Rossi",
            start=0,
            end=11,
        )

        rect = _find_ocr_rect(entry, tokens)

        self.assertIsNotNone(rect)
        assert rect is not None
        page_index, fitz_rect = rect
        self.assertEqual(page_index, 0)
        self.assertEqual((fitz_rect.x0, fitz_rect.y0, fitz_rect.x1, fitz_rect.y1), (10, 20, 80, 32))


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


def _write_multiline_pdf(path: Path, lines: list[str]) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    y = 760
    for line in lines:
        pdf.drawString(72, y, line)
        y -= 28
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
