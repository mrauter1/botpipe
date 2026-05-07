from __future__ import annotations

from tests.contract.engine._shared import *

def test_runtime_extensions_bind_before_workflow_extensions(tmp_path: Path):
    events: list[str] = []

    class RuntimeBound:
        def before_step(self, event):
            events.append(f"runtime:before:{event.step_name}")

        def after_step(self, event):
            events.append(f"runtime:after:{event.step_name}")

        def on_terminal(self, event):
            events.append(f"runtime:terminal:{event.terminal}")

    class WorkflowBound:
        def before_step(self, event):
            events.append(f"workflow:before:{event.step_name}")

        def after_step(self, event):
            events.append(f"workflow:after:{event.step_name}")

        def on_terminal(self, event):
            events.append(f"workflow:terminal:{event.terminal}")

    class WorkflowExtensionRecorder:
        def bind(self, binding):
            return WorkflowBound()

    def _orderedworkflow_on_bootstrap(ctx):
        ctx.state = ctx.state.model_copy(update={'ready': True})
        return Event('done')

    class OrderedWorkflow(Workflow):
        class State(BaseModel):
            ready: bool = False

        bootstrap = PythonStep(name="bootstrap", handler=_orderedworkflow_on_bootstrap)
        entry = bootstrap
        transitions = {bootstrap: {"done": FINISH}}
        extensions = (WorkflowExtensionRecorder(),)


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        OrderedWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_extension_factories=(lambda binding: RuntimeBound(),),
    )

    result = engine.run(
        task_id="task-ordered",
        run_id="run-ordered",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert events == [
        "runtime:before:bootstrap",
        "workflow:before:bootstrap",
        "runtime:after:bootstrap",
        "workflow:after:bootstrap",
        "runtime:terminal:FINISH",
        "workflow:terminal:FINISH",
    ]
def test_extension_core_modules_remain_autoloop_agnostic():
    engine_text = (PACKAGE_ROOT / "autoloop" / "core" / "engine.py").read_text(encoding="utf-8")
    extension_text = (PACKAGE_ROOT / "autoloop" / "core" / "extensions.py").read_text(encoding="utf-8")
    corpus = f"{engine_text}\n{extension_text}"

    for forbidden in (
        "autoloop_v1",
        "run_autoloop_v1",
        "autoloop_v1_support",
        "autoloop_v1_parity",
        "autoloop_v1_conventions",
        "activate_next_phase",
        "phase_selected",
        "phase_started",
        "phase_completed",
    ):
        assert forbidden not in corpus
def test_pair_step_contract_logs_raw_output_and_updates_state(tmp_path: Path):
    def _pairworkflow_on_start(ctx):
        ctx.open_session(PairWorkflow.main)

    def _pairworkflow_on_pair(ctx):
        ctx.state = ctx.state.model_copy(update={'draft_text': ctx.artifacts.draft.read_text()})
        return None

    def _pairworkflow_on_finish(ctx):
        return Event('done')

    class PairWorkflow(Workflow):
        class State(BaseModel):
            draft_text: str = ""

        main = Session()
        request = Artifact("{task_folder}/request.txt")
        raw_log = Artifact("{run_folder}/pair.log")
        pair = ProduceVerifyStep(
            name="pair",
            session=main,
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            requires=[request],
            producer_writes={"draft": Artifact("{run_folder}/draft.txt")},
            log_artifacts=[raw_log],
        )
        finish = PythonStep(name="finish", handler=_pairworkflow_on_finish)
        entry = pair
        transitions = {pair: {"pair_ok": finish}, finish: {"done": FINISH}}
    PairWorkflow.pair.before = _chain_hooks(_pairworkflow_on_start, PairWorkflow.pair.before)
    PairWorkflow.pair.after_verifier = _chain_hooks(_pairworkflow_on_pair, PairWorkflow.pair.after_verifier)


    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "request.txt").write_text("request", encoding="utf-8")
    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.draft.write_text("artifact draft"),
                "producer raw\n",
            )[1]
        ],
        verifier_turns=[Outcome(raw_output="verified", tag="pair_ok")],
    )
    engine = Engine(
        PairWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.draft_text == "artifact draft"
    assert (run_folder / "pair.log").read_text(encoding="utf-8") == "producer raw\n"
    assert result.history == ("pair", "finish")
    assert [(call.kind, call.step_name, call.prompt_path) for call in provider.calls] == [
        ("producer", "pair", "pair/producer.md"),
        ("verifier", "pair", "pair/verifier.md"),
    ]
def test_step_finish_exposes_raw_outputs_for_package_local_parity_extensions(tmp_path: Path):
    pair_usage = StepProviderUsage(
        producer=TokenUsage(input_tokens=5, output_tokens=7, total_tokens=12, source="fake"),
        verifier=TokenUsage(input_tokens=11, output_tokens=3, total_tokens=14, source="fake"),
    )
    llm_usage = StepProviderUsage(llm=TokenUsage(input_tokens=2, output_tokens=4, total_tokens=6, source="fake"))
    seen: list[tuple[str, str | None, str | None, StepProviderUsage | None]] = []

    class RawOutputExtension:
        def bind(self, binding):
            class Bound:
                def before_step(self, event):
                    return None

                def after_step(self, event):
                    seen.append((event.step_name, event.producer_raw_output, event.verifier_raw_output, event.provider_usage))

                def on_terminal(self, event):
                    return None

            return Bound()

    def _rawoutputworkflow_on_start(ctx):
        ctx.open_session(RawOutputWorkflow.main)

    def _rawoutputworkflow_on_finish(ctx):
        return Event('complete')

    class RawOutputWorkflow(Workflow):
        class State(BaseModel):
            note: str = ""

        main = Session()
        request = Artifact("{task_folder}/request.txt")
        pair = ProduceVerifyStep(name="pair", producer="pair/producer.md", verifier="pair/verifier.md", requires=[request], session=main)
        ask = PromptStep(name="ask", producer="ask.md", session=main)
        finish = PythonStep(name="finish", handler=_rawoutputworkflow_on_finish)
        entry = pair
        transitions = {pair: {"pair_ok": ask}, ask: {"done": finish}, finish: {"complete": FINISH}}
        extensions = (RawOutputExtension(),)
    RawOutputWorkflow.pair.before = _chain_hooks(_rawoutputworkflow_on_start, RawOutputWorkflow.pair.before)


    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "request.txt").write_text("request", encoding="utf-8")
    engine = Engine(
        RawOutputWorkflow,
        provider=ScriptedLLMProvider(
            producer_turns=[
                ProducerResponse(
                    raw_output="pair producer raw\n",
                    usage=pair_usage.producer,
                )
            ],
            verifier_turns=[
                OutcomeResponse(
                    outcome=Outcome(raw_output="pair verifier raw\n", tag="pair_ok"),
                    usage=pair_usage.verifier,
                )
            ],
            llm_turns=[
                OutcomeResponse(
                    outcome=Outcome(raw_output="llm raw\n", tag="done"),
                    usage=llm_usage.llm,
                )
            ],
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert seen == [
        ("pair", "pair producer raw\n", "pair verifier raw\n", pair_usage),
        ("ask", "llm raw\n", None, llm_usage),
        ("finish", None, None, None),
    ]
def test_pair_and_llm_handlers_remain_optional(tmp_path: Path):
    def _optionalhandlerworkflow_on_start(ctx):
        ctx.open_session(OptionalHandlerWorkflow.main)

    def _optionalhandlerworkflow_on_finish(ctx):
        ctx.state = ctx.state.model_copy(update={'finished': True})
        return Event('complete')

    class OptionalHandlerWorkflow(Workflow):
        class State(BaseModel):
            finished: bool = False

        main = Session()
        request = Artifact("{task_folder}/request.txt")
        pair = ProduceVerifyStep(name="pair", producer="pair/producer.md", verifier="pair/verifier.md", requires=[request], session=main)
        ask = PromptStep(name="ask", producer="ask.md", session=main)
        finish = PythonStep(name="finish", handler=_optionalhandlerworkflow_on_finish)
        entry = pair
        transitions = {pair: {"pair_ok": ask}, ask: {"done": finish}, finish: {"complete": FINISH}}
    OptionalHandlerWorkflow.pair.before = _chain_hooks(_optionalhandlerworkflow_on_start, OptionalHandlerWorkflow.pair.before)


    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "request.txt").write_text("request", encoding="utf-8")
    engine = Engine(
        OptionalHandlerWorkflow,
        provider=ScriptedLLMProvider(
            producer_turns=["producer raw"],
            verifier_turns=[Outcome(raw_output="verified", tag="pair_ok")],
            llm_turns=[Outcome(raw_output="done", tag="done")],
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.finished is True
    assert result.history == ("pair", "ask", "finish")
def test_llm_step_contract_logs_outcome_raw_output_and_uses_global_route(tmp_path: Path):
    def _llmworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'tag_seen': ctx.outcome.tag})
        return None

    class LLMWorkflow(Workflow):
        class State(BaseModel):
            tag_seen: str = ""

        request = Artifact("{task_folder}/request.txt")
        raw_log = Artifact("{run_folder}/llm.log")
        ask = PromptStep(
            name="ask",
            producer="ask.md",
            requires=[request],
            log_artifacts=[raw_log],
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {"done": FINISH},
            GLOBAL: {"failed": "FAIL"},
        }

    LLMWorkflow.ask.after = _chain_hooks(_llmworkflow_on_ask, LLMWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "request.txt").write_text("request", encoding="utf-8")
    provider = ScriptedLLMProvider(
        llm_turns=[Outcome(raw_output="bad\n", tag="failed", reason="The request could not be completed.")]
    )
    engine = Engine(
        LLMWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == "FAIL"
    assert result.state.tag_seen == "failed"
    assert (run_folder / "llm.log").read_text(encoding="utf-8") == "bad\n"
    assert [(call.kind, call.step_name, call.prompt_path) for call in provider.calls] == [("step", "ask", "ask.md")]
def test_llm_requests_include_step_control_contracts(tmp_path: Path):
    class ReviewPayload(BaseModel):
        summary: str

    def _contractworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'summary': ctx.outcome.payload['summary']})
        return None

    class ContractWorkflow(Workflow):
        class State(BaseModel):
            summary: str = ""

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            expected_output_schema=ReviewPayload,
            route_metadata={"done": "workflow completed cleanly"},
        )
        entry = ask
        transitions = {
            ask: {"done": FINISH},
            GLOBAL: {"failed": FAIL},
        }

    ContractWorkflow.ask.after = _chain_hooks(_contractworkflow_on_ask, ContractWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[Outcome(raw_output="ok", tag="done", payload={"summary": "ready"})]
    )
    engine = Engine(
        ContractWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    call = provider.calls[0]
    assert result.terminal == FINISH
    assert result.state.summary == "ready"
    assert call.kind == "step"
    assert call.available_routes == ("done", "failed", "question")
    assert call.routes["done"].summary == "workflow completed cleanly"
    assert call.expected_output_schema is not None
    assert call.expected_output_schema["required"] == ["summary"]
    assert call.readable_artifacts == ()
    assert call.required_artifacts == ()
    assert call.writable_artifacts == ()
    assert call.route_required_writes == {
        "done": (),
        "failed": (),
        "question": (),
    }
    assert call.attempt == 1
    assert call.max_attempts == 3
def test_pair_requests_include_step_control_contracts(tmp_path: Path):
    class VerdictPayload(BaseModel):
        verdict: str

    def _paircontractworkflow_on_pair(ctx):
        ctx.state = ctx.state.model_copy(update={'verdict': ctx.outcome.payload['verdict']})
        return None

    def _paircontractworkflow_on_finish(ctx):
        return Event('done')

    class PairContractWorkflow(Workflow):
        class State(BaseModel):
            verdict: str = ""

        request = Artifact("{task_folder}/request.txt")
        pair = ProduceVerifyStep(
            name="pair",
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            requires=[request],
            expected_output_schema=VerdictPayload,
            route_metadata={"pair_ok": "verification finished"},
        )
        finish = PythonStep(name="finish", handler=_paircontractworkflow_on_finish)
        entry = pair
        transitions = {
            pair: {"pair_ok": finish},
            finish: {"done": FINISH},
            GLOBAL: {"failed": FAIL},
        }
    PairContractWorkflow.pair.after_verifier = _chain_hooks(_paircontractworkflow_on_pair, PairContractWorkflow.pair.after_verifier)


    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "request.txt").write_text("request", encoding="utf-8")
    provider = ScriptedLLMProvider(
        producer_turns=["producer raw\n"],
        verifier_turns=[Outcome(raw_output="verified", tag="pair_ok", payload={"verdict": "approve"})],
    )
    engine = Engine(
        PairContractWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.verdict == "approve"
    assert [(call.kind, call.available_routes) for call in provider.calls] == [
        ("producer", ()),
        ("verifier", ("pair_ok", "failed", "question")),
    ]
    assert provider.calls[0].routes == {}
    assert provider.calls[0].expected_output_schema is None
    assert provider.calls[1].expected_output_schema is not None
    assert provider.calls[0].readable_artifacts == ()
    assert [ref.qualified_name for ref in provider.calls[0].required_artifacts] == ["request"]
    assert provider.calls[0].writable_artifacts == ()
    assert provider.calls[0].route_required_writes == {}
    assert provider.calls[1].routes["pair_ok"].summary == "verification finished"
def test_declared_extensions_bind_once_per_run_in_tuple_order(tmp_path: Path):
    events: list[tuple[object, ...]] = []
    first = _RecordingExtension("first", events)
    second = _RecordingExtension("second", events)

    def _extensionworkflow_on_ask(ctx):
        return None

    def _extensionworkflow_on_finish(ctx):
        ctx.state = ctx.state.model_copy(update={'done': True})
        return Event('complete')

    class ExtensionWorkflow(Workflow):
        class State(BaseModel):
            done: bool = False

        extensions = (first, second)
        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        finish = PythonStep(name="finish", handler=_extensionworkflow_on_finish)
        entry = ask
        transitions = {ask: {"done": finish}, finish: {"complete": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        ExtensionWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert len(first.bindings) == 1
    assert len(second.bindings) == 1
    assert first.bindings[0] == second.bindings[0]
    assert first.bindings[0].root == tmp_path
    assert first.bindings[0].workflow_name == "extension_workflow"
    assert [(name, phase, step) for name, phase, step, *_ in events] == [
        ("first", "before", "ask"),
        ("second", "before", "ask"),
        ("first", "after", "ask"),
        ("second", "after", "ask"),
        ("first", "before", "finish"),
        ("second", "before", "finish"),
        ("first", "after", "finish"),
        ("second", "after", "finish"),
        ("first", "terminal", FINISH),
        ("second", "terminal", FINISH),
    ]
def test_extensions_receive_isolated_snapshots_and_cannot_mutate_execution_state(tmp_path: Path):
    class MutatingExtension:
        def bind(self, binding: RunBinding):
            class Bound:
                def before_step(self, event: StepStart) -> None:
                    event.state.seen = "before"

                def after_step(self, event: StepFinish) -> None:
                    event.state_before.seen = "mutated-before"
                    event.state_after.seen = "mutated-after"
                    if event.outcome is not None:
                        event.outcome.payload["tag_seen"] = "mutated"

                def on_terminal(self, event: TerminalFinish) -> None:
                    if event.state is not None:
                        event.state.seen = "terminal"

            return Bound()

    def _isolationworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': ctx.outcome.payload['tag_seen']})
        return None

    class IsolationWorkflow(Workflow):
        class State(BaseModel):
            seen: str = ""

        extensions = (MutatingExtension(),)
        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}

    IsolationWorkflow.ask.after = _chain_hooks(_isolationworkflow_on_ask, IsolationWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        IsolationWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[Outcome(raw_output="ok", tag="done", payload={"tag_seen": "done"})]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.seen == "done"
def test_malformed_bound_extension_fails_before_any_step_executes(tmp_path: Path):
    class BrokenExtension:
        def bind(self, binding: RunBinding):
            class Bound:
                def before_step(self, event: StepStart) -> None:
                    return None

                def after_step(self, event: StepFinish) -> None:
                    return None

            return Bound()

    def _brokenworkflow_on_ask(ctx):
        return None

    class BrokenWorkflow(Workflow):
        class State(BaseModel):
            pass

        extensions = (BrokenExtension(),)
        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        BrokenWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match=r"without callable on_terminal\(\)"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    assert provider.calls == []
    assert checkpoint_store.load() is None
def test_system_step_contract_bypasses_middleware(tmp_path: Path):
    def _systemworkflow_on_begin(ctx):
        ctx.state = ctx.state.model_copy(update={'completed': True})
        return Event('done')

    def _systemworkflow_on_outcome(ctx):
        raise AssertionError('middleware must not run for system steps')

    class SystemWorkflow(Workflow):
        class State(BaseModel):
            completed: bool = False

        begin = PythonStep(name="begin", handler=_systemworkflow_on_begin)
        entry = begin
        transitions = {begin: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    session_store = InMemorySessionStore()
    engine = Engine(
        SystemWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.completed is True
    snapshot = session_store.snapshot()
    assert "default" not in snapshot.active_keys_by_slot
    assert snapshot.bindings == ()
def test_python_step_tuple_state_event_return_is_rejected(tmp_path: Path):
    def _invalidtuplepythonstepworkflow_on_publish(ctx):
        return (ctx.state, Event('done'))

    class InvalidTuplePythonStepWorkflow(Workflow):
        class State(BaseModel):
            pass

        publish = PythonStep(name="publish", handler=_invalidtuplepythonstepworkflow_on_publish)
        entry = publish
        transitions = {publish: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        InvalidTuplePythonStepWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(WorkflowExecutionError, match=r"python_step hook for step 'publish' returned unsupported value"):
        engine.run(
            task_id="task-tuple-return",
            run_id="run-tuple-return",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_python_step_basemodel_return_is_rejected(tmp_path: Path):
    def _invalidstatereturnworkflow_on_publish(ctx):
        return ctx.state.model_copy(update={'done': True})

    class InvalidStateReturnWorkflow(Workflow):
        class State(BaseModel):
            done: bool = False

        publish = PythonStep(name="publish", handler=_invalidstatereturnworkflow_on_publish)
        entry = publish
        transitions = {publish: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        InvalidStateReturnWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(WorkflowExecutionError, match=r"python_step hook for step 'publish' returned unsupported value"):
        engine.run(
            task_id="task-state-return",
            run_id="run-state-return",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_compiled_workflow_is_deterministic():
    def _deterministicworkflow_on_ask(ctx):
        return None

    class DeterministicWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}


    first = compile_workflow(DeterministicWorkflow)
    second = compile_workflow(DeterministicWorkflow)

    assert first is second
def test_step_named_start_executes_without_being_treated_as_lifecycle_hook(tmp_path: Path):
    def _startnamedworkflow_on_start(ctx):
        ctx.state = ctx.state.model_copy(update={'handler_calls': ctx.state.handler_calls + 1})
        return None

    class StartNamedWorkflow(Workflow):
        class State(BaseModel):
            handler_calls: int = 0

        start = PromptStep(name="start", producer="start.md")
        entry = start
        transitions = {start: {"done": FINISH}}

    StartNamedWorkflow.start.after = _chain_hooks(_startnamedworkflow_on_start, StartNamedWorkflow.start.after)


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        StartNamedWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.handler_calls == 1
def test_step_named_outcome_executes_without_being_treated_as_global_middleware(tmp_path: Path):
    def _outcomenamedworkflow_on_outcome(ctx):
        ctx.state = ctx.state.model_copy(update={'handler_calls': ctx.state.handler_calls + 1})
        return None

    class OutcomeNamedWorkflow(Workflow):
        class State(BaseModel):
            handler_calls: int = 0

        outcome = PromptStep(name="outcome", producer="outcome.md")
        entry = outcome
        transitions = {outcome: {"done": FINISH}}

    OutcomeNamedWorkflow.outcome.after = _chain_hooks(_outcomenamedworkflow_on_outcome, OutcomeNamedWorkflow.outcome.after)


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        OutcomeNamedWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.handler_calls == 1
def test_step_named_verdict_executes_without_being_treated_as_global_middleware(tmp_path: Path):
    def _verdictnamedworkflow_on_verdict(ctx):
        ctx.state = ctx.state.model_copy(update={'handler_calls': ctx.state.handler_calls + 1})
        return None

    class VerdictNamedWorkflow(Workflow):
        class State(BaseModel):
            handler_calls: int = 0

        verdict = PromptStep(name="verdict", producer="verdict.md")
        entry = verdict
        transitions = {verdict: {"done": FINISH}}

    VerdictNamedWorkflow.verdict.after = _chain_hooks(_verdictnamedworkflow_on_verdict, VerdictNamedWorkflow.verdict.after)


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        VerdictNamedWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.handler_calls == 1
def test_llm_and_classify_step_replay_across_reruns(tmp_path: Path) -> None:
    class Summary(BaseModel):
        title: str

    class ReplayWorkflow(SimpleWorkflow):
        summary = llm.step(prompt="Summarize the request.", returns=Summary)
        verdict = classify.step(prompt="Classify {summary.value}.", choices=["solid", "weak"])

        @python_step(routes={"solid": FINISH, "weak": FAIL})
        def route(ctx):
            return ctx.values.verdict

    task_folder, run_folder = _workspace(tmp_path)

    first_provider = ScriptedLLMProvider(operation_turns=['{"title":"ready"}', "solid"])
    first_result = Engine(
        ReplayWorkflow,
        provider=first_provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-replay",
        run_id="run-replay",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert first_result.terminal == FINISH
    assert [call.kind for call in first_provider.calls] == ["operation", "operation"]

    replay_provider = ScriptedLLMProvider()
    replay_result = Engine(
        ReplayWorkflow,
        provider=replay_provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-replay",
        run_id="run-replay",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert replay_result.terminal == FINISH
    assert replay_provider.calls == []
def test_resume_restores_recorded_values_for_following_python_step(tmp_path: Path) -> None:
    class Summary(BaseModel):
        title: str

    class ResumeWorkflow(SimpleWorkflow):
        class State(BaseModel):
            published_title: str = ""

        summary = llm.step(prompt="Summarize the request.", returns=Summary)

        @python_step(routes={"question": AWAIT_INPUT, "done": "publish"})
        def gate(ctx):
            if ctx.answer is None:
                return Event("question", question="Proceed?")
            return "done"

        @python_step
        def publish(ctx):
            ctx.state = ctx.state.model_copy(update={"published_title": ctx.values.summary.title})
            return None

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()

    paused_result = Engine(
        ResumeWorkflow,
        provider=ScriptedLLMProvider(operation_turns=['{"title":"Ready to publish"}']),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).run(
        task_id="task-resume-values",
        run_id="run-resume-values",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused_result.terminal == AWAIT_INPUT
    assert paused_result.checkpoint is not None
    assert paused_result.checkpoint.values == {"summary": {"title": "Ready to publish"}}

    resumed_result = Engine(
        ResumeWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).resume(
        task_id="task-resume-values",
        run_id="run-resume-values",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        answer="yes",
    )

    assert resumed_result.terminal == FINISH
    assert resumed_result.state.published_title == "Ready to publish"
