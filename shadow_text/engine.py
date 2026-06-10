from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any, Iterable

from .crypto import decrypt_text, encrypt_text


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Span:
    label: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class RedactionEntry:
    label: str
    tag: str
    value: str
    start: int
    end: int


LABEL_PREFIXES = {
    "account_number": "CONTO",
    "company": "AZIENDA",
    "iban": "IBAN",
    "organization": "AZIENDA",
    "private_address": "INDIRIZZO",
    "private_date": "DATA",
    "private_email": "EMAIL",
    "private_person": "PERSONA",
    "private_phone": "TELEFONO",
    "private_url": "URL",
    "secret": "SEGRETO",
    "tax_code": "CODICE_FISCALE",
    "vat_number": "PARTITA_IVA",
}


def label_to_prefix(label: str) -> str:
    normalized = label.strip().lower()
    if normalized in LABEL_PREFIXES:
        return LABEL_PREFIXES[normalized]
    prefix = re.sub(r"[^A-Z0-9]+", "_", normalized.upper()).strip("_")
    return prefix or "DATO"


def redact_text(text: str, spans: Iterable[Span]) -> tuple[str, list[RedactionEntry]]:
    clean_spans = _non_overlapping_spans(text, spans)
    counters: dict[str, int] = {}
    entries: list[RedactionEntry] = []
    pieces: list[str] = []
    cursor = 0

    for span in clean_spans:
        prefix = label_to_prefix(span.label)
        counters[prefix] = counters.get(prefix, 0) + 1
        tag = f"{prefix}_{counters[prefix]:05d}"
        value = text[span.start : span.end]

        pieces.append(text[cursor : span.start])
        pieces.append(tag)
        entries.append(
            RedactionEntry(
                label=span.label,
                tag=tag,
                value=value,
                start=span.start,
                end=span.end,
            )
        )
        cursor = span.end

    pieces.append(text[cursor:])
    return "".join(pieces), entries


def build_mapping(
    *,
    source_filename: str,
    redacted_filename: str,
    entries: Iterable[RedactionEntry],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_filename": source_filename,
        "redacted_filename": redacted_filename,
        "entries": [asdict(entry) for entry in entries],
    }


def write_mapping(data_dir: Path, mapping: dict[str, Any]) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_mapping_filename(str(mapping["redacted_filename"]))
    path = data_dir / f"{filename}.enc"
    payload = json.dumps(mapping, ensure_ascii=False, indent=2)
    path.write_text(
        encrypt_text(payload),
        encoding="utf-8",
    )
    return path


def load_mapping(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".enc":
        raw = decrypt_text(raw)
    return json.loads(raw)


def restore_text(redacted_text: str, mapping: dict[str, Any]) -> str:
    restored = redacted_text
    entries = sorted(
        mapping.get("entries", []),
        key=lambda entry: len(str(entry.get("tag", ""))),
        reverse=True,
    )
    for entry in entries:
        tag = str(entry["tag"])
        value = str(entry["value"])
        restored = restored.replace(tag, value)
    return restored


def find_mapping_for_redacted_file(data_dir: Path, redacted_filename: str) -> Path | None:
    if not data_dir.exists():
        return None
    expected = data_dir / _safe_mapping_filename(redacted_filename)
    encrypted_expected = data_dir / f"{expected.name}.enc"
    if encrypted_expected.exists():
        return encrypted_expected
    if expected.exists():
        return expected
    for candidate in list(data_dir.glob("*.json.enc")) + list(data_dir.glob("*.json")):
        try:
            payload = load_mapping(candidate)
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("redacted_filename") == redacted_filename:
            return candidate
    return None


def _non_overlapping_spans(text: str, spans: Iterable[Span]) -> list[Span]:
    valid = [
        span
        for span in spans
        if 0 <= span.start < span.end <= len(text)
    ]
    valid.sort(key=lambda span: (span.start, -(span.end - span.start)))

    selected: list[Span] = []
    cursor = 0
    for span in valid:
        if span.start < cursor:
            continue
        selected.append(span)
        cursor = span.end
    return selected


def _safe_mapping_filename(redacted_filename: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", redacted_filename).strip("._")
    return f"{safe or 'mapping'}.json"
