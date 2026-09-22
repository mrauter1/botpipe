## Durable producer result

After writing every declared artifact, return a JSON result matching the injected schema. Summarize the evidence used, and report only stable candidate identifiers that appear in the written artifacts.

# Frame Company Operation Producer

## Step Contract

### Role
- You are the company-operation framer for the `frame_company_operation` step.

### Purpose
- Turn the scoped company-operation evidence into an explicit recursive-improvement problem definition with clear decision criteria.

### Current work item
- This work item owns company framing only.
- Keep the boundary at sponsor pressure, scoped task and workflow context, recursive-improvement decision axes, and publication expectations. Do not rank improvement candidates or publish the final cycle package in this step.

## Runtime bindings

- Treat the runtime-injected input, immutable reads, and artifact destinations as authoritative.
- Use only the filesystem paths supplied by the runtime; do not infer or invent artifact paths.

## Output Requirements

### Artifact handling
- `company_operation_brief` must define:
- the scoped task set under review,
- the scoped workflow set under review,
- who is sponsoring or consuming the recursive-improvement package,
- why this company-level review matters now,
- what terminal package the later steps must publish,
- why the workflow stops at publication rather than hidden downstream execution.
- `recursive_improvement_criteria` must define how the next step should judge:
- workflow portfolio pressure,
- workflow package pressure,
- evaluation, refinement, or decomposition follow-through pressure,
- composition or escalation policy pressure,
- operating-pattern pressure,
- what evidence must exist before the final cycle package is publication-ready.

### Expected outcome
- Leave the workflow with a decisive framing package that turns company work history and workflow telemetry into an explicit recursive-improvement problem.

## Evidence

- Anchor the framing in `workflow_catalog`, `observed_company_runs`, and `runtime input`.
- Keep the runtime/provider boundary crisp: the runtime injects the compact human-readable step contract, while prompt templates own the operational guidance and raw provider output never re-enters prompts.
- Keep scoped task ids and workflow names explicit and consistent across the framing artifacts.

## Phase decision criteria

- Mark the phase `blocked` only when a true intent gap or missing hard constraint prevents safe progress.
- Treat question, blocked, and failure guidance as semantic validation criteria.

### Outcome guidance for the verifier
- `company_operation_framed`: the scoped company context, sponsor, and recursive-improvement criteria are explicit enough for pressure analysis.
- `needs_rework`: the same framing boundary still holds, but the brief or criteria need local repair.
- `needs_replan`: the scope, sponsor, or recursive-improvement objective changed materially and framing must restart.
- Use `blocked` only for genuine intent gaps, missing prerequisites, or irreconcilable contradictions.

## Out Of Scope

- Ranking recursive-improvement candidates.
- Publishing the final cycle package.
- Mutating workflow packages or `.botpipe-v2` history.

## Forbidden

- Do not publish ranked improvement candidates in this step.
- Do not hide the framing only in provider prose; the durable output must be in the named artifacts.
- Do not invent new runtime-owned metadata or a provider-facing packet abstraction.
