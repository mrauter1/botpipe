# Recursive Architecture Improvement Cycle 2 Plan

## Cycle mode

`consolidate`

Rationale: the repository already has the reusable workflow portfolio needed for this cycle, while the strongest remaining cross-workflow duplication sits in `workflows/*/params.py`. Removing that duplication improves authoring clarity across existing workflows more directly than adding another workflow package.

## Pre-change audit summary

### Most relevant existing workflows/helpers

1. `stdlib/validation.py`
   - Already owns the shared parameter-validator factories (`required_text_fields(...)`, `optional_text_fields(...)`, `deduped_string_list_fields(...)`, `positive_int_fields(...)`) and is the current convergence seam for generic parameter mechanics.
2. `workflows/task_to_candidate_workflow_set/params.py` and `workflows/task_to_workflow_strategy/params.py`
   - These are effectively the same parameter contract today: `task_title`, `sponsor_role`, `desired_outcome`, `constraints`, and `evidence_expectations`.
3. `workflows/candidate_workflow_to_adapted_execution_plan/params.py`, `workflows/workflow_to_eval_suite/params.py`, `workflows/workflow_and_eval_to_refined_workflow_package/params.py`, and `workflows/workflow_package_to_composable_building_blocks/params.py`
   - These repeat the same selected-workflow/task framing core, with small workflow-specific deltas such as `target_test_command` or evaluation artifact paths.

### Repeated patterns observed

- Repeated `task_title` + sponsor/desired-outcome + constraints bundles across the portfolio/front-door/governance family.
- Repeated `selected_workflow` + task framing bundles across the adaptation/eval/refinement/decomposition/diagnostics family.
- Repeated `target_test_command` and positive-int adjunct fields on otherwise identical parameter models.
- Repeated `params.py` file shape where most lines restate shared fields instead of workflow-specific contract differences.

### Simplification opportunity

Introduce an additive stdlib-owned parameter-model seam for the exact repeated parameter bundles, then migrate only the workflows whose `Parameters` classes are mostly duplicated scaffolding today. Keep workflow-local `Parameters` exports, runtime loader behavior, and workflow-specific validators unchanged.

### New workflow necessity

No new workflow is necessary. The current pressure is authoring-surface duplication, not a missing terminal artifact package, and the new-workflow gate does not beat the leverage of consolidating the existing parameter family first.

### What would make this workflow family 10x easier to author

Future `params.py` files should declare only workflow-specific deltas. Shared task framing, selected-workflow framing, evidence-expectation lists, decision-driver lists, and test-command normalization should come from one obvious stdlib seam instead of being recopied across packages.

### Decision

Change and consolidate the parameter-authoring surface. Do not add, split, merge, or retire workflows in this cycle.

## Candidate options considered

1. Shared `params.py` contract convergence
   - Highest leverage because the gap ledger explicitly identifies repeated `params.py` shapes as the remaining authoring debt after validation migration.
2. Further prompt-contract compaction
   - Valuable, but the prompt families already have standardized `prompts/README.md` boundaries and shorter bodies; the remaining duplication is less structural than the parameter-model repetition.
3. Another candidate-surface helper extraction
   - Deferred because the remaining refinement/decomposition local logic is more workflow-specific and riskier to over-abstract than the clearly duplicated parameter models.

## Chosen improvement

Add one additive shared parameter-model seam under `stdlib/` and migrate the duplicated workflow families onto it.

Planned scope:

- Define reusable Pydantic base models or mixins for the repeated task-framing and selected-workflow parameter bundles.
- Re-export the seam through `stdlib/__init__.py` so workflows keep using the existing stdlib import boundary.
- Migrate the duplicated workflow families first:
  - `task_to_candidate_workflow_set`
  - `task_to_workflow_strategy`
  - `candidate_workflow_to_adapted_execution_plan`
  - `workflow_to_eval_suite`
  - `workflow_and_eval_to_refined_workflow_package`
  - `workflow_package_to_composable_building_blocks`
  - `workflow_portfolio_to_operating_system`
  - `company_operation_to_recursive_improvement_cycle`
  - `workflow_run_history_to_failure_modes` where only the shared core moves and the order-sensitive status normalization remains local
- Update docs and recursive-memory files, including the standing charter, so the new parameter seam boundary is explicit and future cycles do not reopen the same question.

### Why this is higher leverage than a new workflow

- It shortens multiple existing workflow packages at once.
- It reduces future builder-era and hand-written workflow boilerplate without touching runtime policy.
- It improves readability in the exact files authors edit when adding or adapting workflows.
- It preserves the current workflow portfolio while making that portfolio easier to maintain and reason about.

## Interface and compatibility notes

