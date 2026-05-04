from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from autoloop.core.compiler import compile_workflow
from autoloop.core.context import Context
from autoloop.core.providers.fake import ScriptedLLMProvider
from autoloop.core.stores import InMemorySessionStore
from autoloop.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from autoloop.runtime.loader import discover_workflow_packages, resolve_workflow_reference
from autoloop.runtime.runner import RunnerOptions, run_workflow_package
from autoloop.core.primitives import Outcome
from tests.runtime.workflow_contract_helpers import invoke_after_verifier_hook, invoke_python_step


REPO_ROOT = Path(__file__).resolve().parents[2]


def _clear_workflow_modules() -> None:
    for name in list(sys.modules):
        if name == "workflows" or name.startswith("workflows.") or name == "autoloop.workflows" or name.startswith("autoloop.workflows."):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_workflow_modules():
    _clear_workflow_modules()
    yield
    _clear_workflow_modules()


def _invoke_optimizer_python_step(workflow_pkg, step_name: str, ctx: Context) -> object:
    return invoke_python_step(workflow_pkg.WorkflowRunTracesToOptimizationCandidates, step_name, ctx)


def _invoke_optimizer_after_verifier_hook(
    workflow_pkg,
    step_name: str,
    ctx: Context,
    *,
    outcome: Outcome,
    artifacts: object | None = None,
) -> object:
    return invoke_after_verifier_hook(
        workflow_pkg.WorkflowRunTracesToOptimizationCandidates,
        step_name,
        ctx,
        outcome=outcome,
        artifacts=artifacts,
    )


def test_workflow_is_registered_and_describable() -> None:
    discovered = {package.workflow_name: package for package in discover_workflow_packages(REPO_ROOT)}

    assert "workflow_run_traces_to_optimization_candidates" in discovered
    package = discovered["workflow_run_traces_to_optimization_candidates"]
    assert package.package_name == "workflow_run_traces_to_optimization_candidates"
    assert "workflow-optimization-candidates" in package.aliases
    assert package.manifest_path == (
        REPO_ROOT / "autoloop" / "workflows" / "workflow_run_traces_to_optimization_candidates" / "workflow.toml"
    )


def test_workflow_describe_lists_parameters_and_pairs(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("autoloop.workflows.workflow_run_traces_to_optimization_candidates")
    resolved = resolve_workflow_reference(REPO_ROOT, workflow_pkg.WorkflowRunTracesToOptimizationCandidates)
    compiled = compile_workflow(resolved.workflow_cls)

    assert resolved.parameters_cls is not None
    assert compiled.entry_step_name == "bootstrap"
    assert tuple(compiled.steps) == (
        "bootstrap",
        "capture_frame_context",
        "frame",
        "rank_targets",
        "mine_failures",
        "optimize_producer",
        "optimize_verifier_rubric",
        "route_optimize_tokens",
        "optimize_tokens",
        "route_adversarial_cases",
        "adversarial_cases",
        "route_workflow_level",
        "workflow_level",
        "package",
        "publish_optimization_packet",
    )
    pair_steps = tuple(name for name, step in compiled.steps.items() if step.kind == "produce_verify")
    assert pair_steps == (
        "frame",
        "rank_targets",
        "mine_failures",
        "optimize_producer",
        "optimize_verifier_rubric",
        "optimize_tokens",
        "adversarial_cases",
        "workflow_level",
        "package",
    )
    assert set(resolved.parameters_cls.model_fields) >= {
        "selected_workflow",
        "task_title",
        "run_refs",
        "run_statuses",
        "route_tags",
        "history_limit",
        "top_k_steps",
        "optimization_depth",
        "include_adversarial_generation",
        "include_token_optimization",
        "include_workflow_level_candidates",
        "max_failure_scenarios",
        "max_candidates_per_pass",
    }

    frame_step = compiled.steps["frame"]
    assert frame_step.available_routes == (
        "optimization_scope_framed",
        "no_eligible_trace_evidence",
        "needs_rework",
        "question",
        "blocked",
        "failed",
    )
    assert list(compiled.route("frame", "no_eligible_trace_evidence").required_writes) == [
        "capture_frame_context.selected_workflow_capability",
        "capture_frame_context.selected_workflow_authoring_surface",
        "capture_frame_context.selected_workflow_decomposition_surface",
        "capture_frame_context.selected_workflow_source_manifest",
        "capture_frame_context.workflow_optimization_scope",
        "capture_frame_context.workflow_optimization_trace_corpus",
        "capture_frame_context.excluded_run_report",
        "capture_frame_context.workflow_failure_scenario_seeds",
    ]
    package_step = compiled.steps["package"]
    assert list(compiled.route("package", "optimization_packet_ready").required_writes) == [
        "package.workflow_optimization_scorecard",
        "package.workflow_optimization_packet",
    ]


def test_pairs_subset_must_be_ordered_prefix(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("autoloop.workflows.workflow_run_traces_to_optimization_candidates")
    resolved = resolve_workflow_reference(REPO_ROOT, workflow_pkg.WorkflowRunTracesToOptimizationCandidates)
    compiled = compile_workflow(resolved.workflow_cls)

    pair_steps = tuple(name for name, step in compiled.steps.items() if step.kind == "produce_verify")
    allowed_prefixes = {pair_steps[:index] for index in range(1, len(pair_steps) + 1)}

    assert ("frame",) in allowed_prefixes
    assert ("frame", "rank_targets", "mine_failures") in allowed_prefixes
    assert pair_steps in allowed_prefixes
    assert ("frame", "mine_failures") not in allowed_prefixes
    assert ("rank_targets", "mine_failures") not in allowed_prefixes


def test_capture_frame_context_excludes_old_runs_missing_plan1_observability(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_minimal_run_metadata(tmp_path, "release-old", "release_candidate_to_go_no_go", "run-old", "failed")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)

    event = _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)

    assert event.tag == "frame_context_captured"
    assert ctx.state.candidate_run_count == 1
    assert ctx.state.eligible_run_count == 0
    assert ctx.state.excluded_run_count == 1
    report = json.loads((ctx.workflow_folder / "excluded_run_report.json").read_text(encoding="utf-8"))
    assert report["excluded_runs"] == [
        {
            "task_id": "release-old",
            "run_id": "run-old",
            "run_ref": "release-old/run-old",
            "reason": "missing_trace_jsonl",
        }
    ]
    del params


def test_capture_frame_context_normalizes_trace_corpus_from_seeded_runs(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    _write_minimal_run_metadata(tmp_path, "release-old", "release_candidate_to_go_no_go", "run-old", "failed")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)

    event = _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)

    assert event.tag == "frame_context_captured"
    assert ctx.state.candidate_run_count == 2
    assert ctx.state.eligible_run_count == 1
    assert ctx.state.excluded_run_count == 1
    corpus = json.loads((ctx.workflow_folder / "workflow_optimization_trace_corpus.json").read_text(encoding="utf-8"))
    assert corpus["runs"][0]["run_ref"] == "release-good/run-good"
    assert corpus["step_observations"][0]["raw_output_refs"]["producer"] == "raw/000003_assessment_producer.txt"
    assert corpus["step_observations"][0]["commit_after_step"] == "commit-after-step"
    del params


def test_capture_frame_context_keeps_public_trace_filtered_but_internal_trace_complete(
    tmp_path: Path, monkeypatch
) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_upstream_pass_downstream_fail_run(tmp_path, "release-upstream", "release_candidate_to_go_no_go", "run-upstream")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch, route_tags=["failed"])

    event = _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)

    public_corpus = json.loads((ctx.workflow_folder / "workflow_optimization_trace_corpus.json").read_text(encoding="utf-8"))
    internal_corpus = json.loads(
        (ctx.workflow_folder / "_workflow_optimization_internal_trace_corpus.json").read_text(encoding="utf-8")
    )
    report = json.loads((ctx.workflow_folder / "step_optimization_priority_report.json").read_text(encoding="utf-8"))

    assert event.tag == "frame_context_captured"
    assert ctx.state.eligible_run_count == 1
    assert "all_step_observations" not in public_corpus
    assert "static_step_graphs" not in public_corpus
    assert [entry["step_name"] for entry in public_corpus["step_observations"]] == ["package"]
    assert {entry["step_name"] for entry in internal_corpus["all_step_observations"]} == {"assessment", "package"}
    assert report["ranked_steps"][0]["step_name"] == "assessment"
    del params


def test_rank_targets_writes_priority_report(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)

    _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)

    metrics = json.loads((ctx.workflow_folder / "step_trace_metrics.json").read_text(encoding="utf-8"))
    report = json.loads((ctx.workflow_folder / "step_optimization_priority_report.json").read_text(encoding="utf-8"))

    assert metrics["schema"] == "autoloop.workflow_optimization.step_trace_metrics/v1"
    assert metrics["steps"][0]["step_name"] == "assessment"
    assert report["schema"] == "autoloop.workflow_optimization.step_priority_report/v1"
    assert report["ranked_steps"][0]["step_name"] == "assessment"
    del params


def test_route_optimize_tokens_skips_when_disabled(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)
    _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)
    disabled_state = ctx.state.model_copy(update={"include_token_optimization": False})
    ctx.state = disabled_state

    event = _invoke_optimizer_python_step(workflow_pkg, "route_optimize_tokens", ctx)

    payload = json.loads((ctx.workflow_folder / "token_optimization_candidates.json").read_text(encoding="utf-8"))
    assert event.tag == "token_pass_not_applicable"
    assert ctx.state.token_status == "token_pass_not_applicable"
    assert payload == {
        "schema": "autoloop.workflow_optimization.token_candidates/v1",
        "selected_workflow": "release_candidate_to_go_no_go",
        "candidates": [],
    }
    del params


def test_adversarial_cases_can_be_skipped(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)
    _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)
    disabled_state = ctx.state.model_copy(update={"include_adversarial_generation": False})
    ctx.state = disabled_state

    event = _invoke_optimizer_python_step(workflow_pkg, "route_adversarial_cases", ctx)

    payload = json.loads((ctx.workflow_folder / "adversarial_case_candidates.json").read_text(encoding="utf-8"))
    assert event.tag == "adversarial_generation_skipped"
    assert ctx.state.adversarial_status == "adversarial_generation_skipped"
    assert payload == {
        "schema": "autoloop.workflow_optimization.adversarial_case_candidates/v1",
        "selected_workflow": "release_candidate_to_go_no_go",
        "cases": [],
    }
    del params


