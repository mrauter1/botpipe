# Implement ↔ Code Reviewer Feedback

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: implement
- Phase ID: public-surface-terminal-cut
- Phase Directory Key: public-surface-terminal-cut
- Phase Title: Public Surface And Terminal Cut
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` `runtime/cli.py:_run_summary_payload`, `runtime/cli.py:_run_record_payload`, `runtime/workspace.py:RunRecord.paused`
  The hard cut still exposes public `paused` metadata after renaming the canonical terminal/status surface to `AWAIT_INPUT` / `awaiting_input`. A caller using the CLI JSON surfaces now sees mixed terminology (`status: "awaiting_input"` plus `paused: true`), which contradicts the phase objective to rename pause-oriented externally observed metadata without compatibility exports. Minimal fix: centralize canonical run-state serialization and replace the public `paused` field with an `awaiting_input`-named field or remove the redundant boolean entirely.

- IMP-002 `blocking` `runtime/workspace.py:list_workflow_run_summaries`, `runtime/workspace.py:list_task_operation_summaries`
  Status filtering still compares raw persisted `record.status` values, while the docs and runtime now present `awaiting_input` as the canonical status. Older runs persisted as `status="paused"` therefore disappear from summary/status-filter queries when callers use the new canonical term, which breaks the explicit compatibility decision to keep legacy paused records answerable during the cutover. Minimal fix: centralize one normalized status accessor on `RunRecord` and use it consistently for filters, counts, and emitted summary payloads.

- IMP-003 `blocking` `tests/unit/test_stdlib_and_extensions.py`
  The phase-owned tests were only partially updated: this file still contains many expectations for `"PAUSE"`, `"paused"`, and old pause-route summaries even though the production surface now emits `AWAIT_INPUT` / `awaiting_input`. Once the project test environment is available, the hard-cut coverage will fail and the phase deliverable of updated strictness/authoring-surface tests is not actually met. Minimal fix: sweep the remaining phase-relevant assertions and fixtures in this file (and adjacent touched runtime tests if needed) to the new terminal/status spellings.

- IMP-004 `non-blocking` `docs/authoring.md`
  The touched authoring doc now says `Route.await_input(...)`, but the same sentence still recommends `Route.complete(...)`, which is not part of the live route helper surface. Minimal fix: align that sentence to the actual supported helpers (`Route.to(...)`, `Route.finish(...)`, `Route.await_input(...)`, `Route.fail(...)`).
