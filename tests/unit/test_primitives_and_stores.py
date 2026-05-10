from __future__ import annotations

from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest
from pydantic import BaseModel

import botlane
import botlane.simple as public_simple
import botlane.core.primitives as strict_primitives
from botlane.core.artifacts import Artifact, ArtifactHandle, ResolvedArtifacts, render_runtime_template, resolve_artifact_template
from botlane.core.branch_groups.context import BranchMetadata, FanInMetadata, create_branch_context, create_fan_in_context
from botlane.core.context_placeholders import validate_safe_ctx_reference
from botlane.core.context import Context
from botlane.core.errors import WorkflowExecutionError
from botlane.core.sessions import Continuity, SessionKey
from botlane.core.worklists import Selection, SelectionSnapshot, Selector, WorkItem, WorkItemSnapshot, Worklist
from botlane.core import Session as StrictSession
from botlane.core.primitives import Checkpoint, Event, Goto, Outcome, PendingHandoff
from botlane.core.prompts import Prompt, PromptRegistry
from botlane.core.stores import (
    InMemoryCheckpointStore,
    InMemorySessionBackend,
    InMemorySessionStore,
    PendingInput,
    SessionStore,
    SessionBinding,
    SessionSnapshot,
)
from botlane.runtime.runner import _prompt_registry_roots


class _PhaseState(BaseModel):
    id: str = "phase-1"


class _State(BaseModel):
    phase: _PhaseState = _PhaseState()


class _PromptState(BaseModel):
    status: str = "draft"
    count: int = 1


class _PromptParams(BaseModel):
    mode: str = "brief"
    enabled: bool = True


class _PromptInput(BaseModel):
    topic: str


class _PromptInputWithMessage(BaseModel):
    message: str
    topic: str


class _ComplexPromptInput(BaseModel):
    tags: list[str]


def test_context_request_surface_reads_run_snapshot_and_task_request_file(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)
    (task_folder / "request.md").write_text("Task request\n", encoding="utf-8")
    (run_folder / "request.md").write_text("Line one\nLine two\n", encoding="utf-8")

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_State(),
        session_store=InMemorySessionStore(),
    )

    assert context.request_file == run_folder / "request.md"
    assert context.request.file == context.request_file
    assert context.request.task_file == task_folder / "request.md"
    assert context.request.text == "Line one\nLine two"
    assert context.message == "Line one\nLine two"
    assert context.input_fields is None
    assert context.input.message == "Line one\nLine two"
    assert context.input.model_dump() == {"message": "Line one\nLine two"}


def test_context_request_surface_preserves_trailing_spaces_while_stripping_only_newlines(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)
    (run_folder / "request.md").write_text("Line one  \nLine two   \n\n", encoding="utf-8")

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_State(),
        session_store=InMemorySessionStore(),
    )

    assert context.request.text == "Line one  \nLine two   "
    assert context.message == "Line one  \nLine two   "


def test_context_message_raises_when_run_request_snapshot_is_missing(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_State(),
        session_store=InMemorySessionStore(),
    )

    with pytest.raises(WorkflowExecutionError, match=r"run request snapshot could not be read: .*request\.md"):
        _ = context.message


def test_context_request_surface_leaves_task_request_file_unset_when_absent(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)
    (run_folder / "request.md").write_text("Only run request\n", encoding="utf-8")

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_State(),
        session_store=InMemorySessionStore(),
    )

    assert context.request.task_file is None
    assert context.message == "Only run request"


def test_validate_safe_ctx_reference_rejects_unsafe_segments() -> None:
    assert validate_safe_ctx_reference("ctx.message") == ("ctx", "message")
    assert validate_safe_ctx_reference("ctx.request.text") == ("ctx", "request", "text")
    assert validate_safe_ctx_reference("ctx.input.message") == ("ctx", "input", "message")
    assert validate_safe_ctx_reference("ctx.input.topic") == ("ctx", "input", "topic")

    for reference in (
        "ctx.__dict__",
        "ctx.request.file.read_text()",
        "ctx.request._private",
        'ctx["message"]',
        "ctx.message upper",
        "ctx.message.extra",
        "ctx.request.file.read_text",
        "ctx.request.missing",
        "ctx.input.topic.extra",
    ):
        with pytest.raises(ValueError):
            validate_safe_ctx_reference(reference)


def test_render_runtime_template_resolves_ctx_bindings_with_scalar_values(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)
    (task_folder / "request.md").write_text("Task request\n", encoding="utf-8")
    (run_folder / "request.md").write_text("Ship the release safely.\n", encoding="utf-8")

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_PromptState(),
        params=_PromptParams(mode="brief", enabled=True),
        workflow_input=_PromptInput(topic="release"),
        session_store=InMemorySessionStore(),
    )

    rendered = render_runtime_template(
        "Message={ctx.message}; Topic={ctx.input.topic}; Mode={ctx.params.mode}; Status={ctx.state.status}; File={ctx.request.file}",
        context,
        placeholder_label="prompt placeholder",
        replace_roots=frozenset({"ctx"}),
    )

    assert rendered == (
        "Message=Ship the release safely.; Topic=release; Mode=brief; "
        f"Status=draft; File={run_folder / 'request.md'}"
    )


def test_render_runtime_template_resolves_ctx_input_message_without_typed_input(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)
    (run_folder / "request.md").write_text("Ship the release safely.\n", encoding="utf-8")

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_PromptState(),
        params=_PromptParams(mode="brief", enabled=True),
        workflow_input=_PromptInput(topic="release"),
        session_store=InMemorySessionStore(),
    )

    rendered = render_runtime_template(
        "{ctx.input.message}",
        context,
        placeholder_label="prompt placeholder",
        replace_roots=frozenset({"ctx"}),
    )

    assert rendered == "Ship the release safely."


