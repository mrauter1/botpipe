from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

import botpipe.simple as simple
from botpipe.core.artifacts import resolve_artifact_template
from botpipe.core.compiler import compile_workflow
from botpipe.core.context import Context
from botpipe.core.errors import WorkflowExecutionError, WorkflowValidationError
from botpipe.core.execution_runtime_services import ArtifactRuntimeService
from botpipe.core.identifiers import ArtifactId
from botpipe.core.primitives import Event
from botpipe.core.prompt_templates import render_inline_prompt_template, validate_inline_prompt_template
from botpipe.core.reference_graph import ReferenceGraph
from botpipe.core.stores import InMemorySessionStore
from botpipe.core.template_refs import PlaceholderRef


class _State(BaseModel):
    status: str = "draft"


class _Params(BaseModel):
    mode: str = "brief"


class _Input(BaseModel):
    topic: str


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


def test_jinja_ref_extraction_uses_explicit_roots_only() -> None:
    validation = validate_inline_prompt_template(
        "Draft {{ message }} for {{ input.topic }} using {{ params.mode }} and {{ state.status }}.",
        surface="prompt template",
    )

    assert [ref.raw for ref in validation.refs] == ["message", "input.topic", "params.mode", "state.status"]


def test_jinja_ref_extraction_supports_literal_string_keys() -> None:
    validation = validate_inline_prompt_template(
        'Use {{ artifacts["report"].path }} for {{ input["topic"] }}.',
        surface="prompt template",
    )

    assert [ref.raw for ref in validation.refs] == ["artifacts.report.path", "input.topic"]


def test_jinja_ref_extraction_marks_dynamic_artifact_access_without_rejecting_it() -> None:
    validation = validate_inline_prompt_template(
        "{{ artifacts[params.report_name].path }}",
        surface="prompt template",
    )

    assert validation.dynamic_artifact_access is True
    assert [ref.raw for ref in validation.refs] == ["artifacts", "params.report_name"]


def test_jinja_ref_extraction_marks_broad_dynamic_artifact_access() -> None:
    dynamic_templates = [
        "{{ artifacts|attr(params.report_name) }}",
        "{% set selected = artifacts %}{{ selected.report.path }}",
        "{% with selected = artifacts %}{{ selected[params.report_name].path }}{% endwith %}",
        "{% for artifact in artifacts %}{{ artifact.path }}{% endfor %}",
        "{{ artifacts|length }}",
        "{{ artifacts }}",
    ]

    for template in dynamic_templates:
        validation = validate_inline_prompt_template(template, surface="prompt template")
        assert validation.dynamic_artifact_access is True


def test_jinja_ref_extraction_keeps_static_artifact_access_static() -> None:
    validation = validate_inline_prompt_template(
        '{{ artifacts.report.path }} / {{ artifacts["summary"].path }}',
        surface="prompt template",
    )

    assert validation.dynamic_artifact_access is False
    assert [ref.raw for ref in validation.refs] == ["artifacts.report.path", "artifacts.summary.path"]


def test_jinja_rejects_ctx_and_context_roots() -> None:
    with pytest.raises(WorkflowValidationError, match="unknown Jinja variable\\(s\\): ctx"):
        validate_inline_prompt_template("{{ ctx.input.topic }}", surface="prompt template")

    with pytest.raises(WorkflowValidationError, match="unknown Jinja variable\\(s\\): context"):
        validate_inline_prompt_template("{{ context.input.topic }}", surface="prompt template")

    with pytest.raises(WorkflowValidationError, match="unknown Jinja variable\\(s\\): ctx"):
        validate_inline_prompt_template("{{ ctx|attr('input') }}", surface="prompt template")


def test_jinja_rejects_input_message_request_text_alias() -> None:
    with pytest.raises(
        WorkflowValidationError,
        match=r"unsupported Jinja request-text reference '\{\{ input\.message \}\}'",
    ):
        validate_inline_prompt_template("{{ input.message }}", surface="prompt template")


