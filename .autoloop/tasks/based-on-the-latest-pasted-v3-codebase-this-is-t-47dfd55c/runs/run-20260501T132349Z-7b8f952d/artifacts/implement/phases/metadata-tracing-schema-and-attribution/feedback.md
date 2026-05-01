# Implement ↔ Code Reviewer Feedback

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: implement
- Phase ID: metadata-tracing-schema-and-attribution
- Phase Directory Key: metadata-tracing-schema-and-attribution
- Phase Title: Metadata Tracing Schema And Attribution
- Scope: phase-local authoritative verifier artifact

- IMP-001 (`blocking`): `autoloop_optimizer/optimization.py:189-195` and `autoloop_optimizer/optimization.py:1078-1094` still ingest `run.json`, `trace.jsonl`, `git_tracking.jsonl`, and `static_step_graph.json` without validating their owned schema ids. A run folder with an explicit unsupported schema like `autoloop.run_metadata/v2` or `autoloop.workflow_static_step_graph/v2` is currently treated as a valid observability bundle instead of failing with the clear migration error required by AC-3 and the turn decision to reject explicit unknown schemas. Minimal fix: centralize runtime-artifact schema validation in the optimizer readers, using `validate_persisted_schema` (or an equivalent file-to-expected-schema dispatch) for each persisted runtime surface, and add coverage for legacy schema-less payloads versus explicit unsupported schema ids.
- IMP-002 (`blocking`): `core/history.py:766-778` classifies a finished direct `Goto` control as `status == "running"`. After a step returns `Goto(...)`, `ctx.history.step_telemetry(step)["status"]` never reflects that the step instance finished, which misreports diagnostics and any downstream analysis that consumes step telemetry. Minimal fix: make `_status_from_step_finished()` treat successful direct `goto` finalization as a finished status (or introduce a dedicated finished-runtime-control status that downstream consumers understand) and add a history test covering `Goto`.