def test_render_runtime_template_resolves_ctx_input_message_from_runtime_message_with_typed_input(
    tmp_path: Path,
) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)
    (run_folder / "request.md").write_text("Ship the release safely.\n", encoding="utf-8")

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_PromptState(),
        params=_PromptParams(mode="brief", enabled=True),
        workflow_input=_PromptInputWithMessage(message="Typed input message", topic="release"),
        session_store=InMemorySessionStore(),
    )

    rendered = render_runtime_template(
        "Request={ctx.message}; InputMessage={ctx.input.message}; Topic={ctx.input.topic}",
        context,
        placeholder_label="prompt placeholder",
        replace_roots=frozenset({"ctx"}),
    )

    assert rendered == "Request=Ship the release safely.; InputMessage=Ship the release safely.; Topic=release"


def test_context_can_keep_message_separate_from_request_snapshot_and_typed_input(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)
    (run_folder / "request.md").write_text("Fallback request text\n", encoding="utf-8")

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_PromptState(),
        message=None,
        workflow_input=_PromptInput(topic="release"),
        session_store=InMemorySessionStore(),
    )

    assert context.message is None
    assert context.request.text == "Fallback request text"
    assert context.input.message is None
    assert context.input.topic == "release"
    assert context.input_fields == _PromptInput(topic="release")
    assert context.input.model_dump() == {"message": None, "topic": "release"}


def test_context_input_fields_remain_available_without_request_snapshot(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_PromptState(),
        workflow_input=_PromptInput(topic="release"),
        session_store=InMemorySessionStore(),
    )

    assert context.input.topic == "release"
    assert context.input.message is None
    assert context.input_fields == _PromptInput(topic="release")
    assert context.input.model_dump() == {"message": None, "topic": "release"}


def test_render_runtime_template_rejects_missing_ctx_input(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)
    (run_folder / "request.md").write_text("Missing input check\n", encoding="utf-8")

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_PromptState(),
        params=_PromptParams(),
        session_store=InMemorySessionStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"ctx\.input\.topic requires workflow input, but no input was provided",
    ):
        render_runtime_template(
            "{ctx.input.topic}",
            context,
            placeholder_label="prompt placeholder",
            replace_roots=frozenset({"ctx"}),
        )


def test_render_runtime_template_rejects_non_scalar_ctx_values(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)
    (run_folder / "request.md").write_text("Complex input check\n", encoding="utf-8")

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_PromptState(),
        params=_PromptParams(),
        workflow_input=_ComplexPromptInput(tags=["alpha", "beta"]),
        session_store=InMemorySessionStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"prompt placeholder \{ctx\.input\.tags\} resolved to a non-scalar value",
    ):
        render_runtime_template(
            "{ctx.input.tags}",
            context,
            placeholder_label="prompt placeholder",
            replace_roots=frozenset({"ctx"}),
        )


def test_render_runtime_template_rejects_unsafe_ctx_paths(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)
    (run_folder / "request.md").write_text("Unsafe path check\n", encoding="utf-8")

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_PromptState(),
        session_store=InMemorySessionStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"prompt placeholder \{ctx\.__dict__\} is not a supported safe dotted path",
    ):
        render_runtime_template(
            "{ctx.__dict__}",
            context,
            placeholder_label="prompt placeholder",
            replace_roots=frozenset({"ctx"}),
        )


def test_resolve_artifact_template_rejects_ctx_placeholders(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)
    (run_folder / "request.md").write_text("Artifact path check\n", encoding="utf-8")

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_PromptState(),
        session_store=InMemorySessionStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"ctx\.\* placeholders are only supported in prompts and workflow-step messages, not artifact paths",
    ):
        resolve_artifact_template("outputs/{ctx.message}.md", context)


def test_resolve_artifact_template_supports_composite_input_message_and_fields(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)
    (run_folder / "request.md").write_text("artifact-request\n", encoding="utf-8")

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_PromptState(),
        workflow_input=_PromptInput(topic="release"),
        session_store=InMemorySessionStore(),
    )

    resolved = resolve_artifact_template("outputs/{input.message}-{input.topic}.md", context)

    assert resolved == Path("outputs") / "artifact-request-release.md"


def test_render_runtime_template_bare_input_message_uses_runtime_message(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)
    (run_folder / "request.md").write_text("artifact-request\n", encoding="utf-8")

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_PromptState(),
        workflow_input=_PromptInput(topic="release"),
        session_store=InMemorySessionStore(),
    )

    rendered = render_runtime_template(
        "Message={input.message}; Topic={input.topic}",
        context,
        placeholder_label="artifact template placeholder",
    )

    assert rendered == "Message=artifact-request; Topic=release"


def test_render_runtime_template_keeps_bare_input_message_separate_from_ctx_input_message(
    tmp_path: Path,
) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir(parents=True)
    (run_folder / "request.md").write_text("artifact-request\n", encoding="utf-8")

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=_PromptState(),
        workflow_input=_PromptInputWithMessage(message="typed-input", topic="release"),
        session_store=InMemorySessionStore(),
    )

    rendered = render_runtime_template(
        "Bare={input.message}; Ctx={ctx.input.message}; Topic={ctx.input.topic}",
        context,
        placeholder_label="artifact template placeholder",
    )

    assert rendered == "Bare=artifact-request; Ctx=artifact-request; Topic=release"


def test_event_and_outcome():
    outcome = Outcome(raw_output="raw", tag="ok", payload={"x": 1})
    assert Event(tag="ok").tag == "ok"
    assert outcome.payload == {"x": 1}


def test_event_handoff_requires_non_empty_text():
    assert Event(tag="ok", handoff="  carry forward  ").handoff == "carry forward"

    with pytest.raises(ValueError, match="Event.handoff"):
        Event(tag="ok", handoff="   ")


