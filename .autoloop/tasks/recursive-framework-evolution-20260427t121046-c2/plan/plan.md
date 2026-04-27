# Recursive Framework Evolution Cycle 2 Plan

## Cycle Mode

- Primary mode: `consolidate`
- Rationale: prompt-contract compaction, validation migration, parameter-model convergence, typed bootstrap cleanup, and optimizer helper extraction are already closed. The clearest remaining cross-workflow debt is selected-workflow context capture and snapshot-writing duplication across the adaptation, evaluation, diagnostics, refinement/decomposition, and optimizer families.

## Pre-Change Audit Summary

- Mandatory inspection completed across repo inventory, `docs/architecture.md`, `docs/authoring.md`, `core/`, `runtime/`, `extensions/`, `stdlib/`, `workflows/`, relevant `tests/`, and `.autoloop_recursive/`.
- Three most relevant existing workflows/helpers:
  - `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py` plus `stdlib/adaptation.py`
  - `workflows/workflow_to_eval_suite/workflow.py` plus `stdlib/evaluation.py`
  - `workflows/workflow_run_history_to_failure_modes/workflow.py` plus `stdlib/diagnostics.py`
- Repeated patterns found:
  - `write_selected_workflow_*` helpers each re-resolve the repo root and workflow reference, rebuild the same envelope fields, and write one artifact-local payload.
  - Multiple workflows immediately re-read freshly written selected-workflow artifacts only to recover `selected_workflow_name` and validate the same capture boundary again.
  - The optimizer and decomposition/refinement consumers compose the same selected-workflow surfaces through adjacent but still partly duplicated helper paths.
- Simplification opportunity:
  - add one additive selected-workflow helper seam that owns reference resolution, shared envelope writing, and capture-time validation while keeping workflow-specific publication and evidence policy local.
- New workflow necessary: no.
- 10x authoring improvement target:
  - selected-workflow workflows should read as `capture context -> do local reasoning -> publish` instead of repeating snapshot resolution, existence checks, and name-alignment boilerplate.
- Cycle decision:
  - consolidate existing helper/workflow code; do not add, split, or retire workflows.

## Candidate Options Considered

1. Selected-workflow context-capture convergence across stdlib and the current selected-workflow workflow family.
   - Highest leverage because it shortens several existing workflows without widening runtime policy or portfolio size.
2. Portfolio-shape cleanup across `task_to_workflow_strategy` and `task_to_candidate_workflow_set`.
   - Deferred because the current explicit composition is already legible; the stronger pressure is helper duplication, not workflow overlap.
3. New workflow or new building block.
   - Rejected because wrapper policy disallows adding a workflow here and the new-workflow gate does not beat the leverage of existing-surface consolidation.

## Chosen Improvement

- Introduce one additive selected-workflow helper seam, tentatively centered in `stdlib/selected_workflow.py` or an equivalent private helper location.
- Rebase the existing selected-workflow artifact writers on that seam:
  - `stdlib/adaptation.py`
  - `stdlib/refinement.py`
  - `stdlib/decomposition.py`
  - `stdlib/diagnostics.py`
- Migrate the highest-reuse workflow consumers first:
  - `candidate_workflow_to_adapted_execution_plan`
  - `workflow_to_eval_suite`
  - `workflow_run_history_to_failure_modes`
  - `workflow_package_to_composable_building_blocks`
  - optimizer-family capture/publish paths where they reuse the same selected-workflow surfaces
- Preserve current helper entrypoints and current artifact filenames and top-level schemas:
  - `selected_workflow_capability.json`
  - `selected_workflow_authoring_surface.json`
  - `selected_workflow_decomposition_surface.json`
  - `selected_workflow_run_history.json`
  - optimizer-local selected-workflow evidence artifacts

## Why This Beats A New Workflow

- The repo already has credible workflow coverage for the current portfolio pressure.
- The remaining friction is authoring duplication inside shared selected-workflow consumers, not a missing trigger-to-terminal workflow package.
- A new workflow would increase portfolio size without removing the repeated capture mechanics that current workflows still carry.

## Interface And Boundary Notes

- Shared seam responsibilities:
  - resolve repo root and selected workflow reference once
  - expose the canonical `selected_workflow_name`
  - write the common envelope fields: `repo_root`, `run_id`, `task_id`, `workflow_name`, `selected_workflow_name`
  - delegate artifact-local payload shaping to existing capability/authoring/decomposition/run-history builders
  - provide a small capture-time validation utility so workflows stop re-reading fresh artifacts just to recover `selected_workflow_name`
- Non-goals:
  - no runtime-owned workflow selection or auto-execution
  - no new `workflow.toml` semantics
  - no root `workflow` surface expansion
  - no CLI, provider, or `ctx.invoke_workflow(...)` behavior change
  - no prompt path, route name, or artifact name changes

## Milestones

### 1. Shared selected-workflow helper

- Add the shared authoring-only helper seam.
- Rebase the existing selected-workflow stdlib helpers on the common resolution/envelope path.
- Keep exported helper names stable unless an additive helper is clearly cleaner and lower risk than changing call sites only.

### 2. Workflow-family migration

- Simplify capture/bootstrap logic in the adaptation, eval-suite, diagnostics, decomposition, and optimizer families.
- Remove repeated `write -> existence check -> re-read -> selected_workflow_name extraction` tails where the shared seam can provide the same data explicitly.
- Keep workflow-local publish handlers focused on domain-specific checks.

### 3. Proof, docs, and memory closeout

- Update `docs/authoring.md` only if the helper boundary or non-goals need to be frozen more explicitly.
- Update recursive memory files and ledgers with the audit, chosen seam, no-new-workflow rationale, and deferred debt.
- Run targeted unit/runtime/doc proof for the migrated helper family.

## Compatibility And Regression Controls

- Must preserve:
  - global CLI behavior
  - strict workflow/runtime/provider boundary
  - `ctx.invoke_workflow(...)` compatibility
  - current selected-workflow artifact filenames and top-level JSON schemas
  - current prompt/readme layout
- Main regression risks:
  - schema drift in selected-workflow artifacts
  - hidden changes to `selected_workflow_name` alignment logic
  - dropped workflow state such as `evidence_run_ids`, `case_ids`, or `proposed_parameter_keys`
  - optimizer regressions because it consumes multiple selected-workflow surfaces together
- Validation approach:
  - `tests/unit/test_stdlib_and_extensions.py`
  - `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
  - `tests/runtime/test_workflow_to_eval_suite.py`
  - `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  - `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`
  - `tests/test_architecture_baseline_docs.py`

## Boilerplate And Clarity Budget

- Expected direct boilerplate reduction:
  - duplicate selected-workflow resolution/envelope writers removed from the current stdlib helper family
  - repeated capture-step snapshot re-read / selected-workflow-name extraction removed from at least three workflows
  - helper boundary documented once instead of rediscovered across neighboring workflows
- Implementation closeout must report:
  - files added
  - files deleted
  - net line change
  - workflows migrated to the shared seam
  - old workflow-local capture/validation blocks replaced
  - readability before/after for the touched workflow family

## Deferred Debt After This Cycle

- Portfolio-shape work stays deferred unless helper convergence exposes real overlap with explicit evidence.
- New workflow additions remain lower priority than remaining helper-cleanup pressure.
