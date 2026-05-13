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
| `workflow_failure_scenario_seeds` | Read | Input evidence only, not the authoritative final artifact. |
| `workflow_failure_scenarios` | Read | Candidate failure scenarios. |

## Output Requirements

- Return one `FailureScenarioPayload` JSON object through the selected route.
- Include `summary`, `selected_workflow_name`, `target_steps`, and `failure_ids`.

## Evidence

- Accept grounded scenarios even when some evidence-reference arrays are omitted.
- Validate the producer-authored `workflow_failure_scenarios.json`.
- Reject invented evidence, invalid schema, wrong selected workflow, or invalid failure kinds.
- Do not reject solely because evidence-reference arrays are absent.

## Route Guidance

- Treat helper routes only when the runtime contract exposes them for this step; use `question` only use it only when a true intent gap or missing hard constraint blocks safe progress.
- Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

- Use `failure_scenarios_mined` when the failure set is grounded and useful.
- Use `no_failure_scenarios` when the artifact honestly concludes none were credible.
- Use `needs_rework` for local scenario defects.

## Forbidden

- Reject outputs that imply source mutation, hidden reruns, or automatic promotion.
- Reject outputs missing required payload fields.
