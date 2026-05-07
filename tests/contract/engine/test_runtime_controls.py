from __future__ import annotations

from tests.contract.engine._shared import _ApprovalInput, _chain_hooks, _workspace
from tests.contract.engine._shared import *

def test_middleware_pause_skips_handler_and_resume_injects_answer_once(tmp_path: Path):
    def _pauseworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'handler_calls': ctx.state.handler_calls + 1, 'answer_seen': ctx.outcome.payload.get('answer')})
        return None

    def _pauseworkflow_on_finish(ctx):
        ctx.state = ctx.state.model_copy(update={'answer_visible_in_system': ctx.answer})
        return Event('done')

    def _pauseworkflow_on_outcome(ctx):
        if ctx.outcome.tag == 'question':
            return Event('question', reason=ctx.outcome.reason, question=ctx.outcome.question)
        return None

    class PauseWorkflow(Workflow):
        class State(BaseModel):
            handler_calls: int = 0
            answer_seen: str | None = None
            answer_visible_in_system: str | None = None

        ask = PromptStep(name="ask", producer="ask.md")
        finish = PythonStep(name="finish", handler=_pauseworkflow_on_finish)
        entry = ask
        transitions = {ask: {"answered": finish, "question": "AWAIT_INPUT"}, finish: {"done": FINISH}}
    PauseWorkflow.ask.after = _chain_hooks(_pauseworkflow_on_outcome, _pauseworkflow_on_ask, PauseWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        PauseWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: Outcome(
                    raw_output="Need answer",
                    tag="answered" if request.context.answer else "question",
                    question=None if request.context.answer else "What value?",
                    payload={"answer": request.context.answer} if request.context.answer else {},
                ),
                lambda request: Outcome(
                    raw_output="Need answer",
                    tag="answered" if request.context.answer else "question",
                    question=None if request.context.answer else "What value?",
                    payload={"answer": request.context.answer} if request.context.answer else {},
                ),
            ]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    paused = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused.terminal == "AWAIT_INPUT"
    assert paused.state.handler_calls == 0
    assert paused.checkpoint.pending_input is not None
    assert paused.checkpoint.pending_input.question == "What value?"

    resumed = engine.resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        answer="42",
    )

    assert resumed.terminal == FINISH
    assert resumed.state.handler_calls == 1
    assert resumed.state.answer_seen == "42"
    assert resumed.state.answer_visible_in_system is None
    assert checkpoint_store.load() is None
def test_terminal_extensions_receive_pause_fail_and_fatal_events(tmp_path: Path):
    seen: list[tuple[str, str | None, str]] = []

    class TerminalExtension:
        def bind(self, binding: RunBinding):
            class Bound:
                def before_step(self, event: StepStart) -> None:
                    return None

                def after_step(self, event: StepFinish) -> None:
                    return None

                def on_terminal(self, event: TerminalFinish) -> None:
                    seen.append((event.terminal, event.step_name, event.binding.run_id))

            return Bound()

    def _pauseworkflow_on_outcome(ctx):
        return Event('question', question=ctx.outcome.question)

    class PauseWorkflow(Workflow):
        class State(BaseModel):
            pass

        extensions = (TerminalExtension(),)
        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"question": "AWAIT_INPUT"}}

    PauseWorkflow.ask.after = _chain_hooks(_pauseworkflow_on_outcome, PauseWorkflow.ask.after)


    class FailWorkflow(Workflow):
        class State(BaseModel):
            pass

        extensions = (TerminalExtension(),)
        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"failed": "FAIL"}}

    def _fatalworkflow_on_ask(ctx):
        raise RuntimeError('boom')

    class FatalWorkflow(Workflow):
        class State(BaseModel):
            pass

        extensions = (TerminalExtension(),)
        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}

    FatalWorkflow.ask.after = _chain_hooks(_fatalworkflow_on_ask, FatalWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)

    paused = Engine(
        PauseWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="Need answer", tag="question", question="What value?")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(task_id="task-1", run_id="run-1", task_folder=task_folder, run_folder=run_folder, root=tmp_path)

    failed = Engine(
        FailWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="bad", tag="failed", reason="The step failed.")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(task_id="task-2", run_id="run-2", task_folder=task_folder, run_folder=run_folder, root=tmp_path)

    fatal_checkpoint_store = InMemoryCheckpointStore()
    fatal_engine = Engine(
        FatalWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=fatal_checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="boom"):
        fatal_engine.run(task_id="task-3", run_id="run-3", task_folder=task_folder, run_folder=run_folder, root=tmp_path)

    assert paused.terminal == "AWAIT_INPUT"
    assert failed.terminal == "FAIL"
    assert fatal_checkpoint_store.load() is not None
    assert seen == [
        ("AWAIT_INPUT", "ask", "run-1"),
        ("FAIL", "ask", "run-2"),
        ("fatal", "ask", "run-3"),
    ]
