# Implementation Notes

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: implement
- Phase ID: metadata-tracing-schema-and-attribution
- Phase Directory Key: metadata-tracing-schema-and-attribution
- Phase Title: Metadata Tracing Schema And Attribution
- Scope: phase-local producer artifact

## Files changed
- `core/schema_registry.py`
- `core/history.py`
- `core/operations.py`
- `core/engine.py`
- `runtime/events.py`
- `runtime/static_graph.py`
- `runtime/stores/filesystem.py`
- `runtime/workspace.py`
- `runtime/runner.py`
- `tests/runtime/test_runtime_tracing.py`
- `tests/runtime/test_history.py`
- `tests/runtime/test_workspace_and_context.py`
- `tests/runtime/test_security_finding_to_verified_remediation.py`
- `tests/runtime/test_compatibility_runtime.py`

## Symbols touched
- `validate_persisted_schema`
- runtime schema constants for run metadata, checkpoint, events, child summaries, replay, and topology-side JSON artifacts
- `HistoryReader._record_step_finished`
- `HistoryReader._read_jsonl`
- `HistoryReader._read_json_object`
- `StepFinalizationRecord`
- `RunResult.last_transition`
- `update_run_metadata`
- `_child_run_record_payload_from_parts`
- `_pending_input_metadata`
- `_last_transition_payload`
- `FilesystemCheckpointStore.save/load`
- `EventLogger.emit`
- `_load_replay_store` / `_write_replay_store`

## Checklist mapping
- Phase 3 metadata/tracing: added run-metadata `finalization` payloads, child-summary `finalization`, and richer history route records.
- Phase 3 awaiting-input attribution: preserved terminal/status `awaiting_input` separately from provider `question` in run metadata and child summaries.
- Phase 3 schema registry: added owned schema ids for run metadata, checkpoint, runtime events, child summaries, operation replay, and topology-side JSON artifacts; readers accept schema-less legacy payloads and reject explicit unknown schemas.

## Assumptions
- Schema-less persisted payloads are the only legacy format that must remain readable in this phase.
- Child-run summaries are the relevant persisted “history summary” surface for this phase’s attribution work.

## Preserved invariants
- Missing legacy `schema` fields do not block reads.
- Pending input remains sourced from `pending_input`, not resurrected `pending_question`.
- Direct runtime controls still bypass route finalization and required-write validation; this phase only changes persisted metadata and derived history status.

## Intended behavior changes
- `run.json` now carries a top-level schema id and a `finalization` section for the last completed step transition.
- `checkpoint.json`, `events.jsonl`, `children.jsonl`, `operation_replay.json`, and the topology-side JSON artifacts are schema-stamped.
- History route records now surface `runtime_control`, `target_step`, `terminal`, `provider_attributable`, `source_hook`, and `source_phase`, and direct-control step finishes map to truthful statuses.

## Known non-changes
- No package-namespace relocation or optimizer import cleanup in this phase.
- No replay mismatch warn/fail behavior change in this phase beyond schema ownership for replay payloads.
- No provider-contract rendering changes in this phase.

## Expected side effects
- Readers now fail clearly when a persisted runtime artifact declares an explicit unsupported schema id.
- Parent workflows and workspace summaries can inspect last-step finalization metadata without inferring it from provider route tags.

## Validation performed
- `python3 -m compileall core runtime tests/runtime/test_runtime_tracing.py tests/runtime/test_history.py tests/runtime/test_workspace_and_context.py tests/runtime/test_security_finding_to_verified_remediation.py tests/runtime/test_compatibility_runtime.py`

## Validation gaps
- `pytest` was not available in the environment (`python3 -m pytest` failed with `No module named pytest`), so targeted runtime tests were not executed.

## Deduplication / centralization
- Centralized persisted-schema validation in `core/schema_registry.validate_persisted_schema`.
- Reused a single `finalization` payload shape across run metadata and child-run summaries instead of introducing separate attribution structures.
