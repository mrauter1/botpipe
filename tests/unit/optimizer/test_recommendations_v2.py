from __future__ import annotations
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from botpipe_optimizer.recommendations import (
    build_empty_candidate_set,
    finalize_candidate_review_payload,
    finalize_candidate_set_payload,
    publish_recommendation,
    validate_candidate_review,
    validate_candidate_set,
)
from botpipe_optimizer.candidate_surfaces import derive_surface_manifest
from botpipe_optimizer.evidence import (
    capture_evidence_snapshot,
    write_evidence_snapshot,
)
from labs.workflows.workflow_run_traces_to_optimization_candidates.params import Params
from labs.workflows.workflow_run_traces_to_optimization_candidates.workflow import (
    _invocation_id,
)


def _evidence():
    return SimpleNamespace(
        snapshot_id="evidence-1",
        baseline_surface_manifest_id="surface-1",
        shortlist=[],
        issues=[],
        recommendation_basis="current_verified",
        citable_observation_ids=lambda: frozenset({"obs-1"}),
    )


def _draft(kind="producer_prompt", citation="obs-1"):
    payload = {
        "prompt_paths": ["wf/prompt.md"],
        "replacement_strategy": "Tighten evidence rules.",
    }
    return {
        "schema": "botpipe.workflow_optimization.candidate_set/v2",
        "selected_workflow": "wf",
        "evidence_snapshot_id": "evidence-1",
        "baseline_surface_manifest_id": "surface-1",
        "candidates": [
            {
                "kind": kind,
                "title": "Tighten prompt",
                "targets": ["wf/prompt.md"],
                "cited_observation_ids": [citation],
                "proposed_change": "Require source references.",
                "expected_effect": "Reduce observed rejection recurrence.",
                "risks": ["May reject terse valid output."],
                "validation_plan": {
                    "description": "Replay frozen cases.",
                    "checks": ["compile", "evaluate"],
                    "falsification": "No reliability improvement.",
                },
                "payload": payload,
            }
        ],
        "next_action": "implement_candidate",
        "no_candidate_reason": None,
    }


def test_t13_rejects_forged_citation_duplicate_ids_and_disabled_kind():
    forged = finalize_candidate_set_payload(_draft(citation="invented"))
    with pytest.raises(ValueError, match="unknown"):
        validate_candidate_set(
            forged,
            evidence_snapshot=_evidence(),
            max_candidates=3,
            allowed_kinds={"producer_prompt"},
            expected_selected_workflow="wf",
        )
    raw = _draft()
    raw["candidates"].append(dict(raw["candidates"][0]))
    duplicate = finalize_candidate_set_payload(raw)
    with pytest.raises(ValueError, match="unique"):
        validate_candidate_set(
            duplicate,
            evidence_snapshot=_evidence(),
            max_candidates=3,
            allowed_kinds={"producer_prompt"},
            expected_selected_workflow="wf",
        )
    with pytest.raises(ValueError, match="disabled"):
        validate_candidate_set(
            finalize_candidate_set_payload(_draft()),
            evidence_snapshot=_evidence(),
            max_candidates=3,
            allowed_kinds={"workflow"},
            expected_selected_workflow="wf",
        )


@pytest.mark.parametrize(
    ("location", "field"),
    [
        ("candidate_set", "observed_failure_count"),
        ("candidate_set", "metrics"),
        ("candidate", "known_total_tokens"),
        ("candidate", "distinct_run_count"),
    ],
)
def test_t13_model_authored_metrics_and_counts_are_rejected(location, field):
    draft = _draft()
    target = draft if location == "candidate_set" else draft["candidates"][0]
    target[field] = 999

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        finalize_candidate_set_payload(draft)


def test_t14_empty_candidate_set_is_valid_and_requires_no_review():
    cs = build_empty_candidate_set(
        selected_workflow="wf",
        evidence_snapshot_id="evidence-1",
        baseline_surface_manifest_id="surface-1",
        next_action="collect_evidence",
        reason="No eligible failures.",
    )
    validate_candidate_set(
        cs,
        evidence_snapshot=_evidence(),
        max_candidates=3,
        allowed_kinds=set(),
        expected_selected_workflow="wf",
    )
    assert cs.candidates == []


