# Follow-up implementation request

Complete the remaining public-authoring-surface cleanup left by the previous run.

- Update `cleanup.md` so it documents only the `autoloop` public authoring surface. Remove the remaining `autoloop.simple` guidance and keep the wording aligned with the final `python_step` / explicit-hook model already documented elsewhere.
- Fix `autoloop/runtime/cli.py` workflow scaffolds for all supported shapes (`single`, `flow-specs`, and `package`) so generated starter workflows use the finalized `python_step` handler contract and compile under the current validator.
- Update or extend `tests/runtime/test_package_cli.py` so the scaffolded source is checked against the final contract directly, not just for file creation.
- Re-run at least:
  - `./.venv/bin/pytest -q tests/test_architecture_baseline_docs.py`
  - `./.venv/bin/pytest -q tests/runtime/test_package_cli.py -k 'init_workflow_scaffolds_supported_shapes_and_rejects_duplicates or init_workflow_defaults_to_flow_specs_shape'`
