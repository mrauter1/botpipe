"""Canonical schema identifiers shared across runtime and optimizer payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

RUN_METADATA_SCHEMA = "autoloop.run_metadata/v1"
CHECKPOINT_SCHEMA = "autoloop.checkpoint/v1"
RUNTIME_TRACE_SCHEMA = "autoloop.runtime_trace/v1"
RUNTIME_EVENT_SCHEMA = "autoloop.runtime_event/v1"
CHILD_RUN_SUMMARY_SCHEMA = "autoloop.child_run_summary/v1"
OPERATION_REPLAY_SCHEMA = "autoloop.operation_replay/v1"
GIT_TRACKING_SCHEMA = "autoloop.git_tracking/v1"
WORKFLOW_STATIC_STEP_GRAPH_SCHEMA = "autoloop.workflow_static_step_graph/v1"
WORKFLOW_TOPOLOGY_SCHEMA = "autoloop.workflow_topology/v1"
WORKFLOW_ARTIFACT_CONTRACTS_SCHEMA = "autoloop.workflow_artifact_contracts/v1"
WORKFLOW_PROMPT_REFS_SCHEMA = "autoloop.workflow_prompt_refs/v1"
WORKFLOW_STATE_CONTRACTS_SCHEMA = "autoloop.workflow_state_contracts/v1"
WORKFLOW_SESSION_CONTRACTS_SCHEMA = "autoloop.workflow_session_contracts/v1"

WORKFLOW_OPTIMIZATION_TRACE_CORPUS_SCHEMA = "autoloop.workflow_optimization.trace_corpus/v1"
WORKFLOW_OPTIMIZATION_SOURCE_MANIFEST_SCHEMA = "autoloop.workflow_optimization.source_manifest/v1"
WORKFLOW_OPTIMIZATION_EXCLUDED_RUN_REPORT_SCHEMA = "autoloop.workflow_optimization.excluded_run_report/v1"
WORKFLOW_REFINEMENT_EVIDENCE_SCHEMA = "autoloop.workflow_refinement_evidence/v1"
WORKFLOW_OPTIMIZATION_STEP_TRACE_METRICS_SCHEMA = "autoloop.workflow_optimization.step_trace_metrics/v1"
WORKFLOW_OPTIMIZATION_STEP_PRIORITY_REPORT_SCHEMA = "autoloop.workflow_optimization.step_priority_report/v1"
WORKFLOW_OPTIMIZATION_FAILURE_SCENARIO_SEEDS_SCHEMA = "autoloop.workflow_optimization.failure_scenario_seeds/v1"
WORKFLOW_OPTIMIZATION_FAILURE_SCENARIOS_SCHEMA = "autoloop.workflow_optimization.failure_scenarios/v1"
WORKFLOW_OPTIMIZATION_SCOPE_SCHEMA = "autoloop.workflow_optimization.scope/v1"


def validate_persisted_schema(
    payload: Mapping[str, Any],
    *,
    expected: str,
    artifact_name: str,
) -> str | None:
    """Validate a persisted payload schema.

    Older runtime payloads may omit ``schema`` entirely; readers accept that as the
    legacy format for this cutover. Explicit but unknown schema ids fail loudly.
    """

    schema = payload.get("schema")
    if schema is None:
        return None
    if not isinstance(schema, str) or not schema:
        raise ValueError(f"{artifact_name} must define a non-empty schema string when present")
    if schema != expected:
        raise ValueError(
            f"{artifact_name} uses unsupported schema {schema!r}; expected {expected!r} or a legacy payload without schema"
        )
    return schema

__all__ = [
    "CHECKPOINT_SCHEMA",
    "CHILD_RUN_SUMMARY_SCHEMA",
    "GIT_TRACKING_SCHEMA",
    "OPERATION_REPLAY_SCHEMA",
    "RUN_METADATA_SCHEMA",
    "RUNTIME_EVENT_SCHEMA",
    "RUNTIME_TRACE_SCHEMA",
    "WORKFLOW_ARTIFACT_CONTRACTS_SCHEMA",
    "WORKFLOW_OPTIMIZATION_EXCLUDED_RUN_REPORT_SCHEMA",
    "WORKFLOW_OPTIMIZATION_FAILURE_SCENARIO_SEEDS_SCHEMA",
    "WORKFLOW_OPTIMIZATION_FAILURE_SCENARIOS_SCHEMA",
    "WORKFLOW_OPTIMIZATION_SCOPE_SCHEMA",
    "WORKFLOW_OPTIMIZATION_SOURCE_MANIFEST_SCHEMA",
    "WORKFLOW_OPTIMIZATION_STEP_PRIORITY_REPORT_SCHEMA",
    "WORKFLOW_OPTIMIZATION_STEP_TRACE_METRICS_SCHEMA",
    "WORKFLOW_OPTIMIZATION_TRACE_CORPUS_SCHEMA",
    "WORKFLOW_PROMPT_REFS_SCHEMA",
    "WORKFLOW_REFINEMENT_EVIDENCE_SCHEMA",
    "WORKFLOW_SESSION_CONTRACTS_SCHEMA",
    "WORKFLOW_STATE_CONTRACTS_SCHEMA",
    "WORKFLOW_STATIC_STEP_GRAPH_SCHEMA",
    "WORKFLOW_TOPOLOGY_SCHEMA",
    "validate_persisted_schema",
]
