# `candidate_workflow_to_adapted_execution_plan`

`candidate_workflow_to_adapted_execution_plan` is a reusable building block that turns one already-chosen workflow plus concrete task context into an execution-ready adapted plan, a machine-readable summary, a validated workflow-parameter artifact, and a deterministic publication receipt. It stops at plan publication so the chosen workflow can still be run explicitly and inspectably afterward.

## Problem and value

- Problem solved: convert a chosen workflow that is close but not plug-and-play into a durable execution package instead of ad hoc chat guidance and manual parameter guessing.
- Why it matters: once the portfolio has a front door and reusable candidate retrieval, the next missing reuse-over-rebuild layer is concrete adaptation planning that survives handoff.
- Likely sponsors: engineering productivity, platform owners, TPM and delivery leads, consulting delivery teams, and recursive portfolio operators who want to reuse existing workflows before defaulting to greenfield authoring.
- Classification: reusable workflow building block.
- Why Botpipe fits: the work needs durable artifacts, verifier-gated repair loops, inspectable workflow contracts, and deterministic validation of workflow parameters against the shared loader rules.
- Why one-shot is insufficient: the selected workflow, execution assumptions, parameter mapping, expected downstream artifacts, and next action all need to survive challenge and handoff instead of disappearing into transient chat prose.

## Invocation

- Lab path: `labs/workflows/candidate_workflow_to_adapted_execution_plan/`
- Discovery: lab workflow; copy or reference the workflow folder explicitly before running it by name.
- Direct run:

```bash
botpipe run candidate_workflow_to_adapted_execution_plan <task-id> \
  --message "Adapt the security remediation workflow for an admin impersonation privilege-escalation finding." \
  -wf selected_workflow security_finding_to_verified_remediation \
  -wf task_title "Admin impersonation privilege escalation response" \
  -wf sponsor_role "security engineering" \
  -wf desired_outcome "Publish an execution-ready adapted remediation plan." \
  -wf constraints "Preserve the existing workflow boundary and prefer validated workflow parameters over workflow edits." \
  -wf evidence_expectations "Need a validated run plan and concrete next action."
```

Params:

- `selected_workflow` required
- `task_title` required
- `sponsor_role` optional
- `desired_outcome` optional
- `constraints` optional and repeatable
- `evidence_expectations` optional and repeatable

This building block is also the concrete cycle-6 handoff target for the `adapt` route in `task_to_workflow_strategy`. The front door still owns route selection, but it now points the `adapt` route at this package through the existing `workflow_strategy_package.md` and `strategy_next_action.md` surfaces instead of a generic prose handoff.

## Candidate additions considered

| Candidate | Why it matters | Trade-off | Decision |
| --- | --- | --- | --- |
| `workflow_idea_to_workflow_package` | Remains the workflow-builder baseline and must be reconsidered each cycle until a stronger builder exists | Already credible in code, docs, and runtime proof, so repeating another builder-first cycle would delay the more urgent reuse-over-rebuild gap | Deferred |
| `workflow_to_eval_suite` | High-value building block for authoring benchmark tasks, edge cases, and pass/fail evidence for workflows | Strong next follow-on, but adaptation planning is the more immediate missing layer between candidate retrieval and downstream execution | Deferred |
| `candidate_workflow_to_adapted_execution_plan` | Turns a chosen workflow plus task context into a durable adapted execution package with validated parameters | Requires a narrow selected-workflow adaptation seam and careful publication validation, but it directly fills the current reuse-over-rebuild gap | Chosen and shipped in cycle 6 |

## Framework improvement candidates considered

| Candidate | Benefits | Trade-offs | Decision |
| --- | --- | --- | --- |
| Additive authoring-only adaptation helper seam | Lets workflows snapshot one selected workflow's contract and validate proposed workflow parameters through the shared loader without widening `workflow.toml` or runtime-owned routing | Requires one new stdlib module plus docs/tests, but keeps policy visible in workflow code and artifacts | Chosen in the paired framework slice and consumed here |
| Expand `workflow.toml` with adaptation metadata and parameter defaults | Could make adaptation artifacts more static and machine-readable | Widens the manifest contract, forces repo-wide metadata backfill, and hides workflow meaning in static metadata instead of visible artifacts | Rejected |
| Runtime-owned adaptation planner or auto-runner | Could make adaptation runs terse from the CLI | Hides adaptation policy in runtime code and violates the doctrine that workflows own the global SOP and terminal boundary | Rejected |

## Meaningful design decisions

### 1. Input boundary