def test_public_authoring_surfaces_export_requested_runtime_primitives():
    for removed in ("Checkpoint", "ChildWorkflowResult", "ResolvedArtifacts"):
        assert not hasattr(public_simple, removed)

    assert not hasattr(botlane, "Checkpoint")
    assert not hasattr(botlane, "ChildWorkflowResult")
    assert not hasattr(botlane, "ResolvedArtifacts")
    assert botlane.Event is public_simple.Event
    assert botlane.Outcome is public_simple.Outcome
    assert hasattr(public_simple, "Event")
    assert hasattr(public_simple, "Outcome")
    for exported in ("Checkpoint", "Event", "Outcome", "PendingHandoff", "ResolvedArtifacts"):
        assert exported in strict_primitives.__all__


def test_public_context_hides_runtime_mutators(tmp_path: Path) -> None:
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
    )

    for hidden_name in (
        "_runtime",
        "_set_state",
        "_set_route",
        "_set_outcome",
        "_set_selection",
        "_cache_worklist_items",
    ):
        assert not hasattr(context, hidden_name)


def test_prompt_registry_roots_include_capability_prompt_dirs_outside_workflow_parent(tmp_path: Path):
    package_dir = tmp_path / "workflows" / "example"
    external_prompt = tmp_path / "shared_prompts" / "ask.md"
    external_prompt.parent.mkdir(parents=True, exist_ok=True)
    external_prompt.write_text("shared prompt\n", encoding="utf-8")
    roots = _prompt_registry_roots(
        package_dir,
        compiled=SimpleNamespace(
            steps={
                "ask": SimpleNamespace(
                    producer_prompt=Prompt.file("prompts/ask.md"),
                    verifier_prompt=None,
                )
            }
        ),
        capability_prompt_paths=(external_prompt,),
    )

    assert roots[0] == package_dir.resolve()
    assert (package_dir / "prompts").resolve() in roots
    assert external_prompt.parent.resolve() in roots


def test_prompt_registry_roots_include_plain_string_prompt_spec_dirs(tmp_path: Path):
    package_dir = tmp_path / "workflows" / "example"
    roots = _prompt_registry_roots(
        package_dir,
        compiled=SimpleNamespace(
            steps={
                "ask": SimpleNamespace(
                    producer_prompt="prompts/ask.md",
                    verifier_prompt="reviews/verify.md",
                )
            }
        ),
    )

    assert roots[0] == package_dir.resolve()
    assert (package_dir / "prompts").resolve() in roots
    assert (package_dir / "reviews").resolve() in roots


def test_artifact_template_resolution_supports_dot_notation_and_missing_keys(tmp_path: Path):
    package_folder = tmp_path / "workflows" / "example"
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=package_folder,
        state=_State(),
        session_store=InMemorySessionStore(),
    )

    workflow_resolved = resolve_artifact_template("{workflow_folder}/phases/{state.phase.id}/{state.missing}/file.txt", context)
    package_resolved = resolve_artifact_template("{package_folder}/prompts/{workflow_name}.md", context)

    assert workflow_resolved == tmp_path / "task" / "wf_example" / "phases" / "phase-1" / "file.txt"
    assert package_resolved == package_folder / "prompts" / "example.md"


def test_artifact_template_resolution_supports_step_local_relative_artifacts(tmp_path: Path):
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
    )
    artifact = Artifact.md("draft.md", required=True)
    artifact.bind_name("draft")
    artifact.bind_owner_step("plan")

    resolved = resolve_artifact_template(artifact, context)

    assert resolved == tmp_path / "task" / "wf_example" / "plan" / "draft.md"


def test_artifact_template_resolution_renders_branch_placeholders_under_owner_step_root(tmp_path: Path) -> None:
    parent = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
    )
    branch = create_branch_context(
        parent,
        step_name="assess_one",
        branch=BranchMetadata(
            name="security",
            index=0,
            group="assess",
            input={"area": "security"},
            count=2,
        ),
        session_store=parent._session_store,
    )
    artifact = Artifact.md("reports/{branch.name}.md", required=True)
    artifact.bind_name("report")
    artifact.bind_owner_step("assess_one")

    resolved = resolve_artifact_template(artifact, branch)

    assert resolved == tmp_path / "task" / "wf_example" / "assess_one" / "reports" / "security.md"


def test_artifact_template_resolution_renders_fan_in_placeholders_under_owner_step_root(tmp_path: Path) -> None:
    parent = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
    )
    fan_in = create_fan_in_context(
        parent,
        step_name="combine_reviews",
        fan_in=FanInMetadata(
            results={"branches": []},
            results_path=parent.workflow_folder / "_branch_groups" / "reviews" / "results.json",
            context_path=parent.workflow_folder / "_branch_groups" / "reviews" / "context.md",
            context_text="# Reviews",
            branch_count=2,
            completed_count=1,
            failed_count=0,
            needs_input_count=0,
            cancelled_count=0,
        ),
        session_store=parent._session_store,
    )
    artifact = Artifact.text("summaries/{fan_in.completed_count}.txt", required=True)
    artifact.bind_name("summary")
    artifact.bind_owner_step("combine_reviews")

    resolved = resolve_artifact_template(artifact, fan_in)

    assert resolved == tmp_path / "task" / "wf_example" / "combine_reviews" / "summaries" / "1.txt"


def test_artifact_template_resolution_treats_mid_chain_none_state_values_as_empty_strings(tmp_path: Path):
    class _NullablePhaseState(BaseModel):
        dir_key: str | None = None

    class _NullableState(BaseModel):
        phase: _NullablePhaseState = _NullablePhaseState()

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_NullableState(),
        session_store=InMemorySessionStore(),
    )

    resolved = resolve_artifact_template("{workflow_folder}/phases/{state.phase.dir_key}/file.txt", context)

    assert resolved == tmp_path / "task" / "wf_example" / "phases" / "file.txt"


