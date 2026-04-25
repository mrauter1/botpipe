# Recursive Architecture Improvement Cycle 10 Plan

## Cycle Mode And Rationale

- Primary mode: `consolidate`
- Rationale: after the recent validation-convergence cycles, the strongest remaining authoring debt is not another missing workflow. It is the repeated manual JSON summary and manifest parsing inside existing publish handlers, even though the repo already ships a typed JSON-artifact seam in `stdlib/json_artifacts.py` plus Pydantic model-file helpers in `stdlib/validation.py`. Consolidating that seam is higher leverage than expanding the workflow portfolio again.

## Mandatory Inspection Coverage

- Reviewed the authoritative request snapshot, raw log, current plan artifacts, and the latest decision-header block for this turn.
- Reviewed `docs/architecture.md` and `docs/authoring.md`.
- Audited repo-wide structure and relevant behavior across `core/`, `runtime/`, `extensions/`, `stdlib/`, `workflows/`, `tests/`, and `.autoloop_recursive/`.
- Compared the current cycle target against recent recursive-memory closeouts so the plan does not duplicate already-shipped validation or prompt-convergence work.

## Pre-Change Audit Summary

### Most Relevant Existing Workflows / Helpers

1. `stdlib/json_artifacts.py` and `stdlib/validation.py`
   - The repo already has `JsonArtifactSpec`, `read_model_file(...)`, `write_model_file(...)`, and `validate_model_file(...)`, but the seam is only unit-tested and is not yet the default publish-summary authoring path.
2. `workflows/candidate_workflow_to_adapted_execution_plan/{contracts.py,workflow.py}`
   - The publish step manually re-validates `adapted_execution_summary.json` field by field even though the workflow already defines a matching terminal payload model.
3. `workflows/workflow_to_eval_suite/{contracts.py,workflow.py}`
   - The publish step repeats the same untyped summary parsing pattern for `workflow_eval_suite_summary.json` and the validated case manifest.
4. `workflows/task_to_candidate_workflow_set/workflow.py` and `workflows/task_to_workflow_strategy/workflow.py`
   - Both front-door workflow layers keep large manual summary-validation tails around `candidate_workflow_set_summary.json` and `strategy_summary.json`, which makes the core flow harder to scan.

### Repeated Patterns Identified

- Repeated untyped JSON-summary reads in publish handlers:
  `candidate_workflow_to_adapted_execution_plan`, `workflow_to_eval_suite`, `task_to_candidate_workflow_set`, `task_to_workflow_strategy`, and adjacent workflows all call `read_json_object(...)` or `_read_json(...)` and then manually unpack the same fields.
- Repeated field-level summary validation:
  `authoritative_artifacts`, `next_action`, `ready_for_publication` / `ready_for_handoff` / `ready_for_execution`, selected-workflow identity, entry-step names, parameter-support booleans, and case or candidate ID lists are validated by hand in multiple workflows.
- Existing typed seam is underused:
  `JsonArtifactSpec`, `read_model_file(...)`, and `validate_model_file(...)` are present and tested in `tests/unit/test_stdlib_and_extensions.py`, but no current workflow publish handler appears to consume them directly.
- Workflow-local contracts are already close to the published summary shape:
  the `contracts.py` terminal payload models in the scoped workflow family already capture most of the same machine-readable fields that the publish handlers re-parse from the summary artifacts.

### Simplification Opportunity

- Make package summaries and direct-fit manifests first-class typed artifacts.
- Reuse the existing model-file helper seam so publish handlers start from validated Pydantic models rather than raw dictionaries.
- Keep only cross-artifact, state-alignment, text-artifact, and domain-policy checks in workflow code.

### New Workflow Necessity

- No new workflow is necessary.
- The current pressure is inside existing workflow authoring and publish mechanics, so adding another workflow would increase portfolio size without reducing the main readability bottleneck.

### What Would Make This Workflow Family 10x Easier To Author, Read, And Reason About

- A future workflow author should be able to look in one obvious place for each JSON artifact contract: the workflow-local model/spec definition, not a long publish handler full of `summary.get(...)` calls.
- Publish handlers should read like:
  load typed artifacts, enforce cross-artifact invariants, write receipt.
- The builder/front-door/selected-workflow package family should converge on that same authoring pattern before more workflows are added on top of it.

### Cycle Decision

- Change and consolidate existing workflows and helper usage.
- Do not add, split, merge, or retire workflows in this cycle.

## Candidate Options Considered

1. Reuse the existing typed JSON-artifact seam for package summaries and direct-fit manifests
   - Pros: removes repeated manual summary parsing, activates an already-shipped stdlib seam, and shortens the publish handlers on the builder/front-door/selected-workflow path.
   - Cons: requires careful model alignment so typed artifacts do not silently drift from current JSON keys.
   - Decision: chosen.

