# Provider Boundary Refactor Plan

## Objective
Implement the requested provider-boundary refactor in the repo-root `core/` and `runtime/` modules so CLI-backed providers consume one shared rendered markdown prompt, provider transports become pure CLI transport adapters, provider-mediated failures retry by policy with a default budget of 3, and route handoffs are persisted and delivered only to the resolved target step. Keep semantic provider support, public CLI/config behavior, raw-output telemetry, route contracts, artifact validation, and expected-output validation intact.

## Current Repository Anchors
- Semantic provider boundary already exists in [core/providers/protocols.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/providers/protocols.py) and [core/providers/models.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/providers/models.py).
- Runtime providers still mix rendering/parsing concerns in [runtime/providers/codex.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/providers/codex.py), [runtime/providers/claude.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/providers/claude.py), and [runtime/providers/_common.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/providers/_common.py).
- Engine request construction, output validation, route application, and checkpoint persistence live in [core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/engine.py).
- Step compilation and authoring validation already normalize `expected_output_schema`, `available_routes`, and `route_contracts` in [core/compiler.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/compiler.py), [core/validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/validation.py), and [core/route_contracts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/route_contracts.py).
- Checkpoint/session compatibility surfaces are [core/primitives.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/primitives.py), [core/stores/protocols.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/stores/protocols.py), [core/stores/memory.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/stores/memory.py), and [runtime/stores/filesystem.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/stores/filesystem.py).
- Existing regression guards already cover runtime providers, engine contracts, validation, primitives/stores, and baseline docs.

## Target Boundary
- Keep `LLMProvider` as the engine-facing semantic protocol with `run_producer`, `run_verifier`, and `run_llm`.
- Add `RenderedProviderTurn` and `ProviderTurnResult` as the only transport-facing I/O for CLI providers.
- Add `ProviderTransport.run_turn(turn: RenderedProviderTurn) -> ProviderTurnResult`.
- Add `RenderedLLMProvider` in core to:
  1. map semantic requests into a `ProviderTurnContext`;
  2. render one shared markdown prompt;
  3. dispatch that prompt through a transport;
  4. parse outcome JSON for verifier/LLM turns only.
- Move outcome JSON parsing to a core parsing module and keep runtime transports unaware of workflow outcome semantics.
- Keep `VerifierRequest.raw_output` temporarily as a deprecated telemetry field, but make the new renderer ignore it completely.

## Milestones
### 1. Shared rendered-turn boundary
- Add `core/providers/turns.py` for `RenderedProviderTurn` and `ProviderTurnResult`.
- Extend `core/providers/protocols.py` with `ProviderTransport` without changing `LLMProvider`.
- Extend `core/providers/models.py` with `ProviderArtifactRef`, `ProviderTurnContext`, and defaulted request metadata fields for artifact refs, retry feedback, route handoff, and attempt counters.
- Add `core/providers/rendering.py` with deterministic markdown rendering and an optional `ProviderPromptRenderPolicy` whose default remains unlimited and fail-on-overflow.
- Add `core/providers/parsing.py` for shared `parse_outcome_json`.
- Add `core/providers/rendered.py` for `RenderedLLMProvider`.
- Refactor Codex and Claude runtime providers into pure transports, keeping CLI capability probing, subprocess execution, session binding, and envelope parsing in runtime.
- Update `runtime/provider_backends.py` to return `RenderedLLMProvider(CodexTransport(...))` or `RenderedLLMProvider(ClaudeTransport(...))`.

### 2. Engine request enrichment and provider retries
- Add `ProviderRetryPolicy` and retry-feedback rendering in `core/providers/retries.py`.
- Add `retry_policy` to `LLMStep` and `PairStep`, compile it into `CompiledStep`, export it through `core/__init__.py` and `workflow/__init__.py`, and reject it on `SystemStep`.
- Add engine helpers to build provider artifact refs from canonical resolved artifacts and route-required artifact maps from compiled route contracts.
- Replace `_request_control_contract` with richer provider request construction that includes required inputs, writable artifacts, route-required artifacts, retry feedback, route handoff, and attempt counters.
- Wrap only provider-mediated execution in a retry loop. `PairStep` retries restart producer → verifier → validate as one attempt. Missing input artifacts, middleware/system routing bugs, handler failures, and extension failures remain non-retryable.
- Preserve raw-output logging, `StepFinish` telemetry, and failure context while adding retry count and retry classification to exhausted failures.

### 3. Route handoff effects and persistence
- Add `Handoff` in `core/effects.py` and export it through the authoring shims. Do not add `max_chars`.
- Extend `Event` with `handoff: str | None` and validate non-empty stripped text.
- Add `PendingHandoff` plus `pending_handoffs` to checkpoint payloads and persistence backends with backward-compatible deserialization defaults.
- Resolve handoffs after route resolution, including destination overrides from route effects such as `Advance(...)`.
- Persist handoffs by resolved target step plus worklist/item identity when the source step is scoped.
- Inject the combined handoff only into the matching target provider turn, consume it after dispatch starts, and preserve it across resume if dispatch never begins.
- Enforce Option A from the request: validation rejects handoff delivery to `SystemStep` targets.

