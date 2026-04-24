# Recursive Framework Evolution Cycle 5 Plan

## Cycle mode

`authoring-surface`

Rationale:
- Cycle 14 closed the older-domain validation migration, so the highest-leverage remaining authoring debt is no longer generic validation logic.
- The four older domain workflow families still expose the pre-cycle-4 prompt surface: `26` prompt bodies still use `Read these artifacts`, `13` producer prompts still repeat `Write these artifacts`, `0` of those prompt bodies use the compact `## Step Contract` structure, and all `4` prompt READMEs still miss the standardized README contract sections.
- Compacting that surface shortens future workflow authoring, makes the prompt contract easier to scan, and does not require a new workflow, runtime helper seam, or serializer expansion.

## Pre-change audit summary

### Most relevant existing workflows/helpers

1. `workflows/task_to_workflow_strategy/prompts/`
   - Canonical compact prompt-contract reference after the cycle-4 migration; it shows the README boundary and the target section layout for prompt files.
2. `workflows/release_candidate_to_go_no_go/prompts/`
   - Mature domain workflow still using the older prompt scaffolding in every prompt body and README.
3. `workflows/security_finding_to_verified_remediation/prompts/`
   - Richest older-domain consumer because it mixes child-workflow composition, assessment, remediation planning, and closure packaging, so it is the strongest regression surface for prompt compaction.

Corroborating surfaces checked:
- `workflows/investigation_request_to_evidence_pack/prompts/`
- `workflows/incident_to_hardening_program/prompts/`
- `docs/architecture.md`
- `docs/authoring.md`
- `core/`, `runtime/`, `extensions/`, and `stdlib/` for any runtime-owned prompt seam that would make this migration unsafe
- all workflow packages under `workflows/`
- runtime suites under `tests/runtime/`
- baseline docs assertions in `tests/test_architecture_baseline_docs.py`
- recursive-memory files under `.autoloop_recursive/`

### Repeated patterns found

- Older domain prompt bodies still rely on the legacy prose scaffold:
  - `26` prompt bodies repeat `Read these artifacts`
  - `13` producer prompts repeat `Write these artifacts`
  - all `26` prompt bodies lack the compact `Step Contract` / `Artifact Contract` / `Output Requirements` / `Evidence` / `Routes` / `Forbidden` section shape already used by the newer workflow family
- The four older-domain `prompts/README.md` files still use ad hoc package summaries and do not carry the standardized cycle-4 sections:
  - `## Shared README Boundary`
  - `## Keep In Each Prompt`
  - `## Step Surface`
  - `## Route Surface`
  - `## Verifier Payloads`
- The older domain runtime suites currently validate workflow behavior and route contracts, but they do not yet pin prompt README structure or reject legacy prompt scaffolding explicitly.
- The runtime and stdlib do not need a new prompt abstraction. `docs/authoring.md` already freezes the correct doctrine: keep prompts explicit, keep runtime injection narrow, and avoid a template engine or hidden prose injection.

### Simplification opportunity

- Extend the existing compact prompt-contract style from the newer workflow family to the four older domain workflow families.
- Keep family-wide reminders in each package README once, then rewrite step prompts so the step-local contract is easy to scan through compact headings and artifact tables.
- Add prompt-shape assertions to the older domain runtime suites and baseline docs so the repo stops regressing back to the legacy scaffold.

### New workflow necessity

- No new workflow is necessary.
- The repo already has broad workflow coverage, and the standing deferred authoring-surface gaps explicitly name older domain prompt-family compaction as higher leverage than another workflow addition.
- Adding a workflow now would increase portfolio size while leaving the current domain authoring surface noisy and inconsistent with the rest of the portfolio.

### What makes this workflow family 10x easier to author/read/reason about

- A prompt author should be able to scan one file and immediately see:
  - the current step role and boundary
  - the exact artifact read/write contract
  - the evidence bar for the verifier
  - the legal routes and forbidden actions
- Shared family rules should live once in `prompts/README.md`, not once per prompt body.
- The domain workflow family should use the same prompt shape as the newer builder/selected-workflow/governance/company/refinement/decomposition families, so future authors do not have to remember two competing prompt idioms.

### Change decision