- Alternatives considered:
- force this workflow to compose `task_to_candidate_workflow_set` every time
- require upstream strategy artifacts as the only legal entry point
- accept one explicit `selected_workflow` plus the same task-context fields the front door already uses
- Selected: explicit `selected_workflow` plus standard task-context fields
- Why: it keeps the building block reusable both standalone and downstream of `task_to_workflow_strategy` without forcing redundant candidate retrieval.

### 2. Terminal boundary

- Alternatives considered:
- auto-run the selected workflow after planning
- stop at a prose-only adaptation memo
- stop at a published execution plan plus validated workflow-parameter artifact
- Selected: stop at a published execution plan plus validated workflow-parameter artifact
- Why: it keeps execution visible and inspectable while still producing a terminal package another operator or workflow can use immediately.

### 3. Validation boundary

- Alternatives considered:
- let the provider write the final authoritative workflow-parameter artifact directly
- validate workflow parameters during analysis and trust them afterward
- let the provider propose parameters, then validate and canonicalize them in the publish step
- Selected: provider proposal plus deterministic publish-step validation
- Why: publish becomes the authoritative guard against invalid workflow references, unknown parameter names, missing required values, and summary drift.

## Implementation candidates considered

| Candidate | Description | Trade-off | Decision |
| --- | --- | --- | --- |
| Workflow-only implementation with ad hoc imports | Build the package directly on core/runtime inspection helpers inside workflow code | Smallest diff, but duplicates repo-root resolution and weakens the authoring boundary | Rejected |
| New adaptation helper seam plus dedicated workflow package plus front-door handoff wording | Add the helper seam, build the workflow on top of it, and make the front-door `adapt` route point here through existing artifacts | Slightly broader change set, but the clearest reusable and inspectable design | Selected |
| Absorb adaptation planning into `task_to_workflow_strategy` | Let the front door produce the entire adapted execution package itself | Reduces package count, but collapses the front-door boundary and leaves no reusable adaptation building block | Rejected |

## Workflow contract

### Objective

Turn a chosen existing workflow plus concrete task context into an execution-ready adapted plan without auto-running the workflow or widening runtime-owned control logic.

### Global deterministic workflow responsibilities

- Bootstrap the run-local invocation contract.
- Capture an authoritative selected-workflow contract snapshot from the current repository.
- Keep framing, adaptation analysis, and packaging as separate work items.
- Validate the proposed workflow-parameter mapping mechanically before publication.
- Publish only after the plan, summary, next-action artifact, and validated parameter artifact all exist and agree.

### Provider-owned cognitive responsibilities

- Frame the selected workflow against the current task and acceptance surface.
- Decide what stays fixed versus what must be parameterized or explicitly carried forward at run time.
- Explain execution assumptions, expected downstream artifacts, verification expectations, and adaptation risks.
- Package the final execution plan and handoff artifacts.

### Work-item boundary doctrine

- `capture_selected_workflow_contract`: deterministic contract capture only.
- `frame_adaptation_request`: task framing and acceptance criteria only.
- `analyze_adaptation_surface`: fit assessment, parameterization reasoning, and execution-risk analysis only.
- `package_adapted_execution_plan`: terminal plan, proposed parameter artifact, machine-readable summary, and next action only.
- `needs_rework`: the same work-item boundary still holds.
- `needs_replan`: the task framing, selected workflow, or execution boundary changed materially.

### Role topology

- deterministic `bootstrap`
- deterministic `capture_selected_workflow_contract`
- `workflow adaptation framer` / `adaptation-request verifier`
- `workflow adaptation analyst` / `adaptation-surface verifier`
- `adapted-execution-plan packager` / `adapted-execution-plan verifier`
- deterministic `publish_adapted_execution_plan`

### Control flow

1. `bootstrap`
2. `capture_selected_workflow_contract`
3. `frame_adaptation_request`
4. `analyze_adaptation_surface`
5. `package_adapted_execution_plan`
6. `publish_adapted_execution_plan`

### Route grammar

Helper routes:

- `question` when provider questions are allowed by the interaction policy
- question routes use `outcome.route_fields.questions`; blocked and failed routes use nullable `outcome.route_fields.reason`

Application routes:

- `inputs_prepared`
- `selected_workflow_contract_captured`
- `adaptation_request_framed`
- `adaptation_surface_analyzed`
- `adapted_execution_plan_ready`
- `needs_rework`
- `needs_replan`
- `adapted_execution_plan_published`

Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

### Artifact contract

