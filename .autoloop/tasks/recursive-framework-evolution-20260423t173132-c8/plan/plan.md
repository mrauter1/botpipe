# Cycle 8 Plan

## Scope considered

- Authoritative inputs reviewed: the immutable request snapshot, the current run raw log, the standing recursive memory files, the current repo-root framework/docs/workflow packages, and the empty cycle-8 plan artifacts.
- No clarifications were appended after run start, so the initial request snapshot remains authoritative for this turn.
- The request snapshot's mandatory inspection paths are stale in this checkout. The current authoritative equivalents are repo-root `docs/architecture.md`, `docs/authoring.md`, `core/`, `runtime/`, `stdlib/`, and repo-root `workflows/`.
- The worktree is dirty from broader migration work. Cycle 8 implementation must stay scoped to the paired refinement workflow, its authoring-only framework seam, proof/docs, and the required recursive-memory files; unrelated dirty files remain out of scope.
- In scope:
- ship one new high-value reusable workflow building block
- ship one paired framework improvement that keeps runtime/provider boundaries narrow and mechanical
- update workflow docs, targeted tests, architecture-baseline docs, and `.autoloop_recursive/` memory in the same change set
- Out of scope:
- `recursive_autoloop/` wrapper/template cleanup
- widening `workflow.toml`
- runtime-owned refinement execution, runtime-owned routing, or hidden promotion automation
- public CLI, workspace-layout, provider, or session-contract changes

## Current findings

- `workflow_idea_to_workflow_package` remains a credible workflow-builder baseline. The package, decision-record doc, and runtime proof in `tests/runtime/test_workflow_builder_package.py` satisfy the current builder standard, so cycle 8 does not need another builder-first addition.
- The portfolio now has a visible builder, a front door, candidate retrieval, adaptation planning, and evaluation-suite authoring. The clearest missing layer is the closed-loop consumer that turns evaluation evidence into concrete workflow-package improvements.
- The roadmap, charter, and candidate ledger already converge on `workflow_and_eval_to_refined_workflow_package` as the strongest deferred follow-on after cycle 7.
- Existing reusable seams already cover most of the deterministic work this cycle needs:
- `stdlib/lifecycle.py` covers deterministic bootstrap and publication receipts
- `stdlib/composition.py` covers explicit child composition where needed
- `stdlib/adaptation.py` covers selected-workflow contract capture and parameter validation
- `stdlib/evaluation.py` covers validation of eval-case manifests against a selected workflow
- Missing seam: a narrow authoring-only way to snapshot one selected workflow's editable authoring surface so refinement workflows can inspect package files, prompt files, asset files, docs, and runtime-test paths without ad hoc repo scraping or manifest expansion.

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Mandatory builder baseline and still the greenfield path when the portfolio has a real gap | Already credible in code, docs, and tests, so another builder-first cycle would delay the stronger closed-loop refinement gap | Deferred |
| `workflow_run_history_to_failure_modes` | Valuable diagnostic layer for clustering failures, human escalations, and recurring weak points | Strong follow-on, but it is less leverage right now because the repository still lacks the consumer that turns evaluation evidence into concrete package changes | Deferred |
| `workflow_and_eval_to_refined_workflow_package` | Turns one selected workflow plus evaluation evidence into an explicit candidate refinement package, verification artifacts, and promotion/rollback evidence | Requires a narrow authoring-surface seam plus careful baseline/candidate separation, but it directly closes the current builder -> eval -> refine loop | Chosen |

### Why the chosen addition wins