def test_artifact_template_rejects_legacy_single_brace_placeholder(tmp_path: Path) -> None:
    context = _build_context(tmp_path)

    with pytest.raises(
        WorkflowExecutionError,
        match=r"legacy single-brace placeholder '\{ctx\.message\}'",
    ):
        resolve_artifact_template("{ctx.message}.md", context)


def test_reference_graph_stores_jinja_refs_and_inferred_reads() -> None:
    graph = ReferenceGraph(
        prompt_refs={
            "review": (PlaceholderRef(raw="message", root="message", path=(), source="prompt"),)
        },
        artifact_template_refs={
            "report": (PlaceholderRef(raw="input.topic", root="input", path=("topic",), source="artifact"),)
        },
        inferred_artifact_reads={"review": (ArtifactId("workflow", name="report"),)},
    )

    assert graph.prompt_refs["review"][0].raw == "message"
    assert graph.artifact_template_refs["report"][0].raw == "input.topic"
    assert graph.inferred_artifact_reads["review"][0].qualified_name == "report"


def test_compile_workflow_populates_reference_graph_for_jinja_surfaces() -> None:
    class GraphWorkflow(simple.Workflow):
        class State(BaseModel):
            status: str = "draft"

        class Input(BaseModel):
            topic: str

        gate = simple.Worklist.from_items(
            name="gate",
            items=({"id": "one", "title": "One", "payload": {"status": "ready"}},),
        )

        report = simple.step(
            "Draft {{ message }} for {{ input.topic }} and {{ worklist.gate.current.payload.status }}.",
            name="report",
            scope=gate,
            writes=[simple.Md("report", path="reports/{{ input.topic }}.md")],
        )
        review = simple.step("Review {{ report }}.", name="review")
        assess = simple.parallel(
            branches={
                "security": simple.step(
                    "Assess {{ branch.input.area }}.",
                    name="assess_one",
                    session=simple.Session.fresh(),
                ),
            },
            fan_in=simple.step(
                "Summarize {{ fan_in.context_text }}.",
                name="summarize",
            ),
        )

    compiled = compile_workflow(GraphWorkflow)
    graph = compiled.reference_graph

    assert [ref.raw for ref in graph.prompt_refs["report"]] == [
        "message",
        "input.topic",
        "worklist.gate.current.payload.status",
    ]
    assert [ref.raw for ref in graph.prompt_refs["review"]] == ["report"]
    assert [ref.raw for ref in graph.prompt_refs["assess_one"]] == ["branch.input.area"]
    assert [ref.raw for ref in graph.prompt_refs["summarize"]] == ["fan_in.context_text"]
    assert [ref.raw for ref in graph.artifact_template_refs["report.report"]] == ["input.topic"]
    assert [artifact_id.qualified_name for artifact_id in graph.inferred_artifact_reads["review"]] == ["report.report"]
    assert [ref.raw for ref in graph.step_output_refs["review"]] == ["report"]
    assert [ref.raw for ref in graph.branch_refs["assess_one"]] == ["branch.input.area"]
    assert [ref.raw for ref in graph.fan_in_refs["summarize"]] == ["fan_in.context_text"]
    assert [ref.raw for ref in graph.worklist_refs["report"]] == ["worklist.gate.current.payload.status"]


def test_compile_workflow_rejects_invalid_workflow_step_message_template() -> None:
    class Child(simple.Workflow):
        note = simple.step("Child note.")

    class Parent(simple.Workflow):
        launch = simple.workflow_step(Child, message="{{ missing_root.value }}")

    with pytest.raises(
        WorkflowValidationError,
        match=r"workflow step 'launch' message template <inline prompt template> uses unknown Jinja variable\(s\): missing_root",
    ):
        compile_workflow(Parent)


def test_compile_workflow_rejects_invalid_artifact_template_scope() -> None:
    class BadArtifactWorkflow(simple.Workflow):
        note = simple.step(
            "Draft.",
            writes=[simple.Md("note", path="reports/{{ item.payload.foo }}.md")],
        )

    with pytest.raises(
        WorkflowValidationError,
        match=r"artifact template 'note\.note' \{\{ item\.payload\.foo \}\} requires scope=\.\.\. on the same step",
    ):
        compile_workflow(BadArtifactWorkflow)