def test_t15_total_cap_and_review_anchor_are_hard_failures():
    raw = _draft()
    second = json.loads(json.dumps(raw["candidates"][0]))
    second["title"] = "Second"
    raw["candidates"].append(second)
    cs = finalize_candidate_set_payload(raw)
    with pytest.raises(ValueError, match="max_candidates"):
        validate_candidate_set(
            cs,
            evidence_snapshot=_evidence(),
            max_candidates=1,
            allowed_kinds={"producer_prompt"},
            expected_selected_workflow="wf",
        )
    review = finalize_candidate_review_payload(
        {
            "schema": "botpipe.workflow_optimization.candidate_review/v2",
            "candidate_set_id": cs.candidate_set_id,
            "evidence_snapshot_id": cs.evidence_snapshot_id,
            "baseline_surface_manifest_id": cs.baseline_surface_manifest_id,
            "accepted": True,
            "reviewed_candidate_ids": list(
                reversed([c.candidate_id for c in cs.candidates])
            ),
            "findings": [],
        }
    )
    with pytest.raises(ValueError, match="exactly"):
        validate_candidate_review(review, candidate_set=cs)


def test_t15_oversized_baseline_is_rejected_before_any_file_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from labs.workflows.workflow_run_traces_to_optimization_candidates import (
        workflow as optimizer_workflow,
    )

    source = tmp_path / "source.py"
    source.write_bytes(b"oversized")
    output = tmp_path / "optimizer-output"
    monkeypatch.setattr(optimizer_workflow, "MAX_BYTES", len(b"oversized") - 1)

    with pytest.raises(ValueError, match="baseline exceeds byte limit before copy"):
        optimizer_workflow._copy_baseline(
            output,
            {"package_root_relative_path": "workflow"},
            [{"relative_path": "workflow/source.py", "source_path": str(source)}],
        )

    snapshot_parent = output / "baseline_snapshots"
    assert snapshot_parent.is_dir()
    assert not any(path.is_file() for path in snapshot_parent.rglob("*"))


def test_failed_publication_replaces_stale_success_with_incomplete(tmp_path: Path):
    (tmp_path / "optimization_publication_receipt.json").write_text(
        '{"status":"accepted"}'
    )
    cs = finalize_candidate_set_payload(_draft())
    with pytest.raises(ValueError, match="accepted independent review"):
        publish_recommendation(
            output_dir=tmp_path,
            evidence_snapshot_path=tmp_path / "e.json",
            baseline_surface_manifest_path=tmp_path / "b.json",
            evidence_snapshot=_evidence(),
            candidate_set=cs,
            review=None,
            max_output_bytes=1024,
        )
    assert (
        json.loads((tmp_path / "optimization_publication_receipt.json").read_text())[
            "status"
        ]
        == "incomplete"
    )


def test_deadline_crossed_immediately_before_commit_cannot_publish_success(
    tmp_path: Path,
):
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    (baseline / "workflow.py").write_text("# frozen\n")
    manifest = derive_surface_manifest(
        baseline,
        expected_root=baseline,
        boundary={"package_root_relative_path": "wf"},
        surface_kind="workflow",
    )
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(manifest))
    evidence = capture_evidence_snapshot(
        tmp_path,
        "wf",
        [],
        tmp_path / "snapshot",
        current_surface_manifest_id=manifest["surface_id"],
    )
    evidence_path = write_evidence_snapshot(evidence, tmp_path / "evidence.json")
    cs = build_empty_candidate_set(
        selected_workflow="wf",
        evidence_snapshot_id=evidence.snapshot_id,
        baseline_surface_manifest_id=manifest["surface_id"],
        next_action="collect_evidence",
        reason="Missing evidence.",
    )

    def expired():
        raise ValueError("deadline exhausted")

    with pytest.raises(ValueError, match="deadline"):
        publish_recommendation(
            output_dir=tmp_path,
            evidence_snapshot_path=evidence_path,
            baseline_surface_manifest_path=baseline_path,
            evidence_snapshot=evidence,
            candidate_set=cs,
            review=None,
            max_output_bytes=10000,
            expected_baseline_root=baseline,
            expected_baseline_boundary={"package_root_relative_path": "wf"},
            before_commit=expired,
        )
    assert (
        json.loads((tmp_path / "optimization_publication_receipt.json").read_text())[
            "status"
        ]
        == "incomplete"
    )


