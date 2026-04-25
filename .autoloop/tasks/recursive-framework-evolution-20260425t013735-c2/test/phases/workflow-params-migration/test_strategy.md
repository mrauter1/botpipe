# Test Strategy

- Task ID: recursive-framework-evolution-20260425t013735-c2
- Pair: test
- Phase ID: workflow-params-migration
- Phase Directory Key: workflow-params-migration
- Phase Title: Workflow Params Migration
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Shared parameter bundle normalization and stdlib export surface
  - Coverage: `tests/unit/test_stdlib_and_extensions.py::test_parameter_model_bundles_preserve_shared_task_and_selected_workflow_normalization`
  - Behaviors: task-framing, selected-workflow-framing, evidence-expectation, and portfolio-review bundles normalize trimmed text, dedupe repeatable strings, preserve positive-int composition, and stay re-exported through `stdlib`.

- Inherited validator preservation for workflow-local subclasses
  - Coverage: `tests/unit/test_stdlib_and_extensions.py::test_workflow_specific_parameter_models_keep_inherited_selected_workflow_validation`
  - Behaviors: refinement and decomposition subclasses keep inherited `selected_workflow` / `task_title` non-empty validation while preserving local field normalization for `failure_modes_path`, `evidence_paths`, and `target_test_command`.

- Front-door and candidate-retrieval workflow parameter acceptance
  - Coverage: `tests/runtime/test_task_to_candidate_workflow_set.py`, `tests/runtime/test_task_to_workflow_strategy.py`
  - Behaviors: shared task-framing-with-evidence parameters remain accepted through runtime workflow invocation and preserve downstream artifact production.

- Adaptation and eval selected-workflow parameter acceptance
  - Coverage: `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`, `tests/runtime/test_workflow_to_eval_suite.py`
  - Behaviors: shared selected-workflow-with-evidence parameters continue to validate at runtime, blank selected-workflow input is rejected, and the selected-workflow snapshot/publication path stays intact.

- Refinement and decomposition workflow-local delta preservation
  - Coverage: `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`, `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  - Behaviors: migrated subclasses keep local workflow-specific fields and publication checks without losing the shared selected-workflow/task framing base behavior.

- Governance, company, and diagnostic local-rule preservation
  - Coverage: `tests/runtime/test_workflow_portfolio_to_operating_system.py`, `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`, `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  - Behaviors: portfolio/company positive-int filters remain enforced, focus lists remain normalized, and the diagnostic workflow keeps its local sorted `statuses` behavior instead of inheriting generic list output.

- Authoring and memory documentation boundary
  - Coverage: `tests/test_architecture_baseline_docs.py`
  - Behaviors: the architecture/authoring baseline still documents the shared parameter seam, preserved compatibility surfaces, and the strict workflow/runtime/provider boundary.

## Preserved invariants checked

- CLI `-wf` parameter handling remains unchanged.
- Runtime parameter resolution order remains unchanged.
- Local workflow `Parameters` exports remain unchanged.
- `ctx.params`, `ctx.workflow_params`, artifact contracts, and `ctx.invoke_workflow(...)` behavior remain unchanged.

## Edge cases and failure paths

- Blank required task or selected-workflow text is rejected.
- Duplicate or whitespace-only repeatable strings normalize deterministically.
- Positive-int fields reject zero/non-positive values.
- Diagnostic `statuses` output remains sorted and deduplicated locally.

## Stability / flake controls

- Proof is deterministic and filesystem-local only; no network, timing, or nondeterministic ordering dependencies were introduced.
- The rerun uses the same scoped suite that exercises the migrated workflow families and the seam-level unit assertions.

## Known gaps

- No new repository test files were modified in this phase because the relevant seam-level and workflow-family coverage already existed and passed after revalidation.
- Prompt-body behavior and unrelated domain workflow params modules remain intentionally out of scope for this phase.
