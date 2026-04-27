# Standalone implementation plan — Autoloop v3 workflow optimization process

## Scope

Implement the **workflow optimization process** that consumes runtime evidence from completed Autoloop v3 runs and emits optimization candidates.

This plan assumes Plan 1 has already made normal runs produce:

```text
run.json
events.jsonl
trace.jsonl
git_tracking.jsonl
static_step_graph.json
raw/
```

This plan implements a new workflow package that analyzes those traces and produces candidate improvements. It must not change runtime execution semantics, must not silently mutate workflow source, and must not automatically promote optimized prompts or workflow packages.

The optimizer is a normal Autoloop workflow. It is not a runtime feature.

---

## 1. Target outcome

Add a new bundled workflow:

```text
workflow_run_traces_to_optimization_candidates
```

It consumes selected workflow run traces and emits:

```text
workflow_optimization_trace_corpus.json
step_trace_metrics.json
step_optimization_priority_report.json
workflow_failure_scenarios.json
producer_prompt_optimization_candidates.json
verifier_rubric_optimization_candidates.json
token_optimization_candidates.json
adversarial_case_candidates.json
workflow_level_optimization_candidates.json
workflow_optimization_scorecard.json
workflow_refinement_evidence.json
workflow_optimization_packet.md
optimization_publication_receipt.json
```

Optional follow-up workflow, not required in this implementation phase:

```text
workflow_optimization_candidates_to_ablation_results
```

The main workflow emits **candidate optimization evidence only**. It does not edit source files and does not execute ablations by default.

---

## 2. Non-goals

Do not implement:

```text
automatic prompt rewriting in source files
automatic workflow code mutation
automatic repo patch materialization
automatic promotion
automatic rollback
mandatory ablation
hidden target-workflow execution
hidden refinement workflow execution
runtime-level optimization
```

Do not add optimization logic to the engine or runner. The runtime provides evidence; this workflow consumes evidence.

---

## 3. Core model

Optimization has two phases:

```text
Phase 1 — Step-local optimization
  1. normalize trace corpus
  2. rank highest-leverage step(s)
  3. mine failure scenarios
  4. propose producer prompt candidates
  5. propose verifier/rubric candidates
  6. propose token optimization candidates
  7. propose adversarial case candidates

Phase 2 — Workflow-level optimization
  8. inspect cross-step handoffs, topology, artifact flow, route contracts, and prompt conventions
  9. propose workflow-level candidates
  10. publish scorecard and refinement evidence
```

Candidate ablation is optional and separate.

Default mode:

```text
cheap:
  Use existing traces only.
  Generate ranked candidates.
  Do not rerun the target workflow.
  Do not apply patches.
```

---

## 4. Important boundaries

The optimizer must preserve these boundaries:

```text
Runtime:
  produces trace/git/raw/static-graph evidence

Optimization workflow:
  reads evidence and proposes candidates

Refinement workflow:
  converts accepted evidence into an implementation-ready refinement package

Repo-patch workflow:
  explicitly materializes source changes

Nothing is silently optimized, applied, promoted, or rolled back.
```

The optimizer may propose prompt diffs or patch instructions, but those are candidate artifacts. They are not applied to the selected workflow.

---

## 5. New workflow package

Create:

```text
workflows/workflow_run_traces_to_optimization_candidates/
  __init__.py
  workflow.py
  contracts.py
  params.py
  workflow.toml
  assets/
    optimization_package_checklist.md
  prompts/
    README.md
    frame_producer.md
    frame_verifier.md
    rank_targets_producer.md
    rank_targets_verifier.md
    mine_failures_producer.md
    mine_failures_verifier.md
    optimize_producer_producer.md
    optimize_producer_verifier.md
    optimize_verifier_rubric_producer.md
    optimize_verifier_rubric_verifier.md
    optimize_tokens_producer.md
    optimize_tokens_verifier.md
    adversarial_cases_producer.md
    adversarial_cases_verifier.md
    workflow_level_producer.md
    workflow_level_verifier.md
    package_producer.md
    package_verifier.md
```

### `workflow.toml`

```toml
name = "workflow_run_traces_to_optimization_candidates"
title = "Workflow Run Traces To Optimization Candidates"
description = "Turn selected workflow run traces into step-local and workflow-level optimization candidates without mutating the authoritative workflow."
aliases = ["workflow-optimization-candidates", "trace-to-optimization-candidates"]
```

---

## 6. Register the workflow

Update the bundled workflow registry so the workflow is discoverable.

Update whichever files currently register bundled workflows, including but not limited to:

```text
workflows/__init__.py
docs/workflows/
docs/architecture.md
docs/authoring.md
tests/test_architecture_baseline_docs.py
```

Add a workflow documentation page:

```text
docs/workflows/workflow_run_traces_to_optimization_candidates.md
```

The workflow must appear in `autoloop workflow list` or equivalent bundled workflow listing.

---

## 7. Workflow parameters

Create `params.py`.

Required:

```python
selected_workflow: str
task_title: str
```

Optional:

```python
run_refs: list[str] = []
run_statuses: list[str] = ["failed", "paused", "blocked"]
route_tags: list[str] = ["needs_rework", "needs_replan", "failed", "blocked"]
history_limit: int = 25
top_k_steps: int = 1
optimization_depth: Literal["cheap", "standard", "ablation"] = "cheap"
include_adversarial_generation: bool = True
include_token_optimization: bool = True
include_workflow_level_candidates: bool = True
max_failure_scenarios: int = 25
max_candidates_per_pass: int = 3
focus: str | None = None
sponsor_role: str | None = None
desired_outcome: str | None = None
constraints: list[str] = []
```

### `run_refs`

Use `run_refs`, not bare `run_ids`.

Accepted format:

```text
<task_id>/<run_id>
```

Example:

