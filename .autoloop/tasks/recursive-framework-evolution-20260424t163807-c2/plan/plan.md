# Recursive Framework Evolution Cycle 2 Plan

## Cycle mode

`consolidate`

Rationale:
- Cycle 13 already proved the shared workflow-validation seam on the newer workflow family and left one explicit follow-on debt item: the older domain workflow wave.
- The repo does not have a workflow-portfolio gap that is higher leverage than removing duplicated validation tails from four existing workflows.
- This improvement can shorten existing workflow files, reduce repeated helper noise, and improve testability without widening runtime-owned behavior or adding a new workflow.

## Pre-change audit summary

### Most relevant existing workflows/helpers

1. `stdlib/validation.py`
   - Existing shared seam for generic JSON/string/list/mapping/int validation.
2. `workflows/investigation_request_to_evidence_pack/workflow.py`
   - Oldest remaining workflow with a full tail of workflow-local generic validators.
3. `workflows/security_finding_to_verified_remediation/workflow.py`
   - Most validation-heavy remaining consumer, including child-artifact publish checks that must stay domain-local.

Corroborating repeats checked:
- `workflows/release_candidate_to_go_no_go/workflow.py`
- `workflows/incident_to_hardening_program/workflow.py`
- `stdlib/company.py`
- `stdlib/diagnostics.py`
- `stdlib/portfolio.py`

### Repeated patterns found

- Workflow-local copies of generic helpers such as `_require_text`, `_normalize_optional_text`, `_normalize_unique_strings` / `_normalize_evidence_paths`, `_read_json`, `_require_string_list`, `_normalize_string_list`, and non-negative integer checks remain in the four older domain workflows.
- Three stdlib snapshot helpers still repeat string-filter normalization with local `_require_text` helpers instead of consuming the shared validation seam.
- `params.py` models across many workflows still repeat similar Pydantic validators, but that is a separate authoring-surface cleanup from the more urgent workflow readability debt.

### Simplification opportunity

- Finish the validation migration wave by extending `stdlib/validation.py` only where a missing generic primitive is still needed, then delete the generic helper tails from the four older domain workflows.
- Reuse the same shared validation seam for `stdlib/company.py`, `stdlib/diagnostics.py`, and `stdlib/portfolio.py` if that cleanup stays mechanical and does not add another abstraction.

### New workflow necessity

- No new workflow is necessary.
- The current pressure is consolidation of existing authoring surfaces, not missing workflow coverage.
- Adding a workflow in this cycle would increase portfolio size while leaving a known cross-workflow readability defect unresolved.

### What makes this workflow family 10x easier to author/read/reason about

- Keep top-level workflow files focused on state changes, artifact contracts, child-composition behavior, and domain-specific publication assertions.
- Move only generic validation mechanics into `stdlib/validation.py`.
- Delete local helper tails so bootstrap and publish handlers read as one obvious control flow instead of mixing domain logic with repeated parsing utilities.

### Change decision

- Change and consolidate existing helpers/workflows.
- Delete workflow-local generic validation tails where the shared seam is sufficient.
- Do not add or retire workflows in this cycle.

## Candidate options considered

1. Migrate the four older domain workflows to the shared validation seam and optionally clean up matching stdlib snapshot filters.
   - Pros: directly resolves the only active validation-debt item, improves readability in existing workflows, and reduces repeated helper code across both workflows and stdlib helper modules.
   - Cons: touches several mature workflows, so regression proof must stay tight.
   - Decision: chosen.

2. Extract shared Pydantic parameter validators across `workflows/*/params.py`.
   - Pros: would reduce authoring boilerplate across many workflows.
   - Cons: lower immediate leverage than the already-recorded workflow-local validation debt; risks broad churn in coercion error messages and parameter-model readability.
   - Decision: deferred.

3. Compact prompt-template wording across existing workflows.
   - Pros: could improve authoring-surface elegance.
   - Cons: prompt shape is not the current highest-risk duplication point, and the existing docs/tests already preserve the current provider-facing contract style.
   - Decision: deferred.

## Chosen improvement

Finish the validation-consolidation wave for the older domain workflow family:

- Extend `stdlib/validation.py` only for generic mechanics still missing from the shared seam.
- Migrate these workflows off workflow-local generic helpers:
  - `investigation_request_to_evidence_pack`
  - `security_finding_to_verified_remediation`
  - `release_candidate_to_go_no_go`
  - `incident_to_hardening_program`
- Keep domain-specific publication rules local:
  - investigation kind alignment
  - selected remediation semantics
  - evidence-pack child-result adoption rules
  - domain-specific summary/receipt invariants
