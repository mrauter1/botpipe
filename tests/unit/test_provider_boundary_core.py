from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass

import pytest

from autoloop.core.errors import ProviderExecutionError
from autoloop.core.prompts import ResolvedPrompt
from autoloop.core.providers.models import (
    LLMRequest,
    OperationRequest,
    OutcomeResponse,
    ProducerRequest,
    ProducerResponse,
    ProviderArtifactRef,
    ProviderReadableRef,
    ProviderRoute,
    ProviderTurnContext,
    TokenUsage,
    VerifierRequest,
)
from autoloop.core.providers.fake import ScriptedLLMProvider
from autoloop.core.providers.parsing import parse_outcome_json
from autoloop.core.providers.protocols import validate_llm_provider, validate_provider_transport
from autoloop.core.providers.rendered import RenderedLLMProvider
from autoloop.core.providers.rendering import ProviderPromptRenderPolicy, render_provider_turn_with_policy
from autoloop.core.providers.rendering import render_provider_turn
from autoloop.core.providers.turns import ProviderTurnResult, RenderedProviderTurn
from autoloop.core.stores.protocols import SessionBinding


def _session_binding(session_id: str = "provider-session-1") -> SessionBinding:
    return SessionBinding(ref_name="main", scope=None, session_id=session_id)


def _artifact_ref(
    name: str,
    *,
    path: str,
    kind: str = "markdown",
    required: bool = True,
    exists: bool = True,
    schema_name: str | None = None,
) -> ProviderArtifactRef:
    return ProviderArtifactRef(
        name=name,
        qualified_name=f"step.{name}",
        path=path,
        kind=kind,
        required=required,
        exists=exists,
        schema_name=schema_name,
    )


def _readable_ref(
    name: str,
    *,
    path: str,
    exists: bool,
    declared_artifact: bool,
    kind: str | None = "markdown",
    qualified_name: str | None = None,
    schema_name: str | None = None,
) -> ProviderReadableRef:
    return ProviderReadableRef(
        name=name,
        path=path,
        exists=exists,
        declared_artifact=declared_artifact,
        kind=kind,
        qualified_name=qualified_name,
        schema_name=schema_name,
    )


def _turn_context(
    *,
    prompt_text: str = "Follow the workflow-authored instructions.",
    route_handoff: str | None = None,
    retry_feedback: str | None = None,
) -> ProviderTurnContext:
    return ProviderTurnContext(
        step_name="design",
        turn_kind="verifier",
        prompt=ResolvedPrompt(path="design.md", text=prompt_text),
        context=object(),
        artifacts=object(),
        session=_session_binding(),
        expected_output_schema={
            "type": "object",
            "required": ["summary", "decision"],
            "properties": {
                "summary": {"type": "string", "description": "Concise decision summary."},
                "decision": {"type": "string"},
                "details": {
                    "type": "object",
                    "properties": {"owner": {"type": "string"}},
                },
            },
        },
        available_routes=("done", "needs_rework"),
        routes={
            "done": ProviderRoute(
                summary="Package the accepted design.",
                required_writes=("design_doc", "decision_record"),
                explicit_required_writes=("design_doc", "decision_record"),
            ),
            "needs_rework": ProviderRoute(
                summary="Repair the current design before packaging.",
                required_writes=("design_doc",),
                explicit_required_writes=("design_doc",),
            ),
        },
        readable_artifacts=(
            _readable_ref(
                "previous_decision",
                path="/tmp/previous-decision.md",
                exists=False,
                declared_artifact=False,
                kind=None,
            ),
            _readable_ref(
                "design_brief",
                path="/tmp/design-brief.md",
                exists=True,
                declared_artifact=True,
                qualified_name="design.design_brief",
            ),
        ),
        required_artifacts=(
            _artifact_ref("request", path="/tmp/request.md"),
            _artifact_ref("constraints", path="/tmp/constraints.json", kind="json", schema_name="Constraints"),
        ),
        writable_artifacts=(
            _artifact_ref("design_doc", path="/tmp/design.md", required=False),
            _artifact_ref(
                "decision_record",
                path="/tmp/decision.json",
                kind="json",
                required=False,
                exists=False,
                schema_name="DecisionRecord",
            ),
        ),
        route_required_writes={
            "done": ("design_doc", "decision_record"),
            "needs_rework": ("design_doc",),
        },
        route_handoff=route_handoff,
        retry_feedback=retry_feedback,
        attempt=2,
        max_attempts=3,
    )


