from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import BaseModel

from botlane.core.artifacts import resolve_artifact_template
from botlane.core.context import Context
from botlane.core.errors import WorkflowExecutionError, WorkflowValidationError
from botlane.core.identifiers import ArtifactId
from botlane.core.placeholders import (
    PlaceholderRef,
    parse_placeholders,
    render_placeholder_ref,
    render_template_with_refs,
    validate_placeholder_ref,
)
from botlane.core.reference_graph import ReferenceGraph
from botlane.core.stores import InMemorySessionStore


class _State(BaseModel):
    status: str = "draft"


class _Params(BaseModel):
    mode: str = "brief"


class _Input(BaseModel):
    topic: str


def _simple_prompt_symbols(**overrides: object) -> dict[str, object]:
    symbols: dict[str, object] = {
        "kind": "simple_prompt",
        "step_name": "review",
        "own_outputs": frozenset({"draft"}),
        "state_fields": frozenset({"status"}),
        "parameter_fields": frozenset({"mode"}),
        "input_fields": frozenset({"topic"}),
        "scope_name": "gate",
        "worklist_item_state_fields": {"gate": frozenset({"priority"})},
        "step_state_fields": {"review": frozenset({"approved"})},
        "step_item_state_fields": {"review": frozenset({"priority"})},
        "step_output_names": {"review": frozenset({"draft"}), "previous_step": frozenset({"report"})},
        "artifact_name_counts": {"draft": 1, "report": 1},
        "allow_branch_placeholders": False,
        "allow_fan_in_placeholders": False,
    }
    symbols.update(overrides)
    return symbols


def _build_context(tmp_path: Path) -> Context:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)
    (task_folder / "request.md").write_text("Task request\n", encoding="utf-8")
    (run_folder / "request.md").write_text("Ship it.\n", encoding="utf-8")
    return Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_State(),
        params=_Params(),
        workflow_input=_Input(topic="release"),
        session_store=InMemorySessionStore(),
    )


def test_parse_placeholders_extracts_refs_exactly() -> None:
    refs = parse_placeholders(
        "Echo {ctx.message} / {input.topic} / {worklist.gate.current.payload.status}",
        source="prompt",
    )

    assert refs == (
        PlaceholderRef(raw="ctx.message", root="ctx", path=("message",), source="prompt"),
        PlaceholderRef(raw="input.topic", root="input", path=("topic",), source="prompt"),
        PlaceholderRef(
            raw="worklist.gate.current.payload.status",
            root="worklist",
            path=("gate", "current", "payload", "status"),
            source="prompt",
        ),
    )


def test_validate_placeholder_ref_preserves_known_simple_prompt_surfaces() -> None:
    symbols = _simple_prompt_symbols()

    assert validate_placeholder_ref(
        parse_placeholders("{ctx.message}", source="prompt")[0],
        surface="simple step 'review' prompt placeholder",
        symbols=symbols,
    ) is None
    assert validate_placeholder_ref(
        parse_placeholders("{input.topic}", source="prompt")[0],
        surface="simple step 'review' prompt placeholder",
        symbols=symbols,
    ) is None
    assert validate_placeholder_ref(
        parse_placeholders("{params.mode}", source="prompt")[0],
        surface="simple step 'review' prompt placeholder",
        symbols=symbols,
    ) is None
    assert validate_placeholder_ref(
        parse_placeholders("{state.status}", source="prompt")[0],
        surface="simple step 'review' prompt placeholder",
        symbols=symbols,
    ) is None
    assert validate_placeholder_ref(
        parse_placeholders("{worklist.gate.current.payload.status}", source="prompt")[0],
        surface="simple step 'review' prompt placeholder",
        symbols=symbols,
    ) is None
    assert (
        validate_placeholder_ref(
            parse_placeholders("{previous_step.report}", source="prompt")[0],
            surface="simple step 'review' prompt placeholder",
            symbols=symbols,
        )
        == "previous_step.report"
    )


