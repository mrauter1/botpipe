# Recursive Architecture Improvement Cycle 9 Plan

## Cycle Mode And Rationale

- Primary mode: `consolidate`
- Rationale: the highest-leverage remaining authoring debt is no longer missing workflows or prompt scaffolding; it is repeated mechanical publish-handler logic across existing governance and diagnostic workflows. That duplication makes the core flow harder to read, hides domain policy inside long publication validators, and is a better target than any new workflow in this cycle.

## Pre-Change Audit Summary

### Most Relevant Existing Workflows / Helpers

1. `workflows/workflow_portfolio_to_operating_system/workflow.py`
   - Long publish handler mixes governance-specific checks with repeated mechanical publication checks, required-artifact existence loops, and hidden-execution validation.
2. `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`
   - Carries nearly the same publication-boundary and hidden-execution machinery as the portfolio-governance workflow, plus duplicated snapshot-extraction helpers.
3. `workflows/workflow_run_history_to_failure_modes/workflow.py`
   - Uses the same publish-step structure and publication-boundary concept, but with a narrower local hidden-execution implementation and repeated text/required-artifact checks.
4. Supporting helpers already in play:
   - `stdlib/validation.py`
   - `stdlib/lifecycle.py`
   - `stdlib/portfolio.py`
   - `stdlib/company.py`
   - `stdlib/diagnostics.py`

### Repeated Patterns Identified

- Repeated required publication artifact checks:
  each publish step constructs a `required_paths` mapping, loops over it, and raises the same `missing required publication artifact` error.
- Repeated text-artifact guards:
  multiple workflows keep local `_read_required_text(...)` helpers.
- Repeated publication-summary mechanics:
  `authoritative_artifacts` subset checks, `next_action` non-empty checks, and `ready_for_publication` / `ready_for_handoff` / `ready_for_strategy_selection` flag checks recur across the family.
- Repeated publication-boundary enforcement:
  `workflow_portfolio_to_operating_system` and `company_operation_to_recursive_improvement_cycle` duplicate the same hidden-downstream-execution regex sets and text-policy helpers; `workflow_run_history_to_failure_modes` enforces the same policy with a narrower local check.
- Repeated scoped-snapshot extraction:
  `workflow_portfolio_to_operating_system` and `company_operation_to_recursive_improvement_cycle` duplicate `_workflow_names_from_capability_snapshot(...)` and `_extract_portfolio_workflow_names(...)`.

### Simplification Opportunity

- Extract mechanical publication validation into existing stdlib validation seams so publish handlers keep only domain assertions:
  lifecycle posture semantics, recursive-improvement priority semantics, and run-history evidence semantics remain workflow-local; file existence, non-empty text reads, publication-boundary enforcement, and hidden-execution detection become shared.

### New Workflow Necessity

- No new workflow is necessary.
- The observed pressure is inside existing workflow publish handlers and authoring helpers, so expansion would increase portfolio size without addressing the current readability bottleneck.

### What Would Make This Workflow Family 10x Easier To Author / Read

- Publish handlers should read like: load required artifacts, validate domain-specific invariants, emit receipt.
- Mechanical guards should move behind shared helpers so the top-level flow shows the real business logic instead of long blocks of repetitive validation plumbing.

### Cycle Decision

- Change and consolidate existing workflows/helpers.
- Do not add, split, or retire workflows in this cycle.

## Candidate Options Considered

1. Shared publication-boundary and publish-handler validation seam for governance / diagnostic workflows
   - Pros: removes repeated mechanics from the longest publish handlers, keeps domain policy explicit, and improves the clearest current readability bottleneck.
   - Cons: requires careful helper boundaries so workflow-specific policy is not over-generalized.
   - Decision: chosen.

2. Further prompt/doc compaction in the same workflow family
   - Pros: low runtime risk.
   - Cons: prompt scaffolding debt is already substantially reduced; current duplication pressure is more in Python publish handlers than in prompt text.
   - Decision: deferred.

3. Add or migrate another workflow/building block
   - Pros: expands portfolio capability.
   - Cons: conflicts with the cycle’s consolidation bias and leaves current publish-handler repetition in place.
   - Decision: rejected for this cycle.

## Chosen Improvement

- Introduce additive shared publication-validation helpers in existing stdlib validation seams.
- Migrate the governance/diagnostic workflow family to those helpers first:
  - `workflow_portfolio_to_operating_system`
  - `company_operation_to_recursive_improvement_cycle`
  - `workflow_run_history_to_failure_modes`
- Reuse the new helpers opportunistically in adjacent publish handlers only if the fit is direct and mechanical:
  - `task_to_candidate_workflow_set`
  - `task_to_workflow_strategy`
  - `candidate_workflow_to_adapted_execution_plan`
  - `workflow_to_eval_suite`
  The cycle should not force over-generalization just to widen the migration set.

## Proposed Helper Boundary

### Shared Responsibilities