def test_workflow_level_can_be_skipped(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)
    _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)
    disabled_state = ctx.state.model_copy(update={"include_workflow_level_candidates": False})
    ctx.state = disabled_state

    event = _invoke_optimizer_python_step(workflow_pkg, "route_workflow_level", ctx)

    payload = json.loads(
        (ctx.workflow_folder / "workflow_level_optimization_candidates.json").read_text(encoding="utf-8")
    )
    assert event.tag == "workflow_level_pass_not_applicable"
    assert ctx.state.workflow_level_status == "workflow_level_pass_not_applicable"
    assert payload == {
        "schema": "autoloop.workflow_optimization.workflow_level_candidates/v1",
        "selected_workflow": "release_candidate_to_go_no_go",
        "candidates": [],
    }
    del params


_NOT_APPLICABLE_HANDLER_CASES = [
    (
        "on_optimize_producer",
        "producer_status",
        "producer_prompt_optimization_candidates",
        "producer_prompt_optimization_candidates.json",
        "producer_pass_not_applicable",
        {
            "schema": "autoloop.workflow_optimization.producer_candidates/v1",
            "selected_workflow": "release_candidate_to_go_no_go",
            "target_steps": ["assessment"],
            "candidates": [
                {
                    "candidate_id": "producer-existing-001",
                    "step_name": "assessment",
                    "target_surface": "producer_prompt",
                    "target_path": "autoloop/workflows/release_candidate_to_go_no_go/prompts/assessment_producer.md",
                    "failure_ids_addressed": ["assessment_missing_rollback_evidence"],
                    "diagnosis": "Existing provider-authored producer candidate.",
                    "proposed_change_summary": "Preserve the authored producer candidate on not-applicable routes.",
                    "confidence": 0.71,
                    "evidence_strength": "medium",
                    "risks": [],
                    "requires_ablation": False,
                }
            ],
        },
        {
            "schema": "autoloop.workflow_optimization.producer_candidates/v1",
            "selected_workflow": "release_candidate_to_go_no_go",
            "target_steps": [],
            "candidates": [],
        },
    ),
    (
        "on_optimize_verifier_rubric",
        "verifier_rubric_status",
        "verifier_rubric_optimization_candidates",
        "verifier_rubric_optimization_candidates.json",
        "verifier_rubric_pass_not_applicable",
        {
            "schema": "autoloop.workflow_optimization.verifier_rubric_candidates/v1",
            "selected_workflow": "release_candidate_to_go_no_go",
            "target_steps": ["assessment"],
            "candidates": [
                {
                    "candidate_id": "verifier-existing-001",
                    "step_name": "assessment",
                    "target_surfaces": ["verifier_prompt", "criteria"],
                    "diagnosis": "Existing provider-authored verifier/rubric candidate.",
                    "failure_ids_addressed": ["assessment_missing_rollback_evidence"],
                    "proposed_changes": [],
                    "expected_effect": {},
                    "confidence": 0.69,
                    "evidence_strength": "medium",
                    "risks": [],
                    "requires_ablation": False,
                }
            ],
        },
        {
            "schema": "autoloop.workflow_optimization.verifier_rubric_candidates/v1",
            "selected_workflow": "release_candidate_to_go_no_go",
            "target_steps": [],
            "candidates": [],
        },
    ),
    (
        "on_optimize_tokens",
        "token_status",
        "token_optimization_candidates",
        "token_optimization_candidates.json",
        "token_pass_not_applicable",
        {
            "schema": "autoloop.workflow_optimization.token_candidates/v1",
            "selected_workflow": "release_candidate_to_go_no_go",
            "candidates": [
                {
                    "candidate_id": "token-existing-handler-001",
                    "step_name": "assessment",
                    "target_surface": "producer_prompt",
                    "compression_kind": "deduplicate_instruction_block",
                    "risk_class": "safe_compression",
                    "estimated_input_token_reduction": 120,
                    "diagnosis": "Existing provider-authored token candidate.",
                    "proposed_change_summary": "Preserve the token candidate on not-applicable routes.",
                    "quality_risk": "Low because the change only removes duplication.",
                    "confidence": 0.72,
                    "evidence_strength": "medium",
                    "requires_ablation": False,
                }
            ],
        },
        {
            "schema": "autoloop.workflow_optimization.token_candidates/v1",
            "selected_workflow": "release_candidate_to_go_no_go",
            "candidates": [],
        },
    ),
    (
        "on_adversarial_cases",
        "adversarial_status",
        "adversarial_case_candidates",
        "adversarial_case_candidates.json",
        "adversarial_generation_skipped",
        {
            "schema": "autoloop.workflow_optimization.adversarial_case_candidates/v1",
            "selected_workflow": "release_candidate_to_go_no_go",
            "cases": [
                {
                    "case_id": "adversarial-existing-handler-001",
                    "case_kind": "missing_evidence_claim",
                    "attack_vector": "Ask for promotion without rollback evidence.",
                    "prompt": "Approve release with no rollback owner or evidence trail.",
                    "source_failure_ids": ["provider-failure-001"],
                    "expected_stress": "Verifier should force explicit evidence collection.",
                    "expected_route": "needs_rework",
                    "expected_artifacts": ["assessment.md"],
                    "recommended_for_eval_suite": True,
                    "confidence": 0.68,
                    "evidence_strength": "medium",
                }
            ],
        },
        {
            "schema": "autoloop.workflow_optimization.adversarial_case_candidates/v1",
            "selected_workflow": "release_candidate_to_go_no_go",
            "cases": [],
        },
    ),
    (
        "on_workflow_level",
        "workflow_level_status",
        "workflow_level_optimization_candidates",
        "workflow_level_optimization_candidates.json",
        "workflow_level_pass_not_applicable",
        {
            "schema": "autoloop.workflow_optimization.workflow_level_candidates/v1",
            "selected_workflow": "release_candidate_to_go_no_go",
            "candidates": [
                {
                    "candidate_id": "workflow-existing-handler-001",
                    "candidate_kind": "prompt_readme_change",
                    "diagnosis": "Existing provider-authored workflow-level candidate.",
                    "affected_steps": ["assessment"],
                    "proposed_change_summary": "Clarify the workflow-level review boundary.",
                    "proposed_surfaces": ["autoloop/workflows/release_candidate_to_go_no_go/prompts/README.md"],
                    "confidence": 0.64,
                    "evidence_strength": "low",
                    "risks": [],
                    "requires_refinement_workflow": False,
                    "requires_ablation": False,
                }
            ],
        },
        {
            "schema": "autoloop.workflow_optimization.workflow_level_candidates/v1",
            "selected_workflow": "release_candidate_to_go_no_go",
            "candidates": [],
        },
    ),
]


@pytest.mark.parametrize(
    ("disabled_flag", "handler_name", "status_field", "artifact_filename", "expected_tag", "existing_payload"),
    [
        (
            "include_token_optimization",
            "on_route_optimize_tokens",
            "token_status",
            "token_optimization_candidates.json",
            "token_pass_not_applicable",
            {
                "schema": "autoloop.workflow_optimization.token_candidates/v1",
                "selected_workflow": "release_candidate_to_go_no_go",
                "candidates": [
                    {
                        "candidate_id": "token-existing-001",
                        "step_name": "assessment",
                        "target_surface": "producer_prompt",
                        "compression_kind": "deduplicate_instruction_block",
                        "risk_class": "safe_compression",
                        "estimated_input_token_reduction": 120,
                        "diagnosis": "Existing provider-authored token candidate.",
                        "proposed_change_summary": "Keep the focused compression candidate.",
                        "quality_risk": "Low because the change only removes duplication.",
                        "confidence": 0.72,
                        "evidence_strength": "medium",
                        "requires_ablation": False,
                    }
                ],
            },
        ),
        (
            "include_adversarial_generation",
            "on_route_adversarial_cases",
            "adversarial_status",
            "adversarial_case_candidates.json",
            "adversarial_generation_skipped",
            {
                "schema": "autoloop.workflow_optimization.adversarial_case_candidates/v1",
                "selected_workflow": "release_candidate_to_go_no_go",
                "cases": [
                    {
                        "case_id": "adversarial-existing-001",
                        "case_kind": "missing_evidence_claim",
                        "attack_vector": "Ask for promotion without rollback evidence.",
                        "prompt": "Approve release with no rollback owner or evidence trail.",
                        "source_failure_ids": ["provider-failure-001"],
                        "expected_stress": "Verifier should force explicit evidence collection.",
                        "expected_route": "needs_rework",
                        "expected_artifacts": ["assessment.md"],
                        "recommended_for_eval_suite": True,
                        "confidence": 0.68,
                        "evidence_strength": "medium",
                    }
                ],
            },
        ),
        (
            "include_workflow_level_candidates",
            "on_route_workflow_level",
            "workflow_level_status",
            "workflow_level_optimization_candidates.json",
            "workflow_level_pass_not_applicable",
            {
                "schema": "autoloop.workflow_optimization.workflow_level_candidates/v1",
                "selected_workflow": "release_candidate_to_go_no_go",
                "candidates": [
                    {
                        "candidate_id": "workflow-existing-001",
                        "candidate_kind": "prompt_readme_change",
                        "diagnosis": "Existing provider-authored workflow-level candidate.",
                        "affected_steps": ["assessment"],
                        "proposed_change_summary": "Clarify the workflow-level review boundary.",
                        "proposed_surfaces": [
                            "autoloop/workflows/release_candidate_to_go_no_go/prompts/README.md"
                        ],
                        "confidence": 0.64,
                        "evidence_strength": "low",
                        "risks": [],
                        "requires_refinement_workflow": False,
                        "requires_ablation": False,
                    }
                ],
            },
        ),
    ],
)
def test_optional_skip_routes_preserve_existing_artifacts_when_present(
    tmp_path: Path,
    monkeypatch,
    disabled_flag: str,
    handler_name: str,
    status_field: str,
    artifact_filename: str,
    expected_tag: str,
    existing_payload: dict[str, object],
) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)
    _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)
    disabled_state = ctx.state.model_copy(update={disabled_flag: False})
    ctx.state = disabled_state

    artifact_path = ctx.workflow_folder / artifact_filename
    artifact_path.write_text(json.dumps(existing_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    event = _invoke_optimizer_python_step(workflow_pkg, handler_name.removeprefix("on_"), ctx)

    assert event.tag == expected_tag
    assert getattr(ctx.state, status_field) == expected_tag
    assert json.loads(artifact_path.read_text(encoding="utf-8")) == existing_payload
    del params


@pytest.mark.parametrize(
    (
        "handler_name",
        "status_field",
        "artifact_field",
        "artifact_filename",
        "outcome_tag",
        "existing_payload",
        "expected_empty_payload",
    ),
    _NOT_APPLICABLE_HANDLER_CASES,
)
def test_not_applicable_candidate_handlers_preserve_existing_artifacts(
    tmp_path: Path,
    monkeypatch,
    handler_name: str,
    status_field: str,
    artifact_field: str,
    artifact_filename: str,
    outcome_tag: str,
    existing_payload: dict[str, object],
    expected_empty_payload: dict[str, object],
) -> None:
    del expected_empty_payload
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)
    _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)

    artifact_path = ctx.workflow_folder / artifact_filename
    artifact_path.write_text(json.dumps(existing_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    _invoke_optimizer_after_verifier_hook(
        workflow_pkg,
        handler_name.removeprefix("on_"),
        ctx,
        outcome=Outcome(
            raw_output="not applicable\n",
            tag=outcome_tag,
            payload={
                "summary": "This optimization surface is not applicable for the selected evidence.",
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "target_steps": ["assessment"],
                "candidate_ids": [],
                "case_ids": [],
            },
        ),
        artifacts=SimpleNamespace(**{artifact_field: _JsonHandle(artifact_path)}),
    )

    assert getattr(ctx.state, status_field) == outcome_tag
    assert json.loads(artifact_path.read_text(encoding="utf-8")) == existing_payload
    del params


@pytest.mark.parametrize(
    (
        "handler_name",
        "status_field",
        "artifact_field",
        "artifact_filename",
        "outcome_tag",
        "existing_payload",
        "expected_empty_payload",
    ),
    _NOT_APPLICABLE_HANDLER_CASES,
)
def test_not_applicable_candidate_handlers_write_empty_artifacts_when_missing(
    tmp_path: Path,
    monkeypatch,
    handler_name: str,
    status_field: str,
    artifact_field: str,
    artifact_filename: str,
    outcome_tag: str,
    existing_payload: dict[str, object],
    expected_empty_payload: dict[str, object],
) -> None:
    del existing_payload
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)
    _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)

    artifact_path = ctx.workflow_folder / artifact_filename
    artifact_path.unlink(missing_ok=True)

    _invoke_optimizer_after_verifier_hook(
        workflow_pkg,
        handler_name.removeprefix("on_"),
        ctx,
        outcome=Outcome(
            raw_output="not applicable\n",
            tag=outcome_tag,
            payload={
                "summary": "This optimization surface is not applicable for the selected evidence.",
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "target_steps": ["assessment"],
                "candidate_ids": [],
                "case_ids": [],
            },
        ),
        artifacts=SimpleNamespace(**{artifact_field: _JsonHandle(artifact_path)}),
    )

    assert getattr(ctx.state, status_field) == outcome_tag
    assert json.loads(artifact_path.read_text(encoding="utf-8")) == expected_empty_payload
    del params


