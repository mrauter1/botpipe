# Implementation Notes

- Task ID: full-revised-autoloop-v3-redesign-implementation-16af2351
- Pair: implement
- Phase ID: feedforward-operations
- Phase Directory Key: feedforward-operations
- Phase Title: Feedforward operations
- Scope: phase-local producer artifact

## Files changed

- `core/operations.py`
- `autoloop/simple.py`
- `autoloop/__init__.py`
- `core/context.py`
- `core/engine.py`
- `core/validation.py`
- `core/providers/models.py`
- `core/providers/protocols.py`
- `core/providers/rendered.py`
- `core/providers/rendering.py`
- `core/providers/fake.py`
- `core/providers/turns.py`
- `core/stores/protocols.py`
- `runtime/stores/filesystem.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_provider_boundary_core.py`
- `tests/contract/test_engine_contracts.py`

## Symbols touched

- Public API: `llm`, `classify`, `llm.step`, `classify.step`
- New runtime module: `OperationRuntime`, `OperationStepSpec`, `llm_call`, `classify_call`, `_normalize_operation_prompt(...)`
- Provider boundary: `OperationRequest`, `OperationResponse`, `LLMProvider.run_operation(...)`
- Persistence: `CheckpointPayload.values`, run-local `operation_replay.json`

## Checklist mapping

- Phase 4 public APIs: implemented standalone `llm()` / `classify()` and `.step(...)` helpers.
- Provider operation path: implemented raw-text `run_operation(...)` contract and rendered-provider support.
- Retry and replay: implemented retry feedback, deterministic replay lookup, and fingerprint mismatch failure.
- `python_step` / helper usage: implemented ambient operation runtime binding from `Engine`.
- Tests: added coverage for standalone calls, retry, provider rendering, replay reruns, mismatch failure, and resume value restoration.
- Reviewer follow-up `IMP-001`: normalized bare string feedforward prompts at the shared operation boundary and added rendered-provider regression coverage for direct calls and helper calls inside `python_step`.

## Assumptions

- Explicit standalone calls may supply `provider=...`; ambient workflow runtime remains the default path for helper-function usage.
- Recorded `ctx.values` may deserialize to JSON-shaped mappings on resume; `NamespaceProxy` keeps attribute-style access for downstream steps.

## Preserved invariants

- The compiled FSM remains unchanged for normal step routing and lowers new feedforward nodes through existing system-step execution.
- `classify.step(...)` does not create implicit FSM routes.
- Replay drift fails loudly instead of silently reusing stale results.

## Intended behavior changes

- Feedforward operations now use a value-returning provider path and can replay from persisted successful results.
- Completed feedforward step values survive pause/resume through checkpointed `ctx.values`.
- Bare string prompts passed to `llm(...)` / `classify(...)` now resolve as inline prompts on the rendered provider path, matching the public shorthand used by standalone and helper-function call sites.

## Known non-changes

- No implicit prompt interpolation or classifier-to-route helper was added in this phase.
- No broad provider transport refactor beyond the additive operation path.
- No top-level workflow parallelism changes.

## Expected side effects

- Runs that execute feedforward operations now create `operation_replay.json` alongside other run artifacts.
- Reusing a run folder with changed operation fingerprints now raises a replay mismatch error instead of re-executing.

## Validation performed

- `python3 -m py_compile` on all touched source and test files in cycle 1.
- `python3 -m py_compile core/operations.py tests/unit/test_simple_surface.py tests/contract/test_engine_contracts.py` after the reviewer follow-up fix in cycle 2.
- Direct test execution was not possible here because the environment lacks `pytest` and `pydantic`.

## Deduplication / centralization

- Centralized feedforward execution, retry, replay, and ambient runtime binding in `core/operations.py`.
- Centralized bare-string prompt normalization in `core/operations.py` so direct calls and workflow-bound helper calls share the same inline-prompt semantics as `.step(...)`.
- Reused existing system-step lowering instead of adding a second compiled engine path for value nodes.
