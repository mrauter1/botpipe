# Test Strategy

- Task ID: you-are-implementing-a-new-workflow-runtime-and-c9229fad
- Pair: test
- Phase ID: docs-hardening-and-final-proof
- Phase Directory Key: docs-hardening-and-final-proof
- Phase Title: Docs Hardening And Final Proof
- Scope: phase-local producer artifact

## Behavior-To-Test Coverage Map

- Docs reflect the shipped runtime boundary, not plan-era module names.
  - Covered by `autoloop_v3/tests/test_architecture_baseline_docs.py::test_docs_match_shipped_runtime_module_layout_and_boundaries`
  - Preserved invariants checked: required docs still exist; stale `runtime.logging` or `runtime.providers` references do not reappear.
- Generic CLI smoke path executes `autoloop_v1.py` end-to-end.
  - Covered by `autoloop_v3/tests/runtime/test_compatibility_runtime.py::test_cli_module_smoke_executes_autoloop_v1_end_to_end`
  - Happy path checked: request snapshot, phase artifacts, plan session file, and success event log.
- Generic CLI smoke path executes `Ralph_loop.py` end-to-end.
  - Covered by `autoloop_v3/tests/runtime/test_compatibility_runtime.py::test_cli_module_smoke_executes_ralph_loop_end_to_end`
  - Happy path checked: `action_log.md`, `main_session.json`, and success event log.
- Existing runtime parity and compatibility remain intact after the new smoke additions.
  - Covered by `autoloop_v3/tests/runtime/test_workflow_integration_parity.py`
  - Covered by `autoloop_v3/tests/runtime/test_compatibility_runtime.py`

## Edge Cases

- Smoke tests isolate `XDG_CONFIG_HOME` and `PYTHONPATH` to avoid user-local config or import pollution.
- Temporary provider modules keep provider behavior deterministic and network-free.

## Failure Paths

- Existing coverage retained for config errors, unsupported compatibility flags, and legacy resume without `checkpoint.json` in `test_compatibility_runtime.py`.

## Known Gaps

- The CLI smoke proof covers the happy path for both target workflows, not every legacy runner mode.
- Remaining warnings are legacy Pydantic deprecations from `Ralph_loop.py`; they are observed but not normalized into new expectations.
