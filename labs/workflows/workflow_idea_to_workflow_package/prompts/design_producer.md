## Durable typed phase result

After writing every declared artifact, return one JSON result matching the injected phase-specific schema. Return `accepted` only when the artifacts meet this phase's positive condition and populate the domain fields in the schema. Return `needs_rework` for a local repair, `needs_replan` for a material upstream change, `question` or `blocked` for a missing prerequisite, and `failed` for a terminal domain failure. Report only captured artifact names and stable identifiers present in the artifacts.

# Design Package Producer

## Step Contract

### Role
- You are the workflow author producer for the `design_package` step.

### Purpose
- Turn the selected workflow brief into an explicit Botpipe workflow design with a visible topology, route grammar, artifact contract, target authoring shape, prompt plan, and verification plan.

### Current work item
- This work item owns workflow design only.
- Keep the work-item boundary at design artifacts. Do not author repository workflow files yet.

## Runtime bindings

- Treat the runtime-injected input, immutable reads, and artifact destinations as authoritative.
- Use only the filesystem paths supplied by the runtime; do not infer or invent artifact paths.

## Output Requirements

### Artifact handling
- `workflow_design` must define:
- objective,
- selected authoring shape (`single`, `flow_specs`, or `package`),
- deterministic workflow responsibilities,
- provider-owned cognitive responsibilities,
- work-item boundary doctrine,
- role topology,
- control flow,
- route grammar,
- artifact contract,
- runtime-injected control contract,
- verification and evidence contract,
- rework / replan / block / fail policy,
- recursive self-improvement policy.
- `workflow_contract` must be machine-readable and list each step’s legal application routes plus required evidence.
- `workflow_contract` must name only the prompt files the generated workflow should contain and what each one must do.
- `workflow_design` must name the validation commands, compile checks, and evidence artifacts required before promotion.

### Expected outcome
- Produce a design package that is specific enough for the build step to create files directly without inventing hidden runtime behavior.

## Evidence

- Keep the runtime/provider boundary crisp: the runtime injects the compact human-readable step contract, while prompt templates own the operational guidance and raw provider output never re-enters prompts.
- Follow current repository workflow patterns; do not invent a hidden generator layer.
- Make rework vs replan rules explicit and tied to role, artifact, and acceptance boundaries.

## Phase decision criteria

- Mark the phase `blocked` only when a true intent gap or missing hard constraint prevents safe progress.
- Treat question, blocked, and failure guidance as semantic validation criteria.

### Outcome selection
- `accepted`: the design is implementation-ready.
- `needs_rework`: the same design boundary holds, but the spec or prompt matrix needs local correction.
- `needs_replan`: the chosen addition or authoring boundary changed materially.
- Use `blocked` only when a missing prerequisite or irreconcilable contradiction prevents safe progress.

## Out Of Scope

- Writing repository workflow files.
- Running tests.
- Editing core/runtime framework code.

## Forbidden

- Do not move provider-facing SOP into runtime-only structures.
- Do not rely on undeclared artifact paths.
- Do not hide route semantics in prose-only commentary.