- Change and standardize existing prompt surfaces for the older domain workflow family.
- Do not add, merge, split, or retire workflows in this cycle.
- Do not widen runtime prompt behavior, add a serializer seam, or introduce any new root authoring primitive for this cleanup.

## Candidate options considered

1. Compact the older domain prompt families and bring their README/test coverage onto the cycle-4 prompt contract.
   - Pros: resolves the most visible remaining prompt-authoring inconsistency, shortens future workflow authoring, and keeps behavior unchanged.
   - Cons: touches many prompt markdown files and needs prompt-facing test additions because current domain suites do not pin the prompt structure.
   - Decision: chosen.

2. Converge the selected-workflow serializers across `stdlib/refinement.py` and `stdlib/decomposition.py`.
   - Pros: real code-level consolidation with clear overlap in selected-workflow surface serialization.
   - Cons: narrower immediate leverage because it affects a smaller helper seam than the domain prompt surface every workflow author sees first.
   - Decision: deferred.

3. Extract new reusable assessment/remediation building blocks from the current domain workflows.
   - Pros: could expand portfolio reuse.
   - Cons: the wrapper forbids new workflows by default here, and the current evidence says authoring-surface cleanup is higher leverage than additional portfolio growth.
   - Decision: rejected for this cycle.

## Chosen improvement

Migrate the four older domain workflow prompt families to the compact prompt-contract style already frozen in `docs/authoring.md` and proven in the newer workflow family:

- Standardize `prompts/README.md` for:
  - `release_candidate_to_go_no_go`
  - `investigation_request_to_evidence_pack`
  - `security_finding_to_verified_remediation`
  - `incident_to_hardening_program`
- Rewrite the `26` step prompt files in those four packages to the compact section contract.
- Update the corresponding runtime suites and `tests/test_architecture_baseline_docs.py` so prompt regressions are caught explicitly.
- Keep the following unchanged:
  - prompt file paths
  - step names
  - artifact names
  - route names
  - expected output schemas
  - workflow topology
  - CLI/runtime/provider boundaries
  - `ctx.invoke_workflow(...)` behavior

## Why this is higher leverage than a new workflow

- It improves four mature workflow packages that already matter to the portfolio instead of adding another package to maintain.
- It aligns the last older-domain prompt family with the current best authoring practice, reducing cognitive branching across the portfolio.
- It follows the standing recursive-memory direction directly: compare new workflow ideas against prompt compaction and serializer convergence before expanding the portfolio again.

## Scope and milestones

### Milestone 1: older-domain prompt surface migration

- Rewrite the four older-domain `prompts/README.md` files to the standardized README contract shape.
- Rewrite the `26` prompt bodies in those packages to the compact contract style:
  - `## Step Contract`
  - `## Artifact Contract`
  - `## Output Requirements`
  - `## Evidence`
  - `## Routes`
  - `## Forbidden`
- Use compact artifact tables where they materially shorten the prompt while preserving the same artifact read/write semantics.
- Add prompt-shape assertions to:
  - `tests/runtime/test_release_candidate_to_go_no_go.py`
  - `tests/runtime/test_investigation_request_to_evidence_pack.py`
  - `tests/runtime/test_security_finding_to_verified_remediation.py`
  - `tests/runtime/test_incident_to_hardening_program.py`
- Expand `tests/test_architecture_baseline_docs.py` so the older domain README files are covered by the same shared README contract assertions.

### Milestone 2: proof, docs, and recursive-memory sync

- Run targeted prompt-facing proof for the four touched domain runtime suites plus `tests/test_architecture_baseline_docs.py`.
- Update recursive-memory files:
  - `.autoloop_recursive/framework_evolution_charter.md`
  - `.autoloop_recursive/framework_roadmap.md`
  - `.autoloop_recursive/framework_gap_ledger.md`
  - `.autoloop_recursive/workflow_candidate_ledger.md`
  - `.autoloop_recursive/validation_debt_ledger.md`
- Record the cycle as prompt-authoring compaction only, with no CLI/runtime/provider/`ctx.invoke_workflow(...)` contract change.
- Update `docs/authoring.md` only if implementation reveals wording drift against the already-frozen compact prompt doctrine; otherwise record an explicit no-doctrine-change outcome in recursive memory instead of broadening docs scope unnecessarily.

## Interfaces and compatibility constraints

