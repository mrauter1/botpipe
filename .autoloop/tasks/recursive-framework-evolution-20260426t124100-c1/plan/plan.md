# Recursive Architecture Improvement Cycle 1 Plan

## Cycle mode
`consolidate`

Rationale: the highest-leverage remaining pressure is repeated workflow-local JSON publication parsing in the later governance and diagnostic family. Existing workflows already prove a narrower typed-artifact seam, so expanding the workflow portfolio now would add surface without reducing authoring cost.

## Pre-change audit
- Three most relevant existing references:
  - `workflows/task_to_candidate_workflow_set` already uses `JsonArtifactSpec` for `candidate_workflow_set_summary.json`.
  - `workflows/candidate_workflow_to_adapted_execution_plan` already uses typed summary plus validated-parameter artifacts and keeps cross-artifact invariants local.
  - `workflows/workflow_to_eval_suite` already uses typed summary and manifest artifacts as the clearest current publish-surface pattern.
- Highest-pressure target workflows:
  - `workflows/workflow_portfolio_to_operating_system/workflow.py`
  - `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`
  - `workflows/workflow_run_history_to_failure_modes/workflow.py`
- Repeated patterns found:
  - large publish handlers still hand-parse summary or manifest JSON with raw mapping/list/string checks
  - repeated authoritative-artifact, next-action, and publication-boundary validation sequences
  - workflow-local domain assertions are mixed with low-level JSON mechanics, obscuring the core publication flow
- Simplification opportunity:
  - converge those summary and manifest artifacts on workflow-local `JsonArtifactSpec` contracts and let publish handlers begin from typed models
- New workflow necessity:
  - none; the active gap is consolidation of existing publication surfaces, not missing workflow coverage
- 10x authoring improvement target:
  - make publish handlers read as `load typed artifacts -> validate cross-artifact invariants -> write receipt`
- Decision:
  - change and consolidate existing workflows; do not add, merge, retire, or create workflows in this cycle

## Candidate options considered
1. Split large workflows into `flow.py` plus `specs.py`.
   - Improves file layout, but does not remove the repeated JSON/publication mechanics driving the current readability problem.
2. Add a broad runtime-owned or stdlib-owned publication engine.
   - Risks hiding workflow-specific policy and widening the workflow/runtime boundary.
3. Converge workflow-local typed publication contracts on the existing `JsonArtifactSpec` seam.
   - Reuses an existing pattern, shortens publish handlers, and keeps domain policy visible in workflow code.

Chosen: option 3.

## Chosen improvement
Converge the governance and diagnostic publication family on workflow-local typed artifact contracts, starting with:
- `workflow_portfolio_to_operating_system`
- `company_operation_to_recursive_improvement_cycle`
- `workflow_run_history_to_failure_modes`

Secondary follow-on only if it stays inside the same seam and remains net-simplifying:
- `workflow_and_eval_to_refined_workflow_package`
- `workflow_package_to_composable_building_blocks`

## Why this is higher leverage than a new workflow
The repository already has credible portfolio coverage for this family of work, but the publish surfaces of the later workflows remain materially harder to read and maintain than the earlier selected-workflow family. Converging those surfaces removes live authoring debt across multiple workflows without increasing portfolio size, runtime policy, or CLI complexity.

## Milestones
1. Add typed artifact contracts.
   - Define workflow-local `JsonArtifactSpec` entries and nested Pydantic models for the currently hand-parsed summary and manifest artifacts.
   - Preserve artifact filenames, JSON keys, enum values, and publication-boundary strings.
2. Migrate target publish handlers.
   - Replace raw summary/manifest dict parsing with typed `.read(...)` calls.
   - Keep cross-artifact drift checks, state alignment, markdown-boundary checks, and hidden-execution checks local to the workflow.
   - Only add a shared stdlib validator if two or more target workflows need the exact same model-independent check after the contract migration.
3. Proof, docs, and recursive-memory closeout.
   - Update `docs/authoring.md` with the preferred typed publication-artifact pattern.
   - Update `.autoloop_recursive/framework_evolution_charter.md`, `.autoloop_recursive/framework_roadmap.md`, `.autoloop_recursive/framework_gap_ledger.md`, `.autoloop_recursive/workflow_candidate_ledger.md`, and `.autoloop_recursive/validation_debt_ledger.md`.
   - Run targeted proof and record boilerplate-reduction metrics.

