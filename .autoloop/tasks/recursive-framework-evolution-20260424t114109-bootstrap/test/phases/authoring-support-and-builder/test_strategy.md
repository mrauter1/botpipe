# Test Strategy

- Task ID: recursive-framework-evolution-20260424t114109-bootstrap
- Pair: test
- Phase ID: authoring-support-and-builder
- Phase Directory Key: authoring-support-and-builder
- Phase Title: Authoring Support And Builder
- Scope: phase-local producer artifact

## Behavior Coverage Map

- AC-1 stdlib-only helper surface:
  Covered in `tests/unit/test_stdlib_and_extensions.py`.
  Checks stdlib export surface, pure-authoring module boundaries, validation helper happy path, JSON parse failure, non-object JSON failure reporting, typed JSON artifact wrapper behavior, and explicit route-contract bundles.

- AC-2 `autoloop init workflow` shape support:
  Covered in `tests/runtime/test_package_cli.py`.
  Checks `single`, `flow-specs`, and `package` scaffold outputs compile, duplicate initialization is rejected, default shape is `flow-specs`, package shape creates optional prompts/assets, and non-package shapes do not create package-only clutter.

- AC-3 builder emits flow-first outputs without forced package clutter:
  Covered in `tests/runtime/test_workflow_builder_package.py`.
  Checks builder parameter validation, CLI-style `flow-specs` normalization to internal `flow_specs`, generated layout metadata, compilable outputs for `single`, `flow_specs`, and `package`, and absence of `__init__.py` / `workflow.toml` / `prompts` / `assets` for the non-package builder shapes.

- AC-4 scaffold and builder tests compile generated workflows:
  Covered in `tests/runtime/test_package_cli.py` and `tests/runtime/test_workflow_builder_package.py`.
  Checks compile-time resolution for scaffolded workflows and builder-generated workflows after file creation.

## Edge Cases And Failure Paths

- Validation helpers:
  Invalid JSON and valid-but-wrong-shape JSON both produce readable failure reports instead of silent success.

- Scaffold behavior:
  Re-running `autoloop init workflow` for the same target returns a usage error instead of overwriting files.

- Builder parameter seam:
  Invalid package names are rejected, and hyphenated CLI spelling for `flow-specs` is normalized deterministically for runtime use.

## Preserved Invariants Checked

- Root `workflow` shim is not widened by the new stdlib helpers.
- Non-package shapes remain runnable without mandatory manifest, prompts, assets, or package `__init__.py`.
- Package shape still emits the mature optional support surface.

## Validation Run

- `PYTHONPATH=/home/rauter/autoloop_v3_bkp .venv/bin/pytest -q tests/runtime/test_package_cli.py tests/runtime/test_workflow_builder_package.py`
  Result: `26 passed in 1.17s`

## Known Gaps

- This phase does not broaden into the out-of-scope recursive template/docs baseline drift already noted elsewhere.
- The full mixed unit+runtime suite was already covered in implementation review; this test turn focused on the changed runtime acceptance surfaces and their regressions.
