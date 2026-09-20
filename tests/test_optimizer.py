from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from pydantic import BaseModel

from botpipe import Botpipe, Policy, Session, current_run, workflow
from botpipe.providers import FakeProvider, ProviderResponse
from botpipe_optimizer import (
    capture_evidence_snapshot,
    capture_source_manifest,
    evaluate_candidate_workspace,
    load_run_observation,
    optimize_observations,
    prepare_candidate_workspace,
    validate_authoritative_sources_unchanged,
    validate_eval_case_manifest,
    validate_optimization_candidate,
    validate_workflow_parameters,
)
from botpipe_optimizer.recommendations import (
    finalize_candidate_review_payload,
    finalize_candidate_set_payload,
    load_optimization_candidate,
    publish_recommendation,
    validate_candidate_review,
    validate_candidate_set,
)
from labs.workflows.workflow_run_traces_to_optimization_candidates import (
    Params as OptimizerParams,
)
from labs.workflows.workflow_run_traces_to_optimization_candidates import (
    WorkflowRunTracesToOptimizationCandidates,
)


class EvalInputs(BaseModel):
    topic: str
    limit: int = 2


@workflow(name="alias_observed")
def alias_observed_workflow():
    return current_run().operation(
        "activity",
        {"value": "observed"},
        lambda: "observed",
        retry_safe=True,
        name="observed activity",
    )


def inspected_run(*, run_id="run-1", status="failed", operations=()):
    return {
        "run": {"run_id": run_id, "workflow_name": "example", "status": status},
        "operations": list(operations),
        "events": [],
        "artifacts": {},
    }


def operation(operation_id, *, name="draft", status="completed", attempts=1, tokens=0):
    return {
        "id": operation_id,
        "run_id": "run-1",
        "scope": "root",
        "ordinal": 1,
        "kind": "provider",
        "name": name,
        "status": status,
        "attempts": attempts,
        "started_at": "2026-01-01T00:00:00+00:00",
        "finished_at": "2026-01-01T00:00:01+00:00",
        "usage": {"total_tokens": tokens},
        "inputs": {},
        "result": {"value": {"outcome": "accepted"}, "artifacts": {}},
    }


def provenanced_run(
    *,
    operations,
    surface="surface-current",
    orchestration="orchestration-current",
    run_id="run-1",
):
    provenance = {
        "verified": True,
        "workflow_identity": "workflow-example",
        "surface_id": surface,
        "orchestration_id": orchestration,
    }
    return {
        "run": {
            "run_id": run_id,
            "task_id": "task",
            "workflow": "example",
            "status": "failed",
            "provenance_start": provenance,
            "provenance_end": provenance,
        },
        "operations": operations,
        "events": [],
        "artifacts": {},
    }


def test_optimizer_ranks_only_observed_operations_and_preserves_evidence():
    run = load_run_observation(
        inspected_run(
            operations=[
                operation("op-1", status="failed", attempts=2, tokens=20),
                operation("op-2", name="package", tokens=100),
            ]
        )
    )
    report = optimize_observations("example", [run])

    assert report.observation_absent is False
    assert {metric.name for metric in report.metrics} == {"draft", "package"}
    assert report.candidates[0].target_name == "draft"
    assert report.candidates[0].category == "reliability"
    assert report.candidates[0].evidence_operation_ids == ("op-1",)


def test_legacy_report_labels_counts_and_generic_duration_without_cost_or_latency_claims():
    usage_run = load_run_observation(
        inspected_run(operations=[operation("usage", name="usage step", tokens=20)])
    )
    usage_candidate = optimize_observations("example", [usage_run]).candidates[0]
    assert usage_candidate.category == "token_usage"
    assert "cost" not in usage_candidate.rationale.lower()

    duration_operation = operation("duration", name="duration step", tokens=0)
    duration_operation["usage"] = {}
    duration_run = load_run_observation(inspected_run(operations=[duration_operation]))
    duration_candidate = optimize_observations("example", [duration_run]).candidates[0]
    assert duration_candidate.category == "recorded_duration"
    assert "latency" not in duration_candidate.rationale.lower()
    assert "recorded operation duration" in duration_candidate.rationale.lower()


