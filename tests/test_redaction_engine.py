import os
import tempfile
import unittest
from pathlib import Path

from shadow_text.engine import (
    Span,
    build_mapping,
    load_mapping,
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

    def test_mapping_is_encrypted_when_shadow_text_key_is_set(self):
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
            with _temporary_key("azienda-secret"):
                path = write_mapping(Path(tmp), mapping)
                raw = path.read_text(encoding="utf-8")
                payload = load_mapping(path)

        self.assertEqual(path.name, "nota.censurato.md.json.enc")
        self.assertNotIn("test@example.com", raw)
        self.assertEqual(payload["redacted_filename"], "nota.censurato.md")
        self.assertEqual(payload["entries"][0]["tag"], "EMAIL_00001")
        self.assertEqual(payload["entries"][0]["value"], "test@example.com")

    def test_mapping_requires_key_for_new_writes(self):
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
            with _temporary_key(None):
                with self.assertRaisesRegex(RuntimeError, "SHADOW_TEXT_KEY"):
                    write_mapping(Path(tmp), mapping)

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
