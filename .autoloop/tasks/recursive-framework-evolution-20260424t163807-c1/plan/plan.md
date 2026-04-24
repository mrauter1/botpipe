# Cycle 1 Plan

## Scope considered

- Authoritative inputs reviewed: the immutable request snapshot, the current run raw log, the standing recursive-memory files, the active empty plan artifacts, and the current repo-root codebase.
- Mandatory inspection completed across `docs/architecture.md`, `docs/authoring.md`, `core/`, `runtime/`, `extensions/`, `stdlib/`, `workflows/`, `tests/`, and `.autoloop_recursive/`.
- No clarification entries were appended after run start, so the initial request snapshot remains authoritative for this turn.
- In scope:
- choose one cycle mode and one concrete architecture improvement with direct evidence from the current workflow portfolio
- keep changes inside existing framework/workflow/doc/test surfaces rather than adding a new workflow
- preserve the global CLI contract, `ctx.invoke_workflow(...)`, and the strict workflow/runtime/provider boundary
- update the recursive-memory files as part of implementation closeout
- Out of scope:
- new workflow packages
- CLI, config, workspace-layout, provider, or `workflow.toml` semantic changes
- hidden runtime-owned routing, validation policy, or downstream execution
- unrelated dirty worktree files

## Cycle mode

- Primary cycle mode: `consolidate`
- Rationale: the highest-leverage gap is no longer portfolio coverage. The repo now has a credible builder plus routing, adaptation, evaluation, refinement, diagnostics, governance, decomposition, and company-level recursive-learning workflows. The clearest remaining pressure is repeated workflow-local validation and JSON-shape helper code copied across the newer workflow family.

## Pre-change audit summary

