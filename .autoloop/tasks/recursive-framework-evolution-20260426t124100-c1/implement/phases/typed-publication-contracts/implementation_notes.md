# Implementation Notes

- Task ID: recursive-framework-evolution-20260426t124100-c1
- Pair: implement
- Phase ID: typed-publication-contracts
- Phase Directory Key: typed-publication-contracts
- Phase Title: Typed Publication Contracts
- Scope: phase-local producer artifact

## Pre-Change Audit

- Cycle mode: `consolidate`
- Most relevant existing references:
  - `workflows/task_to_candidate_workflow_set/contracts.py`
  - `workflows/candidate_workflow_to_adapted_execution_plan/contracts.py`
  - `workflows/workflow_to_eval_suite/contracts.py`
- Repeated pattern confirmed: raw publish-time `summary.get(...)` / `manifest.get(...)` entry reads mixed mechanical JSON shape checks with workflow-local publication policy.
- Simplification chosen: add workflow-local typed publication specs in the target contracts modules and keep allow-lists, drift checks, and receipt shaping local.
- New workflow needed: no

## Files Changed

- `workflows/workflow_portfolio_to_operating_system/contracts.py`
- `workflows/workflow_portfolio_to_operating_system/workflow.py`
- `workflows/company_operation_to_recursive_improvement_cycle/contracts.py`
- `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`
- `workflows/workflow_run_history_to_failure_modes/contracts.py`
- `workflows/workflow_run_history_to_failure_modes/workflow.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `docs/authoring.md`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `.autoloop_recursive/validation_debt_ledger.md`
- `.autoloop/tasks/recursive-framework-evolution-20260426t124100-c1/decisions.txt`

## Symbols Touched

- `PORTFOLIO_OPERATING_SUMMARY_ARTIFACT`
- `PortfolioOperatingSummaryArtifactPayload`
- `RECURSIVE_IMPROVEMENT_SUMMARY_ARTIFACT`
- `RecursiveImprovementSummaryArtifactPayload`
- `FAILURE_MODE_MANIFEST_ARTIFACT`
- `FailureModeManifestArtifactPayload`
- `IMPROVEMENT_OPPORTUNITIES_SUMMARY_ARTIFACT`
- `ImprovementOpportunitiesSummaryArtifactPayload`
- `WorkflowPortfolioToOperatingSystem.on_publish_portfolio_operating_system`
- `CompanyOperationToRecursiveImprovementCycle.on_publish_recursive_improvement_cycle`
- `WorkflowRunHistoryToFailureModes.on_publish_failure_mode_package`

## Checklist Mapping

- Milestone 1: completed via workflow-local typed artifact specs and payload models in the three target `contracts.py` modules.
- Milestone 2: completed via publish-handler migrations to `JsonArtifactSpec.read(...)` while preserving workflow-local policy checks and artifact names.
- Milestone 3: completed via focused unit/runtime proof, `docs/authoring.md`, recursive memory updates, and decisions closeout.

## Assumptions

- Artifact filenames, top-level JSON keys, route names, receipt filenames, and publication-boundary literals are compatibility-sensitive and must not change.
- Existing workflow-local `ValueError` policy for invalid lifecycle postures, priority categories, publication boundaries, and hidden execution should remain intact.

## Preserved Invariants

- No CLI changes.
- No `workflow.toml` schema changes.
- No runtime-owned publication orchestration.
- No new shared stdlib or runtime helper seam.
- `ctx.invoke_workflow(...)` compatibility preserved.

## Intended Behavior Changes

- Publish handlers for the scoped governance/company/diagnostic family now start from typed artifact loads instead of raw top-level dictionary unpacking.

## Known Non-Changes

- Candidate/refinement/decomposition secondary follow-on workflows remain untouched in this phase.
- Domain-specific publication policy still lives in workflow code rather than in shared helpers or runtime code.

## Expected Side Effects

- Publish-step entry reads are shorter and clearer.
- The target contracts modules now expose explicit durable summary or manifest contracts for focused proof and later migrations.

## Validation Performed

- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py` (`89 passed`)
- `PYTHONPATH=/home/rauter/autoloop_v3_bkp ./.venv/bin/pytest -q tests/runtime/test_workflow_portfolio_to_operating_system.py tests/runtime/test_company_operation_to_recursive_improvement_cycle.py tests/runtime/test_workflow_run_history_to_failure_modes.py tests/test_architecture_baseline_docs.py` (`105 passed`)

## Deduplication / Centralization

- Old workflow-local raw `summary.get(...)` / `manifest.get(...)` publish-entry reads were replaced in 3 existing publish handlers.
- No new helper seam was introduced; this phase converges on the existing workflow-local `JsonArtifactSpec(...)` pattern only.
- Files added: `0`. Files deleted: `0`.
- Tracked diff for the phase-owned files is `+226 / -47` lines in this checkout; recursive memory and some repo-root proof files are untracked here and therefore excluded from that tracked count.
