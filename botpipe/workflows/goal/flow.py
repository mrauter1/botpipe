"""Persistent subgoal workflow equivalent to the ``/goal`` command family."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from botpipe import (
    Artifact,
    OutputValidationError,
    Provider,
    Session,
    activity,
    ask_human,
    current_run,
    workflow,
)

GoalStatus = Literal[
    "active", "paused", "blocked", "usage_limited", "budget_limited", "complete"
]
PlanningStatus = Literal["unplanned", "planned", "stale"]
GoalAction = Literal["set", "status", "pause", "resume", "clear", "edit", "replan"]
SubgoalStatus = Literal[
    "pending", "active", "needs_rework", "blocked", "complete", "skipped"
]


class GoalWorkflowInput(BaseModel):
    action: GoalAction = "set"
    objective: str | None = None
    replace_existing: bool = False
    allow_replace_completed: bool = True
    token_budget: int | None = Field(default=None, gt=0)
    max_goal_turns: int | None = Field(default=None, ge=1)


class GoalRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_id: Literal["botpipe.goal/v2"] = Field(
        default="botpipe.goal/v2", alias="schema"
    )
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
    def migrate_required_artifacts(cls, value: object) -> object:
        if (
            isinstance(value, dict)
            and "evidence_artifacts" not in value
            and "required_artifacts" in value
        ):
            value = dict(value)
            value["evidence_artifacts"] = value.get("required_artifacts")
        return value


class SubgoalPlan(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_id: Literal["botpipe.goal.subgoals/v1"] = Field(
        default="botpipe.goal.subgoals/v1", alias="schema"
    )
    goal_id: str = ""
    active_subgoal_id: str | None = None
    subgoals: list[SubgoalRecord] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


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


class PlanDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["accepted", "needs_rework"]
    reason: str | None = None
    coverage_summary: str = ""
    risks: list[str] = Field(default_factory=list)


class SubgoalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["complete", "continue", "needs_rework", "blocked"]
    reason: str
    completion_summary: str | None = None
    criteria_results: dict[str, str] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    blocker_fingerprint: str | None = None
    blocked_criteria: list[str] = Field(default_factory=list)


class FinalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["complete", "needs_rework", "replan"]
    reason: str
    completion_summary: str | None = None
    evidence: list[str] = Field(default_factory=list)
    subgoal_ids: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_write(path: Path, value: BaseModel | dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        value.model_dump(mode="json", by_alias=True)
        if isinstance(value, BaseModel)
        else value
    )
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


@activity
def _read_goal(path: str) -> GoalRecord | None:
    target = Path(path)
    if not target.is_file():
        return None
    return GoalRecord.model_validate_json(target.read_text(encoding="utf-8"))


@activity
def _read_plan(path: str) -> SubgoalPlan | None:
    target = Path(path)
    if not target.is_file():
        return None
    return SubgoalPlan.model_validate_json(target.read_text(encoding="utf-8"))


@activity
def _save_state(
    goal_path: str, goal: GoalRecord, plan_path: str, plan: SubgoalPlan | None
) -> tuple[GoalRecord, SubgoalPlan | None]:
    goal = goal.model_copy(deep=True)
    goal.updated_at = _now()
    _json_write(Path(goal_path), goal)
    if plan is not None:
        plan = plan.model_copy(deep=True)
        plan.updated_at = _now()
        if not plan.created_at:
            plan.created_at = plan.updated_at
        _json_write(Path(plan_path), plan)
    return goal, plan


@activity
def _new_goal(
    task_id: str, objective: str, token_budget: int | None, max_goal_turns: int | None
) -> GoalRecord:
    timestamp = _now()
    return GoalRecord(
        thread_id=task_id,
        goal_id=uuid4().hex,
        objective=objective,
        status="active",
        token_budget=token_budget,
        max_goal_turns=max_goal_turns,
        created_at=timestamp,
        updated_at=timestamp,
    )


@activity(retry_safe=True)
def _timestamp() -> str:
    return _now()


@activity
def _clear_state(goal_path: str, plan_path: str) -> None:
    Path(goal_path).unlink(missing_ok=True)
    Path(plan_path).unlink(missing_ok=True)


@activity
def _write_report(path: str, text: str) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text.rstrip() + "\n", encoding="utf-8")
    return str(target)


def _find(plan: SubgoalPlan, item_id: str | None) -> SubgoalRecord | None:
    return next((item for item in plan.subgoals if item.id == item_id), None)


def _refresh(goal: GoalRecord, plan: SubgoalPlan) -> None:
    goal.total_subgoal_count = len(plan.subgoals)
    goal.completed_subgoal_count = sum(
        item.status == "complete" for item in plan.subgoals
    )


def _validate_plan(plan: SubgoalPlan, goal: GoalRecord) -> str | None:
    if not plan.subgoals:
        return "subgoals.json must contain at least one subgoal"
    ids = [item.id.strip() for item in plan.subgoals]
    if any(not item for item in ids) or len(ids) != len(set(ids)):
        return "subgoal ids must be non-empty and unique"
    known = set(ids)
    for item in plan.subgoals:
        if (
            not item.title.strip()
            or not item.description.strip()
            or not item.verifier_criteria
        ):
            return (
                f"subgoal {item.id!r} needs a title, description, and verifier criteria"
            )
        if item.id in item.dependencies or any(
            dep not in known for dep in item.dependencies
        ):
            return f"subgoal {item.id!r} has an invalid dependency"
    visiting: set[str] = set()
    visited: set[str] = set()
    by_id = {item.id: item for item in plan.subgoals}

    def visit(item_id: str) -> bool:
        if item_id in visiting:
            return False
        if item_id in visited:
            return True
        visiting.add(item_id)
        if not all(visit(dep) for dep in by_id[item_id].dependencies):
            return False
        visiting.remove(item_id)
        visited.add(item_id)
        return True

    if not all(visit(item_id) for item_id in ids):
        return "subgoal dependency cycle detected"
    plan.goal_id = goal.goal_id
    return None


def _select(plan: SubgoalPlan) -> SubgoalRecord | None:
    completed = {item.id for item in plan.subgoals if item.status == "complete"}
    active = _find(plan, plan.active_subgoal_id)
    if (
        active
        and active.status in {"pending", "active", "needs_rework"}
        and set(active.dependencies) <= completed
    ):
        return active
    candidates = [
        item
        for item in plan.subgoals
        if item.status in {"pending", "active", "needs_rework"}
        and set(item.dependencies) <= completed
    ]
    return min(candidates, key=lambda item: (item.priority, item.id), default=None)


def _usage_tokens(usage: Any) -> int:
    if not isinstance(usage, dict):
        return 0
    for key in ("total_tokens", "tokens", "token_count"):
        value = usage.get(key)
        if isinstance(value, int):
            return max(0, value)
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if isinstance(input_tokens, int) or isinstance(output_tokens, int):
        cached = usage.get("cached_input_tokens")
        uncached_input = max(0, int(input_tokens or 0) - int(cached or 0))
        return uncached_input + max(0, int(output_tokens or 0))
    return sum(
        _usage_tokens(value) for value in usage.values() if isinstance(value, dict)
    )


def _charge(goal: GoalRecord, subgoal: SubgoalRecord | None, *results: Any) -> None:
    tokens = sum(_usage_tokens(getattr(result, "usage", None)) for result in results)
    goal.tokens_used += tokens
    if subgoal is not None:
        subgoal.tokens_used += tokens


def _goal_turn(
    provider: Provider,
    prompt: str,
    goal_record: GoalRecord,
    plan: SubgoalPlan | None,
    goal_path: Path,
    plan_path: Path,
    *,
    subgoal: SubgoalRecord | None = None,
    **kwargs: Any,
):
    """Persist usage from an exhausted output-contract repair before failing."""
    try:
        return provider.run(prompt, **kwargs)
    except OutputValidationError as exc:
        tokens = _usage_tokens(getattr(exc, "usage", {}))
        goal_record.tokens_used += tokens
        if subgoal is not None:
            subgoal.tokens_used += tokens
        _save_state(str(goal_path), goal_record, str(plan_path), plan)
        raise


def _limited(goal: GoalRecord) -> str | None:
    if goal.token_budget is not None and goal.tokens_used >= goal.token_budget:
        return "Goal token budget reached."
    if goal.max_goal_turns is not None and goal.turns_completed >= goal.max_goal_turns:
        return f"Maximum goal turns reached: {goal.max_goal_turns}."
    return None


def _status_text(goal: GoalRecord | None, plan: SubgoalPlan | None) -> str:
    if goal is None:
        return "# Goal Status\n\nNo goal is currently set.\n"
    lines = [
        "# Goal Status",
        "",
        f"- Goal id: `{goal.goal_id}`",
        f"- Status: `{goal.status}`",
        f"- Planning status: `{goal.planning_status}`",
        f"- Objective: {goal.objective}",
        f"- Active subgoal: `{goal.active_subgoal_id or '(none)'}`",
        f"- Completed subgoals: {goal.completed_subgoal_count}/{goal.total_subgoal_count}",
        f"- Tokens used: {goal.tokens_used}",
        f"- Token budget: {goal.token_budget or 'none'}",
        f"- Goal turns: {goal.turns_completed}/{goal.max_goal_turns or 'unbounded'}",
        "",
    ]
    if plan:
        lines.extend(["## Subgoals", ""])
        lines.extend(
            f"- `{item.id}` [{item.status}] {item.title}" for item in plan.subgoals
        )
    return "\n".join(lines) + "\n"


def _output(
    goal_path: Path,
    plan_path: Path,
    status_path: Path,
    final_path: Path,
    goal: GoalRecord | None,
    fallback: Literal["missing", "cleared"] = "missing",
) -> GoalWorkflowOutput:
    if goal is None:
        return GoalWorkflowOutput(
            status=fallback,
            goal_path=str(goal_path),
            subgoals_path=str(plan_path),
            status_report_path=str(status_path) if status_path.exists() else None,
            final_report_path=str(final_path) if final_path.exists() else None,
        )
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
        goal_path=str(goal_path),
        subgoals_path=str(plan_path),
        status_report_path=str(status_path) if status_path.exists() else None,
        final_report_path=str(final_path) if final_path.exists() else None,
    )


PLAN = """Decompose the supplied durable parent goal into the smallest sufficient set of auditable subgoals.
Inspect the repository and feedback. Write subgoals.json using the declared SubgoalPlan schema. Every subgoal needs
a stable id, bounded description, concrete verifier criteria, coherent earlier dependencies, priority, evidence
references, and useful suggested commands. Preserve still-valid completed work when replanning."""

PLAN_REVIEW = """Independently audit the supplied subgoal plan against the original parent objective and repository.
Accept only when all requirements are covered, every subgoal is coherent and auditable, and dependencies are acyclic.
Write plan_audit.md and return a structured accepted or needs_rework verdict."""

WORK = """Work only on the supplied active subgoal. Reconstruct state from goal.json, subgoals.json, status, prior
progress, prior audit, repository files, and declared evidence. Implement and validate the subgoal without broadening
it. Write subgoal_progress.md with changes, evidence, commands, results, remaining work, and blockers."""

VERIFY = """Independently verify only the supplied active subgoal against every verifier criterion. Use current,
credible evidence and targeted checks. Write subgoal_audit.md. Return complete, continue, needs_rework, or blocked;
blocked requires a stable blocker_fingerprint. Do not infer parent-goal completion from this review."""

FINAL = """Prepare a final completion packet for the original parent objective. Use all completed subgoals as
supporting evidence, inspect the current repository, identify risks and validation, and write goal_summary.md."""

FINAL_VERIFY = """Independently audit the original parent objective requirement by requirement. Completed subgoals
are supporting evidence only. Write goal_audit.md and return complete, needs_rework with affected subgoal_ids, or
replan with missing requirements. Require current credible evidence for every completion claim."""


def _options(
    value: GoalWorkflowInput | dict[str, Any] | str | None,
    *,
    action: GoalAction | None,
    objective: str | None,
    replace_existing: bool,
    allow_replace_completed: bool,
    token_budget: int | None,
    max_goal_turns: int | None,
) -> GoalWorkflowInput:
    if isinstance(value, GoalWorkflowInput):
        base = value.model_dump()
    elif isinstance(value, dict):
        base = dict(value)
    elif isinstance(value, str):
        base = {"objective": value}
    else:
        base = {}
    explicit = {
        "action": action,
        "objective": objective,
        "token_budget": token_budget,
        "max_goal_turns": max_goal_turns,
    }
    base.update({key: item for key, item in explicit.items() if item is not None})
    if "replace_existing" not in base:
        base["replace_existing"] = replace_existing
    if "allow_replace_completed" not in base:
        base["allow_replace_completed"] = allow_replace_completed
    return GoalWorkflowInput.model_validate(base)


@workflow(name="goal", version="1")
def goal(
    input: GoalWorkflowInput | dict[str, Any] | str | None = None,
    *,
    action: GoalAction | None = None,
    objective: str | None = None,
    replace_existing: bool = False,
    allow_replace_completed: bool = True,
    token_budget: int | None = None,
    max_goal_turns: int | None = None,
) -> GoalWorkflowOutput:
    options = _options(
        input,
        action=action,
        objective=objective,
        replace_existing=replace_existing,
        allow_replace_completed=allow_replace_completed,
        token_budget=token_budget,
        max_goal_turns=max_goal_turns,
    )
    ctx = current_run()
    folder = ctx.task_folder / "goal"
    goal_path, plan_path = folder / "goal.json", folder / "subgoals.json"
    status_path, final_path = folder / "status.md", folder / "final_report.md"
    goal_record = _read_goal(str(goal_path))
    plan = _read_plan(str(plan_path))

    if options.action == "status":
        _write_report(str(status_path), _status_text(goal_record, plan))
        return _output(goal_path, plan_path, status_path, final_path, goal_record)
    if options.action == "clear":
        _clear_state(str(goal_path), str(plan_path))
        _write_report(str(status_path), "# Goal cleared")
        return _output(goal_path, plan_path, status_path, final_path, None, "cleared")
    if options.action == "pause":
        if goal_record is not None and goal_record.status != "complete":
            goal_record.status, goal_record.last_reason = "paused", "Paused by user."
            goal_record, plan = _save_state(
                str(goal_path), goal_record, str(plan_path), plan
            )
        _write_report(str(status_path), _status_text(goal_record, plan))
        return _output(goal_path, plan_path, status_path, final_path, goal_record)

    if options.action in {"resume", "edit", "replan"} and goal_record is None:
        objective_answer = ask_human(
            "No goal exists. What objective should be set?", returns=str
        )
        options = options.model_copy(
            update={"action": "set", "objective": objective_answer}
        )

    if options.action == "resume":
        if goal_record.status == "complete":
            return _output(goal_path, plan_path, status_path, final_path, goal_record)
        goal_record.status = "active"
        goal_record.last_reason = "Resumed by user."
        if options.token_budget is not None:
            goal_record.token_budget = options.token_budget
        if options.max_goal_turns is not None:
            goal_record.max_goal_turns = options.max_goal_turns
        if goal_record.planning_status != "planned" or plan is None:
            goal_record.planning_status = "stale"
    elif options.action in {"edit", "replan"}:
        if goal_record.status == "complete":
            return _output(goal_path, plan_path, status_path, final_path, goal_record)
        if options.action == "edit":
            edited = (options.objective or "").strip() or ask_human(
                "What is the revised objective?", returns=str
            )
            goal_record.objective = edited
        goal_record.status, goal_record.planning_status = "active", "stale"
        goal_record.active_subgoal_id = None
        goal_record.last_reason = (
            "Objective edited; plan is stale."
            if options.action == "edit"
            else "Replan requested."
        )
        if options.token_budget is not None:
            goal_record.token_budget = options.token_budget
        if options.max_goal_turns is not None:
            goal_record.max_goal_turns = options.max_goal_turns
    elif options.action == "set":
        requested = (options.objective or "").strip() or ask_human(
            "What objective should this goal pursue?", returns=str
        )
        if (
            goal_record is not None
            and goal_record.status != "complete"
            and not options.replace_existing
        ):
            replace = ask_human(
                "An active goal exists. Replace it? Return true or false.", returns=bool
            )
            if not replace:
                _write_report(str(status_path), _status_text(goal_record, plan))
                return _output(
                    goal_path, plan_path, status_path, final_path, goal_record
                )
        if (
            goal_record is not None
            and goal_record.status == "complete"
            and not options.allow_replace_completed
        ):
            return _output(goal_path, plan_path, status_path, final_path, goal_record)
        goal_record = _new_goal(
            ctx.task_id, requested, options.token_budget, options.max_goal_turns
        )
        plan = None

    goal_record, plan = _save_state(str(goal_path), goal_record, str(plan_path), plan)
    _write_report(str(status_path), _status_text(goal_record, plan))
    goal_spec = Artifact.json(
        str(goal_path), name="goal", schema=GoalRecord, required=True
    )
    plan_spec = Artifact.json(
        str(plan_path), name="subgoals", schema=SubgoalPlan, required=True
    )
    status_spec = Artifact.md(str(status_path), name="status_report")
    plan_audit = Artifact.md(
        str(folder / "plan_audit.md"), name="plan_audit", required=True
    )
    progress = Artifact.md(
        str(folder / "subgoal_progress.md"), name="subgoal_progress", required=True
    )
    subgoal_audit = Artifact.md(
        str(folder / "subgoal_audit.md"), name="subgoal_audit", required=True
    )
    goal_summary = Artifact.md(
        str(folder / "goal_summary.md"), name="goal_summary", required=True
    )
    goal_audit = Artifact.md(
        str(folder / "goal_audit.md"), name="goal_audit", required=True
    )
    goal_session = Provider(session=Session.task(key="goal-main"))
    latest_plan_audit = None
    latest_subgoal_audit = None

    while True:
        limit = _limited(goal_record)
        if limit:
            goal_record.status, goal_record.last_reason = "budget_limited", limit
            goal_record, plan = _save_state(
                str(goal_path), goal_record, str(plan_path), plan
            )
            _write_report(
                str(final_path),
                f"# Goal Budget Limited\n\n{limit}\n\n{_status_text(goal_record, plan)}",
            )
            return _output(goal_path, plan_path, status_path, final_path, goal_record)

        if goal_record.planning_status != "planned" or plan is None:
            planning_feedback: tuple[Any, ...] = ()
            while True:
                proposed = _goal_turn(
                    goal_session,
                    PLAN,
                    goal_record,
                    plan,
                    goal_path,
                    plan_path,
                    input={"goal": goal_record.model_dump(mode="json")},
                    reads=(goal_spec.path, status_spec.path, *planning_feedback),
                    writes=(plan_spec,),
                )
                _charge(goal_record, None, proposed)
                if _limited(goal_record):
                    break
                try:
                    candidate = SubgoalPlan.model_validate_json(
                        proposed.artifacts.subgoals.read_text()
                    )
                    error = _validate_plan(candidate, goal_record)
                except Exception as exc:
                    error = str(exc)
                    candidate = None
                if error:
                    planning_feedback = (proposed.artifacts.subgoals,)
                    if _limited(goal_record):
                        break
                    continue
                reviewed = _goal_turn(
                    goal_session.with_config(session=None),
                    PLAN_REVIEW,
                    goal_record,
                    plan,
                    goal_path,
                    plan_path,
                    input={
                        "goal": goal_record.model_dump(mode="json"),
                        "plan": candidate.model_dump(mode="json"),
                    },
                    reads=(goal_spec.path, proposed.artifacts.subgoals),
                    writes=(plan_audit,),
                    returns=PlanDecision,
                )
                _charge(goal_record, None, reviewed)
                if reviewed.value.verdict == "accepted":
                    plan = candidate
                    latest_plan_audit = reviewed.artifacts.plan_audit
                    break
                planning_feedback = (reviewed.artifacts.plan_audit,)
                if _limited(goal_record):
                    break
            if plan is None or _limited(goal_record):
                continue
            goal_record.planning_status = "planned"
            goal_record.status = "active"
            goal_record.active_subgoal_id = None
            plan.active_subgoal_id = None
            _refresh(goal_record, plan)
            goal_record, plan = _save_state(
                str(goal_path), goal_record, str(plan_path), plan
            )

        if all(item.status == "complete" for item in plan.subgoals):
            summary_turn = _goal_turn(
                goal_session,
                FINAL,
                goal_record,
                plan,
                goal_path,
                plan_path,
                input={
                    "goal": goal_record.model_dump(mode="json"),
                    "plan": plan.model_dump(mode="json"),
                },
                reads=(
                    goal_spec.path,
                    plan_spec.path,
                    status_spec.path,
                    progress.path,
                    subgoal_audit.path,
                    plan_audit.path,
                ),
                writes=(goal_summary,),
            )
            _charge(goal_record, None, summary_turn)
            limit = _limited(goal_record)
            if limit:
                goal_record.status, goal_record.last_reason = "budget_limited", limit
                goal_record, plan = _save_state(
                    str(goal_path), goal_record, str(plan_path), plan
                )
                _write_report(
                    str(final_path),
                    f"# Goal Budget Limited\n\n{limit}\n\n{_status_text(goal_record, plan)}",
                )
                return _output(
                    goal_path, plan_path, status_path, final_path, goal_record
                )
            final_turn = _goal_turn(
                goal_session.with_config(session=None),
                FINAL_VERIFY,
                goal_record,
                plan,
                goal_path,
                plan_path,
                input={
                    "goal": goal_record.model_dump(mode="json"),
                    "plan": plan.model_dump(mode="json"),
                },
                reads=(
                    goal_spec.path,
                    plan_spec.path,
                    summary_turn.artifacts.goal_summary,
                    progress.path,
                    subgoal_audit.path,
                ),
                writes=(goal_audit,),
                returns=FinalDecision,
            )
            _charge(goal_record, None, final_turn)
            decision = final_turn.value
            if decision.verdict == "complete":
                goal_record.status = "complete"
                goal_record.completed_at = _timestamp()
                goal_record.completion_summary = (
                    decision.completion_summary or decision.reason
                )
                goal_record.active_subgoal_id = plan.active_subgoal_id = None
                _refresh(goal_record, plan)
                goal_record, plan = _save_state(
                    str(goal_path), goal_record, str(plan_path), plan
                )
                _write_report(
                    str(final_path),
                    f"# Goal Complete\n\n## Objective\n\n{goal_record.objective}\n\n"
                    f"## Completion Summary\n\n{goal_record.completion_summary}\n",
                )
                _write_report(str(status_path), _status_text(goal_record, plan))
                return _output(
                    goal_path, plan_path, status_path, final_path, goal_record
                )
            if decision.verdict == "replan":
                goal_record.planning_status = "stale"
                goal_record.last_reason = decision.reason
                plan.active_subgoal_id = goal_record.active_subgoal_id = None
                goal_record, plan = _save_state(
                    str(goal_path), goal_record, str(plan_path), plan
                )
                continue
            requested = set(decision.subgoal_ids) or {item.id for item in plan.subgoals}
            for item in plan.subgoals:
                if item.id in requested:
                    item.status, item.completed_at, item.last_reason = (
                        "needs_rework",
                        None,
                        decision.reason,
                    )
            goal_record.last_reason = decision.reason
            goal_record, plan = _save_state(
                str(goal_path), goal_record, str(plan_path), plan
            )
            continue

        selected = _select(plan)
        if selected is None:
            goal_record.status = "blocked"
            goal_record.last_reason = "No selectable incomplete subgoals remain."
            goal_record.active_subgoal_id = plan.active_subgoal_id = None
            goal_record, plan = _save_state(
                str(goal_path), goal_record, str(plan_path), plan
            )
            _write_report(
                str(final_path), f"# Goal Blocked\n\n{goal_record.last_reason}\n"
            )
            return _output(goal_path, plan_path, status_path, final_path, goal_record)

        selected.status = "active"
        goal_record.active_subgoal_id = plan.active_subgoal_id = selected.id
        _refresh(goal_record, plan)
        goal_record, plan = _save_state(
            str(goal_path), goal_record, str(plan_path), plan
        )
        selected = _find(plan, goal_record.active_subgoal_id)
        assert selected is not None
        _write_report(str(status_path), _status_text(goal_record, plan))
        provider = goal_session.with_config(
            session=Session.task(key=f"goal:{goal_record.goal_id}:{selected.id}")
        )
        work_reads: list[Any] = [goal_spec.path, plan_spec.path, status_spec.path]
        if latest_plan_audit is not None:
            work_reads.append(latest_plan_audit)
        if latest_subgoal_audit is not None:
            work_reads.append(latest_subgoal_audit)
        work_turn = _goal_turn(
            provider,
            WORK,
            goal_record,
            plan,
            goal_path,
            plan_path,
            subgoal=selected,
            input={
                "goal": goal_record.model_dump(mode="json"),
                "subgoal": selected.model_dump(mode="json"),
            },
            reads=tuple(work_reads),
            writes=(progress,),
        )
        _charge(goal_record, selected, work_turn)
        limit = _limited(goal_record)
        if limit:
            goal_record.status, goal_record.last_reason = "budget_limited", limit
            goal_record, plan = _save_state(
                str(goal_path), goal_record, str(plan_path), plan
            )
            _write_report(
                str(final_path),
                f"# Goal Budget Limited\n\n{limit}\n\n{_status_text(goal_record, plan)}",
            )
            return _output(goal_path, plan_path, status_path, final_path, goal_record)
        verify_reads: list[Any] = [
            goal_spec.path,
            plan_spec.path,
            work_turn.artifacts.subgoal_progress,
        ]
        if latest_subgoal_audit is not None:
            verify_reads.append(latest_subgoal_audit)
        verify_turn = _goal_turn(
            goal_session.with_config(session=None),
            VERIFY,
            goal_record,
            plan,
            goal_path,
            plan_path,
            subgoal=selected,
            input={
                "goal": goal_record.model_dump(mode="json"),
                "subgoal": selected.model_dump(mode="json"),
            },
            reads=tuple(verify_reads),
            writes=(subgoal_audit,),
            returns=SubgoalDecision,
        )
        _charge(goal_record, selected, verify_turn)
        goal_record.turns_completed += 1
        selected.turns_completed += 1
        selected.last_verifier_route = verify_turn.value.verdict
        selected.last_reason = verify_turn.value.reason
        decision = verify_turn.value
        latest_subgoal_audit = verify_turn.artifacts.subgoal_audit
        if decision.verdict == "complete":
            selected.status = "complete"
            selected.completion_summary = decision.completion_summary or decision.reason
            selected.criteria_results = decision.criteria_results
            selected.evidence = decision.evidence
            selected.completed_at = _timestamp()
            selected.blocker_fingerprint = selected.blocker_reason = None
            selected.consecutive_blocked_turns = 0
            goal_record.active_subgoal_id = plan.active_subgoal_id = None
        elif decision.verdict == "blocked":
            fingerprint = decision.blocker_fingerprint or "unspecified-blocker"
            selected.consecutive_blocked_turns = (
                selected.consecutive_blocked_turns + 1
                if selected.blocker_fingerprint == fingerprint
                else 1
            )
            selected.blocker_fingerprint, selected.blocker_reason = (
                fingerprint,
                decision.reason,
            )
            if selected.consecutive_blocked_turns >= 3:
                selected.status = "blocked"
                goal_record.active_subgoal_id = plan.active_subgoal_id = None
        elif decision.verdict == "needs_rework":
            selected.status = "needs_rework"
            selected.consecutive_blocked_turns = 0
        else:
            selected.status = "active"
            selected.consecutive_blocked_turns = 0
        _refresh(goal_record, plan)
        goal_record, plan = _save_state(
            str(goal_path), goal_record, str(plan_path), plan
        )


GoalWorkflow = goal
Params = GoalWorkflowInput

__all__ = [
    "FinalDecision",
    "GoalRecord",
    "GoalWorkflow",
    "GoalWorkflowInput",
    "GoalWorkflowOutput",
    "Params",
    "PlanDecision",
    "SubgoalDecision",
    "SubgoalPlan",
    "SubgoalRecord",
    "goal",
]
