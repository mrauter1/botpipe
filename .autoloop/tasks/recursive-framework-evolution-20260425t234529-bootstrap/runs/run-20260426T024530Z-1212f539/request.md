# Full revised standalone implementation plan for Autoloop v3

## Goal

Implement a provider-interface refactor in `autoloop_v3` so that CLI-backed providers such as Codex CLI and Claude receive a **single shared, human-readable, runtime-rendered step prompt**, while provider-specific code becomes a pure transport layer.

The implementation must also add:

1. provider-attributable retry behavior, defaulting to `3` attempts;
2. route handoffs for backtracking and special routing;
3. runtime-injected artifact/route/output contracts in markdown;
4. strict removal of provider raw output from provider-facing prompts.

The current repository already has a strict core/runtime split, a `core/providers` area, runtime provider adapters, engine contract tests, prompt README baseline tests, worklist/scoped-step tests, and raw-output telemetry tests. This plan preserves those surfaces while moving CLI provider rendering out of runtime provider adapters. 

---

# 1. Required final architecture

Use this layering:

```text id="f5y8fr"
Engine
  ↓ existing semantic LLMProvider protocol
RenderedLLMProvider
  ↓ shared rendering/parsing layer
ProviderTransport
  ↓ CLI transport only
CodexTransport / ClaudeTransport
```

The engine-facing semantic provider protocol stays intact:

```python id="obop7k"
run_producer(request: ProducerRequest) -> ProducerResponse
run_verifier(request: VerifierRequest) -> OutcomeResponse
run_llm(request: LLMRequest) -> OutcomeResponse
```

Add a lower-level transport protocol for CLI-backed providers:

```python id="1kkx44"
run_turn(turn: RenderedProviderTurn) -> ProviderTurnResult
```

`RenderedLLMProvider` implements the existing semantic provider protocol by:

```text id="y8tcnm"
1. receiving ProducerRequest / VerifierRequest / LLMRequest from the engine;
2. converting that semantic request into ProviderTurnContext;
3. rendering ProviderTurnContext into RenderedProviderTurn using shared core rendering;
4. sending RenderedProviderTurn to a ProviderTransport;
5. parsing workflow outcome JSON for verifier/LLM turns;
6. returning the existing ProducerResponse / OutcomeResponse objects.
```

Provider-specific Codex/Claude code must not know about:

```text id="ld2i3r"
route_contracts
available_routes
expected_output_schema
required_artifacts
writable_artifacts
route_required_artifacts
retry_feedback
route_handoff
producer raw output
verifier raw output
workflow outcome JSON parsing
```

Provider-specific code may know only about:

```text id="kh2dya"
CLI command construction
subprocess invocation
session resume
provider metadata
transport-level errors
parsing CLI envelope into assistant text
```

---

# 2. Non-goals

Do not:

```text id="y96i2x"
- rewrite workflow authoring;
- change the public CLI;
- remove ScriptedLLMProvider or semantic in-process provider support;
- remove raw-output logging/tracing/extension telemetry;
- remove existing route contracts;
- remove existing expected_output_schema validation;
- remove existing artifact validation;
- force all providers through rendered markdown;
- add arbitrary max_chars limits to Handoff.
```

---

# 3. Core invariants

The final implementation must satisfy:

```text id="5r0kvf"
1. Runtime providers never render workflow inputs.
2. Runtime providers never parse workflow outcome JSON.
3. Runtime providers receive only RenderedProviderTurn.
4. Runtime providers return only ProviderTurnResult.
5. Shared core renderer produces human-readable markdown.
6. Provider raw output is never rendered into a provider prompt.
7. Provider raw output remains available to logs, traces, extension events, and failure records.
8. Provider-attributable failures retry up to ProviderRetryPolicy.max_attempts.
9. Default ProviderRetryPolicy.max_attempts is 3.
10. Handoff carries text only; it has no max_chars field.
11. Optional prompt-size limits belong to the shared renderer policy, not the Handoff primitive.
12. Route handoff is delivered only to the resolved target step.
13. Route handoff is scoped to worklist item when relevant.
```

The current authoring docs and tests already treat `expected_output_schema`, `available_routes`, and `route_contracts` as the existing runtime-injected provider contract, so docs and baseline tests must be updated to the broader human-readable contract. 

---

# 4. Implementation order

Codex should implement in this order:

