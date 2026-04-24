# Cycle 7 Plan

## Scope considered

- Authoritative inputs reviewed: the immutable request snapshot, the current run raw log, the standing recursive memory files, the current repo-root framework/docs/workflow packages, and the empty cycle-7 plan artifacts.
- No clarifications were appended after run start, so the initial request snapshot remains authoritative.
- The request snapshot's mandatory inspection paths are stale. The current equivalents are repo-root `docs/architecture.md`, `docs/authoring.md`, `core/`, `runtime/`, `stdlib/`, and `workflows/`.
- The worktree is dirty from broader repo migration work. Cycle 7 implementation must stay scoped to the new evaluation building block, its paired framework seam, tests/docs, and the required recursive-memory files; unrelated dirty deletions/renames stay out of scope.
- In scope:
- ship one new reusable workflow building block with clear value for real software-work operations
- ship one paired framework improvement that keeps runtime/provider boundaries narrow and mechanical
- update workflow docs, targeted tests, architecture-baseline docs, and `.autoloop_recursive/` memory in the same change set
- Out of scope:
- `recursive_autoloop/` wrapper/template cleanup
- widening `workflow.toml`
- runtime-owned eval execution, runtime-owned routing, or hidden downstream workflow execution
- changes to the public CLI, workspace layout, or provider/session contracts

## Current findings

- `workflow_idea_to_workflow_package` is already a credible workflow-builder baseline. The package, decision-record doc, and runtime proof in `tests/runtime/test_workflow_builder_package.py` satisfy the repository's current builder standard.
- The portfolio now has a visible builder, evidence-building block, front door, reusable candidate retrieval, and reusable adaptation planning. The clearest missing layer is reusable evaluation authoring.
- The roadmap, charter, and candidate ledger all already converge on `workflow_to_eval_suite` as the strongest deferred follow-on after cycle 6.
- Existing reusable seams are strong enough to support an evaluation-authoring workflow without widening runtime behavior:
- `stdlib/lifecycle.py` covers deterministic bootstrap/publication
- `stdlib/composition.py` covers explicit child composition
- `core/workflow_capabilities.py`, `stdlib/portfolio.py`, and `stdlib/adaptation.py` already provide inspectable selected-workflow and portfolio-contract capture
- Missing seam: a narrow authoring-only way to validate and canonicalize a proposed evaluation-case manifest against one selected workflow's known parameters and artifact surface without copying loader logic into every evaluation/refinement workflow.

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Mandatory builder baseline and still the greenfield path when the portfolio has a real gap | Already credible in code, docs, and tests, so another builder-first cycle would delay the now more urgent evaluation-authoring gap | Deferred |
| `workflow_to_eval_suite` | Adds the missing reusable layer for benchmark, edge-case, adversarial, and rubric authoring across the existing workflow portfolio | Requires a small shared evaluation-validation seam and careful package boundaries so it stops at suite publication instead of hidden execution | Chosen |
| `workflow_and_eval_to_refined_workflow_package` | High-value recursive improvement workflow once evaluation suites exist | Premature before the repository has a reusable eval-suite authoring layer and canonical eval artifacts | Deferred |

### Why the chosen addition wins

- Problem solved: turn one chosen workflow into a durable evaluation suite package instead of ad hoc benchmark ideas and one-off chat guidance.
- Likely sponsors: engineering productivity, AI platform owners, QA/reliability leads, workflow maintainers, and recursive portfolio owners.
- Classification: reusable workflow building block.
- Why Autoloop fits: the work is multi-artifact, verification-sensitive, and benefits from explicit producer/verifier boundaries plus durable filesystem outputs.
- Why one-shot is insufficient: a useful suite needs framed success dimensions, categorized cases, validated case manifests, rubrics, and a publication receipt another workflow or operator can rely on later.
- Terminal outcome: a published workflow-eval suite with benchmark, edge-case, and adversarial coverage, a validated eval-case manifest, a rubric, and a deterministic receipt.

## Chosen addition contract

- Package path: `workflows/workflow_to_eval_suite/`
- Discovery target: `autoloop workflows show workflow_to_eval_suite`
- Direct invocation:

```bash
autoloop run workflow_to_eval_suite <task-id> \
  --message "Author an evaluation suite for the release go/no-go workflow." \
  -wf selected_workflow release_candidate_to_go_no_go \
  -wf task_title "Release readiness evaluation suite" \
  -wf sponsor_role "engineering productivity" \
  -wf desired_outcome "Publish a reusable eval suite for workflow quality gating." \
  -wf constraints "Keep runtime control narrow and stop at suite publication." \
  -wf evidence_expectations "Need benchmark, edge, adversarial, rubric, and validated eval-case artifacts."
```

- Parameters:
- `selected_workflow` required
- `task_title` required
- `sponsor_role` optional
- `desired_outcome` optional
- `constraints` optional and repeatable
- `evidence_expectations` optional and repeatable

### Workflow objective

Turn one chosen workflow plus evaluation intent into a reusable eval-suite package without auto-running the target workflow or widening runtime-owned control logic.

### Global deterministic workflow responsibilities

- Bootstrap the run-local invocation contract.
- Capture an authoritative selected-workflow contract snapshot from the current repository.
- Keep target framing, case/rubric design, and package publication as separate work items.
- Validate the proposed eval-case manifest mechanically before publication.
- Publish only after the suite package, summary, next-action artifact, and validated eval-case manifest all exist and agree.

### Provider-owned cognitive responsibilities

- Frame the selected workflow's acceptance surface and quality risks.
- Design benchmark, edge, and adversarial cases that pressure the workflow meaningfully.
- Define expected artifacts, pass/fail logic, and rubric guidance.
- Package the final eval suite and downstream handoff artifacts.

### Work-item boundary doctrine

- `capture_selected_workflow_contract`: deterministic contract capture only.
- `frame_evaluation_target`: evaluation framing and success dimensions only.
- `design_eval_cases`: benchmark/edge/adversarial coverage, expected artifacts, and rubric design only.
- `package_workflow_eval_suite`: terminal eval-suite package, summary, and next-action artifact only.
- `needs_rework`: the same work-item boundary still holds.
- `needs_replan`: the selected workflow, evaluation boundary, or acceptance surface changed materially.

### Role topology

- deterministic `bootstrap`
- deterministic `capture_selected_workflow_contract`
- `workflow evaluation framer` / `evaluation-target verifier`
- `workflow evaluation designer` / `eval-design verifier`
- `eval-suite packager` / `eval-suite verifier`
- deterministic `publish_workflow_eval_suite`

### Planned control flow

1. `bootstrap`
2. `capture_selected_workflow_contract`
3. `frame_evaluation_target`
4. `design_eval_cases`
5. `package_workflow_eval_suite`
6. `publish_workflow_eval_suite`

### Planned route grammar

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `selected_workflow_contract_captured`
- `evaluation_target_framed`
- `eval_cases_designed`
- `workflow_eval_suite_ready`
- `needs_rework`
- `needs_replan`
- `workflow_eval_suite_published`

### Planned artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local input snapshot |
| `capture_selected_workflow_contract` | request, invocation contract | `selected_workflow_capability.json` | authoritative selected-workflow contract snapshot |
| `frame_evaluation_target` | request, invocation contract, selected-workflow contract, framework docs | `evaluation_request_brief.md`, `evaluation_dimensions.md` | authoritative evaluation framing package |
| `design_eval_cases` | request, invocation contract, selected-workflow contract, framing artifacts | `benchmark_case_matrix.md`, `edge_case_matrix.md`, `adversarial_case_matrix.md`, `eval_case_manifest.json`, `eval_rubric.md` | authoritative case/rubric design surface prior to publication validation |
| `package_workflow_eval_suite` | request, invocation contract, selected-workflow contract, checklist, framing and design artifacts | `workflow_eval_suite.md`, `workflow_eval_suite_summary.json`, `workflow_eval_next_action.md` | terminal human-readable and machine-readable eval-suite package |
| `publish_workflow_eval_suite` | selected-workflow contract, design artifacts, package artifacts | `validated_eval_case_manifest.json`, `workflow_eval_suite_receipt.json` | deterministic terminal receipt plus authoritative validated eval-case manifest |

### Planned runtime-injected control contract

The workflow must continue using only:

- `expected_output_schema`
- `available_routes`
- `route_contracts`