def test_render_provider_turn_renders_markdown_contract_without_raw_output() -> None:
    turn = render_provider_turn(
        _turn_context(
            route_handoff="Repair the design and preserve the interface boundary.",
            retry_feedback="The previous attempt used an unsupported route.",
        )
    )

    assert turn.step_name == "design"
    assert turn.turn_kind == "verifier"
    assert turn.expected_response == "outcome_json"
    assert "# Step: design" in turn.prompt_text
    assert "## Runtime Step Contract" in turn.prompt_text
    assert "### Readable inputs" in turn.prompt_text
    assert "### Required inputs" in turn.prompt_text
    assert "### Declared artifacts this step may write" in turn.prompt_text
    assert "not an exclusive allow-list" in turn.prompt_text
    assert "### Available routes" in turn.prompt_text
    assert "Explicit required writes" in turn.prompt_text
    assert "Effective required writes" in turn.prompt_text
    assert "### Control response" in turn.prompt_text
    assert '"outcome": {' in turn.prompt_text
    assert '"tag": "<one available route>"' in turn.prompt_text
    assert '"payload": {}' in turn.prompt_text
    assert '"route_fields": {}' in turn.prompt_text
    assert "For question-style routes, include a non-empty `outcome.route_fields.questions` list." in turn.prompt_text
    assert "Route helper reasons belong in `outcome.route_fields.reason`" in turn.prompt_text
    assert "If the selected route is `blocked` or `failed`" not in turn.prompt_text
    assert "#### Required outcome structure" in turn.prompt_text
    assert "previous_decision" in turn.prompt_text
    assert "workspace path; missing at runtime" in turn.prompt_text
    assert "declared artifact; present at runtime" in turn.prompt_text
    assert "request" in turn.prompt_text
    assert "/tmp/design.md" in turn.prompt_text
    assert "done" in turn.prompt_text
    assert "Package the accepted design." in turn.prompt_text
    assert "design_doc, decision_record" in turn.prompt_text
    assert "summary" in turn.prompt_text
    assert "decision" in turn.prompt_text
    assert "### Route handoff" in turn.prompt_text
    assert "The current Runtime Step Contract remains authoritative." in turn.prompt_text
    assert "### Retry feedback" in turn.prompt_text
    assert "The previous attempt used an unsupported route." in turn.prompt_text
    assert "<producer_raw_output>" not in turn.prompt_text
    assert "producer raw" not in turn.prompt_text.lower()
    assert "verifier raw" not in turn.prompt_text.lower()
    assert "Producer output log" not in turn.prompt_text
    assert "sha256" not in turn.prompt_text
    assert "The producer turn immediately precedes" not in turn.prompt_text


def test_render_provider_turn_omits_optional_sections_when_absent() -> None:
    turn = render_provider_turn(_turn_context(route_handoff=None, retry_feedback=None))

    assert "### Route handoff" not in turn.prompt_text
    assert "### Retry feedback" not in turn.prompt_text


def test_render_provider_turn_excludes_hidden_routes_from_prompt_contract() -> None:
    context = _turn_context()
    turn = render_provider_turn(
        ProviderTurnContext(
            step_name=context.step_name,
            turn_kind=context.turn_kind,
            prompt=context.prompt,
            context=context.context,
            artifacts=context.artifacts,
            session=context.session,
            expected_output_schema=context.expected_output_schema,
            available_routes=("done", "needs_rework", "human_escalation"),
            routes={
                **context.routes,
                "human_escalation": ProviderRoute(
                    summary="Escalate to a hidden SOP branch.",
                    provider_visible=False,
                ),
            },
            readable_artifacts=context.readable_artifacts,
            required_artifacts=context.required_artifacts,
            writable_artifacts=context.writable_artifacts,
            route_required_writes={
                **context.route_required_writes,
                "human_escalation": (),
            },
            retry_feedback=context.retry_feedback,
            route_handoff=context.route_handoff,
            attempt=context.attempt,
            max_attempts=context.max_attempts,
        )
    )

    assert "human_escalation" not in turn.prompt_text
    assert "done" in turn.prompt_text
    assert "needs_rework" in turn.prompt_text