def test_failure_scenario_seeds_are_written_separately_from_failure_scenarios(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)
    _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)

    seeds_payload = json.loads((ctx.workflow_folder / "workflow_failure_scenario_seeds.json").read_text(encoding="utf-8"))
    assert seeds_payload["schema"] == "autoloop.workflow_optimization.failure_scenario_seeds/v1"
    assert seeds_payload["selected_workflow"] == "release_candidate_to_go_no_go"
    assert isinstance(seeds_payload["seeds"], list)

    provider_payload = {
        "schema": "autoloop.workflow_optimization.failure_scenarios/v1",
        "selected_workflow": "release_candidate_to_go_no_go",
        "failure_scenarios": [
            {
                "failure_id": "provider-authored-001",
                "step_name": "assessment",
                "failure_kind": "producer_failed_verifier",
                "severity": "medium",
                "frequency": 1,
                "evidence_observation_ids": ["release-good/run-good:000003:assessment"],
            }
        ],
    }
    (ctx.workflow_folder / "workflow_failure_scenarios.json").write_text(
        json.dumps(provider_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    artifacts = SimpleNamespace(
        workflow_failure_scenarios=_JsonHandle(ctx.workflow_folder / "workflow_failure_scenarios.json"),
    )
    _invoke_optimizer_after_verifier_hook(
        workflow_pkg,
        "mine_failures",
        ctx,
        outcome=Outcome(
            raw_output="failure scenarios grounded\n",
            tag="failure_scenarios_mined",
            payload={
                "summary": "Failure scenarios were mined from the ranked target set.",
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "target_steps": ["assessment"],
                "failure_ids": ["assessment_producer_failed_verifier"],
            },
        ),
        artifacts=artifacts,
    )

    final_payload = json.loads((ctx.workflow_folder / "workflow_failure_scenarios.json").read_text(encoding="utf-8"))
    assert final_payload == provider_payload
    assert seeds_payload["schema"] != final_payload["schema"]
    del params


def test_mine_failures_preserves_provider_authored_failure_scenarios(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)
    _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)

    provider_payload = {
        "schema": "autoloop.workflow_optimization.failure_scenarios/v1",
        "selected_workflow": "release_candidate_to_go_no_go",
        "failure_scenarios": [
            {
                "failure_id": "provider-distinctive-001",
                "step_name": "assessment",
                "failure_kind": "producer_failed_verifier",
                "severity": "medium",
                "frequency": 7,
                "evidence_observation_ids": ["distinctive-observation"],
                "producer_gap": "Distinctive provider-authored content.",
            }
        ],
    }
    final_path = ctx.workflow_folder / "workflow_failure_scenarios.json"
    final_path.write_text(json.dumps(provider_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    _invoke_optimizer_after_verifier_hook(
        workflow_pkg,
        "mine_failures",
        ctx,
        outcome=Outcome(
            raw_output="failure scenarios grounded\n",
            tag="failure_scenarios_mined",
            payload={
                "summary": "Failure scenarios were mined from the ranked target set.",
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "target_steps": ["assessment"],
                "failure_ids": ["provider-distinctive-001"],
            },
        ),
        artifacts=SimpleNamespace(workflow_failure_scenarios=_JsonHandle(final_path)),
    )

    seeds_payload = json.loads((ctx.workflow_folder / "workflow_failure_scenario_seeds.json").read_text(encoding="utf-8"))
    preserved_payload = json.loads(final_path.read_text(encoding="utf-8"))

    assert ctx.state.failure_status == "failure_scenarios_mined"
    assert preserved_payload == provider_payload
    assert preserved_payload != seeds_payload
    del params


def test_mine_failures_writes_empty_artifact_only_for_no_failure_scenarios_when_missing(
    tmp_path: Path, monkeypatch
) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)
    _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)

    final_path = ctx.workflow_folder / "workflow_failure_scenarios.json"
    final_path.unlink(missing_ok=True)

    _invoke_optimizer_after_verifier_hook(
        workflow_pkg,
        "mine_failures",
        ctx,
        outcome=Outcome(
            raw_output="no failure scenarios\n",
            tag="no_failure_scenarios",
            payload={
                "summary": "No credible failure scenarios were mined.",
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "target_steps": ["assessment"],
                "failure_ids": [],
            },
        ),
        artifacts=SimpleNamespace(workflow_failure_scenarios=_JsonHandle(final_path)),
    )

    payload = json.loads(final_path.read_text(encoding="utf-8"))
    assert ctx.state.failure_status == "no_failure_scenarios"
    assert payload == {
        "schema": "autoloop.workflow_optimization.failure_scenarios/v1",
        "selected_workflow": "release_candidate_to_go_no_go",
        "failure_scenarios": [],
    }
    del params


def test_mine_failures_malformed_artifact_is_not_replaced(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)
    _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)

    final_path = ctx.workflow_folder / "workflow_failure_scenarios.json"
    final_path.write_text(
        json.dumps(
            {
                "schema": "autoloop.workflow_optimization.failure_scenarios/v1",
                "selected_workflow": "wrong_workflow",
                "failure_scenarios": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    original_text = final_path.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="workflow_failure_scenarios.json selected_workflow must match"):
        _invoke_optimizer_after_verifier_hook(
            workflow_pkg,
            "mine_failures",
            ctx,
            outcome=Outcome(
                raw_output="failure scenarios grounded\n",
                tag="failure_scenarios_mined",
                payload={
                    "summary": "Failure scenarios were mined from the ranked target set.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "target_steps": ["assessment"],
                    "failure_ids": [],
                },
            ),
            artifacts=SimpleNamespace(workflow_failure_scenarios=_JsonHandle(final_path)),
        )

    assert final_path.read_text(encoding="utf-8") == original_text
    del params


def test_optimize_producer_writes_candidate_artifact(tmp_path: Path) -> None:
    result, provider, workflow_dir = _run_enabled_candidate_workflow(tmp_path)

    payload = json.loads((workflow_dir / "producer_prompt_optimization_candidates.json").read_text(encoding="utf-8"))

    assert result.terminal == "FINISH"
    assert "optimize_producer" in [call.step_name for call in provider.calls]
    assert payload["schema"] == "autoloop.workflow_optimization.producer_candidates/v1"
    assert payload["candidates"][0]["candidate_id"] == "producer-assessment-001"
    assert payload["candidates"][0]["step_name"] == "assessment"


def test_max_candidates_per_pass_is_prompt_guidance_not_schema_limit(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    params, state, ctx, workflow_pkg = _bootstrap_context(
        tmp_path,
        monkeypatch,
        max_candidates_per_pass=1,
    )
    _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)

    payload = {
        "schema": "autoloop.workflow_optimization.producer_candidates/v1",
        "selected_workflow": "release_candidate_to_go_no_go",
        "target_steps": ["assessment"],
        "candidates": [
            {
                "candidate_id": "producer-assessment-001",
                "step_name": "assessment",
                "target_surface": "producer_prompt",
                "target_path": "autoloop/workflows/release_candidate_to_go_no_go/prompts/assessment_producer.md",
                "failure_ids_addressed": ["assessment_missing_rollback_evidence"],
                "diagnosis": "First high-leverage candidate.",
                "proposed_change_summary": "Tighten evidence requirements.",
                "confidence": 0.7,
                "evidence_strength": "medium",
                "risks": [],
                "requires_ablation": False,
            },
            {
                "candidate_id": "producer-assessment-002",
                "step_name": "assessment",
                "target_surface": "producer_prompt",
                "target_path": "autoloop/workflows/release_candidate_to_go_no_go/prompts/assessment_producer.md",
                "failure_ids_addressed": ["assessment_missing_rollback_evidence"],
                "diagnosis": "Second candidate kept intentionally over budget.",
                "proposed_change_summary": "Add explicit unsupported-claim handling.",
                "confidence": 0.65,
                "evidence_strength": "medium",
                "risks": [],
                "requires_ablation": False,
            },
        ],
    }
    artifact_path = ctx.workflow_folder / "producer_prompt_optimization_candidates.json"
    artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    _invoke_optimizer_after_verifier_hook(
        workflow_pkg,
        "optimize_producer",
        ctx,
        outcome=Outcome(
            raw_output="producer candidates ready\n",
            tag="producer_candidates_ready",
            payload={
                "summary": "Two grounded candidates remain useful even though the soft budget is one.",
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "target_steps": ["assessment"],
                "candidate_ids": ["producer-assessment-001", "producer-assessment-002"],
            },
        ),
        artifacts=SimpleNamespace(producer_prompt_optimization_candidates=_JsonHandle(artifact_path)),
    )

    scope = json.loads((ctx.workflow_folder / "workflow_optimization_scope.json").read_text(encoding="utf-8"))
    final_payload = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert ctx.state.producer_status == "producer_candidates_ready"
    assert scope["max_candidates_per_pass"] == 1
    assert len(final_payload["candidates"]) == 2
    assert [candidate["candidate_id"] for candidate in final_payload["candidates"]] == [
        "producer-assessment-001",
        "producer-assessment-002",
    ]
    del params


def test_optimize_verifier_rubric_writes_merged_acceptance_candidates(tmp_path: Path) -> None:
    result, provider, workflow_dir = _run_enabled_candidate_workflow(tmp_path)

    payload = json.loads((workflow_dir / "verifier_rubric_optimization_candidates.json").read_text(encoding="utf-8"))

    assert result.terminal == "FINISH"
    assert "optimize_verifier_rubric" in [call.step_name for call in provider.calls]
    assert payload["schema"] == "autoloop.workflow_optimization.verifier_rubric_candidates/v1"
    assert payload["candidates"][0]["candidate_id"] == "verifier-rubric-assessment-001"
    assert payload["candidates"][0]["target_surfaces"] == ["verifier_prompt", "criteria", "route_contract"]


def test_optimize_tokens_writes_token_candidates(tmp_path: Path) -> None:
    result, provider, workflow_dir = _run_enabled_candidate_workflow(tmp_path)

    payload = json.loads((workflow_dir / "token_optimization_candidates.json").read_text(encoding="utf-8"))

    assert result.terminal == "FINISH"
    assert "optimize_tokens" in [call.step_name for call in provider.calls]
    assert payload["schema"] == "autoloop.workflow_optimization.token_candidates/v1"
    assert payload["candidates"][0]["candidate_id"] == "token-assessment-001"
    assert payload["candidates"][0]["risk_class"] == "safe_compression"


def test_adversarial_cases_writes_candidate_cases_when_enabled(tmp_path: Path) -> None:
    result, provider, workflow_dir = _run_enabled_candidate_workflow(tmp_path)

    payload = json.loads((workflow_dir / "adversarial_case_candidates.json").read_text(encoding="utf-8"))

    assert result.terminal == "FINISH"
    assert "adversarial_cases" in [call.step_name for call in provider.calls]
    assert payload["schema"] == "autoloop.workflow_optimization.adversarial_case_candidates/v1"
    assert payload["cases"][0]["case_id"] == "adversarial-missing-rollback-owner"
    assert payload["cases"][0]["expected_route"] == "needs_rework"


def test_frame_no_eligible_runs_publishes_noop_packet(tmp_path: Path) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_minimal_run_metadata(tmp_path, "release-old", "release_candidate_to_go_no_go", "run-old", "failed")

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: "frame reviewed\n",
            _produce_noop_package,
        ],
        verifier_turns=[
            Outcome(
                raw_output="no eligible evidence\n",
                tag="no_eligible_trace_evidence",
                payload={
                    "summary": "Historical runs were discovered, but none had the required Plan-1 observability bundle.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "candidate_run_count": 1,
                    "eligible_run_count": 0,
                    "excluded_run_count": 1,
                    "top_k_steps": 1,
                    "route_tags": ["needs_rework", "needs_replan", "failed", "blocked"],
                },
            ),
            Outcome(
                raw_output="optimization packet ready\n",
                tag="optimization_packet_ready",
                payload={
                    "summary": "The no-op scorecard and packet are aligned for deterministic publication.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "authoritative_artifacts": [
                        "workflow_optimization_scorecard",
                        "workflow_optimization_packet",
                    ],
                    "highest_priority_candidate_ids": [],
                    "recommended_next_action": "Collect eligible Plan-1 observability bundles, then rerun the optimizer.",
                    "requires_ablation_before_promotion": False,
                    "source_mutation_check_expected": True,
                },
            ),
        ],
    )

    result = run_workflow_package(
        "workflow_run_traces_to_optimization_candidates",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="optimizer-task",
            message="Publish a no-op optimizer packet for historical runs missing observability.\n",
            workflow_params={
                "selected_workflow": "release_candidate_to_go_no_go",
                "task_title": "Release workflow optimization",
                "run_statuses": ["failed", "awaiting_input", "blocked"],
                "route_tags": ["needs_rework", "needs_replan", "failed", "blocked"],
            },
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    workflow_dir = tmp_path / ".autoloop" / "tasks" / "optimizer-task" / "wf_workflow_run_traces_to_optimization_candidates"
    assert result.terminal == "FINISH"
    assert (workflow_dir / "workflow_optimization_scope.json").exists()
    assert (workflow_dir / "workflow_optimization_trace_corpus.json").exists()
    assert (workflow_dir / "excluded_run_report.json").exists()
    assert (workflow_dir / "selected_workflow_source_manifest.json").exists()
    assert (workflow_dir / "workflow_optimization_scorecard.json").exists()
    assert (workflow_dir / "workflow_refinement_evidence.json").exists()
    assert (workflow_dir / "workflow_optimization_packet.md").exists()
    assert (workflow_dir / "optimization_publication_receipt.json").exists()
    assert not (tmp_path / ".autoloop" / "tasks" / "optimizer-task" / "wf_workflow_and_eval_to_refined_workflow_package").exists()

    scorecard = json.loads((workflow_dir / "workflow_optimization_scorecard.json").read_text(encoding="utf-8"))
    receipt = json.loads((workflow_dir / "optimization_publication_receipt.json").read_text(encoding="utf-8"))
    evidence = json.loads((workflow_dir / "workflow_refinement_evidence.json").read_text(encoding="utf-8"))
    packet_text = (workflow_dir / "workflow_optimization_packet.md").read_text(encoding="utf-8")

    assert scorecard["selected_workflow"] == "release_candidate_to_go_no_go"
    assert scorecard["evidence_run_count"] == 0
    assert scorecard["excluded_run_count"] == 1
    assert receipt["no_eligible_trace_evidence"] is True
    assert evidence["evidence_entries"][0]["kind"] == "workflow_optimization_scorecard"
    assert "No eligible Plan-1 observability bundles were available" in packet_text


def test_full_run_skips_disabled_optional_passes_without_provider_calls(tmp_path: Path) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: "frame reviewed\n",
            lambda request: "ranking reviewed\n",
            lambda request: "failure review complete\n",
            _produce_skipped_optional_passes_package,
        ],
        verifier_turns=[
            Outcome(
                raw_output="frame grounded\n",
                tag="optimization_scope_framed",
                payload={
                    "summary": "The selected workflow and trace scope are grounded for ranking.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "candidate_run_count": 1,
                    "eligible_run_count": 1,
                    "excluded_run_count": 0,
                    "top_k_steps": 1,
                    "route_tags": ["needs_rework", "needs_replan", "failed", "blocked"],
                },
            ),
            Outcome(
                raw_output="targets ranked\n",
                tag="targets_ranked",
                payload={
                    "summary": "Assessment is the highest-leverage target.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "ranked_steps": ["assessment"],
                    "ranking_method": "static_graph_plus_trace_metrics_plus_llm_attribution",
                },
            ),
            Outcome(
                raw_output="no local failure scenarios\n",
                tag="no_failure_scenarios",
                payload={
                    "summary": "No targeted failure scenarios were mined, so optional local passes are considered from skip gates.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "target_steps": ["assessment"],
                    "failure_ids": [],
                },
            ),
            Outcome(
                raw_output="optimization packet ready\n",
                tag="optimization_packet_ready",
                payload={
                    "summary": "The scorecard and packet are aligned after optional passes were skipped.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "authoritative_artifacts": [
                        "workflow_optimization_scorecard",
                        "workflow_optimization_packet",
                    ],
                    "highest_priority_candidate_ids": [],
                    "recommended_next_action": "Review the ranked scope before enabling optional candidate passes.",
                    "requires_ablation_before_promotion": False,
                    "source_mutation_check_expected": True,
                },
            ),
        ],
    )

    result = run_workflow_package(
        "workflow_run_traces_to_optimization_candidates",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="optimizer-task",
            message="Publish an optimizer packet with all optional passes disabled.\n",
            workflow_params={
                "selected_workflow": "release_candidate_to_go_no_go",
                "task_title": "Release workflow optimization",
                "include_token_optimization": False,
                "include_adversarial_generation": False,
                "include_workflow_level_candidates": False,
                "run_statuses": ["failed", "awaiting_input", "blocked"],
                "route_tags": ["needs_rework", "needs_replan", "failed", "blocked"],
            },
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    workflow_dir = tmp_path / ".autoloop" / "tasks" / "optimizer-task" / "wf_workflow_run_traces_to_optimization_candidates"
    token_candidates = json.loads((workflow_dir / "token_optimization_candidates.json").read_text(encoding="utf-8"))
    adversarial_candidates = json.loads((workflow_dir / "adversarial_case_candidates.json").read_text(encoding="utf-8"))
    workflow_level_candidates = json.loads(
        (workflow_dir / "workflow_level_optimization_candidates.json").read_text(encoding="utf-8")
    )

    observed_step_calls = [call.step_name for call in provider.calls]

    assert result.terminal == "FINISH"
    assert "frame" in observed_step_calls
    assert "rank_targets" in observed_step_calls
    assert "mine_failures" in observed_step_calls
    assert "package" in observed_step_calls
    assert "optimize_tokens" not in observed_step_calls
    assert "adversarial_cases" not in observed_step_calls
    assert "workflow_level" not in observed_step_calls
    assert token_candidates["candidates"] == []
    assert adversarial_candidates["cases"] == []
    assert workflow_level_candidates["candidates"] == []


def test_insufficient_evidence_short_circuit_does_not_publish_failure_scenarios(tmp_path: Path) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: "frame reviewed\n",
            lambda request: "ranking reviewed\n",
            _produce_insufficient_evidence_package,
        ],
        verifier_turns=[
            Outcome(
                raw_output="frame grounded\n",
                tag="optimization_scope_framed",
                payload={
                    "summary": "The selected workflow and trace scope are grounded for ranking.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "candidate_run_count": 1,
                    "eligible_run_count": 1,
                    "excluded_run_count": 0,
                    "top_k_steps": 1,
                    "route_tags": ["needs_rework", "needs_replan", "failed", "blocked"],
                },
            ),
            Outcome(
                raw_output="evidence is thin\n",
                tag="insufficient_evidence",
                payload={
                    "summary": "The deterministic ranking artifacts are low-confidence and should short-circuit to packaging.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "ranked_steps": [],
                    "ranking_method": "static_graph_plus_trace_metrics_plus_llm_attribution",
                },
            ),
            Outcome(
                raw_output="insufficient evidence package ready\n",
                tag="optimization_packet_ready",
                payload={
                    "summary": "The low-confidence scorecard and packet are aligned for publication.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "authoritative_artifacts": [
                        "workflow_optimization_scorecard",
                        "workflow_optimization_packet",
                    ],
                    "highest_priority_candidate_ids": [],
                    "recommended_next_action": "Collect more representative trace evidence before attempting optimization.",
                    "requires_ablation_before_promotion": False,
                    "source_mutation_check_expected": True,
                },
            ),
        ],
    )

    result = run_workflow_package(
        "workflow_run_traces_to_optimization_candidates",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="optimizer-task",
            message="Publish an insufficient-evidence optimizer packet.\n",
            workflow_params={
                "selected_workflow": "release_candidate_to_go_no_go",
                "task_title": "Release workflow optimization",
                "run_statuses": ["failed", "awaiting_input", "blocked"],
                "route_tags": ["needs_rework", "needs_replan", "failed", "blocked"],
            },
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    workflow_dir = tmp_path / ".autoloop" / "tasks" / "optimizer-task" / "wf_workflow_run_traces_to_optimization_candidates"
    evidence = json.loads((workflow_dir / "workflow_refinement_evidence.json").read_text(encoding="utf-8"))

    assert result.terminal == "FINISH"
    assert (workflow_dir / "workflow_failure_scenario_seeds.json").exists()
    assert not (workflow_dir / "workflow_failure_scenarios.json").exists()
    assert all(entry["kind"] != "workflow_failure_scenarios" for entry in evidence["evidence_entries"])


def test_bootstrap_rejects_unknown_selected_workflow_before_side_effects(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("autoloop.workflows.workflow_run_traces_to_optimization_candidates")
    typed_params = workflow_pkg.Params(
        selected_workflow="does_not_exist",
        task_title="Release workflow optimization",
        run_statuses=["failed", "awaiting_input", "blocked"],
        route_tags=["needs_rework", "needs_replan", "failed", "blocked"],
    )
    task_folder = tmp_path / ".autoloop" / "tasks" / "optimizer-task"
    workflow_folder = task_folder / "wf_workflow_run_traces_to_optimization_candidates"
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)
    (run_folder / "request.md").write_text("Optimize the selected workflow.\n", encoding="utf-8")
    ctx = Context(
        task_id="optimizer-task",
        run_id="run-1",
        workflow_name="workflow_run_traces_to_optimization_candidates",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=tmp_path / "autoloop" / "workflows" / "workflow_run_traces_to_optimization_candidates",
        state=workflow_pkg.WorkflowRunTracesToOptimizationCandidates.State(),
        session_store=InMemorySessionStore(),
        params=typed_params,
        workflow_params={},
    )

    with pytest.raises(LookupError):
        _invoke_optimizer_python_step(workflow_pkg, "bootstrap", ctx)

    assert not (workflow_folder / "invocation_contract.json").exists()


def test_package_writes_scorecard_refinement_evidence_packet_and_receipt(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)
    _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)
    _write_publishable_package(ctx)

    event = _invoke_optimizer_python_step(workflow_pkg, "publish_optimization_packet", ctx)

    assert event.tag == "optimization_candidates_published"
    assert ctx.state.published is True
    assert (ctx.workflow_folder / "workflow_refinement_evidence.json").exists()
    assert (ctx.workflow_folder / "optimization_publication_receipt.json").exists()
    scorecard = json.loads((ctx.workflow_folder / "workflow_optimization_scorecard.json").read_text(encoding="utf-8"))
    packet = (ctx.workflow_folder / "workflow_optimization_packet.md").read_text(encoding="utf-8")
    assert scorecard["optimization_depth"] == "cheap"
    assert scorecard["ablation_executed"] is False
    assert "## Optimization Depth" in packet
    assert "Target workflow reruns executed: no" in packet
    assert "Ablations executed: no" in packet
    del params