```text id="8lzb0l"
1. Add RenderedProviderTurn and ProviderTurnResult.
2. Add ProviderTransport protocol.
3. Add ProviderArtifactRef and ProviderTurnContext.
4. Add shared markdown renderer.
5. Add RenderedLLMProvider wrapper.
6. Move/copy workflow outcome JSON parsing into core provider parsing.
7. Refactor Codex provider into CodexTransport.
8. Refactor Claude provider into ClaudeTransport.
9. Update runtime provider backend resolution to return RenderedLLMProvider(Transport).
10. Add provider transport purity tests.
11. Add renderer tests.
12. Add ProviderRetryPolicy.
13. Add retry_policy to LLMStep and PairStep; compile it.
14. Implement retry loop for provider-mediated steps.
15. Add retry feedback rendering.
16. Add Handoff effect.
17. Add Event.handoff.
18. Add PendingHandoff and checkpoint persistence.
19. Deliver handoff to resolved target provider turn.
20. Update docs and prompt README baseline tests.
21. Update changed failure tests for retry semantics.
22. Run targeted tests.
23. Run full test suite.
```

---

# 5. Phase 1 — Add rendered transport models

Create:

```text id="mdo7ux"
core/providers/turns.py
```

Add:

```python id="yq6jgr"
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from autoloop_v3.core.stores import SessionBinding  # adjust if actual import path differs


ProviderTurnKind = Literal["producer", "verifier", "llm"]
ExpectedProviderResponse = Literal["raw_text", "outcome_json"]


@dataclass(frozen=True, slots=True)
class RenderedProviderTurn:
    step_name: str
    turn_kind: ProviderTurnKind
    prompt_text: str
    session: SessionBinding | None
    expected_response: ExpectedProviderResponse


@dataclass(frozen=True, slots=True)
class ProviderTurnResult:
    raw_text: str
    session: SessionBinding | None
    metadata: dict[str, Any] = field(default_factory=dict)
```

Update:

```text id="xla9zj"
core/providers/__init__.py
```

to export:

```python id="d3bx2s"
RenderedProviderTurn
ProviderTurnResult
```

---

# 6. Phase 2 — Add ProviderTransport protocol

Edit:

```text id="t5n8x2"
core/providers/protocols.py
```

Keep the existing semantic provider protocol unchanged.

Add:

```python id="7d8fai"
from typing import Protocol

from autoloop_v3.core.providers.turns import RenderedProviderTurn, ProviderTurnResult


class ProviderTransport(Protocol):
    def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        ...
```

---

# 7. Phase 3 — Add provider artifact and turn-context models

Edit:

```text id="jvulw6"
core/providers/models.py
```

Add:

```python id="7b83ap"
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from autoloop_v3.core.artifacts import ResolvedArtifacts
from autoloop_v3.core.context import Context
from autoloop_v3.core.prompts import ResolvedPrompt
from autoloop_v3.core.stores import SessionBinding


@dataclass(frozen=True, slots=True)
class ProviderArtifactRef:
    name: str
    qualified_name: str
    path: str
    kind: str
    required: bool
    exists: bool
    schema_name: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderTurnContext:
    step_name: str
    turn_kind: Literal["producer", "verifier", "llm"]
    prompt: ResolvedPrompt
    context: Context
    artifacts: ResolvedArtifacts
    session: SessionBinding | None
    expected_output_schema: Mapping[str, Any] | None
    available_routes: tuple[str, ...]
    route_contracts: Mapping[str, Mapping[str, Any]]
    required_artifacts: tuple[ProviderArtifactRef, ...] = ()
    writable_artifacts: tuple[ProviderArtifactRef, ...] = ()
    route_required_artifacts: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    retry_feedback: str | None = None
    route_handoff: str | None = None
    attempt: int = 1
    max_attempts: int = 3
```

Extend existing `ProducerRequest`, `VerifierRequest`, and `LLMRequest` with defaulted fields:

```python id="3x2sj9"
required_artifacts: tuple[ProviderArtifactRef, ...] = ()
writable_artifacts: tuple[ProviderArtifactRef, ...] = ()
route_required_artifacts: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
retry_feedback: str | None = None
route_handoff: str | None = None
attempt: int = 1
max_attempts: int = 3
```

For `VerifierRequest`, keep the current `raw_output` field temporarily:

```python id="7j75fd"
raw_output: str = ""
```

but add this comment:

```python id="y6nq3a"
# Deprecated telemetry field. Shared provider rendering must not include this in prompts.
```

Do not remove `raw_output` in this implementation pass.

---

# 8. Phase 4 — Add shared markdown renderer

