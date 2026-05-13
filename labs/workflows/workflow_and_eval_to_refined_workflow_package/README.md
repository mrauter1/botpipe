# `workflow_and_eval_to_refined_workflow_package`

`workflow_and_eval_to_refined_workflow_package` is a reusable closed-loop refinement building block that turns one selected workflow plus explicit evaluation evidence into a baseline snapshot, a workflow-local candidate workflow surface, verification artifacts, and a deterministic refinement receipt. It stops before promotion so later publication and rollback remain explicit and inspectable.

## Problem and value

- Problem solved: convert evaluation evidence into a concrete candidate workflow package instead of leaving refinement stranded in prose, issue comments, or ad hoc local edits.
- Why it matters: once the portfolio can build workflows, adapt them, and author evaluation suites, the next missing layer is the consumer that turns evidence into controlled package improvements.
- Likely sponsors: engineering productivity, workflow maintainers, AI platform owners, QA and reliability leads, and recursive portfolio operators.
- Classification: reusable workflow building block.
- Why Botpipe fits: the work needs durable baseline and candidate artifacts, verifier-gated rework loops, explicit promotion and rollback evidence, and deterministic publication-side validation.
- Why one-shot is insufficient: credible refinement needs baseline capture, accepted framing, file-level planning, candidate implementation, verification artifacts, and publish-time validation that the authoritative selected workflow stayed untouched.

## Invocation

- Lab path: `labs/workflows/workflow_and_eval_to_refined_workflow_package/`
- Discovery: lab workflow; copy or reference the workflow folder explicitly before running it by name.
- Direct run:

```bash
botpipe run workflow_and_eval_to_refined_workflow_package <task-id> \
  --message "Refine the release go/no-go workflow from the latest evaluation evidence." \
  -wf selected_workflow release_candidate_to_go_no_go \
  -wf task_title "Release go/no-go refinement from evaluation evidence" \
  -wf evaluation_summary_path .botpipe/evals/release_go_no_go_eval_summary.json \
  -wf evaluation_findings_path .botpipe/evals/release_go_no_go_eval_findings.md \
  -wf failure_modes_path .botpipe/evals/release_go_no_go_failure_modes.md \
  -wf sponsor_role "engineering productivity" \
  -wf desired_outcome "Publish a verified refinement candidate package and promotion bundle for the selected workflow." \
  -wf constraints "Keep runtime control narrow, preserve explicit baseline/candidate separation, and stop before promotion." \
  -wf target_test_command "pytest -q tests/runtime/test_release_candidate_to_go_no_go.py"
```

Params:

- `selected_workflow` required
- `task_title` required
- `evaluation_summary_path` required; the JSON must include `selected_workflow_name` matching `selected_workflow`
- `evaluation_findings_path` required
- `failure_modes_path` optional
- `sponsor_role` optional
- `desired_outcome` optional
- `constraints` optional and repeatable
- `target_test_command` optional, default `pytest -q`

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Remains the workflow-builder baseline and the comparison floor for any new addition | Already credible in code, docs, and proof, so repeating another builder-first cycle would delay the stronger closed-loop refinement gap | Deferred |
| `workflow_run_history_to_failure_modes` | Valuable diagnostic layer for clustering failures, escalations, and recurring weak points | Strong follow-on, but lower leverage right now because the repository still lacked the consumer that turns evaluation evidence into package changes | Deferred |
| `workflow_and_eval_to_refined_workflow_package` | Turns one selected workflow plus evaluation evidence into a candidate refinement package with promotion and rollback artifacts | Requires careful baseline/candidate separation and publish-time boundary validation, but it directly closes the current builder -> eval -> refine loop | Chosen and shipped in cycle 8 |

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Dedicated authoring-only refinement surface seam | Gives refinement workflows one reusable way to snapshot a selected workflow's editable authoring surface without widening runtime behavior or `workflow.toml` | Adds one focused stdlib seam plus docs/tests, but keeps file-selection and change policy visible in workflow code and artifacts | Chosen in the paired framework slice and consumed here |
| Broaden `write_selected_workflow_capability_snapshot(...)` to include editable file inventory | Reuses an existing selected-workflow helper name and may reduce file count | Blurs compiled contract inspection with authoring-surface inspection, making later authoring helpers and tests harder to reason about | Rejected |
| Runtime-owned refinement or promotion automation | Could centralize selected-workflow editing and publication behavior | Hides workflow meaning in runtime code, widens the framework surface prematurely, and violates the explicit workflow-owned SOP doctrine | Rejected |

## Meaningful design decisions

### 1. Evidence boundary

- Alternatives considered:
- auto-discover the latest evaluation artifacts from run history
- auto-run `workflow_to_eval_suite` or a future evaluation runner inside refinement
- require explicit evaluation evidence artifact paths as the legal input contract
- Selected: explicit evaluation evidence artifact paths
- Why: it keeps the refinement workflow inspectable, avoids hidden downstream execution, and works before the repository has a runtime-owned evaluation runner.

