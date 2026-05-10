from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

from botlane import Botlane, Policy
from botlane.runtime.config import resolve_runtime_config
from workflows.botlane_cleanup_workflow import BotlaneCyclicalCleanupWorkflow


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Botlane cyclical cleanup workflow from source.",
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
        default="botlane/core",
        help="Cleanup scope. Default: botlane/core.",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=3,
        help=(
            "Maximum cleanup cycles to budget. The workflow has 3 executable "
            "steps per cycle, so max_steps is cycles * 3. Default: 3."
        ),
    )
    parser.add_argument(
        "--batch-size",
        choices=("small", "medium", "large"),
        default="small",
        help="Cleanup batch size. Default: small.",
    )
    parser.add_argument(
        "--allow-read",
        action="append",
        default=None,
        help=(
            "Optional read root. Can be repeated or comma-separated. "
            "If omitted, Botlane defaults to allow_read='.'."
        ),
    )
    parser.add_argument(
        "--allow-write",
        action="append",
        default=None,
        help=(
            "Optional write root. Can be repeated or comma-separated. "
            "If omitted, Botlane defaults to allow_write='.'."
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

    if args.cycles < 1:
        raise ValueError("--cycles must be >= 1")

    workspace = Path(args.workspace).expanduser().resolve()
    max_steps = args.cycles * 3

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

    client = Botlane(
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

    notes = args.notes.strip()
    cycle_note = (
        f"Runner cycle budget: {args.cycles} cleanup cycle(s), "
        f"mapped to max_steps={max_steps}. "
        "Each normal cycle has analyze/plan, implement/verify, and audit/decide."
    )
    combined_notes = f"{cycle_note}\n\n{notes}" if notes else cycle_note

    run_kwargs = {}
    if policy is not None:
        run_kwargs["policy"] = policy

    result = client.run(
        BotlaneCyclicalCleanupWorkflow,
        message=(
            "Run the Botlane cyclical cleanup workflow. "
            "Start with measurement and planning. Implement only the approved cleanup batch. "
            "Repeat only while the audit routes repeat and the step budget allows it."
        ),
        input={
            "scope": args.scope,
            "max_cleanup_batch_size": args.batch_size,
            "require_production_loc_decrease": True,
            "allow_test_loc_increase": True,
            "allow_public_api_changes": False,
            "require_no_new_technical_debt": True,
            "require_taste_not_decrease": True,
            "notes": combined_notes,
        },
        max_steps=max_steps,
        **run_kwargs,
    )

    _print_result_summary(result, workspace=workspace)

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
