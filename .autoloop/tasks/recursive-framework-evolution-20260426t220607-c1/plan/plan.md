# Recursive Architecture Improvement Cycle 1 Plan

## Cycle Mode

`consolidate`

Rationale:
- No missing workflow capability is blocking the portfolio today.
- The repo still has five workflow bootstraps that re-read `ctx.workflow_params` and manually normalize values even though the typed `Parameters` path already exists and `docs/authoring.md` says `ctx.params` is the default bootstrap surface.
- Finishing that convergence shortens existing workflows, removes repeated normalization, and brings code, docs, tests, and recursive memory back into alignment without widening the runtime or adding a new helper seam.

## Pre-Change Audit

### Most Relevant Existing Workflows / Helpers

1. `core/context.py` plus `runtime/loader.py`
   - `Context.params` already exposes typed workflow parameters and `materialize_workflow_params(...)` / `coerce_workflow_parameter_mapping(...)` already own coercion.
   - Compatibility pressure is to consume that surface, not to add a second bootstrap abstraction.

2. Remaining raw-parameter workflow family
   - `workflows/release_candidate_to_go_no_go/workflow.py`
   - `workflows/investigation_request_to_evidence_pack/workflow.py`
   - `workflows/security_finding_to_verified_remediation/workflow.py`
   - `workflows/incident_to_hardening_program/workflow.py`
   - `workflows/workflow_idea_to_workflow_package/workflow.py`

3. `stdlib/lifecycle.py` and the targeted runtime suites
   - `open_workflow_sessions(...)` and `write_invocation_contract(...)` already make the bootstrap shape explicit and stable.
   - Existing runtime tests already assert invocation-contract and receipt behavior for the affected workflows, so the migration can be proven without changing public behavior.

### Repeated Patterns Found

- Five bootstraps still start from `dict(ctx.workflow_params)` and repeat manual `require_non_empty_string(...)`, `normalize_optional_string(...)`, or `normalize_unique_strings(...)` logic after the `Parameters` model has already normalized the same fields.
- Those workflows then project the normalized values into state and `invocation_contract.json` using the same explicit lifecycle shape the already-migrated families use.
- Recursive memory currently over-claims that typed-bootstrap migration is fully closed, which creates documentation drift against the actual codebase.

### Simplification Opportunity

- Replace the remaining raw bootstrap normalization blocks with direct projection from `ctx.params`.
- Keep workflow-specific validator behavior in each `params.py` file.
- Keep bootstrap logic explicit in workflow code through `open_workflow_sessions(...)` and `write_invocation_contract(...)`.

### New Workflow Necessity

- No new workflow is necessary.
- The active pressure is authoring-surface duplication inside existing workflows, not a missing terminal artifact package.

### What Makes This Family 10x Easier To Author / Read

- One obvious bootstrap shape across all workflows with `Parameters`:
  1. `params = ctx.params`
  2. project typed fields into state
  3. open declared sessions explicitly
  4. write the invocation contract explicitly
- No workflow-local second pass over raw parameter mappings unless the workflow is intentionally using the compatibility dict surface for a separate reason.

### Change / Add / Delete / Merge Decision

- Change existing workflows only.
- No new workflow package.
- No new runtime feature.
- No new helper seam.
- Delete the remaining workflow-local raw bootstrap normalization blocks where they become redundant.

## Candidate Options Considered

1. Finish the remaining typed-bootstrap migration across the older domain workflows and workflow-builder package.
   - Pros: removes clear duplication in five workflows, matches the documented authoring contract, requires no public-interface change, and is likely net-negative in lines.
   - Cons: does not reduce the separate publish-handler verbosity yet.
   - Decision: chosen.

2. Migrate more publish handlers onto typed `JsonArtifactSpec(...)` entrypoints.
   - Pros: could shorten some publication validators.
   - Cons: broader surface, more workflow-specific policy remains local, and several families already depend on different publication invariants; lower leverage than finishing the still-open bootstrap duplication first.
   - Decision: deferred.

3. Add another shared publish-helper seam for selected-workflow or portfolio publication flows.
   - Pros: may reduce some longer publish handlers later.
   - Cons: risks hiding domain policy, adds helper-surface breadth, and the current stdlib already has the narrow seams needed for this cycle.
   - Decision: rejected for this cycle.

## Chosen Improvement

Finish typed-bootstrap convergence in the five remaining workflows that still re-read `ctx.workflow_params`, while preserving all current workflow/runtime/provider boundaries.

### Planned Code Scope

- Migrate these bootstraps to `ctx.params`:
  - `workflows/release_candidate_to_go_no_go/workflow.py`
  - `workflows/investigation_request_to_evidence_pack/workflow.py`
  - `workflows/security_finding_to_verified_remediation/workflow.py`
  - `workflows/incident_to_hardening_program/workflow.py`
  - `workflows/workflow_idea_to_workflow_package/workflow.py`

- Keep these seams unchanged:
  - `core/context.py`
  - `runtime/loader.py`
  - `runtime/cli.py`
  - `ctx.invoke_workflow(...)`
  - `workflow.toml`
  - workflow artifact names, route names, receipt filenames, and prompt files

- Update proof and standing memory:
  - `tests/runtime/test_release_candidate_to_go_no_go.py`
  - `tests/runtime/test_investigation_request_to_evidence_pack.py`
  - `tests/runtime/test_security_finding_to_verified_remediation.py`
  - `tests/runtime/test_incident_to_hardening_program.py`
  - `tests/runtime/test_workflow_builder_package.py`
  - `tests/test_architecture_baseline_docs.py`
  - `.autoloop_recursive/framework_evolution_charter.md`
  - `.autoloop_recursive/framework_roadmap.md`
  - `.autoloop_recursive/framework_gap_ledger.md`
  - `.autoloop_recursive/workflow_candidate_ledger.md`
  - `.autoloop_recursive/validation_debt_ledger.md`