def test_source_manifest_marks_unvisited_dynamic_paths_without_scoring_them():
    def example(flag: bool):
        if flag:
            worker.run("do work", name="conditional")  # noqa: F821
        return "done"

    example.name = "example"
    manifest = capture_source_manifest(example)
    report = optimize_observations("example", [], source_manifest=manifest)

    assert manifest.topology_dynamic is True
    assert manifest.branch_lines
    assert any(site.name == "conditional" for site in manifest.sites)
    assert report.observation_absent is True
    assert report.candidates == ()
    assert report.unseen_declared_paths


def test_candidate_validation_rejects_fabricated_evidence():
    run = load_run_observation(inspected_run(operations=[operation("op-real")]))
    report = optimize_observations("example", [run])
    fabricated = replace(report.candidates[0], evidence_operation_ids=("op-invented",))

    with pytest.raises(ValueError, match="unknown operations"):
        validate_optimization_candidate(fabricated, observed_operations=run.operations)


def test_inspection_rejects_duplicate_operation_ids():
    with pytest.raises(ValueError, match="duplicate operation ids"):
        load_run_observation(
            inspected_run(operations=[operation("same"), operation("same")])
        )


def test_optimizer_consumes_real_journaled_typed_outcome_and_usage(tmp_path):
    class Decision(BaseModel):
        outcome: str
        summary: str

    @workflow(name="observed")
    def observed():
        session = Session()
        return session.run(
            "decide",
            returns=Decision,
            name="decide",
            policy=Policy(model="profile-model", effort="high"),
        ).value

    provider = FakeProvider(
        [
            ProviderResponse(
                '{"outcome":"accepted","summary":"evidenced"}',
                usage={"input_tokens": 7, "output_tokens": 5, "total_tokens": 12},
            )
        ]
    )
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(observed, task_id="observed", run_id="run-real")
        inspection = client.inspect(result.run_id)

    observation = load_run_observation(inspection)
    decision = next(item for item in observation.operations if item.name == "decide")
    report = optimize_observations("observed", [observation])

    assert decision.outcome == "accepted"
    assert len(decision.dispatches) == 1
    assert decision.dispatches[0].usage_availability == "known_total"
    assert decision.dispatches[0].provider == "fake"
    assert decision.dispatches[0].model == "profile-model"
    assert decision.dispatches[0].effort == "high"
    assert decision.dispatches[0].effort_present is True
    assert decision.dispatches[0].policy_fingerprint
    assert decision.usage["total_tokens"] == 12
    assert (
        next(
            metric for metric in report.metrics if metric.name == "decide"
        ).total_tokens
        == 12
    )


