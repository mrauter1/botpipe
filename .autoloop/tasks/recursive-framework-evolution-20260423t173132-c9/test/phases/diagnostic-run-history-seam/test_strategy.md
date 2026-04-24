# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c9
- Pair: test
- Phase ID: diagnostic-run-history-seam
- Phase Directory Key: diagnostic-run-history-seam
- Phase Title: Diagnostic Run-History Seam
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Shared resolution + read-only discovery seam:
  Covered by `test_diagnostics_helper_snapshots_selected_workflow_run_history_via_shared_resolution_and_run_discovery`.
  Verifies alias resolution, `list_run_records(...)` reuse, deterministic status filtering, ordered run selection, normalized run metadata, parsed request/events/children/parent payloads, and workflow-local output shape.

- Read-only boundary / preserved invariants:
  Covered by the same diagnostics snapshot test plus the authoring-doc boundary test.
  Verifies selected workflow files and existing run artifacts remain unchanged, the helper writes only under `ctx.workflow_folder`, and docs freeze the no-runtime-owned-diagnostics policy.

- Edge case: empty filtered histories remain valid at the helper layer:
  Covered by `test_diagnostics_helper_accepts_main_workflow_class_references_and_allows_empty_filtered_histories`.
  Verifies main workflow class references are accepted and that unmatched status filters produce an explicit empty snapshot instead of helper-level rejection.

- Failure paths:
  Covered by diagnostics helper assertions for path escape, non-`.json` output paths, invalid `max_runs`, and invalid/blank `statuses`.

## Preserved invariants checked

- No CLI or `workflow.toml` semantics are encoded in tests.
- The helper remains a workflow-local snapshot seam, not a failure-mode policy engine.
- Ordering is stabilized through explicit `created_at` / `updated_at` timestamps in fixtures.

## Known gaps

- Malformed historical `events.jsonl`, `children.jsonl`, or `parent.json` inputs are not newly frozen here because the phase contract did not require a public corruption-handling policy for legacy run artifacts.