### Expected Implementation Shape

1. Replace each remaining `payload = dict(ctx.workflow_params)` bootstrap with `params = ctx.params`.
2. Project already-typed parameter fields into workflow state without re-normalizing them locally.
3. Preserve current defaults, state reset behavior, session opening, and invocation-contract payload shape.
4. Remove now-unused bootstrap-local normalization code only when it becomes dead.
5. Update recursive memory so the recorded migration scope matches the actual repo state.

## Why This Is Higher Leverage Than A New Workflow

- It improves five existing workflows immediately instead of growing the portfolio.
- It removes a repeated authoring pattern the framework already has a documented answer for.
- It strengthens readability in the top-level flow definitions by making `bootstrap` mechanical and uniform.
- It preserves the narrow runtime boundary and explicit lifecycle helpers instead of adding new machinery.

## Compatibility Notes

- No CLI syntax change.
- No workflow parameter name change.
- No change to `Context.workflow_params`; it remains the compatibility/raw-mapping surface for existing runtime helpers such as `core/worklists.py`.
- No change to `Context.params` behavior beyond consuming it from more workflows.
- No change to artifact names, route names, receipt names, prompt paths, child composition, or publish-step semantics.
- No change to `workflow.toml` semantics.

## Regression-Risk Notes

### Primary Risks

1. Typed bootstrap projection could accidentally change defaults or normalization order.
   - Guardrail: keep existing `Parameters` models authoritative and preserve invocation-contract payload keys and values.

2. Builder-specific or domain-specific validation could be lost if bootstrap code was carrying policy that really belongs in `params.py`.
   - Guardrail: migrate only the duplicated generic normalization; keep package-name, literal normalization, and domain allow-list rules inside the existing parameter models.

3. Recursive memory could continue to drift from actual code.
   - Guardrail: update the five standing memory files in the same slice and keep `tests/test_architecture_baseline_docs.py` aligned.

### Invariants That Must Remain True

- `coerce_workflow_parameter_mapping(...)` remains the only parameter coercion authority.
- `ctx.params` remains the default typed bootstrap surface when `Parameters` exists.
- `ctx.workflow_params` remains available and unchanged as a compatibility dict surface.
- Invocation contracts and publication receipts keep the same filenames and workflow-facing payloads.
- The global CLI and resume behavior remain untouched.

## Validation Strategy

### Targeted Proof

- Run the five affected runtime suites:
  - `tests/runtime/test_release_candidate_to_go_no_go.py`
  - `tests/runtime/test_investigation_request_to_evidence_pack.py`
  - `tests/runtime/test_security_finding_to_verified_remediation.py`
  - `tests/runtime/test_incident_to_hardening_program.py`
  - `tests/runtime/test_workflow_builder_package.py`

- Run the recursive-memory and authoring-boundary baseline:
  - `tests/test_architecture_baseline_docs.py`

### What The Tests Must Prove

- The affected workflows still resolve `Parameters` correctly.
- Invocation-contract JSON output remains compatible after the bootstrap migration.
- Existing publish-step and receipt assertions still pass unchanged unless a test was relying on an implementation detail that the new typed bootstrap intentionally removes.
- Recursive memory now describes the repo truthfully.

## Rollout / Rollback

### Rollout

- Land the migration as one small consolidation slice.
- Keep file scope limited to the five bootstraps, their targeted tests, and recursive memory.

### Rollback

- Revert the five workflow bootstrap edits and the matching test/memory changes together.
- Do not partially roll back only the memory files or only the workflow code, because the current risk is code-memory drift.

## Boilerplate And Clarity Budget

- Files added: expected `0`
- Files deleted: expected `0`
- Net line change: expected small negative
- Repeated validation idioms removed: five raw bootstrap normalization blocks
- Repeated prompt sections removed or shortened: `0`
- Workflows changed to use shared helpers/surfaces: `5` via `Context.params` and existing lifecycle helpers
- New helper functions introduced: expected `0`
- Old workflow-local validation blocks replaced: five bootstrap-local raw parameter normalization blocks
- Core flow readability before/after:
  - Before: `payload = dict(ctx.workflow_params)` plus manual normalization noise
  - After: typed `params` projection plus explicit lifecycle setup

## Recursive Memory Update Requirements

- `framework_evolution_charter.md`
  - Append a concise cycle closeout note that finishing the old-family bootstrap migration stayed authoring-only and did not widen runtime or CLI behavior.

- `framework_roadmap.md`
  - Record the code migration, targeted proof, and cycle metrics.

- `framework_gap_ledger.md`
  - Record that the earlier typed-bootstrap closeout was incomplete in scope and that this cycle closes the remaining old-family/bootstrap residue.

- `workflow_candidate_ledger.md`
  - Record that no new workflow was chosen because the remaining leverage was still consolidation inside existing workflows.

- `validation_debt_ledger.md`
  - Clarify that the earlier resolved bootstrap item covered only part of the portfolio, then mark the old-family residue resolved by this cycle.

## Remaining Deferred Debt

- Older publish handlers that still read raw JSON summaries directly instead of entering through typed artifact specs remain a valid follow-on, but they are secondary to this bootstrap cleanup.
- Longer selected-workflow and governance publish handlers still carry workflow-specific policy locally; do not abstract that further unless a later cycle proves a narrow mechanical seam.
