from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

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
