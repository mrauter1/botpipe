"""Workflow-local output contracts for optimization-candidate generation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

try:  # pragma: no branch - supports both package and direct repo-root imports
    from autoloop_v3.stdlib import JsonArtifactSpec
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from stdlib import JsonArtifactSpec

from workflow import RouteContract


EvidenceStrength = Literal["low", "medium", "high"]
OptimizationDepth = Literal["cheap", "standard", "ablation"]
TokenRiskClass = Literal[
    "safe_compression",
    "risky_compression",
    "semantic_behavior_change_disguised_as_compression",
]
WorkflowLevelCandidateKind = Literal[
    "artifact_handoff_change",
    "route_contract_change",
    "step_split",
    "step_merge",
    "prompt_readme_change",
    "context_rendering_change",
    "session_policy_change",
    "workflow_code_change",
    "workflow_parameter_change",
    "eval_suite_gap",
    "input_quality_gap",
    "operator_process_gap",
    "insufficient_evidence",
]
FailureKind = Literal[
    "producer_failed_verifier",
    "verifier_false_accept",
    "verifier_false_reject",
    "verifier_rubric_ambiguity",
    "route_misuse",
    "needs_rework_loop",
    "needs_replan_loop",
    "blocked_missing_context",
    "artifact_invalid",
    "artifact_missing",
    "token_bloat",
    "downstream_failure_after_local_pass",
    "workflow_handoff_gap",
    "insufficient_evidence",
    "eval_suite_gap",
    "input_quality_gap",
    "operator_process_gap",
]
FailureSeverity = Literal["high", "medium", "low"]


class WorkflowOptimizationScopeArtifactPayload(BaseModel):
    schema: str = Field(min_length=1)
    selected_workflow: str = Field(min_length=1)
    task_title: str = Field(min_length=1)
    run_refs: list[str] = Field(default_factory=list)
    run_statuses: list[str] = Field(default_factory=list)
    route_tags: list[str] = Field(default_factory=list)
    history_limit: int = Field(ge=1)
    top_k_steps: int = Field(ge=1)
    optimization_depth: OptimizationDepth
    include_adversarial_generation: bool
    include_token_optimization: bool
    include_workflow_level_candidates: bool
    focus: str | None = None
    constraints: list[str] = Field(default_factory=list)


class ExcludedRunPayload(BaseModel):
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    run_ref: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ExcludedRunReportArtifactPayload(BaseModel):
    schema: str = Field(min_length=1)
    selected_workflow: str = Field(min_length=1)
    candidate_run_count: int = Field(ge=0)
    excluded_runs: list[ExcludedRunPayload] = Field(default_factory=list)


class RawOutputRefsPayload(BaseModel):
    producer: str | None = None
    verifier: str | None = None
    llm: str | None = None


class StepUsagePayload(BaseModel):
    producer_input_tokens: int = Field(ge=0, default=0)
    producer_output_tokens: int = Field(ge=0, default=0)
    verifier_input_tokens: int = Field(ge=0, default=0)
    verifier_output_tokens: int = Field(ge=0, default=0)
    total_tokens: int = Field(ge=0, default=0)


class TraceCorpusRunPayload(BaseModel):
    run_ref: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    workflow: str = Field(min_length=1)
    run_dir: str = Field(min_length=1)
    run_json_path: str = Field(min_length=1)
    trace_jsonl_path: str = Field(min_length=1)
    git_tracking_jsonl_path: str = Field(min_length=1)
    static_step_graph_path: str = Field(min_length=1)
    terminal: str | None = None
    status: str | None = None
    commit_before_run: str | None = None
    commit_after_run: str | None = None
    eligible_for_optimization: bool


class TraceCorpusObservationPayload(BaseModel):
    observation_id: str = Field(min_length=1)
    run_ref: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    step_name: str = Field(min_length=1)
    step_kind: str = Field(min_length=1)
    route: str = Field(min_length=1)
    raw_output_refs: RawOutputRefsPayload = Field(default_factory=RawOutputRefsPayload)
    usage: StepUsagePayload = Field(default_factory=StepUsagePayload)
    commit_before_step: str | None = None
    commit_after_step: str | None = None
    local_outcome: str = Field(min_length=1)
    downstream_outcome: str = Field(min_length=1)


class WorkflowOptimizationTraceCorpusArtifactPayload(BaseModel):
    schema: str = Field(min_length=1)
    selected_workflow: str = Field(min_length=1)
    candidate_run_count: int = Field(ge=0)
    eligible_run_count: int = Field(ge=0)
    excluded_run_count: int = Field(ge=0)
    excluded_run_report_path: str = Field(min_length=1)
    step_observation_count: int = Field(ge=0)
    runs: list[TraceCorpusRunPayload] = Field(default_factory=list)
    step_observations: list[TraceCorpusObservationPayload] = Field(default_factory=list)


class SourceManifestFilePayload(BaseModel):
    path: str = Field(min_length=1)
    sha256: str = Field(min_length=1)
    bytes: int = Field(ge=0)


class SelectedWorkflowSourceManifestArtifactPayload(BaseModel):
    schema: str = Field(min_length=1)
    selected_workflow: str = Field(min_length=1)
    package_dir: str = Field(min_length=1)
    files: list[SourceManifestFilePayload] = Field(default_factory=list)


class WorkflowOptimizationScorecardArtifactPayload(BaseModel):
    schema: str = Field(min_length=1)
    selected_workflow: str = Field(min_length=1)
    evidence_run_count: int = Field(ge=0)
    excluded_run_count: int = Field(ge=0)
    target_steps_ranked: int = Field(ge=0)
    failure_scenarios: int = Field(ge=0)
    candidate_counts: dict[str, int] = Field(default_factory=dict)
    recommended_next_action: str = Field(min_length=1)
    highest_priority_candidate_ids: list[str] = Field(default_factory=list)
    requires_ablation_before_promotion: bool
    source_mutation_check: dict[str, object]
    summary: str = Field(min_length=1)


class StepTraceMetricPayload(BaseModel):
    step_name: str = Field(min_length=1)
    step_kind: str = Field(min_length=1)
    observed_count: int = Field(ge=0)
    route_counts: dict[str, int] = Field(default_factory=dict)
    producer_failed_verifier_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    needs_rework_count: int = Field(ge=0)
    needs_replan_count: int = Field(ge=0)
    estimated_token_total: int = Field(ge=0)
    token_share: float = Field(ge=0.0, le=1.0)
    downstream_failure_after_pass_count: int = Field(ge=0)
    artifact_centrality: float = Field(ge=0.0, le=1.0)
    route_criticality: float = Field(ge=0.0, le=1.0)


class StepTraceMetricsArtifactPayload(BaseModel):
    schema: str = Field(min_length=1)
    selected_workflow: str = Field(min_length=1)
    steps: list[StepTraceMetricPayload] = Field(default_factory=list)


class LikelyFailureSurfacePayload(BaseModel):
    surface: str = Field(min_length=1)
    probability: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)


class RankedStepPayload(BaseModel):
    step_name: str = Field(min_length=1)
    rank: int = Field(ge=1)
    priority_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_strength: EvidenceStrength
    recommended_first_pass: str = Field(min_length=1)
    secondary_passes: list[str] = Field(default_factory=list)
    why_high_leverage: list[str] = Field(default_factory=list)
    likely_failure_surfaces: list[LikelyFailureSurfacePayload] = Field(default_factory=list)


class NotSelectedStepPayload(BaseModel):
    step_name: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class StepOptimizationPriorityReportArtifactPayload(BaseModel):
    schema: str = Field(min_length=1)
    selected_workflow: str = Field(min_length=1)
    ranking_method: str = Field(min_length=1)
    top_k_steps: int = Field(ge=1)
    ranked_steps: list[RankedStepPayload] = Field(default_factory=list)
    not_selected: list[NotSelectedStepPayload] = Field(default_factory=list)


class WorkflowFailureScenarioArtifactPayload(BaseModel):
    failure_id: str = Field(min_length=1)
    step_name: str = Field(min_length=1)
    failure_kind: FailureKind
    severity: FailureSeverity
    frequency: int = Field(ge=0)
    evidence_observation_ids: list[str] = Field(default_factory=list)
    producer_gap: str | None = None
    verifier_behavior: str | None = None
    likely_fix_surfaces: list[str] = Field(default_factory=list)
    downstream_effect: str | None = None


class WorkflowFailureScenariosArtifactPayload(BaseModel):
    schema: str = Field(min_length=1)
    selected_workflow: str = Field(min_length=1)
    failure_scenarios: list[WorkflowFailureScenarioArtifactPayload] = Field(default_factory=list)


class ProducerPromptOptimizationCandidatePayload(BaseModel):
    candidate_id: str = Field(min_length=1)
    step_name: str = Field(min_length=1)
    target_surface: str = Field(min_length=1)
    target_path: str | None = None
    failure_ids_addressed: list[str] = Field(default_factory=list)
    diagnosis: str = Field(min_length=1)
    proposed_change_summary: str = Field(min_length=1)
    proposed_unified_diff: str | None = None
    proposed_patch_instructions: list[str] = Field(default_factory=list)
    expected_effect: dict[str, str] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_strength: EvidenceStrength
    risks: list[str] = Field(default_factory=list)
    requires_ablation: bool


class ProducerPromptOptimizationCandidatesArtifactPayload(BaseModel):
    schema: str = Field(min_length=1)
    selected_workflow: str = Field(min_length=1)
    target_steps: list[str] = Field(default_factory=list)
    candidates: list[ProducerPromptOptimizationCandidatePayload] = Field(default_factory=list)


class VerifierRubricChangePayload(BaseModel):
    target_surface: str = Field(min_length=1)
    target_path: str | None = None
    route: str | None = None
    change_type: str | None = None
    summary: str = Field(min_length=1)


class VerifierRubricOptimizationCandidatePayload(BaseModel):
    candidate_id: str = Field(min_length=1)
    step_name: str = Field(min_length=1)
    target_surfaces: list[str] = Field(default_factory=list)
    diagnosis: str = Field(min_length=1)
    failure_ids_addressed: list[str] = Field(default_factory=list)
    proposed_changes: list[VerifierRubricChangePayload] = Field(default_factory=list)
    expected_effect: dict[str, str] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_strength: EvidenceStrength
    risks: list[str] = Field(default_factory=list)
    requires_ablation: bool


class VerifierRubricOptimizationCandidatesArtifactPayload(BaseModel):
    schema: str = Field(min_length=1)
    selected_workflow: str = Field(min_length=1)
    target_steps: list[str] = Field(default_factory=list)
    candidates: list[VerifierRubricOptimizationCandidatePayload] = Field(default_factory=list)


class TokenOptimizationCandidatePayload(BaseModel):
    candidate_id: str = Field(min_length=1)
    step_name: str = Field(min_length=1)
    target_surface: str = Field(min_length=1)
    target_path: str | None = None
    compression_kind: str = Field(min_length=1)
    risk_class: TokenRiskClass
    estimated_input_token_reduction: int = Field(ge=0)
    diagnosis: str = Field(min_length=1)
    proposed_change_summary: str = Field(min_length=1)
    quality_risk: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_strength: EvidenceStrength
    requires_ablation: bool


class TokenOptimizationCandidatesArtifactPayload(BaseModel):
    schema: str = Field(min_length=1)
    selected_workflow: str = Field(min_length=1)
    candidates: list[TokenOptimizationCandidatePayload] = Field(default_factory=list)


class AdversarialCaseCandidatePayload(BaseModel):
    case_id: str = Field(min_length=1)
    case_kind: str = Field(min_length=1)
    attack_vector: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    source_failure_ids: list[str] = Field(default_factory=list)
    expected_stress: str = Field(min_length=1)
    expected_route: str = Field(min_length=1)
    expected_artifacts: list[str] = Field(default_factory=list)
    recommended_for_eval_suite: bool
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_strength: EvidenceStrength


class AdversarialCaseCandidatesArtifactPayload(BaseModel):
    schema: str = Field(min_length=1)
    selected_workflow: str = Field(min_length=1)
    cases: list[AdversarialCaseCandidatePayload] = Field(default_factory=list)


class WorkflowLevelOptimizationCandidatePayload(BaseModel):
    candidate_id: str = Field(min_length=1)
    candidate_kind: WorkflowLevelCandidateKind
    diagnosis: str = Field(min_length=1)
    affected_steps: list[str] = Field(default_factory=list)
    proposed_change_summary: str = Field(min_length=1)
    proposed_surfaces: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_strength: EvidenceStrength
    risks: list[str] = Field(default_factory=list)
    requires_refinement_workflow: bool
    requires_ablation: bool


class WorkflowLevelOptimizationCandidatesArtifactPayload(BaseModel):
    schema: str = Field(min_length=1)
    selected_workflow: str = Field(min_length=1)
    candidates: list[WorkflowLevelOptimizationCandidatePayload] = Field(default_factory=list)


class FrameOptimizationPayload(BaseModel):
    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    candidate_run_count: int = Field(ge=0)
    eligible_run_count: int = Field(ge=0)
    excluded_run_count: int = Field(ge=0)
    top_k_steps: int = Field(ge=1)
    route_tags: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class RankTargetsPayload(BaseModel):
    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    ranked_steps: list[str] = Field(default_factory=list)
    ranking_method: str = Field(min_length=1)
    replan_reason: str | None = None


class FailureScenarioPayload(BaseModel):
    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    target_steps: list[str] = Field(default_factory=list)
    failure_ids: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class CandidatePassPayload(BaseModel):
    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    target_steps: list[str] = Field(default_factory=list)
    candidate_ids: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class AdversarialCasesPayload(BaseModel):
    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    case_ids: list[str] = Field(default_factory=list)
    replan_reason: str | None = None


class OptimizationPackagePayload(BaseModel):
    summary: str = Field(min_length=1)
    selected_workflow_name: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(min_length=1)
    highest_priority_candidate_ids: list[str] = Field(default_factory=list)
    recommended_next_action: str = Field(min_length=1)
    requires_ablation_before_promotion: bool
    source_mutation_check_expected: bool
    replan_reason: str | None = None


WORKFLOW_OPTIMIZATION_SCOPE_ARTIFACT = JsonArtifactSpec(
    "workflow_optimization_scope.json",
    WorkflowOptimizationScopeArtifactPayload,
)
EXCLUDED_RUN_REPORT_ARTIFACT = JsonArtifactSpec(
    "excluded_run_report.json",
    ExcludedRunReportArtifactPayload,
)
WORKFLOW_OPTIMIZATION_TRACE_CORPUS_ARTIFACT = JsonArtifactSpec(
    "workflow_optimization_trace_corpus.json",
    WorkflowOptimizationTraceCorpusArtifactPayload,
)
STEP_TRACE_METRICS_ARTIFACT = JsonArtifactSpec(
    "step_trace_metrics.json",
    StepTraceMetricsArtifactPayload,
)
STEP_OPTIMIZATION_PRIORITY_REPORT_ARTIFACT = JsonArtifactSpec(
    "step_optimization_priority_report.json",
    StepOptimizationPriorityReportArtifactPayload,
)
WORKFLOW_FAILURE_SCENARIOS_ARTIFACT = JsonArtifactSpec(
    "workflow_failure_scenarios.json",
    WorkflowFailureScenariosArtifactPayload,
)
PRODUCER_PROMPT_OPTIMIZATION_CANDIDATES_ARTIFACT = JsonArtifactSpec(
    "producer_prompt_optimization_candidates.json",
    ProducerPromptOptimizationCandidatesArtifactPayload,
)
VERIFIER_RUBRIC_OPTIMIZATION_CANDIDATES_ARTIFACT = JsonArtifactSpec(
    "verifier_rubric_optimization_candidates.json",
    VerifierRubricOptimizationCandidatesArtifactPayload,
)
TOKEN_OPTIMIZATION_CANDIDATES_ARTIFACT = JsonArtifactSpec(
    "token_optimization_candidates.json",
    TokenOptimizationCandidatesArtifactPayload,
)
ADVERSARIAL_CASE_CANDIDATES_ARTIFACT = JsonArtifactSpec(
    "adversarial_case_candidates.json",
    AdversarialCaseCandidatesArtifactPayload,
)
WORKFLOW_LEVEL_OPTIMIZATION_CANDIDATES_ARTIFACT = JsonArtifactSpec(
    "workflow_level_optimization_candidates.json",
    WorkflowLevelOptimizationCandidatesArtifactPayload,
)
SELECTED_WORKFLOW_SOURCE_MANIFEST_ARTIFACT = JsonArtifactSpec(
    "selected_workflow_source_manifest.json",
    SelectedWorkflowSourceManifestArtifactPayload,
)
WORKFLOW_OPTIMIZATION_SCORECARD_ARTIFACT = JsonArtifactSpec(
    "workflow_optimization_scorecard.json",
    WorkflowOptimizationScorecardArtifactPayload,
)


FRAME_ROUTE_CONTRACTS = {
    "optimization_scope_framed": RouteContract(
        summary="The selected workflow, trace-evidence boundary, and optimization scope are explicit enough for downstream ranking.",
        required_artifacts=(
            "selected_workflow_capability",
            "selected_workflow_authoring_surface",
            "selected_workflow_decomposition_surface",
            "selected_workflow_source_manifest",
            "workflow_optimization_scope",
            "workflow_optimization_trace_corpus",
            "excluded_run_report",
        ),
        work_item_effect="Locks the optimizer scope on the authoritative workflow and filtered trace corpus without mutating source.",
    ),
    "no_eligible_trace_evidence": RouteContract(
        summary="No eligible Plan-1 observability bundles remained after deterministic filtering, so the workflow should publish a no-op optimization packet.",
        required_artifacts=(
            "selected_workflow_capability",
            "selected_workflow_authoring_surface",
            "selected_workflow_decomposition_surface",
            "selected_workflow_source_manifest",
            "workflow_optimization_scope",
            "workflow_optimization_trace_corpus",
            "excluded_run_report",
        ),
        work_item_effect="Short-circuits the workflow to no-op packaging rather than inventing optimization evidence or failing the run.",
    ),
    "needs_rework": RouteContract(
        summary="The optimization scope still holds, but the framing rationale or evidence interpretation needs local repair.",
        required_artifacts=(
            "workflow_optimization_scope",
            "workflow_optimization_trace_corpus",
            "excluded_run_report",
        ),
        work_item_effect="Keeps the work local to optimizer framing without changing the selected workflow or rerunning the target workflow.",
    ),
}

RANK_TARGETS_ROUTE_CONTRACTS = {
    "targets_ranked": RouteContract(
        summary="The deterministic evidence and framing are strong enough to rank the highest-leverage optimization targets.",
        required_artifacts=("step_trace_metrics", "step_optimization_priority_report"),
        work_item_effect="Advances the workflow into failure-scenario mining for the ranked target set.",
    ),
    "insufficient_evidence": RouteContract(
        summary="The corpus is real but too thin to rank credible targets, so the workflow should package a conservative no-op or low-confidence output.",
        required_artifacts=("step_trace_metrics", "step_optimization_priority_report"),
        work_item_effect="Short-circuits candidate generation without claiming optimization confidence that the evidence does not support.",
    ),
    "needs_rework": RouteContract(
        summary="The same ranking boundary still holds, but the attribution or ranking rationale needs local repair.",
        required_artifacts=("step_trace_metrics", "step_optimization_priority_report"),
        work_item_effect="Keeps ranking local to the same trace corpus and selected workflow boundary.",
    ),
}

MINE_FAILURES_ROUTE_CONTRACTS = {
    "failure_scenarios_mined": RouteContract(
        summary="Failure scenarios are explicit enough to drive producer-side candidate generation.",
        required_artifacts=("workflow_failure_scenarios",),
        work_item_effect="Advances to producer-prompt candidate generation against mined failure surfaces.",
    ),
    "no_failure_scenarios": RouteContract(
        summary="The ranked targets did not yield concrete failure scenarios, so the workflow should skip directly to token analysis.",
        required_artifacts=("workflow_failure_scenarios",),
        work_item_effect="Skips producer-side candidate generation without fabricating failure scenarios.",
    ),
    "needs_rework": RouteContract(
        summary="The same failure-scenario boundary still holds, but the mined scenarios need local repair.",
        required_artifacts=("workflow_failure_scenarios",),
        work_item_effect="Keeps failure analysis local to the same ranked target set.",
    ),
}

OPTIMIZE_PRODUCER_ROUTE_CONTRACTS = {
    "producer_candidates_ready": RouteContract(
        summary="Producer-side optimization candidates are ready for downstream acceptance-function review.",
        required_artifacts=("producer_prompt_optimization_candidates",),
        work_item_effect="Advances to verifier/rubric candidate generation while keeping producer and acceptance surfaces separate.",
    ),
    "producer_pass_not_applicable": RouteContract(
        summary="Producer-side changes are not justified by the evidence, so the workflow should continue to acceptance-function review without forcing producer changes.",
        required_artifacts=("producer_prompt_optimization_candidates",),
        work_item_effect="Preserves candidate-only discipline by explicitly recording that the producer pass was not applicable.",
    ),
    "needs_rework": RouteContract(
        summary="Producer-side candidate generation needs local repair under the same failure-surface boundary.",
        required_artifacts=("producer_prompt_optimization_candidates",),
        work_item_effect="Keeps candidate generation local to producer-facing surfaces only.",
    ),
}

OPTIMIZE_VERIFIER_RUBRIC_ROUTE_CONTRACTS = {
    "verifier_rubric_candidates_ready": RouteContract(
        summary="Acceptance-function candidates are ready for downstream token analysis.",
        required_artifacts=("verifier_rubric_optimization_candidates",),
        work_item_effect="Advances to token analysis while keeping verifier, rubric, and route-contract changes merged on one surface.",
    ),
    "verifier_rubric_pass_not_applicable": RouteContract(
        summary="The evidence does not justify acceptance-function changes, so the workflow should continue without forcing verifier or rubric edits.",
        required_artifacts=("verifier_rubric_optimization_candidates",),
        work_item_effect="Preserves the rule that verifier/rubric changes must be evidence-backed rather than pass-rate chasing.",
    ),
    "needs_rework": RouteContract(
        summary="Acceptance-function candidate generation needs local repair under the same mined-failure boundary.",
        required_artifacts=("verifier_rubric_optimization_candidates",),
        work_item_effect="Keeps verifier/rubric work local to the same ranked target and failure set.",
    ),
}

OPTIMIZE_TOKENS_ROUTE_CONTRACTS = {
    "token_candidates_ready": RouteContract(
        summary="Token-compression candidates are ready and classified by risk for downstream adversarial analysis.",
        required_artifacts=("token_optimization_candidates",),
        work_item_effect="Advances to adversarial-case generation after explicitly classifying safe versus risky compression ideas.",
    ),
    "token_pass_not_applicable": RouteContract(
        summary="Token optimization is disabled or not justified by the current evidence, so the workflow should continue without compression claims.",
        required_artifacts=("token_optimization_candidates",),
        work_item_effect="Skips token compression without silently changing semantics or inventing savings.",
    ),
    "needs_rework": RouteContract(
        summary="Token candidate generation needs local repair while preserving the current optimization boundary.",
        required_artifacts=("token_optimization_candidates",),
        work_item_effect="Keeps token analysis local to compression classification and prompt-shape pressure only.",
    ),
}

ADVERSARIAL_CASES_ROUTE_CONTRACTS = {
    "adversarial_cases_ready": RouteContract(
        summary="Adversarial case candidates are ready for workflow-level analysis and later eval-suite consideration.",
        required_artifacts=("adversarial_case_candidates",),
        work_item_effect="Advances to workflow-level analysis without materializing the cases into an eval suite automatically.",
    ),
    "adversarial_generation_skipped": RouteContract(
        summary="Adversarial generation is disabled, so the workflow should continue directly to workflow-level analysis.",
        required_artifacts=("adversarial_case_candidates",),
        work_item_effect="Keeps the skip explicit rather than implying that adversarial work happened.",
    ),
    "needs_rework": RouteContract(
        summary="Adversarial-case generation needs local repair without widening the optimization boundary.",
        required_artifacts=("adversarial_case_candidates",),
        work_item_effect="Keeps adversarial work local to observed failure modes only.",
    ),
}

WORKFLOW_LEVEL_ROUTE_CONTRACTS = {
    "workflow_level_candidates_ready": RouteContract(
        summary="Workflow-level candidates are ready for packaging alongside any local optimization outputs.",
        required_artifacts=("workflow_level_optimization_candidates",),
        work_item_effect="Advances to packaging after local and cross-step evidence has been made explicit.",
    ),
    "workflow_level_pass_not_applicable": RouteContract(
        summary="The evidence does not justify workflow-level changes, so the workflow should package only local or no-op findings.",
        required_artifacts=("workflow_level_optimization_candidates",),
        work_item_effect="Preserves the rule to prefer local fixes unless workflow-level causes are explicit.",
    ),
    "needs_rework": RouteContract(
        summary="Workflow-level candidate generation needs local repair under the same optimization boundary.",
        required_artifacts=("workflow_level_optimization_candidates",),
        work_item_effect="Keeps workflow-level analysis local and evidence-driven.",
    ),
}

PACKAGE_ROUTE_CONTRACTS = {
    "optimization_packet_ready": RouteContract(
        summary="The optimization packet and scorecard are aligned and ready for deterministic publication checks and receipt writing.",
        required_artifacts=("workflow_optimization_scorecard", "workflow_optimization_packet"),
        work_item_effect="Advances to deterministic publication checks, refinement-evidence writing, and receipt publication without mutating the selected workflow.",
    ),
    "needs_rework": RouteContract(
        summary="The package artifacts need local repair before publication can proceed.",
        required_artifacts=("workflow_optimization_scorecard", "workflow_optimization_packet"),
        work_item_effect="Keeps packaging local and candidate-only without inventing downstream execution.",
    ),
}


__all__ = [
    "ADVERSARIAL_CASES_ROUTE_CONTRACTS",
    "ADVERSARIAL_CASE_CANDIDATES_ARTIFACT",
    "AdversarialCaseCandidatePayload",
    "AdversarialCaseCandidatesArtifactPayload",
    "AdversarialCasesPayload",
    "CandidatePassPayload",
    "EXCLUDED_RUN_REPORT_ARTIFACT",
    "ExcludedRunPayload",
    "ExcludedRunReportArtifactPayload",
    "EvidenceStrength",
    "FRAME_ROUTE_CONTRACTS",
    "FrameOptimizationPayload",
    "MINE_FAILURES_ROUTE_CONTRACTS",
    "FailureScenarioPayload",
    "OPTIMIZE_PRODUCER_ROUTE_CONTRACTS",
    "OPTIMIZE_TOKENS_ROUTE_CONTRACTS",
    "OPTIMIZE_VERIFIER_RUBRIC_ROUTE_CONTRACTS",
    "OptimizationDepth",
    "OptimizationPackagePayload",
    "PACKAGE_ROUTE_CONTRACTS",
    "PRODUCER_PROMPT_OPTIMIZATION_CANDIDATES_ARTIFACT",
    "ProducerPromptOptimizationCandidatePayload",
    "ProducerPromptOptimizationCandidatesArtifactPayload",
    "RANK_TARGETS_ROUTE_CONTRACTS",
    "RawOutputRefsPayload",
    "RankTargetsPayload",
    "SELECTED_WORKFLOW_SOURCE_MANIFEST_ARTIFACT",
    "SelectedWorkflowSourceManifestArtifactPayload",
    "SourceManifestFilePayload",
    "STEP_OPTIMIZATION_PRIORITY_REPORT_ARTIFACT",
    "STEP_TRACE_METRICS_ARTIFACT",
    "StepOptimizationPriorityReportArtifactPayload",
    "StepTraceMetricPayload",
    "StepTraceMetricsArtifactPayload",
    "StepUsagePayload",
    "TraceCorpusObservationPayload",
    "TraceCorpusRunPayload",
    "TOKEN_OPTIMIZATION_CANDIDATES_ARTIFACT",
    "TokenOptimizationCandidatePayload",
    "TokenOptimizationCandidatesArtifactPayload",
    "TokenRiskClass",
    "VERIFIER_RUBRIC_OPTIMIZATION_CANDIDATES_ARTIFACT",
    "VerifierRubricChangePayload",
    "VerifierRubricOptimizationCandidatePayload",
    "VerifierRubricOptimizationCandidatesArtifactPayload",
    "WORKFLOW_FAILURE_SCENARIOS_ARTIFACT",
    "WORKFLOW_LEVEL_ROUTE_CONTRACTS",
    "WORKFLOW_LEVEL_OPTIMIZATION_CANDIDATES_ARTIFACT",
    "WorkflowLevelCandidateKind",
    "WorkflowLevelOptimizationCandidatePayload",
    "WorkflowLevelOptimizationCandidatesArtifactPayload",
    "WORKFLOW_OPTIMIZATION_SCORECARD_ARTIFACT",
    "WORKFLOW_OPTIMIZATION_SCOPE_ARTIFACT",
    "WORKFLOW_OPTIMIZATION_TRACE_CORPUS_ARTIFACT",
    "WorkflowOptimizationScopeArtifactPayload",
    "WorkflowOptimizationScorecardArtifactPayload",
    "WorkflowOptimizationTraceCorpusArtifactPayload",
    "WorkflowFailureScenarioArtifactPayload",
    "WorkflowFailureScenariosArtifactPayload",
]
