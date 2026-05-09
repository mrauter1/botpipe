from __future__ import annotations

from types import SimpleNamespace

import pytest

from botlane.core.artifacts import Artifact
from botlane.core.compiler import CompiledRoute
from botlane.core.identifiers import ArtifactId
from botlane.core.inventory import ArtifactInventoryRecord
from botlane.core.plan_adapters import compiled_route_from_route_contract, route_contract_from_compiled_route
from botlane.core.primitives import AWAIT_INPUT, FAIL, FINISH
from botlane.core.route_contracts import (
    AwaitInput,
    Continue,
    FailAction,
    Finish,
    available_route_tags,
    provider_visible_route_tags,
    route_action_for_contract,
    runtime_control_route_tags,
)


def _inventory_record(
    *,
    name: str,
    qualified_name: str,
    owner_step: str | None,
    workflow_level: bool,
) -> ArtifactInventoryRecord:
    artifact = Artifact(
        f"{qualified_name}.txt",
        name=name,
        kind="text",
        owner_step=owner_step,
        qualified_name=qualified_name,
    )
    return ArtifactInventoryRecord(
        artifact=artifact,
        name=name,
        qualified_name=qualified_name,
        owner_step=owner_step,
        workflow_level=workflow_level,
        producer_steps=() if owner_step is None else (owner_step,),
    )


def test_route_contract_targets_map_to_internal_route_actions() -> None:
    finish_contract = route_contract_from_compiled_route(
        CompiledRoute(source_step="ask", tag="done", target=FINISH),
    )
    await_input_contract = route_contract_from_compiled_route(
        CompiledRoute(source_step="ask", tag="question", target=AWAIT_INPUT, is_runtime_control=True),
    )
    fail_contract = route_contract_from_compiled_route(
        CompiledRoute(source_step="ask", tag="failed", target=FAIL, is_runtime_control=True),
    )
    continue_contract = route_contract_from_compiled_route(
        CompiledRoute(source_step="ask", tag="repair", target="repair"),
    )
    disabled_contract = route_contract_from_compiled_route(
        CompiledRoute(source_step="ask", tag="blocked", target=None, disabled=True),
    )

    assert finish_contract.target.kind == "finish"
    assert await_input_contract.target.kind == "await_input"
    assert fail_contract.target.kind == "fail"
    assert continue_contract.target.kind == "step"
    assert continue_contract.target.step_name == "repair"
    assert disabled_contract.target.kind == "disabled"

    assert route_action_for_contract(finish_contract) == Finish()
    assert route_action_for_contract(await_input_contract, pending_input={"question": "Need approval"}) == AwaitInput(
        pending_input={"question": "Need approval"}
    )
    assert route_action_for_contract(
        fail_contract,
        reason="runtime failure",
        failure_context={"kind": "runtime_control_validation"},
    ) == FailAction(reason="runtime failure", failure_context={"kind": "runtime_control_validation"})
    assert route_action_for_contract(continue_contract) == Continue(target_step="repair")

    with pytest.raises(ValueError, match="disabled routes do not have a runtime action"):
        route_action_for_contract(disabled_contract)


def test_route_contract_round_trip_preserves_metadata_and_inventory_backed_required_writes() -> None:
    def _on_taken(_ctx) -> None:
        return None

    payload_validator = object()
    route_fields_validator = object()
    draft_record = _inventory_record(
        name="report.v2.json",
        qualified_name="draft.report.v2.json",
        owner_step="draft",
        workflow_level=False,
    )
    workflow_record = _inventory_record(
        name="report.summary",
        qualified_name="report.summary",
        owner_step=None,
        workflow_level=True,
    )
    inventory = {
        draft_record.qualified_name: draft_record,
        workflow_record.qualified_name: workflow_record,
    }
    compiled = CompiledRoute(
        source_step="draft",
        tag="publish",
        target="archive",
        summary="publish the drafted report",
        required_writes=("draft.report.v2.json", "report.summary"),
        handoff="Send the final report",
        on_taken=_on_taken,
        provider_visibility="interactive_only",
        provider_visible=True,
        provider_visible_interactive=True,
        provider_visible_full_auto=False,
        payload_schema_mode="explicit",
        payload_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        payload_validator=payload_validator,
        route_fields_schema={"type": "object", "properties": {"reason": {"type": "string"}}},
        route_fields_validator=route_fields_validator,
        preset_kind="custom",
        inheritance_source="global",
        disabled=False,
        is_runtime_control=False,
        _required_writes_explicit=True,
    )

    contract = route_contract_from_compiled_route(compiled, inventory=inventory)

    assert contract.required_writes.declared == (
        ArtifactId("step", name="report.v2.json", step="draft"),
        ArtifactId("workflow", name="report.summary"),
    )
    assert contract.required_writes.explicit == contract.required_writes.declared
    assert contract.required_writes.effective == contract.required_writes.declared
    assert contract.provider.visibility == "interactive_only"
    assert contract.payload.schema == {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    assert contract.payload.validator is payload_validator
    assert contract.route_fields.schema == {
        "type": "object",
        "properties": {"reason": {"type": "string"}},
    }
    assert contract.route_fields.validator is route_fields_validator

    assert compiled_route_from_route_contract(contract) == compiled


def test_route_contract_preserves_explicit_empty_required_writes_without_inventory() -> None:
    compiled = CompiledRoute(
        source_step="draft",
        tag="done",
        target=FINISH,
        required_writes=(),
        _required_writes_explicit=True,
    )

    contract = route_contract_from_compiled_route(compiled)

    assert contract.required_writes.declared == ()
    assert contract.required_writes.explicit == ()
    assert contract.required_writes.effective == ()
    assert compiled_route_from_route_contract(contract) == compiled


def test_route_contract_requires_inventory_for_non_empty_required_writes() -> None:
    compiled = CompiledRoute(
        source_step="draft",
        tag="done",
        target=FINISH,
        required_writes=("draft.report",),
    )

    with pytest.raises(ValueError, match="route required_writes adaptation requires artifact inventory"):
        route_contract_from_compiled_route(compiled)


def test_route_view_helpers_derive_tags_from_plan_route_tables() -> None:
    ask_routes = {
        "done": route_contract_from_compiled_route(CompiledRoute(source_step="ask", tag="done", target=FINISH)),
        "question": route_contract_from_compiled_route(
            CompiledRoute(
                source_step="ask",
                tag="question",
                target=AWAIT_INPUT,
                provider_visibility="interactive_only",
                provider_visible=True,
                provider_visible_interactive=True,
                provider_visible_full_auto=False,
                is_runtime_control=True,
            )
        ),
        "hidden": route_contract_from_compiled_route(
            CompiledRoute(
                source_step="ask",
                tag="hidden",
                target="repair",
                provider_visibility="hidden",
                provider_visible=False,
                provider_visible_interactive=False,
                provider_visible_full_auto=False,
            )
        ),
        "disabled": route_contract_from_compiled_route(
            CompiledRoute(
                source_step="ask",
                tag="disabled",
                target=None,
                disabled=True,
                provider_visibility="hidden",
                provider_visible=False,
                provider_visible_interactive=False,
                provider_visible_full_auto=False,
            )
        ),
    }
    plan = SimpleNamespace(routes={"ask": ask_routes})

    assert available_route_tags(plan, "ask") == ("done", "question", "hidden")
    assert runtime_control_route_tags(plan, "ask") == ("question",)
    assert provider_visible_route_tags(plan, "ask", mode="interactive") == ("done", "question")
    assert provider_visible_route_tags(plan, "ask", mode="full_auto") == ("done",)
