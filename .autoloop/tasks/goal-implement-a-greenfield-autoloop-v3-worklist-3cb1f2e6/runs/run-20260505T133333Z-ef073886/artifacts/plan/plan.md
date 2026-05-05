# Plan

## Goal
Restore full-suite compatibility after repo-local `workflows/` discovery/import support landed, while preserving the accepted greenfield worklist behavior and the currently green focused suites.

## Current Failure Picture
- `autoloop/core/workflow_catalog.py`, `autoloop/runtime/loader.py`, and `autoloop/core/workflow_capabilities.py` now let repo-local `workflows/` win enough resolution paths that older contracts break in two ways:
  - repo-local flow/workflow packages are treated like package-module imports and now require `__init__.py` re-exports that older path/class contracts never required,
  - lower-precedence `.autoloop/workflows/` aliases disappear entirely when a higher-precedence repo-local package shadows the canonical workflow name.
- Explicit repo-local file/class references no longer preserve isolated `_autoloop_workspace_workflows...` module loading and parameter-model lookup parity.
- `autoloop_optimizer/optimization.py` currently validates run observability bundles too strictly for the supported test/runtime contract:
  - schemaless legacy payloads are rejected instead of migrated,
  - valid Plan-1 bundles are excluded before route filtering, which collapses eligible-run counts to zero and cascades into optimizer no-op failures.
- Optimizer and packaged-workflow publication helpers still bind selected-workflow source manifests and boundary checks to the discovery root that won at runtime, even when broader repository contracts still expect canonical package-style paths such as `autoloop/workflows/...`.
- Packaged workflow regressions cluster into shared contracts:
  - route-constant drift where frame/package steps no longer declare authored `blocked` / `failed` routes expected by prompt packages and compile tests,
  - framework artifact path assumptions hard-coded to installed-package depth (`autoloop/workflows/...`) rather than source-root-agnostic workflow package locations,
  - decomposition/refinement/publication validators still hard-code old package-root strings instead of consuming one canonical selected-workflow/package-surface contract.

## Implementation Plan
### 1. Restore the workflow reference-resolution contract
Target modules:
- `autoloop/core/workflow_catalog.py`
- `autoloop/runtime/loader.py`
- `autoloop/core/workflow_capabilities.py`

Implementation intent:
- Keep repo-local `workflows/` support, but split named catalog precedence from explicit file/class loading behavior.
- Change shadowing to preserve non-conflicting lower-precedence resolution keys so `.autoloop/workflows/` manifest aliases remain resolvable even when repo-local packages win the canonical workflow name.
- Keep named canonical-name resolution precedence as repo-local `workflows/` -> `.autoloop/workflows/` -> installed `autoloop/workflows`.
- Make explicit repo-local path references and explicit class references load through the isolated workspace namespace when that was the prior contract, including Params/spec relative-import parity.
- Limit package-export validation (`__init__.py` re-export plus `__all__`) to intentional package-module imports, not every repo-local flow/workflow package reached through named/path resolution.
- Preserve source metadata (`source_path`, `source_root`, `source_root_kind`, `package_dir`, module namespace) so runtime state and downstream helpers can distinguish canonical name resolution from explicit isolated loads.

### 2. Reconcile optimizer observability and selected-workflow source contracts
Target modules:
- `autoloop_optimizer/optimization.py`
- any small shared helper touched by selected-workflow source canonicalization

Implementation intent:
- Make observability readers follow the runtime migration pattern already used elsewhere: accept schemaless `run.json`, `trace.jsonl`, `git_tracking.jsonl`, and `static_step_graph.json` by migration, but keep explicit unsupported schema IDs as hard failures.
- Keep run eligibility independent from route-filter matches; filter published step observations, not the candidate run set itself.
- Preserve direct `runtime_control:*` and authored route tags distinctly inside normalized observations so optimizer ranking/reporting does not conflate `question`, `blocked`, `failed`, and `awaiting_input`.
- Introduce one canonical selected-workflow source-surface contract for optimizer manifests and mutation checks:
  - canonical workflow identity comes from the resolved manifest/package contract,
  - stored package-root/path strings must stay compatible with the established packaged-workflow publication boundary where tests still require `autoloop/workflows/...`,
  - repo-local `workflows/` support must remain functional for actual source loading and inspection.
