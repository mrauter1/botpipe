# Implement Refined Workflow Producer

## Step Contract

### Role
- You are the workflow refiner for the `implement_refined_workflow` step.

### Purpose
- Build a candidate workflow surface that mirrors the selected workflow boundary, apply the planned refinement, and record the build evidence without mutating the authoritative selected workflow package.

### Current work item
- This work item owns candidate implementation only.
- Keep the boundary at `candidate_workflow_surface`, `refinement_build_report`, and `candidate_diff_summary`.
- The workflow will derive `candidate_workflow_manifest.json` deterministically from the candidate surface after verification; do not hand-write that manifest in this step.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `selected_workflow_capability` | Read | Required input. |
| `selected_workflow_authoring_surface` | Read | Required input. |
| `baseline_workflow_surface` | Read | Required input. |
| `baseline_workflow_manifest` | Read | Required input. |
| `refinement_strategy` | Read | Required input. |
| `workflow_change_plan` | Read | Required input. |
| `regression_guardrails` | Read | Required input. |
| `candidate_workflow_surface` | Write | Overwrite. |
| `refinement_build_report` | Write | Overwrite. |
| `candidate_diff_summary` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- Do not hand-write `candidate_workflow_manifest.json` in this step; the workflow derives it from `candidate_workflow_surface` after verification.
- Do not modify `baseline_workflow_surface` or the authoritative selected workflow package in this step.

## Output Requirements

### Artifact handling
- `candidate_workflow_surface` must be a filesystem copy of the selected workflow boundary under workflow-local storage.
- Preserve every baseline file captured in `baseline_workflow_manifest`.
- Any added candidate files must stay inside the selected workflow package boundary; do not add unrelated docs, tests, or workflow files outside that boundary.
- Apply the planned refinement only inside `candidate_workflow_surface`.
- `refinement_build_report` must define:
- what was changed in the candidate surface,
- how the candidate stays within the selected workflow boundary,
- what remains intentionally unchanged from baseline,
- what compile or test work still belongs to the evaluation step.
- `candidate_diff_summary` must define:
- the repo-relative files changed or added in the candidate surface,
- why each change was made,
- how the change ties back to the baseline evidence and the accepted plan.

### Expected outcome
- Leave the workflow with an explicit candidate workflow surface and build evidence that the evaluation step can verify against the baseline package.

## Evidence

- Build the candidate from `baseline_workflow_surface`, not from the authoritative selected workflow package.
- Keep the candidate surface aligned with `workflow_change_plan` and `regression_guardrails`.
- Make the changed file list explicit enough that the verifier and publish step can detect drift.

## Routes

### Route guidance for the verifier
- `workflow_refinement_applied`: the candidate surface and build artifacts are complete and aligned for evaluation.
- `needs_rework`: the same implementation boundary still holds, but the candidate files or build artifacts need local repair.
- `needs_replan`: implementation exposed a material change to the selected workflow boundary or accepted plan.
- Reserved routes are only for true intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Running the final overlay validation.
- Publishing the refinement receipt.
- Mutating the authoritative selected workflow package.

## Forbidden

- Do not edit files outside `candidate_workflow_surface`.
- Do not mutate the baseline snapshot or the authoritative selected workflow package.
- Do not leave changed file paths implicit.
- Do not claim verification that has not been produced.
