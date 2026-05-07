from __future__ import annotations

from tests.contract.engine._shared import *

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
def test_prompt_runtime_reports_missing_payload_path_with_placeholder_context(tmp_path: Path):
    class MissingPayloadPromptWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(
            name="gate",
            items=({"id": "alpha", "title": "Alpha", "payload": {}},),
        )
        assess = PromptStep(
            name="assess",
            producer=Prompt.inline("Inspect {item.payload.foo}."),
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
        match=r"prompt placeholder on step 'assess' \{item\.payload\.foo\} references missing payload path 'foo' on worklist 'gate'",
    ):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_operation_prompt_runtime_reports_missing_payload_path_with_placeholder_context(tmp_path: Path):
    def _missingpayloadoperationworkflow_on_assess(ctx):
        llm("Inspect {item.payload.foo}.")
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
        match=r"prompt placeholder on step 'assess' \{item\.payload\.foo\} references missing payload path 'foo' on worklist 'gate'",
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
def test_ctx_prompt_bindings_render_in_provider_and_operation_prompts(tmp_path: Path) -> None:
    class PromptBindingWorkflow(SimpleWorkflow):
        class Input(BaseModel):
            topic: str

        class Params(BaseModel):
            mode: str = "brief"

        class State(BaseModel):
            status: str = "draft"

        summary = step(
            "Message={ctx.message}; Topic={ctx.input.topic}; Mode={ctx.params.mode}; Status={ctx.state.status}",
            routes={"done": "review"},
        )
        review = produce_verify_step(
            producer_prompt="Produce {ctx.message}; topic={ctx.input.topic}; mode={ctx.params.mode}; status={ctx.state.status}",
            verifier_prompt="Verify {ctx.message}; topic={ctx.input.topic}; mode={ctx.params.mode}; status={ctx.state.status}",
            routes={"approved": "risk"},
        )
        risk = llm.step(
            prompt="Risk for {ctx.message}; topic={ctx.input.topic}; mode={ctx.params.mode}; status={ctx.state.status}",
            returns=str,
        )
        kind = classify.step(
            prompt="Classify {ctx.message} for {ctx.input.topic}",
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
    assert all("{ctx." not in text for text in rendered_prompts)
def test_runtime_templates_resolve_bare_input_message_and_fields(tmp_path: Path) -> None:
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
        "Message={input.message}; Topic={input.topic}",
        context,
        placeholder_label="artifact template placeholder",
    )
    resolved = resolve_artifact_template("outputs/{input.message}-{input.topic}.md", context)

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
        match=r"artifact template placeholder \{input\.missing\} references unknown input field 'missing'",
    ):
        render_runtime_template(
            "{input.missing}",
            context,
            placeholder_label="artifact template placeholder",
        )
def test_runtime_templates_resolve_ctx_input_message_without_typed_input(tmp_path: Path) -> None:
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
        "{ctx.input.message}",
        context,
        placeholder_label="artifact template placeholder",
        replace_roots=frozenset({"ctx"}),
    )

    assert rendered == "artifact-request"
def test_runtime_templates_resolve_ctx_input_message_separately_from_request(tmp_path: Path) -> None:
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
        "Request={ctx.message}; InputMessage={ctx.input.message}; Topic={ctx.input.topic}",
        context,
        placeholder_label="artifact template placeholder",
        replace_roots=frozenset({"ctx"}),
    )

    assert rendered == "Request=runtime-message; InputMessage=runtime-message; Topic=release"
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
        (
            {
                "schema": "autoloop.operation_replay/v1",
                "records": {"legacy": {"value": "stale"}},
                "attempts": ["first", "second"],
            },
            ["first", "second"],
        ),
    ],
)
def test_operation_replay_store_migrates_only_schemaless_and_v1_payloads(
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
                "schema": "autoloop.operation_replay/v3",
                "records": {"legacy": {"value": "stale"}},
                "attempts": ["first"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="uses unsupported schema 'autoloop.operation_replay/v3'"):
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
