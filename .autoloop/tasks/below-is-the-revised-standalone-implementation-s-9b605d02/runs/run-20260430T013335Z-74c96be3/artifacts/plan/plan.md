# Canonical Public-Surface Cleanup Plan

## Scope

Finish the post-pass cleanup so the documented greenfield surface is actually canonical:

- `autoloop.simple` and `autoloop` stay as the only public authoring surface.
- active `core/*`, `runtime/*`, `stdlib/*`, and active test suites stop exposing or depending on legacy names such as `SUCCESS`, `RouteInfo`, `route_infos`, `required_outputs`, `LLMStep`, `PairStep`, and `SystemStep`.
- any remaining compatibility support is explicit, internal, and justified by persisted-run or fixture migration readers only.

Out of scope:

- broad runtime/provider redesign unrelated to legacy-name removal
- changing documented public behavior beyond the intentional legacy removals already requested
- deleting persisted-run migration support that still normalizes old on-disk payloads

## Current Findings

- `autoloop/__init__.py` is already near-canonical, but [autoloop/simple.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/simple.py) still imports and therefore publicly exposes non-canonical helpers including `ResolvedArtifacts`, `ChildWorkflowResult`, `Checkpoint`, and `AfterHookResult`.
- [core/__init__.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/__init__.py) still exports the full legacy low-level authoring contract and still installs the `core` ↔ `autoloop_v3.core` alias shim.
- [core/routes.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/routes.py), [core/steps.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/steps.py), [core/validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/validation.py), and [core/compiler.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/compiler.py) still carry live `RouteInfo` and `SUCCESS` normalization on active compilation paths, not only persisted-run readers.
- [stdlib/steps.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/stdlib/steps.py) still exposes `pair_step(...)` on top of `PairStep`, which keeps removed vocabulary alive in maintained helpers.
- [tests/strictness/test_no_compat.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/strictness/test_no_compat.py) currently scans docs/workflows only and explicitly excludes `core/`, `runtime/`, and `tests/`, which misses the active implementation/test surface the request wants enforced.
- Active non-migration suites still use legacy names, especially [tests/contract/test_engine_contracts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/contract/test_engine_contracts.py), [tests/unit/test_validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_validation.py), [tests/unit/test_simple_surface.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_simple_surface.py), and provider/runtime fixtures. Dedicated compatibility coverage already exists in [tests/runtime/test_compatibility_runtime.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_compatibility_runtime.py).

## Target Interfaces

### Public authoring surface

`autoloop.simple` should expose only the documented canonical authoring API:

- `Workflow`
- `step`, `produce_verify_step`, `python_step`, `workflow_step`
- `llm`, `classify`
- `Json`, `Md`, `Text`, `Raw`
- `Prompt`, `Route`
- `Session`, `Continuity`, `Worklist`
- `Event`, `Outcome`
- `FINISH`, `PAUSE`, `FAIL`, `SELF`

It should not re-export or document:

- `AfterHookResult`
- `Checkpoint`
- `ChildWorkflowResult`
- `ResolvedArtifacts`
- `WorkflowStep`
- any strict `core` step classes or legacy descriptor aliases

### Internal `core` surface

Active top-level `core` imports should be reduced to the strict runtime/kernel pieces that are still current. Legacy compatibility, if still needed, should move behind an explicit internal module such as `core._compat` or `core._migration`, instead of remaining in `core/__init__.py`, `core.routes`, `core.primitives`, or other active imports.

Expected active naming after cleanup:

- terminals: `FINISH`, `PAUSE`, `FAIL`
- route metadata: `Route.summary`, `Route.required_writes`, `Route.handoff`, `Route.on_taken`
- provider-backed step kind: canonical compiled/output vocabulary only (`step`, `produce_verify`, `python`, `workflow`, `operation`)

Legacy-only naming allowed after cleanup:

- persisted-run terminal normalization from historical `"SUCCESS"` payloads
- compatibility readers or quarantined migration fixtures that intentionally exercise old serialized shapes

## Milestones

### Milestone 1: Trim the public/exported surface

- reduce `autoloop.simple` imports and `__all__`-reachable symbols to the canonical surface only
- update or add surface tests so `autoloop.simple` import failures mirror the existing `autoloop` root expectations
- prune `core/__init__.py` exports to the still-supported strict kernel surface
- decide alias-shim fate:
  - remove the dynamic `core` ↔ `autoloop_v3.core` alias if implementation/tests no longer need it
  - otherwise replace it with an explicit compatibility package/module boundary instead of a hidden `sys.modules` bridge

