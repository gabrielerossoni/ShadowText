from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def write_audit(data_dir: Path, event: str, payload: dict[str, Any]) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "storico.jsonl"
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **payload,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path
