# Test Author ↔ Test Auditor Feedback

- Task ID: task-implement-the-refactor-suggestions-below-to-c2f5dbe1
- Pair: test
- Phase ID: runtime-and-discovery-extraction
- Phase Directory Key: runtime-and-discovery-extraction
- Phase Title: Runtime And Discovery Extraction
- Scope: phase-local authoritative verifier artifact

- Added focused phase-local parity coverage in `tests/unit/test_runtime_and_discovery_extraction.py` for `AWAIT_INPUT` resume-failure context, `FAIL` checkpoint persistence, `FINISH` no-checkpoint behavior, and discovery duplicate-step validation; the focused file now passes with `6 passed`.

- TST-001 `blocking` — [tests/unit/test_runtime_and_discovery_extraction.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_runtime_and_discovery_extraction.py:1), [test_strategy.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/task-implement-the-refactor-suggestions-below-to-c2f5dbe1/runs/run-20260509T124548Z-f67cf8d4/artifacts/test/phases/runtime-and-discovery-extraction/test_strategy.md:10): AC-2 explicitly requires preserved lowered-simple-step behavior, but the updated phase-local tests and strategy never exercise `_lower_discovered_simple_steps()` through any simple-step declaration path. The discovery coverage only hits explicit `PythonStep` ordering, `global_session`, and duplicate-name rejection. Concrete missed-regression scenario: the extraction could stop lowering `simple.python_step(...)` declarations into compiled steps, reorder lowered steps, or break lowered entry/transition wiring, and all added tests would still pass. Minimal correction: add one discovery regression test that defines a workflow using the repository’s simple-step declaration path and asserts the lowered step names/order/entry or route wiring, or explicitly map and rerun an existing simple-surface test that exercises `describe_workflow_class()` through that lowering path.

- Added direct simple-step lowering coverage via `simple.Workflow` and `simple.python_step(...)` declarations, asserting lowered step order, default entry, and resolved transition wiring through `describe_workflow_class()`; the focused file now passes with `7 passed`.

- TST-002 `non-blocking` — Re-audit of the updated phase found no remaining blocking coverage gaps. `TST-001` is resolved by the direct `simple.Workflow` lowering test, and the focused validation target now completes with `.venv/bin/python -m py_compile tests/unit/test_runtime_and_discovery_extraction.py && .venv/bin/python -m pytest tests/unit/test_runtime_and_discovery_extraction.py -q` → `7 passed`.
