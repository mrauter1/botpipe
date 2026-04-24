# Recursive Framework Evolution Cycle 3 Plan

## Cycle mode

`consolidate`

Rationale:
- Cycle 14 closed the workflow-local validation migration wave and explicitly left `params.py` validator deduplication as the next authoring-surface comparison point.
- The repo already has broad workflow coverage; the highest-leverage remaining pressure is repeated Pydantic validator boilerplate across existing workflow parameter models.
- This improvement can shorten nearly every package's parameter surface, keep author intent visible, and avoid adding another workflow or runtime seam.

## Pre-change audit summary

### Most relevant existing workflows/helpers

1. `stdlib/validation.py`
   - Existing shared home for generic string/list/mapping/int validation and the narrowest place to add additive parameter-model helpers.
2. `workflows/task_to_workflow_strategy/params.py`
   - Canonical front-door parameter surface that matches the repeated `task_title` / optional text / deduped list pattern used across the selected-workflow family.
3. `workflows/company_operation_to_recursive_improvement_cycle/params.py`
   - Richest current parameter model with repeated string-list normalization plus repeated positive-int checks that can prove the helper seam scales without widening runtime behavior.

Corroborating repeats checked:
- All `14` current `workflows/*/params.py` files
- `runtime/loader.py`
- `docs/authoring.md`
- `tests/runtime/test_*` workflow suites that validate parameter coercion
- `tests/unit/test_validation.py`
- `tests/unit/test_stdlib_and_extensions.py`

### Repeated patterns found

- `14` `params.py` files still normalize repeatable string fields with near-identical `field_validator(...)` loops that strip, drop empties, and dedupe while preserving order.
- `13` `params.py` files still hand-roll required non-empty text validators for titles, workflow names, or path-like string fields.
- `12` `params.py` files still repeat optional-text trimming for sponsor and outcome style fields.
- `3` `params.py` files still hand-roll positive-int checks for bounded snapshot filters.
- Only a small subset of validators are truly workflow-specific:
  - package identifier rules in `workflow_idea_to_workflow_package`
  - hyphen-to-underscore normalization for `authoring_shape`
  - pre-normalization for literal enum inputs in the investigation and security workflows
  - sorted status-filter output where ordering is semantically intentional

### Simplification opportunity

- Add one additive parameter-validator helper layer in `stdlib/validation.py` that wraps the existing generic validation primitives for Pydantic `field_validator(...)` use.
- Keep field lists explicit inside each `Parameters` model so the local schema remains readable, while deleting the repeated helper bodies.
- Leave only domain-specific normalization logic in the few workflows that truly need custom behavior.

### New workflow necessity

- No new workflow is necessary.
- The pressure is authoring-surface repetition inside existing packages, not a missing terminal workflow outcome.
- Adding a workflow in this cycle would increase portfolio size while leaving an active cross-workflow readability defect untouched.

### What makes this workflow family 10x easier to author/read/reason about

- Future `params.py` files should read mostly as field declarations plus a small number of workflow-specific exceptions.
- Shared helper-generated validators should replace 8 to 20 lines of repeated boilerplate at a time without hiding parameter names or moving coercion policy into runtime code.
- Workflow authors should be able to reuse the same narrow helper seam the way workflow-local artifact validation already reuses `stdlib/validation.py`.

### Change decision

- Change and consolidate existing helper usage across `params.py`.
- Delete repeated workflow-local parameter validator blocks where the shared seam is sufficient.
- Do not add, merge, split, or retire workflows in this cycle.

## Candidate options considered

1. Deduplicate `params.py` validators across the workflow portfolio with additive helper factories in `stdlib/validation.py`.
   - Pros: directly resolves the one active deferred validation-debt item, shortens authoring surfaces across `14` packages, and keeps the root `workflow` and runtime contracts unchanged.
   - Cons: touches many parameter models, so error wording and coercion behavior need tight regression proof.
   - Decision: chosen.

