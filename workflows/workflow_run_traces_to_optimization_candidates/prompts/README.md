# `workflow_run_traces_to_optimization_candidates` Prompts

## Shared README Boundary

- This workflow proposes optimization candidates only.
- Do not edit source prompts or workflow files.
- Do not run the selected workflow.
- Do not claim a candidate improves performance unless ablation or rerun evidence exists.
- Separate observed evidence from inference.
- Prefer targeted local changes before workflow-level changes.
- Verifier/rubric changes are one merged acceptance-function surface.
- Token compression must be classified by quality risk.
- Prompt files still own the step role, current work-item boundary, exact artifact read/write set, route posture, and forbidden actions.
- The runtime injects a compact human-readable step contract with required inputs, writable artifacts, route-specific artifact requirements, expected output payload requirements, optional route handoff, and optional retry feedback.
- Provider raw output is runtime telemetry. It is persisted for logs, traces, debugging, and replay, but it is not rendered into provider prompts.
- Provider prose is control metadata unless it is written into a declared artifact.
- Verifier prompts return one JSON object through the selected route and step payload; they do not mutate artifacts unless the step contract says otherwise.

## LLM-authored Artifact Ownership

- Deterministic helpers may prepare trace corpora, metrics, rankings, and failure-scenario seeds.
- Once a producer writes a failure or candidate artifact and the verifier accepts it, workflow handlers validate and publish that artifact; they do not deterministically rewrite it.

## Failure Scenario Seeds

- `workflow_failure_scenario_seeds.json` is deterministic input evidence.
- `workflow_failure_scenarios.json` is the producer-authored final failure-scenario artifact.

## Optimization Depth

- `cheap`: Use existing traces only. Produce concise, high-leverage candidates. Avoid speculative expansion.
- `standard`: Use existing traces only. Perform deeper cross-checking across trace corpus, selected workflow surfaces, priority report, and candidate artifacts. Lower confidence when evidence is thin.
- `ablation`: Do not run ablations. Treat this as ablation-planning mode only. Mark candidates that should be ablated before promotion and include ablation-oriented rationale where useful.

## Candidate Budget

- `workflow_optimization_scope.max_candidates_per_pass` is a soft authoring budget.
- Try to keep each candidate-producing pass within that number.
- This is not a hard schema limit. Use judgment if additional candidates are necessary, but explain why.

## Keep In Each Prompt

- role and step name
- step purpose and current work-item boundary
- exact artifacts to read, write, or leave untouched
- step-specific evidence requirements, route reminders, and forbidden actions
- non-mutation rule
- candidate-only rule
- no hidden execution rule

## Step Surface

| Step | Prompt pair | Writes | Step-complete route |
| --- | --- | --- | --- |
| `frame` | `frame_producer.md` / `frame_verifier.md` | deterministic frame artifacts remain authoritative; verifier returns framing control only | `optimization_scope_framed` |
| `rank_targets` | `rank_targets_producer.md` / `rank_targets_verifier.md` | `step_trace_metrics`, `step_optimization_priority_report` | `targets_ranked` |
| `mine_failures` | `mine_failures_producer.md` / `mine_failures_verifier.md` | `workflow_failure_scenarios` | `failure_scenarios_mined` |
| `optimize_producer` | `optimize_producer_producer.md` / `optimize_producer_verifier.md` | `producer_prompt_optimization_candidates` | `producer_candidates_ready` |
| `optimize_verifier_rubric` | `optimize_verifier_rubric_producer.md` / `optimize_verifier_rubric_verifier.md` | `verifier_rubric_optimization_candidates` | `verifier_rubric_candidates_ready` |
| `optimize_tokens` | `optimize_tokens_producer.md` / `optimize_tokens_verifier.md` | `token_optimization_candidates` | `token_candidates_ready` |
| `adversarial_cases` | `adversarial_cases_producer.md` / `adversarial_cases_verifier.md` | `adversarial_case_candidates` | `adversarial_cases_ready` |
| `workflow_level` | `workflow_level_producer.md` / `workflow_level_verifier.md` | `workflow_level_optimization_candidates` | `workflow_level_candidates_ready` |
| `package` | `package_producer.md` / `package_verifier.md` | `workflow_optimization_scorecard`, `workflow_optimization_packet` | `optimization_packet_ready` |

## Route Surface

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `frame_context_captured`
- `optimization_scope_framed`
- `no_eligible_trace_evidence`
- `targets_ranked`
- `insufficient_evidence`
- `failure_scenarios_mined`
- `no_failure_scenarios`
- `producer_candidates_ready`
- `producer_pass_not_applicable`
- `verifier_rubric_candidates_ready`
- `verifier_rubric_pass_not_applicable`
- `token_candidates_ready`
- `token_pass_not_applicable`
- `adversarial_cases_ready`
- `adversarial_generation_skipped`
- `workflow_level_candidates_ready`
- `workflow_level_pass_not_applicable`
- `optimization_packet_ready`
- `needs_rework`
- `optimization_candidates_published`

## Verifier Payloads

| Step | Payload |
| --- | --- |
| `frame` | `FrameOptimizationPayload` |
| `rank_targets` | `RankTargetsPayload` |
| `mine_failures` | `FailureScenarioPayload` |
| `optimize_producer` | `CandidatePassPayload` |
| `optimize_verifier_rubric` | `CandidatePassPayload` |
| `optimize_tokens` | `CandidatePassPayload` |
| `adversarial_cases` | `AdversarialCasesPayload` |
| `workflow_level` | `CandidatePassPayload` |
| `package` | `OptimizationPackagePayload` |

## Verifier Rejections

- Reject outputs that omit required schema fields.
- Reject outputs that invent run evidence or fabricate selected-workflow files.
- Reject outputs that claim tests, reruns, or ablations happened without evidence.
- Reject outputs that propose direct source mutation or automatic promotion.
- Reject outputs that collapse producer and verifier/rubric surfaces into one local pass.
- Reject outputs that mislabel risky semantic changes as safe compression.
- Do not reject solely because evidence references are absent when the narrative remains otherwise grounded.
