"""Packaged goal workflow inspired by Codex CLI `/goal`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel

from botpipe import Event, FAIL, FINISH, Json, Md, Workflow, python_step


GOAL_SCHEMA_VERSION = "botpipe.goal/v1"
GOAL_OBJECTIVE_MAX_CHARS = 4000

GoalStatus = Literal["unset", "active", "paused"]
GoalAction = Literal["view", "set", "pause", "resume", "clear", "invalid"]


class GoalState(BaseModel):
    """Durable task-attached goal state."""

    schema_version: str = GOAL_SCHEMA_VERSION
    objective: str | None = None
    status: GoalStatus = "unset"
    created_at: str | None = None
    updated_at: str | None = None
    paused_at: str | None = None
    resumed_at: str | None = None
    cleared_at: str | None = None
    last_command: str | None = None


@dataclass(frozen=True, slots=True)
class GoalCommand:
    """Parsed `/goal`-style command."""

    action: GoalAction
    objective: str | None = None
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
        objective = body[4:].strip()
    else:
        objective = body

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
    return GoalCommand("set", objective=objective)


def _strip_goal_prefix(text: str) -> str:
    if text == "/goal":
        return ""
    if text.startswith("/goal") and len(text) > len("/goal") and text[len("/goal")].isspace():
        return text[len("/goal") :].strip()
    return text


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
            status="active",
            created_at=now,
            updated_at=now,
            paused_at=None,
            resumed_at=None,
            cleared_at=None,
            last_command="set",
        )
        return next_state, "Goal set and active.", True

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
        return next_state, "Goal resumed.", True

    if command.action == "clear":
        if state.objective is None or state.status == "unset":
            next_state = GoalState(status="unset", updated_at=now, cleared_at=now, last_command="clear")
            return next_state, "No goal was set; state is clear.", True
        next_state = GoalState(status="unset", updated_at=now, cleared_at=now, last_command="clear")
        return next_state, "Goal cleared.", True

    return state.model_copy(update={"last_command": "invalid", "updated_at": now}), "Unsupported goal command.", False


def render_goal_status(state: GoalState, *, note: str) -> str:
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
            "",
            "## Commands",
            "",
            "- `/goal <objective>` sets or replaces the active goal.",
            "- `/goal` or `/goal status` views the current goal.",
            "- `/goal pause` pauses the current goal.",
            "- `/goal resume` resumes a paused goal.",
            "- `/goal clear` removes the current goal.",
            "",
        ]
    )
    return "\n".join(lines)


def _blockquote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


class Goal(Workflow):
    """Manage a task-attached goal using Codex-style `/goal` commands."""

    name = "goal"

    goal_state = Json(
        "goal_state",
        schema=GoalState,
        path="{{ task.folder }}/goal/goal.json",
    )
    goal_status = Md(
        "goal_status",
        path="{{ workflow.folder }}/goal_status.md",
    )

    @python_step(
        name="manage",
        reads=[goal_state],
        writes=[goal_state, goal_status],
        routes={"done": FINISH, "failed": FAIL},
    )
    def manage(ctx):
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
        return Event("done", reason=note)

    entry = manage