```text
release-audit-123/run-20260426T120000Z-abcd1234
```

Validation:

```text
run_refs entries must be non-empty strings.
run_refs entries must be unique.
run_refs entries must contain exactly one "/" separator.
```

If `run_refs` is supplied, the optimizer uses only those runs.

If `run_refs` is empty, the optimizer discovers recent runs for `selected_workflow` using `run_statuses` and `history_limit`.

### `run_statuses` vs. `route_tags`

Keep these distinct:

```text
run_statuses:
  filters run-level or terminal status

route_tags:
  filters step-level evidence inside selected runs
```

`needs_rework` and `needs_replan` are step route tags, not run statuses.

Validation:

```text
selected_workflow must resolve to a known workflow.
task_title must be non-empty.
history_limit must be positive.
top_k_steps must be positive.
max_failure_scenarios must be positive.
max_candidates_per_pass must be positive.
optimization_depth must be one of cheap, standard, ablation.
run_statuses entries must be unique.
route_tags entries must be unique.
constraints entries must be non-empty after normalization.
```

---

## 8. Optimization depth semantics

Define exact behavior:

```text
cheap:
  Existing traces only.
  No target-workflow reruns.
  No ablation execution.
  Produces candidates and scorecard.

standard:
  Existing traces only.
  Uses deeper LLM review and stronger cross-checking.
  No target-workflow reruns.
  No ablation execution.
  Produces candidates, scorecard, and may mark higher confidence when evidence is strong.

ablation:
  Does not execute ablations inside this workflow.
  Emits ablation-recommended candidate markings and optional ablation plan fields.
  The separate workflow_optimization_candidates_to_ablation_results may later consume those artifacts.
```

This workflow must never execute ablation runs directly.

---

## 9. Workflow topology

Pair order:

```text
frame
rank_targets
mine_failures
optimize_producer
optimize_verifier_rubric
optimize_tokens
adversarial_cases
workflow_level
package
```

Supported `pairs` subsets must be ordered prefixes only.

### Routes

```text
frame:
  optimization_scope_framed -> rank_targets
  no_eligible_trace_evidence -> package
  needs_rework -> frame
  blocked -> PAUSE
  failed -> FAIL

rank_targets:
  targets_ranked -> mine_failures
  insufficient_evidence -> package
  needs_rework -> rank_targets
  failed -> FAIL

mine_failures:
  failure_scenarios_mined -> optimize_producer
  no_failure_scenarios -> optimize_tokens
  needs_rework -> mine_failures
  failed -> FAIL

optimize_producer:
  producer_candidates_ready -> optimize_verifier_rubric
  producer_pass_not_applicable -> optimize_verifier_rubric
  needs_rework -> optimize_producer
  failed -> FAIL

optimize_verifier_rubric:
  verifier_rubric_candidates_ready -> optimize_tokens
  verifier_rubric_pass_not_applicable -> optimize_tokens
  needs_rework -> optimize_verifier_rubric
  failed -> FAIL

optimize_tokens:
  token_candidates_ready -> adversarial_cases
  token_pass_not_applicable -> adversarial_cases
  needs_rework -> optimize_tokens
  failed -> FAIL

adversarial_cases:
  adversarial_cases_ready -> workflow_level
  adversarial_generation_skipped -> workflow_level
  needs_rework -> adversarial_cases
  failed -> FAIL

workflow_level:
  workflow_level_candidates_ready -> package
  workflow_level_pass_not_applicable -> package
  needs_rework -> workflow_level
  failed -> FAIL

package:
  optimization_packet_ready -> SUCCESS
  needs_rework -> package
  failed -> FAIL
```

Short-circuit behavior:

```text
include_adversarial_generation=false:
  adversarial_cases -> adversarial_generation_skipped

include_token_optimization=false:
  optimize_tokens -> token_pass_not_applicable

include_workflow_level_candidates=false:
  workflow_level -> workflow_level_pass_not_applicable
```

---

## 10. Artifact layout

All artifacts should be written under the optimizer workflow folder:

```text
{workflow_folder}/...
```

Do not write into the selected workflow’s source package.

### Frame artifacts

```text
selected_workflow_capability.json
selected_workflow_authoring_surface.json
selected_workflow_decomposition_surface.json
selected_workflow_source_manifest.json
workflow_optimization_scope.json
workflow_optimization_trace_corpus.json
excluded_run_report.json
```

### Ranking artifacts

```text
step_trace_metrics.json
step_optimization_priority_report.json
```

### Failure artifacts

```text
workflow_failure_scenarios.json
```

### Producer artifacts

```text
producer_prompt_optimization_candidates.json
```

### Verifier/rubric artifacts

```text
verifier_rubric_optimization_candidates.json
```

### Token artifacts

```text
token_optimization_candidates.json
```

### Adversarial artifacts

```text
adversarial_case_candidates.json
```

### Workflow-level artifacts

```text
workflow_level_optimization_candidates.json
```

### Package artifacts

```text
workflow_optimization_scorecard.json
workflow_refinement_evidence.json
workflow_optimization_packet.md
optimization_publication_receipt.json
```

---

## 11. Reuse existing selected-workflow helpers

Do not implement a second selected-workflow serializer.

Reuse existing helper family where possible for:

```text
selected_workflow_capability.json
selected_workflow_authoring_surface.json
selected_workflow_decomposition_surface.json
selected workflow validation
selected workflow identity alignment
```

The optimizer should consume the same selected-workflow surfaces used by adaptation, refinement, decomposition, and eval-suite workflows.

Only add optimizer-specific artifacts around those surfaces.

---

## 12. Deterministic no-source-mutation check

The optimizer must prove it did not mutate the selected workflow source package.

At `frame`, write:

```text
selected_workflow_source_manifest.json
```

This manifest should include enough information to detect accidental source mutation:

