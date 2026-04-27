# Workflow Level Verifier

## Step Contract

- Role: workflow-level verifier.
- Purpose: validate cross-step candidates without letting them displace better local fixes.
- Current boundary: verify workflow-level candidate discipline only.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `selected_workflow_capability` | Read | Canonical workflow topology. |
| `workflow_optimization_trace_corpus` | Read | Cross-step evidence boundary. |
| `step_optimization_priority_report` | Read | Local-first ranking boundary. |
| `workflow_level_optimization_candidates` | Read | Candidate artifact under review. |

## Output Requirements

- Return one `CandidatePassPayload` JSON object through the selected route.
- Include `summary`, `selected_workflow_name`, `target_steps`, and `candidate_ids`.

## Evidence

- Reject workflow-level changes that are really local producer or verifier issues.
- Accept `workflow_level_pass_not_applicable` when the evidence does not justify workflow-level changes.

## Route Guidance

- Use `workflow_level_candidates_ready` when grounded workflow-level candidates exist.
- Use `workflow_level_pass_not_applicable` when they are not justified.
- Use `needs_rework` for local candidate defects.

## Forbidden

- Reject hidden execution, direct source mutation, or payloads missing required fields.
