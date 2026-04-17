"""Append-only raw, event, and decisions logging."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .stores.filesystem import set_pending_session_note
from .workspace import PLAN_DECISIONS_PHASE_ID


DECISIONS_HEADER_PREFIX = "<autoloop-decisions-header "
LEGACY_DECISIONS_HEADER_PREFIX = "<superloop-decisions-header "
DECISIONS_HEADER_PREFIXES = (DECISIONS_HEADER_PREFIX, LEGACY_DECISIONS_HEADER_PREFIX)
DECISIONS_HEADER_SUFFIX = " />"
DECISIONS_VERSION = "1"


@dataclass(frozen=True, slots=True)
class DecisionsBlock:
    attrs: dict[str, str]
    start_offset: int
    header_end_offset: int
    end_offset: int
    body: str


class EventLogger:
    """Append-only JSONL event writer."""

    def __init__(self, run_id: str, events_file: Path) -> None:
        self.run_id = run_id
        self.events_file = events_file
        self.sequence = _latest_sequence(events_file)

    def emit(self, event_type: str, **fields: object) -> None:
        self.sequence += 1
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "seq": self.sequence,
            "event_type": event_type,
            **fields,
        }
        self.events_file.parent.mkdir(parents=True, exist_ok=True)
        with self.events_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def append_raw_log_entry(raw_phase_log: Path, body: str, **fields: object) -> None:
    header = " | ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    raw_phase_log.parent.mkdir(parents=True, exist_ok=True)
    with raw_phase_log.open("a", encoding="utf-8") as handle:
        handle.write("\n\n---\n")
        handle.write(f"{header}\n")
        handle.write("---\n")
        handle.write(body if body else "[empty stdout]\n")
        if not body.endswith("\n"):
            handle.write("\n")


def append_runtime_raw_log(
    raw_phase_log: Path,
    run_id: str,
    entry: str,
    body: str,
    *,
    pair: str | None = None,
    phase: str | None = None,
    cycle: int | None = None,
    attempt: int | None = None,
    thread_id: str | None = None,
    source: str | None = None,
) -> None:
    append_raw_log_entry(
        raw_phase_log,
        body,
        run_id=run_id,
        entry=entry,
        pair=pair,
        phase=phase,
        cycle=cycle,
        attempt=attempt,
        thread_id=thread_id,
        source=source,
    )


def parse_decisions_headers(text: str) -> list[DecisionsBlock]:
    lines = text.splitlines(keepends=True)
    headers: list[tuple[int, int, dict[str, str]]] = []
    offset = 0
    for line in lines:
        stripped = line.rstrip("\r\n")
        if any(stripped.startswith(prefix) for prefix in DECISIONS_HEADER_PREFIXES) and stripped.endswith("/>"):
            attrs = {
                match.group(1): html.unescape(match.group(2))
                for match in re.finditer(r'([a-z_]+)="([^"]*)"', stripped)
            }
            headers.append((offset, offset + len(line), attrs))
        offset += len(line)

    blocks: list[DecisionsBlock] = []
    for index, (start_offset, header_end_offset, attrs) in enumerate(headers):
        end_offset = headers[index + 1][0] if index + 1 < len(headers) else len(text)
        blocks.append(
            DecisionsBlock(
                attrs=attrs,
                start_offset=start_offset,
                header_end_offset=header_end_offset,
                end_offset=end_offset,
                body=text[header_end_offset:end_offset],
            )
        )
    return blocks


def next_decisions_block_seq(decisions_path: Path) -> int:
    return _next_decisions_sequence(decisions_path, "block_seq")


def next_decisions_qa_seq(decisions_path: Path) -> int:
    return _next_decisions_sequence(decisions_path, "qa_seq")


def next_decisions_turn_seq(decisions_path: Path, *, run_id: str, pair: str, phase_id: str) -> int:
    return _next_decisions_sequence(
        decisions_path,
        "turn_seq",
        matcher=lambda block: (
            block.attrs.get("run_id") == run_id
            and block.attrs.get("pair") == pair
            and block.attrs.get("phase_id") == phase_id
        ),
    )


def append_decisions_header(
    decisions_path: Path,
    *,
    owner: str,
    pair: str,
    phase_id: str,
    turn_seq: int,
    run_id: str,
    ts: str | None = None,
    entry: str | None = None,
    qa_seq: int | None = None,
    source: str | None = None,
) -> int:
    block_seq = next_decisions_block_seq(decisions_path)
    header = _format_decisions_header(
        {
            "version": DECISIONS_VERSION,
            "block_seq": block_seq,
            "owner": owner,
            "phase_id": phase_id,
            "pair": pair,
            "turn_seq": turn_seq,
            "run_id": run_id,
            "ts": ts or datetime.now(timezone.utc).isoformat(),
            "entry": entry,
            "qa_seq": qa_seq,
            "source": source,
        }
    )
    _append_decisions_text(decisions_path, f"{header}\n")
    return block_seq


def append_decisions_runtime_block(
    decisions_path: Path,
    *,
    pair: str,
    phase_id: str,
    run_id: str,
    entry: str,
    body: str,
    turn_seq: int | None = None,
    qa_seq: int | None = None,
    source: str | None = None,
) -> tuple[int, int]:
    resolved_turn_seq = turn_seq or next_decisions_turn_seq(decisions_path, run_id=run_id, pair=pair, phase_id=phase_id)
    resolved_qa_seq = qa_seq or next_decisions_qa_seq(decisions_path)
    append_decisions_header(
        decisions_path,
        owner="runtime",
        pair=pair,
        phase_id=phase_id,
        turn_seq=resolved_turn_seq,
        run_id=run_id,
        entry=entry,
        qa_seq=resolved_qa_seq,
        source=source,
    )
    normalized_body = body if body.endswith("\n") else f"{body}\n"
    _append_decisions_text(decisions_path, normalized_body)
    return resolved_turn_seq, resolved_qa_seq


def append_clarification(
    run_raw_phase_log: Path,
    task_raw_phase_log: Path,
    decisions_path: Path,
    session_file: Path,
    *,
    pair: str,
    phase_id: str | None,
    phase: str,
    cycle: int,
    attempt: int,
    question: str,
    answer: str,
    run_id: str,
    source: str = "human",
) -> None:
    phase_marker = phase_id or PLAN_DECISIONS_PHASE_ID
    clarification_body = f"Question:\n{question}\n\nAnswer:\n{answer}\n"
    for raw_log in (task_raw_phase_log, run_raw_phase_log):
        append_runtime_raw_log(
            raw_log,
            run_id,
            "clarification",
            clarification_body,
            pair=pair,
            phase=phase,
            cycle=cycle,
            attempt=attempt,
            source=source,
        )

    turn_seq, qa_seq = append_decisions_runtime_block(
        decisions_path,
        pair=pair,
        phase_id=phase_marker,
        run_id=run_id,
        entry="questions",
        body=question,
        source=source,
    )
    append_decisions_runtime_block(
        decisions_path,
        pair=pair,
        phase_id=phase_marker,
        run_id=run_id,
        entry="answers",
        body=answer,
        turn_seq=turn_seq,
        qa_seq=qa_seq,
        source=source,
    )
    set_pending_session_note(session_file, answer)


def extract_clarifications(run_raw_phase_log: Path) -> list[tuple[str, str]]:
    if not run_raw_phase_log.exists():
        return []
    text = run_raw_phase_log.read_text(encoding="utf-8")
    blocks = text.split("\n\n---\n")
    clarifications: list[tuple[str, str]] = []
    for block in blocks:
        if "entry=clarification" not in block:
            continue
        if "Question:\n" not in block or "\n\nAnswer:\n" not in block:
            continue
        body = block.split("---\n", 1)[-1]
        question, answer = body.split("\n\nAnswer:\n", 1)
        clarifications.append((question.replace("Question:\n", "", 1).strip(), answer.strip()))
    return clarifications


def prior_phase_status_lines(events_file: Path, selected_phase_ids: tuple[str, ...]) -> list[str]:
    if not events_file.exists():
        return []
    allowed = set(selected_phase_ids)
    lines: list[str] = []
    for raw in events_file.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        phase_id = event.get("phase_id")
        if not isinstance(phase_id, str) or phase_id not in allowed:
            continue
        if event.get("event_type") in {"phase_started", "phase_completed", "phase_blocked", "phase_deferred"}:
            lines.append(f"{phase_id}: {event.get('event_type')}")
    return lines


def _append_decisions_text(decisions_path: Path, chunk: str) -> None:
    decisions_path.parent.mkdir(parents=True, exist_ok=True)
    prefix = ""
    if decisions_path.exists():
        existing = decisions_path.read_text(encoding="utf-8")
        if existing and not existing.endswith("\n"):
            prefix = "\n"
    with decisions_path.open("a", encoding="utf-8") as handle:
        handle.write(prefix + chunk)


def _format_decisions_header(attrs: dict[str, object]) -> str:
    ordered_keys = (
        "version",
        "block_seq",
        "owner",
        "phase_id",
        "pair",
        "turn_seq",
        "run_id",
        "ts",
        "entry",
        "qa_seq",
        "source",
    )
    serialized = [
        f'{key}="{html.escape(str(attrs[key]), quote=True)}"'
        for key in ordered_keys
        if attrs.get(key) is not None
    ]
    return f"{DECISIONS_HEADER_PREFIX}{' '.join(serialized)}{DECISIONS_HEADER_SUFFIX}"


def _next_decisions_sequence(
    decisions_path: Path,
    attr_name: str,
    *,
    matcher: callable | None = None,
) -> int:
    text = decisions_path.read_text(encoding="utf-8") if decisions_path.exists() else ""
    blocks = parse_decisions_headers(text)
    values: list[int] = []
    for block in blocks:
        if matcher is not None and not matcher(block):
            continue
        raw_value = block.attrs.get(attr_name)
        if raw_value is None:
            continue
        try:
            values.append(int(raw_value))
        except ValueError:
            continue
    return (max(values) + 1) if values else 1


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
