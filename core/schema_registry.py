"""Canonical schema identifiers shared across runtime and optimizer payloads."""

from __future__ import annotations

RUNTIME_TRACE_SCHEMA = "autoloop.runtime_trace/v1"
GIT_TRACKING_SCHEMA = "autoloop.git_tracking/v1"
WORKFLOW_STATIC_STEP_GRAPH_SCHEMA = "autoloop.workflow_static_step_graph/v1"
WORKFLOW_TOPOLOGY_SCHEMA = "autoloop.workflow_topology/v1"

WORKFLOW_OPTIMIZATION_TRACE_CORPUS_SCHEMA = "autoloop.workflow_optimization.trace_corpus/v1"
WORKFLOW_OPTIMIZATION_SOURCE_MANIFEST_SCHEMA = "autoloop.workflow_optimization.source_manifest/v1"
WORKFLOW_OPTIMIZATION_EXCLUDED_RUN_REPORT_SCHEMA = "autoloop.workflow_optimization.excluded_run_report/v1"
WORKFLOW_REFINEMENT_EVIDENCE_SCHEMA = "autoloop.workflow_refinement_evidence/v1"
WORKFLOW_OPTIMIZATION_STEP_TRACE_METRICS_SCHEMA = "autoloop.workflow_optimization.step_trace_metrics/v1"
WORKFLOW_OPTIMIZATION_STEP_PRIORITY_REPORT_SCHEMA = "autoloop.workflow_optimization.step_priority_report/v1"
WORKFLOW_OPTIMIZATION_FAILURE_SCENARIO_SEEDS_SCHEMA = "autoloop.workflow_optimization.failure_scenario_seeds/v1"
WORKFLOW_OPTIMIZATION_FAILURE_SCENARIOS_SCHEMA = "autoloop.workflow_optimization.failure_scenarios/v1"
WORKFLOW_OPTIMIZATION_SCOPE_SCHEMA = "autoloop.workflow_optimization.scope/v1"

__all__ = [
    "GIT_TRACKING_SCHEMA",
    "RUNTIME_TRACE_SCHEMA",
    "WORKFLOW_OPTIMIZATION_EXCLUDED_RUN_REPORT_SCHEMA",
    "WORKFLOW_OPTIMIZATION_FAILURE_SCENARIO_SEEDS_SCHEMA",
    "WORKFLOW_OPTIMIZATION_FAILURE_SCENARIOS_SCHEMA",
    "WORKFLOW_OPTIMIZATION_SCOPE_SCHEMA",
    "WORKFLOW_OPTIMIZATION_SOURCE_MANIFEST_SCHEMA",
    "WORKFLOW_OPTIMIZATION_STEP_PRIORITY_REPORT_SCHEMA",
    "WORKFLOW_OPTIMIZATION_STEP_TRACE_METRICS_SCHEMA",
    "WORKFLOW_OPTIMIZATION_TRACE_CORPUS_SCHEMA",
    "WORKFLOW_REFINEMENT_EVIDENCE_SCHEMA",
    "WORKFLOW_STATIC_STEP_GRAPH_SCHEMA",
    "WORKFLOW_TOPOLOGY_SCHEMA",
]
