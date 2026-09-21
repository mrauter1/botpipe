"""Declared workflow and observed-run inspection."""

from __future__ import annotations

import hashlib
import inspect
import re
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from . import codec
from .discovery import resolve_workflow, workflow_contract


def inspect_workflow(
    reference: str | Callable[..., Any], workspace: str | Path = "."
) -> dict[str, Any]:
    """Describe a callable contract and source without inventing static topology."""

    workflow = resolve_workflow(reference, workspace)
    unwrapped = inspect.unwrap(workflow)
    try:
        source = inspect.getsource(unwrapped)
        source_file = inspect.getsourcefile(unwrapped)
        source_line = inspect.getsourcelines(unwrapped)[1]
    except (OSError, TypeError):
        source = None
        source_file = None
        source_line = None
    declaration = _declaration(workflow)
    return {
        "name": declaration.get("name")
        or getattr(workflow, "__name__", type(workflow).__name__),
        "version": declaration.get("version"),
        "module": getattr(workflow, "__module__", None),
        "function": getattr(
            workflow, "__qualname__", getattr(workflow, "__name__", None)
        ),
        "description": inspect.getdoc(workflow),
        "contract": workflow_contract(workflow, workspace),
        "policy": _record(declaration.get("policy")),
        "source": {
            "path": source_file,
            "line": source_line,
            "text": source,
            "sha256": hashlib.sha256(source.encode()).hexdigest()
            if source is not None
            else None,
        },
        "topology": {
            "dynamic": True,
            "complete": False,
            "message": "Branches, loops, nested workflows, and operations are observed during execution.",
        },
    }


def inspect_run(client: Any, run_id: str) -> dict[str, Any]:
    """Return run details plus a graph built only from observed operations."""

    details = client.inspect(run_id)
    if not isinstance(details, Mapping):
        raise TypeError("Botpipe.inspect() must return a mapping")
    payload = dict(details)
    operations = list(payload.get("operations") or ())
    payload["observed_graph"] = observed_graph(operations)
    run = payload.get("run")
    payload["topology"] = {
        "dynamic": True,
        "complete": False,
        "run_finished": run.get("status") in {"completed", "failed", "budget_exceeded"}
        if isinstance(run, Mapping)
        else False,
        "message": "This graph contains recorded operations only.",
    }
    return payload


def observed_graph(operations: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Build deterministic nodes and only provable ordering/lineage edges."""

    ordered = sorted(
        operations,
        key=lambda operation: (
            str(operation.get("scope") or ""),
            _integer(operation.get("ordinal")),
            _operation_id(operation),
        ),
    )
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    previous_by_scope: dict[str, str] = {}
    first_by_scope: dict[str, str] = {}
    operation_index: dict[tuple[str, int], Mapping[str, Any]] = {}

    for operation in ordered:
        operation_id = _operation_id(operation)
        if not operation_id:
            continue
        scope = str(operation.get("scope") or "root")
        ordinal = _integer(operation.get("ordinal"))
        inputs = _safe_decode(operation.get("inputs"))
        nodes.append(
            {
                "id": operation_id,
                "scope": scope,
                "ordinal": operation.get("ordinal"),
                "kind": operation.get("kind"),
                "name": operation.get("name"),
                "status": operation.get("status"),
                "inputs": inputs,
                "result": _safe_decode(operation.get("result")),
                "error": _safe_decode(operation.get("error")),
                "usage": _inspection_value(operation.get("usage") or {}),
                "attempt": inputs.get("attempt")
                if isinstance(inputs, Mapping)
                else None,
                "provider_session": _provider_session(operation),
                "artifact_dependencies": _artifact_dependencies(inputs),
                "started_at": operation.get("started_at"),
                "finished_at": operation.get("finished_at"),
            }
        )
        operation_index[(scope, ordinal)] = operation
        first_by_scope.setdefault(scope, operation_id)
        previous = previous_by_scope.get(scope)
        if previous:
            edges.append(
                {"from": previous, "to": operation_id, "kind": "observed_order"}
            )
        previous_by_scope[scope] = operation_id

    for scope, first_operation in first_by_scope.items():
        parent = _scope_parent_operation(scope)
        if parent is None:
            continue
        parent_scope, parent_ordinal, expected_kind = parent
        parent_record = operation_index.get((parent_scope, parent_ordinal))
        if parent_record is None or parent_record.get("kind") != expected_kind:
            continue
        parent_id = _operation_id(parent_record)
        if parent_id:
            edges.append(
                {"from": parent_id, "to": first_operation, "kind": "observed_child"}
            )

    return {"nodes": nodes, "edges": edges, "complete_static_topology": False}


def _scope_parent_operation(scope: str) -> tuple[str, int, str] | None:
    child = re.fullmatch(r"(.+)/child-(\d+)", scope)
    if child:
        return child.group(1), int(child.group(2)), "child"
    branch = re.fullmatch(r"(.+)/parallel-(\d+)/\d+", scope)
    if branch:
        return branch.group(1), int(branch.group(2)), "parallel"
    return None


def _declaration(workflow: Callable[..., Any]) -> dict[str, Any]:
    for marker in ("__botpipe_workflow__", "_botpipe_workflow", "__workflow__"):
        value = getattr(workflow, marker, None)
        if isinstance(value, Mapping):
            return dict(value)
        if value is not None and value is not True:
            return {
                key: getattr(value, key)
                for key in ("name", "version", "policy")
                if hasattr(value, key)
            }
    return {
        key: getattr(workflow, key)
        for key in ("name", "version", "policy")
        if hasattr(workflow, key)
    }


def _record(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool, list, dict)):
        return value
    for method in ("to_dict", "model_dump"):
        callback = getattr(value, method, None)
        if callable(callback):
            return callback()
    return repr(value)


def _safe_decode(value: Any) -> Any:
    try:
        decoded = codec.decode(value)
    except (AttributeError, ImportError, KeyError, TypeError, ValueError):
        decoded = value
    return _inspection_value(decoded)


def _inspection_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _inspection_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_inspection_value(item) for item in value]
    for method in ("to_record", "model_dump", "to_dict"):
        callback = getattr(value, method, None)
        if callable(callback):
            return _inspection_value(callback())
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _inspection_value(getattr(value, field.name))
            for field in fields(value)
        }
    return repr(value)


def _provider_session(operation: Mapping[str, Any]) -> Any:
    for field in ("response", "result"):
        value = _safe_decode(operation.get(field))
        if isinstance(value, Mapping) and value.get("session_id") is not None:
            return value["session_id"]
    inputs = _safe_decode(operation.get("inputs"))
    return inputs.get("session_id") if isinstance(inputs, Mapping) else None


def _artifact_dependencies(inputs: Any) -> dict[str, Any]:
    if not isinstance(inputs, Mapping):
        return {"reads": [], "writes": []}
    return {
        "reads": inputs.get("reads") or [],
        "writes": inputs.get("writes") or inputs.get("artifacts") or [],
    }


def _integer(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _operation_id(operation: Mapping[str, Any]) -> str:
    return str(operation.get("id") or operation.get("operation_id") or "")


__all__ = ["inspect_run", "inspect_workflow", "observed_graph"]
