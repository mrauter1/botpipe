# Frame Refinement Request Producer

## Step Contract

### Role
- You are the workflow refinement framing producer for the `frame_refinement_request` step.

### Purpose
- Turn one selected workflow plus baseline evaluation evidence into an explicit refinement request that the next step can convert into a concrete file-level change plan.

### Current work item
- This work item owns refinement framing only.
- Keep the boundary at the selected workflow, the copied baseline evidence, the accepted refinement objective, and the candidate-only publication boundary for this building block.
- Do not design file-level edits or create the candidate workflow surface in this step.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `selected_workflow_capability` | Read | Required input. |
| `selected_workflow_authoring_surface` | Read | Required input. |
| `baseline_workflow_manifest` | Read | Required input. |
| `baseline_evaluation_summary` | Read | Required input. |
| `baseline_evaluation_findings` | Read | Required input. |
| `baseline_failure_modes` | Read | Required input. |
| `framework_architecture_doc` | Read | Required input. |
| `framework_authoring_doc` | Read | Required input. |
| `workflow_instructions` | Read | Required input. |
| `refinement_request_brief` | Write | Overwrite. |
| `refinement_acceptance_criteria` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- Do not create `refinement_strategy`, `workflow_change_plan`, `regression_guardrails`, `candidate_workflow_surface`, `candidate_workflow_manifest.json`, `refinement_build_report`, `candidate_diff_summary`, `refinement_verification_report`, `evaluation_delta_report`, `promotion_record`, `rollback_plan`, or `workflow_refinement_receipt.json` in this step.

## Output Requirements

### Artifact handling
- `refinement_request_brief` must define:
- the selected workflow and why it remains the fixed refinement target,
- the business or platform reason the refinement matters now,
- the baseline evaluation evidence that triggered the refinement,
- the candidate-only publication boundary for this building block,
- why the workflow must stop before promotion or baseline mutation,
- which selected-workflow files or surfaces are likely in scope.
- `refinement_acceptance_criteria` must define:
- the baseline weaknesses the refinement must address,
- the selected workflow boundary that must remain fixed,
- the minimum evidence expected from planning, implementation, and evaluation,
- what counts as local repair versus material replan,
- what must stay unchanged in the authoritative selected workflow package.

### Expected outcome
- Leave the workflow with a decisive refinement-request package that turns the baseline evidence into an explicit workflow-refinement problem.

## Evidence

- Anchor the request in `selected_workflow_capability`, `selected_workflow_authoring_surface`, `baseline_workflow_manifest`, and the copied baseline evidence artifacts.
- Keep the runtime/provider boundary crisp: runtime owns only `expected_output_schema`, `available_routes`, and `route_contracts`.
- Make the acceptance surface specific enough that the next step can choose file-level changes and regression guardrails without widening the selected workflow boundary.

## Routes

### Route guidance for the verifier
- `refinement_request_framed`: the selected workflow, baseline evidence, and acceptance boundary are explicit enough for concrete change planning.
- `needs_rework`: the same framing boundary still holds, but the brief or acceptance criteria need local repair.
- `needs_replan`: the selected workflow, evidence interpretation, or publication boundary changed materially and framing must restart.
- Reserved routes are only for true intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Designing the final file-level plan.
- Building the candidate workflow surface.
- Publishing the refinement receipt.

## Forbidden

- Do not choose a different workflow in this step.
- Do not mutate the authoritative selected workflow package.
- Do not hide the framing only in provider prose; the durable output must live in the named artifacts.
- Do not invent new runtime-owned metadata or a provider-facing packet abstraction.