def test_package_fails_if_selected_workflow_source_changed(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)
    _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)
    _write_publishable_package(ctx)

    target_prompt = (
        tmp_path / "autoloop" / "workflows" / "release_candidate_to_go_no_go" / "prompts" / "assessment_producer.md"
    )
    target_prompt.write_text(target_prompt.read_text(encoding="utf-8") + "\nMutation.\n", encoding="utf-8")

    with pytest.raises(ValueError, match="authoritative selected workflow file changed during optimization publication"):
        _invoke_optimizer_python_step(workflow_pkg, "publish_optimization_packet", ctx)
    del params


def test_workflow_never_mutates_selected_workflow_source(tmp_path: Path) -> None:
    _install_repo_optimizer_package(tmp_path)
    selected_workflow_dir = tmp_path / "autoloop" / "workflows" / "release_candidate_to_go_no_go"
    before_snapshot = _snapshot_tree(selected_workflow_dir)

    result, provider, workflow_dir = _run_enabled_candidate_workflow(tmp_path, install_repo=False)
    after_snapshot = _snapshot_tree(selected_workflow_dir)

    assert result.terminal == "FINISH"
    assert "workflow_level" in [call.step_name for call in provider.calls]
    assert (workflow_dir / "selected_workflow_source_manifest.json").exists()
    assert before_snapshot == after_snapshot


