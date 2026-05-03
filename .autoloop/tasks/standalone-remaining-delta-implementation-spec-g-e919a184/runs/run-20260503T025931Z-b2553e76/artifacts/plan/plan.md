# Public Authoring Surface Cleanup Plan

## Milestone 1: Remaining Cleanup Slice
Scope:
- Update `cleanup.md` so it documents only the greenfield `autoloop` public authoring surface and the final explicit-hook / `python_step` model.
- Fix `autoloop/runtime/cli.py` starter scaffolds for `single`, `flow-specs`, and `package` so generated workflows satisfy the current `python_step` validator contract.
- Extend `tests/runtime/test_package_cli.py` so scaffold coverage validates the final starter contract directly, then rerun the requested focused pytest targets.

Primary files:
- `cleanup.md`
- `autoloop/runtime/cli.py`
- `tests/runtime/test_package_cli.py`

## Interface And Invariants
- `cleanup.md` must keep the active public surface wording aligned with `docs/authoring.md` and `tests/test_architecture_baseline_docs.py`: mention the greenfield `autoloop` surface, `import from \`autoloop\``, `Event` / `Outcome` from `autoloop`, and `contracts.py` discoverability, while removing all `autoloop.simple` guidance.
- All scaffold shapes must keep their current filesystem layouts and CLI JSON response fields; only the emitted workflow source contract changes.
- Generated starter workflows must use the finalized `python_step` authoring form: a one-argument handler (`ctx` only), state mutation through `ctx.state`, and declared step-local routes on `python_step(...)`. Do not keep `_bootstrap(state, ctx)` helpers or `python_step(_bootstrap, ...)` scaffolds.
- The scaffold must compile through `resolve_workflow_reference(...)` and `compile_workflow(...)` under current validation rules for all supported shapes.

## Test And Validation Plan
- Keep the existing scaffold file-creation assertions for each shape.
- Add direct contract assertions in `tests/runtime/test_package_cli.py` against the generated source and/or compiled workflow so the test proves the final handler shape, route declaration, and absence of the legacy two-argument scaffold pattern.
- Re-run:
  - `./.venv/bin/pytest -q tests/test_architecture_baseline_docs.py`
  - `./.venv/bin/pytest -q tests/runtime/test_package_cli.py -k 'init_workflow_scaffolds_supported_shapes_and_rejects_duplicates or init_workflow_defaults_to_flow_specs_shape'`

## Compatibility, Risks, Rollback
- Compatibility: this slice intentionally tightens only generated starter code and working-tree guidance; it does not change supported workflow shapes, init payload shape, or runtime semantics beyond matching the already-finalized validator contract.
- Regression risk: `cleanup.md` can fail baseline-doc assertions if required autoloop-only phrases are dropped while removing `autoloop.simple`.
- Regression risk: scaffold changes can accidentally break only one shape if source generation paths diverge between `single` and package-backed scaffolds.
- Rollback: revert the scaffold-source change and matching test expectations together if any supported shape stops compiling; do not leave mixed legacy/final scaffold patterns in the generator or tests.