def test_before_hook_request_input_short_circuits_without_provider_and_preserves_last_route(tmp_path: Path):
    def before_ask(ctx):
        ctx.state.approval_status = "awaiting_input"
        return RequestInput("Approve the change?", input_schema=_ApprovalInput)

    def _beforehookrequestinputworkflow_on_ask(ctx):
        raise AssertionError('provider outcome handler should not run when before short-circuits')

    class BeforeHookRequestInputWorkflow(Workflow):
        class State(BaseModel):
            approval_status: str = "new"

        ask = PromptStep(name="ask", producer="ask.md", before=before_ask)
        entry = ask
        transitions = {ask: {"done": FINISH}}

    BeforeHookRequestInputWorkflow.ask.after = _chain_hooks(_beforehookrequestinputworkflow_on_ask, BeforeHookRequestInputWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="unexpected", tag="done")])
    paused = Engine(
        BeforeHookRequestInputWorkflow,
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

    assert paused.terminal == AWAIT_INPUT
    assert paused.state.approval_status == "awaiting_input"
    assert provider.calls == []
    assert paused.last_transition is not None
    assert paused.last_transition.candidate_route is None
    assert paused.last_transition.final_route is None
    assert paused.last_transition.runtime_control == "request_input"
    assert paused.last_transition.provider_attempted is False
    assert paused.checkpoint is not None
    assert paused.checkpoint.pending_input is not None
    assert paused.last_transition.pending_input_id == paused.checkpoint.pending_input.pending_input_id
    assert paused.checkpoint.pending_input.question == "Approve the change?"
    assert paused.checkpoint.pending_input.source_hook == "before_ask"
    assert paused.checkpoint.pending_input.source_phase == "before"
    assert paused.checkpoint.step_states is not None
    assert paused.checkpoint.step_states["ask"]["last_route"] is None
def test_before_verifier_request_input_short_circuits_verifier_and_checkpoints_pending_input(tmp_path: Path):
    def before_verifier(ctx):
        ctx.state.approval_status = "awaiting_verifier_input"
        return RequestInput("Approve before verification?", input_schema=_ApprovalInput)

    def _beforeverifierrequestinputworkflow_on_pair(ctx):
        raise AssertionError("pair outcome handler should not run when before_verifier short-circuits")

    class BeforeVerifierRequestInputWorkflow(Workflow):
        class State(BaseModel):
            approval_status: str = "new"

        pair = ProduceVerifyStep(
            name="pair",
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            before_verifier=before_verifier,
        )
        entry = pair
        transitions = {pair: {"approved": FINISH}}

    BeforeVerifierRequestInputWorkflow.pair.after_verifier = _chain_hooks(
        _beforeverifierrequestinputworkflow_on_pair,
        BeforeVerifierRequestInputWorkflow.pair.after_verifier,
    )

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=["draft copy"],
        verifier_turns=[Outcome(raw_output="unexpected", tag="approved")],
    )
    paused = Engine(
        BeforeVerifierRequestInputWorkflow,
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

    assert paused.terminal == AWAIT_INPUT
    assert paused.state.approval_status == "awaiting_verifier_input"
    assert [call.kind for call in provider.calls] == ["producer"]
    assert paused.last_transition is not None
    assert paused.last_transition.candidate_route is None
    assert paused.last_transition.final_route is None
    assert paused.last_transition.runtime_control == "request_input"
    assert paused.last_transition.provider_attributable is False
    assert paused.last_transition.provider_attempted is True
    assert paused.last_transition.producer_attempted is True
    assert paused.last_transition.verifier_attempted is False
    assert paused.checkpoint is not None
    assert paused.checkpoint.pending_input is not None
    assert paused.last_transition.pending_input_id == paused.checkpoint.pending_input.pending_input_id
    assert paused.checkpoint.pending_input.question == "Approve before verification?"
    assert paused.checkpoint.pending_input.source_hook == "before_verifier"
    assert paused.checkpoint.pending_input.source_phase == "before_verifier"
    assert paused.checkpoint.step_states is not None
    assert paused.checkpoint.step_states["pair"]["last_route"] is None
def test_before_verifier_invalid_goto_preserves_state_and_failure_context(tmp_path: Path):
    def before_verifier(ctx):
        ctx.state.approval_status = "mutated before invalid goto"
        return Goto("missing_step", reason="Verifier should jump to a missing step.")

    class BeforeVerifierInvalidGotoWorkflow(Workflow):
        class State(BaseModel):
            approval_status: str = "new"

        pair = ProduceVerifyStep(
            name="pair",
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            before_verifier=before_verifier,
        )
        entry = pair
        transitions = {pair: {"approved": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    provider = ScriptedLLMProvider(
        producer_turns=["draft copy"],
        verifier_turns=[Outcome(raw_output="unexpected", tag="approved")],
    )
    engine = Engine(
        BeforeVerifierInvalidGotoWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="declared workflow step"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.state.approval_status == "mutated before invalid goto"
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "runtime_control_validation"
    assert checkpoint.failure_context["runtime_control"] == "goto"
    assert checkpoint.failure_context["source_hook"] == "before_verifier"
    assert checkpoint.failure_context["source_phase"] == "before_verifier"
    assert [call.kind for call in provider.calls] == ["producer"]
def test_before_producer_request_input_short_circuits_without_provider_and_checkpoints_pending_input(tmp_path: Path):
    def before_producer(ctx):
        ctx.state.approval_status = "awaiting_producer_input"
        return RequestInput("Approve the producer plan?", input_schema=_ApprovalInput)

    def _beforeproducerrequestinputworkflow_on_pair(ctx):
        raise AssertionError('pair outcome handler should not run when before_producer short-circuits')

    class BeforeProducerRequestInputWorkflow(Workflow):
        class State(BaseModel):
            approval_status: str = "new"

        pair = ProduceVerifyStep(
            name="pair",
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            before_producer=before_producer,
        )
        entry = pair
        transitions = {pair: {"approved": FINISH}}

    BeforeProducerRequestInputWorkflow.pair.after_verifier = _chain_hooks(_beforeproducerrequestinputworkflow_on_pair, BeforeProducerRequestInputWorkflow.pair.after_verifier)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=["unexpected draft"],
        verifier_turns=[Outcome(raw_output="unexpected", tag="approved")],
    )
    paused = Engine(
        BeforeProducerRequestInputWorkflow,
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

    assert paused.terminal == AWAIT_INPUT
    assert paused.state.approval_status == "awaiting_producer_input"
    assert provider.calls == []
    assert paused.last_transition is not None
    assert paused.last_transition.candidate_route is None
    assert paused.last_transition.final_route is None
    assert paused.last_transition.runtime_control == "request_input"
    assert paused.last_transition.provider_attempted is False
    assert paused.checkpoint is not None
    assert paused.checkpoint.pending_input is not None
    assert paused.last_transition.pending_input_id == paused.checkpoint.pending_input.pending_input_id
    assert paused.checkpoint.pending_input.question == "Approve the producer plan?"
    assert paused.checkpoint.pending_input.source_phase == "before_producer"
    assert paused.checkpoint.step_states is not None
    assert paused.checkpoint.step_states["pair"]["last_route"] is None
def test_after_hook_request_input_checkpoints_pending_input_and_resume_validates_input(tmp_path: Path):
    def after(ctx):
        assert ctx.route is not None
        assert ctx.route.tag == "done"
        assert ctx.route.target == "FINISH"
        assert ctx.route.handoff is None
        if ctx.input_response is None:
            return RequestInput(
                "Approve the change?",
                reason="A human approval is required.",
                best_supposition="approve",
                input_schema=_ApprovalInput,
            )
        ctx.state.approval = ctx.input_response.approval
        return None

    def _requestinputworkflow_on_ask(ctx):
        return Event('done')

    class RequestInputWorkflow(Workflow):
        class State(BaseModel):
            approval: str | None = None

        ask = PythonStep(name="ask", after=after, handler=_requestinputworkflow_on_ask)
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        RequestInputWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    paused = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused.terminal == AWAIT_INPUT
    assert paused.last_event is None
    assert paused.checkpoint is not None
    assert paused.checkpoint.pending_input is not None
    assert paused.checkpoint.pending_input.question == "Approve the change?"
    assert paused.checkpoint.pending_input.source_hook == "after"
    assert paused.checkpoint.pending_input.input_schema is not None
    assert paused.checkpoint.step_states is not None
    assert paused.checkpoint.step_states["ask"]["last_route"] is None

    resumed = engine.resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        answer='{"approval":"approved"}',
    )

    assert resumed.terminal == FINISH
    assert resumed.state.approval == "approved"
def test_resumed_request_input_is_consumed_before_later_steps(tmp_path: Path):
    def after_ask(ctx):
        assert ctx.route is not None
        assert ctx.route.tag == "next"
        assert ctx.route.target == "confirm"
        assert ctx.route.handoff is None
        if ctx.input_response is None:
            return RequestInput("Approve the draft?", input_schema=_ApprovalInput)
        ctx.state.first_approval = ctx.input_response.approval
        return None

    def after_confirm(ctx):
        assert ctx.route is not None
        assert ctx.route.tag == "done"
        assert ctx.route.target == "FINISH"
        assert ctx.route.handoff is None
        if ctx.input_response is None:
            return RequestInput("Confirm the publication?", input_schema=_ApprovalInput)
        ctx.state.second_approval = ctx.input_response.approval
        return None

    def _multistageapprovalworkflow_on_ask(ctx):
        return Event('next')

    def _multistageapprovalworkflow_on_confirm(ctx):
        assert ctx.input_response is None
        return Event('done')

    class MultiStageApprovalWorkflow(Workflow):
        class State(BaseModel):
            first_approval: str | None = None
            second_approval: str | None = None

        ask = PythonStep(name="ask", after=after_ask, handler=_multistageapprovalworkflow_on_ask)
        confirm = PythonStep(name="confirm", after=after_confirm, handler=_multistageapprovalworkflow_on_confirm)
        entry = ask
        transitions = {ask: {"next": confirm}, confirm: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        MultiStageApprovalWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    first_pause = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert first_pause.terminal == AWAIT_INPUT
    assert first_pause.checkpoint is not None
    assert first_pause.checkpoint.pending_input is not None
    first_pending_input_id = first_pause.checkpoint.pending_input.pending_input_id
    assert first_pause.checkpoint.pending_input.question == "Approve the draft?"

    second_pause = engine.resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        answer='{"approval":"approved"}',
    )

    assert second_pause.terminal == AWAIT_INPUT
    assert second_pause.state.first_approval == "approved"
    assert second_pause.state.second_approval is None
    assert second_pause.checkpoint is not None
    assert second_pause.checkpoint.pending_input is not None
    assert second_pause.checkpoint.pending_input.question == "Confirm the publication?"
    assert second_pause.checkpoint.pending_input.source_step == "confirm"
    assert second_pause.checkpoint.pending_input.pending_input_id != first_pending_input_id
    assert second_pause.checkpoint.step_states is not None
    assert second_pause.checkpoint.step_states["ask"]["last_route"] == "next"
    assert second_pause.checkpoint.step_states["confirm"]["last_route"] is None
def test_resume_invalid_pending_input_preserves_checkpoint_and_failure_context(tmp_path: Path):
    def after(ctx):
        assert ctx.route is not None
        assert ctx.route.tag == "done"
        assert ctx.route.target == "FINISH"
        assert ctx.route.handoff is None
        if ctx.input_response is None:
            return RequestInput("Approve the change?", input_schema=_ApprovalInput)
        return None

    def _requestinputworkflow_on_ask(ctx):
        return Event('done')

    class RequestInputWorkflow(Workflow):
        class State(BaseModel):
            approval: str | None = None

        ask = PythonStep(name="ask", after=after, handler=_requestinputworkflow_on_ask)
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        RequestInputWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    paused = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused.checkpoint is not None

    with pytest.raises(WorkflowExecutionError, match="resumed input did not satisfy"):
        engine.resume(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
            answer='{"approval": 7}',
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.pending_input is not None
    assert checkpoint.pending_input.question == "Approve the change?"
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "resume_input_validation"
    assert checkpoint.failure_context["pending_input_id"] == checkpoint.pending_input.pending_input_id
def test_after_producer_goto_short_circuits_verifier(tmp_path: Path):
    step_finishes = []

    def after_producer(ctx):
        assert ctx.outcome == "draft copy"
        return Goto("publish", reason="Producer output is already approved.")

    def _producergotoworkflow_on_pair(ctx):
        return None

    def _producergotoworkflow_on_publish(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, 'publish']})
        return Event('done')

    class ProducerGotoWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        pair = ProduceVerifyStep(
            name="pair",
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            after_producer=after_producer,
        )
        publish = PythonStep(name="publish", handler=_producergotoworkflow_on_publish)
        entry = pair
        transitions = {
            pair: {"approved": FINISH},
            publish: {"done": FINISH},
        }
    ProducerGotoWorkflow.pair.after_verifier = ProducerGotoWorkflow.pair.after

    class _Recorder:
        def before_step(self, event):
            pass

        def after_step(self, event):
            step_finishes.append(event)

        def on_terminal(self, event):
            pass


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(producer_turns=["draft copy"])
    result = Engine(
        ProducerGotoWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_extension_factories=(lambda binding: _Recorder(),),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.history == ("pair", "publish")
    assert result.state.seen == ["publish"]
    assert [call.kind for call in provider.calls] == ["producer"]
    pair_finish = next(event for event in step_finishes if event.step_name == "pair")
    assert pair_finish.candidate_route is None
    assert pair_finish.final_route is None
    assert pair_finish.runtime_control == "goto"
    assert pair_finish.target_step == "publish"
    assert pair_finish.provider_attempted is True
    assert pair_finish.producer_attempted is True
    assert pair_finish.verifier_attempted is False
    assert pair_finish.source_hook == "after_producer"
    assert pair_finish.source_phase == "after_producer"
def test_after_producer_request_input_checkpoints_pending_input_before_verifier(tmp_path: Path):
    def after_producer(ctx):
        assert ctx.outcome == "draft copy"
        if ctx.input_response is None:
            return RequestInput(
                "Approve the producer draft?",
                reason="Verifier review requires a human gate.",
                input_schema=_ApprovalInput,
            )
        ctx.state.approval = ctx.input_response.approval
        return None

    def _producerrequestinputworkflow_on_pair(ctx):
        return None

    class ProducerRequestInputWorkflow(Workflow):
        class State(BaseModel):
            approval: str | None = None

        pair = ProduceVerifyStep(
            name="pair",
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            after_producer=after_producer,
        )
        entry = pair
        transitions = {pair: {"approved": FINISH}}

    ProducerRequestInputWorkflow.pair.after_verifier = ProducerRequestInputWorkflow.pair.after


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    provider = ScriptedLLMProvider(
        producer_turns=["draft copy", "draft copy"],
        verifier_turns=[Outcome(raw_output="approved", tag="approved")],
    )
    engine = Engine(
        ProducerRequestInputWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    paused = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused.terminal == AWAIT_INPUT
    assert paused.last_event is None
    assert paused.last_transition is not None
    assert paused.last_transition.runtime_control == "request_input"
    assert paused.last_transition.provider_attempted is True
    assert paused.last_transition.producer_attempted is True
    assert paused.last_transition.verifier_attempted is False
    assert paused.last_transition.source_hook == "after_producer"
    assert paused.last_transition.source_phase == "after_producer"
    assert paused.checkpoint is not None
    assert paused.checkpoint.pending_input is not None
    assert paused.last_transition.pending_input_id == paused.checkpoint.pending_input.pending_input_id
    assert paused.checkpoint.pending_input.question == "Approve the producer draft?"
    assert paused.checkpoint.pending_input.source_hook == "after_producer"
    assert [call.kind for call in provider.calls] == ["producer"]

    resumed = engine.resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        answer='{"approval":"approved"}',
    )

    assert resumed.terminal == FINISH
    assert resumed.state.approval == "approved"
    assert [call.kind for call in provider.calls] == ["producer", "producer", "verifier"]
def test_on_taken_goto_skips_declared_route_target_and_emits_runtime_control(tmp_path: Path):
    runtime_events: list[tuple[str, dict[str, object]]] = []

    def on_draft_taken(ctx):
        return Goto("publish", reason="The publish path is pre-approved.")

    def _gotoworkflow_on_ask(ctx):
        return None

    def _gotoworkflow_on_review(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, 'review']})
        return Event('done')

    def _gotoworkflow_on_publish(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, 'publish']})
        return Event('done')

    class GotoWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        review = PythonStep(name="review", handler=_gotoworkflow_on_review)
        publish = PythonStep(name="publish", handler=_gotoworkflow_on_publish)
        entry = ask
        transitions = {
            ask: {
                "draft": Route.to(review, on_taken=on_draft_taken),
            },
            review: {"done": FINISH},
            publish: {"done": FINISH},
        }


    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        GotoWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="draft")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.history == ("ask", "publish")
    assert result.state.seen == ["publish"]
    assert [
        payload
        for event_type, payload in runtime_events
        if event_type == "hook_runtime_control"
    ] == [
        {
            "step_name": "ask",
            "visit": 1,
            "step_execution_id": "ask:1",
            "control": "goto",
            "hook": "on_draft_taken",
            "source_phase": "on_taken",
            "target_step": "publish",
            "reason": "The publish path is pre-approved.",
        }
    ]