- Problem solved: convert a workflow package plus evaluation evidence into a concrete refined workflow package instead of leaving recursive improvement stranded at suite publication.
- Likely sponsors: workflow maintainers, engineering-productivity owners, AI platform teams, quality/reliability leads, and recursive portfolio operators.
- Classification: reusable workflow building block.
- Why Autoloop fits: the work spans durable evidence review, bounded design/rework loops, direct package edits, verification artifacts, and promotion/rollback records.
- Why one-shot is insufficient: credible refinement needs explicit framing of the failure surface, a justified change strategy, controlled package edits, proof that the updated workflow still compiles/tests, and a deterministic publication receipt.
- Terminal outcome: an explicit baseline snapshot plus candidate refinement package, refinement summary, evaluation-delta evidence, promotion record, rollback plan, and receipt.

## Chosen addition contract

- Package path: `workflows/workflow_and_eval_to_refined_workflow_package/`
- Discovery target: `autoloop workflows show workflow_and_eval_to_refined_workflow_package`
- Direct invocation:

```bash
autoloop run workflow_and_eval_to_refined_workflow_package <task-id> \
  --message "Refine the release go/no-go workflow using evaluation evidence from the latest quality review." \
  -wf selected_workflow release_candidate_to_go_no_go \
  -wf task_title "Release go/no-go refinement from evaluation evidence" \
  -wf evaluation_summary_path .autoloop/evals/release_go_no_go_eval_summary.json \
  -wf evaluation_findings_path .autoloop/evals/release_go_no_go_eval_findings.md \
  -wf failure_modes_path .autoloop/evals/release_go_no_go_failure_modes.md \
  -wf sponsor_role "engineering productivity" \
  -wf desired_outcome "Publish a verified refinement candidate package and promotion bundle for the selected workflow." \
  -wf constraints "Keep runtime control narrow, preserve explicit baseline/candidate separation, and stop before promotion." \
  -wf target_test_command "pytest -q tests/runtime/test_release_candidate_to_go_no_go.py"
```

- Parameters:
- `selected_workflow` required
- `task_title` required
- `evaluation_summary_path` required
- `evaluation_findings_path` required
- `failure_modes_path` optional
- `sponsor_role` optional
- `desired_outcome` optional
- `constraints` optional and repeatable
- `target_test_command` optional, default `pytest -q`

### Workflow objective

Turn one selected workflow plus evaluation evidence into a validated candidate workflow package and promotion bundle without widening runtime-owned control logic or hiding refinement/promotion policy in runtime code.

### Global deterministic workflow responsibilities

- Bootstrap the run-local invocation contract.
- Capture authoritative local copies of the supplied evaluation evidence, one selected workflow's capability plus authoring surface, and an explicit workflow-local baseline snapshot.
- Keep refinement framing, change planning, candidate package implementation, and verification as separate work items.
- Validate the selected workflow's authoring surface mechanically before candidate generation and validate the candidate package surface separately before publication.
- Publish only after the baseline snapshot, candidate package surface, verification artifacts, promotion record, rollback plan, and receipt all exist and agree.

### Provider-owned cognitive responsibilities

- Interpret evaluation evidence and decide what should change in the selected workflow.
- Design a refinement strategy that preserves the workflow's purpose while addressing concrete failure modes.
- Update workflow code, prompts, docs, assets, and tests inside a workflow-local candidate package surface that mirrors the selected workflow boundary.
- Produce justification, candidate-vs-baseline evidence, and promotion/rollback guidance.

### Work-item boundary doctrine

- `capture_refinement_context`: deterministic evidence, selected-workflow surface capture, and baseline snapshot publication only.
- `frame_refinement_request`: refinement framing, failure-surface interpretation, and acceptance criteria only.
- `design_refinement_plan`: concrete change strategy, file-level plan, and regression guardrails only.
- `implement_refined_workflow`: workflow-local candidate package creation plus local build/diff reporting only.
- `evaluate_refined_workflow`: candidate verification evidence, evaluation delta, promotion record, and rollback plan only.
- `needs_rework`: the same work-item boundary still holds.
- `needs_replan`: the selected workflow, accepted refinement boundary, or artifact graph changed materially.

### Role topology

