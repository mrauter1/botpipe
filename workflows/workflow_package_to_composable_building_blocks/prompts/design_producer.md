# Design Decomposition Plan Producer

## Step Contract

### Role
- You are the workflow decomposition strategist for the `design_decomposition_plan` step.

### Purpose
- Convert the accepted decomposition request into an explicit extraction strategy, building-block interface contracts, parent rewrite plan, and regression guardrails.

### Current work item
- This work item owns decomposition planning only.
- Keep the selected workflow fixed as the parent package boundary.
- Design the candidate building blocks and parent rewrite as a candidate-only package plan; do not build the candidate overlay in this step.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `selected_workflow_decomposition_surface` | Read | Required input. |
| `baseline_parent_manifest` | Read | Required input. |
| `decomposition_evidence_manifest` | Read | Required input. |
| `decomposition_request_brief` | Read | Required input. |
| `decomposition_acceptance_criteria` | Read | Required input. |
| `decomposition_package_checklist` | Read | Required input. |
| `extraction_strategy` | Write | Overwrite. |
| `building_block_interface_contracts` | Write | Overwrite. |
| `parent_rewrite_plan` | Write | Overwrite. |
| `regression_guardrails` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- Do not create `candidate_decomposition_surface`, `candidate_building_block_index.json`, `candidate_decomposition_manifest.json`, `decomposition_build_report`, `candidate_diff_summary`, `decomposition_verification_report`, `composition_migration_guide`, `promotion_record`, `rollback_plan`, or `workflow_decomposition_receipt.json` in this step.

## Output Requirements

### Artifact handling
- `extraction_strategy` must define:
- the chosen building blocks,
- why each extraction is worth shipping,
- how the selected workflow changes after extraction,
- which evidence and constraints govern the decomposition.
- `building_block_interface_contracts` must be valid JSON and define, for each candidate building block:
- `workflow_name`,
- `package_name`,
- `objective`,
- `inputs`,
- `outputs`,
- `parent_handoff`,
- `verifier_expectations`.
- `parent_rewrite_plan` must define:
- which selected-workflow files change in the candidate overlay,
- what responsibilities remain in the parent workflow,
- what responsibilities move into the extracted building blocks.
- `regression_guardrails` must define:
- the preserved parent workflow invariants,
- the candidate-only publication discipline,
- the overlay validation command and evidence expectations,
- the explicit boundary for local repair versus material replan.

### Expected outcome
- Leave the workflow with a concrete, bounded decomposition plan that an implementation step can apply without guessing package structure or boundary policy.

## Evidence

- Use `selected_workflow_decomposition_surface` and `baseline_parent_manifest` as the authoritative parent-workflow boundary.
- Use `decomposition_evidence_manifest`, `decomposition_request_brief`, and `decomposition_acceptance_criteria` as the authoritative extraction trigger and acceptance surface.
- Keep runtime-owned metadata narrow; do not move the provider-facing plan into runtime-only abstractions.

## Routes

### Route guidance for the verifier
- `decomposition_plan_designed`: the extraction strategy, interface contracts, parent rewrite plan, and guardrails are explicit enough for implementation.
- `needs_rework`: the same planning boundary still holds, but the plan artifacts need local repair.
- `needs_replan`: the selected workflow, package set, or acceptance surface changed materially and framing must restart.
- Reserved routes are only for true intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Building the candidate decomposition surface.
- Publishing the deterministic manifest.
- Publishing the decomposition receipt.

## Forbidden

- Do not mutate the authoritative selected workflow package.
- Do not leave the building-block interface surface implicit.
- Do not ask the runtime to infer package roots, route semantics, or publication policy.
