# Implementation Notes

- Task ID: recursive-framework-evolution-20260425t234529-bootstrap-bootstrap
- Pair: implement
- Phase ID: provider-boundary-core
- Phase Directory Key: provider-boundary-core
- Phase Title: Core Provider Boundary
- Scope: phase-local producer artifact

## Files changed
- `core/providers/__init__.py`
- `core/providers/models.py`
- `core/providers/parsing.py`
- `core/providers/protocols.py`
- `core/providers/rendered.py`
- `core/providers/rendering.py`
- `core/providers/turns.py`
- `runtime/providers/_common.py`
- `runtime/providers/claude.py`
- `runtime/providers/codex.py`
- `tests/runtime/test_runtime_providers.py`
- `tests/unit/test_provider_boundary_core.py`

## Symbols touched
- `ProviderArtifactRef`
- `ProviderTurnContext`
- `RenderedProviderTurn`
- `ProviderTurnResult`
- `ProviderTransport`
- `ProviderPromptRenderPolicy`
- `render_provider_turn(...)`
- `render_provider_turn_with_policy(...)`
- `parse_outcome_json(...)`
- `RenderedLLMProvider`
- `ProducerRequest` / `VerifierRequest` / `LLMRequest` additive fields
- `CodexProvider` / `ClaudeProvider` private transport delegation

## Checklist mapping
- Plan item 1: added rendered transport models in `core/providers/turns.py`.
- Plan item 2: added `ProviderTransport` to `core/providers/protocols.py`.
- Plan item 3: added provider artifact/context models and additive request metadata fields.
- Plan item 4: added shared markdown renderer plus render policy type.
- Plan item 5: added `RenderedLLMProvider`.
- Plan item 6: moved shared outcome parsing into `core/providers/parsing.py`.
- Reviewer IMP-001: verifier/LLM runtime providers now delegate outcome parsing through `RenderedLLMProvider` instead of parsing in runtime provider methods.
- Reviewer IMP-002: render policy is now caller-addressable through `render_provider_turn_with_policy(...)`.
- Plan items 7-10 and later: intentionally deferred to later phases.

## Assumptions
- This phase is allowed to make minimal runtime import updates needed to consume the new core parser without performing the transport refactor.
- Engine/request construction remains unchanged in this phase, so additive request fields must stay fully default-compatible.

## Preserved invariants
- The semantic `LLMProvider` protocol and `ScriptedLLMProvider` remain intact.
- Runtime backend resolution and public provider class names are unchanged.
- Provider raw output is excluded from the new shared renderer path.
- Response metadata shape remains `metadata` on `ProducerResponse` / `OutcomeResponse`.

## Intended behavior changes
- Shared provider-turn rendering now exists in core and emits human-readable markdown runtime contracts.
- Outcome JSON parsing now lives in `core/providers/parsing.py` and verifier/LLM runtime execution crosses the core `RenderedLLMProvider` boundary before parsing.
- Render policy can now be supplied explicitly via `render_provider_turn_with_policy(...)`.

## Known non-changes
- `runtime/providers/codex.py` and `runtime/providers/claude.py` still expose the semantic provider interface in this phase.
- Producer turns still use the existing direct prompt path to avoid widening this phase into backend-resolution work; verifier/LLM turns now use the private transport plus core wrapper path.
- `render_verifier_input(...)` remains runtime-local test-covered compatibility code until the later provider-transport purity phase.
- Engine retry loops, artifact metadata injection, handoff persistence, backend wrapping, and docs/baseline updates are not part of this phase change set.

## Expected side effects
- New core renderer/wrapper modules are available for later engine/backend integration work.
- Existing runtime provider tests now validate that verifier/LLM prompts cross the shared rendered boundary without including producer raw output.

## Deduplication / centralization
- Centralized workflow-aware outcome parsing in `core/providers/parsing.py`.
- Centralized shared prompt rendering in `core/providers/rendering.py`.
- Centralized verifier/LLM runtime parsing ownership in `RenderedLLMProvider` while leaving producer transport behavior stable for this phase.

## Validation performed
- `.venv/bin/python -m compileall core/providers runtime/providers tests/unit/test_provider_boundary_core.py tests/runtime/test_runtime_providers.py`
- `.venv/bin/pytest -q tests/unit/test_provider_boundary_core.py`
- `.venv/bin/pytest -q tests/runtime/test_runtime_providers.py`
- `.venv/bin/pytest -q tests/runtime/test_provider_backends.py`
- `.venv/bin/pytest -q tests/contract/test_engine_contracts.py`
- `.venv/bin/pytest -q tests/unit/test_provider_boundary_core.py tests/runtime/test_runtime_providers.py tests/runtime/test_provider_backends.py tests/contract/test_engine_contracts.py`
