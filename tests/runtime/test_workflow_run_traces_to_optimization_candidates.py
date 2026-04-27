from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from autoloop_v3.core.compiler import compile_workflow
from autoloop_v3.core.context import Context
from autoloop_v3.core.providers.fake import ScriptedLLMProvider
from autoloop_v3.core.stores import InMemorySessionStore
from autoloop_v3.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from autoloop_v3.runtime.loader import discover_workflow_packages, resolve_workflow_reference
from autoloop_v3.runtime.runner import RunnerOptions, run_workflow_package
from workflow.primitives import Outcome


REPO_ROOT = Path(__file__).resolve().parents[2]


def _clear_workflow_modules() -> None:
    for name in list(sys.modules):
        if name == "workflows" or name.startswith("workflows."):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_workflow_modules():
    _clear_workflow_modules()
    yield
    _clear_workflow_modules()


def test_workflow_is_registered_and_describable() -> None:
    discovered = {package.workflow_name: package for package in discover_workflow_packages(REPO_ROOT)}

    assert "workflow_run_traces_to_optimization_candidates" in discovered
    package = discovered["workflow_run_traces_to_optimization_candidates"]
    assert package.package_name == "workflow_run_traces_to_optimization_candidates"
    assert "workflow-optimization-candidates" in package.aliases
    assert package.manifest_path == (
        REPO_ROOT / "workflows" / "workflow_run_traces_to_optimization_candidates" / "workflow.toml"
    )


def test_workflow_describe_lists_parameters_and_pairs(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_run_traces_to_optimization_candidates")
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
        "optimize_tokens",
        "adversarial_cases",
        "workflow_level",
        "package",
        "publish_optimization_packet",
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
    assert frame_step.route_contracts["no_eligible_trace_evidence"]["required_artifacts"] == [
        "selected_workflow_capability",
        "selected_workflow_authoring_surface",
        "selected_workflow_decomposition_surface",
        "selected_workflow_source_manifest",
        "workflow_optimization_scope",
        "workflow_optimization_trace_corpus",
        "excluded_run_report",
    ]
    package_step = compiled.steps["package"]
    assert package_step.route_contracts["optimization_packet_ready"]["required_artifacts"] == [
        "workflow_optimization_scorecard",
        "workflow_optimization_packet",
    ]


def test_capture_frame_context_excludes_old_runs_missing_plan1_observability(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_minimal_run_metadata(tmp_path, "release-old", "release_candidate_to_go_no_go", "run-old", "failed")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)

    next_state, event = workflow_pkg.WorkflowRunTracesToOptimizationCandidates.on_capture_frame_context(state, ctx)

    assert event.tag == "frame_context_captured"
    assert next_state.candidate_run_count == 1
    assert next_state.eligible_run_count == 0
    assert next_state.excluded_run_count == 1
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

    next_state, event = workflow_pkg.WorkflowRunTracesToOptimizationCandidates.on_capture_frame_context(state, ctx)

    assert event.tag == "frame_context_captured"
    assert next_state.candidate_run_count == 2
    assert next_state.eligible_run_count == 1
    assert next_state.excluded_run_count == 1
    corpus = json.loads((ctx.workflow_folder / "workflow_optimization_trace_corpus.json").read_text(encoding="utf-8"))
    assert corpus["runs"][0]["run_ref"] == "release-good/run-good"
    assert corpus["step_observations"][0]["raw_output_refs"]["producer"] == "raw/000003_assessment_producer.txt"
    assert corpus["step_observations"][0]["commit_after_step"] == "commit-after-step"
    del params


def test_rank_targets_writes_priority_report(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)

    workflow_pkg.WorkflowRunTracesToOptimizationCandidates.on_capture_frame_context(state, ctx)

    metrics = json.loads((ctx.workflow_folder / "step_trace_metrics.json").read_text(encoding="utf-8"))
    report = json.loads((ctx.workflow_folder / "step_optimization_priority_report.json").read_text(encoding="utf-8"))

    assert metrics["schema"] == "autoloop.workflow_optimization.step_trace_metrics/v1"
    assert metrics["steps"][0]["step_name"] == "assessment"
    assert report["schema"] == "autoloop.workflow_optimization.step_priority_report/v1"
    assert report["ranked_steps"][0]["step_name"] == "assessment"
    del params


def test_mine_failures_writes_failure_scenarios(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    _write_observable_run(tmp_path, "release-good", "release_candidate_to_go_no_go", "run-good")
    params, state, ctx, workflow_pkg = _bootstrap_context(tmp_path, monkeypatch)
    state, _ = workflow_pkg.WorkflowRunTracesToOptimizationCandidates.on_capture_frame_context(state, ctx)

    artifacts = SimpleNamespace(
        workflow_optimization_internal_trace_corpus=_JsonHandle(
            ctx.workflow_folder / "_workflow_optimization_internal_trace_corpus.json"
        ),
        workflow_optimization_trace_corpus=_JsonHandle(ctx.workflow_folder / "workflow_optimization_trace_corpus.json"),
        step_optimization_priority_report=_JsonHandle(ctx.workflow_folder / "step_optimization_priority_report.json"),
        workflow_failure_scenarios=_JsonHandle(ctx.workflow_folder / "workflow_failure_scenarios.json"),
    )
    next_state = workflow_pkg.WorkflowRunTracesToOptimizationCandidates.on_mine_failures(
        state,
        Outcome(
            raw_output="failure scenarios grounded\n",
            tag="failure_scenarios_mined",
            payload={
                "summary": "Failure scenarios were mined from the ranked target set.",
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "target_steps": ["assessment"],
                "failure_ids": ["assessment_producer_failed_verifier"],
            },
        ),
        artifacts,
    )

    payload = json.loads((ctx.workflow_folder / "workflow_failure_scenarios.json").read_text(encoding="utf-8"))
    assert next_state.failure_status == "failure_scenarios_mined"
    assert payload["schema"] == "autoloop.workflow_optimization.failure_scenarios/v1"
    assert payload["failure_scenarios"][0]["step_name"] == "assessment"
    assert payload["failure_scenarios"][0]["failure_kind"] in {
        "producer_failed_verifier",
        "token_bloat",
        "downstream_failure_after_local_pass",
    }
    del params


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
                "run_statuses": ["failed", "paused", "blocked"],
                "route_tags": ["needs_rework", "needs_replan", "failed", "blocked"],
            },
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    workflow_dir = tmp_path / ".autoloop" / "tasks" / "optimizer-task" / "wf_workflow_run_traces_to_optimization_candidates"
    assert result.terminal == "SUCCESS"
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
                "run_statuses": ["failed", "paused", "blocked"],
                "route_tags": ["needs_rework", "needs_replan", "failed", "blocked"],
            },
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    workflow_dir = tmp_path / ".autoloop" / "tasks" / "optimizer-task" / "wf_workflow_run_traces_to_optimization_candidates"
    evidence = json.loads((workflow_dir / "workflow_refinement_evidence.json").read_text(encoding="utf-8"))

    assert result.terminal == "SUCCESS"
    assert (workflow_dir / "workflow_failure_scenarios.json").exists()
    assert all(entry["kind"] != "workflow_failure_scenarios" for entry in evidence["evidence_entries"])


