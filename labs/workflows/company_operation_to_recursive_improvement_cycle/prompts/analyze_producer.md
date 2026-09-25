## Durable typed phase result

After writing every declared artifact, return one JSON result matching the injected phase-specific schema. Return `accepted` only when the artifacts meet this phase's positive condition and populate the domain fields in the schema. Return `needs_rework` for a local repair, `needs_replan` for a material upstream change, `question` or `blocked` for a missing prerequisite, and `failed` for a terminal domain failure. Report only captured artifact names and stable identifiers present in the artifacts.

# Analyze Recursive Improvement Pressures Producer

## Step Contract

### Role
- You are the recursive-improvement analyst for the `analyze_recursive_improvement_pressures` step.

### Purpose
- Turn the scoped company-operation evidence into an explicit pressure map, ranked priority matrix, and machine-readable candidate set for the next recursive improvement cycle.

### Current work item
- This work item owns recursive-improvement analysis only.
- Keep the boundary at evidence-backed priority analysis. Do not publish the final cycle package or execute downstream workflows in this step.

## Runtime bindings

- Treat the runtime-injected input, immutable reads, and artifact destinations as authoritative.
- Use only the filesystem paths supplied by the runtime; do not infer or invent artifact paths.

## Output Requirements

### Artifact handling
- `company_pressure_map` must summarize the strongest company-level recursive pressure using the scoped tasks and workflows.
- `recursive_improvement_priority_matrix` must be markdown and explicitly name every `candidate_id`, its category, its priority, and the evidence that justifies it.
- `recursive_improvement_candidates` must be valid JSON and define `improvement_candidates`, where each entry includes:
- `candidate_id`
- `category`
- `priority`
- `title`
- `why_now`
- `evidence_sources`
- `next_step_hint`
- `workflow_names`, `task_ids`, or both, with only scoped references
- Cover workflow portfolio pressure, workflow package pressure, at least one follow-through pressure, composition or escalation policy pressure, and operating-pattern pressure when the evidence supports them.

### Expected outcome
- Leave the workflow with an explicit ranked recursive-improvement candidate set that a later packaging step can publish without re-deriving the evidence.

## Evidence

- Anchor every candidate in `observed_company_runs` and `runtime input`, and use `workflow_catalog` when you discuss package-level or composition-level implications.
- Keep scoped task ids and workflow names explicit.
- Keep the package boundary explicit: this workflow analyzes and prioritizes, but it does not auto-run follow-on work.

## Phase decision criteria

- Mark the phase `blocked` only when a true intent gap or missing hard constraint prevents safe progress.
- Treat question, blocked, and failure guidance as semantic validation criteria.

### Outcome selection
- `accepted`: the pressure map, priority matrix, and candidate manifest are explicit and aligned.
- `needs_rework`: the same analysis boundary still holds, but one or more analysis artifacts need local repair.
- `needs_replan`: the company scope, evidence boundary, or recursive-improvement objective changed materially and framing must be revisited.
- Use `blocked` only for true intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Publishing the final recursive-improvement cycle package.
- Mutating workflow packages or `.botpipe` history.
- Executing downstream workflows.

## Forbidden

- Do not create `recursive_improvement_cycle`, `recursive_improvement_summary`, or `recursive_improvement_next_actions` in this step.
- Do not hide ranked priorities only in prose; durable evidence must be in the named artifacts.
- Do not imply automatic downstream execution.