```json
{
  "schema": "autoloop.workflow_optimization.source_manifest/v1",
  "selected_workflow": "release_candidate_to_go_no_go",
  "package_dir": "workflows/release_candidate_to_go_no_go",
  "files": [
    {
      "path": "workflows/release_candidate_to_go_no_go/workflow.py",
      "sha256": "...",
      "bytes": 12345
    },
    {
      "path": "workflows/release_candidate_to_go_no_go/prompts/assessment_producer.md",
      "sha256": "...",
      "bytes": 4567
    }
  ]
}
```

Include source files, prompt files, workflow manifest files, contracts, params, assets, and docs inside the selected workflow package.

At `package`, recompute the manifest and compare:

```text
If manifest differs:
  route failed
  write failure reason into workflow_optimization_scorecard.json if possible
```

Do not rely only on git commit equality for this check, because the optimizer itself writes run artifacts and git commits may move.

---

## 13. Old-run and missing-evidence behavior

Many historical runs may predate Plan 1 and lack required observability files.

A run is eligible only if it has:

```text
run.json
trace.jsonl
git_tracking.jsonl
static_step_graph.json
raw/
```

If any required file is missing:

```text
exclude the run by default
record exclusion reason in excluded_run_report.json
do not fail the workflow
```

If all candidate runs are excluded:

```text
route frame -> no_eligible_trace_evidence
package writes a no-op packet explaining why no optimization was performed
```

`workflow_optimization_trace_corpus.json` should include counts:

```json
{
  "candidate_run_count": 12,
  "eligible_run_count": 5,
  "excluded_run_count": 7,
  "excluded_run_report_path": "excluded_run_report.json"
}
```

---

## 14. Artifact schemas

Create schemas in `contracts.py` using the existing JSON artifact/Pydantic helper style.

Keep top-level structure strict. Avoid over-validating natural-language rationale fields.

### 14.1 `workflow_optimization_scope.json`

```json
{
  "schema": "autoloop.workflow_optimization.scope/v1",
  "selected_workflow": "release_candidate_to_go_no_go",
  "task_title": "Optimize release decision workflow",
  "run_refs": ["task-123/run-456"],
  "run_statuses": ["failed", "paused", "blocked"],
  "route_tags": ["needs_rework", "needs_replan", "failed", "blocked"],
  "history_limit": 25,
  "top_k_steps": 1,
  "optimization_depth": "cheap",
  "include_adversarial_generation": true,
  "include_token_optimization": true,
  "include_workflow_level_candidates": true,
  "focus": null,
  "constraints": []
}
```

### 14.2 `excluded_run_report.json`

```json
{
  "schema": "autoloop.workflow_optimization.excluded_run_report/v1",
  "selected_workflow": "release_candidate_to_go_no_go",
  "candidate_run_count": 12,
  "excluded_runs": [
    {
      "task_id": "task-old",
      "run_id": "run-old",
      "run_ref": "task-old/run-old",
      "reason": "missing trace.jsonl"
    }
  ]
}
```

Allowed reasons:

```text
missing_run_json
missing_trace_jsonl
missing_git_tracking_jsonl
missing_static_step_graph
missing_raw_dir
wrong_selected_workflow
unreadable_observability_files
malformed_observability_files
```

### 14.3 `workflow_optimization_trace_corpus.json`

```json
{
  "schema": "autoloop.workflow_optimization.trace_corpus/v1",
  "selected_workflow": "release_candidate_to_go_no_go",
  "candidate_run_count": 12,
  "eligible_run_count": 5,
  "excluded_run_count": 7,
  "step_observation_count": 18,
  "runs": [
    {
      "run_ref": "task-123/run-456",
      "run_id": "run-456",
      "task_id": "task-123",
      "workflow": "release_candidate_to_go_no_go",
      "run_dir": ".autoloop/tasks/task-123/wf_release_candidate_to_go_no_go/runs/run-456",
      "run_json_path": "...",
      "trace_jsonl_path": "...",
      "git_tracking_jsonl_path": "...",
      "static_step_graph_path": "...",
      "terminal": "FAIL",
      "status": "failed",
      "commit_before_run": "abc123",
      "commit_after_run": "def456",
      "eligible_for_optimization": true
    }
  ],
  "step_observations": [
    {
      "observation_id": "task-123/run-456:000003:assessment",
      "run_ref": "task-123/run-456",
      "run_id": "run-456",
      "task_id": "task-123",
      "sequence": 3,
      "step_name": "assessment",
      "step_kind": "pair",
      "route": "needs_rework",
      "raw_output_refs": {
        "producer": "raw/000003_assessment_producer.txt",
        "verifier": "raw/000003_assessment_verifier.txt"
      },
      "usage": {
        "producer_input_tokens": 1000,
        "producer_output_tokens": 200,
        "verifier_input_tokens": 900,
        "verifier_output_tokens": 150,
        "total_tokens": 2250
      },
      "commit_before_step": "abc123",
      "commit_after_step": "def456",
      "local_outcome": "rejected_by_verifier",
      "downstream_outcome": "unknown"
    }
  ]
}
```

### 14.4 `step_trace_metrics.json`

```json
{
  "schema": "autoloop.workflow_optimization.step_trace_metrics/v1",
  "selected_workflow": "release_candidate_to_go_no_go",
  "steps": [
    {
      "step_name": "assessment",
      "step_kind": "pair",
      "observed_count": 12,
      "route_counts": {
        "assessment_complete": 5,
        "needs_rework": 6,
        "failed": 1
      },
      "producer_failed_verifier_count": 6,
      "blocked_count": 0,
      "failed_count": 1,
      "needs_rework_count": 6,
      "needs_replan_count": 0,
      "estimated_token_total": 42000,
      "token_share": 0.41,
      "downstream_failure_after_pass_count": 2,
      "artifact_centrality": 0.8,
      "route_criticality": 0.7
    }
  ]
}
```

