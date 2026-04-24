# `workflow_run_history_to_failure_modes` Prompts

- `frame_producer.md`: frames one selected workflow plus filtered run history as an explicit diagnostic problem with a bounded evidence window.
- `frame_verifier.md`: checks that the diagnostic scope and evidence window are explicit enough for failure-mode clustering.
- `analyze_producer.md`: clusters failure modes, writes the machine-readable manifest, and surfaces recurring weak points.
- `analyze_verifier.md`: checks that the failure clusters and weak points are evidence-backed, non-duplicative, and packaging-ready.
- `package_producer.md`: ranks improvement opportunities and writes the terminal diagnostic package plus next-action artifact.
- `package_verifier.md`: confirms the terminal package is aligned, publication-ready, and still stops at diagnostic publication.

## Step To Artifact Map

- `frame_diagnostic_scope` writes `diagnostic_scope_brief` and `run_history_scope`.
- `map_failure_modes` writes `failure_mode_map`, `failure_mode_manifest`, and `recurring_weak_points`.
- `package_improvement_pressure` writes `improvement_opportunities`, `improvement_opportunities_summary`, and `diagnostic_next_actions`.

## Route Grammar

Reserved routes:

- `question`
- `blocked`
- `failed`

Application routes:

- `inputs_prepared`
- `run_history_context_captured`
- `diagnostic_scope_framed`
- `failure_modes_mapped`
- `improvement_pressure_packaged`
- `needs_rework`
- `needs_replan`
- `failure_mode_diagnostics_published`

## Verifier JSON Expectations

- `frame_verifier.md` returns `DiagnosticScopePayload`.
- `analyze_verifier.md` returns `FailureModeMapPayload`.
- `package_verifier.md` returns `ImprovementPressurePayload`.

## Runtime Boundary

Prompt templates carry the provider-facing operational guidance.
The runtime injects only `expected_output_schema`, `available_routes`, and `route_contracts`.