def test_candidate_and_review_share_one_output_cap(tmp_path: Path):
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    (baseline / "workflow.py").write_text("# frozen\n")
    boundary = {"package_root_relative_path": "wf"}
    manifest = derive_surface_manifest(
        baseline, expected_root=baseline, boundary=boundary, surface_kind="workflow"
    )
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(manifest))
    evidence = capture_evidence_snapshot(
        tmp_path,
        "wf",
        [],
        tmp_path / "snapshot",
        current_surface_manifest_id=manifest["surface_id"],
    )
    evidence_path = write_evidence_snapshot(evidence, tmp_path / "evidence.json")
    cs = build_empty_candidate_set(
        selected_workflow="wf",
        evidence_snapshot_id=evidence.snapshot_id,
        baseline_surface_manifest_id=manifest["surface_id"],
        next_action="collect_evidence",
        reason="Missing evidence.",
    )
    review = finalize_candidate_review_payload(
        {
            "schema": "botpipe.workflow_optimization.candidate_review/v2",
            "candidate_set_id": cs.candidate_set_id,
            "evidence_snapshot_id": cs.evidence_snapshot_id,
            "baseline_surface_manifest_id": cs.baseline_surface_manifest_id,
            "accepted": True,
            "reviewed_candidate_ids": [],
            "findings": [],
        }
    )
    candidate_path = tmp_path / "candidate-source.json"
    candidate_path.write_text(json.dumps(cs.model_dump(mode="json", by_alias=True)))
    review_path = tmp_path / "review-source.json"
    review_path.write_text(json.dumps(review.model_dump(mode="json", by_alias=True)))
    combined = candidate_path.stat().st_size + review_path.stat().st_size
    with pytest.raises(ValueError, match="max_output_bytes"):
        publish_recommendation(
            output_dir=tmp_path,
            evidence_snapshot_path=evidence_path,
            baseline_surface_manifest_path=baseline_path,
            evidence_snapshot=evidence,
            candidate_set=cs,
            review=review,
            max_output_bytes=combined - 1,
            candidate_set_source_path=candidate_path,
            review_source_path=review_path,
            expected_baseline_root=baseline,
            expected_baseline_boundary=boundary,
        )
    assert (
        json.loads((tmp_path / "optimization_publication_receipt.json").read_text())[
            "status"
        ]
        == "incomplete"
    )


def test_tampered_persisted_evidence_cannot_publish(tmp_path: Path):
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    (baseline / "workflow.py").write_text("# frozen\n")
    boundary = {"package_root_relative_path": "wf"}
    manifest = derive_surface_manifest(
        baseline, expected_root=baseline, boundary=boundary, surface_kind="workflow"
    )
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(manifest))
    evidence = capture_evidence_snapshot(
        tmp_path,
        "wf",
        [],
        tmp_path / "snapshot",
        current_surface_manifest_id=manifest["surface_id"],
    )
    evidence_path = write_evidence_snapshot(evidence, tmp_path / "evidence.json")
    cs = build_empty_candidate_set(
        selected_workflow="wf",
        evidence_snapshot_id=evidence.snapshot_id,
        baseline_surface_manifest_id=manifest["surface_id"],
        next_action="collect_evidence",
        reason="Missing evidence.",
    )
    payload = json.loads(evidence_path.read_text())
    payload["objective"] = "tampered"
    evidence_path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        publish_recommendation(
            output_dir=tmp_path,
            evidence_snapshot_path=evidence_path,
            baseline_surface_manifest_path=baseline_path,
            evidence_snapshot=evidence,
            candidate_set=cs,
            review=None,
            max_output_bytes=10000,
            expected_baseline_root=baseline,
            expected_baseline_boundary=boundary,
        )
    assert (
        json.loads((tmp_path / "optimization_publication_receipt.json").read_text())[
            "status"
        ]
        == "incomplete"
    )


def test_t20_parameter_aliases_warn_and_conflicts_fail():
    with pytest.warns(FutureWarning, match="max_candidates_per_pass"):
        params = Params(
            selected_workflow="wf", task_title="Review", max_candidates_per_pass=2
        )
    assert params.max_candidates == 2
    with pytest.raises(ValueError, match="conflicts"):
        Params(
            selected_workflow="wf",
            task_title="Review",
            max_candidates=3,
            max_candidates_per_pass=2,
        )
    with pytest.warns(FutureWarning, match="optimization_depth"):
        standard = Params(
            selected_workflow="wf", task_title="Review", optimization_depth="standard"
        )
    assert (standard.max_provider_turns, standard.max_analysis_seconds) == (12, 3600)


def test_resume_invocation_identity_changes_with_effective_params(tmp_path: Path):
    request = tmp_path / "request.md"
    request.write_text("diagnose")
    original = Params(selected_workflow="wf", task_title="Review", max_candidates=3)
    changed = Params(selected_workflow="wf", task_title="Review", max_candidates=2)
    assert _invocation_id(original, request, "wf") != _invocation_id(
        changed, request, "wf"
    )