- Reuse that canonical contract in source-manifest generation, mutation validation, and optimizer packet publication so downstream suites do not each invent their own path normalization rules.

### 3. Converge packaged-workflow compile/runtime contracts and prove the full suite
Target modules:
- packaged workflow contracts/workflows under `autoloop/workflows/*`
- shared packaged-workflow helper seams touched by framework artifact path resolution and publication-boundary validation

Implementation intent:
- Update only the workflow packages whose compile/runtime contracts are actually broken, starting with:
  - `candidate_workflow_to_adapted_execution_plan`
  - `workflow_run_traces_to_optimization_candidates`
  - `workflow_package_to_composable_building_blocks`
  - any additional listed packaged workflows that fail for the same shared route/artifact contract
- Restore authored `blocked` / `failed` route declarations where prompt/readme contracts and compile tests already require them; do not add new runtime-control shims.
- Replace installed-package-depth assumptions for `framework_architecture_doc`, `framework_authoring_doc`, and `workflow_instructions` with a shared source-root-agnostic path strategy so copied repo-local workflow packages can resolve the same framework artifacts.
- Repoint decomposition/refinement/package validators to the canonical selected-workflow/package-surface contract from Phase 2 instead of hard-coded `autoloop/workflows/...` strings scattered across workflow-local checks.
- Keep changes local to shared seams first; only patch individual workflow packages where failures prove their route contracts or required-artifact declarations are genuinely stale.

## Interfaces And Invariants
- Preserve accepted worklist behavior:
  - selector modes remain `all`, `single`, `up_to`, `from_to`,
  - progress-board shape remains strict `items/id/title/status`,
  - no legacy selector aliases or board-shape shims are reintroduced.
- Workflow resolution invariants:
  - canonical-name precedence still prefers repo-local `workflows/`,
  - lower-precedence aliases remain discoverable when they do not conflict directly with a higher-precedence key,
  - explicit repo-local file/class references preserve isolated workspace namespace behavior.
- Optimizer invariants:
  - supported schemaless observability payloads are migrated on read,
  - explicit unsupported schema IDs still fail validation,
  - selected-workflow source manifests compare canonical workflow/package surfaces rather than incidental discovery-root winners.
- Packaged workflow invariants:
  - authored `blocked` / `failed` remain ordinary application routes,
  - framework artifact reads must succeed for both installed-package and repo-local copied workflow packages,
  - publication/boundary validators consume one canonical package-surface rule.

## Compatibility / Behavior
- No rework of the new greenfield worklist API is planned unless a failing broader suite proves a real regression in it.
- Repo-local `workflows/` support stays in place; this work narrows where that support is allowed to change legacy resolution, manifest, and publication contracts.
- For packaged workflows, canonical stored/publication paths should remain compatible with the existing repository contract even when execution used repo-local copied sources.

## Validation
- Keep the currently green focused and adjacent suites green.
- Run and green:
  - `tests/runtime/test_workflow_reference_resolution.py`
  - `tests/unit/test_optimization_helpers.py`
  - the listed packaged-workflow/runtime suites currently failing from shared route/artifact/path-contract drift
- Finish with `.venv/bin/python -m pytest`.

## Risk Register
- Key-level shadowing changes can drift catalog listing behavior from runtime resolution.
  Mitigation: keep one shared resolution-key model and validate named, alias, path, and explicit class references together.
- Canonical package-path normalization can regress genuine repo-local workflow authoring if package identity and on-disk source location are conflated.
  Mitigation: separate canonical stored/publication identity from actual source-loading location.
- Relaxing observability readers too far could hide corrupt runtime bundles.
  Mitigation: migrate only schemaless payloads; keep explicit bad schema IDs and malformed JSON as hard failures.
- Shared artifact-path fixes across packaged workflows can introduce broad regressions if every package hard-codes its own relative depth.
  Mitigation: centralize the framework-artifact path strategy, then touch workflow-local declarations only where tests still prove drift.

## Rollback
- Revert Phase 1 catalog/loader changes together if named resolution, alias visibility, or explicit isolated loading diverge.
- Revert optimizer source-manifest canonicalization and observability-reader changes together if publication checks or mutation detection drift.
- Revert packaged-workflow route/path fixes with their corresponding shared helper changes; do not keep mixed path semantics across workflow packages.
