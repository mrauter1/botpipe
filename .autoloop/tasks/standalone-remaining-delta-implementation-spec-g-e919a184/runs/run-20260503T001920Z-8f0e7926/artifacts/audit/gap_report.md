# Intent Gap Report

## Original intent considered

- The immutable request requires the final public authoring model: single-argument `hook(ctx)`, explicit runtime controls, no legacy public hook/class-handler compatibility, no removed public documentation surfaces, and final `python_step`/`writes` vocabulary.
- The authoritative run artifacts split that work across four phases and explicitly included public docs/examples cleanup in the final phase.
- This audit considered the request snapshot, `raw_phase_log.md`, `decisions.txt`, phase plan artifacts, implement/test artifacts, the current codebase, and targeted live test results.

## Clarifications / superseding decisions

- No later clarification reintroduced legacy public authoring forms.
- `decisions.txt` records that public `Context` is author-safe only, legacy class handlers are intentionally rejected, and docs should describe the final explicit hook / `python_step` surface only.
- The test-phase artifacts explicitly treat `cleanup.md` as part of the active docs contract, so stale public-surface guidance there is in scope rather than optional cleanup.

## Implemented behavior

- The runtime/compiler public surface was substantially aligned with the request: legacy class-level handlers were removed, public `Context` mutators were hidden, `HookExecutionResult` / `StepExecutionResult` / related dataclasses replaced active tuple plumbing, `ProviderContractBuilder` was introduced, status classification was centralized, resume mismatch now warns by default, and extension failure policy is explicit.
- The final docs/tests phase strengthened regression coverage for the final public surface, including `tests/test_architecture_baseline_docs.py` and updated workflow-doc/package-fixture checks.
- The phase artifacts show the scoped implementation/test slices were otherwise accepted after re-review.

## Unresolved gaps

### 1. `cleanup.md` still documents the removed `autoloop.simple` public surface

- Current file contents still say the greenfield surface is ``autoloop.simple`` and `autoloop`, and instruct authors to import from either one.
- That conflicts with the request’s documentation section and the run’s final-phase acceptance criteria, which require author-facing docs/examples to use only `autoloop`.
- Live evidence: `./.venv/bin/pytest -q tests/test_architecture_baseline_docs.py` currently fails:
  - `test_active_working_tree_note_points_to_greenfield_authoring_surface`
  - `test_public_docs_do_not_reintroduce_removed_surface_or_system_step_terms`
- The run’s own test artifacts already documented this as a remaining implementation gap.

### 2. `autoloop init workflow` still scaffolds legacy two-argument `python_step` handlers

- `autoloop/runtime/cli.py:527-529` and `autoloop/runtime/cli.py:558-560` still generate `def _bootstrap(state, ctx):`.
- The current validator requires one-argument `python_step` handlers, so the generated starter workflows do not compile under the current runtime.
- Live evidence: `./.venv/bin/pytest -q tests/runtime/test_package_cli.py -k 'init_workflow_scaffolds_supported_shapes_and_rejects_duplicates or init_workflow_defaults_to_flow_specs_shape'` fails 3 scaffold cases with `WorkflowValidationError: "python_step 'bootstrap' handler" must accept 1 positional arguments`.
- This is material because `autoloop init workflow` is a public authoring entrypoint; the generated source currently contradicts the finalized contract and breaks immediately under `compile_workflow(...)`.

## Differences justified by later clarification or analysis

- The always-available built-in scoped `ctx.item_state` model was an explicit recorded decision, not a silent behavior change.
- Resume mismatch behavior changing to warn-and-continue by default was explicitly planned, implemented, and tested.
- The expanded docs-baseline checks against `cleanup.md` were justified in the test artifacts as part of the existing active-docs contract, not test-side scope creep.

## Recommended next run

- Update `cleanup.md` so it documents only the `autoloop` public authoring surface and final `python_step` vocabulary.
- Fix `autoloop/runtime/cli.py` scaffold generation for `single`, `flow-specs`, and `package` shapes so generated `python_step` handlers use the final one-argument `ctx` contract and valid state mutation through `ctx`.
- Tighten `tests/runtime/test_package_cli.py` to assert the final scaffold source contract directly and rerun the scaffold-focused package CLI tests plus `tests/test_architecture_baseline_docs.py`.