Create:

```text id="kg2064"
core/providers/rendering.py
```

Add public API:

```python id="e1psp2"
from __future__ import annotations

from typing import Any, Mapping, Sequence

from autoloop_v3.core.providers.models import ProviderArtifactRef, ProviderTurnContext
from autoloop_v3.core.providers.turns import RenderedProviderTurn


def render_provider_turn(context: ProviderTurnContext) -> RenderedProviderTurn:
    ...
```

The renderer must produce a `RenderedProviderTurn` where:

```python id="s43ku0"
expected_response = "raw_text" if context.turn_kind == "producer" else "outcome_json"
```

## Required prompt structure

The rendered `prompt_text` must be markdown:

```markdown id="9x478v"
# Step: <step_name>

<workflow-authored prompt text>

## Runtime Step Contract

### Required inputs

| Artifact | Path | Required | Notes |
|---|---|---:|---|

### Artifacts this step may write

| Artifact | Path | Format | Required by routes | Notes |
|---|---|---|---|---|

### Available routes

| Route | Meaning | Required artifacts before choosing this route |
|---|---|---|

### Output payload

| Field | Required | Type | Notes |
|---|---:|---|---|

### Route handoff

<only if route_handoff is non-empty>

### Retry feedback

<only if retry_feedback is non-empty>
```

## Hard exclusions

The renderer must never render:

```text id="v6psy1"
producer raw output
verifier raw output
<producer_raw_output>
<verifier_raw_output>
raw output log paths
sha256 digests
same-session explanations
provider metadata
checkpoint ids
internal session metadata
```

Specific forbidden phrases in rendered prompts:

```text id="gr9buc"
The producer turn immediately precedes this verifier turn
Producer output log
Producer output digest
<producer_raw_output>
```

## Renderer helper functions

Implement deterministic helpers:

```python id="fj1orp"
def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    ...

def _yes_no(value: bool) -> str:
    return "yes" if value else "no"

def _required_by_routes(context: ProviderTurnContext, artifact_name: str) -> str:
    ...

def _route_required_artifacts(context: ProviderTurnContext, route: str) -> str:
    ...

def _schema_name(ref: ProviderArtifactRef) -> str:
    ...

def _render_expected_output_schema(schema: Mapping[str, Any] | None) -> str:
    ...
```

For output schema rendering:

```text id="zatpcr"
- Prefer a top-level field table.
- Use JSON schema "required" if present.
- Infer simple types from JSON schema property type.
- If schema is too complex, render required top-level fields and a concise fallback note.
- Do not dump raw JSON schema.
```

For route rendering:

```text id="6sxlwb"
- Route name comes from available_routes.
- Meaning comes from route_contracts[route]["summary"] if present.
- Required artifacts come from route_required_artifacts[route].
- Use "none" when no required artifacts are known.
```

---

# 9. Phase 5 — Add optional whole-prompt render policy

Do **not** add `max_chars` to `Handoff`.

If prompt-size control is desired, put it on the renderer.

In `core/providers/rendering.py`, add:

```python id="mf2jg7"
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ProviderPromptRenderPolicy:
    max_prompt_chars: int | None = None
    overflow_behavior: Literal["fail", "truncate_with_marker"] = "fail"
```

Default behavior:

```python id="mcsvdv"
ProviderPromptRenderPolicy(
    max_prompt_chars=None,
    overflow_behavior="fail",
)
```

Rules:

```text id="e9vlwn"
- No prompt-size limit by default.
- If max_prompt_chars is None, render full prompt.
- If max_prompt_chars is set and prompt exceeds it:
  - fail by default with a clear error;
  - only truncate if overflow_behavior == "truncate_with_marker".
- Never silently truncate handoffs.
```

If truncating explicitly, include:

```markdown id="gch2i3"
[TRUNCATED BY RUNTIME PROMPT BUDGET]
```

But default must be `fail`, not truncate.

---

# 10. Phase 6 — Add shared outcome parser

Create:

```text id="n6mmcg"
core/providers/parsing.py
```

Move or copy workflow outcome JSON parsing from runtime provider common code into this core-level module:

```python id="6ds5ss"
def parse_outcome_json(text: str) -> Outcome:
    ...
```

Runtime provider transports must not import this parser.

`RenderedLLMProvider` will import it.

---

# 11. Phase 7 — Add RenderedLLMProvider

Create:

```text id="y7ejoh"
core/providers/rendered.py
```

Add:

```python id="7r81qo"
from __future__ import annotations

from autoloop_v3.core.providers.models import (
    LLMRequest,
    OutcomeResponse,
    ProducerRequest,
    ProducerResponse,
    ProviderTurnContext,
    VerifierRequest,
)
from autoloop_v3.core.providers.parsing import parse_outcome_json
from autoloop_v3.core.providers.protocols import ProviderTransport
from autoloop_v3.core.providers.rendering import render_provider_turn


class RenderedLLMProvider:
    def __init__(self, transport: ProviderTransport) -> None:
        self._transport = transport

    def run_producer(self, request: ProducerRequest) -> ProducerResponse:
        context = _producer_context(request)
        turn = render_provider_turn(context)
        result = self._transport.run_turn(turn)
        return ProducerResponse(
            raw_output=result.raw_text,
            session=result.session,
            metadata=result.metadata,
        )

    def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:
        context = _verifier_context(request)
        turn = render_provider_turn(context)
        result = self._transport.run_turn(turn)
        outcome = parse_outcome_json(result.raw_text)
        return OutcomeResponse(
            outcome=outcome,
            session=result.session,
            metadata=result.metadata,
        )

    def run_llm(self, request: LLMRequest) -> OutcomeResponse:
        context = _llm_context(request)
        turn = render_provider_turn(context)
        result = self._transport.run_turn(turn)
        outcome = parse_outcome_json(result.raw_text)
        return OutcomeResponse(
            outcome=outcome,
            session=result.session,
            metadata=result.metadata,
        )
```

Use the existing actual response field names. If the current model uses `provider_metadata` instead of `metadata`, preserve the current field names.

Add private helpers:

```python id="n734at"
def _producer_context(request: ProducerRequest) -> ProviderTurnContext:
    ...

def _verifier_context(request: VerifierRequest) -> ProviderTurnContext:
    ...

def _llm_context(request: LLMRequest) -> ProviderTurnContext:
    ...
```

Important:

```text id="ske9hf"
- _verifier_context must ignore request.raw_output.
- _verifier_context must not include raw output in route_handoff, retry_feedback, or any rendered field.
```

Export:

```text id="r7pvmb"
RenderedLLMProvider
```

from:

```text id="f44rmf"
core/providers/__init__.py
```

---

# 12. Phase 8 — Refactor Codex provider into pure transport

Edit:

```text id="i3g9tj"
runtime/providers/codex.py
```

Refactor the current provider class to a transport. Either rename to `CodexTransport`, or keep `CodexProvider` as a compatibility alias while making it implement only `ProviderTransport`.

Preferred:

```python id="8iqoz3"
class CodexTransport:
    def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        ...
```

Remove imports of:

```text id="lh5lbr"
ProducerRequest
VerifierRequest
LLMRequest
ProducerResponse
OutcomeResponse
parse_outcome_json
render_verifier_input
render_provider_turn
```

`CodexTransport.run_turn(...)` should:

```text id="pjga75"
1. validate or reject incompatible provider session metadata;
2. choose start/resume Codex command from turn.session;
3. send turn.prompt_text to subprocess;
4. parse Codex CLI envelope into assistant text and session id;
5. return ProviderTurnResult(raw_text=assistant_text, session=updated_session, metadata=metadata).
```

It may keep:

```text id="xkodvp"
resolve_codex_cli_commands
parse_codex_exec_json
verify_codex_exec_capabilities
session metadata handling
subprocess error handling
cross-provider session guard
```

It must not know whether the turn is producer/verifier/LLM except for non-semantic metadata/logging if already necessary.

---

# 13. Phase 9 — Refactor Claude provider into pure transport

Edit:

```text id="2199uk"
runtime/providers/claude.py
```

Refactor into:

```python id="2h9e9g"
class ClaudeTransport:
    def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        ...
```

Remove imports of:

```text id="7khuga"
ProducerRequest
VerifierRequest
LLMRequest
ProducerResponse
OutcomeResponse
parse_outcome_json
render_verifier_input
render_provider_turn
```

`ClaudeTransport.run_turn(...)` should:

```text id="q4d8p7"
1. validate or reject incompatible provider session metadata;
2. build claude command with -p turn.prompt_text;
3. apply existing permission/model/session behavior;
4. parse Claude CLI envelope into assistant text and session id;
5. return ProviderTurnResult(raw_text=assistant_text, session=updated_session, metadata=metadata).
```

It may keep:

```text id="p2j0yg"
claude_permission_args
parse_claude_exec_json
verify_claude_code_capabilities
subprocess invocation
session metadata handling
```

It must not call `render_verifier_input`.

---

# 14. Phase 10 — Update runtime provider backend resolution

Edit:

```text id="cpvp1h"
runtime/provider_backends.py
```

Where provider backend resolution currently returns a concrete Codex/Claude provider, now return:

```python id="wjovwp"
RenderedLLMProvider(CodexTransport(...))
```

or:

```python id="wlpzs1"
RenderedLLMProvider(ClaudeTransport(...))
```

The rest of the runtime should still see an object satisfying the existing semantic provider protocol.

Do not alter public config semantics.

---

# 15. Phase 11 — Add provider retry policy

Create:

```text id="m8uw9k"
core/providers/retries.py
```

Add:

```python id="mv4f8x"
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderRetryPolicy:
    max_attempts: int = 3
    retry_provider_execution_error: bool = True
    retry_illegal_route: bool = True
    retry_invalid_payload: bool = True
    retry_missing_required_output_artifact: bool = True
    retry_invalid_output_artifact: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int):
            raise TypeError("ProviderRetryPolicy.max_attempts must be an integer.")
        if self.max_attempts < 1:
            raise ValueError("ProviderRetryPolicy.max_attempts must be >= 1.")
```

Add retry feedback builder:

```python id="2lxv9u"
def build_retry_feedback(
    exc: Exception,
    *,
    step_name: str,
    attempt: int,
    max_attempts: int,
) -> str:
    ...
```

It must return markdown:

```markdown id="7w2u59"
## Retry Feedback

The previous attempt could not be accepted.

Attempt:
- 2 of 3

Problem:
- <concise validation/runtime error>

Action required:
- Repair the issue using the current Runtime Step Contract.
- Use only an allowed route.
- Write all artifacts required by the selected route.
```

Specialize messages for:

```text id="t7ifg0"
illegal route
invalid payload
missing route-required artifact
invalid artifact schema
provider transport failure
malformed provider output
```

---

# 16. Phase 12 — Add retry policy to steps

Edit:

```text id="ry7sgg"
core/steps.py
core/compiler.py
core/validation.py
core/__init__.py
workflow/__init__.py
```

Add optional retry policy to `LLMStep` and `PairStep`:

```python id="ifhj4q"
retry_policy: ProviderRetryPolicy | None = None
```

Store default:

```python id="f453km"
self.retry_policy = retry_policy or ProviderRetryPolicy()
```

Add to compiled step:

```python id="e8ldfy"
retry_policy: ProviderRetryPolicy
```

For `SystemStep`, reject provider retry policy:

```text id="vjdxjg"
SystemStep does not call a provider and cannot declare provider retry policy.
```

Add validation tests.

---

# 17. Phase 13 — Build provider artifact metadata in engine

Edit:

```text id="43m4ax"
core/engine.py
```

Add helpers:

```python id="7acxyi"
def _provider_artifact_ref(self, name: str, handle: ArtifactHandle) -> ProviderArtifactRef:
    ...

def _provider_artifact_refs(
    self,
    names: tuple[str, ...],
    artifacts: ResolvedArtifacts,
) -> tuple[ProviderArtifactRef, ...]:
    ...

def _route_required_artifacts_for_step(
    self,
    step: CompiledStep,
) -> dict[str, tuple[str, ...]]:
    ...
```

Each artifact ref should include:

```text id="8jczeg"
name
qualified_name
path
kind
required
exists
schema_name
```

`_route_required_artifacts_for_step(...)` should derive from:

```python id="u9zs7i"
step.route_contracts[route]["required_artifacts"]
```

Do not invent new validation semantics silently. If a route has no explicit required artifacts, use an empty tuple unless current validation logic already has route-required artifacts.

When building `ProducerRequest`, `VerifierRequest`, or `LLMRequest`, set:

```python id="dyhuhp"
required_artifacts=...
writable_artifacts=...
route_required_artifacts=...
attempt=...
max_attempts=...
retry_feedback=...
route_handoff=...
```

---

# 18. Phase 14 — Implement retry loop in engine

Edit:

```text id="ie8cji"
core/engine.py
```

Wrap only provider-mediated execution:

```text id="u0nrtk"
LLMStep
PairStep
```

Do not wrap:

```text id="pgtupc"
SystemStep
on_start
middleware
extensions
worklist loading
required input artifact validation
handler exceptions
```

## Retryable failures

