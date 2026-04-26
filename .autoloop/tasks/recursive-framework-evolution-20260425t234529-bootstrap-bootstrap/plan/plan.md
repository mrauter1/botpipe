# Provider Boundary Refactor Plan

## Scope Lock
- Implement the request snapshot as written: shared rendered provider turns for CLI transports, provider-attributable retry policy with default `3`, route handoff support, and strict removal of raw provider output from provider-facing prompts.
- Preserve the engine-facing semantic `LLMProvider` protocol, `ScriptedLLMProvider`, public CLI/config flow, route contracts, expected output validation, artifact validation, and raw-output telemetry surfaces.
- Keep prompt rendering in `core/providers`, not `runtime/providers`, and do not add `max_chars` to `Handoff`.

## Current Baseline
- `runtime/providers/codex.py` and `runtime/providers/claude.py` currently implement the semantic provider interface directly, call `render_verifier_input(...)`, and parse verifier/LLM outcome JSON themselves.
- `runtime/providers/_common.py` currently mixes transport-safe helpers with workflow-aware helpers (`parse_outcome_json`, `render_verifier_input`), so the boundary split needs a careful extraction rather than a blind move.
- `core/engine.py` currently injects only `expected_output_schema`, `available_routes`, and `route_contracts`; it validates provider output once, persists only `pending_question` / `pending_answer`, and has no provider retry loop or handoff state.
- `core/primitives.py`, `core/effects.py`, `core/routes.py`, `core/stores/*`, and `runtime/stores/filesystem.py` currently have no handoff representation or checkpoint persistence for deferred route context.
- Docs and baseline tests currently freeze the older “narrow runtime-injected contract” wording, so implementation and documentation must land together.

## Implementation Milestones

### 1. Provider Boundary Refactor In Core
- Add `core/providers/turns.py` with `RenderedProviderTurn` and `ProviderTurnResult`.
- Extend `core/providers/protocols.py` with `ProviderTransport` while leaving `LLMProvider` unchanged.
- Extend `core/providers/models.py` with `ProviderArtifactRef`, `ProviderTurnContext`, and additive request fields for artifacts, retries, and handoffs. Keep `VerifierRequest.raw_output` only as deprecated telemetry.
- Add `core/providers/rendering.py` for markdown prompt rendering plus optional render policy, and `core/providers/parsing.py` for shared outcome JSON parsing.
- Add `core/providers/rendered.py` with `RenderedLLMProvider` to translate semantic requests into rendered transport turns and parse verifier/LLM outcomes in core.

### 2. Convert Runtime Providers To Pure CLI Transports
- Refactor `runtime/providers/codex.py` and `runtime/providers/claude.py` so they accept only `RenderedProviderTurn` and return only `ProviderTurnResult`.
- Leave CLI capability probing, subprocess invocation, CLI envelope parsing, session resume, and cross-provider resume guards in runtime.
- Remove semantic request/response imports, workflow outcome parsing, verifier packet rendering, and workflow-contract awareness from runtime providers.
- Update `runtime/provider_backends.py` to return `RenderedLLMProvider(CodexTransport(...))` or `RenderedLLMProvider(ClaudeTransport(...))` without changing config semantics.

### 3. Add Provider Retry Policy And Retryable Step Execution
- Add `core/providers/retries.py` with `ProviderRetryPolicy` and `build_retry_feedback(...)`.
- Add `retry_policy` to `LLMStep` and `PairStep`, compile it into `CompiledStep`, export it through `core/__init__.py` and `workflow/__init__.py`, and reject it on `SystemStep`.
- Build provider artifact metadata in `core/engine.py` so requests carry required inputs, writable outputs, route-required artifacts, retry feedback, handoff text, attempt, and max-attempt metadata.
- Wrap only provider-mediated execution (`LLMStep`, `PairStep`) in a retry loop. Pair retries must restart from producer, not verifier.
- On final retry exhaustion, persist checkpoint failure data that includes useful failure context plus retry-attempt consumption so resume/debug surfaces and changed failure tests can distinguish first-failure from exhausted-retry failure.
- Preserve the current distinction between provider failures and middleware/system/required-input failures so only provider-attributable failures retry.

