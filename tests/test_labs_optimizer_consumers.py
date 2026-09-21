from __future__ import annotations

import json
import sys
from hashlib import sha256

import pytest
from pydantic import ValidationError

from botpipe import Botpipe
from botpipe.discovery import resolve_workflow
from botpipe.providers import FakeProvider
from botpipe.surface_identity import derive_workflow_surface_manifest
from botpipe_optimizer.evidence import capture_evidence_snapshot
from botpipe_optimizer.optimization import (
    OperationObservation,
    RunObservation,
    capture_source_manifest,
)
from botpipe_optimizer.recommendations import (
    finalize_candidate_review_payload,
    finalize_candidate_set_payload,
    publish_recommendation,
)
from labs.workflows.optimizer_integration import (
    evaluation_suite_identity,
    load_legacy_evaluation_inputs,
    load_optimizer_candidate_handoff,
    staged_workflow_reference,
    validate_materialized_handoff,
)
from labs.workflows.workflow_and_eval_to_refined_workflow_package import (
    Params as RefinementParams,
)
from labs.workflows.workflow_and_eval_to_refined_workflow_package import (
    workflow_callable as refinement_workflow,
)
from labs.workflows.workflow_package_to_composable_building_blocks import (
    Params as DecompositionParams,
)
from labs.workflows.workflow_to_eval_suite import Params as EvalSuiteParams
from labs.workflows.workflow_to_eval_suite import (
    workflow_callable as eval_suite_workflow,
)


def _refinement(**changes):
    values = {
        "selected_workflow": "release_candidate_to_go_no_go",
        "task_title": "Refine release review",
        "evaluation_summary_path": "summary.json",
        "evaluation_findings_path": "findings.md",
    }
    values.update(changes)
    return RefinementParams(**values)


def test_refinement_requires_one_complete_input_form():
    assert _refinement().evaluation_summary_path == "summary.json"
    with pytest.raises(ValidationError, match="mutually exclusive"):
        _refinement(
            optimization_receipt_path="receipt.json",
            candidate_id="candidate_" + "1" * 64,
        )
    with pytest.raises(ValidationError, match="requires evaluation_summary_path"):
        RefinementParams(
            selected_workflow="release_candidate_to_go_no_go",
            task_title="Refine",
            evaluation_findings_path="findings.md",
        )
    candidate = "candidate_" + "2" * 64
    params = RefinementParams(
        selected_workflow="release_candidate_to_go_no_go",
        task_title="Refine",
        optimization_receipt_path="receipt.json",
        candidate_id=candidate,
    )
    assert params.candidate_id == candidate


def test_commands_are_argv_and_eval_selection_is_complete():
    params = DecompositionParams(
        selected_workflow="release_candidate_to_go_no_go",
        task_title="Decompose",
        target_test_command="python -c 'raise SystemExit(0)'",
    )
    assert params.target_test_argv == ["python", "-c", "raise SystemExit(0)"]
    with pytest.raises(ValidationError, match="mutually exclusive"):
        DecompositionParams(
            selected_workflow="release_candidate_to_go_no_go",
            task_title="Decompose",
            target_test_command="pytest -q",
            target_test_argv=["pytest", "-q"],
        )
    with pytest.raises(ValidationError, match="supplied together"):
        EvalSuiteParams(
            selected_workflow="release_candidate_to_go_no_go",
            task_title="Build evals",
            candidate_id="candidate_" + "3" * 64,
        )


