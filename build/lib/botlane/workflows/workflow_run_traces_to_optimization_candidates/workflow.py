"""Optimization-candidate workflow shell built on runtime-owned run observability."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from botlane_optimizer import (
    EXCLUDED_RUN_REPORT_SCHEMA,
    FAILURE_SCENARIOS_SCHEMA,
    OptimizationArtifactSpec,
    capture_optimization_frame_context,
    collect_optimization_publication_surface,
    finalize_optional_optimization_artifact,
    read_optimization_artifact_payload,
    resolve_selected_workflow_name,
    validate_optimization_scorecard_publication,
    validate_optimization_selected_workflow_field,
    validate_selected_workflow_source_unchanged,
    write_optimization_refinement_evidence,
)
from botlane.stdlib import (
    open_workflow_sessions,
    read_json_object,
    read_required_text,
    require_existing_artifact_paths,
    require_non_empty_string,
    validate_no_hidden_execution_signal,
    validate_selected_workflow_authoring_surface_snapshot,
    validate_selected_workflow_capability_snapshot,
    validate_selected_workflow_decomposition_surface_snapshot,
    write_invocation_contract,
    write_publication_receipt,
    write_workflow_json,
)
from botlane import Event, FINISH, Outcome, Prompt, Route, Session, Workflow, produce_verify_step, python_step
from botlane.core import Artifact

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
    WORKFLOW_FAILURE_SCENARIO_SEEDS_ARTIFACT,
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
    "workflow_failure_scenario_seeds",
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
_PRODUCER_CANDIDATES_SCHEMA = "botlane.workflow_optimization.producer_candidates/v1"
_VERIFIER_RUBRIC_CANDIDATES_SCHEMA = "botlane.workflow_optimization.verifier_rubric_candidates/v1"
_TOKEN_CANDIDATES_SCHEMA = "botlane.workflow_optimization.token_candidates/v1"
_ADVERSARIAL_CASE_CANDIDATES_SCHEMA = "botlane.workflow_optimization.adversarial_case_candidates/v1"
_WORKFLOW_LEVEL_CANDIDATES_SCHEMA = "botlane.workflow_optimization.workflow_level_candidates/v1"


def _after_frame(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    selected_workflow_name = payload.get("selected_workflow_name")
    ctx.state.frame_status = outcome.tag
    if isinstance(selected_workflow_name, str):
        ctx.state.selected_workflow_name = selected_workflow_name
    ctx.state.candidate_run_count = int(payload.get("candidate_run_count") or ctx.state.candidate_run_count)
    ctx.state.eligible_run_count = int(payload.get("eligible_run_count") or ctx.state.eligible_run_count)
    ctx.state.excluded_run_count = int(payload.get("excluded_run_count") or ctx.state.excluded_run_count)
    ctx.state.no_eligible_trace_evidence = outcome.tag == "no_eligible_trace_evidence"
    return None


def _after_rank_targets(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    ctx.state.ranking_status = outcome.tag
    return None


def _after_mine_failures(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    selected_workflow_name = _selected_workflow_name_from_state(ctx.state)
    if outcome.tag == "failure_scenarios_mined":
        read_optimization_artifact_payload(
            ctx.artifacts.workflow_failure_scenarios.path,
            spec=_FAILURE_SCENARIOS_SPEC,
            selected_workflow_name=selected_workflow_name,
        )
    elif outcome.tag == "no_failure_scenarios":
        if ctx.artifacts.workflow_failure_scenarios.path.is_file():
            read_optimization_artifact_payload(
                ctx.artifacts.workflow_failure_scenarios.path,
                spec=_FAILURE_SCENARIOS_SPEC,
                selected_workflow_name=selected_workflow_name,
            )
        else:
            ctx.artifacts.workflow_failure_scenarios.path.write_text(
                json.dumps(
                    _empty_failure_scenarios_payload(selected_workflow=selected_workflow_name),
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
    ctx.state.failure_status = outcome.tag
    return None


def _after_optimize_producer(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    finalize_optional_optimization_artifact(
        route=outcome.tag,
        path=ctx.artifacts.producer_prompt_optimization_candidates.path,
        selected_workflow_name=_selected_workflow_name_from_state(ctx.state),
        spec=_PRODUCER_CANDIDATES_SPEC,
    )
    ctx.state.producer_status = outcome.tag
    return None


def _after_optimize_verifier_rubric(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    finalize_optional_optimization_artifact(
        route=outcome.tag,
        path=ctx.artifacts.verifier_rubric_optimization_candidates.path,
        selected_workflow_name=_selected_workflow_name_from_state(ctx.state),
        spec=_VERIFIER_RUBRIC_CANDIDATES_SPEC,
    )
    ctx.state.verifier_rubric_status = outcome.tag
    return None


def _after_optimize_tokens(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    finalize_optional_optimization_artifact(
        route=outcome.tag,
        path=ctx.artifacts.token_optimization_candidates.path,
        selected_workflow_name=_selected_workflow_name_from_state(ctx.state),
        spec=_TOKEN_CANDIDATES_SPEC,
    )
    ctx.state.token_status = outcome.tag
    return None


def _after_adversarial_cases(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    finalize_optional_optimization_artifact(
        route=outcome.tag,
        path=ctx.artifacts.adversarial_case_candidates.path,
        selected_workflow_name=_selected_workflow_name_from_state(ctx.state),
        spec=_ADVERSARIAL_CASES_SPEC,
    )
    ctx.state.adversarial_status = outcome.tag
    return None


def _after_workflow_level(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    finalize_optional_optimization_artifact(
        route=outcome.tag,
        path=ctx.artifacts.workflow_level_optimization_candidates.path,
        selected_workflow_name=_selected_workflow_name_from_state(ctx.state),
        spec=_WORKFLOW_LEVEL_CANDIDATES_SPEC,
    )
    ctx.state.workflow_level_status = outcome.tag
    return None


def _after_package(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    ctx.state.packaging_status = outcome.tag
    return None


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
    framework_architecture_doc = Artifact("{root}/docs/architecture.md")
    framework_authoring_doc = Artifact("{root}/docs/authoring.md")
    workflow_instructions = Artifact("{root}/Workflow_Instructions.md")
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
        "{workflow_folder}/_workflow_optimization_internal_trace_corpus.json",
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
    workflow_failure_scenario_seeds = Artifact.json(
        "{workflow_folder}/workflow_failure_scenario_seeds.json",
        schema=WORKFLOW_FAILURE_SCENARIO_SEEDS_ARTIFACT.model_cls,
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

    frame = produce_verify_step(
        producer_prompt=Prompt.file("prompts/frame_producer.md"),
        verifier_prompt=Prompt.file("prompts/frame_verifier.md"),
        session=frame_session,
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
            workflow_failure_scenario_seeds,
            framework_architecture_doc,
            framework_authoring_doc,
            workflow_instructions,
        ],
        producer_writes=[
            selected_workflow_capability,
            selected_workflow_authoring_surface,
            selected_workflow_decomposition_surface,
            selected_workflow_source_manifest,
            workflow_optimization_scope,
            workflow_optimization_trace_corpus,
            excluded_run_report,
            workflow_failure_scenario_seeds,
        ],
        control_schema=FrameOptimizationPayload,
        routes=FRAME_ROUTE_CONTRACTS,
        after_verifier=_after_frame,
    )
    rank_targets = produce_verify_step(
        producer_prompt=Prompt.file("prompts/rank_targets_producer.md"),
        verifier_prompt=Prompt.file("prompts/rank_targets_verifier.md"),
        session=rank_targets_session,
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            selected_workflow_authoring_surface,
            selected_workflow_decomposition_surface,
            workflow_optimization_scope,
            workflow_optimization_trace_corpus,
        ],
        producer_writes=[step_trace_metrics, step_optimization_priority_report],
        control_schema=RankTargetsPayload,
        routes=RANK_TARGETS_ROUTE_CONTRACTS,
        after_verifier=_after_rank_targets,
    )
    mine_failures = produce_verify_step(
        producer_prompt=Prompt.file("prompts/mine_failures_producer.md"),
        verifier_prompt=Prompt.file("prompts/mine_failures_verifier.md"),
        session=mine_failures_session,
        requires=[
            request,
            invocation_contract,
            selected_workflow_authoring_surface,
            workflow_optimization_scope,
            workflow_optimization_internal_trace_corpus,
            workflow_optimization_trace_corpus,
            step_optimization_priority_report,
            workflow_failure_scenario_seeds,
        ],
        producer_writes=[workflow_failure_scenarios],
        control_schema=FailureScenarioPayload,
        routes=MINE_FAILURES_ROUTE_CONTRACTS,
        after_verifier=_after_mine_failures,
    )
    optimize_producer = produce_verify_step(
        producer_prompt=Prompt.file("prompts/optimize_producer_producer.md"),
        verifier_prompt=Prompt.file("prompts/optimize_producer_verifier.md"),
        session=optimize_producer_session,
        requires=[
            request,
            invocation_contract,
            selected_workflow_authoring_surface,
            workflow_optimization_scope,
            workflow_failure_scenarios,
            step_optimization_priority_report,
        ],
        producer_writes=[producer_prompt_optimization_candidates],
        control_schema=CandidatePassPayload,
        routes=OPTIMIZE_PRODUCER_ROUTE_CONTRACTS,
        after_verifier=_after_optimize_producer,
    )
    optimize_verifier_rubric = produce_verify_step(
        producer_prompt=Prompt.file("prompts/optimize_verifier_rubric_producer.md"),
        verifier_prompt=Prompt.file("prompts/optimize_verifier_rubric_verifier.md"),
        session=optimize_verifier_rubric_session,
        requires=[
            request,
            invocation_contract,
            selected_workflow_authoring_surface,
            workflow_optimization_scope,
            workflow_failure_scenarios,
            step_optimization_priority_report,
        ],
        producer_writes=[verifier_rubric_optimization_candidates],
        control_schema=CandidatePassPayload,
        routes=OPTIMIZE_VERIFIER_RUBRIC_ROUTE_CONTRACTS,
        after_verifier=_after_optimize_verifier_rubric,
    )
    optimize_tokens = produce_verify_step(
        producer_prompt=Prompt.file("prompts/optimize_tokens_producer.md"),
        verifier_prompt=Prompt.file("prompts/optimize_tokens_verifier.md"),
        session=optimize_tokens_session,
        requires=[
            request,
            invocation_contract,
            selected_workflow_authoring_surface,
            workflow_optimization_scope,
            workflow_optimization_trace_corpus,
            step_optimization_priority_report,
        ],
        producer_writes=[token_optimization_candidates],
        control_schema=CandidatePassPayload,
        routes=OPTIMIZE_TOKENS_ROUTE_CONTRACTS,
        after_verifier=_after_optimize_tokens,
    )
    adversarial_cases = produce_verify_step(
        producer_prompt=Prompt.file("prompts/adversarial_cases_producer.md"),
        verifier_prompt=Prompt.file("prompts/adversarial_cases_verifier.md"),
        session=adversarial_cases_session,
        requires=[
            request,
            invocation_contract,
            workflow_optimization_scope,
            workflow_failure_scenarios,
            step_optimization_priority_report,
        ],
        producer_writes=[adversarial_case_candidates],
        control_schema=AdversarialCasesPayload,
        routes=ADVERSARIAL_CASES_ROUTE_CONTRACTS,
        after_verifier=_after_adversarial_cases,
    )
    workflow_level = produce_verify_step(
        producer_prompt=Prompt.file("prompts/workflow_level_producer.md"),
        verifier_prompt=Prompt.file("prompts/workflow_level_verifier.md"),
        session=workflow_level_session,
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            selected_workflow_authoring_surface,
            selected_workflow_decomposition_surface,
            workflow_optimization_scope,
            workflow_optimization_trace_corpus,
            step_optimization_priority_report,
        ],
        producer_writes=[workflow_level_optimization_candidates],
        control_schema=CandidatePassPayload,
        routes=WORKFLOW_LEVEL_ROUTE_CONTRACTS,
        after_verifier=_after_workflow_level,
    )
    package = produce_verify_step(
        producer_prompt=Prompt.file("prompts/package_producer.md"),
        verifier_prompt=Prompt.file("prompts/package_verifier.md"),
        session=package_session,
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
        producer_writes=[workflow_optimization_scorecard, workflow_optimization_packet],
        control_schema=OptimizationPackagePayload,
        routes=PACKAGE_ROUTE_CONTRACTS,
        after_verifier=_after_package,
    )

    @python_step(
        name="bootstrap",
        requires=[request],
        writes=[invocation_contract],
        routes={"inputs_prepared": "capture_frame_context"},
    )
    def bootstrap(ctx):
        params = ctx.params
        selected_workflow_name = resolve_selected_workflow_name(ctx.root, params.selected_workflow)
        next_state = ctx.state.model_copy(
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
        ctx.state = next_state
        return "inputs_prepared"

    @python_step(
        name="capture_frame_context",
        requires=[request, invocation_contract],
        writes=[
            selected_workflow_capability,
            selected_workflow_authoring_surface,
            selected_workflow_decomposition_surface,
            selected_workflow_source_manifest,
            workflow_optimization_scope,
            workflow_optimization_trace_corpus,
            workflow_optimization_internal_trace_corpus,
            excluded_run_report,
            workflow_failure_scenario_seeds,
        ],
        routes={"frame_context_captured": "frame"},
    )
    def capture_frame_context(ctx):
        frame_capture = capture_optimization_frame_context(
            ctx=ctx,
            selected_workflow_reference=ctx.state.selected_workflow_reference,
            task_title=ctx.state.task_title,
            run_refs=ctx.state.run_refs,
            run_statuses=ctx.state.run_statuses,
            route_tags=ctx.state.route_tags,
            history_limit=ctx.state.history_limit,
            top_k_steps=ctx.state.top_k_steps,
            optimization_depth=ctx.state.optimization_depth,
            include_adversarial_generation=ctx.state.include_adversarial_generation,
            include_token_optimization=ctx.state.include_token_optimization,
            include_workflow_level_candidates=ctx.state.include_workflow_level_candidates,
            max_failure_scenarios=ctx.state.max_failure_scenarios,
            max_candidates_per_pass=ctx.state.max_candidates_per_pass,
            focus=ctx.state.focus,
            constraints=ctx.state.constraints,
        )
        ctx.state.selected_workflow_name = frame_capture.selected_workflow_name
        ctx.state.candidate_run_count = frame_capture.candidate_run_count
        ctx.state.eligible_run_count = frame_capture.eligible_run_count
        ctx.state.excluded_run_count = frame_capture.excluded_run_count
        ctx.state.no_eligible_trace_evidence = frame_capture.no_eligible_trace_evidence
        return "frame_context_captured"

    @python_step(
        name="route_optimize_tokens",
        writes=[token_optimization_candidates],
        routes={
            "token_optimization_enabled": Route.to(
                "optimize_tokens",
                summary="Token optimization remains enabled, so the workflow continues into the token candidate pass.",
            ),
            "token_pass_not_applicable": Route.to(
                "route_adversarial_cases",
                summary="Token optimization was disabled explicitly, so the workflow publishes an empty candidate artifact and skips the pass.",
                required_writes=("token_optimization_candidates",),
            ),
        },
    )
    def route_optimize_tokens(ctx):
        if ctx.state.include_token_optimization:
            return "token_optimization_enabled"
        finalize_optional_optimization_artifact(
            route="token_pass_not_applicable",
            path=ctx.workflow_folder / _TOKEN_CANDIDATES_SPEC.filename,
            selected_workflow_name=_selected_workflow_name_from_state(ctx.state),
            spec=_TOKEN_CANDIDATES_SPEC,
        )
        ctx.state.token_status = "token_pass_not_applicable"
        return "token_pass_not_applicable"

    @python_step(
        name="route_adversarial_cases",
        writes=[adversarial_case_candidates],
        routes={
            "adversarial_generation_enabled": Route.to(
                "adversarial_cases",
                summary="Adversarial case generation remains enabled, so the workflow continues into the adversarial candidate pass.",
            ),
            "adversarial_generation_skipped": Route.to(
                "route_workflow_level",
                summary="Adversarial case generation was disabled explicitly, so the workflow publishes an empty candidate artifact and skips the pass.",
                required_writes=("adversarial_case_candidates",),
            ),
        },
    )
    def route_adversarial_cases(ctx):
        if ctx.state.include_adversarial_generation:
            return "adversarial_generation_enabled"
        finalize_optional_optimization_artifact(
            route="adversarial_generation_skipped",
            path=ctx.workflow_folder / _ADVERSARIAL_CASES_SPEC.filename,
            selected_workflow_name=_selected_workflow_name_from_state(ctx.state),
            spec=_ADVERSARIAL_CASES_SPEC,
        )
        ctx.state.adversarial_status = "adversarial_generation_skipped"
        return "adversarial_generation_skipped"

    @python_step(
        name="route_workflow_level",
        writes=[workflow_level_optimization_candidates],
        routes={
            "workflow_level_enabled": Route.to(
                "workflow_level",
                summary="Workflow-level optimization remains enabled, so the workflow continues into the cross-step candidate pass.",
            ),
            "workflow_level_pass_not_applicable": Route.to(
                "package",
                summary="Workflow-level optimization was disabled explicitly, so the workflow publishes an empty candidate artifact and skips the pass.",
                required_writes=("workflow_level_optimization_candidates",),
            ),
        },
    )
    def route_workflow_level(ctx):
        if ctx.state.include_workflow_level_candidates:
            return "workflow_level_enabled"
        finalize_optional_optimization_artifact(
            route="workflow_level_pass_not_applicable",
            path=ctx.workflow_folder / _WORKFLOW_LEVEL_CANDIDATES_SPEC.filename,
            selected_workflow_name=_selected_workflow_name_from_state(ctx.state),
            spec=_WORKFLOW_LEVEL_CANDIDATES_SPEC,
        )
        ctx.state.workflow_level_status = "workflow_level_pass_not_applicable"
        return "workflow_level_pass_not_applicable"

    @python_step(
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
        writes=[workflow_refinement_evidence, optimization_publication_receipt],
        routes={"optimization_candidates_published": FINISH},
    )
    def publish_optimization_packet(ctx):
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
            expected_selected_workflow_name=ctx.state.selected_workflow_name,
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
        validate_optimization_selected_workflow_field(
            read_json_object(required_paths["selected_workflow_source_manifest"]),
            artifact_name="selected_workflow_source_manifest.json",
            expected_selected_workflow_name=selected_workflow_name,
        )
        scope_payload = read_json_object(required_paths["workflow_optimization_scope"])
        validate_optimization_selected_workflow_field(
            scope_payload,
            artifact_name="workflow_optimization_scope.json",
            expected_selected_workflow_name=selected_workflow_name,
        )
        WORKFLOW_OPTIMIZATION_SCOPE_ARTIFACT.read(required_paths["workflow_optimization_scope"])
        validate_optimization_selected_workflow_field(
            read_json_object(required_paths["workflow_optimization_trace_corpus"]),
            artifact_name="workflow_optimization_trace_corpus.json",
            expected_selected_workflow_name=selected_workflow_name,
        )
        excluded_report = read_json_object(required_paths["excluded_run_report"])
        if excluded_report.get("schema") != EXCLUDED_RUN_REPORT_SCHEMA:
            raise ValueError("excluded_run_report.json must preserve the optimizer excluded-run schema")
        validate_optimization_selected_workflow_field(
            excluded_report,
            artifact_name="excluded_run_report.json",
            expected_selected_workflow_name=selected_workflow_name,
        )

        if scope_payload.get("optimization_depth") != ctx.state.optimization_depth:
            raise ValueError("workflow_optimization_scope.json optimization_depth must match the workflow request")

        publication_surface = collect_optimization_publication_surface(
            workflow_folder,
            selected_workflow_name=selected_workflow_name,
            artifact_specs=_CANDIDATE_ARTIFACT_SPECS,
        )
        scorecard_payload = read_json_object(required_paths["workflow_optimization_scorecard"])
        scorecard_payload["optimization_depth"] = ctx.state.optimization_depth
        scorecard_payload["ablation_executed"] = False
        scorecard_payload["requires_ablation_before_promotion"] = publication_surface.requires_ablation
        write_workflow_json(ctx, "workflow_optimization_scorecard.json", scorecard_payload)
        WORKFLOW_OPTIMIZATION_SCORECARD_ARTIFACT.read(required_paths["workflow_optimization_scorecard"])
        validate_optimization_selected_workflow_field(
            scorecard_payload,
            artifact_name="workflow_optimization_scorecard.json",
            expected_selected_workflow_name=selected_workflow_name,
        )
        validate_optimization_scorecard_publication(
            scorecard_payload=scorecard_payload,
            publication_surface=publication_surface,
        )
        packet_text = read_required_text(
            required_paths["workflow_optimization_packet"],
            "workflow_optimization_packet.md must be non-empty",
        )
        packet_text = _ensure_packet_optimization_depth_section(
            packet_text,
            optimization_depth=ctx.state.optimization_depth,
        )
        required_paths["workflow_optimization_packet"].write_text(packet_text, encoding="utf-8")
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
            no_eligible=ctx.state.no_eligible_trace_evidence,
            ranking_status=ctx.state.ranking_status,
            failure_status=ctx.state.failure_status,
        )
        write_optimization_refinement_evidence(
            ctx=ctx,
            selected_workflow=selected_workflow_name,
            evidence_entries=evidence_entries,
        )
        receipt_payload = {
            "selected_workflow_name": selected_workflow_name,
            "evidence_run_count": ctx.state.eligible_run_count,
            "excluded_run_count": ctx.state.excluded_run_count,
            "no_eligible_trace_evidence": ctx.state.no_eligible_trace_evidence,
            "optimization_depth": ctx.state.optimization_depth,
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
        ctx.state.published = True
        return "optimization_candidates_published"

    entry = bootstrap



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


def _empty_failure_scenarios_payload(*, selected_workflow: str) -> dict[str, Any]:
    return {
        "schema": FAILURE_SCENARIOS_SCHEMA,
        "selected_workflow": selected_workflow,
        "failure_scenarios": [],
    }


def _empty_producer_candidates_payload(*, selected_workflow: str) -> dict[str, Any]:
    return {
        "schema": _PRODUCER_CANDIDATES_SCHEMA,
        "selected_workflow": selected_workflow,
        "target_steps": [],
        "candidates": [],
    }


def _empty_verifier_rubric_candidates_payload(*, selected_workflow: str) -> dict[str, Any]:
    return {
        "schema": _VERIFIER_RUBRIC_CANDIDATES_SCHEMA,
        "selected_workflow": selected_workflow,
        "target_steps": [],
        "candidates": [],
    }


def _empty_token_candidates_payload(*, selected_workflow: str) -> dict[str, Any]:
    return {
        "schema": _TOKEN_CANDIDATES_SCHEMA,
        "selected_workflow": selected_workflow,
        "candidates": [],
    }


def _empty_adversarial_cases_payload(*, selected_workflow: str) -> dict[str, Any]:
    return {
        "schema": _ADVERSARIAL_CASE_CANDIDATES_SCHEMA,
        "selected_workflow": selected_workflow,
        "cases": [],
    }


def _empty_workflow_level_candidates_payload(*, selected_workflow: str) -> dict[str, Any]:
    return {
        "schema": _WORKFLOW_LEVEL_CANDIDATES_SCHEMA,
        "selected_workflow": selected_workflow,
        "candidates": [],
    }


_FAILURE_SCENARIOS_SPEC = OptimizationArtifactSpec(
    filename="workflow_failure_scenarios.json",
    artifact_name="workflow_failure_scenarios.json",
    expected_schema=FAILURE_SCENARIOS_SCHEMA,
    list_field="failure_scenarios",
    reader=WORKFLOW_FAILURE_SCENARIOS_ARTIFACT.read,
    empty_payload_factory=_empty_failure_scenarios_payload,
)

_PRODUCER_CANDIDATES_SPEC = OptimizationArtifactSpec(
    filename="producer_prompt_optimization_candidates.json",
    artifact_name="producer_prompt_optimization_candidates.json",
    expected_schema=_PRODUCER_CANDIDATES_SCHEMA,
    list_field="candidates",
    reader=PRODUCER_PROMPT_OPTIMIZATION_CANDIDATES_ARTIFACT.read,
    empty_payload_factory=_empty_producer_candidates_payload,
    count_key="producer",
    id_field="candidate_id",
    requires_ablation_field="requires_ablation",
)

_VERIFIER_RUBRIC_CANDIDATES_SPEC = OptimizationArtifactSpec(
    filename="verifier_rubric_optimization_candidates.json",
    artifact_name="verifier_rubric_optimization_candidates.json",
    expected_schema=_VERIFIER_RUBRIC_CANDIDATES_SCHEMA,
    list_field="candidates",
    reader=VERIFIER_RUBRIC_OPTIMIZATION_CANDIDATES_ARTIFACT.read,
    empty_payload_factory=_empty_verifier_rubric_candidates_payload,
    count_key="verifier_rubric",
    id_field="candidate_id",
    requires_ablation_field="requires_ablation",
)

_TOKEN_CANDIDATES_SPEC = OptimizationArtifactSpec(
    filename="token_optimization_candidates.json",
    artifact_name="token_optimization_candidates.json",
    expected_schema=_TOKEN_CANDIDATES_SCHEMA,
    list_field="candidates",
    reader=TOKEN_OPTIMIZATION_CANDIDATES_ARTIFACT.read,
    empty_payload_factory=_empty_token_candidates_payload,
    count_key="token",
    id_field="candidate_id",
    requires_ablation_field="requires_ablation",
)

_ADVERSARIAL_CASES_SPEC = OptimizationArtifactSpec(
    filename="adversarial_case_candidates.json",
    artifact_name="adversarial_case_candidates.json",
    expected_schema=_ADVERSARIAL_CASE_CANDIDATES_SCHEMA,
    list_field="cases",
    reader=ADVERSARIAL_CASE_CANDIDATES_ARTIFACT.read,
    empty_payload_factory=_empty_adversarial_cases_payload,
    count_key="adversarial_cases",
    id_field="case_id",
)

_WORKFLOW_LEVEL_CANDIDATES_SPEC = OptimizationArtifactSpec(
    filename="workflow_level_optimization_candidates.json",
    artifact_name="workflow_level_optimization_candidates.json",
    expected_schema=_WORKFLOW_LEVEL_CANDIDATES_SCHEMA,
    list_field="candidates",
    reader=WORKFLOW_LEVEL_OPTIMIZATION_CANDIDATES_ARTIFACT.read,
    empty_payload_factory=_empty_workflow_level_candidates_payload,
    count_key="workflow_level",
    id_field="candidate_id",
    requires_ablation_field="requires_ablation",
)

_CANDIDATE_ARTIFACT_SPECS = (
    _PRODUCER_CANDIDATES_SPEC,
    _VERIFIER_RUBRIC_CANDIDATES_SPEC,
    _TOKEN_CANDIDATES_SPEC,
    _ADVERSARIAL_CASES_SPEC,
    _WORKFLOW_LEVEL_CANDIDATES_SPEC,
)


def _ensure_packet_optimization_depth_section(packet_text: str, *, optimization_depth: str) -> str:
    section_lines = [
        "## Optimization Depth",
        "",
        f"Requested depth: `{optimization_depth}`",
        "",
        "Target workflow reruns executed: no  ",
        "Ablations executed: no  ",
        "Refinement executed: no",
    ]
    if optimization_depth == "ablation":
        section_lines.extend(
            [
                "",
                "Ablation mode produced ablation recommendations only. It did not execute ablation runs.",
            ]
        )
    section = "\n".join(section_lines)
    if "## Optimization Depth" in packet_text:
        return packet_text
    if packet_text.endswith("\n"):
        return f"{packet_text}\n{section}\n"
    return f"{packet_text}\n\n{section}\n"
__all__ = ["WorkflowRunTracesToOptimizationCandidates"]
