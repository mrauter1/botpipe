# Evaluate Refined Workflow Producer

## Step Contract

### Role
- You are the workflow refinement evaluator for the `evaluate_refined_workflow` step.

### Purpose
- Evaluate the candidate workflow surface against the baseline evidence, describe the expected improvement, and produce promotion and rollback guidance without publishing the receipt directly.

### Current work item
- This work item owns evaluation only.
- Keep the boundary at `refinement_verification_report`, `evaluation_delta_report`, `promotion_record`, and `rollback_plan`.
- Do not mutate the candidate or authoritative workflow surfaces in this step.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `selected_workflow_capability` | Read | Required input. |
| `selected_workflow_authoring_surface` | Read | Required input. |
| `baseline_workflow_surface` | Read | Required input. |
| `baseline_workflow_manifest` | Read | Required input. |
| `baseline_evaluation_summary` | Read | Required input. |
| `baseline_evaluation_findings` | Read | Required input. |
| `baseline_failure_modes` | Read | Required input. |
| `refinement_strategy` | Read | Required input. |
| `workflow_change_plan` | Read | Required input. |
| `regression_guardrails` | Read | Required input. |
| `candidate_workflow_surface` | Read | Required input. |
| `candidate_workflow_manifest` | Read | Required input. |
| `refinement_build_report` | Read | Required input. |
| `candidate_diff_summary` | Read | Required input. |
| `refinement_package_checklist` | Read | Required input. |
| `refinement_verification_report` | Write | Overwrite. |
| `evaluation_delta_report` | Write | Overwrite. |
| `promotion_record` | Write | Overwrite. |
| `rollback_plan` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- Do not create `workflow_refinement_receipt.json` in this step.
- Do not modify `candidate_workflow_surface`, `candidate_workflow_manifest.json`, or the authoritative selected workflow package in this step.

## Output Requirements

### Artifact handling
- `refinement_verification_report` must define:
- what verification evidence exists now,
- what compile or test command should validate the candidate overlay,
- whether the candidate appears aligned with the baseline package and accepted plan,
- what unresolved risks remain.
- `evaluation_delta_report` must define:
- how the candidate changes address the supplied baseline evidence,
- what before or after differences matter,
- what evidence still remains unproven.
- `promotion_record` must define:
- why the candidate is or is not ready for later promotion,
- which artifacts should gate promotion,
- how the baseline and candidate manifests define the promotion boundary.
- `rollback_plan` must define:
- how to abandon or reverse the candidate publication safely,
- how to restore confidence in the authoritative selected workflow baseline,
- what artifacts govern rollback.

### Expected outcome
- Leave the workflow with an evaluation package that is concrete enough for deterministic publication-side validation and later human or automated promotion decisions.

## Evidence

- Compare the candidate against the copied baseline evidence and the baseline or candidate manifests, not just provider intuition.
- Make the overlay validation path explicit by naming the exact command from `invocation_contract`.
- Keep promotion and rollback guidance concrete enough that publication does not need to infer workflow boundaries or evidence ownership.

## Routes

### Route guidance for the verifier
- `workflow_refinement_evaluated`: the verification package is publication-ready and the workflow can attempt deterministic receipt publication.
- `needs_rework`: the same refinement boundary still holds, but the candidate needs local repair before publication.
- `needs_replan`: evaluation showed the accepted refinement boundary or plan changed materially.
- Reserved routes are only for true intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Publishing the refinement receipt.
- Promoting the candidate into the authoritative selected workflow package.
- Inventing runtime-owned promotion behavior.

## Forbidden

- Do not mutate the candidate or authoritative selected workflow surfaces.
- Do not claim measured improvement without tying it to the supplied baseline evidence.
- Do not skip rollback detail for candidate-to-baseline promotion decisions.
- Do not leave the overlay validation command implicit.
