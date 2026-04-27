# Test Strategy

- Task ID: recursive-framework-evolution-20260427t144615-bootstrap
- Pair: test
- Phase ID: surface-foundations
- Phase Directory Key: surface-foundations
- Phase Title: Additive Surface Foundations
- Scope: phase-local producer artifact

## Behavior Coverage Map

- AC-1 / public `autoloop.simple` surface:
  - `tests/unit/test_simple_surface.py::test_autoloop_simple_imports_in_installed_package_mode`
  - `tests/unit/test_simple_surface.py::test_autoloop_simple_imports_with_repo_root_fallback_only`
  - Confirms importability outside the repo root from an isolated top-level exported layout and from repo-root source fallback.
- AC-1 / strict shim unchanged:
  - `tests/unit/test_simple_surface.py::test_strict_workflow_counterpart_preserves_import_time_validation`
  - `tests/strictness/test_no_compat.py`
  - Confirms `workflow` remains strict and existing strictness guardrails still hold.
- AC-2 / prompt origin metadata:
  - `tests/unit/test_simple_surface.py::test_prompt_inline_and_file_primitives_preserve_origin_metadata`
  - Confirms inline/file origins, path behavior, and resolved prompt text remain deterministic.
- AC-2 / route metadata:
  - `tests/unit/test_simple_surface.py::test_route_primitives_accept_optional_metadata_without_changing_target_or_effects`
  - Confirms additive summaries, required outputs, and handoff metadata do not change existing route targets.
- Simple artifact helper specifications:
  - `tests/unit/test_simple_surface.py::test_simple_workflow_declarations_bind_names_and_infer_step_local_artifact_paths`
  - `tests/unit/test_simple_surface.py::test_simple_artifact_specs_materialize_preserving_schema_requiredness_and_explicit_paths`
  - Confirms descriptor-based name binding, inferred step-local paths, schema/required propagation, and explicit path overrides.
- Non-strict simple workflow declarations:
  - `tests/unit/test_simple_surface.py::test_simple_workflow_base_does_not_trigger_strict_class_definition_validation`
  - Confirms simple declarations do not trigger strict import-time validation.

## Preserved Invariants Checked

- Existing prompt registries and provider/runtime prompt consumers still pass targeted regression slices.
- Existing route/static-graph/validation coverage remains green on the targeted slice.
- Authoring docs explicitly mention the additive simple surface without weakening the strict `workflow` guidance.

## Edge Cases And Failure Paths

- Strict counterpart without `State` still fails at class definition time.
- Installed/export layout probe runs from outside the repo root so cwd does not hide missing top-level exports.
- Explicit artifact paths override inferred step-local defaults.

## Stabilization Notes

- Installed-package compatibility is tested by staging the exported `autoloop` and `core` packages into an isolated site directory rather than invoking `pip`; this avoids flake from missing build-tool availability while still validating the import/export contract.

## Known Gaps

- This phase does not yet test compiler lowering or runtime execution of simple declarations because those behaviors are explicitly deferred.