def test_render_provider_operation_prompt_excludes_hidden_choices() -> None:
    context = _turn_context()
    turn = render_provider_turn(
        ProviderTurnContext(
            step_name="decision",
            turn_kind="operation",
            prompt=ResolvedPrompt(path="decision.md", text="Choose the next route."),
            context=context.context,
            artifacts=context.artifacts,
            session=context.session,
            expected_output_schema=None,
            available_routes=("done", "needs_rework", "human_escalation"),
            routes={
                "done": ProviderRoute(summary="Complete the operation."),
                "needs_rework": ProviderRoute(summary="Retry locally."),
                "human_escalation": ProviderRoute(
                    summary="Escalate to a hidden SOP branch.",
                    provider_visible=False,
                ),
            },
            route_required_writes={
                "done": (),
                "needs_rework": (),
                "human_escalation": (),
            },
        )
    )

    assert "Allowed choices: done, needs_rework." in turn.prompt_text
    assert "human_escalation" not in turn.prompt_text


def test_render_required_inputs_marks_runtime_preconditions_required_even_for_optional_artifacts() -> None:
    context = _turn_context()
    turn = render_provider_turn(
        ProviderTurnContext(
            step_name=context.step_name,
            turn_kind=context.turn_kind,
            prompt=context.prompt,
            context=context.context,
            artifacts=context.artifacts,
            session=context.session,
            expected_output_schema=context.expected_output_schema,
            available_routes=context.available_routes,
            routes=context.routes,
            readable_artifacts=context.readable_artifacts,
            required_artifacts=(
                _artifact_ref("optional_input", path="/tmp/optional.md", required=False),
            ),
            writable_artifacts=context.writable_artifacts,
            route_required_writes=context.route_required_writes,
            retry_feedback=context.retry_feedback,
            route_handoff=context.route_handoff,
            attempt=context.attempt,
            max_attempts=context.max_attempts,
        )
    )

    assert "| optional_input | /tmp/optional.md | yes |" in turn.prompt_text


def test_render_provider_turn_uses_route_summary() -> None:
    context = _turn_context()
    turn = render_provider_turn(
        ProviderTurnContext(
            step_name=context.step_name,
            turn_kind=context.turn_kind,
            prompt=context.prompt,
            context=context.context,
            artifacts=context.artifacts,
            session=context.session,
            expected_output_schema=context.expected_output_schema,
            available_routes=context.available_routes,
            routes={
                **context.routes,
                "done": ProviderRoute(summary="route summary wins."),
            },
            readable_artifacts=context.readable_artifacts,
            required_artifacts=context.required_artifacts,
            writable_artifacts=context.writable_artifacts,
            route_required_writes=context.route_required_writes,
            retry_feedback=context.retry_feedback,
            route_handoff=context.route_handoff,
            attempt=context.attempt,
            max_attempts=context.max_attempts,
        )
    )

    assert "route summary wins." in turn.prompt_text


def test_render_provider_turn_uses_raw_text_response_contract_for_producer_turns() -> None:
    context = _turn_context()
    turn = render_provider_turn(
        ProviderTurnContext(
            step_name=context.step_name,
            turn_kind="producer",
            prompt=context.prompt,
            context=context.context,
            artifacts=context.artifacts,
            session=context.session,
            expected_output_schema=context.expected_output_schema,
            available_routes=context.available_routes,
            routes=context.routes,
            readable_artifacts=context.readable_artifacts,
            required_artifacts=context.required_artifacts,
            writable_artifacts=context.writable_artifacts,
            route_required_writes=context.route_required_writes,
            retry_feedback=context.retry_feedback,
            route_handoff=context.route_handoff,
            attempt=context.attempt,
            max_attempts=context.max_attempts,
        )
    )

    assert turn.expected_response == "raw_text"
    assert "### Producer response" in turn.prompt_text
    assert "Return the authored content as raw text." in turn.prompt_text
    assert "### Control response" not in turn.prompt_text


