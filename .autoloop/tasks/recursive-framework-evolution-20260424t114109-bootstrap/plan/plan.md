# Flow-First Flexible Workflow Authoring Plan

## Intent contract

- Treat the request snapshot as the implementation contract.
- Keep the root `workflow` shim strict and minimal.
- Keep `workflow.toml` metadata-only and optional for execution.
- Make single-file workflows, `flow.py` packages, and legacy `workflow.py` packages first-class.
- Keep `specs.py`, docs, prompts, assets, tests, `params.py`, and `contracts.py` optional.
- Do not introduce a new workflow DSL or runtime-owned hidden policy.

## Current repo findings

- `core.workflow_catalog` only discovers `<root>/workflows/*/workflow.toml`, requires `workflows/__init__.py`, requires per-package `__init__.py`, and hard-fails if `workflow.py` is absent.
- `core.workflow_capabilities` imports `workflows.<package>.workflow` and validates package re-exports, so deep inspection is package-only.
- `runtime.loader`, `runtime.cli`, `runtime.runner`, and `runtime.workspace` expose package-only terminology and metadata (`WorkflowPackage`, package-only CLI help text, package-root prompt/workspace assumptions).
- `stdlib/portfolio.py`, `stdlib/adaptation.py`, `stdlib/refinement.py`, `stdlib/decomposition.py`, `stdlib/evaluation.py`, `stdlib/company.py`, and `stdlib/diagnostics.py` derive the repo root from `ctx.package_folder.parent.parent`; that only works for `workflows/<pkg>/workflow.py` and breaks for `workflows/foo.py` or arbitrary explicit file refs.
- The request names `docs/architecture.md` and `docs/authoring.md` as the canonical docs, but the repo currently stores equivalent text under `legacy_docs/` while tests, recursive templates, and the workflow builder already reference `docs/`.
- `workflow_idea_to_workflow_package`, its prompts, and its tests still hard-code the package minimum as `workflow.py`, `workflow.toml`, `prompts/`, and `assets/`.
- All shipped repo workflows already set an explicit `name`, so changing the unnamed fallback from raw class name to snake_case is low-risk for production workflows but still requires test updates.

## Target internal interfaces

- Introduce an internal `WorkflowReference` as the canonical origin descriptor shared by discovery, deep inspection, and execution.
- Suggested `WorkflowReference` fields: `original`, `kind`, `workflow_name`, `title`, `description`, `aliases`, `class_name`, `module_name`, `source_path`, `package_dir`, `manifest_path`, `authoring_shape`.
- Generalize `WorkflowCatalogEntry` so shallow discovery can represent manifest and inferred workflows without imports. Stable fields: `workflow_name`, `title`, `description`, `aliases`, `authoring_shape`, `package_dir`, `source_path`. Optional fields: `manifest_path`, `flow_path`, `legacy_workflow_path`, `spec_paths`, `prompt_paths`, `asset_paths`, `doc_paths`, `test_paths`.
- Keep `ResolvedWorkflow` as the runtime-loaded contract, but back it with the new reference/origin model instead of package-only assumptions.
- Extend `core.context.Context` with `root: Path` so stdlib helpers stop inferring the repo root from package layout heuristics.
- Extend `workflow.json`, `run.json`, and child-run metadata with workflow origin details: `reference`, `source_path`, `class_name`, `authoring_shape`, `manifest_path`.
- Update the unnamed workflow fallback so compilation/runtime identity defaults to snake_case class name when `name` is absent.

## Resolution and discovery rules

- Named resolution order: manifest catalog entry, inferred `workflows/<name>/flow.py`, inferred `workflows/<name>/workflow.py`, inferred `workflows/<name>.py`.
- Explicit path resolution accepts `.py` files and workflow directories; file/directory loads use an isolated module namespace and require `:ClassName` when multiple workflow classes exist.
- Module resolution uses normal Python imports rooted at the repo root; `__init__.py` remains required only for true package/module imports.
- Prompt/package resolution uses the executable source container: single-file workflow => file parent; `flow.py`/`workflow.py` package => containing directory.
- If two different origins would map to the same `workflow_name` within one task/workspace, fail clearly instead of silently merging histories.

## Phase 1: Resolver Foundation And Contract Tests

- Add tests for single-file workflows, multi-class ambiguity, path/module/class refs, explicit workflow-directory refs, `flow.py` packages without `workflow.toml`, prompt resolution, parameter resolution order, and strict root shim invariants.
- Introduce isolated import/reference helpers and refactor `runtime.loader.resolve_workflow_reference(...)` to handle names, aliases, file refs, directory refs, module refs, and imported classes through one path.
- Update `runtime.runner`, `runtime.workspace`, `core.context`, and related tests so execution uses the resolved reference/package directory, persists origin metadata, and exposes `ctx.root`.
- Preserve existing package workflows, aliases, `ctx.invoke_workflow(...)`, and package-local prompt resolution.