2. Add a broader publication registry or generic publication framework
   - Pros: could centralize more publish mechanics.
   - Cons: adds new framework machinery, makes the code harder to trace, and risks violating the “prefer consolidation over expansion” bias.
   - Decision: rejected.

3. Add or reshape another workflow instead of consolidating authoring surfaces
   - Pros: expands portfolio coverage.
   - Cons: lower leverage than reducing the repeated publish-summary debt already sitting in existing workflows.
   - Decision: rejected for this cycle.

## Chosen Improvement

- Reuse `stdlib/json_artifacts.py` and the existing model-file helpers as the default authoring seam for package summaries and direct-fit manifests in the scoped workflow family.
- Add or tighten workflow-local typed artifact contracts where the current `contracts.py` terminal payload model does not yet fully match the on-disk JSON artifact shape.
- Migrate the clearest direct-fit publish handlers first:
  - `workflows/task_to_candidate_workflow_set/workflow.py`
  - `workflows/task_to_workflow_strategy/workflow.py`
  - `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
  - `workflows/workflow_to_eval_suite/workflow.py`
- Allow opportunistic follow-on migration only when the fit is obviously mechanical and does not require a new abstraction:
  - `workflows/investigation_request_to_evidence_pack/workflow.py`
  - `workflows/security_finding_to_verified_remediation/workflow.py`
- Keep artifact names, JSON keys, route tags, receipt filenames, CLI behavior, runtime/provider boundaries, and `ctx.invoke_workflow(...)` compatibility unchanged.

## Why This Is Higher Leverage Than A New Workflow

- The scoped workflows sit on the core authoring path for future portfolio work: candidate retrieval, strategy selection, adaptation planning, and evaluation authoring.
- One consolidation pass there reduces repeated code in multiple current workflows and makes future workflows shorter to write.
- The repo already invested in a typed JSON-artifact seam. Activating that seam in real workflows is higher leverage than adding another package while the current authoring surface still ignores it.

## Boilerplate / Repetition To Reduce

- Replace repeated `read_json_object(...)` / `_read_json(...)` plus `summary.get(...)` parsing with typed model reads.
- Delete or shrink workflow-local field-by-field summary validation for:
  - `authoritative_artifacts`
  - `next_action`
  - readiness booleans
  - selected-workflow entry-step and parameter-support fields
  - comparison-candidate and recommended-workflow lists where the artifact model already owns the schema
- Move the obvious JSON artifact contract closer to `contracts.py` or another workflow-local typed spec surface so the publish handler focuses on cross-artifact and state checks.

## Shared Helper / Contract Simplification

- Prefer reusing the existing helper seam:
  - `JsonArtifactSpec`
  - `read_model_file(...)`
  - `write_model_file(...)`
  - `validate_model_file(...)`
- Keep cycle-9 publication-validation helpers for mechanical boundary and hidden-execution checks where they already fit; typed artifact adoption should complement that seam, not replace it.
- Only add a new stdlib helper if migration exposes a direct mechanical gap that cannot be handled cleanly by the current seam.
- Do not add a root `workflow` primitive, runtime-owned publication policy, or a generic publication registry.

## Workflows Simplified Or Made Clearer

- `task_to_candidate_workflow_set`
  - summary parsing should collapse to a typed summary read plus candidate-ranking policy checks.
- `task_to_workflow_strategy`
  - summary parsing should collapse to a typed strategy summary read plus child-summary alignment and route-policy checks.
- `candidate_workflow_to_adapted_execution_plan`
  - summary parsing should collapse to a typed adapted-execution summary read plus validated-parameter and selected-workflow cross-checks.
- `workflow_to_eval_suite`
  - summary and direct-fit manifest parsing should collapse to typed model reads plus case-coverage and selected-workflow cross-checks.

## Interfaces And Expected Touch Points

### Shared Seam

- `stdlib/json_artifacts.py`
- `stdlib/validation.py`
- `stdlib/__init__.py` only if a migrated workflow needs an additional public stdlib export for the already-existing model-file seam

### Workflow-Local Contracts And Migrations

- `workflows/task_to_candidate_workflow_set/contracts.py`
- `workflows/task_to_candidate_workflow_set/workflow.py`
- `workflows/task_to_workflow_strategy/contracts.py`
- `workflows/task_to_workflow_strategy/workflow.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/contracts.py`
- `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
- `workflows/workflow_to_eval_suite/contracts.py`
- `workflows/workflow_to_eval_suite/workflow.py`

### Docs, Tests, And Recursive Memory

- `docs/authoring.md`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/runtime/test_task_to_candidate_workflow_set.py`
- `tests/runtime/test_task_to_workflow_strategy.py`
- `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
- `tests/runtime/test_workflow_to_eval_suite.py`
- `tests/test_architecture_baseline_docs.py`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `.autoloop_recursive/validation_debt_ledger.md`

## Proposed Boundary

### Shared Responsibilities

