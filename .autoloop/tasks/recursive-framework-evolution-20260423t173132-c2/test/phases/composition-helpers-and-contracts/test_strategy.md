# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c2
- Pair: test
- Phase ID: composition-helpers-and-contracts
- Phase Directory Key: composition-helpers-and-contracts
- Phase Title: Add Composition Authoring Helpers
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- `stdlib` export and authoring-only purity: `tests/unit/test_stdlib_and_extensions.py`
  Checks `stdlib/composition.py` stays free of runtime/workflow imports and that `autoloop_v3.stdlib` exports the helper seam.
- Explicit child invocation wrapper: `tests/unit/test_stdlib_and_extensions.py::test_composition_helpers_delegate_to_ctx_invoke_workflow_and_adopt_child_artifacts`
  Checks `run_child_workflow(...)` forwards workflow/message/parameters unchanged and returns the original `ChildWorkflowResult`.
- Parent-local artifact adoption happy path: `tests/unit/test_stdlib_and_extensions.py::test_composition_helpers_delegate_to_ctx_invoke_workflow_and_adopt_child_artifacts`
  Checks selected child artifacts are copied into `ctx.workflow_folder` with preserved contents.
- Failure paths for adoption inputs: `tests/unit/test_stdlib_and_extensions.py`
  Checks `KeyError` for unknown artifact names, `ValueError` for parent-path escape, and `FileNotFoundError` when a declared child artifact points to a missing backing file.
- Runtime preservation of child-workflow behavior: `tests/runtime/test_workspace_and_context.py::test_composition_helpers_keep_child_invocation_explicit_and_adopt_selected_artifacts_into_parent_workflow_folder`
  Checks child request isolation, unchanged task message behavior, preserved child metadata/parent linkage, and workflow-local adopted artifact copies.
- Authoring-doc contract freeze: `tests/test_architecture_baseline_docs.py`
  Checks docs keep the additive composition-helper boundary and the narrow runtime control contract language.

## Preserved invariants checked

- No new runtime-owned control surface beyond `expected_output_schema`, `available_routes`, and `route_contracts`.
- Existing `ctx.invoke_workflow(...)` semantics remain the runtime source of truth.
- Parent-local artifact adoption is explicit and does not mutate child-run metadata.

## Edge cases and failure paths

- Unknown child artifact name.
- Parent-path escape via `..`.
- Declared child artifact path whose backing file is missing.

## Flake risk and stabilization

- Tests are filesystem-local and provider-scripted only; no network, clock-sensitive ordering, or external CLI behavior is involved.
- Temporary workflow fixtures write deterministic files under `tmp_path` and assert exact paths/content.

## Known gaps

- This phase does not migrate release or incident workflows to the helper seam; composition proof stays limited to the dedicated parent/child fixture.
