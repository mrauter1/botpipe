# Test Strategy

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: test
- Phase ID: metadata-tracing-schema-and-attribution
- Phase Directory Key: metadata-tracing-schema-and-attribution
- Phase Title: Metadata Tracing Schema And Attribution
- Scope: phase-local producer artifact

## Behaviors Covered
- AC-1 trace/history finalization metadata:
  - `tests/runtime/test_history.py`
  - Covers route records carrying `candidate_route`, `final_route`, `runtime_control`, `target_step`, `terminal`, `provider_attributable`, `source_hook`, `source_phase`, and redirect-chain payloads.
- AC-1 direct runtime-control status derivation:
  - `tests/runtime/test_history.py`
  - Covers `RequestInput` terminal-derived `awaiting_input` and `Goto` terminal-less `completed` status.
- AC-2 awaiting-input vs provider question separation:
  - `tests/runtime/test_workspace_and_context.py`
  - Covers child-run summaries and run metadata preserving `status == "awaiting_input"` separately from `last_event.tag == "question"`.
- AC-3 runtime-owned schema stamping:
  - `tests/runtime/test_runtime_tracing.py`
  - Covers `run.json` and `static_step_graph.json` schema ids.
  - `tests/runtime/test_compatibility_runtime.py`
  - Covers `checkpoint.json` schema stamping and explicit unsupported checkpoint schema failure.
- AC-3 older-schema reader behavior:
  - `tests/unit/test_optimization_helpers.py`
  - Covers schema-less legacy runtime observability payloads loading successfully and explicit unsupported runtime schemas failing on optimizer ingestion.
  - `tests/runtime/test_history.py`
  - Covers schema-less legacy trace records loading successfully and explicit unsupported trace schemas failing at the history-reader boundary.

## Preserved Invariants Checked
- Schema-less persisted runtime payloads remain readable where the phase declared legacy compatibility.
- Explicit unknown schema ids fail loudly instead of being silently reinterpreted.
- Direct runtime controls do not require a finalized route to produce truthful step telemetry.

## Edge Cases
- Mixed runtime observability bundle with only the schema field removed from legacy payloads.
- Direct `Goto` finalization with no `final_route` and no terminal.
- History-reader trace consumption with unsupported schema ids.

## Failure Paths
- Optimizer bundle load records a load error for explicit unsupported runtime schemas.
- HistoryReader raises `ValueError` on explicit unsupported trace schemas.
- Filesystem checkpoint load raises on explicit unsupported checkpoint schemas.

## Flake Risks / Stabilization
- No timing, network, or subprocess ordering dependencies were added.
- New coverage uses temporary directories and inline JSON payloads only.

## Known Gaps
- `pytest` is unavailable in the current environment, so the targeted pytest selection could not be executed here.
- This phase does not add separate explicit unknown-schema tests for every runtime reader surface because checkpoint, optimizer ingestion, and history-reader trace coverage already exercise the shared cutover rule on representative owned readers.
