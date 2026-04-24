# Recursive Framework Evolution Cycle 4 Plan

## Cycle mode

`authoring-surface`

Rationale:
- Cycle 3 closed the broad parameter-model cleanup, so the highest-leverage remaining pressure is now the repeated prompt authoring surface rather than missing validation helpers or missing workflows.
- The newer workflow family still carries heavy prompt duplication: `113` prompt markdown files exist, `92` repeat a `Read these artifacts` block, `66` repeat a `Write these artifacts` block, `46` repeat an `Out of scope` block, `20` verifier prompts repeat the same file-mutation policy, `9` frame producers repeat the same runtime-boundary sentence, and `6` prompt READMEs restate the same runtime footer.
- Compacting that surface improves how workflows are authored and reviewed without widening runtime behavior, adding a new workflow, or changing CLI/composition contracts.

## Pre-change audit summary

### Most relevant existing workflows/helpers

1. `workflows/task_to_workflow_strategy/prompts/`
   - Canonical three-step portfolio workflow whose prompts show the repeated framing/package scaffolding now shared across the newer workflow family.
2. `workflows/workflow_and_eval_to_refined_workflow_package/prompts/`
   - Richest current multi-step package; its prompts prove how much repeated contract boilerplate accumulates when the workflow surface grows.
3. `workflows/workflow_package_to_composable_building_blocks/prompts/`
   - Closest sibling to the refinement package, with near-parallel prompt structure and README content that can validate a compact shared style.

Corroborating surfaces checked:
- `docs/architecture.md`
- `docs/authoring.md`
- `core/`, `runtime/`, `extensions/`, and `stdlib/` for any existing prompt/runtime helper seam that would make compaction risky
- all current workflow packages under `workflows/`
- runtime prompt-facing test suites under `tests/runtime/`
- recursive-memory files under `.autoloop_recursive/`

### Repeated patterns found

- The selected-workflow, governance, company, and builder-era workflow families all restate the same prompt scaffolding with step-local names substituted:
  - large `Read these artifacts` lists
  - large `Write these artifacts` lists
  - repeated runtime-boundary reminders
  - repeated `Out of scope` and `Forbidden` blocks
  - repeated verifier file-mutation policy text
- Prompt READMEs for the newer workflow family duplicate the same sections:
  - step-to-artifact map
  - route grammar summary
  - verifier payload summary
  - the same runtime-boundary footer
- Runtime tests already pin this surface, especially for:
  - `task_to_workflow_strategy`
  - `workflow_to_eval_suite`
  - `workflow_run_history_to_failure_modes`
  - `workflow_portfolio_to_operating_system`
  - `company_operation_to_recursive_improvement_cycle`
  - `workflow_and_eval_to_refined_workflow_package`
  - `workflow_package_to_composable_building_blocks`
- The runtime itself does not need a new prompt abstraction. Current doctrine already says prompts should be compact and the runtime should inject only `expected_output_schema`, `available_routes`, and `route_contracts`.

### Simplification opportunity

- Keep prompt semantics explicit, but compress the repeated prose into a consistent compact contract style:
  - preserve prompt-local role, purpose, evidence rules, and route guidance
  - switch repeated artifact lists to compact tables where they materially shorten the file
  - move family-wide shared notes into per-workflow `prompts/README.md` once instead of restating them in every prompt
  - keep step prompts focused on what changes in that step rather than re-explaining the same runtime boundary repeatedly
- This improves the prompt surface without adding a template engine, runtime prompt injection, or another root authoring primitive.

### New workflow necessity

- No new workflow is necessary.
- The repo already has broad workflow coverage and the main architecture pain is duplicated provider-facing authoring text.
- Adding another workflow now would increase portfolio size while leaving the current authoring surface noisy and harder to maintain.

### What makes this workflow family 10x easier to author/read/reason about

- A future author should be able to scan one prompt and immediately see:
  - the step role
  - the exact artifacts to read and write
  - what must not be touched
  - the route boundary
- Shared family rules should live once in the workflow prompt README and once in `docs/authoring.md`, not in every step prompt.
- Runtime tests should assert the preserved contract shape rather than force large amounts of copied prose to stay word-for-word.

### Change decision

