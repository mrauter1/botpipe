# Implementation Notes

- Task ID: you-are-a-principal-software-architect-and-imple-63e1905d
- Pair: implement
- Phase ID: book-architecture-core
- Phase Directory Key: book-architecture-core
- Phase Title: Book-Architecture Core
- Scope: phase-local producer artifact

## Files Changed

- `autoloop_v3/ARCHITECTURE_DECISIONS.md`
- `autoloop_v3/workflow/{__init__.py,compiler.py,engine.py,primitives.py,steps.py,validation.py}`
- `autoloop_v3/runtime/loader.py`
- `workflow/__init__.py`
- `autoloop_v3/tests/unit/{test_primitives_and_stores.py,test_validation.py}`
- `autoloop_v3/tests/contract/test_engine_contracts.py`
- `autoloop_v3/tests/runtime/test_compatibility_runtime.py`
- deleted `autoloop_v3/workflow/compat.py`

## Symbols Touched

- `Session`, `Workflow`, `compile_workflow`, `Engine._select_session`, `outcome_middleware_name`
- removed `SessionLifecycle`, `Verdict`, `normalize_workflow`, `legacy_annotation_globals`

## Checklist Mapping

- Phase 1 / decision record: completed via `autoloop_v3/ARCHITECTURE_DECISIONS.md`
- Phase 1 / remove strict-core compat: completed in workflow core, loader, and root shim
- Phase 1 / strict proofs: completed with unit, contract, and focused loader tests
- Deferred intentionally: runtime-core reduction and Autoloop-v1 parity harness relocation remain later-phase work

## Assumptions

- Repo-root workflows already import explicit canonical symbols and therefore do not require loader injection in this phase
- Stale compatibility docs and runtime-parity docs remain until the later documentation and runtime phases

## Preserved Invariants

- explicit `entry` remains mandatory
- `on_start(self, ctx)` remains the only automatic lifecycle hook
- routing precedence remains step-local, then `GLOBAL`, else error
- Pair/LLM handlers remain optional; System handlers remain required

## Intended Behavior Changes

- strict core no longer accepts `Verdict`, `on_verdict`, `SessionLifecycle`, inferred session opening, or legacy handler arities
- repo-root `workflow` exports the strict `Workflow` base directly
- loader imports workflow modules without prebinding canonical names

## Known Non-Changes

- runtime workspace/session-path policy remains unchanged in this phase
- legacy/parity docs were not rewritten in this phase
- Autoloop-v1 parity harness relocation was not started here by design

## Expected Side Effects

- workflows that relied on hidden imports, `on_verdict`, `Verdict`, `SessionLifecycle`, or auto-opened sessions will now fail fast during import, validation, or execution

## Validation Performed

- `pytest autoloop_v3/tests/unit/test_primitives_and_stores.py autoloop_v3/tests/unit/test_validation.py autoloop_v3/tests/contract/test_engine_contracts.py`
- `pytest autoloop_v3/tests/runtime/test_compatibility_runtime.py -k 'autoloop_v1_imports_through_root_workflow_shim_and_legacy_loader_handles_ralph or loader_does_not_inject_canonical_symbols'`

## Deduplication / Centralization

- centralized the single global middleware concept on `on_outcome`
- removed duplicated session-opening policy from steps, compiler, and engine by making workflows own `ctx.open_session(...)`
