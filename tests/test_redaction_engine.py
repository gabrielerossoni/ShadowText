import json
import tempfile
import unittest
from pathlib import Path

from censura_privacy.engine import (
    Span,
    build_mapping,
    redact_text,
    restore_text,
    write_mapping,
)


class RedactionEngineTests(unittest.TestCase):
    def test_redact_text_replaces_spans_with_stable_typed_tags(self):
        text = "IBAN IT60X0542811101000000123456 intestato a Mario Rossi."
        iban = "IT60X0542811101000000123456"
        person = "Mario Rossi"
        spans = [
            Span(label="iban", start=text.index(iban), end=text.index(iban) + len(iban), text=iban),
            Span(label="private_person", start=text.index(person), end=text.index(person) + len(person), text=person),
        ]

        redacted, entries = redact_text(text, spans)

        self.assertEqual(
            redacted,
            "IBAN IBAN_00001 intestato a PERSONA_00001.",
        )
        self.assertEqual(entries[0].tag, "IBAN_00001")
        self.assertEqual(entries[0].value, "IT60X0542811101000000123456")
        self.assertEqual(entries[1].tag, "PERSONA_00001")
        self.assertEqual(entries[1].value, "Mario Rossi")

    def test_mapping_json_contains_redacted_filename_and_sensitive_values(self):
        entries = redact_text(
            "Email: test@example.com",
            [Span(label="private_email", start=7, end=23, text="test@example.com")],
        )[1]

        mapping = build_mapping(
            source_filename="nota.md",
            redacted_filename="nota.censurato.md",
            entries=entries,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = write_mapping(Path(tmp), mapping)
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["redacted_filename"], "nota.censurato.md")
        self.assertEqual(payload["entries"][0]["tag"], "EMAIL_00001")
        self.assertEqual(payload["entries"][0]["value"], "test@example.com")

    def test_restore_text_replaces_tags_with_original_values(self):
        redacted = "Chiamare TELEFONO_00001 o scrivere a EMAIL_00001."
        mapping = {
            "entries": [
                {"tag": "TELEFONO_00001", "value": "+39 333 1234567"},
                {"tag": "EMAIL_00001", "value": "team@example.com"},
            ]
        }

        restored = restore_text(redacted, mapping)

        self.assertEqual(
            restored,
            "Chiamare +39 333 1234567 o scrivere a team@example.com.",
        )


if __name__ == "__main__":
    unittest.main()