def test_artifact_factories_and_binding_capture_extended_metadata():
    class Summary(BaseModel):
        text: str

    artifact = Artifact.json("summary.json", schema=Summary, required=True)
    artifact.bind_name("summary")
    artifact.bind_owner_step("draft")

    assert artifact.kind == "json"
    assert artifact.schema is Summary
    assert artifact.required is True
    assert artifact.owner_step == "draft"
    assert artifact.qualified_name == "draft.summary"
    assert Artifact.text("note.txt").kind == "text"
    assert Artifact.md("note.md").kind == "markdown"
    assert Artifact.raw("blob.bin").kind == "raw"


def test_resolved_artifacts_expose_attribute_access(tmp_path: Path):
    handle = ArtifactHandle(name="draft", path=tmp_path / "draft.txt")
    handle.write_text("hello")
    artifacts = ResolvedArtifacts({"draft": handle})

    assert artifacts["draft"].read_text() == "hello"
    assert artifacts.draft.read_text() == "hello"


def test_artifact_handle_json_and_model_helpers_round_trip(tmp_path: Path):
    class Summary(BaseModel):
        text: str

    artifact = Artifact.json("summary.json", schema=Summary, required=True, name="summary")
    handle = ArtifactHandle(name="summary", path=tmp_path / "summary.json", artifact=artifact)

    handle.write_json({"text": "hello"})
    assert handle.read_json() == {"text": "hello"}
    assert handle.read_model() == Summary(text="hello")

    handle.write_model(Summary(text="updated"))
    assert handle.read_json() == {"text": "updated"}


def test_artifact_handle_read_model_requires_pydantic_schema(tmp_path: Path):
    artifact = Artifact.text("note.txt", name="note")
    handle = ArtifactHandle(name="note", path=tmp_path / "note.txt", artifact=artifact)
    handle.write_text("hello")

    with pytest.raises(TypeError, match="artifact has no schema"):
        handle.read_model()


def test_artifact_handle_validation_reports_schema_and_requiredness(tmp_path: Path):
    class Summary(BaseModel):
        text: str

    missing_artifact = Artifact.json("summary.json", schema=Summary, required=True, name="summary")
    missing_artifact.bind_owner_step("draft")
    missing = ArtifactHandle(name="summary", path=tmp_path / "missing.json", artifact=missing_artifact)

    missing_result = missing.validate()

    assert missing_result.ok is False
    assert missing_result.qualified_name == "draft.summary"
    assert missing_result.errors == ("artifact file does not exist",)

    invalid_handle = ArtifactHandle(name="summary", path=tmp_path / "summary.json", artifact=missing_artifact)
    invalid_handle.write_json({"other": "value"})

    invalid_result = invalid_handle.validate()

    assert invalid_result.ok is False
    assert invalid_result.errors
    assert "Field required" in invalid_result.errors[0]


def test_artifact_handle_validation_allows_missing_optional_artifact(tmp_path: Path):
    class Summary(BaseModel):
        text: str

    artifact = Artifact.json("summary.json", schema=Summary, required=False, name="summary")
    handle = ArtifactHandle(name="summary", path=tmp_path / "missing.json", artifact=artifact)

    result = handle.validate()

    assert result.ok is True
    assert result.errors == ()


def test_artifact_handle_validation_allows_directory_outputs_without_schema(tmp_path: Path):
    artifact = Artifact("{workflow_folder}/candidate_workflow_surface", name="candidate_workflow_surface")
    path = tmp_path / "candidate_workflow_surface"
    path.mkdir()
    handle = ArtifactHandle(name="candidate_workflow_surface", path=path, artifact=artifact)

    result = handle.validate()

    assert result.ok is True
    assert result.errors == ()


def test_artifact_handle_validation_rejects_directory_outputs_for_json_artifacts(tmp_path: Path):
    class Summary(BaseModel):
        text: str

    artifact = Artifact.json("{workflow_folder}/candidate_summary", schema=Summary, required=True, name="summary")
    path = tmp_path / "candidate_summary"
    path.mkdir()
    handle = ArtifactHandle(name="summary", path=path, artifact=artifact)

    result = handle.validate()

    assert result.ok is False
    assert result.errors == ("artifact path is a directory",)


def test_context_invoke_workflow_omits_input_for_legacy_invokers(tmp_path: Path):
    captured: dict[str, object] = {}

    def _legacy_invoker(workflow, *, message, parameters):
        captured["workflow"] = workflow
        captured["message"] = message
        captured["parameters"] = parameters
        return "ok"

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "task" / "wf_example" / "runs" / "run-1",
        package_folder=tmp_path / "workflows" / "example",
        state=_State(),
        session_store=InMemorySessionStore(),
        workflow_invoker=_legacy_invoker,
    )

    result = context.invoke_workflow("child", message="run child", parameters={"mode": "strict"})

    assert result == "ok"
    assert captured == {
        "workflow": "child",
        "message": "run child",
        "parameters": {"mode": "strict"},
    }


def test_context_invoke_workflow_rejects_typed_input_for_legacy_invokers(tmp_path: Path):
    def _legacy_invoker(workflow, *, message, parameters):
        raise AssertionError("legacy invoker should not run when typed input cannot be delivered")

    class ChildInput(BaseModel):
        topic: str

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "task" / "wf_example" / "runs" / "run-1",
        package_folder=tmp_path / "workflows" / "example",
        state=_State(),
        session_store=InMemorySessionStore(),
        workflow_invoker=_legacy_invoker,
    )

    with pytest.raises(TypeError, match="does not accept typed child input"):
        context.invoke_workflow(
            "child",
            message="run child",
            parameters={"mode": "strict"},
            input=ChildInput(topic="alpha"),
        )


