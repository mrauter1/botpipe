from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

from botpipe import Botpipe, Policy
from botpipe.runtime.config import resolve_runtime_config
from workflows.botpipe_cleanup_workflow import BotpipeCyclicalCleanupWorkflow


def _csv_or_repeated(values: Sequence[str] | None) -> tuple[str, ...] | None:
    if values is None:
        return None

    normalized: list[str] = []
    for value in values:
        for part in value.split(","):
            item = part.strip()
            if item:
                normalized.append(item)

    return tuple(dict.fromkeys(normalized)) or None


def _result_route(result: Any) -> str | None:
    for attr in ("last_event", "last_outcome"):
        tag = getattr(getattr(result, attr, None), "tag", None)
        if isinstance(tag, str) and tag.strip():
            return tag
    return None


def _result_error(result: Any) -> str | None:
    validation_error = getattr(result, "output_validation_error", None)
    if isinstance(validation_error, str) and validation_error.strip():
        return validation_error

    for attr in ("last_event", "last_outcome"):
        reason = getattr(getattr(result, attr, None), "reason", None)
        if isinstance(reason, str) and reason.strip():
            return reason

    terminal = getattr(result, "terminal", None)
    if getattr(result, "ok", None) is False and isinstance(terminal, str) and terminal.strip():
        return f"terminal: {terminal}"
    return None


def _print_result_summary(result: Any, *, workspace: Path) -> None:
    debug = getattr(result, "debug", None)

    print("ok:", result.ok)
    print("status:", result.status)
    print("terminal:", result.terminal)
    print("route:", _result_route(result))
    print("task_id:", getattr(debug, "task_id", None))
    print("run_id:", getattr(debug, "run_id", None))
    print("workspace:", workspace)

    if not result.ok:
        error = _result_error(result)
        if error is not None:
            print("error:", error)


def _impact_cleanup_note(*, target_loc_delta: int) -> str:
    return (
        "Impact-oriented cleanup preference:\n"
        f"- Treat {target_loc_delta}+ production LOC reduction as a soft planning "
        "target for an ordinary cleanup batch, not as an audit gate.\n"
        "- Audit acceptance only requires an actual net production LOC decrease "
        "when production LOC decrease is required, plus preserved behavior and "
        "quality gates.\n"
        "- When multiple safe batches are available, select the one with the larger "
        "expected production LOC decrease and stronger conceptual simplification.\n"
        f"- A batch below {target_loc_delta} production LOC is acceptable only when it "
        "still decreases production LOC and materially reduces framework "
        "ownership/representation bloat, is required to unblock a larger cleanup, "
        "or no larger safe target exists.\n"
        "- Small dead-code and stale-helper cleanup is still welcome, but it should be "
        "batched with the larger coherent seam when it is adjacent or covered by the "
        "same behavior locks.\n"
        "- Do not select isolated helper shaving as the whole batch unless no "
        "higher-impact bloat target is safe under the current scope, policy, and tests.\n"
        "- Rank candidates by conceptual simplification, production LOC reduction, "
        "duplicate-representation removal, ownership-boundary clarity, and testability.\n"
        "- Treat these as first-class high-impact targets when present: "
        "Engine/execution_runtime_services ownership overlap, execution_services seam, "
        "Context private-mutator coupling, engine-private test coupling, duplicate "
        "route or legacy normalization paths, and repeated parser/renderer/validator "
        "representations.\n"
        "- If a high-impact seam is too large for one cycle, choose a coherent sub-batch "
        "inside that seam and include nearby small dead-code cleanup in the same files "
        "when safe.\n"
        "- If the selected batch is low-impact, explicitly explain in the plan why each "
        "higher-impact target was unsafe, blocked, or outside scope."
    )