| Step | Required reads | Required writes | Authority / downstream use |
| --- | --- | --- | --- |
| `bootstrap` | `request.md`, workflow params | `invocation_contract.json` | authoritative run-local input snapshot |
| `capture_selected_workflow_contract` | request, invocation contract | `selected_workflow_capability.json` | authoritative selected-workflow contract snapshot |
| `frame_adaptation_request` | request, invocation contract, selected-workflow contract, framework docs | `adaptation_request_brief.md`, `adaptation_success_criteria.md` | authoritative adaptation framing package |
| `analyze_adaptation_surface` | request, invocation contract, selected-workflow contract, framing artifacts | `workflow_fit_assessment.md`, `step_adaptation_matrix.md` | authoritative fit, parameterization, and execution-surface analysis |
| `package_adapted_execution_plan` | request, invocation contract, selected-workflow contract, checklist, framing and analysis artifacts | `adapted_execution_plan.md`, `proposed_workflow_parameters.json`, `adapted_execution_summary.json`, `adapted_execution_next_action.md` | terminal human-facing and machine-readable adapted-execution package |
| `publish_adapted_execution_plan` | selected-workflow contract, package artifacts | `validated_workflow_parameters.json`, `adapted_execution_plan_receipt.json` | deterministic terminal receipt plus authoritative validated workflow parameters |

### Runtime-injected control contract

The runtime injects only:

- `expected_output_schema`
- `available_routes`
- step-local `Route.to(...)` metadata

Payload models used by the package:

- `AdaptationRequestFramingPayload`
- `AdaptationSurfaceAnalysisPayload`
- `AdaptedExecutionPlanPayload`

### Prompt templates

- `prompts/frame_producer.md`: role `workflow adaptation framer`; frames the selected workflow, current task, and adaptation acceptance surface without analyzing the step topology yet.
- `prompts/frame_verifier.md`: role `adaptation-request verifier`; checks that the framing package is explicit enough for bounded fit analysis.
- `prompts/analyze_producer.md`: role `workflow adaptation analyst`; explains workflow fit, expected downstream artifacts, and step-level adaptation notes without yet writing the terminal package.
- `prompts/analyze_verifier.md`: role `adaptation-surface verifier`; checks that the selected workflow remains fixed and the analysis is packaging-ready.
- `prompts/package_producer.md`: role `adapted-execution-plan packager`; writes the terminal plan, proposed parameter artifact, machine-readable summary, and next action.
- `prompts/package_verifier.md`: role `adapted-execution-plan verifier`; confirms the package is ready for deterministic publication and still stops at plan publication rather than downstream execution.

## Verification and evidence contract

- Workflow discovery must find the package by canonical name and alias.
- Compilation must expose the typed route metadata for the three pair steps.
- Runtime proof must cover:
- successful end-to-end publication of the adapted plan, summary, next-action artifact, validated workflow parameters, and receipt
- stable publication of `selected_workflow_capability.json`, `adapted_execution_summary.json`, and `validated_workflow_parameters.json`
- proof that the workflow stops at publication rather than auto-running the selected workflow
- publication validation that rejects invalid selected-workflow references, invalid proposed parameter payloads, missing authoritative-artifact declarations, and summary drift from the validated parameter artifact

## Rework / replan / block / fail policy

- `needs_rework`: local repair inside the same framing, analysis, or packaging boundary.
- `needs_replan`: the task framing, selected workflow, or execution boundary changed materially enough that the workflow must move backward.
- When the workflow explicitly authors `blocked`, use it when a missing prerequisite or repository fact prevents a credible adapted execution package.
- When the workflow explicitly authors `failed`, use it when irreconcilable contradictions make the current adaptation package non-credible.

## Recursive self-improvement policy

- `workflow_idea_to_workflow_package` remains the standing greenfield authoring path and was reconsidered before shipping this narrower adaptation layer.
- The package relies on the cycle-6 `stdlib/adaptation.py` seam instead of inventing runtime-owned adaptation or widening `workflow.toml`.
- Future cycles can now build `workflow_to_eval_suite`, refinement workflows, or broader portfolio operating workflows on top of explicit candidate retrieval, front-door strategy selection, and concrete adaptation planning instead of re-deriving those layers from scratch.

## Evidence

- Lab implementation: `labs/workflows/candidate_workflow_to_adapted_execution_plan/`
- Shared adaptation seam consumed: `stdlib/adaptation.py`
- Front-door handoff update: `labs/workflows/task_to_workflow_strategy/`
- Lab asset: `labs/workflows/candidate_workflow_to_adapted_execution_plan/assets/adapted_execution_plan_checklist.md`
- Workflow-specific proof: `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
- The scripted tests prove workflow discovery, compilation, terminal publication, and publication-side validation of workflow-reference resolution, workflow-parameter coercion, authoritative-artifact declarations, and summary drift.