def test_package_rejects_candidate_count_mismatch(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)
    _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)
    _write_valid_producer_candidates(ctx)
    _write_publishable_package(
        ctx,
        scorecard_overrides={
            "candidate_counts": {
                "producer": 0,
                "verifier_rubric": 0,
                "token": 0,
                "adversarial_cases": 0,
                "workflow_level": 0,
            },
        },
    )

    with pytest.raises(
        ValueError,
        match="workflow_optimization_scorecard.json candidate_counts.producer must match the validated candidate artifact count",
    ):
        _invoke_optimizer_python_step(workflow_pkg, "publish_optimization_packet", ctx)
    del params


def test_package_rejects_malformed_candidate_artifact(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)
    _invoke_optimizer_python_step(workflow_pkg, "capture_frame_context", ctx)
    _write_publishable_package(ctx)
    (ctx.workflow_folder / "producer_prompt_optimization_candidates.json").write_text(
        json.dumps(
            {
                "schema": "autoloop.workflow_optimization.producer_candidates/v1",
                "selected_workflow": "release_candidate_to_go_no_go",
                "target_steps": ["assessment"],
                "candidates": [
                    {
                        "step_name": "assessment",
                        "target_surface": "producer_prompt",
                        "diagnosis": "Missing required candidate identity.",
                        "proposed_change_summary": "This payload is intentionally malformed for regression coverage.",
                        "confidence": 0.5,
                        "evidence_strength": "medium",
                        "requires_ablation": False,
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        _invoke_optimizer_python_step(workflow_pkg, "publish_optimization_packet", ctx)
    del params


def test_optimization_depth_standard_is_recorded_and_no_reruns_execute(tmp_path: Path) -> None:
    result, provider, workflow_dir = _run_enabled_candidate_workflow(
        tmp_path,
        workflow_params_overrides={"optimization_depth": "standard"},
    )

    scope = json.loads((workflow_dir / "workflow_optimization_scope.json").read_text(encoding="utf-8"))
    scorecard = json.loads((workflow_dir / "workflow_optimization_scorecard.json").read_text(encoding="utf-8"))
    packet = (workflow_dir / "workflow_optimization_packet.md").read_text(encoding="utf-8")
    selected_workflow_runs = list(
        (tmp_path / ".autoloop" / "tasks" / "release-good" / "wf_release_candidate_to_go_no_go" / "runs").iterdir()
    )

    assert result.terminal == "FINISH"
    assert "package" in [call.step_name for call in provider.calls]
    assert scope["optimization_depth"] == "standard"
    assert scorecard["optimization_depth"] == "standard"
    assert scorecard["ablation_executed"] is False
    assert "Requested depth: `standard`" in packet
    assert "Target workflow reruns executed: no" in packet
    assert "Ablations executed: no" in packet
    assert len(selected_workflow_runs) == 1


def test_optimization_depth_ablation_records_planning_mode_without_executing_ablation(tmp_path: Path) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_minimal_run_metadata(tmp_path, "release-old", "release_candidate_to_go_no_go", "run-old", "failed")

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: "frame reviewed\n",
            _produce_noop_package,
        ],
        verifier_turns=[
            Outcome(
                raw_output="no eligible evidence\n",
                tag="no_eligible_trace_evidence",
                payload={
                    "summary": "Historical runs were discovered, but none had the required Plan-1 observability bundle.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "candidate_run_count": 1,
                    "eligible_run_count": 0,
                    "excluded_run_count": 1,
                    "top_k_steps": 1,
                    "route_tags": ["needs_rework", "needs_replan", "failed", "blocked"],
                },
            ),
            Outcome(
                raw_output="optimization packet ready\n",
                tag="optimization_packet_ready",
                payload={
                    "summary": "The no-op scorecard and packet are aligned for deterministic publication.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "authoritative_artifacts": [
                        "workflow_optimization_scorecard",
                        "workflow_optimization_packet",
                    ],
                    "highest_priority_candidate_ids": [],
                    "recommended_next_action": "Collect eligible Plan-1 observability bundles, then rerun the optimizer.",
                    "requires_ablation_before_promotion": False,
                    "source_mutation_check_expected": True,
                },
            ),
        ],
    )

    result = run_workflow_package(
        "workflow_run_traces_to_optimization_candidates",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="optimizer-task",
            message="Publish an ablation-depth optimizer packet without executing ablations.\n",
            workflow_params={
                "selected_workflow": "release_candidate_to_go_no_go",
                "task_title": "Release workflow optimization",
                "optimization_depth": "ablation",
                "run_statuses": ["failed", "awaiting_input", "blocked"],
                "route_tags": ["needs_rework", "needs_replan", "failed", "blocked"],
            },
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    receipt = json.loads(
        (
            tmp_path
            / ".autoloop"
            / "tasks"
            / "optimizer-task"
            / "wf_workflow_run_traces_to_optimization_candidates"
            / "optimization_publication_receipt.json"
        ).read_text(encoding="utf-8")
    )
    workflow_dir = (
        tmp_path
        / ".autoloop"
        / "tasks"
        / "optimizer-task"
        / "wf_workflow_run_traces_to_optimization_candidates"
    )
    scope = json.loads((workflow_dir / "workflow_optimization_scope.json").read_text(encoding="utf-8"))
    scorecard = json.loads((workflow_dir / "workflow_optimization_scorecard.json").read_text(encoding="utf-8"))
    packet = (workflow_dir / "workflow_optimization_packet.md").read_text(encoding="utf-8")
    assert result.terminal == "FINISH"
    assert scope["optimization_depth"] == "ablation"
    assert scorecard["optimization_depth"] == "ablation"
    assert scorecard["ablation_executed"] is False
    assert receipt["optimization_depth"] == "ablation"
    assert "Requested depth: `ablation`" in packet
    assert "Target workflow reruns executed: no" in packet
    assert "Ablations executed: no" in packet
    assert "Ablation mode produced ablation recommendations only. It did not execute ablation runs." in packet
    assert not (
        tmp_path / ".autoloop" / "tasks" / "optimizer-task" / "wf_workflow_optimization_candidates_to_ablation_results"
    ).exists()


def _run_enabled_candidate_workflow(
    tmp_path: Path,
    *,
    install_repo: bool = True,
    workflow_params_overrides: dict[str, object] | None = None,
) -> tuple[object, ScriptedLLMProvider, Path]:
    if install_repo:
        _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: "frame reviewed\n",
            lambda request: "ranking reviewed\n",
            _produce_failure_scenarios,
            _produce_producer_candidates,
            _produce_verifier_rubric_candidates,
            _produce_token_candidates,
            _produce_adversarial_cases,
            _produce_workflow_level_candidates,
            _produce_full_candidate_package,
        ],
        verifier_turns=[
            Outcome(
                raw_output="frame grounded\n",
                tag="optimization_scope_framed",
                payload={
                    "summary": "The selected workflow and trace scope are grounded for candidate generation.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "candidate_run_count": 1,
                    "eligible_run_count": 1,
                    "excluded_run_count": 0,
                    "top_k_steps": 1,
                    "route_tags": ["needs_rework", "needs_replan", "failed", "blocked"],
                },
            ),
            Outcome(
                raw_output="targets ranked\n",
                tag="targets_ranked",
                payload={
                    "summary": "Assessment is the highest-leverage target for local optimization.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "ranked_steps": ["assessment"],
                    "ranking_method": "static_graph_plus_trace_metrics_plus_llm_attribution",
                },
            ),
            Outcome(
                raw_output="failure scenarios mined\n",
                tag="failure_scenarios_mined",
                payload={
                    "summary": "Assessment failures support candidate generation across local optimization surfaces.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "target_steps": ["assessment"],
                    "failure_ids": ["assessment_missing_rollback_evidence"],
                },
            ),
            Outcome(
                raw_output="producer candidates ready\n",
                tag="producer_candidates_ready",
                payload={
                    "summary": "Producer-side optimization candidates are ready for acceptance-function review.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "target_steps": ["assessment"],
                    "candidate_ids": ["producer-assessment-001"],
                },
            ),
            Outcome(
                raw_output="verifier and rubric candidates ready\n",
                tag="verifier_rubric_candidates_ready",
                payload={
                    "summary": "Acceptance-function candidates are ready for token review.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "target_steps": ["assessment"],
                    "candidate_ids": ["verifier-rubric-assessment-001"],
                },
            ),
            Outcome(
                raw_output="token candidates ready\n",
                tag="token_candidates_ready",
                payload={
                    "summary": "Token candidates are ready for adversarial-case generation.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "target_steps": ["assessment"],
                    "candidate_ids": ["token-assessment-001"],
                },
            ),
            Outcome(
                raw_output="adversarial cases ready\n",
                tag="adversarial_cases_ready",
                payload={
                    "summary": "Adversarial-case candidates are ready for workflow-level review.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "case_ids": ["adversarial-missing-rollback-owner"],
                },
            ),
            Outcome(
                raw_output="workflow-level candidates ready\n",
                tag="workflow_level_candidates_ready",
                payload={
                    "summary": "Workflow-level candidates are ready for packaging.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "target_steps": ["assessment", "package"],
                    "candidate_ids": ["workflow-level-001"],
                },
            ),
            Outcome(
                raw_output="optimization packet ready\n",
                tag="optimization_packet_ready",
                payload={
                    "summary": "The candidate artifacts, scorecard, and packet are aligned for publication.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "authoritative_artifacts": [
                        "workflow_optimization_scorecard",
                        "workflow_optimization_packet",
                    ],
                    "highest_priority_candidate_ids": [
                        "verifier-rubric-assessment-001",
                        "producer-assessment-001",
                    ],
                    "recommended_next_action": "Run workflow_and_eval_to_refined_workflow_package with this refinement evidence.",
                    "requires_ablation_before_promotion": True,
                    "source_mutation_check_expected": True,
                },
            ),
        ],
    )

    result = run_workflow_package(
        "workflow_run_traces_to_optimization_candidates",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="optimizer-task",
            message="Publish optimizer candidate artifacts from one eligible run.\n",
            workflow_params={
                "selected_workflow": "release_candidate_to_go_no_go",
                "task_title": "Release workflow optimization",
                "run_statuses": ["failed", "awaiting_input", "blocked"],
                "route_tags": ["needs_rework", "needs_replan", "failed", "blocked"],
            }
            | (workflow_params_overrides or {}),
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )
    workflow_dir = tmp_path / ".autoloop" / "tasks" / "optimizer-task" / "wf_workflow_run_traces_to_optimization_candidates"
    return result, provider, workflow_dir


