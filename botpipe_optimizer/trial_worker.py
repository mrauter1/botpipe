"""Private subprocess entry point for :mod:`botpipe_optimizer.trials`."""

from __future__ import annotations

import difflib
import hashlib
import importlib.util
import json
import os
import sys
import time
import traceback
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

from botpipe import Botpipe, provider_budget, workflow
from botpipe.discovery import resolve_workflow, validate_workflow_inputs
from botpipe.inspection import inspect_run
from botpipe.providers import get_provider

from .trial_models import TrialCase, TrialResult, TrialSettings

_TARGET = None
_CASE: TrialCase | None = None
_SETTINGS: TrialSettings | None = None
_ARGS: tuple[Any, ...] = ()
_KWARGS: dict[str, Any] = {}


@workflow(name="optimizer_trial_wrapper", version="1")
def _trial_wrapper():
    assert _TARGET is not None and _CASE is not None and _SETTINGS is not None
    with provider_budget(
        max_turns=_SETTINGS.max_provider_turns,
        max_seconds=_SETTINGS.timeout_seconds,
    ):
        return _TARGET(*_ARGS, **_KWARGS)


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: trial_worker CONFIG RESULT")
    config_path = Path(sys.argv[1]).resolve(strict=True)
    result_path = Path(sys.argv[2]).resolve()
    started = time.monotonic()
    config: Mapping[str, Any] = {}
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        result = _execute(config, started)
        code = 0
    except BaseException as exc:  # noqa: BLE001 - subprocess protocol boundary
        case_id = "unknown"
        run_id = None
        raw_case = config.get("case")
        if isinstance(raw_case, Mapping):
            case_id = str(raw_case.get("case_id", case_id))
        raw_run_id = config.get("run_id")
        run_id = raw_run_id if isinstance(raw_run_id, str) else None
        result = TrialResult(
            case_id=case_id,
            execution="infrastructure_error",
            outcome="worker_exception",
            run_id=run_id,
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=20)}",
            elapsed_seconds=max(0.0, time.monotonic() - started),
        )
        code = 1
    _write_result(result_path, result)
    return code


def _execute(config: Mapping[str, Any], started: float) -> TrialResult:
    global _TARGET, _CASE, _SETTINGS, _ARGS, _KWARGS
    code_root = Path(config["code_root"]).resolve(strict=True)
    workspace = Path(config["workspace"]).resolve(strict=True)
    state_dir = Path(config["state_dir"]).resolve(strict=True)
    _CASE = TrialCase.model_validate(config["case"])
    _SETTINGS = TrialSettings.model_validate(config["settings"])
    try:
        _install_code_paths(code_root, str(config["workflow_reference"]))
        _TARGET = resolve_workflow(
            str(config["workflow_reference"]), workspace=code_root
        )
        bound = validate_workflow_inputs(_TARGET, tuple(_CASE.args), _CASE.kwargs)
    except Exception as exc:  # noqa: BLE001 - candidate import/input boundary
        artifacts, omissions, _remaining = capture_workspace_outputs(
            _CASE,
            workspace,
            Path(config["fixture_root"]) if config.get("fixture_root") else None,
            _SETTINGS.max_output_bytes,
        )
        return _fit(
            TrialResult(
                case_id=_CASE.case_id,
                execution="complete",
                outcome="failed",
                run_id=str(config["run_id"]),
                error=f"{type(exc).__name__}: {exc}",
                elapsed_seconds=max(0.0, time.monotonic() - started),
                artifacts=artifacts,
                omissions=[
                    "target workflow could not be invoked; no provider dispatched",
                    *omissions,
                ],
            ),
            _SETTINGS.max_output_bytes,
        )
    _ARGS, _KWARGS = bound.args, bound.kwargs
    provider_config = dict(config.get("provider_config") or {})
    provider = _provider(config.get("provider_factory"), provider_config, code_root)
    run_id = str(config["run_id"])
    task_id = str(config["task_id"])
    os.chdir(workspace)
    with Botpipe(
        workspace=workspace,
        state_dir=state_dir,
        provider=provider,
        provider_config=provider_config,
        policy=config.get("policy"),
        timeout=_SETTINGS.timeout_seconds,
    ) as client:
        ledger = state_dir / "tasks" / task_id / "runs" / run_id / "ledger.jsonl"
        if ledger.is_file():
            run = client.resume(run_id, workflow=_trial_wrapper)
        else:
            run = client.run(_trial_wrapper, task_id=task_id, run_id=run_id)
        details = inspect_run(client, run_id)
        operations = _operations(details)
        artifacts, omissions, remaining = capture_workspace_outputs(
            _CASE,
            workspace,
            Path(config["fixture_root"]) if config.get("fixture_root") else None,
            _SETTINGS.max_output_bytes,
        )
        managed_artifacts, managed_omissions = _artifacts(run.artifacts, remaining)
        artifacts.extend(managed_artifacts)
        omissions.extend(managed_omissions)
        budget = _budget(details, operations)
        execution = _execution_class(run.status, operations)
        payload = TrialResult(
            case_id=_CASE.case_id,
            execution=execution,
            outcome=run.status,
            run_id=run.run_id,
            value=_plain(run.value),
            error=run.error,
            artifacts=artifacts,
            operations=operations,
            usage=_plain(run.usage),
            elapsed_seconds=max(0.0, time.monotonic() - started),
            provider_budget=budget,
            omissions=omissions,
        )
    return _fit(payload, _SETTINGS.max_output_bytes)


