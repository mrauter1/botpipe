# Implementation Notes

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: engine-provider-persistence
- Phase Directory Key: engine-provider-persistence
- Phase Title: Runtime Contract Cleanup
- Scope: phase-local producer artifact

## Files changed

- Runtime/provider/persistence: `core/primitives.py`, `core/sessions.py`, `core/stores/protocols.py`, `core/compiler.py`, `core/engine.py`, `core/operations.py`, `core/providers/models.py`, `core/providers/rendered.py`, `core/providers/rendering.py`, `core/providers/fake.py`, `core/providers/turns.py`, `runtime/runner.py`, `runtime/static_graph.py`, `runtime/tracing.py`, `runtime/git_tracking.py`, `runtime/stores/filesystem.py`
- Schema registry / payload writers: `core/schema_registry.py`, `autoloop_optimizer/optimization.py`
- Compatibility adapter: `core/workflow_capabilities.py`
- Regression tests: `tests/unit/test_provider_boundary_core.py`, `tests/runtime/test_runtime_static_graph.py`, `tests/runtime/test_runtime_tracing.py`, `tests/runtime/test_runtime_git_tracking.py`

## Symbols touched

- `normalize_terminal`, `canonical_session_slot_name`
- `ProviderRoute`, `ProviderTurnContext`, `ProducerRequest`, `VerifierRequest`
- `workflow_topology_payload`, `RuntimeTraceWriter`, `RuntimeGitTracker`
- `normalize_session_snapshot`, filesystem session binding readers
- `TRACE_SCHEMA`, `STATIC_GRAPH_SCHEMA`, `TOPOLOGY_SCHEMA`, optimizer schema constants

## Checklist mapping

- Milestone 3: canonicalized runtime/provider payload fields, topology artifacts, git-tracking payload schema sources, and persisted terminal/session normalization paths.
- Milestone 5: added focused provider/runtime regression coverage and exercised legacy resume/session normalization via compatibility tests.

## Intended behavior changes

- Runtime results, git-tracking payloads, topology artifacts, and trace terminal events now use `FINISH`, not `SUCCESS`.
- Provider turn contracts now use canonical field names and emit `turn_kind="step"` for single-turn harness steps.
- Static topology payload now emits `entry` and `terminals` as canonical fields.
- Persisted legacy `"SUCCESS"` terminals and `"default"` session-slot names are normalized on read for resume/session hydration.

## Preserved invariants

- Legacy normalization remains reader-side only for persisted run/session payloads.
- Existing workflow-capability inspection consumers keep their legacy-shaped DTOs via `core.workflow_capabilities`; canonical runtime/provider payload cleanup did not force the optimizer/CLI inspection migration in this phase.
- Runtime git-tracking behavior remains runtime-config owned.

## Known non-changes

- `runtime/cli.py` and other out-of-phase inspection/consumer surfaces were not migrated to canonical payload keys beyond what was required to keep existing capability adapters working.
- Public/simple-surface cleanup, compiler normalization, and workflow/optimizer consumer migration beyond the active phase scope were not expanded here.

## Validation performed

- `.venv/bin/python -m pytest tests/unit/test_provider_boundary_core.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_runtime_tracing.py tests/runtime/test_runtime_git_tracking.py tests/runtime/test_compatibility_runtime.py -q`
- Result: `87 passed`

## Assumptions and centralization

- `core/schema_registry.py` is the single source for runtime/static-graph/git-tracking/optimizer schema ids introduced in this phase.
- Capability inspection remains a deliberate legacy adapter on top of canonical compiled metadata until the later consumer-migration phase.