### 4. Docs, baselines, and verification
- Update architecture/authoring docs and all affected workflow `prompts/README.md` baselines from the narrow three-field contract language to the requested compact human-readable runtime step contract language.
- Remove doc guidance that forbids a shared runtime prompt renderer, because that guidance conflicts with the requested architecture.
- Add transport-purity tests, renderer tests, retry tests, handoff tests, provider-backend tests, and checkpoint compatibility coverage.
- Run the targeted pytest commands from the request, then the full suite.

## Interface Delta
- `core/providers/turns.py`
  - `RenderedProviderTurn(step_name, turn_kind, prompt_text, session, expected_response)`
  - `ProviderTurnResult(raw_text, session, metadata)`
- `core/providers/models.py`
  - new `ProviderArtifactRef`
  - new `ProviderTurnContext`
  - request additions: `required_artifacts`, `writable_artifacts`, `route_required_artifacts`, `retry_feedback`, `route_handoff`, `attempt`, `max_attempts`
  - `VerifierRequest.raw_output` stays temporarily with a deprecation comment
- `core/providers/rendering.py`
  - `render_provider_turn(context)`
  - `ProviderPromptRenderPolicy(max_prompt_chars=None, overflow_behavior="fail")`
- `core/providers/parsing.py`
  - `parse_outcome_json(text) -> Outcome`
- `core/providers/rendered.py`
  - `RenderedLLMProvider(transport: ProviderTransport)`
- `core/providers/retries.py`
  - `ProviderRetryPolicy`
  - `build_retry_feedback(...)`
- `core/effects.py`
  - `Handoff(message: str)`
- `core/primitives.py`
  - `Event.handoff`
  - `PendingHandoff`
  - `Checkpoint.pending_handoffs`

## Compatibility And Migration Notes
- Public CLI and runtime config stay unchanged. Backend resolution remains keyed by `provider.name`.
- Semantic in-process providers remain supported. `ScriptedLLMProvider` continues consuming semantic request objects and should gain only additive request fields.
- Runtime provider files become transport-only, but capability probing, session resume semantics, and subprocess error formatting stay local to runtime.
- Checkpoint persistence gains `pending_handoffs`; loaders must treat missing data as `()`, so existing checkpoints remain readable.
- Route contracts, artifact validation, and `expected_output_schema` semantics stay authoritative. The renderer exposes them in human-readable markdown rather than raw narrow metadata.
- Raw outputs remain available through `Outcome.raw_output`, `StepFinish`, log artifacts, tracing/extension payloads, and failure records, but never enter rendered provider prompts.

## Regression Controls
- Preserve the semantic/provider split: engine continues talking to `LLMProvider`; only runtime-backed backends are wrapped in `RenderedLLMProvider`.
- Keep runtime transports free of workflow semantics via explicit source-level purity tests against `runtime/providers/codex.py` and `runtime/providers/claude.py`.
- Keep retry classification narrow and explicit so middleware/system failures are not miscategorized as provider retries.
- Rebuild each retry attempt from canonical context and artifact state only; never replay previous raw provider output into the next prompt.
- Scope handoffs by resolved target step and active worklist item to prevent leakage between unrelated scoped runs.
- Keep filesystem checkpoint reads tolerant of older payloads and write new fields additively.

## Risk Register
- Risk: provider refactor breaks CLI resume/session binding semantics.
  Mitigation: leave session metadata helpers in runtime, preserve provider-match guards, and add backend-resolution plus transport-session tests.
- Risk: retry loop duplicates side effects or retries non-provider failures.
  Mitigation: wrap only provider-mediated turn execution and validation; keep missing-input, middleware/system, handler, extension, and worklist failures outside the retry loop.
- Risk: handoff leaks across worklist items or survives too long.
  Mitigation: persist `PendingHandoff` with worklist/item identity, deliver only on exact target-step match, and consume only after provider dispatch starts.
- Risk: doc baselines diverge across many workflow prompt packages.
  Mitigation: drive updates from a repository-wide search of the narrow contract phrase and rerun baseline-doc tests after edits.

## Validation
- Targeted: `tests/runtime/test_runtime_providers.py`, `tests/runtime/test_provider_backends.py`, `tests/contract/test_engine_contracts.py`, `tests/unit/test_validation.py`, `tests/unit/test_primitives_and_stores.py`, `tests/test_architecture_baseline_docs.py`.
- Full suite: `.venv/bin/pytest -q`.
- Done means: runtime transports are pure, shared rendering owns all CLI prompt text, default provider retries are 3 with explicit opt-down to 1, handoffs survive resume without leaking scope, and raw-output telemetry remains intact while prompts exclude it.