### 14.5 `step_optimization_priority_report.json`

```json
{
  "schema": "autoloop.workflow_optimization.step_priority_report/v1",
  "selected_workflow": "release_candidate_to_go_no_go",
  "ranking_method": "static_graph_plus_trace_metrics_plus_llm_attribution",
  "top_k_steps": 1,
  "ranked_steps": [
    {
      "step_name": "assessment",
      "rank": 1,
      "priority_score": 0.86,
      "confidence": 0.78,
      "evidence_strength": "medium",
      "recommended_first_pass": "verifier_rubric_local_optimization",
      "secondary_passes": [
        "producer_local_optimization",
        "token_optimization"
      ],
      "why_high_leverage": [
        "highest needs_rework loop rate",
        "large token share",
        "downstream failures after local acceptance"
      ],
      "likely_failure_surfaces": [
        {
          "surface": "verifier_rubric",
          "probability": 0.48,
          "rationale": "Verifier feedback shows acceptance-boundary ambiguity."
        },
        {
          "surface": "producer_prompt",
          "probability": 0.34,
          "rationale": "Repeated missing evidence normalization across rejected outputs."
        }
      ]
    }
  ],
  "not_selected": [
    {
      "step_name": "package",
      "reason": "Mostly downstream symptom of weak assessment output."
    }
  ]
}
```

Allowed `evidence_strength` values:

```text
low
medium
high
```

### 14.6 `workflow_failure_scenarios.json`

```json
{
  "schema": "autoloop.workflow_optimization.failure_scenarios/v1",
  "selected_workflow": "release_candidate_to_go_no_go",
  "failure_scenarios": [
    {
      "failure_id": "assessment_missing_rollback_evidence",
      "step_name": "assessment",
      "failure_kind": "producer_failed_verifier",
      "severity": "high",
      "frequency": 4,
      "evidence_observation_ids": [
        "task-123/run-456:000003:assessment"
      ],
      "producer_gap": "Producer inferred rollback readiness without direct evidence.",
      "verifier_behavior": "Verifier correctly rejected unsupported claim.",
      "likely_fix_surfaces": [
        "producer_prompt"
      ],
      "downstream_effect": "Decision package could not be published."
    }
  ]
}
```

Allowed `failure_kind` values:

```text
producer_failed_verifier
verifier_false_accept
verifier_false_reject
verifier_rubric_ambiguity
route_misuse
needs_rework_loop
needs_replan_loop
blocked_missing_context
artifact_invalid
artifact_missing
token_bloat
downstream_failure_after_local_pass
workflow_handoff_gap
insufficient_evidence
eval_suite_gap
input_quality_gap
operator_process_gap
```

Do **not** add a validation rule requiring evidence references. The model may include evidence fields, but missing evidence references must not invalidate the artifact.

### 14.7 `producer_prompt_optimization_candidates.json`

```json
{
  "schema": "autoloop.workflow_optimization.producer_candidates/v1",
  "selected_workflow": "release_candidate_to_go_no_go",
  "target_steps": ["assessment"],
  "candidates": [
    {
      "candidate_id": "producer-assessment-001",
      "step_name": "assessment",
      "target_surface": "producer_prompt",
      "target_path": "workflows/release_candidate_to_go_no_go/prompts/assessment_producer.md",
      "failure_ids_addressed": [
        "assessment_missing_rollback_evidence"
      ],
      "diagnosis": "Producer does not separate observed evidence from inference.",
      "proposed_change_summary": "Add explicit evidence/inference separation rule and require missing-evidence callouts.",
      "proposed_unified_diff": null,
      "proposed_patch_instructions": [
        "Add a section requiring direct evidence for each release readiness claim.",
        "Require a Missing Evidence subsection when evidence is absent."
      ],
      "expected_effect": {
        "verifier_pass_rate": "increase",
        "false_accepts": "decrease",
        "token_usage": "slight_increase"
      },
      "confidence": 0.72,
      "evidence_strength": "medium",
      "risks": [
        "May make routine cases more verbose."
      ],
      "requires_ablation": false
    }
  ]
}
```

### 14.8 `verifier_rubric_optimization_candidates.json`

This is one merged acceptance-function artifact.

```json
{
  "schema": "autoloop.workflow_optimization.verifier_rubric_candidates/v1",
  "selected_workflow": "release_candidate_to_go_no_go",
  "target_steps": ["assessment"],
  "candidates": [
    {
      "candidate_id": "verifier-rubric-assessment-001",
      "step_name": "assessment",
      "target_surfaces": [
        "verifier_prompt",
        "criteria",
        "route_contract"
      ],
      "diagnosis": "Verifier accepts schema-valid but semantically unsupported package sections.",
      "failure_ids_addressed": [
        "assessment_false_accept_unsupported_rollback"
      ],
      "proposed_changes": [
        {
          "target_surface": "verifier_prompt",
          "target_path": "workflows/release_candidate_to_go_no_go/prompts/assessment_verifier.md",
          "change_type": "tighten_acceptance_rule",
          "summary": "Reject approval when rollback readiness lacks direct evidence."
        },
        {
          "target_surface": "route_contract",
          "route": "needs_rework",
          "summary": "Clarify that local evidence gaps require needs_rework, not assessment_complete."
        }
      ],
      "expected_effect": {
        "false_accepts": "decrease",
        "false_rejects": "neutral",
        "token_usage": "neutral"
      },
      "confidence": 0.69,
      "evidence_strength": "medium",
      "risks": [
        "May over-block evidence that is implicit but acceptable."
      ],
      "requires_ablation": true
    }
  ]
}
```

### 14.9 `token_optimization_candidates.json`

