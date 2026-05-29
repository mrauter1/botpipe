Independently verify the Botpipe recreation design.

Inspect:
- The request and invocation contract.
- `source_manifest.json`.
- `behavior_inventory.json`.
- `behavior_inventory.md`.
- `trace_pattern_notes.md`.
- `behavior_review.md`.
- `workflow_design.md`.
- `step_contracts.json`.
- `prompt_contract_matrix.md`.
- `equivalence_plan.md`.
- `coverage_map.json`.
- Botpipe workflow authoring skill at `skills/botpipe-workflow-autoring.md`.
- Botpipe authoring examples, when available.
- Prior `design_review.md`, if present.

Accept with `design_accepted` only if:
- The design uses valid Botpipe workflow concepts and public authoring APIs.
- The design follows the Botpipe workflow authoring skill's guidance for provider-heavy steps, session boundaries, artifact handoffs, routes, and validation.
- `workflow_design.md` includes an explicit session topology and rationale, including which steps share context, which steps use independent context, and what artifacts supply each independent session.
- The generated workflow target is `.botpipe/workflows/<generated_workflow_name>/`.
- Every behavior id appears in `coverage_map.json`.
- Required behaviors are mapped to generated steps, artifacts, routes, prompts, tests, or explicit unsupported gaps.
- Unsupported gaps have concrete reasons and do not hide missing core behavior.

Use `needs_rework` for local design defects.
Use `needs_replan` if the behavior inventory itself is materially incomplete or wrong.

Always write `design_review.md` with the decision and exact required rework.