def test_render_provider_turn_rejects_missing_prompt_text() -> None:
    context = _turn_context()
    context = ProviderTurnContext(
        step_name=context.step_name,
        turn_kind=context.turn_kind,
        prompt=ResolvedPrompt(path="design.md", text=None),
        context=context.context,
        artifacts=context.artifacts,
        session=context.session,
        expected_output_schema=context.expected_output_schema,
        available_routes=context.available_routes,
        routes=context.routes,
        readable_artifacts=context.readable_artifacts,
        required_artifacts=context.required_artifacts,
        writable_artifacts=context.writable_artifacts,
        route_required_writes=context.route_required_writes,
        retry_feedback=context.retry_feedback,
        route_handoff=context.route_handoff,
        attempt=context.attempt,
        max_attempts=context.max_attempts,
    )

    with pytest.raises(ProviderExecutionError, match=r"cannot render provider turn for step 'design'"):
        render_provider_turn(context)


def test_render_provider_turn_honors_custom_render_policy() -> None:
    turn = render_provider_turn_with_policy(
        _turn_context(prompt_text="A" * 300),
        policy=ProviderPromptRenderPolicy(
            max_prompt_chars=120,
            overflow_behavior="truncate_with_marker",
        ),
    )

    assert turn.prompt_text.endswith("[TRUNCATED BY RUNTIME PROMPT BUDGET]")


def test_render_provider_turn_fails_by_default_when_budget_is_exceeded() -> None:
    with pytest.raises(ProviderExecutionError, match="max_prompt_chars budget"):
        render_provider_turn_with_policy(
            _turn_context(prompt_text="B" * 300),
            policy=ProviderPromptRenderPolicy(max_prompt_chars=120),
        )


@dataclass
class _TransportStub:
    result_text: str
    session: SessionBinding | None = None
    metadata: dict[str, object] | None = None
    usage: TokenUsage | None = None
    seen_turns: list[RenderedProviderTurn] | None = None

    def __post_init__(self) -> None:
        if self.seen_turns is None:
            self.seen_turns = []
        if self.metadata is None:
            self.metadata = {"mode": "start"}

    async def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        assert self.seen_turns is not None
        self.seen_turns.append(turn)
        return ProviderTurnResult(
            raw_text=self.result_text,
            session=self.session,
            metadata=dict(self.metadata or {}),
            usage=self.usage,
        )


@dataclass
class _AsyncTransportStub:
    result_text: str
    session: SessionBinding | None = None
    metadata: dict[str, object] | None = None
    usage: TokenUsage | None = None
    seen_turns: list[RenderedProviderTurn] | None = None

    def __post_init__(self) -> None:
        if self.seen_turns is None:
            self.seen_turns = []
        if self.metadata is None:
            self.metadata = {"mode": "start"}

    async def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        assert self.seen_turns is not None
        self.seen_turns.append(turn)
        return ProviderTurnResult(
            raw_text=self.result_text,
            session=self.session,
            metadata=dict(self.metadata or {}),
            usage=self.usage,
        )


@dataclass
class _SyncTransportStub:
    result_text: str

    def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        return ProviderTurnResult(raw_text=self.result_text)


class _SyncProviderStub:
    def run_producer(self, request: ProducerRequest) -> ProducerResponse:
        return ProducerResponse(raw_output="draft")

    def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:
        return OutcomeResponse(outcome=parse_outcome_json('{"tag":"done"}'))

    def run_llm(self, request: LLMRequest) -> OutcomeResponse:
        return OutcomeResponse(outcome=parse_outcome_json('{"tag":"done"}'))


