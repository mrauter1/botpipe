# Test Strategy

- Task ID: standalone-remaining-delta-implementation-spec-g-e919a184
- Pair: test
- Phase ID: compiler-resume-schema-docs
- Phase Directory Key: compiler-resume-schema-docs
- Phase Title: Compiler Resume Schema And Docs
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Explicit compiler/resume contract coverage:
  - `tests/runtime/test_workspace_and_context.py::test_compile_workflow_recompiles_when_source_changes`
  - `tests/runtime/test_workspace_and_context.py::test_resume_warns_and_continues_when_saved_topology_hash_differs`
  - `tests/runtime/test_workspace_and_context.py::test_resume_topology_mismatch_can_fail_in_strict_mode`
  - `tests/runtime/test_workspace_and_context.py::test_resume_rejects_unsupported_embedded_topology_schema_when_topology_file_is_missing`
  - `tests/runtime/test_workspace_and_context.py::test_runtime_inspection_loaders_migrate_schema_less_run_metadata_and_topology`
- Extension failure policy coverage:
  - `tests/runtime/test_runtime_tracing.py` record-and-continue tracing behavior
  - `tests/runtime/test_runtime_git_tracking.py` record-and-continue git tracking behavior
  - `tests/runtime/test_provider_backends.py` runtime config defaults and merge behavior
  - `tests/runtime/test_optional_extensions.py` fatal tracing propagate behavior
- Public docs/boundary coverage:
  - `tests/test_architecture_baseline_docs.py` updated to assert `autoloop` as the public authoring surface and forbid `autoloop.simple` / `system step` in maintained docs and `cleanup.md`
  - `tests/runtime/test_workflow_package_to_composable_building_blocks.py` fixture text updated to emit `python_step` vocabulary instead of `system step`

## Preserved Invariants Checked

- Resume still continues by default when continuation is executable and the saved topology only mismatches by source/topology hash.
- Strict resume mode still hard-fails on mismatch.
- Legacy schema-less persisted payloads continue to load only through explicit migration-aware readers.
- Unsupported embedded topology schemas fail instead of silently bypassing validation.
- Runtime config policy names stay `propagate` / `record_and_continue`.

## Edge Cases

- Resume fallback after deleting `topology.json` and relying on legacy schema-less embedded `run.json["topology"]`.
- Resume fallback when embedded topology schema is explicitly unsupported.
- Public docs regression scan across both `docs/` and the top-level working-tree note.

## Failure Paths

- `tests/test_architecture_baseline_docs.py` now fails on `cleanup.md` because it still documents `autoloop.simple`; this is an intentional regression-catching expectation aligned with the phase request.
- Unsupported embedded topology schema path raises a validation error during resume instead of warning/continuing.

## Flake Risks And Stabilization

- Runtime resume tests use temp directories, local workflow packages, and deterministic fake-provider turns only.
- Docs tests use static file reads and exact-string assertions; no timing or ordering dependencies.

## Known Gaps

- This phase adds no new optimizer-facing tests beyond the existing import/boundary scans already exercised elsewhere.
- `cleanup.md` remains an outstanding implementation gap rather than a test gap; the updated baseline docs test now makes that visible.
