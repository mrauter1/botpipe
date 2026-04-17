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
    parser.add_argument("--pairs", help="Compatibility runtime pair selection.")
    parser.add_argument("--max-iterations", type=int, help="Compatibility runtime iteration cap.")
    parser.add_argument("--phase-mode", help="Compatibility runtime phase selection mode.")
    parser.add_argument("--phase-id", help="Compatibility runtime phase target.")
    parser.add_argument("--intent-mode", help="Compatibility runtime intent merge mode.")
    parser.add_argument("--full-auto-answers", dest="full_auto_answers", action="store_true")
    parser.add_argument("--no-full-auto-answers", dest="full_auto_answers", action="store_false")
    parser.add_argument("--git", dest="no_git", action="store_false")
    parser.add_argument("--no-git", dest="no_git", action="store_true")
    parser.add_argument("--track-autoloop-artifacts", dest="track_autoloop_artifacts", action="store_true")
    parser.add_argument("--no-track-autoloop-artifacts", dest="track_autoloop_artifacts", action="store_false")
    parser.set_defaults(full_auto_answers=None, no_git=None, track_autoloop_artifacts=None)
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
                pairs=config.runtime.pairs,
                max_iterations=config.runtime.max_iterations,
                phase_mode=config.runtime.phase_mode,
                phase_id=args.phase_id,
                full_auto_answers=config.runtime.full_auto_answers,
                no_git=config.runtime.no_git,
                track_autoloop_artifacts=config.runtime.track_autoloop_artifacts,
            ),
        )
    except ConfigError as exc:
        parser.error(str(exc))
    except WorkflowExecutionError as exc:
        parser.exit(2, f"{exc}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