def test_token_usage_model_accepts_partial_usage() -> None:
    usage = TokenUsage(output_tokens=12, source="codex", provider_raw={"output_tokens": 12})

    assert usage.input_tokens is None
    assert usage.output_tokens == 12
    assert usage.total_tokens is None
    assert usage.cached_input_tokens is None
    assert usage.reasoning_tokens is None
    assert usage.source == "codex"
    assert usage.provider_raw == {"output_tokens": 12}


def test_provider_validation_rejects_sync_only_provider_methods() -> None:
    with pytest.raises(TypeError, match="must be async coroutine functions"):
        validate_llm_provider(_SyncProviderStub())


def test_transport_validation_rejects_sync_only_run_turn() -> None:
    with pytest.raises(TypeError, match="must be async coroutine functions"):
        validate_provider_transport(_SyncTransportStub(result_text="sync"))


def test_rendered_provider_rejects_sync_only_transport_at_construction() -> None:
    with pytest.raises(TypeError, match="must be async coroutine functions"):
        RenderedLLMProvider(_SyncTransportStub(result_text="sync"))


def test_fake_provider_and_rendered_transport_surfaces_remain_async_only() -> None:
    forbidden_names = tuple(
        "run_" + suffix
        for suffix in ("llm_" + "async", "producer_" + "async", "verifier_" + "async")
    )

    assert inspect.iscoroutinefunction(ScriptedLLMProvider.run_producer)
    assert inspect.iscoroutinefunction(ScriptedLLMProvider.run_verifier)
    assert inspect.iscoroutinefunction(ScriptedLLMProvider.run_llm)
    assert inspect.iscoroutinefunction(_TransportStub.run_turn)
    for name in forbidden_names:
        assert not hasattr(ScriptedLLMProvider, name)
        assert not hasattr(RenderedLLMProvider, name)


def test_producer_response_usage_defaults_to_none() -> None:
    response = ProducerResponse(raw_output="draft")

    assert response.usage is None


def test_outcome_response_usage_defaults_to_none() -> None:
    response = OutcomeResponse(outcome=parse_outcome_json('{"tag":"done","reason":"completed"}'))

    assert response.usage is None


def test_fake_provider_can_emit_usage() -> None:
    producer_usage = TokenUsage(input_tokens=3, output_tokens=5, total_tokens=8, source="fake")
    verifier_usage = TokenUsage(input_tokens=7, output_tokens=2, total_tokens=9, source="fake")
    llm_usage = TokenUsage(total_tokens=4, source="fake")
    provider = ScriptedLLMProvider(
        producer_turns=[ProducerResponse(raw_output="draft", usage=producer_usage)],
        verifier_turns=[OutcomeResponse(outcome=parse_outcome_json('{"tag":"done","reason":"verified"}'), usage=verifier_usage)],
        llm_turns=[OutcomeResponse(outcome=parse_outcome_json('{"tag":"done","reason":"answered"}'), usage=llm_usage)],
    )

    producer_response = asyncio.run(
        provider.run_producer(
            ProducerRequest(
                step_name="draft",
                producer_prompt=ResolvedPrompt(path="draft.md", text="Write a draft."),
                context=object(),
                artifacts=object(),
            )
        )
    )
    verifier_response = asyncio.run(
        provider.run_verifier(
            VerifierRequest(
                step_name="verify",
                verifier_prompt=ResolvedPrompt(path="verify.md", text="Verify the draft."),
                producer_raw_output="draft",
                context=object(),
                artifacts=object(),
            )
        )
    )
    llm_response = asyncio.run(
        provider.run_llm(
            LLMRequest(
                step_name="ask",
                prompt=ResolvedPrompt(path="ask.md", text="Answer the question."),
                context=object(),
                artifacts=object(),
            )
        )
    )

    assert producer_response.usage == producer_usage
    assert verifier_response.usage == verifier_usage
    assert llm_response.usage == llm_usage


def test_fake_provider_supports_async_turn_methods() -> None:
    provider = ScriptedLLMProvider(llm_turns=[OutcomeResponse(outcome=parse_outcome_json('{"tag":"done"}'))])

    response = asyncio.run(
        provider.run_llm(
            LLMRequest(
                step_name="ask",
                prompt=ResolvedPrompt(path="ask.md", text="Answer the question."),
                context=object(),
                artifacts=object(),
            )
        )
    )

    assert response.outcome.tag == "done"
    assert provider.calls[0].kind == "step"


