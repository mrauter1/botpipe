# Implementation Notes

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: implement
- Phase ID: public-surface-docs-regression
- Phase Directory Key: public-surface-docs-regression
- Phase Title: Public Surface, Docs, And Regression
- Scope: phase-local producer artifact

## Files Changed

- `workflow/primitives.py`
- `docs/authoring.md`
- `docs/architecture.md`
- `core/context.py`
- `core/artifacts.py`
- `core/engine.py`
- `tests/strictness/test_no_compat.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/test_architecture_baseline_docs.py`

## Symbols Touched

- `workflow.primitives.__all__`
- `Context.invoke_workflow(...)`
- `validate_artifact_handle(...)`
- `_resolve_placeholder(...)`
- `Engine._build_workflow_output(...)`

## Checklist Mapping

- Public shim/runtime split: confirmed root `workflow` stays authoring-only and `workflow.primitives` documents the low-level runtime surface, including `ChildWorkflowResult`.
- Docs: updated `docs/authoring.md` and `docs/architecture.md` for continuity, scoped session overrides, typed params, artifact contracts, typed routes/effects, worklists, and typed child outputs.
- Strictness/regression: updated public-surface/doc assertions and aligned stale recursive-memory assertions with the maintained ledger layout.
- Full regression: ran `.venv/bin/pytest -q` successfully.

## Assumptions

- `workflow.primitives` is the intended public home for `ChildWorkflowResult`, while `core.primitives` remains narrower.
- Existing workflow-owned child invokers that only accept `workflow`, `message`, and `parameters` remain valid unless typed child input is actually supplied.
- Existing workflows may continue to use plain `Artifact(...)` declarations for directory outputs without rewriting them to `Artifact.raw(...)`.

## Preserved Invariants

- `workflow.toml` remains metadata-only.
- `ctx.open_session(..., scope=...)` keyword and positional usage remain supported.
- Dict transition shorthand remains valid beside typed `Route` objects.
- Existing child composition helpers keep working without requiring invoker callback rewrites.

## Intended Behavior Changes

- Docs now describe the final additive compatibility model instead of the earlier greenfield framing.
- Typed child workflow output validation is strict, so invalid typed outputs are recorded instead of being coerced into valid models.

## Known Non-Changes

- Root `workflow` exports were already in the intended shape; this phase did not widen them beyond the requested authoring surface.
- Recursive memory/template content was not broadly rewritten; only stale tests were aligned to the maintained ledger structure.

## Expected Side Effects

- Directory-backed produced artifacts now validate by existence when they have no schema, which preserves older workflow package patterns during route-contract enforcement.
- Legacy workflow invokers keep working for composition helpers and workflow-local tests while still rejecting dropped typed input.

## Validation Performed

- `.venv/bin/pytest -q tests/strictness/test_no_compat.py tests/unit/test_primitives_and_stores.py tests/test_architecture_baseline_docs.py`
- `.venv/bin/pytest -q tests/unit/test_primitives_and_stores.py tests/unit/test_stdlib_and_extensions.py::test_composition_helpers_delegate_to_ctx_invoke_workflow_and_adopt_child_artifacts tests/runtime/test_security_finding_to_verified_remediation.py::test_security_remediation_compose_step_blocks_not_ready_child_and_keeps_deployment_constraints_local tests/runtime/test_workspace_and_context.py::test_context_invoke_workflow_records_typed_child_output_validation_failures tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py::test_workflow_and_eval_to_refined_workflow_package_runs_and_publishes_candidate_refinement_artifacts tests/runtime/test_workflow_package_to_composable_building_blocks.py::test_workflow_package_to_composable_building_blocks_runs_and_publishes_candidate_decomposition_artifacts tests/runtime/test_workflow_integration_parity.py::test_autoloop_v1_runs_through_general_runtime_and_preserves_package_local_sidecars`
- `.venv/bin/pytest -q`

## Deduplication / Centralization Decisions

- Kept backward-compatibility logic for legacy child invokers centralized in `Context.invoke_workflow(...)` rather than duplicating it in stdlib composition helpers.
- Kept directory-output compatibility in shared artifact validation so workflow packages do not need local special cases.
