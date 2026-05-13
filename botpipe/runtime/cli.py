"""Workflow-reference CLI entrypoint for the filesystem runtime harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

from ..sdk import Botpipe, SDKExecutionError, WorkflowResult
from ..core.errors import WorkflowExecutionError
from .config import ConfigError, SUPPORTED_PROVIDER_NAMES, resolve_runtime_config
from .loader import (
    WorkflowDiscoveryError,
    WorkflowManifestError,
    WorkflowParameterError,
    annotation_display_name,
    discover_workflow_catalog,
    discover_workflow_packages,
    inspect_workflow_reference,
    resolve_workflow_reference,
    validate_workflow_parameters,
    workflow_parameter_fields,
)
from .provider_backends import resolve_provider_backend
from .runner import RunnerOptions, execute_workflow_package
from .workspace import resolve_run_record


EXIT_SUCCESS = 0
EXIT_RUNTIME_ERROR = 1
EXIT_USAGE_ERROR = 2
EXIT_RESOLUTION_ERROR = 3

_WORKSPACE_HELP = (
    "Workspace directory. Package workflows are loaded from the installed botpipe package; "
    "workspace workflows are loaded from `.botpipe/workflows/`. Defaults to the current directory."
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="botpipe",
        description="Run workflows through the filesystem Botpipe runtime.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--workspace",
        dest="root",
        type=Path,
        metavar="WORKSPACE",
        default=Path("."),
        help=_WORKSPACE_HELP,
    )

    mutate = argparse.ArgumentParser(add_help=False)
    mutate.add_argument(
        "--workspace",
        dest="root",
        type=Path,
        metavar="WORKSPACE",
        default=Path("."),
        help=_WORKSPACE_HELP,
    )
    mutate.add_argument(
        "--provider",
        choices=sorted(SUPPORTED_PROVIDER_NAMES),
        help="Built-in provider backend override.",
    )
    mutate.add_argument("--model", help="Provider model override.")
    mutate.add_argument("--model-effort", dest="model_effort", help="Provider reasoning-effort override.")
    mutate.add_argument("--policy-file", type=Path, help="Merge provider policy overrides from the given YAML file.")
    mutate.add_argument(
        "--policy-validation-unsupported",
        choices=("fail", "warn", "ignore"),
        dest="policy_validation_unsupported",
        help="Override handling for provider policy features the target provider does not support.",
    )
    mutate.add_argument(
        "--policy-validation-lossy",
        choices=("fail", "warn", "ignore"),
        dest="policy_validation_lossy",
        help="Override handling for lossy provider policy mappings.",
    )
    mutate.add_argument(
        "--policy-validation-unsafe-expansion",
        choices=("fail", "warn", "ignore"),
        dest="policy_validation_unsafe_expansion",
        help="Override handling for unsafe provider policy expansions.",
    )
    mutate.add_argument("--max-steps", type=int, help="Maximum workflow steps to execute before failing.")
    mutate.add_argument("--no-git", action="store_true", help="Disable runtime git tracking for this command.")
    mutate.add_argument(
        "--git-commit-policy",
        choices=("off", "run", "step"),
        help="Override the runtime git tracking commit policy for this command.",
    )
    mutate.add_argument("--no-trace", action="store_true", help="Disable runtime trace writing for this command.")

    workflows_parser = subparsers.add_parser("workflows", help="Inspect discovered workflow metadata.")
    workflows_subparsers = workflows_parser.add_subparsers(dest="workflows_command", required=True)

    workflows_list = workflows_subparsers.add_parser(
        "list",
        parents=[common],
        help="List discovered workflow metadata without importing workflow modules.",
    )
    workflows_list.add_argument(
        "--all",
        action="store_true",
        help="Include shadowed package workflows in addition to the effective catalog.",
    )
    workflows_list.set_defaults(handler=_handle_workflows_list)

    workflows_show = workflows_subparsers.add_parser(
        "show",
        parents=[common],
        help="Show workflow details for a resolved workflow reference.",
    )
    workflows_show.add_argument("workflow", help="Workflow reference (name, file, module, or optional :Class).")
    workflows_show.set_defaults(handler=_handle_workflows_show)

    run_parser = subparsers.add_parser("run", parents=[mutate], help="Start a new workflow run.")
    run_parser.add_argument("workflow", help="Workflow reference (name, file, module, or optional :Class).")
    run_parser.add_argument("task_id", help="Stable task identifier.")
    run_parser.add_argument("--message", required=True, help="Initial message for the run.")
    run_parser.add_argument(
        "-wf",
        dest="workflow_params",
        action="append",
        nargs=2,
        metavar=("NAME", "VALUE"),
        default=[],
        help="Workflow-specific parameter pair.",
    )
    run_parser.set_defaults(handler=_handle_run)

    resume_parser = subparsers.add_parser("resume", parents=[mutate], help="Resume an existing workflow run.")
    resume_parser.add_argument("workflow", help="Workflow reference (name, file, module, or optional :Class).")
    resume_parser.add_argument("task_id", help="Stable task identifier.")
    resume_parser.add_argument("--run-id", help="Explicit run id to resume.")
    resume_parser.set_defaults(handler=_handle_resume)

    answer_parser = subparsers.add_parser("answer", parents=[mutate], help="Answer an awaiting-input workflow run.")
    answer_parser.add_argument("workflow", help="Workflow reference (name, file, module, or optional :Class).")
    answer_parser.add_argument("task_id", help="Stable task identifier.")
    answer_parser.add_argument("--run-id", help="Explicit run id to answer.")
    answer_parser.add_argument("--answer", required=True, help="Answer to inject into the awaiting-input run.")
    answer_parser.set_defaults(handler=_handle_answer)

    runs_parser = subparsers.add_parser("runs", help="Inspect run metadata.")
    runs_subparsers = runs_parser.add_subparsers(dest="runs_command", required=True)

    runs_list = runs_subparsers.add_parser("list", parents=[common], help="List runs.")
    runs_list.add_argument("--workflow", help="Filter by workflow reference.")
    runs_list.add_argument("--task", dest="task_id", help="Filter by task id.")
    runs_list.add_argument("--status", help="Filter by normalized run status.")
    runs_list.set_defaults(handler=_handle_runs_list)

    runs_show = runs_subparsers.add_parser("show", parents=[common], help="Show run metadata.")
    runs_show.add_argument("workflow", help="Workflow reference (name, file, module, or optional :Class).")
    runs_show.add_argument("task_id", help="Stable task identifier.")
    runs_show.add_argument("--run-id", help="Explicit run id to inspect.")
    runs_show.set_defaults(handler=_handle_runs_show)

    logs_parser = subparsers.add_parser("logs", parents=[common], help="Print run log output.")
    logs_parser.add_argument("workflow", help="Workflow reference (name, file, module, or optional :Class).")
    logs_parser.add_argument("task_id", help="Stable task identifier.")
    logs_parser.add_argument("--run-id", help="Explicit run id to inspect.")
    log_group = logs_parser.add_mutually_exclusive_group()
    log_group.add_argument("--events", action="store_true", help="Show events.jsonl.")
    log_group.add_argument("--trace", action="store_true", help="Show trace.jsonl.")
    log_group.add_argument("--raw", action="store_true", help="Show workflow-owned raw logs.")
    logs_parser.set_defaults(handler=_handle_logs)

    init_parser = subparsers.add_parser("init", help="Scaffold new workflows.")
    init_subparsers = init_parser.add_subparsers(dest="init_command", required=True)
    init_workflow = init_subparsers.add_parser(
        "workflow",
        parents=[common],
        help="Create a workflow scaffold in `.botpipe/workflows/`.",
    )
    init_workflow.add_argument("name", help="Workflow name.")
    init_workflow.add_argument(
        "--shape",
        choices=("single", "flow-specs", "package"),
        default="package",
        help="Authoring shape to scaffold. Defaults to package.",
    )
    init_workflow.set_defaults(handler=_handle_init_workflow)

    return parser


def main(
    argv: list[str] | None = None,
    *,
    provider_factory: Callable[..., Any] | None = None,
) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args, provider_factory=provider_factory)
    except (ConfigError, WorkflowManifestError, WorkflowParameterError, FileExistsError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE_ERROR
    except (WorkflowDiscoveryError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_RESOLUTION_ERROR
    except SDKExecutionError as exc:
        print(str(exc), file=sys.stderr)
        return _sdk_cli_exit_code(exc)
    except WorkflowExecutionError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    except Exception as exc:  # pragma: no cover - defensive top-level CLI guard
        print(str(exc), file=sys.stderr)
        return EXIT_RUNTIME_ERROR


def _handle_workflows_list(args: argparse.Namespace, *, provider_factory: Callable[..., Any] | None = None) -> int:
    del provider_factory
    catalog = discover_workflow_catalog(args.root, include_shadowed=args.all)
    _emit_json(
        [
            {
                "aliases": list(entry.aliases),
                "authoring_shape": entry.authoring_shape,
                "description": entry.description,
                "manifest_present": entry.manifest_path is not None,
                "name": entry.workflow_name,
                "package_folder": str(entry.package_dir),
                "source_path": str(entry.source_path),
                "source_root_kind": entry.source_root_kind,
                "shadowed": entry.shadowed,
                "shadowed_by": entry.shadowed_by,
                "title": entry.title,
            }
            for entry in catalog
        ]
    )
    return EXIT_SUCCESS


def _handle_workflows_show(args: argparse.Namespace, *, provider_factory: Callable[..., Any] | None = None) -> int:
    del provider_factory
    root = args.root.resolve()
    entry = inspect_workflow_reference(args.root, args.workflow)
    resolved = resolve_workflow_reference(root, args.workflow)
    catalog_entry = _catalog_entry_for_resolved_reference(root, resolved)
    _emit_json(
        {
            "aliases": list(entry.aliases),
            "artifacts": [
                {
                    "name": artifact.name,
                    "producer_steps": list(artifact.producer_steps),
                    "template": artifact.template,
                    "workflow_level": artifact.workflow_level,
                }
                for artifact in entry.artifacts
            ],
            "asset_paths": [str(path) for path in entry.asset_paths],
            "authoring_shape": entry.authoring_shape,
            "description": entry.description,
            "doc_path": None if entry.doc_path is None else str(entry.doc_path),
            "doc_paths": [str(path) for path in entry.doc_paths],
            "flow_path": None if entry.flow_path is None else str(entry.flow_path),
            "global_routes": dict(entry.global_routes),
            "workflow_py_path": None if entry.workflow_py_path is None else str(entry.workflow_py_path),
            "manifest_path": None if resolved.manifest_path is None else str(resolved.manifest_path),
            "name": entry.workflow_name,
            "package_folder": str(resolved.package_dir),
            "package_init_path": None if entry.package_init_path is None else str(entry.package_init_path),
            "package_module": resolved.package_module,
            "package_name": resolved.package_name,
            "parameters": [
                {
                    "default": field.default,
                    "name": field.name,
                    "repeated": field.supports_multiple,
                    "required": field.required,
                    "type": annotation_display_name(field.annotation),
                }
                for field in workflow_parameter_fields(resolved.parameters_cls)
            ],
            "parameters_model": entry.parameters_model,
            "parameters_supported": resolved.parameters_cls is not None,
            "params_path": None if entry.params_path is None else str(entry.params_path),
            "prompt_paths": [str(path) for path in entry.prompt_paths],
            "reference": resolved.reference.original,
            "sessions": list(entry.sessions),
            "shadowed": False if catalog_entry is None else catalog_entry.shadowed,
            "shadowed_by": None if catalog_entry is None else catalog_entry.shadowed_by,
            "source_path": None if resolved.source_path is None else str(resolved.source_path),
            "source_root": None if resolved.source_root is None else str(resolved.source_root),
            "source_root_kind": resolved.source_root_kind,
            "spec_paths": [str(path) for path in entry.spec_paths],
            "state_model": entry.state_model,
            "steps": [
                {
                    "available_routes": list(step.available_routes),
                    "authored_routes": list(step.authored_routes),
                    "has_expected_output_schema": step.expected_output_schema is not None,
                    "kind": step.kind,
                    "log_artifacts": list(step.log_artifacts),
                    "name": step.name,
                    "provider_visible_routes_full_auto": list(step.provider_visible_routes_full_auto),
                    "provider_visible_routes_interactive": list(step.provider_visible_routes_interactive),
                    "producer_prompt": step.producer_prompt,
                    "writes": list(step.writes),
                    "reads": list(step.reads),
                    "requires": list(step.requires),
                    "runtime_control_routes": list(step.runtime_control_routes),
                    "routes": {
                        route_name: {
                            "target": route.target,
                            "summary": route.summary,
                            "required_writes": list(route.required_writes or ()),
                            "handoff": route.handoff,
                            "on_taken": route.on_taken,
                            "provider_visible": route.provider_visible,
                            "provider_visible_interactive": route.provider_visible_interactive,
                            "provider_visible_full_auto": route.provider_visible_full_auto,
                            "is_runtime_control": route.is_runtime_control,
                        }
                        for route_name, route in step.routes.items()
                    },
                    "session_name": step.session_name,
                    "typed_output_schema": step.expected_output_schema,
                    "verifier_prompt": step.verifier_prompt,
                }
                for step in entry.steps
            ],
            "test_paths": [str(path) for path in entry.test_paths],
            "title": entry.title,
            "routes": {
                "global": dict(entry.global_routes),
                "steps": {step_name: dict(routes) for step_name, routes in entry.routes.items()},
            },
            "workflow_class": entry.workflow_class,
            "workflow_module": resolved.workflow_module,
        }
    )
    return EXIT_SUCCESS


def _handle_run(args: argparse.Namespace, *, provider_factory: Callable[..., Any] | None = None) -> int:
    root = args.root.resolve()
    resolved = resolve_workflow_reference(root, args.workflow)
    workflow_params = validate_workflow_parameters(resolved.parameters_cls, args.workflow_params)
    config = resolve_runtime_config(root, args)
    provider = _resolve_provider(config=config, args=args, provider_factory=provider_factory)
    execution = execute_workflow_package(
        args.workflow,
        provider=provider,
        options=RunnerOptions(
            root=root,
            task_id=args.task_id,
            message=args.message,
            max_steps=config.runtime.max_steps,
            workflow_params=workflow_params,
            runtime_config=config.runtime,
            provider_policy_config=config.provider_policy,
        ),
    )
    _emit_json(_run_summary_payload(execution))
    return EXIT_SUCCESS


def _handle_resume(args: argparse.Namespace, *, provider_factory: Callable[..., Any] | None = None) -> int:
    client = _mutating_client(args, provider_factory=provider_factory)
    result = client.runs.resume(
        args.workflow,
        args.task_id,
        run_id=args.run_id,
    )
    _emit_json(_workflow_result_summary_payload(client, result))
    return EXIT_SUCCESS


def _handle_answer(args: argparse.Namespace, *, provider_factory: Callable[..., Any] | None = None) -> int:
    client = _mutating_client(args, provider_factory=provider_factory)
    result = client.runs.resume(
        args.workflow,
        args.task_id,
        run_id=args.run_id,
        answer=args.answer,
    )
    _emit_json(_workflow_result_summary_payload(client, result))
    return EXIT_SUCCESS


def _handle_runs_list(args: argparse.Namespace, *, provider_factory: Callable[..., Any] | None = None) -> int:
    del provider_factory
    client = _readonly_client(args)
    records = client.runs.list(workflow=args.workflow, task_id=args.task_id, status=args.status)
    _emit_json([_run_record_payload(record) for record in records])
    return EXIT_SUCCESS


def _handle_runs_show(args: argparse.Namespace, *, provider_factory: Callable[..., Any] | None = None) -> int:
    del provider_factory
    client = _readonly_client(args)
    record = client.runs.show(args.workflow, args.task_id, run_id=args.run_id)
    _emit_json(_run_record_payload(record, include_paths=True))
    return EXIT_SUCCESS


def _handle_logs(args: argparse.Namespace, *, provider_factory: Callable[..., Any] | None = None) -> int:
    del provider_factory
    client = _readonly_client(args)

    if args.trace:
        content = client.runs.trace_text(args.workflow, args.task_id, run_id=args.run_id)
    elif args.raw:
        record = client.runs.show(args.workflow, args.task_id, run_id=args.run_id)
        content = _read_raw_logs(record)
    else:
        content = client.runs.events_text(args.workflow, args.task_id, run_id=args.run_id)
    print(content, end="" if content.endswith("\n") else "\n")
    return EXIT_SUCCESS


def _handle_init_workflow(args: argparse.Namespace, *, provider_factory: Callable[..., Any] | None = None) -> int:
    del provider_factory
    root = args.root.resolve()
    workflow_name = args.name.strip()
    if not workflow_name:
        raise ConfigError("workflow name must be a non-empty string")
    if not workflow_name.replace("_", "").isalnum() or workflow_name[0].isdigit():
        raise ConfigError("workflow name must be a valid Python package identifier using letters, digits, or underscores")

    workflows_root = root / ".botpipe" / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)

    class_name = _workflow_class_name(workflow_name)
    shape = args.shape
    created = _scaffold_workflow(workflows_root, workflow_name=workflow_name, class_name=class_name, shape=shape)

    _emit_json(
        {
            "name": workflow_name,
            "workflow_class": class_name,
            "shape": shape,
            "package_folder": str(workflows_root / workflow_name) if shape != "single" else None,
            "source_path": str(workflows_root / f"{workflow_name}.py") if shape == "single" else None,
            "created": [str(path) for path in created],
        }
    )
    return EXIT_SUCCESS


def _scaffold_workflow(
    workflows_root: Path,
    *,
    workflow_name: str,
    class_name: str,
    shape: str,
) -> list[Path]:
    if shape == "single":
        target = workflows_root / f"{workflow_name}.py"
        if target.exists() or (workflows_root / workflow_name).exists():
            raise FileExistsError(f"workflow {workflow_name!r} already exists at {target}")
        target.write_text(_single_file_workflow_source(workflow_name, class_name), encoding="utf-8")
        return [target]

    package_dir = workflows_root / workflow_name
    if package_dir.exists() or (workflows_root / f"{workflow_name}.py").exists():
        raise FileExistsError(f"workflow {workflow_name!r} already exists at {package_dir}")
    package_dir.mkdir(parents=True, exist_ok=False)

    flow_path = package_dir / "flow.py"
    specs_path = package_dir / "specs.py"
    flow_path.write_text(_flow_package_source(workflow_name, class_name), encoding="utf-8")
    specs_path.write_text(_flow_specs_source(), encoding="utf-8")
    created: list[Path] = [flow_path, specs_path]

    if shape == "package":
        init_path = package_dir / "__init__.py"
        manifest_path = package_dir / "workflow.toml"
        prompts_dir = package_dir / "prompts"
        assets_dir = package_dir / "assets"
        init_path.write_text(f'from .flow import {class_name}\n\n__all__ = ["{class_name}"]\n', encoding="utf-8")
        manifest_path.write_text(
            "\n".join(
                (
                    f'name = "{workflow_name}"',
                    f'title = "{_workflow_title(workflow_name)}"',
                    'description = "Describe this workflow."',
                    "aliases = []",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        prompts_dir.mkdir(parents=True, exist_ok=False)
        assets_dir.mkdir(parents=True, exist_ok=False)
        (prompts_dir / "README.md").write_text("# Prompts\n", encoding="utf-8")
        (assets_dir / ".gitkeep").write_text("", encoding="utf-8")
        created.extend([init_path, manifest_path, prompts_dir, assets_dir])

    return created


def _single_file_workflow_source(workflow_name: str, class_name: str) -> str:
    return (
        "\n".join(
            (
                "from __future__ import annotations",
                "",
                "from pydantic import BaseModel",
                "",
                "from botpipe import Event, FINISH, Workflow, python_step",
                "",
                "",
                f"class {class_name}(Workflow):",
                f'    name = "{workflow_name}"',
                "",
                "    class State(BaseModel):",
                "        ready: bool = False",
                "",
                '    @python_step(name="bootstrap", routes={"ready": FINISH})',
                "    def bootstrap(ctx):",
                '        ctx.state = ctx.state.model_copy(update={"ready": True})',
                '        return Event("ready")',
                "",
                '    entry = "bootstrap"',
            )
        )
        + "\n"
    )


def _flow_package_source(workflow_name: str, class_name: str) -> str:
    return (
        "\n".join(
            (
                "from __future__ import annotations",
                "",
                "from botpipe import Event, FINISH, Workflow, python_step",
                "",
                "from .specs import State",
                "",
                "",
                f"class {class_name}(Workflow):",
                f'    name = "{workflow_name}"',
                "    State = State",
                "",
                '    @python_step(name="bootstrap", routes={"ready": FINISH})',
                "    def bootstrap(ctx):",
                '        ctx.state = ctx.state.model_copy(update={"ready": True})',
                '        return Event("ready")',
                "",
                '    entry = "bootstrap"',
            )
        )
        + "\n"
    )


def _flow_specs_source() -> str:
    return (
        "\n".join(
            (
                "from __future__ import annotations",
                "",
                "from pydantic import BaseModel",
                "",
                "",
                "class State(BaseModel):",
                "    ready: bool = False",
            )
        )
        + "\n"
    )


def _resolve_provider(
    *,
    config: Any,
    args: argparse.Namespace,
    provider_factory: Callable[..., Any] | None,
) -> Any:
    if provider_factory is not None:
        return provider_factory(config=config, args=args)
    del args
    return resolve_provider_backend(config=config)


class _ReadOnlyProvider:
    async def run_producer(self, request):  # pragma: no cover - defensive
        raise RuntimeError(f"read-only CLI command should not execute provider producer turns: {request!r}")

    async def run_verifier(self, request):  # pragma: no cover - defensive
        raise RuntimeError(f"read-only CLI command should not execute provider verifier turns: {request!r}")

    async def run_llm(self, request):  # pragma: no cover - defensive
        raise RuntimeError(f"read-only CLI command should not execute provider llm turns: {request!r}")


_READ_ONLY_PROVIDER = _ReadOnlyProvider()


def _readonly_client(args: argparse.Namespace) -> Botpipe:
    return Botpipe(workspace=args.root.resolve(), provider=_READ_ONLY_PROVIDER)


def _mutating_client(
    args: argparse.Namespace,
    *,
    provider_factory: Callable[..., Any] | None,
) -> Botpipe:
    root = args.root.resolve()
    config = resolve_runtime_config(root, args)
    provider = _resolve_provider(config=config, args=args, provider_factory=provider_factory)
    return Botpipe(
        workspace=root,
        provider=provider,
        runtime_config=config.runtime,
        provider_policy_config=config.provider_policy,
    )


def _sdk_cli_exit_code(exc: SDKExecutionError) -> int:
    original = exc.original_error
    while isinstance(original, SDKExecutionError):
        original = original.original_error
    if isinstance(original, (WorkflowDiscoveryError, FileNotFoundError)):
        return EXIT_RESOLUTION_ERROR
    return EXIT_RUNTIME_ERROR


def _emit_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))


def _run_summary_payload(execution) -> dict[str, Any]:
    record = resolve_run_record(
        execution.task_workspace.root,
        workflow_name=execution.compiled.workflow_name,
        task_id=execution.task_workspace.task_id,
        run_id=execution.run_workspace.run_id,
        selector="latest",
    )
    return {
        "workflow": execution.compiled.workflow_name,
        "workflow_reference": record.metadata.get("workflow", {}).get("reference"),
        "task_id": execution.task_workspace.task_id,
        "run_id": execution.run_workspace.run_id,
        "status": record.normalized_status,
        "awaiting_input": record.awaiting_input,
        "pending_input": record.pending_input,
        "run_folder": record.metadata.get("run_folder"),
    }


def _workflow_result_summary_payload(client: Botpipe, result: WorkflowResult) -> dict[str, Any]:
    candidates = [
        record
        for record in client.runs.list(task_id=result.debug.task_id)
        if record.run_id == result.debug.run_id
    ]
    for record in candidates:
        if record.run_dir.resolve() == result.debug.run_dir.resolve():
            return _workflow_result_record_payload(record)
    if len(candidates) == 1:
        return _workflow_result_record_payload(candidates[0])
    raise FileNotFoundError(f"run {result.debug.run_id!r} does not exist on task {result.debug.task_id!r}")


def _workflow_result_record_payload(record) -> dict[str, Any]:
    return {
        "workflow": record.workflow_name,
        "workflow_reference": record.metadata.get("workflow", {}).get("reference"),
        "task_id": record.task_id,
        "run_id": record.run_id,
        "status": record.normalized_status,
        "awaiting_input": record.awaiting_input,
        "pending_input": record.pending_input,
        "run_folder": record.metadata.get("run_folder"),
    }


def _run_record_payload(record, *, include_paths: bool = False) -> dict[str, Any]:
    payload = {
        "workflow": record.workflow_name,
        "task_id": record.task_id,
        "run_id": record.run_id,
        "status": record.normalized_status,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "awaiting_input": record.awaiting_input,
        "resumable": record.resumable,
    }
    if include_paths:
        payload.update(
            {
                "checkpoint_exists": record.checkpoint_exists,
                "pending_input": record.pending_input,
                "workflow_params": record.workflow_params,
                "task_folder": record.metadata.get("task_folder"),
                "workflow_folder": record.metadata.get("workflow_folder"),
                "run_folder": record.metadata.get("run_folder"),
                "request_file": record.metadata.get("request_file"),
                "package_folder": record.metadata.get("package_folder"),
                "workflow_origin": record.metadata.get("workflow"),
            }
        )
    return payload


def _catalog_entry_for_resolved_reference(root: Path, resolved) -> Any:
    for entry in discover_workflow_catalog(root, include_shadowed=True):
        if resolved.source_path is not None and entry.source_path.resolve() == resolved.source_path.resolve():
            return entry
        if resolved.manifest_path is not None and entry.manifest_path is not None:
            if entry.manifest_path.resolve() == resolved.manifest_path.resolve():
                return entry
    return None


def _read_raw_logs(record) -> str:
    candidates: list[Path] = []
    legacy_raw_phase_log = record.run_dir / "raw_phase_log.md"
    if legacy_raw_phase_log.is_file():
        candidates.append(legacy_raw_phase_log)
    if record.raw_dir.is_dir():
        candidates.extend(sorted(path for path in record.raw_dir.rglob("*") if path.is_file()))
    if not candidates:
        raise FileNotFoundError(f"raw log output is missing for run {record.run_id!r}")
    if len(candidates) == 1:
        return candidates[0].read_text(encoding="utf-8")

    rendered: list[str] = []
    for index, path in enumerate(candidates):
        if index:
            rendered.append("")
        rendered.append(f"== {path.relative_to(record.run_dir)} ==")
        rendered.append(path.read_text(encoding="utf-8").rstrip("\n"))
    return "\n".join(rendered) + "\n"


def _workflow_class_name(workflow_name: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in workflow_name.split("_") if part) or "WorkflowPackage"


def _workflow_title(workflow_name: str) -> str:
    return " ".join(part[:1].upper() + part[1:] for part in workflow_name.split("_") if part) or "Workflow Package"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