## Phase 2: Shallow Discovery, Deep Inspection, And Helper Migration

- Refactor `core.workflow_catalog` to scan manifests plus inferred `flow.py`, `workflow.py`, and top-level `*.py` under `workflows/` without importing modules or requiring `workflows/__init__.py`.
- Refactor `core.workflow_capabilities` to deep-inspect via the unified resolver instead of `workflows.<pkg>.workflow` imports, including path-based deep inspection and generalized parameter lookup order.
- Update stdlib helper seams (`portfolio`, `adaptation`, `refinement`, `decomposition`, `evaluation`, `company`, `diagnostics`) to use `ctx.root`, tolerate absent manifest/spec/docs/prompts/assets/tests, and emit authoring-shape-aware payloads.
- Keep manifest validation metadata-only and reject semantic fields such as `steps`, `transitions`, `prompts`, `sessions`, `parameters`, `artifacts`, and `route_contracts`.

## Phase 3: Authoring Helpers, Scaffold, And Builder Migration

- Add focused stdlib helpers in `stdlib/validation.py`, `stdlib/json_artifacts.py`, and `stdlib/contracts.py`; export them from `stdlib/__init__.py`, not the root `workflow` shim.
- Update `autoloop init workflow` to support `--shape single|flow-specs|package`, default `flow-specs`, and keep scaffold output rooted under `<root>/workflows/`.
- Update `workflow_idea_to_workflow_package` artifacts, prompts, checklists, and tests so it can emit `single`, `flow_specs`, and `package` layouts, defaulting to `flow_specs`.
- Ensure scaffold and builder output compile without requiring `workflow.toml`, `prompts/`, `assets/`, `params.py`, or `contracts.py` unless the selected shape needs them.

## Phase 4: Canonical Docs, Recursive Templates, And Regression Sweep

- Create/update canonical `docs/architecture.md`, `docs/authoring.md`, and relevant `docs/workflows/*.md` content to describe single-file, flow/specs, and mature-package authoring without widening `workflow.toml`.
- Update recursive templates and wrapper-facing text to reference the new authoring doctrine and flexible discovery shapes while keeping the package/message-oriented CLI framing.
- Update CLI help text and workflow inspection output to remove package-only language; keep `workflows list` shallow/no-import and retain compatibility-conscious `workflows show` behavior.
- Run targeted suites first, then the full test suite, and fix regressions before closing the slice.

## Compatibility and migration notes

- No change to the root `workflow` shim export surface.
- Existing `workflow.py` + `workflow.toml` packages remain runnable and discoverable.
- `workflow.toml` stays optional for execution and metadata-only when present.
- `specs.py` remains ordinary Python and is never scanned or required by the runtime.
- `workflows list` must surface manifest and inferred workflows without import side effects.
- `workflows show` and execution may import/compile.
- Resume/log/run-history commands continue to key off canonical `workflow_name`; origin metadata provides traceability for path-based runs.
- Canonical docs move to `docs/`; `legacy_docs/` can remain archival unless a later cleanup explicitly removes or syncs it.

## Regression controls

- Add negative tests for manifest semantic-field rejection, multi-class ambiguity, duplicate named candidates, origin/name collisions, missing prompt files, and path-escape protection in JSON helper writers.
- Validate that `ctx.invoke_workflow(...)` and stdlib composition helpers can still invoke existing package workflows and new file-based workflows through the same resolver.
- Keep shallow discovery import-free by testing with sentinel files that would raise on import.
- Verify run metadata, child-run records, and workflow-local snapshot helpers all persist the same canonical `workflow_name` while preserving origin details.
- Confirm new stdlib helpers reduce repeated validation/route boilerplate without adding runtime-owned routing or manifest semantics.

## Risk register

- `workflow_name` collisions from file-based refs can merge task histories if not rejected explicitly.
- Package-layout repo-root heuristics in stdlib helpers will break immediately for single-file workflows if `ctx.root` is not introduced in the same slice as the resolver change.
- Dynamic module caching can cross-contaminate two path-based workflows with the same stem unless isolated import names are hashed by origin.
- Snapshot artifact schema changes can break in-repo workflows that consume helper JSON unless helper producers and consumers move together.
- Tests, templates, and builder prompts currently assume `docs/` exists even though the repo stores live prose under `legacy_docs/`; splitting the contract further would create additional drift.

## Validation / exit criteria

- Single-file, flow/specs, and legacy `workflow.py` workflows all compile and run.
- Shallow discovery lists manifest and inferred workflows without import side effects.
- Deep inspection exposes steps, parameters, routes, prompts, and optional support-file paths for every supported authoring shape.
- `autoloop init workflow` and the builder generate the requested shapes with the correct defaults.
- Docs/templates no longer claim `workflow.py`, `workflow.toml`, `prompts/`, and `assets/` are mandatory minimums.
