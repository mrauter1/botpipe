from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from autoloop_v3.stdlib.optimization import (
    list_selected_workflow_runs,
    load_run_observability_bundle,
    normalize_trace_corpus,
    parse_run_ref,
    validate_observability_bundle,
    validate_selected_workflow_source_unchanged,
    write_optimization_refinement_evidence,
    write_selected_workflow_source_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_parse_run_ref_accepts_task_slash_run() -> None:
    assert parse_run_ref("task-123/run-456") == ("task-123", "run-456")


@pytest.mark.parametrize("raw", ("", "task-only", "task/run/extra", "/run", "task/"))
def test_parse_run_ref_rejects_invalid_shapes(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_run_ref(raw)


def test_list_selected_workflow_runs_filters_by_workflow_and_status(tmp_path: Path) -> None:
    _write_minimal_run_metadata(tmp_path, "task-1", "release_candidate_to_go_no_go", "run-failed", "failed")
    _write_minimal_run_metadata(tmp_path, "task-2", "release_candidate_to_go_no_go", "run-success", "success")
    _write_minimal_run_metadata(tmp_path, "task-3", "incident_to_hardening_program", "run-other", "failed")

    runs = list_selected_workflow_runs(
        tmp_path,
        "release_candidate_to_go_no_go",
        run_refs=[],
        run_statuses=["failed", "paused"],
        history_limit=10,
    )

    assert runs == [
        tmp_path
        / ".autoloop"
        / "tasks"
        / "task-1"
        / "wf_release_candidate_to_go_no_go"
        / "runs"
        / "run-failed"
    ]


def test_explicit_run_refs_select_exact_runs(tmp_path: Path) -> None:
    run_one = _write_minimal_run_metadata(
        tmp_path,
        "task-1",
        "release_candidate_to_go_no_go",
        "run-one",
        "failed",
    )
    _write_minimal_run_metadata(tmp_path, "task-2", "release_candidate_to_go_no_go", "run-two", "failed")

    runs = list_selected_workflow_runs(
        tmp_path,
        "release_candidate_to_go_no_go",
        run_refs=["task-1/run-one"],
        run_statuses=["failed"],
        history_limit=10,
    )

    assert runs == [run_one]


def test_load_run_observability_bundle_requires_run_json_trace_static_graph_git_tracking_and_raw(tmp_path: Path) -> None:
    run_dir = _write_observable_run(tmp_path, "task-1", "release_candidate_to_go_no_go", "run-good")

    bundle = load_run_observability_bundle(run_dir)

    assert validate_observability_bundle(bundle) == (True, None)
    assert bundle.run_json is not None
    assert bundle.trace_records is not None
    assert bundle.git_tracking_records is not None
    assert bundle.static_step_graph is not None


def test_missing_plan1_files_exclude_run_with_reason(tmp_path: Path) -> None:
    run_dir = _write_minimal_run_metadata(
        tmp_path,
        "task-1",
        "release_candidate_to_go_no_go",
        "run-old",
        "failed",
    )
    (run_dir / "git_tracking.jsonl").write_text("", encoding="utf-8")
    (run_dir / "static_step_graph.json").write_text("{}", encoding="utf-8")
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)

    bundle = load_run_observability_bundle(run_dir)

    assert validate_observability_bundle(bundle) == (False, "missing_trace_jsonl")


def test_normalize_trace_corpus_preserves_raw_refs_and_git_commits(tmp_path: Path) -> None:
    run_dir = _write_observable_run(tmp_path, "task-1", "release_candidate_to_go_no_go", "run-good")

    corpus = normalize_trace_corpus(
        selected_workflow="release_candidate_to_go_no_go",
        run_dirs=[run_dir],
        route_tags=["needs_rework", "failed"],
    )

    assert corpus["candidate_run_count"] == 1
    assert corpus["eligible_run_count"] == 1
    assert corpus["excluded_run_count"] == 0
    assert corpus["step_observation_count"] == 1
    assert corpus["runs"][0]["commit_before_run"] == "commit-before-run"
    assert corpus["runs"][0]["commit_after_run"] == "commit-after-run"
    assert corpus["step_observations"][0]["raw_output_refs"] == {
        "producer": "raw/000003_assessment_producer.txt",
        "verifier": "raw/000003_assessment_verifier.txt",
    }
    assert corpus["step_observations"][0]["commit_before_step"] == "commit-before-step"
    assert corpus["step_observations"][0]["commit_after_step"] == "commit-after-step"


def test_write_selected_workflow_source_manifest_records_hashes(tmp_path: Path) -> None:
    _install_selected_workflow(tmp_path)
    workflow_folder = tmp_path / ".autoloop" / "tasks" / "task-1" / "wf_optimizer"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    ctx = SimpleNamespace(root=tmp_path, workflow_folder=workflow_folder)

    manifest_path = write_selected_workflow_source_manifest(
        ctx=ctx,
        selected_workflow="release_candidate_to_go_no_go",
        relative_path="selected_workflow_source_manifest.json",
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["selected_workflow"] == "release_candidate_to_go_no_go"
    first_entry = payload["files"][0]
    absolute_path = tmp_path / first_entry["path"]
    content = absolute_path.read_bytes()
    assert first_entry["sha256"] == hashlib.sha256(content).hexdigest()
    assert first_entry["bytes"] == len(content)


def test_validate_selected_workflow_source_unchanged_detects_mutation(tmp_path: Path) -> None:
    _install_selected_workflow(tmp_path)
    workflow_folder = tmp_path / ".autoloop" / "tasks" / "task-1" / "wf_optimizer"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    ctx = SimpleNamespace(root=tmp_path, workflow_folder=workflow_folder)

    manifest_path = write_selected_workflow_source_manifest(
        ctx=ctx,
        selected_workflow="release_candidate_to_go_no_go",
        relative_path="selected_workflow_source_manifest.json",
    )
    target_file = tmp_path / "workflows" / "release_candidate_to_go_no_go" / "workflow.toml"
    target_file.write_text(target_file.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")

    ok, details = validate_selected_workflow_source_unchanged(
        ctx=ctx,
        selected_workflow="release_candidate_to_go_no_go",
        manifest_path=manifest_path,
    )

    assert ok is False
    assert "changed during optimization publication" in details


def test_write_optimization_refinement_evidence_uses_expected_schema(tmp_path: Path) -> None:
    workflow_folder = tmp_path / ".autoloop" / "tasks" / "task-1" / "wf_optimizer"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    ctx = SimpleNamespace(root=tmp_path, workflow_folder=workflow_folder)

    path = write_optimization_refinement_evidence(
        ctx=ctx,
        selected_workflow="release_candidate_to_go_no_go",
        evidence_entries=[
            {
                "kind": "workflow_optimization_scorecard",
                "path": "workflow_optimization_scorecard.json",
                "summary": "No-op packet because no eligible traces were present.",
                "handling": "Candidate-only boundary.",
            }
        ],
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == "autoloop.workflow_refinement_evidence/v1"
    assert payload["target_workflow_id"] == "release_candidate_to_go_no_go"
    assert payload["evidence_entries"][0]["kind"] == "workflow_optimization_scorecard"


def _write_minimal_run_metadata(root: Path, task_id: str, workflow_name: str, run_id: str, status: str) -> Path:
    run_dir = root / ".autoloop" / "tasks" / task_id / f"wf_{workflow_name}" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": "2026-04-24T06:00:00+00:00",
        "package_folder": str(Path("workflows") / workflow_name),
        "run_folder": str(Path(".autoloop") / "tasks" / task_id / f"wf_{workflow_name}" / "runs" / run_id),
        "run_id": run_id,
        "status": status,
        "task_folder": str(Path(".autoloop") / "tasks" / task_id),
        "task_id": task_id,
        "updated_at": "2026-04-24T06:05:00+00:00",
        "workflow_folder": str(Path(".autoloop") / "tasks" / task_id / f"wf_{workflow_name}"),
        "workflow_name": workflow_name,
        "workflow_params": {},
    }
    (run_dir / "run.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return run_dir


def _write_observable_run(root: Path, task_id: str, workflow_name: str, run_id: str) -> Path:
    run_dir = _write_minimal_run_metadata(root, task_id, workflow_name, run_id, "failed")
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    run_payload["terminal"] = "FAIL"
    run_payload["git_tracking"] = {
        "commit_before_run": "commit-before-run",
        "commit_after_run": "commit-after-run",
    }
    (run_dir / "run.json").write_text(json.dumps(run_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    producer_text = "producer output\n"
    verifier_text = "verifier output\n"
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "000003_assessment_producer.txt").write_text(producer_text, encoding="utf-8")
    (raw_dir / "000003_assessment_verifier.txt").write_text(verifier_text, encoding="utf-8")
    (run_dir / "trace.jsonl").write_text(
        json.dumps(
            {
                "schema": "autoloop.runtime_trace/v1",
                "event_type": "step_finished",
                "sequence": 3,
                "step_name": "assessment",
                "step_kind": "pair",
                "event": {"tag": "needs_rework"},
                "outcome": {"tag": "needs_rework"},
                "git": {"commit_before_step": "commit-before-step"},
                "provider_usage": {
                    "producer": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120, "source": "provider"},
                    "verifier": {"input_tokens": 80, "output_tokens": 10, "total_tokens": 90, "source": "provider"},
                },
                "raw_output_refs": {
                    "producer": {
                        "path": "raw/000003_assessment_producer.txt",
                        "sha256": hashlib.sha256(producer_text.encode("utf-8")).hexdigest(),
                        "bytes": len(producer_text.encode("utf-8")),
                    },
                    "verifier": {
                        "path": "raw/000003_assessment_verifier.txt",
                        "sha256": hashlib.sha256(verifier_text.encode("utf-8")).hexdigest(),
                        "bytes": len(verifier_text.encode("utf-8")),
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "git_tracking.jsonl").write_text(
        json.dumps(
            {
                "schema": "autoloop.git_tracking/v1",
                "event_type": "step_committed",
                "sequence": 3,
                "step_name": "assessment",
                "commit_before_step": "commit-before-step",
                "commit_after_step": "commit-after-step",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "static_step_graph.json").write_text(
        json.dumps(
            {
                "schema": "autoloop.workflow_static_step_graph/v1",
                "workflow_name": workflow_name,
                "steps": [{"name": "assessment", "kind": "pair"}],
                "transitions": {"steps": {"assessment": {"needs_rework": "assessment"}}, "global": {}},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_dir


def _install_selected_workflow(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    shutil.copytree(
        REPO_ROOT / "workflows" / "release_candidate_to_go_no_go",
        workflows_root / "release_candidate_to_go_no_go",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(
        REPO_ROOT / "docs",
        root / "docs",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
