from __future__ import annotations

from tests.contract.engine._shared import (
    _RenderedTransportStub,
    _chain_hooks,
    _install_fake_jsonschema_validator,
    _workspace,
)
from tests.contract.engine._shared import *

def test_route_objects_execute_without_breaking_engine_routing(tmp_path: Path):
    def _typedrouteworkflow_on_ask(ctx):
        return None

    def _typedrouteworkflow_on_finish(ctx):
        ctx.state = ctx.state.model_copy(update={'finished': True})
        return Event('complete')

    class TypedRouteWorkflow(Workflow):
        class State(BaseModel):
            finished: bool = False

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Answer the request."),
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        finish = PythonStep(name="finish", handler=_typedrouteworkflow_on_finish)
        entry = ask
        transitions = {
            ask: {"done": Route.to(finish)},
            finish: {"complete": Route.finish()},
        }


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        TypedRouteWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok\n", tag="done")]),
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
    assert result.history == ("ask", "finish")
def test_full_auto_hides_default_question_route_from_provider_contract(tmp_path: Path):
    class FullAutoQuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Answer the request."),
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])
    result = Engine(
        FullAutoQuestionWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        interaction_policy=RuntimeInteractionPolicy(allow_provider_questions=False),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert provider.calls[0].available_routes == ("done",)
def test_invalid_route_tag_raises_provider_execution_error_and_checkpoints(tmp_path: Path):
    def _invalidrouteworkflow_on_ask(ctx):
        return None

    class InvalidRouteWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Answer the request."),
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {"done": FINISH},
            GLOBAL: {"failed": FAIL},
        }


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        InvalidRouteWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="oops", tag="unexpected")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(ProviderExecutionError, match="illegal route 'unexpected'"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"
    assert len(engine.provider.calls) == 1
    assert engine.provider.calls[0].attempt == 1
    assert engine.provider.calls[0].retry_feedback is None
def test_invalid_expected_output_payload_raises_provider_execution_error_and_checkpoints(tmp_path: Path):
    class ReviewPayload(BaseModel):
        summary: str

    def _invalidpayloadworkflow_on_ask(ctx):
        return None

    class InvalidPayloadWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            expected_output_schema=ReviewPayload,
            route_metadata={"done": "workflow completed cleanly"},
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        InvalidPayloadWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done", payload={})]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(ProviderExecutionError, match="invalid payload"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"
    assert len(engine.provider.calls) == 1
    assert engine.provider.calls[0].attempt == 1
def test_scripted_provider_rejects_invalid_custom_raw_route_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_jsonschema_validator(monkeypatch)
    raw_payload_schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    }

    class RawRoutePayloadWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Answer the request."),
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {
                "done": Route.finish(payload_schema=raw_payload_schema),
            }
        }

    task_folder, run_folder = _workspace(tmp_path)
    with pytest.raises(ProviderExecutionError, match="invalid payload"):
        Engine(
            RawRoutePayloadWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="bad payload", tag="done", payload={})]),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-raw-route-payload-scripted",
            run_id="run-raw-route-payload-scripted",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_scripted_provider_rejects_invalid_custom_raw_route_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_jsonschema_validator(monkeypatch)
    raw_route_fields_schema = {
        "type": "object",
        "properties": {"reason": {"type": "string"}},
        "required": ["reason"],
        "additionalProperties": False,
    }

    class RawRouteFieldsWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Answer the request."),
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {
                "done": Route.finish(route_fields_schema=raw_route_fields_schema),
            }
        }

    task_folder, run_folder = _workspace(tmp_path)
    with pytest.raises(ProviderExecutionError, match="invalid payload"):
        Engine(
            RawRouteFieldsWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="bad route fields", tag="done", route_fields={})]),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-raw-route-fields-scripted",
            run_id="run-raw-route-fields-scripted",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_rendered_provider_rejects_invalid_custom_raw_route_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_jsonschema_validator(monkeypatch)
    raw_payload_schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    }

    class RawRoutePayloadWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Answer the request."),
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {
                "done": Route.finish(payload_schema=raw_payload_schema),
            }
        }

    task_folder, run_folder = _workspace(tmp_path)
    transport = _RenderedTransportStub(raw_text='{"outcome":{"tag":"done","payload":{},"route_fields":{}}}')

    with pytest.raises(ProviderExecutionError, match="invalid payload"):
        Engine(
            RawRoutePayloadWorkflow,
            provider=RenderedLLMProvider(transport),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-raw-route-payload-rendered",
            run_id="run-raw-route-payload-rendered",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_rendered_provider_rejects_invalid_custom_raw_route_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_jsonschema_validator(monkeypatch)
    raw_route_fields_schema = {
        "type": "object",
        "properties": {"reason": {"type": "string"}},
        "required": ["reason"],
        "additionalProperties": False,
    }

    class RawRouteFieldsWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Answer the request."),
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {
                "done": Route.finish(route_fields_schema=raw_route_fields_schema),
            }
        }

    task_folder, run_folder = _workspace(tmp_path)
    transport = _RenderedTransportStub(raw_text='{"outcome":{"tag":"done","payload":{},"route_fields":{}}}')

    with pytest.raises(ProviderExecutionError, match="invalid payload"):
        Engine(
            RawRouteFieldsWorkflow,
            provider=RenderedLLMProvider(transport),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-raw-route-fields-rendered",
            run_id="run-raw-route-fields-rendered",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_question_route_requires_question_field(tmp_path: Path):
    def _questionworkflow_on_ask(ctx):
        return None

    class QuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {ask: {"question": AWAIT_INPUT}}


    task_folder, run_folder = _workspace(tmp_path)
    with pytest.raises(ProviderExecutionError, match="question route without a non-empty question"):
        Engine(
            QuestionWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="need input", tag="question")]),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_provider_invalid_question_retries_and_recovers(tmp_path: Path):
    def _questionworkflow_on_ask(ctx):
        return None

    class QuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=2))
        entry = ask
        transitions = {ask: {"question": AWAIT_INPUT}}


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="need input", tag="question", reason="Need input"),
            Outcome(raw_output="need input", tag="question", reason="Need input", question="Approve?"),
        ]
    )
    result = Engine(
        QuestionWorkflow,
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

    assert result.terminal == AWAIT_INPUT
    assert result.checkpoint is not None
    assert result.checkpoint.pending_input is not None
    assert result.checkpoint.pending_input.question == "Approve?"
    assert [call.attempt for call in provider.calls] == [1, 2]
    assert provider.calls[1].retry_feedback is not None
    assert (
        "The selected route 'question' has an invalid payload: "
        "question route requires a non-empty question field."
    ) in provider.calls[1].retry_feedback
def test_rendered_provider_invalid_question_retries_and_recovers(tmp_path: Path):
    class QuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Ask for the missing input when needed."),
            retry_policy=ProviderRetryPolicy(max_attempts=2),
        )
        entry = ask
        transitions = {ask: {"question": AWAIT_INPUT}}

    task_folder, run_folder = _workspace(tmp_path)
    transport = _RenderedTransportStub(
        raw_texts=[
            '{"tag":"question"}',
            '{"tag":"question","question":"Approve?"}',
        ]
    )
    result = Engine(
        QuestionWorkflow,
        provider=RenderedLLMProvider(transport),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == AWAIT_INPUT
    assert result.checkpoint is not None
    assert result.checkpoint.pending_input is not None
    assert result.checkpoint.pending_input.question == "Approve?"
    assert len(transport.turns) == 2
    assert (
        "The selected route 'question' has an invalid payload: "
        "question route requires a non-empty question field."
    ) in transport.turns[1].prompt_text
def test_rendered_provider_canonical_question_route_does_not_fall_back_to_legacy_question(tmp_path: Path):
    class QuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Ask for the missing input when needed."),
            retry_policy=ProviderRetryPolicy(max_attempts=2),
        )
        entry = ask
        transitions = {ask: {"question": AWAIT_INPUT}}

    task_folder, run_folder = _workspace(tmp_path)
    transport = _RenderedTransportStub(
        raw_texts=[
            '{"outcome":{"tag":"question","payload":{},"route_fields":{}},"question":"Legacy?"}',
            '{"outcome":{"tag":"question","payload":{},"route_fields":{"questions":["Approve?"],"reason":null}}}',
        ]
    )
    result = Engine(
        QuestionWorkflow,
        provider=RenderedLLMProvider(transport),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == AWAIT_INPUT
    assert result.checkpoint is not None
    assert result.checkpoint.pending_input is not None
    assert result.checkpoint.pending_input.question == "Approve?"
    assert len(transport.turns) == 2
    assert (
        "The selected route 'question' has an invalid payload: "
        "question route requires a non-empty question field."
    ) in transport.turns[1].prompt_text
def test_explicit_blocked_and_failed_routes_do_not_require_reason_field(tmp_path: Path):
    def _failureworkflow_on_ask(ctx):
        return None

    class FailureWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Choose a legal route."),
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {ask: {"blocked": AWAIT_INPUT, "failed": FAIL}}

    task_folder, run_folder = _workspace(tmp_path)
    blocked_result = Engine(
        FailureWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="blocked", tag="blocked")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-blocked",
        run_id="run-blocked",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )
    failed_result = Engine(
        FailureWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="failed", tag="failed")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-failed",
        run_id="run-failed",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert blocked_result.terminal == AWAIT_INPUT
    assert blocked_result.last_event is not None
    assert blocked_result.last_event.tag == "blocked"
    assert blocked_result.last_event.reason == ""
    assert failed_result.terminal == FAIL
    assert failed_result.last_event is not None
    assert failed_result.last_event.tag == "failed"
    assert failed_result.last_event.reason == ""
