# Test Strategy

- Task ID: standalone-remaining-delta-implementation-spec-g-e919a184
- Pair: test
- Phase ID: public-authoring-surface-cleanup
- Phase Directory Key: public-authoring-surface-cleanup
- Phase Title: Public Authoring Surface Cleanup
- Scope: phase-local producer artifact

## Behavior To Coverage Map
- AC-1 `cleanup.md` autoloop-only wording: covered by `tests/test_architecture_baseline_docs.py`, especially the required-phrase checks and the global forbidden-token scan for `autoloop.simple`.
- AC-2 scaffold source contract for `single`, `flow-specs`, and `package`: covered by `test_cli_init_workflow_scaffolds_supported_shapes_and_rejects_duplicates`, which asserts emitted source contains the finalized decorator-based `python_step` form and excludes `_bootstrap(state, ctx)` / `python_step(_bootstrap, ...)`.
- AC-2 compiled contract for generated workflows: covered by `_assert_compiled_bootstrap_contract(...)` in the same shape-parametrized test and in `test_cli_init_workflow_defaults_to_flow_specs_shape`, asserting entry step, available routes, route target, and one-argument handler signature.
- AC-3 file creation and default-shape behavior: covered by the existing scaffold file-presence assertions, duplicate rejection assertions, and the default `flow-specs` shape test.

## Preserved Invariants Checked
- Supported scaffold shapes and filesystem layouts remain unchanged.
- `package` still includes `prompts/` and `assets/`; `flow-specs` still omits package extras; `single` still emits a top-level module.
- Generated workflows still resolve and compile through `resolve_workflow_reference(...)` and `compile_workflow(...)`.

## Edge Cases
- Duplicate scaffold creation remains rejected after successful creation for each supported shape.
- Default-shape initialization now proves both emitted source and compiled bootstrap contract, not just file creation.

## Failure Paths
- Source-contract checks fail if legacy two-argument handler patterns or wrapper-style `python_step(_bootstrap, ...)` reappear.
- Compiled-contract checks fail if the default/bootstrap route target or the handler signature drifts from the finalized validator contract.

## Flake Risk / Stabilization
- Tests are filesystem-local and deterministic; they use `tmp_path` plus module-cache eviction to avoid cross-test import leakage.
- No timing, network, or nondeterministic ordering dependencies are introduced.

## Known Gaps
- The focused coverage does not exhaustively compile every scaffold via live CLI subprocesses beyond the existing in-process `cli.main(...)` path, which is acceptable because the request only targets authoring-surface and init-scaffold contract regressions.
