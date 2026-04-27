"""Optimization-candidate workflow shell built on runtime-owned run observability."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

try:  # pragma: no branch - supports both package and direct repo-root imports
    from autoloop_v3.stdlib import (
        open_workflow_sessions,
        read_json_object,
        read_required_text,
        require_existing_artifact_paths,
        require_mapping,
        require_non_empty_string,
        validate_no_hidden_execution_signal,
        validate_selected_workflow_artifact_alignment,
        validate_selected_workflow_authoring_surface_snapshot,
        validate_selected_workflow_capability_snapshot,
        validate_selected_workflow_decomposition_surface_snapshot,
        write_invocation_contract,
        write_publication_receipt,
        write_selected_workflow_authoring_surface,
        write_selected_workflow_capability_snapshot,
        write_selected_workflow_decomposition_surface,
        write_workflow_json,
    )
    from autoloop_v3.stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from autoloop_v3.stdlib.optimization import (
        EXCLUDED_RUN_REPORT_SCHEMA,
        TRACE_CORPUS_SCHEMA,
        list_selected_workflow_runs,
        normalize_trace_corpus,
        validate_selected_workflow_source_unchanged,
        write_optimization_refinement_evidence,
        write_selected_workflow_source_manifest,
    )
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from stdlib import (
        open_workflow_sessions,
        read_json_object,
        read_required_text,
        require_existing_artifact_paths,
        require_mapping,
        require_non_empty_string,
        validate_no_hidden_execution_signal,
        validate_selected_workflow_artifact_alignment,
        validate_selected_workflow_authoring_surface_snapshot,
        validate_selected_workflow_capability_snapshot,
        validate_selected_workflow_decomposition_surface_snapshot,
        write_invocation_contract,
        write_publication_receipt,
        write_selected_workflow_authoring_surface,
        write_selected_workflow_capability_snapshot,
        write_selected_workflow_decomposition_surface,
        write_workflow_json,
    )
    from stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from stdlib.optimization import (
        EXCLUDED_RUN_REPORT_SCHEMA,
        TRACE_CORPUS_SCHEMA,
        list_selected_workflow_runs,
        normalize_trace_corpus,
        validate_selected_workflow_source_unchanged,
        write_optimization_refinement_evidence,
        write_selected_workflow_source_manifest,
    )

from workflow import Artifact, FAIL, PairStep, Session, SUCCESS, SystemStep, Workflow
from workflow.primitives import Event, Outcome

from .contracts import (
    ADVERSARIAL_CASES_ROUTE_CONTRACTS,
    AdversarialCasesPayload,
    CandidatePassPayload,
    EXCLUDED_RUN_REPORT_ARTIFACT,
    FRAME_ROUTE_CONTRACTS,
    FrameOptimizationPayload,
    MINE_FAILURES_ROUTE_CONTRACTS,
    FailureScenarioPayload,
    OPTIMIZE_PRODUCER_ROUTE_CONTRACTS,
    OPTIMIZE_TOKENS_ROUTE_CONTRACTS,
    OPTIMIZE_VERIFIER_RUBRIC_ROUTE_CONTRACTS,
    OptimizationPackagePayload,
    PACKAGE_ROUTE_CONTRACTS,
    RANK_TARGETS_ROUTE_CONTRACTS,
    SELECTED_WORKFLOW_SOURCE_MANIFEST_ARTIFACT,
    WORKFLOW_LEVEL_ROUTE_CONTRACTS,
    WORKFLOW_OPTIMIZATION_SCOPE_ARTIFACT,
    WORKFLOW_OPTIMIZATION_SCORECARD_ARTIFACT,
    WORKFLOW_OPTIMIZATION_TRACE_CORPUS_ARTIFACT,
    RankTargetsPayload,
)


_FRAME_ARTIFACT_NAMES = (
    "selected_workflow_capability",
    "selected_workflow_authoring_surface",
    "selected_workflow_decomposition_surface",
    "selected_workflow_source_manifest",
    "workflow_optimization_scope",
    "workflow_optimization_trace_corpus",
    "excluded_run_report",
)
_PACKAGE_EVIDENCE_FILES = {
    "step_optimization_priority_report.json": "step_optimization_priority_report",
    "workflow_failure_scenarios.json": "workflow_failure_scenarios",
    "producer_prompt_optimization_candidates.json": "producer_prompt_optimization_candidates",
    "verifier_rubric_optimization_candidates.json": "verifier_rubric_optimization_candidates",
    "token_optimization_candidates.json": "token_optimization_candidates",
    "adversarial_case_candidates.json": "adversarial_case_candidates",
    "workflow_level_optimization_candidates.json": "workflow_level_optimization_candidates",
    "workflow_optimization_scorecard.json": "workflow_optimization_scorecard",
}


class WorkflowRunTracesToOptimizationCandidates(Workflow):
    """Turn one selected workflow's runtime traces into candidate-only optimization evidence."""

    name = "workflow_run_traces_to_optimization_candidates"

    class State(BaseModel):
        selected_workflow_reference: str = ""
        selected_workflow_name: str | None = None
        task_title: str = ""
        run_refs: list[str] = Field(default_factory=list)
        run_statuses: list[str] = Field(default_factory=list)
        route_tags: list[str] = Field(default_factory=list)
        history_limit: int = 25
        top_k_steps: int = 1
        optimization_depth: str = "cheap"
        include_adversarial_generation: bool = True
        include_token_optimization: bool = True
        include_workflow_level_candidates: bool = True
        max_failure_scenarios: int = 25
        max_candidates_per_pass: int = 3
        focus: str | None = None
        sponsor_role: str | None = None
        desired_outcome: str | None = None
        constraints: list[str] = Field(default_factory=list)
        frame_status: str | None = None
        ranking_status: str | None = None
        failure_status: str | None = None
        producer_status: str | None = None
        verifier_rubric_status: str | None = None
        token_status: str | None = None
        adversarial_status: str | None = None
        workflow_level_status: str | None = None
        packaging_status: str | None = None
        candidate_run_count: int = 0
        eligible_run_count: int = 0
        excluded_run_count: int = 0
        no_eligible_trace_evidence: bool = False
        published: bool = False

    frame_session = Session()
    rank_targets_session = Session()
    mine_failures_session = Session()
    optimize_producer_session = Session()
    optimize_verifier_rubric_session = Session()
    optimize_tokens_session = Session()
    adversarial_cases_session = Session()
    workflow_level_session = Session()
    package_session = Session()

    request = Artifact("{run_folder}/request.md")
    framework_architecture_doc = Artifact("{package_folder}/../../docs/architecture.md")
    framework_authoring_doc = Artifact("{package_folder}/../../docs/authoring.md")
    workflow_instructions = Artifact("{package_folder}/../../Workflow_Instructions.md")
    optimization_package_checklist = Artifact("{package_folder}/assets/optimization_package_checklist.md")

    invocation_contract = Artifact("{workflow_folder}/invocation_contract.json")
    selected_workflow_capability = Artifact("{workflow_folder}/selected_workflow_capability.json")
    selected_workflow_authoring_surface = Artifact("{workflow_folder}/selected_workflow_authoring_surface.json")
    selected_workflow_decomposition_surface = Artifact("{workflow_folder}/selected_workflow_decomposition_surface.json")
    selected_workflow_source_manifest = Artifact("{workflow_folder}/selected_workflow_source_manifest.json")
    workflow_optimization_scope = Artifact("{workflow_folder}/workflow_optimization_scope.json")
    excluded_run_report = Artifact("{workflow_folder}/excluded_run_report.json")
    workflow_optimization_trace_corpus = Artifact("{workflow_folder}/workflow_optimization_trace_corpus.json")
    step_trace_metrics = Artifact("{workflow_folder}/step_trace_metrics.json")
    step_optimization_priority_report = Artifact("{workflow_folder}/step_optimization_priority_report.json")
    workflow_failure_scenarios = Artifact("{workflow_folder}/workflow_failure_scenarios.json")
    producer_prompt_optimization_candidates = Artifact(
        "{workflow_folder}/producer_prompt_optimization_candidates.json"
    )
    verifier_rubric_optimization_candidates = Artifact(
        "{workflow_folder}/verifier_rubric_optimization_candidates.json"
    )
    token_optimization_candidates = Artifact("{workflow_folder}/token_optimization_candidates.json")
    adversarial_case_candidates = Artifact("{workflow_folder}/adversarial_case_candidates.json")
    workflow_level_optimization_candidates = Artifact(
        "{workflow_folder}/workflow_level_optimization_candidates.json"
    )
    workflow_optimization_scorecard = Artifact("{workflow_folder}/workflow_optimization_scorecard.json")
    workflow_refinement_evidence = Artifact("{workflow_folder}/workflow_refinement_evidence.json")
    workflow_optimization_packet = Artifact("{workflow_folder}/workflow_optimization_packet.md")
    optimization_publication_receipt = Artifact("{workflow_folder}/optimization_publication_receipt.json")

    bootstrap = SystemStep(
        name="bootstrap",
        requires=[request],
        produces={"invocation_contract": invocation_contract},
    )
    capture_frame_context = SystemStep(
        name="capture_frame_context",
        requires=[request, invocation_contract],
        produces={
            "selected_workflow_capability": selected_workflow_capability,
            "selected_workflow_authoring_surface": selected_workflow_authoring_surface,
            "selected_workflow_decomposition_surface": selected_workflow_decomposition_surface,
            "selected_workflow_source_manifest": selected_workflow_source_manifest,
            "workflow_optimization_scope": workflow_optimization_scope,
            "workflow_optimization_trace_corpus": workflow_optimization_trace_corpus,
            "excluded_run_report": excluded_run_report,
        },
    )
    frame = PairStep(
        name="frame",
        session=frame_session,
        producer="prompts/frame_producer.md",
        verifier="prompts/frame_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            selected_workflow_authoring_surface,
            selected_workflow_decomposition_surface,
            selected_workflow_source_manifest,
            workflow_optimization_scope,
            workflow_optimization_trace_corpus,
            excluded_run_report,
            framework_architecture_doc,
            framework_authoring_doc,
            workflow_instructions,
        ],
        produces={
            "selected_workflow_capability": selected_workflow_capability,
            "selected_workflow_authoring_surface": selected_workflow_authoring_surface,
            "selected_workflow_decomposition_surface": selected_workflow_decomposition_surface,
            "selected_workflow_source_manifest": selected_workflow_source_manifest,
            "workflow_optimization_scope": workflow_optimization_scope,
            "workflow_optimization_trace_corpus": workflow_optimization_trace_corpus,
            "excluded_run_report": excluded_run_report,
        },
        expected_output_schema=FrameOptimizationPayload,
        route_contracts=FRAME_ROUTE_CONTRACTS,
    )
    rank_targets = PairStep(
        name="rank_targets",
        session=rank_targets_session,
        producer="prompts/rank_targets_producer.md",
        verifier="prompts/rank_targets_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            selected_workflow_authoring_surface,
            selected_workflow_decomposition_surface,
            workflow_optimization_scope,
            workflow_optimization_trace_corpus,
        ],
        produces={
            "step_trace_metrics": step_trace_metrics,
            "step_optimization_priority_report": step_optimization_priority_report,
        },
        expected_output_schema=RankTargetsPayload,
        route_contracts=RANK_TARGETS_ROUTE_CONTRACTS,
    )
    mine_failures = PairStep(
        name="mine_failures",
        session=mine_failures_session,
        producer="prompts/mine_failures_producer.md",
        verifier="prompts/mine_failures_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_authoring_surface,
            workflow_optimization_trace_corpus,
            step_optimization_priority_report,
        ],
        produces={"workflow_failure_scenarios": workflow_failure_scenarios},
        expected_output_schema=FailureScenarioPayload,
        route_contracts=MINE_FAILURES_ROUTE_CONTRACTS,
    )
    optimize_producer = PairStep(
        name="optimize_producer",
        session=optimize_producer_session,
        producer="prompts/optimize_producer_producer.md",
        verifier="prompts/optimize_producer_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_authoring_surface,
            workflow_failure_scenarios,
            step_optimization_priority_report,
        ],
        produces={
            "producer_prompt_optimization_candidates": producer_prompt_optimization_candidates,
        },
        expected_output_schema=CandidatePassPayload,
        route_contracts=OPTIMIZE_PRODUCER_ROUTE_CONTRACTS,
    )
    optimize_verifier_rubric = PairStep(
        name="optimize_verifier_rubric",
        session=optimize_verifier_rubric_session,
        producer="prompts/optimize_verifier_rubric_producer.md",
        verifier="prompts/optimize_verifier_rubric_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_authoring_surface,
            workflow_failure_scenarios,
            step_optimization_priority_report,
        ],
        produces={
            "verifier_rubric_optimization_candidates": verifier_rubric_optimization_candidates,
        },
        expected_output_schema=CandidatePassPayload,
        route_contracts=OPTIMIZE_VERIFIER_RUBRIC_ROUTE_CONTRACTS,
    )
    optimize_tokens = PairStep(
        name="optimize_tokens",
        session=optimize_tokens_session,
        producer="prompts/optimize_tokens_producer.md",
        verifier="prompts/optimize_tokens_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_authoring_surface,
            workflow_optimization_trace_corpus,
            step_optimization_priority_report,
        ],
        produces={"token_optimization_candidates": token_optimization_candidates},
        expected_output_schema=CandidatePassPayload,
        route_contracts=OPTIMIZE_TOKENS_ROUTE_CONTRACTS,
    )
    adversarial_cases = PairStep(
        name="adversarial_cases",
        session=adversarial_cases_session,
        producer="prompts/adversarial_cases_producer.md",
        verifier="prompts/adversarial_cases_verifier.md",
        requires=[
            request,
            invocation_contract,
            workflow_failure_scenarios,
            step_optimization_priority_report,
        ],
        produces={"adversarial_case_candidates": adversarial_case_candidates},
        expected_output_schema=AdversarialCasesPayload,
        route_contracts=ADVERSARIAL_CASES_ROUTE_CONTRACTS,
    )
    workflow_level = PairStep(
        name="workflow_level",
        session=workflow_level_session,
        producer="prompts/workflow_level_producer.md",
        verifier="prompts/workflow_level_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            selected_workflow_authoring_surface,
            selected_workflow_decomposition_surface,
            workflow_optimization_trace_corpus,
            step_optimization_priority_report,
        ],
        produces={
            "workflow_level_optimization_candidates": workflow_level_optimization_candidates,
        },
        expected_output_schema=CandidatePassPayload,
        route_contracts=WORKFLOW_LEVEL_ROUTE_CONTRACTS,
    )
    package = PairStep(
        name="package",
        session=package_session,
        producer="prompts/package_producer.md",
        verifier="prompts/package_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            selected_workflow_authoring_surface,
            selected_workflow_decomposition_surface,
            selected_workflow_source_manifest,
            workflow_optimization_scope,
            workflow_optimization_trace_corpus,
            excluded_run_report,
            optimization_package_checklist,
        ],
        produces={
            "workflow_optimization_scorecard": workflow_optimization_scorecard,
            "workflow_optimization_packet": workflow_optimization_packet,
        },
        expected_output_schema=OptimizationPackagePayload,
        route_contracts=PACKAGE_ROUTE_CONTRACTS,
    )
    publish_optimization_packet = SystemStep(
        name="publish_optimization_packet",
        requires=[
            selected_workflow_capability,
            selected_workflow_authoring_surface,
            selected_workflow_decomposition_surface,
            selected_workflow_source_manifest,
            workflow_optimization_scope,
            workflow_optimization_trace_corpus,
            excluded_run_report,
            workflow_optimization_scorecard,
            workflow_optimization_packet,
        ],
        produces={
            "workflow_refinement_evidence": workflow_refinement_evidence,
            "optimization_publication_receipt": optimization_publication_receipt,
        },
    )

    entry = bootstrap

    transitions = merge_transitions(
        global_routes(pause_on_outcome_tags("question", "blocked"), failed=FAIL),
        {
            bootstrap: {"inputs_prepared": capture_frame_context},
            capture_frame_context: {"frame_context_captured": frame},
            frame: {
                "optimization_scope_framed": rank_targets,
                "no_eligible_trace_evidence": package,
                "needs_rework": frame,
            },
            rank_targets: {
                "targets_ranked": mine_failures,
                "insufficient_evidence": package,
                "needs_rework": rank_targets,
            },
            mine_failures: {
                "failure_scenarios_mined": optimize_producer,
                "no_failure_scenarios": optimize_tokens,
                "needs_rework": mine_failures,
            },
            optimize_producer: {
                "producer_candidates_ready": optimize_verifier_rubric,
                "producer_pass_not_applicable": optimize_verifier_rubric,
                "needs_rework": optimize_producer,
            },
            optimize_verifier_rubric: {
                "verifier_rubric_candidates_ready": optimize_tokens,
                "verifier_rubric_pass_not_applicable": optimize_tokens,
                "needs_rework": optimize_verifier_rubric,
            },
            optimize_tokens: {
                "token_candidates_ready": adversarial_cases,
                "token_pass_not_applicable": adversarial_cases,
                "needs_rework": optimize_tokens,
            },
            adversarial_cases: {
                "adversarial_cases_ready": workflow_level,
                "adversarial_generation_skipped": workflow_level,
                "needs_rework": adversarial_cases,
            },
            workflow_level: {
                "workflow_level_candidates_ready": package,
                "workflow_level_pass_not_applicable": package,
                "needs_rework": workflow_level,
            },
            package: {
                "optimization_packet_ready": publish_optimization_packet,
                "needs_rework": package,
            },
            publish_optimization_packet: {"optimization_candidates_published": SUCCESS},
        },
    )

    @staticmethod
    def on_bootstrap(state: State, ctx) -> tuple[State, Event]:
        params = ctx.params
        next_state = state.model_copy(
            update={
                "selected_workflow_reference": params.selected_workflow,
                "selected_workflow_name": None,
                "task_title": params.task_title,
                "run_refs": list(params.run_refs),
                "run_statuses": list(params.run_statuses),
                "route_tags": list(params.route_tags),
                "history_limit": params.history_limit,
                "top_k_steps": params.top_k_steps,
                "optimization_depth": params.optimization_depth,
                "include_adversarial_generation": params.include_adversarial_generation,
                "include_token_optimization": params.include_token_optimization,
                "include_workflow_level_candidates": params.include_workflow_level_candidates,
                "max_failure_scenarios": params.max_failure_scenarios,
                "max_candidates_per_pass": params.max_candidates_per_pass,
                "focus": params.focus,
                "sponsor_role": params.sponsor_role,
                "desired_outcome": params.desired_outcome,
                "constraints": list(params.constraints),
                "frame_status": None,
                "ranking_status": None,
                "failure_status": None,
                "producer_status": None,
                "verifier_rubric_status": None,
                "token_status": None,
                "adversarial_status": None,
                "workflow_level_status": None,
                "packaging_status": None,
                "candidate_run_count": 0,
                "eligible_run_count": 0,
                "excluded_run_count": 0,
                "no_eligible_trace_evidence": False,
                "published": False,
            }
        )
        open_workflow_sessions(
            ctx,
            "frame_session",
            "rank_targets_session",
            "mine_failures_session",
            "optimize_producer_session",
            "optimize_verifier_rubric_session",
            "optimize_tokens_session",
            "adversarial_cases_session",
            "workflow_level_session",
            "package_session",
        )
        write_invocation_contract(
            ctx,
            {
                "selected_workflow_reference": next_state.selected_workflow_reference,
                "task_title": next_state.task_title,
                "run_refs": next_state.run_refs,
                "run_statuses": next_state.run_statuses,
                "route_tags": next_state.route_tags,
                "history_limit": next_state.history_limit,
                "top_k_steps": next_state.top_k_steps,
                "optimization_depth": next_state.optimization_depth,
                "include_adversarial_generation": next_state.include_adversarial_generation,
                "include_token_optimization": next_state.include_token_optimization,
                "include_workflow_level_candidates": next_state.include_workflow_level_candidates,
                "max_failure_scenarios": next_state.max_failure_scenarios,
                "max_candidates_per_pass": next_state.max_candidates_per_pass,
                "focus": next_state.focus,
                "sponsor_role": next_state.sponsor_role,
                "desired_outcome": next_state.desired_outcome,
                "constraints": next_state.constraints,
            },
        )
        return next_state, Event("inputs_prepared")

    @staticmethod
    def on_capture_frame_context(state: State, ctx) -> tuple[State, Event]:
        capability_path = write_selected_workflow_capability_snapshot(ctx, state.selected_workflow_reference)
        authoring_surface_path = write_selected_workflow_authoring_surface(ctx, state.selected_workflow_reference)
        decomposition_surface_path = write_selected_workflow_decomposition_surface(ctx, state.selected_workflow_reference)
        source_manifest_path = write_selected_workflow_source_manifest(
            ctx=ctx,
            selected_workflow=state.selected_workflow_reference,
            relative_path="selected_workflow_source_manifest.json",
        )

        capability_snapshot = read_json_object(capability_path)
        selected_workflow_name, _ = validate_selected_workflow_capability_snapshot(capability_snapshot)
        authoring_snapshot = read_json_object(authoring_surface_path)
        validate_selected_workflow_authoring_surface_snapshot(
            authoring_snapshot,
            expected_selected_workflow_name=selected_workflow_name,
            expected_label="selected_workflow_capability.json",
        )
        decomposition_snapshot = read_json_object(decomposition_surface_path)
        validate_selected_workflow_decomposition_surface_snapshot(
            decomposition_snapshot,
            expected_selected_workflow_name=selected_workflow_name,
            expected_label="selected_workflow_capability.json",
        )
        _validate_selected_workflow_field(
            read_json_object(source_manifest_path),
            artifact_name="selected_workflow_source_manifest.json",
            expected_selected_workflow_name=selected_workflow_name,
        )

        run_dirs = list_selected_workflow_runs(
            ctx.root,
            selected_workflow_name,
            run_refs=state.run_refs,
            run_statuses=state.run_statuses,
            history_limit=state.history_limit,
        )
        trace_corpus = normalize_trace_corpus(
            selected_workflow=selected_workflow_name,
            run_dirs=run_dirs,
            route_tags=state.route_tags,
        )
        excluded_runs = list(trace_corpus.pop("excluded_runs", []))
        trace_corpus.pop("static_step_graphs", None)
        write_workflow_json(
            ctx,
            "workflow_optimization_scope.json",
            {
                "schema": "autoloop.workflow_optimization.scope/v1",
                "selected_workflow": selected_workflow_name,
                "task_title": state.task_title,
                "run_refs": state.run_refs,
                "run_statuses": state.run_statuses,
                "route_tags": state.route_tags,
                "history_limit": state.history_limit,
                "top_k_steps": state.top_k_steps,
                "optimization_depth": state.optimization_depth,
                "include_adversarial_generation": state.include_adversarial_generation,
                "include_token_optimization": state.include_token_optimization,
                "include_workflow_level_candidates": state.include_workflow_level_candidates,
                "focus": state.focus,
                "constraints": state.constraints,
            },
        )
        write_workflow_json(
            ctx,
            "excluded_run_report.json",
            {
                "schema": EXCLUDED_RUN_REPORT_SCHEMA,
                "selected_workflow": selected_workflow_name,
                "candidate_run_count": trace_corpus["candidate_run_count"],
                "excluded_runs": excluded_runs,
            },
        )
        write_workflow_json(
            ctx,
            "workflow_optimization_trace_corpus.json",
            trace_corpus,
        )

        return (
            state.model_copy(
                update={
                    "selected_workflow_name": selected_workflow_name,
                    "candidate_run_count": int(trace_corpus["candidate_run_count"]),
                    "eligible_run_count": int(trace_corpus["eligible_run_count"]),
                    "excluded_run_count": int(trace_corpus["excluded_run_count"]),
                    "no_eligible_trace_evidence": int(trace_corpus["eligible_run_count"]) == 0,
                }
            ),
            Event("frame_context_captured"),
        )

    @staticmethod
    def on_frame(state: State, outcome: Outcome, artifacts):
        del artifacts
        payload = outcome.payload
        selected_workflow_name = payload.get("selected_workflow_name")
        return state.model_copy(
            update={
                "frame_status": outcome.tag,
                "selected_workflow_name": (
                    selected_workflow_name if isinstance(selected_workflow_name, str) else state.selected_workflow_name
                ),
                "candidate_run_count": int(payload.get("candidate_run_count") or state.candidate_run_count),
                "eligible_run_count": int(payload.get("eligible_run_count") or state.eligible_run_count),
                "excluded_run_count": int(payload.get("excluded_run_count") or state.excluded_run_count),
                "no_eligible_trace_evidence": outcome.tag == "no_eligible_trace_evidence",
            }
        )

    @staticmethod
    def on_rank_targets(state: State, outcome: Outcome, artifacts):
        del artifacts
        return state.model_copy(update={"ranking_status": outcome.tag})

    @staticmethod
    def on_mine_failures(state: State, outcome: Outcome, artifacts):
        del artifacts
        return state.model_copy(update={"failure_status": outcome.tag})

    @staticmethod
    def on_optimize_producer(state: State, outcome: Outcome, artifacts):
        del artifacts
        return state.model_copy(update={"producer_status": outcome.tag})

    @staticmethod
    def on_optimize_verifier_rubric(state: State, outcome: Outcome, artifacts):
        del artifacts
        return state.model_copy(update={"verifier_rubric_status": outcome.tag})

    @staticmethod
    def on_optimize_tokens(state: State, outcome: Outcome, artifacts):
        del artifacts
        return state.model_copy(update={"token_status": outcome.tag})

    @staticmethod
    def on_adversarial_cases(state: State, outcome: Outcome, artifacts):
        del artifacts
        return state.model_copy(update={"adversarial_status": outcome.tag})

    @staticmethod
    def on_workflow_level(state: State, outcome: Outcome, artifacts):
        del artifacts
        return state.model_copy(update={"workflow_level_status": outcome.tag})

    @staticmethod
    def on_package(state: State, outcome: Outcome, artifacts):
        del artifacts
        return state.model_copy(update={"packaging_status": outcome.tag})

    @staticmethod
    def on_publish_optimization_packet(state: State, ctx) -> tuple[State, Event]:
        workflow_folder = ctx.workflow_folder
        required_paths = require_existing_artifact_paths(
            {
                "selected_workflow_capability": workflow_folder / "selected_workflow_capability.json",
                "selected_workflow_authoring_surface": workflow_folder / "selected_workflow_authoring_surface.json",
                "selected_workflow_decomposition_surface": workflow_folder / "selected_workflow_decomposition_surface.json",
                "selected_workflow_source_manifest": workflow_folder / "selected_workflow_source_manifest.json",
                "workflow_optimization_scope": workflow_folder / "workflow_optimization_scope.json",
                "workflow_optimization_trace_corpus": workflow_folder / "workflow_optimization_trace_corpus.json",
                "excluded_run_report": workflow_folder / "excluded_run_report.json",
                "workflow_optimization_scorecard": workflow_folder / "workflow_optimization_scorecard.json",
                "workflow_optimization_packet": workflow_folder / "workflow_optimization_packet.md",
            }
        )
        capability_snapshot = read_json_object(required_paths["selected_workflow_capability"])
        selected_workflow_name, _ = validate_selected_workflow_capability_snapshot(
            capability_snapshot,
            expected_selected_workflow_name=state.selected_workflow_name,
            expected_label="workflow state",
        )
        validate_selected_workflow_authoring_surface_snapshot(
            read_json_object(required_paths["selected_workflow_authoring_surface"]),
            expected_selected_workflow_name=selected_workflow_name,
            expected_label="selected_workflow_capability.json",
        )
        validate_selected_workflow_decomposition_surface_snapshot(
            read_json_object(required_paths["selected_workflow_decomposition_surface"]),
            expected_selected_workflow_name=selected_workflow_name,
            expected_label="selected_workflow_capability.json",
        )
        _validate_selected_workflow_field(
            read_json_object(required_paths["selected_workflow_source_manifest"]),
            artifact_name="selected_workflow_source_manifest.json",
            expected_selected_workflow_name=selected_workflow_name,
        )
        _validate_selected_workflow_field(
            read_json_object(required_paths["workflow_optimization_scope"]),
            artifact_name="workflow_optimization_scope.json",
            expected_selected_workflow_name=selected_workflow_name,
        )
        _validate_selected_workflow_field(
            read_json_object(required_paths["workflow_optimization_trace_corpus"]),
            artifact_name="workflow_optimization_trace_corpus.json",
            expected_selected_workflow_name=selected_workflow_name,
        )
        excluded_report = read_json_object(required_paths["excluded_run_report"])
        if excluded_report.get("schema") != EXCLUDED_RUN_REPORT_SCHEMA:
            raise ValueError("excluded_run_report.json must preserve the optimizer excluded-run schema")
        _validate_selected_workflow_field(
            excluded_report,
            artifact_name="excluded_run_report.json",
            expected_selected_workflow_name=selected_workflow_name,
        )

        scorecard_payload = read_json_object(required_paths["workflow_optimization_scorecard"])
        _validate_selected_workflow_field(
            scorecard_payload,
            artifact_name="workflow_optimization_scorecard.json",
            expected_selected_workflow_name=selected_workflow_name,
        )
        packet_text = read_required_text(
            required_paths["workflow_optimization_packet"],
            "workflow_optimization_packet.md must be non-empty",
        )
        validate_no_hidden_execution_signal(
            packet_text,
            "workflow_optimization_packet.md must not imply hidden downstream execution",
        )

        source_ok, source_details = validate_selected_workflow_source_unchanged(
            ctx=ctx,
            selected_workflow=selected_workflow_name,
            manifest_path=required_paths["selected_workflow_source_manifest"],
        )
        if not source_ok:
            updated_scorecard = dict(scorecard_payload)
            updated_scorecard["source_mutation_check"] = {"passed": False, "details": source_details}
            write_workflow_json(ctx, "workflow_optimization_scorecard.json", updated_scorecard)
            raise ValueError(source_details)

        evidence_entries = _optimization_evidence_entries(workflow_folder, state.no_eligible_trace_evidence)
        write_optimization_refinement_evidence(
            ctx=ctx,
            selected_workflow=selected_workflow_name,
            evidence_entries=evidence_entries,
        )
        receipt_payload = {
            "selected_workflow_name": selected_workflow_name,
            "evidence_run_count": state.eligible_run_count,
            "excluded_run_count": state.excluded_run_count,
            "no_eligible_trace_evidence": state.no_eligible_trace_evidence,
            "optimization_depth": state.optimization_depth,
            "publication_boundary": "candidate_only",
            "artifacts": {
                "workflow_optimization_scorecard": "workflow_optimization_scorecard.json",
                "workflow_refinement_evidence": "workflow_refinement_evidence.json",
                "workflow_optimization_packet": "workflow_optimization_packet.md",
            },
            "source_mutation_check": {"passed": True, "details": source_details},
        }
        write_publication_receipt(
            ctx,
            "optimization_publication_receipt.json",
            receipt_payload,
        )
        return state.model_copy(update={"published": True}), Event("optimization_candidates_published")

    on_outcome = staticmethod(event_on_outcome_tags("question", "blocked", "failed"))


