from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from core.context import Context
from core.history import StepInstanceKey
from core.primitives import AWAIT_INPUT
from core.schema_registry import RUNTIME_TRACE_SCHEMA
from core.stores import InMemorySessionStore


class _State(BaseModel):
    ready: bool = False


def _context(tmp_path: Path) -> tuple[Context, Path]:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_demo"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "workflows" / "demo"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)
    ctx = Context(
        root=tmp_path,
        task_id="task-1",
        run_id="run-1",
        workflow_name="demo",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_State(),
        session_store=InMemorySessionStore(),
    )
    return ctx, run_folder


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def test_context_history_derives_scoped_telemetry_from_trace(tmp_path: Path) -> None:
    ctx, run_folder = _context(tmp_path)
    _write_jsonl(
        run_folder / "trace.jsonl",
        [
            {
                "schema": RUNTIME_TRACE_SCHEMA,
                "event_type": "step_started",
                "timestamp": "2026-04-30T10:00:00+00:00",
                "step_name": "legal_review",
                "scope": "articles",
                "item_id": "article_17",
                "visit": 3,
                "step_execution_id": "legal_review:articles:article_17:3",
            },
            {
                "schema": RUNTIME_TRACE_SCHEMA,
                "event_type": "provider_attempt_started",
                "timestamp": "2026-04-30T10:00:01+00:00",
                "step_name": "legal_review",
                "scope": "articles",
                "item_id": "article_17",
                "visit": 3,
                "step_execution_id": "legal_review:articles:article_17:3",
                "turn_kind": "producer",
                "attempt": 1,
            },
            {
                "schema": RUNTIME_TRACE_SCHEMA,
                "event_type": "provider_attempt_finished",
                "timestamp": "2026-04-30T10:00:02+00:00",
                "step_name": "legal_review",
                "scope": "articles",
                "item_id": "article_17",
                "visit": 3,
                "step_execution_id": "legal_review:articles:article_17:3",
                "turn_kind": "producer",
                "attempt": 1,
                "token_usage": {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
            },
            {
                "schema": RUNTIME_TRACE_SCHEMA,
                "event_type": "provider_attempt_started",
                "timestamp": "2026-04-30T10:00:03+00:00",
                "step_name": "legal_review",
                "scope": "articles",
                "item_id": "article_17",
                "visit": 3,
                "step_execution_id": "legal_review:articles:article_17:3",
                "turn_kind": "verifier",
                "attempt": 1,
            },
            {
                "schema": RUNTIME_TRACE_SCHEMA,
                "event_type": "provider_attempt_finished",
                "timestamp": "2026-04-30T10:00:04+00:00",
                "step_name": "legal_review",
                "scope": "articles",
                "item_id": "article_17",
                "visit": 3,
                "step_execution_id": "legal_review:articles:article_17:3",
                "turn_kind": "verifier",
                "attempt": 1,
                "token_usage": {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8},
            },
            {
                "schema": RUNTIME_TRACE_SCHEMA,
                "event_type": "hook_route_redirected",
                "timestamp": "2026-04-30T10:00:05+00:00",
                "step_name": "legal_review",
                "hook": "cap_rework",
                "phase": "on_taken",
                "from_route": "needs_rework",
                "to_route": "approved",
            },
            {
                "schema": RUNTIME_TRACE_SCHEMA,
                "event_type": "step_finished",
                "timestamp": "2026-04-30T10:00:06+00:00",
                "step_name": "legal_review",
                "scope": "articles",
                "item_id": "article_17",
                "visit": 3,
                "step_execution_id": "legal_review:articles:article_17:3",
                "candidate_route": "needs_rework",
                "final_route": "approved",
                "hook_route_redirects": [
                    {
                        "hook": "cap_rework",
                        "phase": "on_taken",
                        "from_route": "needs_rework",
                        "to_route": "approved",
                    }
                ],
                "provider_usage": {
                    "producer": {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
                    "verifier": {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8},
                },
                "event": {"tag": "approved", "reason": "accepted"},
            },
        ],
    )
    _write_jsonl(run_folder / "events.jsonl", [])

    telemetry_map = ctx.history.step_telemetry()
    key = StepInstanceKey(step_name="legal_review", scope="articles", item_id="article_17")

    assert key in telemetry_map
    telemetry = telemetry_map[key]
    assert telemetry["completed"] is True
    assert telemetry["accepted_once"] is True
    assert telemetry["status"] == "completed"
    assert telemetry["do_attempts"] == 1
    assert telemetry["verify_attempts"] == 1
    assert telemetry["token_usage"]["producer"]["total_tokens"] == 12
    assert telemetry["token_usage"]["verifier"]["total_tokens"] == 8
    assert telemetry["durations"]["total_seconds"] == 6.0

    route_records = ctx.history.routes(step="legal_review", item_id="article_17")
    assert route_records == (
        {
            "event_type": "step_finished",
            "step_name": "legal_review",
            "scope": "articles",
            "item_id": "article_17",
            "candidate_route": "needs_rework",
            "final_route": "approved",
            "runtime_control": None,
            "target_step": None,
            "terminal": None,
            "provider_attributable": False,
            "source_hook": None,
            "source_phase": None,
            "visit": 3,
            "step_execution_id": "legal_review:articles:article_17:3",
            "timestamp": "2026-04-30T10:00:06+00:00",
            "hook_route_redirects": (
                {
                    "hook": "cap_rework",
                    "phase": "on_taken",
                    "from_route": "needs_rework",
                    "to_route": "approved",
                },
            ),
        },
    )


def test_context_history_uses_runtime_control_terminal_for_status_and_route_metadata(tmp_path: Path) -> None:
    ctx, run_folder = _context(tmp_path)
    _write_jsonl(
        run_folder / "trace.jsonl",
        [
            {
                "schema": RUNTIME_TRACE_SCHEMA,
                "event_type": "step_started",
                "timestamp": "2026-04-30T11:00:00+00:00",
                "step_name": "triage",
                "visit": 1,
                "step_execution_id": "triage:1",
            },
            {
                "schema": RUNTIME_TRACE_SCHEMA,
                "event_type": "step_finished",
                "timestamp": "2026-04-30T11:00:02+00:00",
                "step_name": "triage",
                "visit": 1,
                "step_execution_id": "triage:1",
                "candidate_route": "ready",
                "runtime_control": "request_input",
                "terminal": AWAIT_INPUT,
                "provider_attributable": False,
                "source_hook": "after",
                "source_phase": "after",
            },
        ],
    )
    _write_jsonl(run_folder / "events.jsonl", [])

    telemetry = ctx.history.step_telemetry("triage")
    route_records = ctx.history.routes(step="triage")

    assert telemetry["status"] == "awaiting_input"
    assert route_records == (
        {
            "event_type": "step_finished",
            "step_name": "triage",
            "scope": None,
            "item_id": None,
            "candidate_route": "ready",
            "final_route": None,
            "runtime_control": "request_input",
            "target_step": None,
            "terminal": AWAIT_INPUT,
            "provider_attributable": False,
            "source_hook": "after",
            "source_phase": "after",
            "visit": 1,
            "step_execution_id": "triage:1",
            "timestamp": "2026-04-30T11:00:02+00:00",
            "hook_route_redirects": (),
        },
    )


def test_context_history_falls_back_to_events_without_trace(tmp_path: Path) -> None:
    ctx, run_folder = _context(tmp_path)
    _write_jsonl(
        run_folder / "events.jsonl",
        [
            {
                "ts": "2026-04-30T10:10:00+00:00",
                "seq": 1,
                "run_id": "run-1",
                "event_type": "provider_attempt_started",
                "step_name": "implement",
                "turn_kind": "llm",
                "attempt": 1,
                "visit": 1,
                "step_execution_id": "implement:1",
            },
            {
                "ts": "2026-04-30T10:10:01+00:00",
                "seq": 2,
                "run_id": "run-1",
                "event_type": "provider_attempt_finished",
                "step_name": "implement",
                "turn_kind": "llm",
                "attempt": 1,
                "visit": 1,
                "step_execution_id": "implement:1",
                "token_usage": {"input_tokens": 2, "output_tokens": 4, "total_tokens": 6},
            },
            {
                "ts": "2026-04-30T10:10:02+00:00",
                "seq": 3,
                "run_id": "run-1",
                "event_type": "step_executed",
                "workflow": "demo",
                "step_name": "implement",
            },
        ],
    )

    telemetry = ctx.history.step_telemetry("implement")

    assert ctx.history.trace() == ()
    assert telemetry["completed"] is True
    assert telemetry["status"] == "completed"
    assert telemetry["do_attempts"] == 1
    assert telemetry["verify_attempts"] == 0
    assert telemetry["token_usage"]["llm"]["total_tokens"] == 6
    assert ctx.history.failures(step="implement") == ()


def test_context_history_attributes_scoped_hook_failures_from_trace(tmp_path: Path) -> None:
    ctx, run_folder = _context(tmp_path)
    _write_jsonl(
        run_folder / "trace.jsonl",
        [
            {
                "event_type": "step_started",
                "timestamp": "2026-04-30T10:20:00+00:00",
                "step_name": "legal_review",
                "scope": "articles",
                "item_id": "article_17",
                "visit": 2,
                "step_execution_id": "legal_review:articles:article_17:2",
            },
            {
                "event_type": "hook_failed",
                "timestamp": "2026-04-30T10:20:01+00:00",
                "step_name": "legal_review",
                "scope": "articles",
                "item_id": "article_17",
                "visit": 2,
                "step_execution_id": "legal_review:articles:article_17:2",
                "phase": "on_route",
                "hook_name": "cap_rework",
                "error": "boom",
            },
        ],
    )
    _write_jsonl(run_folder / "events.jsonl", [])

    telemetry = ctx.history.step_telemetry("legal_review", item_id="article_17")
    failures = ctx.history.failures(step="legal_review", item_id="article_17")

    assert telemetry["completed"] is False
    assert telemetry["errors"] == [
        {
            "event_type": "hook_failed",
            "step_name": "legal_review",
            "scope": "articles",
            "item_id": "article_17",
            "phase": "on_route",
            "hook": "cap_rework",
            "error": "boom",
            "timestamp": "2026-04-30T10:20:01+00:00",
        }
    ]
    assert failures == (
        {
            "event_type": "hook_failed",
            "step_name": "legal_review",
            "scope": "articles",
            "item_id": "article_17",
            "phase": "on_route",
            "hook": "cap_rework",
            "error": "boom",
            "timestamp": "2026-04-30T10:20:01+00:00",
        },
    )
