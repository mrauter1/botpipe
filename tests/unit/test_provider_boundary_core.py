from __future__ import annotations

from dataclasses import dataclass

import pytest

from autoloop_v3.core.errors import ProviderExecutionError
from autoloop_v3.core.prompts import ResolvedPrompt
from autoloop_v3.core.providers.models import (
    LLMRequest,
    ProducerRequest,
    ProviderArtifactRef,
    ProviderTurnContext,
    VerifierRequest,
)
from autoloop_v3.core.providers.rendered import RenderedLLMProvider
from autoloop_v3.core.providers.rendering import ProviderPromptRenderPolicy, render_provider_turn_with_policy
from autoloop_v3.core.providers.rendering import render_provider_turn
from autoloop_v3.core.providers.turns import ProviderTurnResult, RenderedProviderTurn
from autoloop_v3.core.stores.protocols import SessionBinding


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
        route_contracts={
            "done": {"summary": "Package the accepted design."},
            "needs_rework": {"summary": "Repair the current design before packaging."},
        },
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
        route_required_artifacts={
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
    assert "### Required inputs" in turn.prompt_text
    assert "### Artifacts this step may write" in turn.prompt_text
    assert "### Available routes" in turn.prompt_text
    assert "### Output payload" in turn.prompt_text
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
        route_contracts=context.route_contracts,
        required_artifacts=context.required_artifacts,
        writable_artifacts=context.writable_artifacts,
        route_required_artifacts=context.route_required_artifacts,
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


@dataclass
class _TransportStub:
    result_text: str
    session: SessionBinding | None = None
    metadata: dict[str, object] | None = None
    seen_turns: list[RenderedProviderTurn] | None = None

    def __post_init__(self) -> None:
        if self.seen_turns is None:
            self.seen_turns = []
        if self.metadata is None:
            self.metadata = {"mode": "start"}

    def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        assert self.seen_turns is not None
        self.seen_turns.append(turn)
        return ProviderTurnResult(
            raw_text=self.result_text,
            session=self.session,
            metadata=dict(self.metadata or {}),
        )


def test_rendered_llm_provider_returns_producer_response() -> None:
    binding = _session_binding()
    transport = _TransportStub(result_text="producer text", session=binding, metadata={"mode": "resume"})
    provider = RenderedLLMProvider(transport)

    response = provider.run_producer(
        ProducerRequest(
            step_name="draft",
            prompt=ResolvedPrompt(path="draft.md", text="Write the draft."),
            context=object(),
            artifacts=object(),
            session=binding,
            required_artifacts=(_artifact_ref("brief", path="/tmp/brief.md"),),
        )
    )

    assert response.raw_output == "producer text"
    assert response.session == binding
    assert response.metadata == {"mode": "resume"}
    assert transport.seen_turns is not None
    assert transport.seen_turns[0].expected_response == "raw_text"


def test_rendered_llm_provider_parses_verifier_outcome_and_excludes_raw_output_from_prompt() -> None:
    transport = _TransportStub(result_text='{"tag":"done","reason":"accepted","payload":{"score": 1}}')
    provider = RenderedLLMProvider(transport)

    response = provider.run_verifier(
        VerifierRequest(
            step_name="verify",
            prompt=ResolvedPrompt(path="verify.md", text="Verify the package."),
            raw_output="producer raw output that must stay out of the prompt",
            context=object(),
            artifacts=object(),
            session=None,
            route_handoff="Tighten the package and keep the route legal.",
        )
    )

    assert response.outcome.tag == "done"
    assert response.outcome.reason == "accepted"
    assert response.outcome.payload == {"score": 1}
    assert transport.seen_turns is not None
    rendered_prompt = transport.seen_turns[0].prompt_text
    assert "producer raw output that must stay out of the prompt" not in rendered_prompt
    assert "<producer_raw_output>" not in rendered_prompt
    assert "Tighten the package and keep the route legal." in rendered_prompt


def test_rendered_llm_provider_parses_llm_outcome() -> None:
    transport = _TransportStub(result_text='```json\n{"tag":"needs_rework","question":"Fix it?"}\n```')
    provider = RenderedLLMProvider(transport)

    response = provider.run_llm(
        LLMRequest(
            step_name="analyze",
            prompt=ResolvedPrompt(path="analyze.md", text="Analyze the request."),
            context=object(),
            artifacts=object(),
            session=None,
        )
    )

    assert response.outcome.tag == "needs_rework"
    assert response.outcome.question == "Fix it?"