- deterministic `bootstrap`
- deterministic `capture_refinement_context`
- `workflow refinement framer` / `refinement-request verifier`
- `workflow refinement strategist` / `refinement-plan verifier`
- `workflow refiner` / `refinement-build verifier`
- `workflow refinement evaluator` / `refinement-release verifier`
- deterministic `publish_refined_workflow`

### Planned control flow

1. `bootstrap`
2. `capture_refinement_context`
3. `frame_refinement_request`
4. `design_refinement_plan`
5. `implement_refined_workflow`
6. `evaluate_refined_workflow`
7. `publish_refined_workflow`

### Planned route grammar

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `refinement_context_captured`
- `refinement_request_framed`
- `refinement_plan_designed`
- `workflow_refinement_applied`
- `workflow_refinement_evaluated`
- `workflow_refinement_published`
- `needs_rework`
- `needs_replan`

### Planned artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local input snapshot |
| `capture_refinement_context` | request, invocation contract, external evaluation evidence paths, selected workflow reference | `selected_workflow_capability.json`, `selected_workflow_authoring_surface.json`, `baseline_workflow_surface/`, `baseline_workflow_manifest.json`, `baseline_evaluation_summary.json`, `baseline_evaluation_findings.md`, optional `baseline_failure_modes.md` | authoritative refinement-input bundle plus explicit baseline snapshot |
| `frame_refinement_request` | request, invocation contract, captured refinement context, framework docs | `refinement_request_brief.md`, `refinement_acceptance_criteria.md` | authoritative refinement framing package |
| `design_refinement_plan` | request, invocation contract, captured refinement context, framing artifacts | `refinement_strategy.md`, `workflow_change_plan.md`, `regression_guardrails.md` | authoritative change and regression plan |
| `implement_refined_workflow` | captured refinement context, planning artifacts, baseline workflow surface | `candidate_workflow_surface/`, `candidate_workflow_manifest.json`, `refinement_build_report.md`, `candidate_diff_summary.md` | authoritative candidate refinement package plus local diff evidence |
| `evaluate_refined_workflow` | candidate workflow surface, baseline snapshot, captured context, planning artifacts, build artifacts, target test command | `refinement_verification_report.md`, `evaluation_delta_report.md`, `promotion_record.md`, `rollback_plan.md` | authoritative candidate verification and promotion/rollback surface |
| `publish_refined_workflow` | selected-workflow capability snapshot, authoring-surface snapshot, baseline manifest, candidate manifest, verification artifacts | `workflow_refinement_receipt.json` | deterministic terminal receipt proving the candidate package surface is explicit, validated, and ready for later promotion |

### Planned runtime-injected control contract

The workflow must continue using only:

- `expected_output_schema`
- `available_routes`
- `route_contracts`

Planned payload models:

- `RefinementRequestFramingPayload`
- `WorkflowRefinementPlanPayload`
- `WorkflowRefinementBuildPayload`
- `WorkflowRefinementEvaluationPayload`

### Planned step prompt contracts

- `prompts/frame_producer.md`
- Role: `workflow refinement framer`
- Required reads: `request.md`, `invocation_contract.json`, `selected_workflow_capability.json`, `selected_workflow_authoring_surface.json`, `baseline_workflow_manifest.json`, `baseline_evaluation_summary.json`, `baseline_evaluation_findings.md`, optional `baseline_failure_modes.md`, `docs/architecture.md`, and `docs/authoring.md`
- Required writes: `refinement_request_brief.md` and `refinement_acceptance_criteria.md`
- Legal routes: `refinement_request_framed`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: make the selected workflow's current purpose, the observed weakness, the intended improvement surface, and the acceptance boundary explicit enough for concrete file-level planning
- Forbidden/out of scope: do not edit the authoritative workflow package yet, do not invent new runtime-owned metadata, do not leave evidence interpretation or target files implicit, and do not silently widen the workflow boundary

