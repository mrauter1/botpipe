"""Runtime-owned static workflow graph persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from core.compiler import CompiledRoute, CompiledWorkflow
from core.primitives import FAIL, FINISH, PAUSE
from core.prompts import Prompt
from core.route_required_writes import route_required_write_payload
from core.schema_registry import WORKFLOW_STATIC_STEP_GRAPH_SCHEMA, WORKFLOW_TOPOLOGY_SCHEMA


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


def workflow_static_step_graph_payload(compiled: CompiledWorkflow) -> dict[str, Any]:
    return {
        "schema": STATIC_GRAPH_SCHEMA,
        "workflow_name": compiled.workflow_name,
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
                "verifier_session_name": step.verifier_session_name,
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
        "terminals": [FINISH, PAUSE, FAIL],
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
                "hooks": {
                    "before": _callable_name(step.before_hook),
                    "after": _callable_name(step.after_hook),
                    "on_route": _callable_name(step.on_route_hook),
                    "before_producer": _callable_name(step.before_producer_hook),
                    "after_producer": _callable_name(step.after_producer_hook),
                    "before_verifier": _callable_name(step.before_verifier_hook),
                    "after_verifier": _callable_name(step.after_verifier_hook),
                },
                "verifier_session_name": step.verifier_session_name,
                "state_model": step.step_state_model.__name__,
                "state_fields": list(step.step_state_fields),
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
                step_name="GLOBAL",
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
                "workflow_name": compiled.workflow_name,
                "source_hash": compiled.source_hash,
                "topology_hash": compiled.topology_hash,
                "steps": {step.name: list(_prompt_references(step)) for step in compiled.steps.values()},
            },
        ),
        STATE_CONTRACTS_FILENAME: _write_json_file(
            run_dir / STATE_CONTRACTS_FILENAME,
            {
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
                    }
                    for step in compiled.steps.values()
                },
            },
        ),
        SESSION_CONTRACTS_FILENAME: _write_json_file(
            run_dir / SESSION_CONTRACTS_FILENAME,
            {
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


def _topology_route_payload(
    *,
    compiled: CompiledWorkflow,
    step_name: str,
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
        "source_step": step_name,
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
        "| Step | Route | Target | Explicit Required Writes | Effective Required Writes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for step_name, routes in compiled.routes.items():
        for route_tag, route in routes.items():
            payload = route_required_write_payload(
                compiled,
                step_name=step_name,
                route_tag=route_tag,
                route=route,
            )
            explicit = payload["explicit_required_writes"]
            explicit_text = "inherit" if explicit is None else ", ".join(explicit) if explicit else "none (explicit)"
            effective = payload["effective_required_writes"]
            effective_text = ", ".join(effective) if effective else "-"
            lines.append(
                f"| {step_name} | {route_tag} | {route.target} | "
                f"{explicit_text} | {effective_text} |"
            )
    return "\n".join(lines)


def _topology_mermaid(compiled: CompiledWorkflow) -> str:
    lines = ["flowchart TD"]
    for step_name, routes in compiled.routes.items():
        for route_tag, route in routes.items():
            hook = f" / {_callable_name(route.on_taken)}" if route.on_taken is not None else ""
            lines.append(
                f"    {step_name} -- {route_tag}{hook} --> {route.target}"
            )
    for route_tag, route in compiled.global_routes.items():
        lines.append(f"    GLOBAL -- {route_tag} --> {route.target}")
    return "\n".join(lines)


def _compile_report_text(compiled: CompiledWorkflow) -> str:
    return "\n".join(
        (
            "# Compile Report",
            "",
            f"- workflow: `{compiled.workflow_name}`",
            f"- entry: `{compiled.entry_step_name}`",
            f"- source hash: `{compiled.source_hash}`",
            f"- topology hash: `{compiled.topology_hash}`",
            f"- steps: `{len(compiled.steps)}`",
            f"- routes: `{sum(len(routes) for routes in compiled.routes.values())}`",
            f"- artifacts: `{len(compiled.artifacts_by_qualified_name)}`",
            f"- sessions: `{len(compiled.sessions)}`",
        )
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
