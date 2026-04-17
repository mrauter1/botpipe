# Test Strategy

- Task ID: you-are-a-principal-software-architect-and-imple-5867bc5e
- Pair: test
- Phase ID: runtime-session-store-ownership
- Phase Directory Key: runtime-session-store-ownership
- Phase Title: Move Session Payload Writes Into Runtime Store
- Scope: phase-local producer artifact

## Coverage Map

- AC-1 helper ownership:
  - `test_runtime_store_placeholder_helper_creates_generic_session_payload`
  - `test_runtime_store_write_helper_preserves_sparse_metadata_and_non_codex_thread_id`
  - `test_runtime_store_write_helper_mirrors_codex_session_id_into_thread_id`
  - `test_autoloop_v1_support_delegates_session_payload_writes_to_runtime_store_helpers`
- AC-2 preserved compatibility:
  - `test_filesystem_session_store_uses_generic_paths_and_loads_legacy_thread_id`
  - `test_filesystem_session_store_sparse_writes_preserve_existing_metadata`
  - `test_autoloop_v1_parity_harness_persists_clarifications_and_resumes`
- AC-3 generic path semantics:
  - `test_runtime_store_placeholder_helper_creates_generic_session_payload`
  - `test_filesystem_session_store_supports_custom_path_resolver`

## Preserved Invariants Checked

- Legacy payloads that only contain `thread_id` still hydrate as codex sessions.
- Sparse metadata fields survive restore/upsert and direct helper writes.
- Codex writes mirror `session_id` into `thread_id`; non-codex writes preserve explicit legacy `thread_id`.
- Workflow-owned Autoloop support code delegates session-file persistence to runtime helpers instead of owning JSON writers.

## Edge Cases

- Placeholder creation on an arbitrary path with no existing file.
- Direct helper writes for both codex and non-codex providers.
- Custom path resolver still controls filenames and scope directories.

## Failure Paths / Regression Traps

- Source-level contract test catches reintroduction of workflow-owned `_write_session_payload` or `_ensure_session_placeholder`.
- Resume clarification parity test catches regressions in `sessions/plan.json` pending-note persistence.

## Stabilization Notes

- All tests use `tmp_path` and scripted providers only; no network, timing, or nondeterministic ordering dependencies.

## Known Gaps

- Full-file `test_compatibility_runtime.py` still includes an unrelated `Ralph_loop.py` strict-validation failure outside this phase; the targeted selector avoids normalizing that out-of-scope issue.
