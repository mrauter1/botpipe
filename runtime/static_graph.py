"""Runtime-owned static workflow graph persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ..core.compiler import CompiledRoute, CompiledWorkflow
from ..core.primitives import FAIL, FINISH, PAUSE
from ..core.prompts import Prompt


STATIC_GRAPH_SCHEMA = "autoloop.workflow_static_step_graph/v1"
STATIC_GRAPH_FILENAME = "static_step_graph.json"

TOPOLOGY_SCHEMA = "autoloop.workflow_topology/v1"
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
                "do_prompt": _prompt_path(step.producer_prompt),
                "review_prompt": _prompt_path(step.verifier_prompt),
                "producer_prompt": _prompt_path(step.producer_prompt),
                "verifier_prompt": _prompt_path(step.verifier_prompt),
                "reads": list(step.reads),
                "requires": list(step.requires),
                "review_requires": list(step.review_requires),
                "produces": list(step.produces),
                "review_writes": list(step.review_writes),
                "writes": list(step.produces),
                "log_artifacts": list(step.log_artifacts),
                "available_routes": list(step.available_routes),
                "review_session_name": step.review_session_name,
                "route_infos": {
                    route_name: {
                        "summary": info.summary,
                        "required_outputs": list(info.required_outputs),
                        "required_writes": list(info.required_outputs),
                        "handoff": info.handoff,
                    }
                    for route_name, info in step.route_infos.items()
                },
                "route_required_outputs": {
                    route_name: list(required_outputs)
                    for route_name, required_outputs in step.route_required_outputs.items()
                },
                "route_required_writes": {
                    route_name: list(required_outputs)
                    for route_name, required_outputs in step.route_required_outputs.items()
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
        "entry_step": compiled.entry_step_name,
        "terminals": {"FINISH": FINISH, "PAUSE": PAUSE, "FAIL": FAIL},
        "steps": [
            {
                "name": step.name,
                "kind": step.kind,
                "do_prompt": _prompt_path(step.producer_prompt),
                "review_prompt": _prompt_path(step.verifier_prompt),
                "producer_prompt": _prompt_path(step.producer_prompt),
                "verifier_prompt": _prompt_path(step.verifier_prompt),
                "reads": list(step.reads),
                "requires": list(step.requires),
                "review_requires": list(step.review_requires),
                "review_writes": list(step.review_writes),
                "writes": list(step.produces),
                "log_artifacts": list(step.log_artifacts),
                "prompt_references": list(_prompt_references(step)),
                "available_routes": list(step.available_routes),
                "hooks": {
                    "before": _callable_name(step.before_hook),
                    "after": _callable_name(step.after_hook),
                    "on_route": _callable_name(step.on_route_hook),
                    "before_do": _callable_name(step.before_do_hook),
                    "after_do": _callable_name(step.after_do_hook),
                    "before_review": _callable_name(step.before_review_hook),
                    "after_review": _callable_name(step.after_review_hook),
                },
                "review_session_name": step.review_session_name,
                "state_fields": list(step.step_state_fields),
                "routes": [
                    _topology_route_payload(
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
            route_tag: _topology_route_payload(step_name="GLOBAL", route_tag=route_tag, route=route)
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
                "state_model": compiled.state_cls.__name__,
                "fields": sorted(getattr(compiled.state_cls, "model_fields", {}).keys()),
                "step_state_fields": {
                    step.name: list(step.step_state_fields)
                    for step in compiled.steps.values()
                    if step.step_state_fields
                },
            },
        ),
        SESSION_CONTRACTS_FILENAME: _write_json_file(
            run_dir / SESSION_CONTRACTS_FILENAME,
            {
                "workflow_name": compiled.workflow_name,
                "source_hash": compiled.source_hash,
                "topology_hash": compiled.topology_hash,
                "default_session": compiled.default_session_name,
                "default_session_open": compiled.default_session_open,
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
    path.write_text(json.dumps(dict(payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
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
    return tuple(getattr(step.step, "simple_prompt_references", ()))


def _topology_route_payload(*, step_name: str, route_tag: str, route: CompiledRoute | None) -> dict[str, Any]:
    if route is None:
        return {
            "tag": route_tag,
            "target": None,
            "summary": None,
            "required_writes": [],
            "handoff": None,
            "on_taken": None,
        }
    return {
        "tag": route_tag,
        "target": _canonical_target(route.target),
        "summary": route.summary,
        "required_writes": list(route.required_outputs),
        "handoff": route.handoff,
        "on_taken": _callable_name(route.on_taken),
        "source_step": step_name,
    }


def _canonical_target(target: str) -> str:
    return FINISH if target == "SUCCESS" else target


def _callable_name(value: object | None) -> str | None:
    if value is None:
        return None
    return getattr(value, "__name__", type(value).__name__)


def _route_table_text(compiled: CompiledWorkflow) -> str:
    lines = ["# Route Table", "", "| Step | Route | Target | Required Writes |", "| --- | --- | --- | --- |"]
    for step_name, routes in compiled.routes.items():
        for route_tag, route in routes.items():
            lines.append(
                f"| {step_name} | {route_tag} | {_canonical_target(route.target)} | "
                f"{', '.join(route.required_outputs) if route.required_outputs else '-'} |"
            )
    return "\n".join(lines)


def _topology_mermaid(compiled: CompiledWorkflow) -> str:
    lines = ["flowchart TD"]
    for step_name, routes in compiled.routes.items():
        for route_tag, route in routes.items():
            hook = f" / {_callable_name(route.on_taken)}" if route.on_taken is not None else ""
            lines.append(
                f"    {step_name} -- {route_tag}{hook} --> {_canonical_target(route.target)}"
            )
    for route_tag, route in compiled.global_routes.items():
        lines.append(f"    GLOBAL -- {route_tag} --> {_canonical_target(route.target)}")
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
