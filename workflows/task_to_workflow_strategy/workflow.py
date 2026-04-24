"""Task-to-workflow-strategy workflow package."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

try:  # pragma: no branch - supports both package and direct repo-root imports
    from autoloop_v3.stdlib import (
        adopt_child_artifacts,
        require_child_workflow_result,
        run_child_workflow,
        write_workflow_portfolio_snapshot,
    )
    from autoloop_v3.stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from autoloop_v3.stdlib.lifecycle import (
        open_workflow_sessions,
        write_invocation_contract,
        write_publication_receipt,
    )
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from stdlib import adopt_child_artifacts, require_child_workflow_result, run_child_workflow, write_workflow_portfolio_snapshot
    from stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt

from workflow import Artifact, FAIL, PairStep, Session, SUCCESS, SystemStep, Workflow
from workflow.primitives import Event, Outcome

from .contracts import (
    FRAME_TASK_ROUTE_CONTRACTS,
    PACKAGE_STRATEGY_ROUTE_CONTRACTS,
    SELECT_STRATEGY_ROUTE_CONTRACTS,
    StrategyPackagePayload,
    StrategySelectionPayload,
    TaskFramingPayload,
)


_STRATEGY_ROUTES = frozenset({"run_existing", "compose", "adapt", "create_new"})
_BUILDER_BASELINE = "workflow_idea_to_workflow_package"
_PORTFOLIO_POSTURES = frozenset({"direct_fit", "compose_needed", "adapt_needed", "material_gap"})


class TaskToWorkflowStrategy(Workflow):
    """Turn an arbitrary task into a durable workflow strategy package."""

    name = "task_to_workflow_strategy"

    class State(BaseModel):
        task_title: str = ""
        sponsor_role: str | None = None
        desired_outcome: str | None = None
        constraints: list[str] = Field(default_factory=list)
        evidence_expectations: list[str] = Field(default_factory=list)
        framing_status: str | None = None
        selection_status: str | None = None
        packaging_status: str | None = None
        selected_strategy: str | None = None
        recommended_workflows: list[str] = Field(default_factory=list)
        published: bool = False

    frame_session = Session()
    selection_session = Session()
    package_session = Session()

    request = Artifact("{run_folder}/request.md")
    framework_architecture_doc = Artifact("{package_folder}/../../docs/architecture.md")
    framework_authoring_doc = Artifact("{package_folder}/../../docs/authoring.md")
    workflow_instructions = Artifact("{package_folder}/../../Workflow_Instructions.md")
    strategy_package_checklist = Artifact("{package_folder}/assets/strategy_package_checklist.md")

    invocation_contract = Artifact("{workflow_folder}/invocation_contract.json")
    workflow_portfolio_snapshot = Artifact("{workflow_folder}/workflow_portfolio_snapshot.json")
    task_strategy_brief = Artifact("{workflow_folder}/task_strategy_brief.md")
    workflow_selection_criteria = Artifact("{workflow_folder}/workflow_selection_criteria.md")
    workflow_candidate_matrix = Artifact("{workflow_folder}/workflow_candidate_matrix.md")
    workflow_gap_analysis = Artifact("{workflow_folder}/workflow_gap_analysis.md")
    candidate_route_posture = Artifact("{workflow_folder}/candidate_route_posture.md")
    candidate_workflow_set = Artifact("{workflow_folder}/candidate_workflow_set.md")
    candidate_workflow_set_summary = Artifact("{workflow_folder}/candidate_workflow_set_summary.json")
    candidate_next_action = Artifact("{workflow_folder}/candidate_next_action.md")
    strategy_decision = Artifact("{workflow_folder}/strategy_decision.md")
    workflow_strategy_package = Artifact("{workflow_folder}/workflow_strategy_package.md")
    strategy_summary = Artifact("{workflow_folder}/strategy_summary.json")
    strategy_next_action = Artifact("{workflow_folder}/strategy_next_action.md")
    strategy_receipt = Artifact("{workflow_folder}/strategy_receipt.json")

    bootstrap = SystemStep(
        name="bootstrap",
        requires=[request],
        produces={"invocation_contract": invocation_contract},
    )
    capture_workflow_portfolio = SystemStep(
        name="capture_workflow_portfolio",
        requires=[request, invocation_contract],
        produces={"workflow_portfolio_snapshot": workflow_portfolio_snapshot},
    )
    frame_task = PairStep(
        name="frame_task",
        session=frame_session,
        producer="prompts/frame_producer.md",
        verifier="prompts/frame_verifier.md",
        requires=[
            request,
            invocation_contract,
            workflow_portfolio_snapshot,
            framework_architecture_doc,
            framework_authoring_doc,
            workflow_instructions,
        ],
        produces={
            "task_strategy_brief": task_strategy_brief,
            "workflow_selection_criteria": workflow_selection_criteria,
        },
        expected_output_schema=TaskFramingPayload,
        route_contracts=FRAME_TASK_ROUTE_CONTRACTS,
    )
    build_candidate_workflow_set = SystemStep(
        name="build_candidate_workflow_set",
        requires=[
            request,
            invocation_contract,
            workflow_portfolio_snapshot,
            task_strategy_brief,
            workflow_selection_criteria,
        ],
        produces={
            "workflow_candidate_matrix": workflow_candidate_matrix,
            "workflow_gap_analysis": workflow_gap_analysis,
            "candidate_route_posture": candidate_route_posture,
            "candidate_workflow_set": candidate_workflow_set,
            "candidate_workflow_set_summary": candidate_workflow_set_summary,
            "candidate_next_action": candidate_next_action,
        },
    )
    select_strategy = PairStep(
        name="select_strategy",
        session=selection_session,
        producer="prompts/select_producer.md",
        verifier="prompts/select_verifier.md",
        requires=[
            request,
            invocation_contract,
            workflow_portfolio_snapshot,
            task_strategy_brief,
            workflow_selection_criteria,
            workflow_candidate_matrix,
            workflow_gap_analysis,
            candidate_route_posture,
            candidate_workflow_set,
            candidate_workflow_set_summary,
            candidate_next_action,
        ],
        produces={"strategy_decision": strategy_decision},
        expected_output_schema=StrategySelectionPayload,
        route_contracts=SELECT_STRATEGY_ROUTE_CONTRACTS,
    )
    package_strategy = PairStep(
        name="package_strategy",
        session=package_session,
        producer="prompts/package_producer.md",
        verifier="prompts/package_verifier.md",
        requires=[
            request,
            invocation_contract,
            workflow_portfolio_snapshot,
            strategy_package_checklist,
            task_strategy_brief,
            workflow_selection_criteria,
            workflow_candidate_matrix,
            workflow_gap_analysis,
            candidate_route_posture,
            candidate_workflow_set,
            candidate_workflow_set_summary,
            candidate_next_action,
            strategy_decision,
        ],
        produces={
            "workflow_strategy_package": workflow_strategy_package,
            "strategy_summary": strategy_summary,
            "strategy_next_action": strategy_next_action,
        },
        expected_output_schema=StrategyPackagePayload,
        route_contracts=PACKAGE_STRATEGY_ROUTE_CONTRACTS,
    )
    publish_strategy = SystemStep(
        name="publish_strategy",
        requires=[
            workflow_portfolio_snapshot,
            workflow_candidate_matrix,
            workflow_gap_analysis,
            strategy_decision,
            workflow_strategy_package,
            strategy_summary,
            strategy_next_action,
        ],
        produces={"strategy_receipt": strategy_receipt},
    )

    entry = bootstrap

    transitions = merge_transitions(
        global_routes(pause_on_outcome_tags("question", "blocked"), failed=FAIL),
        {
            bootstrap: {"inputs_prepared": capture_workflow_portfolio},
            capture_workflow_portfolio: {"portfolio_snapshotted": frame_task},
            frame_task: {
                "task_framed": build_candidate_workflow_set,
                "needs_rework": frame_task,
                "needs_replan": frame_task,
            },
            build_candidate_workflow_set: {"candidate_workflow_set_built": select_strategy},
            select_strategy: {
                "strategy_selected": package_strategy,
                "needs_rework": select_strategy,
                "needs_replan": frame_task,
            },
            package_strategy: {
                "strategy_package_ready": publish_strategy,
                "needs_rework": package_strategy,
                "needs_replan": select_strategy,
            },
            publish_strategy: {"strategy_published": SUCCESS},
        },
    )

    @staticmethod
    def on_bootstrap(state: State, ctx) -> tuple[State, Event]:
        payload = dict(ctx.workflow_params)
        task_title = _require_text(
            payload.get("task_title"),
            "task_to_workflow_strategy requires workflow parameter 'task_title'",
        )
        next_state = state.model_copy(
            update={
                "task_title": task_title,
                "sponsor_role": _normalize_optional_text(payload.get("sponsor_role")),
                "desired_outcome": _normalize_optional_text(payload.get("desired_outcome")),
                "constraints": _normalize_unique_strings(payload.get("constraints")),
                "evidence_expectations": _normalize_unique_strings(payload.get("evidence_expectations")),
                "framing_status": None,
                "selection_status": None,
                "packaging_status": None,
                "selected_strategy": None,
                "recommended_workflows": [],
                "published": False,
            }
        )
        open_workflow_sessions(ctx, "frame_session", "selection_session", "package_session")
        write_invocation_contract(
            ctx,
            {
                "task_title": next_state.task_title,
                "sponsor_role": next_state.sponsor_role,
                "desired_outcome": next_state.desired_outcome,
                "constraints": next_state.constraints,
                "evidence_expectations": next_state.evidence_expectations,
            },
        )
        return next_state, Event("inputs_prepared")

    @staticmethod
    def on_capture_workflow_portfolio(state: State, ctx) -> tuple[State, Event]:
        snapshot_path = write_workflow_portfolio_snapshot(ctx)
        if not snapshot_path.exists():
            raise FileNotFoundError(f"workflow portfolio snapshot was not written at {snapshot_path}")
        summary = _read_json(snapshot_path)
        workflow_count = summary.get("workflow_count")
        if not isinstance(workflow_count, int) or workflow_count < 1:
            raise ValueError("workflow_portfolio_snapshot.json must define a positive workflow_count")
        return state, Event("portfolio_snapshotted")

    @staticmethod
    def on_frame_task(state: State, outcome: Outcome, artifacts):
        del artifacts
        return state.model_copy(update={"framing_status": outcome.tag})

    @staticmethod
    def on_build_candidate_workflow_set(state: State, ctx) -> tuple[State, Event]:
        child_result = run_child_workflow(
            ctx,
            "task_to_candidate_workflow_set",
            message=_read_request_text(ctx),
            parameters={
                "task_title": state.task_title,
                "sponsor_role": state.sponsor_role,
                "desired_outcome": state.desired_outcome,
                "constraints": state.constraints,
                "evidence_expectations": state.evidence_expectations,
            },
        )
        child_last_event = None if child_result.last_event is None else child_result.last_event.tag
        if child_result.status == "paused" and child_last_event in {"question", "blocked"}:
            question = None if child_result.last_event is None else child_result.last_event.question
            return state, Event(child_last_event, question=question)

        require_child_workflow_result(
            child_result,
            status="success",
            last_event="candidate_workflow_set_published",
            required_artifacts=(
                "workflow_candidate_matrix",
                "workflow_gap_analysis",
                "candidate_route_posture",
                "candidate_workflow_set",
                "candidate_workflow_set_summary",
                "candidate_next_action",
            ),
        )
        adopt_child_artifacts(
            ctx,
            child_result,
            mapping={
                "workflow_candidate_matrix": "workflow_candidate_matrix.md",
                "workflow_gap_analysis": "workflow_gap_analysis.md",
                "candidate_route_posture": "candidate_route_posture.md",
                "candidate_workflow_set": "candidate_workflow_set.md",
                "candidate_workflow_set_summary": "candidate_workflow_set_summary.json",
                "candidate_next_action": "candidate_next_action.md",
            },
        )
        return state, Event("candidate_workflow_set_built")

    @staticmethod
    def on_select_strategy(state: State, outcome: Outcome, artifacts):
        del artifacts
        payload = outcome.payload
        selected_strategy = payload.get("selected_strategy")
        recommended_workflows = _normalize_unique_strings(payload.get("recommended_workflows"))
        return state.model_copy(
            update={
                "selection_status": outcome.tag,
                "selected_strategy": (
                    selected_strategy if isinstance(selected_strategy, str) and selected_strategy in _STRATEGY_ROUTES else state.selected_strategy
                ),
                "recommended_workflows": recommended_workflows or state.recommended_workflows,
            }
        )

    @staticmethod
    def on_package_strategy(state: State, outcome: Outcome, artifacts):
        del artifacts
        payload = outcome.payload
        selected_strategy = payload.get("selected_strategy")
        recommended_workflows = _normalize_unique_strings(payload.get("recommended_workflows"))
        return state.model_copy(
            update={
                "packaging_status": outcome.tag,
                "selected_strategy": (
                    selected_strategy if isinstance(selected_strategy, str) and selected_strategy in _STRATEGY_ROUTES else state.selected_strategy
                ),
                "recommended_workflows": recommended_workflows or state.recommended_workflows,
            }
        )

    @staticmethod
    def on_publish_strategy(state: State, ctx) -> tuple[State, Event]:
        workflow_folder = ctx.workflow_folder
        required_paths = {
            "workflow_portfolio_snapshot": workflow_folder / "workflow_portfolio_snapshot.json",
            "workflow_candidate_matrix": workflow_folder / "workflow_candidate_matrix.md",
            "workflow_gap_analysis": workflow_folder / "workflow_gap_analysis.md",
            "candidate_route_posture": workflow_folder / "candidate_route_posture.md",
            "candidate_workflow_set": workflow_folder / "candidate_workflow_set.md",
            "candidate_workflow_set_summary": workflow_folder / "candidate_workflow_set_summary.json",
            "candidate_next_action": workflow_folder / "candidate_next_action.md",
            "strategy_decision": workflow_folder / "strategy_decision.md",
            "workflow_strategy_package": workflow_folder / "workflow_strategy_package.md",
            "strategy_summary": workflow_folder / "strategy_summary.json",
            "strategy_next_action": workflow_folder / "strategy_next_action.md",
        }
        for artifact_path in required_paths.values():
            if not artifact_path.exists():
                raise FileNotFoundError(f"missing required publication artifact at {artifact_path}")

        summary = _read_json(required_paths["strategy_summary"])
        selected_strategy = _require_strategy(
            summary.get("selected_strategy"),
            "strategy_summary.json must define a legal selected_strategy",
        )
        recommended_workflows = _require_string_list(
            summary.get("recommended_workflows"),
            "strategy_summary.json must define non-empty recommended_workflows",
        )
        comparison_candidates = _require_string_list(
            summary.get("comparison_candidates"),
            "strategy_summary.json must define comparison_candidates with at least three workflow names",
        )
        if len(comparison_candidates) < 3:
            raise ValueError("strategy_summary.json must compare at least three candidate workflows")

        builder_baseline_workflow = _require_text(
            summary.get("builder_baseline_workflow"),
            "strategy_summary.json must define a non-empty builder_baseline_workflow",
        )
        if builder_baseline_workflow != _BUILDER_BASELINE:
            raise ValueError(
                f"strategy_summary.json builder_baseline_workflow must be {_BUILDER_BASELINE!r}"
            )
        if builder_baseline_workflow not in comparison_candidates:
            raise ValueError("strategy_summary.json must include the builder baseline in comparison_candidates")

        builder_considered = summary.get("builder_considered")
        if builder_considered is not True:
            raise ValueError("strategy_summary.json must confirm builder_considered=true")

        create_new_required = summary.get("create_new_required")
        if not isinstance(create_new_required, bool):
            raise ValueError("strategy_summary.json must define boolean create_new_required")
        if create_new_required != (selected_strategy == "create_new"):
            raise ValueError(
                "strategy_summary.json create_new_required must match whether selected_strategy is create_new"
            )
        if selected_strategy == "create_new" and _BUILDER_BASELINE not in recommended_workflows:
            raise ValueError(
                "strategy_summary.json must recommend workflow_idea_to_workflow_package when selected_strategy is create_new"
            )
        if selected_strategy == "compose" and len(recommended_workflows) < 2:
            raise ValueError("strategy_summary.json must recommend at least two workflows for compose")

        authoritative_artifacts = _require_string_list(
            summary.get("authoritative_artifacts"),
            "strategy_summary.json must define non-empty authoritative_artifacts",
        )
        rejected_routes = _normalize_unique_strings(summary.get("rejected_routes"))
        next_action = _require_text(
            summary.get("next_action"),
            "strategy_summary.json must define a non-empty next_action",
        )
        ready_for_handoff = summary.get("ready_for_handoff")
        if ready_for_handoff is not True:
            raise ValueError("strategy_summary.json must confirm ready_for_handoff=true")

        candidate_summary = _read_json(required_paths["candidate_workflow_set_summary"])
        candidate_comparison_candidates = _require_string_list(
            candidate_summary.get("comparison_candidates"),
            "candidate_workflow_set_summary.json must define comparison_candidates",
        )
        if comparison_candidates != candidate_comparison_candidates:
            raise ValueError(
                "strategy_summary.json comparison_candidates must match candidate_workflow_set_summary.json"
            )
        candidate_recommended_workflows = _require_string_list(
            candidate_summary.get("recommended_candidate_workflows"),
            "candidate_workflow_set_summary.json must define recommended_candidate_workflows",
        )
        if not set(recommended_workflows).issubset(candidate_recommended_workflows):
            raise ValueError(
                "strategy_summary.json recommended_workflows must be drawn from candidate_workflow_set_summary.json"
            )
        candidate_portfolio_posture = _require_portfolio_posture(
            candidate_summary.get("portfolio_posture"),
            "candidate_workflow_set_summary.json must define a legal portfolio_posture",
        )
        expected_strategy = _strategy_for_portfolio_posture(candidate_portfolio_posture)
        if selected_strategy != expected_strategy:
            raise ValueError(
                "strategy_summary.json selected_strategy must align with candidate_workflow_set_summary.json portfolio_posture"
            )
        child_ready = candidate_summary.get("ready_for_strategy_selection")
        if child_ready is not True:
            raise ValueError(
                "candidate_workflow_set_summary.json must confirm ready_for_strategy_selection=true"
            )

        if state.selected_strategy is not None and selected_strategy != state.selected_strategy:
            raise ValueError("strategy_summary.json selected_strategy must match workflow state")
        if state.recommended_workflows and recommended_workflows != state.recommended_workflows:
            raise ValueError("strategy_summary.json recommended_workflows must match workflow state")

        write_publication_receipt(
            ctx,
            "strategy_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "task_title": state.task_title,
                "sponsor_role": state.sponsor_role,
                "desired_outcome": state.desired_outcome,
                "selected_strategy": selected_strategy,
                "recommended_workflows": recommended_workflows,
                "comparison_candidates": comparison_candidates,
                "builder_baseline_workflow": builder_baseline_workflow,
                "rejected_routes": rejected_routes,
                "next_action": next_action,
                "authoritative_artifacts": authoritative_artifacts,
                "workflow_portfolio_snapshot": str(required_paths["workflow_portfolio_snapshot"]),
                "strategy_summary": str(required_paths["strategy_summary"]),
                "workflow_strategy_package": str(required_paths["workflow_strategy_package"]),
                "strategy_next_action": str(required_paths["strategy_next_action"]),
                "published": True,
            },
        )
        return state.model_copy(
            update={
                "selected_strategy": selected_strategy,
                "recommended_workflows": recommended_workflows,
                "published": True,
            }
        ), Event("strategy_published")

    on_outcome = staticmethod(event_on_outcome_tags("question", "blocked", "failed"))


def _require_text(value, error_message: str) -> str:
    if value is None:
        raise ValueError(error_message)
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(error_message)
    return normalized


def _normalize_optional_text(value) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_unique_strings(raw_value) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, list):
        candidates = raw_value
    else:
        candidates = [raw_value]
    normalized: list[str] = []
    for value in candidates:
        candidate = str(value).strip()
        if candidate and candidate not in normalized:
            normalized.append(candidate)
    return normalized


def _require_strategy(value, error_message: str) -> str:
    strategy = _require_text(value, error_message)
    if strategy not in _STRATEGY_ROUTES:
        raise ValueError(error_message)
    return strategy


def _require_portfolio_posture(value, error_message: str) -> str:
    posture = _require_text(value, error_message)
    if posture not in _PORTFOLIO_POSTURES:
        raise ValueError(error_message)
    return posture


def _require_string_list(value, error_message: str) -> list[str]:
    normalized = _normalize_unique_strings(value)
    if not normalized:
        raise ValueError(error_message)
    return normalized


def _strategy_for_portfolio_posture(portfolio_posture: str) -> str:
    mapping = {
        "direct_fit": "run_existing",
        "compose_needed": "compose",
        "adapt_needed": "adapt",
        "material_gap": "create_new",
    }
    return mapping[portfolio_posture]


def _read_request_text(ctx) -> str:
    return (ctx.run_folder / "request.md").read_text(encoding="utf-8")


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))
