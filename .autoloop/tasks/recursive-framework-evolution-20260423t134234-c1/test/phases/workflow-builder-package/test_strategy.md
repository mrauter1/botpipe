# Test Strategy

- Task ID: recursive-framework-evolution-20260423t134234-c1
- Pair: test
- Phase ID: workflow-builder-package
- Phase Directory Key: workflow-builder-package
- Phase Title: Ship Workflow Builder
- Scope: phase-local producer artifact

## Behaviors Covered

- Workflow package discovery exposes `workflow_idea_to_workflow_package` by canonical name and alias from the repo workflows namespace.
- Workflow compilation preserves the explicit step order, narrow control contract surfaces, and route grammar expected by the builder package.
- Workflow-specific documentation captures the required decision records, route grammar, control contract, and test evidence references.
- Scripted end-to-end execution writes the expected design/build/evaluation artifacts, generates a discoverable child package, and compiles that generated package successfully.
- Deterministic system-step artifacts now have content assertions: `invocation_contract.json` must preserve authoritative invocation data and `publish_receipt.json` must preserve promotion/rollback publication evidence.
- Workflow parameter coercion rejects invalid generated package names through the exported `Parameters` model and runtime coercion helper.

## Preserved Invariants Checked

- The builder remains artifact-first: bootstrap and publish evidence are durable files, not transient provider prose.
- Provider-facing control data remains explicit and narrow through `expected_output_schema`, `available_routes`, and `route_contracts`.
- The generated package is still compiled through the same discovery and compiler path used by normal workflows.

## Edge Cases And Failure Paths

- Invalid `package_name` values containing hyphens fail parameter coercion with a workflow-parameter error.
- End-to-end assertions verify that authored aliases, requested test command, and selected candidate identity survive into the durable workflow artifacts.

## Flake Control

- All coverage is deterministic via `tmp_path` isolation plus `ScriptedLLMProvider`; there are no network, timing, or nondeterministic ordering dependencies.

## Known Gaps

- The scripted exercise proves package generation, artifact emission, and compilation of the generated workflow, but it does not attempt to semantically validate arbitrary downstream workflows authored by the builder.
- Top-level `run_workflow_package(..., workflow_params=...)` currently does not coerce initial workflow parameters through the package `Parameters` model before execution, so failure-path coverage is anchored to the package parameter-coercion surface instead of the runner entrypoint.

## Validation Run

- `.venv/bin/python -m pytest -q tests/runtime/test_workflow_builder_package.py`
- `.venv/bin/python -m pytest -q tests/runtime/test_workflow_integration_parity.py tests/test_architecture_baseline_docs.py`
- `PYTHONPATH=.. .venv/bin/python -m autoloop_v3.runtime.cli workflows show workflow_idea_to_workflow_package --root .`
