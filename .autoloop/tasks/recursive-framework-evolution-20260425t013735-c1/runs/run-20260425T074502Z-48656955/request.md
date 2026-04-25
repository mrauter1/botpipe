# Recursive Architecture Improvement Cycle 1

This cycle is not required to add a workflow.

Primary objective:
Improve the architecture so workflows become easier to read, shorter to author, less repetitive, easier to test, and easier to reason about.

Default bias:
- Prefer consolidation over expansion.
- Prefer deletion over addition.
- Prefer shared validation helpers over workflow-local validation.
- Prefer making existing workflows clearer over creating new workflows.
- Prefer one obvious core flow over many scattered helper-specific flows.
- Prefer helper-seam convergence over adding another helper seam.
- Prefer adapting or composing existing workflows over creating new ones.

Standing memory files to read and update:
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `.autoloop_recursive/framework_gap_ledger.md`
- `.autoloop_recursive/workflow_candidate_ledger.md`
- `.autoloop_recursive/validation_debt_ledger.md`

Mandatory inspection before changes:
- entire repo codebase
- `docs/architecture.md`
- `docs/authoring.md`
- `core/`
- `runtime/`
- `extensions/`
- `stdlib/`
- current workflow definitions under `workflows/`
- relevant tests under `tests/`
- `.autoloop_recursive/`

CLI and composition reminders:
- Greenfield additions must preserve feature compatibility with the global CLI and the strict workflow/runtime/provider boundary.
- The recursive wrapper runs through the globally installed CLI: `autoloop --workspace ... --task-id ... --intent ... --pairs ...` and `autoloop --workspace ... --task-id ... --resume`.
- Existing workflow composition through `ctx.invoke_workflow(...)` must keep working.


## Cycle Mode

Choose exactly one primary cycle mode:

1. `consolidate`
- Reduce duplication across existing workflows or helpers.
- Extract shared validation, publication, catalog, snapshot, serializer, or prompt helpers.
- Delete, merge, or simplify redundant code.
- Do not add a new workflow unless required to complete the consolidation.

2. `authoring-surface`
- Improve workflow authoring so future workflows are shorter and easier to reason about.
- Prefer helper extraction, serializer unification, test simplification, prompt-template simplification, or docs clarification.
- Ask what would make workflow authoring 10x more elegant and understandable.

3. `portfolio-shaping`
- Review the existing workflow portfolio.
- Identify overlap, missing building blocks, obsolete seams, and workflows that should reuse, compose, decompose, merge, or retire.
- May add, merge, split, or retire workflows, but only with explicit evidence.

4. `expand`
- Add one new workflow or reusable building block.
- Allowed only if reuse, adaptation, composition, refinement, or decomposition of existing workflows is insufficient.
- Must also reduce future boilerplate or prove reuse of existing helper seams.

Default preference order:
1. consolidate
2. authoring-surface
3. portfolio-shaping
4. expand

If the wrapper specified a cycle mode, respect it unless it would clearly harm the repository:
`auto`

## Mandatory Pre-Change Audit

Before editing code, perform this audit:

1. Identify the three most relevant existing workflows/helpers.
2. Identify repeated validation, schema, artifact, prompt, route, or publication patterns.
3. Identify at least one simplification opportunity.
4. Identify whether a new workflow is actually necessary.
5. Identify what would make the touched workflow family 10x easier to author, read, and reason about.
6. Decide whether this cycle should add, change, consolidate, delete, merge, or retire.

Record the audit in the cycle notes or docs touched by the change.

## New Workflow Gate

Do not create a new workflow package unless all are true:

- At least three existing workflows/building blocks were checked for reuse or adaptation.
- The candidate cannot be expressed as a parameterized run, composition, adaptation, refinement, or decomposition of existing workflows.
- The candidate has a distinct terminal artifact package and sponsor/use case.
- The implementation reuses existing stdlib/helper seams where applicable.
- The new workflow does not introduce a new validation idiom that should instead be shared.
- The new workflow reduces future ambiguity more than it increases portfolio size.
- The new workflow is more valuable than a consolidation or authoring-surface improvement in this cycle.

If new workflows are disallowed by wrapper policy, do not add one:
`0`

## Boilerplate and Clarity Budget

Every cycle must report:

- files added
- files deleted
- net line count change, if practical
- repeated validation idioms removed
- repeated prompt sections removed or shortened
- workflows changed to use shared helpers
- new helper functions introduced
- old workflow-local validation blocks replaced
- core flow readability before/after

If the cycle adds more than 500 net lines, explain why the added surface is not avoidable.