def test_prompt_registry_resolves_prompt_objects_and_plain_strings():
    registry = PromptRegistry({"pair.md": "pair prompt", "llm.md": "llm prompt"})

    assert registry.resolve(Prompt("pair.md")).text == "pair prompt"
    assert registry.resolve("llm.md").text == "llm prompt"


def test_in_memory_session_store_tracks_active_scope_and_restores_snapshots():
    store = InMemorySessionStore()
    alpha = store.open("phase_session", scope="phase-a")
    store.open("phase_session", scope="phase-b")

    assert store.get("phase_session") != alpha
    assert store.get("phase_session").scope == "phase-b"

    snapshot = store.snapshot()
    restored = InMemorySessionStore()
    restored.restore(snapshot)

    assert restored.get("phase_session").scope == "phase-b"
    assert restored.get("phase_session", scope="phase-a") == alpha
    assert restored.snapshot().active_keys_by_slot["phase_session"] == SessionKey(
        slot="phase_session",
        domain="explicit_scope",
        value="phase-b",
    )


def test_session_store_can_be_composed_from_backend() -> None:
    store = SessionStore(InMemorySessionBackend())
    binding = store.open("main")

    assert binding.session_id is not None
    assert store.get("main") == binding


def test_context_copies_workflow_params_from_mapping_boundary(tmp_path: Path) -> None:
    source = {"mode": "strict"}
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        workflow_params=MappingProxyType(source),
    )

    source["mode"] = "loose"
    observed = context.workflow_params
    observed["mode"] = "mutated"

    assert context.workflow_params == {"mode": "strict"}


def test_in_memory_session_store_restores_legacy_active_scope_snapshots() -> None:
    alpha = SessionBinding(ref_name="phase_session", scope="phase-a", session_id="phase_session:phase-a:1")
    global_main = SessionBinding(ref_name="main", scope=None, session_id="main:global:1")
    snapshot = SessionSnapshot(
        bindings=(alpha, global_main),
        active_scopes={"phase_session": "phase-a", "main": None},
    )

    restored = InMemorySessionStore()
    restored.restore(snapshot)

    assert restored.get("phase_session").session_id == "phase_session:phase-a:1"
    assert restored.get("phase_session").key == SessionKey("phase_session", "explicit_scope", "phase-a")
    assert restored.get("main").session_id == "main:global:1"

    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=Path("."),
        workflow_folder=Path("."),
        run_folder=Path("."),
        package_folder=Path("."),
        state=_State(),
        session_store=restored,
    )

    reopened = context.open_session("main")

    assert reopened.session_id == "main:global:1"
    assert restored.get("main") == reopened


def test_checkpoint_store_round_trip_preserves_pending_question_and_answer():
    session_store = InMemorySessionStore()
    session_store.upsert(SessionBinding(ref_name="main", scope=None, session_id="main:global:1"))
    checkpoint = Checkpoint(
        stage="ask",
        state=_State(),
        session_bindings=session_store.snapshot(),
        pending_question="What now?",
        pending_answer="Later",
    )
    store = InMemoryCheckpointStore()
    store.save(checkpoint)

    loaded = store.load()

    assert loaded == checkpoint
    assert loaded.pending_question == "What now?"
    assert loaded.pending_answer == "Later"
    assert loaded.session_bindings.active_scopes == {"main": None}


def test_checkpoint_store_round_trip_preserves_pending_input_metadata():
    checkpoint = Checkpoint(
        stage="ask",
        state=_State(),
        session_bindings=SessionSnapshot(bindings=(), active_keys_by_slot={}),
        pending_input=PendingInput(
            pending_input_id="pending-1",
            source_step="ask",
            source_hook="after",
            source_phase="after",
            question="Who approves this?",
            reason="Approval required",
            best_supposition="approve",
            input_schema={"type": "object", "properties": {"approved_by": {"type": "string"}}},
            created_at="2026-05-01T00:00:00+00:00",
        ),
        pending_question="Who approves this?",
    )
    store = InMemoryCheckpointStore()
    store.save(checkpoint)

    loaded = store.load()

    assert loaded is not None
    assert loaded.pending_input == checkpoint.pending_input
    assert loaded.pending_question == "Who approves this?"


def test_checkpoint_store_round_trip_preserves_worklist_selection_snapshots():
    checkpoint = Checkpoint(
        stage="assess",
        state=_State(),
        session_bindings=SessionSnapshot(bindings=(), active_keys_by_slot={}),
        worklist_selections={
            "gate": SelectionSnapshot(
                worklist_name="gate",
                mode="all",
                items=(
                    WorkItemSnapshot(id="alpha", title="Alpha", status="completed", dir_key="alpha"),
                    WorkItemSnapshot(id="beta", title="Beta", status=None, dir_key="beta"),
                ),
                explicit=False,
                current_index=1,
            )
        },
    )
    store = InMemoryCheckpointStore()

    store.save(checkpoint)
    loaded = store.load()

    assert loaded is not None
    assert loaded.worklist_selections == checkpoint.worklist_selections


def test_checkpoint_store_round_trip_preserves_pending_handoffs():
    checkpoint = Checkpoint(
        stage="review",
        state=_State(),
        session_bindings=SessionSnapshot(bindings=(), active_keys_by_slot={}),
        pending_handoffs=(
            PendingHandoff(
                source_step="draft",
                route_tag="review",
                target_step="review",
                message="Carry the unresolved design notes.",
                worklist_name="gate",
                item_id="alpha",
            ),
        ),
    )
    store = InMemoryCheckpointStore()

    store.save(checkpoint)
    loaded = store.load()

    assert loaded is not None
    assert loaded.pending_handoffs == checkpoint.pending_handoffs


