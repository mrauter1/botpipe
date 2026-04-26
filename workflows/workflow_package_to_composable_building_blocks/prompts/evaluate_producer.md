# Evaluate Candidate Decomposition Producer

## Step Contract

### Role
- You are the workflow decomposition evaluator for the `evaluate_candidate_decomposition` step.

### Purpose
- Convert the candidate decomposition overlay into explicit verification, migration, promotion, and rollback artifacts without promoting the candidate into the authoritative repo.

### Current work item
- This work item owns decomposition evaluation only.
- Use the candidate overlay, deterministic manifest, and declared building-block index as the publication boundary.
- Do not publish the receipt in this step.

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
| `candidate_decomposition_surface` | Read | Required input. |
| `candidate_decomposition_manifest` | Read | Required input. |
| `candidate_building_block_index` | Read | Required input. |
| `decomposition_build_report` | Read | Required input. |
| `candidate_diff_summary` | Read | Required input. |
| `decomposition_verification_report` | Write | Overwrite. |
| `composition_migration_guide` | Write | Overwrite. |
| `promotion_record` | Write | Overwrite. |
| `rollback_plan` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- Do not create `workflow_decomposition_receipt.json` in this step.

## Output Requirements

### Artifact handling
- `decomposition_verification_report` must define:
- why the candidate overlay is or is not publication-ready,
- what overlay-validation evidence is required,
- how the declared building-block boundary stays explicit.
- `composition_migration_guide` must define:
- how to move from the baseline parent workflow to the decomposed candidate,
- how the extracted building blocks should be adopted,
- what operators must verify before promotion.
- `promotion_record` must define:
- what artifacts are authoritative for promotion,
- what must stay true before promotion,
- why promotion remains explicit rather than automatic.
- `rollback_plan` must define:
- the authoritative rollback baseline,
- how to discard or quarantine the candidate overlay if it proves unsafe,
- how to preserve evidence when promotion is deferred or rejected.

### Expected outcome
- Leave the workflow with a publication-ready decomposition package that still stops before promotion.

## Evidence

- Treat `candidate_decomposition_manifest.json` and `candidate_building_block_index.json` as the authoritative candidate boundary.
- Keep the runtime/provider boundary crisp: prompt templates own the operational evaluation guidance, while the runtime injects the compact human-readable step contract and raw provider output never re-enters prompts.
- Make the outputs specific enough that the publish step can validate them mechanically.

## Routes

### Route guidance for the verifier
- `candidate_decomposition_evaluated`: the verification report, migration guide, promotion record, and rollback plan are publication-ready.
- `needs_rework`: the same decomposition boundary still holds, but the candidate package needs local repair before publication.
- `needs_replan`: evaluation showed the accepted decomposition boundary or package set changed materially and planning must be revisited.
- Reserved routes are only for true intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Publishing the receipt.
- Promoting the candidate into the authoritative repo.
- Expanding the building-block set beyond the accepted plan.

## Forbidden

- Do not mutate the authoritative selected workflow package.
- Do not hide promotion or rollback policy only in provider prose.
- Do not treat missing overlay-validation evidence as acceptable for publication.