- workflow-local required-artifact existence checks returning resolved paths
- non-empty required text-artifact reads
- publication-boundary string validation
- hidden downstream execution detection with shared negation handling
- reusable authoritative-artifact subset validation
- reusable readiness-flag validation for summary payloads when the check is purely mechanical

### Workflow-Local Responsibilities That Must Stay Local

- lifecycle posture, change-candidate, and priority semantics
- recursive-improvement candidate/category policy
- selected-workflow and run-history evidence alignment beyond already-shared helpers
- receipt payload shaping and terminal artifact naming
- any workflow-specific error wording that explains domain semantics rather than generic mechanics

### Placement Constraints

- Prefer `stdlib/validation.py` for validation mechanics.
- Keep `stdlib/lifecycle.py` limited to writing/opening helpers unless a change is strictly about workflow-local JSON artifact IO.
- Do not add runtime-owned policy, hidden routing, root `workflow` surface expansion, or new semantic `workflow.toml` fields.

## Milestones

### Milestone 1: Shared Publication Validation Helpers

- Add the minimal shared helper surface for publish-step mechanics.
- Freeze it with focused unit coverage.
- Keep helper inputs explicit and additive; do not build a generic publication framework or registry.

### Milestone 2: Workflow Migration

- Refactor the three scoped workflows to use the shared helpers.
- Remove duplicated local helper tails when the shared seam fully replaces them.
- Preserve artifact names, receipt filenames, route names, and publish-step behavior.

### Milestone 3: Docs, Recursive Memory, And Proof

- Update `docs/authoring.md` to document the new helper boundary.
- Update recursive memory:
  - `.autoloop_recursive/framework_evolution_charter.md`
  - `.autoloop_recursive/framework_roadmap.md`
  - `.autoloop_recursive/framework_gap_ledger.md`
  - `.autoloop_recursive/workflow_candidate_ledger.md`
  - `.autoloop_recursive/validation_debt_ledger.md`
- In `.autoloop_recursive/framework_evolution_charter.md`, record either the doctrine change itself or an explicit no-doctrine-change closeout note for cycle 9 so the standing memory requirement is satisfied visibly.
- Run targeted proof and record closeout accounting.

## Compatibility And Regression Controls

- Preserve CLI behavior in `runtime/cli.py` and runtime execution behavior in `runtime/runner.py`.
- Preserve `ctx.invoke_workflow(...)` compatibility and child-workflow composition behavior.
- Preserve workflow artifact names, summary filenames, receipt filenames, and route tags.
- Preserve prompt paths and workflow package layout.
- Keep helpers additive and stdlib-owned; do not move policy into runtime or provider layers.
- Treat error-message drift as a regression risk where tests assert exact publish-time failures.

## Tests And Validation Plan

### Unit / Helper Proof

- `tests/unit/test_validation.py`
- `tests/unit/test_stdlib_and_extensions.py`

### Targeted Runtime Proof

- `tests/runtime/test_workflow_portfolio_to_operating_system.py`
- `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
- `tests/runtime/test_workflow_run_history_to_failure_modes.py`

### Broader Contract / Docs Guardrails

- `tests/test_architecture_baseline_docs.py`

### Optional Opportunistic Follow-On Proof

- If helper fit is expanded to adjacent publish handlers, add the relevant runtime suites for those workflows in the same change rather than relying on inference.

## Risk Register

1. Risk: helper over-generalization hides workflow policy
   - Control: keep only mechanical publication checks shared; leave domain semantics local.
2. Risk: hidden-execution detection behavior drifts during deduplication
   - Control: preserve current regex/negation behavior with direct unit tests and targeted runtime regressions.
3. Risk: publish-time error surfaces change unintentionally
   - Control: retain existing artifact names and failure conditions; update helpers to support existing wording where tests pin it.
4. Risk: migration widens beyond the clear-fit family and creates abstraction debt
   - Control: scope the mandatory migration to the three highest-pressure workflows and treat wider reuse as optional.

## Boilerplate / Clarity Budget To Report At Closeout

- files added
- files deleted
- net line count change if practical
- repeated validation idioms removed
- repeated prompt sections removed or shortened
- workflows changed to use shared helpers
- new helper functions introduced
- old workflow-local validation blocks replaced
- core flow readability before/after

Expected qualitative outcome:

- publish handlers in the scoped family become visibly shorter
- duplicated hidden-execution helpers disappear from workflow files
- no new workflow is added
- the cycle remains net-neutral or net-negative in conceptual surface area even if a small helper addition causes a slight line increase

## Deferred Debt After This Cycle

- adjacent publish-handler duplication in `task_to_candidate_workflow_set`, `task_to_workflow_strategy`, `candidate_workflow_to_adapted_execution_plan`, and `workflow_to_eval_suite` if their remaining mechanical checks still justify another consolidation pass
- possible convergence of duplicated scoped-snapshot extraction helpers if the publication-helper migration leaves that pressure concrete and mechanically shareable
- workflow portfolio shaping and domain-building-block extraction remain deferred until current publish surfaces are cleaner