- No CLI changes.
- No runtime changes.
- No provider adapter changes.
- No changes to `ctx.invoke_workflow(...)`.
- No new `workflow.toml` semantic fields.
- No new workflow package.
- Prompt file paths must remain unchanged so existing workflow step declarations continue to resolve them.
- The runtime-injected provider contract remains limited to:
  - `expected_output_schema`
  - `available_routes`
  - `route_contracts`

## Regression-risk notes

1. Prompt under-specification
   - Risk: compacting the older domain prompts could drop a step-local restriction or artifact-handling rule that only appears once today.
   - Control: preserve artifact names, route names, and step boundaries exactly; add prompt-shape assertions in the domain suites rather than relying on manual review alone.

2. README drift from workflow reality
   - Risk: the new README tables could list the wrong writes, routes, or verifier payload names.
   - Control: derive the README updates directly from the compiled workflow step surfaces already pinned by the runtime tests.

3. Scope creep into serializer convergence
   - Risk: while touching authoring surfaces, implementation could spill into `stdlib/refinement.py` / `stdlib/decomposition.py`.
   - Control: keep serializer convergence explicitly deferred unless prompt migration reveals a blocking inconsistency that cannot be addressed locally.

## Validation strategy

Targeted proof should cover:

- `tests/runtime/test_release_candidate_to_go_no_go.py`
- `tests/runtime/test_investigation_request_to_evidence_pack.py`
- `tests/runtime/test_security_finding_to_verified_remediation.py`
- `tests/runtime/test_incident_to_hardening_program.py`
- `tests/test_architecture_baseline_docs.py`

Validation focus:
- prompt files remain at the existing package-relative paths
- README tables and prompt headings match the compact contract shape
- legacy `Read these artifacts` / `Write these artifacts` scaffolding is removed from the four older domain prompt families
- artifact names, route names, route contracts, and runtime behavior remain unchanged
- child-workflow composition in `security_finding_to_verified_remediation` remains explicit and deterministic

## Risk register

- `R1`: prompt edit volume (`26` bodies plus `4` READMEs) causes inconsistent style or missed step-local restrictions.
  - Mitigation: migrate per workflow package, add prompt-shape tests in the same change, and keep the target section shape fixed.
- `R2`: baseline docs assertions still only protect the newer prompt README family.
  - Mitigation: extend the README assertion set to cover the four older domain packages in the same implementation slice.
- `R3`: recursive memory could frame the cycle as a new doctrine change instead of a migration to an existing doctrine.
  - Mitigation: record an explicit no-doctrine-change note unless `docs/authoring.md` truly needs wording changes.

## Rollback

- Revert prompt markdown, README, and prompt-facing test updates together if the compact structure drops required step behavior or creates confusing proof failures.
- Revert recursive-memory updates independently only if implementation scope changes before proof is complete.
- Do not leave the repo in a split state where only part of the older domain family uses the compact prompt contract without an explicit deferral note.

## Boilerplate and clarity budget target

- Files added: `0` expected.
- Files deleted: `0` expected.
- Net line change: negative expected across the four older domain prompt packages.
- Repeated validation idioms removed: none planned in Python code.
- Repeated prompt sections removed or shortened:
  - repeated `Read these artifacts` scaffolding
  - repeated `Write these artifacts` scaffolding
  - repeated package-level runtime-boundary reminders
  - repeated file-mutation policy prose in verifier prompts
- Workflows changed to use shared helpers: none in code; the improvement is prompt-surface and README/test convergence.
- New helper functions introduced: none planned.
- Old workflow-local validation blocks replaced: none planned.
- Core flow readability before/after:
  - before: the older domain prompt family buries the step-local contract under repetitive prose and README drift
  - after: the step-local contract is front-loaded and the family-wide contract lives once per package

## Deferred debt after this cycle

- Selected-workflow serializer convergence across `stdlib/refinement.py` and `stdlib/decomposition.py` remains the clearest next code-level consolidation candidate after the older-domain prompt migration.
- Reusable assessment/remediation building blocks remain deferred portfolio-shape work and should not outrank current authoring-surface cleanup without stronger evidence.
- No new validation debt is expected from this cycle because the change is prompt-local, README-local, and test/memory-local rather than workflow-code or runtime-code expansion.