def _install_code_paths(code_root: Path, reference: str) -> None:
    paths = [code_root]
    if ":" in reference:
        location = reference.rsplit(":", 1)[0]
        candidate = Path(location)
        if candidate.suffix == ".py" or candidate.exists():
            candidate = candidate if candidate.is_absolute() else code_root / candidate
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(code_root):
                raise ValueError("workflow file reference escapes code_root")
            paths.insert(0, resolved.parent)
    for path in reversed(paths):
        value = str(path)
        if value in sys.path:
            sys.path.remove(value)
        sys.path.insert(0, value)


def _provider(reference: Any, config: dict[str, Any], code_root: Path) -> Any:
    if reference is None:
        return get_provider("codex", config=config)
    if not isinstance(reference, str) or ":" not in reference:
        raise ValueError("provider_factory must be a module:function reference")
    module_name, qualified = reference.rsplit(":", 1)
    candidate = Path(module_name)
    if candidate.suffix == ".py" or candidate.exists():
        candidate = candidate if candidate.is_absolute() else code_root / candidate
        path = candidate.resolve(strict=True)
        factory = next(
            (
                module
                for module in sys.modules.values()
                if getattr(module, "__file__", None)
                and Path(module.__file__).resolve() == path
            ),
            None,
        )
        if factory is None:
            spec = importlib.util.spec_from_file_location(
                f"_botpipe_trial_factory_{abs(hash(str(path)))}", path
            )
            if spec is None or spec.loader is None:
                raise ImportError(f"could not load provider factory file: {path}")
            factory = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = factory
            spec.loader.exec_module(factory)
    else:
        factory = importlib.import_module(module_name)
    for part in qualified.split("."):
        factory = getattr(factory, part)
    if not callable(factory):
        raise TypeError("provider_factory did not resolve to a callable")
    provider = factory(dict(config))
    if not callable(getattr(provider, "run", None)):
        raise TypeError("provider_factory must return a provider object")
    return provider


def _operations(details: Mapping[str, Any]) -> list[dict[str, Any]]:
    graph = details.get("observed_graph") or {}
    nodes = graph.get("nodes") if isinstance(graph, Mapping) else []
    raw_by_id = {
        str(item.get("id") or item.get("operation_id")): item
        for item in details.get("operations", [])
        if isinstance(item, Mapping)
    }
    result = []
    for node in nodes or []:
        record = _plain(node)
        raw = raw_by_id.get(str(node.get("id")), {})
        dispatches = []
        for dispatch in raw.get("dispatches", []) if isinstance(raw, Mapping) else []:
            if not isinstance(dispatch, Mapping):
                continue
            response = dispatch.get("response")
            dispatches.append(
                _plain(
                    {
                        "outcome": dispatch.get("outcome"),
                        "usage": dispatch.get("usage") or {},
                        "usage_availability": dispatch.get("usage_availability"),
                        "response": response,
                        "error": dispatch.get("error"),
                    }
                )
            )
        if dispatches:
            record["dispatches"] = dispatches
        result.append(record)
    return result


