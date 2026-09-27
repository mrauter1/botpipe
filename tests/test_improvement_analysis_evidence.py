from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path

import pytest

from labs.workflows.improve_workflow.analysis_evidence import (
    freeze_analysis_evidence,
    validate_exact_quote,
    verify_analysis_evidence,
)


def _artifact(path: Path, name: str) -> dict:
    data = path.read_bytes()
    return {
        "name": name,
        "path": str(path),
        "source_path": str(path),
        "kind": "text",
        "digest": sha256(data).hexdigest(),
        "schema": None,
    }


def test_analysis_bundle_keeps_drafts_rejection_and_artifact_versions(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("draft artifact version one")
    second.write_text("draft artifact version two")
    operations = [
        {
            "id": "run:root:0",
            "kind": "provider",
            "inputs": {"value": {"prompt": "produce the first draft"}},
            "response": {"text": "first draft response"},
            "result": {"artifact": _artifact(first, "draft")},
        },
        {
            "id": "run:root:1",
            "kind": "provider",
            "inputs": {"value": {"prompt": "revise the draft"}},
            "response": {"text": "second draft response"},
            "result": {"artifact": _artifact(second, "draft")},
        },
        {
            "id": "run:root:2",
            "kind": "provider",
            "inputs": {"value": {"prompt": "review both drafts"}},
            "response": {
                "text": "Rejected: the second draft removed a required boundary case."
            },
            "result": None,
        },
    ]
    frozen = freeze_analysis_evidence(
        (
            {
                "run": {
                    "run_id": "run",
                    "task_id": "task",
                    "status": "completed",
                    "version": "workflow-v1",
                    "surface_id": "surface-v1",
                },
                "operations": operations,
            },
        ),
        tmp_path / "bundle",
    )
    verify_analysis_evidence(frozen)
    root = Path(frozen.root)
    responses = sorted(root.glob("runs/*/operations/*/response.md"))
    assert [path.read_text() for path in responses] == [
        "first draft response",
        "second draft response",
        "Rejected: the second draft removed a required boundary case.",
    ]
    review_path = responses[-1].relative_to(root).as_posix()
    validate_exact_quote(root, review_path, "removed a required boundary case")
    assert sorted(path.read_text() for path in (root / "artifacts").iterdir()) == [
        "draft artifact version one",
        "draft artifact version two",
    ]


def test_analysis_bundle_marks_bounded_and_unavailable_content(tmp_path):
    missing = tmp_path / "missing.txt"
    operation = {
        "id": "run:root:0",
        "kind": "provider",
        "inputs": {"value": {"prompt": "x" * 5000}},
        "response": {"text": "y" * 5000},
        "result": {
            "artifact": {
                "name": "missing",
                "path": str(missing),
                "source_path": str(missing),
                "kind": "text",
                "digest": "a" * 64,
                "schema": None,
            }
        },
    }
    frozen = freeze_analysis_evidence(
        ({"run": {"run_id": "run", "status": "completed"}, "operations": [operation]},),
        tmp_path / "bundle",
        max_bytes=3000,
    )
    verify_analysis_evidence(frozen)
    index = json.loads((Path(frozen.root) / "index.json").read_text())
    reasons = {item["reason"] for item in index["omissions"]}
    assert reasons == {"max_evidence_bytes", "recorded_artifact_unavailable"}
    assert (
        sum((Path(frozen.root) / relative).stat().st_size for relative in frozen.hashes)
        <= 3000
    )


def _single_response_inspection():
    return (
        {
            "run": {"run_id": "run", "status": "completed"},
            "operations": [
                {
                    "id": "run:root:0",
                    "kind": "provider",
                    "inputs": {"value": {"prompt": "draft"}},
                    "response": {"text": "completed response"},
                    "result": None,
                }
            ],
        },
    )


def test_interrupted_partial_generation_replays_from_fresh_staging(
    tmp_path, monkeypatch
):
    destination = tmp_path / "nested" / "bundle"
    original_write = Path.write_bytes

    def interrupt_response(path, data):
        if path.name == "response.md":
            raise KeyboardInterrupt("interrupt staged evidence write")
        return original_write(path, data)

    monkeypatch.setattr(Path, "write_bytes", interrupt_response)
    with pytest.raises(KeyboardInterrupt, match="staged evidence write"):
        freeze_analysis_evidence(_single_response_inspection(), destination)
    assert not destination.exists()
    assert not list(tmp_path.glob(".bundle.pending-*"))

    monkeypatch.setattr(Path, "write_bytes", original_write)
    frozen = freeze_analysis_evidence(_single_response_inspection(), destination)
    verify_analysis_evidence(frozen)
    assert (
        Path(frozen.root) / "runs/001-run/operations/001-run-root-0/response.md"
    ).read_text() == ("completed response")


def test_installed_generation_replays_after_completion_before_activity_commit(
    tmp_path, monkeypatch
):
    destination = tmp_path / "nested" / "bundle"
    history = tmp_path / "history"
    history.mkdir()
    ledger = history / "ledger.jsonl"
    ledger.write_text("original immutable history\n")
    inspection = _single_response_inspection()
    inspection[0]["run"]["folder"] = str(history)
    original_replace = os.replace

    def interrupt_after_install(source, target):
        original_replace(source, target)
        if Path(target) == destination:
            raise KeyboardInterrupt("interrupt after atomic install")

    monkeypatch.setattr(os, "replace", interrupt_after_install)
    with pytest.raises(KeyboardInterrupt, match="after atomic install"):
        freeze_analysis_evidence(inspection, destination)
    assert destination.is_dir()

    # Activity replay must restore the installed generation without consulting
    # mutable historical locations again.
    ledger.write_text("history changed after the completed activity side effect\n")
    monkeypatch.setattr(os, "replace", original_replace)
    replayed = freeze_analysis_evidence(inspection, destination)
    verify_analysis_evidence(replayed)
    assert replayed.managed_root == str(destination)
    frozen_ledger = next(Path(replayed.root).glob("runs/*/journal/ledger.jsonl"))
    assert frozen_ledger.read_text() == "original immutable history\n"