def test_fake_provider_records_session_binding_for_async_turns() -> None:
    binding = _session_binding("branch-session-1")
    provider = ScriptedLLMProvider(llm_turns=[OutcomeResponse(outcome=parse_outcome_json('{"tag":"done"}'))])

    asyncio.run(
        provider.run_llm(
            LLMRequest(
                step_name="ask",
                prompt=ResolvedPrompt(path="ask.md", text="Answer the question."),
                context=object(),
                artifacts=object(),
                session=binding,
            )
        )
    )

    assert provider.calls[0].session == binding
    assert provider.calls[0].session is not binding


def test_fake_provider_awaits_async_scripted_turn_callbacks() -> None:
    async def scripted_turn(request: LLMRequest) -> OutcomeResponse:
        await asyncio.sleep(0)
        return OutcomeResponse(
            outcome=parse_outcome_json(f'{{"tag":"done","payload":{{"step":"{request.step_name}"}}}}')
        )

    provider = ScriptedLLMProvider(llm_turns=[scripted_turn])

    response = asyncio.run(
        provider.run_llm(
            LLMRequest(
                step_name="ask",
                prompt=ResolvedPrompt(path="ask.md", text="Answer the question."),
                context=object(),
                artifacts=object(),
            )
        )
    )

    assert response.outcome.tag == "done"
    assert response.outcome.payload == {"step": "ask"}


def test_fake_provider_rejects_awaitable_sync_operation_responses() -> None:
    async def scripted_operation(_: OperationRequest) -> str:
        await asyncio.sleep(0)
        return '{"summary":"ready"}'

    provider = ScriptedLLMProvider(operation_turns=[scripted_operation])

    with pytest.raises(TypeError, match="must not be awaitable"):
        provider.run_operation(
            OperationRequest(
                step_name="summary",
                prompt=ResolvedPrompt(path="summary.md", text="Summarize the report."),
                context=None,
                session=None,
                operation_kind="llm",
                return_schema={"type": "object", "properties": {"summary": {"type": "string"}}},
            )
        )


def test_parse_outcome_json_defaults_missing_reason_to_empty_string() -> None:
    outcome = parse_outcome_json('{"tag":"done"}')

    assert outcome.reason == ""


def test_rendered_llm_provider_returns_producer_response() -> None:
    binding = _session_binding()
    usage = TokenUsage(input_tokens=5, output_tokens=7, total_tokens=12, source="codex")
    transport = _TransportStub(result_text="producer text", session=binding, metadata={"mode": "resume"}, usage=usage)
    provider = RenderedLLMProvider(transport)

    response = asyncio.run(
        provider.run_producer(
            ProducerRequest(
                step_name="draft",
                producer_prompt=ResolvedPrompt(path="draft.md", text="Write the draft."),
                context=object(),
                artifacts=object(),
                session=binding,
                required_artifacts=(_artifact_ref("brief", path="/tmp/brief.md"),),
            )
        )
    )

    assert response.raw_output == "producer text"
    assert response.session == binding
    assert response.metadata == {"mode": "resume"}
    assert response.usage == usage
    assert transport.seen_turns is not None
    assert transport.seen_turns[0].expected_response == "raw_text"


def test_rendered_llm_provider_supports_async_turn_methods() -> None:
    binding = _session_binding()
    usage = TokenUsage(total_tokens=9, source="codex")
    transport = _AsyncTransportStub(
        result_text='{"tag":"done","reason":"accepted"}',
        session=binding,
        metadata={"mode": "resume"},
        usage=usage,
    )
    provider = RenderedLLMProvider(transport)

    response = asyncio.run(
        provider.run_llm(
            LLMRequest(
                step_name="draft",
                prompt=ResolvedPrompt(path="draft.md", text="Write the draft."),
                context=object(),
                artifacts=object(),
                session=binding,
            )
        )
    )

    assert response.outcome.tag == "done"
    assert response.outcome.reason == "accepted"
    assert response.session == binding
    assert response.usage == usage
    assert transport.seen_turns is not None
    assert transport.seen_turns[0].expected_response == "outcome_json"


