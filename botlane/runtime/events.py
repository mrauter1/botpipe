"""Append-only event logging for filesystem runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from botlane.core.schema_registry import RUNTIME_EVENT_SCHEMA


class EventLogger:
    """Append-only JSONL event writer."""

    def __init__(self, run_id: str, events_file: Path) -> None:
        self.run_id = run_id
        self.events_file = events_file
        self.sequence = _latest_sequence(events_file)

    def emit(self, event_type: str, **fields: object) -> None:
        self.sequence = max(self.sequence, _latest_sequence(self.events_file)) + 1
        event = {
            "schema": RUNTIME_EVENT_SCHEMA,
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "seq": self.sequence,
            "event_type": event_type,
            **fields,
        }
        self.events_file.parent.mkdir(parents=True, exist_ok=True)
        with self.events_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _latest_sequence(events_file: Path) -> int:
    if not events_file.exists():
        return 0
    last_sequence = 0
    for raw in events_file.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        seq = event.get("seq")
        if isinstance(seq, int):
            last_sequence = max(last_sequence, seq)
    return last_sequence
