# Implementation Notes

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: implement
- Phase ID: namespace-cut-optimizer-boundary-prompts-and-extensions
- Phase Directory Key: namespace-cut-optimizer-boundary-prompts-and-extensions
- Phase Title: Namespace Cut Optimizer Boundary Prompts And Extensions
- Scope: phase-local producer artifact

## Files Changed

- Namespace move: `autoloop/core/**`, `autoloop/runtime/**`, `autoloop/stdlib/**`, `autoloop/extensions/**`; removed top-level `core/`, `runtime/`, `stdlib/`, `extensions/`, and `autoloop_v3/`.
- Runtime seam: `autoloop/runtime/runner.py`, `autoloop/runtime/__init__.py`, new `autoloop/runtime/inspection.py`.
- Extension cleanup: `autoloop/extensions/__init__.py`, `autoloop/extensions/git/__init__.py`; deleted `autoloop/extensions/tracing.py`, `autoloop/extensions/git/declaration.py`.
- Optimizer imports/boundary: `autoloop_optimizer/_selected_workflow.py`, `adaptation.py`, `candidate_surfaces.py`, `company.py`, `decomposition.py`, `diagnostics.py`, `evaluation.py`, `optimization.py`, `portfolio.py`, `refinement.py`.
- Packaging/docs/tests: `pyproject.toml`, `docs/authoring.md`, `docs/architecture.md`, `docs/workflows/investigation_request_to_evidence_pack.md`, `tests/strictness/test_no_compat.py`, `tests/runtime/test_optional_extensions.py`, `tests/unit/test_optimization_helpers.py`, `tests/unit/test_primitives_and_stores.py`, `tests/fixtures/toy_runtime_workflow.py`; deleted `tests/runtime/test_compatibility_runtime.py`.

## Symbols Touched

- `prepare_runtime_services`, `_prompt_registry_roots`, `validate_resume_state`, `_runtime_compiled_workflow`
- `HistoryReader`, `list_runs`, `load_run_record`, `load_run_topology`, `load_run_history`, `load_run_metadata`
- `write_selected_workflow_source_manifest`, `validate_observability_bundle`
- `SessionPaths`, `GitChange`, `GitCommitPlan`, `GitDelta`, `GitPolicy`

## Checklist Mapping

- Phase 6 package cleanup: completed via the `autoloop/` namespace move, import sweep, package discovery change, and `autoloop_v3` removal.
- Optimizer boundary: completed via `autoloop.runtime.inspection` and optimizer import migration onto stable read-only seams.
- Prompt registry expansion: completed via prompt-root seeding from workflow root, compiled prompt-relative roots, and capability prompt paths.
- Workflow-facing git/tracing cleanup: completed via declaration deletion, export removal, runtime runner cleanup, and docs/tests updates.

## Assumptions

- The existing repository dirty state outside this phase scope is intentional and was left untouched.
- Runtime git tracking and tracing remain runtime config surfaces; only workflow declarations were removed.
- Source-manifest generation only needs stable package files, not compiled capability payloads.

## Preserved Invariants

- Runtime-owned git tracking and tracing files stay under the existing runtime observability pipeline.
- Optimizer observability readers still validate schema ids and still tolerate schema-less legacy payloads.
- Workflow/session path handling still uses the existing `SessionPaths` declaration surface.

## Intended Behavior Changes

- Canonical imports are now `autoloop.*`; top-level internal packages and `autoloop_v3` are intentionally unsupported.
- Workflow-authored `GitTracking` and `Tracing` declarations are gone; runtime config is the only supported observability control surface.
- Prompt registry lookup now includes capability-derived prompt roots beyond the immediate workflow package directory.

## Known Non-Changes

- Core runtime-control/on-route internals from earlier phases were not refactored further here.
- Runtime git tracking implementation details remain in place; only the workflow-facing declaration layer was removed.
- Full engine collaborator extraction remains deferred to the maintainability phase.

## Expected Side Effects

- Large mechanical import churn across workflows/tests because the package root moved.
- Strictness now fails fast on `core`, `runtime`, `stdlib`, `extensions`, and `autoloop_v3` imports.
- Source-manifest generation no longer compiles the selected workflow when catalog metadata is sufficient.

## Validation Performed

- `.venv/bin/pytest tests/strictness/test_no_compat.py tests/runtime/test_optional_extensions.py tests/unit/test_optimization_helpers.py tests/unit/test_primitives_and_stores.py::test_prompt_registry_roots_include_capability_prompt_dirs_outside_workflow_parent -q`

## Dedup / Centralization Decisions

- Centralized optimizer read-only access in `autoloop.runtime.inspection` instead of keeping separate direct imports from loader/workspace/core capability internals.
- Centralized prompt-root widening in `_prompt_registry_roots` so runtime services do not rebuild ad-hoc prompt registries in multiple call sites.