Retry:

```text id="6xz46t"
ProviderExecutionError caused by provider transport failure
ProviderExecutionError caused by malformed provider output
ProviderExecutionError caused by illegal provider route
ProviderExecutionError caused by invalid expected output payload
ProviderExecutionError caused by missing route-required output artifact
ProviderExecutionError caused by invalid output artifact schema
```

## Non-retryable failures

Do not retry:

```text id="qi0qna"
MissingArtifactError for required input artifacts
WorkflowValidationError
WorkflowExecutionError from extension failure
RoutingError caused by middleware returning bogus route
RoutingError caused by SystemStep returning bogus route
handler exceptions
worklist duplicate ids
worklist selection errors
```

Existing tests distinguish provider invalid routes from middleware/system invalid routes, so preserve that distinction. 

## Retry request behavior

On each retry attempt, rebuild the provider request from:

```text id="apsi9h"
current canonical artifacts
current step contract
current workflow context
retry feedback
pending route handoff, if any
```

Do not include:

```text id="p1k4p5"
previous provider raw output
previous full prompt
previous transcript
log path
raw-output digest
```

## PairStep retry semantics

For a `PairStep`, retry the whole pair attempt:

```text id="ycj3qw"
producer → verifier → validate
```

If verifier route/payload/artifact validation fails, retry from producer.

After final failure, checkpoint with useful failure context and retry count.

---

# 19. Phase 15 — Add Handoff effect

Edit:

```text id="ezh8ij"
core/effects.py
core/routes.py
core/compiler.py
core/validation.py
core/__init__.py
workflow/__init__.py
```

Add:

```python id="ciklp1"
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Handoff(Effect):
    message: str

    def __post_init__(self) -> None:
        message = self.message.strip() if isinstance(self.message, str) else ""
        if not message:
            raise ValueError("Handoff.message must be a non-empty string.")
        object.__setattr__(self, "message", message)
```

Do **not** add:

```python id="p2rcvw"
max_chars
```

Usage:

```python id="p90suc"
Route.to(
    design,
    Handoff("Repair the design by adding the eval harness interface before returning to package.")
)
```

If prompt-size controls are needed, use renderer-level policy only.

---

# 20. Phase 16 — Add dynamic Event.handoff

Edit:

```text id="nk133t"
core/primitives.py
workflow/primitives.py
```

Extend `Event`:

```python id="thnf3a"
handoff: str | None = None
```

Validation rule:

```text id="04gi55"
If handoff is present, it must be non-empty text after stripping.
```

Do not impose a character limit here.

---

# 21. Phase 17 — Persist pending handoffs

Edit:

```text id="k5u29f"
core/primitives.py
core/stores/memory.py
runtime/stores/filesystem.py
core/engine.py
```

Add:

```python id="9g9hsh"
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PendingHandoff:
    source_step: str
    route_tag: str
    target_step: str
    message: str
    worklist_name: str | None = None
    item_id: str | None = None
```

Add to `Checkpoint`:

```python id="zj8zia"
pending_handoffs: tuple[PendingHandoff, ...] = ()
```

Update memory and filesystem checkpoint serialization/deserialization.

## Handoff resolution rules

```text id="h6k81e"
1. Resolve the route target first, including fallback behavior.
2. If the resolved target is terminal, do not deliver a handoff.
3. Combine static Handoff effects and Event.handoff.
4. Persist handoff keyed by resolved target step plus worklist/item identity when relevant.
5. When the matching target provider-mediated step starts, include handoff in ProviderTurnContext.route_handoff.
6. Consume handoff after successful provider dispatch begins.
7. Preserve handoff across resume if crash occurs before dispatch.
8. Do not deliver handoff to unrelated steps.
9. Do not deliver handoff to unrelated worklist items.
```

If a handoff would target a `SystemStep`, choose one of:

```text id="amc926"
Option A: reject handoff-to-system target in validation.
Option B: make handoff available on Context for that system step.
```

For the first implementation, use **Option A**: reject handoff-to-system targets unless there is an explicit product need.

---

# 22. Phase 18 — Render handoff in shared provider prompt

In `core/providers/rendering.py`, render handoff only when `ProviderTurnContext.route_handoff` is non-empty:

```markdown id="g7sqr3"
### Route handoff

<message>
```

Do not add artificial log/digest/session explanation.

Add one authority-boundary line:

```markdown id="llidva"
The current Runtime Step Contract remains authoritative.
```