### Milestone 2: Remove live legacy route/runtime contracts from active code

- migrate active route metadata flow from `step.route_infos + RouteInfo.required_outputs` to `Route.required_writes` only
- stop using `SUCCESS` in compiler/validation/static-graph/runtime compilation paths
- narrow `Route.to(...)` so the public helper no longer carries positional effect DSL on the active surface; strict internal effect usage should move to explicit internal-only construction if still needed
- quarantine or replace `LLMStep`, `PairStep`, `SystemStep`, `WorkflowStep`, `Param`, `StateVar`, and `AfterHookResult` from active top-level imports when they are only serving compatibility
- remove or rewrite stdlib helpers that encode `PairStep` or `produces` vocabulary, especially `stdlib/steps.py::pair_step`
- clean static-graph helpers once compiled routes are guaranteed canonical, removing fallback `"SUCCESS"` target rewriting there

### Milestone 3: Migrate active tests and enforce strictness

- move intentional old-contract coverage under clearly named compatibility/migration suites and fixtures only
- migrate active contract/unit/runtime/provider tests to canonical names:
  - `FINISH` instead of `SUCCESS`
  - `required_writes` instead of `required_outputs`
  - simple/public APIs instead of direct legacy step classes where the suite is validating active public behavior
- update strictness scanning to cover maintained implementation and active tests:
  - include `autoloop/`, `core/`, `runtime/`, `stdlib/`, and active `tests/`
  - exclude only explicit compatibility/migration fixtures and legacy docs/templates already treated separately by other tests
- rerun the canonical verification suite plus targeted compatibility tests to confirm the quarantine boundary is correct

## Implementation Notes

### Compatibility seam

- persisted-run/session/checkpoint readers already have a legitimate migration need for terminal normalization; keep that behavior but move it behind an explicit internal compatibility helper instead of leaving `SUCCESS` on active imports
- route metadata compatibility should follow the same rule: only keep old `RouteInfo` or `required_outputs` parsing if a real serialized-reader path still consumes it
- active in-memory authoring/compilation should not accept or propagate `route_infos`, `required_outputs`, or `SUCCESS`

### Alias handling

- current packaging only finds real top-level packages (`core`, `runtime`, `stdlib`, `autoloop`, etc.); this checkout does not contain a maintained `autoloop_v3/core` source tree
- because `autoloop_v3.core` is not a real package here, removing the alias must be sequenced with import-path cleanup or an explicit compatibility package; do not silently break tests or installed-package consumers

### Test quarantine boundary

- keep compatibility coverage separate instead of weakening strictness for the whole tree
- likely quarantine candidates:
  - `tests/runtime/test_compatibility_runtime.py`
  - fixtures currently built solely for compatibility serialized-shape coverage, such as [tests/fixtures/toy_runtime_workflow.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/fixtures/toy_runtime_workflow.py), if they cannot be migrated cleanly

## Validation

- surface tests:
  - canonical import/export assertions for `autoloop` and `autoloop.simple`
  - import-failure assertions for removed symbols
- compiler/runtime tests:
  - canonical topology/static-graph payloads contain `required_writes` and never emit `SUCCESS`, `route_infos`, `route_required_outputs`, or `required_outputs`
  - active runtime/provider contract payloads continue to expose the canonical route/write shape only
- strictness tests:
  - active maintained code/tests fail on banned legacy names outside explicit compatibility fixtures
- compatibility tests:
  - persisted-run migration readers still normalize historical terminal/session payloads as before
- full regression check:
  - canonical contract suite
  - updated unit/runtime/provider suites touched by migration

## Risk Register

- Alias removal risk: hidden dependence on `autoloop_v3.core` imports may break tests or installed usage unless import paths are migrated in the same slice or replaced with an explicit compat module.
- Route metadata risk: removing `RouteInfo` too early can break any remaining serialized-reader or test fixture that still constructs legacy route metadata in memory.
- Strictness risk: broadening the scan before quarantining compatibility fixtures will create noisy failures and obscure real regressions.
- Stdlib risk: deleting `pair_step` without replacing its active consumers can break maintained workflow helpers that still compile through strict `PairStep`.

## Rollback

- keep changes sliced so export trimming, compatibility-module extraction, and test quarantine can be reverted independently
- if canonical runtime tests fail after route/runtime cleanup, temporarily restore only the internal compatibility adapter, not the old public exports
- if alias removal breaks import resolution, restore a minimal explicit compat package/module rather than reintroducing the dynamic `sys.modules` alias