If the cycle adds a new workflow and no shared helper or simplification, that is usually a failed cycle.

If the cycle repeats validation logic already present in two or more workflows, extract a shared helper instead.

## Workflow Authoring Doctrine

Workflow authoring doctrine (must follow):

## 1. Global-vs-local boundary

- The workflow owns the global SOP.
- The prompt template owns the provider-facing local SOP for the current step.
- The provider owns cognition inside the current step.
- The runtime stays narrow, mechanical, and policy-light.
- Do not move domain policy into runtime-only abstractions.

## 2. Root authoring surface discipline

- Keep the root `workflow` import surface strict and minimal.
- Authoring usually happens under `workflows/<name>/`, while execution stays on the public `autoloop run/resume/answer` contract.
- Do not add public root primitives merely to reduce local boilerplate.
- Prefer stdlib helpers before expanding the core DSL.
- Prefer helper functions that write explicit artifacts over hidden runtime behavior.
- Do not expose engine, compiler, loader, runner, provider, store, or compatibility internals through the root workflow shim.

## 3. Prompt-template doctrine

Prompt templates should tell the provider:

- which role or step it is executing
- the purpose of the current step
- relevant context and current work item, if any
- which artifacts to read
- which artifacts to create, update, or leave untouched
- where to write artifacts
- what evidence must be produced
- how to choose among legal routes
- what is in scope, out of scope, and forbidden

But prompt templates should not become bloated.

Use compact tables where possible:

| Artifact | Read/Write | Purpose | Handling |
|---|---:|---|---|

Use concise route guidance. Do not restate machine-readable route contracts verbatim when the runtime already injects `available_routes` and `route_contracts`.

## 4. Runtime-injected control contract

The runtime may inject or enforce only narrow machine-readable control surfaces such as:

- `expected_output_schema`
- `available_routes`
- `route_contracts`

The runtime may validate returned routes and schemas, and enforce reserved-route behavior.

Do not widen the runtime-injected provider contract unless there is a clear cross-workflow reason.

## 5. Artifact-first design

Prefer filesystem artifacts as the durable work product.

Provider prose is control metadata unless it is written into a declared artifact.

For each step, specify:

- required input artifacts
- required output artifacts
- exact names and paths or path templates
- overwrite / append / patch handling
- authoritative artifacts
- evidence artifacts
- downstream-consumed artifacts

## 6. Validation and schema discipline

Do not repeat low-level validation code across workflows.

If the same validation appears in two or more workflows, prefer a shared helper.

Generic validation that should usually be shared:

- JSON object/list shape checks
- required string/list/bool/int checks
- path-safety checks
- selected-workflow existence checks
- known-artifact-name checks
- manifest/summary/receipt consistency checks
- duplicate ID checks
- status/category allow-list checks

Workflow code should keep domain-specific assertions, but generic mechanics should move to stdlib or core helper seams.

## 7. Verification doctrine

For non-trivial or quality-sensitive work, explicitly enforce producer/verifier behavior.

Verification must have:

- clear evidence requirements
- clear artifact checks
- clear route decision policy
- clear rework vs replan boundary

Rework loops must be local to the same work-item contract.
Replan must be explicit when local repair is no longer the right response.

## 8. Work-item boundary doctrine

Do not optimize only for tiny tasks.

Work items may be ambitious and long-horizon, but their boundaries should be coherent across:

- role / specialization
- artifact family
- acceptance surface
- verifier authority
- local repairability

`needs_rework` means the same work-item contract still holds.
`needs_replan` means the boundary, sequencing, specialization, or artifact graph changed materially.

## 9. Composition doctrine

Prefer explicit workflow composition over hidden runtime sequencing.

When invoking child workflows:

- use explicit workflow code or approved stdlib composition helpers
- keep child execution compatible with `ctx.invoke_workflow(...)`
- validate child status, terminal route, and required artifacts before adoption
- copy explicitly named child artifacts into the parent workflow folder when needed
- route child `question` and `blocked` states explicitly in the parent
- do not create hidden downstream execution

## 10. Helper-seam doctrine

Helper seams should:

- be additive
- write explicit workflow-local artifacts
- avoid mutating workflow packages unless that is the workflow’s explicit purpose
- avoid adding `workflow.toml` semantic fields
- avoid runtime-owned routing/policy
- have clear boundaries and non-goals
- be reused by multiple workflows or justified by clear future reuse

## 11. Readability doctrine

For every workflow touched or created, the top-level flow definition in `flow.py`, legacy `workflow.py`, or a single-file workflow should make the core flow obvious quickly:

- workflow purpose
- state fields that matter
- artifacts grouped by role/output
- steps in order
- transitions in order
- system/publication handlers separated from provider-step handlers

If a workflow requires a long publication validator, move generic parts into stdlib and leave only domain-specific assertions in the workflow.

## 12. Recursive self-improvement doctrine

Candidate workflow, prompt, helper, policy, or artifact changes may be proposed by the provider.

Promotion must remain deterministic and evidence-gated.

Baseline, candidate, evaluation, regression, promotion, and rollback artifacts should be explicit.

Future recursive cycles should improve architecture shape, not merely add more workflows.

## Architecture Improvement Examples

Architecture improvement examples for inspiration only:

1. repeated_json_validation_to_shared_helper

Input: three workflows each validate JSON shape, selected workflow names, expected artifact names, and publication receipts.
Output: shared validation helpers, updated workflows, tests proving equivalent behavior, fewer workflow-local lines.
Why this is good: it reduces boilerplate and makes workflow code easier to read.

2. duplicated_capability_snapshot_serializers_to_single_surface

Input: portfolio, adaptation, refinement, decomposition, and evaluation helpers each serialize compiled workflow information differently.
Output: one authoritative compiled-surface serializer and updated helper snapshots.
Why this is good: it prevents schema drift and makes downstream workflows easier to reason about.

3. verbose_prompt_contracts_to_compact_step_contract_style

Input: several producer/verifier prompts repeat route grammar and artifact handling in long prose.
Output: compact prompt contract tables and docs explaining which details come from runtime route contracts.
Why this is good: it keeps prompts explicit but less cluttered.

4. workflow_local_publication_checks_to_domain_validators

Input: workflows contain large publication validators with repeated low-level checks.
Output: shared validator functions plus short domain-specific workflow checks.
Why this is good: the workflow core flow becomes visible again.

5. workflow_portfolio_sprawl_to_composition_map

Input: many workflows overlap in purpose.
Output: map of shared building blocks, candidates for merge/decomposition, and one concrete simplification.
Why this is good: it keeps the workflow ecosystem legible.

6. scattered_path_safety_to_single_file_writer

Input: many helpers manually check paths remain under `ctx.workflow_folder`.
Output: a shared workflow-local file writer/JSON writer used by all helpers.
Why this is good: it removes repeated security/safety boilerplate.

7. repeated_route_contracts_to_optional_helper_bundles

Input: workflows repeat `needs_rework`, `needs_replan`, `question`, `blocked`, and `failed` route prose.
Output: optional route-contract helper bundles with clear local overrides.
Why this is good: it reduces repetition without hiding transitions.

8. large_workflow_to_clearer_sections

Input: a workflow file mixes artifacts, state, topology, publication validation, helper functions, and handlers.
Output: same behavior, but organized into obvious sections and smaller named validators.
Why this is good: the top-level flow becomes easier to understand.

9. workflow_builder_output_to_current_best_practice

Input: generated workflows do not consistently use current stdlib helper seams.
Output: workflow builder emits current style: invocation contract, publication receipt, explicit route grammar, concise prompts, and shared validation helpers.
Why this is good: future workflow surfaces start cleaner.

10. stale_recursive_memory_to_actionable_ledgers

Input: recursive memory grows as narrative history but does not guide next changes.
Output: memory files track active validation debt, portfolio overlap, and concrete consolidation opportunities.
Why this is good: future cycles converge instead of rediscovering old issues.

## Workflow Examples

Example workflow families for inspiration only.

Use these examples only after checking whether the right move is consolidation, adaptation, composition, refinement, or decomposition. Do not treat this list as a backlog to implement one-by-one.

Layout reminders:
- Single-file workflows such as `workflows/<name>.py` are supported
- Serious package workflows often start with `workflows/<name>/flow.py` plus optional `specs.py`
- Mature workflow surfaces may add `workflow.toml`, `prompts/`, and `assets/` when justified
- Recursive execution stays on `autoloop --workspace ... --task-id ... --intent ... --pairs ...`
- Existing parent/child composition continues through `ctx.invoke_workflow(...)`

## Strong end-to-end workflow naming rule

A strong end-to-end workflow name should read like:

`<starting situation>_to_<terminal outcome>`

Good:

- `incident_to_hardening_program`
- `release_candidate_to_go_no_go`
- `workflow_idea_to_workflow_package`
- `customer_escalation_to_resolution_package`

Weak:

- `incident_analysis`
- `release_review`
- `business_analysis`
- `product_discovery`

## Strong workflow quality rule