This is acceptable because handoff can be provider-authored; it should not override the step contract.

---

# 23. Phase 19 — Keep raw output telemetry

Keep raw output in:

```text id="6sy7ow"
StepFinish.producer_raw_output
StepFinish.verifier_raw_output
log_artifacts
tracing extension payloads
runtime logs
failure records
```

Do not remove existing extension/log behavior.

Existing contract tests verify raw output visibility through `StepFinish`, so keep those passing. 

---

# 24. Phase 20 — Add provider transport purity tests

Add tests that inspect:

```text id="nmj2pa"
runtime/providers/codex.py
runtime/providers/claude.py
```

They must fail if either contains:

```text id="jvvsf8"
ProducerRequest
VerifierRequest
LLMRequest
ProducerResponse
OutcomeResponse
parse_outcome_json
render_verifier_input
render_provider_turn
route_contracts
available_routes
required_artifacts
retry_feedback
route_handoff
producer_raw_output
<producer_raw_output>
```

Do not over-ban `raw_text`, because transports return raw assistant text.

Be careful with `raw_output`: if the transport parser uses the phrase for process stdout, avoid false positives. Ban semantic strings like `producer_raw_output`, `<producer_raw_output>`, and `request.raw_output`.

---

# 25. Phase 21 — Add renderer tests

Test `render_provider_turn(...)` directly.

Assertions that rendered prompt includes:

```text id="kgct7e"
# Step:
## Runtime Step Contract
### Required inputs
### Artifacts this step may write
### Available routes
### Output payload
```

Assertions that rendered prompt excludes:

```text id="a80txk"
<producer_raw_output>
producer raw
verifier raw
Producer output log
sha256
same provider session
The producer turn immediately precedes
```

Add tests for:

```text id="cw4spk"
- route table includes route names;
- route table includes route-contract summaries;
- route table includes route-required artifacts;
- writable artifact table includes paths and format;
- output payload table includes required fields;
- retry feedback renders only when present;
- route handoff renders only when present;
- no JSON schema dump appears.
```

---

# 26. Phase 22 — Update runtime provider tests

Update:

```text id="vmsf7c"
tests/runtime/test_runtime_providers.py
tests/runtime/test_provider_backends.py
```

Add tests:

```text id="t8osn6"
1. CodexTransport sends RenderedProviderTurn.prompt_text to CLI stdin.
2. ClaudeTransport sends RenderedProviderTurn.prompt_text to claude -p.
3. CodexTransport does not parse workflow outcome JSON.
4. ClaudeTransport does not parse workflow outcome JSON.
5. RenderedLLMProvider parses outcome JSON for verifier and LLM turns.
6. RenderedLLMProvider returns ProducerResponse for producer turns.
7. Runtime provider backend resolution returns RenderedLLMProvider around CodexTransport/ClaudeTransport.
```

Update any tests currently expecting `render_verifier_input` or `<producer_raw_output>`.

---

# 27. Phase 23 — Add retry tests

Add engine contract tests:

```text id="mqwhx2"
1. LLMStep invalid route twice, valid third attempt → success.
2. LLMStep invalid payload twice, valid third attempt → success.
3. PairStep missing route-required artifact first attempt, writes it second attempt → success.
4. Retry budget exhausted → checkpoint includes retry count and useful failure context.
5. Missing required input artifact does not call provider and does not retry.
6. Middleware bogus route does not retry as provider failure.
7. SystemStep bogus route does not retry as provider failure.
8. retry_policy=ProviderRetryPolicy(max_attempts=1) preserves old single-attempt failure behavior.
```

Update existing hard-failure tests to either:

```text id="xff80j"
- set retry_policy=ProviderRetryPolicy(max_attempts=1), or
- assert retry exhaustion after the default 3 attempts.
```

Prefer:

```text id="lb9rsl"
- keep old tests with max_attempts=1;
- add new tests for default 3-attempt retry.
```

---

# 28. Phase 24 — Add handoff tests

Add tests:

```text id="uh0r9m"
1. Static Handoff effect compiles.
2. Empty Handoff message is rejected.
3. Static Handoff reaches resolved target step prompt.
4. Dynamic Event.handoff reaches resolved target step prompt.
5. Static and dynamic handoffs combine deterministically.
6. Handoff works across different sessions.
7. Handoff is consumed once.
8. Handoff survives checkpoint/resume.
9. Handoff is scoped to active worklist item.
10. Handoff does not leak to unrelated steps.
11. Handoff-to-SystemStep is rejected if using Option A.
```

