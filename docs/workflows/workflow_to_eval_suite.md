# `workflow_to_eval_suite`

`workflow_to_eval_suite` is a reusable workflow building block that turns one selected workflow plus evaluation intent into a durable evaluation-suite package, a machine-readable summary, a validated eval-case manifest, and a deterministic publication receipt. It stops at suite publication so later evaluation execution remains explicit and inspectable.

## Problem and value

- Problem solved: convert a selected workflow into a reusable benchmark, edge-case, and adversarial evaluation suite instead of scattered benchmark ideas and ad hoc chat guidance.
- Why it matters: once the portfolio can discover, choose, and adapt workflows, the next missing layer is explicit evaluation authoring that survives handoff and enables later refinement cycles.
- Likely sponsors: engineering productivity, AI platform owners, workflow maintainers, QA and reliability leads, and recursive portfolio operators.
- Classification: reusable workflow building block.
- Why Botlane fits: the work needs durable artifacts, verifier-gated rework loops, selected-workflow contract inspection, and deterministic publication-side validation.
- Why one-shot is insufficient: a useful suite needs explicit evaluation framing, categorized cases, a reusable rubric, a validated manifest, and a publication receipt another operator or workflow can trust later.

## Invocation

- Package path: `botlane/workflows/workflow_to_eval_suite/`
- Discovery: `botlane workflows show workflow_to_eval_suite`
- Direct run:

```bash
botlane run workflow_to_eval_suite <task-id> \
  --message "Author an evaluation suite for the release go/no-go workflow." \
  -wf selected_workflow release_candidate_to_go_no_go \
  -wf task_title "Release readiness evaluation suite" \
  -wf sponsor_role "engineering productivity" \
  -wf desired_outcome "Publish a reusable eval suite for workflow quality gating." \
  -wf constraints "Keep runtime control narrow and stop at suite publication." \
  -wf evidence_expectations "Need benchmark, edge, adversarial coverage plus a validated manifest."
```

Params:

- `selected_workflow` required
- `task_title` required
- `sponsor_role` optional
- `desired_outcome` optional
- `constraints` optional and repeatable
- `evidence_expectations` optional and repeatable

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Remains the workflow-builder baseline and still needs to be reconsidered every cycle until a stronger builder exists | Already credible in code, docs, and proof, so repeating another builder-first cycle would delay the more urgent evaluation-authoring gap | Deferred |
| `workflow_and_eval_to_refined_workflow_package` | High-value recursive refinement layer once reusable evaluation suites exist | Premature before the repo has a durable suite-authoring layer and validated eval-case manifest contract | Deferred |
| `workflow_to_eval_suite` | Turns one selected workflow into a reusable evaluation suite with categorized cases, rubric, validated manifest, and receipt | Requires a narrow authoring-only validation seam plus careful publish-side drift checks, but it directly fills the missing evaluation-authoring layer | Chosen and shipped in cycle 7 |

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Additive authoring-only evaluation helper seam | Lets workflows validate and canonicalize a proposed eval-case manifest against one selected workflow's parameter contract and artifact surface without widening `workflow.toml` or runtime-owned routing | Adds one focused stdlib seam plus docs/tests, but keeps evaluation policy visible in workflow code and artifacts | Chosen in the paired framework slice and consumed here |
| Expand `workflow.toml` with evaluation metadata and case schemas | Could make some suite metadata statically visible to tooling | Widens the manifest contract, forces repo-wide metadata backfill, and hides workflow meaning in static manifests instead of durable authored artifacts | Rejected |
| Runtime-owned evaluation runner and suite publisher | Could reduce workflow code in the short term | Hides policy in runtime code, mixes authoring with execution, and violates the boundary that workflows own the global SOP and terminal outcome | Rejected |

## Meaningful design decisions

### 1. Input boundary

- Alternatives considered:
- force this workflow to compose candidate retrieval or adaptation planning every time
- require only upstream front-door artifacts as the legal entry point
- accept one explicit `selected_workflow` plus the same task-context fields the front door already uses
- Selected: explicit `selected_workflow` plus standard task-context fields
- Why: it keeps the building block reusable both standalone and downstream of the front door without forcing redundant retrieval or adaptation work.

### 2. Validation boundary

