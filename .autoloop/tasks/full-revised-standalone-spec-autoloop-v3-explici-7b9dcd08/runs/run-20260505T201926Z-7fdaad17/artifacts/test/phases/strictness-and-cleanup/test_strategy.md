# Test Strategy

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: test
- Phase ID: strictness-and-cleanup
- Phase Directory Key: strictness-and-cleanup
- Phase Title: Strictness and Cleanup
- Scope: phase-local producer artifact

## Behavior-to-test map

- AC-1 strictness guard for forbidden async/thread primitives:
  - `tests/strictness/test_no_compat.py::test_branch_group_subsystem_does_not_reintroduce_forbidden_thread_backed_primitives`
  - `tests/strictness/test_no_compat.py::test_forbidden_branch_group_primitive_scanner_catches_import_and_alias_forms`
  - Covers dotted references plus imported and aliased forms for `concurrent.futures`, `concurrent.futures.wait`, `ThreadPoolExecutor`, `Future`, `FIRST_COMPLETED`, `threading.RLock`, and `asyncio.to_thread`.

- AC-2 required branch-group runtime failure-path coverage:
  - `tests/contract/test_branch_group_runtime.py::test_parallel_branch_group_captures_fail_runtime_control_as_failed`
  - `tests/contract/test_branch_group_runtime.py::test_branch_group_results_manifest_write_failure_stops_before_fan_in_and_downstream_routing`
  - `tests/contract/test_branch_group_runtime.py::test_branch_group_context_write_failure_stops_before_fan_in_and_downstream_routing`
  - Preserves the branch `Fail` capture contract and distinguishes first-write vs second-write evidence failure before fan-in.

- AC-2 preserved compile/runtime matrix already exercised in focused suite:
  - `tests/unit/test_simple_surface.py`
  - `tests/unit/test_branch_group_context_sessions.py`
  - `tests/contract/test_async_step_dispatcher.py`
  - `tests/runtime/test_runtime_tracing.py`
  - `tests/runtime/test_runtime_static_graph.py`
  - `tests/unit/test_validation.py`

## Preserved invariants checked

- No sync-provider fallback or fake-async/thread-backed execution is normalized by the strictness path.
- Branch-group evidence failure still aborts before fan-in routing.
- The broader branch-group compile/runtime/tracing/static-graph surface remains green after the strictness and failure-path additions.

## Edge cases and failure paths

- Imported forbidden primitives without dotted usage.
- Aliased module access such as `th.RLock` and `aio.to_thread`.
- `results.json` failure before any evidence is written.
- `context.md` failure after `results.json` is successfully written.

## Flake risk and stabilization

- No timing-sensitive additions in this turn.
- The scanner helper test uses temp files and `monkeypatch` instead of mutating the maintained tree.
- Evidence-write failure tests patch exact `Path.write_text` targets to avoid nondeterministic broad failures.

## Known gaps

- No new gaps identified in phase-local scope after the focused suite run.

## Validation run

- `./.venv/bin/python -m pytest -q tests/strictness/test_no_compat.py`
- `./.venv/bin/python -m pytest -q tests/strictness/test_no_compat.py tests/unit/test_simple_surface.py tests/unit/test_branch_group_context_sessions.py tests/contract/test_async_step_dispatcher.py tests/contract/test_branch_group_runtime.py tests/runtime/test_runtime_tracing.py tests/runtime/test_runtime_static_graph.py tests/unit/test_validation.py`
