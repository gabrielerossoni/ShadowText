import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from shadow_text.detectors import RegexDetector
from shadow_text.engine import load_mapping, redact_text
from shadow_text.memory import add_always_redact, load_memory
from shadow_text.watcher import main, process_for_censura


class EmptyDetector:
    def detect(self, text):
        return []


class CompanyDetectionTests(unittest.TestCase):
    def test_memory_can_redact_company_names_with_azienda_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "Dati"
            source = root / "Censura" / "nota.txt"
            source.parent.mkdir()
            source.write_text("Cliente: OpenAI", encoding="utf-8")
            memory_path = data_dir / "memoria.json"
            add_always_redact(memory_path, text="OpenAI", label="company")

            redacted = process_for_censura(
                source,
                data_dir=data_dir,
                detector=EmptyDetector(),
                memory_path=memory_path,
            )

            self.assertIsNotNone(redacted)
            assert redacted is not None
            self.assertEqual(redacted.read_text(encoding="utf-8"), "Cliente: AZIENDA_00001")
            mapping = load_mapping(data_dir / "nota.censurato.txt.json.enc")
            self.assertEqual(mapping["entries"][0]["label"], "company")

    def test_regex_detects_company_names_with_legal_suffixes(self):
        text = "Fattura emessa da Rossi Consulting S.r.l. per servizi."

        spans = RegexDetector().detect(text)
        redacted, entries = redact_text(text, spans)

        self.assertIn("AZIENDA_00001", redacted)
        self.assertEqual(entries[0].label, "company")
        self.assertEqual(entries[0].value, "Rossi Consulting S.r.l.")

    def test_cli_remember_company_persists_company_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Dati"
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                result = main(
                    [
                        "remember-company",
                        "--dati-dir",
                        str(data_dir),
                        "--text",
                        "OpenAI",
                    ]
                )

            self.assertEqual(result, 0)
            memory = load_memory(data_dir / "memoria.json")
            self.assertEqual(memory["always_redact"][0]["text"], "OpenAI")
            self.assertEqual(memory["always_redact"][0]["label"], "company")


if __name__ == "__main__":
    unittest.main()
