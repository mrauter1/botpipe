"""Task-to-workflow-strategy workflow package."""

from __future__ import annotations

from pydantic import BaseModel, Field

from botlane_optimizer import write_workflow_portfolio_snapshot
from botlane.stdlib import (
    adopt_child_artifacts,
    normalize_unique_strings,
    read_json_object,
    require_child_workflow_result,
    require_non_empty_string,
    require_string_list,
    run_child_workflow,
)
from botlane.stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt

from botlane import Event, FINISH, Outcome, Prompt, Session, Workflow, produce_verify_step, python_step
from botlane.core import Artifact

from .contracts import (
    CANDIDATE_WORKFLOW_SET_SUMMARY_ARTIFACT,
    FRAME_TASK_ROUTE_CONTRACTS,
    PACKAGE_STRATEGY_ROUTE_CONTRACTS,
    SELECT_STRATEGY_ROUTE_CONTRACTS,
    STRATEGY_SUMMARY_ARTIFACT,
    StrategyPackagePayload,
    StrategySelectionPayload,
    TaskFramingPayload,
)


_STRATEGY_ROUTES = frozenset({"run_existing", "compose", "adapt", "create_new"})
_BUILDER_BASELINE = "workflow_idea_to_workflow_package"
_ADAPTATION_BUILDING_BLOCK = "candidate_workflow_to_adapted_execution_plan"
_PORTFOLIO_POSTURES = frozenset({"direct_fit", "compose_needed", "adapt_needed", "material_gap"})


