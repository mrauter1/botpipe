from __future__ import annotations

import importlib.util
import re
import sys
from uuid import uuid4

from tests.contract.engine._shared import (
    _ConfigurableRenderedTransport,
    _RenderedTransportStub,
    _load_replay_store,
    _chain_hooks,
    _rendered_provider_with_operation_executor,
    _workspace,
)
from tests.contract.engine._shared import *

INVALID_OPERATION_REPLAY_V3 = "unsupported.operation_replay/v3"

def test_low_level_engine_requires_prompt_registry_for_relative_file_prompts(tmp_path: Path):
    (tmp_path / "ask.md").write_text("Answer the request.\n", encoding="utf-8")

    def _filepromptworkflow_on_ask(ctx):
        return None

    class FilePromptWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer=Prompt.file("ask.md"), retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    transport = _RenderedTransportStub()
    provider = RenderedLLMProvider(transport)

    with pytest.raises(ProviderExecutionError, match="did not resolve to text"):
        Engine(
            FilePromptWorkflow,
            provider=provider,
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-file-prompt-missing-registry",
            run_id="run-file-prompt-missing-registry",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    assert transport.turns == []
def test_low_level_engine_resolves_relative_file_prompts_with_filesystem_registry(tmp_path: Path):
    prompt_path = tmp_path / "ask.md"
    prompt_path.write_text("Answer the request.\n", encoding="utf-8")

    def _filepromptworkflow_on_ask(ctx):
        return None

    class FilePromptWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer=Prompt.file("ask.md"), retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    transport = _RenderedTransportStub()
    result = Engine(
        FilePromptWorkflow,
        provider=_rendered_provider_with_operation_executor(transport),
        prompt_registry=FilesystemPromptRegistry(tmp_path),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-file-prompt-with-registry",
        run_id="run-file-prompt-with-registry",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert len(transport.turns) == 1
    assert "Answer the request." in transport.turns[0].prompt_text


def test_file_prompt_uses_jinja_context_features_and_preserves_single_brace_literals(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "include.md").write_text("Included: {{ workflow.name }}\n", encoding="utf-8")
    (prompts_dir / "ask.md").write_text(
        "\n".join(
            (
                "Message={{ message }}",
                "Request={{ request.text }}",
                "Input={{ input.topic }}",
                "Param={{ params.mode }}",
                "State={{ state.status }}",
                "{% if input.topic == 'release' %}Conditional=yes{% endif %}",
                "{% for artifact in artifacts %}Artifact={{ artifact.name }}:{{ artifact.path.name }}{% endfor %}",
                "{% include 'include.md' %}",
                "Literal JSON: {\"status\": \"ready\"}",
                "{% raw %}Raw Jinja: {{ not_rendered }}{% endraw %}",
                "Old syntax stays literal: {ctx.message}",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    class JinjaPromptWorkflow(SimpleWorkflow):
        class Input(BaseModel):
            topic: str

        class Params(BaseModel):
            mode: str = "strict"

        class State(BaseModel):
            status: str = "draft"

        draft = Md("draft")
        ask = step(prompt=Prompt.file("prompts/ask.md"), writes=[draft])

    task_folder, run_folder = _workspace(tmp_path)
    (run_folder / "request.md").write_text("Review this change.\n", encoding="utf-8")
    captured: dict[str, str] = {}
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                captured.__setitem__("prompt", request.prompt.text),
                Outcome(raw_output="done", tag="done"),
            )[1]
        ]
    )

    result = Engine(
        JinjaPromptWorkflow,
        provider=provider,
        prompt_registry=FilesystemPromptRegistry(tmp_path),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-jinja-file-prompt",
        run_id="run-jinja-file-prompt",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        params=JinjaPromptWorkflow.Params(mode="strict"),
        workflow_input=JinjaPromptWorkflow.Input(topic="release"),
    )

    assert result.terminal == FINISH
    rendered = captured["prompt"]
    assert "Message=Review this change." in rendered
    assert "Request=Review this change." in rendered
    assert "Input=release" in rendered
    assert "Param=strict" in rendered
    assert "State=draft" in rendered
    assert "Conditional=yes" in rendered
    assert "Artifact=draft:draft.md" in rendered
    assert "Included: jinja_prompt_workflow" in rendered
    assert 'Literal JSON: {"status": "ready"}' in rendered
    assert "Raw Jinja: {{ not_rendered }}" in rendered
    assert "Old syntax stays literal: {ctx.message}" in rendered
    assert "{{ message }}" not in rendered


def test_file_prompt_rejects_include_path_escape(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (tmp_path / "secret.md").write_text("secret\n", encoding="utf-8")
    (prompts_dir / "ask.md").write_text("{% include '../secret.md' %}\n", encoding="utf-8")

    class EscapeIncludeWorkflow(SimpleWorkflow):
        class State(BaseModel):
            pass

        ask = step(prompt=Prompt.file("prompts/ask.md"))

    task_folder, run_folder = _workspace(tmp_path)
    with pytest.raises(WorkflowExecutionError, match="unsafe Jinja template path"):
        Engine(
            EscapeIncludeWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="done", tag="done")]),
            prompt_registry=FilesystemPromptRegistry(tmp_path),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-jinja-escape",
            run_id="run-jinja-escape",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


def test_symlinked_file_prompt_includes_from_lexical_prompt_directory(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "prompts"
    shared_dir = tmp_path / "shared"
    prompts_dir.mkdir()
    shared_dir.mkdir()
    (prompts_dir / "local.md").write_text("Included from lexical root\n", encoding="utf-8")
    (shared_dir / "local.md").write_text("Included from symlink target root\n", encoding="utf-8")
    (shared_dir / "ask.md").write_text("Prompt\n{% include 'local.md' %}", encoding="utf-8")
    (prompts_dir / "ask.md").symlink_to(shared_dir / "ask.md")

    class SymlinkPromptWorkflow(SimpleWorkflow):
        class State(BaseModel):
            pass

        ask = step(prompt=Prompt.file("prompts/ask.md"))

    task_folder, run_folder = _workspace(tmp_path)
    captured: dict[str, str] = {}
    result = Engine(
        SymlinkPromptWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: (
                    captured.__setitem__("prompt", request.prompt.text),
                    Outcome(raw_output="done", tag="done"),
                )[1]
            ]
        ),
        prompt_registry=FilesystemPromptRegistry(tmp_path),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-symlink-prompt",
        run_id="run-symlink-prompt",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert "Included from lexical root" in captured["prompt"]
    assert "Included from symlink target root" not in captured["prompt"]


@pytest.mark.parametrize(
    ("prompt_path_factory", "expected"),
    [
        (lambda root: str((root / "absolute.md").absolute()), "absolute prompt"),
        (lambda root: "../outside/ask.md", "outside prompt"),
    ],
)
def test_file_prompt_allows_absolute_and_parent_relative_paths(
    tmp_path: Path,
    prompt_path_factory,
    expected: str,
) -> None:
    workflow_root = tmp_path / "workflow"
    outside_root = tmp_path / "outside"
    workflow_root.mkdir()
    outside_root.mkdir()
    (tmp_path / "absolute.md").write_text("{{ input.topic }} absolute prompt\n", encoding="utf-8")
    (outside_root / "ask.md").write_text("{{ input.topic }} outside prompt\n", encoding="utf-8")
    prompt_path = prompt_path_factory(tmp_path)

    class PermissiveFilePromptWorkflow(SimpleWorkflow):
        class Input(BaseModel):
            topic: str

        class State(BaseModel):
            pass

        ask = step(prompt=Prompt.file(prompt_path))

    workflow_name_suffix = expected.replace(" ", "_")
    PermissiveFilePromptWorkflow.__name__ = f"PermissiveFilePromptWorkflow_{workflow_name_suffix}"
    PermissiveFilePromptWorkflow.__qualname__ = PermissiveFilePromptWorkflow.__name__

    task_folder, run_folder = _workspace(tmp_path)
    captured: dict[str, str] = {}
    result = Engine(
        PermissiveFilePromptWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: (
                    captured.__setitem__("prompt", request.prompt.text),
                    Outcome(raw_output="done", tag="done"),
                )[1]
            ]
        ),
        prompt_registry=FilesystemPromptRegistry(workflow_root),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-permissive-file-prompt",
        run_id="run-permissive-file-prompt",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_input=PermissiveFilePromptWorkflow.Input(topic="release"),
    )

    assert result.terminal == FINISH
    assert captured["prompt"] == f"release {expected}\n"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("{{ missing_value }}\n", "unknown Jinja variable"),
        ("{% if message %}\n", "Jinja syntax error"),
    ],
)
def test_file_prompt_reports_strict_jinja_template_errors(tmp_path: Path, body: str, message: str) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "ask.md").write_text(body, encoding="utf-8")

    class InvalidJinjaWorkflow(SimpleWorkflow):
        class State(BaseModel):
            pass

        ask = step(prompt=Prompt.file("prompts/ask.md"))

    task_folder, run_folder = _workspace(tmp_path)
    with pytest.raises(WorkflowExecutionError, match=message):
        Engine(
            InvalidJinjaWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="done", tag="done")]),
            prompt_registry=FilesystemPromptRegistry(tmp_path),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-jinja-invalid",
            run_id="run-jinja-invalid",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("{{ missing_value }}\n", "unknown Jinja variable"),
        ("{% include 'missing.md' %}\n", "missing Jinja template"),
    ],
)
def test_compile_workflow_validates_file_prompt_jinja_templates(tmp_path: Path, body: str, message: str) -> None:
    package_dir = tmp_path / "workflow_pkg"
    prompts_dir = package_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "ask.md").write_text(body, encoding="utf-8")
    workflow_path = package_dir / "workflow.py"
    workflow_path.write_text(
        """
from pydantic import BaseModel
from botpipe import Prompt, Workflow, step


class CompileJinjaWorkflow(Workflow):
    class State(BaseModel):
        pass

    ask = step(prompt=Prompt.file("prompts/ask.md"))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    module_name = f"compile_jinja_workflow_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, workflow_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        with pytest.raises(WorkflowValidationError, match=message):
            compile_workflow(module.CompileJinjaWorkflow)
    finally:
        sys.modules.pop(module_name, None)


@pytest.mark.parametrize(
    ("files", "message"),
    [
        (
            {"ask.md": "{% include 'nested.md' %}\n", "nested.md": "{{ missing_value }}\n"},
            "nested.md.*unknown Jinja variable",
        ),
        (
            {"ask.md": "{% include 'nested.md' %}\n", "nested.md": "{% if message %}\n"},
            "nested.md.*Jinja syntax error",
        ),
        (
            {"ask.md": "{% include 'nested.md' %}\n", "nested.md": "{% include 'missing.md' %}\n"},
            "nested.md.*missing Jinja template",
        ),
        (
            {"ask.md": "{% include 'nested.md' %}\n", "nested.md": "{% include '../secret.md' %}\n"},
            "nested.md.*unsafe Jinja template path",
        ),
    ],
)
def test_compile_workflow_recursively_validates_file_prompt_includes(
    tmp_path: Path,
    files: dict[str, str],
    message: str,
) -> None:
    package_dir = tmp_path / "workflow_pkg"
    prompts_dir = package_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    for name, body in files.items():
        (prompts_dir / name).write_text(body, encoding="utf-8")
    workflow_path = package_dir / "workflow.py"
    workflow_path.write_text(
        """
from pydantic import BaseModel
from botpipe import Prompt, Workflow, step


class CompileNestedJinjaWorkflow(Workflow):
    class State(BaseModel):
        pass

    ask = step(prompt=Prompt.file("prompts/ask.md"))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    module_name = f"compile_nested_jinja_workflow_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, workflow_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        with pytest.raises(WorkflowValidationError, match=message):
            compile_workflow(module.CompileNestedJinjaWorkflow)
    finally:
        sys.modules.pop(module_name, None)


def test_step_contract_keeps_missing_workspace_reads_visible_as_unavailable_context(tmp_path: Path):
    def _missingreadworkflow_on_ask(ctx):
        return None

    class MissingReadWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md", reads=["notes/missing.txt"])
        entry = ask
        transitions = {ask: {"done": FINISH}}

    MissingReadWorkflow.ask.after = _chain_hooks(_missingreadworkflow_on_ask, MissingReadWorkflow.ask.after)

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])
    result = Engine(
        MissingReadWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert len(provider.calls) == 1
    readable_ref = provider.calls[0].readable_artifacts[0]
    assert readable_ref.name == "notes/missing.txt"
    assert readable_ref.path == str((tmp_path / "notes/missing.txt").resolve())
    assert readable_ref.exists is False
    assert readable_ref.declared_artifact is False
def test_prompt_runtime_reports_missing_payload_path_with_jinja_context(tmp_path: Path):
    class MissingPayloadPromptWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(
            name="gate",
            items=({"id": "alpha", "title": "Alpha", "payload": {}},),
        )
        assess = PromptStep(
            name="assess",
            producer=Prompt.inline("Inspect {{ item.payload.foo }}."),
            scope=gates,
        )
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        MissingPayloadPromptWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"prompt placeholder on step 'assess' <inline prompt template>: undefined Jinja value: .*foo",
    ):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_operation_prompt_runtime_reports_missing_payload_path_with_jinja_context(tmp_path: Path):
    def _missingpayloadoperationworkflow_on_assess(ctx):
        llm("Inspect {{ item.payload.foo }}.")
        return None

    class MissingPayloadOperationWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(
            name="gate",
            items=({"id": "alpha", "title": "Alpha", "payload": {}},),
        )
        assess = PromptStep(
            name="assess",
            producer=Prompt.inline("Assess the current item."),
            scope=gates,
        )
        entry = assess
        transitions = {assess: {"done": FINISH}}

    MissingPayloadOperationWorkflow.assess.before = _chain_hooks(
        _missingpayloadoperationworkflow_on_assess,
        MissingPayloadOperationWorkflow.assess.before,
    )

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        MissingPayloadOperationWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"operation prompt placeholder on step 'assess' <inline prompt template>: undefined Jinja value: .*foo",
    ):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_python_step_feedforward_helpers_accept_plain_string_prompts_with_rendered_provider(tmp_path: Path) -> None:
    class Summary(BaseModel):
        title: str

    class HelperWorkflow(SimpleWorkflow):
        class State(BaseModel):
            title: str = ""
            risk: str = ""

        @python_step
        def produce(ctx):
            summary = llm("Generate a summary.", returns=Summary)
            risk = classify("Classify risk.", choices=["low", "medium", "high"])
            ctx.state = ctx.state.model_copy(update={"title": summary.title, "risk": risk})
            return None

    task_folder, run_folder = _workspace(tmp_path)
    transport = _RenderedTransportStub(raw_texts=['{"title":"Rendered summary"}', "medium"])

    result = Engine(
        HelperWorkflow,
        provider=_rendered_provider_with_operation_executor(transport),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-helper-rendered",
        run_id="run-helper-rendered",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.title == "Rendered summary"
    assert result.state.risk == "medium"
    assert [turn.turn_kind for turn in transport.turns] == ["operation", "operation"]
    assert "Generate a summary." in transport.turns[0].prompt_text
    assert "Classify risk." in transport.turns[1].prompt_text
def test_jinja_prompt_bindings_render_in_provider_and_operation_prompts(tmp_path: Path) -> None:
    class PromptBindingWorkflow(SimpleWorkflow):
        class Input(BaseModel):
            topic: str

        class Params(BaseModel):
            mode: str = "brief"

        class State(BaseModel):
            status: str = "draft"

        summary = step(
            "Message={{ message }}; Topic={{ input.topic }}; Mode={{ params.mode }}; Status={{ state.status }}",
            routes={"done": "review"},
        )
        review = produce_verify_step(
            producer_prompt="Produce {{ message }}; topic={{ input.topic }}; mode={{ params.mode }}; status={{ state.status }}",
            verifier_prompt="Verify {{ message }}; topic={{ input.topic }}; mode={{ params.mode }}; status={{ state.status }}",
            routes={"approved": "risk"},
        )
        risk = llm.step(
            prompt="Risk for {{ message }}; topic={{ input.topic }}; mode={{ params.mode }}; status={{ state.status }}",
            returns=str,
        )
        kind = classify.step(
            prompt="Classify {{ message }} for {{ input.topic }}",
            choices=["bug", "feature"],
        )

        @python_step(routes={"done": FINISH})
        def finish(ctx):
            assert ctx.values.risk == "medium"
            assert ctx.values.kind == "feature"
            return "done"

    task_folder, run_folder = _workspace(tmp_path)
    (run_folder / "request.md").write_text("Ship the release safely.\n", encoding="utf-8")
    captured: dict[str, object] = {"operations": []}
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                captured.__setitem__("step", request.prompt.text),
                Outcome(raw_output="done", tag="done"),
            )[1]
        ],
        producer_turns=[
            lambda request: (
                captured.__setitem__("producer", request.producer_prompt.text),
                "producer draft",
            )[1]
        ],
        verifier_turns=[
            lambda request: (
                captured.__setitem__("verifier", request.verifier_prompt.text),
                Outcome(raw_output="approved", tag="approved"),
            )[1]
        ],
        operation_turns=[
            lambda request: (
                cast(list[str], captured["operations"]).append(request.prompt.text),
                "medium",
            )[1],
            lambda request: (
                cast(list[str], captured["operations"]).append(request.prompt.text),
                "feature",
            )[1],
        ],
    )

    result = Engine(
        PromptBindingWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-ctx-prompts",
        run_id="run-ctx-prompts",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        params=PromptBindingWorkflow.Params(mode="brief"),
        workflow_input=PromptBindingWorkflow.Input(topic="release"),
    )

    assert result.terminal == FINISH
    assert captured["step"] == "Message=Ship the release safely.; Topic=release; Mode=brief; Status=draft"
    assert captured["producer"] == "Produce Ship the release safely.; topic=release; mode=brief; status=draft"
    assert captured["verifier"] == "Verify Ship the release safely.; topic=release; mode=brief; status=draft"
    operation_prompts = cast(list[str], captured["operations"])
    assert operation_prompts == [
        "Risk for Ship the release safely.; topic=release; mode=brief; status=draft",
        "Classify Ship the release safely. for release",
    ]
    rendered_prompts = [
        cast(str, captured["step"]),
        cast(str, captured["producer"]),
        cast(str, captured["verifier"]),
        *operation_prompts,
    ]
    assert all("{{" not in text for text in rendered_prompts)