def test_on_taken_goto_handoff_reaches_target_provider_step(tmp_path: Path):
    def on_draft_taken(ctx):
        return Goto("publish", reason="Ship it.", handoff="Use the pre-approved publish checklist.")

    def _gotohandoffworkflow_on_ask(ctx):
        return None

    def _gotohandoffworkflow_on_publish(ctx):
        return None

    class GotoHandoffWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        publish = PromptStep(name="publish", producer="publish.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {
            ask: {"draft": Route.to(FINISH, on_taken=on_draft_taken)},
            publish: {"done": FINISH},
        }


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="ok", tag="draft"),
            Outcome(raw_output="published", tag="done"),
        ]
    )
    result = Engine(
        GotoHandoffWorkflow,
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
    assert [call.step_name for call in provider.calls] == ["ask", "publish"]
    assert provider.calls[1].route_handoff == "Use the pre-approved publish checklist."
def test_invalid_goto_after_state_mutation_preserves_state_and_failure_context(tmp_path: Path):
    def after(ctx):
        assert ctx.route is not None
        assert ctx.route.tag == "done"
        assert ctx.route.target == "FINISH"
        assert ctx.route.handoff is None
        ctx.state.note = "mutated before invalid goto"
        return Goto("missing_step", reason="This target does not exist.")

    def _invalidgotoworkflow_on_ask(ctx):
        return Event('done')

    class InvalidGotoWorkflow(Workflow):
        class State(BaseModel):
            note: str = "initial"

        ask = PythonStep(name="ask", after=after, handler=_invalidgotoworkflow_on_ask)
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        InvalidGotoWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="declared workflow step"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.state.note == "mutated before invalid goto"
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "runtime_control_validation"
    assert checkpoint.failure_context["runtime_control"] == "goto"
    assert checkpoint.failure_context["source_hook"] == "after"
    assert checkpoint.failure_context["source_phase"] == "after"
def test_on_taken_goto_checkpoints_target_before_next_step_dispatch(tmp_path: Path):
    def on_draft_taken(ctx):
        return Goto("publish", reason="Dispatch directly.")

    class FailingBeforePublishExtension:
        def before_step(self, event):
            if event.step_name == "publish":
                raise RuntimeError("stop before publish dispatch")

        def after_step(self, event):
            pass

        def on_terminal(self, event):
            pass

    def _gotocheckpointworkflow_on_ask(ctx):
        return None

    def _gotocheckpointworkflow_on_publish(ctx):
        return None

    class GotoCheckpointWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        publish = PromptStep(name="publish", producer="publish.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {
            ask: {"draft": Route.to(FINISH, on_taken=on_draft_taken)},
            publish: {"done": FINISH},
        }


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    with pytest.raises(RuntimeError, match="stop before publish dispatch"):
        Engine(
            GotoCheckpointWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="draft")]),
            session_store=InMemorySessionStore(),
            checkpoint_store=checkpoint_store,
            runtime_extension_factories=(lambda binding: FailingBeforePublishExtension(),),
        ).run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "publish"
def test_on_taken_fail_preserves_mutated_state_and_emits_runtime_control(tmp_path: Path):
    runtime_events: list[tuple[str, dict[str, object]]] = []

    def on_done_taken(ctx):
        ctx.state.status = "hook-mutated"
        return Fail("Stop after route review.")

    def _failworkflow_on_ask(ctx):
        return None

    class FailWorkflow(Workflow):
        class State(BaseModel):
            status: str = "draft"

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {
            ask: {
                "done": Route.to(FINISH, on_taken=on_done_taken),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        FailWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FAIL
    assert result.state.status == "hook-mutated"
    assert result.last_event is None
    assert result.checkpoint is not None
    assert result.checkpoint.state.status == "hook-mutated"
    assert [
        payload
        for event_type, payload in runtime_events
        if event_type == "hook_runtime_control"
    ] == [
        {
            "step_name": "ask",
            "visit": 1,
            "step_execution_id": "ask:1",
            "control": "fail",
            "hook": "on_done_taken",
            "source_phase": "on_taken",
            "reason": "Stop after route review.",
        }
    ]