- `prompts/frame_verifier.md`
- Role: `refinement-request verifier`
- Required reads: the same framing inputs plus `refinement_request_brief.md` and `refinement_acceptance_criteria.md`
- Required writes: verifier control metadata only through `RefinementRequestFramingPayload`; leave workflow/package files untouched unless local repair is requested through `needs_rework`
- Legal routes: `refinement_request_framed`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: confirm the refinement boundary, failure interpretation, expected downstream evidence, and route choice are explicit and still local to the same selected workflow unless a real replan is required
- Forbidden/out of scope: do not author the change plan, do not approve framing that leaves file ownership or acceptance criteria ambiguous, and do not move provider-facing SOP into runtime-only fields

- `prompts/design_producer.md`
- Role: `workflow refinement strategist`
- Required reads: `request.md`, `invocation_contract.json`, captured refinement context, `refinement_request_brief.md`, and `refinement_acceptance_criteria.md`
- Required writes: `refinement_strategy.md`, `workflow_change_plan.md`, and `regression_guardrails.md`
- Legal routes: `refinement_plan_designed`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: publish a concrete change strategy with file-level intent, prompt/contract/test/doc impacts, regression guardrails, and a rationale tied directly to the supplied evaluation evidence
- Forbidden/out of scope: do not edit package files yet, do not defer core decisions into generic prose, do not assume hidden runtime support, and do not omit rollback/regression considerations

- `prompts/design_verifier.md`
- Role: `refinement-plan verifier`
- Required reads: the planning-step inputs plus `refinement_strategy.md`, `workflow_change_plan.md`, and `regression_guardrails.md`
- Required writes: verifier control metadata only through `WorkflowRefinementPlanPayload`; leave planning artifacts intact unless local repair is requested through `needs_rework`
- Legal routes: `refinement_plan_designed`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: confirm the plan is file-specific, evidence-driven, scoped to the selected workflow surface, and explicit about which changes are local repair versus material replan
- Forbidden/out of scope: do not approve vague "improve prompts/tests" guidance, do not collapse regression controls into a generic checklist, and do not bless a plan that edits outside the selected workflow boundary without explicit cause

- `prompts/implement_producer.md`
- Role: `workflow refiner`
- Required reads: captured refinement context, planning artifacts, the baseline workflow surface, and the selected workflow files named in `selected_workflow_authoring_surface.json`
- Required writes: `candidate_workflow_surface/`, `candidate_workflow_manifest.json`, `refinement_build_report.md`, and `candidate_diff_summary.md`
- Legal routes: `workflow_refinement_applied`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: make the selected workflow materially better against the stated evidence, keep prompt-template doctrine explicit in the candidate files, and record exactly which candidate files changed relative to the baseline
- Forbidden/out of scope: do not mutate the authoritative selected workflow package, do not edit unrelated workflows, do not widen `workflow.toml`, and do not claim verification that has not been produced

- `prompts/implement_verifier.md`
- Role: `refinement-build verifier`
- Required reads: the implementation-step inputs plus `candidate_workflow_surface/`, `candidate_workflow_manifest.json`, `refinement_build_report.md`, and `candidate_diff_summary.md`
- Required writes: verifier control metadata only through `WorkflowRefinementBuildPayload`; leave the candidate workflow surface intact unless local repair is requested through `needs_rework`
- Legal routes: `workflow_refinement_applied`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: confirm the candidate workflow surface is explicit, the baseline-to-candidate manifest is explicit, the candidate still reflects the accepted plan, and any replan request is tied to a material contract or artifact-boundary change
- Forbidden/out of scope: do not redo evaluation work here, do not approve hidden candidate files not captured in the manifest/report, and do not accept prompt/template changes that obscure route or artifact handling

