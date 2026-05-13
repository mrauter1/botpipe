# Frame Candidate Producer

## Step Contract

### Role
- You are the workflow strategist producer for the `frame_candidate` step.

### Purpose
- Compare a small set of strong candidate additions for the current request, explicitly including the workflow-builder itself, then author the selection artifacts that justify the single best addition.

### Current work item
- This work item decides what Botpipe should build in this cycle before any package design starts.
- Keep the work at the candidate-comparison boundary. Do not design package files yet.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | authoritative run request snapshot. |
| `invocation_contract` | Read | authoritative workflow parameters and requested target package identity. |
| `framework_architecture_doc` | Read | , `framework_authoring_doc`, `workflow_authoring_guidelines`: current framework doctrine and authoring rules. |
| `existing_workflow_manifest` | Read | , `existing_workflow_definition`, `existing_workflow_prompts`: current package conventions from `botpipe_v1`. |
| `candidate_comparison` | Write | Overwrite. |
| `selected_workflow_brief` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- Inspect the current installed workflow package inventory in the repository if you need broader context, but treat the listed artifacts as the minimum required read set.
- Do not create package files, tests, docs, or prompt files in this step.

## Output Requirements

### Artifact handling
- `candidate_comparison` must compare at least three strong candidates.
- One candidate must be `workflow_idea_to_workflow_package` unless the repository already has a strong workflow-builder.
- For each candidate, record: problem solved, likely sponsor/user, why multi-turn helps, terminal outcome, why Botpipe fits, and key framework pressure revealed.
- `selected_workflow_brief` must name the chosen addition, state whether it is end-to-end or a reusable building block, and explain why the other candidates were deferred or rejected.

### Expected outcome
- Leave the repository with a clear, evidence-backed selection package that downstream design can treat as authoritative.
- The verifier will decide the route. Your job is to make the artifacts decisive enough that `candidate_selected` is possible if the work is strong.

## Evidence

- The comparison must explicitly include the workflow-builder.
- The brief must explain why the chosen addition matters, who would sponsor it, why Botpipe is a fit, and what terminal outcome it should produce.
- The artifacts must stay consistent with the current repository architecture and not rely on retired pre-greenfield source-tree paths.

## Routes

- Treat helper routes only when the runtime contract exposes them for this step; use `question` only use it only when a true intent gap or missing hard constraint blocks safe progress.
- Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

### Route guidance for the verifier
- `candidate_selected`: the comparison is complete, explicit, and supports one choice.
- `needs_rework`: the same framing boundary still holds, but the comparison or brief is incomplete or weak.
- `needs_replan`: the candidate set or selection framing is materially wrong.
- Treat helper routes only when the runtime contract exposes them for this step; use `question` only use it only for true intent gaps, missing prerequisites, or unrecoverable contradictions.

## Out Of Scope

- Package implementation.
- Prompt authoring for the chosen package.
- Framework code changes.

## Forbidden

- Do not edit generated package files.
- Do not hide the comparison in provider prose only; the durable output must be in the listed artifacts.
- Do not omit the workflow-builder candidate.