def test_inline_prompt_preserves_legacy_single_brace_literals(tmp_path: Path) -> None:
    class LegacyLiteralWorkflow(SimpleWorkflow):
        class Input(BaseModel):
            topic: str

        class State(BaseModel):
            pass

        summary = step("Old={ctx.message}; Input={input.topic}; New={{ input.topic }}", routes={"done": FINISH})

    task_folder, run_folder = _workspace(tmp_path)
    (run_folder / "request.md").write_text("Natural-language request\n", encoding="utf-8")
    captured: dict[str, str] = {}
    result = Engine(
        LegacyLiteralWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: (
                    captured.__setitem__("prompt", request.prompt.text),
                    Outcome(raw_output="done", tag="done"),
                )[1]
            ]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-inline-legacy-literal",
        run_id="run-inline-legacy-literal",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_input=LegacyLiteralWorkflow.Input(topic="release"),
    )

    assert result.terminal == FINISH
    assert captured["prompt"] == "Old={ctx.message}; Input={input.topic}; New=release"


def test_prompt_message_root_requires_readable_request_snapshot_only_when_referenced(tmp_path: Path) -> None:
    class NoMessageReferenceWorkflow(SimpleWorkflow):
        class State(BaseModel):
            pass

        summary = step("Workflow={{ workflow.name }}", routes={"done": FINISH})

    class MessageReferenceWorkflow(SimpleWorkflow):
        class State(BaseModel):
            pass

        summary = step("Message={{ message }}", routes={"done": FINISH})

    task_folder, run_folder = _workspace(tmp_path)
    captured: dict[str, str] = {}
    result = Engine(
        NoMessageReferenceWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: (
                    captured.__setitem__("prompt", request.prompt.text),
                    Outcome(raw_output="done", tag="done"),
                )[1]
            ]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-no-message-reference",
        run_id="run-no-message-reference",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert captured["prompt"] == "Workflow=no_message_reference_workflow"

    with pytest.raises(WorkflowExecutionError, match=r"run request snapshot could not be read: .*request\.md"):
        Engine(
            MessageReferenceWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="done", tag="done")]),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-message-reference",
            run_id="run-message-reference",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_runtime_templates_resolve_message_and_typed_input_fields(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir()
    (run_folder / "request.md").write_text("artifact-request\n", encoding="utf-8")

    class PromptInput(BaseModel):
        topic: str

    class PromptState(BaseModel):
        status: str = "draft"

    context = Context(
        task_id="task-bare-input-template",
        run_id="run-bare-input-template",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=PromptState(),
        workflow_input=PromptInput(topic="release"),
        session_store=InMemorySessionStore(),
    )

    rendered = render_runtime_template(
        "Message={{ message }}; Topic={{ input.topic }}",
        context,
        placeholder_label="artifact template placeholder",
    )
    resolved = resolve_artifact_template("outputs/{{ message }}-{{ input.topic }}.md", context)

    assert rendered == "Message=artifact-request; Topic=release"
    assert resolved == Path("outputs") / "artifact-request-release.md"
def test_runtime_templates_reject_unknown_bare_input_field(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir()
    (run_folder / "request.md").write_text("artifact-request\n", encoding="utf-8")

    class PromptInput(BaseModel):
        topic: str

    class PromptState(BaseModel):
        status: str = "draft"

    context = Context(
        task_id="task-bare-input-template-error",
        run_id="run-bare-input-template-error",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=PromptState(),
        workflow_input=PromptInput(topic="release"),
        session_store=InMemorySessionStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"undefined Jinja value: .*missing",
    ):
        render_runtime_template(
            "{{ input.missing }}",
            context,
            placeholder_label="artifact template placeholder",
        )
def test_runtime_templates_resolve_message_without_typed_input(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir()
    (run_folder / "request.md").write_text("artifact-request\n", encoding="utf-8")

    class PromptState(BaseModel):
        status: str = "draft"

    context = Context(
        task_id="task-ctx-input-message",
        run_id="run-ctx-input-message",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=PromptState(),
        session_store=InMemorySessionStore(),
    )

    rendered = render_runtime_template(
        "{{ message }}",
        context,
        placeholder_label="artifact template placeholder",
    )

    assert rendered == "artifact-request"
def test_runtime_templates_resolve_message_separately_from_typed_input(tmp_path: Path) -> None:
    task_folder = tmp_path / "task"
    workflow_folder = task_folder / "wf_example"
    run_folder = workflow_folder / "runs" / "run-1"
    package_folder = tmp_path / "package"
    run_folder.mkdir(parents=True)
    package_folder.mkdir()
    (run_folder / "request.md").write_text("artifact-request\n", encoding="utf-8")

    class PromptInput(BaseModel):
        topic: str

    class PromptState(BaseModel):
        status: str = "draft"

    context = Context(
        task_id="task-ctx-input-message",
        run_id="run-ctx-input-message",
        workflow_name="example",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=package_folder,
        state=PromptState(),
        message="runtime-message",
        workflow_input=PromptInput(topic="release"),
        session_store=InMemorySessionStore(),
    )

    rendered = render_runtime_template(
        "Request={{ message }}; Topic={{ input.topic }}",
        context,
        placeholder_label="artifact template placeholder",
    )

    assert rendered == "Request=runtime-message; Topic=release"
def test_prompt_steps_do_not_auto_inject_run_message_without_ctx_binding(tmp_path: Path) -> None:
    class NoAutoInjectionWorkflow(SimpleWorkflow):
        summary = step("Write a generic summary.", routes={"done": FINISH})

    task_folder, run_folder = _workspace(tmp_path)
    (run_folder / "request.md").write_text("THIS SHOULD NOT APPEAR UNLESS BOUND\n", encoding="utf-8")
    captured: dict[str, str] = {}
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                captured.__setitem__("step", request.prompt.text),
                Outcome(raw_output="done", tag="done"),
            )[1]
        ]
    )

    result = Engine(
        NoAutoInjectionWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-no-auto-injection",
        run_id="run-no-auto-injection",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert captured["step"] == "Write a generic summary."
    assert "THIS SHOULD NOT APPEAR UNLESS BOUND" not in captured["step"]
def test_engine_context_message_raises_when_run_snapshot_is_removed_after_context_construction(tmp_path: Path) -> None:
    class MissingSnapshotWorkflow(SimpleWorkflow):
        @python_step(routes={"done": FINISH})
        def remove_snapshot_then_read(ctx):
            ctx.request_file.unlink()
            _ = ctx.message
            return "done"

    task_folder, run_folder = _workspace(tmp_path)
    (run_folder / "request.md").write_text("Natural-language request\n", encoding="utf-8")

    engine = Engine(
        MissingSnapshotWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(WorkflowExecutionError, match=r"run request snapshot could not be read: .*request\.md"):
        engine.run(
            task_id="task-missing-snapshot",
            run_id="run-missing-snapshot",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_python_step_feedforward_helpers_require_operation_executor_for_rendered_provider_in_active_loop(
    tmp_path: Path,
) -> None:
    class Summary(BaseModel):
        title: str

    class HelperWorkflow(SimpleWorkflow):
        class State(BaseModel):
            title: str = ""

        @python_step
        def produce(ctx):
            summary = llm("Generate a summary.", returns=Summary)
            ctx.state = ctx.state.model_copy(update={"title": summary.title})
            return None

    task_folder, run_folder = _workspace(tmp_path)
    transport = _RenderedTransportStub(raw_text='{"title":"Rendered summary"}')

    with pytest.raises(RuntimeError, match="requires an explicit operation_executor"):
        Engine(
            HelperWorkflow,
            provider=RenderedLLMProvider(transport),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-helper-rendered-missing-executor",
            run_id="run-helper-rendered-missing-executor",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    assert transport.turns == []
def test_operation_replay_fingerprint_mismatch_warns_and_reuses_cached_value_by_default(tmp_path: Path) -> None:
    class FirstWorkflow(SimpleWorkflow):
        name = "operation_replay"
        summary = llm.step(prompt="Summarize version one.", returns=str)

    class SecondWorkflow(SimpleWorkflow):
        name = "operation_replay"
        summary = llm.step(prompt="Summarize version two.", returns=str)

    task_folder, run_folder = _workspace(tmp_path)

    Engine(
        FirstWorkflow,
        provider=ScriptedLLMProvider(operation_turns=["first result"]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-mismatch",
        run_id="run-mismatch",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    runtime_events: list[tuple[str, dict[str, object]]] = []
    result = Engine(
        SecondWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-mismatch",
        run_id="run-mismatch",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert runtime_events[-1][0] == "operation_replay_fingerprint_mismatch"
    assert runtime_events[-1][1]["behavior"] == "warn"
def test_operation_replay_fingerprint_mismatch_fails_in_strict_mode(tmp_path: Path) -> None:
    class FirstWorkflow(SimpleWorkflow):
        name = "operation_replay"
        summary = llm.step(prompt="Summarize version one.", returns=str)

    class SecondWorkflow(SimpleWorkflow):
        name = "operation_replay"
        summary = llm.step(prompt="Summarize version two.", returns=str)

    task_folder, run_folder = _workspace(tmp_path)

    Engine(
        FirstWorkflow,
        provider=ScriptedLLMProvider(operation_turns=["first result"]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-mismatch-strict",
        run_id="run-mismatch-strict",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    with pytest.raises(ProviderExecutionError, match="operation replay fingerprint mismatch"):
        Engine(
            SecondWorkflow,
            provider=ScriptedLLMProvider(),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
            operation_replay_mismatch_behavior="fail",
        ).run(
            task_id="task-mismatch-strict",
            run_id="run-mismatch-strict",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_operation_replay_fingerprint_includes_provider_configuration(tmp_path: Path) -> None:
    class ConfiguredWorkflow(SimpleWorkflow):
        name = "operation_replay"
        summary = llm.step(prompt="Summarize version one.", returns=str)

    task_folder, run_folder = _workspace(tmp_path)

    Engine(
        ConfiguredWorkflow,
        provider=_rendered_provider_with_operation_executor(_ConfigurableRenderedTransport(model="gpt-5.5")),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-provider-mismatch",
        run_id="run-provider-mismatch",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    runtime_events: list[tuple[str, dict[str, object]]] = []
    result = Engine(
        ConfiguredWorkflow,
        provider=_rendered_provider_with_operation_executor(_ConfigurableRenderedTransport(model="gpt-5.4")),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-provider-mismatch",
        run_id="run-provider-mismatch",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert runtime_events[-1][0] == "operation_replay_fingerprint_mismatch"
    assert runtime_events[-1][1]["behavior"] == "warn"
@pytest.mark.parametrize(
    ("payload", "expected_attempts"),
    [
        ({"records": {"legacy": {"value": "stale"}}, "attempts": ["first"]}, ["first"]),
    ],
)
def test_operation_replay_store_migrates_only_schemaless_payloads(
    tmp_path: Path,
    payload: dict[str, object],
    expected_attempts: list[str],
) -> None:
    replay_path = tmp_path / "operation_replay.json"
    replay_path.write_text(json.dumps(payload), encoding="utf-8")

    replay_store = _load_replay_store(replay_path)

    assert replay_store == {
        "schema": OPERATION_REPLAY_SCHEMA,
        "records": {},
        "attempts": expected_attempts,
    }
def test_operation_replay_store_rejects_unsupported_schema_versions(tmp_path: Path) -> None:
    replay_path = tmp_path / "operation_replay.json"
    replay_path.write_text(
        json.dumps(
            {
                "schema": INVALID_OPERATION_REPLAY_V3,
                "records": {"legacy": {"value": "stale"}},
                "attempts": ["first"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=rf"uses unsupported schema '{re.escape(INVALID_OPERATION_REPLAY_V3)}'"):
        _load_replay_store(replay_path)
def test_inline_operation_provider_override_participates_in_replay_fingerprint(tmp_path: Path) -> None:
    first_override = _rendered_provider_with_operation_executor(
        _ConfigurableRenderedTransport(model="gpt-5.5", raw_text="first override")
    )
    second_override = _rendered_provider_with_operation_executor(
        _ConfigurableRenderedTransport(model="gpt-5.4", raw_text="second override")
    )
    override_provider_ref = {"provider": first_override}

    class OverrideWorkflow(SimpleWorkflow):
        name = "operation_replay_override"

        class State(BaseModel):
            summary: str = ""

        @python_step
        def produce(ctx):
            summary = llm("Summarize the override provider.", provider=override_provider_ref["provider"])
            ctx.state = ctx.state.model_copy(update={"summary": summary})
            return None

    task_folder, run_folder = _workspace(tmp_path)

    Engine(
        OverrideWorkflow,
        provider=_rendered_provider_with_operation_executor(_ConfigurableRenderedTransport(model="ambient")),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-provider-override-mismatch",
        run_id="run-provider-override-mismatch",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    override_provider_ref["provider"] = second_override
    runtime_events: list[tuple[str, dict[str, object]]] = []
    result = Engine(
        OverrideWorkflow,
        provider=_rendered_provider_with_operation_executor(_ConfigurableRenderedTransport(model="ambient")),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-provider-override-mismatch",
        run_id="run-provider-override-mismatch",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.summary == "first override"
    assert runtime_events[-1][0] == "operation_replay_fingerprint_mismatch"
    assert runtime_events[-1][1]["behavior"] == "warn"
    assert len(first_override._transport.turns) == 1
    assert len(second_override._transport.turns) == 0
