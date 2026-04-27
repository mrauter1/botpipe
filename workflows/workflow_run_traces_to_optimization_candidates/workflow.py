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
        FAILURE_SCENARIOS_SCHEMA,
        TRACE_CORPUS_SCHEMA,
        build_step_trace_metrics,
        extract_failure_scenario_seeds,
        list_selected_workflow_runs,
        normalize_trace_corpus,
        rank_optimization_targets,
        resolve_selected_workflow_name,
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
        FAILURE_SCENARIOS_SCHEMA,
        TRACE_CORPUS_SCHEMA,
        build_step_trace_metrics,
        extract_failure_scenario_seeds,
        list_selected_workflow_runs,
        normalize_trace_corpus,
        rank_optimization_targets,
        resolve_selected_workflow_name,
        validate_selected_workflow_source_unchanged,
        write_optimization_refinement_evidence,
        write_selected_workflow_source_manifest,
    )

from workflow import Artifact, FAIL, PairStep, Session, SUCCESS, SystemStep, Workflow
from workflow.primitives import Event, Outcome

from .contracts import (
    ADVERSARIAL_CASES_ROUTE_CONTRACTS,
    ADVERSARIAL_CASE_CANDIDATES_ARTIFACT,
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
    PRODUCER_PROMPT_OPTIMIZATION_CANDIDATES_ARTIFACT,
    RANK_TARGETS_ROUTE_CONTRACTS,
    SELECTED_WORKFLOW_SOURCE_MANIFEST_ARTIFACT,
    WORKFLOW_LEVEL_ROUTE_CONTRACTS,
    WORKFLOW_LEVEL_OPTIMIZATION_CANDIDATES_ARTIFACT,
    WORKFLOW_OPTIMIZATION_SCOPE_ARTIFACT,
    WORKFLOW_OPTIMIZATION_SCORECARD_ARTIFACT,
    WORKFLOW_OPTIMIZATION_TRACE_CORPUS_ARTIFACT,
    RankTargetsPayload,
    STEP_OPTIMIZATION_PRIORITY_REPORT_ARTIFACT,
    STEP_TRACE_METRICS_ARTIFACT,
    TOKEN_OPTIMIZATION_CANDIDATES_ARTIFACT,
    VERIFIER_RUBRIC_OPTIMIZATION_CANDIDATES_ARTIFACT,
    WORKFLOW_FAILURE_SCENARIOS_ARTIFACT,
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
_CANDIDATE_ARTIFACT_COUNT_KEYS = (
    ("producer", "producer_prompt_optimization_candidates.json"),
    ("verifier_rubric", "verifier_rubric_optimization_candidates.json"),
    ("token", "token_optimization_candidates.json"),
    ("adversarial_cases", "adversarial_case_candidates.json"),
    ("workflow_level", "workflow_level_optimization_candidates.json"),
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
    selected_workflow_source_manifest = Artifact.json(
        "{workflow_folder}/selected_workflow_source_manifest.json",
        schema=SELECTED_WORKFLOW_SOURCE_MANIFEST_ARTIFACT.model_cls,
    )
    workflow_optimization_scope = Artifact.json(
        "{workflow_folder}/workflow_optimization_scope.json",
        schema=WORKFLOW_OPTIMIZATION_SCOPE_ARTIFACT.model_cls,
    )
    excluded_run_report = Artifact.json(
        "{workflow_folder}/excluded_run_report.json",
        schema=EXCLUDED_RUN_REPORT_ARTIFACT.model_cls,
    )
    workflow_optimization_trace_corpus = Artifact.json(
        "{workflow_folder}/workflow_optimization_trace_corpus.json",
        schema=WORKFLOW_OPTIMIZATION_TRACE_CORPUS_ARTIFACT.model_cls,
    )
    workflow_optimization_internal_trace_corpus = Artifact.json(
        "{workflow_folder}/_workflow_optimization_internal_trace_corpus.json"
    )
    step_trace_metrics = Artifact.json(
        "{workflow_folder}/step_trace_metrics.json",
        schema=STEP_TRACE_METRICS_ARTIFACT.model_cls,
    )
    step_optimization_priority_report = Artifact.json(
        "{workflow_folder}/step_optimization_priority_report.json",
        schema=STEP_OPTIMIZATION_PRIORITY_REPORT_ARTIFACT.model_cls,
    )
    workflow_failure_scenarios = Artifact.json(
        "{workflow_folder}/workflow_failure_scenarios.json",
        schema=WORKFLOW_FAILURE_SCENARIOS_ARTIFACT.model_cls,
    )
    producer_prompt_optimization_candidates = Artifact.json(
        "{workflow_folder}/producer_prompt_optimization_candidates.json",
        schema=PRODUCER_PROMPT_OPTIMIZATION_CANDIDATES_ARTIFACT.model_cls,
    )
    verifier_rubric_optimization_candidates = Artifact.json(
        "{workflow_folder}/verifier_rubric_optimization_candidates.json",
        schema=VERIFIER_RUBRIC_OPTIMIZATION_CANDIDATES_ARTIFACT.model_cls,
    )
    token_optimization_candidates = Artifact.json(
        "{workflow_folder}/token_optimization_candidates.json",
        schema=TOKEN_OPTIMIZATION_CANDIDATES_ARTIFACT.model_cls,
    )
    adversarial_case_candidates = Artifact.json(
        "{workflow_folder}/adversarial_case_candidates.json",
        schema=ADVERSARIAL_CASE_CANDIDATES_ARTIFACT.model_cls,
    )
    workflow_level_optimization_candidates = Artifact.json(
        "{workflow_folder}/workflow_level_optimization_candidates.json",
        schema=WORKFLOW_LEVEL_OPTIMIZATION_CANDIDATES_ARTIFACT.model_cls,
    )
    workflow_optimization_scorecard = Artifact.json(
        "{workflow_folder}/workflow_optimization_scorecard.json",
        schema=WORKFLOW_OPTIMIZATION_SCORECARD_ARTIFACT.model_cls,
    )
    workflow_refinement_evidence = Artifact.json("{workflow_folder}/workflow_refinement_evidence.json")
    workflow_optimization_packet = Artifact("{workflow_folder}/workflow_optimization_packet.md")
    optimization_publication_receipt = Artifact.json("{workflow_folder}/optimization_publication_receipt.json")

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
            "workflow_optimization_internal_trace_corpus": workflow_optimization_internal_trace_corpus,
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
            workflow_optimization_internal_trace_corpus,
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
    route_optimize_tokens = SystemStep(
        name="route_optimize_tokens",
        produces={"token_optimization_candidates": token_optimization_candidates},
        route_contracts={
            "token_optimization_enabled": {
                "summary": "Token optimization remains enabled, so the workflow continues into the token candidate pass.",
            },
            "token_pass_not_applicable": {
                "summary": "Token optimization was disabled explicitly, so the workflow publishes an empty candidate artifact and skips the pass.",
                "required_artifacts": ("token_optimization_candidates",),
            },
        },
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
    route_adversarial_cases = SystemStep(
        name="route_adversarial_cases",
        produces={"adversarial_case_candidates": adversarial_case_candidates},
        route_contracts={
            "adversarial_generation_enabled": {
                "summary": "Adversarial case generation remains enabled, so the workflow continues into the adversarial candidate pass.",
            },
            "adversarial_generation_skipped": {
                "summary": "Adversarial case generation was disabled explicitly, so the workflow publishes an empty candidate artifact and skips the pass.",
                "required_artifacts": ("adversarial_case_candidates",),
            },
        },
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
    route_workflow_level = SystemStep(
        name="route_workflow_level",
        produces={
            "workflow_level_optimization_candidates": workflow_level_optimization_candidates,
        },
        route_contracts={
            "workflow_level_enabled": {
                "summary": "Workflow-level optimization remains enabled, so the workflow continues into the cross-step candidate pass.",
            },
            "workflow_level_pass_not_applicable": {
                "summary": "Workflow-level optimization was disabled explicitly, so the workflow publishes an empty candidate artifact and skips the pass.",
                "required_artifacts": ("workflow_level_optimization_candidates",),
            },
        },
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
                "no_failure_scenarios": route_optimize_tokens,
                "needs_rework": mine_failures,
            },
            optimize_producer: {
                "producer_candidates_ready": optimize_verifier_rubric,
                "producer_pass_not_applicable": optimize_verifier_rubric,
                "needs_rework": optimize_producer,
            },
            optimize_verifier_rubric: {
                "verifier_rubric_candidates_ready": route_optimize_tokens,
                "verifier_rubric_pass_not_applicable": route_optimize_tokens,
                "needs_rework": optimize_verifier_rubric,
            },
            route_optimize_tokens: {
                "token_optimization_enabled": optimize_tokens,
                "token_pass_not_applicable": route_adversarial_cases,
            },
            optimize_tokens: {
                "token_candidates_ready": route_adversarial_cases,
                "token_pass_not_applicable": route_adversarial_cases,
                "needs_rework": optimize_tokens,
            },
            route_adversarial_cases: {
                "adversarial_generation_enabled": adversarial_cases,
                "adversarial_generation_skipped": route_workflow_level,
            },
            adversarial_cases: {
                "adversarial_cases_ready": route_workflow_level,
                "adversarial_generation_skipped": route_workflow_level,
                "needs_rework": adversarial_cases,
            },
            route_workflow_level: {
                "workflow_level_enabled": workflow_level,
                "workflow_level_pass_not_applicable": package,
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
        selected_workflow_name = resolve_selected_workflow_name(ctx.root, params.selected_workflow)
        next_state = state.model_copy(
            update={
                "selected_workflow_reference": params.selected_workflow,
                "selected_workflow_name": selected_workflow_name,
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
        step_metrics_payload = _build_step_metrics_payload(trace_corpus)
        priority_report_payload = _build_priority_report_payload(
            step_metrics_payload=step_metrics_payload,
            top_k_steps=state.top_k_steps,
        )
        failure_scenarios_payload = _build_failure_scenarios_payload(
            trace_corpus=trace_corpus,
            priority_report=priority_report_payload,
            max_failure_scenarios=state.max_failure_scenarios,
        )
        internal_trace_corpus = dict(trace_corpus)
        excluded_runs = list(trace_corpus.pop("excluded_runs", []))
        trace_corpus.pop("all_step_observations", None)
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
        write_workflow_json(
            ctx,
            "_workflow_optimization_internal_trace_corpus.json",
            internal_trace_corpus,
        )
        write_workflow_json(ctx, "step_trace_metrics.json", step_metrics_payload)
        write_workflow_json(ctx, "step_optimization_priority_report.json", priority_report_payload)
        write_workflow_json(ctx, "workflow_failure_scenarios.json", failure_scenarios_payload)

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
        artifacts.workflow_failure_scenarios.write_json(
            _build_failure_scenarios_payload(
                trace_corpus=artifacts.workflow_optimization_internal_trace_corpus.read_json(),
                priority_report=artifacts.step_optimization_priority_report.read_json(),
                max_failure_scenarios=state.max_failure_scenarios,
            )
        )
        return state.model_copy(update={"failure_status": outcome.tag})

    @staticmethod
    def on_route_optimize_tokens(state: State, ctx) -> tuple[State, Event]:
        if state.include_token_optimization:
            return state, Event("token_optimization_enabled")
        write_workflow_json(
            ctx,
            "token_optimization_candidates.json",
            _empty_token_candidates_payload(selected_workflow=_selected_workflow_name_from_state(state)),
        )
        return state.model_copy(update={"token_status": "token_pass_not_applicable"}), Event(
            "token_pass_not_applicable"
        )

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
    def on_route_adversarial_cases(state: State, ctx) -> tuple[State, Event]:
        if state.include_adversarial_generation:
            return state, Event("adversarial_generation_enabled")
        write_workflow_json(
            ctx,
            "adversarial_case_candidates.json",
            _empty_adversarial_cases_payload(selected_workflow=_selected_workflow_name_from_state(state)),
        )
        return state.model_copy(update={"adversarial_status": "adversarial_generation_skipped"}), Event(
            "adversarial_generation_skipped"
        )

    @staticmethod
    def on_adversarial_cases(state: State, outcome: Outcome, artifacts):
        del artifacts
        return state.model_copy(update={"adversarial_status": outcome.tag})

    @staticmethod
    def on_route_workflow_level(state: State, ctx) -> tuple[State, Event]:
        if state.include_workflow_level_candidates:
            return state, Event("workflow_level_enabled")
        write_workflow_json(
            ctx,
            "workflow_level_optimization_candidates.json",
            _empty_workflow_level_candidates_payload(selected_workflow=_selected_workflow_name_from_state(state)),
        )
        return state.model_copy(update={"workflow_level_status": "workflow_level_pass_not_applicable"}), Event(
            "workflow_level_pass_not_applicable"
        )

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
        WORKFLOW_OPTIMIZATION_SCORECARD_ARTIFACT.read(required_paths["workflow_optimization_scorecard"])
        _validate_selected_workflow_field(
            scorecard_payload,
            artifact_name="workflow_optimization_scorecard.json",
            expected_selected_workflow_name=selected_workflow_name,
        )
        _validate_candidate_artifact_publication_surface(
            workflow_folder,
            selected_workflow_name=selected_workflow_name,
            scorecard_payload=scorecard_payload,
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
            raise ValueError(
                "authoritative selected workflow file changed during optimization publication"
            )

        evidence_entries = _optimization_evidence_entries(
            workflow_folder,
            no_eligible=state.no_eligible_trace_evidence,
            ranking_status=state.ranking_status,
            failure_status=state.failure_status,
        )
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


def _optimization_evidence_entries(
    workflow_folder: Path,
    *,
    no_eligible: bool,
    ranking_status: str | None,
    failure_status: str | None,
) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for filename, kind in _PACKAGE_EVIDENCE_FILES.items():
        path = workflow_folder / filename
        if not path.is_file():
            continue
        if no_eligible and kind != "workflow_optimization_scorecard":
            continue
        if kind == "workflow_failure_scenarios" and (
            ranking_status != "targets_ranked" or failure_status != "failure_scenarios_mined"
        ):
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


def _selected_workflow_name_from_state(state: WorkflowRunTracesToOptimizationCandidates.State) -> str:
    return require_non_empty_string(
        state.selected_workflow_name or state.selected_workflow_reference,
        error_message="selected_workflow_name must be available before optional pass routing",
        coerce=True,
    )


def _empty_token_candidates_payload(*, selected_workflow: str) -> dict[str, Any]:
    return {
        "schema": "autoloop.workflow_optimization.token_candidates/v1",
        "selected_workflow": selected_workflow,
        "candidates": [],
    }


def _empty_adversarial_cases_payload(*, selected_workflow: str) -> dict[str, Any]:
    return {
        "schema": "autoloop.workflow_optimization.adversarial_case_candidates/v1",
        "selected_workflow": selected_workflow,
        "cases": [],
    }


def _empty_workflow_level_candidates_payload(*, selected_workflow: str) -> dict[str, Any]:
    return {
        "schema": "autoloop.workflow_optimization.workflow_level_candidates/v1",
        "selected_workflow": selected_workflow,
        "candidates": [],
    }


def _validate_candidate_artifact_publication_surface(
    workflow_folder: Path,
    *,
    selected_workflow_name: str,
    scorecard_payload: Mapping[str, Any],
) -> None:
    scorecard_counts = require_mapping(
        scorecard_payload.get("candidate_counts"),
        "workflow_optimization_scorecard.json must define candidate_counts as a JSON object",
    )
    computed_counts, candidate_ids, requires_ablation = _read_candidate_publication_surface(
        workflow_folder,
        selected_workflow_name=selected_workflow_name,
    )
    for key, _filename in _CANDIDATE_ARTIFACT_COUNT_KEYS:
        raw_value = scorecard_counts.get(key, 0)
        if not isinstance(raw_value, int) or raw_value < 0:
            raise ValueError(f"workflow_optimization_scorecard.json candidate_counts.{key} must be a non-negative int")
        if raw_value != computed_counts[key]:
            raise ValueError(
                f"workflow_optimization_scorecard.json candidate_counts.{key} must match the validated candidate artifact count"
            )
    highest_priority_ids = [
        candidate_id
        for candidate_id in scorecard_payload.get("highest_priority_candidate_ids", [])
        if isinstance(candidate_id, str) and candidate_id
    ]
    missing_candidate_ids = sorted(set(highest_priority_ids) - candidate_ids)
    if missing_candidate_ids:
        raise ValueError(
            "workflow_optimization_scorecard.json highest_priority_candidate_ids must refer to validated candidate artifacts"
        )
    requires_ablation_before_promotion = scorecard_payload.get("requires_ablation_before_promotion")
    if not isinstance(requires_ablation_before_promotion, bool):
        raise ValueError("workflow_optimization_scorecard.json requires_ablation_before_promotion must be a bool")
    if requires_ablation and not requires_ablation_before_promotion:
        raise ValueError(
            "workflow_optimization_scorecard.json requires_ablation_before_promotion must be true when any validated candidate requires ablation"
        )


def _read_candidate_publication_surface(
    workflow_folder: Path,
    *,
    selected_workflow_name: str,
) -> tuple[dict[str, int], set[str], bool]:
    counts = {key: 0 for key, _filename in _CANDIDATE_ARTIFACT_COUNT_KEYS}
    candidate_ids: set[str] = set()
    requires_ablation = False

    producer_path = workflow_folder / "producer_prompt_optimization_candidates.json"
    if producer_path.is_file():
        artifact = PRODUCER_PROMPT_OPTIMIZATION_CANDIDATES_ARTIFACT.read(producer_path)
        _validate_selected_workflow_field(
            artifact.model_dump(mode="json"),
            artifact_name="producer_prompt_optimization_candidates.json",
            expected_selected_workflow_name=selected_workflow_name,
        )
        counts["producer"] = len(artifact.candidates)
        candidate_ids.update(candidate.candidate_id for candidate in artifact.candidates)
        requires_ablation = requires_ablation or any(candidate.requires_ablation for candidate in artifact.candidates)

    verifier_path = workflow_folder / "verifier_rubric_optimization_candidates.json"
    if verifier_path.is_file():
        artifact = VERIFIER_RUBRIC_OPTIMIZATION_CANDIDATES_ARTIFACT.read(verifier_path)
        _validate_selected_workflow_field(
            artifact.model_dump(mode="json"),
            artifact_name="verifier_rubric_optimization_candidates.json",
            expected_selected_workflow_name=selected_workflow_name,
        )
        counts["verifier_rubric"] = len(artifact.candidates)
        candidate_ids.update(candidate.candidate_id for candidate in artifact.candidates)
        requires_ablation = requires_ablation or any(candidate.requires_ablation for candidate in artifact.candidates)

    token_path = workflow_folder / "token_optimization_candidates.json"
    if token_path.is_file():
        artifact = TOKEN_OPTIMIZATION_CANDIDATES_ARTIFACT.read(token_path)
        _validate_selected_workflow_field(
            artifact.model_dump(mode="json"),
            artifact_name="token_optimization_candidates.json",
            expected_selected_workflow_name=selected_workflow_name,
        )
        counts["token"] = len(artifact.candidates)
        candidate_ids.update(candidate.candidate_id for candidate in artifact.candidates)
        requires_ablation = requires_ablation or any(candidate.requires_ablation for candidate in artifact.candidates)

    adversarial_path = workflow_folder / "adversarial_case_candidates.json"
    if adversarial_path.is_file():
        artifact = ADVERSARIAL_CASE_CANDIDATES_ARTIFACT.read(adversarial_path)
        _validate_selected_workflow_field(
            artifact.model_dump(mode="json"),
            artifact_name="adversarial_case_candidates.json",
            expected_selected_workflow_name=selected_workflow_name,
        )
        counts["adversarial_cases"] = len(artifact.cases)
        candidate_ids.update(case.case_id for case in artifact.cases)

    workflow_level_path = workflow_folder / "workflow_level_optimization_candidates.json"
    if workflow_level_path.is_file():
        artifact = WORKFLOW_LEVEL_OPTIMIZATION_CANDIDATES_ARTIFACT.read(workflow_level_path)
        _validate_selected_workflow_field(
            artifact.model_dump(mode="json"),
            artifact_name="workflow_level_optimization_candidates.json",
            expected_selected_workflow_name=selected_workflow_name,
        )
        counts["workflow_level"] = len(artifact.candidates)
        candidate_ids.update(candidate.candidate_id for candidate in artifact.candidates)
        requires_ablation = requires_ablation or any(candidate.requires_ablation for candidate in artifact.candidates)

    return counts, candidate_ids, requires_ablation


def _build_step_metrics_payload(trace_corpus: Mapping[str, Any]) -> dict[str, Any]:
    static_step_graphs = [item for item in trace_corpus.get("static_step_graphs", []) if isinstance(item, Mapping)]
    return build_step_trace_metrics(trace_corpus, static_step_graphs)


def _build_priority_report_payload(
    *,
    step_metrics_payload: Mapping[str, Any],
    top_k_steps: int,
) -> dict[str, Any]:
    return rank_optimization_targets(
        step_metrics=step_metrics_payload,
        static_centrality={},
        top_k=top_k_steps,
    )


def _build_failure_scenarios_payload(
    *,
    trace_corpus: Mapping[str, Any],
    priority_report: Mapping[str, Any],
    max_failure_scenarios: int,
) -> dict[str, Any]:
    seeds_payload = extract_failure_scenario_seeds(
        trace_corpus=trace_corpus,
        priority_report=priority_report,
        max_scenarios=max_failure_scenarios,
    )
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for seed in seeds_payload.get("failure_scenario_seeds", []):
        if not isinstance(seed, Mapping):
            continue
        step_name = require_non_empty_string(
            seed.get("step_name"),
            error_message="failure scenario seeds must define step_name",
            coerce=True,
        )
        reasons = [reason for reason in seed.get("seed_reasons", []) if isinstance(reason, str)]
        failure_kind = _classify_failure_kind(reasons)
        group_key = (step_name, failure_kind)
        observation_ids = {
            observation_id
            for observation_id in seed.get("observation_ids", [])
            if isinstance(observation_id, str) and observation_id
        }
        existing = grouped.get(group_key)
        if existing is None:
            grouped[group_key] = {
                "failure_id": f"{_slug(step_name)}_{_slug(failure_kind)}",
                "step_name": step_name,
                "failure_kind": failure_kind,
                "severity": _failure_severity(failure_kind),
                "frequency": max(1, int(seed.get("frequency") or len(observation_ids))),
                "evidence_observation_ids": observation_ids,
                "producer_gap": _producer_gap(failure_kind, reasons),
                "verifier_behavior": _verifier_behavior(failure_kind),
                "likely_fix_surfaces": _likely_fix_surfaces(failure_kind),
                "downstream_effect": _downstream_effect(failure_kind, reasons),
            }
            continue
        existing["frequency"] = max(
            int(existing["frequency"]),
            len(existing["evidence_observation_ids"] | observation_ids),
            int(existing["frequency"]) + int(seed.get("frequency") or 0),
        )
        existing["evidence_observation_ids"] |= observation_ids

    failure_scenarios = sorted(
        (
            {
                **payload,
                "evidence_observation_ids": sorted(payload["evidence_observation_ids"]),
            }
            for payload in grouped.values()
        ),
        key=lambda item: (-_severity_rank(str(item["severity"])), -int(item["frequency"]), str(item["step_name"])),
    )[:max_failure_scenarios]
    return {
        "schema": FAILURE_SCENARIOS_SCHEMA,
        "selected_workflow": require_non_empty_string(
            trace_corpus.get("selected_workflow"),
            error_message="trace_corpus.selected_workflow must be non-empty",
            coerce=True,
        ),
        "failure_scenarios": failure_scenarios,
    }


def _classify_failure_kind(reasons: list[str]) -> str:
    if any(reason == "repeated_same_step_needs_rework_loop" for reason in reasons):
        return "needs_rework_loop"
    if any(reason == "repeated_same_step_needs_replan_loop" for reason in reasons):
        return "needs_replan_loop"
    if "terminal_failure_after_local_pass" in reasons:
        return "downstream_failure_after_local_pass"
    if "route:blocked" in reasons:
        return "blocked_missing_context"
    if "route:failed" in reasons:
        return "artifact_invalid"
    if "high_token_usage_without_success" in reasons:
        return "token_bloat"
    if "missing_raw_output_reference" in reasons:
        return "artifact_missing"
    if "missing_usage_data" in reasons or "missing_static_graph" in reasons:
        return "insufficient_evidence"
    if "route:needs_replan" in reasons:
        return "input_quality_gap"
    if "route:needs_rework" in reasons:
        return "producer_failed_verifier"
    return "insufficient_evidence"


def _failure_severity(failure_kind: str) -> str:
    if failure_kind in {"downstream_failure_after_local_pass", "blocked_missing_context", "artifact_invalid"}:
        return "high"
    if failure_kind in {"needs_rework_loop", "needs_replan_loop", "producer_failed_verifier", "token_bloat"}:
        return "medium"
    return "low"


def _severity_rank(severity: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(severity, 0)


def _producer_gap(failure_kind: str, reasons: list[str]) -> str | None:
    if failure_kind == "producer_failed_verifier":
        return "Producer output likely missed required evidence, structure, or normalization expected by the verifier."
    if failure_kind in {"needs_rework_loop", "needs_replan_loop"}:
        return "The step repeated without resolving the same gap, suggesting unstable local instructions or missing evidence discipline."
    if failure_kind == "token_bloat":
        return "High token use did not translate into a successful local outcome."
    if failure_kind == "artifact_missing":
        return "The step completed without durable raw output references needed for later diagnosis."
    if failure_kind == "input_quality_gap" or "route:needs_replan" in reasons:
        return "Inputs reaching the step appear too weak or incomplete for the current prompt contract."
    return None


def _verifier_behavior(failure_kind: str) -> str | None:
    if failure_kind in {"producer_failed_verifier", "needs_rework_loop"}:
        return "Verifier or route control pushed the step back for local repair."
    if failure_kind == "artifact_invalid":
        return "The workflow failed locally before a stable artifact could be accepted downstream."
    if failure_kind == "downstream_failure_after_local_pass":
        return "The step passed locally, but later workflow execution still failed."
    return None


def _likely_fix_surfaces(failure_kind: str) -> list[str]:
    if failure_kind in {"producer_failed_verifier", "artifact_missing", "token_bloat"}:
        return ["producer_prompt"]
    if failure_kind in {"needs_rework_loop", "needs_replan_loop"}:
        return ["producer_prompt", "verifier_rubric"]
    if failure_kind == "downstream_failure_after_local_pass":
        return ["workflow_handoff", "workflow_level"]
    if failure_kind == "blocked_missing_context":
        return ["input_contract", "producer_prompt"]
    if failure_kind == "input_quality_gap":
        return ["input_quality", "operator_process"]
    return ["insufficient_evidence"]


def _downstream_effect(failure_kind: str, reasons: list[str]) -> str | None:
    if failure_kind == "downstream_failure_after_local_pass":
        return "A later step or the terminal workflow outcome still failed after this step passed locally."
    if failure_kind in {"needs_rework_loop", "needs_replan_loop"}:
        return "The workflow paid repeated local loop cost without progressing cleanly."
    if "route:blocked" in reasons:
        return "Execution stalled because required context or artifacts were unavailable."
    return None


def _slug(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "_" for char in value)
    collapsed = "_".join(part for part in cleaned.split("_") if part)
    return collapsed or "item"

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
