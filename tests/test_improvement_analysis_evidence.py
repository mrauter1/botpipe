from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from botpipe import ArtifactHandle, codec
from labs.workflows.improve_workflow.analysis_evidence import (
    AnalysisIntegrityError,
    freeze_analysis_evidence,
    validate_exact_quote,
    verify_analysis_evidence,
)


class _ArtifactModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    handles: list[ArtifactHandle]


@dataclass
class _ArtifactEnvelope:
    model: _ArtifactModel


def _artifact(path: Path, name: str) -> ArtifactHandle:
    data = path.read_bytes()
    return ArtifactHandle(
        name=name,
        path=path,
        source_path=path,
        kind="text",
        digest=sha256(data).hexdigest(),
    )


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
            "result": codec.encode(
                _ArtifactEnvelope(_ArtifactModel(handles=[_artifact(first, "draft")]))
            ),
        },
        {
            "id": "run:root:1",
            "kind": "provider",
            "inputs": {"value": {"prompt": "revise the draft"}},
            "response": {"text": "second draft response"},
            "result": codec.encode({"nested": (_artifact(second, "draft"),)}),
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


def test_analysis_bundle_finds_artifact_in_encoded_enum_value(tmp_path):
    source = tmp_path / "enum-artifact.txt"
    source.write_text("artifact stored as an enum value")
    artifact_enum = Enum(
        "_ArtifactEnum",
        {"RESULT": _artifact(source, "enum-artifact")},
        module=__name__,
    )
    inspection = (
        {
            "run": {"run_id": "run", "status": "completed"},
            "operations": [
                {
                    "id": "run:root:0",
                    "inputs": codec.encode({}),
                    "response": None,
                    "result": codec.encode(artifact_enum.RESULT),
                }
            ],
        },
    )

    frozen = freeze_analysis_evidence(inspection, tmp_path / "bundle")

    artifacts = list((Path(frozen.root) / "artifacts").iterdir())
    assert len(artifacts) == 1
    assert artifacts[0].read_text() == "artifact stored as an enum value"


def test_analysis_bundle_marks_bounded_and_unavailable_content(tmp_path):
    missing = tmp_path / "missing.txt"
    missing_handle = ArtifactHandle(
        name="missing",
        path=missing,
        source_path=missing,
        kind="text",
        digest="a" * 64,
    )
    operation = {
        "id": "run:root:0",
        "kind": "provider",
        "inputs": {"value": {"prompt": "x" * 5000}},
        "response": {"text": "y" * 5000},
        "result": codec.encode({"artifact": missing_handle}),
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


@pytest.mark.parametrize("escaped_tag", [False, True])
def test_analysis_bundle_does_not_treat_business_records_as_artifacts(
    tmp_path, escaped_tag
):
    source = tmp_path / "ordinary.txt"
    source.write_text("ordinary business data")
    record: dict[str, Any] = {
        "name": "not-an-artifact",
        "path": str(source),
        "source_path": str(source),
        "kind": "text",
        "digest": sha256(source.read_bytes()).hexdigest(),
        "schema": None,
    }
    value: Any = {"$botpipe": "artifact", "value": record} if escaped_tag else record
    inspection = (
        {
            "run": {"run_id": "run", "status": "completed"},
            "operations": [
                {
                    "id": "run:root:0",
                    "inputs": codec.encode({}),
                    "response": None,
                    "result": codec.encode({"business_record": value}),
                }
            ],
        },
    )

    frozen = freeze_analysis_evidence(inspection, tmp_path / "bundle")

    artifact_root = Path(frozen.root) / "artifacts"
    assert not artifact_root.exists()
    assert "recorded_artifact_unavailable" not in {
        item["reason"]
        for item in json.loads((Path(frozen.root) / "index.json").read_text())[
            "omissions"
        ]
    }


def test_analysis_bundle_does_not_walk_raw_contract_or_artifact_schema(tmp_path):
    counterfeit_source = tmp_path / "counterfeit.txt"
    counterfeit_source.write_text("must not be captured")
    counterfeit = {
        "$botpipe": "artifact",
        "value": {
            "name": "counterfeit",
            "path": str(counterfeit_source),
            "source_path": str(counterfeit_source),
            "kind": "text",
            "digest": sha256(counterfeit_source.read_bytes()).hexdigest(),
            "schema": None,
        },
    }
    encoded_model = codec.encode(_ArtifactEnvelope(_ArtifactModel(handles=[])))
    encoded_model["contract"]["counterfeit_default"] = counterfeit

    genuine_source = tmp_path / "genuine.txt"
    genuine_source.write_text("genuine artifact")
    genuine = ArtifactHandle(
        name="genuine",
        path=genuine_source,
        source_path=genuine_source,
        kind="text",
        digest=sha256(genuine_source.read_bytes()).hexdigest(),
        schema={"default": counterfeit},
    )
    inspection = (
        {
            "run": {"run_id": "run", "status": "completed"},
            "operations": [
                {
                    "id": "run:root:0",
                    "inputs": codec.encode({}),
                    "response": None,
                    "result": encoded_model,
                },
                {
                    "id": "run:root:1",
                    "inputs": codec.encode({}),
                    "response": None,
                    "result": codec.encode(genuine),
                },
            ],
        },
    )

    frozen = freeze_analysis_evidence(inspection, tmp_path / "bundle")

    artifacts = list((Path(frozen.root) / "artifacts").iterdir())
    assert len(artifacts) == 1
    assert artifacts[0].name.endswith("-genuine")
    assert artifacts[0].read_text() == "genuine artifact"


def test_malformed_canonical_artifact_tag_is_an_integrity_error(tmp_path):
    malformed = {
        "$botpipe": "artifact",
        "value": {
            "name": "incomplete",
            "path": str(tmp_path / "incomplete.txt"),
            "source_path": str(tmp_path / "incomplete.txt"),
            "kind": "text",
            "digest": "a" * 64,
        },
    }
    inspection = (
        {
            "run": {"run_id": "run", "status": "completed"},
            "operations": [
                {
                    "id": "run:root:0",
                    "inputs": codec.encode({}),
                    "response": None,
                    "result": malformed,
                }
            ],
        },
    )

    with pytest.raises(AnalysisIntegrityError, match="artifact tag is malformed"):
        freeze_analysis_evidence(inspection, tmp_path / "bundle")


def test_artifact_same_length_rewrite_with_restored_mtime_is_detected(
    tmp_path, monkeypatch
):
    source = tmp_path / "mutable.txt"
    source.write_bytes(b"version-one")
    before = source.stat()
    handle = _artifact(source, "mutable")
    inspection = (
        {
            "run": {"run_id": "run", "status": "completed"},
            "operations": [
                {
                    "id": "run:root:0",
                    "inputs": codec.encode({}),
                    "response": None,
                    "result": codec.encode(handle),
                }
            ],
        },
    )
    original_fdopen = os.fdopen

    class MutatingReader:
        def __init__(self, descriptor, *args, **kwargs):
            self.stream = original_fdopen(descriptor, *args, **kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.stream.close()

        def read(self, size):
            data = self.stream.read(size)
            source.write_bytes(b"version-two")
            os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
            original_mode = before.st_mode & 0o777
            os.chmod(source, original_mode ^ 0o100)
            os.chmod(source, original_mode)
            assert source.stat().st_ctime_ns != before.st_ctime_ns
            return data

    monkeypatch.setattr(os, "fdopen", MutatingReader)

    with pytest.raises(AnalysisIntegrityError, match="changed while being captured"):
        freeze_analysis_evidence(inspection, tmp_path / "bundle")


def test_dangling_artifact_symlink_is_an_integrity_error(tmp_path):
    link = tmp_path / "dangling.txt"
    link.symlink_to(tmp_path / "missing.txt")
    handle = ArtifactHandle(
        name="dangling",
        path=link,
        source_path=link,
        kind="text",
        digest="a" * 64,
    )
    inspection = (
        {
            "run": {"run_id": "run", "status": "completed"},
            "operations": [
                {
                    "id": "run:root:0",
                    "inputs": codec.encode({}),
                    "response": None,
                    "result": codec.encode(handle),
                }
            ],
        },
    )

    with pytest.raises(AnalysisIntegrityError, match="recorded artifact.*symlink"):
        freeze_analysis_evidence(inspection, tmp_path / "bundle")


def test_oversized_artifact_is_omitted_without_reading_content(tmp_path, monkeypatch):
    source = tmp_path / "oversized.bin"
    source.write_bytes(b"x" * 4096)
    digest = sha256(source.read_bytes()).hexdigest()
    handle = ArtifactHandle(
        name="oversized",
        path=source,
        source_path=source,
        kind="raw",
        digest=digest,
    )
    inspection = (
        {
            "run": {"run_id": "run", "status": "completed"},
            "operations": [
                {
                    "id": "run:root:0",
                    "inputs": codec.encode({}),
                    "response": None,
                    "result": codec.encode(handle),
                }
            ],
        },
    )

    monkeypatch.setattr(
        os,
        "fdopen",
        lambda *_args, **_kwargs: pytest.fail("oversized artifact was read"),
    )
    frozen = freeze_analysis_evidence(inspection, tmp_path / "bundle", max_bytes=2500)

    omissions = json.loads((Path(frozen.root) / "index.json").read_text())["omissions"]
    name_sha256 = sha256(b"oversized").hexdigest()
    assert {
        "path": f"artifacts/{digest}-{name_sha256}-oversized",
        "reason": "max_evidence_bytes",
        "bytes": 4096,
        "sha256": digest,
    } in omissions


def test_colliding_artifact_name_slugs_have_distinct_bounded_paths(tmp_path):
    source = tmp_path / "shared.bin"
    source.write_bytes(b"x" * 3000)
    digest = sha256(source.read_bytes()).hexdigest()
    operations = []
    for index, name in enumerate(("a b", "a-b")):
        handle = ArtifactHandle(
            name=name,
            path=source,
            source_path=source,
            kind="raw",
            digest=digest,
        )
        operations.append(
            {
                "id": f"run:root:{index}",
                "inputs": codec.encode({}),
                "response": None,
                "result": codec.encode(handle),
            }
        )
    inspection = (
        {
            "run": {"run_id": "run", "status": "completed"},
            "operations": operations,
        },
    )

    bounded = freeze_analysis_evidence(
        inspection, tmp_path / "bounded-bundle", max_bytes=6000
    )
    bounded_root = Path(bounded.root)
    omissions = json.loads((bounded_root / "index.json").read_text())["omissions"]
    present = set(bounded.hashes)
    omitted = {item["path"] for item in omissions}
    assert not present & omitted
    assert len(list((bounded_root / "artifacts").iterdir())) == 1

    complete = freeze_analysis_evidence(
        inspection, tmp_path / "complete-bundle", max_bytes=12_000
    )
    complete_root = Path(complete.root)
    artifacts = list((complete_root / "artifacts").iterdir())
    assert len(artifacts) == 2
    assert len({path.name for path in artifacts}) == 2
    assert {path.read_bytes() for path in artifacts} == {source.read_bytes()}


def test_oversized_journal_file_is_omitted_without_reading_content(
    tmp_path, monkeypatch
):
    history = tmp_path / "history"
    history.mkdir()
    (history / "ledger.jsonl").write_bytes(b"x" * 4096)
    inspection = (
        {
            "run": {
                "run_id": "run",
                "status": "completed",
                "folder": str(history),
            },
            "operations": [],
        },
    )

    monkeypatch.setattr(
        os,
        "fdopen",
        lambda *_args, **_kwargs: pytest.fail("oversized journal was read"),
    )
    frozen = freeze_analysis_evidence(inspection, tmp_path / "bundle", max_bytes=2500)

    omissions = json.loads((Path(frozen.root) / "index.json").read_text())["omissions"]
    assert any(
        item["path"].endswith("/journal/ledger.jsonl")
        and item["reason"] == "max_evidence_bytes"
        and item["bytes"] == 4096
        and item["sha256"] is None
        for item in omissions
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
