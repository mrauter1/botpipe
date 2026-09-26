from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Annotated

import pytest
from pydantic import TypeAdapter, ValidationError

from botpipe import Botpipe, Provider, workflow
from botpipe.providers import FakeProvider
from labs.workflows._evidence import EvidenceIntake, capture_declared_evidence
from labs.workflows.task_to_workflow_strategy.contracts import (
    StrategySelectionPayload,
)

OWNED_PACKAGES = (
    "task_to_workflow_strategy",
    "task_to_candidate_workflow_set",
    "candidate_workflow_to_adapted_execution_plan",
    "company_operation_to_recursive_improvement_cycle",
    "workflow_portfolio_to_operating_system",
    "workflow_to_eval_suite",
    "investigation_request_to_evidence_pack",
    "incident_to_hardening_program",
    "security_finding_to_verified_remediation",
    "release_candidate_to_go_no_go",
)

EVIDENCE_PACKAGE_INPUTS = (
    (
        "investigation_request_to_evidence_pack",
        {"investigation_title": "x", "investigation_kind": "general"},
    ),
    ("incident_to_hardening_program", {"incident_title": "x"}),
    (
        "security_finding_to_verified_remediation",
        {"finding_title": "x", "finding_source": "internal_review"},
    ),
    ("release_candidate_to_go_no_go", {"release_name": "x"}),
)


@workflow(name="test_observe_frozen_lab_evidence", version="1")
def _observe_frozen_evidence(evidence_path: str) -> EvidenceIntake:
    intake = capture_declared_evidence((evidence_path,))
    provider = Provider()
    provider.run("inspect the immutable evidence", reads=intake.handles)
    provider.run("inspect the same immutable evidence again", reads=intake.handles)
    return intake


@workflow(name="test_capture_bounded_lab_evidence", version="1")
def _capture_bounded_evidence(evidence_paths: tuple[str, ...]) -> EvidenceIntake:
    return capture_declared_evidence(
        evidence_paths,
        max_files=4,
        max_file_bytes=4,
        max_total_bytes=4,
    )


def _reviewed_phases(package: str) -> set[str]:
    source = Path("labs/workflows", package, "workflow.py").read_text()
    tree = ast.parse(source)
    reviewed = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != "run_phase":
            continue
        keywords = {item.arg: item.value for item in node.keywords if item.arg}
        if "reviewer" not in keywords:
            continue
        phase = keywords["phase"]
        assert isinstance(phase, ast.Constant)
        reviewed.add(phase.value)
    return reviewed


def test_candidate_breadth_follows_available_evidence() -> None:
    result = StrategySelectionPayload(
        outcome="accepted",
        summary="The only credible catalog workflow is a direct fit.",
        artifact_names=["strategy_decision"],
        compared_workflows=["one_real_candidate"],
        selected_strategy="run_existing",
        recommended_workflows=["one_real_candidate"],
    )

    assert result.compared_workflows == ["one_real_candidate"]


@pytest.mark.parametrize("package", OWNED_PACKAGES)
def test_workflow_provider_budget_is_positive_and_strict(package: str) -> None:
    params_type = importlib.import_module(f"labs.workflows.{package}.params").Params
    field = params_type.model_fields["max_provider_turns"]
    adapter = TypeAdapter(Annotated[field.annotation, *field.metadata])

    assert field.default == 32
    with pytest.raises(ValidationError):
        adapter.validate_python(False)
    with pytest.raises(ValidationError):
        adapter.validate_python(0)


@pytest.mark.parametrize(("package", "required"), EVIDENCE_PACKAGE_INPUTS)
def test_declared_evidence_input_is_bounded(package: str, required: dict) -> None:
    params_type = importlib.import_module(f"labs.workflows.{package}.params").Params

    with pytest.raises(ValidationError):
        params_type.model_validate({**required, "evidence_paths": ["x"] * 33})
    with pytest.raises(ValidationError):
        params_type.model_validate({**required, "evidence_paths": ["x" * 1025]})


def test_independent_review_is_reserved_for_material_gates() -> None:
    assert _reviewed_phases("investigation_request_to_evidence_pack") == {
        "assemble_evidence_pack"
    }
    assert _reviewed_phases("incident_to_hardening_program") == {
        "assemble_evidence_pack",
        "rank_cause_hypotheses",
    }
    assert _reviewed_phases("security_finding_to_verified_remediation") == {
        "assess_security_finding",
        "plan_verified_remediation",
    }
    assert _reviewed_phases("release_candidate_to_go_no_go") == {
        "assemble_evidence_pack",
        "assess_go_no_go",
    }


def test_declared_evidence_is_fixed_across_steps_and_replay(tmp_path: Path) -> None:
    source = tmp_path / "evidence.txt"
    source.write_text("before")
    observed: list[bytes] = []

    def inspect(request):
        assert len(request.reads) == 1
        observed.append(request.reads[0].read_bytes())
        source.write_text("after")
        return "ok"

    provider = FakeProvider([inspect, inspect])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(_observe_frozen_evidence, "evidence.txt")
        replayed = client.resume(result.run_id)

    assert result.status == "completed"
    assert replayed.status == "completed"
    assert observed == [b"before", b"before"]
    assert result.value.handles[0].read_bytes() == b"before"
    assert replayed.value.handles[0].digest == result.value.handles[0].digest


def test_unsafe_missing_and_oversize_evidence_are_explicit(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("no")
    (tmp_path / "large.txt").write_text("12345")
    (tmp_path / "folder").mkdir()
    (tmp_path / "link.txt").symlink_to(outside)
    (tmp_path / "extra.txt").write_text("ok")
    (tmp_path / "first.txt").write_text("123")
    (tmp_path / "second.txt").write_text("456")

    with Botpipe(tmp_path) as client:
        result = client.run(
            _capture_bounded_evidence,
            ("missing.txt", "large.txt", "folder", "link.txt", "extra.txt"),
        )
        total_limited = client.run(
            _capture_bounded_evidence, ("first.txt", "second.txt")
        )
        path_limited = client.run(_capture_bounded_evidence, ("x" * 2048,))

    reasons = [record.unavailable_reason for record in result.value.records]
    assert result.status == "completed"
    assert reasons == [
        "missing",
        "file_too_large",
        "not_regular_file",
        "unsafe_path",
        "file_count_limit",
    ]
    assert result.value.handles == ()
    assert result.value.captured_bytes == 0
    assert [record.unavailable_reason for record in total_limited.value.records] == [
        None,
        "total_byte_limit",
    ]
    assert total_limited.value.handles[0].read_bytes() == b"123"
    assert path_limited.value.records[0].unavailable_reason == "unsafe_path"
    assert len(path_limited.value.records[0].declared_path) < 100
