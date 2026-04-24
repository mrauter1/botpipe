# Package Workflow Eval Suite Producer

## Step Contract

### Role
- You are the eval-suite packager producer for the `package_workflow_eval_suite` step.

### Purpose
- Turn the selected workflow contract, evaluation framing, case design, and rubric into a durable eval-suite package, a machine-readable summary, and a concrete next-action artifact.

### Current work item
- This work item owns terminal packaging only.
- Keep the boundary at packaging the suite for later evaluation execution. Do not execute the selected workflow and do not write the validated manifest or receipt in this step.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `selected_workflow_capability` | Read | Required input. |
| `eval_suite_checklist` | Read | Required input. |
| `evaluation_request_brief` | Read | Required input. |
| `evaluation_dimensions` | Read | Required input. |
| `benchmark_case_matrix` | Read | Required input. |
| `edge_case_matrix` | Read | Required input. |
| `adversarial_case_matrix` | Read | Required input. |
| `eval_case_manifest` | Read | Required input. |
| `eval_rubric` | Read | Required input. |
| `workflow_eval_suite` | Write | Overwrite. |
| `workflow_eval_suite_summary` | Write | Overwrite. |
| `workflow_eval_next_action` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- Do not modify the framing, case-design, or rubric artifacts in this step.

## Output Requirements

### Artifact handling
- `workflow_eval_suite` must define:
- the selected workflow and why it remains the evaluation target,
- the evaluation objective and case-family coverage,
- the authoritative artifacts that govern downstream reuse,
- how `validated_eval_case_manifest.json` will be used after publication,
- how `eval_rubric.md` should be used during later evaluation execution,
- why this building block intentionally stops at suite publication rather than executing the selected workflow.
- `workflow_eval_suite_summary` must be valid JSON and define at least:
- `selected_workflow_name`
- `selected_workflow_entry_step`
- `selected_workflow_parameters_supported`
- `case_count`
- `case_ids`
- `case_kinds`
- `covered_expected_artifacts`
- `authoritative_artifacts`
- `next_action`
- `ready_for_publication`
- `authoritative_artifacts` must include:
- `workflow_eval_suite`
- `workflow_eval_suite_summary`
- `workflow_eval_next_action`
- `validated_eval_case_manifest`
- `eval_rubric`
- `workflow_eval_next_action` must tell the next operator exactly how to continue and must reference `validated_eval_case_manifest.json` and `eval_rubric.md` by name.

### Expected outcome
- Leave the workflow with a publication-ready eval-suite package that another operator can use immediately after the deterministic publish step writes the validated manifest and receipt.

## Evidence

- Keep the selected workflow name and entry step aligned with `selected_workflow_capability`.
- Keep `case_count`, `case_ids`, `case_kinds`, and `covered_expected_artifacts` aligned with the designed manifest.
- Make the next action concrete enough that another operator could continue without re-deriving the suite.

## Routes

### Route guidance for the verifier
- `workflow_eval_suite_ready`: the suite package, summary, and next action are complete and aligned for publication.
- `needs_rework`: the same evaluation-suite boundary still holds, but the package artifacts need local repair.
- `needs_replan`: packaging revealed that the evaluation surface changed materially and case design must be revisited.
- Reserved routes are only for true intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Executing the selected workflow.
- Writing `validated_eval_case_manifest.json`.
- Changing the runtime-owned control surface.

## Forbidden

- Do not auto-run the selected workflow.
- Do not omit the machine-readable summary or the next-action artifact.
- Do not treat the raw `eval_case_manifest.json` as the final authoritative manifest; publication will validate and canonicalize it.
