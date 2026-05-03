# Test Author ↔ Test Auditor Feedback

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: test
- Phase ID: lazy-worklists-and-sessions
- Phase Directory Key: lazy-worklists-and-sessions
- Phase Title: Lazy Worklists And Sessions
- Scope: phase-local authoritative verifier artifact

- Added unit coverage for explicit lazy selection and lazy artifact-template placeholder resolution so non-dispatch first-use paths are exercised alongside the existing contract tests for scoped execution, sparse resume, and work-item continuity.
- Added engine-level explicit-access coverage with `runtime_event_sink` so AC-2 now asserts `worklist_selection_resolved` on non-scoped first use, not only on the scoped-dispatch path.

- `TST-001` `blocking`: AC-2 requires first scoped or explicit worklist use to emit a runtime resolution event, but only the scoped-dispatch path asserts `worklist_selection_resolved` today (`tests/contract/test_engine_contracts.py::test_artifact_backed_worklist_materializes_after_runtime_creates_source`). The explicit-use additions in `tests/unit/test_primitives_and_stores.py` use a manual resolver outside the engine and therefore cannot catch a regression where `ctx.selection(...)`, `ctx.current(...)`, or lazy artifact-template rendering still materialize correctly but stop emitting the engine runtime event on non-scoped first use. Add an engine-level regression test that performs explicit worklist access from a non-scoped step under `runtime_event_sink` and asserts both one-worklist-only materialization and `worklist_selection_resolved` emission.
