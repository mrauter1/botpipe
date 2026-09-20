from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic import BaseModel

from botpipe import Botpipe, Session, workflow
from botpipe.providers import FakeProvider, ProviderResponse
from botpipe_optimizer import (
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


class EvalInputs(BaseModel):
    topic: str
    limit: int = 2


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
        return session.run("decide", returns=Decision, name="decide").value

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