### 4. Add Route Handoff Effect, Event Data, And Persistence
- Add `Handoff` to `core/effects.py` and validation/compile support in `core/routes.py`, `core/compiler.py`, and `core/validation.py`.
- Extend `Event` with `handoff: str | None` and validate non-empty stripped text only.
- Expose `Handoff` on the public authoring surface through `core/__init__.py` and `workflow/__init__.py`, and expose the updated `Event` primitive through `workflow/primitives.py` so workflow authors can use the new surface without reaching into core internals.
- Add `PendingHandoff` to checkpoint primitives and persist `pending_handoffs` through in-memory and filesystem checkpoint stores.
- Resolve handoffs only after route resolution, ignore them for terminal destinations, reject handoff-to-`SystemStep` during validation, scope them by worklist/item identity when present, and consume them only after provider dispatch begins.

### 5. Update Tests, Docs, And Baselines Together
- Add provider transport purity tests, renderer tests, retry tests, and handoff tests covering persistence, scoping, non-leakage, and one-time consumption.
- Update runtime provider tests to assert prompt transport behavior and core-side outcome parsing.
- Update baseline-asserted docs (`docs/architecture.md`, `docs/authoring.md`, `workflows/*/prompts/README.md`, `tests/test_architecture_baseline_docs.py`) and sweep adjacent docs/prompts that still repeat the stale “narrow contract only” wording.
- Run targeted tests first, then the full suite.

## Interface Deltas
- `core/providers/turns.py`
  - `RenderedProviderTurn(step_name, turn_kind, prompt_text, session, expected_response)`
  - `ProviderTurnResult(raw_text, session, metadata)`
- `core/providers/protocols.py`
  - `ProviderTransport.run_turn(turn: RenderedProviderTurn) -> ProviderTurnResult`
- `core/providers/models.py`
  - `ProviderArtifactRef`
  - `ProviderTurnContext`
  - additive request fields: `required_artifacts`, `writable_artifacts`, `route_required_artifacts`, `retry_feedback`, `route_handoff`, `attempt`, `max_attempts`
- `core/providers/rendering.py`
  - `render_provider_turn(context) -> RenderedProviderTurn`
  - `ProviderPromptRenderPolicy(max_prompt_chars=None, overflow_behavior="fail")`
- `core/providers/parsing.py`
  - `parse_outcome_json(text) -> Outcome`
- `core/providers/rendered.py`
  - `RenderedLLMProvider(transport: ProviderTransport)`
- `core/providers/retries.py`
  - `ProviderRetryPolicy`
  - `build_retry_feedback(...)`
- `core/steps.py` / `core/compiler.py`
  - additive `retry_policy` on provider-mediated steps only
- `core/__init__.py` / `workflow/__init__.py`
  - export `ProviderRetryPolicy`
  - export `Handoff`
- `core/effects.py` / `core/primitives.py`
  - `Handoff`
  - `Event.handoff`
  - `PendingHandoff`
  - additive `Checkpoint.pending_handoffs`
- `workflow/primitives.py`
  - re-export the updated `Event` surface with `handoff`

## Compatibility Notes
- Semantic in-process providers remain on the current `LLMProvider` protocol. Only CLI-backed runtime providers move behind `ProviderTransport`.
- `ScriptedLLMProvider` remains a semantic provider and should keep existing test ergonomics.
- Raw provider output remains visible on `Outcome.raw_output`, `StepFinish.producer_raw_output`, `StepFinish.verifier_raw_output`, log artifacts, tracing payloads, and failure context. The renderer must never consume it.
- Checkpoint schema changes are additive. Old checkpoints must continue to load with `pending_handoffs=()`.
- Retry exhaustion changes checkpoint failure payload content additively: old checkpoints continue to load, and new exhausted-provider failures must record retry consumption without changing resume entrypoints.
- Public CLI, runtime config keys, and session slot selection behavior stay unchanged.
- Public workflow authoring imports must stay coherent: `Handoff` and `ProviderRetryPolicy` are available from the same top-level surfaces as the existing step/effect primitives, and `workflow.primitives.Event` exposes `handoff`.
- Default retry behavior changes to `3` attempts for `LLMStep` and `PairStep`; single-attempt legacy expectations must become explicit with `ProviderRetryPolicy(max_attempts=1)`.
- Handoff to terminal destinations is dropped after target resolution. Handoff to `SystemStep` is intentionally rejected in validation for this implementation pass.

