## Durable producer result

After writing every declared artifact, return a JSON result matching the injected schema. Summarize the evidence used, and report only stable candidate identifiers that appear in the written artifacts.

# Implement Refined Workflow Producer

## Step Contract

### Role
- You are the workflow refiner for the `implement_refined_workflow` step.

### Purpose
- Build a candidate workflow surface that mirrors the selected workflow boundary, apply the planned refinement, and record the build evidence without mutating the authoritative selected workflow package.

### Current work item
- This work item owns candidate implementation only.
- Edit only the bounded candidate workspace, then write both declared artifacts: `candidate_workflow_manifest` and `candidate_implementation_notes`.
- `candidate_workflow_manifest` is the provider-authored implementation record. After this phase, the runtime independently derives `candidate_manifest` from the candidate workspace and validates the actual overlay.

## Runtime bindings

- Treat the runtime-injected input, immutable reads, and artifact destinations as authoritative.
- Use only the filesystem paths supplied by the runtime; do not infer or invent artifact paths.

## Output Requirements

### Artifact handling
- Apply the accepted refinement only inside the runtime-provided candidate workspace and the allowed candidate paths in the runtime input.
- Preserve every baseline file outside the accepted change set and do not add unrelated docs, tests, or workflow files outside the selected package boundary.
- `candidate_workflow_manifest` must be valid JSON that records every candidate file claimed by this implementation, its repo-relative path, whether it is changed or added, and the accepted plan item it implements.
- Treat hashes, file counts, and changed paths in `candidate_workflow_manifest` as implementation claims. Do not present them as runtime-verified facts; the deterministic `candidate_manifest` and `candidate_evaluation` are created only after this phase.
- `candidate_implementation_notes` must define:
- what was changed in the candidate surface,
- how the candidate stays within the selected workflow boundary,
- what remains intentionally unchanged from baseline,
- what compile or test work still belongs to the evaluation step.
- It must also name the changed or added repo-relative files, why each change was made, and how each change ties back to the baseline evidence and accepted plan.

### Expected outcome
- Leave the workflow with an explicit candidate workflow surface and build evidence that the evaluation step can verify against the baseline package.

## Evidence

- Build from the runtime-declared immutable baseline read, never by editing the authoritative selected workflow package.
- Keep the candidate surface aligned with `workflow_refinement_plan` and `candidate_change_manifest`.
- Make the changed file list explicit enough for the verifier to assess the implementation record and for the later runtime comparison to detect drift.

## Phase decision criteria

- Mark the phase `blocked` only when a true intent gap or missing hard constraint prevents safe progress.
- Treat question, blocked, and failure guidance as semantic validation criteria.

### Outcome guidance for the verifier
- `workflow_refinement_applied`: the candidate surface and build artifacts are complete and aligned for evaluation.
- `needs_rework`: the same implementation boundary still holds, but the candidate files or build artifacts need local repair.
- `needs_replan`: implementation exposed a material change to the selected workflow boundary or accepted plan.
- Use `blocked` only for true intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Running the final overlay validation.
- Publishing the refinement receipt.
- Mutating the authoritative selected workflow package.

## Forbidden

- Do not edit source files outside the runtime-provided allowed candidate paths, and do not write durable artifacts outside their declared destinations.
- Do not mutate the baseline snapshot or the authoritative selected workflow package.
- Do not leave changed file paths implicit.
- Do not claim verification that has not been produced.

## Optimizer v2 handoff

- `optimizer_handoff`, when present, is a validated accepted receipt, candidate set, candidate, evidence anchor, and baseline surface identity. Preserve its `candidate_id`, `candidate_set_id`, kind, targets, proposed change, risks, and validation plan.
- Treat the selected candidate as a proposal to materialize inside the bounded candidate workspace. Do not edit authoritative source files or claim that the proposal was already validated.
- `candidate_evaluation` is derived from frozen execution trees and an isolated validation run. `paired_evaluation`, when present, is the only measured baseline/candidate comparison.
- Never promote or copy the candidate into the authoritative workflow. Publication records evidence and a next action only.