A workflow is truly end-to-end only if it has all three:

1. a concrete trigger
2. a concrete terminal decision or output package
3. clear artifacts that another team could immediately use

## Example end-to-end workflows

1. `customer_request_to_delivery_plan`

Input: “A customer wants SSO, audit logs, and SCIM this quarter.”
Output: scoped delivery plan, architecture options, dependency map, risk register, phased backlog, staffing recommendation, and customer-safe commitment draft.
Flow: intake → clarify business outcome → map capability gaps → shape solution options → estimate delivery slices → identify delivery risks → recommend scope/sequence → produce commit-ready plan.
Why this is good: it goes from ambiguous deal pressure to an execution-ready delivery position.

2. `product_idea_to_prd_and_release_slices`

Input: “We should launch usage-based billing for mid-market customers.”
Output: PRD, user/problem framing, pricing/ops constraints, architecture implications, analytics plan, rollout plan, and release slices.
Flow: problem framing → stakeholder assumptions → user journeys → success metrics → solution shape → constraints → MVP/release slicing → decision memo.
Why this is good: it ends with something product, engineering, and go-to-market teams can run.

3. `incident_to_hardening_program`

Input: “Payments API returned 500s for 47 minutes last night.”
Output: incident summary, timeline, likely cause ranking, mitigation plan, customer communication draft, hardening backlog, observability gaps, and follow-up owners.
Flow: evidence collection → blast-radius analysis → hypothesis ranking → mitigation options → verification plan → stakeholder comms → hardening recommendations → owner-ready backlog.
Why this is good: it closes the loop into prevention.

4. `release_candidate_to_go_no_go`

Input: “We want to ship release 2026.04 on Friday.”
Output: go/no-go decision, blocking issues list, rollback plan, test evidence pack, operational checklist, release communications, and signed release recommendation.
Flow: gather release contents → check completeness → verify test evidence → assess operational readiness → assess rollback safety → assess customer impact → produce go/no-go package.
Why this is good: it ends in an operational decision.

5. `legacy_service_to_modernization_plan`

Input: “Replace the monolith’s billing module without disrupting renewals.”
Output: current-state map, seam analysis, target-state architecture, migration strategy, phased cutover plan, dependency/risk ledger, and migration backlog.
Flow: inventory current behavior → identify seams/contracts → define target boundaries → compare migration strategies → recommend phased plan → identify proving milestones → produce execution package.
Why this is good: it is concrete modernization work.

6. `security_finding_to_verified_remediation`

Input: “Pentest found privilege escalation in admin impersonation.”
Output: exploit summary, affected surface, remediation options, chosen fix, validation plan, rollout plan, and evidence of closure.
Flow: reproduce finding → bound impact → map code/config causes → design remediation options → choose fix → define verification evidence → prepare rollout/comms → produce closure packet.
Why this is good: it goes from finding to verified remediation.

7. `failing_delivery_to_recovery_plan`

Input: “This initiative is six weeks late and nobody trusts the plan.”
Output: reset status, root causes, scope triage, dependency cleanup, rebaselined milestones, owner/accountability map, and recovery narrative.
Flow: reality capture → missed-assumption analysis → backlog triage → dependency compression → milestone redesign → risk negotiation → recovery recommendation.
Why this is good: it handles delivery recovery as an end-to-end problem.

8. `customer_escalation_to_resolution_package`

Input: “Strategic customer says reporting is unreliable and may churn.”
Output: issue brief, evidence pack, problem decomposition, response options, immediate stabilizing actions, customer communication draft, and durable remediation plan.
Flow: intake escalation → gather evidence → separate symptom from root cause → rank response options → define immediate/durable actions → prepare internal/external comms.
Why this is good: it ends with both action and communication.

9. `workflow_idea_to_workflow_package`

Input: “We need a workflow for release-readiness reviews.”
Output: workflow surface with topology, control flow, prompts, artifact contract, parameter model, tests, docs, and example usage.
Flow: clarify user job → decide workflow vs building block → define inputs/outputs → define topology → define routes/artifacts → generate prompts → add tests/docs → publish package.
Why this is good: this is workflow-builder infrastructure.

10. `deal_to_solution_architecture_and_delivery_shape`

Input: “Prospect needs regional data residency, SAML, and delegated admin in 90 days.”
Output: solution architecture, gaps vs current platform, delivery shape, sequencing options, commercial risk notes, and recommended delivery posture.
Flow: extract requirements → classify hard constraints → map platform fit/gaps → propose solution variants → analyze feasibility → identify risks → recommend shape.
Why this is good: it spans pre-sales, architecture, and delivery.

