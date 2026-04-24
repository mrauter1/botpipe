"""Run-history-to-failure-modes diagnostic building-block workflow package."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

try:  # pragma: no branch - supports both package and direct repo-root imports
    from autoloop_v3.stdlib import (
        write_selected_workflow_capability_snapshot,
        write_selected_workflow_run_history_snapshot,
    )
    from autoloop_v3.stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from autoloop_v3.stdlib.lifecycle import (
        open_workflow_sessions,
        write_invocation_contract,
        write_publication_receipt,
    )
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from stdlib import write_selected_workflow_capability_snapshot, write_selected_workflow_run_history_snapshot
    from stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt

from workflow import Artifact, FAIL, PairStep, Session, SUCCESS, SystemStep, Workflow
from workflow.primitives import Event, Outcome

from .contracts import (
    DiagnosticScopePayload,
    FailureModeMapPayload,
    FRAME_DIAGNOSTIC_SCOPE_ROUTE_CONTRACTS,
    ImprovementPressurePayload,
    MAP_FAILURE_MODES_ROUTE_CONTRACTS,
    PACKAGE_IMPROVEMENT_PRESSURE_ROUTE_CONTRACTS,
)


_AUTHORITATIVE_PACKAGE_ARTIFACTS = frozenset(
    {
        "improvement_opportunities",
        "improvement_opportunities_summary",
        "diagnostic_next_actions",
        "failure_mode_map",
        "failure_mode_manifest",
        "recurring_weak_points",
    }
)
_ALLOWED_FAILURE_SEVERITIES = frozenset({"high", "medium", "low"})
_ALLOWED_PRIORITY_LEVELS = frozenset({"P1", "P2", "P3"})
_PUBLICATION_BOUNDARY = "diagnostic_publication_only"


class WorkflowRunHistoryToFailureModes(Workflow):
    """Turn one selected workflow's run history into a diagnostic failure-mode package."""

    name = "workflow_run_history_to_failure_modes"

    class State(BaseModel):
        selected_workflow_reference: str = ""
        selected_workflow_name: str | None = None
        task_title: str = ""
        statuses: list[str] = Field(default_factory=list)
        max_runs: int = 25
        sponsor_role: str | None = None
        desired_outcome: str | None = None
        constraints: list[str] = Field(default_factory=list)
        framing_status: str | None = None
        mapping_status: str | None = None
        packaging_status: str | None = None
        evidence_run_ids: list[str] = Field(default_factory=list)
        failure_mode_ids: list[str] = Field(default_factory=list)
        recurring_weak_point_ids: list[str] = Field(default_factory=list)
        ranked_opportunity_ids: list[str] = Field(default_factory=list)
        published: bool = False

    frame_session = Session()
    analysis_session = Session()
    package_session = Session()

    request = Artifact("{run_folder}/request.md")
    framework_architecture_doc = Artifact("{package_folder}/../../docs/architecture.md")
    framework_authoring_doc = Artifact("{package_folder}/../../docs/authoring.md")
    workflow_instructions = Artifact("{package_folder}/../../Workflow_Instructions.md")
    failure_mode_diagnostic_checklist = Artifact("{package_folder}/assets/failure_mode_diagnostic_checklist.md")

    invocation_contract = Artifact("{workflow_folder}/invocation_contract.json")
    selected_workflow_capability = Artifact("{workflow_folder}/selected_workflow_capability.json")
    selected_workflow_run_history = Artifact("{workflow_folder}/selected_workflow_run_history.json")
    diagnostic_scope_brief = Artifact("{workflow_folder}/diagnostic_scope_brief.md")
    run_history_scope = Artifact("{workflow_folder}/run_history_scope.md")
    failure_mode_map = Artifact("{workflow_folder}/failure_mode_map.md")
    failure_mode_manifest = Artifact("{workflow_folder}/failure_mode_manifest.json")
    recurring_weak_points = Artifact("{workflow_folder}/recurring_weak_points.md")
    improvement_opportunities = Artifact("{workflow_folder}/improvement_opportunities.md")
    improvement_opportunities_summary = Artifact("{workflow_folder}/improvement_opportunities.json")
    diagnostic_next_actions = Artifact("{workflow_folder}/diagnostic_next_actions.md")
    failure_mode_diagnostic_receipt = Artifact("{workflow_folder}/failure_mode_diagnostic_receipt.json")

    bootstrap = SystemStep(
        name="bootstrap",
        requires=[request],
        produces={"invocation_contract": invocation_contract},
    )
    capture_run_history_context = SystemStep(
        name="capture_run_history_context",
        requires=[request, invocation_contract],
        produces={
            "selected_workflow_capability": selected_workflow_capability,
            "selected_workflow_run_history": selected_workflow_run_history,
        },
    )
    frame_diagnostic_scope = PairStep(
        name="frame_diagnostic_scope",
        session=frame_session,
        producer="prompts/frame_producer.md",
        verifier="prompts/frame_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            selected_workflow_run_history,
            framework_architecture_doc,
            framework_authoring_doc,
            workflow_instructions,
        ],
        produces={
            "diagnostic_scope_brief": diagnostic_scope_brief,
            "run_history_scope": run_history_scope,
        },
        expected_output_schema=DiagnosticScopePayload,
        route_contracts=FRAME_DIAGNOSTIC_SCOPE_ROUTE_CONTRACTS,
    )
    map_failure_modes = PairStep(
        name="map_failure_modes",
        session=analysis_session,
        producer="prompts/analyze_producer.md",
        verifier="prompts/analyze_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            selected_workflow_run_history,
            diagnostic_scope_brief,
            run_history_scope,
        ],
        produces={
            "failure_mode_map": failure_mode_map,
            "failure_mode_manifest": failure_mode_manifest,
            "recurring_weak_points": recurring_weak_points,
        },
        expected_output_schema=FailureModeMapPayload,
        route_contracts=MAP_FAILURE_MODES_ROUTE_CONTRACTS,
    )
    package_improvement_pressure = PairStep(
        name="package_improvement_pressure",
        session=package_session,
        producer="prompts/package_producer.md",
        verifier="prompts/package_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            selected_workflow_run_history,
            failure_mode_diagnostic_checklist,
            diagnostic_scope_brief,
            run_history_scope,
            failure_mode_map,
            failure_mode_manifest,
            recurring_weak_points,
        ],
        produces={
            "improvement_opportunities": improvement_opportunities,
            "improvement_opportunities_summary": improvement_opportunities_summary,
            "diagnostic_next_actions": diagnostic_next_actions,
        },
        expected_output_schema=ImprovementPressurePayload,
        route_contracts=PACKAGE_IMPROVEMENT_PRESSURE_ROUTE_CONTRACTS,
    )
    publish_failure_mode_package = SystemStep(
        name="publish_failure_mode_package",
        requires=[
            selected_workflow_capability,
            selected_workflow_run_history,
            diagnostic_scope_brief,
            run_history_scope,
            failure_mode_map,
            failure_mode_manifest,
            recurring_weak_points,
            improvement_opportunities,
            improvement_opportunities_summary,
            diagnostic_next_actions,
        ],
        produces={"failure_mode_diagnostic_receipt": failure_mode_diagnostic_receipt},
    )

    entry = bootstrap

    transitions = merge_transitions(
        global_routes(pause_on_outcome_tags("question", "blocked"), failed=FAIL),
        {
            bootstrap: {"inputs_prepared": capture_run_history_context},
            capture_run_history_context: {"run_history_context_captured": frame_diagnostic_scope},
            frame_diagnostic_scope: {
                "diagnostic_scope_framed": map_failure_modes,
                "needs_rework": frame_diagnostic_scope,
                "needs_replan": frame_diagnostic_scope,
            },
            map_failure_modes: {
                "failure_modes_mapped": package_improvement_pressure,
                "needs_rework": map_failure_modes,
                "needs_replan": frame_diagnostic_scope,
            },
            package_improvement_pressure: {
                "improvement_pressure_packaged": publish_failure_mode_package,
                "needs_rework": package_improvement_pressure,
                "needs_replan": map_failure_modes,
            },
            publish_failure_mode_package: {"failure_mode_diagnostics_published": SUCCESS},
        },
    )

    @staticmethod
    def on_bootstrap(state: State, ctx) -> tuple[State, Event]:
        payload = dict(ctx.workflow_params)
        selected_workflow_reference = _require_text(
            payload.get("selected_workflow"),
            "workflow_run_history_to_failure_modes requires workflow parameter 'selected_workflow'",
        )
        task_title = _require_text(
            payload.get("task_title"),
            "workflow_run_history_to_failure_modes requires workflow parameter 'task_title'",
        )
        max_runs = _require_positive_int(
            payload.get("max_runs"),
            "workflow_run_history_to_failure_modes requires workflow parameter 'max_runs' as a positive integer",
        )

        next_state = state.model_copy(
            update={
                "selected_workflow_reference": selected_workflow_reference,
                "selected_workflow_name": None,
                "task_title": task_title,
                "statuses": _normalize_status_filters(payload.get("statuses")),
                "max_runs": max_runs,
                "sponsor_role": _normalize_optional_text(payload.get("sponsor_role")),
                "desired_outcome": _normalize_optional_text(payload.get("desired_outcome")),
                "constraints": _normalize_unique_strings(payload.get("constraints")),
                "framing_status": None,
                "mapping_status": None,
                "packaging_status": None,
                "evidence_run_ids": [],
                "failure_mode_ids": [],
                "recurring_weak_point_ids": [],
                "ranked_opportunity_ids": [],
                "published": False,
            }
        )
        open_workflow_sessions(ctx, "frame_session", "analysis_session", "package_session")
        write_invocation_contract(
            ctx,
            {
                "selected_workflow_reference": next_state.selected_workflow_reference,
                "task_title": next_state.task_title,
                "statuses": next_state.statuses or None,
                "max_runs": next_state.max_runs,
                "sponsor_role": next_state.sponsor_role,
                "desired_outcome": next_state.desired_outcome,
                "constraints": next_state.constraints,
            },
        )
        return next_state, Event("inputs_prepared")

    @staticmethod
    def on_capture_run_history_context(state: State, ctx) -> tuple[State, Event]:
        capability_path = write_selected_workflow_capability_snapshot(ctx, state.selected_workflow_reference)
        history_path = write_selected_workflow_run_history_snapshot(
            ctx,
            state.selected_workflow_reference,
            statuses=state.statuses or None,
            max_runs=state.max_runs,
        )
        if not capability_path.exists():
            raise FileNotFoundError(f"selected workflow capability snapshot was not written at {capability_path}")
        if not history_path.exists():
            raise FileNotFoundError(f"selected workflow run history snapshot was not written at {history_path}")

        capability_snapshot = _read_json(capability_path)
        snapshot_selected_workflow_name = _require_text(
            capability_snapshot.get("selected_workflow_name"),
            "selected_workflow_capability.json must define a non-empty selected_workflow_name",
        )
        selected_capability = _require_mapping(
            capability_snapshot.get("selected_workflow_capability"),
            "selected_workflow_capability.json must define selected_workflow_capability as a JSON object",
        )
        capability_workflow_name = _require_text(
            selected_capability.get("workflow_name"),
            "selected_workflow_capability.json must define selected_workflow_capability.workflow_name",
        )
        if capability_workflow_name != snapshot_selected_workflow_name:
            raise ValueError("selected_workflow_capability.json workflow_name must match selected_workflow_name")

        history_snapshot = _read_json(history_path)
        history_selected_workflow_name = _require_text(
            history_snapshot.get("selected_workflow_name"),
            "selected_workflow_run_history.json must define a non-empty selected_workflow_name",
        )
        if history_selected_workflow_name != snapshot_selected_workflow_name:
            raise ValueError(
                "selected_workflow_run_history.json selected_workflow_name must match selected_workflow_capability.json"
            )
        run_history = _require_mapping(
            history_snapshot.get("selected_workflow_run_history"),
            "selected_workflow_run_history.json must define selected_workflow_run_history as a JSON object",
        )
        captured_statuses = run_history.get("statuses")
        expected_statuses = state.statuses or None
        if captured_statuses is None:
            if expected_statuses is not None:
                raise ValueError("selected_workflow_run_history.json statuses must match the invocation contract")
        else:
            normalized_statuses = _require_string_list(
                captured_statuses,
                "selected_workflow_run_history.json statuses must be a string list when present",
            )
            if normalized_statuses != expected_statuses:
                raise ValueError("selected_workflow_run_history.json statuses must match the invocation contract")
        captured_max_runs = run_history.get("max_runs")
        if captured_max_runs != state.max_runs:
            raise ValueError("selected_workflow_run_history.json max_runs must match the invocation contract")
        evidence_run_ids = _extract_history_run_ids(run_history.get("runs"), allow_empty=True)

        return (
            state.model_copy(
                update={
                    "selected_workflow_name": snapshot_selected_workflow_name,
                    "evidence_run_ids": evidence_run_ids,
                }
            ),
            Event("run_history_context_captured"),
        )

    @staticmethod
    def on_frame_diagnostic_scope(state: State, outcome: Outcome, artifacts):
        del artifacts
        payload = outcome.payload
        selected_workflow_name = payload.get("selected_workflow_name")
        evidence_run_ids = _require_string_list(
            payload.get("evidence_run_ids"),
            "frame verifier payload must define evidence_run_ids as a non-empty string list",
        )
        return state.model_copy(
            update={
                "framing_status": outcome.tag,
                "selected_workflow_name": (
                    selected_workflow_name if isinstance(selected_workflow_name, str) else state.selected_workflow_name
                ),
                "evidence_run_ids": evidence_run_ids,
            }
        )

    @staticmethod
    def on_map_failure_modes(state: State, outcome: Outcome, artifacts):
        del artifacts
        payload = outcome.payload
        selected_workflow_name = payload.get("selected_workflow_name")
        evidence_run_ids = _require_string_list(
            payload.get("evidence_run_ids"),
            "analysis verifier payload must define evidence_run_ids as a non-empty string list",
        )
        failure_mode_ids = _require_string_list(
            payload.get("failure_mode_ids"),
            "analysis verifier payload must define failure_mode_ids as a non-empty string list",
        )
        recurring_weak_point_ids = _require_string_list(
            payload.get("recurring_weak_point_ids"),
            "analysis verifier payload must define recurring_weak_point_ids as a non-empty string list",
        )
        return state.model_copy(
            update={
                "mapping_status": outcome.tag,
                "selected_workflow_name": (
                    selected_workflow_name if isinstance(selected_workflow_name, str) else state.selected_workflow_name
                ),
                "evidence_run_ids": evidence_run_ids,
                "failure_mode_ids": failure_mode_ids,
                "recurring_weak_point_ids": recurring_weak_point_ids,
            }
        )

    @staticmethod
    def on_package_improvement_pressure(state: State, outcome: Outcome, artifacts):
        del artifacts
        payload = outcome.payload
        selected_workflow_name = payload.get("selected_workflow_name")
        evidence_run_ids = _require_string_list(
            payload.get("evidence_run_ids"),
            "package verifier payload must define evidence_run_ids as a non-empty string list",
        )
        failure_mode_ids = _require_string_list(
            payload.get("failure_mode_ids"),
            "package verifier payload must define failure_mode_ids as a non-empty string list",
        )
        ranked_opportunity_ids = _require_string_list(
            payload.get("ranked_opportunity_ids"),
            "package verifier payload must define ranked_opportunity_ids as a non-empty string list",
        )
        return state.model_copy(
            update={
                "packaging_status": outcome.tag,
                "selected_workflow_name": (
                    selected_workflow_name if isinstance(selected_workflow_name, str) else state.selected_workflow_name
                ),
                "evidence_run_ids": evidence_run_ids,
                "failure_mode_ids": failure_mode_ids,
                "ranked_opportunity_ids": ranked_opportunity_ids,
            }
        )

    @staticmethod
    def on_publish_failure_mode_package(state: State, ctx) -> tuple[State, Event]:
        workflow_folder = ctx.workflow_folder
        required_paths = {
            "selected_workflow_capability": workflow_folder / "selected_workflow_capability.json",
            "selected_workflow_run_history": workflow_folder / "selected_workflow_run_history.json",
            "diagnostic_scope_brief": workflow_folder / "diagnostic_scope_brief.md",
            "run_history_scope": workflow_folder / "run_history_scope.md",
            "failure_mode_map": workflow_folder / "failure_mode_map.md",
            "failure_mode_manifest": workflow_folder / "failure_mode_manifest.json",
            "recurring_weak_points": workflow_folder / "recurring_weak_points.md",
            "improvement_opportunities": workflow_folder / "improvement_opportunities.md",
            "improvement_opportunities_summary": workflow_folder / "improvement_opportunities.json",
            "diagnostic_next_actions": workflow_folder / "diagnostic_next_actions.md",
        }
        for artifact_path in required_paths.values():
            if not artifact_path.exists():
                raise FileNotFoundError(f"missing required publication artifact at {artifact_path}")

        capability_snapshot = _read_json(required_paths["selected_workflow_capability"])
        snapshot_selected_workflow_name = _require_text(
            capability_snapshot.get("selected_workflow_name"),
            "selected_workflow_capability.json must define a non-empty selected_workflow_name",
        )
        selected_capability = _require_mapping(
            capability_snapshot.get("selected_workflow_capability"),
            "selected_workflow_capability.json must define selected_workflow_capability as a JSON object",
        )
        capability_workflow_name = _require_text(
            selected_capability.get("workflow_name"),
            "selected_workflow_capability.json must define selected_workflow_capability.workflow_name",
        )
        if capability_workflow_name != snapshot_selected_workflow_name:
            raise ValueError("selected_workflow_capability.json workflow_name must match selected_workflow_name")
        if state.selected_workflow_name is not None and snapshot_selected_workflow_name != state.selected_workflow_name:
            raise ValueError("selected_workflow_capability.json selected_workflow_name must match workflow state")

        history_snapshot = _read_json(required_paths["selected_workflow_run_history"])
        history_selected_workflow_name = _require_text(
            history_snapshot.get("selected_workflow_name"),
            "selected_workflow_run_history.json must define a non-empty selected_workflow_name",
        )
        if history_selected_workflow_name != snapshot_selected_workflow_name:
            raise ValueError(
                "selected_workflow_run_history.json selected_workflow_name must match selected_workflow_capability.json"
            )
        run_history = _require_mapping(
            history_snapshot.get("selected_workflow_run_history"),
            "selected_workflow_run_history.json must define selected_workflow_run_history as a JSON object",
        )
        history_run_count = run_history.get("run_count")
        if not isinstance(history_run_count, int):
            raise ValueError("selected_workflow_run_history.json must define integer run_count")
        if history_run_count <= 0:
            raise ValueError("selected_workflow_run_history.json must contain at least one filtered run")

        history_max_runs = run_history.get("max_runs")
        if history_max_runs != state.max_runs:
            raise ValueError("selected_workflow_run_history.json max_runs must match the invocation contract")
        history_statuses = run_history.get("statuses")
        expected_statuses = state.statuses or None
        if history_statuses is None:
            if expected_statuses is not None:
                raise ValueError("selected_workflow_run_history.json statuses must match the invocation contract")
        else:
            normalized_statuses = _require_string_list(
                history_statuses,
                "selected_workflow_run_history.json statuses must be a string list when present",
            )
            if normalized_statuses != expected_statuses:
                raise ValueError("selected_workflow_run_history.json statuses must match the invocation contract")

        runs = _require_mapping_list(
            run_history.get("runs"),
            "selected_workflow_run_history.json runs must be a JSON array of objects",
        )
        if len(runs) != history_run_count:
            raise ValueError("selected_workflow_run_history.json run_count must match the number of runs")

        evidence_run_ids: list[str] = []
        for index, run in enumerate(runs):
            run_metadata = _require_mapping(
                run.get("run_metadata"),
                f"selected_workflow_run_history.json runs[{index}] must define run_metadata as a JSON object",
            )
            run_id = _require_text(
                run_metadata.get("run_id"),
                "selected_workflow_run_history.json run_metadata must define a non-empty run_id",
            )
            workflow_name = _require_text(
                run_metadata.get("workflow_name"),
                "selected_workflow_run_history.json run_metadata must define a non-empty workflow_name",
            )
            if workflow_name != snapshot_selected_workflow_name:
                raise ValueError(
                    "selected_workflow_run_history.json run_metadata.workflow_name must match selected_workflow_capability.json"
                )
            source_paths = _require_mapping(
                run.get("source_paths"),
                f"selected_workflow_run_history.json runs[{index}] must define source_paths as a JSON object",
            )
            _require_text(
                source_paths.get("request_file"),
                "selected_workflow_run_history.json source_paths must define request_file",
            )
            _require_mapping_list(
                run.get("events"),
                "selected_workflow_run_history.json events must be a JSON array of objects",
            )
            _require_mapping_list(
                run.get("children"),
                "selected_workflow_run_history.json children must be a JSON array of objects",
                min_length=0,
            )
            parent_record = run.get("parent_record")
            if parent_record is not None:
                _require_mapping(
                    parent_record,
                    "selected_workflow_run_history.json parent_record must be a JSON object when present",
                )
            request_text = run.get("request_text")
            if request_text is not None and not isinstance(request_text, str):
                raise ValueError("selected_workflow_run_history.json request_text must be a string when present")
            evidence_run_ids.append(run_id)

        _ensure_unique_strings(
            evidence_run_ids,
            "selected_workflow_run_history.json evidence run IDs must be unique",
        )
        if state.evidence_run_ids and evidence_run_ids != state.evidence_run_ids:
            raise ValueError("selected_workflow_run_history.json evidence run IDs must match workflow state")

        diagnostic_scope_text = _read_required_text(
            required_paths["diagnostic_scope_brief"],
            "diagnostic_scope_brief.md must not be empty",
        )
        if snapshot_selected_workflow_name not in diagnostic_scope_text:
            raise ValueError("diagnostic_scope_brief.md must name the selected workflow")

        run_history_scope_text = _read_required_text(
            required_paths["run_history_scope"],
            "run_history_scope.md must not be empty",
        )
        if not any(run_id in run_history_scope_text for run_id in evidence_run_ids):
            raise ValueError("run_history_scope.md must reference the filtered run IDs")

        manifest = _read_json(required_paths["failure_mode_manifest"])
        manifest_selected_workflow_name = _require_text(
            manifest.get("selected_workflow_name"),
            "failure_mode_manifest.json must define a non-empty selected_workflow_name",
        )
        if manifest_selected_workflow_name != snapshot_selected_workflow_name:
            raise ValueError("failure_mode_manifest.json selected_workflow_name must match selected_workflow_capability.json")
        manifest_evidence_run_ids = _require_string_list(
            manifest.get("evidence_run_ids"),
            "failure_mode_manifest.json must define non-empty evidence_run_ids",
        )
        if manifest_evidence_run_ids != evidence_run_ids:
            raise ValueError("failure_mode_manifest.json evidence_run_ids must match selected_workflow_run_history.json")
        manifest_failure_mode_ids = _require_string_list(
            manifest.get("failure_mode_ids"),
            "failure_mode_manifest.json must define non-empty failure_mode_ids",
        )
        _ensure_unique_strings(manifest_failure_mode_ids, "failure_mode_manifest.json failure_mode_ids must be unique")
        if state.failure_mode_ids and manifest_failure_mode_ids != state.failure_mode_ids:
            raise ValueError("failure_mode_manifest.json failure_mode_ids must match workflow state")
        manifest_recurring_weak_point_ids = _require_string_list(
            manifest.get("recurring_weak_point_ids"),
            "failure_mode_manifest.json must define non-empty recurring_weak_point_ids",
        )
        _ensure_unique_strings(
            manifest_recurring_weak_point_ids,
            "failure_mode_manifest.json recurring_weak_point_ids must be unique",
        )
        if state.recurring_weak_point_ids and manifest_recurring_weak_point_ids != state.recurring_weak_point_ids:
            raise ValueError("failure_mode_manifest.json recurring_weak_point_ids must match workflow state")
        manifest_workflow_name = _require_text(
            manifest.get("workflow_name"),
            "failure_mode_manifest.json must define a non-empty workflow_name",
        )
        if manifest_workflow_name != ctx.workflow_name:
            raise ValueError("failure_mode_manifest.json workflow_name must match the current workflow")

        failure_modes = _require_mapping_list(
            manifest.get("failure_modes"),
            "failure_mode_manifest.json failure_modes must be a JSON array of objects",
        )
        if len(failure_modes) != len(manifest_failure_mode_ids):
            raise ValueError("failure_mode_manifest.json failure_modes must match failure_mode_ids")

        derived_failure_mode_ids: list[str] = []
        for index, mode in enumerate(failure_modes):
            failure_mode_id = _require_text(
                mode.get("failure_mode_id"),
                "failure_mode_manifest.json failure_modes must define non-empty failure_mode_id",
            )
            _require_text(
                mode.get("title"),
                "failure_mode_manifest.json failure_modes must define non-empty title",
            )
            severity = _require_text(
                mode.get("severity"),
                "failure_mode_manifest.json failure_modes must define non-empty severity",
            )
            if severity not in _ALLOWED_FAILURE_SEVERITIES:
                raise ValueError("failure_mode_manifest.json failure mode severity must be high, medium, or low")
            per_mode_run_ids = _require_string_list(
                mode.get("evidence_run_ids"),
                "failure_mode_manifest.json failure_modes must define non-empty evidence_run_ids",
            )
            for run_id in per_mode_run_ids:
                if run_id not in evidence_run_ids:
                    raise ValueError("failure_mode_manifest.json failure_modes must reference only filtered run IDs")
            _require_text(
                mode.get("symptom_pattern"),
                "failure_mode_manifest.json failure_modes must define non-empty symptom_pattern",
            )
            _require_string_list(
                mode.get("likely_causes"),
                "failure_mode_manifest.json failure_modes must define non-empty likely_causes",
            )
            _require_string_list(
                mode.get("supporting_signals"),
                "failure_mode_manifest.json failure_modes must define non-empty supporting_signals",
            )
            derived_failure_mode_ids.append(failure_mode_id)
        if derived_failure_mode_ids != manifest_failure_mode_ids:
            raise ValueError("failure_mode_manifest.json failure_mode_ids must match the failure_modes entries")

        failure_mode_map_text = _read_required_text(
            required_paths["failure_mode_map"],
            "failure_mode_map.md must not be empty",
        )
        for failure_mode_id in manifest_failure_mode_ids:
            if failure_mode_id not in failure_mode_map_text:
                raise ValueError("failure_mode_map.md must reference each failure_mode_id")

        recurring_weak_points_text = _read_required_text(
            required_paths["recurring_weak_points"],
            "recurring_weak_points.md must not be empty",
        )
        for recurring_weak_point_id in manifest_recurring_weak_point_ids:
            if recurring_weak_point_id not in recurring_weak_points_text:
                raise ValueError("recurring_weak_points.md must reference each recurring_weak_point_id")

        improvement_summary = _read_json(required_paths["improvement_opportunities_summary"])
        summary_selected_workflow_name = _require_text(
            improvement_summary.get("selected_workflow_name"),
            "improvement_opportunities.json must define a non-empty selected_workflow_name",
        )
        if summary_selected_workflow_name != snapshot_selected_workflow_name:
            raise ValueError(
                "improvement_opportunities.json selected_workflow_name must match selected_workflow_capability.json"
            )
        summary_evidence_run_ids = _require_string_list(
            improvement_summary.get("evidence_run_ids"),
            "improvement_opportunities.json must define non-empty evidence_run_ids",
        )
        if summary_evidence_run_ids != evidence_run_ids:
            raise ValueError("improvement_opportunities.json evidence_run_ids must match selected_workflow_run_history.json")
        summary_failure_mode_ids = _require_string_list(
            improvement_summary.get("failure_mode_ids"),
            "improvement_opportunities.json must define non-empty failure_mode_ids",
        )
        if summary_failure_mode_ids != manifest_failure_mode_ids:
            raise ValueError("improvement_opportunities.json failure_mode_ids must match failure_mode_manifest.json")
        ranked_opportunity_ids = _require_string_list(
            improvement_summary.get("ranked_opportunity_ids"),
            "improvement_opportunities.json must define non-empty ranked_opportunity_ids",
        )
        _ensure_unique_strings(
            ranked_opportunity_ids,
            "improvement_opportunities.json ranked_opportunity_ids must be unique",
        )
        if state.ranked_opportunity_ids and ranked_opportunity_ids != state.ranked_opportunity_ids:
            raise ValueError("improvement_opportunities.json ranked_opportunity_ids must match workflow state")
        opportunities = _require_mapping_list(
            improvement_summary.get("opportunities"),
            "improvement_opportunities.json opportunities must be a JSON array of objects",
        )
        if len(opportunities) != len(ranked_opportunity_ids):
            raise ValueError("improvement_opportunities.json opportunities must match ranked_opportunity_ids")

        derived_opportunity_ids: list[str] = []
        for opportunity in opportunities:
            opportunity_id = _require_text(
                opportunity.get("opportunity_id"),
                "improvement_opportunities.json opportunities must define non-empty opportunity_id",
            )
            _require_text(
                opportunity.get("title"),
                "improvement_opportunities.json opportunities must define non-empty title",
            )
            priority = _require_text(
                opportunity.get("priority"),
                "improvement_opportunities.json opportunities must define non-empty priority",
            )
            if priority not in _ALLOWED_PRIORITY_LEVELS:
                raise ValueError("improvement_opportunities.json priority must be one of P1, P2, or P3")
            linked_failure_mode_ids = _require_string_list(
                opportunity.get("linked_failure_mode_ids"),
                "improvement_opportunities.json opportunities must define non-empty linked_failure_mode_ids",
            )
            for failure_mode_id in linked_failure_mode_ids:
                if failure_mode_id not in manifest_failure_mode_ids:
                    raise ValueError(
                        "improvement_opportunities.json opportunities must reference only known failure_mode_ids"
                    )
            _require_text(
                opportunity.get("recommended_next_step"),
                "improvement_opportunities.json opportunities must define non-empty recommended_next_step",
            )
            _require_text(
                opportunity.get("why_now"),
                "improvement_opportunities.json opportunities must define non-empty why_now",
            )
            _require_text(
                opportunity.get("expected_impact"),
                "improvement_opportunities.json opportunities must define non-empty expected_impact",
            )
            derived_opportunity_ids.append(opportunity_id)
        if derived_opportunity_ids != ranked_opportunity_ids:
            raise ValueError("improvement_opportunities.json ranked_opportunity_ids must match the opportunities entries")

        authoritative_artifacts = _require_string_list(
            improvement_summary.get("authoritative_artifacts"),
            "improvement_opportunities.json must define non-empty authoritative_artifacts",
        )
        if not _AUTHORITATIVE_PACKAGE_ARTIFACTS.issubset(authoritative_artifacts):
            raise ValueError(
                "improvement_opportunities.json authoritative_artifacts must include improvement_opportunities, improvement_opportunities_summary, diagnostic_next_actions, failure_mode_map, failure_mode_manifest, and recurring_weak_points"
            )
        next_action = _require_text(
            improvement_summary.get("next_action"),
            "improvement_opportunities.json must define a non-empty next_action",
        )
        publication_boundary = _require_text(
            improvement_summary.get("publication_boundary"),
            "improvement_opportunities.json must define a non-empty publication_boundary",
        )
        if publication_boundary != _PUBLICATION_BOUNDARY:
            raise ValueError(
                "improvement_opportunities.json publication_boundary must be diagnostic_publication_only"
            )
        ready_for_publication = improvement_summary.get("ready_for_publication")
        if ready_for_publication is not True:
            raise ValueError("improvement_opportunities.json must confirm ready_for_publication=true")
        summary_workflow_name = _require_text(
            improvement_summary.get("workflow_name"),
            "improvement_opportunities.json must define a non-empty workflow_name",
        )
        if summary_workflow_name != ctx.workflow_name:
            raise ValueError("improvement_opportunities.json workflow_name must match the current workflow")

        improvement_opportunities_text = _read_required_text(
            required_paths["improvement_opportunities"],
            "improvement_opportunities.md must not be empty",
        )
        for opportunity_id in ranked_opportunity_ids:
            if opportunity_id not in improvement_opportunities_text:
                raise ValueError("improvement_opportunities.md must reference each ranked_opportunity_id")

        diagnostic_next_actions_text = _read_required_text(
            required_paths["diagnostic_next_actions"],
            "diagnostic_next_actions.md must not be empty",
        )
        if _PUBLICATION_BOUNDARY not in diagnostic_next_actions_text:
            raise ValueError("diagnostic_next_actions.md must state the diagnostic publication boundary explicitly")
        if any(marker in diagnostic_next_actions_text.lower() for marker in ("auto-run", "automatically run")):
            raise ValueError("diagnostic_next_actions.md must not imply hidden downstream execution")

        write_publication_receipt(
            ctx,
            "failure_mode_diagnostic_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "task_title": state.task_title,
                "sponsor_role": state.sponsor_role,
                "desired_outcome": state.desired_outcome,
                "selected_workflow_reference": state.selected_workflow_reference,
                "selected_workflow_name": snapshot_selected_workflow_name,
                "statuses": expected_statuses,
                "max_runs": state.max_runs,
                "run_count": history_run_count,
                "evidence_run_ids": evidence_run_ids,
                "failure_mode_ids": manifest_failure_mode_ids,
                "recurring_weak_point_ids": manifest_recurring_weak_point_ids,
                "ranked_opportunity_ids": ranked_opportunity_ids,
                "next_action": next_action,
                "publication_boundary": publication_boundary,
                "authoritative_artifacts": authoritative_artifacts,
                "selected_workflow_capability": str(required_paths["selected_workflow_capability"]),
                "selected_workflow_run_history": str(required_paths["selected_workflow_run_history"]),
                "diagnostic_scope_brief": str(required_paths["diagnostic_scope_brief"]),
                "run_history_scope": str(required_paths["run_history_scope"]),
                "failure_mode_map": str(required_paths["failure_mode_map"]),
                "failure_mode_manifest": str(required_paths["failure_mode_manifest"]),
                "recurring_weak_points": str(required_paths["recurring_weak_points"]),
                "improvement_opportunities": str(required_paths["improvement_opportunities"]),
                "improvement_opportunities_summary": str(required_paths["improvement_opportunities_summary"]),
                "diagnostic_next_actions": str(required_paths["diagnostic_next_actions"]),
                "published": True,
            },
        )
        return (
            state.model_copy(
                update={
                    "selected_workflow_name": snapshot_selected_workflow_name,
                    "evidence_run_ids": evidence_run_ids,
                    "failure_mode_ids": manifest_failure_mode_ids,
                    "recurring_weak_point_ids": manifest_recurring_weak_point_ids,
                    "ranked_opportunity_ids": ranked_opportunity_ids,
                    "published": True,
                }
            ),
            Event("failure_mode_diagnostics_published"),
        )

    on_outcome = staticmethod(event_on_outcome_tags("question", "blocked", "failed"))


