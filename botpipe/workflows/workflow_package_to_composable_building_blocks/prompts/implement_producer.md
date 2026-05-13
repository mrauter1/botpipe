# Implement Candidate Decomposition Producer

## Step Contract

### Role
- You are the workflow decomposer for the `implement_candidate_decomposition` step.

### Purpose
- Build the candidate decomposition overlay, declared building-block index, and supporting build artifacts without mutating the authoritative selected workflow package.

### Current work item
- This work item owns candidate implementation only.
- Use the copied baseline parent workflow surface as the source for the candidate overlay.
- Publish the parent rewrite and extracted building blocks into `candidate_decomposition_surface/`.
- Do not publish the receipt or promotion the candidate in this step.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `selected_workflow_decomposition_surface` | Read | Required input. |
| `baseline_parent_workflow_surface` | Read | Required input. |
| `baseline_parent_manifest` | Read | Required input. |
| `decomposition_evidence_manifest` | Read | Required input. |
| `decomposition_request_brief` | Read | Required input. |
| `decomposition_acceptance_criteria` | Read | Required input. |
| `extraction_strategy` | Read | Required input. |
| `building_block_interface_contracts` | Read | Required input. |
| `parent_rewrite_plan` | Read | Required input. |
| `regression_guardrails` | Read | Required input. |
| `candidate_decomposition_surface` | Write | Overwrite. |
| `candidate_building_block_index.json` | Write | Overwrite. |
| `decomposition_build_report` | Write | Overwrite. |
| `candidate_diff_summary` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- Do not hand-write `candidate_decomposition_manifest.json`; the workflow derives it deterministically after verification.
- Do not create `decomposition_verification_report`, `composition_migration_guide`, `promotion_record`, `rollback_plan`, or `workflow_decomposition_receipt.json` in this step.

## Output Requirements

### Artifact handling
- `candidate_decomposition_surface/` must contain:
- the rewritten parent workflow surface,
- at least one extracted workflow package under `botpipe/workflows/`,
- the associated docs and runtime-test footprint for each extracted building block.
- `candidate_building_block_index.json` must be valid JSON and define:
- `selected_workflow_name`,
- `publication_mode` set to `candidate_only`,
- `promotion_required` set to `true`,
- `building_blocks` with one entry per candidate building block and explicit package, doc, and runtime-test paths.
- `decomposition_build_report` must state what changed, what stayed unchanged in the authoritative repo, and how the candidate overlay should be validated later.
- `candidate_diff_summary` must summarize the parent rewrite and each extracted building block.

### Expected outcome
- Leave the workflow with an explicit candidate decomposition overlay that another step can evaluate and publish without guessing package identity, file boundaries, or hidden execution policy.

## Evidence

- Keep every baseline parent workflow file present in the candidate overlay.
- Keep the candidate package candidate-only: no in-place promotion, no hidden mutation of the authoritative selected workflow package, and no undeclared building blocks.
- Make the declared building-block index consistent with the candidate overlay so deterministic manifest derivation can succeed.

## Routes

- Treat helper routes only when the runtime contract exposes them for this step; use `question` only use it only when a true intent gap or missing hard constraint blocks safe progress.
- Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

### Route guidance for the verifier
- `candidate_decomposition_built`: the candidate surface, declared building-block index, and build artifacts are explicit enough for evaluation.
- `needs_rework`: the same implementation boundary still holds, but the candidate files or build artifacts need local repair.
- `needs_replan`: implementation exposed a material change to the selected workflow boundary, declared package set, or accepted plan.
- Treat helper routes only when the runtime contract exposes them for this step; use `question` only use it only for true intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Publishing the deterministic manifest yourself.
- Publishing the evaluation artifacts or receipt.
- Mutating the authoritative selected workflow package.

## Forbidden

- Do not write outside `candidate_decomposition_surface/` except for the named build artifacts.
- Do not create undeclared workflow packages, docs, or tests that are missing from `candidate_building_block_index.json`.
- Do not hide publication policy or promotion behavior in provider prose only; durable outputs must capture it explicitly.
