"""Runtime-owned static workflow graph persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from botlane.core.discovery import get_workflow_definition
from botlane.core.route_contracts import (
    RouteContract,
    available_route_tags,
    provider_visible_route_tags,
    route_target_value,
    runtime_control_route_tags,
)
from botlane.core.route_reporting import (
    payload_contract_for_route,
    provider_response_contract_for_routes,
    route_fields_contract_for_route,
)
from botlane.core.primitives import AWAIT_INPUT, FAIL, FINISH
from botlane.core.prompts import Prompt
from botlane.core.route_required_writes import explicit_route_required_writes, route_required_write_payload
from botlane.core.schema_registry import (
    WORKFLOW_ARTIFACT_CONTRACTS_SCHEMA,
    WORKFLOW_PROMPT_REFS_SCHEMA,
    WORKFLOW_SESSION_CONTRACTS_SCHEMA,
    WORKFLOW_STATE_CONTRACTS_SCHEMA,
    WORKFLOW_STATIC_STEP_GRAPH_SCHEMA,
    WORKFLOW_TOPOLOGY_SCHEMA,
)
from botlane.core.step_state import built_in_step_state_model
from botlane.core.step_plans import StepPlan
from botlane.core.workflow_plan import WorkflowPlan
from botlane.core.lowering import step_authored_route_tags


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


def workflow_static_step_graph_payload(compiled: WorkflowPlan) -> dict[str, Any]:
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
                "reads": [_json_value(value) for value in step.reads],
                "requires": [_json_value(value) for value in step.requires],
                "producer_reads": [_json_value(value) for value in step.producer_reads],
                "producer_requires": [_json_value(value) for value in step.producer_requires],
                "producer_writes": [_json_value(value) for value in step.producer_writes],
                "verifier_reads": [_json_value(value) for value in step.verifier_reads],
                "verifier_requires": [_json_value(value) for value in step.verifier_requires],
                "verifier_writes": [_json_value(value) for value in step.verifier_writes],
                "writes": [_json_value(value) for value in step.writes],
                "log_artifacts": [_json_value(value) for value in step.log_artifacts],
                "available_routes": list(available_route_tags(compiled, step.name)),
                "authored_routes": list(_authored_route_tags(compiled, step)),
                "compiled_route_tags": list(_compiled_route_tags(compiled, step)),
                "suppressed_route_tags": list(_suppressed_route_tags(compiled, step)),
                "runtime_control_routes": list(runtime_control_route_tags(compiled, step.name)),
                "provider_visible_routes_interactive": list(provider_visible_route_tags(compiled, step.name, mode="interactive")),
                "provider_visible_routes_full_auto": list(provider_visible_route_tags(compiled, step.name, mode="full_auto")),
                "provider_response_contracts": _provider_response_contracts(compiled, step),
                "verifier_session_name": step.verifier_session_name,
                "state_surface": _step_state_surface_payload(step),
                "step_item_state_model": step.step_item_state_model.__name__ if step.step_item_state_model is not None else None,
                "step_item_state_fields": list(step.step_item_state_fields),
                "step_item_state_surface": _step_item_state_surface_payload(step),
                "route_hook_locations": _route_hook_locations(compiled, step),
                "runtime_control_hook_locations": _route_hook_locations(compiled, step),
                "routes": {
                    route_name: _topology_route_payload(
                        compiled=compiled,
                        step_name=step.name,
                        route_tag=route_name,
                        route=compiled.routes.get(step.name, {}).get(route_name) or compiled.global_routes.get(route_name),
                        expected_output_schema=step.expected_output_schema,
                    )
                    for route_name in available_route_tags(compiled, step.name)
                },
                "compiled_routes": {
                    route_name: _topology_route_payload(
                        compiled=compiled,
                        step_name=step.name,
                        route_tag=route_name,
                        route=compiled.routes.get(step.name, {}).get(route_name),
                        expected_output_schema=step.expected_output_schema,
                        available=route_name in available_route_tags(compiled, step.name),
                    )
                    for route_name in _compiled_route_tags(compiled, step)
                },
                "prompt_references": list(_prompt_references(compiled, step)),
                "has_expected_output_schema": step.expected_output_schema is not None,
                **(
                    {"branch_group": _branch_group_surface_payload(compiled, step.branch_group, route_shape="mapping")}
                    if step.branch_group is not None
                    else {}
                ),
            }
            for step in compiled.steps.values()
        ],
        "transitions": {
            "steps": {
                step_name: {
                    route_tag: route_target_value(compiled_route.target)
                    for route_tag, compiled_route in routes.items()
                }
                for step_name, routes in compiled.routes.items()
            },
            "global": {
                route_tag: route_target_value(compiled_route.target)
                for route_tag, compiled_route in compiled.global_routes.items()
            },
        },
    }


def workflow_topology_payload(compiled: WorkflowPlan) -> dict[str, Any]:
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
                "reads": [_json_value(value) for value in step.reads],
                "requires": [_json_value(value) for value in step.requires],
                "producer_reads": [_json_value(value) for value in step.producer_reads],
                "producer_requires": [_json_value(value) for value in step.producer_requires],
                "producer_writes": [_json_value(value) for value in step.producer_writes],
                "verifier_reads": [_json_value(value) for value in step.verifier_reads],
                "verifier_requires": [_json_value(value) for value in step.verifier_requires],
                "verifier_writes": [_json_value(value) for value in step.verifier_writes],
                "writes": [_json_value(value) for value in step.writes],
                "log_artifacts": [_json_value(value) for value in step.log_artifacts],
                "prompt_references": list(_prompt_references(compiled, step)),
                "available_routes": list(available_route_tags(compiled, step.name)),
                "authored_routes": list(_authored_route_tags(compiled, step)),
                "compiled_route_tags": list(_compiled_route_tags(compiled, step)),
                "suppressed_route_tags": list(_suppressed_route_tags(compiled, step)),
                "hooks": {
                    "before": _callable_name(step.before_hook),
                    "after": _callable_name(step.after_hook),
                    "before_producer": _callable_name(step.before_producer_hook),
                    "after_producer": _callable_name(step.after_producer_hook),
                    "before_verifier": _callable_name(step.before_verifier_hook),
                    "after_verifier": _callable_name(step.after_verifier_hook),
                },
                "provider_visible_routes_interactive": list(provider_visible_route_tags(compiled, step.name, mode="interactive")),
                "provider_visible_routes_full_auto": list(provider_visible_route_tags(compiled, step.name, mode="full_auto")),
                "provider_response_contracts": _provider_response_contracts(compiled, step),
                "verifier_session_name": step.verifier_session_name,
                "runtime_control_routes": list(runtime_control_route_tags(compiled, step.name)),
                "state_model": step.step_state_model.__name__,
                "state_fields": list(step.step_state_fields),
                "state_surface": _step_state_surface_payload(step),
                "step_item_state_model": step.step_item_state_model.__name__ if step.step_item_state_model is not None else None,
                "step_item_state_fields": list(step.step_item_state_fields),
                "step_item_state_surface": _step_item_state_surface_payload(step),
                "route_hook_locations": _route_hook_locations(compiled, step),
                "runtime_control_hook_locations": _route_hook_locations(compiled, step),
                "routes": [
                    _topology_route_payload(
                        compiled=compiled,
                        step_name=step.name,
                        route_tag=route_tag,
                        route=compiled.routes.get(step.name, {}).get(route_tag) or compiled.global_routes.get(route_tag),
                        expected_output_schema=step.expected_output_schema,
                    )
                    for route_tag in available_route_tags(compiled, step.name)
                ],
                "compiled_routes": [
                    _topology_route_payload(
                        compiled=compiled,
                        step_name=step.name,
                        route_tag=route_tag,
                        route=compiled.routes.get(step.name, {}).get(route_tag),
                        expected_output_schema=step.expected_output_schema,
                        available=route_tag in available_route_tags(compiled, step.name),
                    )
                    for route_tag in _compiled_route_tags(compiled, step)
                ],
                **(
                    {"branch_group": _branch_group_surface_payload(compiled, step.branch_group, route_shape="list")}
                    if step.branch_group is not None
                    else {}
                ),
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


def write_static_step_graph(run_dir: Path, compiled: WorkflowPlan) -> Path:
    return write_static_step_graph_payload(run_dir, workflow_static_step_graph_payload(compiled))


def write_topology_artifacts(run_dir: Path, compiled: WorkflowPlan) -> dict[str, Path]:
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
                        "kind": compiled.artifact_spec(artifact_id).kind,
                        "required": compiled.artifact_spec(artifact_id).required,
                        "owner_step": compiled.artifact_spec(artifact_id).owner_step,
                        "producer_steps": list(compiled.artifact_spec(artifact_id).producer_steps),
                    }
                    for name, artifact_id in compiled.artifacts_by_qualified_name.items()
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
                "steps": {step.name: list(_prompt_references(compiled, step)) for step in compiled.steps.values()},
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


def _prompt_references(compiled: WorkflowPlan, step: StepPlan) -> tuple[str, ...]:
    return tuple(ref.raw for ref in compiled.reference_graph.prompt_refs.get(step.name, ()))


def _workflow_state_surface_payload(compiled: WorkflowPlan) -> dict[str, Any]:
    return {
        "model": compiled.state_cls.__name__,
        "fields": sorted(getattr(compiled.state_cls, "model_fields", {}).keys()),
    }


def _workflow_params_surface_payload(compiled: WorkflowPlan) -> dict[str, Any] | None:
    if compiled.parameters_cls is None:
        return None
    return {
        "model": compiled.parameters_cls.__name__,
        "fields": sorted(getattr(compiled.parameters_cls, "model_fields", {}).keys()),
    }


def _branch_group_surface_payload(
    compiled: WorkflowPlan,
    spec: Any,
    *,
    route_shape: str,
) -> dict[str, Any]:
    return {
        "name": spec.name,
        "kind": spec.kind,
        "branch_count": len(spec.branches),
        "concurrency": spec.concurrency,
        "settle": spec.settle,
        "success_routes": list(spec.success_routes),
        "outcome_policy": _branch_group_outcome_payload(spec.outcome),
        "exposed_routes": list(spec.composite_route_tags),
        "has_fan_in": spec.fan_in_step is not None,
        "default_chain_route": spec.default_chain_route,
        "rework_chain_route": spec.rework_chain_route,
        "branches": [
            {
                "name": branch.name,
                "index": branch.index,
                "input": branch.input,
                "step": _internal_step_surface_payload(
                    compiled,
                    branch.step,
                    route_shape=route_shape,
                ),
            }
            for branch in spec.branches
        ],
        "fan_in_step": None
        if spec.fan_in_step is None
        else _internal_step_surface_payload(
            compiled,
            spec.fan_in_step,
            route_shape=route_shape,
        ),
    }


def _branch_group_outcome_payload(outcome: object) -> str | None:
    if outcome is None:
        return None
    if isinstance(outcome, str):
        return outcome
    return _callable_name(outcome) or type(outcome).__name__


def _internal_step_surface_payload(
    compiled: WorkflowPlan,
    step: StepPlan,
    *,
    route_shape: str,
) -> dict[str, Any]:
    route_table = dict(compiled.routes.get(step.name, {}))
    available_routes = available_route_tags(compiled, step.name)
    routes: dict[str, Any] | list[dict[str, Any]]
    if route_shape == "mapping":
        routes = {
            route_name: _internal_route_payload(
                compiled=compiled,
                step=step,
                route_tag=route_name,
                route=route_table.get(route_name),
                available=route_name in available_routes,
            )
            for route_name in available_routes
        }
    elif route_shape == "list":
        routes = [
            _internal_route_payload(
                compiled=compiled,
                step=step,
                route_tag=route_name,
                route=route_table.get(route_name),
                available=route_name in available_routes,
            )
            for route_name in available_routes
        ]
    else:
        raise ValueError(f"unsupported route shape {route_shape!r}")
    return {
        "name": step.name,
        "kind": step.kind,
        "scope_name": step.scope_name,
        "session_name": step.session_name,
        "prompt": _prompt_path(step.prompt),
        "producer_prompt": _prompt_path(step.producer_prompt),
        "verifier_prompt": _prompt_path(step.verifier_prompt),
        "reads": [_json_value(value) for value in step.reads],
        "requires": [_json_value(value) for value in step.requires],
        "producer_reads": [_json_value(value) for value in step.producer_reads],
        "producer_requires": [_json_value(value) for value in step.producer_requires],
        "producer_writes": [_json_value(value) for value in step.producer_writes],
        "verifier_reads": [_json_value(value) for value in step.verifier_reads],
        "verifier_requires": [_json_value(value) for value in step.verifier_requires],
        "verifier_writes": [_json_value(value) for value in step.verifier_writes],
        "writes": [_json_value(value) for value in step.writes],
        "log_artifacts": [_json_value(value) for value in step.log_artifacts],
        "available_routes": list(available_routes),
        "authored_routes": list(_authored_route_tags(compiled, step)),
        "compiled_route_tags": list(_compiled_route_tags(compiled, step)),
        "suppressed_route_tags": list(_suppressed_route_tags(compiled, step)),
        "runtime_control_routes": list(runtime_control_route_tags(compiled, step.name)),
        "provider_visible_routes_interactive": list(provider_visible_route_tags(compiled, step.name, mode="interactive")),
        "provider_visible_routes_full_auto": list(provider_visible_route_tags(compiled, step.name, mode="full_auto")),
        "provider_response_contracts": _provider_response_contracts(compiled, step),
        "verifier_session_name": step.verifier_session_name,
        "hooks": {
            "before": _callable_name(step.before_hook),
            "after": _callable_name(step.after_hook),
            "before_producer": _callable_name(step.before_producer_hook),
            "after_producer": _callable_name(step.after_producer_hook),
            "before_verifier": _callable_name(step.before_verifier_hook),
            "after_verifier": _callable_name(step.after_verifier_hook),
        },
        "state_model": step.step_state_model.__name__,
        "state_fields": list(step.step_state_fields),
        "state_surface": _step_state_surface_payload(step),
        "step_item_state_model": step.step_item_state_model.__name__ if step.step_item_state_model is not None else None,
        "step_item_state_fields": list(step.step_item_state_fields),
        "step_item_state_surface": _step_item_state_surface_payload(step),
        "route_hook_locations": _route_hook_locations(compiled, step),
        "runtime_control_hook_locations": _route_hook_locations(compiled, step),
        "routes": routes,
        "compiled_routes": (
            {
                route_name: _internal_route_payload(
                    compiled=compiled,
                    step=step,
                    route_tag=route_name,
                    route=route_table.get(route_name),
                    available=route_name in available_routes,
                )
                for route_name in _compiled_route_tags(compiled, step)
            }
            if route_shape == "mapping"
            else [
                _internal_route_payload(
                    compiled=compiled,
                    step=step,
                    route_tag=route_name,
                    route=route_table.get(route_name),
                    available=route_name in available_routes,
                )
                for route_name in _compiled_route_tags(compiled, step)
            ]
        ),
        "prompt_references": list(_prompt_references(compiled, step)),
        "has_expected_output_schema": step.expected_output_schema is not None,
    }


def _internal_route_payload(
    *,
    compiled: WorkflowPlan,
    step: StepPlan,
    route_tag: str,
    route: RouteContract | None,
    available: bool = True,
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
            "available": available,
            "suppressed": not available,
        }
    explicit_required_writes = explicit_route_required_writes(route)
    if explicit_required_writes is None:
        effective_required_writes = [
            artifact_id.qualified_name
            for artifact_id in step.writes
            if compiled.artifact_spec(artifact_id).required
        ]
    else:
        effective_required_writes = list(explicit_required_writes)
    payload_contract = payload_contract_for_route(route, expected_output_schema=step.expected_output_schema)
    route_fields_contract = route_fields_contract_for_route(route)
    return {
        "tag": route_tag,
        "target": route_target_value(route.target),
        "summary": route.summary,
        "required_writes": list(
            artifact_id.qualified_name for artifact_id in route.required_writes.declared
        ),
        "explicit_required_writes": None if explicit_required_writes is None else list(explicit_required_writes),
        "effective_required_writes": effective_required_writes,
        "handoff": route.handoff,
        "on_taken": _callable_name(route.on_taken),
        "provider_visibility": route.provider_visibility,
        "provider_visible": route.provider_visible,
        "provider_visible_interactive": route.provider_visible_interactive,
        "provider_visible_full_auto": route.provider_visible_full_auto,
        "payload_schema_mode": route.payload_schema_mode,
        "payload_contract": payload_contract,
        "payload_schema": payload_contract["schema"],
        "payload_schema_source": payload_contract["source"],
        "payload_schema_name": payload_contract["name"],
        "payload_schema_fingerprint": payload_contract["fingerprint"],
        "route_fields_schema": route.route_fields_schema,
        "route_fields_contract": route_fields_contract,
        "route_fields_schema_effective": route_fields_contract["schema"],
        "route_fields_schema_source": route_fields_contract["source"],
        "route_fields_schema_name": route_fields_contract["name"],
        "route_fields_schema_fingerprint": route_fields_contract["fingerprint"],
        "preset_kind": route.preset_kind,
        "inheritance_source": route.inheritance_source,
        "disabled": route.disabled,
        "available": available and not route.disabled,
        "suppressed": route.disabled,
        "is_runtime_control": route.is_runtime_control,
        "source_step": step.name,
    }


def _worklist_surfaces_payload(compiled: WorkflowPlan) -> dict[str, dict[str, Any]]:
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


def _authored_route_tags(compiled: WorkflowPlan, step: StepPlan) -> tuple[str, ...]:
    definition = get_workflow_definition(compiled.workflow_cls)
    authored_step = next((candidate for candidate in definition.steps if candidate.name == step.name), None)
    if authored_step is None:
        return available_route_tags(compiled, step.name)
    return step_authored_route_tags(definition, authored_step)


def _compiled_route_tags(compiled: WorkflowPlan, step: StepPlan) -> tuple[str, ...]:
    route_table = compiled.routes.get(step.name, {})
    return tuple(route_table.keys())


def _suppressed_route_tags(compiled: WorkflowPlan, step: StepPlan) -> tuple[str, ...]:
    route_table = compiled.routes.get(step.name, {})
    return tuple(tag for tag, route in route_table.items() if route.disabled)


def _provider_route_map(compiled: WorkflowPlan, step: StepPlan, *, policy: str) -> dict[str, RouteContract]:
    visible_tags = provider_visible_route_tags(compiled, step.name, mode="interactive" if policy == "interactive" else "full_auto")
    route_table = compiled.routes.get(step.name, {})
    return {
        route_tag: route_table[route_tag]
        for route_tag in visible_tags
        if route_tag in route_table and not route_table[route_tag].disabled
    }


def _provider_response_contracts(compiled: WorkflowPlan, step: StepPlan) -> dict[str, Any]:
    route_table = compiled.routes.get(step.name, {})
    if not route_table:
        return {
            "interactive": {"route_tags": [], "schema_simplified": False, "schema_fingerprint": None, "schema_chars": 0},
            "full_auto": {"route_tags": [], "schema_simplified": False, "schema_fingerprint": None, "schema_chars": 0},
        }
    return {
        "interactive": provider_response_contract_for_routes(
            routes=_provider_route_map(compiled, step, policy="interactive"),
            expected_output_schema=step.expected_output_schema,
        ),
        "full_auto": provider_response_contract_for_routes(
            routes=_provider_route_map(compiled, step, policy="full_auto"),
            expected_output_schema=step.expected_output_schema,
        ),
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


def _route_hook_locations(compiled: WorkflowPlan, step: StepPlan) -> list[dict[str, Any]]:
    locations: list[dict[str, Any]] = []
    route_table = dict(compiled.routes.get(step.name, {}))
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
    for route_tag in available_route_tags(compiled, step.name):
        route = route_table.get(route_tag) or compiled.global_routes.get(route_tag)
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
    compiled: WorkflowPlan,
    step_name: str | None,
    route_tag: str,
    route: RouteContract | None,
    expected_output_schema: Mapping[str, Any] | None = None,
    available: bool = True,
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
            "available": available,
            "suppressed": not available,
        }
    payload_contract = payload_contract_for_route(route, expected_output_schema=expected_output_schema)
    route_fields_contract = route_fields_contract_for_route(route)
    return {
        "tag": route_tag,
        "target": route_target_value(route.target),
        "summary": route.summary,
        **route_required_write_payload(
            compiled,
            step_name=step_name,
            route_tag=route_tag,
            route=route,
        ),
        "handoff": route.handoff,
        "on_taken": _callable_name(route.on_taken),
        "provider_visibility": route.provider_visibility,
        "provider_visible": route.provider_visible,
        "provider_visible_interactive": route.provider_visible_interactive,
        "provider_visible_full_auto": route.provider_visible_full_auto,
        "payload_schema_mode": route.payload_schema_mode,
        "payload_contract": payload_contract,
        "payload_schema": payload_contract["schema"],
        "payload_schema_source": payload_contract["source"],
        "payload_schema_name": payload_contract["name"],
        "payload_schema_fingerprint": payload_contract["fingerprint"],
        "route_fields_schema": route.route_fields_schema,
        "route_fields_contract": route_fields_contract,
        "route_fields_schema_effective": route_fields_contract["schema"],
        "route_fields_schema_source": route_fields_contract["source"],
        "route_fields_schema_name": route_fields_contract["name"],
        "route_fields_schema_fingerprint": route_fields_contract["fingerprint"],
        "preset_kind": route.preset_kind,
        "inheritance_source": route.inheritance_source,
        "disabled": route.disabled,
        "available": available and not route.disabled,
        "suppressed": route.disabled,
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


def _route_table_text(compiled: WorkflowPlan) -> str:
    lines = [
        "# Route Table",
        "",
        "| Step | Route | Preset | Source | Target | Visibility | State | Payload Schema | Route Fields Schema | Explicit Required Writes | Effective Required Writes | Handoff | On Taken |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for step_name, routes in compiled.routes.items():
        expected_output_schema = compiled.steps[step_name].expected_output_schema if step_name in compiled.steps else None
        for route_tag, route in routes.items():
            route_view = _route_view_payload(
                compiled,
                step_name=step_name,
                route_tag=route_tag,
                route=route,
                expected_output_schema=expected_output_schema,
            )
            lines.append(
                f"| {step_name} | {route_tag} | {route_view['preset']} | {route_view['source']} | {route_target_value(route.target)} | "
                f"{route_view['visibility']} | {route_view['state']} | "
                f"{route_view['payload_schema_text']} | {route_view['route_fields_schema_text']} | "
                f"{route_view['explicit_required_writes_text']} | {route_view['effective_required_writes_text']} | "
                f"{route.handoff or '-'} | {_callable_name(route.on_taken) or '-'} |"
            )
    for route_tag, route in compiled.global_routes.items():
        route_view = _route_view_payload(
            compiled,
            step_name=None,
            route_tag=route_tag,
            route=route,
            expected_output_schema=None,
        )
        lines.append(
            f"| GLOBAL | {route_tag} | {route_view['preset']} | {route_view['source']} | {route_target_value(route.target)} | "
            f"{route_view['visibility']} | {route_view['state']} | "
            f"{route_view['payload_schema_text']} | {route_view['route_fields_schema_text']} | "
            f"{route_view['explicit_required_writes_text']} | {route_view['effective_required_writes_text']} | "
            f"{route.handoff or '-'} | {_callable_name(route.on_taken) or '-'} |"
        )
    return "\n".join(lines)


def _topology_mermaid(compiled: WorkflowPlan) -> str:
    lines = ["flowchart TD"]
    for step_name, routes in compiled.routes.items():
        for route_tag, route in routes.items():
            hook = f" / {_callable_name(route.on_taken)}" if route.on_taken is not None else ""
            visibility = f" [{_mermaid_route_labels(route)}]"
            lines.append(
                f"    {step_name} -- {route_tag}{hook}{visibility} --> {route_target_value(route.target)}"
            )
    for route_tag, route in compiled.global_routes.items():
        visibility = f" [{_mermaid_route_labels(route)}]"
        lines.append(f"    GLOBAL -- {route_tag}{visibility} --> {route_target_value(route.target)}")
    return "\n".join(lines)


def _compile_report_text(compiled: WorkflowPlan) -> str:
    hidden_route_count = sum(
        1
        for routes in compiled.routes.values()
        for route in routes.values()
        if route.inheritance_source != "global" and not route.provider_visible
    ) + sum(1 for route in compiled.global_routes.values() if not route.provider_visible)
    suppressed_route_count = sum(
        1
        for routes in compiled.routes.values()
        for route in routes.values()
        if route.inheritance_source != "global" and route.disabled
    ) + sum(1 for route in compiled.global_routes.values() if route.disabled)
    declared_route_count = sum(
        1
        for routes in compiled.routes.values()
        for route in routes.values()
        if route.inheritance_source != "global"
    ) + len(compiled.global_routes)
    route_hooks = [
        f"`{step.name}`: " + ", ".join(
            (
                f"{location['hook']}:{location.get('route', location['callable'])}"
                if location["hook"] == "on_taken"
                else f"{location['hook']}:{location['callable']}"
            )
            for location in _route_hook_locations(compiled, step)
        )
        for step in compiled.steps.values()
        if _route_hook_locations(compiled, step)
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
            f"- routes: `{declared_route_count}`",
            f"- hidden routes: `{hidden_route_count}`",
            f"- suppressed routes: `{suppressed_route_count}`",
            f"- artifacts: `{len(compiled.artifacts_by_qualified_name)}`",
            f"- sessions: `{len(compiled.sessions)}`",
            f"- worklists: `{len(compiled.worklists)}`",
            "",
            "## Step Route Views",
            *(_step_route_view_line(compiled, step) for step in compiled.steps.values()),
            "",
            "## Route Contracts",
            *(
                _route_contract_line(compiled, step_name, route_tag, route)
                for step_name, routes in compiled.routes.items()
                for route_tag, route in routes.items()
            ),
            *(
                _route_contract_line(compiled, None, route_tag, route)
                for route_tag, route in compiled.global_routes.items()
            ),
            "",
            "## Route Hook Locations",
            *(route_hooks or ("- none",)),
        )
    )


def _route_view_payload(
    compiled: WorkflowPlan,
    *,
    step_name: str | None,
    route_tag: str,
    route: RouteContract,
    expected_output_schema: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload = route_required_write_payload(
        compiled,
        step_name=step_name,
        route_tag=route_tag,
        route=route,
    )
    explicit = payload["explicit_required_writes"]
    effective = payload["effective_required_writes"]
    payload_contract = payload_contract_for_route(route, expected_output_schema=expected_output_schema)
    route_fields_contract = route_fields_contract_for_route(route)
    return {
        "preset": route.preset_kind,
        "source": route.inheritance_source,
        "visibility": route.provider_visibility,
        "state": "suppressed" if route.disabled else "available",
        "payload_schema_text": _schema_contract_text(payload_contract["source"], payload_contract["name"], payload_contract["fingerprint"]),
        "route_fields_schema_text": _schema_contract_text(
            route_fields_contract["source"],
            route_fields_contract["name"],
            route_fields_contract["fingerprint"],
        ),
        "explicit_required_writes_text": "inherit" if explicit is None else ", ".join(explicit) if explicit else "none (explicit)",
        "effective_required_writes_text": ", ".join(effective) if effective else "-",
    }


def _mermaid_route_labels(route: RouteContract) -> str:
    labels = [route.preset_kind, route.inheritance_source, route.provider_visibility]
    if route.disabled:
        labels.append("suppressed")
    return ", ".join(labels)


def _step_route_view_line(compiled: WorkflowPlan, step: StepPlan) -> str:
    authored = ", ".join(f"`{route}`" for route in _authored_route_tags(compiled, step)) or "none"
    runtime_control = ", ".join(f"`{route}`" for route in runtime_control_route_tags(compiled, step.name)) or "none"
    interactive = ", ".join(f"`{route}`" for route in provider_visible_route_tags(compiled, step.name, mode="interactive")) or "none"
    full_auto = ", ".join(f"`{route}`" for route in provider_visible_route_tags(compiled, step.name, mode="full_auto")) or "none"
    compiled_routes = ", ".join(f"`{route}`" for route in _compiled_route_tags(compiled, step)) or "none"
    suppressed = ", ".join(f"`{route}`" for route in _suppressed_route_tags(compiled, step)) or "none"
    provider_contracts = _provider_response_contracts(compiled, step)
    return (
        f"- `{step.name}`: compiled={compiled_routes}; available={', '.join(f'`{route}`' for route in available_route_tags(compiled, step.name)) or 'none'}; "
        f"suppressed={suppressed}; provider_visible_interactive={interactive}; provider_visible_full_auto={full_auto}; "
        f"provider_schema_fallback(interactive/full_auto)=`{provider_contracts['interactive']['schema_simplified']}`/`{provider_contracts['full_auto']['schema_simplified']}`; "
        f"legacy_authored={authored}; legacy_runtime_control={runtime_control}"
    )


def _route_contract_line(
    compiled: WorkflowPlan,
    step_name: str | None,
    route_tag: str,
    route: RouteContract,
) -> str:
    expected_output_schema = None if step_name is None else compiled.steps[step_name].expected_output_schema
    route_view = _route_view_payload(
        compiled,
        step_name=step_name,
        route_tag=route_tag,
        route=route,
        expected_output_schema=expected_output_schema,
    )
    scope = step_name or "GLOBAL"
    return (
        f"- `{scope}.{route_tag}`: preset=`{route_view['preset']}`, source=`{route_view['source']}`, "
        f"visibility=`{route_view['visibility']}`, state=`{route_view['state']}`, "
        f"payload={route_view['payload_schema_text']}, route_fields={route_view['route_fields_schema_text']}, "
        f"target=`{route_target_value(route.target)}`"
    )


def _schema_contract_text(source: str, name: str | None, fingerprint: str | None) -> str:
    label = name or "anonymous"
    suffix = fingerprint[:12] if isinstance(fingerprint, str) else "none"
    return f"{source}:{label}#{suffix}"


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
