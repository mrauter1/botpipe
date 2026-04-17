"""CLI entrypoint for the filesystem runtime harness."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..workflow.errors import WorkflowExecutionError
from .config import ConfigError, resolve_runtime_config
from .runner import RunnerOptions, load_provider_factory, run_workflow


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run autoloop_v3 workflows through the filesystem runtime.")
    parser.add_argument("workflow", help="Workflow module path or import name.")
    parser.add_argument("--class-name", help="Explicit workflow class name.")
    parser.add_argument("--task-id", required=True, help="Stable task identifier.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root.")
    parser.add_argument("--run-id", help="Resume or force a specific run id.")
    parser.add_argument("--resume", action="store_true", help="Resume an existing run.")
    parser.add_argument("--answer", help="Injected answer for a paused checkpoint.")
    parser.add_argument("--request-text", help="Initial task request text.")
    parser.add_argument("--provider-factory", required=True, help="Provider factory in module:function form.")
    parser.add_argument("--model", help="Provider model override.")
    parser.add_argument("--model-effort", help="Provider reasoning-effort override.")
    parser.add_argument("--max-steps", type=int, help="Maximum workflow steps to execute before failing.")
    parser.add_argument("--intent-mode", choices=("append", "preserve", "replace"), help="Request snapshot merge mode.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        config = resolve_runtime_config(args.root, args)
        provider_factory = load_provider_factory(args.provider_factory)
        provider = provider_factory(config=config, args=args)
        run_workflow(
            args.workflow,
            provider=provider,
            options=RunnerOptions(
                root=args.root,
                task_id=args.task_id,
                run_id=args.run_id,
                request_text=args.request_text,
                resume=args.resume,
                answer=args.answer,
                class_name=args.class_name,
                intent_mode=config.runtime.intent_mode,
                max_steps=config.runtime.max_steps,
            ),
        )
    except ConfigError as exc:
        parser.error(str(exc))
    except WorkflowExecutionError as exc:
        parser.exit(2, f"{exc}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
