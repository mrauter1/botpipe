"""Runtime-owned static workflow graph persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from autoloop.core.compiler import CompiledRoute, CompiledWorkflow
from autoloop.core.primitives import AWAIT_INPUT, FAIL, FINISH
from autoloop.core.prompts import Prompt
from autoloop.core.route_required_writes import route_required_write_payload
from autoloop.core.schema_registry import (
    WORKFLOW_ARTIFACT_CONTRACTS_SCHEMA,
    WORKFLOW_PROMPT_REFS_SCHEMA,
    WORKFLOW_SESSION_CONTRACTS_SCHEMA,
    WORKFLOW_STATE_CONTRACTS_SCHEMA,
    WORKFLOW_STATIC_STEP_GRAPH_SCHEMA,
    WORKFLOW_TOPOLOGY_SCHEMA,
)
from autoloop.core.step_state import built_in_step_state_model


STATIC_GRAPH_SCHEMA = WORKFLOW_STATIC_STEP_GRAPH_SCHEMA
STATIC_GRAPH_FILENAME = "static_step_graph.json"

TOPOLOGY_SCHEMA = WORKFLOW_TOPOLOGY_SCHEMA
TOPOLOGY_FILENAME = "topology.json"
TOPOLOGY_MERMAID_FILENAME = "topology.mmd"
ROUTE_TABLE_FILENAME = "route_table.md"
ARTIFACT_CONTRACTS_FILENAME = "artifact_contracts.json"
PROMPT_REFS_FILENAME = "prompt_refs.json"
STATE_CONTRACTS_FILENAME = "state_contracts.json"
SESSION_CONTRACTS_FILENAME = "session_contracts.json"
COMPILE_REPORT_FILENAME = "compile_report.md"

ARTIFACT_CONTRACTS_SCHEMA = WORKFLOW_ARTIFACT_CONTRACTS_SCHEMA
PROMPT_REFS_SCHEMA = WORKFLOW_PROMPT_REFS_SCHEMA
STATE_CONTRACTS_SCHEMA = WORKFLOW_STATE_CONTRACTS_SCHEMA
SESSION_CONTRACTS_SCHEMA = WORKFLOW_SESSION_CONTRACTS_SCHEMA


def workflow_static_step_graph_payload(compiled: CompiledWorkflow) -> dict[str, Any]:
    return {
        "schema": STATIC_GRAPH_SCHEMA,
        "workflow_name": compiled.workflow_name,
        "terminals": [FINISH, AWAIT_INPUT, FAIL],
        "workflow_state": _workflow_state_surface_payload(compiled),
        "workflow_params": _workflow_params_surface_payload(compiled),
        "worklists": _worklist_surfaces_payload(compiled),
        "steps": [
            {
                "name": step.name,
                "kind": step.kind,
                "prompt": _prompt_path(step.prompt),
                "producer_prompt": _prompt_path(step.producer_prompt),
                "verifier_prompt": _prompt_path(step.verifier_prompt),
                "reads": list(step.reads),
                "requires": list(step.requires),
                "producer_reads": list(step.producer_reads),
                "producer_requires": list(step.producer_requires),
                "producer_writes": list(step.producer_writes),
                "verifier_reads": list(step.verifier_reads),
                "verifier_requires": list(step.verifier_requires),
                "verifier_writes": list(step.verifier_writes),
                "writes": list(step.writes),
                "log_artifacts": list(step.log_artifacts),
                "available_routes": list(step.available_routes),
                "authored_routes": list(step.authored_routes),
                "runtime_control_routes": list(step.runtime_control_routes),
                "provider_visible_routes_interactive": list(step.provider_visible_routes_interactive),
                "provider_visible_routes_full_auto": list(step.provider_visible_routes_full_auto),
                "verifier_session_name": step.verifier_session_name,
                "state_surface": _step_state_surface_payload(step),
                "step_item_state_model": step.step_item_state_model.__name__ if step.step_item_state_model is not None else None,
                "step_item_state_fields": list(step.step_item_state_fields),
                "step_item_state_surface": _step_item_state_surface_payload(step),
                "runtime_control_hook_locations": _runtime_control_hook_locations(compiled, step),
                "routes": {
                    route_name: _topology_route_payload(
                        compiled=compiled,
                        step_name=step.name,
                        route_tag=route_name,
                        route=compiled.routes.get(step.name, {}).get(route_name) or compiled.global_routes.get(route_name),
                    )
                    for route_name in step.available_routes
                },
                "prompt_references": list(_prompt_references(step)),
                "has_expected_output_schema": step.expected_output_schema is not None,
            }
            for step in compiled.steps.values()
        ],
        "transitions": {
            "steps": {
                step_name: {
                    route_tag: compiled_route.target
                    for route_tag, compiled_route in routes.items()
                }
                for step_name, routes in compiled.routes.items()
            },
            "global": {
                route_tag: compiled_route.target
                for route_tag, compiled_route in compiled.global_routes.items()
            },
        },
    }


def workflow_topology_payload(compiled: CompiledWorkflow) -> dict[str, Any]:
    return {
        "schema": TOPOLOGY_SCHEMA,
        "workflow_name": compiled.workflow_name,
        "source_hash": compiled.source_hash,
        "topology_hash": compiled.topology_hash,
        "entry": compiled.entry_step_name,
        "terminals": [FINISH, AWAIT_INPUT, FAIL],
        "workflow_state": _workflow_state_surface_payload(compiled),
        "workflow_params": _workflow_params_surface_payload(compiled),
        "worklists": _worklist_surfaces_payload(compiled),
        "steps": [
            {
                "name": step.name,
                "kind": step.kind,
                "prompt": _prompt_path(step.prompt),
                "producer_prompt": _prompt_path(step.producer_prompt),
                "verifier_prompt": _prompt_path(step.verifier_prompt),
                "reads": list(step.reads),
                "requires": list(step.requires),
                "producer_reads": list(step.producer_reads),
                "producer_requires": list(step.producer_requires),
                "producer_writes": list(step.producer_writes),
                "verifier_reads": list(step.verifier_reads),
                "verifier_requires": list(step.verifier_requires),
                "verifier_writes": list(step.verifier_writes),
                "writes": list(step.writes),
                "log_artifacts": list(step.log_artifacts),
                "prompt_references": list(_prompt_references(step)),
                "available_routes": list(step.available_routes),
                "authored_routes": list(step.authored_routes),
                "hooks": {
                    "before": _callable_name(step.before_hook),
                    "after": _callable_name(step.after_hook),
                    "before_producer": _callable_name(step.before_producer_hook),
                    "after_producer": _callable_name(step.after_producer_hook),
                    "before_verifier": _callable_name(step.before_verifier_hook),
                    "after_verifier": _callable_name(step.after_verifier_hook),
                },
                "provider_visible_routes_interactive": list(step.provider_visible_routes_interactive),
                "provider_visible_routes_full_auto": list(step.provider_visible_routes_full_auto),
                "verifier_session_name": step.verifier_session_name,
                "runtime_control_routes": list(step.runtime_control_routes),
                "state_model": step.step_state_model.__name__,
                "state_fields": list(step.step_state_fields),
                "state_surface": _step_state_surface_payload(step),
                "step_item_state_model": step.step_item_state_model.__name__ if step.step_item_state_model is not None else None,
                "step_item_state_fields": list(step.step_item_state_fields),
                "step_item_state_surface": _step_item_state_surface_payload(step),
                "runtime_control_hook_locations": _runtime_control_hook_locations(compiled, step),
                "routes": [
                    _topology_route_payload(
                        compiled=compiled,
                        step_name=step.name,
                        route_tag=route_tag,
                        route=compiled.routes.get(step.name, {}).get(route_tag) or compiled.global_routes.get(route_tag),
                    )
                    for route_tag in step.available_routes
                ],
            }
            for step in compiled.steps.values()
        ],
        "global_routes": {
            route_tag: _topology_route_payload(
                compiled=compiled,
                step_name=None,
                route_tag=route_tag,
                route=route,
            )
            for route_tag, route in compiled.global_routes.items()
        },
    }


def write_static_step_graph(run_dir: Path, compiled: CompiledWorkflow) -> Path:
    return write_static_step_graph_payload(run_dir, workflow_static_step_graph_payload(compiled))


def write_topology_artifacts(run_dir: Path, compiled: CompiledWorkflow) -> dict[str, Path]:
    topology_payload = workflow_topology_payload(compiled)
    outputs = {
        TOPOLOGY_FILENAME: _write_json_file(run_dir / TOPOLOGY_FILENAME, topology_payload),
        ARTIFACT_CONTRACTS_FILENAME: _write_json_file(
            run_dir / ARTIFACT_CONTRACTS_FILENAME,
            {
                "schema": ARTIFACT_CONTRACTS_SCHEMA,
                "workflow_name": compiled.workflow_name,
                "source_hash": compiled.source_hash,
                "topology_hash": compiled.topology_hash,
                "artifacts": [
                    {
                        "qualified_name": name,
                        "kind": artifact.kind,
                        "required": artifact.required,
                        "owner_step": artifact.owner_step,
                        "producer_steps": list(artifact.producer_steps),
                    }
                    for name, artifact in compiled.artifacts_by_qualified_name.items()
                ],
            },
        ),
        PROMPT_REFS_FILENAME: _write_json_file(
            run_dir / PROMPT_REFS_FILENAME,
            {
                "schema": PROMPT_REFS_SCHEMA,
                "workflow_name": compiled.workflow_name,
                "source_hash": compiled.source_hash,
                "topology_hash": compiled.topology_hash,
                "steps": {step.name: list(_prompt_references(step)) for step in compiled.steps.values()},
            },
        ),
        STATE_CONTRACTS_FILENAME: _write_json_file(
            run_dir / STATE_CONTRACTS_FILENAME,
            {
                "schema": STATE_CONTRACTS_SCHEMA,
                "workflow_name": compiled.workflow_name,
                "source_hash": compiled.source_hash,
                "topology_hash": compiled.topology_hash,
                "workflow_state": {
                    "model": compiled.state_cls.__name__,
                    "fields": sorted(getattr(compiled.state_cls, "model_fields", {}).keys()),
                },
                "workflow_params": None
                if compiled.parameters_cls is None
                else {
                    "model": compiled.parameters_cls.__name__,
                    "fields": sorted(getattr(compiled.parameters_cls, "model_fields", {}).keys()),
                },
                "step_states": {
                    step.name: {
                        "model": step.step_state_model.__name__,
                        "fields": list(step.step_state_fields),
                        "runtime_fields": _step_runtime_state_fields(step),
                        "custom_fields": [
                            field_name
                            for field_name in step.step_state_fields
                            if field_name not in _step_runtime_state_fields(step)
                        ],
                    }
                    for step in compiled.steps.values()
                },
                "step_item_states": {
                    step.name: {
                        "model": step.step_item_state_model.__name__ if step.step_item_state_model is not None else None,
                        "fields": list(step.step_item_state_fields),
                        "runtime_fields": _step_runtime_state_fields(step) if step.step_item_state_model is not None else [],
                        "custom_fields": [
                            field_name
                            for field_name in step.step_item_state_fields
                            if field_name not in _step_runtime_state_fields(step)
                        ],
                    }
                    for step in compiled.steps.values()
                },
                "worklist_item_states": _worklist_surfaces_payload(compiled),
            },
        ),
        SESSION_CONTRACTS_FILENAME: _write_json_file(
            run_dir / SESSION_CONTRACTS_FILENAME,
            {
                "schema": SESSION_CONTRACTS_SCHEMA,
                "workflow_name": compiled.workflow_name,
                "source_hash": compiled.source_hash,
                "topology_hash": compiled.topology_hash,
                "global_session": compiled.default_session_name,
                "global_session_open": compiled.default_session_open,
                "sessions": [
                    {
                        "name": name,
                        "continuity": session.continuity.kind,
                        "open": session.open,
                    }
                    for name, session in compiled.sessions.items()
                ],
            },
        ),
        ROUTE_TABLE_FILENAME: _write_text_file(run_dir / ROUTE_TABLE_FILENAME, _route_table_text(compiled)),
        TOPOLOGY_MERMAID_FILENAME: _write_text_file(run_dir / TOPOLOGY_MERMAID_FILENAME, _topology_mermaid(compiled)),
        COMPILE_REPORT_FILENAME: _write_text_file(run_dir / COMPILE_REPORT_FILENAME, _compile_report_text(compiled)),
    }
    return outputs


def write_static_step_graph_payload(run_dir: Path, payload: dict[str, Any] | Mapping[str, Any]) -> Path:
    return _write_json_file(run_dir / STATIC_GRAPH_FILENAME, dict(payload))


def _write_json_file(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=2, ensure_ascii=False, default=_json_value) + "\n",
        encoding="utf-8",
    )
    return path


def _write_text_file(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    return path


def _prompt_path(prompt: str | Prompt | None) -> str | None:
    if prompt is None:
        return None
    if isinstance(prompt, Prompt):
        return prompt.path
    return prompt


def _prompt_references(step: Any) -> tuple[str, ...]:
    return tuple(_json_value(reference) for reference in getattr(step.step, "simple_prompt_references", ()))


def _workflow_state_surface_payload(compiled: CompiledWorkflow) -> dict[str, Any]:
    return {
        "model": compiled.state_cls.__name__,
        "fields": sorted(getattr(compiled.state_cls, "model_fields", {}).keys()),
    }


def _workflow_params_surface_payload(compiled: CompiledWorkflow) -> dict[str, Any] | None:
    if compiled.parameters_cls is None:
        return None
    return {
        "model": compiled.parameters_cls.__name__,
        "fields": sorted(getattr(compiled.parameters_cls, "model_fields", {}).keys()),
    }


def _worklist_surfaces_payload(compiled: CompiledWorkflow) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "item_state_model": worklist.runtime_item_state_model.__name__,
            "item_state_fields": sorted(worklist.runtime_item_state_model.model_fields.keys()),
            "item_state_runtime_fields": ["status", "last_step", "last_route"],
            "item_state_custom_fields": [
                field_name
                for field_name in sorted(worklist.runtime_item_state_model.model_fields.keys())
                if field_name not in {"status", "last_step", "last_route"}
            ],
            "source_type": worklist.source_type,
            "source_descriptor": worklist.source_descriptor(),
            "missing_policy": worklist.missing_policy,
            "materialization_state": "declared",
        }
        for name, worklist in compiled.worklists.items()
    }


def _step_runtime_state_fields(step: Any) -> list[str]:
    return list(built_in_step_state_model(step.kind).model_fields.keys())


def _state_surface_payload(
    *,
    model_name: str | None,
    fields: list[str],
    runtime_fields: list[str],
) -> dict[str, Any]:
    runtime_field_set = set(runtime_fields)
    return {
        "model": model_name,
        "fields": fields,
        "runtime_fields": runtime_fields,
        "custom_fields": [field_name for field_name in fields if field_name not in runtime_field_set],
    }


def _step_state_surface_payload(step: Any) -> dict[str, Any]:
    runtime_fields = _step_runtime_state_fields(step)
    return _state_surface_payload(
        model_name=step.step_state_model.__name__,
        fields=list(step.step_state_fields),
        runtime_fields=runtime_fields,
    )


def _step_item_state_surface_payload(step: Any) -> dict[str, Any] | None:
    if step.step_item_state_model is None:
        return None
    runtime_fields = _step_runtime_state_fields(step)
    return _state_surface_payload(
        model_name=step.step_item_state_model.__name__,
        fields=list(step.step_item_state_fields),
        runtime_fields=runtime_fields,
    )


def _runtime_control_hook_locations(compiled: CompiledWorkflow, step: Any) -> list[dict[str, Any]]:
    locations: list[dict[str, Any]] = []
    for hook_phase, hook in (
        ("before", step.before_hook),
        ("before_producer", step.before_producer_hook),
        ("before_verifier", step.before_verifier_hook),
        ("after", step.after_hook),
        ("after_producer", step.after_producer_hook),
        ("after_verifier", step.after_verifier_hook),
    ):
        if hook is None:
            continue
        locations.append({"hook": hook_phase, "callable": _callable_name(hook)})
    for route_tag in step.available_routes:
        route = compiled.routes.get(step.name, {}).get(route_tag) or compiled.global_routes.get(route_tag)
        if route is None or route.on_taken is None:
            continue
        locations.append(
            {
                "hook": "on_taken",
                "callable": _callable_name(route.on_taken),
                "route": route_tag,
                "source_step": route.source_step,
            }
        )
    return locations


def _topology_route_payload(
    *,
    compiled: CompiledWorkflow,
    step_name: str | None,
    route_tag: str,
    route: CompiledRoute | None,
) -> dict[str, Any]:
    if route is None:
        return {
            "tag": route_tag,
            "target": None,
            "summary": None,
            "required_writes": [],
            "explicit_required_writes": None,
            "effective_required_writes": [],
            "handoff": None,
            "on_taken": None,
            "provider_visible": True,
            "provider_visible_interactive": True,
            "provider_visible_full_auto": True,
            "is_runtime_control": False,
        }
    return {
        "tag": route_tag,
        "target": route.target,
        "summary": route.summary,
        **route_required_write_payload(
            compiled,
            step_name=step_name,
            route_tag=route_tag,
            route=route,
        ),
        "handoff": route.handoff,
        "on_taken": _callable_name(route.on_taken),
        "provider_visible": route.provider_visible,
        "provider_visible_interactive": route.provider_visible_interactive,
        "provider_visible_full_auto": route.provider_visible_full_auto,
        "is_runtime_control": route.is_runtime_control,
        "source_step": step_name or "GLOBAL",
    }


def _callable_name(value: object | None) -> str | None:
    if value is None:
        return None
    return getattr(value, "__name__", type(value).__name__)


def _json_value(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    qualified_name = getattr(value, "qualified_name", None)
    if isinstance(qualified_name, str) and qualified_name:
        return qualified_name
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name
    return repr(value)


def _route_table_text(compiled: CompiledWorkflow) -> str:
    lines = [
        "# Route Table",
        "",
        "| Step | Route | Kind | Target | Interactive Visible | Full Auto Visible | Explicit Required Writes | Effective Required Writes | Handoff | On Taken |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for step_name, routes in compiled.routes.items():
        for route_tag, route in routes.items():
            route_view = _route_view_payload(
                compiled,
                step_name=step_name,
                route_tag=route_tag,
                route=route,
            )
            lines.append(
                f"| {step_name} | {route_tag} | {route_view['kind']} | {route.target} | "
                f"{str(route.provider_visible_interactive).lower()} | {str(route.provider_visible_full_auto).lower()} | "
                f"{route_view['explicit_required_writes_text']} | {route_view['effective_required_writes_text']} | "
                f"{route.handoff or '-'} | {_callable_name(route.on_taken) or '-'} |"
            )
    for route_tag, route in compiled.global_routes.items():
        route_view = _route_view_payload(
            compiled,
            step_name=None,
            route_tag=route_tag,
            route=route,
        )
        lines.append(
            f"| GLOBAL | {route_tag} | {route_view['kind']} | {route.target} | "
            f"{str(route.provider_visible_interactive).lower()} | {str(route.provider_visible_full_auto).lower()} | "
            f"{route_view['explicit_required_writes_text']} | {route_view['effective_required_writes_text']} | "
            f"{route.handoff or '-'} | {_callable_name(route.on_taken) or '-'} |"
        )
    return "\n".join(lines)


def _topology_mermaid(compiled: CompiledWorkflow) -> str:
    lines = ["flowchart TD"]
    for step_name, routes in compiled.routes.items():
        for route_tag, route in routes.items():
            hook = f" / {_callable_name(route.on_taken)}" if route.on_taken is not None else ""
            visibility = f" [{_mermaid_route_labels(route)}]"
            lines.append(
                f"    {step_name} -- {route_tag}{hook}{visibility} --> {route.target}"
            )
    for route_tag, route in compiled.global_routes.items():
        visibility = f" [{_mermaid_route_labels(route)}]"
        lines.append(f"    GLOBAL -- {route_tag}{visibility} --> {route.target}")
    return "\n".join(lines)


def _compile_report_text(compiled: CompiledWorkflow) -> str:
    hidden_route_count = sum(
        1
        for routes in compiled.routes.values()
        for route in routes.values()
        if not route.provider_visible
    ) + sum(1 for route in compiled.global_routes.values() if not route.provider_visible)
    runtime_control_hooks = [
        f"`{step.name}`: " + ", ".join(
            (
                f"{location['hook']}:{location.get('route', location['callable'])}"
                if location["hook"] == "on_taken"
                else f"{location['hook']}:{location['callable']}"
            )
            for location in _runtime_control_hook_locations(compiled, step)
        )
        for step in compiled.steps.values()
        if _runtime_control_hook_locations(compiled, step)
    ]
    return "\n".join(
        (
            "# Compile Report",
            "",
            f"- workflow: `{compiled.workflow_name}`",
            f"- entry: `{compiled.entry_step_name}`",
            f"- source hash: `{compiled.source_hash}`",
            f"- topology hash: `{compiled.topology_hash}`",
            f"- terminals: `{FINISH}`, `{AWAIT_INPUT}`, `{FAIL}`",
            f"- steps: `{len(compiled.steps)}`",
            f"- routes: `{sum(len(routes) for routes in compiled.routes.values()) + len(compiled.global_routes)}`",
            f"- hidden routes: `{hidden_route_count}`",
            f"- artifacts: `{len(compiled.artifacts_by_qualified_name)}`",
            f"- sessions: `{len(compiled.sessions)}`",
            f"- worklists: `{len(compiled.worklists)}`",
            "",
            "## Step Route Views",
            *(
                _step_route_view_line(step)
                for step in compiled.steps.values()
            ),
            "",
            "## Runtime-Control Hook Locations",
            *(runtime_control_hooks or ("- none",)),
        )
    )


def _route_view_payload(
    compiled: CompiledWorkflow,
    *,
    step_name: str | None,
    route_tag: str,
    route: CompiledRoute,
) -> dict[str, Any]:
    payload = route_required_write_payload(
        compiled,
        step_name=step_name,
        route_tag=route_tag,
        route=route,
    )
    explicit = payload["explicit_required_writes"]
    effective = payload["effective_required_writes"]
    return {
        "kind": "runtime-control" if route.is_runtime_control else "authored",
        "explicit_required_writes_text": "inherit" if explicit is None else ", ".join(explicit) if explicit else "none (explicit)",
        "effective_required_writes_text": ", ".join(effective) if effective else "-",
    }


def _mermaid_route_labels(route: CompiledRoute) -> str:
    labels = ["runtime-control" if route.is_runtime_control else "authored"]
    if route.provider_visible_interactive and route.provider_visible_full_auto:
        labels.append("interactive+full-auto")
    elif route.provider_visible_interactive:
        labels.append("interactive-only")
    else:
        labels.append("hidden")
    return ", ".join(labels)


def _step_route_view_line(step) -> str:
    authored = ", ".join(f"`{route}`" for route in step.authored_routes) or "none"
    runtime_control = ", ".join(f"`{route}`" for route in step.runtime_control_routes) or "none"
    interactive = ", ".join(f"`{route}`" for route in step.provider_visible_routes_interactive) or "none"
    full_auto = ", ".join(f"`{route}`" for route in step.provider_visible_routes_full_auto) or "none"
    return (
        f"- `{step.name}`: authored={authored}; runtime_control={runtime_control}; "
        f"provider_visible_interactive={interactive}; provider_visible_full_auto={full_auto}"
    )


__all__ = [
    "ARTIFACT_CONTRACTS_FILENAME",
    "COMPILE_REPORT_FILENAME",
    "PROMPT_REFS_FILENAME",
    "ROUTE_TABLE_FILENAME",
    "SESSION_CONTRACTS_FILENAME",
    "STATE_CONTRACTS_FILENAME",
    "STATIC_GRAPH_FILENAME",
    "STATIC_GRAPH_SCHEMA",
    "TOPOLOGY_FILENAME",
    "TOPOLOGY_MERMAID_FILENAME",
    "TOPOLOGY_SCHEMA",
    "workflow_static_step_graph_payload",
    "workflow_topology_payload",
    "write_static_step_graph",
    "write_static_step_graph_payload",
    "write_topology_artifacts",
]
