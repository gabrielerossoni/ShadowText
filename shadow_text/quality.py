from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def build_quality_report(mapping: dict[str, Any]) -> dict[str, Any]:
    entries = list(mapping.get("entries", []))
    labels = Counter(str(entry.get("label", "unknown")) for entry in entries)
    prefixes = Counter(str(entry.get("tag", "DATO")).split("_", 1)[0] for entry in entries)
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_filename": mapping.get("source_filename"),
        "redacted_filename": mapping.get("redacted_filename"),
        "total_redactions": len(entries),
        "counts_by_label": dict(sorted(labels.items())),
        "counts_by_tag_prefix": dict(sorted(prefixes.items())),
        "confidence_average": None,
    }


def write_quality_report(data_dir: Path, mapping: dict[str, Any]) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    filename = _report_filename(str(mapping["redacted_filename"]))
    path = data_dir / filename
    path.write_text(
        json.dumps(build_quality_report(mapping), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _report_filename(redacted_filename: str) -> str:
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in redacted_filename)
    safe = safe.strip("._") or "report"
    return f"{safe}.report.json"
