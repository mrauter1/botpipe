# Implementation Notes

- Task ID: recursive-framework-evolution-20260422t165825-bootstrap
- Pair: implement
- Phase ID: docs-tests-and-legacy-removal
- Phase Directory Key: docs-tests-and-legacy-removal
- Phase Title: Docs Tests And Legacy Removal
- Scope: phase-local producer artifact

## Files Changed

- `runtime/config.py`
- `runtime/runner.py`
- `runtime/loader.py`
- `runtime/workspace.py`
- `runtime/__init__.py`
- `docs/architecture.md`
- `docs/authoring.md`
- `workflow/__init__.py`
- `workflow/primitives.py`
- `workflows/autoloop_v1/conventions.py`
- `tests/test_architecture_baseline_docs.py`
- `tests/strictness/test_no_compat.py`
- `tests/runtime/test_compatibility_runtime.py`
- `tests/runtime/test_workspace_and_context.py`
- `tests/runtime/test_optional_extensions.py`
- `tests/runtime/test_workflow_integration_parity.py`
- `tests/runtime/test_package_cli.py`
- `tests/contract/test_engine_contracts.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/unit/test_validation.py`
- `decisions.txt`

## Symbols Touched

- `runtime.config.CONFIG_FILENAMES`
- `runtime.config.RuntimeConfig`
- `runtime.config.RuntimeConfigOverride`
- `runtime.runner.RunnerOptions`
- `runtime.runner.run_workflow_package`
- `runtime.loader.discover_workflow_packages`
- `runtime.loader.resolve_workflow_reference`
- `runtime.loader._evict_stale_workflow_modules`
- `runtime.workspace.ensure_workspace`
- `runtime.workspace.create_run`
- `runtime.workspace.resolve_resume_state_root`
- `runtime.__all__`

## Checklist Mapping

- Plan item 6: finished the message-model cleanup by removing runtime `intent_mode` behavior and old message payload fields.
- Plan item 17: rewrote docs around `core`, package-based `autoloop`, task -> workflow -> runs, package prompts/assets, and `ctx.invoke_workflow(...)`.
- Plan item 18: rewrote/extended tests to cover strict shims, package execution, workflow-folder git scope, docs, and absence of legacy public surfaces.
- Plan item 19: enforced absence of raw public runtime loader/runner surfaces through strictness coverage and `runtime.__all__` cleanup.
- Plan item 20: removed leftover compatibility-only config discovery and message-merge behavior that no longer serves the redesign.

## Assumptions

- Package-based CLI and package/class workflow resolution from prior phases remain authoritative; this phase should not reintroduce raw public runtime targeting.
- Internal helper names may still mention `request.md` where they describe the immutable request snapshot artifact rather than the old public input contract.

## Preserved Invariants

- Root `workflow` and `workflow.primitives` remain the strict authoring surface.
- Workflow discovery remains manifest-based under repo-root `workflows/`.
- Workspace layout stays `tasks/<task>/wf_<workflow>/runs/<run>`.
- Child workflow execution, Autoloop-v1 parity, workflow-scoped git tracking, and run-local tracing remain intact.

## Intended Behavior Changes

- Runtime config no longer discovers `superloop.*` files or accepts `runtime.intent_mode`.
- Task message persistence stores only timestamped messages; task `request.md` is always the latest snapshot instead of supporting append/preserve merge modes.
- Raw loader/runner helpers are no longer re-exported from `runtime`; live tests now exercise generated workflows through discovered packages.
- Explicit workflow `root` resolution now remains authoritative across multiple repositories in the same Python process; stale `workflows.*` modules from another root are evicted centrally in the loader.

## Known Non-Changes

- Raw loader internals were not rewritten into a new abstraction; only the public re-exports and raw-target test usage were removed.
- `request.md` remains the canonical rendered snapshot artifact name at task and run scope.

## Expected Side Effects

- Tests that create temporary workflow packages must clear cached `workflows.*` modules between roots to avoid import leakage.
- Repositories that still place only `superloop.yaml`/`superloop.config` in the root will no longer have those files discovered.

## Deduplication / Centralization

- Optional-extension tests now use the same package-based execution model as the other runtime tests instead of maintaining a separate raw-file path.
- Strictness coverage for removed runtime exports lives in `tests/strictness/test_no_compat.py` so legacy public-surface checks stay centralized.
- Cross-root workflow cache invalidation is centralized in `runtime.loader` instead of scattered `sys.modules` clearing in callers.

## Validation Performed

- `./.venv/bin/python -m compileall runtime tests workflow workflows docs`
- `./.venv/bin/pytest tests/runtime/test_compatibility_runtime.py tests/runtime/test_workspace_and_context.py tests/runtime/test_optional_extensions.py tests/runtime/test_package_cli.py tests/runtime/test_workflow_integration_parity.py tests/strictness/test_no_compat.py tests/test_architecture_baseline_docs.py tests/unit/test_primitives_and_stores.py tests/unit/test_stdlib_and_extensions.py tests/unit/test_validation.py tests/contract/test_engine_contracts.py`

## Open Follow-Up

- None within phase scope.