def test_compile_workflow_allows_prompt_jinja_input_refs_without_input_model() -> None:
    class PromptMissingInputWorkflow(simple.Workflow):
        review = simple.step("Echo {{ input.customer }}", name="review")

    class ChildWorkflow(simple.Workflow):
        note = simple.step("Child note.")

    class WorkflowStepMissingInputWorkflow(simple.Workflow):
        launch = simple.workflow_step(
            ChildWorkflow,
            name="launch",
            message="{{ input.topic }}",
        )

    prompt_plan = compile_workflow(PromptMissingInputWorkflow)
    workflow_step_plan = compile_workflow(WorkflowStepMissingInputWorkflow)

    assert [ref.raw for ref in prompt_plan.reference_graph.prompt_refs["review"]] == ["input.customer"]
    assert [ref.raw for ref in workflow_step_plan.reference_graph.prompt_refs["launch"]] == ["input.topic"]


def test_compile_workflow_reports_missing_input_model_for_artifact_templates() -> None:
    class ArtifactTemplateMissingInputWorkflow(simple.Workflow):
        review = simple.step(
            "Draft.",
            name="review",
            writes=[simple.Md("report", path="reports/{{ input.topic }}.md")],
        )

    with pytest.raises(
        WorkflowValidationError,
        match=r"artifact template 'review\.report' \{\{ input\.topic \}\} requires workflow input, but no input was provided",
    ):
        compile_workflow(ArtifactTemplateMissingInputWorkflow)


def test_compile_workflow_infers_workflow_step_message_artifact_reads() -> None:
    class ChildWorkflow(simple.Workflow):
        note = simple.step("Child note.")

    class WorkflowStepMessageReadsWorkflow(simple.Workflow):
        report = simple.step("Draft.", name="report", writes=[simple.Md("report")])
        launch = simple.workflow_step(
            ChildWorkflow,
            name="launch",
            message="Use {{ report }}",
        )

    compiled = compile_workflow(WorkflowStepMessageReadsWorkflow)

    assert [ref.raw for ref in compiled.reference_graph.prompt_refs["launch"]] == ["report"]
    assert [artifact_id.qualified_name for artifact_id in compiled.reference_graph.inferred_artifact_reads["launch"]] == [
        "report.report"
    ]


def test_compile_workflow_rejects_root_prompt_consuming_branch_scoped_artifact() -> None:
    report = simple.Md("report", path="reports/{{ branch.name }}.md")

    class BranchArtifactWorkflow(simple.Workflow):
        assess = simple.fan_out(
            step=simple.python_step(
                lambda ctx: Event("done"),
                name="write_one",
                writes=[report],
                routes={"done": "summarize"},
            ),
            branches={"security": {"area": "security"}},
        )
        summarize = simple.step("Summarize {{ artifacts.report.path }}.", name="summarize")

    with pytest.raises(
        WorkflowValidationError,
        match=r"step 'summarize' prompt template cannot consume artifact 'write_one\.report'.*requires branch scope",
    ):
        compile_workflow(BranchArtifactWorkflow)


def test_compile_workflow_rejects_root_requires_consuming_branch_scoped_artifact() -> None:
    report = simple.Md("report", path="reports/{{ branch.name }}.md")

    class BranchArtifactRequiresWorkflow(simple.Workflow):
        assess = simple.fan_out(
            step=simple.python_step(
                lambda ctx: Event("done"),
                name="write_one",
                writes=[report],
                routes={"done": "summarize"},
            ),
            branches={"security": {"area": "security"}},
        )
        summarize = simple.step("Summarize.", name="summarize", requires=[report])

    with pytest.raises(
        WorkflowValidationError,
        match=r"step 'summarize' requires artifact 'write_one\.report' as a single artifact.*reports/\{\{ branch\.name \}\}\.md",
    ):
        compile_workflow(BranchArtifactRequiresWorkflow)