```json
{
  "schema": "autoloop.workflow_optimization.token_candidates/v1",
  "selected_workflow": "release_candidate_to_go_no_go",
  "candidates": [
    {
      "candidate_id": "token-assessment-001",
      "step_name": "assessment",
      "target_surface": "producer_prompt",
      "target_path": "workflows/release_candidate_to_go_no_go/prompts/assessment_producer.md",
      "compression_kind": "remove_duplicate_static_guidance",
      "risk_class": "safe_compression",
      "estimated_input_token_reduction": 650,
      "diagnosis": "Prompt repeats artifact handling guidance already present in README.",
      "proposed_change_summary": "Replace repeated static checklist text with compact reference to README contract.",
      "quality_risk": "low",
      "confidence": 0.78,
      "evidence_strength": "medium",
      "requires_ablation": false
    }
  ]
}
```

Allowed `risk_class` values:

```text
safe_compression
risky_compression
semantic_behavior_change_disguised_as_compression
```

### 14.10 `adversarial_case_candidates.json`

```json
{
  "schema": "autoloop.workflow_optimization.adversarial_case_candidates/v1",
  "selected_workflow": "release_candidate_to_go_no_go",
  "cases": [
    {
      "case_id": "adversarial_missing_rollback_owner",
      "case_kind": "adversarial",
      "attack_vector": "Evidence implies rollback confidence but omits rollback owner.",
      "prompt": "Assess this release with release notes that sound complete but omit rollback ownership evidence.",
      "source_failure_ids": [
        "assessment_missing_rollback_evidence"
      ],
      "expected_stress": "Verifier should reject unsupported rollback readiness.",
      "expected_route": "needs_rework",
      "expected_artifacts": [
        "release_risk_assessment",
        "blocking_issues"
      ],
      "recommended_for_eval_suite": true,
      "confidence": 0.74,
      "evidence_strength": "medium"
    }
  ]
}
```

### 14.11 `workflow_level_optimization_candidates.json`

```json
{
  "schema": "autoloop.workflow_optimization.workflow_level_candidates/v1",
  "selected_workflow": "release_candidate_to_go_no_go",
  "candidates": [
    {
      "candidate_id": "workflow-level-001",
      "candidate_kind": "artifact_handoff_change",
      "diagnosis": "Assessment and package prompts duplicate release decision criteria, creating drift.",
      "affected_steps": ["assessment", "package"],
      "proposed_change_summary": "Move shared release evidence obligations into one artifact contract and remove duplicate package-level interpretation.",
      "proposed_surfaces": [
        "workflow_code",
        "prompt_readme",
        "package_prompt"
      ],
      "confidence": 0.61,
      "evidence_strength": "low",
      "risks": [
        "Requires workflow-level refactor, not prompt-only patch."
      ],
      "requires_refinement_workflow": true,
      "requires_ablation": true
    }
  ]
}
```

Allowed `candidate_kind` values:

```text
artifact_handoff_change
route_contract_change
step_split
step_merge
prompt_readme_change
context_rendering_change
session_policy_change
workflow_code_change
workflow_parameter_change
eval_suite_gap
input_quality_gap
operator_process_gap
insufficient_evidence
```

### 14.12 `workflow_optimization_scorecard.json`

```json
{
  "schema": "autoloop.workflow_optimization.scorecard/v1",
  "selected_workflow": "release_candidate_to_go_no_go",
  "evidence_run_count": 5,
  "excluded_run_count": 7,
  "target_steps_ranked": 3,
  "failure_scenarios": 12,
  "candidate_counts": {
    "producer": 3,
    "verifier_rubric": 2,
    "token": 2,
    "adversarial_cases": 5,
    "workflow_level": 1
  },
  "recommended_next_action": "Run workflow_and_eval_to_refined_workflow_package with this refinement evidence.",
  "highest_priority_candidate_ids": [
    "verifier-rubric-assessment-001",
    "producer-assessment-001"
  ],
  "requires_ablation_before_promotion": true,
  "source_mutation_check": {
    "passed": true,
    "details": "Selected workflow source manifest unchanged."
  },
  "summary": "Assessment is the highest-leverage local optimization target."
}
```

### 14.13 `workflow_refinement_evidence.json`

Use the existing refinement-evidence pattern.

Add optimization-specific entries:

```json
{
  "schema": "autoloop.workflow_refinement_evidence/v1",
  "source_path": null,
  "target_workflow_id": "release_candidate_to_go_no_go",
  "evidence_entries": [
    {
      "kind": "step_optimization_priority_report",
      "path": "step_optimization_priority_report.json",
      "summary": "Assessment is the highest-leverage optimization target.",
      "handling": "Use to prioritize refinement package changes."
    },
    {
      "kind": "producer_prompt_optimization_candidates",
      "path": "producer_prompt_optimization_candidates.json",
      "summary": "Producer prompt candidates address missing evidence separation.",
      "handling": "Candidate only; validate before materializing."
    },
    {
      "kind": "verifier_rubric_optimization_candidates",
      "path": "verifier_rubric_optimization_candidates.json",
      "summary": "Verifier/rubric candidates tighten false-accept behavior.",
      "handling": "Candidate only; review and optionally ablate before materializing."
    }
  ]
}
```

---

## 15. Standard library support

Create:

```text
stdlib/optimization.py
```

This module should provide deterministic ingestion, metrics, validation, and publication helpers. It should not call LLMs.

Add functions:

```python
def parse_run_ref(run_ref: str) -> tuple[str, str]:
    ...

def list_selected_workflow_runs(
    root: Path,
    selected_workflow: str,
    *,
    run_refs: Sequence[str],
    run_statuses: Sequence[str],
    history_limit: int,
) -> list[Path]:
    ...

def load_run_observability_bundle(run_dir: Path) -> RunObservabilityBundle:
    ...

def validate_observability_bundle(bundle: RunObservabilityBundle) -> tuple[bool, str | None]:
    ...

def normalize_trace_corpus(
    *,
    selected_workflow: str,
    run_dirs: Sequence[Path],
    route_tags: Sequence[str],
) -> dict[str, Any]:
    ...

def build_step_trace_metrics(
    trace_corpus: Mapping[str, Any],
    static_step_graphs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    ...

def compute_static_step_centrality(
    static_step_graph: Mapping[str, Any],
) -> dict[str, float]:
    ...

def rank_optimization_targets(
    *,
    step_metrics: Mapping[str, Any],
    static_centrality: Mapping[str, float],
    top_k: int,
) -> dict[str, Any]:
    ...

def extract_failure_scenario_seeds(
    *,
    trace_corpus: Mapping[str, Any],
    priority_report: Mapping[str, Any],
    max_scenarios: int,
) -> dict[str, Any]:
    ...

def write_selected_workflow_source_manifest(
    *,
    ctx: Context,
    selected_workflow: str,
    relative_path: str,
) -> Path:
    ...

def validate_selected_workflow_source_unchanged(
    *,
    ctx: Context,
    selected_workflow: str,
    manifest_path: Path,
) -> tuple[bool, str]:
    ...

def write_optimization_refinement_evidence(
    *,
    ctx: Context,
    selected_workflow: str,
    evidence_entries: Sequence[Mapping[str, Any]],
) -> Path:
    ...
```

Avoid importing runtime internals directly unless the existing stdlib already has safe helper patterns for reading `.autoloop` state. Prefer filesystem-level ingestion of run artifacts.

---

## 16. Step priority scoring

Implement deterministic base scoring in `stdlib/optimization.py`.

Formula:

```text
priority_score =
  0.25 * direct_failure_rate
+ 0.20 * downstream_blast_radius
+ 0.15 * rework_loop_cost
+ 0.15 * artifact_centrality
+ 0.10 * route_criticality
+ 0.10 * token_cost_share
+ 0.05 * sample_support
```

Penalties:

```text
insufficient_sample_penalty
missing_trace_data_penalty
no_prompt_surface_penalty
likely_downstream_symptom_penalty
```

The LLM `rank_targets` pair may adjust attribution and rationale, but should not override deterministic evidence without explanation.

Ranking must distinguish:

```text
highest failure count
```

from:

```text
highest leverage optimization target
```

If a later step fails because an upstream artifact is weak, the priority report should attribute optimization pressure upstream.

---

## 17. Failure scenario mining

Use deterministic seeds plus LLM diagnosis.

Deterministic seeds:

```text
PairStep route in route_tags
LLMStep route in route_tags
repeated same-step route loops
high token usage with no success
terminal failure after a step passed
missing raw output reference
missing usage data
missing static graph
```

LLM diagnosis should classify failures into the allowed `failure_kind` values.

A failure scenario may include observation IDs and raw-output references, but the artifact must not require them.

---

## 18. Prompt requirements

Each optimization prompt must include:

```text
input artifacts to read
output artifact to write
schema requirements
non-mutation rule
candidate-only rule
no hidden execution rule
no claims of reruns unless ablation evidence exists
```

### Shared prompt README

`prompts/README.md` must say:

```text
This workflow proposes optimization candidates only.
Do not edit source prompts or workflow files.
Do not run the selected workflow.
Do not claim a candidate improves performance unless ablation or rerun evidence exists.
Separate observed evidence from inference.
Prefer targeted local changes before workflow-level changes.
Verifier/rubric changes are one acceptance-function surface.
Token compression must be classified by quality risk.
```

### Verifier prompts

Verifier prompts must reject outputs that:

```text
omit required schema fields
invent run evidence
claim tests/reruns happened without evidence
propose direct source mutation
recommend automatic promotion
collapse producer and verifier/rubric surfaces
mislabel risky semantic changes as safe compression
```

Do not add rejection solely because evidence references are absent.

---

## 19. Pass-by-pass implementation

### 19.1 `frame`

Purpose:

```text
Resolve selected workflow.
Write selected-workflow snapshots.
Write selected-workflow source manifest.
Collect eligible run evidence.
Normalize trace corpus.
Write no-op packet if no eligible runs exist.
```

Implementation:

```text
Use selected-workflow helper family.
Use stdlib/optimization.py to find and load run evidence.
Exclude old/malformed runs and write excluded_run_report.json.
Write workflow_optimization_scope.json.
Write workflow_optimization_trace_corpus.json.
```

Outputs:

```text
selected_workflow_capability.json
selected_workflow_authoring_surface.json
selected_workflow_decomposition_surface.json
selected_workflow_source_manifest.json
workflow_optimization_scope.json
workflow_optimization_trace_corpus.json
excluded_run_report.json
```

Routes:

```text
optimization_scope_framed
no_eligible_trace_evidence
needs_rework
blocked
failed
```

### 19.2 `rank_targets`

Purpose:

```text
Identify highest-leverage step(s) and likely optimization surface.
```

Implementation:

```text
Deterministically build step_trace_metrics.json.
LLM reviews metrics, static graph, and representative trace summaries.
Write step_optimization_priority_report.json.
```

Outputs:

```text
step_trace_metrics.json
step_optimization_priority_report.json
```

Routes:

```text
targets_ranked
insufficient_evidence
needs_rework
failed
```

### 19.3 `mine_failures`

Purpose:

```text
Turn trace observations into failure scenarios for selected high-priority steps.
```

Inputs:

```text
workflow_optimization_trace_corpus.json
step_optimization_priority_report.json
selected_workflow_authoring_surface.json
static graphs
raw output refs
```

Output:

```text
workflow_failure_scenarios.json
```

Routes:

```text
failure_scenarios_mined
no_failure_scenarios
needs_rework
failed
```

### 19.4 `optimize_producer`

Purpose:

```text
Propose producer prompt candidates only.
```

Allowed targets:

```text
producer prompt
producer artifact instructions
producer evidence-discipline instructions
producer output-shape instructions
```

Forbidden targets:

```text
verifier prompt
criteria/rubric
route contracts
workflow topology
runtime behavior
source mutation
```

Output:

```text
producer_prompt_optimization_candidates.json
```

Routes:

```text
producer_candidates_ready
producer_pass_not_applicable
needs_rework
failed
```

### 19.5 `optimize_verifier_rubric`

Purpose:

```text
Propose acceptance-function candidates.
```

Merged target surface:

```text
verifier prompt
criteria/rubric text
route-review policy
route contracts
required-artifact interpretation
feedback specificity
```

Output:

```text
verifier_rubric_optimization_candidates.json
```

Important rule:

```text
If evidence suggests the verifier was correct and the producer failed, do not propose verifier/rubric changes merely to improve pass rate.
```

Routes:

```text
verifier_rubric_candidates_ready
verifier_rubric_pass_not_applicable
needs_rework
failed
```

### 19.6 `optimize_tokens`

Purpose:

```text
Propose token-reduction candidates without silently changing semantics.
```

Output:

```text
token_optimization_candidates.json
```

Token candidates must classify risk as:

```text
safe_compression
risky_compression
semantic_behavior_change_disguised_as_compression
```

Routes:

```text
token_candidates_ready
token_pass_not_applicable
needs_rework
failed
```

### 19.7 `adversarial_cases`

Purpose:

```text
Use a strong LLM to propose adversarial cases targeting observed failure modes.
```

Output:

```text
adversarial_case_candidates.json
```

Do not add cases directly to an eval suite.

Routes:

```text
adversarial_cases_ready
adversarial_generation_skipped
needs_rework
failed
```

### 19.8 `workflow_level`

Purpose:

```text
Propose global workflow candidates after local passes exist.
```

Allowed targets:

```text
artifact handoff
route contract
step split/merge
prompt README
context rendering
session policy
workflow parameter
workflow code
eval suite gap
input quality gap
operator process gap
```

Output:

```text
workflow_level_optimization_candidates.json
```

Rule:

```text
Prefer local optimization candidates unless evidence shows cross-step or workflow-level cause.
```

Routes:

```text
workflow_level_candidates_ready
workflow_level_pass_not_applicable
needs_rework
failed
```

### 19.9 `package`

Purpose:

```text
Verify selected workflow source was not mutated.
Publish scorecard, refinement evidence, packet, and receipt.
```

Required deterministic check:

```text
Recompute selected_workflow_source_manifest.json.
If selected workflow source changed, route failed.
```

Outputs:

```text
workflow_optimization_scorecard.json
workflow_refinement_evidence.json
workflow_optimization_packet.md
optimization_publication_receipt.json
```

The packet must state:

```text
which candidates are ready for review
which require ablation
which are token-only
which are adversarial eval-case candidates
which require workflow-level refinement
```

---

## 20. Optional ablation workflow design

This is optional and may be implemented later:

```text
workflows/workflow_optimization_candidates_to_ablation_results/
```

It must never run by default.

Inputs:

```python
selected_workflow: str
optimization_candidates_path: str
case_matrix_path: str | None = None
suite_manifest_path: str | None = None
candidate_ids: list[str] = []
max_case_runs: int = 5
focus: str | None = None
```

Outputs:

```text
optimization_ablation_plan.json
optimization_ablation_results.json
workflow_refinement_evidence.json
```

Boundary:

```text
If candidate overlay execution is not supported, publish an ablation plan and mark execution unsupported.
Do not fake ablation results.
Do not mutate authoritative workflow files.
```

---

## 21. Refinement integration

Update `workflow_and_eval_to_refined_workflow_package` only enough to accept optimization evidence entries as valid refinement evidence.

Accepted evidence kinds:

```text
step_optimization_priority_report
workflow_failure_scenarios
producer_prompt_optimization_candidates
verifier_rubric_optimization_candidates
token_optimization_candidates
adversarial_case_candidates
workflow_level_optimization_candidates
workflow_optimization_scorecard
optimization_ablation_results
```

Update refinement prompts so they understand:

```text
optimization candidates are not proof of improvement
ablation results, if present, are stronger evidence than candidate estimates
token candidates must preserve semantics
adversarial cases should usually feed eval-suite authoring before prompt promotion
```

Do not merge optimization workflow into refinement workflow.

---

## 22. Documentation

Add:

```text
docs/workflows/workflow_run_traces_to_optimization_candidates.md
```

Required sections:

```text
Problem and value
Invocation
Parameters
Artifacts
Topology
Step-local optimization phase
Workflow-level optimization phase
Optional ablation boundary
Refinement handoff
Non-mutation guarantee
Validation commands
```

Update:

```text
docs/architecture.md
docs/authoring.md
docs/workflows/workflow_and_eval_to_refined_workflow_package.md
docs/workflows/workflow_to_eval_suite.md
docs/workflows/workflow_run_history_to_failure_modes.md
```

Must document:

```text
The optimizer consumes runtime trace/git/raw/static graph evidence.
The optimizer emits candidates only.
The optimizer does not edit workflow source.
The optimizer does not run target workflows by default.
The optimizer does not run refinement automatically.
Ablation is optional and separate.
Verifier/rubric optimization is one merged acceptance-function pass.
run_refs use <task_id>/<run_id>.
run_statuses and route_tags are separate.
Historical runs missing Plan-1 observability are excluded by default.
```

---

## 23. Tests

### 23.1 Unit tests for optimization helpers

Create:

```text
tests/unit/test_optimization_helpers.py
```