def _after_frame_task(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    ctx.state.framing_status = outcome.tag
    return None


def _after_select_strategy(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    selected_strategy = payload.get("selected_strategy")
    recommended_workflows = normalize_unique_strings(
        payload.get("recommended_workflows"),
        allow_scalar=True,
    )
    ctx.state.selection_status = outcome.tag
    if isinstance(selected_strategy, str) and selected_strategy in _STRATEGY_ROUTES:
        ctx.state.selected_strategy = selected_strategy
    if recommended_workflows:
        ctx.state.recommended_workflows = recommended_workflows
    return None


def _after_package_strategy(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    payload = outcome.payload
    selected_strategy = payload.get("selected_strategy")
    recommended_workflows = normalize_unique_strings(
        payload.get("recommended_workflows"),
        allow_scalar=True,
    )
    ctx.state.packaging_status = outcome.tag
    if isinstance(selected_strategy, str) and selected_strategy in _STRATEGY_ROUTES:
        ctx.state.selected_strategy = selected_strategy
    if recommended_workflows:
        ctx.state.recommended_workflows = recommended_workflows
    return None


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
    framework_architecture_doc = Artifact("{root}/docs/architecture.md")
    framework_authoring_doc = Artifact("{root}/docs/authoring.md")
    workflow_instructions = Artifact("{root}/Workflow_Instructions.md")
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

    frame_task = produce_verify_step(
        producer_prompt=Prompt.file("prompts/frame_producer.md"),
        verifier_prompt=Prompt.file("prompts/frame_verifier.md"),
        session=frame_session,
        requires=[
            request,
            invocation_contract,
            workflow_portfolio_snapshot,
            framework_architecture_doc,
            framework_authoring_doc,
            workflow_instructions,
        ],
        producer_writes=[task_strategy_brief, workflow_selection_criteria],
        control_schema=TaskFramingPayload,
        routes=FRAME_TASK_ROUTE_CONTRACTS,
        after_verifier=_after_frame_task,
    )
    select_strategy = produce_verify_step(
        producer_prompt=Prompt.file("prompts/select_producer.md"),
        verifier_prompt=Prompt.file("prompts/select_verifier.md"),
        session=selection_session,
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
        producer_writes=[strategy_decision],
        control_schema=StrategySelectionPayload,
        routes=SELECT_STRATEGY_ROUTE_CONTRACTS,
        after_verifier=_after_select_strategy,
    )
    package_strategy = produce_verify_step(
        producer_prompt=Prompt.file("prompts/package_producer.md"),
        verifier_prompt=Prompt.file("prompts/package_verifier.md"),
        session=package_session,
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
        producer_writes=[workflow_strategy_package, strategy_summary, strategy_next_action],
        control_schema=StrategyPackagePayload,
        routes=PACKAGE_STRATEGY_ROUTE_CONTRACTS,
        after_verifier=_after_package_strategy,
    )

    @python_step(
        name="bootstrap",
        requires=[request],
        writes=[invocation_contract],
        routes={"inputs_prepared": "capture_workflow_portfolio"},
    )
    def bootstrap(ctx):
        params = ctx.params
        next_state = ctx.state.model_copy(
            update={
                "task_title": params.task_title,
                "sponsor_role": params.sponsor_role,
                "desired_outcome": params.desired_outcome,
                "constraints": list(params.constraints),
                "evidence_expectations": list(params.evidence_expectations),
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
        ctx.state = next_state
        return "inputs_prepared"

    @python_step(
        name="capture_workflow_portfolio",
        requires=[request, invocation_contract],
        writes=[workflow_portfolio_snapshot],
        routes={"portfolio_snapshotted": "frame_task"},
    )
    def capture_workflow_portfolio(ctx):
        snapshot_path = write_workflow_portfolio_snapshot(ctx)
        if not snapshot_path.exists():
            raise FileNotFoundError(f"workflow portfolio snapshot was not written at {snapshot_path}")
        summary = read_json_object(snapshot_path)
        workflow_count = summary.get("workflow_count")
        if not isinstance(workflow_count, int) or workflow_count < 1:
            raise ValueError("workflow_portfolio_snapshot.json must define a positive workflow_count")
        return "portfolio_snapshotted"

    @python_step(
        name="build_candidate_workflow_set",
        requires=[
            request,
            invocation_contract,
            workflow_portfolio_snapshot,
            task_strategy_brief,
            workflow_selection_criteria,
        ],
        writes=[
            workflow_candidate_matrix,
            workflow_gap_analysis,
            candidate_route_posture,
            candidate_workflow_set,
            candidate_workflow_set_summary,
            candidate_next_action,
        ],
        routes={"candidate_workflow_set_built": "select_strategy"},
    )
    def build_candidate_workflow_set(ctx):
        child_result = run_child_workflow(
            ctx,
            "task_to_candidate_workflow_set",
            message=_read_request_text(ctx),
            parameters={
                "task_title": ctx.state.task_title,
                "sponsor_role": ctx.state.sponsor_role,
                "desired_outcome": ctx.state.desired_outcome,
                "constraints": ctx.state.constraints,
                "evidence_expectations": ctx.state.evidence_expectations,
            },
        )
        child_last_event = None if child_result.last_event is None else child_result.last_event.tag
        if child_result.status == "awaiting_input" and child_last_event in {"question", "blocked"}:
            question = None if child_result.last_event is None else child_result.last_event.question
            return Event(child_last_event, question=question)

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
        return "candidate_workflow_set_built"

    @python_step(
        name="publish_strategy",
        requires=[
            workflow_portfolio_snapshot,
            workflow_candidate_matrix,
            workflow_gap_analysis,
            candidate_route_posture,
            candidate_workflow_set,
            candidate_workflow_set_summary,
            candidate_next_action,
            strategy_decision,
            workflow_strategy_package,
            strategy_summary,
            strategy_next_action,
        ],
        writes=[strategy_receipt],
        routes={"strategy_published": FINISH},
    )
    def publish_strategy(ctx):
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

        summary = STRATEGY_SUMMARY_ARTIFACT.read(required_paths["strategy_summary"])
        selected_strategy = _require_strategy(
            summary.selected_strategy,
            "strategy_summary.json must define a legal selected_strategy",
        )
        recommended_workflows = require_string_list(
            summary.recommended_workflows,
            error_message="strategy_summary.json must define non-empty recommended_workflows",
            allow_scalar=True,
            dedupe=True,
            coerce=True,
        )
        comparison_candidates = require_string_list(
            summary.comparison_candidates,
            error_message="strategy_summary.json must define comparison_candidates with at least three workflow names",
            allow_scalar=True,
            dedupe=True,
            coerce=True,
        )
        if len(comparison_candidates) < 3:
            raise ValueError("strategy_summary.json must compare at least three candidate workflows")

        builder_baseline_workflow = require_non_empty_string(
            summary.builder_baseline_workflow,
            error_message="strategy_summary.json must define a non-empty builder_baseline_workflow",
            coerce=True,
        )
        if builder_baseline_workflow != _BUILDER_BASELINE:
            raise ValueError(
                f"strategy_summary.json builder_baseline_workflow must be {_BUILDER_BASELINE!r}"
            )
        if builder_baseline_workflow not in comparison_candidates:
            raise ValueError("strategy_summary.json must include the builder baseline in comparison_candidates")

        builder_considered = summary.builder_considered
        if builder_considered is not True:
            raise ValueError("strategy_summary.json must confirm builder_considered=true")

        create_new_required = summary.create_new_required
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
        if selected_strategy == "adapt" and len(recommended_workflows) != 1:
            raise ValueError("strategy_summary.json must recommend exactly one workflow for adapt")

        authoritative_artifacts = require_string_list(
            summary.authoritative_artifacts,
            error_message="strategy_summary.json must define non-empty authoritative_artifacts",
            allow_scalar=True,
            dedupe=True,
            coerce=True,
        )
        rejected_routes = normalize_unique_strings(summary.rejected_routes, allow_scalar=True)
        next_action = require_non_empty_string(
            summary.next_action,
            error_message="strategy_summary.json must define a non-empty next_action",
            coerce=True,
        )
        ready_for_handoff = summary.ready_for_handoff
        if ready_for_handoff is not True:
            raise ValueError("strategy_summary.json must confirm ready_for_handoff=true")

        workflow_strategy_package_text = _read_text(required_paths["workflow_strategy_package"])
        strategy_next_action_text = _read_text(required_paths["strategy_next_action"])
        if selected_strategy == "adapt":
            selected_workflow = recommended_workflows[0]
            _require_concrete_adapt_handoff(
                "workflow_strategy_package.md",
                workflow_strategy_package_text,
                selected_workflow,
            )
            _require_concrete_adapt_handoff(
                "strategy_summary.json next_action",
                next_action,
                selected_workflow,
            )
            _require_concrete_adapt_handoff(
                "strategy_next_action.md",
                strategy_next_action_text,
                selected_workflow,
            )

        candidate_summary = CANDIDATE_WORKFLOW_SET_SUMMARY_ARTIFACT.read(
            required_paths["candidate_workflow_set_summary"]
        )
        candidate_comparison_candidates = require_string_list(
            candidate_summary.comparison_candidates,
            error_message="candidate_workflow_set_summary.json must define comparison_candidates",
            allow_scalar=True,
            dedupe=True,
            coerce=True,
        )
        if comparison_candidates != candidate_comparison_candidates:
            raise ValueError(
                "strategy_summary.json comparison_candidates must match candidate_workflow_set_summary.json"
            )
        candidate_recommended_workflows = require_string_list(
            candidate_summary.recommended_candidate_workflows,
            error_message="candidate_workflow_set_summary.json must define recommended_candidate_workflows",
            allow_scalar=True,
            dedupe=True,
            coerce=True,
        )
        if not set(recommended_workflows).issubset(candidate_recommended_workflows):
            raise ValueError(
                "strategy_summary.json recommended_workflows must be drawn from candidate_workflow_set_summary.json"
            )
        candidate_portfolio_posture = _require_portfolio_posture(
            candidate_summary.portfolio_posture,
            "candidate_workflow_set_summary.json must define a legal portfolio_posture",
        )
        expected_strategy = _strategy_for_portfolio_posture(candidate_portfolio_posture)
        if selected_strategy != expected_strategy:
            raise ValueError(
                "strategy_summary.json selected_strategy must align with candidate_workflow_set_summary.json portfolio_posture"
            )
        child_ready = candidate_summary.ready_for_strategy_selection
        if child_ready is not True:
            raise ValueError(
                "candidate_workflow_set_summary.json must confirm ready_for_strategy_selection=true"
            )

        if ctx.state.selected_strategy is not None and selected_strategy != ctx.state.selected_strategy:
            raise ValueError("strategy_summary.json selected_strategy must match workflow state")
        if ctx.state.recommended_workflows and recommended_workflows != ctx.state.recommended_workflows:
            raise ValueError("strategy_summary.json recommended_workflows must match workflow state")

        write_publication_receipt(
            ctx,
            "strategy_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "task_title": ctx.state.task_title,
                "sponsor_role": ctx.state.sponsor_role,
                "desired_outcome": ctx.state.desired_outcome,
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
        ctx.state.selected_strategy = selected_strategy
        ctx.state.recommended_workflows = recommended_workflows
        ctx.state.published = True
        return Event("strategy_published")

    entry = bootstrap


def _require_strategy(value, error_message: str) -> str:
    strategy = require_non_empty_string(value, error_message=error_message, coerce=True)
    if strategy not in _STRATEGY_ROUTES:
        raise ValueError(error_message)
    return strategy


def _require_portfolio_posture(value, error_message: str) -> str:
    posture = require_non_empty_string(value, error_message=error_message, coerce=True)
    if posture not in _PORTFOLIO_POSTURES:
        raise ValueError(error_message)
    return posture


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


def _read_text(path) -> str:
    return path.read_text(encoding="utf-8")


def _require_concrete_adapt_handoff(surface_name: str, text: str, selected_workflow: str) -> None:
    if _ADAPTATION_BUILDING_BLOCK not in text:
        raise ValueError(
            f"{surface_name} must name {_ADAPTATION_BUILDING_BLOCK} when selected_strategy is adapt"
        )
    if selected_workflow not in text:
        raise ValueError(
            f"{surface_name} must name the selected workflow when selected_strategy is adapt"
        )
