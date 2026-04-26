# Recursive Architecture Improvement Cycle 1 Plan

## Cycle mode and rationale

- Primary cycle mode: `consolidate`
- Rationale: the highest-leverage open duplication is workflow-local bootstrap normalization that still re-reads `ctx.workflow_params` and re-validates fields that the shared `Parameters` models and runtime already normalize through `ctx.params`. This improves authoring clarity across existing workflows without adding a new workflow, widening the runtime, or expanding the root `workflow` shim.

## Pre-change audit summary

- Most relevant existing workflows/helpers:
  - `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
  - `workflows/workflow_to_eval_suite/workflow.py`
  - `workflows/workflow_run_history_to_failure_modes/workflow.py`
  - supporting seams: `stdlib/parameters.py`, `stdlib/lifecycle.py`, `stdlib/adaptation.py`, `core/context.py`
- Repeated patterns identified:
  - Many workflow `on_bootstrap(...)` handlers still unpack `ctx.workflow_params` into a local dict and then repeat `require_non_empty_string(...)`, `normalize_optional_string(...)`, deduping, and positive-int checks even though the workflow already declares a shared `Parameters` model.
  - The task-framing, selected-workflow, portfolio-review, and governance workflow families each repeat the same session-opening plus invocation-contract setup.
  - Selected-workflow system-step capture still repeats `write_*snapshot(...)` -> `read_json_object(...)` -> `validate_*snapshot(...)` before copying `selected_workflow_name` into state.
  - Prompt README boundary prose is still repeated package-to-package, but the Python authoring duplication is the higher-leverage surface for this cycle.
- At least one simplification opportunity:
  - Make `ctx.params` the default authoring surface for bootstrap handlers and keep `ctx.workflow_params` as the compatibility dict surface.
  - Only extract another helper if duplicate selected-workflow capture code is still materially noisy after the typed-bootstrap migration.
- New workflow necessity:
  - No new workflow is necessary. The current pressure is on existing authoring surfaces, not missing workflow coverage or terminal artifact packages.
- What would make this family 10x easier to author/read/reason about:
  - Bootstrap handlers should project already-typed fields into workflow state, open declared sessions, and write the invocation contract without re-implementing parameter validation locally.
- Cycle decision:
  - Change/consolidate existing workflows, docs, tests, and recursive memory. Do not add, split, or retire a workflow package in this cycle.

## Candidate options considered

1. Prompt README compaction across workflow packages
   - Pros: removes visible prose duplication across prompt families.
   - Cons: lower leverage than the Python-side bootstrap duplication and does not reduce workflow-local validation/state wiring.
   - Decision: deferred.
2. Typed bootstrap convergence on `ctx.params`
   - Pros: reuses an existing runtime-supported surface, deletes repeated workflow-local validation, shortens bootstraps across many workflows, and improves readability without adding a new public abstraction.
   - Cons: requires broad workflow/test/doc touch points.
   - Decision: chosen.
3. Shared selected-workflow capture/publish helper extraction
   - Pros: could reduce remaining snapshot-capture boilerplate in selected-workflow families.
   - Cons: easy to over-abstract and hide workflow semantics if attempted before the typed-bootstrap duplication is removed.
   - Decision: defer unless duplication remains clearly material after the chosen migration.

## Chosen improvement

- Migrate workflows that already declare shared `Parameters` bundles to read typed inputs from `ctx.params` in `on_bootstrap(...)` and remove redundant generic normalization from the bootstrap path.
- Prioritize the workflow families with the heaviest reuse pressure:
  - `task_to_candidate_workflow_set`
  - `task_to_workflow_strategy`
  - `candidate_workflow_to_adapted_execution_plan`
  - `workflow_to_eval_suite`
  - `workflow_run_history_to_failure_modes`
  - `workflow_portfolio_to_operating_system`
  - `company_operation_to_recursive_improvement_cycle`
  - `workflow_and_eval_to_refined_workflow_package`
  - `workflow_package_to_composable_building_blocks`
- Preserve current artifact names, route names, receipt files, CLI behavior, `ctx.invoke_workflow(...)` behavior, and `workflow.toml` semantics.
- Keep workflow-specific transforms local:
  - status sorting or allow-lists
  - workflow-specific identifier rules
  - publication-boundary policy
  - selected-workflow/decomposition/refinement alignment checks
- Update `docs/authoring.md` to make the authoring rule explicit:
  - use `ctx.params` when a workflow declares a `Parameters` model
  - treat `ctx.workflow_params` as the compatibility/raw-mapping surface, not the default workflow-authoring surface
- Only add a helper if needed after migration, and if so keep it additive under an existing `stdlib/` seam rather than adding runtime-owned machinery or a new public root primitive.

## Interfaces and compatibility notes

- Public interfaces that must remain unchanged:
  - `autoloop` CLI behavior and flags
  - workflow names, routes, artifact names, receipt filenames, and transition behavior
  - `workflow.toml` metadata-only semantics
  - `ctx.invoke_workflow(...)`
  - runtime/provider boundary and provider control-contract behavior
- Internal authoring contract clarified by this cycle:
  - `Context.params` is the preferred typed source for workflow bootstrap/state initialization when `Parameters` exists.
  - `Context.workflow_params` remains available for compatibility and low-level mapping access.
- No runtime-owned bootstrap automation, no hidden sequencing, and no root `workflow` shim expansion are allowed.

## Milestones

1. Freeze the authoring contract and migration surface
   - Update `docs/authoring.md` so the typed-parameter bootstrap rule is explicit.
   - Record the pre-change audit in the touched cycle docs/memory files.
   - Confirm the exact workflow family to migrate and the remaining deferred surfaces.
2. Migrate workflow bootstraps to typed params
   - Replace bootstrap dict unpacking in the selected workflow/task framing/portfolio/governance families with `ctx.params`.
   - Delete redundant generic normalization imports and local validation tails from those bootstraps.
   - Keep session opening, invocation-contract writing, and downstream system-step sequencing explicit in workflow code.
3. Verify behavior and close the cycle
   - Run targeted unit/runtime/doc baseline tests for the touched workflows and helper seams.
   - Update the recursive memory files listed in the request.
   - Record the boilerplate/clarity-budget outcomes and any remaining deferred debt.

## Boilerplate and clarity budget

- Files added: target `0`; allow at most one additive helper file only if migration cannot stay clear by reusing current seams.
- Files deleted: target `0`.
- Net line count: target neutral-to-negative; any positive delta must come from tests/docs rather than new framework machinery.
- Repeated validation idioms to remove:
  - bootstrap-time required string extraction already covered by shared parameter models
  - bootstrap-time optional string normalization already covered by shared parameter models
  - bootstrap-time deduped string-list normalization already covered by shared parameter models
  - bootstrap-time positive-int validation already covered by shared parameter models
- Repeated prompt sections removed or shortened:
  - not primary scope for this cycle; defer unless documentation updates naturally shorten touched guidance
- Workflows changed to use shared helpers/surfaces:
  - the targeted workflow family above should read from `ctx.params`
  - `open_workflow_sessions(...)` and `write_invocation_contract(...)` remain the explicit bootstrap helpers
- New helper functions introduced:
  - ideally none
  - if needed, one additive helper under an existing `stdlib/` module only
- Old workflow-local validation blocks replaced:
  - workflow-local bootstrap dict normalization replaced by runtime-validated typed parameter access
- Core-flow readability before/after:
  - before: bootstraps mix parameter validation, normalization, session setup, and invocation-contract writing
  - after: bootstraps should read as typed state projection plus explicit workflow setup

## Regression prevention and risk register

- Risk: `ctx.params` may not match every existing manual bootstrap normalization path exactly.
  - Control: keep workflow-specific transforms local and add or update targeted tests for optional fields, deduped lists, defaults, and integer normalization.
- Risk: migration could accidentally change persisted `workflow_params` expectations or child-workflow behavior.
  - Control: do not change runtime parameter persistence or `ctx.workflow_params`; only change workflow-internal reads.
- Risk: attempting to fold selected-workflow capture logic into a helper too early could hide topology or artifact boundaries.
  - Control: treat helper extraction as optional and only after the typed-bootstrap migration proves the remaining duplication is still worth abstracting.
- Risk: broad workflow edits could drift docs/tests out of sync.
  - Control: update `docs/authoring.md`, workflow runtime suites, and `tests/test_architecture_baseline_docs.py` in the same change set.

## Validation approach

- Unit coverage:
  - `tests/unit/test_stdlib_and_extensions.py`
  - `tests/unit/test_validation.py`
- Targeted runtime coverage:
  - `tests/runtime/test_task_to_candidate_workflow_set.py`
  - `tests/runtime/test_task_to_workflow_strategy.py`
  - `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
  - `tests/runtime/test_workflow_to_eval_suite.py`
  - `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  - `tests/runtime/test_workflow_portfolio_to_operating_system.py`
  - `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
  - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- Documentation/baseline proof:
  - `tests/test_architecture_baseline_docs.py`
- Compile/compatibility invariant:
  - no CLI, runtime-routing, provider, artifact, or `ctx.invoke_workflow(...)` contract change

## Recursive memory updates required

- Update:
  - `.autoloop_recursive/framework_evolution_charter.md`
  - `.autoloop_recursive/framework_roadmap.md`
  - `.autoloop_recursive/framework_gap_ledger.md`
  - `.autoloop_recursive/workflow_candidate_ledger.md`
  - `.autoloop_recursive/validation_debt_ledger.md`
- Keep the charter update explicit even if the change is only a short synchronization note confirming that the chosen consolidation still fits the standing doctrine.

## Deferred debt after this cycle

- If selected-workflow capture still has noisy duplication after the typed-bootstrap migration, plan a follow-on consolidation under an existing `stdlib/` seam rather than adding another workflow.
- Prompt README boundary prose repetition remains deferred unless the implementation naturally exposes a narrow, documentation-only consolidation that does not compete with the chosen Python authoring-surface cleanup.