- `prompts/evaluate_producer.md`
- Role: `workflow refinement evaluator`
- Required reads: captured refinement context, planning artifacts, the baseline and candidate workflow surfaces, `candidate_workflow_manifest.json`, `refinement_build_report.md`, `candidate_diff_summary.md`, and the configured test command
- Required writes: `refinement_verification_report.md`, `evaluation_delta_report.md`, `promotion_record.md`, and `rollback_plan.md`
- Legal routes: `workflow_refinement_evaluated`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: verify the candidate workflow surface still compiles through an isolated overlay or equivalent deterministic validation path, compare the candidate against the supplied baseline evidence, and produce explicit promotion/rollback guidance
- Forbidden/out of scope: do not invent runtime-owned promotion behavior, do not publish the receipt directly, do not claim measured improvement without citing concrete evidence, and do not skip rollback detail for candidate-to-baseline promotion

- `prompts/evaluate_verifier.md`
- Role: `refinement-release verifier`
- Required reads: the evaluation-step inputs plus `refinement_verification_report.md`, `evaluation_delta_report.md`, `promotion_record.md`, and `rollback_plan.md`
- Required writes: verifier control metadata only through `WorkflowRefinementEvaluationPayload`; leave the verification artifacts intact unless local repair is requested through `needs_rework`
- Legal routes: `workflow_refinement_evaluated`, `needs_rework`, `needs_replan`, `question`, `blocked`, `failed`
- Evidence expectation: confirm the verification package is publication-ready, the delta report is tied to supplied baseline evidence plus the candidate package, and promotion/rollback instructions are concrete enough for deterministic later promotion
- Forbidden/out of scope: do not silently validate missing test proof, do not approve contradictory promotion/rollback guidance, and do not leave the receipt/publish step to infer baseline/candidate boundaries or authoritative artifacts

- `prompts/README.md`
- Required contents: one concise index of the eight prompts, the step-to-artifact map, reserved/application route grammar, verifier JSON expectations, and the rule that prompt templates carry provider-facing guidance while the runtime injects only `expected_output_schema`, `available_routes`, and `route_contracts`

### Prompt/package expectations

- Prompt files: `prompts/frame_producer.md`, `prompts/frame_verifier.md`, `prompts/design_producer.md`, `prompts/design_verifier.md`, `prompts/implement_producer.md`, `prompts/implement_verifier.md`, `prompts/evaluate_producer.md`, `prompts/evaluate_verifier.md`, and `prompts/README.md`
- Asset: `assets/refinement_package_checklist.md`
- Decision/evidence doc: `docs/workflows/workflow_and_eval_to_refined_workflow_package.md`
- Runtime proof: `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`

### Verification and evidence contract

- Workflow discovery must find the package by canonical name and alias.
- Compilation must expose typed route contracts for the four pair steps.
- Runtime proof must cover:
- successful terminal publication of a baseline snapshot, candidate workflow surface, and refinement receipt without mutating the authoritative selected workflow package
- stable publication of `selected_workflow_capability.json`, `selected_workflow_authoring_surface.json`, `baseline_workflow_manifest.json`, `candidate_workflow_manifest.json`, `evaluation_delta_report.md`, and `workflow_refinement_receipt.json`
- proof that the candidate surface can be validated through an isolated overlay or equivalent deterministic temp-copy path before later promotion
- deterministic publish-step validation that the candidate surface matches the selected workflow boundary and that the authoritative selected workflow was not mutated during refinement publication
- rejection of missing evaluation evidence artifacts, selected-workflow/authoring-surface mismatches, baseline/candidate manifest drift, and refinement receipts that do not match the selected workflow name

### Rework / replan / block / fail policy

- `needs_rework`: local repair inside the same framing, planning, implementation, or evaluation boundary.
- `needs_replan`: the selected workflow, accepted refinement boundary, or required artifact graph changed materially enough that earlier work must be revisited.
- `blocked`: a missing prerequisite or repository fact prevents a credible refinement package.
- `failed`: irreconcilable contradictions make the current refinement package non-credible.

### Recursive self-improvement policy

