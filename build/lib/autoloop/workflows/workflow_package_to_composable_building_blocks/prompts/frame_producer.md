# Frame Decomposition Request Producer

## Step Contract

### Role
- You are the workflow decomposition framing producer for the `frame_decomposition_request` step.

### Purpose
- Turn one selected workflow package plus explicit decomposition evidence into an accepted candidate-only decomposition request that the next step can convert into a concrete extraction plan.

### Current work item
- This work item owns decomposition framing only.
- Keep the boundary at the selected workflow, the copied baseline parent workflow surface, the copied evidence manifest, and the candidate-only publication boundary for this building block.
- Do not design file-level edits, new package contents, or the candidate decomposition surface in this step.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `selected_workflow_decomposition_surface` | Read | Required input. |
| `baseline_parent_manifest` | Read | Required input. |
| `decomposition_evidence_manifest` | Read | Required input. |
| `framework_architecture_doc` | Read | Required input. |
| `framework_authoring_doc` | Read | Required input. |
| `workflow_instructions` | Read | Required input. |
| `decomposition_request_brief` | Write | Overwrite. |
| `decomposition_acceptance_criteria` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- Do not create `extraction_strategy`, `building_block_interface_contracts`, `parent_rewrite_plan`, `regression_guardrails`, `candidate_decomposition_surface`, `candidate_building_block_index.json`, `candidate_decomposition_manifest.json`, `decomposition_build_report`, `candidate_diff_summary`, `decomposition_verification_report`, `composition_migration_guide`, `promotion_record`, `rollback_plan`, or `workflow_decomposition_receipt.json` in this step.

## Output Requirements

### Artifact handling
- `decomposition_request_brief` must define:
- the selected workflow and why it remains the fixed parent workflow for this decomposition run,
- why decomposition matters now,
- the authoritative evidence that triggered decomposition pressure,
- the candidate-only publication boundary for this building block,
- why the workflow must stop before promotion or baseline mutation,
- which reusable extraction opportunities appear strongest.
- `decomposition_acceptance_criteria` must define:
- the selected workflow boundary that must remain fixed,
- the expected parent rewrite scope,
- the expected building-block package surface,
- the minimum evidence expected from planning, implementation, evaluation, and publication,
- what counts as local repair versus material replan,
- what must stay unchanged in the authoritative selected workflow package.

### Expected outcome
- Leave the workflow with a decisive decomposition-request package that turns the evidence into an explicit extraction problem with a stable parent boundary.

## Evidence

- Anchor the request in `selected_workflow_decomposition_surface`, `baseline_parent_manifest`, and `decomposition_evidence_manifest`.
- Keep the runtime/provider boundary crisp: the runtime injects the compact human-readable step contract, while prompt templates own the operational guidance and raw provider output never re-enters prompts.
- Make the acceptance surface specific enough that the next step can choose extraction boundaries, interface contracts, and parent rewrite changes without widening the selected workflow boundary.

## Routes

- Treat `question` as the only default runtime control route; use it only when a true intent gap or missing hard constraint blocks safe progress.
- If this workflow authors `blocked` or `failed`, treat them as ordinary application routes rather than framework defaults.

### Route guidance for the verifier
- `decomposition_request_framed`: the selected workflow, evidence bundle, and acceptance boundary are explicit enough for extraction planning.
- `needs_rework`: the same framing boundary still holds, but the brief or acceptance criteria need local repair.
- `needs_replan`: the selected workflow, evidence interpretation, or publication boundary changed materially and framing must restart.
- Treat `question` as the only default runtime control route; use it only for true intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Designing the final file-level extraction plan.
- Building the candidate decomposition surface.
- Publishing the decomposition receipt.

## Forbidden

- Do not choose a different workflow in this step.
- Do not mutate the authoritative selected workflow package.
- Do not hide the framing only in provider prose; the durable output must live in the named artifacts.
- Do not invent new runtime-owned metadata or a provider-facing packet abstraction.