2. Add a new `stdlib/params.py` module for Pydantic-specific helpers.
   - Pros: keeps parameter-model helpers physically separate from the existing validation primitives.
   - Cons: adds a new seam when `stdlib/validation.py` already owns the relevant generic logic and already has Pydantic-aware utilities; increases surface area for a cleanup whose goal is consolidation.
   - Decision: rejected.

3. Compact prompt contracts or add a new remediation-oriented building block instead.
   - Pros: prompt compaction could improve provider-facing readability, and a new building block could expand portfolio utility.
   - Cons: both are lower leverage than removing repeated validator boilerplate that every future workflow author still pays today.
   - Decision: deferred.

## Chosen improvement

Deduplicate workflow parameter-model validators without changing the runtime parameter-coercion path:

- Extend `stdlib/validation.py` and `stdlib/__init__.py` with additive helper factories or helper-wired validator callables for the repeated `Parameters`-model patterns:
  - required non-empty strings
  - optional trimmed strings
  - deduped repeatable string lists
  - positive integers
- Reuse those helpers across the current workflow portfolio:
  - `workflow_idea_to_workflow_package`
  - `release_candidate_to_go_no_go`
  - `incident_to_hardening_program`
  - `investigation_request_to_evidence_pack`
  - `security_finding_to_verified_remediation`
  - `task_to_candidate_workflow_set`
  - `task_to_workflow_strategy`
  - `candidate_workflow_to_adapted_execution_plan`
  - `workflow_to_eval_suite`
  - `workflow_run_history_to_failure_modes`
  - `workflow_portfolio_to_operating_system`
  - `company_operation_to_recursive_improvement_cycle`
  - `workflow_and_eval_to_refined_workflow_package`
  - `workflow_package_to_composable_building_blocks`
- Keep these validators local because they carry workflow-specific naming or enum policy:
  - `package_name` identifier validation
  - `authoring_shape` normalization and allow-list enforcement
  - literal-input trimming for investigation/security enums where the local field semantics stay clearer inline
  - any status ordering behavior that is intentionally sorted rather than order-preserving

## Why this is higher leverage than a new workflow

- It removes authoring friction from almost every current workflow package at once instead of adding one more package to maintain.
- It improves the builder-era baseline for future workflows by making parameter surfaces shorter, clearer, and more uniform.
- It follows the standing preference order after cycle 14: compare new workflow ideas against authoring-surface cleanup before expanding the portfolio again.

## Scope and milestones

### Milestone 1: shared parameter-validator seam

- Add the smallest possible helper surface to `stdlib/validation.py` for reusable Pydantic field validators backed by the existing generic primitives.
- Re-export the helper surface from `stdlib/__init__.py`.
- Freeze helper behavior in unit tests before broad workflow migration.
- Keep the helper seam additive and authoring-only; do not change `runtime/loader.py` coercion ownership.

### Milestone 2: params model migration and closeout

- Migrate the `14` workflow `params.py` files to the shared seam where the behavior is generic.
- Leave genuinely workflow-specific validation inline and visible.
- Update `docs/authoring.md` to document the new boundary for parameter-model authoring.
- Update targeted runtime tests and recursive-memory files:
  - `.autoloop_recursive/framework_evolution_charter.md`
  - `.autoloop_recursive/framework_roadmap.md`
  - `.autoloop_recursive/framework_gap_ledger.md`
  - `.autoloop_recursive/workflow_candidate_ledger.md`
  - `.autoloop_recursive/validation_debt_ledger.md`
- Record boilerplate reduction, workflows migrated, and any intentionally deferred parameter-validation edge cases in implementation closeout.

## Interfaces and compatibility constraints

- No CLI changes.
- No runtime-owned parameter normalization or hidden workflow policy.
- No root `workflow` import-surface expansion.
- No new `workflow.toml` semantic fields.
- No new workflow package.
- Preserve workflow parameter names, defaults, repeatability, and current loader entry points.
- Preserve the runtime-owned parameter coercion boundary in `runtime/loader.py`; the new helpers only shorten workflow-local `Parameters` definitions.