- Keep the runtime parameter resolution order unchanged: `Workflow.Parameters`, module-level `Parameters`, package-exported `Parameters`, then legacy `params.py`.
- Keep each workflow exporting a concrete `Parameters` class from its local module/package; do not ask the runtime loader to discover a new contract shape.
- Do not change CLI `-wf` behavior, `ctx.params`, `ctx.workflow_params`, artifact names, `workflow.toml`, or `ctx.invoke_workflow(...)`.
- Keep the new seam stdlib-only and additive; do not expand the root `workflow` shim.
- Preserve current normalized parameter payloads for existing workflows unless the authoritative clarification history explicitly permits a behavior change. No such clarification exists for this turn.

## Ordered milestones

### Phase 1: shared parameter seam

- Add the shared stdlib-owned parameter-model seam for the repeated field bundles already present across the current workflow portfolio.
- Freeze the seam with focused unit coverage so validator order, defaults, and normalized payload shape stay explicit.
- Keep the seam narrow: shared field bundles only, with workflow-specific literals, identifier rules, and order-sensitive normalization staying local.

### Phase 2: workflow migration and docs

- Migrate the duplicated workflow `params.py` files onto the shared seam.
- Update `docs/authoring.md` to document where shared parameter bundles belong and where workflow-local validation must remain.
- Review and synchronize `.autoloop_recursive/framework_evolution_charter.md`, even if the outcome is an explicit no-change confirmation, so the standing charter remains aligned with the chosen seam boundary.
- Update any affected architecture/doc baseline expectations and the recursive-memory files:
  - `.autoloop_recursive/framework_evolution_charter.md`
  - `.autoloop_recursive/framework_roadmap.md`
  - `.autoloop_recursive/framework_gap_ledger.md`
  - `.autoloop_recursive/workflow_candidate_ledger.md`
  - `.autoloop_recursive/validation_debt_ledger.md`

### Phase 3: proof and closeout

- Run targeted proof across the migrated workflow family and the shared stdlib seam.
- Confirm no drift in loader coercion, runtime compatibility, artifact contracts, or published workflow behavior.
- Record the full cycle closeout metrics contract, including zero-value items when applicable.

## Regression prevention and validation

### Invariants that must remain true

- The same workflow parameter names remain accepted for every migrated workflow.
- Blank required text still fails the same workflows.
- Optional text and repeatable string-list normalization remain stable.
- Positive-integer constraints remain stable where currently enforced.
- Local special cases remain local:
  - package-name identifier rules
  - literal pre-normalization for investigation/security enums
  - order-sensitive status normalization in `workflow_run_history_to_failure_modes`
- No workflow artifact contract, prompt path, route contract, runtime routing rule, or CLI behavior changes.

### Targeted validation approach

- Add or extend unit tests for the new shared parameter-model seam.
- Re-run workflow-parameter coercion/runtime coverage for the migrated family, especially:
  - `tests/runtime/test_task_to_candidate_workflow_set.py`
  - `tests/runtime/test_task_to_workflow_strategy.py`
  - `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
  - `tests/runtime/test_workflow_to_eval_suite.py`
  - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  - `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  - `tests/runtime/test_workflow_portfolio_to_operating_system.py`
  - `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
  - `tests/test_architecture_baseline_docs.py`
- Keep proof scoped to the touched family; do not broaden into unrelated dirty areas.

## Risk register

1. Pydantic inheritance or mixin ordering could change normalized payloads or error surfaces.
   - Control: add seam-level unit proof and keep the first migration wave limited to exact duplication clusters.
2. Over-abstracting unlike workflows could hide real domain differences.
   - Control: extract only the repeated common bundles and leave workflow-specific validators local.
3. Docs or recursive-memory drift could cause later cycles to re-open the same seam decision.
   - Control: update authoring docs plus all required recursive-memory ledgers in the same change set.
4. Broad migration could touch too many workflows without clear verification coverage.
   - Control: migrate only the workflows with near-identical `params.py` scaffolding and back them with targeted runtime suites.

## Boilerplate and clarity budget

Implementation should report:

- files added, deleted, and net line delta if practical
- repeated validation idioms removed
- repeated prompt sections removed or shortened
- repeated `params.py` bundles removed
- workflows migrated onto the shared seam
- new helper functions or parameter base models introduced
- old workflow-local validation blocks replaced
- any remaining workflow-local validators kept intentionally
- before/after readability of the touched `params.py` files

Closeout must explicitly state the requested cycle-report fields even when the value is zero or `none`, rather than omitting the line entirely.

Expected closeout outcome:

- one shared parameter seam added
- no new workflow packages
- multiple `params.py` modules reduced to workflow-specific deltas
- docs/tests/memory synchronized to the new boundary

## Deferred debt after this planned slice

- Prompt-body compaction remains deferred unless the parameter consolidation exposes a clearly adjacent prompt win.
- Refinement/decomposition local candidate-surface policy remains intentionally local unless a later cycle finds cross-workflow repetition beyond the current shared seam.
- Reusable assessment/remediation building blocks remain deferred because this cycle is explicitly prioritizing authoring-surface convergence over portfolio expansion.
