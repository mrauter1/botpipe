# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t173132-c9
- Pair: implement
- Phase ID: diagnostic-run-history-seam
- Phase Directory Key: diagnostic-run-history-seam
- Phase Title: Diagnostic Run-History Seam
- Scope: phase-local producer artifact

## Files changed

- `runtime/workspace.py`
- `stdlib/diagnostics.py`
- `stdlib/__init__.py`
- `docs/authoring.md`
- `tests/unit/test_stdlib_and_extensions.py`

## Symbols touched

- `runtime.workspace.RunRecord`
- `runtime.workspace.list_run_records(...)`
- `autoloop_v3.stdlib.write_selected_workflow_run_history_snapshot(...)`
- `stdlib.__all__`

## Checklist mapping

- Plan milestone 1: complete in this phase.
- Plan milestones 2-3: intentionally deferred; out of active phase scope.

## Assumptions

- The active phase contract is authoritative; only the diagnostic seam, docs, export, and unit proof ship here.
- Empty filtered histories remain valid at the helper layer; later workflow publication logic decides whether an empty history is acceptable.

## Preserved invariants

- Writes stay under `ctx.workflow_folder` only.
- No `.autoloop` run state or selected workflow files are mutated.
- No CLI, `workflow.toml`, provider, session, or runtime-injected control-contract changes were introduced.
- Selected-workflow resolution and run discovery still reuse shared framework seams.

## Intended behavior changes

- Read-only `RunRecord` instances now expose authoritative `run_meta_file`, `request_file`, `children_file`, and `parent_file` paths.
- Workflow code can now publish `selected_workflow_run_history.json` with normalized run metadata, request text, parsed events, parsed child-run records, parsed parent metadata when present, and deterministic status/`max_runs` filtering.

## Known non-changes

- No runtime-owned diagnostics automation, failure-mode clustering, severity policy, or downstream routing was added.
- No new `workflow.toml` semantics or CLI flags were added.

## Expected side effects

- Diagnostic workflows can consume one selected workflow's historical run evidence without ad hoc `.autoloop` scraping.

## Validation performed

- `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py`
- `.venv/bin/pytest -q tests/runtime/test_workspace_and_context.py`

## Deduplication / centralization

- The new helper reuses `resolve_workflow_reference(...)` and `list_run_records(...)` instead of adding a parallel workflow lookup or run-discovery path.