## Workflow portfolio patterns

Useful workflow families may include:

1. `task_to_workflow_strategy`
- Front door for deciding whether to run, compose, adapt, or create workflows.

2. `task_to_candidate_workflow_set`
- Candidate retrieval and fit-gap analysis.

3. `candidate_workflow_to_adapted_execution_plan`
- Reuse-over-rebuild adaptation planning.

4. `workflow_idea_to_workflow_package`
- Greenfield workflow authoring.

5. `workflow_package_to_composable_building_blocks`
- Decomposition into reusable building blocks.

6. `workflow_to_eval_suite`
- Evaluation authoring for workflow packages.

7. `workflow_run_history_to_failure_modes`
- Diagnostics from run history.

8. `workflow_and_eval_to_refined_workflow_package`
- Closed-loop refinement.

9. `workflow_portfolio_to_operating_system`
- Portfolio governance.

10. `company_operation_to_recursive_improvement_cycle`
- Company-level recursive learner.

Do not implement these merely because they are listed. Prefer reuse, adaptation, composition, refinement, and consolidation first.

## Framework Improvement Evaluation

When evaluating framework improvements:

- Consider what core framework improvements would make workflow authoring 10x more elegant, easy to reason about, and easy to understand.
- Do not limit yourself to just one improvement if a coherent set of improvements is needed.
- Consider improvements to core, stdlib, runtime, workflow-builder, prompts, docs, tests, serializers, validation helpers, and recursive wrapper behavior.
- Prefer improvements that reduce cognitive load across many workflows.
- Prefer improvements that remove repeated boilerplate without hiding important workflow semantics.
- Prefer improvements that make the top-level workflow flow obvious.
- Prefer improvements that let future workflow authors express intent with less code, fewer local validators, and clearer artifact contracts.

Framework improvement preference order:

1. Delete obsolete code, docs, prompts, or workflow surfaces.
2. Extract repeated validation into shared helpers.
3. Extract repeated snapshot/catalog/publication patterns into shared helpers.
4. Centralize serializers used by multiple helpers.
5. Simplify workflow-builder output.
6. Simplify prompt templates while preserving provider-facing clarity.
7. Improve diagnostics using existing seams.
8. Add runtime/compiler capability only when repeated concrete pressure proves it is needed.

Do not add framework machinery unless it clearly improves expression, execution, reuse, reliability, readability, or authoring leverage.

## Acceptance Gates

The cycle must satisfy these gates:

- The chosen work must improve real workflow usefulness, authoring quality, architecture clarity, or portfolio shape.
- The implementation must make at least one existing surface easier to read, reuse, validate, or reason about.
- The cycle must explicitly identify repeated patterns and decide whether to extract or defer them.
- No new workflow unless the new-workflow gate passes.
- No repeated validation logic if a shared helper can reasonably handle it.
- No new helper seam without documenting its boundary and non-goals.
- No new semantic `workflow.toml` fields.
- No runtime-owned hidden routing, adaptation, evaluation, promotion, decomposition, scoring, or prioritization.
- No broad root `workflow` authoring-surface expansion without explicit justification.
- The core flow of touched workflows must be easier to understand after the change.
- Tests and docs must preserve or improve the strict workflow/runtime/provider boundary.

## Required Output

1. Cycle mode and rationale.
2. Pre-change audit summary.
3. Candidate options considered.
4. Chosen improvement.
5. Why this improvement is higher leverage than a new workflow, unless expansion mode is chosen.
6. Boilerplate/repetition reduced.
7. Shared helper, serializer, validator, or prompt simplification introduced, if applicable.
8. Workflows simplified or made clearer.
9. Tests and docs updated.
10. Recursive memory files updated:
    - framework roadmap
    - framework gap ledger
    - workflow candidate ledger
    - validation debt ledger
11. Remaining deferred validation debt or portfolio-shape debt.

## Decision-Record Discipline

Use full 3-option decision records only for architectural decisions that change public/helper/runtime shape.

For local implementation choices, use a concise rationale.

Do not create repetitive decision records for prompt wording, file naming, or mechanical test updates.

Prefer one concise cycle decision record over many scattered mini-ADRs.

## Outcome Standard

The cycle must leave the repository more capable of supporting valuable workflows with less clutter.

Prefer work that strengthens:
- immediate usefulness
- long-term workflow ecosystem quality
- authoring leverage
- readability
- reuse
- validation consistency
- portfolio legibility

If no high-leverage improvement remains, produce a no-op convergence report instead of adding another workflow.
