import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from shadow_text.engine import Span
from shadow_text.engine import load_mapping
from shadow_text.memory import add_always_redact, add_never_redact, load_memory
from shadow_text.watcher import main, process_for_censura


class EmptyDetector:
    def detect(self, text: str) -> list[Span]:
        return []


class OpenAIDetector:
    def detect(self, text: str) -> list[Span]:
        value = "OpenAI"
        start = text.index(value)
        return [
            Span(
                label="private_person",
                start=start,
                end=start + len(value),
                text=value,
            )
        ]


class MemoryWorkflowTests(unittest.TestCase):
    def test_always_redact_rule_catches_model_miss_and_writes_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "Dati"
            memory_path = data_dir / "memoria.json"
            source = root / "Censura" / "nota.txt"
            source.parent.mkdir()
            source.write_text("Nome: Mario Rossi", encoding="utf-8")

            add_always_redact(memory_path, text="Mario Rossi", label="private_person")
            with _temporary_key("azienda-secret"):
                redacted = process_for_censura(
                    source,
                    data_dir=data_dir,
                    detector=EmptyDetector(),
                    memory_path=memory_path,
                )
                mapping = load_mapping(data_dir / "nota.censurato.txt.json.enc")

            self.assertIsNotNone(redacted)
            assert redacted is not None
            self.assertFalse(source.exists())
            self.assertEqual(redacted.read_text(encoding="utf-8"), "Nome: PERSONA_00001")

            self.assertEqual(mapping["entries"][0]["value"], "Mario Rossi")
            audit_line = (data_dir / "storico.jsonl").read_text(encoding="utf-8").splitlines()[0]
            self.assertEqual(json.loads(audit_line)["event"], "censor")

    def test_never_redact_rule_suppresses_false_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "Dati"
            memory_path = data_dir / "memoria.json"
            source = root / "Censura" / "nota.txt"
            source.parent.mkdir()
            source.write_text("OpenAI e una societa.", encoding="utf-8")

            add_never_redact(memory_path, text="OpenAI")
            with _temporary_key("azienda-secret"):
                redacted = process_for_censura(
                    source,
                    data_dir=data_dir,
                    detector=OpenAIDetector(),
                    memory_path=memory_path,
                )
                mapping = load_mapping(data_dir / "nota.censurato.txt.json.enc")

            self.assertIsNotNone(redacted)
            assert redacted is not None
            self.assertEqual(redacted.read_text(encoding="utf-8"), "OpenAI e una societa.")
            self.assertEqual(mapping["entries"], [])

    def test_cli_remember_redact_persists_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Dati"

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(
                    [
                        "remember-redact",
                        "--dati-dir",
                        str(data_dir),
                        "--text",
                        "Mario Rossi",
                        "--label",
                        "private_person",
                    ]
                )

            self.assertEqual(result, 0)
            memory = load_memory(data_dir / "memoria.json")
            self.assertEqual(memory["always_redact"][0]["text"], "Mario Rossi")
            self.assertEqual(memory["always_redact"][0]["label"], "private_person")

    def test_censor_logs_only_useful_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "Dati"
            source = root / "Censura" / "nota.txt"
            source.parent.mkdir()
            source.write_text("Email: test@example.com", encoding="utf-8")
            logs: list[str] = []

            with _temporary_key("azienda-secret"):
                process_for_censura(
                    source,
                    data_dir=data_dir,
                    detector=EmptyDetector(),
                    logger=logs.append,
                )

            joined = "\n".join(logs)
            self.assertIn("Dati sensibili trovati", joined)
            self.assertIn("File censurato pronto", joined)
            self.assertNotIn("Lettura file", joined)
            self.assertNotIn("Mapping scritto", joined)
            self.assertNotIn("Originale archiviato", joined)

    def test_censor_writes_quality_report_without_sensitive_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "Dati"
            source = root / "Censura" / "nota.txt"
            source.parent.mkdir()
            source.write_text("Email: test@example.com", encoding="utf-8")

            class EmailDetector:
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

            with _temporary_key("azienda-secret"):
                redacted = process_for_censura(source, data_dir=data_dir, detector=EmailDetector())

            self.assertIsNotNone(redacted)
            report_path = data_dir / "nota.censurato.txt.report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            raw_report = report_path.read_text(encoding="utf-8")
            self.assertEqual(report["total_redactions"], 1)
            self.assertEqual(report["counts_by_label"]["private_email"], 1)
            self.assertEqual(report["counts_by_tag_prefix"]["EMAIL"], 1)
            self.assertNotIn("test@example.com", raw_report)


class _temporary_key:
    def __init__(self, value: str | None) -> None:
        self.value = value
        self.original = os.environ.get("SHADOW_TEXT_KEY")

    def __enter__(self):
        if self.value is None:
            os.environ.pop("SHADOW_TEXT_KEY", None)
        else:
            os.environ["SHADOW_TEXT_KEY"] = self.value

    def __exit__(self, exc_type, exc, tb):
        if self.original is None:
            os.environ.pop("SHADOW_TEXT_KEY", None)
        else:
            os.environ["SHADOW_TEXT_KEY"] = self.original


if __name__ == "__main__":
    unittest.main()
