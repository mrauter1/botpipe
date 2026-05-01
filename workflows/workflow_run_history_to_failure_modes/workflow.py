"""Run-history-to-failure-modes diagnostic building-block workflow package."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from typing import Any

from pydantic import BaseModel, Field

from autoloop_optimizer import (
    capture_selected_workflow,
    write_selected_workflow_capability_snapshot,
    write_selected_workflow_run_history_snapshot,
)
from autoloop.stdlib import (
    read_json_object,
    read_required_text,
    require_existing_artifact_paths,
    require_mapping,
    require_mapping_list,
    require_non_empty_string,
    require_positive_int,
    require_string_list,
    require_true_flag,
    require_unique_values,
    validate_authoritative_artifact_subset,
    validate_no_hidden_execution_signal,
    validate_publication_boundary,
    validate_selected_workflow_artifact_alignment,
    validate_selected_workflow_capability_snapshot,
)
from autoloop.stdlib.control import event_on_outcome_tags
from autoloop.stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt

from autoloop import Event, FAIL, FINISH, Outcome, Prompt, Session, Workflow, produce_verify_step, python_step
from autoloop.core import Artifact

from .contracts import (
    DiagnosticScopePayload,
    FAILURE_MODE_MANIFEST_ARTIFACT,
    FailureModeMapPayload,
    FRAME_DIAGNOSTIC_SCOPE_ROUTE_CONTRACTS,
    IMPROVEMENT_OPPORTUNITIES_SUMMARY_ARTIFACT,
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

    frame_diagnostic_scope = produce_verify_step(
        producer_prompt=Prompt.file("prompts/frame_producer.md"),
        verifier_prompt=Prompt.file("prompts/frame_verifier.md"),
        session=frame_session,
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            selected_workflow_run_history,
            framework_architecture_doc,
            framework_authoring_doc,
            workflow_instructions,
        ],
        producer_writes=[diagnostic_scope_brief, run_history_scope],
        control_schema=DiagnosticScopePayload,
        routes=FRAME_DIAGNOSTIC_SCOPE_ROUTE_CONTRACTS,
    )
    map_failure_modes = produce_verify_step(
        producer_prompt=Prompt.file("prompts/analyze_producer.md"),
        verifier_prompt=Prompt.file("prompts/analyze_verifier.md"),
        session=analysis_session,
        requires=[
            request,
            invocation_contract,
            selected_workflow_capability,
            selected_workflow_run_history,
            diagnostic_scope_brief,
            run_history_scope,
        ],
        producer_writes=[failure_mode_map, failure_mode_manifest, recurring_weak_points],
        control_schema=FailureModeMapPayload,
        routes=MAP_FAILURE_MODES_ROUTE_CONTRACTS,
    )
    package_improvement_pressure = produce_verify_step(
        producer_prompt=Prompt.file("prompts/package_producer.md"),
        verifier_prompt=Prompt.file("prompts/package_verifier.md"),
        session=package_session,
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
        producer_writes=[improvement_opportunities, improvement_opportunities_summary, diagnostic_next_actions],
        control_schema=ImprovementPressurePayload,
        routes=PACKAGE_IMPROVEMENT_PRESSURE_ROUTE_CONTRACTS,
    )
    @python_step(
        name="bootstrap",
        requires=[request],
        writes=[invocation_contract],
        routes={"inputs_prepared": "capture_run_history_context"},
    )
    def bootstrap(state: State, ctx):
        params = ctx.params

        next_state = state.model_copy(
            update={
                "selected_workflow_reference": params.selected_workflow,
                "selected_workflow_name": None,
                "task_title": params.task_title,
                "statuses": list(params.statuses),
                "max_runs": params.max_runs,
                "sponsor_role": params.sponsor_role,
                "desired_outcome": params.desired_outcome,
                "constraints": list(params.constraints),
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

    @python_step(
        name="capture_run_history_context",
        requires=[request, invocation_contract],
        writes=[selected_workflow_capability, selected_workflow_run_history],
        routes={"run_history_context_captured": "frame_diagnostic_scope"},
    )
    def capture_run_history_context(state: State, ctx):
        capture = capture_selected_workflow(ctx, state.selected_workflow_reference)
        capability_path = write_selected_workflow_capability_snapshot(ctx, state.selected_workflow_reference)
        history_path = write_selected_workflow_run_history_snapshot(
            ctx,
            state.selected_workflow_reference,
            statuses=state.statuses or None,
            max_runs=state.max_runs,
        )
        required_paths = require_existing_artifact_paths(
            {
                "selected_workflow_capability": capability_path,
                "selected_workflow_run_history": history_path,
            }
        )

        history_snapshot = _read_json(required_paths["selected_workflow_run_history"])
        validate_selected_workflow_artifact_alignment(
            history_snapshot,
            artifact_name="selected_workflow_run_history.json",
            expected_selected_workflow_name=capture.selected_workflow_name,
            expected_artifact_name="selected_workflow_capability.json",
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
                    "selected_workflow_name": capture.selected_workflow_name,
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

    @python_step(
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
        writes=[failure_mode_diagnostic_receipt],
        routes={"failure_mode_diagnostics_published": FINISH},
    )
    def publish_failure_mode_package(state: State, ctx):
        workflow_folder = ctx.workflow_folder
        required_paths = require_existing_artifact_paths(
            {
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
        )

        capability_snapshot = _read_json(required_paths["selected_workflow_capability"])
        snapshot_selected_workflow_name, _ = validate_selected_workflow_capability_snapshot(
            capability_snapshot,
            expected_selected_workflow_name=state.selected_workflow_name,
            expected_label="workflow state",
        )

        history_snapshot = _read_json(required_paths["selected_workflow_run_history"])
        validate_selected_workflow_artifact_alignment(
            history_snapshot,
            artifact_name="selected_workflow_run_history.json",
            expected_selected_workflow_name=snapshot_selected_workflow_name,
            expected_artifact_name="selected_workflow_capability.json",
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

        require_unique_values(
            evidence_run_ids,
            error_message="selected_workflow_run_history.json evidence run IDs must be unique",
        )
        if state.evidence_run_ids and evidence_run_ids != state.evidence_run_ids:
            raise ValueError("selected_workflow_run_history.json evidence run IDs must match workflow state")

        diagnostic_scope_text = read_required_text(
            required_paths["diagnostic_scope_brief"],
            "diagnostic_scope_brief.md must not be empty",
        )
        if snapshot_selected_workflow_name not in diagnostic_scope_text:
            raise ValueError("diagnostic_scope_brief.md must name the selected workflow")

        run_history_scope_text = read_required_text(
            required_paths["run_history_scope"],
            "run_history_scope.md must not be empty",
        )
        if not any(run_id in run_history_scope_text for run_id in evidence_run_ids):
            raise ValueError("run_history_scope.md must reference the filtered run IDs")

        manifest = FAILURE_MODE_MANIFEST_ARTIFACT.read(required_paths["failure_mode_manifest"])
        validate_selected_workflow_artifact_alignment(
            manifest.model_dump(mode="python"),
            artifact_name="failure_mode_manifest.json",
            expected_selected_workflow_name=snapshot_selected_workflow_name,
            expected_artifact_name="selected_workflow_capability.json",
        )
        manifest_evidence_run_ids = _require_string_list(
            manifest.evidence_run_ids,
            "failure_mode_manifest.json must define non-empty evidence_run_ids",
        )
        if manifest_evidence_run_ids != evidence_run_ids:
            raise ValueError("failure_mode_manifest.json evidence_run_ids must match selected_workflow_run_history.json")
        manifest_failure_mode_ids = _require_string_list(
            manifest.failure_mode_ids,
            "failure_mode_manifest.json must define non-empty failure_mode_ids",
        )
        require_unique_values(
            manifest_failure_mode_ids,
            error_message="failure_mode_manifest.json failure_mode_ids must be unique",
        )
        if state.failure_mode_ids and manifest_failure_mode_ids != state.failure_mode_ids:
            raise ValueError("failure_mode_manifest.json failure_mode_ids must match workflow state")
        manifest_recurring_weak_point_ids = _require_string_list(
            manifest.recurring_weak_point_ids,
            "failure_mode_manifest.json must define non-empty recurring_weak_point_ids",
        )
        require_unique_values(
            manifest_recurring_weak_point_ids,
            error_message="failure_mode_manifest.json recurring_weak_point_ids must be unique",
        )
        if state.recurring_weak_point_ids and manifest_recurring_weak_point_ids != state.recurring_weak_point_ids:
            raise ValueError("failure_mode_manifest.json recurring_weak_point_ids must match workflow state")
        manifest_workflow_name = _require_text(
            manifest.workflow_name,
            "failure_mode_manifest.json must define a non-empty workflow_name",
        )
        if manifest_workflow_name != ctx.workflow_name:
            raise ValueError("failure_mode_manifest.json workflow_name must match the current workflow")

        failure_modes = [entry.model_dump(mode="python") for entry in manifest.failure_modes]
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

        failure_mode_map_text = read_required_text(
            required_paths["failure_mode_map"],
            "failure_mode_map.md must not be empty",
        )
        for failure_mode_id in manifest_failure_mode_ids:
            if failure_mode_id not in failure_mode_map_text:
                raise ValueError("failure_mode_map.md must reference each failure_mode_id")

        recurring_weak_points_text = read_required_text(
            required_paths["recurring_weak_points"],
            "recurring_weak_points.md must not be empty",
        )
        for recurring_weak_point_id in manifest_recurring_weak_point_ids:
            if recurring_weak_point_id not in recurring_weak_points_text:
                raise ValueError("recurring_weak_points.md must reference each recurring_weak_point_id")

        improvement_summary = IMPROVEMENT_OPPORTUNITIES_SUMMARY_ARTIFACT.read(
            required_paths["improvement_opportunities_summary"]
        )
        validate_selected_workflow_artifact_alignment(
            improvement_summary.model_dump(mode="python"),
            artifact_name="improvement_opportunities.json",
            expected_selected_workflow_name=snapshot_selected_workflow_name,
            expected_artifact_name="selected_workflow_capability.json",
        )
        summary_evidence_run_ids = _require_string_list(
            improvement_summary.evidence_run_ids,
            "improvement_opportunities.json must define non-empty evidence_run_ids",
        )
        if summary_evidence_run_ids != evidence_run_ids:
            raise ValueError("improvement_opportunities.json evidence_run_ids must match selected_workflow_run_history.json")
        summary_failure_mode_ids = _require_string_list(
            improvement_summary.failure_mode_ids,
            "improvement_opportunities.json must define non-empty failure_mode_ids",
        )
        if summary_failure_mode_ids != manifest_failure_mode_ids:
            raise ValueError("improvement_opportunities.json failure_mode_ids must match failure_mode_manifest.json")
        ranked_opportunity_ids = _require_string_list(
            improvement_summary.ranked_opportunity_ids,
            "improvement_opportunities.json must define non-empty ranked_opportunity_ids",
        )
        require_unique_values(
            ranked_opportunity_ids,
            error_message="improvement_opportunities.json ranked_opportunity_ids must be unique",
        )
        if state.ranked_opportunity_ids and ranked_opportunity_ids != state.ranked_opportunity_ids:
            raise ValueError("improvement_opportunities.json ranked_opportunity_ids must match workflow state")
        opportunities = [entry.model_dump(mode="python") for entry in improvement_summary.opportunities]
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

        authoritative_artifacts = validate_authoritative_artifact_subset(
            improvement_summary.authoritative_artifacts,
            required_artifacts=_AUTHORITATIVE_PACKAGE_ARTIFACTS,
            missing_error_message="improvement_opportunities.json must define non-empty authoritative_artifacts",
            subset_error_message="improvement_opportunities.json authoritative_artifacts must include improvement_opportunities, improvement_opportunities_summary, diagnostic_next_actions, failure_mode_map, failure_mode_manifest, and recurring_weak_points",
        )
        next_action = _require_text(
            improvement_summary.next_action,
            "improvement_opportunities.json must define a non-empty next_action",
        )
        publication_boundary = validate_publication_boundary(
            improvement_summary.publication_boundary,
            expected_boundary=_PUBLICATION_BOUNDARY,
            missing_error_message="improvement_opportunities.json must define a non-empty publication_boundary",
            mismatch_error_message="improvement_opportunities.json publication_boundary must be diagnostic_publication_only",
        )
        require_true_flag(
            improvement_summary.ready_for_publication,
            "improvement_opportunities.json must confirm ready_for_publication=true",
        )
        summary_workflow_name = _require_text(
            improvement_summary.workflow_name,
            "improvement_opportunities.json must define a non-empty workflow_name",
        )
        if summary_workflow_name != ctx.workflow_name:
            raise ValueError("improvement_opportunities.json workflow_name must match the current workflow")

        improvement_opportunities_text = read_required_text(
            required_paths["improvement_opportunities"],
            "improvement_opportunities.md must not be empty",
        )
        for opportunity_id in ranked_opportunity_ids:
            if opportunity_id not in improvement_opportunities_text:
                raise ValueError("improvement_opportunities.md must reference each ranked_opportunity_id")

        diagnostic_next_actions_text = read_required_text(
            required_paths["diagnostic_next_actions"],
            "diagnostic_next_actions.md must not be empty",
        )
        if _PUBLICATION_BOUNDARY not in diagnostic_next_actions_text:
            raise ValueError("diagnostic_next_actions.md must state the diagnostic publication boundary explicitly")
        validate_no_hidden_execution_signal(
            diagnostic_next_actions_text,
            "diagnostic_next_actions.md must not imply hidden downstream execution",
        )

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

    entry = bootstrap

    on_outcome = staticmethod(event_on_outcome_tags("question", "blocked", "failed"))


_require_text = partial(require_non_empty_string, coerce=True)
_require_positive_int = require_positive_int
_require_string_list = partial(require_string_list, coerce=True)
_require_mapping = require_mapping
_require_mapping_list = require_mapping_list
_read_json = read_json_object


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


__all__ = ["WorkflowRunHistoryToFailureModes"]