def capture_workspace_outputs(
    case: TrialCase,
    workspace: Path,
    fixture_root: Path | None,
    max_read_bytes: int,
) -> tuple[list[dict[str, Any]], list[str], int]:
    result: list[dict[str, Any]] = []
    omissions: list[str] = []
    budget = {"remaining": max_read_bytes}
    for relative in case.output_paths:
        after_path, unsafe = _declared_path(workspace, relative)
        before_path, before_unsafe = (
            (None, None)
            if fixture_root is None
            else _declared_path(fixture_root, relative)
        )
        record: dict[str, Any] = {
            "key": f"workspace:{relative}",
            "kind": "workspace_output",
            "workspace_path": relative,
        }
        if unsafe or before_unsafe:
            record.update(status="unsafe", content_omitted="symlink_or_invalid_path")
            omissions.append(f"declared output {relative!r} uses an unsafe path")
            result.append(record)
            continue
        assert after_path is not None
        before = _declared_file(before_path, budget, f"original {relative}")
        after = _declared_file(after_path, budget, f"output {relative}")
        before_exists = before["state"] not in {"absent"}
        after_exists = after["state"] not in {"absent"}
        if not before_exists and not after_exists:
            record.update(status="missing", content_missing=True)
            omissions.append(f"declared output {relative!r} is missing")
        elif before_exists and not after_exists:
            record.update(status="deleted", content_deleted=True)
        elif not before_exists:
            record["status"] = "created"
        else:
            record["status"] = "unchanged" if before.get("data") == after.get("data") else "modified"
        if after_exists:
            record["size_bytes"] = after.get("size")
            record["sha256"] = after.get("sha256")
            if after["state"] == "text":
                record["content"] = after["text"]
            else:
                record["content_omitted"] = after["state"]
                omissions.append(
                    f"declared output {relative!r} content omitted: {after['state']}"
                )
        if before_exists or after_exists:
            if before["state"] in {"text", "absent"} and after["state"] in {
                "text",
                "absent",
            }:
                record["diff"] = "".join(
                    difflib.unified_diff(
                        [] if before["state"] == "absent" else before["text"].splitlines(keepends=True),
                        [] if after["state"] == "absent" else after["text"].splitlines(keepends=True),
                        fromfile="/dev/null" if before["state"] == "absent" else f"a/{relative}",
                        tofile="/dev/null" if after["state"] == "absent" else f"b/{relative}",
                    )
                )
            else:
                record["diff_omitted"] = "binary_or_oversize"
                omissions.append(
                    f"declared output {relative!r} diff omitted: binary or oversize"
                )
        result.append(record)
    return result, omissions, budget["remaining"]


def _declared_path(root: Path, relative: str) -> tuple[Path | None, str | None]:
    raw = Path(relative)
    if (
        raw.is_absolute()
        or not raw.parts
        or any(part in {"", ".", ".."} for part in raw.parts)
        or "\\" in relative
    ):
        return None, "invalid"
    candidate = root / raw
    current = candidate
    while True:
        if current.is_symlink():
            return None, "symlink"
        if current == root:
            break
        if root not in current.parents:
            return None, "escape"
        current = current.parent
    return candidate, None


def _declared_file(
    path: Path | None, budget: dict[str, int], label: str
) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"state": "absent"}
    if path.is_symlink() or not path.is_file():
        return {"state": "not_regular"}
    size = path.stat().st_size
    if size > budget["remaining"]:
        return {"state": "oversize", "size": size}
    with path.open("rb") as stream:
        data = stream.read(budget["remaining"] + 1)
    if len(data) > budget["remaining"]:
        return {"state": "oversize", "size": len(data)}
    budget["remaining"] -= len(data)
    record: dict[str, Any] = {
        "state": "binary",
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "data": data,
        "label": label,
    }
    try:
        record.update(state="text", text=data.decode("utf-8"))
    except UnicodeDecodeError:
        pass
    return record


