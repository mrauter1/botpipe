# Test Strategy

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: test
- Phase ID: compatibility-bridge-removal
- Phase Directory Key: compatibility-bridge-removal
- Phase Title: Remove Compatibility Bridges
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Intentional break: `autoloop_v3.core` import fails
  Covered by `tests/strictness/test_no_compat.py::test_legacy_core_package_import_fails_after_bridge_removal`.
- Maintained Python surface no longer imports `autoloop_v3.core` or `core._compat`
  Covered by `tests/strictness/test_no_compat.py::test_active_python_files_do_not_import_removed_core_compatibility_paths`.
- Maintained Python surface no longer imports deleted non-core `autoloop_v3` namespaces (`runtime`, `extensions`, `stdlib`, `workflows`, `autoloop_optimizer`)
  Covered by `tests/strictness/test_no_compat.py::test_active_python_files_do_not_import_deleted_autoloop_v3_non_core_namespaces`.
- Canonical public API remains the active authoring surface after bridge removal
  Covered by `tests/unit/test_simple_surface.py` export/import/signature assertions.
- Canonical helper packages remain importable after optimizer import-path rewrites
  Covered by module imports and helper-behavior assertions in `tests/unit/test_stdlib_and_extensions.py`.

## Preserved Invariants Checked

- Only strictness coverage intentionally mentions `autoloop_v3.core`.
- Deleted compatibility helpers and payload keys stay absent from maintained source and topology/static-graph outputs.
- `stdlib` authoring helpers do not reintroduce `runtime` or `workflows` import dependencies.

## Edge And Failure Paths

- Failure-path coverage is static and deterministic: forbidden import scans fail on exact import statements rather than raw token mentions.
- Strictness self-file is excluded from the maintained-source scan so the intentional failed-import assertion does not create a false positive.

## Known Gaps

- Dynamic `pytest` execution remains blocked in this shell because project dependencies such as `pytest` and `pydantic` are unavailable.
- No additional runtime-behavior tests were added here because the phase change is import-path and compatibility-surface focused rather than engine-behavior focused.