- `workflow_idea_to_workflow_package` remains the standing greenfield authoring path and was reconsidered before choosing this narrower closed-loop refinement layer.
- `workflow_to_eval_suite` remains the standing evaluation-authoring building block; this workflow must consume published evaluation evidence rather than re-deriving eval artifacts ad hoc.
- `workflow_run_history_to_failure_modes` remains a strong next follow-on, but cycle 8 should first ship the consumer that turns evaluation evidence into package changes.
- Promotion remains evidence-gated by workflow-local artifacts, deterministic publish-step validation, runtime tests, and recursive-memory closeout updates.

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Dedicated authoring-only refinement surface seam | Gives refinement-oriented workflows one reusable way to snapshot a selected workflow's editable package surface without widening runtime behavior or `workflow.toml` | Adds one focused stdlib seam plus docs/tests, but keeps file-selection and change policy visible in workflow code and artifacts | Chosen |
| Broaden `write_selected_workflow_capability_snapshot(...)` to include editable file inventory | Reuses an existing selected-workflow helper name and may reduce file count | Blurs compiled contract inspection with authoring-surface inspection, making later authoring helpers and tests harder to reason about | Rejected |
| Runtime-owned refinement/promotion automation or manifest-owned authoring metadata | Could centralize selected-workflow editing and publication behavior | Hides workflow meaning in runtime/manifest code, widens framework surface prematurely, and violates the explicit workflow-owned SOP doctrine | Rejected |

### Chosen framework slice

- Add `stdlib/refinement.py` and export it from `stdlib/__init__.py`.
- Reuse `resolve_workflow_reference(...)`, `discover_workflow_catalog(...)`, and the existing selected-workflow capability seam; do not duplicate workflow resolution or widen `workflow.toml`.
- Planned helper surface:
- `write_selected_workflow_authoring_surface(ctx, workflow, relative_path="selected_workflow_authoring_surface.json")`
- Helper rules:
- write only workflow-local JSON under `ctx.workflow_folder`
- capture one selected workflow's package-level file inventory, including `__init__.py`, `workflow.toml`, `workflow.py`, optional `params.py`, optional `contracts.py`, prompt files, asset files, linked workflow doc path when present, and inferred `tests/runtime/test_<workflow>.py` path when present
- do not mutate the selected workflow package
- do not capture provider-facing policy, route selection, or runtime behavior
- keep later refinement decisions in workflow code and prompts, not the helper payload

## Meaningful design decisions

### 1. Workflow boundary

- Alternatives considered:
- ship `workflow_run_history_to_failure_modes` first
- repeat another builder-first workflow cycle
- ship `workflow_and_eval_to_refined_workflow_package` as the next reusable closed-loop building block
- Selected: ship `workflow_and_eval_to_refined_workflow_package`
- Why: the builder is already credible and the strongest leverage now is the missing consumer that turns evaluation evidence into package changes.

### 2. Evidence boundary

- Alternatives considered:
- auto-discover the latest evaluation artifacts from run history
- auto-run `workflow_to_eval_suite` or a future eval runner inside refinement
- require explicit evaluation evidence artifact paths as the legal input contract
- Selected: explicit evaluation evidence artifact paths
- Why: it keeps the refinement workflow inspectable, avoids hidden downstream execution, and works before the repository has a runtime-owned evaluation runner.

### 3. Publication boundary

- Alternatives considered:
- stage a sibling candidate workflow package
- stage a workflow-local candidate surface plus explicit promotion bundle
- refine the selected workflow in place with deterministic rollback evidence and publish-time validation
- Selected: stage a workflow-local candidate surface plus explicit promotion bundle
- Why: it preserves the request's explicit baseline/candidate/promotion doctrine while still producing a useful terminal refinement package another operator or workflow can validate and promote later.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Workflow-only implementation with ad hoc repo scraping | Build the refinement package directly and let prompts/workflow code discover selected-workflow files manually | Smallest initial diff, but duplicates file-discovery logic and weakens inspectability | Rejected |
| New refinement surface seam plus dedicated workflow package plus explicit candidate publication proof/docs | Add the helper seam, build the workflow on top of it, and prove end-to-end baseline/candidate publication in a temp repo copy | Slightly broader change set, but the clearest reusable and inspectable design | Selected |
| Fold refinement into `workflow_idea_to_workflow_package` or `workflow_to_eval_suite` | Reuse an existing package and avoid adding a new workflow directory | Collapses workflow boundaries and leaves no reusable closed-loop refinement building block | Rejected |