def test_context_open_session_scope_and_key_resolution_are_backward_compatible(tmp_path: Path) -> None:
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        session_definitions={"orbit": StrictSession(continuity=Continuity.task())},
    )

    keyword = context.open_session("orbit", scope="cluster-1")
    positional = context.get_session("orbit", "cluster-1")
    explicit_key = context.open_session("orbit", key="customer-acme")
    continuity_bound = context.open_session("orbit", continuity=Continuity.task())

    assert keyword.key == SessionKey("orbit", "explicit_scope", "cluster-1")
    assert positional == keyword
    assert explicit_key.key == SessionKey("orbit", "explicit_key", "customer-acme")
    assert continuity_bound.key == SessionKey("orbit", "task", "task-1")

    with pytest.raises(Exception, match="mutually exclusive"):
        context.open_session("orbit", scope="cluster-2", key="customer-b")


def test_context_defaults_params_to_an_immutable_empty_model(tmp_path: Path) -> None:
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
    )

    assert context.params.model_dump(mode="python") == {}

    with pytest.raises(Exception):
        context.params.anything = "value"


def test_context_exposes_worklist_selection_helpers_and_item_placeholder_state(tmp_path: Path) -> None:
    gates = Worklist.from_items(
        name="gate",
        items=(
            {"id": "alpha", "title": "Alpha"},
            {"id": "beta", "title": "Beta"},
        ),
        selector=Selector(item_param="gate_id", mode_param="mode", allowed_modes=("all", "single")),
    )
    selection = Selection(
        worklist_name="gate",
        mode="single",
        items=gates.initial_selection(
            Context(
                task_id="task-1",
                run_id="run-1",
                workflow_name="example",
                task_folder=tmp_path / "task",
                workflow_folder=tmp_path / "task" / "wf_example",
                run_folder=tmp_path / "run",
                package_folder=tmp_path / "package",
                state=_State(),
                session_store=InMemorySessionStore(),
                worklists={"gate": gates},
                selections={},
                workflow_params={"gate_id": "beta", "mode": "single"},
            )
        ).items,
        explicit=True,
        current_index=0,
    )
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        worklists={"gate": gates},
        selections={"gate": selection},
        workflow_params={"gate_id": "beta", "mode": "single"},
    )
    context._execution_frame.set_active_worklist("gate")

    assert context.selection(gates).current is not None
    assert context.current("gate").id == "beta"
    assert context.item.id == "beta"
    assert context.selection("gate").explicit is True
    assert context.worklists.gate.current_id == "beta"
    assert context.current_worklist.current_id == "beta"
    assert context.current_worklist.item_ids == ("beta",)


def test_context_ensure_selection_lazily_materializes_missing_worklist(tmp_path: Path) -> None:
    gates = Worklist.from_items(
        name="gate",
        items=(
            {"id": "alpha", "title": "Alpha"},
            {"id": "beta", "title": "Beta"},
        ),
    )
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        worklists={"gate": gates},
        selections={},
    )
    runtime = context._execution_frame
    runtime.set_active_worklist("gate")
    calls: list[str] = []

    def _resolve(worklist_name: str):
        calls.append(worklist_name)
        selection = gates.initial_selection(context)
        runtime.set_selection(worklist_name, selection)
        return selection

    runtime.set_worklist_selection_resolver(_resolve)

    first = context.ensure_selection("gate")
    second = context.selection(gates)

    assert first is second
    assert context.current("gate") is not None
    assert context.item is not None
    assert context.item.id == "alpha"
    assert calls == ["gate"]


def test_context_ensure_selection_only_materializes_requested_worklist(tmp_path: Path) -> None:
    gates = Worklist.from_items(name="gate", items=({"id": "alpha", "title": "Alpha"},))
    reviews = Worklist.from_items(name="review", items=({"id": "beta", "title": "Beta"},))
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        worklists={"gate": gates, "review": reviews},
        selections={},
    )
    runtime = context._execution_frame
    calls: list[str] = []

    def _resolve(worklist_name: str):
        calls.append(worklist_name)
        worklist = gates if worklist_name == "gate" else reviews
        selection = worklist.initial_selection(context)
        runtime.set_selection(worklist_name, selection)
        return selection

    runtime.set_worklist_selection_resolver(_resolve)

    selection = context.ensure_selection("gate")

    assert selection.current is not None
    assert selection.current.id == "alpha"
    assert calls == ["gate"]
    assert set(context._selections) == {"gate"}


def test_worklist_runtime_view_updates_selection_emits_events_and_returns_exhaustion_control(tmp_path: Path) -> None:
    gates = Worklist.from_items(
        name="gate",
        items=(
            {"id": "alpha", "title": "Alpha"},
            {"id": "beta", "title": "Beta"},
        ),
    )
    runtime_events: list[tuple[str, dict[str, object]]] = []
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        worklists={"gate": gates},
        selections={"gate": gates.initial_selection(Context(
            task_id="task-1",
            run_id="run-1",
            workflow_name="example",
            task_folder=tmp_path / "task",
            workflow_folder=tmp_path / "task" / "wf_example",
            run_folder=tmp_path / "run",
            package_folder=tmp_path / "package",
            state=_State(),
            session_store=InMemorySessionStore(),
        ))},
        active_worklist="gate",
        step_name="review",
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
        item_state_store={"status": "queued", "last_step": "review", "last_route": None},
        step_item_state_store={"visits": 1, "last_route": None, "last_reason": None},
    )
    context._execution_frame.set_execution_source(
        hook_name="complete_and_advance",
        phase="on_taken",
        invocation_id="hook-1",
    )

    view = context.current_worklist
    assert view.current_id == "alpha"
    first = view.advance()
    exhausted = view.advance_or(Goto("finalize"))

    assert first is True
    assert view.current_id is None
    assert isinstance(exhausted, Goto)
    assert exhausted.target == "finalize"
    assert [event_type for event_type, _ in runtime_events] == [
        "worklist_advanced",
        "worklist_advanced",
        "worklist_exhausted",
    ]
    assert runtime_events[-1][1]["source_phase"] == "on_taken"
    assert runtime_events[-1][1]["source_hook"] == "complete_and_advance"


