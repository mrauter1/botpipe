"""Runtime-owned static workflow graph persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ..core.compiler import CompiledWorkflow
from ..core.prompts import Prompt


STATIC_GRAPH_SCHEMA = "autoloop.workflow_static_step_graph/v1"
STATIC_GRAPH_FILENAME = "static_step_graph.json"


def workflow_static_step_graph_payload(compiled: CompiledWorkflow) -> dict[str, Any]:
    return {
        "schema": STATIC_GRAPH_SCHEMA,
        "workflow_name": compiled.workflow_name,
        "steps": [
            {
                "name": step.name,
                "kind": step.kind,
                "producer_prompt": _prompt_path(step.producer_prompt),
                "verifier_prompt": _prompt_path(step.verifier_prompt),
                "reads": list(step.reads),
                "requires": list(step.requires),
                "produces": list(step.produces),
                "log_artifacts": list(step.log_artifacts),
                "available_routes": list(step.available_routes),
                "route_infos": {
                    route_name: {
                        "summary": info.summary,
                        "required_outputs": list(info.required_outputs),
                        "handoff": info.handoff,
                    }
                    for route_name, info in step.route_infos.items()
                },
                "route_required_outputs": {
                    route_name: list(required_outputs)
                    for route_name, required_outputs in step.route_required_outputs.items()
                },
                "route_contracts": {
                    route_name: dict(contract)
                    for route_name, contract in step.route_contracts.items()
                },
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


def write_static_step_graph(run_dir: Path, compiled: CompiledWorkflow) -> Path:
    return write_static_step_graph_payload(run_dir, workflow_static_step_graph_payload(compiled))


def write_static_step_graph_payload(run_dir: Path, payload: dict[str, Any] | Mapping[str, Any]) -> Path:
    output_path = run_dir / STATIC_GRAPH_FILENAME
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dict(payload), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output_path


def _prompt_path(prompt: str | Prompt | None) -> str | None:
    if prompt is None:
        return None
    if isinstance(prompt, Prompt):
        return prompt.path
    return prompt
