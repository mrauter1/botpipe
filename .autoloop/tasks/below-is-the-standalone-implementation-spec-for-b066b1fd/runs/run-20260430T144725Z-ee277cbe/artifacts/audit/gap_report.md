# Original intent considered

- Immutable request snapshot in `request.md`, covering:
  - canonical public naming around `produce_verify_step`;
  - removal of the `autoloop_v3.core` / `core._compat` bridge surface;
  - built-in persisted step runtime state plus `StateVar` sugar;
  - item state and step-item state for scoped workflows;
  - hook rerouting and redirect chaining;
  - effective required writes;
  - read-only `ctx.history` telemetry.
- Authoritative run log in `raw_phase_log.md`.
- Run decisions in `decisions.txt`.
- Pair artifacts under `artifacts/plan`, `artifacts/implement`, and `artifacts/test`.
- Final codebase and maintained tests.

# Clarifications / superseding decisions

- No later raw-log clarification changed user intent after the request snapshot.
- Recorded implementation decisions that matter to audit classification:
  - `autoloop_v3.core` is intentionally disabled by raising `ModuleNotFoundError` from `autoloop_v3/core/__init__.py` instead of silently bridging.
  - Simple scoped `step(...)` keeps the new `scope=` and `item_state=` authoring surface; this was explicitly carried in the scoped-item-state decisions and tests.
  - Inherited `global_routes[*].effective_required_writes` serialize as `null` when no step context exists, while step-local route projections carry the concrete effective set.
  - Hook rerouting begins only once a candidate `Event` exists; producer-phase `after_producer` hooks remain non-rerouting.

# Implemented behavior

- Public export surface matches the requested top-level API in `autoloop/__init__.py`; forbidden legacy names such as `SUCCESS`, `review_step`, `do_review_step`, `system_step`, `Checkpoint`, `ChildWorkflowResult`, `ResolvedArtifacts`, and `Param` are not re-exported.
- The compatibility bridge is removed from production code:
  - root `__init__.py` no longer bridges;
  - `core/_compat.py` is absent;
  - `autoloop_v3/core/__init__.py` fails intentionally;
  - `rg -n "autoloop_v3\\.core|core\\._compat|bridge_core_package" autoloop core runtime extensions stdlib workflows autoloop_optimizer -S` returned no production matches.
- Scoped state behavior is implemented on the public simple surface:
  - `autoloop/simple.py` exposes `step(..., scope=..., item_state=...)`;
  - `autoloop/simple.py` exposes `produce_verify_step(..., scope=..., state=..., item_state=...)`;
  - `tests/unit/test_simple_surface.py:560-620` covers scoped `step.item_state` validation and built-in scoped step-item state.
- Spec-critical behavior is exercised and green in focused verification:
  - `./.venv/bin/python -m pytest -q tests/strictness/test_no_compat.py::test_legacy_core_package_import_fails_after_bridge_removal tests/strictness/test_no_compat.py::test_autoloop_root_does_not_reexport_removed_simple_surface_aliases tests/runtime/test_runtime_static_graph.py::test_topology_payload_and_route_table_preserve_explicit_vs_effective_required_writes tests/runtime/test_history.py::test_context_history_falls_back_to_events_without_trace tests/contract/test_engine_contracts.py::test_route_redirect_cycle_fails_after_max_hook_redirects tests/unit/test_simple_surface.py::test_simple_scoped_item_state_and_step_item_state_restore_on_resume`
  - result: `6 passed in 0.32s`
- A broader focused suite covering strictness, simple surface, validation, history, tracing, static graph, engine contracts, and canonical runtime contracts produced:
  - `264 passed, 1 deselected` when excluding one obsolete signature assertion;
  - one failure when that assertion is included.

# Unresolved gaps

- Maintained signature coverage is stale and currently fails against the implemented, spec-required scoped-state public surface.
  - Evidence:
    - `tests/unit/test_simple_surface.py:190-227` still asserts that `simple.step` does not accept `scope` / `item_state`, and that `simple.produce_verify_step` does not accept `scope` / `item_state`.
    - `autoloop/simple.py:361-423` exposes both `scope` and `item_state` on `step(...)` and `produce_verify_step(...)`.
    - `tests/unit/test_simple_surface.py:560-620` already relies on the scoped `step(..., item_state=...)` behavior that the failing signature assertion denies.
    - Focused run:
      - `./.venv/bin/python -m pytest -q tests/strictness/test_no_compat.py tests/unit/test_simple_surface.py tests/unit/test_validation.py tests/runtime/test_history.py tests/runtime/test_runtime_tracing.py tests/runtime/test_runtime_static_graph.py tests/contract/test_engine_contracts.py tests/contract/test_canonical_runtime_contracts.py`
      - result: `1 failed, 264 passed`
      - failing test: `tests/unit/test_simple_surface.py::test_canonical_simple_signatures_expose_only_canonical_argument_names`
- This gap is material because it leaves the maintained regression suite red and encodes behavior that conflicts with both the request and the already-landed scoped-item-state implementation.

# Differences justified by later clarification or analysis

- `autoloop_v3.core` was disabled rather than physically removed. This is consistent with the request’s “delete or disable” language and the recorded compatibility-removal decision; the required observable behavior is that `import autoloop_v3.core` fails.
- `StateVar` is exposed on the public simple surface (`autoloop`, `autoloop.simple`) rather than added as a `core` public API. This matches the request’s public API list, which is about the canonical user-facing surface.
- `global_routes[*].effective_required_writes` uses `null` when inheritance depends on step context. This is documented in the effective-required-writes decisions and still preserves accurate step-local effective required-write data.
- Hook rerouting remains unavailable to producer-phase `after_producer` hooks. The decision record constrains rerouting to phases where a candidate route exists, which is consistent with the request’s route-finalization algorithm.

# Recommended next run

- Update `tests/unit/test_simple_surface.py::test_canonical_simple_signatures_expose_only_canonical_argument_names` so the maintained signature expectations match the scoped-state surface that was intentionally added:
  - `step(...)` should include `scope` and `item_state`;
  - `produce_verify_step(...)` should include `scope` and `item_state`;
  - `python_step(...)` should remain unchanged unless its public signature has intentionally changed.
- Re-run the focused suite that currently reports `1 failed, 264 passed` and confirm it becomes fully green without changing the implemented scoped-state authoring behavior.
