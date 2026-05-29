"""Persistent subgoal-based goal workflow: Botpipe equivalent of Codex /goal.

Command-equivalent inputs:
- /goal <objective>       -> action="set", objective="..."
- /goal                   -> action="status"
- /goal clear             -> action="clear"
- /goal pause             -> action="pause"
- /goal resume            -> action="resume"
- /goal edit <objective>  -> action="edit", objective="..."
- replan current goal     -> action="replan"

Design:
- goal.json is the durable parent objective.
- subgoals.json is the plan-of-record.
- exactly one active subgoal is selected at a time.
- each subgoal has its own verifier criteria.
- completion of all subgoals is necessary but not sufficient: final_goal_audit
  independently verifies the original parent objective.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from botpipe import (
    Event,
    FAIL,
    FINISH,
    Prompt,
    Route,
    Session,
    Workflow,
    produce_verify_step,
    python_step,
    step,
)
from botpipe.core import Artifact
from botpipe.core.extensions import RunBinding, StepFinish, StepStart, TerminalFinish


GoalStatus = Literal[
    "active",
    "paused",
    "blocked",
    "usage_limited",
    "budget_limited",
    "complete",
]

PlanningStatus = Literal["unplanned", "planned", "stale"]

GoalAction = Literal[
    "set",
    "status",
    "pause",
    "resume",
    "clear",
    "edit",
    "replan",
]

SubgoalStatus = Literal[
    "pending",
    "active",
    "needs_rework",
    "blocked",
    "complete",
    "skipped",
]


class GoalWorkflowInput(BaseModel):
    action: GoalAction = "set"
    objective: str | None = None

    replace_existing: bool = False
    allow_replace_completed: bool = True

    token_budget: int | None = Field(default=None, gt=0)
    max_goal_turns: int | None = Field(default=None, ge=1)


class GoalRecord(BaseModel):
    schema: Literal["botpipe.goal/v2"] = "botpipe.goal/v2"

    thread_id: str
    goal_id: str
    objective: str
    status: GoalStatus
    planning_status: PlanningStatus = "unplanned"

    token_budget: int | None = None
    tokens_used: int = 0
    time_used_seconds: int = 0
    max_goal_turns: int | None = None
    turns_completed: int = 0

    active_subgoal_id: str | None = None
    completed_subgoal_count: int = 0
    total_subgoal_count: int = 0

    created_at: str
    updated_at: str
    last_reason: str | None = None

    completion_summary: str | None = None
    completed_at: str | None = None


class SubgoalRecord(BaseModel):
    id: str
    title: str
    description: str
    status: SubgoalStatus = "pending"

    verifier_criteria: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    priority: int = 100

    evidence_artifacts: list[str] = Field(default_factory=list)
    suggested_commands: list[str] = Field(default_factory=list)

    turns_completed: int = 0
    tokens_used: int = 0
    time_used_seconds: int = 0

    last_verifier_route: str | None = None
    last_reason: str | None = None

    blocker_fingerprint: str | None = None
    blocker_reason: str | None = None
    consecutive_blocked_turns: int = 0

    completion_summary: str | None = None
    criteria_results: dict[str, str] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    completed_at: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_required_artifacts(cls, value: object) -> object:
        if isinstance(value, dict) and "evidence_artifacts" not in value and "required_artifacts" in value:
            value = dict(value)
            value["evidence_artifacts"] = value.get("required_artifacts")
        return value


class SubgoalPlan(BaseModel):
    schema: Literal["botpipe.goal.subgoals/v1"] = "botpipe.goal.subgoals/v1"
    goal_id: str = ""
    active_subgoal_id: str | None = None
    subgoals: list[SubgoalRecord] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class GoalWorkflowState(BaseModel):
    goal_id: str | None = None
    status: GoalStatus | Literal["missing", "cleared"] = "missing"
    planning_status: PlanningStatus | Literal["missing"] = "missing"
    active_subgoal_id: str | None = None
    last_reason: str | None = None


class GoalWorkflowOutput(BaseModel):
    status: GoalStatus | Literal["missing", "cleared"]
    goal_id: str | None = None
    objective: str | None = None
    planning_status: PlanningStatus | Literal["missing"] = "missing"
    active_subgoal_id: str | None = None
    completed_subgoal_count: int = 0
    total_subgoal_count: int = 0
    tokens_used: int = 0
    token_budget: int | None = None
    time_used_seconds: int = 0
    goal_path: str
    subgoals_path: str
    status_report_path: str | None = None
    final_report_path: str | None = None


class ReasonRouteFields(BaseModel):
    reason: str | None = None
    evidence: str | None = None


class PlanAcceptedFields(BaseModel):
    reason: str | None = None
    coverage_summary: str
    risks: list[str] = Field(default_factory=list)


class SubgoalCompleteFields(BaseModel):
    reason: str | None = None
    completion_summary: str
    criteria_results: dict[str, str] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)


class SubgoalBlockedFields(BaseModel):
    reason: str
    blocker_fingerprint: str
    blocked_criteria: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class FinalCompleteFields(BaseModel):
    reason: str | None = None
    completion_summary: str
    evidence: list[str] = Field(default_factory=list)


class FinalNeedsReworkFields(BaseModel):
    reason: str
    subgoal_ids: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class FinalReplanFields(BaseModel):
    reason: str
    missing_requirements: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _goal_exists(ctx) -> bool:
    return ctx.artifacts.goal.exists()


def _subgoals_exist(ctx) -> bool:
    return ctx.artifacts.subgoals.exists()


def _load_goal(ctx) -> GoalRecord:
    return GoalRecord.model_validate(ctx.artifacts.goal.read_json())


def _load_plan(ctx) -> SubgoalPlan:
    return SubgoalPlan.model_validate(ctx.artifacts.subgoals.read_json())


def _write_goal(ctx, goal: GoalRecord) -> None:
    goal.updated_at = _now()
    ctx.artifacts.goal.write_model(goal)
    _sync_state(ctx, goal)


def _write_plan(ctx, plan: SubgoalPlan) -> None:
    plan.updated_at = _now()
    if not plan.created_at:
        plan.created_at = _now()
    ctx.artifacts.subgoals.write_model(plan)


def _sync_state(ctx, goal: GoalRecord | None) -> None:
    if goal is None:
        ctx.state.goal_id = None
        ctx.state.status = "missing"
        ctx.state.planning_status = "missing"
        ctx.state.active_subgoal_id = None
        ctx.state.last_reason = None
        return

    ctx.state.goal_id = goal.goal_id
    ctx.state.status = goal.status
    ctx.state.planning_status = goal.planning_status
    ctx.state.active_subgoal_id = goal.active_subgoal_id
    ctx.state.last_reason = goal.last_reason


def _input_objective(ctx) -> str | None:
    options = _workflow_options(ctx)
    objective = _clean_text(getattr(options, "objective", None))
    if objective is not None:
        return objective
    return _clean_text(ctx.message)


def _workflow_options(ctx) -> GoalWorkflowInput:
    workflow_input = getattr(ctx, "input", None)
    if workflow_input is not None:
        return workflow_input

    params = getattr(ctx, "params", None)
    if params is not None:
        return params

    return GoalWorkflowInput()


def _new_goal(ctx, objective: str) -> GoalRecord:
    options = _workflow_options(ctx)
    return GoalRecord(
        thread_id=ctx.task_id,
        goal_id=uuid4().hex,
        objective=objective,
        status="active",
        planning_status="unplanned",
        token_budget=getattr(options, "token_budget", None),
        max_goal_turns=getattr(options, "max_goal_turns", None),
        created_at=_now(),
        updated_at=_now(),
    )


def _event_fields(ctx) -> dict[str, Any]:
    outcome = ctx.outcome
    fields = getattr(outcome, "route_fields", None)
    if isinstance(fields, dict):
        return dict(fields)

    event_source = getattr(ctx.event, "_source", None)
    if isinstance(event_source, dict):
        fields = event_source.get("route_fields")
        if isinstance(fields, dict):
            return dict(fields)

    return {}


def _list_from_field(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _goal_status_markdown(goal: GoalRecord | None, plan: SubgoalPlan | None = None) -> str:
    if goal is None:
        return "# Goal Status\n\nNo goal is currently set.\n"

    token_budget = "none" if goal.token_budget is None else str(goal.token_budget)
    remaining = (
        "unbounded"
        if goal.token_budget is None
        else str(max(0, goal.token_budget - goal.tokens_used))
    )

    lines = [
        "# Goal Status",
        "",
        f"- Goal id: `{goal.goal_id}`",
        f"- Status: `{goal.status}`",
        f"- Planning status: `{goal.planning_status}`",
        f"- Objective: {goal.objective}",
        f"- Active subgoal id: `{goal.active_subgoal_id or '(none)'}`",
        f"- Completed subgoals: {goal.completed_subgoal_count}/{goal.total_subgoal_count}",
        f"- Tokens used: {goal.tokens_used}",
        f"- Token budget: {token_budget}",
        f"- Tokens remaining: {remaining}",
        f"- Time used seconds: {goal.time_used_seconds}",
        f"- Goal turns completed: {goal.turns_completed}",
        f"- Max goal turns: {goal.max_goal_turns if goal.max_goal_turns is not None else 'none'}",
        f"- Last reason: {goal.last_reason or '(none)'}",
        "",
    ]

    if plan is not None and plan.subgoals:
        lines.extend(["## Subgoals", ""])
        for subgoal in plan.subgoals:
            deps = ", ".join(subgoal.dependencies) or "none"
            lines.append(
                f"- `{subgoal.id}` [{subgoal.status}] {subgoal.title} "
                f"(deps: {deps}, blocked turns: {subgoal.consecutive_blocked_turns})"
            )
        lines.append("")

        active = _find_subgoal(plan, plan.active_subgoal_id or goal.active_subgoal_id)
        if active is not None:
            lines.extend(
                [
                    "## Active Subgoal",
                    "",
                    f"- Id: `{active.id}`",
                    f"- Title: {active.title}",
                    f"- Status: `{active.status}`",
                    f"- Description: {active.description}",
                    f"- Last reason: {active.last_reason or '(none)'}",
                    "",
                    "### Verifier Criteria",
                    "",
                ]
            )
            lines.extend(f"- {criterion}" for criterion in active.verifier_criteria)
            lines.extend(
                [
                    "",
                    "### Evidence Artifact References",
                    "",
                    "These are planner-supplied references for provider and verifier inspection, not Botpipe runtime-required writes.",
                    "",
                ]
            )
            if active.evidence_artifacts:
                lines.extend(f"- `{artifact}`" for artifact in active.evidence_artifacts)
            else:
                lines.append("- none declared")
            lines.extend(["", "### Suggested Commands", ""])
            if active.suggested_commands:
                lines.extend(f"- `{command}`" for command in active.suggested_commands)
            else:
                lines.append("- none declared")
            if active.evidence:
                lines.extend(["", "### Latest Accepted Evidence", ""])
                lines.extend(f"- `{item}`" for item in active.evidence)
            lines.append("")

    return "\n".join(lines)


def _run_artifacts_markdown(ctx) -> str:
    artifacts = [
        ("goal", ctx.artifacts.goal),
        ("subgoals", ctx.artifacts.subgoals),
        ("status_report", ctx.artifacts.status_report),
        ("run_context", ctx.artifacts.run_context),
        ("plan_audit", ctx.artifacts.plan_audit),
        ("subgoal_progress", ctx.artifacts.subgoal_progress),
        ("subgoal_audit", ctx.artifacts.subgoal_audit),
        ("goal_summary", ctx.artifacts.goal_summary),
        ("goal_audit", ctx.artifacts.goal_audit),
        ("final_report", ctx.artifacts.final_report),
    ]
    lines = ["## Workflow Artifacts", ""]
    for name, artifact in artifacts:
        state = "present" if name in {"status_report", "run_context"} or artifact.exists() else "missing"
        lines.append(f"- `{name}`: `{artifact.path}` ({state})")
    return "\n".join(lines)


def _run_context_markdown(ctx, *, heading: str) -> str:
    goal = _load_goal(ctx) if _goal_exists(ctx) else None
    plan = _load_plan(ctx) if _subgoals_exist(ctx) else None

    lines = [
        "# Run Context",
        "",
        f"- Phase: {heading}",
        f"- Updated at: {_now()}",
        f"- Workflow folder: `{ctx.workflow_folder}`",
        "",
    ]

    if goal is None:
        lines.extend(["## Parent Goal", "", "No goal is currently set.", ""])
        return "\n".join(lines)

    lines.extend(
        [
            "## Parent Goal",
            "",
            f"- Goal id: `{goal.goal_id}`",
            f"- Status: `{goal.status}`",
            f"- Planning status: `{goal.planning_status}`",
            f"- Objective: {goal.objective}",
            f"- Active subgoal id: `{goal.active_subgoal_id or '(none)'}`",
            f"- Completed subgoals: {goal.completed_subgoal_count}/{goal.total_subgoal_count}",
            f"- Last reason: {goal.last_reason or '(none)'}",
            "",
        ]
    )

    if plan is None or not plan.subgoals:
        lines.extend(["## Subgoal Plan", "", "No subgoal plan is present.", ""])
        return "\n".join(lines)

    active = _find_subgoal(plan, plan.active_subgoal_id or goal.active_subgoal_id)
    if active is not None:
        lines.extend(
            [
                "## Active Subgoal",
                "",
                f"- Id: `{active.id}`",
                f"- Title: {active.title}",
                f"- Status: `{active.status}`",
                f"- Description: {active.description}",
                f"- Last verifier route: `{active.last_verifier_route or '(none)'}`",
                f"- Last reason: {active.last_reason or '(none)'}",
                "",
                "### Acceptance Criteria",
                "",
            ]
        )
        lines.extend(f"- {criterion}" for criterion in active.verifier_criteria)
        lines.extend(
            [
                "",
                "### Evidence Artifact References",
                "",
            ]
        )
        if active.evidence_artifacts:
            lines.extend(f"- `{artifact}`" for artifact in active.evidence_artifacts)
        else:
            lines.append("- none declared")
        lines.extend(["", "### Suggested Commands", ""])
        if active.suggested_commands:
            lines.extend(f"- `{command}`" for command in active.suggested_commands)
        else:
            lines.append("- none declared")
        lines.append("")

    completed = [item for item in plan.subgoals if item.status == "complete"]
    if completed:
        lines.extend(["## Completed Subgoals", ""])
        for item in completed:
            summary = item.completion_summary or item.last_reason or "complete"
            lines.append(f"- `{item.id}` {item.title}: {summary}")
        lines.append("")

    latest_evidence: list[str] = []
    for item in plan.subgoals:
        for evidence in item.evidence:
            if evidence not in latest_evidence:
                latest_evidence.append(evidence)
    if latest_evidence:
        lines.extend(["## Evidence Index", ""])
        lines.extend(f"- `{evidence}`" for evidence in latest_evidence[:30])
        if len(latest_evidence) > 30:
            lines.append(f"- ... {len(latest_evidence) - 30} more evidence entries")
        lines.append("")

    lines.extend(
        [
            "## Workflow Artifacts",
            "",
            f"- Goal: `{ctx.artifacts.goal.path}`",
            f"- Subgoals: `{ctx.artifacts.subgoals.path}`",
            f"- Status: `{ctx.artifacts.status_report.path}`",
            f"- Plan audit: `{ctx.artifacts.plan_audit.path}`",
            f"- Subgoal progress: `{ctx.artifacts.subgoal_progress.path}`",
            f"- Subgoal audit: `{ctx.artifacts.subgoal_audit.path}`",
            f"- Goal summary: `{ctx.artifacts.goal_summary.path}`",
            f"- Goal audit: `{ctx.artifacts.goal_audit.path}`",
            "",
        ]
    )
    return "\n".join(lines)


def _write_status_report(ctx, heading: str = "Goal Status") -> None:
    goal = _load_goal(ctx) if _goal_exists(ctx) else None
    plan = _load_plan(ctx) if _subgoals_exist(ctx) else None
    text = _goal_status_markdown(goal, plan)
    if heading != "Goal Status":
        text = text.replace("# Goal Status", f"# {heading}", 1)
    text = f"{text.rstrip()}\n\n{_run_artifacts_markdown(ctx)}\n"
    ctx.artifacts.status_report.write_text(text)
    ctx.artifacts.run_context.write_text(_run_context_markdown(ctx, heading=heading))


def _subgoal_ids(plan: SubgoalPlan) -> set[str]:
    return {item.id for item in plan.subgoals}


def _find_subgoal(plan: SubgoalPlan, subgoal_id: str | None) -> SubgoalRecord | None:
    if subgoal_id is None:
        return None
    for item in plan.subgoals:
        if item.id == subgoal_id:
            return item
    return None


def _completed_ids(plan: SubgoalPlan) -> set[str]:
    return {item.id for item in plan.subgoals if item.status == "complete"}


def _dependency_cycle_error(plan: SubgoalPlan) -> str | None:
    graph = {item.id: list(item.dependencies) for item in plan.subgoals}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, path: list[str]) -> str | None:
        if node in visiting:
            return f"Subgoal dependency cycle detected: {' -> '.join([*path, node])}"
        if node in visited:
            return None

        visiting.add(node)
        for dep in graph.get(node, []):
            error = visit(dep, [*path, node])
            if error is not None:
                return error
        visiting.remove(node)
        visited.add(node)
        return None

    for node in graph:
        error = visit(node, [])
        if error is not None:
            return error
    return None


def _refresh_goal_counts(goal: GoalRecord, plan: SubgoalPlan) -> None:
    goal.total_subgoal_count = len(plan.subgoals)
    goal.completed_subgoal_count = len([item for item in plan.subgoals if item.status == "complete"])


def _validate_plan(plan: SubgoalPlan, goal: GoalRecord) -> str | None:
    if not plan.subgoals:
        return "subgoals.json must contain at least one subgoal."

    all_ids = _subgoal_ids(plan)
    seen: set[str] = set()

    for subgoal in plan.subgoals:
        if not subgoal.id.strip():
            return "Every subgoal must have a non-empty id."
        if subgoal.id in seen:
            return f"Duplicate subgoal id: {subgoal.id}"
        seen.add(subgoal.id)

        if not subgoal.title.strip():
            return f"Subgoal {subgoal.id!r} must have a non-empty title."
        if not subgoal.description.strip():
            return f"Subgoal {subgoal.id!r} must have a non-empty description."
        if not subgoal.verifier_criteria:
            return f"Subgoal {subgoal.id!r} must declare verifier_criteria."

        for dep in subgoal.dependencies:
            if dep == subgoal.id:
                return f"Subgoal {subgoal.id!r} depends on itself."
            if dep not in all_ids:
                return f"Subgoal {subgoal.id!r} depends on unknown subgoal {dep!r}."

    cycle_error = _dependency_cycle_error(plan)
    if cycle_error is not None:
        return cycle_error

    plan.goal_id = goal.goal_id
    return None


def _select_next(plan: SubgoalPlan) -> SubgoalRecord | None:
    completed = _completed_ids(plan)

    active = _find_subgoal(plan, plan.active_subgoal_id)
    if (
        active is not None
        and active.status in {"active", "needs_rework", "pending"}
        and all(dep in completed for dep in active.dependencies)
    ):
        return active

    candidates = [
        item
        for item in plan.subgoals
        if item.status in {"pending", "active", "needs_rework"}
        and all(dep in completed for dep in item.dependencies)
    ]
    if not candidates:
        return None

    return sorted(candidates, key=lambda item: (item.priority, item.id))[0]


def _has_incomplete_subgoals(plan: SubgoalPlan) -> bool:
    return any(item.status != "complete" for item in plan.subgoals)


def _all_remaining_paths_blocked(plan: SubgoalPlan) -> bool:
    if not _has_incomplete_subgoals(plan):
        return False
    completed = _completed_ids(plan)
    selectable = [
        item
        for item in plan.subgoals
        if item.status in {"pending", "active", "needs_rework"}
        and all(dep in completed for dep in item.dependencies)
    ]
    if selectable:
        return False
    return any(item.status == "blocked" for item in plan.subgoals)


def _usage_tokens(provider_usage: Any) -> int:
    if provider_usage is None:
        return 0
    total = 0
    for attr in ("producer", "verifier", "llm", "repair"):
        total += _token_delta(getattr(provider_usage, attr, None))
    return total


def _token_delta(token_usage: Any) -> int:
    if token_usage is None:
        return 0

    input_tokens = getattr(token_usage, "input_tokens", None)
    output_tokens = getattr(token_usage, "output_tokens", None)
    cached_input_tokens = getattr(token_usage, "cached_input_tokens", None)
    total_tokens = getattr(token_usage, "total_tokens", None)

    if input_tokens is not None or output_tokens is not None:
        non_cached = max(0, int(input_tokens or 0) - int(cached_input_tokens or 0))
        output = max(0, int(output_tokens or 0))
        return non_cached + output

    return max(0, int(total_tokens or 0))


def _patch_usage_files(workflow_folder: Path, *, tokens: int, elapsed_seconds: int) -> None:
    if tokens <= 0 and elapsed_seconds <= 0:
        return

    goal_path = workflow_folder / "goal.json"
    subgoals_path = workflow_folder / "subgoals.json"

    if not goal_path.exists():
        return

    goal_payload = json.loads(goal_path.read_text(encoding="utf-8"))
    active_subgoal_id = goal_payload.get("active_subgoal_id")

    goal_payload["tokens_used"] = int(goal_payload.get("tokens_used") or 0) + max(0, tokens)
    goal_payload["time_used_seconds"] = int(goal_payload.get("time_used_seconds") or 0) + max(0, elapsed_seconds)

    if goal_payload.get("status") == "active":
        budget = goal_payload.get("token_budget")
        if isinstance(budget, int) and budget > 0 and goal_payload["tokens_used"] >= budget:
            goal_payload["status"] = "budget_limited"
            goal_payload["last_reason"] = "Goal token budget reached."

    goal_payload["updated_at"] = _now()
    goal_path.write_text(json.dumps(goal_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if subgoals_path.exists() and isinstance(active_subgoal_id, str) and active_subgoal_id:
        plan_payload = json.loads(subgoals_path.read_text(encoding="utf-8"))
        for subgoal in plan_payload.get("subgoals", []):
            if isinstance(subgoal, dict) and subgoal.get("id") == active_subgoal_id:
                subgoal["tokens_used"] = int(subgoal.get("tokens_used") or 0) + max(0, tokens)
                subgoal["time_used_seconds"] = int(subgoal.get("time_used_seconds") or 0) + max(0, elapsed_seconds)
                break
        plan_payload["updated_at"] = _now()
        subgoals_path.write_text(json.dumps(plan_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class GoalUsageAccounting:
    """Workflow extension that accounts provider usage into goal.json/subgoals.json.

    It only patches usage fields and only transitions an active parent goal to
    budget_limited. It never demotes complete/blocked/paused goals.
    """

    def __init__(self, tracked_steps: set[str] | frozenset[str] | None = None) -> None:
        self.tracked_steps = frozenset(
            tracked_steps
            or {
                "plan_subgoals",
                "work_subgoal",
                "final_goal_audit",
                "wrap_up_budget_limited",
            }
        )

    def bind(self, binding: RunBinding) -> "_BoundGoalUsageAccounting":
        return _BoundGoalUsageAccounting(binding, self.tracked_steps)


class _BoundGoalUsageAccounting:
    def __init__(self, binding: RunBinding, tracked_steps: frozenset[str]) -> None:
        self.binding = binding
        self.tracked_steps = tracked_steps
        self.started_at_by_key: dict[str, datetime] = {}

    def before_step(self, event: StepStart) -> None:
        if event.step_name in self.tracked_steps:
            self.started_at_by_key[self._key(event)] = datetime.now(timezone.utc)

    def after_step(self, event: StepFinish) -> None:
        if event.step_name not in self.tracked_steps:
            return
        try:
            started = self.started_at_by_key.pop(self._key(event), None)
            elapsed = 0 if started is None else max(
                0,
                int((datetime.now(timezone.utc) - started).total_seconds()),
            )
            tokens = _usage_tokens(event.provider_usage)
            _patch_usage_files(self.binding.workflow_folder, tokens=tokens, elapsed_seconds=elapsed)

            usage_path = self.binding.workflow_folder / "usage.jsonl"
            usage_path.parent.mkdir(parents=True, exist_ok=True)
            usage_path.open("a", encoding="utf-8").write(
                json.dumps(
                    {
                        "at": _now(),
                        "step": event.step_name,
                        "final_route": event.final_route,
                        "tokens": tokens,
                        "elapsed_seconds": elapsed,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        except Exception:
            return

    def on_terminal(self, event: TerminalFinish) -> None:
        return None

    @staticmethod
    def _key(event: StepStart | StepFinish) -> str:
        return event.step_execution_id or f"{event.step_name}:{event.visit or 0}"


def _after_subgoal_verifier(ctx) -> None:
    outcome = ctx.outcome
    if outcome is None:
        return

    goal = _load_goal(ctx)
    plan = _load_plan(ctx)
    active = _find_subgoal(plan, plan.active_subgoal_id or goal.active_subgoal_id)
    if active is None:
        return

    fields = _event_fields(ctx)
    tag = outcome.tag

    goal.turns_completed += 1
    active.turns_completed += 1
    active.last_verifier_route = tag
    active.last_reason = _clean_text(fields.get("reason")) or _clean_text(getattr(outcome, "reason", None))

    if tag == "complete":
        active.status = "complete"
        active.completion_summary = _clean_text(fields.get("completion_summary"))
        active.criteria_results = dict(fields.get("criteria_results") or {})
        active.evidence = _list_from_field(fields.get("evidence"))
        active.completed_at = _now()
        active.consecutive_blocked_turns = 0
        active.blocker_fingerprint = None
        active.blocker_reason = None

    elif tag == "blocked":
        fingerprint = _clean_text(fields.get("blocker_fingerprint")) or "unspecified-blocker"
        reason = _clean_text(fields.get("reason")) or "Blocked."

        if active.blocker_fingerprint == fingerprint:
            active.consecutive_blocked_turns += 1
        else:
            active.blocker_fingerprint = fingerprint
            active.consecutive_blocked_turns = 1

        active.blocker_reason = reason
        active.status = "active"

    elif tag == "needs_rework":
        active.status = "needs_rework"
        active.consecutive_blocked_turns = 0
        active.blocker_fingerprint = None
        active.blocker_reason = None

    else:
        active.status = "active"
        active.consecutive_blocked_turns = 0
        active.blocker_fingerprint = None
        active.blocker_reason = None

    _refresh_goal_counts(goal, plan)
    goal.status = "active"
    goal.last_reason = active.last_reason
    goal.active_subgoal_id = active.id
    plan.active_subgoal_id = active.id

    _write_plan(ctx, plan)
    _write_goal(ctx, goal)


def _after_final_goal_verifier(ctx) -> None:
    outcome = ctx.outcome
    if outcome is None:
        return

    goal = _load_goal(ctx)
    plan = _load_plan(ctx)
    fields = _event_fields(ctx)
    tag = outcome.tag

    if tag == "complete":
        goal.status = "active"
        goal.completion_summary = _clean_text(fields.get("completion_summary"))
        goal.last_reason = _clean_text(fields.get("reason")) or "Final audit proved parent goal completion."

    elif tag == "needs_rework":
        requested_ids = set(_list_from_field(fields.get("subgoal_ids")))
        if not requested_ids:
            requested_ids = {item.id for item in plan.subgoals if item.status == "complete"}
        for item in plan.subgoals:
            if item.id in requested_ids:
                item.status = "needs_rework"
                item.last_reason = _clean_text(fields.get("reason")) or "Final audit found incomplete subgoal work."
                item.completed_at = None
        goal.status = "active"
        goal.planning_status = "planned"
        goal.last_reason = _clean_text(fields.get("reason")) or "Final audit requires subgoal rework."

    elif tag == "replan":
        goal.status = "active"
        goal.planning_status = "stale"
        goal.active_subgoal_id = None
        plan.active_subgoal_id = None
        goal.last_reason = _clean_text(fields.get("reason")) or "Final audit found missing parent-goal requirements."

    _refresh_goal_counts(goal, plan)
    _write_plan(ctx, plan)
    _write_goal(ctx, goal)


class GoalWorkflow(Workflow):
    name = "goal"
    State = GoalWorkflowState
    Params = GoalWorkflowInput
    Input = GoalWorkflowInput
    Output = GoalWorkflowOutput

    goal_session = Session.task()
    subgoal_session = Session.fresh()
    planning_verifier_session = Session.fresh()
    subgoal_verifier_session = Session.fresh()
    final_verifier_session = Session.fresh()

    goal = Artifact.json(
        "{{ workflow.folder }}/goal.json",
        schema=GoalRecord,
        name="goal",
        required=False,
    )
    subgoals = Artifact.json(
        "{{ workflow.folder }}/subgoals.json",
        schema=SubgoalPlan,
        name="subgoals",
        required=False,
    )
    status_report = Artifact.md(
        "{{ workflow.folder }}/status.md",
        name="status_report",
        required=False,
    )
    run_context = Artifact.md(
        "{{ workflow.folder }}/run_context.md",
        name="run_context",
        required=False,
    )
    plan_audit = Artifact.md(
        "{{ workflow.folder }}/plan_audit.md",
        name="plan_audit",
        required=False,
    )
    subgoal_progress = Artifact.md(
        "{{ workflow.folder }}/subgoal_progress.md",
        name="subgoal_progress",
        required=False,
    )
    subgoal_audit = Artifact.md(
        "{{ workflow.folder }}/subgoal_audit.md",
        name="subgoal_audit",
        required=False,
    )
    goal_summary = Artifact.md(
        "{{ workflow.folder }}/goal_summary.md",
        name="goal_summary",
        required=False,
    )
    goal_audit = Artifact.md(
        "{{ workflow.folder }}/goal_audit.md",
        name="goal_audit",
        required=False,
    )
    final_report = Artifact.md(
        "{{ workflow.folder }}/final_report.md",
        name="final_report",
        required=False,
    )

    extensions = (GoalUsageAccounting(),)

    @python_step(
        name="initialize_goal",
        writes=[goal, subgoals, status_report, run_context],
        routes={
            "plan": "plan_subgoals",
            "select": "select_next_subgoal",
            "budget_limited": "wrap_up_budget_limited",
            "paused": FINISH,
            "cleared": FINISH,
            "status": FINISH,
            "question": Route.question(),
            "failed": FAIL,
        },
    )
    def initialize_goal(ctx):
        options = _workflow_options(ctx)
        action = getattr(options, "action", "set")
        existing = _load_goal(ctx) if _goal_exists(ctx) else None

        if action == "status":
            _sync_state(ctx, existing)
            _write_status_report(ctx)
            return "status"

        if action == "clear":
            if ctx.artifacts.goal.exists():
                ctx.artifacts.goal.path.unlink()
            if ctx.artifacts.subgoals.exists():
                ctx.artifacts.subgoals.path.unlink()
            _sync_state(ctx, None)
            ctx.state.status = "cleared"
            ctx.artifacts.status_report.write_text("# Goal cleared\n")
            ctx.artifacts.run_context.write_text("# Run Context\n\nGoal cleared.\n")
            return "cleared"

        if action == "pause":
            if existing is None:
                _sync_state(ctx, None)
                _write_status_report(ctx)
                return "status"
            if existing.status == "complete":
                _sync_state(ctx, existing)
                _write_status_report(ctx, heading="Goal Already Complete")
                return "status"
            existing.status = "paused"
            existing.last_reason = "Paused by user."
            _write_goal(ctx, existing)
            _write_status_report(ctx)
            return "paused"

        if action == "resume":
            if existing is None:
                return Event(
                    "question",
                    reason="No goal exists to resume.",
                    question="No goal is currently set. Provide a new objective with action='set'.",
                )
            if existing.status == "complete":
                return Event(
                    "question",
                    reason="Completed goals cannot be resumed.",
                    question="The current goal is complete. Provide a new objective with action='set'.",
                )

            if getattr(options, "token_budget", None) is not None:
                existing.token_budget = options.token_budget
            if getattr(options, "max_goal_turns", None) is not None:
                existing.max_goal_turns = options.max_goal_turns

            existing.status = "active"
            existing.last_reason = "Resumed by user."
            if existing.token_budget is not None and existing.tokens_used >= existing.token_budget:
                existing.status = "budget_limited"
                existing.last_reason = "Goal token budget is already exhausted."

            _write_goal(ctx, existing)
            _write_status_report(ctx)
            if existing.status == "budget_limited":
                return "budget_limited"
            return "select" if existing.planning_status == "planned" and _subgoals_exist(ctx) else "plan"

        if action == "replan":
            if existing is None:
                return Event(
                    "question",
                    reason="No goal exists to replan.",
                    question="No goal is currently set. Provide a new objective with action='set'.",
                )
            if existing.status == "complete":
                return Event(
                    "question",
                    reason="Completed goals cannot be replanned.",
                    question="The current goal is complete. Provide a new objective with action='set'.",
                )
            if getattr(options, "token_budget", None) is not None:
                existing.token_budget = options.token_budget
            if getattr(options, "max_goal_turns", None) is not None:
                existing.max_goal_turns = options.max_goal_turns
            existing.status = "active"
            existing.planning_status = "stale"
            existing.active_subgoal_id = None
            existing.last_reason = "Replan requested by user."
            _write_goal(ctx, existing)
            _write_status_report(ctx, heading="Goal Replan Requested")
            return "plan"

        if action == "edit":
            if existing is None:
                return Event(
                    "question",
                    reason="No goal exists to edit.",
                    question="No goal is currently set. Provide a new objective with action='set'.",
                )
            if existing.status == "complete":
                return Event(
                    "question",
                    reason="Completed goals cannot be edited.",
                    question="The current goal is complete. Provide a new objective with action='set'.",
                )
            objective = _input_objective(ctx)
            if objective is None:
                return Event(
                    "question",
                    reason="Missing edited objective.",
                    question="Provide the new objective for action='edit'.",
                )

            existing.objective = objective
            existing.status = "active"
            existing.planning_status = "stale"
            existing.active_subgoal_id = None
            existing.last_reason = "Objective edited by user; prior subgoal plan is stale."
            if getattr(options, "token_budget", None) is not None:
                existing.token_budget = options.token_budget
            if getattr(options, "max_goal_turns", None) is not None:
                existing.max_goal_turns = options.max_goal_turns

            _write_goal(ctx, existing)
            _write_status_report(ctx, heading="Goal Objective Updated")
            ctx.open_session("goal_session")
            return "plan"

        if action != "set":
            return Event(
                "question",
                reason=f"Unsupported goal action: {action!r}.",
                question="Use action='set', 'status', 'pause', 'resume', 'clear', 'edit', or 'replan'.",
            )

        objective = _input_objective(ctx)
        if objective is None:
            return Event(
                "question",
                reason="Missing goal objective.",
                question="Provide the objective to pursue, equivalent to `/goal <objective>`.",
            )

        replace_existing = bool(getattr(options, "replace_existing", False))
        allow_replace_completed = bool(getattr(options, "allow_replace_completed", True))

        if existing is not None:
            if existing.status == "complete":
                if not allow_replace_completed:
                    return Event(
                        "question",
                        reason="A completed goal already exists.",
                        question="Set allow_replace_completed=True or clear the existing goal.",
                    )
            elif not replace_existing:
                return Event(
                    "question",
                    reason="A non-complete goal already exists.",
                    question=(
                        "A goal already exists and is not complete. Re-run with "
                        "replace_existing=True to replace it, or use action='resume', "
                        "action='pause', action='clear', action='edit', action='replan', "
                        "or action='status'."
                    ),
                )

        new_goal = _new_goal(ctx, objective)
        _write_goal(ctx, new_goal)
        if ctx.artifacts.subgoals.exists():
            ctx.artifacts.subgoals.path.unlink()
        _write_status_report(ctx, heading="Goal Started")
        ctx.open_session("goal_session")
        return "plan"

    plan_subgoals = produce_verify_step(
        name="plan_subgoals",
        session=goal_session,
        verifier_session=planning_verifier_session,
        requires=[goal],
        reads=[status_report, run_context, plan_audit],
        producer_writes=[subgoals],
        verifier_writes=[plan_audit],
        producer_prompt=Prompt.inline(
            """
            Decompose the active parent goal into a minimal, sufficient set of
            auditable subgoals.

            This planner runs in the main goal session. Use that continuity for
            parent-goal intent, but treat the durable artifacts as the source of
            truth.

            Read:
            - {{ workflow.folder }}/goal.json
            - {{ workflow.folder }}/run_context.md, if present, for current
              durable state and latest evidence
            - {{ workflow.folder }}/status.md, if present
            - existing repository state and relevant files
            - existing {{ workflow.folder }}/subgoals.json, if present
            - existing {{ workflow.folder }}/plan_audit.md, if present

            If plan_audit.md exists and rejected the prior plan, address every
            required fix before rewriting subgoals.json.

            Write {{ workflow.folder }}/subgoals.json matching the declared
            SubgoalPlan schema.

            Requirements for every subgoal:
            - id: stable, path-safe identifier
            - title
            - description
            - verifier_criteria: concrete criteria proving this subgoal is done
            - dependencies: ids of subgoals that must be complete first
            - priority: lower values run earlier
            - evidence_artifacts, if applicable: paths the producer and
              verifier should inspect as evidence; these are not Botpipe
              runtime-required writes
            - suggested_commands, if applicable

            Planning rules:
            - Subgoals must be collectively sufficient for the parent goal.
            - Do not redefine the parent goal into an easier task.
            - Do not create busywork.
            - Do not split merely by file unless file boundaries match real
              acceptance criteria.
            - Prefer reviewable units: a verifier should be able to judge each
              subgoal against one coherent outcome without auditing many
              unrelated behavior surfaces at once.
            - Put validation/evidence work inside the subgoal it proves unless
              the validation is cross-cutting enough to deserve its own
              auditable subgoal.
            - Prefer the smallest plan that is still complete and auditable.
            - Use pending status for new subgoals.
            - When replanning, preserve completed subgoals only if they still
              satisfy the current parent objective and do not hide missing work.
            """.strip()
        ),
        verifier_prompt=Prompt.inline(
            """
            Audit the proposed subgoal plan.

            Read:
            - {{ workflow.folder }}/goal.json
            - {{ workflow.folder }}/subgoals.json
            - {{ workflow.folder }}/run_context.md, if present
            - {{ workflow.folder }}/status.md, if present
            - relevant repository state and referenced files

            Accept only if:
            - every explicit parent-goal requirement is covered by at least one
              subgoal
            - each subgoal has concrete verifier criteria
            - dependencies are coherent and acyclic
            - no subgoal is vague, duplicative, unverifiable, or irrelevant
            - each subgoal is a reviewable unit with clear scope boundaries
            - the plan does not shrink or redefine the parent goal
            - the plan is sufficient to reach the requested end state

            Write {{ workflow.folder }}/plan_audit.md with:
            - coverage analysis
            - rejected/accepted decision
            - missing requirements, if any
            - required fixes, if any
            """.strip()
        ),
        routes={
            "accepted": Route.to(
                "activate_plan",
                summary="The subgoal plan covers the parent goal and is auditable.",
                required_writes=["subgoals", "plan_audit"],
                route_fields_schema=PlanAcceptedFields,
            ),
            "needs_rework": Route.to(
                "planning_gate",
                summary="The subgoal plan is incomplete, vague, or invalid.",
                required_writes=["subgoals", "plan_audit"],
                route_fields_schema=ReasonRouteFields,
            ),
            "question": Route.question(summary="Planning requires user input."),
        },
    )

    @python_step(
        name="planning_gate",
        requires=[goal],
        writes=[goal, status_report, run_context],
        routes={
            "replan": "plan_subgoals",
            "budget_limited": "wrap_up_budget_limited",
        },
    )
    def planning_gate(ctx):
        goal = _load_goal(ctx)

        if goal.status == "budget_limited":
            _write_status_report(ctx, heading="Goal Budget Limited")
            return "budget_limited"

        if goal.token_budget is not None and goal.tokens_used >= goal.token_budget:
            goal.status = "budget_limited"
            goal.last_reason = "Goal token budget reached during planning."
            _write_goal(ctx, goal)
            _write_status_report(ctx, heading="Goal Budget Limited")
            return "budget_limited"

        if goal.max_goal_turns is not None and goal.turns_completed >= goal.max_goal_turns:
            goal.status = "budget_limited"
            goal.last_reason = f"Maximum goal turns reached during planning: {goal.max_goal_turns}."
            _write_goal(ctx, goal)
            _write_status_report(ctx, heading="Goal Turn Limited")
            return "budget_limited"

        goal.status = "active"
        goal.planning_status = "stale"
        _write_goal(ctx, goal)
        _write_status_report(ctx, heading="Planning Rework")
        return "replan"

    @python_step(
        name="activate_plan",
        requires=[goal, subgoals],
        writes=[goal, subgoals, status_report, run_context],
        routes={
            "selected": "select_next_subgoal",
            "needs_rework": "plan_subgoals",
            "budget_limited": "wrap_up_budget_limited",
            "question": Route.question(),
        },
    )
    def activate_plan(ctx):
        goal = _load_goal(ctx)
        plan = _load_plan(ctx)

        if goal.status == "budget_limited":
            _write_status_report(ctx, heading="Goal Budget Limited")
            return "budget_limited"

        if goal.token_budget is not None and goal.tokens_used >= goal.token_budget:
            goal.status = "budget_limited"
            goal.last_reason = "Goal token budget reached before plan activation."
            _write_goal(ctx, goal)
            _write_status_report(ctx, heading="Goal Budget Limited")
            return "budget_limited"

        error = _validate_plan(plan, goal)
        if error is not None:
            return Event("needs_rework", reason=error)

        goal.status = "active"
        goal.planning_status = "planned"
        goal.active_subgoal_id = None
        plan.active_subgoal_id = None
        _refresh_goal_counts(goal, plan)

        _write_plan(ctx, plan)
        _write_goal(ctx, goal)
        _write_status_report(ctx, heading="Subgoal Plan Activated")
        return "selected"

    @python_step(
        name="select_next_subgoal",
        requires=[goal, subgoals],
        writes=[goal, subgoals, status_report, run_context],
        routes={
            "selected": "prepare_subgoal_session",
            "all_done": "final_goal_audit",
            "blocked": "mark_parent_blocked",
            "replan": "plan_subgoals",
            "budget_limited": "wrap_up_budget_limited",
        },
    )
    def select_next_subgoal(ctx):
        goal = _load_goal(ctx)
        plan = _load_plan(ctx)

        if goal.status == "budget_limited":
            return "budget_limited"

        if goal.token_budget is not None and goal.tokens_used >= goal.token_budget:
            goal.status = "budget_limited"
            goal.last_reason = "Goal token budget reached."
            _write_goal(ctx, goal)
            _write_status_report(ctx, heading="Goal Budget Limited")
            return "budget_limited"

        if goal.max_goal_turns is not None and goal.turns_completed >= goal.max_goal_turns:
            goal.status = "budget_limited"
            goal.last_reason = f"Maximum goal turns reached: {goal.max_goal_turns}."
            _write_goal(ctx, goal)
            _write_status_report(ctx, heading="Goal Turn Limited")
            return "budget_limited"

        if goal.planning_status != "planned" or not plan.subgoals:
            goal.planning_status = "stale"
            _write_goal(ctx, goal)
            return "replan"

        if all(item.status == "complete" for item in plan.subgoals):
            goal.active_subgoal_id = None
            plan.active_subgoal_id = None
            _refresh_goal_counts(goal, plan)
            _write_plan(ctx, plan)
            _write_goal(ctx, goal)
            _write_status_report(ctx, heading="All Subgoals Complete")
            return "all_done"

        selected = _select_next(plan)
        if selected is None:
            if _all_remaining_paths_blocked(plan):
                goal.status = "blocked"
                goal.last_reason = "No selectable incomplete subgoals remain; remaining paths are blocked."
                _write_goal(ctx, goal)
                _write_status_report(ctx, heading="Goal Blocked")
                return "blocked"
            goal.planning_status = "stale"
            goal.last_reason = "No selectable subgoal exists; plan appears inconsistent or incomplete."
            _write_goal(ctx, goal)
            return "replan"

        selected.status = "active"
        goal.status = "active"
        goal.active_subgoal_id = selected.id
        plan.active_subgoal_id = selected.id
        goal.last_reason = f"Selected subgoal {selected.id}: {selected.title}"

        _refresh_goal_counts(goal, plan)
        _write_plan(ctx, plan)
        _write_goal(ctx, goal)
        _write_status_report(ctx, heading="Subgoal Selected")
        return "selected"

    @python_step(
        name="prepare_subgoal_session",
        requires=[goal, subgoals],
        writes=[status_report, run_context],
        routes={
            "ready": "work_subgoal",
            "replan": "plan_subgoals",
            "budget_limited": "wrap_up_budget_limited",
            "failed": FAIL,
        },
    )
    def prepare_subgoal_session(ctx):
        goal = _load_goal(ctx)
        plan = _load_plan(ctx)

        if goal.status == "budget_limited":
            _write_status_report(ctx, heading="Goal Budget Limited")
            return "budget_limited"

        active_id = plan.active_subgoal_id or goal.active_subgoal_id
        active = _find_subgoal(plan, active_id)
        if active is None:
            goal.planning_status = "stale"
            goal.active_subgoal_id = None
            plan.active_subgoal_id = None
            goal.last_reason = "No active subgoal exists while preparing a subgoal session."
            _write_plan(ctx, plan)
            _write_goal(ctx, goal)
            _write_status_report(ctx, heading="Subgoal Session Missing Active Work")
            return "replan"

        ctx.open_session("subgoal_session", key=f"{goal.goal_id}:{active.id}")
        _write_status_report(ctx, heading="Subgoal Session Prepared")
        return "ready"

    work_subgoal = produce_verify_step(
        name="work_subgoal",
        session=subgoal_session,
        verifier_session=subgoal_verifier_session,
        requires=[goal, subgoals],
        reads=[status_report, run_context, plan_audit, subgoal_progress, subgoal_audit],
        producer_writes=[subgoal_progress],
        verifier_writes=[subgoal_audit],
        producer_prompt=Prompt.inline(
            """
            Work on the currently active subgoal only.

            This provider session is scoped to the active subgoal. It will not
            contain conversation history from planning, final audits, or other
            subgoals. Reconstruct the run state from artifacts and current
            repository contents before acting.

            Read:
            - {{ workflow.folder }}/goal.json
            - {{ workflow.folder }}/subgoals.json
            - {{ workflow.folder }}/run_context.md for the current durable
              state, active subgoal contract, completed subgoals, and evidence
              index
            - {{ workflow.folder }}/status.md for the active subgoal, run
              status, known workflow artifacts, verifier criteria, evidence
              artifact references, and suggested commands
            - {{ workflow.folder }}/plan_audit.md, if present
            - prior {{ workflow.folder }}/subgoal_progress.md
            - prior {{ workflow.folder }}/subgoal_audit.md
            - every evidence_artifact declared for the active subgoal, if it
              exists; if an important evidence artifact is absent, record that
              as evidence for verifier judgment rather than treating it as a
              Botpipe runtime failure
            - relevant repository files and command output

            Rules:
            - Keep the parent goal in view, but only implement the active subgoal.
            - Do not mark the parent goal complete.
            - Do not broaden the subgoal beyond its verifier criteria.
            - If prior audit found rework, address every listed issue first.
            - Work from current artifacts and repository state, not provider
              memory.
            - Prefer targeted inspection and validation that proves the active
              subgoal. Avoid rerunning broad expensive checks unless needed to
              prove freshness or risk.

            Update {{ workflow.folder }}/subgoal_progress.md with:
            - active subgoal id and title
            - changes made
            - artifacts created, modified, or inspected
            - evidence inspected
            - commands/tests run and results
            - criteria addressed
            - remaining work
            - blockers, if any
            """.strip()
        ),
        verifier_prompt=Prompt.inline(
            """
            Verify the active subgoal only.

            This verifier session may be fresh. Reconstruct context from the
            artifacts and repository state. Do not rely on producer memory.

            Read:
            - {{ workflow.folder }}/goal.json
            - {{ workflow.folder }}/subgoals.json
            - {{ workflow.folder }}/run_context.md for current durable state
              and the evidence index
            - {{ workflow.folder }}/status.md for active-subgoal criteria,
              run status, known workflow artifacts, evidence_artifacts, and
              suggested commands
            - {{ workflow.folder }}/plan_audit.md, if present
            - {{ workflow.folder }}/subgoal_progress.md
            - prior {{ workflow.folder }}/subgoal_audit.md, if present
            - every evidence_artifact declared for the active subgoal, if it
              exists
            - relevant files, tests, command output, and artifacts

            Use the active subgoal's verifier_criteria as the acceptance
            contract. Do not mark complete unless every criterion is proven by
            current-state evidence. Do not substitute parent-goal progress for
            subgoal completion.

            Freshness policy:
            - Accept existing evidence when it is current, credible, and
              sufficient for the active criteria.
            - Run targeted checks when evidence is missing, stale, inconsistent,
              or too weak.
            - Do not blindly repeat expensive full validation when narrower
              checks or existing fresh evidence prove the criteria.

            Routes:
            - complete: every active-subgoal criterion is proven complete.
            - continue: meaningful progress was made but more work remains.
            - needs_rework: work is wrong, incomplete, or failed validation.
            - blocked: a concrete external blocker prevents this subgoal.
              Use the same blocker_fingerprint if the same blocker repeats.
            - question: user input is strictly required.

            Write {{ workflow.folder }}/subgoal_audit.md with:
            - decision
            - criteria-by-criteria audit
            - evidence inspected
            - exact remaining work or rework
            - blocker fingerprint and blocker reason when blocked
            """.strip()
        ),
        routes={
            "complete": Route.to(
                "subgoal_gate",
                summary="The active subgoal is fully complete.",
                required_writes=["subgoal_progress", "subgoal_audit"],
                route_fields_schema=SubgoalCompleteFields,
            ),
            "continue": Route.to(
                "subgoal_gate",
                summary="The active subgoal remains active.",
                required_writes=["subgoal_progress", "subgoal_audit"],
                route_fields_schema=ReasonRouteFields,
            ),
            "needs_rework": Route.to(
                "subgoal_gate",
                summary="The active subgoal needs rework.",
                required_writes=["subgoal_progress", "subgoal_audit"],
                route_fields_schema=ReasonRouteFields,
            ),
            "blocked": Route.to(
                "subgoal_gate",
                summary="The active subgoal may be blocked.",
                required_writes=["subgoal_progress", "subgoal_audit"],
                route_fields_schema=SubgoalBlockedFields,
            ),
            "question": Route.question(summary="Subgoal verification requires user input."),
        },
        after_verifier=_after_subgoal_verifier,
    )

    @python_step(
        name="subgoal_gate",
        requires=[goal, subgoals],
        writes=[goal, subgoals, status_report, run_context],
        routes={
            "continue": "select_next_subgoal",
            "budget_limited": "wrap_up_budget_limited",
        },
    )
    def subgoal_gate(ctx):
        goal = _load_goal(ctx)
        plan = _load_plan(ctx)
        active = _find_subgoal(plan, plan.active_subgoal_id or goal.active_subgoal_id)

        if goal.status == "budget_limited":
            return "budget_limited"

        if goal.token_budget is not None and goal.tokens_used >= goal.token_budget:
            goal.status = "budget_limited"
            goal.last_reason = "Goal token budget reached."
            _write_goal(ctx, goal)
            _write_status_report(ctx, heading="Goal Budget Limited")
            return "budget_limited"

        if goal.max_goal_turns is not None and goal.turns_completed >= goal.max_goal_turns:
            goal.status = "budget_limited"
            goal.last_reason = f"Maximum goal turns reached: {goal.max_goal_turns}."
            _write_goal(ctx, goal)
            _write_status_report(ctx, heading="Goal Turn Limited")
            return "budget_limited"

        if active is not None:
            if active.status == "complete":
                goal.active_subgoal_id = None
                plan.active_subgoal_id = None
            elif active.consecutive_blocked_turns >= 3:
                active.status = "blocked"
                active.last_reason = (
                    active.blocker_reason
                    or "Same blocker repeated for at least three consecutive subgoal turns."
                )
                goal.active_subgoal_id = None
                plan.active_subgoal_id = None

        _refresh_goal_counts(goal, plan)
        goal.status = "active"
        _write_plan(ctx, plan)
        _write_goal(ctx, goal)
        _write_status_report(ctx, heading="Subgoal Gate")
        return "continue"

    final_goal_audit = produce_verify_step(
        name="final_goal_audit",
        session=goal_session,
        verifier_session=final_verifier_session,
        requires=[goal, subgoals],
        reads=[status_report, run_context, subgoal_progress, subgoal_audit, plan_audit],
        producer_writes=[goal_summary],
        verifier_writes=[goal_audit],
        producer_prompt=Prompt.inline(
            """
            Prepare a final parent-goal completion packet.

            All subgoals are currently marked complete. This does not prove the
            parent goal is complete. This producer uses the main goal session,
            but current artifacts remain the source of truth. Read:
            - {{ workflow.folder }}/goal.json
            - {{ workflow.folder }}/subgoals.json
            - {{ workflow.folder }}/run_context.md
            - {{ workflow.folder }}/status.md
            - {{ workflow.folder }}/plan_audit.md
            - {{ workflow.folder }}/subgoal_progress.md
            - {{ workflow.folder }}/subgoal_audit.md
            - relevant current repository files and test output

            Write {{ workflow.folder }}/goal_summary.md with:
            - original parent objective
            - each subgoal and its completion evidence
            - remaining risks
            - commands/tests that prove final state
            - any missing work suspected
            """.strip()
        ),
        verifier_prompt=Prompt.inline(
            """
            Independently audit the original parent goal.

            Completion is still unproven even if every subgoal is marked
            complete. Use subgoal evidence as supporting evidence, not proof by
            itself. The verifier session may be fresh, so reconstruct the run
            state from artifacts and current repository contents.

            Read:
            - {{ workflow.folder }}/goal.json
            - {{ workflow.folder }}/subgoals.json
            - {{ workflow.folder }}/run_context.md
            - {{ workflow.folder }}/status.md
            - {{ workflow.folder }}/plan_audit.md
            - {{ workflow.folder }}/goal_summary.md
            - {{ workflow.folder }}/subgoal_progress.md
            - {{ workflow.folder }}/subgoal_audit.md
            - relevant source files, artifacts, tests, command output, and specs

            Freshness policy:
            - Use subgoal evidence as supporting evidence only when it is
              current, credible, and sufficient for the parent objective.
            - Run targeted checks for gaps, contradictions, or high-risk claims.
            - Do not rerun broad expensive validation solely because this is the
              final audit; rerun it when freshness or risk requires it.

            Routes:
            - complete: the original parent objective is fully satisfied.
            - needs_rework: existing subgoal work is incomplete or wrong.
              Include subgoal_ids when known.
            - replan: the subgoal plan missed requirements or the parent goal
              needs additional subgoals.
            - question: user input is strictly required.

            Write {{ workflow.folder }}/goal_audit.md with:
            - parent-goal requirement-by-requirement audit
            - evidence inspected
            - subgoals accepted/rejected as evidence
            - missing requirements or rework
            - final route decision
            """.strip()
        ),
        routes={
            "complete": Route.to(
                "finish_goal",
                summary="The parent goal is fully complete.",
                required_writes=["goal_summary", "goal_audit"],
                route_fields_schema=FinalCompleteFields,
            ),
            "needs_rework": Route.to(
                "final_goal_gate",
                summary="Completed subgoal work does not actually satisfy the parent goal.",
                required_writes=["goal_summary", "goal_audit"],
                route_fields_schema=FinalNeedsReworkFields,
            ),
            "replan": Route.to(
                "final_goal_gate",
                summary="The subgoal plan missed parent-goal requirements.",
                required_writes=["goal_summary", "goal_audit"],
                route_fields_schema=FinalReplanFields,
            ),
            "question": Route.question(summary="Final audit requires user input."),
        },
        after_verifier=_after_final_goal_verifier,
    )

    @python_step(
        name="final_goal_gate",
        requires=[goal, subgoals],
        writes=[goal, subgoals, status_report, run_context],
        routes={
            "replan": "plan_subgoals",
            "rework": "select_next_subgoal",
            "budget_limited": "wrap_up_budget_limited",
        },
    )
    def final_goal_gate(ctx):
        goal = _load_goal(ctx)
        plan = _load_plan(ctx)

        if goal.status == "budget_limited":
            return "budget_limited"

        if goal.token_budget is not None and goal.tokens_used >= goal.token_budget:
            goal.status = "budget_limited"
            goal.last_reason = "Goal token budget reached during final audit."
            _write_goal(ctx, goal)
            _write_status_report(ctx, heading="Goal Budget Limited")
            return "budget_limited"

        if goal.planning_status == "stale":
            _write_status_report(ctx, heading="Goal Requires Replan")
            return "replan"

        _refresh_goal_counts(goal, plan)
        goal.status = "active"
        _write_plan(ctx, plan)
        _write_goal(ctx, goal)
        _write_status_report(ctx, heading="Goal Requires Rework")
        return "rework"

    @python_step(
        name="finish_goal",
        requires=[goal, subgoals],
        reads=[goal_summary, goal_audit],
        writes=[goal, subgoals, final_report],
        routes={"done": FINISH},
    )
    def finish_goal(ctx):
        goal = _load_goal(ctx)
        plan = _load_plan(ctx)

        fields = _event_fields(ctx)
        goal.status = "complete"
        goal.completed_at = goal.completed_at or _now()
        goal.completion_summary = (
            _clean_text(fields.get("completion_summary"))
            or goal.completion_summary
            or "Final audit proved the parent goal complete."
        )
        goal.active_subgoal_id = None
        plan.active_subgoal_id = None
        _refresh_goal_counts(goal, plan)

        _write_plan(ctx, plan)
        _write_goal(ctx, goal)

        token_budget = goal.token_budget if goal.token_budget is not None else "none"
        lines = [
            "# Goal Complete",
            "",
            f"Goal id: `{goal.goal_id}`",
            "",
            "## Objective",
            "",
            goal.objective,
            "",
            "## Completion Summary",
            "",
            goal.completion_summary or "(see goal audit)",
            "",
            "## Subgoals",
            "",
        ]
        for subgoal in plan.subgoals:
            lines.append(f"- `{subgoal.id}` [{subgoal.status}] {subgoal.title}")
        lines.extend(
            [
                "",
                "## Usage",
                "",
                f"- Tokens used: {goal.tokens_used}",
                f"- Token budget: {token_budget}",
                f"- Time used seconds: {goal.time_used_seconds}",
                f"- Goal turns completed: {goal.turns_completed}",
                "",
                "## Evidence",
                "",
                f"- Goal summary: `{ctx.artifacts.goal_summary.path}`",
                f"- Goal audit: `{ctx.artifacts.goal_audit.path}`",
                f"- Run context: `{ctx.artifacts.run_context.path}`",
                f"- Subgoal plan: `{ctx.artifacts.subgoals.path}`",
                f"- Subgoal progress: `{ctx.artifacts.subgoal_progress.path}`",
                f"- Subgoal audit: `{ctx.artifacts.subgoal_audit.path}`",
                "",
            ]
        )
        ctx.artifacts.final_report.write_text("\n".join(lines))
        return "done"

    @python_step(
        name="mark_parent_blocked",
        requires=[goal, subgoals],
        writes=[goal, subgoals, final_report],
        routes={"done": FINISH},
    )
    def mark_parent_blocked(ctx):
        goal = _load_goal(ctx)
        plan = _load_plan(ctx)

        goal.status = "blocked"
        goal.active_subgoal_id = None
        plan.active_subgoal_id = None
        goal.last_reason = goal.last_reason or "No selectable incomplete subgoals remain; remaining paths are blocked."

        _write_plan(ctx, plan)
        _write_goal(ctx, goal)

        blocked = [item for item in plan.subgoals if item.status == "blocked"]
        lines = [
            "# Goal Blocked",
            "",
            f"Goal id: `{goal.goal_id}`",
            "",
            "## Objective",
            "",
            goal.objective,
            "",
            "## Blocked Subgoals",
            "",
        ]
        if blocked:
            for item in blocked:
                lines.append(f"- `{item.id}` {item.title}: {item.blocker_reason or item.last_reason or 'blocked'}")
        else:
            lines.append("- No specific blocked subgoal recorded.")
        lines.extend(
            [
                "",
                "## Usage",
                "",
                f"- Tokens used: {goal.tokens_used}",
                f"- Token budget: {goal.token_budget if goal.token_budget is not None else 'none'}",
                f"- Time used seconds: {goal.time_used_seconds}",
                "",
            ]
        )
        ctx.artifacts.final_report.write_text("\n".join(lines))
        return "done"

    wrap_up_budget_limited = step(
        Prompt.inline(
            """
            The active parent goal has reached its token budget or deterministic
            turn limit.

            Do not start new substantive work. Wrap up this goal run:
            - summarize useful progress
            - identify completed subgoals
            - identify remaining subgoals
            - identify blockers
            - give the next concrete step for a future resumed/replaced goal

            Read:
            - {{ workflow.folder }}/goal.json
            - {{ workflow.folder }}/subgoals.json, if present
            - {{ workflow.folder }}/run_context.md, if present
            - {{ workflow.folder }}/subgoal_progress.md, if present
            - {{ workflow.folder }}/subgoal_audit.md, if present
            - {{ workflow.folder }}/goal_audit.md, if present

            Write {{ workflow.folder }}/final_report.md.
            """.strip()
        ),
        name="wrap_up_budget_limited",
        session=goal_session,
        requires=[goal],
        reads=[subgoals, run_context, subgoal_progress, subgoal_audit, goal_audit],
        writes=[final_report],
        routes={
            "done": Route.to(
                FINISH,
                summary="Budget-limited wrap-up is written.",
                required_writes=["final_report"],
                route_fields_schema=ReasonRouteFields,
            )
        },
    )

    entry = initialize_goal

    @staticmethod
    def build_output(state: GoalWorkflowState, ctx) -> GoalWorkflowOutput:
        goal_handle = ctx.artifacts["goal"]
        subgoals_handle = ctx.artifacts["subgoals"]
        status_handle = ctx.artifacts["status_report"]
        final_handle = ctx.artifacts["final_report"]

        if goal_handle.exists():
            goal = GoalRecord.model_validate_json(goal_handle.read_text())
            return GoalWorkflowOutput(
                status=goal.status,
                goal_id=goal.goal_id,
                objective=goal.objective,
                planning_status=goal.planning_status,
                active_subgoal_id=goal.active_subgoal_id,
                completed_subgoal_count=goal.completed_subgoal_count,
                total_subgoal_count=goal.total_subgoal_count,
                tokens_used=goal.tokens_used,
                token_budget=goal.token_budget,
                time_used_seconds=goal.time_used_seconds,
                goal_path=str(goal_handle.path),
                subgoals_path=str(subgoals_handle.path),
                status_report_path=str(status_handle.path) if status_handle.exists() else None,
                final_report_path=str(final_handle.path) if final_handle.exists() else None,
            )

        return GoalWorkflowOutput(
            status=state.status,
            planning_status=state.planning_status,
            active_subgoal_id=state.active_subgoal_id,
            goal_path=str(goal_handle.path),
            subgoals_path=str(subgoals_handle.path),
            status_report_path=str(status_handle.path) if status_handle.exists() else None,
            final_report_path=str(final_handle.path) if final_handle.exists() else None,
        )
