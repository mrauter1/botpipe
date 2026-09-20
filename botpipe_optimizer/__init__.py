"""Evidence based optimization for durable Botpipe workflows.

The optimizer deliberately works from journaled operations. A Python workflow's
source manifest says what may run; it is never treated as proof that a path ran.
"""

from .candidates import (
    CandidateEvaluationReport,
    CandidateFile,
    CandidateManifest,
    CandidateWorkspace,
    CommandResult,
    candidate_manifest,
    evaluate_candidate_workspace,
    prepare_candidate_workspace,
    repository_root_for,
    validate_authoritative_sources_unchanged,
)
from .evaluations import (
    CaseKind,
    ValidatedEvalCase,
    ValidatedEvalManifest,
    validate_eval_case_manifest,
    validate_workflow_parameters,
)
from .optimization import (
    OperationMetrics,
    OperationObservation,
    OptimizationCandidate,
    OptimizationReport,
    RunObservation,
    SourceManifest,
    SourceSite,
    build_operation_metrics,
    capture_source_manifest,
    load_run_observation,
    optimize_observations,
    rank_optimization_candidates,
    validate_optimization_candidate,
    validate_optimization_report,
    write_optimization_report,
)
from .parameters import (
    PortfolioReviewParameters,
    SelectedWorkflowTaskFramingParameters,
    SelectedWorkflowTaskFramingWithEvidenceParameters,
    TaskContextParameters,
    TaskFramingParameters,
    TaskFramingWithEvidenceParameters,
)

__all__ = [
    "CandidateEvaluationReport",
    "CandidateFile",
    "CandidateManifest",
    "CandidateWorkspace",
    "CaseKind",
    "CommandResult",
    "OperationMetrics",
    "OperationObservation",
    "OptimizationCandidate",
    "OptimizationReport",
    "PortfolioReviewParameters",
    "RunObservation",
    "SelectedWorkflowTaskFramingParameters",
    "SelectedWorkflowTaskFramingWithEvidenceParameters",
    "SourceManifest",
    "SourceSite",
    "TaskContextParameters",
    "TaskFramingParameters",
    "TaskFramingWithEvidenceParameters",
    "ValidatedEvalCase",
    "ValidatedEvalManifest",
    "build_operation_metrics",
    "candidate_manifest",
    "capture_source_manifest",
    "evaluate_candidate_workspace",
    "load_run_observation",
    "optimize_observations",
    "prepare_candidate_workspace",
    "rank_optimization_candidates",
    "repository_root_for",
    "validate_authoritative_sources_unchanged",
    "validate_eval_case_manifest",
    "validate_optimization_candidate",
    "validate_optimization_report",
    "validate_workflow_parameters",
    "write_optimization_report",
]
