# Design Package Producer

## Step Contract

### Role
- You are the workflow author producer for the `design_package` step.

### Purpose
- Turn the selected workflow brief into an explicit Autoloop workflow design with a visible topology, route grammar, artifact contract, target authoring shape, prompt plan, and verification plan.

### Current work item
- This work item owns workflow design only.
- Keep the work-item boundary at design artifacts. Do not author repository workflow files yet.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `candidate_comparison` | Read | Required input. |
| `selected_workflow_brief` | Read | Required input. |
| `framework_architecture_doc` | Read | Required input. |
| `framework_authoring_doc` | Read | Required input. |
| `workflow_instructions` | Read | Required input. |
| `core_steps_module` | Read | Required input. |
| `core_validation_module` | Read | Required input. |
| `core_compiler_module` | Read | Required input. |
| `core_engine_module` | Read | Required input. |
| `runtime_cli_module` | Read | Required input. |
| `builder_checklist` | Read | Required input. |
| `workflow_package_spec` | Write | Overwrite. |
| `step_contracts` | Write | Overwrite. |
| `prompt_contract_matrix` | Write | Overwrite. |
| `verification_plan` | Write | Overwrite. |

### Artifact Notes
- Use the exact filesystem paths bound to these artifact names in the runtime request:
- Do not create workflow code, docs, or tests in this step.

## Output Requirements

### Artifact handling
- `workflow_package_spec` must define:
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
- `step_contracts` must be machine-readable and list each step’s legal application routes plus required evidence.
- `prompt_contract_matrix` must name only the prompt files the generated workflow should contain and what each one must do.
- `verification_plan` must name the validation commands, compile checks, and evidence artifacts required before promotion.

### Expected outcome
- Produce a design package that is specific enough for the build step to create files directly without inventing hidden runtime behavior.

## Evidence

- Keep the runtime/provider boundary crisp: the runtime injects the compact human-readable step contract, while prompt templates own the operational guidance and raw provider output never re-enters prompts.
- Reuse the existing scaffold contract from `runtime_cli_module`; do not invent a hidden generator layer.
- Make rework vs replan rules explicit and tied to role, artifact, and acceptance boundaries.

## Routes

- Treat `question` as the only default runtime control route; use it only when a true intent gap or missing hard constraint blocks safe progress.
- If this workflow authors `blocked` or `failed`, treat them as ordinary application routes rather than framework defaults.

### Route guidance for the verifier
- `design_accepted`: the design is implementation-ready.
- `needs_rework`: the same design boundary holds, but the spec or prompt matrix needs local correction.
- `needs_replan`: the chosen addition or authoring boundary changed materially.
- Treat `question` as the only default runtime control route; use it only for genuine missing intent, blocked prerequisites, or unrecoverable contradictions.

## Out Of Scope

- Writing repository workflow files.
- Running tests.
- Editing core/runtime framework code.

## Forbidden

- Do not move provider-facing SOP into runtime-only structures.
- Do not rely on undeclared artifact paths.
- Do not hide route semantics in prose-only commentary.