def test_candidate_workspace_executes_in_isolation_and_preserves_authoritative_source(
    tmp_path,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "answer.py"
    source.write_text("VALUE = 1\n")
    workspace = prepare_candidate_workspace(repo, ["answer.py"], tmp_path / "surface")
    (workspace.candidate_root / "answer.py").write_text("VALUE = 2\n")

    report = evaluate_candidate_workspace(
        workspace,
        ["python", "-c", "import answer; assert answer.VALUE == 2"],
        timeout=5,
    )

    assert report.ok
    assert report.manifest.changed_paths == ("answer.py",)
    assert source.read_text() == "VALUE = 1\n"
    validate_authoritative_sources_unchanged(workspace)


def test_candidate_workspace_rejects_path_escape_extra_files_and_source_drift(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "source.py").write_text("x = 1\n")
    with pytest.raises(ValueError, match="repo-relative"):
        prepare_candidate_workspace(repo, ["../outside.py"], tmp_path / "bad")
    workspace = prepare_candidate_workspace(repo, ["source.py"], tmp_path / "surface")
    (workspace.candidate_root / "extra.py").write_text("x = 2\n")
    with pytest.raises(ValueError, match="outside the allowlist"):
        evaluate_candidate_workspace(workspace, ["python", "-c", "pass"])
    (workspace.candidate_root / "extra.py").unlink()
    (repo / "source.py").write_text("x = 3\n")
    with pytest.raises(ValueError, match="authoritative source changed"):
        validate_authoritative_sources_unchanged(workspace)


def test_candidate_package_allows_additions_inside_only_and_reports_diff(tmp_path):
    repo = tmp_path / "repo"
    package = repo / "package"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "workflow.py").write_text("VALUE = 1\n")
    workspace = prepare_candidate_workspace(repo, ["package"], tmp_path / "surface")
    (workspace.candidate_root / "package" / "block.py").write_text("BLOCK = True\n")

    report = evaluate_candidate_workspace(
        workspace, ["python", "-c", "import package.block"]
    )

    assert report.ok
    assert report.manifest.added_paths == ("package/block.py",)
    (package / "unexpected.py").write_text("AUTHORITATIVE = True\n")
    with pytest.raises(ValueError, match="source tree changed"):
        validate_authoritative_sources_unchanged(workspace)
    (package / "unexpected.py").unlink()
    (workspace.candidate_root / "outside.py").write_text("NO = True\n")
    with pytest.raises(ValueError, match="outside the allowlist"):
        evaluate_candidate_workspace(workspace, ["python", "-c", "pass"])


def test_callable_parameter_and_eval_manifest_validation():
    @workflow(name="evaluated")
    def evaluated(params: EvalInputs):
        return params.topic

    assert validate_workflow_parameters(evaluated, {"topic": "durability"}) == {
        "topic": "durability",
        "limit": 2,
    }
    manifest = validate_eval_case_manifest(
        evaluated,
        {
            "cases": [
                {
                    "case_id": "base",
                    "case_kind": "benchmark",
                    "prompt": "base",
                    "workflow_parameters": {"topic": "base"},
                    "expected_artifacts": ["report"],
                },
                {
                    "case_id": "edge",
                    "case_kind": "edge",
                    "prompt": "edge",
                    "workflow_parameters": {"topic": "edge", "limit": 1},
                    "expected_artifacts": ["report"],
                },
                {
                    "case_id": "attack",
                    "case_kind": "adversarial",
                    "prompt": "attack",
                    "workflow_parameters": {"topic": "attack"},
                    "expected_artifacts": ["report"],
                },
            ]
        },
        known_artifacts=["report"],
    )
    assert manifest.case_ids == ["base", "edge", "attack"]
    with pytest.raises(ValueError, match="invalid workflow parameters"):
        validate_workflow_parameters(evaluated, {})


def test_callable_parameter_validation_binds_non_model_signature():
    @workflow(name="plain")
    def plain(request: str, limit: int = 2):
        return request * limit

    assert validate_workflow_parameters(plain, {"request": "x", "limit": 3}) == {
        "request": "x",
        "limit": 3,
    }
    with pytest.raises(ValueError, match="invocation arguments"):
        validate_workflow_parameters(plain, {"limit": 3})


def test_v2_objective_eligibility_keeps_missing_usage_distinct_from_zero():
    def example():
        return None

    manifest = capture_source_manifest(example)
    known_zero = operation("zero", tokens=0)
    unknown = operation("unknown", name="unknown")
    unknown["usage"] = {}
    positive = operation("positive", name="positive", tokens=9)
    snapshot = capture_evidence_snapshot(
        "example",
        [provenanced_run(operations=[known_zero, unknown, positive])],
        source_manifest=manifest,
        objective="token_usage",
        current_workflow_identity="workflow-example",
        current_surface_id="surface-current",
        current_orchestration_id="orchestration-current",
    )

    metrics = {metric.step_id: metric for metric in snapshot.step_metrics}
    assert metrics["draft"].complete_usage is True
    assert metrics["draft"].known_total_tokens == 0
    assert metrics["unknown"].complete_usage is False
    assert metrics["unknown"].known_total_tokens is None
    assert [item.step_id for item in snapshot.shortlist] == ["positive"]
    assert metrics["unknown"].metric_id in snapshot.measure_first