---

# 29. Phase 25 — Update docs and baseline tests

Edit:

```text id="77oz6q"
docs/architecture.md
docs/authoring.md
workflows/*/prompts/README.md
tests/test_architecture_baseline_docs.py
```

Replace wording like:

```text id="blngzt"
The runtime injects only `expected_output_schema`, `available_routes`, and `route_contracts`.
```

with:

```text id="ihzfu7"
The runtime injects a compact human-readable step contract containing required inputs, writable artifacts, route-specific artifact requirements, expected output payload requirements, available routes, route contracts, optional route handoff, and optional retry feedback.
```

Add:

```text id="02h6c7"
Provider raw output is runtime telemetry. It is persisted for logs, traces, extension events, debugging, and replay, but is not rendered into provider prompts.
```

Add:

```text id="e8x6ho"
Route handoff is source-step-to-target-step context selected by workflow routing. Retry feedback repairs the same step attempt after validation/provider failure.
```

Baseline tests currently assert the older narrow runtime-injected contract phrase in docs and prompt READMEs, so updating tests is mandatory. 

---

# 30. Validation commands

Run targeted tests first:

```bash id="s392nk"
.venv/bin/pytest -q tests/runtime/test_runtime_providers.py
.venv/bin/pytest -q tests/runtime/test_provider_backends.py
.venv/bin/pytest -q tests/contract/test_engine_contracts.py
.venv/bin/pytest -q tests/unit/test_validation.py
.venv/bin/pytest -q tests/unit/test_primitives_and_stores.py
.venv/bin/pytest -q tests/test_architecture_baseline_docs.py
```

Then run the full suite:

```bash id="6uiv2m"
.venv/bin/pytest -q
```

---

# 31. Acceptance criteria

## Provider purity

```text id="4lju00"
- Codex/Claude runtime provider files contain no semantic provider request types.
- Codex/Claude runtime provider files do not render workflow prompts.
- Codex/Claude runtime provider files do not parse workflow outcome JSON.
- Codex/Claude runtime provider files only transport RenderedProviderTurn.
```

## Prompt rendering

```text id="vot65e"
- All CLI-backed provider prompts are rendered by the shared core renderer.
- Provider prompts are human-readable markdown.
- Provider prompts include required inputs.
- Provider prompts include writable artifacts.
- Provider prompts include route-specific artifact requirements.
- Provider prompts include available routes.
- Provider prompts include route-contract meanings.
- Provider prompts include expected output payload requirements.
- Provider prompts include retry feedback only on retry.
- Provider prompts include route handoff only for the resolved target step.
- Provider prompts never include raw provider output.
- Provider prompts never include raw-output metadata.
```

## Retry behavior

```text id="j1vx1z"
- Default provider retry attempts = 3.
- Invalid provider route is retried.
- Invalid provider payload is retried.
- Missing route-required output artifact is retried.
- Invalid output artifact schema is retried.
- Missing required input artifact is not retried.
- Middleware/system route failures are not provider retries.
- Exhaustion checkpoints with useful failure context.
```

## Handoff behavior

```text id="5ttxs9"
- Static Handoff effect works.
- Dynamic Event.handoff works.
- Handoff follows resolved route target.
- Handoff works across non-shared sessions.
- Handoff is scoped to worklist item where relevant.
- Handoff persists across resume.
- Handoff is consumed once.
- Handoff does not leak to unrelated steps.
- Handoff has no max_chars field.
```

## Compatibility

```text id="9l9p8r"
- Existing ScriptedLLMProvider tests still use semantic provider request objects.
- Raw outputs remain visible to extensions and logs.
- Existing workflow authoring surface remains stable.
- Runtime provider configuration still selects Codex/Claude through existing config flow.
- Public CLI does not change.
```

---

# 32. Final instruction to Codex

Implement this as a **provider-boundary refactor plus retry/handoff feature**, not as a workflow-authoring rewrite.

Do not remove semantic provider support.

Do not move prompt rendering into `runtime/providers`.

Do not render provider raw output into prompts.

Do not add `max_chars` to `Handoff`.

Do not change public CLI behavior.

The desired final boundary is:

```text id="enmg5o"
workflow-authored prompt
+ shared human-readable runtime step contract
+ optional route handoff
+ optional retry feedback
```

and never:

```text id="wl27nx"
producer raw output
verifier raw output
same-session explanation
raw output log path
raw output digest
provider-specific prompt rendering
```
