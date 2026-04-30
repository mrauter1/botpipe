# Implementation Notes

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: strictness-and-suite-migration
- Phase Directory Key: strictness-and-suite-migration
- Phase Title: Migrate Active Suites And Tighten Strictness
- Scope: phase-local producer artifact

## Files changed

- `core/_compat.py`
- `core/compiler.py`
- `core/descriptors.py`
- `core/engine.py`
- `core/steps.py`
- `core/validation.py`
- `docs/authoring.md`
- `tests/contract/test_engine_contracts.py`
- `tests/fixtures/toy_runtime_workflow.py`
- `tests/runtime/test_compatibility_runtime.py`
- `tests/strictness/test_no_compat.py`
- `tests/test_architecture_baseline_docs.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/unit/test_validation.py`

## Symbols touched

- Internal step/descriptors renamed off legacy tokens: `AfterStepResult`, `PromptStep`, `ProduceVerifyStep`, `PythonStep`, `ChildWorkflowStep`, `ParameterField`, `StateField`
- Removed low-level compatibility exports from `core._compat`
- Strictness banned-name scan expanded to cover the removed low-level class/descriptors tokens in the maintained tree

## Checklist mapping

- Milestone 2 / route-runtime follow-through: active `core` implementation no longer spells the removed low-level class/descriptors names on maintained paths.
- Milestone 3 / suite migration: `tests/unit/test_validation.py`, `tests/contract/test_engine_contracts.py`, runtime compatibility fixtures, and surface/docs assertions now use the renamed internal vocabulary or fragmented removed-name strings where absence is being asserted.
- Milestone 3 / strictness: `tests/strictness/test_no_compat.py` now bans the removed low-level step/descriptors names across `autoloop/`, `core/`, `runtime/`, `stdlib/`, `workflows/`, docs, and active tests while excluding only explicit compatibility fixtures.

## Assumptions

- No persisted-run/session/checkpoint reader in this checkout requires live low-level authoring aliases for the removed names.
- The explicit `autoloop_v3.core` bridge remains required for shared module identity and is intentionally preserved in this phase.

## Preserved invariants

- `core.*` and `autoloop_v3.core.*` still resolve to the same module graph.
- Canonical route/runtime payload semantics remain `FINISH` plus `required_writes`.
- Compatibility coverage still targets persisted payload/session/checkpoint normalization rather than active public authoring aliases.

## Intended behavior changes

- Active `core` implementation and active suites no longer contain the removed low-level identifiers `AfterHookResult`, `LLMStep`, `PairStep`, `SystemStep`, `WorkflowStep`, `Param`, or `StateVar`.
- `core._compat` no longer exposes replacement aliases for those removed names.
- Documentation now describes `workflow_step(...)` without advertising the removed low-level child-workflow class name.

## Known non-changes

- The explicit `core` / `autoloop_v3.core` bridge was not removed.
- Persisted payload normalization behavior in runtime/session/checkpoint code was not broadened or reduced in this phase.
- Internal artifact-mapping storage still uses existing `produces`-backed implementation details; this phase targeted banned legacy names and strictness coverage.

## Expected side effects

- Any future tests or helpers that try to import the removed low-level names from active `core` modules will fail fast and be caught by strictness.
- Compatibility runtime fixtures must author in-memory workflows with the renamed internal classes even when the serialized payload under test is historical.

## Validation performed

- `rg -n "\\b(LLMStep|PairStep|SystemStep|WorkflowStep|AfterHookResult|Param|StateVar|SUCCESS|RouteInfo|required_outputs|route_infos)\\b" autoloop core runtime stdlib workflows tests docs -g '*.py' -g '*.md' --glob '!tests/runtime/test_compatibility_runtime.py' --glob '!tests/fixtures/toy_runtime_workflow.py' --glob '!core/_compat.py'`
  Result: matches remained only inside `tests/strictness/test_no_compat.py`, which is explicitly excluded from its own scan.
- `python3 -m py_compile core/_compat.py core/descriptors.py core/steps.py core/compiler.py core/validation.py core/engine.py tests/unit/test_simple_surface.py tests/unit/test_validation.py tests/unit/test_stdlib_and_extensions.py tests/contract/test_engine_contracts.py tests/runtime/test_compatibility_runtime.py tests/fixtures/toy_runtime_workflow.py tests/strictness/test_no_compat.py tests/test_architecture_baseline_docs.py`
  Result: success.
- Full `pytest` verification was not run because this environment does not have `pydantic` or `pytest` installed.

## Deduplication / centralization

- Applied one shared internal rename across `core` implementation and the active suites instead of keeping alias shims or per-suite compatibility wrappers.