- Alternatives considered:
- let the provider write the final authoritative eval manifest directly
- validate the manifest during case design and trust it afterward
- let the provider propose the manifest, then validate and canonicalize it deterministically in the publish step
- Selected: provider proposal plus deterministic publish-step validation
- Why: publish becomes the authoritative guard against malformed case kinds, duplicate case ids, invalid per-case workflow parameters, unknown expected artifacts, and summary drift.

### 3. Terminal boundary

- Alternatives considered:
- auto-run the selected workflow against the new suite
- stop at a prose-only evaluation memo
- stop at a published eval-suite package plus validated manifest and receipt
- Selected: stop at a published eval-suite package plus validated manifest and receipt
- Why: it keeps later evaluation execution explicit and inspectable while still producing a terminal artifact package another operator or workflow can use immediately.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Workflow-only implementation with ad hoc selected-workflow inspection and manifest validation | Build the package directly against runtime loader details inside workflow code | Smallest diff, but duplicates logic already needed by later refinement workflows and weakens the authoring boundary | Rejected |
| Shared evaluation helper seam plus dedicated workflow package | Reuse the helper seam for manifest validation and keep suite policy visible in the workflow package, prompts, and docs | Slightly broader change set, but it is the clearest reusable and inspectable design | Selected |
| Absorb evaluation authoring into `candidate_workflow_to_adapted_execution_plan` or `task_to_workflow_strategy` | Reduce package count by folding suite authoring into an existing workflow | Collapses boundaries and leaves no reusable evaluation-authoring building block for later refinement workflows | Rejected |

## Workflow contract

### Objective

Turn one chosen workflow plus evaluation intent into a reusable eval-suite package without auto-running the selected workflow or widening runtime-owned control logic.

### Global deterministic workflow responsibilities

- Bootstrap the run-local invocation contract.
- Capture an authoritative selected-workflow contract snapshot from the current repository.
- Keep target framing, case and rubric design, and terminal packaging as separate work items.
- Validate the proposed eval-case manifest mechanically before publication.
- Publish only after the suite package, summary, next-action artifact, and validated manifest all exist and agree.

### Provider-owned cognitive responsibilities

- Frame the selected workflow's evaluation objective and acceptance dimensions.
- Design benchmark, edge, and adversarial cases that pressure the selected workflow meaningfully.
- Define expected artifacts, pass or fail guidance, and rubric criteria.
- Package the final suite artifacts for downstream reuse.

### Work-item boundary doctrine

- `capture_selected_workflow_contract`: deterministic contract capture only.
- `frame_evaluation_target`: evaluation framing and acceptance dimensions only.
- `design_eval_cases`: categorized case coverage, proposed manifest, and rubric only.
- `package_workflow_eval_suite`: terminal suite package, machine-readable summary, and next-action artifact only.
- `needs_rework`: the same work-item boundary still holds.
- `needs_replan`: the selected workflow, evaluation objective, or artifact boundary changed materially.

### Role topology

- deterministic `bootstrap`
- deterministic `capture_selected_workflow_contract`
- `workflow evaluation-target framer` / `evaluation-target verifier`
- `workflow evaluation designer` / `eval-design verifier`
- `eval-suite packager` / `eval-suite verifier`
- deterministic `publish_workflow_eval_suite`

### Control flow

1. `bootstrap`
2. `capture_selected_workflow_contract`
3. `frame_evaluation_target`
4. `design_eval_cases`
5. `package_workflow_eval_suite`
6. `publish_workflow_eval_suite`

### Route grammar

Helper routes:

- `question` when provider questions are allowed by the interaction policy
- question routes use `outcome.route_fields.questions`; blocked and failed routes use nullable `outcome.route_fields.reason`

Application routes:

- `inputs_prepared`
- `selected_workflow_contract_captured`
- `evaluation_target_framed`
- `eval_cases_designed`
- `workflow_eval_suite_ready`
- `needs_rework`
- `needs_replan`
- `workflow_eval_suite_published`

Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

### Artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local input snapshot |
| `capture_selected_workflow_contract` | request, invocation contract | `selected_workflow_capability.json` | authoritative selected-workflow contract snapshot |
| `frame_evaluation_target` | request, invocation contract, selected-workflow contract, framework docs | `evaluation_request_brief.md`, `evaluation_dimensions.md` | authoritative evaluation-target framing package |
| `design_eval_cases` | request, invocation contract, selected-workflow contract, framing artifacts | `benchmark_case_matrix.md`, `edge_case_matrix.md`, `adversarial_case_matrix.md`, `eval_case_manifest.json`, `eval_rubric.md` | authoritative case and rubric design surface before publication validation |
| `package_workflow_eval_suite` | request, invocation contract, selected-workflow contract, checklist, framing and design artifacts | `workflow_eval_suite.md`, `workflow_eval_suite_summary.json`, `workflow_eval_next_action.md` | terminal human-facing and machine-readable suite package |
| `publish_workflow_eval_suite` | selected-workflow contract, design artifacts, package artifacts | `validated_eval_case_manifest.json`, `workflow_eval_suite_receipt.json` | deterministic terminal receipt plus authoritative validated manifest |

### Runtime-injected control contract

The runtime injects only:

- `expected_output_schema`
- `available_routes`
- step-local `Route.to(...)` metadata

Payload models used by the package:

- `EvaluationTargetFramingPayload`
- `EvalCaseDesignPayload`
- `WorkflowEvalSuitePayload`

### Prompt templates

- `prompts/frame_producer.md`: role `workflow evaluation-target framer`; frames the selected workflow and evaluation objective without designing cases yet.
- `prompts/frame_verifier.md`: role `evaluation-target verifier`; checks that the evaluation boundary is explicit enough for case design.
- `prompts/design_producer.md`: role `workflow evaluation designer`; authors benchmark, edge, and adversarial case coverage plus the proposed manifest and rubric.
- `prompts/design_verifier.md`: role `eval-design verifier`; checks that the case coverage, manifest, and rubric are explicit and packaging-ready.
- `prompts/package_producer.md`: role `eval-suite packager`; writes the terminal suite package, machine-readable summary, and next-action artifact.
- `prompts/package_verifier.md`: role `eval-suite verifier`; confirms the terminal package is publication-ready and still stops at suite publication rather than downstream execution.

## Verification and evidence contract

- Workflow discovery must find the package by canonical name and alias.
- Compilation must expose typed route metadata and payload schemas for the three pair steps.
- Runtime proof must cover:
- successful end-to-end publication of the suite package, summary, next-action artifact, validated eval-case manifest, and receipt
- proof that the selected workflow is not auto-run during suite publication
- publish-side rejection of malformed case kinds, duplicate case ids, invalid per-case workflow parameters, unknown expected artifacts, and summary drift
- stable publication of `selected_workflow_capability.json`, `workflow_eval_suite_summary.json`, and `validated_eval_case_manifest.json`

## Rework / replan / block / fail policy

- `needs_rework`: local repair inside the same framing, design, or packaging boundary.
- `needs_replan`: the selected workflow, evaluation objective, or artifact boundary changed materially enough that the workflow must move backward.
- When the workflow explicitly authors `blocked`, use it when a missing prerequisite or repository fact prevents a credible eval-suite package.
- When the workflow explicitly authors `failed`, use it when irreconcilable contradictions make the current evaluation package non-credible.

## Recursive self-improvement policy

- `workflow_idea_to_workflow_package` remains the standing greenfield authoring path and was reconsidered before shipping this narrower evaluation layer.
- The package relies on the cycle-7 `stdlib/evaluation.py` seam instead of inventing runtime-owned evaluation execution or widening `workflow.toml`.
- Future cycles can now build `workflow_and_eval_to_refined_workflow_package`, run-history diagnostics, or broader portfolio operating workflows on top of explicit eval-suite publication instead of re-deriving evaluation artifacts from scratch.

## Evidence

- Package implementation: `botlane/workflows/workflow_to_eval_suite/`
- Shared evaluation seam consumed: `stdlib/evaluation.py`
- Workflow asset: `botlane/workflows/workflow_to_eval_suite/assets/eval_suite_checklist.md`
- Workflow-specific proof: `tests/runtime/test_workflow_to_eval_suite.py`
- The scripted tests prove workflow discovery, compilation, terminal publication, and publish-side validation of malformed case kinds, duplicate ids, workflow-parameter errors, unknown expected artifacts, and summary drift.
