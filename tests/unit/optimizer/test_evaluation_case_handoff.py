from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from botpipe.core.surface_identity import derive_workflow_surface_manifest
from botpipe_optimizer import inspect_selected_workflow
from botpipe_optimizer.candidate_surfaces import derive_surface_manifest
from botpipe_optimizer.evidence import (
    capture_evidence_snapshot,
    write_evidence_snapshot,
)
from botpipe_optimizer.recommendations import (
    finalize_candidate_review_payload,
    finalize_candidate_set_payload,
    publish_recommendation,
    validate_candidate_review,
    validate_candidate_set,
)
from labs.workflows.workflow_to_eval_suite.params import Params
from labs.workflows.workflow_to_eval_suite.workflow import WorkflowToEvalSuite

REPO_ROOT = Path(__file__).resolve().parents[3]


def _accepted_optimization_receipt(tmp_path: Path, *, kind: str) -> tuple[Path, str]:
    output_dir = tmp_path / "optimizer-output"
    output_dir.mkdir()
    inspection = inspect_selected_workflow(
        SimpleNamespace(root=REPO_ROOT), "ralph_loop"
    )
    authoritative = derive_workflow_surface_manifest(REPO_ROOT, inspection.capability)
    baseline_root = output_dir / "baseline-surface"
    source_map = {}
    for entry in authoritative["files"]:
        relative_path = entry["relative_path"]
        source_path = Path(entry["surface_path"])
        target_path = baseline_root / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        source_map[relative_path] = source_path
    baseline = derive_surface_manifest(
        baseline_root,
        expected_root=baseline_root,
        boundary=authoritative["boundary"],
        surface_kind="workflow",
        authoritative_sources=source_map,
    )
    assert baseline["surface_id"] == authoritative["surface_id"]
    baseline_path = output_dir / "baseline_surface_manifest.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    run_dir = (
        tmp_path
        / "capture"
        / ".botpipe"
        / "tasks"
        / "task-run1"
        / "wf_ralph_loop"
        / "runs"
        / "run1"
    )
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "task_id": "task-run1",
                "run_id": "run1",
                "workflow_name": "ralph_loop",
                "status": "failed",
                "provenance": {
                    "workflow_identity": "workflow-identity",
                    "workflow_surface_manifest_id": baseline["surface_id"],
                    "topology_id": "topology-1",
                },
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "trace.jsonl").write_text(
        json.dumps(
            {
                "event_type": "step_finished",
                "sequence": 1,
                "step_execution_id": "execution-1",
                "step_name": "review",
                "step_kind": "pair",
                "scope": "root",
                "item_id": "item-1",
                "final_route": "failed",
                "outcome": {"tag": "failed"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    evidence = capture_evidence_snapshot(
        tmp_path / "capture",
        "ralph_loop",
        [run_dir],
        tmp_path / "evidence-raw",
        explicit_run_refs=True,
        current_workflow_identity="workflow-identity",
        current_surface_manifest_id=baseline["surface_id"],
        current_topology_id="topology-1",
    )
    evidence_path = write_evidence_snapshot(
        evidence, output_dir / "workflow_optimization_evidence.json"
    )
    observation_id = evidence.observations[0].observation_id

    if kind == "evaluation_case":
        payload = {
            "suite_target": "ralph_loop regression suite",
            "case_descriptions": ["Exercise the observed review failure."],
        }
    else:
        payload = {
            "prompt_paths": ["labs/workflows/ralph_loop/prompts/producer.md"],
            "replacement_strategy": "Clarify the completion requirement.",
        }
    candidate_set = finalize_candidate_set_payload(
        {
            "schema": "botpipe.workflow_optimization.candidate_set/v2",
            "selected_workflow": "ralph_loop",
            "evidence_snapshot_id": evidence.snapshot_id,
            "baseline_surface_manifest_id": baseline["surface_id"],
            "candidates": [
                {
                    "kind": kind,
                    "title": "Cover the observed failure",
                    "targets": ["ralph_loop"],
                    "cited_observation_ids": [observation_id],
                    "proposed_change": "Add a regression case for the observed failure.",
                    "expected_effect": "Expose the failure before workflow publication.",
                    "risks": ["The case may be too narrow."],
                    "validation_plan": {
                        "description": "Run the frozen evaluation suite.",
                        "checks": ["compile", "evaluate"],
                        "falsification": "The new case does not reproduce the failure.",
                    },
                    "payload": payload,
                }
            ],
            "next_action": "implement_candidate",
            "no_candidate_reason": None,
        }
    )
    validate_candidate_set(
        candidate_set,
        evidence_snapshot=evidence,
        max_candidates=1,
        allowed_kinds={kind},
        expected_selected_workflow="ralph_loop",
    )
    review = finalize_candidate_review_payload(
        {
            "schema": "botpipe.workflow_optimization.candidate_review/v2",
            "candidate_set_id": candidate_set.candidate_set_id,
            "evidence_snapshot_id": candidate_set.evidence_snapshot_id,
            "baseline_surface_manifest_id": candidate_set.baseline_surface_manifest_id,
            "accepted": True,
            "reviewed_candidate_ids": [candidate_set.candidates[0].candidate_id],
            "findings": [],
        }
    )
    validate_candidate_review(review, candidate_set=candidate_set)
    review_path = output_dir / "workflow_optimization_candidate_review.json"
    review_path.write_text(
        json.dumps(review.model_dump(mode="json", by_alias=True)), encoding="utf-8"
    )
    receipt = publish_recommendation(
        output_dir=output_dir,
        evidence_snapshot_path=evidence_path,
        baseline_surface_manifest_path=baseline_path,
        evidence_snapshot=evidence,
        candidate_set=candidate_set,
        review=review,
        review_source_path=review_path,
        max_output_bytes=1_000_000,
        expected_baseline_root=baseline_root,
        expected_baseline_boundary=baseline["boundary"],
    )
    return (
        output_dir / "optimization_publication_receipt.json",
        receipt.reviewed_candidate_ids[0],
    )


def _bootstrap_context(tmp_path: Path, receipt_path: Path, candidate_id: str):
    run_folder = tmp_path / "authoring-run"
    workflow_folder = tmp_path / "authoring-workflow"
    run_folder.mkdir()
    workflow_folder.mkdir()
    (run_folder / "request.md").write_text(
        "Create an evaluation suite.\n", encoding="utf-8"
    )
    return SimpleNamespace(
        root=REPO_ROOT,
        params=Params(
            selected_workflow="ralph_loop",
            task_title="Author regression coverage",
            optimization_receipt_path=str(receipt_path),
            candidate_id=candidate_id,
        ),
        state=WorkflowToEvalSuite.State(),
        run_folder=run_folder,
        workflow_folder=workflow_folder,
        workflow_name="workflow_to_eval_suite",
        task_id="author-evals",
        run_id="run-1",
        open_session=lambda _ref, scope=None: SimpleNamespace(scope=scope),
    )


def test_t20_evaluation_case_receipt_loads_through_authoring_bootstrap(tmp_path: Path):
    receipt_path, candidate_id = _accepted_optimization_receipt(
        tmp_path, kind="evaluation_case"
    )
    ctx = _bootstrap_context(tmp_path, receipt_path, candidate_id)

    assert WorkflowToEvalSuite.bootstrap.fn(ctx) == "inputs_prepared"

    invocation = json.loads(
        (ctx.workflow_folder / "invocation_contract.json").read_text()
    )
    selection = invocation["optimization_selection"]
    assert selection["candidate"]["candidate_id"] == candidate_id
    assert selection["candidate"]["kind"] == "evaluation_case"
    assert selection["claim_scope"] == "development_cases"


def test_t20_eval_authoring_rejects_non_evaluation_candidate(tmp_path: Path):
    receipt_path, candidate_id = _accepted_optimization_receipt(
        tmp_path, kind="producer_prompt"
    )
    ctx = _bootstrap_context(tmp_path, receipt_path, candidate_id)

    with pytest.raises(ValueError, match="wrong kind"):
        WorkflowToEvalSuite.bootstrap.fn(ctx)


def test_t20_eval_authoring_rejects_current_baseline_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    receipt_path, candidate_id = _accepted_optimization_receipt(
        tmp_path, kind="evaluation_case"
    )
    ctx = _bootstrap_context(tmp_path, receipt_path, candidate_id)
    monkeypatch.setattr(
        "labs.workflows.workflow_to_eval_suite.workflow.derive_workflow_surface_manifest",
        lambda *_args, **_kwargs: {"surface_id": "sha256:" + "0" * 64},
    )

    with pytest.raises(ValueError, match="baseline/evidence changed"):
        WorkflowToEvalSuite.bootstrap.fn(ctx)


@pytest.mark.parametrize(
    "values",
    [
        {"optimization_receipt_path": "receipt.json"},
        {"candidate_id": "candidate_" + "0" * 64},
    ],
)
def test_t20_eval_authoring_requires_receipt_and_candidate_pair(values):
    with pytest.raises(ValidationError, match="must be supplied together"):
        Params(selected_workflow="ralph_loop", task_title="Author coverage", **values)