- typed JSON read/write/validate for workflow-local artifacts
- model-level schema validation for package summaries and direct-fit manifests
- additive helper usage only; no hidden sequencing or runtime-owned behavior

### Workflow-Local Responsibilities That Must Stay Local

- state-drift and child-summary alignment checks
- selected-workflow identity alignment beyond generic model shape
- package-specific domain assertions and allow-lists
- text-artifact content checks
- hidden-execution policy checks where they remain workflow-specific
- receipt payload shaping and terminal artifact naming

## Milestones

### Milestone 1: Typed Artifact Contracts

- Align the scoped workflow family’s package summaries and direct-fit manifests with explicit workflow-local typed contracts.
- Reuse the existing model-file seam instead of introducing a parallel helper pattern.
- Add only the smallest shared helper change if the current seam has a direct ergonomic hole.

### Milestone 2: Publish-Handler Migration

- Refactor the four scoped publish handlers to consume typed model artifacts.
- Delete replaced manual JSON-summary parsing blocks where the typed seam fully covers them.
- Preserve all artifact filenames, summary keys, receipt names, route tags, and external behavior.

### Milestone 3: Docs, Recursive Memory, And Proof

- Update `docs/authoring.md` to document the typed JSON artifact authoring pattern and its non-goals.
- Update all five standing recursive-memory files, including an explicit charter no-doctrine-change note if doctrine itself stays unchanged.
- Run targeted proof and record closeout accounting for repetition removed and compatibility preserved.

## Compatibility And Regression Controls

- Preserve current artifact filenames and top-level JSON key names for every migrated summary or manifest.
- Preserve CLI behavior, runtime/provider boundaries, prompt paths, `workflow.toml` semantics, and `ctx.invoke_workflow(...)` compatibility.
- Do not move workflow-domain policy into stdlib or runtime layers.
- Keep error-surface drift low where tests or downstream workflows may rely on current publish-time failures.
- Reject any migration that requires a larger framework abstraction just to make the typed seam fit.

## Tests And Validation Plan

### Focused Unit Proof

- `tests/unit/test_stdlib_and_extensions.py`
- `tests/unit/test_validation.py` only if the existing model-file helper seam or validation exports change

### Targeted Runtime Proof

- `tests/runtime/test_task_to_candidate_workflow_set.py`
- `tests/runtime/test_task_to_workflow_strategy.py`
- `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
- `tests/runtime/test_workflow_to_eval_suite.py`

### Docs / Boundary Guardrail

- `tests/test_architecture_baseline_docs.py`

### Optional Opportunistic Proof

- If the migration expands into the older domain publish family, run the matching runtime suites in the same change instead of assuming direct equivalence.

## Risk Register

1. Risk: typed artifact models drift from the current on-disk JSON shape
   - Control: preserve filenames and keys, add targeted runtime proof, and prefer direct reuse of the current terminal payload shape where possible.
2. Risk: migration hides workflow-specific policy inside over-generalized helpers
   - Control: keep typed models workflow-local and keep cross-artifact/state assertions inside the workflow publish handler.
3. Risk: manual validation is deleted too aggressively and subtle cross-artifact checks disappear
   - Control: migrate only the direct-fit schema validation into typed artifacts; keep state, child-summary, and selected-workflow alignment checks explicit.
4. Risk: new helper additions expand the framework surface more than the simplification justifies
   - Control: default to existing `JsonArtifactSpec` and model-file helpers; require a direct mechanical gap before adding anything new.

## Boilerplate / Clarity Budget To Report At Closeout

- files added
- files deleted
- net line count change if practical
- repeated manual summary-validation idioms removed
- workflows changed to use typed JSON artifact contracts
- whether any new helper functions were introduced or whether the existing seam was sufficient
- old workflow-local parsing blocks replaced
- publish-handler readability before and after

Expected qualitative outcome:

- the scoped publish handlers become shorter and more obviously domain-focused
- `contracts.py` or adjacent workflow-local typed specs become the obvious JSON artifact contract surface
- no new workflow is added
- the cycle strengthens authoring leverage without widening runtime or root-shim behavior

## Tests, Docs, And Recursive Memory Updates Required At Closeout

- Update `docs/authoring.md`.
- Update all five standing recursive-memory files listed in the request.
- Record either a charter doctrine change or an explicit no-doctrine-change note in `.autoloop_recursive/framework_evolution_charter.md`.
- Record the chosen cycle mode, preserved compatibility, boilerplate reduction, and deferred debt consistently across closeout notes.

## Remaining Deferred Validation Debt Or Portfolio-Shape Debt

- governance and diagnostic summary-model adoption if the typed seam proves clean in the first migration wave
- older domain publish-summary migration if the direct-fit family lands without abstraction debt
- any remaining workflow-local summary shapes whose current artifact contract does not align cleanly with an existing terminal payload model
- workflow portfolio shaping remains deferred until the current builder/front-door/selected-workflow authoring surfaces are shorter and easier to reason about