def _bootstrap_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    route_tags: list[str] | None = None,
    optimization_depth: str = "cheap",
    max_candidates_per_pass: int = 3,
):
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    _clear_workflow_modules()
    workflow_pkg = importlib.import_module("autoloop.workflows.workflow_run_traces_to_optimization_candidates")
    typed_params = workflow_pkg.Params(
        selected_workflow="release_candidate_to_go_no_go",
        task_title="Release workflow optimization",
        run_statuses=["failed", "awaiting_input", "blocked"],
        route_tags=route_tags or ["needs_rework", "needs_replan", "failed", "blocked"],
        optimization_depth=optimization_depth,
        max_candidates_per_pass=max_candidates_per_pass,
    )
    task_folder = tmp_path / ".autoloop" / "tasks" / "optimizer-task"
    workflow_folder = task_folder / "wf_workflow_run_traces_to_optimization_candidates"
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)
    (run_folder / "request.md").write_text("Optimize the selected workflow.\n", encoding="utf-8")
    ctx = Context(
        task_id="optimizer-task",
        run_id="run-1",
        workflow_name="workflow_run_traces_to_optimization_candidates",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=tmp_path / "autoloop" / "workflows" / "workflow_run_traces_to_optimization_candidates",
        state=workflow_pkg.WorkflowRunTracesToOptimizationCandidates.State(),
        session_store=InMemorySessionStore(),
        params=typed_params,
        workflow_params={},
    )
    event = _invoke_optimizer_python_step(workflow_pkg, "bootstrap", ctx)
    assert event.tag == "inputs_prepared"
    return typed_params, ctx.state, ctx, workflow_pkg