def test_worklist_load_items_rejects_duplicate_ids(tmp_path: Path) -> None:
    gates = Worklist.from_items(
        name="gate",
        items=(
            {"id": "alpha", "title": "Alpha"},
            {"id": "alpha", "title": "Duplicate Alpha"},
        ),
    )
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
    )

    with pytest.raises(WorkflowExecutionError, match="duplicate item id"):
        gates.load_items(context)


def test_artifact_template_resolution_supports_worklist_placeholders(tmp_path: Path):
    gates = Worklist.from_items(
        name="gate",
        items=({"id": "alpha", "title": "Alpha"},),
    )
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        worklists={"gate": gates},
        selections={
            "gate": Selection(
                worklist_name="gate",
                mode="all",
                items=gates.load_items(
                    Context(
                        task_id="task-1",
                        run_id="run-1",
                        workflow_name="example",
                        task_folder=tmp_path / "task",
                        workflow_folder=tmp_path / "task" / "wf_example",
                        run_folder=tmp_path / "run",
                        package_folder=tmp_path / "package",
                        state=_State(),
                        session_store=InMemorySessionStore(),
                    )
                ),
                explicit=False,
            )
        },
    )
    context._execution_frame.set_active_worklist("gate")

    resolved = resolve_artifact_template(
        "{workflow_folder}/{item.dir_key}/{worklist.gate.current.id}.md",
        context,
    )

    assert resolved == tmp_path / "task" / "wf_example" / "alpha" / "alpha.md"


def test_artifact_template_resolution_lazily_materializes_worklist_placeholders(tmp_path: Path):
    gates = Worklist.from_items(
        name="gate",
        items=({"id": "alpha", "title": "Alpha"},),
    )
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        worklists={"gate": gates},
        selections={},
    )
    runtime = context._execution_frame
    runtime.set_active_worklist("gate")
    calls: list[str] = []

    def _resolve(worklist_name: str):
        calls.append(worklist_name)
        selection = gates.initial_selection(context)
        runtime.set_selection(worklist_name, selection)
        return selection

    runtime.set_worklist_selection_resolver(_resolve)

    resolved = resolve_artifact_template(
        "{workflow_folder}/{item.dir_key}/{worklist.gate.current.id}.md",
        context,
    )

    assert resolved == tmp_path / "task" / "wf_example" / "alpha" / "alpha.md"
    assert calls == ["gate"]


def test_artifact_template_resolution_supports_item_state_placeholders(tmp_path: Path) -> None:
    class ItemState(BaseModel):
        severity: str = "high"

    gates = Worklist.from_items(
        name="gate",
        items=({"id": "alpha", "title": "Alpha"},),
        item_state=ItemState,
    )
    selection = gates.initial_selection(
        Context(
            task_id="task-1",
            run_id="run-1",
            workflow_name="example",
            task_folder=tmp_path / "task",
            workflow_folder=tmp_path / "task" / "wf_example",
            run_folder=tmp_path / "run",
            package_folder=tmp_path / "package",
            state=_State(),
            session_store=InMemorySessionStore(),
            worklists={"gate": gates},
            selections={},
        )
    )
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        worklists={"gate": gates},
        selections={"gate": selection},
        active_worklist="gate",
        item_state_store=gates.runtime_item_state_model(severity="urgent"),
    )

    resolved = resolve_artifact_template(
        "{workflow_folder}/{item.state.severity}.md",
        context,
    )

    assert resolved == tmp_path / "task" / "wf_example" / "urgent.md"


def test_artifact_template_resolution_reports_missing_payload_path(tmp_path: Path) -> None:
    gates = Worklist.from_items(
        name="gate",
        items=({"id": "alpha", "title": "Alpha", "payload": {}},),
    )
    selection = gates.initial_selection(
        Context(
            task_id="task-1",
            run_id="run-1",
            workflow_name="example",
            task_folder=tmp_path / "task",
            workflow_folder=tmp_path / "task" / "wf_example",
            run_folder=tmp_path / "run",
            package_folder=tmp_path / "package",
            state=_State(),
            session_store=InMemorySessionStore(),
            worklists={"gate": gates},
            selections={},
        )
    )
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        worklists={"gate": gates},
        selections={"gate": selection},
    )
    context._execution_frame.set_active_worklist("gate")

    with pytest.raises(
        WorkflowExecutionError,
        match=r"artifact template placeholder \{item\.payload\.foo\} references missing payload path 'foo' on worklist 'gate'",
    ):
        resolve_artifact_template("{workflow_folder}/{item.payload.foo}.md", context)


def test_artifact_template_resolution_reports_missing_current_item(tmp_path: Path) -> None:
    gates = Worklist.from_items(name="gate", items=())
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        worklists={"gate": gates},
        selections={"gate": gates.initial_selection(
            Context(
                task_id="task-1",
                run_id="run-1",
                workflow_name="example",
                task_folder=tmp_path / "task",
                workflow_folder=tmp_path / "task" / "wf_example",
                run_folder=tmp_path / "run",
                package_folder=tmp_path / "package",
                state=_State(),
                session_store=InMemorySessionStore(),
                worklists={"gate": gates},
                selections={},
            )
        )},
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"artifact template placeholder \{worklist\.gate\.current\.id\} requires a current item on worklist 'gate'",
    ):
        resolve_artifact_template("{workflow_folder}/{worklist.gate.current.id}.md", context)


