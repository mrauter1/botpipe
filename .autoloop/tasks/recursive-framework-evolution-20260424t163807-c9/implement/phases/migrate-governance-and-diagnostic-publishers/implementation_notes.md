# Implementation Notes

- Task ID: recursive-framework-evolution-20260424t163807-c9
- Pair: implement
- Phase ID: migrate-governance-and-diagnostic-publishers
- Phase Directory Key: migrate-governance-and-diagnostic-publishers
- Phase Title: Migrate Governance And Diagnostic Publishers
- Scope: phase-local producer artifact

## Pre-Change Audit

- Cycle mode: `consolidate`
- Most relevant workflows/helpers:
  - `workflows/workflow_portfolio_to_operating_system/workflow.py`
  - `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`
  - `workflows/workflow_run_history_to_failure_modes/workflow.py`
  - `stdlib/validation.py`
- Repeated patterns found:
  - duplicated `workflow_capability_snapshot.json` workflow-name readers in governance/company workflows
  - duplicated `workflow_portfolio_health_snapshot.json` scoped-workflow readers in governance/company workflows
  - already-migrated shared publish helpers in the scoped family that made the remaining snapshot-reader tails the clearest follow-on
- Simplification opportunity: move the remaining mechanical snapshot-name extraction into the shared validation seam so the scoped publish/context hooks keep only unknown-reference checks and domain policy local.
- New workflow needed: no
- Cycle decision: change/consolidate existing helpers and workflows only

## Files Changed

- `stdlib/validation.py`
- `stdlib/__init__.py`
- `workflows/workflow_portfolio_to_operating_system/workflow.py`
- `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`
- `tests/unit/test_validation.py`
- `docs/authoring.md`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `.autoloop_recursive/validation_debt_ledger.md`
- `.autoloop/tasks/recursive-framework-evolution-20260424t163807-c9/decisions.txt`

## Symbols Touched

- `stdlib.validation`
  - `extract_workflow_names_from_capability_snapshot`
  - `extract_workflow_names_from_portfolio_health`
- `stdlib.__init__`
  - shared-export surface for the new snapshot readers
- `WorkflowPortfolioToOperatingSystem`
  - `on_capture_portfolio_context`
  - `on_publish_portfolio_operating_system`
- `CompanyOperationToRecursiveImprovementCycle`
  - `on_capture_company_operation_context`
  - `on_publish_recursive_improvement_cycle`

## Checklist Mapping

- Plan milestone 1: extended the shared validation seam with snapshot-name extraction helpers
- Plan milestone 2: migrated the scoped governance/company workflow hooks and deleted the replaced local helper tails
- Plan milestone 3: updated `docs/authoring.md`, recursive-memory files, the decisions log, and scoped helper proof

## Assumptions

- `workflow_run_history_to_failure_modes` already satisfied the phase’s shared-helper boundary through the selected-workflow validation seam and did not need an additional code change in this follow-on.
- Unknown-workflow checks, company-task extraction, and domain publication semantics remain intentionally workflow-local.

## Preserved Invariants

- No CLI, runtime-owned routing, provider, `workflow.toml`, or `ctx.invoke_workflow(...)` behavior changed.
- Artifact names, receipt filenames, route names, and workflow package layout stayed unchanged.
- The scoped workflows still own unknown-reference checks, scoped-task checks, state-drift policy, and receipt shaping.

## Intended Behavior Changes

- None at the workflow contract level; the change centralizes the remaining duplicated snapshot-name extraction behind shared stdlib helpers.

## Known Non-Changes

- No new workflow or building block was added.
- `workflow_run_history_to_failure_modes` publish semantics were not widened.
- No adjacent workflow migration was forced outside the scoped family.

## Expected Side Effects

- The governance/company workflow files lose two more duplicated helper tails.
- Future governance-family workflows can reuse the same capability/portfolio snapshot readers instead of reintroducing local copies.

## Validation Performed

- Compile check:
  - `./.venv/bin/python -m py_compile stdlib/validation.py stdlib/__init__.py workflows/workflow_portfolio_to_operating_system/workflow.py workflows/company_operation_to_recursive_improvement_cycle/workflow.py tests/unit/test_validation.py`
- Scoped proof:
  - `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/unit/test_validation.py tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/test_architecture_baseline_docs.py`
  - Result: `140 passed`

## Deduplication / Centralization Decisions

- Centralized only the shared workflow-name extraction for capability and portfolio-health snapshots.
- Left unknown-reference checks and company-task extraction local so the new helpers stay mechanical and additive.

## Closeout Accounting

- Files added: `0` tracked in this phase
- Files deleted: `0`
- Net tracked line change across the edited tracked files: `+79` (`157` insertions, `78` deletions)
- Repeated validation idioms removed: `2` duplicated snapshot-name reader tails
- Repeated prompt sections removed or shortened: `0`
- Workflows changed to use shared helpers: `2` (`workflow_portfolio_to_operating_system`, `company_operation_to_recursive_improvement_cycle`)
- New helper functions introduced: `2`
- Old workflow-local validation blocks replaced: `4` call sites plus `2` deleted helper definitions
- Core flow readability before/after: publish/context hooks in the governance/company family no longer carry local capability/portfolio snapshot readers, so the remaining local code is focused on unknown-reference checks and domain policy