- Three most relevant existing workflows/helpers:
- `workflows/task_to_candidate_workflow_set/workflow.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
- `workflows/workflow_to_eval_suite/workflow.py`
- Supporting shared seams already adjacent to the problem: `stdlib/validation.py` and `stdlib/lifecycle.py`
- Repeated patterns found in current workflow packages:
- `def _require_text`: 11 workflow files
- `def _normalize_optional_text`: 13 workflow files
- `def _normalize_unique_strings`: 11 workflow files
- `def _require_string_list`: 11 workflow files
- `def _require_mapping`: 10 workflow files
- `def _read_json`: 13 workflow files
- Representative repeated workflow family: `task_to_candidate_workflow_set`, `task_to_workflow_strategy`, `candidate_workflow_to_adapted_execution_plan`, `workflow_to_eval_suite`, `workflow_run_history_to_failure_modes`, `workflow_portfolio_to_operating_system`, `company_operation_to_recursive_improvement_cycle`, `workflow_and_eval_to_refined_workflow_package`, and `workflow_package_to_composable_building_blocks`.
- Simplification opportunity: extend the existing shared validation surface so workflow packages stop carrying near-identical helper tails for string normalization, string-list normalization, mapping checks, JSON-object reads, duplicate checks, and simple positive-int validation.
- New workflow necessity: none. The current pressure is authoring-surface duplication inside existing packages, not a missing workflow outcome.
- Change decision for this cycle: change and consolidate existing helpers and workflow packages; do not add or retire workflows.
- 10x authoring improvement target: future workflow authors should be able to express bootstrap/publication validation with shared imports and a short domain-specific validator, rather than copying 40 to 120 lines of private helper code into every workflow file.

## Candidate options considered

| Option | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| Shared workflow-validation seam in `stdlib.validation` plus workflow migrations | Removes repetition across the largest current workflow family and directly improves authoring clarity | Requires careful compatibility-preserving helper design and targeted workflow migrations | Chosen |
| Prompt-contract/readme simplification across pair-step workflows | Would shorten prompts and docs that still repeat the same structure | Lower leverage until low-level validation duplication is removed; otherwise workflow files stay noisy even if prompts shrink | Deferred |
| New assessment/remediation building block | Could become a later domain building block after cycle 12 | Fails the cycle preference order and new-workflow gate because consolidation pressure is stronger and already evidenced | Rejected for this cycle |

## Chosen improvement

- Introduce one additive shared validation seam in `stdlib/validation.py` for the repeated workflow-local checks that are currently private helper tails.
- Reuse the existing stdlib validation conventions instead of expanding the root `workflow` surface.
- Keep domain-specific publish-time assertions inside each workflow; only move generic mechanics into stdlib.

### Planned helper surface

- Keep `require_non_empty_string(...)` and `require_string_list(...)` as the baseline shared entry points.
- Add the missing adjacent helpers needed by the repeated workflow family:
- one JSON-object reader for workflow-local artifact files
- one mapping validator and, where needed, mapping-list validation
- one optional-string normalizer
- one deduped string-list normalizer for repeated artifact/category/workflow-name inputs
- one positive-int validator
- one explicit duplicate-string guard where workflow-local order must be preserved
- Keep the seam additive under `stdlib/validation.py` and `stdlib/__init__.py`; do not widen `workflow`, `runtime`, or `workflow.toml`.

### Planned workflow migration set

- `workflows/task_to_candidate_workflow_set/workflow.py`
- `workflows/task_to_workflow_strategy/workflow.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
- `workflows/workflow_to_eval_suite/workflow.py`
- `workflows/workflow_run_history_to_failure_modes/workflow.py`
- `workflows/workflow_portfolio_to_operating_system/workflow.py`
- `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`
- `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
- `workflows/workflow_package_to_composable_building_blocks/workflow.py`

### Deferred migration set

- `workflows/investigation_request_to_evidence_pack/workflow.py`
- `workflows/security_finding_to_verified_remediation/workflow.py`
- `workflows/release_candidate_to_go_no_go/workflow.py`
- `workflows/incident_to_hardening_program/workflow.py`
- Rationale: these older packages use related helper shapes, but they are a lower-leverage second wave and should only move once the shared seam proves stable in the newer selected-workflow/governance family.

## Why this beats a new workflow

- The repository already covers the end-to-end portfolio layers that cycle 12 pointed to; the most visible friction is now inside the authoring surface itself.
- This change improves many existing workflows at once, shortens future workflow authoring, and reduces test duplication without increasing portfolio size.
- It follows the standing preference order: consolidate repeated validation before adding more workflow packages.

## Implementation phases

### Phase 1: shared validation seam

- Extend `stdlib/validation.py` with additive helpers for the repeated workflow-local validation idioms.
- Export the new helper surface from `stdlib/__init__.py`.
- Add or update focused unit coverage in `tests/unit/test_validation.py` and `tests/unit/test_stdlib_and_extensions.py`.
- Preserve current runtime/CLI behavior and keep helper outputs workflow-local and explicit.

### Phase 2: workflow migrations and closeout

- Migrate the selected-workflow/governance workflow family listed above to the shared validation seam.
- Remove the duplicated helper tails from those workflows while leaving domain-specific publish checks local.
- Update `docs/authoring.md` to freeze the boundary: shared low-level validation lives in stdlib; workflow code keeps domain policy.
- Update targeted runtime tests for the migrated workflows plus `tests/test_architecture_baseline_docs.py` if the docs contract changes.
- Update `.autoloop_recursive/framework_evolution_charter.md`, `.autoloop_recursive/framework_roadmap.md`, `.autoloop_recursive/framework_gap_ledger.md`, `.autoloop_recursive/workflow_candidate_ledger.md`, and `.autoloop_recursive/validation_debt_ledger.md`.

## Compatibility and regression controls

- No public CLI changes.
- No runtime-owned validation automation or hidden downstream routing.
- No new semantic `workflow.toml` fields.
- Existing workflow composition through `ctx.invoke_workflow(...)` remains unchanged.
- Migrate only workflows whose helper semantics already match the shared seam closely; defer the older domain workflows instead of forcing a wider risky sweep.
- Treat helper strictness as a compatibility surface: preserve current workflow behavior unless targeted tests show the stricter shared contract is already required.
- Validate both unit-level helper behavior and runtime-level workflow publication behavior before closeout.

## Boilerplate and clarity budget

- Files added: target `0`
- Files deleted: target `0`
- Net line count: target negative; expect helper extraction plus workflow-tail deletion to reduce repository lines overall
- Repeated validation idioms removed:
- shared `_require_text` / non-empty string checks
- shared optional-string normalization
- shared deduped string-list normalization
- shared mapping / mapping-list checks
- shared workflow-local JSON-object reads
- shared positive-int / duplicate-string guards where applicable
- Repeated prompt sections removed or shortened: none required for the core change; prompt simplification is explicitly deferred
- Workflows changed to use shared helpers: the nine-package migration set above
- New helper functions introduced: only the minimum additive validation helpers needed to replace the copied workflow tails
- Old workflow-local validation blocks replaced: private helper tails at the bottom of the migrated workflow files
- Core flow readability before/after:
- before: long local helper tails obscure the end of each workflow file and repeat across packages
- after: workflow files end closer to their workflow-specific publish logic, with generic mechanics imported from stdlib

## Tests and docs update plan

- Unit tests:
- `tests/unit/test_validation.py`
- `tests/unit/test_stdlib_and_extensions.py`
- Targeted runtime tests:
- `tests/runtime/test_task_to_candidate_workflow_set.py`
- `tests/runtime/test_task_to_workflow_strategy.py`
- `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
- `tests/runtime/test_workflow_to_eval_suite.py`
- `tests/runtime/test_workflow_run_history_to_failure_modes.py`
- `tests/runtime/test_workflow_portfolio_to_operating_system.py`
- `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
- `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- Docs:
- `docs/authoring.md`
- `tests/test_architecture_baseline_docs.py` only if the authoring doc contract changes
- Recursive memory closeout:
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `.autoloop_recursive/validation_debt_ledger.md`

## Remaining deferred debt

- The older domain workflows still carry related helper tails and should be the next migration wave after the shared seam proves stable.
- Prompt-template/readme duplication remains real but is lower leverage than the current validation duplication.
- Reusable assessment/remediation building blocks remain deferred portfolio-shape work for a later cycle, not this consolidation pass.
