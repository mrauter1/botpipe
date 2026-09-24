"""Command-line interface over the durable-functions SDK."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .config import ConfigError, load_config
from .discovery import (
    WorkflowDiscoveryError,
    WorkflowInputError,
    discover_workflows,
    resolve_workflow,
)
from .inspection import inspect_run, inspect_workflow

EXIT_OK = 0
EXIT_RUNTIME = 1
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="botpipe", description="Run and inspect durable Python workflows."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser(
        "doctor",
        parents=[_client_parser()],
        help="Check the installed Codex capabilities.",
    )
    doctor.set_defaults(handler=_doctor)

    workflows = commands.add_parser("workflows", help="Discover and inspect workflows.")
    workflow_commands = workflows.add_subparsers(dest="workflow_command", required=True)
    workflow_list = workflow_commands.add_parser(
        "list", parents=[_location_parser()], help="List workflows."
    )
    workflow_list.add_argument(
        "--no-labs", action="store_true", help="Exclude repository lab workflows."
    )
    workflow_list.set_defaults(handler=_workflows_list)
    workflow_show = workflow_commands.add_parser(
        "show", parents=[_location_parser()], help="Show a workflow contract."
    )
    workflow_show.add_argument("workflow")
    workflow_show.set_defaults(handler=_workflows_show)

    run = commands.add_parser(
        "run", parents=[_client_parser()], help="Start a workflow run."
    )
    run.add_argument(
        "workflow", help="Catalog name, module:function, or file.py:function."
    )
    run.add_argument("request", nargs="?", help="Plain-text first argument.")
    _add_inputs(run)
    run.add_argument("--task-id")
    run.add_argument("--run-id")
    run.set_defaults(handler=_run)

    resume = commands.add_parser(
        "resume", parents=[_client_parser()], help="Resume a durable run."
    )
    resume.add_argument("run_id")
    resume.add_argument(
        "--workflow", help="Required for a non-importable local workflow."
    )
    answer = resume.add_mutually_exclusive_group()
    answer.add_argument(
        "--answer", help="JSON answer, or plain text when it is not valid JSON."
    )
    answer.add_argument(
        "--answer-file", type=Path, help="Read a JSON answer from a file."
    )
    resume.set_defaults(handler=_resume)

    answer_command = commands.add_parser(
        "answer", parents=[_client_parser()], help="Answer a paused run."
    )
    answer_command.add_argument("run_id")
    answer_command.add_argument(
        "answer", help="JSON answer, or plain text when it is not valid JSON."
    )
    answer_command.add_argument(
        "--workflow", help="Required for a non-importable local workflow."
    )
    answer_command.set_defaults(handler=_answer)

    resolve = commands.add_parser(
        "resolve", parents=[_client_parser()], help="Resolve an interrupted operation."
    )
    resolve.add_argument("run_id")
    resolve.add_argument("operation_id")
    resolution = resolve.add_mutually_exclusive_group()
    resolution.add_argument(
        "--retry",
        action="store_true",
        help="Explicitly retry the interrupted operation.",
    )
    resolution.add_argument(
        "--accept",
        action="store_true",
        help="Accept the workspace and capture declared outputs.",
    )
    resolution.add_argument(
        "--fail",
        action="store_true",
        help="Record the interrupted operation as failed.",
    )
    resolution.add_argument(
        "--response",
        help="Record its externally observed JSON response (or plain text).",
    )
    resolve.add_argument(
        "--artifact-digests",
        help="Explicit output reconciliation: JSON mapping of every artifact name to SHA-256, or null for an absent optional output.",
    )
    resolve.add_argument(
        "--workflow", help="Required for a non-importable local workflow."
    )
    resolve.add_argument(
        "--no-resume",
        action="store_true",
        help="Record the resolution without resuming the run.",
    )
    resolve.set_defaults(handler=_resolve)

    runs = commands.add_parser("runs", help="Inspect durable runs.")
    run_commands = runs.add_subparsers(dest="runs_command", required=True)
    runs_list = run_commands.add_parser(
        "list", parents=[_client_parser()], help="List runs."
    )
    runs_list.add_argument("--workflow")
    runs_list.add_argument("--task-id")
    runs_list.add_argument("--status")
    runs_list.set_defaults(handler=_runs_list)
    runs_show = run_commands.add_parser(
        "show", parents=[_client_parser()], help="Show one run."
    )
    runs_show.add_argument("run_id")
    runs_show.set_defaults(handler=_runs_show)
    runs_logs = run_commands.add_parser(
        "logs", parents=[_client_parser()], help="Print recorded run events."
    )
    runs_logs.add_argument("run_id")
    runs_logs.add_argument(
        "--operations", action="store_true", help="Print operations instead of events."
    )
    runs_logs.set_defaults(handler=_runs_logs)

    # Keep the familiar top-level spelling while making `runs logs` discoverable.
    logs = commands.add_parser(
        "logs", parents=[_client_parser()], help="Alias for `runs logs`."
    )
    logs.add_argument("run_id")
    logs.add_argument("--operations", action="store_true")
    logs.set_defaults(handler=_runs_logs)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = None
    try:
        args = parser.parse_args(argv)
        return int(args.handler(args))
    except (ConfigError, WorkflowInputError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except (WorkflowDiscoveryError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_NOT_FOUND
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI boundary reports workflow failures
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_RUNTIME
    finally:
        client = getattr(args, "_runtime", None)
        if client is not None:
            client.close()


def _location_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--workspace", type=Path, default=Path("."))
    return parser


def _client_parser() -> argparse.ArgumentParser:
    parser = _location_parser()
    parser.add_argument(
        "--config", type=Path, help="TOML, JSON, or pyproject configuration."
    )
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--provider")
    parser.add_argument("--provider-config", help="Provider-specific JSON object.")
    parser.add_argument(
        "--policy",
        "--policy-file",
        help="Policy JSON object or path to a JSON/TOML file.",
    )
    parser.add_argument("--model", help="Convenience override for policy.model.")
    parser.add_argument(
        "--effort", "--model-effort", help="Convenience override for policy.effort."
    )
    parser.add_argument("--max-operations", type=int)
    parser.add_argument("--timeout", type=float)
    return parser


def _add_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--input",
        help="JSON invocation: object for keyword arguments, array for positional arguments.",
    )
    parser.add_argument(
        "--input-file", type=Path, help="Read the JSON invocation from a file."
    )
    parser.add_argument(
        "--arg", action="append", default=[], help="Additional positional JSON value."
    )
    parser.add_argument(
        "--kw",
        action="append",
        default=[],
        metavar="NAME=JSON",
        help="Keyword JSON value.",
    )


def _workflows_list(args: argparse.Namespace) -> int:
    _emit(
        [
            entry.to_dict()
            for entry in discover_workflows(
                args.workspace, include_labs=not args.no_labs
            )
        ]
    )
    return EXIT_OK


def _doctor(args: argparse.Namespace) -> int:
    from .locks import canonical_workspace

    workspace = canonical_workspace(args.workspace)
    try:
        with _client(args) as client:
            capabilities = client.provider.probe()
    except Exception as exc:  # noqa: BLE001 - report provider diagnostic failures
        _emit(
            {
                "workspace": workspace,
                "codex": {"available": False, "error": str(exc)},
            }
        )
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_RUNTIME
    value = (
        capabilities.to_dict()
        if hasattr(capabilities, "to_dict")
        else capabilities
    )
    report = dict(value) if isinstance(value, Mapping) else {"capabilities": value}
    report["workspace"] = workspace
    _emit(report)
    try:
        require = getattr(capabilities, "require", None)
        if callable(require):
            require("run")
        elif isinstance(value, Mapping):
            run_status = value.get("presets", {}).get("run")
            if isinstance(run_status, Mapping) and not run_status.get("available"):
                raise RuntimeError(
                    run_status.get("reason") or "Codex run preset is unavailable"
                )
    except Exception as exc:  # noqa: BLE001 - doctor reports unusable run support
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_RUNTIME
    return EXIT_OK


def _workflows_show(args: argparse.Namespace) -> int:
    _emit(inspect_workflow(args.workflow, args.workspace))
    return EXIT_OK


def _run(args: argparse.Namespace) -> int:
    client = _client(args)
    workflow = resolve_workflow(args.workflow, args.workspace)
    positional, keyword = _invocation(args)
    result = client.run(
        workflow, *positional, task_id=args.task_id, run_id=args.run_id, **keyword
    )
    _emit(result)
    return _result_exit_code(result)


def _resume(args: argparse.Namespace) -> int:
    client = _client(args)
    workflow = (
        resolve_workflow(args.workflow, args.workspace) if args.workflow else None
    )
    kwargs: dict[str, Any] = {}
    if args.answer_file is not None:
        kwargs["answer"] = _read_json_file(args.answer_file)
    elif args.answer is not None:
        kwargs["answer"] = _json_or_text(args.answer)
    if workflow is not None:
        kwargs["workflow"] = workflow
    if args.max_operations is not None:
        kwargs["max_operations"] = args.max_operations
    if args.timeout is not None:
        kwargs["timeout"] = args.timeout
    result = client.resume(args.run_id, **kwargs)
    _emit(result)
    if "answer" in kwargs and _value(result, "status") == "awaiting_input":
        pending = _value(result, "pending_input") or {}
        if pending.get("diagnostic") is not None:
            return EXIT_USAGE
    return _result_exit_code(result)


def _answer(args: argparse.Namespace) -> int:
    args.answer_file = None
    return _resume(args)


def _resolve(args: argparse.Namespace) -> int:
    client = _client(args)
    options = {"retry": args.retry}
    if args.accept:
        options["accept"] = True
    if args.fail:
        options["fail"] = True
    if args.response is not None:
        # Passing the keyword is significant: JSON null is a valid activity result.
        options["response"] = _json_or_text(args.response)
    if args.artifact_digests is not None:
        options["artifact_digests"] = _json_object(
            args.artifact_digests, "--artifact-digests"
        )
    client.resolve(args.run_id, args.operation_id, **options)
    if args.no_resume or args.fail:
        _emit(
            {"run_id": args.run_id, "operation_id": args.operation_id, "resolved": True}
        )
        return EXIT_OK
    workflow = (
        resolve_workflow(args.workflow, args.workspace) if args.workflow else None
    )
    kwargs = {"workflow": workflow} if workflow is not None else {}
    if args.max_operations is not None:
        kwargs["max_operations"] = args.max_operations
    if args.timeout is not None:
        kwargs["timeout"] = args.timeout
    result = client.resume(args.run_id, **kwargs)
    _emit(result)
    return _result_exit_code(result)


def _runs_list(args: argparse.Namespace) -> int:
    records = list(_client(args).runs())
    filters = {
        "workflow": args.workflow,
        "task_id": args.task_id,
        "status": args.status,
    }
    for key, expected in filters.items():
        if expected is not None:
            records = [record for record in records if _value(record, key) == expected]
    _emit(records)
    return EXIT_OK


def _runs_show(args: argparse.Namespace) -> int:
    _emit(inspect_run(_client(args), args.run_id))
    return EXIT_OK


def _runs_logs(args: argparse.Namespace) -> int:
    details = _client(args).inspect(args.run_id)
    records = details.get("operations" if args.operations else "events", [])
    for record in records:
        print(json.dumps(_jsonable(record), sort_keys=True))
    return EXIT_OK


def _client(args: argparse.Namespace) -> Any:
    provider_config = (
        _json_object(args.provider_config, "--provider-config")
        if args.provider_config
        else None
    )
    policy = _policy_input(args.policy) if args.policy else None
    if args.model is not None or args.effort is not None:
        policy = dict(policy or {})
        if args.model is not None:
            policy["model"] = args.model
        if args.effort is not None:
            policy["effort"] = args.effort
    config = load_config(
        args.workspace,
        path=args.config,
        provider=args.provider,
        state_dir=args.state_dir,
        policy=policy,
        provider_config=provider_config,
        max_operations=args.max_operations,
        timeout=args.timeout,
    )
    kwargs = config.client_kwargs()
    kwargs["policy"] = _make_policy(kwargs["policy"])
    from . import Botpipe

    args._runtime = Botpipe(**kwargs)
    return args._runtime


def _invocation(args: argparse.Namespace) -> tuple[tuple[Any, ...], dict[str, Any]]:
    if args.input is not None and args.input_file is not None:
        raise WorkflowInputError("use only one of --input and --input-file")
    positional: list[Any] = []
    keyword: dict[str, Any] = {}
    if args.request is not None:
        positional.append(args.request)
    invocation = None
    if args.input_file is not None:
        invocation = _read_json_file(args.input_file)
    elif args.input is not None:
        try:
            invocation = json.loads(args.input)
        except json.JSONDecodeError as exc:
            raise WorkflowInputError(f"--input must be valid JSON: {exc.msg}") from exc
    if invocation is not None:
        if isinstance(invocation, dict):
            keyword.update(invocation)
        elif isinstance(invocation, list):
            positional.extend(invocation)
        else:
            positional.append(invocation)
    positional.extend(_json_value(value, "--arg") for value in args.arg)
    for assignment in args.kw:
        name, separator, raw = assignment.partition("=")
        if not separator or not name:
            raise WorkflowInputError("--kw values must use NAME=JSON")
        if name in keyword:
            raise WorkflowInputError(f"input {name!r} was provided more than once")
        keyword[name] = _json_value(raw, f"--kw {name}")
    return tuple(positional), keyword


def _policy_input(value: str) -> dict[str, Any]:
    path = Path(value).expanduser()
    if path.is_file():
        if path.suffix.lower() == ".json":
            return _json_object(path.read_text(encoding="utf-8"), "--policy")
        if path.suffix.lower() == ".toml":
            import tomllib

            payload = tomllib.loads(path.read_text(encoding="utf-8"))
            return dict(payload.get("policy", payload))
        raise ConfigError("--policy files must be JSON or TOML")
    return _json_object(value, "--policy")


def _make_policy(value: Any) -> Any:
    if value is None or not isinstance(value, Mapping):
        return value
    try:
        from .policy import Policy
    except (ImportError, AttributeError):
        return value
    from_dict = getattr(Policy, "from_dict", None)
    if callable(from_dict):
        return from_dict(dict(value))
    return Policy(**dict(value))


def _read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"could not read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc.msg}") from exc


def _json_object(value: str, option: str) -> dict[str, Any]:
    payload = _json_value(value, option)
    if not isinstance(payload, dict):
        raise ConfigError(f"{option} must be a JSON object")
    return payload


def _json_value(value: str, option: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{option} must be valid JSON: {exc.msg}") from exc


def _json_or_text(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _result_exit_code(result: Any) -> int:
    status = _value(result, "status")
    return EXIT_RUNTIME if status in {"failed", "budget_exceeded"} else EXIT_OK


def _value(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _emit(value: Any) -> None:
    print(json.dumps(_jsonable(value), indent=2, sort_keys=True))


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if dataclasses.is_dataclass(value):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    for method in ("model_dump", "to_dict", "to_record"):
        callback = getattr(value, method, None)
        if callable(callback):
            return _jsonable(callback())
    if hasattr(value, "__dict__"):
        return {
            key: _jsonable(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return repr(value)


__all__ = ["build_parser", "main"]


if __name__ == "__main__":  # pragma: no cover - exercised by subprocess tests
    raise SystemExit(main())