def test_validate_placeholder_ref_preserves_branch_and_fan_in_placement_rules() -> None:
    branch_ref = parse_placeholders("{branch.name}", source="prompt")[0]
    fan_in_ref = parse_placeholders("{fan_in.context_text}", source="prompt")[0]

    with pytest.raises(WorkflowValidationError, match="only valid inside branch steps"):
        validate_placeholder_ref(
            branch_ref,
            surface="simple step 'review' prompt placeholder",
            symbols=_simple_prompt_symbols(),
        )
    with pytest.raises(WorkflowValidationError, match="only valid inside fan-in steps"):
        validate_placeholder_ref(
            fan_in_ref,
            surface="simple step 'review' prompt placeholder",
            symbols=_simple_prompt_symbols(),
        )

    assert (
        validate_placeholder_ref(
            branch_ref,
            surface="simple step 'review' prompt placeholder",
            symbols=_simple_prompt_symbols(allow_branch_placeholders=True),
        )
        is None
    )
    assert (
        validate_placeholder_ref(
            fan_in_ref,
            surface="simple step 'review' prompt placeholder",
            symbols=_simple_prompt_symbols(allow_fan_in_placeholders=True),
        )
        is None
    )


def test_render_template_with_refs_preserves_runtime_behavior(tmp_path: Path) -> None:
    context = _build_context(tmp_path)
    template = "Message={ctx.message}; Topic={input.topic}; Branch={branch.name}"
    refs = parse_placeholders(template, source="prompt placeholder")

    rendered = render_template_with_refs(
        template,
        refs,
        context,
        placeholder_label="prompt placeholder",
    )

    assert rendered == "Message=Ship it.; Topic=release; Branch={branch.name}"


def test_render_placeholder_ref_preserves_runtime_resolution_behavior(tmp_path: Path) -> None:
    context = _build_context(tmp_path)
    message_ref = parse_placeholders("{ctx.message}", source="prompt placeholder")[0]
    input_ref = parse_placeholders("{input.topic}", source="prompt placeholder")[0]
    branch_ref = parse_placeholders("{branch.name}", source="prompt placeholder")[0]

    assert render_placeholder_ref(message_ref, context) == "Ship it."
    assert render_placeholder_ref(input_ref, context) == "release"
    assert render_placeholder_ref(branch_ref, context) == "{branch.name}"


def test_render_template_with_refs_preserves_error_quality(tmp_path: Path) -> None:
    context = _build_context(tmp_path)
    ref = parse_placeholders("{input.missing}", source="prompt placeholder")[0]

    with pytest.raises(
        WorkflowExecutionError,
        match=r"prompt placeholder \{input\.missing\} references unknown input field 'missing'",
    ):
        render_template_with_refs(
            "{input.missing}",
            (ref,),
            context,
            placeholder_label="prompt placeholder",
        )


def test_artifact_template_rejects_ctx_placeholders(tmp_path: Path) -> None:
    context = _build_context(tmp_path)

    with pytest.raises(
        WorkflowExecutionError,
        match=r"ctx\.\* placeholders are only supported in prompts and workflow-step messages, not artifact paths",
    ):
        resolve_artifact_template("{ctx.message}.md", context)


def test_reference_graph_stores_placeholder_refs_and_inferred_reads() -> None:
    prompt_refs = {"review": parse_placeholders("Use {ctx.message}", source="prompt")}
    graph = ReferenceGraph(
        prompt_refs=prompt_refs,
        artifact_template_refs={"report": parse_placeholders("reports/{input.topic}.md", source="artifact")},
        inferred_artifact_reads={"review": (ArtifactId("workflow", name="report"),)},
    )

    assert graph.prompt_refs["review"][0].raw == "ctx.message"
    assert graph.artifact_template_refs["report"][0].raw == "input.topic"
    assert graph.inferred_artifact_reads["review"][0].qualified_name == "report"


def test_placeholders_module_does_not_import_context_at_runtime() -> None:
    module_path = Path("botlane/core/placeholders.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "botlane.core.context":
                    pytest.fail("placeholders.py must not import Context at runtime")
        if isinstance(node, ast.ImportFrom) and node.module in {"context", "botlane.core.context"}:
            pytest.fail("placeholders.py must not import Context at runtime")


def test_artifacts_module_no_longer_defines_legacy_runtime_placeholder_helpers() -> None:
    module_path = Path("botlane/core/artifacts.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    legacy_names = {
        "_PLACEHOLDER_RE",
        "PromptContextView",
        "_render_prompt_value",
        "_resolve_placeholder",
        "_resolve_ctx_placeholder",
        "_resolve_input_placeholder",
        "_resolve_item_placeholder",
        "_resolve_worklist_placeholder",
        "_resolve_runtime_path",
        "_lookup_runtime_value",
    }

    defined_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    assigned_names = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    assert not defined_names.intersection(legacy_names)
    assert not assigned_names.intersection(legacy_names)