Required tests:

```text
test_parse_run_ref_accepts_task_slash_run
test_parse_run_ref_rejects_invalid_shapes
test_list_selected_workflow_runs_filters_by_workflow_and_status
test_explicit_run_refs_select_exact_runs
test_load_run_observability_bundle_requires_run_json_trace_static_graph_git_tracking_and_raw
test_missing_plan1_files_exclude_run_with_reason
test_normalize_trace_corpus_preserves_raw_refs_and_git_commits
test_normalize_trace_corpus_separates_run_statuses_from_route_tags
test_build_step_trace_metrics_counts_routes_and_tokens
test_rank_targets_prefers_high_leverage_upstream_step_over_downstream_symptom
test_extract_failure_scenario_seeds_limits_to_max_scenarios
test_write_selected_workflow_source_manifest_records_hashes
test_validate_selected_workflow_source_unchanged_detects_mutation
test_write_optimization_refinement_evidence_uses_expected_schema
```

### 23.2 Workflow tests

Create:

```text
tests/runtime/test_workflow_run_traces_to_optimization_candidates.py
```

Required tests:

```text
test_workflow_is_registered_and_describable
test_workflow_describe_lists_parameters_and_pairs
test_frame_no_eligible_runs_publishes_noop_packet
test_frame_excludes_old_runs_missing_plan1_observability
test_frame_normalizes_trace_corpus_from_seeded_runs
test_rank_targets_writes_priority_report
test_mine_failures_writes_failure_scenarios
test_optimize_producer_writes_candidate_artifact
test_optimize_verifier_rubric_writes_merged_acceptance_candidates
test_optimize_tokens_writes_token_candidates
test_adversarial_cases_can_be_skipped
test_adversarial_cases_writes_candidate_cases_when_enabled
test_workflow_level_can_be_skipped
test_package_writes_scorecard_refinement_evidence_packet_and_receipt
test_package_fails_if_selected_workflow_source_changed
test_workflow_never_mutates_selected_workflow_source
test_pairs_subset_must_be_ordered_prefix
test_optimization_depth_ablation_does_not_execute_ablation
```

Use fake provider scripts for LLM outputs.

### 23.3 Refinement integration tests

Update:

```text
tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py
```

Required tests:

```text
test_refinement_accepts_optimization_refinement_evidence_entries
test_refinement_treats_candidate_without_ablation_as_unproven
test_refinement_does_not_materialize_adversarial_cases_automatically
```

### 23.4 Docs tests

Update:

```text
tests/test_architecture_baseline_docs.py
```

Required assertions:

```text
workflow_run_traces_to_optimization_candidates documented as active bundled workflow
optimizer does not mutate source automatically
optimizer does not run ablation by default
optimizer emits workflow_refinement_evidence.json
verifier/rubric optimization is one merged acceptance-function pass
run_refs use task/run identity
run_statuses and route_tags are distinct
```

---

## 24. Implementation order

Implement in this order:

```text
1. Add stdlib/optimization.py deterministic helpers.
2. Add contracts.py schemas.
3. Add params.py model.
4. Add workflow package directory and workflow.toml.
5. Register workflow in bundled workflow registry.
6. Implement frame pair and trace-corpus generation.
7. Implement source manifest write/validate helpers.
8. Implement static metrics and rank_targets pair.
9. Implement mine_failures pair.
10. Implement optimize_producer pair.
11. Implement optimize_verifier_rubric pair.
12. Implement optimize_tokens pair.
13. Implement adversarial_cases pair with skip behavior.
14. Implement workflow_level pair with skip behavior.
15. Implement package pair, source mutation check, scorecard, receipt, and refinement evidence.
16. Extend refinement workflow to accept optimization evidence kinds.
17. Add workflow docs.
18. Add unit tests.
19. Add workflow tests.
20. Add refinement integration tests.
21. Add architecture/doc baseline tests.
22. Run full test suite.
```

---

## 25. Acceptance criteria

The implementation is complete when:

```text
workflow_run_traces_to_optimization_candidates is discoverable.
workflow describe shows all required params and pairs.
The workflow accepts run_refs in <task_id>/<run_id> format.
run_statuses and route_tags are separate.
Old runs missing Plan-1 observability are excluded by default.
The workflow consumes run.json, trace.jsonl, git_tracking.jsonl, static_step_graph.json, and raw refs.
The workflow emits workflow_optimization_trace_corpus.json.
The workflow ranks highest-leverage step(s) before local optimization.
The workflow mines failure scenarios from traces.
Producer optimization is a separate pass.
Verifier/rubric optimization is one merged pass.
Token optimization is a separate pass.
Adversarial case generation is optional and separate.
Workflow-level optimization runs only after local candidate artifacts exist.
Ablation is not executed by default, even when optimization_depth=ablation.
All candidate artifacts are candidate-only and do not mutate source.
The package step verifies selected workflow source was not mutated.
workflow_refinement_evidence.json includes optimization evidence entries.
workflow_and_eval_to_refined_workflow_package accepts optimization evidence.
No target workflow execution is hidden inside the optimizer.
No refinement workflow execution is hidden inside the optimizer.
All tests pass.
Docs describe the new workflow and boundaries.
```

---

## 26. Final boundary statement

After this implementation:

```text
Runtime evidence layer provides:
  run.json
  events.jsonl
  trace.jsonl
  git_tracking.jsonl
  static_step_graph.json
  raw/

Optimization workflow provides:
  trace corpus
  step ranking
  failure scenarios
  producer candidates
  verifier/rubric candidates
  token candidates
  adversarial case candidates
  workflow-level candidates
  refinement evidence

Refinement workflow provides:
  implementation-ready candidate package

Repo-patch workflow provides:
  explicit materialization

Nothing is silently optimized, applied, promoted, or rolled back.
```
