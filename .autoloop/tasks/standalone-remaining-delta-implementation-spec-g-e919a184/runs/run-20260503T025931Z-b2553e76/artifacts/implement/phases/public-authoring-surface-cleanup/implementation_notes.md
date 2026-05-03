# Implementation Notes

- Task ID: standalone-remaining-delta-implementation-spec-g-e919a184
- Pair: implement
- Phase ID: public-authoring-surface-cleanup
- Phase Directory Key: public-authoring-surface-cleanup
- Phase Title: Public Authoring Surface Cleanup
- Scope: phase-local producer artifact

## Files Changed
- `cleanup.md`
- `autoloop/runtime/cli.py`
- `tests/runtime/test_package_cli.py`

## Symbols Touched
- `_single_file_workflow_source`
- `_flow_package_source`
- `_write_workflow_package`
- `_paused_workflow_source`
- `test_cli_init_workflow_scaffolds_supported_shapes_and_rejects_duplicates`
- `test_cli_init_workflow_defaults_to_flow_specs_shape`
- `_assert_bootstrap_scaffold_contract`

## Checklist Mapping
- Cleanup doc slice: removed remaining `autoloop.simple` guidance from `cleanup.md` and kept the autoloop-only phrases required by baseline docs tests.
- Scaffold contract slice: updated `single`, `flow-specs`, and `package` starter source to decorator-based `python_step` handlers with `ctx`-only signatures and step-local routes.
- Test slice: extended init-workflow coverage to assert source contract details and compiled route/signature details directly.

## Assumptions
- The finalized starter contract may return `Event("ready")`; the active validator accepts that route carrier for `python_step`.

## Preserved Invariants
- Supported workflow shapes, folder layouts, and init JSON payload fields are unchanged.
- `flow-specs` still scaffolds only `flow.py` and `specs.py`; `package` still adds `__init__.py`, `workflow.toml`, `prompts/`, and `assets/`.

## Intended Behavior Changes
- Generated starter workflows no longer use `_bootstrap(state, ctx)` or `python_step(_bootstrap, ...)`.
- Scaffolded deterministic bootstrap steps now use `@python_step(name="bootstrap", routes={"ready": FINISH})` with `def bootstrap(ctx): ...`.

## Known Non-Changes
- No runtime validator or workflow resolution behavior changed.
- No broader documentation rewrites were made outside `cleanup.md`.

## Expected Side Effects
- New scaffold source matches the active public authoring surface and compiles under the current validator for all supported init shapes.
- Targeted tests now fail if legacy two-argument scaffold patterns reappear in emitted starter files.

## Validation Performed
- `./.venv/bin/pytest -q tests/test_architecture_baseline_docs.py`
- `./.venv/bin/pytest -q tests/runtime/test_package_cli.py -k 'init_workflow_scaffolds_supported_shapes_and_rejects_duplicates or init_workflow_defaults_to_flow_specs_shape'`

## Deduplication / Centralization Decisions
- Reused the same bootstrap source contract across both CLI scaffold emitters and centralized the source-level scaffold assertions in `_assert_bootstrap_scaffold_contract`.