Planned payload models:

- `EvaluationTargetFramingPayload`
- `EvalCaseDesignPayload`
- `WorkflowEvalSuitePayload`

### Prompt/package expectations

- Prompt files: `prompts/frame_producer.md`, `prompts/frame_verifier.md`, `prompts/design_producer.md`, `prompts/design_verifier.md`, `prompts/package_producer.md`, `prompts/package_verifier.md`, and `prompts/README.md`
- Asset: `assets/eval_suite_checklist.md`
- Decision/evidence doc: `docs/workflows/workflow_to_eval_suite.md`
- Runtime proof: `tests/runtime/test_workflow_to_eval_suite.py`

### Verification and evidence contract

- Workflow discovery must find the package by canonical name and alias.
- Compilation must expose typed route contracts for the three pair steps.
- Runtime proof must cover:
- successful terminal publication of the eval suite, summary, next action, validated eval-case manifest, and receipt
- stable publication of `selected_workflow_capability.json`, `eval_case_manifest.json`, and `validated_eval_case_manifest.json`
- proof that the workflow stops at suite publication rather than executing the selected workflow
- publication validation that rejects malformed case kinds, duplicate case ids, invalid workflow-parameter mappings, unknown expected artifacts, and summary drift from the validated manifest

### Rework / replan / block / fail policy

- `needs_rework`: local repair inside the same framing, case-design, or packaging boundary.
- `needs_replan`: the selected workflow, evaluation objective, or acceptance boundary changed materially enough that an earlier work item must be revisited.
- `blocked`: a missing prerequisite or repository fact prevents a credible suite package.
- `failed`: irreconcilable contradictions make the current eval suite non-credible.

### Recursive self-improvement policy

- `workflow_idea_to_workflow_package` remains the standing greenfield authoring path and was reconsidered before choosing this narrower evaluation layer.
- `workflow_to_eval_suite` should become the standing evaluation-authoring layer that later refinement workflows consume rather than re-deriving eval suites ad hoc.
- Promotion remains evidence-gated by workflow-local artifacts, the deterministic publish step, runtime tests, and recursive-memory closeout updates.

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Dedicated authoring-only evaluation helper seam | Gives future evaluation/refinement workflows one reusable way to validate and canonicalize eval-case manifests against a selected workflow while keeping runtime/provider boundaries narrow | Adds one new stdlib module plus docs/tests, but keeps evaluation policy visible in workflow code and artifacts | Chosen |
| Broaden `stdlib/adaptation.py` into a generic selected-workflow planning helper module | Reuses an existing selected-workflow module name and may reduce file count | Blurs adaptation and evaluation responsibilities, making future authoring seams harder to reason about | Rejected |
| Runtime-owned or manifest-owned evaluation registry | Could centralize suite metadata and later execution behavior | Widens framework/runtime or `workflow.toml` scope, hides workflow meaning, and violates the artifact-first, workflow-owned SOP doctrine | Rejected |

### Chosen framework slice

- Add `stdlib/evaluation.py` and export it from `stdlib/__init__.py`.
- Reuse `write_selected_workflow_capability_snapshot(...)` from `stdlib/adaptation.py`; do not duplicate selected-workflow snapshot logic.
- Planned helper surface:
- `write_validated_eval_case_manifest(ctx, workflow, case_manifest, relative_path="validated_eval_case_manifest.json")`
- Helper rules:
- write only workflow-local JSON under `ctx.workflow_folder`
- validate unique case ids, legal case kinds (`benchmark`, `edge`, `adversarial`), non-empty case prompts, non-empty expected artifacts, and per-case workflow parameters via the shared loader coercion path
- validate expected artifacts against the selected workflow's compiled artifact surface derived from the selected-workflow capability snapshot
- do not add CLI flags, manifest fields, runtime-owned evaluation execution, or hidden downstream routing
- Update `docs/authoring.md` and `tests/unit/test_stdlib_and_extensions.py` to freeze the helper boundary.

## Meaningful design decisions

### 1. Evaluation target boundary

