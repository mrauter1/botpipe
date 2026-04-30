# Implementation Notes

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: canonicalize-core-produces-surface
- Phase Directory Key: canonicalize-core-produces-surface
- Phase Title: Canonicalize Core Vocabulary
- Scope: phase-local producer artifact

## Files changed
- `core/steps.py`
- `core/compiler.py`
- `core/validation.py`
- `core/engine.py`
- `core/__init__.py`
- `core/_compat.py`
- `core/workflow_capabilities.py`
- `tests/unit/test_validation.py`
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_compatibility_runtime.py`
- `tests/fixtures/toy_runtime_workflow.py`
- `tests/strictness/test_no_compat.py`
- `autoloop_v3/core/__init__.py`
- `__init__.py`

## Symbols touched
- `core.steps.Step`
- `core.steps.ProduceVerifyStep`
- `core.steps.PromptStep`
- `core.steps.PythonStep`
- `core.steps.ChildWorkflowStep`
- `core.compiler._compile_steps`
- `core.validation._SimpleStepSeed`
- `core.validation.describe_workflow_class`
- `core.validation._lower_simple_steps`
- `core.validation._analyze_simple_prompt_references`
- `core.validation._known_simple_step_outputs`
- `core.validation.collect_artifact_inventory`
- `core.validation._validate_required_artifacts`
- `core.validation._normalize_route_required_writes`
- `core.engine.Engine._write_workflow_step_outputs`
- `core._compat.bridge_core_package`
- `core.workflow_capabilities._inspect_catalog_entry`
- `core.workflow_capabilities._resolve_reference`

## Checklist mapping
- Milestone 1: completed
  - Canonicalized maintained core constructor/storage attrs from `produces` to `writes`, and pair-step live attrs to `producer_writes` / `verifier_writes`.
  - Updated compiler, validation, engine, and simple-step lowering to consume canonical write vocabulary only.
  - Removed dynamic alias mirroring from `core/__init__.py`.
- Milestone 2: completed
  - Migrated maintained non-migration workflow declarations in validation, engine-contract, runtime-compatibility, and fixture tests to canonical write vocabulary.
  - Kept compatibility coverage in `tests/runtime/test_compatibility_runtime.py` focused on runtime/package/session behavior without legacy in-memory step authoring.
  - Tightened strictness scan to include the compatibility runtime suite and ban live `produces`/`review_produces`/`do_produces` patterns.

## Assumptions
- The maintained dual-package compatibility requirement is module/class identity for `autoloop_v3.core.*` versus `core.*`, not constructor-level `produces` support.
- The repo can be imported through two package topologies, so both `__init__.py` entrypoints may exist, but the bridge implementation itself must stay centralized.

## Preserved invariants
- Compiled/runtime artifacts still expose canonical `writes`, `producer_writes`, and `verifier_writes`.
- Pair-step verifier dependency checks still distinguish producer-written artifacts from verifier-only writes.
- Child-workflow output materialization still writes canonical child result payloads through declared step output artifacts.
- Mixed `core.*` and `autoloop_v3.core.*` imports still share module/class identity.

## Intended behavior changes
- Maintained core constructors no longer accept live `produces` / `review_produces` kwargs.
- Maintained strictness now fails active `produces=` / `.produces` / `review_produces` / `do_produces` usage across the maintained tree, including the compatibility runtime suite.

## Known non-changes
- Persisted session/checkpoint/run compatibility readers were left untouched.
- Prose/doc usage of the English word `produces` was not treated as banned vocabulary.

## Expected side effects
- Callers using direct `PromptStep` / `PythonStep` / `ChildWorkflowStep` / `ProduceVerifyStep` construction must use canonical write kwargs.
- Workflow capability inspection now imports runtime-loader types via top-level runtime compatibility paths instead of package-relative imports.

## Deduplication / centralization
- Centralized the explicit `autoloop_v3.core -> core` identity bridge implementation in `core/_compat.py`; the repo-root `__init__.py` and nested `autoloop_v3/core/__init__.py` are now thin shims over that single alias table.

## Validation performed
- `.venv/bin/pytest tests/unit/test_simple_surface.py tests/unit/test_validation.py tests/contract/test_engine_contracts.py tests/runtime/test_compatibility_runtime.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_provider_backends.py tests/strictness/test_no_compat.py`
- Result: `279 passed`
