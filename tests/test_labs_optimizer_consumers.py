from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from botpipe import Botpipe
from botpipe.discovery import resolve_workflow
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
    load_optimizer_candidate_handoff,
    staged_workflow_reference,
    validate_materialized_handoff,
)
from labs.workflows.improve_workflow import ImproveWorkflowParams, improve_workflow
from tests.improvement_support import (
    ACCEPT,
    evaluation_spec,
    implement,
    observed_workflow,
    propose,
    validation_argv,
)
from tests.improvement_support import FixtureProvider as FakeProvider
from labs.workflows.workflow_to_eval_suite import Params as EvalSuiteParams
from labs.workflows.workflow_to_eval_suite import (
    workflow_callable as eval_suite_workflow,
)


def test_eval_selection_requires_complete_receipt_identity():
    with pytest.raises(ValidationError, match="supplied together"):
        EvalSuiteParams(
            selected_workflow="release_candidate_to_go_no_go",
            task_title="Build evals",
            candidate_id="candidate_" + "3" * 64,
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


def test_eval_suite_consumes_reviewed_evaluation_case(tmp_path):
    from tests.test_labs import _successful_provider

    candidate_id = _publish_optimizer_candidate(tmp_path, kind="evaluation_case")
    result = Botpipe(tmp_path, provider=FakeProvider([_successful_provider] * 24)).run(
        eval_suite_workflow,
        EvalSuiteParams(
            selected_workflow="release-go-no-go",
            task_title="Build evals",
            optimization_receipt_path="optimization_publication_receipt.json",
            candidate_id=candidate_id,
        ),
    )
    assert result.ok, result.error


def _interrupt_paired_cache(tmp_path, monkeypatch, *, cache_saved):
    from labs.workflows import optimizer_integration

    reference, _ = observed_workflow(tmp_path)
    spec, calls = evaluation_spec(tmp_path)
    params = ImproveWorkflowParams(
        selected_workflow=reference,
        evaluation_spec_path=str(spec),
        target_test_argv=validation_argv(),
    )
    atomic_json = optimizer_integration._atomic_json
    saved = {}

    def interrupt_cache(path, payload):
        if path.name.startswith("paired-evaluation-cache-") and not saved:
            saved.update(path=path, payload=payload)
            if cache_saved:
                atomic_json(path, payload)
            raise KeyboardInterrupt("interrupted at paired cache publication")
        return atomic_json(path, payload)

    with Botpipe(
        tmp_path, provider=FakeProvider([propose, ACCEPT, implement, ACCEPT])
    ) as client:
        with monkeypatch.context() as patched:
            patched.setattr(optimizer_integration, "_atomic_json", interrupt_cache)
            result = client.run(
                improve_workflow,
                params,
                request="Measure the accepted optimizer candidate",
                run_id="interrupted-pair",
            )
        assert result.status == "interrupted", result.error
        assert saved
        operation = next(
            row
            for row in client.inspect(result.run_id)["operations"]
            if row["name"] == "validate frozen candidate and optional paired evaluation"
        )
        assert operation["status"] == "started"
    assert calls.read_text(encoding="utf-8").splitlines() == ["call", "call"]
    return result.run_id, operation["id"], saved, calls


@pytest.mark.parametrize("cache_saved", [False, True])
def test_interrupted_pair_recovers_without_relaunch(tmp_path, monkeypatch, cache_saved):
    from labs.workflows import optimizer_integration

    run_id, operation_id, saved, calls = _interrupt_paired_cache(
        tmp_path, monkeypatch, cache_saved=cache_saved
    )
    with Botpipe(tmp_path, provider=FakeProvider([ACCEPT])) as client:
        if not cache_saved:
            for _ in range(2):
                suspended = client.resume(run_id)
                assert suspended.status == "interrupted", suspended.error
                assert "outcome is unresolved" in suspended.error
                assert client.journal.get(operation_id)["status"] == "started"
                assert calls.read_text(encoding="utf-8").splitlines() == [
                    "call",
                    "call",
                ]

            client.resolve(run_id, operation_id, retry=True)
            suspended = client.resume(run_id)
            assert suspended.status == "interrupted", suspended.error
            assert client.journal.get(operation_id)["status"] in ("started", "response")
            assert calls.read_text(encoding="utf-8").splitlines() == ["call", "call"]
            # Recover the genuine result from the completed evaluator arms.
            optimizer_integration._atomic_json(saved["path"], saved["payload"])

        resumed = client.resume(run_id)
        assert resumed.ok, resumed.error
        assert client.journal.get(operation_id)["status"] == "completed"
        replayed = client.resume(run_id)
        assert replayed.ok, replayed.error
        assert replayed.value == resumed.value
        assert calls.read_text(encoding="utf-8").splitlines() == ["call", "call"]


@pytest.mark.parametrize("invalid_record", ["attempt", "cache"])
def test_interrupted_pair_rejects_invalid_records(
    tmp_path, monkeypatch, invalid_record
):
    run_id, operation_id, saved, calls = _interrupt_paired_cache(
        tmp_path, monkeypatch, cache_saved=invalid_record == "cache"
    )
    if invalid_record == "attempt":
        path = next(saved["path"].parent.glob("paired-evaluation-attempt-*.json"))
        payload = json.loads(path.read_text())
        payload["attempt_id"] = "different-attempt"
        path.write_text(json.dumps(payload), encoding="utf-8")
        expected_error = "paired evaluation inputs changed"
    else:
        saved["path"].write_text("{}", encoding="utf-8")
        expected_error = "ValueError"

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        rejected = client.resume(run_id)
        assert rejected.status == "failed", rejected.error
        assert expected_error in rejected.error
        assert client.journal.get(operation_id)["status"] == "failed"
        assert calls.read_text(encoding="utf-8").splitlines() == ["call", "call"]