def test_v2_reliability_groups_surfaces_and_ranks_distinct_affected_runs():
    def example():
        return None

    manifest = capture_source_manifest(example)
    current_failure = operation("current-failure", status="failed")
    historical_failure = operation("old-failure", status="failed")
    snapshot = capture_evidence_snapshot(
        "example",
        [
            provenanced_run(operations=[current_failure], run_id="current"),
            provenanced_run(
                operations=[historical_failure], surface="surface-old", run_id="old"
            ),
        ],
        source_manifest=manifest,
        objective="reliability",
        current_workflow_identity="workflow-example",
        current_surface_id="surface-current",
        current_orchestration_id="orchestration-current",
    )

    assert len(snapshot.groups) == 2
    assert snapshot.recommendation_basis == "current_verified"
    assert len(snapshot.step_metrics) == 1
    assert snapshot.shortlist[0].direct_failure_run_count == 1
    cited = {
        observation.operation_id
        for observation in snapshot.observations
        if observation.group_id == snapshot.selected_group_id
    }
    assert cited == {"current-failure"}


def test_v2_same_surface_with_different_orchestration_stays_separate():
    def example():
        return None

    manifest = capture_source_manifest(example)
    snapshot = capture_evidence_snapshot(
        "example",
        [
            provenanced_run(
                operations=[operation("current", status="failed")],
                orchestration="orchestration-current",
                run_id="current",
            ),
            provenanced_run(
                operations=[operation("historical", status="failed")],
                orchestration="orchestration-old",
                run_id="old",
            ),
        ],
        source_manifest=manifest,
        objective="reliability",
        current_workflow_identity="workflow-example",
        current_surface_id="surface-current",
        current_orchestration_id="orchestration-current",
    )

    assert len(snapshot.groups) == 2
    selected = next(item for item in snapshot.groups if item.current_match)
    assert selected.orchestration_id == "orchestration-current"
    assert snapshot.selected_group_id == selected.group_id