def test_legacy_evaluation_is_bound_to_selected_workflow(tmp_path):
    (tmp_path / "summary.json").write_text(
        json.dumps({"selected_workflow_name": "release_candidate_to_go_no_go"}),
        encoding="utf-8",
    )
    (tmp_path / "findings.md").write_text("# Findings\n", encoding="utf-8")
    result = load_legacy_evaluation_inputs.__wrapped__(
        workspace=str(tmp_path),
        evaluation_summary_path="summary.json",
        evaluation_findings_path="findings.md",
        expected_selected_workflow="release_candidate_to_go_no_go",
    )
    assert result["findings"] == "# Findings\n"

    (tmp_path / "summary.json").write_text(
        json.dumps({"selected_workflow_name": "another_workflow"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must match"):
        load_legacy_evaluation_inputs.__wrapped__(
            workspace=str(tmp_path),
            evaluation_summary_path="summary.json",
            evaluation_findings_path="findings.md",
            expected_selected_workflow="release_candidate_to_go_no_go",
        )


def test_handoff_and_eval_suite_identities_are_exact():
    validate_materialized_handoff(
        {"baseline_files": {"workflow.py": "abc"}}, {"workflow.py": "abc"}
    )
    with pytest.raises(ValueError, match="stale"):
        validate_materialized_handoff(
            {"baseline_files": {"workflow.py": "abc"}},
            {"workflow.py": "def"},
        )

    manifest = {"selected_workflow": "release_candidate_to_go_no_go", "cases": []}
    first = evaluation_suite_identity(manifest, source_candidate_id="candidate-a")
    assert first == evaluation_suite_identity(
        manifest, source_candidate_id="candidate-a"
    )
    assert first != evaluation_suite_identity(
        manifest, source_candidate_id="candidate-b"
    )
    assert (
        staged_workflow_reference(
            "/original/workflow.py:ReleaseFlow",
            relative_source="pkg/workflow.py",
            function="ReleaseFlow",
        )
        == "pkg/workflow.py:ReleaseFlow"
    )
    assert (
        staged_workflow_reference(
            "release-go-no-go",
            relative_source="pkg/workflow.py",
            function="ReleaseFlow",
        )
        == "release-go-no-go"
    )


def _publish_optimizer_candidate(root, *, kind: str):
    workflow_name = "release_candidate_to_go_no_go"
    workflow = resolve_workflow(workflow_name, ".")
    surface = derive_workflow_surface_manifest(root, workflow)
    source = capture_source_manifest(workflow)
    operation = OperationObservation(
        operation_id="provider-review",
        run_id="observed-run",
        scope="root",
        ordinal=1,
        kind="provider",
        name="review",
        status="completed",
        outcome="needs_rework",
        attempts=1,
        duration_ms=10.0,
        usage={"total_tokens": 10},
        inputs={},
        result={},
        error=None,
    )
    run = RunObservation(
        run_id="observed-run",
        run_ref="observed/observed-run",
        task_id="observed",
        workflow_name=workflow_name,
        workflow_version="2",
        workflow_identity=workflow_name,
        orchestration_id="orchestration-observed",
        surface_id=surface["surface_id"],
        provenance_state="known",
        status="completed",
        operations=(operation,),
    )
    evidence = capture_evidence_snapshot(
        workflow_name,
        [run],
        source_manifest=source,
        current_surface_id=surface["surface_id"],
        baseline_surface_manifest_id=surface["surface_id"],
    )
    target = "labs/workflows/release_candidate_to_go_no_go/workflow.py"
    payload = (
        {
            "suite_target": workflow_name,
            "case_descriptions": ["Exercise a blocked release decision."],
        }
        if kind == "evaluation_case"
        else {"target_paths": [target], "workflow_change": "Improve review handling."}
    )
    candidate_set = finalize_candidate_set_payload(
        {
            "schema": "botpipe.workflow_optimization.candidate_set/v2",
            "selected_workflow": workflow_name,
            "evidence_snapshot_id": evidence.snapshot_id,
            "baseline_surface_manifest_id": surface["surface_id"],
            "candidates": [
                {
                    "candidate_id": "candidate_" + "0" * 64,
                    "kind": kind,
                    "title": "Improve release review",
                    "targets": [target],
                    "cited_observation_ids": [evidence.observations[0].observation_id],
                    "proposed_change": "Improve the observed review path.",
                    "expected_effect": "Fewer review reworks.",
                    "risks": ["The change may regress another decision path."],
                    "validation_plan": {
                        "description": "Validate the candidate in isolation.",
                        "checks": ["compile and exercise the selected workflow"],
                        "falsification": "Any selected-workflow regression.",
                    },
                    "payload": payload,
                }
            ],
            "next_action": "implement_candidate",
            "no_candidate_reason": None,
        }
    )
    candidate = candidate_set.candidates[0]
    review = finalize_candidate_review_payload(
        {
            "schema": "botpipe.workflow_optimization.candidate_review/v2",
            "review_id": "candidate_review_" + "0" * 64,
            "candidate_set_id": candidate_set.candidate_set_id,
            "evidence_snapshot_id": evidence.snapshot_id,
            "baseline_surface_manifest_id": surface["surface_id"],
            "accepted": True,
            "reviewed_candidate_ids": [candidate.candidate_id],
            "findings": [],
        }
    )
    publish_recommendation(
        output_dir=root,
        evidence_snapshot=evidence,
        candidate_set=candidate_set,
        review=review,
        baseline_manifest=surface,
        max_output_bytes=10 * 1024 * 1024,
    )
    return candidate.candidate_id


@pytest.mark.parametrize(
    ("kind", "allowed"),
    [("workflow", ("workflow",)), ("evaluation_case", ("evaluation_case",))],
)
def test_strict_optimizer_receipt_routes_candidate_kind(tmp_path, kind, allowed):
    candidate_id = _publish_optimizer_candidate(tmp_path, kind=kind)
    result = load_optimizer_candidate_handoff.__wrapped__(
        workspace=str(tmp_path),
        optimization_receipt_path="optimization_publication_receipt.json",
        candidate_id=candidate_id,
        expected_selected_workflow="release_candidate_to_go_no_go",
        allowed_kinds=allowed,
        selected_workflow_reference="release-go-no-go",
    )
    assert result["candidate_id"] == candidate_id
    assert result["candidate_kind"] == kind
    assert result["improvement"] == "not_evaluated"

    rejected = ("evaluation_case",) if kind == "workflow" else ("workflow",)
    with pytest.raises(ValueError, match="disallowed kind"):
        load_optimizer_candidate_handoff.__wrapped__(
            workspace=str(tmp_path),
            optimization_receipt_path="optimization_publication_receipt.json",
            candidate_id=candidate_id,
            expected_selected_workflow="release_candidate_to_go_no_go",
            allowed_kinds=rejected,
            selected_workflow_reference="release-go-no-go",
        )


@pytest.mark.parametrize("kind", ["workflow", "evaluation_case"])
def test_optimizer_candidate_runs_through_native_consumer(tmp_path, kind):
    from tests.test_labs import _successful_provider

    candidate_id = _publish_optimizer_candidate(tmp_path, kind=kind)
    common = {
        "selected_workflow": "release-go-no-go",
        "task_title": "Consume optimizer recommendation",
        "optimization_receipt_path": "optimization_publication_receipt.json",
        "candidate_id": candidate_id,
    }
    if kind == "workflow":
        workflow = refinement_workflow
        params = RefinementParams(
            **common,
            target_test_argv=["python", "-c", "pass"],
        )
    else:
        workflow = eval_suite_workflow
        params = EvalSuiteParams(**common)
    result = Botpipe(tmp_path, provider=FakeProvider([_successful_provider] * 24)).run(
        workflow, params, request="Use the accepted optimizer candidate"
    )
    assert result.ok, result.error


def _write_evaluation_spec(root):
    calls = root / "evaluator-calls.txt"
    evaluator = root / "evaluator.py"
    evaluator.write_text(
        "\n".join(
            [
                "import json, os",
                "from pathlib import Path",
                f"calls = Path({str(calls)!r})",
                "with calls.open('a', encoding='utf-8') as stream: stream.write('call\\n')",
                "request = json.loads(Path(os.environ['BOTPIPE_EVAL_REQUEST']).read_text())",
                "cases = [{'case_id': case, 'repetition': 1, 'outcome': 'scored', 'metrics': {'quality': 1.0}, 'evidence_paths': [], 'usage_availability': 'not_attempted', 'elapsed_seconds': 0.01} for case in request['case_ids']]",
                "result = {'schema': 'botpipe.optimizer.eval_result/v1', 'execution_id': request['execution_id'], 'surface_id': request['surface_id'], 'spec_id': request['spec_id'], 'cases': cases}",
                "Path(os.environ['BOTPIPE_EVAL_RESULT']).write_text(json.dumps(result))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    cases = root / "cases.json"
    cases.write_text('{"cases":[{"id":"release-blocked"}]}\n', encoding="utf-8")
    spec = root / "evaluation-spec.json"
    spec.write_text(
        json.dumps(
            {
                "schema": "botpipe.optimizer.evaluation_spec/v1",
                "evaluator_argv": [sys.executable, "{evaluator_path}"],
                "evaluator_path": "evaluator.py",
                "evaluator_content_id": sha256(evaluator.read_bytes()).hexdigest(),
                "case_input_path": "cases.json",
                "case_input_content_id": sha256(cases.read_bytes()).hexdigest(),
                "case_ids": ["release-blocked"],
                "metrics": [
                    {
                        "name": "quality",
                        "unit": "score",
                        "direction": "higher_is_better",
                        "minimum_improvement": 0.1,
                    }
                ],
                "primary_metric": "quality",
            }
        ),
        encoding="utf-8",
    )
    return spec, calls


def test_completed_workflow_reads_saved_pair_without_relaunch(tmp_path):
    from tests.test_labs import _successful_provider

    candidate_id = _publish_optimizer_candidate(tmp_path, kind="workflow")
    spec, calls = _write_evaluation_spec(tmp_path)
    params = RefinementParams(
        selected_workflow="release-go-no-go",
        task_title="Measure optimizer recommendation",
        optimization_receipt_path="optimization_publication_receipt.json",
        candidate_id=candidate_id,
        evaluation_spec_path=spec.name,
        target_test_argv=[sys.executable, "-c", "pass"],
    )
    with Botpipe(
        tmp_path, provider=FakeProvider([_successful_provider] * 24)
    ) as client:
        result = client.run(
            refinement_workflow,
            params,
            request="Measure the accepted optimizer candidate",
            run_id="paired-replay",
        )
        assert result.ok, result.error
        assert calls.read_text(encoding="utf-8").splitlines() == ["call", "call"]
        clean_replay = client.resume(result.run_id)
        assert clean_replay.ok, clean_replay.error
        frozen_evaluator = next(
            (result.folder / "candidate-execution").glob(
                "paired-evaluation-output-*/frozen/evaluator-*"
            )
        )
        frozen_evaluator.write_text("changed after completion\n", encoding="utf-8")
        replay = client.resume(result.run_id)
    assert replay.ok, replay.error
    assert replay.value == result.value
    assert calls.read_text(encoding="utf-8").splitlines() == ["call", "call"]