def test_compile_workflow_rejects_root_message_from_consuming_branch_scoped_artifact() -> None:
    report = simple.Md("report", path="reports/{{ branch.name }}.md")

    class Child(simple.Workflow):
        note = simple.step("Child note.")

    class BranchArtifactMessageFromWorkflow(simple.Workflow):
        assess = simple.fan_out(
            step=simple.python_step(
                lambda ctx: Event("done"),
                name="write_one",
                writes=[report],
                routes={"done": "launch"},
            ),
            branches={"security": {"area": "security"}},
        )
        launch = simple.workflow_step(Child, name="launch", message_from=report)

    with pytest.raises(
        WorkflowValidationError,
        match=r"workflow step 'launch' message_from cannot consume artifact 'write_one\.report'.*requires branch scope",
    ):
        compile_workflow(BranchArtifactMessageFromWorkflow)


def test_runtime_artifact_resolution_reports_out_of_scope_artifact(tmp_path: Path) -> None:
    class BranchArtifactWorkflow(simple.Workflow):
        assess = simple.fan_out(
            step=simple.python_step(
                lambda ctx: Event("done"),
                name="write_one",
                writes=[simple.Md("report", path="reports/{{ branch.name }}.md")],
                routes={"done": simple.FINISH},
            ),
            branches={"security": {"area": "security"}},
        )

    compiled = compile_workflow(BranchArtifactWorkflow)
    artifacts = ArtifactRuntimeService(compiled=compiled, events=None).resolve_artifacts(_build_context(tmp_path))

    with pytest.raises(
        WorkflowExecutionError,
        match=r"artifact 'write_one\.report' cannot be resolved in the current context.*requires branch scope",
    ):
        _ = artifacts["report"]


def test_compile_workflow_rejects_route_phase_roots_in_artifact_templates() -> None:
    class RouteArtifactWorkflow(simple.Workflow):
        review = simple.step(
            "Review.",
            name="review",
            writes=[simple.Md("report", path="reports/{{ route.tag }}.md")],
        )

    with pytest.raises(
        WorkflowValidationError,
        match=r"artifact template 'review\.report' uses runtime phase root\(s\) route",
    ):
        compile_workflow(RouteArtifactWorkflow)


def test_compile_workflow_records_dynamic_artifact_access_with_explicit_reads() -> None:
    class DynamicArtifactWorkflow(simple.Workflow):
        class Params(BaseModel):
            report_name: str = "report"

        report = simple.step("Draft.", name="report", writes=[simple.Md("report")])
        review = simple.step(
            "Review {{ artifacts[params.report_name].path }}.",
            name="review",
            reads=["report"],
        )

    compiled = compile_workflow(DynamicArtifactWorkflow)

    assert compiled.reference_graph.prompt_requirements["review"].dynamic_artifact_access is True


def test_compile_workflow_records_dynamic_artifact_access_without_explicit_reads() -> None:
    class DynamicArtifactWorkflow(simple.Workflow):
        class Params(BaseModel):
            report_name: str = "report"

        report = simple.step("Draft.", name="report", writes=[simple.Md("report")])
        review = simple.step(
            "Review {{ artifacts[params.report_name].path }}.",
            name="review",
        )

    compiled = compile_workflow(DynamicArtifactWorkflow)

    assert compiled.reference_graph.prompt_requirements["review"].dynamic_artifact_access is True


def test_branch_and_fan_in_roots_fail_clearly_if_runtime_scope_is_missing(tmp_path: Path) -> None:
    context = _build_context(tmp_path)

    with pytest.raises(
        WorkflowExecutionError,
        match=r"prompt template <inline prompt template>: branch metadata is only available during branch execution",
    ):
        render_inline_prompt_template("{{ branch.name }}", context, placeholder_label="prompt template")

    with pytest.raises(
        WorkflowExecutionError,
        match=r"prompt template <inline prompt template>: fan_in metadata is only available during fan-in execution",
    ):
        render_inline_prompt_template("{{ fan_in.branch_count }}", context, placeholder_label="prompt template")