def _produce_noop_package(request) -> str:
    corpus = json.loads(request.artifacts.workflow_optimization_trace_corpus.read_text())
    excluded = json.loads(request.artifacts.excluded_run_report.read_text())
    scope = json.loads(request.artifacts.workflow_optimization_scope.read_text())
    request.artifacts.workflow_optimization_scorecard.write_text(
        json.dumps(
            {
                "schema": "autoloop.workflow_optimization.scorecard/v1",
                "selected_workflow": "release_candidate_to_go_no_go",
                "evidence_run_count": corpus["eligible_run_count"],
                "excluded_run_count": excluded["candidate_run_count"] - corpus["eligible_run_count"],
                "target_steps_ranked": 0,
                "failure_scenarios": 0,
                "candidate_counts": {
                    "producer": 0,
                    "verifier_rubric": 0,
                    "token": 0,
                    "adversarial_cases": 0,
                    "workflow_level": 0,
                },
                "optimization_depth": scope["optimization_depth"],
                "ablation_executed": False,
                "recommended_next_action": "Collect eligible Plan-1 observability bundles, then rerun the optimizer.",
                "highest_priority_candidate_ids": [],
                "requires_ablation_before_promotion": False,
                "source_mutation_check": {
                    "passed": True,
                    "details": "Will be rechecked deterministically at publication.",
                },
                "summary": "No eligible Plan-1 observability bundles were available, so no optimization candidates were generated.",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    request.artifacts.workflow_optimization_packet.write_text(
        "\n".join(
            (
                "# Workflow Optimization Packet",
                "",
                "No eligible Plan-1 observability bundles were available.",
                "",
                "- Ready for review: none.",
                "- Requires ablation: none.",
                "- Token-only candidates: none.",
                "- Adversarial eval-case candidates: none.",
                "- Workflow-level refinement candidates: none.",
                "",
                "Recommended next action: collect eligible Plan-1 observability bundles, then rerun the optimizer.",
                "",
            )
        )
    )
    return "packaged noop optimization packet\n"


def _produce_insufficient_evidence_package(request) -> str:
    scope = json.loads(request.artifacts.workflow_optimization_scope.read_text())
    request.artifacts.workflow_optimization_scorecard.write_text(
        json.dumps(
            {
                "schema": "autoloop.workflow_optimization.scorecard/v1",
                "selected_workflow": "release_candidate_to_go_no_go",
                "evidence_run_count": 1,
                "excluded_run_count": 0,
                "target_steps_ranked": 0,
                "failure_scenarios": 0,
                "candidate_counts": {
                    "producer": 0,
                    "verifier_rubric": 0,
                    "token": 0,
                    "adversarial_cases": 0,
                    "workflow_level": 0,
                },
                "optimization_depth": scope["optimization_depth"],
                "ablation_executed": False,
                "recommended_next_action": "Collect more representative trace evidence before attempting optimization.",
                "highest_priority_candidate_ids": [],
                "requires_ablation_before_promotion": False,
                "source_mutation_check": {
                    "passed": True,
                    "details": "Will be rechecked deterministically at publication.",
                },
                "summary": "Trace evidence was too thin for a credible optimization ranking, so candidate generation was not advanced.",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    request.artifacts.workflow_optimization_packet.write_text(
        "\n".join(
            (
                "# Workflow Optimization Packet",
                "",
                "Deterministic ranking evidence was too thin to advance into mined failure scenarios.",
                "",
                "- Ready for review: none.",
                "- Requires ablation: none.",
                "- Token-only candidates: none.",
                "- Adversarial eval-case candidates: none.",
                "- Workflow-level refinement candidates: none.",
                "",
                "Recommended next action: collect more representative trace evidence before attempting optimization.",
                "",
            )
        )
    )
    return "packaged insufficient evidence optimization packet\n"


def _produce_skipped_optional_passes_package(request) -> str:
    scope = json.loads(request.artifacts.workflow_optimization_scope.read_text())
    request.artifacts.workflow_optimization_scorecard.write_text(
        json.dumps(
            {
                "schema": "autoloop.workflow_optimization.scorecard/v1",
                "selected_workflow": "release_candidate_to_go_no_go",
                "evidence_run_count": 1,
                "excluded_run_count": 0,
                "target_steps_ranked": 1,
                "failure_scenarios": 0,
                "candidate_counts": {
                    "producer": 0,
                    "verifier_rubric": 0,
                    "token": 0,
                    "adversarial_cases": 0,
                    "workflow_level": 0,
                },
                "optimization_depth": scope["optimization_depth"],
                "ablation_executed": False,
                "recommended_next_action": "Review the ranked scope before enabling optional candidate passes.",
                "highest_priority_candidate_ids": [],
                "requires_ablation_before_promotion": False,
                "source_mutation_check": {
                    "passed": True,
                    "details": "Will be rechecked deterministically at publication.",
                },
                "summary": "Optional candidate passes were disabled, so publication contains only ranked scope and package artifacts.",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    request.artifacts.workflow_optimization_packet.write_text(
        "\n".join(
            (
                "# Workflow Optimization Packet",
                "",
                "Optional candidate passes were disabled explicitly.",
                "",
                "- Ready for review: none.",
                "- Requires ablation: none.",
                "- Token-only candidates: none.",
                "- Adversarial eval-case candidates: none.",
                "- Workflow-level refinement candidates: none.",
                "",
                "Recommended next action: review the ranked scope before enabling optional candidate passes.",
                "",
            )
        )
    )
    return "packaged skipped-optional-passes optimization packet\n"


def _produce_producer_candidates(request) -> str:
    request.artifacts.producer_prompt_optimization_candidates.write_text(
        json.dumps(
            {
                "schema": "autoloop.workflow_optimization.producer_candidates/v1",
                "selected_workflow": "release_candidate_to_go_no_go",
                "target_steps": ["assessment"],
                "candidates": [
                    {
                        "candidate_id": "producer-assessment-001",
                        "step_name": "assessment",
                        "target_surface": "producer_prompt",
                        "target_path": "autoloop/workflows/release_candidate_to_go_no_go/prompts/assessment_producer.md",
                        "failure_ids_addressed": ["assessment_missing_rollback_evidence"],
                        "diagnosis": "Producer does not separate observed evidence from inference.",
                        "proposed_change_summary": "Add direct evidence and missing-evidence requirements.",
                        "proposed_unified_diff": None,
                        "proposed_patch_instructions": [
                            "Require direct evidence for each release-readiness claim.",
                            "Add a Missing Evidence subsection when claims remain unsupported.",
                        ],
                        "expected_effect": {
                            "verifier_pass_rate": "increase",
                            "false_accepts": "decrease",
                            "token_usage": "slight_increase",
                        },
                        "confidence": 0.72,
                        "evidence_strength": "medium",
                        "risks": ["May make routine cases more verbose."],
                        "requires_ablation": False,
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return "wrote producer optimization candidates\n"


def _produce_failure_scenarios(request) -> str:
    request.artifacts.workflow_failure_scenarios.write_text(
        json.dumps(
            {
                "schema": "autoloop.workflow_optimization.failure_scenarios/v1",
                "selected_workflow": "release_candidate_to_go_no_go",
                "failure_scenarios": [
                    {
                        "failure_id": "assessment_missing_rollback_evidence",
                        "step_name": "assessment",
                        "failure_kind": "producer_failed_verifier",
                        "severity": "medium",
                        "frequency": 2,
                        "evidence_observation_ids": ["release-good/run-good:000003:assessment"],
                        "producer_gap": "Assessment does not reliably separate observed rollback evidence from inference.",
                        "verifier_behavior": "Verifier correctly pushes unsupported rollback claims to needs_rework.",
                        "likely_fix_surfaces": ["producer_prompt", "verifier_rubric"],
                        "downstream_effect": "The workflow loops locally before packaging can proceed cleanly.",
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return "wrote failure scenarios\n"


def _produce_verifier_rubric_candidates(request) -> str:
    request.artifacts.verifier_rubric_optimization_candidates.write_text(
        json.dumps(
            {
                "schema": "autoloop.workflow_optimization.verifier_rubric_candidates/v1",
                "selected_workflow": "release_candidate_to_go_no_go",
                "target_steps": ["assessment"],
                "candidates": [
                    {
                        "candidate_id": "verifier-rubric-assessment-001",
                        "step_name": "assessment",
                        "target_surfaces": ["verifier_prompt", "criteria", "route_contract"],
                        "diagnosis": "Verifier accepts schema-valid sections without enough evidence discipline.",
                        "failure_ids_addressed": ["assessment_false_accept_unsupported_rollback"],
                        "proposed_changes": [
                            {
                                "target_surface": "verifier_prompt",
                                "target_path": "autoloop/workflows/release_candidate_to_go_no_go/prompts/assessment_verifier.md",
                                "change_type": "tighten_acceptance_rule",
                                "summary": "Reject approval when rollback readiness lacks direct evidence.",
                            },
                            {
                                "target_surface": "route_contract",
                                "route": "needs_rework",
                                "summary": "Clarify that evidence gaps require needs_rework rather than local acceptance.",
                            },
                        ],
                        "expected_effect": {
                            "false_accepts": "decrease",
                            "false_rejects": "neutral",
                            "token_usage": "neutral",
                        },
                        "confidence": 0.69,
                        "evidence_strength": "medium",
                        "risks": ["May over-block evidence that is acceptable but implicit."],
                        "requires_ablation": True,
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return "wrote verifier and rubric optimization candidates\n"


def _produce_token_candidates(request) -> str:
    request.artifacts.token_optimization_candidates.write_text(
        json.dumps(
            {
                "schema": "autoloop.workflow_optimization.token_candidates/v1",
                "selected_workflow": "release_candidate_to_go_no_go",
                "candidates": [
                    {
                        "candidate_id": "token-assessment-001",
                        "step_name": "assessment",
                        "target_surface": "producer_prompt",
                        "target_path": "autoloop/workflows/release_candidate_to_go_no_go/prompts/assessment_producer.md",
                        "compression_kind": "remove_duplicate_static_guidance",
                        "risk_class": "safe_compression",
                        "estimated_input_token_reduction": 650,
                        "diagnosis": "Prompt repeats artifact handling guidance already captured elsewhere.",
                        "proposed_change_summary": "Replace repeated checklist text with one compact contract reference.",
                        "quality_risk": "low",
                        "confidence": 0.78,
                        "evidence_strength": "medium",
                        "requires_ablation": False,
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return "wrote token optimization candidates\n"


def _produce_adversarial_cases(request) -> str:
    request.artifacts.adversarial_case_candidates.write_text(
        json.dumps(
            {
                "schema": "autoloop.workflow_optimization.adversarial_case_candidates/v1",
                "selected_workflow": "release_candidate_to_go_no_go",
                "cases": [
                    {
                        "case_id": "adversarial-missing-rollback-owner",
                        "case_kind": "adversarial",
                        "attack_vector": "Evidence implies rollback confidence but omits rollback owner.",
                        "prompt": "Assess this release with notes that imply rollback readiness but omit rollback ownership evidence.",
                        "source_failure_ids": ["assessment_missing_rollback_evidence"],
                        "expected_stress": "Verifier should reject unsupported rollback readiness.",
                        "expected_route": "needs_rework",
                        "expected_artifacts": ["release_risk_assessment", "blocking_issues"],
                        "recommended_for_eval_suite": True,
                        "confidence": 0.74,
                        "evidence_strength": "medium",
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return "wrote adversarial-case candidates\n"


def _produce_workflow_level_candidates(request) -> str:
    request.artifacts.workflow_level_optimization_candidates.write_text(
        json.dumps(
            {
                "schema": "autoloop.workflow_optimization.workflow_level_candidates/v1",
                "selected_workflow": "release_candidate_to_go_no_go",
                "candidates": [
                    {
                        "candidate_id": "workflow-level-001",
                        "candidate_kind": "artifact_handoff_change",
                        "diagnosis": "Assessment and package prompts duplicate release decision criteria, creating drift.",
                        "affected_steps": ["assessment", "package"],
                        "proposed_change_summary": "Move shared release evidence obligations into one artifact contract.",
                        "proposed_surfaces": ["workflow_code", "prompt_readme", "package_prompt"],
                        "confidence": 0.61,
                        "evidence_strength": "low",
                        "risks": ["Requires workflow-level refactor, not prompt-only patch."],
                        "requires_refinement_workflow": True,
                        "requires_ablation": True,
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return "wrote workflow-level optimization candidates\n"


def _produce_full_candidate_package(request) -> str:
    scope = json.loads(request.artifacts.workflow_optimization_scope.read_text())
    request.artifacts.workflow_optimization_scorecard.write_text(
        json.dumps(
            {
                "schema": "autoloop.workflow_optimization.scorecard/v1",
                "selected_workflow": "release_candidate_to_go_no_go",
                "evidence_run_count": 1,
                "excluded_run_count": 0,
                "target_steps_ranked": 1,
                "failure_scenarios": 1,
                "candidate_counts": {
                    "producer": 1,
                    "verifier_rubric": 1,
                    "token": 1,
                    "adversarial_cases": 1,
                    "workflow_level": 1,
                },
                "optimization_depth": scope["optimization_depth"],
                "ablation_executed": False,
                "recommended_next_action": "Run workflow_and_eval_to_refined_workflow_package with this refinement evidence.",
                "highest_priority_candidate_ids": [
                    "verifier-rubric-assessment-001",
                    "producer-assessment-001",
                ],
                "requires_ablation_before_promotion": True,
                "source_mutation_check": {
                    "passed": True,
                    "details": "Will be rechecked deterministically at publication.",
                },
                "summary": "Assessment remains the highest-leverage local optimization target.",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    request.artifacts.workflow_optimization_packet.write_text(
        "\n".join(
            (
                "# Workflow Optimization Packet",
                "",
                "Candidate-only optimization evidence is ready for review.",
                "",
                "- Ready for review: producer-assessment-001, verifier-rubric-assessment-001, token-assessment-001, adversarial-missing-rollback-owner, workflow-level-001.",
                "- Requires ablation: verifier-rubric-assessment-001, workflow-level-001.",
                "- Token-only candidates: token-assessment-001.",
                "- Adversarial eval-case candidates: adversarial-missing-rollback-owner.",
                "- Workflow-level refinement candidates: workflow-level-001.",
                "",
                "Recommended next action: run workflow_and_eval_to_refined_workflow_package with this refinement evidence.",
                "",
            )
        )
    )
    return "packaged full optimization candidate set\n"


def _write_publishable_package(
    ctx: Context,
    *,
    scorecard_overrides: dict[str, object] | None = None,
    optimization_depth: str = "cheap",
) -> None:
    payload: dict[str, object] = {
        "schema": "autoloop.workflow_optimization.scorecard/v1",
        "selected_workflow": "release_candidate_to_go_no_go",
        "evidence_run_count": 1,
        "excluded_run_count": 0,
        "target_steps_ranked": 1,
        "failure_scenarios": 1,
        "candidate_counts": {
            "producer": 0,
            "verifier_rubric": 0,
            "token": 0,
            "adversarial_cases": 0,
            "workflow_level": 0,
        },
        "optimization_depth": optimization_depth,
        "ablation_executed": False,
        "recommended_next_action": "Run workflow_and_eval_to_refined_workflow_package with this refinement evidence.",
        "highest_priority_candidate_ids": [],
        "requires_ablation_before_promotion": False,
        "source_mutation_check": {
            "passed": True,
            "details": "Will be rechecked deterministically at publication.",
        },
        "summary": "Assessment remains the highest-leverage local optimization target.",
    }
    if scorecard_overrides:
        payload.update(scorecard_overrides)
    (ctx.workflow_folder / "workflow_optimization_scorecard.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (ctx.workflow_folder / "workflow_optimization_packet.md").write_text(
        "\n".join(
            (
                "# Workflow Optimization Packet",
                "",
                "Candidate-only optimization evidence is ready for review.",
                "",
                "- Ready for review: none.",
                "- Requires ablation: none.",
                "- Token-only candidates: none.",
                "- Adversarial eval-case candidates: none.",
                "- Workflow-level refinement candidates: none.",
                "",
                "Recommended next action: run workflow_and_eval_to_refined_workflow_package with this refinement evidence.",
                "",
            )
        ),
        encoding="utf-8",
    )


def _write_valid_producer_candidates(ctx: Context) -> None:
    (ctx.workflow_folder / "producer_prompt_optimization_candidates.json").write_text(
        json.dumps(
            {
                "schema": "autoloop.workflow_optimization.producer_candidates/v1",
                "selected_workflow": "release_candidate_to_go_no_go",
                "target_steps": ["assessment"],
                "candidates": [
                    {
                        "candidate_id": "producer-assessment-001",
                        "step_name": "assessment",
                        "target_surface": "producer_prompt",
                        "target_path": "autoloop/workflows/release_candidate_to_go_no_go/prompts/assessment_producer.md",
                        "failure_ids_addressed": ["assessment_missing_rollback_evidence"],
                        "diagnosis": "Producer does not separate observed evidence from inference.",
                        "proposed_change_summary": "Add an explicit evidence-versus-inference split.",
                        "proposed_unified_diff": None,
                        "proposed_patch_instructions": [
                            "Add a Missing Evidence section for unsupported claims.",
                        ],
                        "expected_effect": {
                            "verifier_pass_rate": "increase",
                            "false_accepts": "decrease",
                        },
                        "confidence": 0.72,
                        "evidence_strength": "medium",
                        "risks": ["May add verbosity in routine cases."],
                        "requires_ablation": False,
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _snapshot_tree(root: Path) -> dict[str, tuple[str, int]]:
    snapshot: dict[str, tuple[str, int]] = {}
    for path in sorted(file_path for file_path in root.rglob("*") if file_path.is_file()):
        payload = path.read_bytes()
        snapshot[path.relative_to(root).as_posix()] = (hashlib.sha256(payload).hexdigest(), len(payload))
    return snapshot


class _JsonHandle:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read_json(self) -> dict[str, object]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def write_json(self, payload: dict[str, object]) -> None:
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _install_repo_optimizer_package(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    _clear_workflow_modules()
    importlib.invalidate_caches()

    for package_name in (
        "workflow_run_traces_to_optimization_candidates",
        "release_candidate_to_go_no_go",
    ):
        shutil.copytree(
            REPO_ROOT / "autoloop" / "workflows" / package_name,
            workflows_root / package_name,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    shutil.copytree(
        REPO_ROOT / "docs",
        root / "docs",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (root / "Workflow_Instructions.md").write_text(
        (REPO_ROOT / "Workflow_Instructions.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


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

    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "000003_assessment_producer.txt").write_text("producer output\n", encoding="utf-8")
    (raw_dir / "000003_assessment_verifier.txt").write_text("verifier output\n", encoding="utf-8")
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
                        "sha256": "unused",
                        "bytes": 16,
                    },
                    "verifier": {
                        "path": "raw/000003_assessment_verifier.txt",
                        "sha256": "unused",
                        "bytes": 16,
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


def _write_upstream_pass_downstream_fail_run(root: Path, task_id: str, workflow_name: str, run_id: str) -> Path:
    run_dir = _write_minimal_run_metadata(root, task_id, workflow_name, run_id, "failed")
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    run_payload["terminal"] = "FAIL"
    run_payload["git_tracking"] = {
        "commit_before_run": "commit-before-run",
        "commit_after_run": "commit-after-run",
    }
    (run_dir / "run.json").write_text(json.dumps(run_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "000001_assessment_producer.txt").write_text("assessment producer\n", encoding="utf-8")
    (raw_dir / "000002_package_producer.txt").write_text("package producer\n", encoding="utf-8")
    (run_dir / "trace.jsonl").write_text(
        "\n".join(
            (
                json.dumps(
                    {
                        "schema": "autoloop.runtime_trace/v1",
                        "event_type": "step_finished",
                        "sequence": 1,
                        "step_name": "assessment",
                        "step_kind": "pair",
                        "event": {"tag": "assessment_complete"},
                        "outcome": {"tag": "assessment_complete"},
                        "provider_usage": {
                            "producer": {
                                "input_tokens": 200,
                                "output_tokens": 40,
                                "total_tokens": 240,
                                "source": "provider",
                            }
                        },
                        "raw_output_refs": {
                            "producer": {
                                "path": "raw/000001_assessment_producer.txt",
                                "sha256": "unused",
                                "bytes": 18,
                            }
                        },
                    }
                ),
                json.dumps(
                    {
                        "schema": "autoloop.runtime_trace/v1",
                        "event_type": "step_finished",
                        "sequence": 2,
                        "step_name": "package",
                        "step_kind": "pair",
                        "event": {"tag": "failed"},
                        "outcome": {"tag": "failed"},
                        "provider_usage": {
                            "producer": {
                                "input_tokens": 40,
                                "output_tokens": 10,
                                "total_tokens": 50,
                                "source": "provider",
                            }
                        },
                        "raw_output_refs": {
                            "producer": {
                                "path": "raw/000002_package_producer.txt",
                                "sha256": "unused",
                                "bytes": 16,
                            }
                        },
                    }
                ),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "git_tracking.jsonl").write_text(
        "\n".join(
            (
                json.dumps(
                    {
                        "schema": "autoloop.git_tracking/v1",
                        "event_type": "step_committed",
                        "sequence": 1,
                        "step_name": "assessment",
                        "commit_before_step": "commit-before-assessment",
                        "commit_after_step": "commit-after-assessment",
                    }
                ),
                json.dumps(
                    {
                        "schema": "autoloop.git_tracking/v1",
                        "event_type": "step_committed",
                        "sequence": 2,
                        "step_name": "package",
                        "commit_before_step": "commit-before-package",
                        "commit_after_step": "commit-after-package",
                    }
                ),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "static_step_graph.json").write_text(
        json.dumps(
            {
                "schema": "autoloop.workflow_static_step_graph/v1",
                "workflow_name": workflow_name,
                "steps": [
                    {"name": "assessment", "kind": "pair"},
                    {"name": "package", "kind": "pair"},
                ],
                "transitions": {
                    "steps": {
                        "assessment": {"assessment_complete": "package"},
                        "package": {"failed": "FAIL"},
                    },
                    "global": {},
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_dir
