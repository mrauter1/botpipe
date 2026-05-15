from __future__ import annotations

from botpipe.core.errors import FailureContext
from tests.contract.engine._shared import _chain_hooks, _workspace
from tests.contract.engine._shared import *


def _provider_failure(message: str, *, step_name: str, provider_failure_stage: str) -> ProviderExecutionError:
    return ProviderExecutionError(
        message,
        failure_context=FailureContext(
            kind="malformed_provider_output",
            step_name=step_name,
            provider_attributable=True,
            details={"error": message, "provider_failure_stage": provider_failure_stage},
        ),
        retry_kind="malformed_provider_output",
    )


def _provider_transport_failure(message: str, *, step_name: str) -> ProviderExecutionError:
    return ProviderExecutionError(
        message,
        failure_context=FailureContext(
            kind="provider_transport_failure",
            step_name=step_name,
            provider_attributable=True,
            details={"error": message, "provider_failure_stage": "transport"},
        ),
        retry_kind="provider_transport_failure",
    )


def test_llm_step_retries_illegal_route_twice_and_succeeds_on_third_attempt(tmp_path: Path):
    def _retryrouteworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'final_note': ctx.outcome.raw_output})
        return None

    class RetryRouteWorkflow(Workflow):
        class State(BaseModel):
            final_note: str = ""

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}, GLOBAL: {"failed": FAIL}}

    RetryRouteWorkflow.ask.after = _chain_hooks(_retryrouteworkflow_on_ask, RetryRouteWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="first", tag="unexpected"),
            Outcome(raw_output="second", tag="unexpected"),
            Outcome(raw_output="third", tag="done"),
        ]
    )
    result = Engine(
        RetryRouteWorkflow,
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
    assert result.state.final_note == "third"
    assert [call.attempt for call in provider.calls] == [1, 2, 3]
    assert provider.calls[0].retry_feedback is None
    assert provider.calls[1].retry_feedback is not None
    assert "selected route was not allowed" in provider.calls[1].retry_feedback
    assert provider.calls[2].retry_feedback is not None
def test_llm_step_retries_invalid_payload_twice_and_succeeds_on_third_attempt(tmp_path: Path):
    class ReviewPayload(BaseModel):
        summary: str

    def _retrypayloadworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'summary': ctx.outcome.payload['summary']})
        return None

    class RetryPayloadWorkflow(Workflow):
        class State(BaseModel):
            summary: str = ""

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            expected_output_schema=ReviewPayload,
            route_metadata={"done": "workflow completed cleanly"},
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}

    RetryPayloadWorkflow.ask.after = _chain_hooks(_retrypayloadworkflow_on_ask, RetryPayloadWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="one", tag="done", payload={}),
            Outcome(raw_output="two", tag="done", payload={}),
            Outcome(raw_output="three", tag="done", payload={"summary": "ready"}),
        ]
    )
    result = Engine(
        RetryPayloadWorkflow,
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
    assert result.state.summary == "ready"
    assert [call.attempt for call in provider.calls] == [1, 2, 3]
    assert provider.calls[1].retry_feedback is not None
    assert "The selected route 'done' has an invalid payload:" in provider.calls[1].retry_feedback
    assert "summary" in provider.calls[1].retry_feedback
def test_retry_policy_can_disable_illegal_route_retries(tmp_path: Path):
    def _noillegalrouteretryworkflow_on_ask(ctx):
        return None

    class NoIllegalRouteRetryWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            retry_policy=ProviderRetryPolicy(
                max_attempts=3,
                retry_illegal_route=False,
            ),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}, GLOBAL: {"failed": FAIL}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="bad-route", tag="unexpected"),
            Outcome(raw_output="would-have-succeeded", tag="done"),
        ]
    )
    engine = Engine(
        NoIllegalRouteRetryWorkflow,
        provider=provider,
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
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "illegal_route"
    assert "retry_exhausted" not in checkpoint.failure_context
    assert len(provider.calls) == 1
    assert provider.calls[0].attempt == 1
    assert provider.calls[0].retry_feedback is None
def test_llm_step_retries_malformed_provider_output_twice_and_succeeds_on_third_attempt(tmp_path: Path):
    def _retrymalformedoutputworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'note': ctx.outcome.raw_output})
        return None

    class RetryMalformedOutputWorkflow(Workflow):
        class State(BaseModel):
            note: str = ""

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}

    RetryMalformedOutputWorkflow.ask.after = _chain_hooks(_retrymalformedoutputworkflow_on_ask, RetryMalformedOutputWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: OutcomeResponse(outcome="bad"),  # type: ignore[arg-type]
            lambda request: OutcomeResponse(outcome="still-bad"),  # type: ignore[arg-type]
            Outcome(raw_output="third", tag="done"),
        ]
    )
    result = Engine(
        RetryMalformedOutputWorkflow,
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
    assert result.state.note == "third"
    assert [call.attempt for call in provider.calls] == [1, 2, 3]
    assert provider.calls[0].retry_feedback is None
    assert provider.calls[1].retry_feedback is not None
    assert "could not be parsed into a valid workflow outcome" in provider.calls[1].retry_feedback
    assert "Expected outcome schema:" in provider.calls[1].retry_feedback
    assert "Canonical outcome envelope:" not in provider.calls[1].retry_feedback
    assert provider.calls[2].retry_feedback is not None
def test_llm_step_explicit_outcome_contract_retry_includes_schema_feedback(tmp_path: Path):
    def outcome_contract_failure(_request):
        raise _provider_failure(
            "provider returned malformed outcome JSON: Expecting ',' delimiter",
            step_name="ask",
            provider_failure_stage="outcome_contract",
        )

    class RetryInferredOutcomeContractWorkflow(Workflow):
        class State(BaseModel):
            note: str = ""

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            outcome_contract_failure,
            Outcome(raw_output="recovered", tag="done"),
        ]
    )
    result = Engine(
        RetryInferredOutcomeContractWorkflow,
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
    assert provider.calls[1].retry_feedback is not None
    assert "Expected outcome schema:" in provider.calls[1].retry_feedback


def test_llm_step_explicit_adapter_output_retry_omits_schema_feedback(tmp_path: Path):
    def adapter_output_failure(_request):
        raise _provider_failure(
            "provider 'claude' returned malformed JSON output: Expecting value",
            step_name="ask",
            provider_failure_stage="adapter_output",
        )

    class RetryAdapterOutputWorkflow(Workflow):
        class State(BaseModel):
            note: str = ""

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            adapter_output_failure,
            Outcome(raw_output="recovered", tag="done"),
        ]
    )
    result = Engine(
        RetryAdapterOutputWorkflow,
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
    assert provider.calls[1].retry_feedback is not None
    assert "malformed JSON output" in provider.calls[1].retry_feedback
    assert "Expected outcome schema:" not in provider.calls[1].retry_feedback
    assert "Canonical outcome envelope:" not in provider.calls[1].retry_feedback
def test_llm_step_retries_provider_transport_failure_twice_and_succeeds_on_third_attempt(tmp_path: Path):
    def _retrytransportfailureworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'note': ctx.outcome.raw_output})
        return None

    class RetryTransportFailureWorkflow(Workflow):
        class State(BaseModel):
            note: str = ""

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}

    RetryTransportFailureWorkflow.ask.after = _chain_hooks(_retrytransportfailureworkflow_on_ask, RetryTransportFailureWorkflow.ask.after)


    def transport_failure(_request):
        raise _provider_transport_failure("provider failed while running step 'ask': boom", step_name="ask")

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            transport_failure,
            transport_failure,
            Outcome(raw_output="recovered", tag="done"),
        ]
    )
    result = Engine(
        RetryTransportFailureWorkflow,
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
    assert result.state.note == "recovered"
    assert [call.attempt for call in provider.calls] == [1, 2, 3]
    assert provider.calls[0].retry_feedback is None
    assert provider.calls[1].retry_feedback is not None
    assert "transport failed before a usable response was accepted" in provider.calls[1].retry_feedback
    assert provider.calls[2].retry_feedback is not None
def test_pair_step_retries_from_producer_when_route_required_artifact_is_missing(tmp_path: Path):
    def _retrypairworkflow_on_review(ctx):
        if ctx.outcome.payload.get('write_report'):
            ctx.artifacts.report.write_text('ready')
        ctx.state = ctx.state.model_copy(update={'verified': True})
        return None

    class RetryPairWorkflow(Workflow):
        class State(BaseModel):
            verified: bool = False

        review = ProduceVerifyStep(
            name="review",
            producer="review.md",
            verifier="verify.md",
            producer_writes={"report": Artifact.md("report.md")},
            route_metadata={"done": Route(summary="review completed", required_writes=("report",))},
        )
        entry = review
        transitions = {review: {"done": FINISH}}

    RetryPairWorkflow.review.after_verifier = _chain_hooks(_retrypairworkflow_on_review, RetryPairWorkflow.review.after_verifier)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=["draft-one", "draft-two"],
        verifier_turns=[
            Outcome(raw_output="verify-one", tag="done", payload={"write_report": False}),
            Outcome(raw_output="verify-two", tag="done", payload={"write_report": True}),
        ],
    )
    result = Engine(
        RetryPairWorkflow,
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
    assert result.state.verified is True
    assert [(call.kind, call.attempt) for call in provider.calls] == [
        ("producer", 1),
        ("verifier", 1),
        ("producer", 2),
        ("verifier", 2),
    ]
    assert [ref.qualified_name for ref in provider.calls[0].writable_artifacts] == ["review.report"]
    assert provider.calls[0].route_required_writes == {}
    assert provider.calls[2].retry_feedback is not None
    assert "missing required output artifact" in provider.calls[2].retry_feedback
    assert "draft-one" not in provider.calls[2].retry_feedback
    assert "verify-one" not in provider.calls[2].retry_feedback
def test_pair_step_retries_producer_adapter_output_without_outcome_schema_feedback(tmp_path: Path):
    def producer_adapter_output_failure(_request):
        raise _provider_failure(
            "provider 'codex' returned unusable JSONL output.",
            step_name="review",
            provider_failure_stage="adapter_output",
        )

    class RetryPairProducerAdapterOutputWorkflow(Workflow):
        class State(BaseModel):
            pass

        review = ProduceVerifyStep(
            name="review",
            producer="review.md",
            verifier="verify.md",
            route_metadata={"done": "review completed"},
        )
        entry = review
        transitions = {review: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=[producer_adapter_output_failure, "draft-two"],
        verifier_turns=[Outcome(raw_output="verify-two", tag="done")],
    )
    result = Engine(
        RetryPairProducerAdapterOutputWorkflow,
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
    assert [(call.kind, call.attempt) for call in provider.calls] == [
        ("producer", 1),
        ("producer", 2),
        ("verifier", 2),
    ]
    assert provider.calls[1].retry_feedback is not None
    assert "unusable JSONL output" in provider.calls[1].retry_feedback
    assert "Expected outcome schema:" not in provider.calls[1].retry_feedback
    assert "Canonical outcome envelope:" not in provider.calls[1].retry_feedback


def test_pair_step_retries_malformed_verifier_output_with_outcome_schema_feedback(tmp_path: Path):
    class RetryPairMalformedVerifierWorkflow(Workflow):
        class State(BaseModel):
            verified: bool = False

        review = ProduceVerifyStep(
            name="review",
            producer="review.md",
            verifier="verify.md",
            route_metadata={"done": "review completed"},
        )
        entry = review
        transitions = {review: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=["draft-one", "draft-two"],
        verifier_turns=[
            lambda request: OutcomeResponse(outcome="bad"),  # type: ignore[arg-type]
            Outcome(raw_output="verify-two", tag="done"),
        ],
    )
    result = Engine(
        RetryPairMalformedVerifierWorkflow,
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
    assert [(call.kind, call.attempt) for call in provider.calls] == [
        ("producer", 1),
        ("verifier", 1),
        ("producer", 2),
        ("verifier", 2),
    ]
    assert provider.calls[2].retry_feedback is not None
    assert "must return Outcome instances" in provider.calls[2].retry_feedback
    assert "Expected outcome schema:" in provider.calls[2].retry_feedback
    assert "Canonical outcome envelope:" not in provider.calls[2].retry_feedback
def test_handler_exception_saves_failure_checkpoint(tmp_path: Path):
    def _explodingworkflow_on_ask(ctx):
        raise RuntimeError('boom')

    class ExplodingWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}

    ExplodingWorkflow.ask.after = _chain_hooks(_explodingworkflow_on_ask, ExplodingWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        ExplodingWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="boom"):
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
def test_extension_failure_semantics_checkpoint_latest_state_and_surface_terminal(tmp_path: Path):
    terminals: list[TerminalFinish] = []

    class FailingExtension:
        def bind(self, binding: RunBinding):
            class Bound:
                def before_step(self, event: StepStart) -> None:
                    return None

                def after_step(self, event: StepFinish) -> None:
                    raise RuntimeError("extension boom")

                def on_terminal(self, event: TerminalFinish) -> None:
                    terminals.append(event)

            return Bound()

    def _extensionfailureworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'calls': ctx.state.calls + 1})
        return None

    class ExtensionFailureWorkflow(Workflow):
        class State(BaseModel):
            calls: int = 0

        extensions = (FailingExtension(),)
        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}

    ExtensionFailureWorkflow.ask.after = _chain_hooks(_extensionfailureworkflow_on_ask, ExtensionFailureWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        ExtensionFailureWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(RuntimeError, match="extension boom"):
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
    assert checkpoint.state.calls == 1
    assert len(terminals) == 1
    assert terminals[0].terminal == "fatal"
    assert terminals[0].step_name == "ask"
    assert terminals[0].state is not None
    assert terminals[0].state.calls == 1
def test_retry_budget_exhaustion_checkpoints_failure_context_and_attempt_count(tmp_path: Path):
    def _exhaustedretryworkflow_on_ask(ctx):
        return None

    class ExhaustedRetryWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"summary": Artifact.md("summary.md", required=True)},
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="one", tag="done"),
            Outcome(raw_output="two", tag="done"),
            Outcome(raw_output="three", tag="done"),
        ]
    )
    engine = Engine(
        ExhaustedRetryWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(ProviderExecutionError, match=r"artifact validation failed.*summary"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "missing_required_output_artifact"
    assert checkpoint.failure_context["artifact_name"] == "summary"
    assert checkpoint.failure_context["retry_attempts_consumed"] == 3
    assert checkpoint.failure_context["retry_max_attempts"] == 3
    assert checkpoint.failure_context["retry_exhausted"] is True
    assert len(provider.calls) == 3
def test_engine_emits_provider_attempt_events_with_step_execution_identity(tmp_path: Path):
    def _attempteventworkflow_on_ask(ctx):
        return None

    class AttemptEventWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    runtime_events: list[tuple[str, dict[str, object]]] = []
    result = Engine(
        AttemptEventWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-attempt-events",
        run_id="run-attempt-events",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert runtime_events[:3] == [
        (
            "provider_policy_resolved",
            {
                "policy_fingerprint": runtime_events[0][1]["policy_fingerprint"],
                "step_name": "ask",
                "visit": 1,
                "step_execution_id": "ask:1",
            },
        ),
        (
            "provider_attempt_started",
            {
                "step_name": "ask",
                "visit": 1,
                "step_execution_id": "ask:1",
                "turn_kind": "llm",
                "attempt": 1,
            },
        ),
        (
            "provider_attempt_finished",
            {
                "step_name": "ask",
                "visit": 1,
                "step_execution_id": "ask:1",
                "turn_kind": "llm",
                "attempt": 1,
            },
        ),
    ]
