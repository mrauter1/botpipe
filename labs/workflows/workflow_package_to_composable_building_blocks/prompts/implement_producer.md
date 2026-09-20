## Durable producer result

After writing every declared artifact, return a JSON result matching the injected schema. Summarize the evidence used, and report only stable candidate identifiers that appear in the written artifacts.

# Implement Candidate Decomposition Producer

## Step Contract

### Role
- You are the workflow decomposer for the `implement_candidate_decomposition` step.

### Purpose
- Build the candidate decomposition overlay, declared building-block index, and supporting build artifacts without mutating the authoritative selected workflow package.

### Current work item
- This work item owns candidate implementation only.
- Use the copied baseline parent workflow surface as the source for the candidate overlay.
- Materialize the parent rewrite and extracted building blocks only in the runtime-provided candidate workspace and its allowed paths.
- Write `candidate_decomposition_manifest` as the provider-authored documentary index of that work; after this phase, the runtime independently derives `candidate_manifest` from the workspace.
- Do not publish a receipt or promote the candidate in this step.

## Runtime bindings

- Treat the runtime-injected input, immutable reads, and artifact destinations as authoritative.
- Use only the filesystem paths supplied by the runtime; do not infer or invent artifact paths.

## Output Requirements

### Artifact handling
- Materialize the rewritten parent workflow, at least one extracted lab workflow package, and its documentation and runtime-test footprint inside the runtime-provided candidate workspace and the allowed candidate paths in the runtime input.
- `candidate_decomposition_manifest` must be valid JSON and define:
- `selected_workflow_name`,
- `publication_mode` set to `candidate_only`,
- `promotion_required` set to `true`,
- `building_blocks` with one entry per candidate building block and explicit package, doc, and runtime-test paths,
- every claimed candidate file with its repo-relative path and baseline-change status,
- the parent rewrite and building-block inventory formerly carried by the separate candidate surface, building-block index, build report, and diff summary.
- Treat file counts, hashes, and changed paths in `candidate_decomposition_manifest` as implementation claims. Do not present them as runtime-verified facts.
- `candidate_decomposition_notes` must state what changed, what stayed unchanged in the authoritative repo, and how the candidate overlay should be validated later.
- `candidate_decomposition_notes` must summarize the parent rewrite and each extracted building block.

### Expected outcome
- Leave the workflow with an explicit candidate decomposition overlay that another step can evaluate and publish without guessing package identity, file boundaries, or hidden execution policy.

## Evidence

- Keep every baseline parent workflow file present in the candidate overlay.
- Keep the candidate package candidate-only: no in-place promotion, no hidden mutation of the authoritative selected workflow package, and no undeclared building blocks.
- Make the building-block index explicit enough for later comparison with runtime-derived `candidate_manifest` and `candidate_evaluation`.

## Phase decision criteria

- Mark the phase `blocked` only when a true intent gap or missing hard constraint prevents safe progress.
- Treat question, blocked, and failure guidance as semantic validation criteria.

### Outcome guidance for the verifier
- `candidate_decomposition_built`: the candidate surface, declared building-block index, and build artifacts are explicit enough for evaluation.
- `needs_rework`: the same implementation boundary still holds, but the candidate files or build artifacts need local repair.
- `needs_replan`: implementation exposed a material change to the selected workflow boundary, declared package set, or accepted plan.
- Use `blocked` only for true intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Producing or replacing the runtime-derived `candidate_manifest` or `candidate_evaluation`.
- Publishing the evaluation artifacts or receipt.
- Mutating the authoritative selected workflow package.

## Forbidden

- Do not edit source files outside the runtime-provided allowed candidate paths, and do not write durable artifacts outside their declared destinations.
- Do not create undeclared workflow packages, docs, or tests that are missing from `candidate_decomposition_manifest`.
- Do not hide publication policy or promotion behavior in provider prose only; durable outputs must capture it explicitly.

## Isolated candidate validation

- The candidate is materialized only in the bounded candidate workspace. `candidate_evaluation` comes from frozen execution-tree compilation and the configured argv validation under its timeout.
- Record candidate paths, counts, and hashes as implementation claims for the later deterministic workspace scan; do not describe them as independently validated in this phase.
- Publication may recommend a later promotion review, but this workflow must not copy candidate files into authoritative source or auto-promote them.