def test_rendered_provider_matches_direct_reason_optional_behavior_for_explicit_blocked_and_failed_routes(tmp_path: Path):
    class FailureWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Choose a legal route."),
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {ask: {"blocked": AWAIT_INPUT, "failed": FAIL}}

    task_folder, run_folder = _workspace(tmp_path)
    blocked_result = Engine(
        FailureWorkflow,
        provider=RenderedLLMProvider(_RenderedTransportStub(raw_text='{"tag":"blocked"}')),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-blocked",
        run_id="run-blocked",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )
    failed_result = Engine(
        FailureWorkflow,
        provider=RenderedLLMProvider(_RenderedTransportStub(raw_text='{"tag":"failed"}')),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-failed",
        run_id="run-failed",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert blocked_result.terminal == AWAIT_INPUT
    assert blocked_result.last_event is not None
    assert blocked_result.last_event.tag == "blocked"
    assert blocked_result.last_event.reason == ""
    assert failed_result.terminal == FAIL
    assert failed_result.last_event is not None
    assert failed_result.last_event.tag == "failed"
    assert failed_result.last_event.reason == ""
def test_provider_question_route_is_illegal_in_full_auto_mode(tmp_path: Path):
    def _fullautoworkflow_on_ask(ctx):
        return None

    class FullAutoQuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Choose a legal route."),
            retry_policy=ProviderRetryPolicy(max_attempts=2),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="need input", tag="question", question="Approve?"),
            Outcome(raw_output="done", tag="done"),
        ]
    )
    result = Engine(
        FullAutoQuestionWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        interaction_policy=RuntimeInteractionPolicy(allow_provider_questions=False),
    ).run(
        task_id="task-full-auto",
        run_id="run-full-auto",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert [call.attempt for call in provider.calls] == [1, 2]
    assert provider.calls[1].retry_feedback is not None
    assert "The selected route was not allowed for step 'ask'." in provider.calls[1].retry_feedback
def test_rendered_provider_question_route_is_illegal_in_full_auto_mode(tmp_path: Path):
    class FullAutoQuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Choose a legal route."),
            retry_policy=ProviderRetryPolicy(max_attempts=2),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    transport = _RenderedTransportStub(
        raw_texts=[
            '{"tag":"question","question":"Approve?"}',
            '{"tag":"done"}',
        ]
    )
    result = Engine(
        FullAutoQuestionWorkflow,
        provider=RenderedLLMProvider(transport),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        interaction_policy=RuntimeInteractionPolicy(allow_provider_questions=False),
    ).run(
        task_id="task-full-auto",
        run_id="run-full-auto",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert len(transport.turns) == 2
    assert "question-style route" in transport.turns[1].prompt_text
    assert "outcome.route_fields.questions" in transport.turns[1].prompt_text
def test_provider_invalid_question_retry_exhaustion_marks_failure_context(tmp_path: Path):
    def _questionworkflow_on_ask(ctx):
        return None

    class QuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=2))
        entry = ask
        transitions = {ask: {"question": AWAIT_INPUT}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="need input", tag="question", reason="Need input"),
            Outcome(raw_output="need input", tag="question", reason="Need input"),
        ]
    )
    engine = Engine(
        QuestionWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(ProviderExecutionError, match="question route without a non-empty question"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"
    assert checkpoint.pending_question is None
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "invalid_payload"
    assert checkpoint.failure_context["route"] == "question"
    assert checkpoint.failure_context["provider_attributable"] is True
    assert checkpoint.failure_context["retry_exhausted"] is True
    assert [call.attempt for call in provider.calls] == [1, 2]
def test_rendered_provider_invalid_question_retry_exhaustion_marks_failure_context(tmp_path: Path):
    class QuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer=Prompt.inline("Ask for the missing input when needed."),
            retry_policy=ProviderRetryPolicy(max_attempts=2),
        )
        entry = ask
        transitions = {ask: {"question": AWAIT_INPUT}}

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        QuestionWorkflow,
        provider=RenderedLLMProvider(
            _RenderedTransportStub(
                raw_texts=[
                    '{"tag":"question"}',
                    '{"tag":"question"}',
                ]
            )
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(ProviderExecutionError, match="question route without a non-empty question"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"
    assert checkpoint.pending_question is None
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "invalid_payload"
    assert checkpoint.failure_context["route"] == "question"
    assert checkpoint.failure_context["provider_attributable"] is True
    assert checkpoint.failure_context["retry_exhausted"] is True
def test_route_handoff_combines_static_and_dynamic_messages_for_target_provider_step(tmp_path: Path):
    def _handoffworkflow_on_start(ctx):
        return Event('review', handoff='Dynamic handoff.')

    def _handoffworkflow_on_review(ctx):
        ctx.state = ctx.state.model_copy(update={'done': True})
        return None

    def _handoffworkflow_on_finish(ctx):
        return Event('complete')

    class HandoffWorkflow(Workflow):
        class State(BaseModel):
            done: bool = False

        start = PythonStep(name="start", handler=_handoffworkflow_on_start)
        review = PromptStep(name="review", producer="review.md")
        finish = PythonStep(name="finish", handler=_handoffworkflow_on_finish)
        entry = start
        transitions = {
            start: {"review": Route.to(review, handoff="Static handoff.")},
            review: {"done": finish},
            finish: {"complete": FINISH},
        }
    HandoffWorkflow.review.after = _chain_hooks(_handoffworkflow_on_review, HandoffWorkflow.review.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])
    engine = Engine(
        HandoffWorkflow,
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
    assert provider.calls[0].route_handoff == "Static handoff.\n\nDynamic handoff."
def test_route_handoff_is_consumed_after_first_dispatch(tmp_path: Path):
    def _consumeonceworkflow_on_start(ctx):
        return Event('ask')

    def _consumeonceworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'passes': ctx.state.passes + 1})
        return None

    def _consumeonceworkflow_on_finish(ctx):
        return Event('complete')

    class ConsumeOnceWorkflow(Workflow):
        class State(BaseModel):
            passes: int = 0

        start = PythonStep(name="start", handler=_consumeonceworkflow_on_start)
        ask = PromptStep(name="ask", producer="ask.md")
        finish = PythonStep(name="finish", handler=_consumeonceworkflow_on_finish)
        entry = start
        transitions = {
            start: {"ask": Route.to(ask, handoff="Use this handoff once.")},
            ask: {"redo": ask, "done": finish},
            finish: {"complete": FINISH},
        }
    ConsumeOnceWorkflow.ask.after = _chain_hooks(_consumeonceworkflow_on_ask, ConsumeOnceWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="first", tag="redo"),
            Outcome(raw_output="second", tag="done"),
        ]
    )
    engine = Engine(
        ConsumeOnceWorkflow,
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
    assert [call.route_handoff for call in provider.calls] == ["Use this handoff once.", None]
def test_route_handoff_is_scoped_to_the_active_worklist_item(tmp_path: Path):
    def _scopedhandoffworkflow_on_outcome(ctx):
        if ctx.outcome.tag == 'review':
            item_id = str(ctx.outcome.payload['item_id'])
            return Event('review', handoff=f'handoff:{item_id}')
        return None

    def _scopedhandoffworkflow_on_draft(ctx):
        return None

    def _scopedhandoffworkflow_on_review(ctx):
        item_id = str(ctx.outcome.payload['item_id'])
        ctx.state = ctx.state.model_copy(update={'reviewed': [*ctx.state.reviewed, item_id]})
        return None

    def _scopedhandoffworkflow_on_advance(ctx):
        ctx.worklists.gate.advance()
        return Event('draft')

    def _scopedhandoffworkflow_on_finish(ctx):
        return Event('complete')

    class ScopedHandoffWorkflow(Workflow):
        class State(BaseModel):
            reviewed: list[str] = Field(default_factory=list)

        gates = Worklist.from_items(
            name="gate",
            items=(
                {"id": "alpha", "title": "Alpha"},
                {"id": "beta", "title": "Beta"},
            ),
        )
        draft = PromptStep(name="draft", producer="draft.md", scope=gates)
        review = PromptStep(name="review", producer="review.md", scope=gates)
        advance = PythonStep(name="advance", handler=_scopedhandoffworkflow_on_advance)
        finish = PythonStep(name="finish", handler=_scopedhandoffworkflow_on_finish)
        entry = draft
        transitions = {
            draft: {"review": review},
            review: {"next": advance, "done": finish},
            advance: {"draft": draft},
            finish: {"complete": FINISH},
        }
    ScopedHandoffWorkflow.draft.after = _chain_hooks(_scopedhandoffworkflow_on_outcome, _scopedhandoffworkflow_on_draft, ScopedHandoffWorkflow.draft.after)
    ScopedHandoffWorkflow.review.after = _chain_hooks(_scopedhandoffworkflow_on_outcome, _scopedhandoffworkflow_on_review, ScopedHandoffWorkflow.review.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: Outcome(raw_output="draft alpha", tag="review", payload={"item_id": request.context.item.id}),
            lambda request: Outcome(raw_output="review alpha", tag="next", payload={"item_id": request.context.item.id}),
            lambda request: Outcome(raw_output="draft beta", tag="review", payload={"item_id": request.context.item.id}),
            lambda request: Outcome(raw_output="review beta", tag="done", payload={"item_id": request.context.item.id}),
        ]
    )
    engine = Engine(
        ScopedHandoffWorkflow,
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

    review_calls = [call for call in provider.calls if call.step_name == "review"]

    assert result.terminal == FINISH
    assert [call.route_handoff for call in review_calls] == ["handoff:alpha", "handoff:beta"]
def test_route_handoff_survives_checkpoint_resume_before_dispatch_consumes_it(tmp_path: Path):
    def _resumehandoffworkflow_on_start(ctx):
        return Event('review')

    def _resumehandoffworkflow_on_review(ctx):
        ctx.state = ctx.state.model_copy(update={'done': True})
        return None

    def _resumehandoffworkflow_on_finish(ctx):
        return Event('complete')

    class ResumeHandoffWorkflow(Workflow):
        class State(BaseModel):
            done: bool = False

        start = PythonStep(name="start", handler=_resumehandoffworkflow_on_start)
        review = PromptStep(
            name="review",
            producer="review.md",
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        finish = PythonStep(name="finish", handler=_resumehandoffworkflow_on_finish)
        entry = start
        transitions = {
            start: {"review": Route.to(review, handoff="Resume this handoff.")},
            review: {"done": finish},
            finish: {"complete": FINISH},
        }
    ResumeHandoffWorkflow.review.after = _chain_hooks(_resumehandoffworkflow_on_review, ResumeHandoffWorkflow.review.after)


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    failing_engine = Engine(
        ResumeHandoffWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[lambda request: (_ for _ in ()).throw(RuntimeError("transport crashed"))]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="transport crashed"):
        failing_engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.pending_handoffs

    resumed_provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])
    resumed_engine = Engine(
        ResumeHandoffWorkflow,
        provider=resumed_provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    result = resumed_engine.resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert resumed_provider.calls[0].route_handoff == "Resume this handoff."
def test_route_handoff_targeting_system_step_is_dropped_before_later_provider_step(tmp_path: Path):
    def _systemtargethandoffworkflow_on_outcome(ctx):
        if ctx.outcome.tag == 'bridge':
            return Event('bridge', handoff='Drop this at the system step.')
        return None

    def _systemtargethandoffworkflow_on_ask(ctx):
        return None

    def _systemtargethandoffworkflow_on_bridge(ctx):
        return Event('review')

    def _systemtargethandoffworkflow_on_review(ctx):
        ctx.state = ctx.state.model_copy(update={'reviewed': True})
        return None

    def _systemtargethandoffworkflow_on_finish(ctx):
        return Event('complete')

    class SystemTargetHandoffWorkflow(Workflow):
        class State(BaseModel):
            reviewed: bool = False

        ask = PromptStep(name="ask", producer="ask.md")
        bridge = PythonStep(name="bridge", handler=_systemtargethandoffworkflow_on_bridge)
        review = PromptStep(name="review", producer="review.md")
        finish = PythonStep(name="finish", handler=_systemtargethandoffworkflow_on_finish)
        entry = ask
        transitions = {
            ask: {"bridge": bridge},
            bridge: {"review": review},
            review: {"done": finish},
            finish: {"complete": FINISH},
        }
    SystemTargetHandoffWorkflow.ask.after = _chain_hooks(_systemtargethandoffworkflow_on_outcome, _systemtargethandoffworkflow_on_ask, SystemTargetHandoffWorkflow.ask.after)
    SystemTargetHandoffWorkflow.review.after = _chain_hooks(_systemtargethandoffworkflow_on_outcome, _systemtargethandoffworkflow_on_review, SystemTargetHandoffWorkflow.review.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="route to bridge", tag="bridge"),
            Outcome(raw_output="reviewed", tag="done"),
        ]
    )
    engine = Engine(
        SystemTargetHandoffWorkflow,
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
    assert result.state.reviewed is True
    assert [call.route_handoff for call in provider.calls] == [None, None]
def test_route_handoff_targeting_workflow_step_is_dropped_before_later_provider_step(tmp_path: Path):
    def after_ask(ctx):
        if ctx.outcome.tag == "launch":
            return Event("launch", handoff="Drop this at the workflow step.")
        return None

    class ChildWorkflow(SimpleWorkflow):
        note = step("Write the child note.")

    class WorkflowTargetHandoffWorkflow(SimpleWorkflow):
        ask = step(
            prompt="Ask for child execution.",
            routes={"launch": "launch"},
            after=after_ask,
        )
        launch = workflow_step(ChildWorkflow, message="Run child workflow")
        review = step("Review the child result.")

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    child_runs: list[str] = []

    def invoke_child(workflow, *, message, parameters=None, input=None):
        child_runs.append(message)
        child_run_root = task_folder / "child-runs" / "child-1"
        child_run_root.mkdir(parents=True, exist_ok=True)
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id="child-1",
            terminal=FINISH,
            status="success",
            last_event=Event("done"),
            output_metadata={},
            output_artifacts={},
            task_folder=task_folder,
            workflow_folder=child_run_root,
            run_folder=child_run_root / "run",
            package_folder=child_run_root / "package",
            request_file=child_run_root / "request.md",
            run_meta_file=child_run_root / "run.json",
            events_file=child_run_root / "events.jsonl",
            checkpoint_file=child_run_root / "checkpoint.json",
            sessions_dir=child_run_root / "sessions",
            trace_file=child_run_root / "trace.jsonl",
            raw_dir=child_run_root / "raw",
            parent_file=child_run_root / "parent.json",
        )

    engine = Engine(
        WorkflowTargetHandoffWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                Outcome(raw_output="launch child", tag="launch"),
                lambda request: (_ for _ in ()).throw(RuntimeError("transport crashed")),
            ]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="transport crashed"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
            workflow_invoker=invoke_child,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.pending_handoffs == ()
    assert child_runs == ["Run child workflow"]