- Change and consolidate existing prompt surfaces for the current workflow family.
- Do not add, merge, split, or retire workflows in this cycle.
- Do not add runtime-owned prompt machinery, workflow-templating infrastructure, or root-surface authoring primitives for this cleanup.

## Candidate options considered

1. Compact the prompt contract surface across the current workflow family and builder package.
   - Pros: removes the largest remaining repeated authoring surface, improves readability without changing workflow behavior, and aligns the repo with the standing prompt-template doctrine.
   - Cons: touches many prompt files and requires test updates where prompt structure is pinned.
   - Decision: chosen.

2. Converge the selected-workflow authoring/decomposition serializers in `stdlib/refinement.py` and `stdlib/decomposition.py`.
   - Pros: real helper-seam cleanup with existing unit coverage; prevents drift between the authoring and decomposition surfaces.
   - Cons: narrower leverage than prompt compaction because it affects two helper modules rather than the prompt surface every future workflow author sees first.
   - Decision: deferred.

3. Add a new reusable assessment/remediation building block.
   - Pros: could expand the domain portfolio.
   - Cons: not justified while prompt duplication remains the dominant current authoring burden, and the wrapper explicitly biases this cycle away from new workflows.
   - Decision: rejected for this cycle.

## Chosen improvement

Adopt a compact prompt-contract style for the current workflow family and builder package, without changing runtime behavior:

- Update `docs/authoring.md` to define the compact prompt-contract doctrine explicitly:
  - what must remain in each prompt
  - what should live once in `prompts/README.md`
  - when to use compact artifact tables
  - which repeated runtime details should not be restated verbatim
- Migrate the prompt READMEs and step prompts for:
  - `workflow_idea_to_workflow_package`
  - `task_to_candidate_workflow_set`
  - `task_to_workflow_strategy`
  - `candidate_workflow_to_adapted_execution_plan`
  - `workflow_to_eval_suite`
  - `workflow_run_history_to_failure_modes`
  - `workflow_portfolio_to_operating_system`
  - `company_operation_to_recursive_improvement_cycle`
  - `workflow_and_eval_to_refined_workflow_package`
  - `workflow_package_to_composable_building_blocks`
- Keep the following unchanged:
  - prompt file paths
  - step names
  - artifact names
  - route names
  - expected output schemas
  - workflow topology
  - CLI/runtime/provider boundaries

## Why this is higher leverage than a new workflow

- It improves a surface that nearly every current serious workflow package already exposes, instead of adding one more package to maintain.
- It reduces the amount of prose future workflow authors have to copy and keep consistent, which lowers drift risk across the whole portfolio.
- It follows the standing doctrine more directly than a new workflow would: prompts become more explicit and shorter without hiding behavior in runtime-only abstractions.

## Scope and milestones

### Milestone 1: compact prompt doctrine and README boundary

- Update `docs/authoring.md` with a compact prompt-contract doctrine that preserves explicit artifact-first instructions while encouraging tables and family-level README consolidation.
- Standardize the README shape for the current workflow family so shared runtime-boundary and step-map text lives once per package instead of once per prompt.
- Keep the runtime/provider boundary unchanged and explicit in docs.

### Milestone 2: prompt migration across the current workflow family

- Rewrite the scoped prompt files to the compact contract style while preserving their declared artifacts, scope boundaries, and route intent.
- Prefer:
  - compact artifact tables
  - concise route guidance
  - step-specific restrictions
  - README-carried family-wide reminders
- Avoid:
  - removing required artifact instructions
  - weakening verifier evidence rules
  - inventing a prompt template engine or shared runtime prompt renderer

### Milestone 3: proof, docs, and recursive-memory sync

- Update the prompt-facing runtime tests so they assert the preserved contract content under the new compact structure.
- Update recursive memory files:
  - `.autoloop_recursive/framework_evolution_charter.md`
  - `.autoloop_recursive/framework_roadmap.md`
  - `.autoloop_recursive/framework_gap_ledger.md`
  - `.autoloop_recursive/workflow_candidate_ledger.md`
  - `.autoloop_recursive/validation_debt_ledger.md`
- If the cycle does not change doctrine, record that explicitly in the charter rather than silently skipping the file.
- Record the compaction metrics and any intentionally deferred prompt families in implementation closeout.