def test_v2_evidence_and_candidate_bytes_are_bounded_and_identities_are_verified(
    tmp_path,
):
    def example():
        return None

    manifest = capture_source_manifest(example)
    snapshot = capture_evidence_snapshot(
        "example",
        [provenanced_run(operations=[operation("failed", status="failed")])],
        source_manifest=manifest,
        objective="reliability",
        current_workflow_identity="workflow-example",
        current_surface_id="surface-current",
        current_orchestration_id="orchestration-current",
        max_evidence_bytes=100_000,
    )
    observation_id = snapshot.shortlist and next(
        item.observation_id
        for item in snapshot.observations
        if item.group_id == snapshot.selected_group_id
    )
    candidate_set = finalize_candidate_set_payload(
        {
            "schema": "botpipe.workflow_optimization.candidate_set/v2",
            "selected_workflow": "example",
            "evidence_snapshot_id": snapshot.snapshot_id,
            "baseline_surface_manifest_id": snapshot.baseline_surface_manifest_id,
            "candidates": [
                {
                    "kind": "workflow",
                    "title": "Handle the observed failure",
                    "targets": ["workflow.py"],
                    "cited_observation_ids": [observation_id],
                    "proposed_change": "Tighten failure handling.",
                    "expected_effect": "The observed failure is rejected earlier.",
                    "risks": ["May reject a valid edge case."],
                    "validation_plan": {
                        "description": "Replay the failure.",
                        "checks": ["Run the regression case."],
                        "falsification": "The failure still reaches the provider.",
                    },
                    "payload": {
                        "target_paths": ["workflow.py"],
                        "workflow_change": "Add an explicit guard.",
                    },
                }
            ],
            "next_action": "implement_candidate",
            "no_candidate_reason": None,
        }
    )
    validate_candidate_set(
        candidate_set,
        evidence_snapshot=snapshot,
        max_candidates=1,
        allowed_kinds={"workflow"},
        expected_selected_workflow="example",
        max_output_bytes=100_000,
    )
    with pytest.raises(ValueError, match="max_output_bytes"):
        validate_candidate_set(
            candidate_set,
            evidence_snapshot=snapshot,
            max_candidates=1,
            allowed_kinds={"workflow"},
            expected_selected_workflow="example",
            max_output_bytes=10,
        )
    review = finalize_candidate_review_payload(
        {
            "schema": "botpipe.workflow_optimization.candidate_review/v2",
            "candidate_set_id": candidate_set.candidate_set_id,
            "evidence_snapshot_id": snapshot.snapshot_id,
            "baseline_surface_manifest_id": snapshot.baseline_surface_manifest_id,
            "accepted": True,
            "reviewed_candidate_ids": [candidate_set.candidates[0].candidate_id],
            "findings": [],
        }
    )
    validate_candidate_review(
        review, candidate_set=candidate_set, max_output_bytes=100_000
    )

    output = tmp_path / "published"
    receipt = publish_recommendation(
        output_dir=output,
        evidence_snapshot=snapshot,
        candidate_set=candidate_set,
        review=review,
        baseline_manifest=asdict(manifest),
        max_output_bytes=100_000,
    )
    selection = load_optimization_candidate(
        optimization_receipt_path=output / "optimization_publication_receipt.json",
        candidate_id=candidate_set.candidates[0].candidate_id,
        expected_selected_workflow="example",
        allowed_kinds=("workflow",),
        max_output_bytes=100_000,
        max_evidence_bytes=100_000,
    )
    assert selection.receipt == receipt
    assert selection.candidate == candidate_set.candidates[0]
    Path(receipt.candidate_set_path).write_text("{}")
    with pytest.raises(ValueError, match="changed after publication"):
        load_optimization_candidate(
            optimization_receipt_path=output / "optimization_publication_receipt.json",
            candidate_id=candidate_set.candidates[0].candidate_id,
            expected_selected_workflow="example",
            allowed_kinds=("workflow",),
            max_output_bytes=100_000,
            max_evidence_bytes=100_000,
        )


def test_v2_no_eligible_evidence_uses_zero_provider_turns(tmp_path):
    provider = FakeProvider([])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(
            WorkflowRunTracesToOptimizationCandidates,
            OptimizerParams(
                selected_workflow="release_candidate_to_go_no_go",
                task_title="Review release workflow",
            ),
            request="Recommend the next useful action.",
            task_id="optimizer",
            run_id="empty",
        )
        inspection = client.inspect(result.run_id)

    assert result.ok
    assert result.value.candidate_set.next_action == "collect_evidence"
    assert result.value.candidate_set.candidates == []
    assert result.value.review is None
    assert result.value.provider_budget["used_turns"] == 0
    assert not [item for item in inspection["operations"] if item["kind"] == "provider"]


def test_v2_file_reference_uses_canonical_name_and_exact_task_run_refs(tmp_path):
    provider = FakeProvider([])
    reference = "test_optimizer:alias_observed_workflow"
    with Botpipe(tmp_path, provider=provider) as client:
        observed = client.run(
            alias_observed_workflow, task_id="evidence", run_id="observed"
        )
        assert observed.ok
        result = client.run(
            WorkflowRunTracesToOptimizationCandidates,
            OptimizerParams(selected_workflow=reference, task_title="Alias selection"),
            task_id="optimizer",
            run_id="alias",
        )
        mismatch = client.run(
            WorkflowRunTracesToOptimizationCandidates,
            OptimizerParams(
                selected_workflow=reference,
                task_title="Exact selection",
                run_refs=["wrong-task/observed"],
            ),
            task_id="optimizer",
            run_id="mismatch",
        )

    assert result.ok, result.error
    assert result.value.evidence_snapshot.selected_workflow == "alias_observed"
    assert result.value.evidence_snapshot.selection.admitted_run_count == 1
    assert result.value.provider_budget["used_turns"] == 0
    assert not mismatch.ok
    assert "run reference task does not match journal" in mismatch.error