## Interface definitions
- Workflow-local contract additions:
  - `workflows/workflow_portfolio_to_operating_system/contracts.py`
    - `PORTFOLIO_OPERATING_SUMMARY_ARTIFACT`
    - typed summary-side lifecycle recommendation payloads as needed for publish-time reads
  - `workflows/company_operation_to_recursive_improvement_cycle/contracts.py`
    - `RECURSIVE_IMPROVEMENT_SUMMARY_ARTIFACT`
    - typed candidate and priority payloads as needed for publish-time reads
  - `workflows/workflow_run_history_to_failure_modes/contracts.py`
    - `FAILURE_MODE_MANIFEST_ARTIFACT`
    - `IMPROVEMENT_OPPORTUNITIES_SUMMARY_ARTIFACT`
    - typed failure-mode and opportunity item payloads as needed for publish-time reads
- Existing seams to reuse:
  - `stdlib/json_artifacts.JsonArtifactSpec`
  - `stdlib.validation.validate_authoritative_artifact_subset`
  - `stdlib.validation.validate_publication_boundary`
  - `stdlib.validation.validate_no_hidden_execution_signal`
  - selected-workflow snapshot validators already used by the selected-workflow family
- Non-goals:
  - no new runtime-owned publication registry
  - no new CLI flags or `workflow.toml` fields
  - no hidden downstream execution or route-policy changes

## Compatibility and invariants
- Preserve CLI behavior, workspace layout, receipt names, artifact filenames, and `ctx.invoke_workflow(...)` compatibility.
- Preserve the strict workflow/runtime/provider boundary and keep the root `workflow` authoring surface unchanged.
- Keep publication-boundary literals unchanged:
  - `operating_system_publication_only`
  - `recursive_improvement_publication_only`
  - `diagnostic_publication_only`
- Keep workflow-specific policy local:
  - scoped workflow and task alignment
  - candidate and ranking drift checks
  - markdown section-marker requirements
  - overlay and building-block policy if the secondary follow-on lands

## Regression risks and controls
- Risk: typed models narrow accepted JSON shape earlier than the current handlers.
  - Control: put only stable shape and mechanical requirements into models; keep domain drift and boundary checks explicit in workflow code.
- Risk: targeted tests depend on exact publish-time error messages.
  - Control: retain explicit workflow-authored error messages for cross-artifact mismatches and publication-boundary failures.
- Risk: scope creep into refinement/decomposition-specific policy.
  - Control: include those workflows only if they reuse the exact same seam without introducing another abstraction or widening the boundary.

## Validation plan
- Unit proof:
  - `tests/unit/test_stdlib_and_extensions.py`
- Runtime proof:
  - `tests/runtime/test_workflow_portfolio_to_operating_system.py`
  - `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
  - `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py` and `tests/runtime/test_workflow_package_to_composable_building_blocks.py` only if the secondary follow-on lands
- Docs proof:
  - `tests/test_architecture_baseline_docs.py`

## Boilerplate and clarity budget
- Target files added: `0` unless a missing contract constant truly requires a new local support file.
- Target files deleted: `0`.
- Expected net line change: flat or negative across the target `workflow.py` files.
- Repetition targeted for removal:
  - raw `_read_json(...).get(...)` summary or manifest unpacking in target publish handlers
  - duplicated authoritative-artifact, next-action, and publication-boundary reads before domain checks
- Workflows expected to use the converged seam:
  - `workflow_portfolio_to_operating_system`
  - `company_operation_to_recursive_improvement_cycle`
  - `workflow_run_history_to_failure_modes`
- Core-flow readability before/after:
  - before: publish handlers mix raw JSON mechanics with domain invariants
  - after: publish handlers start from typed artifacts and surface only cross-artifact and business checks

## Deferred debt after this cycle
- `workflow_and_eval_to_refined_workflow_package` and `workflow_package_to_composable_building_blocks` may still warrant a later typed-manifest convergence pass if their publication sections remain materially larger than the converged governance and diagnostic family.
- No new workflow should be proposed until this remaining publish-surface convergence is re-evaluated.
- The charter must remain synchronized with the closeout result even if it needs only a review-confirmation note rather than a doctrinal rewrite.