def _optimization_evidence_entries(workflow_folder: Path, no_eligible: bool) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for filename, kind in _PACKAGE_EVIDENCE_FILES.items():
        path = workflow_folder / filename
        if not path.is_file():
            continue
        if no_eligible and kind != "workflow_optimization_scorecard":
            continue
        summary = (
            "No eligible Plan-1 observability bundles were available, so this scorecard is a no-op publication boundary."
            if kind == "workflow_optimization_scorecard" and no_eligible
            else f"Optimization evidence published in {filename}."
        )
        handling = (
            "Candidate-only boundary; use this to explain the no-op publication outcome."
            if kind == "workflow_optimization_scorecard" and no_eligible
            else "Candidate only; validate before materializing workflow changes."
        )
        entries.append(
            {
                "kind": kind,
                "path": filename,
                "summary": summary,
                "handling": handling,
            }
        )
    return entries

def _validate_selected_workflow_field(
    payload: Mapping[str, Any],
    *,
    artifact_name: str,
    expected_selected_workflow_name: str,
) -> None:
    selected_workflow_name = require_non_empty_string(
        payload.get("selected_workflow"),
        error_message=f"{artifact_name} must define a non-empty selected_workflow",
        coerce=True,
    )
    if selected_workflow_name != expected_selected_workflow_name:
        raise ValueError(f"{artifact_name} selected_workflow must match selected_workflow_capability.json")


__all__ = ["WorkflowRunTracesToOptimizationCandidates"]
