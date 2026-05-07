# Design Eval Cases Producer

## Step Contract

### Role
- You are the workflow evaluation designer for the `design_eval_cases` step.

### Purpose
- Turn the framed evaluation target into explicit benchmark, edge, and adversarial cases, a proposed eval-case manifest, and an evaluation rubric that the publish step can validate mechanically.

### Current work item
- This work item owns case and rubric design only.
- Keep the boundary at case coverage, manifest structure, expected artifacts, and scoring guidance.
- Do not package the terminal suite in this step and do not execute the selected workflow.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `selected_workflow_capability` | Read | Required input. |
| `evaluation_request_brief` | Read | Required input. |
| `evaluation_dimensions` | Read | Required input. |
| `benchmark_case_matrix` | Write | Overwrite. |
| `edge_case_matrix` | Write | Overwrite. |
| `adversarial_case_matrix` | Write | Overwrite. |
| `eval_case_manifest` | Write | Overwrite. |
| `eval_rubric` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- Do not modify the framing artifacts in this step.
- Do not create `workflow_eval_suite`, `workflow_eval_suite_summary`, or `workflow_eval_next_action` in this step.

## Output Requirements

### Artifact handling
- Each case-matrix artifact must contain at least one explicit case row for its category and must make the case id, pressure or scenario, expected artifacts, and why the case matters explicit.
- `eval_case_manifest` must be valid JSON with a top-level `cases` array.
- Each case in `eval_case_manifest` must define:
- `case_id`
- `case_kind`
- `prompt`
- `expected_artifacts`
- optional `workflow_parameters`
- The manifest must include all three legal case kinds: `benchmark`, `edge`, and `adversarial`.
- `expected_artifacts` must come from the selected workflow's declared artifact surface in `selected_workflow_capability`.
- Any `workflow_parameters` must only use supported parameter names for the selected workflow.
- `eval_rubric` must define how to judge artifact completeness, quality, and failure severity for the selected workflow.

### Expected outcome
- Leave the workflow with explicit category coverage, a mechanically valid proposed manifest, and a rubric that another operator can use during later evaluation runs.

## Evidence

- Make the selected workflow name, case ids, case kinds, and expected-artifact coverage explicit in the durable artifacts.
- Keep the publication boundary crisp: this step designs the suite, but it does not claim publication or execute the selected workflow.

## Routes

- Treat helper routes only when the runtime contract exposes them for this step; use `question` only use it only when a true intent gap or missing hard constraint blocks safe progress.
- Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

### Route guidance for the verifier
- `eval_cases_designed`: benchmark, edge, and adversarial coverage plus the rubric are explicit and packaging-ready.
- `needs_rework`: the same case-design boundary still holds, but the matrices, manifest, or rubric need local repair.
- `needs_replan`: the selected workflow or evaluation boundary changed materially and framing must restart.
- Treat helper routes only when the runtime contract exposes them for this step; use `question` only use it only for true intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Packaging the terminal eval suite.
- Writing the validated manifest or publication receipt.
- Executing the selected workflow.

## Forbidden

- Do not omit any of the three legal case kinds.
- Do not rely on undeclared workflow parameters or unknown expected artifacts.
- Do not hide the suite design only in provider prose; the durable output must live in the named artifacts.
