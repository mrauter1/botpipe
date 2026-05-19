"""Packaged goal workflow inspired by Codex CLI `/goal`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from botpipe import Event, FAIL, FINISH, Prompt, Route, Workflow, produce_verify_step, python_step
from botpipe.core import Artifact


GOAL_SCHEMA_VERSION = "botpipe.goal/v1"
GOAL_PLAN_SCHEMA_VERSION = "botpipe.goal_plan/v1"
GOAL_OBJECTIVE_MAX_CHARS = 4000
DEFAULT_ACCEPTANCE_CRITERIA = (
    "The stated objective is completely satisfied.",
    "All relevant implementation and verification work has been performed.",
    "No known regressions, unresolved blockers, or incomplete todo items remain.",
)
_DONE_ITEM_STATUSES = {"accepted", "complete", "completed", "done", "passed"}

GoalStatus = Literal["unset", "active", "paused", "met"]
GoalAction = Literal["view", "set", "pause", "resume", "clear", "invalid"]
WorkItemStatus = Literal["planned", "in_progress", "done"]


class GoalState(BaseModel):
    """Durable task-attached goal state."""

    schema_version: str = GOAL_SCHEMA_VERSION
    objective: str | None = None
    acceptance_criteria: list[str] = Field(default_factory=list)
    status: GoalStatus = "unset"
    created_at: str | None = None
    updated_at: str | None = None
    paused_at: str | None = None
    resumed_at: str | None = None
    cleared_at: str | None = None
    completed_at: str | None = None
    last_command: str | None = None


class GoalWorkItem(BaseModel):
    """One executable todo item for a goal run."""

    id: str
    title: str
    status: WorkItemStatus = "planned"
    goal: str
    acceptance_checks: list[str] = Field(default_factory=list)


class GoalPlan(BaseModel):
    """Provider-authored todo list used by the goal loop."""

    schema_version: str = GOAL_PLAN_SCHEMA_VERSION
    objective: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    items: list[GoalWorkItem] = Field(default_factory=list)


class GoalRuntimeState(BaseModel):
    """Runtime bookkeeping for the current todo item."""

    current_item_id: str | None = None
    current_item_dir_key: str | None = None


@dataclass(frozen=True, slots=True)
class GoalCommand:
    """Parsed `/goal`-style command."""

    action: GoalAction
    objective: str | None = None
    acceptance_criteria: tuple[str, ...] = ()
    error: str | None = None


def parse_goal_request(message: object | None) -> GoalCommand:
    """Parse Codex-style `/goal` input from a Botpipe run message."""

    text = "" if message is None else str(message).strip()
    body = _strip_goal_prefix(text)
    if not body:
        return GoalCommand("view")

    normalized = body.casefold()
    if normalized in {"view", "status"}:
        return GoalCommand("view")
    if normalized == "pause":
        return GoalCommand("pause")
    if normalized == "resume":
        return GoalCommand("resume")
    if normalized == "clear":
        return GoalCommand("clear")

    if normalized == "set":
        return GoalCommand("invalid", error="Goal objective must be non-empty.")
    if normalized.startswith("set "):
        objective_text = body[4:].strip()
    else:
        objective_text = body

    objective, criteria = _split_objective_and_criteria(objective_text)
    if not objective:
        return GoalCommand("invalid", error="Goal objective must be non-empty.")
    if len(objective) > GOAL_OBJECTIVE_MAX_CHARS:
        return GoalCommand(
            "invalid",
            error=(
                "Goal objective must be at most "
                f"{GOAL_OBJECTIVE_MAX_CHARS} characters; received {len(objective)}."
            ),
        )
    return GoalCommand("set", objective=objective, acceptance_criteria=criteria)


def _strip_goal_prefix(text: str) -> str:
    if text == "/goal":
        return ""
    if text.startswith("/goal") and len(text) > len("/goal") and text[len("/goal")].isspace():
        return text[len("/goal") :].strip()
    return text


def _split_objective_and_criteria(text: str) -> tuple[str, tuple[str, ...]]:
    lines = text.splitlines()
    criteria_index = None
    for index, line in enumerate(lines):
        marker = line.strip().casefold()
        if marker in {"criteria", "criteria:", "acceptance criteria", "acceptance criteria:"}:
            criteria_index = index
            break
    if criteria_index is None:
        return text.strip(), ()
    objective = "\n".join(lines[:criteria_index]).strip()
    criteria = _normalize_criteria_lines(lines[criteria_index + 1 :])
    return objective, criteria


def _normalize_criteria_lines(lines: list[str]) -> tuple[str, ...]:
    criteria: list[str] = []
    for line in lines:
        cleaned = line.strip()
        if cleaned.startswith(('-', '*')):
            cleaned = cleaned[1:].strip()
        elif len(cleaned) > 2 and cleaned[0].isdigit() and cleaned[1] in {'.', ')'}:
            cleaned = cleaned[2:].strip()
        if cleaned:
            criteria.append(cleaned)
    return tuple(dict.fromkeys(criteria))


def _effective_criteria(criteria: tuple[str, ...] | list[str]) -> list[str]:
    provided = [criterion.strip() for criterion in criteria if isinstance(criterion, str) and criterion.strip()]
    return provided or list(DEFAULT_ACCEPTANCE_CRITERIA)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_dir_key(value: str) -> str:
    normalized = "".join(character if character.isalnum() or character in {".", "_", "-"} else "-" for character in value)
    normalized = normalized.strip(".-_")
    return normalized or "item"


def load_goal_state(handle) -> GoalState:
    """Load persisted goal state, or return an unset state when absent."""

    if not handle.exists():
        return GoalState()
    return GoalState.model_validate(handle.read_json())


def apply_goal_command(state: GoalState, command: GoalCommand, *, now: str) -> tuple[GoalState, str, bool]:
    """Apply one parsed command.

    Returns ``(next_state, note, ok)``. ``ok`` is false only for invalid
    command input; no-op pause/resume/clear operations are successful because
    they preserve idempotent slash-command behavior.
    """

    if command.action == "invalid":
        return (
            state.model_copy(update={"last_command": "invalid", "updated_at": now}),
            command.error or "Invalid goal command.",
            False,
        )

    if command.action == "view":
        return state.model_copy(update={"last_command": "view", "updated_at": now}), "Goal status viewed.", True

    if command.action == "set":
        assert command.objective is not None
        next_state = GoalState(
            objective=command.objective,
            acceptance_criteria=_effective_criteria(command.acceptance_criteria),
            status="active",
            created_at=now,
            updated_at=now,
            paused_at=None,
            resumed_at=None,
            cleared_at=None,
            completed_at=None,
            last_command="set",
        )
        return next_state, "Goal set; execution loop will start.", True

    if command.action == "pause":
        if state.objective is None or state.status == "unset":
            next_state = state.model_copy(update={"last_command": "pause", "updated_at": now})
            return next_state, "No goal is set; nothing was paused.", True
        next_state = state.model_copy(
            update={
                "status": "paused",
                "updated_at": now,
                "paused_at": now,
                "last_command": "pause",
            }
        )
        return next_state, "Goal paused.", True

    if command.action == "resume":
        if state.objective is None or state.status == "unset":
            next_state = state.model_copy(update={"last_command": "resume", "updated_at": now})
            return next_state, "No goal is set; nothing was resumed.", True
        next_state = state.model_copy(
            update={
                "status": "active",
                "updated_at": now,
                "resumed_at": now,
                "last_command": "resume",
            }
        )
        return next_state, "Goal resumed; execution loop will start.", True

    if command.action == "clear":
        next_state = GoalState(status="unset", updated_at=now, cleared_at=now, last_command="clear")
        if state.objective is None or state.status == "unset":
            return next_state, "No goal was set; state is clear.", True
        return next_state, "Goal cleared.", True

    return state.model_copy(update={"last_command": "invalid", "updated_at": now}), "Unsupported goal command.", False


def next_pending_item(plan: GoalPlan) -> GoalWorkItem | None:
    """Return the next unfinished todo item in plan order."""

    for item in plan.items:
        if item.status.casefold() not in _DONE_ITEM_STATUSES:
            return item
    return None


def mark_plan_item_done(plan: GoalPlan, item_id: str) -> GoalPlan:
    updated_items = []
    for item in plan.items:
        if item.id == item_id:
            updated_items.append(item.model_copy(update={"status": "done"}))
        else:
            updated_items.append(item)
    return plan.model_copy(update={"items": updated_items})


def render_goal_status(state: GoalState, *, note: str, plan: GoalPlan | None = None) -> str:
    lines = [
        "# Goal",
        "",
        f"Status: `{state.status}`",
        "",
        note,
        "",
    ]
    if state.objective:
        lines.extend(["## Objective", "", _blockquote(state.objective), ""])
    else:
        lines.extend(["No goal is currently set.", ""])
    criteria = _effective_criteria(state.acceptance_criteria)
    lines.extend(["## Acceptance Criteria", ""])
    for criterion in criteria:
        lines.append(f"- {criterion}")
    lines.append("")
    if plan is not None:
        lines.extend(["## Todo List", ""])
        if plan.items:
            for item in plan.items:
                lines.append(f"- [{item.status}] {item.id}: {item.title}")
        else:
            lines.append("No todo items are currently planned.")
        lines.append("")
    lines.extend(
        [
            "## Metadata",
            "",
            f"- Schema: `{state.schema_version}`",
            f"- Last command: `{state.last_command or 'none'}`",
            f"- Created at: `{state.created_at or 'n/a'}`",
            f"- Updated at: `{state.updated_at or 'n/a'}`",
            f"- Paused at: `{state.paused_at or 'n/a'}`",
            f"- Resumed at: `{state.resumed_at or 'n/a'}`",
            f"- Cleared at: `{state.cleared_at or 'n/a'}`",
            f"- Completed at: `{state.completed_at or 'n/a'}`",
            "",
            "## Commands",
            "",
            "- `/goal <objective>` sets the goal and starts execution.",
            "- `/goal` or `/goal status` views the current goal.",
            "- `/goal pause` pauses the current goal.",
            "- `/goal resume` resumes and starts execution.",
            "- `/goal clear` removes the current goal.",
            "",
        ]
    )
    return "\n".join(lines)


def _blockquote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


class Goal(Workflow):
    """Execute a task-attached goal until explicit acceptance criteria are met."""

    name = "goal"
    State = GoalRuntimeState

    goal_state = Artifact.json(
        "{{ task.folder }}/goal/goal.json",
        schema=GoalState,
        name="goal_state",
    )
    goal_plan = Artifact.json(
        "{{ workflow.folder }}/goal_plan.json",
        schema=GoalPlan,
        name="goal_plan",
        required=True,
    )
    current_item = Artifact.json(
        "{{ workflow.folder }}/current_item.json",
        schema=GoalWorkItem,
        name="current_item",
        required=True,
    )
    goal_status = Artifact.md(
        "{{ workflow.folder }}/goal_status.md",
        name="goal_status",
    )
    plan_review = Artifact.md(
        "{{ workflow.folder }}/plan_review.md",
        name="plan_review",
        required=True,
    )
    implementation_review = Artifact.md(
        "{{ workflow.folder }}/items/{{ state.current_item_dir_key }}/implementation_review.md",
        name="implementation_review",
        required=True,
    )
    goal_evidence = Artifact.md(
        "{{ workflow.folder }}/goal_evidence.md",
        name="goal_evidence",
        required=True,
    )
    goal_review = Artifact.md(
        "{{ workflow.folder }}/goal_review.md",
        name="goal_review",
        required=True,
    )

    @python_step(
        name="configure",
        reads=[goal_state],
        writes=[goal_state, goal_status],
        routes={"execute": "plan", "done": FINISH, "failed": FAIL},
    )
    def configure(ctx):
        command = parse_goal_request(ctx.message)
        try:
            state = load_goal_state(ctx.artifacts.goal_state)
        except Exception as exc:
            now = _utc_timestamp()
            failed_state = GoalState(updated_at=now, last_command="invalid")
            ctx.artifacts.goal_status.write_text(
                render_goal_status(
                    failed_state,
                    note=f"Existing goal state could not be read or validated: {exc}",
                )
            )
            return Event("failed", reason="Existing goal state is invalid.")

        next_state, note, ok = apply_goal_command(state, command, now=_utc_timestamp())
        ctx.artifacts.goal_state.write_model(next_state)
        ctx.artifacts.goal_status.write_text(render_goal_status(next_state, note=note))
        if not ok:
            return Event("failed", reason=note)
        if command.action == "set":
            return Event("execute", reason=note)
        if command.action == "resume" and next_state.objective and next_state.status == "active":
            return Event("execute", reason=note)
        return Event("done", reason=note)

    plan = produce_verify_step(
        requires=[goal_state],
        producer_prompt=Prompt.inline(
            """
            Read goal_state.json and create goal_plan.json.

            The goal is active. Build the smallest complete todo list that can
            satisfy the goal objective and acceptance criteria. Each todo item
            must be independently executable and verifiable.

            Required JSON shape:
            {
              "schema_version": "botpipe.goal_plan/v1",
              "objective": "goal objective",
              "acceptance_criteria": ["criterion"],
              "items": [
                {
                  "id": "item-1",
                  "title": "Short imperative title",
                  "status": "planned",
                  "goal": "What this item must accomplish",
                  "acceptance_checks": ["What must be true for this item"]
                }
              ]
            }
            """.strip()
        ),
        verifier_prompt=Prompt.inline(
            """
            Verify goal_plan.json against goal_state.json.

            Accept only if the plan fully covers the objective, explicitly maps
            to the acceptance criteria, contains at least one executable item,
            and every item has concrete acceptance checks.

            Write plan_review.md with the decision and exact rework if rejected.
            """.strip()
        ),
        producer_writes=[goal_plan],
        verifier_writes=[plan_review],
        routes={
            "accepted": Route.to(
                "select_next_item",
                required_writes=["goal_plan", "plan_review"],
            ),
            "needs_rework": Route.to(
                "plan",
                required_writes=["plan_review"],
            ),
        },
    )

    @python_step(
        name="select_next_item",
        requires=[goal_plan],
        writes=[current_item, goal_status],
        routes={"item_selected": "execute_item", "all_items_done": "verify_goal", "failed": FAIL},
    )
    def select_next_item(ctx):
        try:
            goal_state = ctx.artifacts.goal_state.read_model()
            plan = ctx.artifacts.goal_plan.read_model()
        except Exception as exc:
            return Event("failed", reason=f"Goal plan could not be read: {exc}")
        item = next_pending_item(plan)
        if item is None:
            ctx.state = ctx.state.model_copy(update={"current_item_id": None, "current_item_dir_key": None})
            ctx.artifacts.goal_status.write_text(
                render_goal_status(goal_state, note="All todo items are complete; verifying the full goal.", plan=plan)
            )
            return Event("all_items_done")
        ctx.state = ctx.state.model_copy(
            update={
                "current_item_id": item.id,
                "current_item_dir_key": _safe_dir_key(item.id),
            }
        )
        ctx.artifacts.current_item.write_model(item.model_copy(update={"status": "in_progress"}))
        ctx.artifacts.goal_status.write_text(
            render_goal_status(goal_state, note=f"Selected next todo item: {item.id}.", plan=plan)
        )
        return Event("item_selected")

    execute_item = produce_verify_step(
        requires=[goal_state, goal_plan, current_item],
        verifier_requires=[goal_state, goal_plan, current_item],
        producer_prompt=Prompt.inline(
            """
            Execute the current goal todo item.

            Read goal_state.json, goal_plan.json, and current_item.json.
            Implement the current item completely in the workspace. Edit files,
            add or update tests, run relevant validation commands, and fix
            failures before finishing.

            Do not claim completion unless the current item's acceptance checks
            are satisfied.
            """.strip()
        ),
        verifier_prompt=Prompt.inline(
            """
            Verify the current goal todo item.

            Read current_item.json, goal_plan.json, repository changes, tests,
            and relevant command output. Accept only if the current item is
            complete and its acceptance checks are satisfied.

            Write implementation_review.md with evidence and exact rework if
            rejected.
            """.strip()
        ),
        verifier_writes=[implementation_review],
        routes={
            "accepted": Route.to(
                "mark_item_done",
                required_writes=["implementation_review"],
            ),
            "needs_rework": Route.to(
                "execute_item",
                required_writes=["implementation_review"],
            ),
        },
    )

    @python_step(
        name="mark_item_done",
        requires=[goal_plan, current_item],
        writes=[goal_plan, goal_status],
        routes={"item_marked": "select_next_item", "failed": FAIL},
    )
    def mark_item_done(ctx):
        try:
            goal_state = ctx.artifacts.goal_state.read_model()
            plan = ctx.artifacts.goal_plan.read_model()
            item = ctx.artifacts.current_item.read_model()
        except Exception as exc:
            return Event("failed", reason=f"Current item could not be marked done: {exc}")
        next_plan = mark_plan_item_done(plan, item.id)
        ctx.artifacts.goal_plan.write_model(next_plan)
        ctx.artifacts.goal_status.write_text(
            render_goal_status(goal_state, note=f"Marked todo item {item.id} done.", plan=next_plan)
        )
        return Event("item_marked")

    verify_goal = produce_verify_step(
        requires=[goal_state, goal_plan],
        verifier_requires=[goal_state, goal_plan, goal_evidence],
        producer_prompt=Prompt.inline(
            """
            Perform a final integration pass for the active goal.

            Read goal_state.json and goal_plan.json. Inspect the repository,
            artifacts, tests, and command output. Run any remaining validation
            needed to determine whether the goal acceptance criteria are met.

            Write goal_evidence.md summarizing the evidence, commands run,
            remaining risks, and whether each acceptance criterion appears met.
            """.strip()
        ),
        verifier_prompt=Prompt.inline(
            """
            Decide whether the goal is fully met.

            Read goal_state.json, goal_plan.json, goal_evidence.md, repository
            state, tests, and relevant command output. Return accepted only if
            every acceptance criterion is satisfied and no incomplete todo item,
            blocker, or regression remains.

            If more work is needed, return needs_more_work and write goal_review.md
            with the missing work so the workflow can replan and continue.
            """.strip()
        ),
        producer_writes=[goal_evidence],
        verifier_writes=[goal_review],
        routes={
            "accepted": Route.to(
                "finalize_goal",
                required_writes=["goal_evidence", "goal_review"],
            ),
            "needs_more_work": Route.to(
                "plan",
                required_writes=["goal_review"],
            ),
        },
    )

    @python_step(
        name="finalize_goal",
        requires=[goal_state, goal_plan],
        writes=[goal_state, goal_status],
        routes={"done": FINISH, "failed": FAIL},
    )
    def finalize_goal(ctx):
        try:
            goal_state = ctx.artifacts.goal_state.read_model()
            plan = ctx.artifacts.goal_plan.read_model()
        except Exception as exc:
            return Event("failed", reason=f"Goal could not be finalized: {exc}")
        now = _utc_timestamp()
        met_state = goal_state.model_copy(
            update={
                "status": "met",
                "updated_at": now,
                "completed_at": now,
                "last_command": "met",
            }
        )
        ctx.artifacts.goal_state.write_model(met_state)
        ctx.artifacts.goal_status.write_text(
            render_goal_status(met_state, note="Goal accepted by final verifier.", plan=plan)
        )
        return Event("done", reason="Goal accepted by final verifier.")

    entry = configure