## Regression-risk notes

1. Pydantic error-wording drift
   - Risk: helper-generated validators could change validation messages that current tests assert against.
   - Control: keep targeted negative-path tests for representative workflows and avoid rewriting domain-specific error messages that are already intentional.

2. Over-abstraction of local schema intent
   - Risk: an overly clever helper API could hide which fields are required, optional, repeated, or order-sensitive.
   - Control: keep field names explicit in each `Parameters` file and limit the seam to a few obvious validator shapes.

3. Behavior drift in sorted or enum-normalized fields
   - Risk: status sorting, identifier checks, or literal pre-normalization could change if forced through a too-generic helper.
   - Control: keep those cases local unless the shared helper can preserve the existing semantics exactly.

## Validation strategy

Targeted proof should cover:

- `tests/unit/test_validation.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/runtime/test_workflow_builder_package.py`
- `tests/runtime/test_release_candidate_to_go_no_go.py`
- `tests/runtime/test_incident_to_hardening_program.py`
- `tests/runtime/test_investigation_request_to_evidence_pack.py`
- `tests/runtime/test_security_finding_to_verified_remediation.py`
- `tests/runtime/test_task_to_candidate_workflow_set.py`
- `tests/runtime/test_task_to_workflow_strategy.py`
- `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
- `tests/runtime/test_workflow_to_eval_suite.py`
- `tests/runtime/test_workflow_run_history_to_failure_modes.py`
- `tests/runtime/test_workflow_portfolio_to_operating_system.py`
- `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
- `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `tests/test_architecture_baseline_docs.py` if docs or recursive-memory files are updated

Validation focus:
- helper-generated validators preserve existing accepted valid inputs
- repeated list fields still dedupe and preserve intended ordering
- positive-int filters keep the same acceptance boundary
- workflow-specific local validators still handle identifier and literal-specific rules
- no CLI, runtime-routing, or `ctx.invoke_workflow(...)` contract changes occur

## Rollback

- Revert the shared helper additions and the `params.py` migrations together if targeted proof shows coercion regressions or error-surface drift that is larger than the cleanup warrants.
- Revert docs and recursive-memory updates independently if implementation scope or proof results change before closeout.
- Do not leave the repo in a split state where some parameter models use the shared seam and others still copy the same generic validator bodies without clear justification.

## Boilerplate and clarity budget target

- Files added: `0` expected.
- Files deleted: `0` expected.
- Net line change: negative expected; helper additions should be smaller than the repeated validator bodies removed from `14` parameter files.
- Repeated validation idioms removed:
  - required non-empty string validators
  - optional trimmed string validators
  - deduped repeatable string-list validators
  - repeated positive-int validators
- Repeated prompt sections removed or shortened: none planned.
- Workflows changed to use shared helpers: all `14` current workflow `params.py` files, except for any intentionally preserved workflow-specific validators within those files.
- New helper functions introduced: only the minimum additive Pydantic-oriented validator helpers needed in `stdlib/validation.py`.
- Old workflow-local validation blocks replaced: yes, in `workflows/*/params.py`.
- Core flow readability before/after:
  - before: each `Parameters` file re-implements the same trimming and dedupe loops
  - after: each `Parameters` file is mostly schema plus local exceptions, with generic mechanics imported from stdlib

## Deferred debt after this cycle

- Prompt-contract compression remains the next clear authoring-surface comparison point once parameter-model duplication is removed.
- Reusable assessment/remediation building blocks remain deferred portfolio-shape work; they should be reconsidered only after this smaller authoring cleanup is complete.
- Investigation/security literal pre-normalization and workflow-builder-specific naming rules should remain local unless a later cycle finds a stable generic pattern without making the helper seam less obvious.
