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
- Do not reject solely because candidate count exceeds `max_candidates_per_pass`.
- Treat over-budget output as a quality concern only when it becomes unfocused, duplicative, or ungrounded.

## Route Guidance

- Treat helper routes only when the runtime contract exposes them for this step; use `question` only use it only when a true intent gap or missing hard constraint blocks safe progress.
- Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

- Use `workflow_level_candidates_ready` when grounded workflow-level candidates exist.
- Use `workflow_level_pass_not_applicable` when they are not justified.
- Use `needs_rework` for local candidate defects.

## Forbidden

- Reject direct source mutation, hidden execution claims, invented rerun or ablation claims, invalid schema, wrong selected workflow, or collapsed optimization surfaces.
- Reject payloads missing required fields.