def _combined_notes(*, target_loc_delta: int, user_notes: str) -> str:
    repeat_note = (
        "Runner repeat behavior: run_cleanup.py does not impose a cleanup-cycle "
        "or max_steps-derived stop condition. Continue audit-driven cycles until "
        "the audit reports no remaining cleanup gaps, asks for human input, or "
        "the runtime itself terminates."
    )
    notes = [repeat_note, _impact_cleanup_note(target_loc_delta=target_loc_delta)]
    stripped_user_notes = user_notes.strip()
    if stripped_user_notes:
        notes.append(stripped_user_notes)
    return "\n\n".join(notes)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Botpipe cyclical cleanup workflow from source.",
    )

    parser.add_argument(
        "--workspace",
        default=".",
        help="Repository/workspace root. Default: current directory.",
    )
    parser.add_argument(
        "--provider",
        default="codex",
        choices=("codex", "claude"),
        help="Provider backend to use. Default: codex.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional provider model override.",
    )
    parser.add_argument(
        "--scope",
        default="botpipe/core",
        help="Cleanup scope. Default: botpipe/core.",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=3,
        help=(
            "Compatibility option retained for existing scripts. It no longer "
            "caps cleanup cycles or maps to max_steps; the workflow repeats from "
            "audit until no gaps remain, human input is required, or the runtime "
            "terminates. Default: 3."
        ),
    )
    parser.add_argument(
        "--batch-size",
        choices=("small", "medium", "large"),
        default="medium",
        help="Cleanup batch size. Default: medium.",
    )
    parser.add_argument(
        "--target-production-loc-delta",
        type=int,
        default=150,
        help=(
            "Soft planning target for production LOC reduction per cleanup batch. "
            "Audit acceptance only requires actual net production LOC decrease; "
            "small dead-code cleanup remains allowed, but should be bundled with "
            "higher-impact seams and larger reductions when safe. Default: 150."
        ),
    )
    parser.add_argument(
        "--allow-read",
        action="append",
        default=None,
        help=(
            "Optional read root. Can be repeated or comma-separated. "
            "If omitted, Botpipe defaults to allow_read='.'."
        ),
    )
    parser.add_argument(
        "--allow-write",
        action="append",
        default=None,
        help=(
            "Optional write root. Can be repeated or comma-separated. "
            "If omitted, Botpipe defaults to allow_write='.'."
        ),
    )
    parser.add_argument(
        "--notes",
        default="",
        help="Extra notes to pass into the cleanup workflow.",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.target_production_loc_delta < 1:
        raise ValueError("--target-production-loc-delta must be >= 1")

    workspace = Path(args.workspace).expanduser().resolve()

    allow_read = _csv_or_repeated(args.allow_read)
    allow_write = _csv_or_repeated(args.allow_write)

    resolved_config = resolve_runtime_config(workspace, argparse.Namespace())
    runtime_config = replace(
        resolved_config.runtime,
        git_tracking=replace(
            resolved_config.runtime.git_tracking,
            failure_policy="record_and_continue",
        ),
    )
    provider_policy_config = resolved_config.provider_policy
    if args.provider == "codex" and allow_read is not None:
        provider_policy_config = provider_policy_config.model_copy(
            update={
                "validation": provider_policy_config.validation.model_copy(
                    update={"unsafe_expansion": "warn"},
                ),
            },
        )

    client = Botpipe(
        workspace=workspace,
        provider=args.provider,
        model=args.model,
        runtime_config=runtime_config,
        provider_policy_config=provider_policy_config,
    )

    policy = None
    if allow_read is not None or allow_write is not None:
        policy = Policy(
            allow_read=allow_read,
            allow_write=allow_write,
        )

    combined_notes = _combined_notes(
        target_loc_delta=args.target_production_loc_delta,
        user_notes=args.notes,
    )

    run_kwargs = {}
    if policy is not None:
        run_kwargs["policy"] = policy

    result = client.run(
        BotpipeCyclicalCleanupWorkflow,
        message=(
            "Run the Botpipe cyclical cleanup workflow. "
            "Start with measurement and planning. Prefer high-impact cleanup batches "
            "that can also absorb adjacent small dead-code cleanup. "
            "Implement only the approved cleanup batch. "
            "Repeat while the audit routes repeat and stop only when the audit "
            "finds no remaining gaps or asks for human input."
        ),
        input={
            "scope": args.scope,
            "cleanup_goal": (
                "Reduce high-impact framework bloat and conceptual ownership overlap. "
                "Batch nearby small dead-code cleanup with larger coherent changes "
                "when safe, without changing public SDK/simple behavior."
            ),
            "max_cleanup_batch_size": args.batch_size,
            "require_production_loc_decrease": True,
            "allow_test_loc_increase": True,
            "allow_public_api_changes": False,
            "require_no_new_technical_debt": True,
            "require_taste_not_decrease": True,
            "notes": combined_notes,
        },
        **run_kwargs,
    )

    _print_result_summary(result, workspace=workspace)

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