def test_artifact_template_resolution_reports_worklist_source_loading_failure(tmp_path: Path) -> None:
    gate_board = Artifact.json("{task_folder}/gates.json", required=True)
    gates = Worklist.from_artifact(
        name="gate",
        artifact=gate_board,
        collection="gates",
        item_id="gate_id",
        title="title",
    )
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        worklists={"gate": gates},
        selections={},
    )
    runtime = context._execution_frame

    def _resolve(worklist_name: str):
        selection = gates.initial_selection(context)
        runtime.set_selection(worklist_name, selection)
        return selection

    runtime.set_worklist_selection_resolver(_resolve)

    with pytest.raises(
        WorkflowExecutionError,
        match=r"artifact template placeholder \{worklist\.gate\.current\.id\} could not load worklist 'gate'",
    ):
        resolve_artifact_template("{workflow_folder}/{worklist.gate.current.id}.md", context)


def test_worklist_load_items_is_cached_per_context(tmp_path: Path) -> None:
    calls: list[str] = []

    class Source:
        mutable = False
        artifact_backed = True

        def load(self, ctx):
            calls.append(ctx.run_id)
            return (WorkItem(id="alpha", title="Alpha", payload={"id": "alpha"}),)

        def save(self, ctx, items):
            return None

        def validate(self, ctx, items):
            return None

    worklist = Worklist(name="gate", source=Source())
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
    )

    first = worklist.load_items(context)
    second = worklist.load_items(context)

    assert first == second
    assert calls == ["run-1"]


def test_worklist_set_current_status_refreshes_cached_items_for_mutable_sources(tmp_path: Path) -> None:
    load_calls: list[str] = []
    saved_statuses: list[list[str | None]] = []

    class Source:
        mutable = True
        artifact_backed = True

        def load(self, ctx):
            load_calls.append(ctx.run_id)
            return (
                WorkItem(id="alpha", title="Alpha", payload={"id": "alpha"}),
                WorkItem(id="beta", title="Beta", payload={"id": "beta"}),
            )

        def save(self, ctx, items):
            saved_statuses.append([item.status for item in items])

        def validate(self, ctx, items):
            return None

    worklist = Worklist(
        name="gate",
        source=Source(),
        selector=Selector(item_param="selected", mode_param="mode", allowed_modes=("all", "single")),
    )
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        workflow_params={"selected": "beta", "mode": "single"},
    )

    selection = worklist.initial_selection(context)
    updated = worklist.set_current_status(context, selection, "done")
    cached = worklist.load_items(context)

    assert updated.current is not None
    assert updated.current.status == "done"
    assert tuple(item.id for item in cached) == ("alpha", "beta")
    assert [item.status for item in cached] == [None, None]
    assert load_calls == ["run-1", "run-1"]
    assert saved_statuses == [["done"]]


def test_worklist_runtime_view_refresh_reloads_mutable_source(tmp_path: Path) -> None:
    source_items = [
        WorkItem(id="alpha", title="Alpha", payload={"id": "alpha"}),
    ]
    load_calls: list[int] = []

    class Source:
        mutable = True
        artifact_backed = True

        def load(self, ctx):
            load_calls.append(len(source_items))
            return tuple(source_items)

        def save(self, ctx, items):
            return None

        def validate(self, ctx, items):
            return None

    worklist = Worklist(name="gate", source=Source())
    base_context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
    )
    selection = worklist.initial_selection(base_context)
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        worklists={"gate": worklist},
        selections={"gate": selection},
        active_worklist="gate",
    )
    context._execution_frame.cache_worklist_items("gate", base_context._execution_frame.get_cached_worklist_items("gate"))

    source_items[:] = [WorkItem(id="alpha", title="Renamed Alpha", payload={"id": "alpha"})]

    refreshed = context.current_worklist.refresh()

    assert refreshed.current is not None
    assert refreshed.current.title == "Renamed Alpha"
    assert context.current_worklist.current is not None
    assert context.current_worklist.current.title == "Renamed Alpha"
    assert load_calls == [1, 1]


def test_worklist_runtime_view_validate_reloads_mutable_source_and_reports_missing_selected_item(tmp_path: Path) -> None:
    source_items = [
        WorkItem(id="alpha", title="Alpha", payload={"id": "alpha"}),
    ]
    load_calls: list[int] = []

    class Source:
        mutable = True
        artifact_backed = True

        def load(self, ctx):
            load_calls.append(len(source_items))
            return tuple(source_items)

        def save(self, ctx, items):
            return None

        def validate(self, ctx, items):
            return None

    worklist = Worklist(name="gate", source=Source())
    base_context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
    )
    selection = worklist.initial_selection(base_context)
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        worklists={"gate": worklist},
        selections={"gate": selection},
        active_worklist="gate",
    )
    context._execution_frame.cache_worklist_items("gate", base_context._execution_frame.get_cached_worklist_items("gate"))

    source_items.clear()

    error = context.current_worklist.validation_error()

    assert error == "worklist 'gate' selection references missing item id(s): alpha"
    assert load_calls == [1, 0]


def test_worklist_runtime_view_refresh_raises_when_mutable_source_drops_selected_item(tmp_path: Path) -> None:
    source_items = [
        WorkItem(id="alpha", title="Alpha", payload={"id": "alpha"}),
    ]
    load_calls: list[int] = []

    class Source:
        mutable = True
        artifact_backed = True

        def load(self, ctx):
            load_calls.append(len(source_items))
            return tuple(source_items)

        def save(self, ctx, items):
            return None

        def validate(self, ctx, items):
            return None

    worklist = Worklist(name="gate", source=Source())
    base_context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
    )
    selection = worklist.initial_selection(base_context)
    context = Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="example",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_example",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        worklists={"gate": worklist},
        selections={"gate": selection},
        active_worklist="gate",
    )
    context._execution_frame.cache_worklist_items("gate", base_context._execution_frame.get_cached_worklist_items("gate"))

    source_items.clear()

    with pytest.raises(WorkflowExecutionError, match="cannot refresh missing item 'alpha'"):
        context.current_worklist.refresh()

    assert load_calls == [1, 0]
