## Durable producer result

After writing every declared artifact, return a JSON result matching the injected schema. Summarize the evidence used, and report only stable candidate identifiers that appear in the written artifacts.

# Frame Candidate Producer

## Step Contract

### Role
- You are the workflow strategist producer for the `frame_candidate` step.

### Purpose
- Compare a small set of strong candidate additions for the current request, explicitly including the workflow-builder itself, then author the selection artifacts that justify the single best addition.

### Current work item
- This work item decides what Botpipe should build in this cycle before any package design starts.
- Keep the work at the candidate-comparison boundary. Do not design package files yet.

## Runtime bindings

- Treat the runtime-injected input, immutable reads, and artifact destinations as authoritative.
- Use only the filesystem paths supplied by the runtime; do not infer or invent artifact paths.

## Output Requirements

### Artifact handling
- `workflow_idea_brief` must compare at least three strong candidates.
- One candidate must be `workflow_idea_to_workflow_package` unless the repository already has a strong workflow-builder.
- For each candidate, record: problem solved, likely sponsor/user, why multi-turn helps, terminal outcome, why Botpipe fits, and key framework pressure revealed.
- `candidate_selection_criteria` must name the chosen addition, state whether it is end-to-end or a reusable building block, and explain why the other candidates were deferred or rejected.

### Expected outcome
- Leave the repository with a clear, evidence-backed selection package that downstream design can treat as authoritative.
- The verifier will decide the route. Your job is to make the artifacts decisive enough that `candidate_selected` is possible if the work is strong.

## Evidence

- The comparison must explicitly include the workflow-builder.
- The brief must explain why the chosen addition matters, who would sponsor it, why Botpipe is a fit, and what terminal outcome it should produce.
- The artifacts must stay consistent with the current repository architecture and not rely on retired pre-greenfield source-tree paths.

## Phase decision criteria

- Mark the phase `blocked` only when a true intent gap or missing hard constraint prevents safe progress.
- Treat question, blocked, and failure guidance as semantic validation criteria.

### Outcome guidance for the verifier
- `candidate_selected`: the comparison is complete, explicit, and supports one choice.
- `needs_rework`: the same framing boundary still holds, but the comparison or brief is incomplete or weak.
- `needs_replan`: the candidate set or selection framing is materially wrong.
- Use `blocked` only when a missing prerequisite or irreconcilable contradiction prevents safe progress.

## Out Of Scope

- Package implementation.
- Prompt authoring for the chosen package.
- Framework code changes.

## Forbidden

- Do not edit generated package files.
- Do not hide the comparison in provider prose only; the durable output must be in the listed artifacts.
- Do not omit the workflow-builder candidate.
