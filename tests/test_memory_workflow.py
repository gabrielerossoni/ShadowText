import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from censura_privacy.engine import Span
from censura_privacy.memory import add_always_redact, add_never_redact, load_memory
from censura_privacy.watcher import main, process_for_censura


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
            redacted = process_for_censura(
                source,
                data_dir=data_dir,
                detector=EmptyDetector(),
                memory_path=memory_path,
            )

            self.assertIsNotNone(redacted)
            assert redacted is not None
            self.assertFalse(source.exists())
            self.assertEqual(redacted.read_text(encoding="utf-8"), "Nome: PERSONA_00001")

            mapping = json.loads((data_dir / "nota.censurato.txt.json").read_text(encoding="utf-8"))
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
            redacted = process_for_censura(
                source,
                data_dir=data_dir,
                detector=OpenAIDetector(),
                memory_path=memory_path,
            )

            self.assertIsNotNone(redacted)
            assert redacted is not None
            self.assertEqual(redacted.read_text(encoding="utf-8"), "OpenAI e una societa.")
            mapping = json.loads((data_dir / "nota.censurato.txt.json").read_text(encoding="utf-8"))
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


if __name__ == "__main__":
    unittest.main()
