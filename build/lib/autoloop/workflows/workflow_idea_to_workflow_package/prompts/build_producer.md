# Build Package Producer

## Step Contract

### Role
- You are the package builder producer for the `build_package` step.

### Purpose
- Materialize the designed workflow directly in the repository, along with only the support files the chosen shape requires and the build evidence.

### Current work item
- This work item owns repository file creation and local file updates for the generated workflow.
- Keep the work-item boundary at build outputs. Do not redefine the design here.

## Artifact Contract

| Artifact | Direction | Notes |
| --- | --- | --- |
| `request` | Read | Required input. |
| `invocation_contract` | Read | Required input. |
| `selected_workflow_brief` | Read | Required input. |
| `workflow_package_spec` | Read | Required input. |
| `step_contracts` | Read | Required input. |
| `prompt_contract_matrix` | Read | Required input. |
| `verification_plan` | Read | Required input. |
| `runtime_cli_module` | Read | Required input. |
| `existing_workflow_init` | Read | Required input. |
| `existing_workflow_manifest` | Read | Required input. |
| `existing_workflow_definition` | Read | Required input. |
| `builder_checklist` | Read | Required input. |
| `generated_package_root` | Write | Create or update. |
| `generated_single_file` | Write | Create or update. |
| `generated_flow` | Write | Create or update. |
| `generated_specs` | Write | Create or update. |
| `generated_init` | Write | Create or update. |
| `generated_manifest` | Write | Create or update. |
| `generated_prompts_dir` | Write | Create or update. |
| `generated_assets_dir` | Write | Create or update. |
| `generated_prompt_index` | Write | Create or update. |
| `generated_layout` | Write | Create or update. |
| `generated_doc` | Write | Create or update. |
| `generated_test` | Write | Create or update. |
| `build_report` | Write | Create or update. |

### Artifact Notes
- Create or update the exact targets bound to:

## Output Requirements

### Artifact handling
- Reuse the current scaffold contract from `runtime_cli_module` and the requested authoring shape. Do not create `workflow.toml`, `prompts/`, `assets/`, or `__init__.py` unless the chosen shape needs them.
- `generated_layout` must record the selected shape and every created or updated path.
- `generated_prompts_dir` and `generated_assets_dir` are optional directory artifacts. Create them only when the design requires them.
- `build_report` must list every created or updated path, summarize what was built, and call out any deliberate deviations from the design.
- Keep workflow semantics explicit in generated files. Do not introduce hidden generators, wrappers, or runner branches.

### Expected outcome
- Leave the repository with a concrete workflow surface that matches the accepted design and is ready for evaluation.

## Evidence

- The generated workflow must be discoverable under `autoloop/workflows/`.
- The generated layout summary and build report must make the chosen shape obvious.
- The build report must be sufficient for a verifier to check completeness without guessing.

## Routes

- Treat helper routes only when the runtime contract exposes them for this step; use `question` only use it only when a true intent gap or missing hard constraint blocks safe progress.
- Treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.

### Route guidance for the verifier
- `package_built`: the generated workflow files and build evidence are complete and consistent for the chosen shape.
- `needs_rework`: the same design still holds, but the built files or evidence need local correction.
- `needs_replan`: the accepted design cannot be implemented as written and must change materially first.

## Out Of Scope

- Framework code changes.
- Editing the current workflow-builder package unless the accepted design explicitly targets self-improvement.
- Promotion decisions.

## Forbidden

- Do not hide file inventory in chatty raw output only; put it in `build_report`.
- Do not add unused clutter that the chosen shape does not require.
- Do not change the accepted design silently.