def test_rendered_llm_provider_parses_verifier_outcome_and_excludes_raw_output_from_prompt() -> None:
    usage = TokenUsage(input_tokens=11, output_tokens=13, total_tokens=24, source="claude")
    transport = _TransportStub(
        result_text='{"tag":"done","reason":"accepted","payload":{"score": 1}}',
        usage=usage,
    )
    provider = RenderedLLMProvider(transport)

    response = asyncio.run(
        provider.run_verifier(
            VerifierRequest(
                step_name="verify",
                verifier_prompt=ResolvedPrompt(path="verify.md", text="Verify the package."),
                producer_raw_output="producer raw output that must stay out of the prompt",
                context=object(),
                artifacts=object(),
                session=None,
                route_handoff="Tighten the package and keep the route legal.",
            )
        )
    )

    assert response.outcome.tag == "done"
    assert response.outcome.reason == "accepted"
    assert response.outcome.payload == {"score": 1}
    assert response.usage == usage
    assert transport.seen_turns is not None
    rendered_prompt = transport.seen_turns[0].prompt_text
    assert "producer raw output that must stay out of the prompt" not in rendered_prompt
    assert "<producer_raw_output>" not in rendered_prompt
    assert "Tighten the package and keep the route legal." in rendered_prompt


def test_rendered_llm_provider_parses_llm_outcome() -> None:
    usage = TokenUsage(total_tokens=9, source="claude")
    transport = _TransportStub(
        result_text='```json\n{"tag":"needs_rework","reason":"Needs local repair.","question":"Fix it?"}\n```',
        usage=usage,
    )
    provider = RenderedLLMProvider(transport)

    response = asyncio.run(
        provider.run_llm(
            LLMRequest(
                step_name="analyze",
                prompt=ResolvedPrompt(path="analyze.md", text="Analyze the request."),
                context=object(),
                artifacts=object(),
                session=None,
            )
        )
    )

    assert response.outcome.tag == "needs_rework"
    assert response.outcome.reason == "Needs local repair."
    assert response.outcome.question == "Fix it?"
    assert response.usage == usage


def test_rendered_llm_provider_runs_value_operation_as_raw_text() -> None:
    usage = TokenUsage(total_tokens=5, source="codex")
    transport = _TransportStub(result_text='{"summary":"ready"}', usage=usage)
    provider = RenderedLLMProvider(transport)

    response = provider.run_operation(
        OperationRequest(
            step_name="summary",
            prompt=ResolvedPrompt(path="summary.md", text="Summarize the report."),
            context=None,
            session=None,
            operation_kind="llm",
            return_schema={"type": "object", "properties": {"summary": {"type": "string"}}},
        )
    )

    assert response.raw_output == '{"summary":"ready"}'
    assert response.usage == usage
    assert transport.seen_turns is not None
    assert transport.seen_turns[0].turn_kind == "operation"
    assert transport.seen_turns[0].expected_response == "raw_text"


def test_rendered_llm_provider_prefers_async_transport_for_sync_operations_outside_active_loop() -> None:
    transport = _TransportStub(result_text='{"summary":"ready"}')

    def fail_if_called(turn: RenderedProviderTurn) -> ProviderTurnResult:  # pragma: no cover - defensive
        raise AssertionError("operation_executor should only be used inside an active event loop")

    provider = RenderedLLMProvider(transport, operation_executor=fail_if_called)

    response = provider.run_operation(
        OperationRequest(
            step_name="summary",
            prompt=ResolvedPrompt(path="summary.md", text="Summarize the report."),
            context=None,
            session=None,
            operation_kind="llm",
            return_schema={"type": "object", "properties": {"summary": {"type": "string"}}},
        )
    )

    assert response.raw_output == '{"summary":"ready"}'
    assert transport.seen_turns is not None
    assert transport.seen_turns[0].turn_kind == "operation"