def test_bootstrap_rejects_unknown_selected_workflow_before_side_effects(tmp_path: Path, monkeypatch) -> None:
    _install_repo_optimizer_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_run_traces_to_optimization_candidates")
    typed_params = workflow_pkg.Parameters(
        selected_workflow="does_not_exist",
        task_title="Release workflow optimization",
        run_statuses=["failed", "paused", "blocked"],
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
        package_folder=tmp_path / "workflows" / "workflow_run_traces_to_optimization_candidates",
        state=workflow_pkg.WorkflowRunTracesToOptimizationCandidates.State(),
        session_store=InMemorySessionStore(),
        params=typed_params,
        workflow_params={},
    )

    with pytest.raises(LookupError):
        workflow_pkg.WorkflowRunTracesToOptimizationCandidates.on_bootstrap(
            workflow_pkg.WorkflowRunTracesToOptimizationCandidates.State(),
            ctx,
        )

    assert not (workflow_folder / "invocation_contract.json").exists()


def _bootstrap_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    _clear_workflow_modules()
    workflow_pkg = importlib.import_module("workflows.workflow_run_traces_to_optimization_candidates")
    typed_params = workflow_pkg.Parameters(
        selected_workflow="release_candidate_to_go_no_go",
        task_title="Release workflow optimization",
        run_statuses=["failed", "paused", "blocked"],
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
        package_folder=tmp_path / "workflows" / "workflow_run_traces_to_optimization_candidates",
        state=workflow_pkg.WorkflowRunTracesToOptimizationCandidates.State(),
        session_store=InMemorySessionStore(),
        params=typed_params,
        workflow_params={},
    )
    state, event = workflow_pkg.WorkflowRunTracesToOptimizationCandidates.on_bootstrap(
        workflow_pkg.WorkflowRunTracesToOptimizationCandidates.State(),
        ctx,
    )
    assert event.tag == "inputs_prepared"
    return typed_params, state, ctx, workflow_pkg


def _produce_noop_package(request) -> str:
    corpus = json.loads(request.artifacts.workflow_optimization_trace_corpus.read_text())
    excluded = json.loads(request.artifacts.excluded_run_report.read_text())
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
            REPO_ROOT / "workflows" / package_name,
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