- Apply the same seam to `stdlib/company.py`, `stdlib/diagnostics.py`, and `stdlib/portfolio.py` only if it remains a direct replacement of duplicated normalization logic.

## Scope and milestones

### Milestone 1: shared validation seam and workflow migration

- Add any missing generic helper(s) required by the old domain workflows to `stdlib/validation.py`.
- Replace workflow-local generic validation helpers in the four domain workflows with shared imports and direct calls.
- Keep all workflow routes, artifact names, prompt paths, and publication receipt filenames unchanged.
- Preserve `ctx.invoke_workflow(...)` behavior and existing child-workflow composition semantics.

### Milestone 2: regression proof, docs, and recursive-memory sync

- Update tests to cover any newly shared generic helper behavior and the migrated workflow paths.
- Update `docs/authoring.md` only as needed to reflect the completed migration and keep the workflow/runtime/provider boundary crisp.
- Update recursive memory files:
  - `.autoloop_recursive/framework_roadmap.md`
  - `.autoloop_recursive/framework_gap_ledger.md`
  - `.autoloop_recursive/workflow_candidate_ledger.md`
  - `.autoloop_recursive/validation_debt_ledger.md`
- Record boilerplate reduction and remaining deferred debt in the implementation closeout.

## Interfaces and compatibility constraints

- No CLI changes.
- No runtime-owned routing or validation policy expansion.
- No new root `workflow` exports.
- No new workflow package.
- No new `workflow.toml` semantic fields.
- Preserve existing workflow artifact names, receipt names, route names, expected output schemas, and composition entry points.
- Shared helpers must remain additive under `stdlib/validation.py`; workflow-specific publication semantics stay in workflow code.

## Regression-risk notes

1. Validation strictness drift
   - Risk: shared helpers could reject values that the old local helpers previously tolerated, or could change error messages that tests rely on.
   - Control: preserve accepted valid shapes, keep targeted negative-path tests, and only tighten behavior when the workflow already expects the stricter shape.

2. Domain-vs-generic boundary drift
   - Risk: migrating too aggressively could move publication semantics into stdlib.
   - Control: only move generic parsing/shape checks; keep all workflow-specific invariants in the workflow publish steps.

3. Snapshot-helper scope creep
   - Risk: cleaning up `stdlib/company.py`, `stdlib/diagnostics.py`, and `stdlib/portfolio.py` could introduce a second abstraction project.
   - Control: treat that cleanup as bounded and optional within the same seam; skip it if it requires a new authoring surface.

## Validation strategy

Targeted proof should cover:

- `tests/unit/test_validation.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/runtime/test_investigation_request_to_evidence_pack.py`
- `tests/runtime/test_security_finding_to_verified_remediation.py`
- `tests/runtime/test_release_candidate_to_go_no_go.py`
- `tests/runtime/test_incident_to_hardening_program.py`
- `tests/test_architecture_baseline_docs.py` if docs are touched

Validation focus:
- bootstrap parameter normalization remains compatible
- publish-step receipts keep the same artifact contract
- child-workflow adoption in security remediation remains explicit and deterministic
- no workflow gains hidden runtime behavior

## Rollback

- Revert the shared-helper additions and the four workflow migrations together if runtime proof shows artifact or publish-validation regressions.
- If the optional stdlib snapshot-helper cleanup causes drift, revert those helper-module changes independently and keep the workflow migration.
- Do not retain partially migrated workflows that mix old local validators and new shared helpers inconsistently.

## Boilerplate and clarity budget target

- Files added: `0` expected.
- Files deleted: `0` expected.
- Net line change: negative expected; helper deletion should outweigh any small shared-helper additions.
- Repeated validation idioms removed: workflow-local non-empty string, optional string, repeatable string, JSON-object, string-list, and non-negative integer checks.
- Repeated prompt sections removed or shortened: none planned.
- Workflows changed to use shared helpers: the four older domain workflows above.
- New helper functions introduced: only generic `stdlib/validation.py` additions strictly required to complete the migration.
- Old workflow-local validation blocks replaced: yes, in each touched older domain workflow.
- Core flow readability before/after: top-level workflow files should end with little or no generic validation tail, making bootstrap and publish behavior easier to scan.

## Deferred debt after this cycle

- Cross-workflow `params.py` validator deduplication remains a distinct authoring-surface follow-on and should be evaluated separately from this workflow-local validation migration.
- Prompt-table compaction remains deferred unless future cycles show prompt verbosity, not validation duplication, as the dominant authoring cost.
- Any decision to migrate `release_candidate_to_go_no_go` or `incident_to_hardening_program` further toward reusable building blocks remains separate from this consolidation slice.
