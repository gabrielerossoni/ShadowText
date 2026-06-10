from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from .engine import Span


SCHEMA_VERSION = 1


def load_memory(path: Path) -> dict:
    if not path.exists():
        return _empty_memory()
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("always_redact", [])
    payload.setdefault("never_redact", [])
    return payload


def save_memory(path: Path, memory: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(memory, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_always_redact(
    path: Path,
    *,
    text: str,
    label: str,
    case_sensitive: bool = False,
) -> dict:
    if not text:
        raise ValueError("Il testo da ricordare non puo essere vuoto")
    if not label:
        raise ValueError("La label non puo essere vuota")
    memory = load_memory(path)
    rule = {
        "text": text,
        "label": label,
        "case_sensitive": case_sensitive,
        "created_at": _now(),
    }
    if not _rule_exists(memory["always_redact"], rule, keys=("text", "label", "case_sensitive")):
        memory["always_redact"].append(rule)
    save_memory(path, memory)
    return memory


def add_never_redact(
    path: Path,
    *,
    text: str,
    case_sensitive: bool = False,
) -> dict:
    if not text:
        raise ValueError("Il testo da ricordare non puo essere vuoto")
    memory = load_memory(path)
    rule = {
        "text": text,
        "case_sensitive": case_sensitive,
        "created_at": _now(),
    }
    if not _rule_exists(memory["never_redact"], rule, keys=("text", "case_sensitive")):
        memory["never_redact"].append(rule)
    save_memory(path, memory)
    return memory


def apply_memory(text: str, spans: list[Span], memory: dict) -> list[Span]:
    keep_ranges = _ranges_for_rules(text, memory.get("never_redact", []))

    filtered = [
        span
        for span in spans
        if not _overlaps_any(span.start, span.end, keep_ranges)
    ]

    for rule in memory.get("always_redact", []):
        label = str(rule["label"])
        for start, end in _find_text_ranges(
            text,
            str(rule["text"]),
            case_sensitive=bool(rule.get("case_sensitive", False)),
        ):
            if _overlaps_any(start, end, keep_ranges):
                continue
            filtered.append(
                Span(
                    label=label,
                    start=start,
                    end=end,
                    text=text[start:end],
                )
            )

    return _deduplicate_spans(filtered)


def _empty_memory() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "always_redact": [],
        "never_redact": [],
    }


def _ranges_for_rules(text: str, rules: list[dict]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for rule in rules:
        ranges.extend(
            _find_text_ranges(
                text,
                str(rule["text"]),
                case_sensitive=bool(rule.get("case_sensitive", False)),
            )
        )
    return ranges


def _find_text_ranges(text: str, needle: str, *, case_sensitive: bool) -> list[tuple[int, int]]:
    if not needle:
        return []
    haystack = text if case_sensitive else text.lower()
    target = needle if case_sensitive else needle.lower()
    ranges: list[tuple[int, int]] = []
    start = 0
    while True:
        index = haystack.find(target, start)
        if index == -1:
            return ranges
        ranges.append((index, index + len(needle)))
        start = index + len(needle)


def _overlaps_any(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start < keep_end and end > keep_start for keep_start, keep_end in ranges)


def _deduplicate_spans(spans: list[Span]) -> list[Span]:
    seen = set()
    unique: list[Span] = []
    for span in sorted(spans, key=lambda item: (item.start, item.end, item.label)):
        key = (span.start, span.end, span.label)
        if key in seen:
            continue
        seen.add(key)
        unique.append(span)
    return unique


def _rule_exists(rules: list[dict], rule: dict, *, keys: tuple[str, ...]) -> bool:
    return any(all(existing.get(key) == rule.get(key) for key in keys) for existing in rules)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