def _artifacts(handles: Any, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    result: list[dict[str, Any]] = []
    omissions: list[str] = []
    content_budget = limit
    for name, handle in sorted(handles.items()):
        record = _plain(handle.to_record())
        record["key"] = name
        try:
            size = handle.path.stat().st_size
            if size > content_budget:
                raise OverflowError(size)
            data = handle.read_bytes()
            content_budget -= len(data)
        except OverflowError as exc:
            record["content_omitted"] = "oversize"
            record["size_bytes"] = exc.args[0]
            omissions.append(f"artifact {name!r} content exceeded evidence limit")
        except (OSError, ValueError) as exc:
            record["content_missing"] = True
            omissions.append(f"artifact {name!r} could not be read: {type(exc).__name__}")
        else:
            if handle.kind == "raw":
                record["content_omitted"] = "binary"
                omissions.append(f"artifact {name!r} binary content omitted")
            else:
                try:
                    text = data.decode("utf-8")
                    record["content"] = json.loads(text) if handle.kind == "json" else text
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    record["content_omitted"] = "invalid_text_or_json"
                    omissions.append(f"artifact {name!r} content omitted: {type(exc).__name__}")
        result.append(record)
    return result, omissions


def _execution_class(status: str, operations: list[dict[str, Any]]) -> str:
    if status in {"completed", "budget_exceeded"}:
        return "complete"
    if status not in {"failed"}:
        return "interrupted"
    infrastructure_types = {
        ("botpipe.capabilities", "CapabilityError"),
        ("botpipe.codex_appserver", "CodexProtocolError"),
        ("botpipe.codex_appserver", "CodexTurnError"),
        ("botpipe.errors", "SessionError"),
        ("botpipe.providers", "ProviderError"),
        ("botpipe.providers", "ProviderInterruptedError"),
        ("botpipe.providers", "ProviderPolicyError"),
        ("botpipe.providers", "ProviderTimeoutError"),
    }
    for operation in operations:
        if operation.get("kind") != "provider" or operation.get("status") != "failed":
            continue
        error = operation.get("error")
        if isinstance(error, Mapping) and (error.get("module"), error.get("type")) in infrastructure_types:
            return "infrastructure_error"
    return "complete"


def _budget(details: Mapping[str, Any], operations: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [str(item.get("id")) for item in operations if item.get("kind") == "provider_budget"]
    if not ids:
        return {}
    selected = ids[0]
    state: dict[str, Any] = {}
    for event in details.get("events", []):
        if not isinstance(event, Mapping):
            continue
        data = event.get("data")
        if (
            event.get("event") == "budget_created"
            and isinstance(data, Mapping)
            and data.get("budget_id") == selected
            and isinstance(data.get("state"), Mapping)
        ):
            state = dict(data["state"])
        states = data.get("budget_states") if isinstance(data, Mapping) else None
        if isinstance(states, Mapping) and isinstance(states.get(selected), Mapping):
            state = dict(states[selected])
    state.pop("last_observed", None)
    return _plain(state)


def _plain(value: Any, *, depth: int = 0) -> Any:
    if depth > 30:
        return "<omitted: maximum depth>"
    if value is None or type(value) in {str, int, float, bool}:
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _plain(item, depth=depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(item, depth=depth + 1) for item in value]
    for method in ("model_dump", "to_record", "to_dict"):
        callback = getattr(value, method, None)
        if callable(callback):
            return _plain(callback(), depth=depth + 1)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _plain(getattr(value, field.name), depth=depth + 1)
            for field in fields(value)
        }
    return repr(value)


def _fit(result: TrialResult, limit: int) -> TrialResult:
    if len(_encoded(result)) <= limit:
        return result
    omissions = list(result.omissions)
    artifacts = []
    for artifact in result.artifacts:
        item = dict(artifact)
        if "content" in item:
            item.pop("content")
            item["content_omitted"] = "trial_result_limit"
        if "diff" in item:
            item.pop("diff")
            item["diff_omitted"] = "trial_result_limit"
        artifacts.append(item)
    omissions.append("artifact contents omitted to fit max_output_bytes")
    result = result.model_copy(update={"artifacts": artifacts, "omissions": omissions})
    if len(_encoded(result)) <= limit:
        return result
    operations = []
    for operation in result.operations:
        operations.append(
            {
                key: operation.get(key)
                for key in ("id", "scope", "ordinal", "kind", "name", "status", "usage")
                if key in operation
            }
        )
    omissions.append("operation details omitted to fit max_output_bytes")
    result = result.model_copy(update={"operations": operations, "omissions": omissions})
    if len(_encoded(result)) <= limit:
        return result
    omissions.append("return value omitted to fit max_output_bytes")
    result = result.model_copy(update={"value": None, "omissions": omissions})
    if len(_encoded(result)) > limit:
        result = result.model_copy(
            update={
                "artifacts": [],
                "operations": [],
                "error": (result.error or "")[:1024] or None,
                "omissions": ["trial evidence omitted to fit max_output_bytes"],
            }
        )
    if len(_encoded(result)) > limit:
        raise ValueError("minimal trial result exceeds max_output_bytes")
    return result


def _encoded(result: TrialResult) -> bytes:
    return json.dumps(
        result.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _write_result(path: Path, result: TrialResult) -> None:
    data = _encoded(result)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


if __name__ == "__main__":
    raise SystemExit(main())
