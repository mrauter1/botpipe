# Implementation Notes

- Task ID: recursive-framework-evolution-20260426t124100-bootstrap
- Pair: implement
- Phase ID: provider-usage-plumbing
- Phase Directory Key: provider-usage-plumbing
- Phase Title: Provider Usage Plumbing
- Scope: phase-local producer artifact

## Files changed
- `core/providers/models.py`
- `core/providers/turns.py`
- `core/providers/rendered.py`
- `core/providers/__init__.py`
- `runtime/providers/_common.py`
- `runtime/providers/codex.py`
- `runtime/providers/claude.py`
- `core/extensions.py`
- `core/engine.py`
- `tests/unit/test_provider_boundary_core.py`
- `tests/runtime/test_runtime_providers.py`
- `tests/contract/test_engine_contracts.py`

## Symbols touched
- `TokenUsage`
- `StepProviderUsage`
- `ProducerResponse.usage`
- `OutcomeResponse.usage`
- `ProviderTurnResult.usage`
- `RenderedLLMProvider.run_producer`
- `RenderedLLMProvider.run_verifier`
- `RenderedLLMProvider.run_llm`
- `extract_token_usage`
- `parse_codex_exec_json`
- `parse_claude_exec_json`
- `StepFinish.provider_usage`
- `Engine._execute_step`
- `Engine._execute_pair_step`
- `Engine._execute_llm_step`
- `Engine._run_pair_step`
- `Engine._run_llm_step`

## Checklist mapping
- Plan milestone 1 / item 1: added `TokenUsage` and `StepProviderUsage`.
- Plan milestone 1 / item 2: extended provider responses and transport result with optional usage.
- Plan milestone 1 / item 3: extended `StepFinish` with `provider_usage` only.
- Plan milestone 1 / item 4: propagated usage through rendered/runtime providers and pair/llm engine execution.
- Plan milestone 1 / validation: added regression coverage for defaults, fake provider emission, runtime usage extraction, and step-finish exposure.

## Assumptions
- Runtime provider CLIs may expose usage under `usage`, `token_usage`, or `provider_usage`, sometimes nested inside provider-specific payloads.
- Per-turn token usage should not become part of resumable session identity metadata.

## Preserved invariants
- Missing provider usage remains non-fatal and defaults to `None`.
- Existing provider callers that ignore usage stay compatible.
- `StepFinish` still carries raw producer/verifier outputs unchanged.
- System steps remain provider-free and emit `provider_usage=None`.

## Intended behavior changes
- Pair and llm step-finish events now surface typed provider usage when available.
- Rendered runtime providers now normalize token usage from CLI payloads into `TokenUsage`.

## Known non-changes
- No git tracking, tracing, static graph, runner, or workspace behavior changed in this phase.
- No workflow semantics, routing, retry policy, or artifact contract behavior changed.

## Expected side effects
- Claude/Codex response metadata still preserves raw provider metadata for the current turn, while session metadata omits transient usage blobs.

## Validation performed
- `./.venv/bin/python -m pytest tests/runtime/test_provider_backends.py tests/unit/test_provider_boundary_core.py tests/runtime/test_runtime_providers.py tests/contract/test_engine_contracts.py -q`
- Result: `126 passed`

## Deduplication / centralization decisions
- Centralized usage normalization in `runtime/providers/_common.py` and the rendered transport seam instead of duplicating mapping logic per semantic provider method.