- Alternatives considered:
- force composition from `task_to_candidate_workflow_set` or `task_to_workflow_strategy` every time
- accept a whole-portfolio target and let the workflow author many suites in one run
- accept one explicit `selected_workflow` plus the same task-context fields already used by the front door and adaptation building block
- Selected: one explicit `selected_workflow` plus standard task-context fields
- Why: it keeps the building block reusable both standalone and downstream of existing portfolio workflows without forcing redundant retrieval or exploding the work-item boundary.

### 2. Case-design boundary

- Alternatives considered:
- collapse framing, case design, and packaging into one monolithic producer/verifier loop
- split benchmark, edge, and adversarial design into separate child workflows immediately
- keep one dedicated design step that writes category matrices, a proposed eval-case manifest, and a rubric before terminal packaging
- Selected: one dedicated design step
- Why: it keeps the artifact family coherent, gives the verifier a clear acceptance surface, and avoids speculative child-workflow extraction before the base eval package exists.

### 3. Validation boundary

- Alternatives considered:
- let the provider write the final authoritative eval-case manifest directly
- validate case data informally during design and trust it during packaging
- let the provider propose the manifest, then validate/canonicalize it in the publish step through a shared authoring helper
- Selected: provider proposal plus deterministic publish-step validation/canonicalization
- Why: the publish step becomes the authoritative guard against duplicate ids, invalid case kinds, bad workflow params, unknown expected artifacts, and summary drift.

### 4. Reuse boundary

- Alternatives considered:
- add a second eval-specific selected-workflow snapshot helper
- inline selected-workflow inspection logic inside the new workflow package
- reuse the existing selected-workflow snapshot helper and add only the missing evaluation-manifest validation seam
- Selected: reuse the existing snapshot helper and add only eval-manifest validation
- Why: it compounds the existing adaptation seam instead of forking near-duplicate authoring helpers.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Workflow-only implementation with local publish validation | Add `workflow_to_eval_suite` and keep all case-validation logic inside its publish step | Smallest diff, but duplicates validation logic future refinement workflows will need again | Rejected |
| New evaluation helper seam plus dedicated workflow package plus docs/tests/memory updates | Add one reusable validation helper, implement the new package on top of it, and land docs/tests/recursive-memory updates together | Slightly broader change set, but the clearest reusable and inspectable design | Selected |
| Fold evaluation authoring into the builder or a future refinement workflow instead of a standalone package | Reduces package count | Leaves the repository without a reusable eval-authoring layer and couples evaluation work to unrelated workflow responsibilities | Rejected |

## Milestones

### Phase 1: Evaluation helper seam

- Add `stdlib/evaluation.py` and exports.
- Implement `write_validated_eval_case_manifest(...)` on top of the existing loader and selected-workflow capability surfaces.
- Document the seam in `docs/authoring.md`.
- Extend unit coverage in `tests/unit/test_stdlib_and_extensions.py`.
- Acceptance:
- helper stays under `ctx.workflow_folder`
- case validation reuses the existing workflow parameter coercion path and selected-workflow capability artifact
- no CLI, runtime, or manifest contract changes

### Phase 2: `workflow_to_eval_suite`

- Add the new workflow package under `workflows/workflow_to_eval_suite/`.
- Implement params, contracts, prompts, checklist asset, workflow logic, publication validation, docs, and runtime tests.
- Publication validation must reject malformed case kinds, duplicate case ids, invalid per-case workflow parameters, unknown expected artifacts, missing authoritative artifacts, or mismatches between the summary and validated eval-case manifest.
- Acceptance:
- workflow discovery and compilation work from the repo root
- scripted runtime proof publishes the terminal suite, summary, next action, validated eval-case manifest, and receipt
- workflow stops at suite publication and does not auto-run the selected workflow

### Phase 3: Recursive memory and regression proof

- Update `.autoloop_recursive/framework_evolution_charter.md`, `.autoloop_recursive/framework_roadmap.md`, `.autoloop_recursive/framework_gap_ledger.md`, and `.autoloop_recursive/workflow_candidate_ledger.md`.
- Update `tests/test_architecture_baseline_docs.py` and any closeout-proof expectations that now depend on the cycle-7 baseline.
- Run targeted validation and record the cycle-7 closeout proof in the recursive memory files.
- Acceptance:
- recursive memory records that the builder remained credible, `workflow_to_eval_suite` shipped, and the evaluation helper seam is the chosen framework slice
- architecture-baseline docs/tests describe cycle 7 accurately
- closeout validation passes without widening runtime/provider control surfaces

