# Remaining `produces` Cleanup Plan

## Goal
Remove the remaining active `produces` contract from maintained `core` runtime/authoring paths and maintained tests, keep legacy translation only at true persisted compatibility boundaries, tighten strictness so the legacy vocabulary cannot re-enter maintained code, and collapse package aliasing to the single explicit `autoloop_v3.core -> core` bridge.

## Milestones
1. Canonicalize maintained `core` step/runtime vocabulary.
2. Migrate maintained tests and fixtures, confine compatibility coverage to persisted-reader inputs, and harden strictness.

## Implementation Plan

### Milestone 1: Canonicalize maintained `core` step/runtime vocabulary
- Update maintained step declarations in `core/steps.py` so active constructor/storage names are canonical:
  - `Step`/`PromptStep`/`PythonStep`/`ChildWorkflowStep`: `writes` instead of `produces`.
  - `ProduceVerifyStep`: `producer_writes` / `verifier_writes` instead of `produces` / `review_produces`.
  - Remove maintained use of `step.produces`, `do_produces`, and `review_produces`; internal attrs should match the compiled/runtime vocabulary already used elsewhere (`writes`, `producer_writes`, `verifier_writes`).
- Rename the remaining validation internals in `core/validation.py` to the same canonical vocabulary:
  - `_SimpleStepSeed` fields, simple-step lowering, inventory collection, prompt-reference analysis, route required-write validation, and verifier dependency checks should all read/write canonical names.
  - Keep legacy handling only where persisted payload/session/checkpoint readers genuinely require translation; do not keep constructor-level or in-memory authoring aliases in maintained `core`.
- Update `core/compiler.py` and `core/engine.py` to consume canonical step attrs only, preserving current qualified artifact resolution and child-workflow output behavior.
- Remove `_alias_core_package_names()` from `core/__init__.py`.
  - `autoloop_v3/core/__init__.py` remains the single explicit package bridge.
  - Confirm maintained imports do not rely on mirrored `sys.modules` aliases for submodules.

### Milestone 2: Migrate maintained suites, narrow compatibility coverage to persisted readers, and harden strictness
- Migrate remaining active maintained tests and fixtures away from `produces`:
  - `tests/unit/test_validation.py`
  - `tests/contract/test_engine_contracts.py`
  - `tests/fixtures/toy_runtime_workflow.py`
  - Any other maintained non-migration workflow declarations found during the edit pass
- Re-check runtime/provider coverage and split the current compatibility suite along the actual legacy boundary.
  - `tests/runtime/test_compatibility_runtime.py` must retain legacy vocabulary only for persisted session/checkpoint/run payload normalization or reader behavior.
  - Any compatibility-runtime tests that currently build live in-memory workflows with `PromptStep(..., produces=...)` or `ProduceVerifyStep(..., review_produces=...)` must be migrated to canonical `writes` authoring or moved out of the compatibility-only surface; they are not protected by the persisted-reader exception.
  - If compatibility fixtures are still needed, they must be persisted payload/source fixtures consumed by reader code, not executable workflow declarations that depend on active constructor aliases.
- Tighten `tests/strictness/test_no_compat.py` to fail on active `produces`, `review_produces`, and `do_produces` usage across the maintained tree.
  - Keep scan roots on maintained code/tests.
  - Exclude only explicit persisted-compatibility fixture files, not maintained implementation files, active fixtures, or broad test suites.

## Interfaces And Compatibility
- Intentional behavior break: direct maintained `core.steps` constructor support for `produces` / `review_produces` is removed as active authoring surface. This is in scope and explicitly requested.
- Allowed legacy boundary: persisted session/checkpoint/run payload normalization and compatibility readers only.
- Compatibility coverage does not justify keeping executable legacy step declarations. If a current compatibility test uses live legacy step authoring, migrate or reclassify the test instead of preserving constructor aliases.
- No compiled/runtime payload contract should regress: compiled steps still expose `writes`, `producer_writes`, and `verifier_writes`, and child workflow result payloads continue to use canonical `output_artifacts`.
- Package compatibility is reduced to one explicit path: `autoloop_v3.core` importing `core`.

## Regression Controls
- Preserve artifact qualification semantics while renaming fields: duplicate-name detection, owner-step binding, verifier read/write separation, route required-write validation, and child-workflow output materialization must remain behaviorally identical.
- Before removing the alias shim, scan maintained imports for any direct reliance on mirrored `core.*` / `autoloop_v3.core.*` submodule identity; if a maintained test fails, fix the import path rather than restoring dynamic aliasing.
- Keep compatibility-only legacy coverage limited to persisted-reader fixtures so strictness can stay aggressive without hiding maintained regressions or preserving active constructor aliases.

## Verification
- For this cleanup, the canonical verification suite is the targeted regression set below:
  - `pytest tests/unit/test_validation.py`
  - `pytest tests/contract/test_engine_contracts.py`
  - `pytest tests/runtime/test_compatibility_runtime.py`
  - `pytest tests/runtime/test_runtime_static_graph.py`
  - `pytest tests/runtime/test_provider_backends.py`
  - `pytest tests/strictness/test_no_compat.py`
- If normal branch CI runs broader coverage after this set, treat any additional alias/vocabulary regression there as blocking before completion.

## Risk Register
- Constructor rename risk: hidden maintained direct `PromptStep` / `ProduceVerifyStep` call sites may still use legacy kwargs.
  - Mitigation: repo-wide search before final verification; strictness test updated to catch regressions.
- Alias removal risk: some import-order paths may have implicitly depended on mirrored `sys.modules` entries.
  - Mitigation: keep only the explicit `autoloop_v3.core` bridge and fix maintained imports/tests if any smoke path breaks.
- Compatibility-boundary risk: keeping live legacy workflow declarations in the compatibility suite would silently preserve the removed constructor surface.
  - Mitigation: split or migrate those tests so only persisted reader fixtures remain legacy, and keep strictness exclusions limited to those exact persisted fixtures.

## Rollback
- If a canonical rename causes unexpected breakage during implementation, rollback by reverting only the local rename in the affected maintained file and re-run targeted tests before proceeding; do not reintroduce broad alias shims or maintained constructor aliases as a shortcut.