def _require_text(value: Any, error_message: str) -> str:
    if value is None:
        raise ValueError(error_message)
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(error_message)
    return normalized


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_unique_strings(values: Any) -> list[str]:
    normalized: list[str] = []
    if not isinstance(values, list):
        return normalized
    for value in values:
        candidate = str(value).strip()
        if candidate and candidate not in normalized:
            normalized.append(candidate)
    return normalized


def _normalize_status_filters(values: Any) -> list[str]:
    return sorted(_normalize_unique_strings(values))


def _require_positive_int(value: Any, error_message: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(error_message)
    return value


def _require_string_list(value: Any, error_message: str, *, min_length: int = 1) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(error_message)
    normalized = [_require_text(item, error_message) for item in value]
    if len(normalized) < min_length:
        raise ValueError(error_message)
    return normalized


def _require_mapping(value: Any, error_message: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(error_message)
    return {str(key): item for key, item in value.items()}


def _require_mapping_list(value: Any, error_message: str, *, min_length: int = 1) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(error_message)
    mappings = [_require_mapping(item, error_message) for item in value]
    if len(mappings) < min_length:
        raise ValueError(error_message)
    return mappings


def _extract_history_run_ids(value: Any, *, allow_empty: bool) -> list[str]:
    if value is None and allow_empty:
        return []
    runs = _require_mapping_list(
        value,
        "selected_workflow_run_history.json runs must be a JSON array of objects",
        min_length=0 if allow_empty else 1,
    )
    run_ids: list[str] = []
    for run in runs:
        run_metadata = _require_mapping(
            run.get("run_metadata"),
            "selected_workflow_run_history.json runs must define run_metadata as a JSON object",
        )
        run_ids.append(
            _require_text(
                run_metadata.get("run_id"),
                "selected_workflow_run_history.json run_metadata must define a non-empty run_id",
            )
        )
    return run_ids


def _read_json(path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def _read_required_text(path, error_message: str) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(error_message)
    return text


def _ensure_unique_strings(values: list[str], error_message: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(error_message)


__all__ = ["WorkflowRunHistoryToFailureModes"]