## Interfaces and compatibility constraints

- No CLI changes.
- No runtime changes.
- No provider adapter changes.
- No changes to `ctx.invoke_workflow(...)`.
- No new `workflow.toml` semantic fields.
- No new workflow package.
- Prompt files must stay at the same package-relative paths so existing workflow definitions continue to resolve them.
- The runtime-injected contract remains limited to:
  - `expected_output_schema`
  - `available_routes`
  - `route_contracts`

## Regression-risk notes

1. Prompt under-specification
   - Risk: compaction could accidentally remove a constraint that a verifier or downstream step still needs.
   - Control: preserve all artifact names, route names, and explicit step boundaries; update tests to assert those contract points directly.

2. Test drift from structure changes
   - Risk: existing runtime tests currently pin repeated headings and README wording.
   - Control: migrate those assertions to the new compact structure in the same phase as the prompt edits, rather than leaving prompts and tests out of sync.

3. Scope creep into older domain workflows
   - Risk: trying to compact every prompt family in one pass would widen regression surface beyond the newest shared style family.
   - Control: keep older domain workflows as deferred follow-on work unless a trivial docs-only wording sync is mechanically safe.

## Validation strategy

Targeted proof should cover:

- `tests/runtime/test_workflow_builder_package.py`
- `tests/runtime/test_task_to_candidate_workflow_set.py`
- `tests/runtime/test_task_to_workflow_strategy.py`
- `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
- `tests/runtime/test_workflow_to_eval_suite.py`
- `tests/runtime/test_workflow_run_history_to_failure_modes.py`
- `tests/runtime/test_workflow_portfolio_to_operating_system.py`
- `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
- `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `tests/test_architecture_baseline_docs.py`

Validation focus:
- prompt files remain resolvable at the existing paths
- prompt READMEs still document the right step-to-artifact map and route surface
- compact prompts still mention the same required artifacts and step boundaries
- no workflow topology, CLI, or runtime contract drift occurs

## Risk register

- `R1`: family-wide prompt edit volume causes inconsistent style halfway through the migration.
  - Mitigation: update READMEs and prompt families in a scoped, enumerated list and keep the old domain workflows out of phase scope.
- `R2`: README consolidation removes information that only existed in one prompt.
  - Mitigation: review each workflow family against its current runtime tests before deleting repeated text.
- `R3`: recursive memory overstates the change as a runtime improvement instead of an authoring-surface cleanup.
  - Mitigation: record this cycle explicitly as prompt-authoring compaction with no CLI/runtime/provider contract change.

## Rollback

- Revert prompt markdown, README, and prompt-facing test updates together if the compact structure drops required behavior or produces confusing proof failures.
- Revert recursive-memory and docs updates independently only if implementation scope changes before closeout.
- Do not leave the repo in a split state where some prompt families use the compact contract style and others in the same scoped family still rely on the older verbose scaffolding without an explicit deferral note.

## Boilerplate and clarity budget target

- Files added: `0` expected.
- Files deleted: `0` expected.
- Net line change: negative expected across the scoped prompt family and prompt READMEs.
- Repeated validation idioms removed: none planned in code.
- Repeated prompt sections removed or shortened:
  - repeated runtime-boundary reminders
  - repeated artifact read/write bullet lists
  - repeated out-of-scope prose
  - repeated verifier mutation-policy text
  - repeated prompt README runtime footers
- Workflows changed to use shared helpers: none in code; the improvement is prompt-surface consolidation.
- New helper functions introduced: none planned by default.
- Old workflow-local validation blocks replaced: none planned.
- Core flow readability before/after:
  - before: step prompts bury the step-specific contract under copied scaffolding that differs mostly by artifact names
  - after: step prompts foreground the step-specific contract, while shared family guidance lives once in the README and authoring docs

## Deferred debt after this cycle

- Selected-workflow authoring/decomposition serializer convergence remains the clearest next code-level consolidation candidate after prompt compaction.
- Older domain workflow prompts remain deferred until the compact prompt style proves stable on the current workflow family.
- Reusable assessment/remediation building blocks remain deferred portfolio-shape work and should not outrank current authoring-surface cleanup unless a later cycle produces stronger evidence.