def test_route_handoff_targeting_terminal_is_not_persisted_in_pause_checkpoint(tmp_path: Path):
    def _terminaltargethandoffworkflow_on_outcome(ctx):
        return Event('pause', handoff='Drop this at pause.')

    def _terminaltargethandoffworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'paused': True})
        return None

    class TerminalTargetHandoffWorkflow(Workflow):
        class State(BaseModel):
            paused: bool = False

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"pause": AWAIT_INPUT}}


    TerminalTargetHandoffWorkflow.ask.after = _chain_hooks(_terminaltargethandoffworkflow_on_outcome, _terminaltargethandoffworkflow_on_ask, TerminalTargetHandoffWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="pause now", tag="pause")])
    engine = Engine(
        TerminalTargetHandoffWorkflow,
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

    assert result.terminal == AWAIT_INPUT
    assert result.checkpoint is not None
    assert result.checkpoint.pending_handoffs == ()
def test_hidden_routes_are_runtime_legal_but_excluded_from_provider_choices(tmp_path: Path):
    from botlane.runtime.static_graph import workflow_topology_payload

    def after_ask(ctx):
        return "human_escalation"

    def on_hidden_taken(ctx):
        ctx.state.seen.append("hidden-route-taken")

    def _hiddenrouteworkflow_on_ask(ctx):
        return None

    class HiddenRouteWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        ask = PromptStep(name="ask", producer="ask.md", after=after_ask, retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {
            ask: {
                "done": Route.to(FINISH),
                "human_escalation": Route.to(
                    FINISH,
                    on_taken=on_hidden_taken,
                    provider_visible=False,
                ),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])
    result = Engine(
        HiddenRouteWorkflow,
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

    topology = workflow_topology_payload(compile_workflow(HiddenRouteWorkflow))
    ask_topology = next(step for step in topology["steps"] if step["name"] == "ask")
    hidden_route = next(route for route in ask_topology["routes"] if route["tag"] == "human_escalation")

    assert "done" in provider.calls[0].available_routes
    assert "human_escalation" not in provider.calls[0].available_routes
    assert "done" in provider.calls[0].routes
    assert "human_escalation" not in provider.calls[0].routes
    assert result.terminal == FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "human_escalation"
    assert result.state.seen == ["hidden-route-taken"]
    assert hidden_route["provider_visible"] is False
def test_prompt_step_rejects_removed_on_route_keyword():
    with pytest.raises(TypeError, match="on_route"):
        PromptStep(name="ask", producer="ask.md", on_route=lambda ctx: None)
def test_produce_verify_step_sends_split_phase_contracts_without_implicitly_requiring_producer_writes(tmp_path: Path):
    def after_assess(ctx):
        ctx.artifacts.review_report.write_text("review report\n")
        return None

    class ReviewWorkflow(SimpleWorkflow):
        main = Session()
        reviewer = Session()

        assess = produce_verify_step(
            producer_prompt="Draft the assessment.",
            verifier_prompt="Review the assessment.",
            producer_writes=[Md("draft")],
            verifier_writes=[Md("review_report")],
            routes={
                "rejected": Route.to(FINISH, required_writes=["review_report"]),
            },
            session=main,
            verifier_session=reviewer,
            after_verifier=after_assess,
        )

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=["draft text"],
        verifier_turns=[Outcome(raw_output="reject", tag="rejected")],
    )

    result = Engine(
        ReviewWorkflow,
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
    assert provider.calls[0].kind == "producer"
    assert provider.calls[0].available_routes == ()
    assert [ref.name for ref in provider.calls[0].writable_artifacts] == ["draft"]
    assert provider.calls[0].required_artifacts == ()
    assert provider.calls[1].kind == "verifier"
    assert [ref.name for ref in provider.calls[1].writable_artifacts] == ["review_report"]
    assert provider.calls[1].required_artifacts == ()
    assert provider.calls[1].available_routes == ("rejected", "question")
def test_produce_verify_step_verifier_contract_preserves_explicit_empty_route_override(tmp_path: Path):
    class ReviewWorkflow(SimpleWorkflow):
        assess = produce_verify_step(
            producer_prompt="Draft the assessment.",
            verifier_prompt="Review the assessment.",
            producer_writes=[Md("draft", required=True)],
            verifier_writes=[Md("review_report", required=True)],
            retry=1,
            routes={
                "approved": Route.to(FINISH, required_writes=[]),
            },
        )

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.draft.write_text("draft text\n"),
                "draft text\n",
            )[1]
        ],
        verifier_turns=[
            lambda request: (
                request.artifacts.review_report.write_text("review report\n"),
                Outcome(raw_output="approve", tag="approved"),
            )[1]
        ],
    )

    result = Engine(
        ReviewWorkflow,
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
    assert provider.calls[0].kind == "producer"
    assert provider.calls[0].route_required_writes == {}
    assert provider.calls[1].kind == "verifier"
    assert provider.calls[1].routes["approved"].required_writes == ()
    assert provider.calls[1].routes["approved"].explicit_required_writes == ()
    assert provider.calls[1].route_required_writes == {
        "approved": (),
        "question": (),
    }
def test_produce_verify_step_verifier_requires_fail_before_verifier_when_declared(tmp_path: Path):
    def after_assess(ctx):
        return None

    class ReviewWorkflow(SimpleWorkflow):
        assess = produce_verify_step(
            producer_prompt="Draft the assessment.",
            verifier_prompt="Review the assessment.",
            producer_writes=[Md("draft")],
            verifier_requires=["draft"],
            verifier_writes=[Md("review_report")],
            routes={
                "approved": Route.to(FINISH, required_writes=["review_report"]),
            },
            retry=1,
            after_verifier=after_assess,
        )

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=["draft text"],
        verifier_turns=[Outcome(raw_output="approve", tag="approved")],
    )

    with pytest.raises(MissingArtifactError, match=r"required artifact 'draft' does not exist for step 'assess'"):
        Engine(
            ReviewWorkflow,
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

    assert [call.kind for call in provider.calls] == ["producer"]