## Interface definitions

### New stdlib surface

- `stdlib/evaluation.py`
- `write_validated_eval_case_manifest(ctx, workflow, case_manifest, relative_path="validated_eval_case_manifest.json")`

### Reused stdlib surface

- `write_selected_workflow_capability_snapshot(...)` from `stdlib/adaptation.py`
- `write_invocation_contract(...)` and `write_publication_receipt(...)` from `stdlib/lifecycle.py`

### New workflow package surface

- `workflows/workflow_to_eval_suite/__init__.py`
- `workflows/workflow_to_eval_suite/params.py`
- `workflows/workflow_to_eval_suite/contracts.py`
- `workflows/workflow_to_eval_suite/workflow.py`
- `workflows/workflow_to_eval_suite/workflow.toml`
- `workflows/workflow_to_eval_suite/prompts/*.md`
- `workflows/workflow_to_eval_suite/assets/eval_suite_checklist.md`

### Updated docs/tests surface

- `docs/authoring.md`
- `docs/workflows/workflow_to_eval_suite.md`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/runtime/test_workflow_to_eval_suite.py`
- `tests/test_architecture_baseline_docs.py`
- `.autoloop_recursive/*.md` standing memory files

### Compatibility notes

- No public CLI, config, manifest, workspace, or provider contract changes are planned for cycle 7.
- The request snapshot's stale `src/autoloop/...` references should be treated as historical names only; implementation should continue targeting the current repo-root package layout and docs.
- Existing helper/test surfaces that assert exact portfolio contents or deferred-idea lists may need additive updates to acknowledge the new workflow and cycle-7 memory baseline.

## Regression prevention, validation, and rollback

- Keep runtime/provider control narrow: only `expected_output_schema`, `available_routes`, and `route_contracts` remain runtime-injected.
- Do not add auto-execution of the selected workflow, runtime-owned evaluation execution, or new `workflow.toml` semantics.
- Keep publish-time validation mechanical and authoring-owned; prompts stay provider-facing local execution contracts.
- Limit file edits to cycle-7 surfaces; do not absorb unrelated dirty migration files.
- Targeted validation command:

```bash
.venv/bin/pytest -q \
  tests/unit/test_stdlib_and_extensions.py \
  tests/runtime/test_workflow_to_eval_suite.py \
  tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py \
  tests/runtime/test_task_to_candidate_workflow_set.py \
  tests/runtime/test_task_to_workflow_strategy.py \
  tests/runtime/test_workflow_builder_package.py \
  tests/test_architecture_baseline_docs.py
```

- Rollback should stay phase-local:
- revert the helper seam if unit/doc boundary tests fail
- revert the workflow package if runtime publication/validation proof fails
- revert recursive-memory/test-baseline updates if they describe behavior the code does not actually ship

## Risk register

- Evaluation helper seam grows beyond authoring support
- Risk: helper starts owning policy, execution, or manifest semantics that should stay visible in workflow code and docs.
- Control: keep one narrow helper focused on eval-case validation/canonicalization only and freeze its boundary in `docs/authoring.md` tests.

- Eval-case manifest drift
- Risk: provider-authored manifest, summary, and receipt diverge or silently omit required case categories.
- Control: deterministic publish-step validation plus runtime tests that reject malformed manifests and summary drift.

- Selected-workflow surface mismatch
- Risk: expected artifacts or workflow parameters in eval cases drift from the real selected workflow contract.
- Control: derive validation from `selected_workflow_capability.json` and the shared loader coercion path instead of duplicating schema rules.

- Builder-priority regression
- Risk: cycle 7 accidentally weakens the standing claim that the builder is already credible.
- Control: keep the builder as an explicitly reconsidered candidate, record why it was not re-chosen, and update recursive memory accordingly.

- Baseline-doc/test drift
- Risk: recursive memory and architecture-baseline tests fall out of sync with the shipped cycle-7 behavior.
- Control: update the four standing memory files and `tests/test_architecture_baseline_docs.py` in the same phase as closeout validation.