### 2. Publication boundary

- Alternatives considered:
- refine the selected workflow in place with rollback notes
- stage a sibling workflow package
- stage a workflow-local candidate surface plus explicit promotion bundle
- Selected: stage a workflow-local candidate surface plus explicit promotion bundle
- Why: it preserves the request’s explicit baseline/candidate/promotion doctrine while still producing a terminal refinement package another operator or workflow can validate and promote later.

### 3. Candidate-manifest ownership

- Alternatives considered:
- let the provider hand-write `candidate_workflow_manifest.json`
- derive candidate-manifest metadata implicitly inside the publish step only
- derive `candidate_workflow_manifest.json` deterministically from `candidate_workflow_surface/` immediately after implementation
- Selected: deterministic manifest derivation after implementation
- Why: it keeps the candidate surface explicit, makes later evaluation and publication inspectable, and avoids trusting a provider-authored manifest for boundary-critical validation.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Workflow-only implementation with ad hoc repo scraping | Build the refinement package directly and let workflow code discover selected-workflow files manually | Smallest initial diff, but duplicates file-discovery logic and weakens inspectability | Rejected |
| Shared refinement-surface seam plus dedicated workflow package plus explicit candidate publication proof | Reuse the helper seam, build the refinement package on top of it, and prove baseline/candidate publication in an isolated temp repo copy | Slightly broader change set, but the clearest reusable and inspectable design | Selected |
| Fold refinement into `workflow_idea_to_workflow_package` or `workflow_to_eval_suite` | Reuse an existing package and avoid a new workflow directory | Collapses workflow boundaries and leaves no reusable closed-loop refinement building block | Rejected |

## Workflow contract

### Objective

Turn one selected workflow plus explicit evaluation evidence into a candidate refinement package without mutating the authoritative selected workflow package and without hiding promotion or rollback policy in runtime code.

### Global deterministic workflow responsibilities

- Bootstrap the run-local invocation contract.
- Capture authoritative local copies of the supplied evaluation evidence, one selected workflow’s compiled contract, one selected workflow’s editable authoring surface, and an explicit baseline workflow surface plus manifest.
- Keep framing, planning, implementation, evaluation, and publication as separate work items.
- Derive `candidate_workflow_manifest.json` deterministically from `candidate_workflow_surface/`.
- Validate baseline/candidate boundaries, authoritative-source immutability, and candidate overlay compilation or test proof before publishing the refinement receipt.

### Provider-owned cognitive responsibilities

- Interpret the baseline evaluation evidence and decide what should change in the selected workflow.
- Design a refinement strategy that preserves the workflow’s purpose while addressing the observed weakness.
- Update the candidate workflow surface, produce the build evidence, and explain the expected improvement.
- Produce explicit promotion and rollback guidance.

### Work-item boundary doctrine

- `capture_refinement_context`: deterministic baseline capture only.
- `frame_refinement_request`: evidence interpretation, refinement objective, and acceptance boundary only.
- `design_refinement_plan`: change strategy, file-level plan, and regression guardrails only.
- `implement_refined_workflow`: candidate workflow-surface implementation plus build evidence only.
- `evaluate_refined_workflow`: verification package, evaluation delta, promotion record, and rollback plan only.
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

### Control flow

1. `bootstrap`
2. `capture_refinement_context`
3. `frame_refinement_request`
4. `design_refinement_plan`
5. `implement_refined_workflow`
6. `evaluate_refined_workflow`
7. `publish_refined_workflow`

### Route grammar

Helper routes:

- `question` when provider questions are allowed by the interaction policy
- question routes use `outcome.route_fields.questions`; blocked and failed routes use nullable `outcome.route_fields.reason`

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

Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

### Artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local input snapshot |
| `capture_refinement_context` | request, invocation contract, selected-workflow reference, explicit evaluation-evidence paths | `selected_workflow_capability.json`, `selected_workflow_authoring_surface.json`, `baseline_workflow_surface/`, `baseline_workflow_manifest.json`, `baseline_evaluation_summary.json`, `baseline_evaluation_findings.md`, `baseline_failure_modes.md` | authoritative refinement input bundle plus explicit baseline snapshot |
| `frame_refinement_request` | request, invocation contract, captured context, baseline evidence, framework docs | `refinement_request_brief.md`, `refinement_acceptance_criteria.md` | authoritative refinement framing package |
| `design_refinement_plan` | request, invocation contract, captured context, framing artifacts | `refinement_strategy.md`, `workflow_change_plan.md`, `regression_guardrails.md` | authoritative change strategy and regression plan |
| `implement_refined_workflow` | captured context, planning artifacts, baseline workflow surface | `candidate_workflow_surface/`, `refinement_build_report.md`, `candidate_diff_summary.md`, deterministic `candidate_workflow_manifest.json` | authoritative candidate workflow package plus machine-readable manifest |
| `evaluate_refined_workflow` | candidate workflow surface, candidate manifest, baseline snapshot, baseline evidence, planning artifacts | `refinement_verification_report.md`, `evaluation_delta_report.md`, `promotion_record.md`, `rollback_plan.md` | authoritative candidate verification and promotion/rollback package |
| `publish_refined_workflow` | selected-workflow snapshots, baseline manifest, candidate manifest, copied baseline evidence, evaluation package | `workflow_refinement_receipt.json` | deterministic terminal receipt proving the candidate is explicit, validated, and publication-ready |