## Milestones

1. Add the authoring-only refinement surface seam in `stdlib/refinement.py`, export it, document the boundary in `docs/authoring.md`, and extend unit coverage.
2. Ship `workflow_and_eval_to_refined_workflow_package` with params, contracts, prompts, checklist asset, candidate-scoped publish-side validation, workflow doc, and runtime proof.
3. Update `.autoloop_recursive/` memory, closeout/baseline tests, and targeted pytest proof so cycle 8 becomes the new explicit recursive baseline.

## Compatibility / regression controls

- No public CLI, provider, session, workspace, or manifest-contract changes are allowed in cycle 8.
- The runtime/provider boundary must remain the same narrow contract: `expected_output_schema`, `available_routes`, and `route_contracts`.
- The chosen helper seam must stay authoring-only and write under `ctx.workflow_folder`; it must not add automatic editing, routing, or promotion behavior.
- The refinement workflow must keep candidate artifacts scoped to the selected workflow package boundary, its linked doc, and its runtime test, and must reject mismatches between the selected-workflow capability snapshot, the authoring-surface snapshot, and the baseline/candidate manifests.
- Architecture-baseline tests are exact-string sensitive; updates to `docs/authoring.md` and `.autoloop_recursive/*.md` must land in lockstep with the new workflow/helper implementation.
- Runtime proof must run in an isolated temp repo copy so candidate overlay behavior is verified without mutating the real checkout during tests.

## Risk register

1. Risk: the new helper seam grows into hidden authoring automation instead of staying a narrow selected-workflow surface snapshot.
   - Control: freeze the helper boundary in `docs/authoring.md` and `tests/unit/test_stdlib_and_extensions.py`; keep the helper write-only for workflow-local JSON and exclude any mutation behavior.
2. Risk: baseline and candidate package boundaries drift or become implicit, making later promotion or rollback non-deterministic.
   - Control: require `selected_workflow_authoring_surface.json`, `baseline_workflow_manifest.json`, `candidate_workflow_manifest.json`, publish-side validation of baseline-to-candidate drift, and explicit promotion/rollback guidance.
3. Risk: refinement proof claims improvement without sufficient evidence because the repo still lacks a runtime-owned evaluation runner.
   - Control: require explicit baseline evaluation artifacts as inputs and demand a concrete `evaluation_delta_report.md` tied to those supplied artifacts plus targeted candidate compile/test evidence.
4. Risk: exact-string recursive-memory and authoring-doc tests drift from the actual shipped cycle-8 behavior.
   - Control: update `.autoloop_recursive/*.md`, `docs/authoring.md`, and `tests/test_architecture_baseline_docs.py` in the same phase and record the targeted pytest proof in the cycle-8 closeout updates.

## Validation / rollback

- Targeted proof command:

```bash
.venv/bin/pytest -q \
  tests/unit/test_stdlib_and_extensions.py \
  tests/runtime/test_workflow_builder_package.py \
  tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py \
  tests/runtime/test_workflow_to_eval_suite.py \
  tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py \
  tests/test_architecture_baseline_docs.py
```

- Rollback plan:
- revert `stdlib/refinement.py`, its export, and the authoring-doc/unit-test updates together
- revert the new workflow package, workflow doc, and runtime test together
- revert cycle-8 recursive-memory and baseline-test updates if they claim behavior or proof that the implementation does not actually ship
