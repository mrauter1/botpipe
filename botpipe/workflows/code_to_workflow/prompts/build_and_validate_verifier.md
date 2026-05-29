Independently verify the generated workflow.

Inspect:
- Generated files under `.botpipe/workflows/<generated_workflow_name>/`.
- `source_manifest.json`.
- `trace_corpus.json`.
- `behavior_inventory.json`.
- `behavior_inventory.md`.
- `trace_pattern_notes.md`.
- `behavior_review.md`.
- `design_review.md`.
- `generated_layout.json`.
- `validation_report.md`.
- `coverage_map.json`.
- Botpipe workflow authoring skill at `skills/botpipe-workflow-autoring.md`.
- The accepted design artifacts.
- Prior `build_review.md`, if present.

Accept with `build_validated` only if:
- `flow.py` and `workflow.toml` exist in the generated workflow directory.
- The generated workflow shape matches the accepted design.
- The implementation follows the Botpipe workflow authoring skill's guidance for provider-heavy work, session boundaries, artifact handoffs, routes, public authoring APIs, and validation.
- The generated workflow implements the accepted session topology deliberately: shared sessions are used for dependent continuation where designed, and independent sessions have enough artifact/prompt context to work without hidden history.
- Validation evidence is real, specific, and sufficient for the requested scope.
- Botpipe can discover and compile the generated workflow from the target workspace. If an environment cannot run the CLI, inspect the generated authoring code for the same failure classes, including missing package-relative imports, unresolved artifact references, and simple helper artifacts used as shared workflow-level inputs.
- No required behavior is left unhandled in the coverage map.
- Any unsupported behavior is explicitly justified.

Use `needs_rework` for local generated-file or validation-report defects.
Use `needs_replan` if the accepted design cannot produce a coherent workflow.

Always write `build_review.md` with the decision and exact required rework.