def test_v2_eligible_evidence_uses_one_producer_and_independent_verifier(tmp_path):
    from botpipe_optimizer.recommendations import (
        finalize_candidate_review_payload,
        finalize_candidate_set_payload,
    )

    @workflow(name="release_candidate_to_go_no_go")
    def failing_release():
        return current_run().operation(
            "activity",
            {"case": "observed-failure"},
            lambda: (_ for _ in ()).throw(RuntimeError("observed failure")),
            retry_safe=True,
            name="explode",
        )

    def prompt_input(request):
        body = request.prompt.rsplit("\n\nInput:\n", 1)[1]
        return json.JSONDecoder().raw_decode(body)[0]

    def propose(request):
        value = prompt_input(request)
        evidence = value["evidence_snapshot"]
        observation_id = next(
            item["observation_id"]
            for item in evidence["observations"]
            if item["group_id"] == evidence["selected_group_id"]
        )
        result = finalize_candidate_set_payload(
            {
                "schema": "botpipe.workflow_optimization.candidate_set/v2",
                "selected_workflow": evidence["selected_workflow"],
                "evidence_snapshot_id": evidence["snapshot_id"],
                "baseline_surface_manifest_id": evidence[
                    "baseline_surface_manifest_id"
                ],
                "candidates": [
                    {
                        "kind": "workflow",
                        "title": "Guard the observed failure",
                        "targets": ["workflow.py"],
                        "cited_observation_ids": [observation_id],
                        "proposed_change": "Add a typed failure guard.",
                        "expected_effect": "The observed invalid state is rejected earlier.",
                        "risks": ["The guard may reject a valid boundary case."],
                        "validation_plan": {
                            "description": "Replay the observed failure.",
                            "checks": ["Run the regression case."],
                            "falsification": "The invalid state still reaches execution.",
                        },
                        "payload": {
                            "target_paths": ["workflow.py"],
                            "workflow_change": "Validate the state before execution.",
                        },
                    }
                ],
                "next_action": "implement_candidate",
                "no_candidate_reason": None,
            }
        )
        return result.model_dump(mode="json", by_alias=True)

    def review(request):
        candidate_set = prompt_input(request)["candidate_set"]
        result = finalize_candidate_review_payload(
            {
                "schema": "botpipe.workflow_optimization.candidate_review/v2",
                "candidate_set_id": candidate_set["candidate_set_id"],
                "evidence_snapshot_id": candidate_set["evidence_snapshot_id"],
                "baseline_surface_manifest_id": candidate_set[
                    "baseline_surface_manifest_id"
                ],
                "accepted": True,
                "reviewed_candidate_ids": [
                    item["candidate_id"] for item in candidate_set["candidates"]
                ],
                "findings": [],
            }
        )
        return result.model_dump(mode="json", by_alias=True)

    class TimedFakeProvider(FakeProvider):
        supports_timeout = True

    provider = TimedFakeProvider([propose, review])
    with Botpipe(tmp_path, provider=provider) as client:
        failed = client.run(
            failing_release, task_id="release", run_id="failed-observation"
        )
        assert not failed.ok
        result = client.run(
            WorkflowRunTracesToOptimizationCandidates,
            OptimizerParams(
                selected_workflow="release_candidate_to_go_no_go",
                task_title="Review release workflow",
                include_adversarial_generation=False,
                include_token_optimization=False,
            ),
            request="Recommend the next useful action.",
            task_id="optimizer",
            run_id="recommend",
        )
        inspection = client.inspect(result.run_id)

    assert result.ok, result.error
    assert result.value.review is not None and result.value.review.accepted
    assert result.value.candidate_set.candidates[0].cited_observation_ids
    assert result.value.provider_budget["used_turns"] == 2
    providers = [
        item for item in inspection["operations"] if item["kind"] == "provider"
    ]
    assert [item["name"] for item in providers] == [
        "propose evidence-bound candidates",
        "independently review candidate set",
    ]
