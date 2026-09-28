"""Opt-in pytest transcript of workflow runs and fake provider turns.

Set BOTPIPE_TRANSCRIPT to a Markdown path and load with
``-p botpipe.workflows.workflow_author.transcript_plugin``.
"""

from __future__ import annotations

import json
import os
from collections import OrderedDict
from collections.abc import Mapping
from functools import wraps
from pathlib import Path

import pytest
from pydantic import BaseModel

from botpipe import codec
from botpipe.providers import FakeProvider
from botpipe.runtime import Botpipe, _UNSET, current_run

_state = None


def _fence(value):
    """Fence the complete original text, including any Markdown backticks."""
    marker = "`" * max(
        3,
        max((len(part) for part in value.split("\n") if part.startswith("`")), default=0) + 1,
    )
    return f"{marker}text\n{value}\n{marker}"


def _display(value):
    if isinstance(value, str):
        return _fence(value)
    try:
        encoded = codec.encode(value)
        return _fence(json.dumps(encoded, ensure_ascii=False, indent=2))
    except (TypeError, ValueError):
        return _fence(repr(value))


def _free_text(value):
    if isinstance(value, str):
        if value:
            yield value
    elif isinstance(value, BaseModel):
        yield from _free_text(value.model_dump(mode="python"))
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _free_text(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _free_text(item)


class _Transcript:
    def __init__(self, target):
        self.target = Path(target)
        self.patches = pytest.MonkeyPatch()
        self.tests = OrderedDict()
        self.active = None

    def event(self, kind, run_id=None, **fields):
        if self.active is not None:
            self.tests.setdefault(self.active, {"events": [], "reports": []})["events"].append(
                {"kind": kind, "run_id": run_id, **fields}
            )

    def install(self):
        original_run, original_resume, original_fake = (
            Botpipe.run, Botpipe.resume, FakeProvider.run
        )
        transcript = self

        def record_result(result):
            transcript.event(
                "result", result.run_id, status=result.status,
                question=(result.pending_input or {}).get("question"),
                error=result.error, value=result.value,
            )
            return result

        @wraps(original_run)
        def run(client, definition, *args, **kwargs):
            try:
                return record_result(original_run(client, definition, *args, **kwargs))
            except BaseException as exc:
                transcript.event("exception", kwargs.get("run_id"), where="run", error=repr(exc))
                raise

        @wraps(original_resume)
        def resume_wrapper(
            client, run_id, *, answer=_UNSET, workflow=None,
            max_operations=None, timeout=None,
        ):
            if answer is not _UNSET:
                transcript.event("answer", run_id, value=answer)
            try:
                return record_result(original_resume(
                    client, run_id, answer=answer, workflow=workflow,
                    max_operations=max_operations, timeout=timeout,
                ))
            except BaseException as exc:
                transcript.event("exception", run_id, where="resume", error=repr(exc))
                raise

        @wraps(original_fake)
        def fake(provider, request):
            try:
                run_id = current_run().run_id
            except Exception:  # provider may be called outside a workflow
                run_id = None
            transcript.event(
                "prompt", run_id, prompt=request.prompt, operation=request.operation_id,
                instructions=request.instructions, session_key=request.session_key,
                session_id=request.session_id,
            )
            try:
                response = original_fake(provider, request)
            except BaseException as exc:
                transcript.event("exception", run_id, where="FakeProvider.run", error=repr(exc))
                raise
            transcript.event("response", run_id, value=response.text)
            return response

        self.patches.setattr(Botpipe, "run", run)
        self.patches.setattr(Botpipe, "resume", resume_wrapper)
        self.patches.setattr(FakeProvider, "run", fake)

    def write(self):
        lines = ["# Workflow test transcript", ""]
        for nodeid, entry in self.tests.items():
            reports = entry["reports"]
            outcome = "failed" if "failed" in reports else "skipped" if "skipped" in reports else "passed"
            lines.extend([f"## {nodeid} — {outcome}", ""])
            events = entry["events"]
            for index, event in enumerate(events):
                kind, run_id = event["kind"], event["run_id"]
                label = f"**{kind}**" + (f" (run `{run_id}`)" if run_id else "")
                lines.extend([label, ""])
                if kind == "prompt":
                    lines.extend([
                        f"Operation: `{event['operation']}`",
                        f"Session key: `{event['session_key']}`; session ID: `{event['session_id']}`",
                        "", "Prompt:", "", _fence(event["prompt"]), "",
                    ])
                    if event["instructions"] is not None:
                        lines.extend(["Instructions:", "", _fence(event["instructions"]), ""])
                elif kind in ("response", "answer"):
                    lines.extend([_display(event["value"]), ""])
                elif kind == "result":
                    lines.extend([f"Status: `{event['status']}`", ""])
                    if event["status"] == "completed":
                        lines.extend(["Final value:", "", _display(event["value"]), ""])
                    if event["question"] is not None:
                        lines.extend(["Human question:", "", _fence(event["question"]), ""])
                    if event["error"]:
                        lines.extend(["Error:", "", _fence(event["error"]), ""])
                elif kind == "exception":
                    lines.extend([f"At: `{event['where']}`", "", _fence(event["error"]), ""])
                if kind == "answer" and run_id:
                    answer_text = list(_free_text(event["value"]))
                    if not answer_text:
                        continue
                    subsequent = [
                        later["prompt"] for later in events[index + 1:]
                        if later["kind"] == "prompt" and later["run_id"] == run_id
                    ]
                    if not subsequent:
                        lines.extend([
                            "Warning: no later provider prompt was recorded for this run after "
                            "the free-text answer; inspect transformed values/session context.", "",
                        ])
                    elif any(
                        not any(
                            variant in prompt for prompt in subsequent
                            for variant in (text, json.dumps(text, ensure_ascii=False)[1:-1])
                        )
                        for text in answer_text
                    ):
                        lines.extend([
                            "Warning: free-text answer not found verbatim in later prompts "
                            "for this run; inspect transformed values/session context.", "",
                        ])
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text("\n".join(lines), encoding="utf-8")


def pytest_sessionstart(session):
    global _state
    target = os.environ.get("BOTPIPE_TRANSCRIPT")
    if target:
        _state = _Transcript(target)
        _state.install()


def pytest_runtest_logstart(nodeid, location):
    if _state is not None:
        _state.active = nodeid
        _state.tests.setdefault(nodeid, {"events": [], "reports": []})


def pytest_runtest_logreport(report):
    if _state is not None:
        _state.tests.setdefault(report.nodeid, {"events": [], "reports": []})["reports"].append(report.outcome)


def pytest_runtest_logfinish(nodeid, location):
    if _state is not None:
        _state.active = None


def pytest_sessionfinish(session, exitstatus):
    if _state is not None:
        _state.write()


def pytest_unconfigure(config):
    global _state
    if _state is not None:
        _state.patches.undo()
        _state = None
