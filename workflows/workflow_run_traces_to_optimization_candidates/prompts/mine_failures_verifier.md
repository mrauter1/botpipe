# Mine Failures Verifier

## Step Contract

- Role: failure-scenario verifier.
- Purpose: validate the mined failure scenarios and choose the correct failure-analysis route.
- Current boundary: verify scenario quality only.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `workflow_optimization_trace_corpus` | Read | Deterministic evidence. |
| `step_optimization_priority_report` | Read | Ranked target boundary. |
| `workflow_failure_scenarios` | Read | Candidate failure scenarios. |

## Output Requirements

- Return one `FailureScenarioPayload` JSON object through the selected route.
- Include `summary`, `selected_workflow_name`, `target_steps`, and `failure_ids`.

## Evidence

- Accept grounded scenarios even when some evidence-reference arrays are omitted.
- Reject invented evidence or invalid failure kinds.

## Route Guidance

- Use `failure_scenarios_mined` when the failure set is grounded and useful.
- Use `no_failure_scenarios` when the artifact honestly concludes none were credible.
- Use `needs_rework` for local scenario defects.

## Forbidden

- Reject outputs that imply source mutation, hidden reruns, or automatic promotion.
- Reject outputs missing required payload fields.