## Regression Controls
- Move only workflow-aware provider logic (`parse_outcome_json`, prompt rendering) into core. Keep subprocess formatting, session binding helpers, and CLI capability detection runtime-local.
- Rebuild each retry request from current artifacts, current route contract, current context, pending handoff, and retry feedback only. Do not include previous raw output, previous full prompt, transcript, log paths, or digests.
- Preserve existing pair-step telemetry ordering: producer raw output is still logged before verifier execution, verifier raw output still reaches `StepFinish`, and LLM raw output still appends to log artifacts.
- Classify retryable failures explicitly so missing required input artifacts, middleware bad routes, `SystemStep` bad routes, extension failures, handler exceptions, and worklist errors do not retry.
- Persist retry exhaustion data in the same engine/checkpoint path that already records failure context so retry counts cannot drift between in-memory checkpoints, filesystem checkpoints, and changed failure tests.
- Consume pending handoffs after provider dispatch begins, not before, so a pre-dispatch crash/resume does not lose them.
- Search and update stale doc/prompt phrases in the same implementation slice as the code change to avoid tests passing while guidance stays contradictory.

## Validation Plan
- Targeted tests:
  - `.venv/bin/pytest -q tests/runtime/test_runtime_providers.py`
  - `.venv/bin/pytest -q tests/runtime/test_provider_backends.py`
  - `.venv/bin/pytest -q tests/contract/test_engine_contracts.py`
  - `.venv/bin/pytest -q tests/unit/test_validation.py`
  - `.venv/bin/pytest -q tests/unit/test_primitives_and_stores.py`
  - `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py`
- Full validation:
  - `.venv/bin/pytest -q`

## Risk Register
- Boundary split risk: workflow-aware helpers are currently mixed into `runtime/providers/_common.py`.
  - Mitigation: extract only `parse_outcome_json` and rendering into core; leave transport/session helpers in runtime.
  - Rollback: temporarily keep runtime helper wrappers delegating to new core modules until tests pass, then remove wrappers in the same slice.
- Retry classification risk: broad `ProviderExecutionError` handling could accidentally retry non-provider failures.
  - Mitigation: drive retryability from known provider failure kinds and contract tests covering middleware/system/missing-input counterexamples.
  - Rollback: pin affected tests to `max_attempts=1` while tightening classification logic.
- Handoff leakage risk: pending handoffs could bleed across unrelated steps or worklist items.
  - Mitigation: persist `source_step`, `route_tag`, `target_step`, `worklist_name`, and `item_id`; deliver only on exact target/item match; add non-leakage tests.
  - Rollback: disable handoff persistence while keeping static validation if delivery semantics prove unsafe.
- Public-surface compatibility risk: internal handoff support could land without matching shim/export updates, leaving workflow authors unable to use the new surface.
  - Mitigation: include `core/__init__.py`, `workflow/__init__.py`, and `workflow/primitives.py` in the handoff phase acceptance criteria and compatibility review.
  - Rollback: preserve temporary compatibility aliases or re-exports until authoring-surface tests pass.
- Checkpoint compatibility risk: additive schema changes must stay aligned across protocol, memory store, filesystem store, engine save/load, and clone helpers.
  - Mitigation: update all checkpoint serializers/deserializers together and add resume tests.
  - Rollback: gate new fields behind safe defaults and preserve unknown-field tolerance in filesystem loading.
- Retry-exhaustion observability risk: retries could work but checkpoint/failure surfaces might omit consumed-attempt data, weakening resume/debug behavior and acceptance-test coverage.
  - Mitigation: add explicit engine tests for exhausted retries and persist attempt counters in additive failure context/checkpoint data.
  - Rollback: keep existing failure-context shape plus a separate additive retry-count field if a shared structure change proves too invasive.
- Docs/baseline drift risk: old “narrow contract only” wording appears in multiple docs and prompt readmes.
  - Mitigation: use repo-wide search to update all baseline-covered instances in the same phase as test changes.
  - Rollback: if wider doc updates become noisy, limit the first change set to files covered by baseline tests and add a tracked follow-up doc sweep.