### Runtime-injected control contract

The runtime injects only:

- `expected_output_schema`
- `available_routes`
- step-local `Route.to(...)` metadata

Payload models used by the package:

- `RefinementRequestFramingPayload`
- `WorkflowRefinementPlanPayload`
- `WorkflowRefinementBuildPayload`
- `WorkflowRefinementEvaluationPayload`

### Prompt templates

- `prompts/frame_producer.md`: role `workflow refinement framer`; frames the selected workflow and baseline evidence without designing file-level changes yet.
- `prompts/frame_verifier.md`: role `refinement-request verifier`; checks that the selected workflow, baseline evidence, and acceptance boundary are explicit enough for planning.
- `prompts/design_producer.md`: role `workflow refinement strategist`; authors the refinement strategy, file-level change plan, and regression guardrails.
- `prompts/design_verifier.md`: role `refinement-plan verifier`; checks that the change plan is concrete, scoped, and evidence-driven.
- `prompts/implement_producer.md`: role `workflow refiner`; creates `candidate_workflow_surface/` and the build evidence without mutating the authoritative selected workflow package.
- `prompts/implement_verifier.md`: role `refinement-build verifier`; checks that the candidate surface is explicit enough for deterministic candidate-manifest derivation and later evaluation.
- `prompts/evaluate_producer.md`: role `workflow refinement evaluator`; writes the verification report, evaluation delta, promotion record, and rollback plan.
- `prompts/evaluate_verifier.md`: role `refinement-release verifier`; checks that the evaluation package is publication-ready and still stops before promotion.

## Verification and evidence contract

- Workflow discovery must find the package by canonical name and alias.
- Compilation must expose typed route metadata and payload schemas for the four pair steps.
- Runtime proof must cover:
- successful terminal publication of a baseline snapshot, candidate workflow surface, candidate manifest, and refinement receipt without mutating the authoritative selected workflow package
- stable publication of `selected_workflow_capability.json`, `selected_workflow_authoring_surface.json`, `baseline_workflow_manifest.json`, `candidate_workflow_manifest.json`, `evaluation_delta_report.md`, and `workflow_refinement_receipt.json`
- proof that the candidate surface can be validated through an isolated overlay plus target-test command before later promotion
- deterministic publish-step rejection of missing baseline evidence artifacts, cross-workflow evaluation-summary drift, selected-workflow/authoring-surface mismatches, baseline/candidate manifest drift, and candidate files outside the selected workflow boundary

## Rework / replan / block / fail policy

- `needs_rework`: local repair inside the same framing, planning, implementation, or evaluation boundary.
- `needs_replan`: the selected workflow, accepted refinement boundary, or required artifact graph changed materially enough that earlier work must be revisited.
- When the workflow explicitly authors `blocked`, use it when a missing prerequisite or repository fact prevents a credible refinement package.
- When the workflow explicitly authors `failed`, use it when irreconcilable contradictions make the current refinement package non-credible.

## Recursive self-improvement policy

- `workflow_idea_to_workflow_package` remains the standing greenfield authoring path and was reconsidered before choosing this narrower closed-loop refinement layer.
- `workflow_to_eval_suite` remains the standing evaluation-authoring building block; this workflow consumes explicit evaluation evidence rather than re-deriving eval artifacts ad hoc.
- Promotion remains evidence-gated by the baseline manifest, candidate manifest, copied baseline evidence, evaluation package artifacts, and deterministic publication-side validation.
- Later cycles can now layer `workflow_run_history_to_failure_modes` or broader portfolio-governance workflows on top of explicit refinement publication instead of inferring refinement state from local edits.

## Evidence

- Lab implementation: `labs/workflows/workflow_and_eval_to_refined_workflow_package/`
- Shared refinement seam consumed: `stdlib/refinement.py`
- Lab asset: `labs/workflows/workflow_and_eval_to_refined_workflow_package/assets/refinement_package_checklist.md`
- Workflow-specific proof: `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- The scripted tests prove workflow discovery, compilation, prompt contract markers, terminal publication, isolated overlay validation, and publish-side rejection of boundary and evidence drift cases.
