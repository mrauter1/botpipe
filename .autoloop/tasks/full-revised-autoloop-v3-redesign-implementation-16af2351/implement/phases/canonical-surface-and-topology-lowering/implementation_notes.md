# Implementation Notes

- Task ID: full-revised-autoloop-v3-redesign-implementation-16af2351
- Pair: implement
- Phase ID: canonical-surface-and-topology-lowering
- Phase Directory Key: canonical-surface-and-topology-lowering
- Phase Title: Canonical surface and topology lowering
- Scope: phase-local producer artifact

## Files Changed

- `autoloop/__init__.py`
- `autoloop/simple.py`
- `cleanup.md`
- `core/__init__.py`
- `core/compiler.py`
- `core/engine.py`
- `core/primitives.py`
- `core/prompts.py`
- `core/routes.py`
- `core/validation.py`
- `docs/architecture.md`
- `docs/authoring.md`
- `runtime/__init__.py`
- `runtime/cli.py`
- `runtime/runner.py`
- `runtime/static_graph.py`
- `runtime/tracing.py`
- `tests/runtime/test_runtime_static_graph.py`
- `tests/test_architecture_baseline_docs.py`
- `tests/unit/test_simple_surface.py`

## Symbols Touched

- Public exports: `FINISH`, `SELF`, `python_step`, `do_review_step`, `Prompt.ref`, `writes`
- Simple declarations: `step`, `review_step`, `system_step`, `workflow_step`, `python_step`
- Validation/lowering: prompt placeholder analysis, declaration-order entry/default-route lowering, named target resolution, control-route opt-out
- Runtime artifacts: `workflow_topology_payload`, `write_topology_artifacts`, topology sidecar filenames

## Checklist Mapping

- Phase 1 public surface:
  `FINISH`, `SELF`, `python_step`, `do_review_step`, `Prompt.inline/file/ref`, `writes` landed with compatibility aliases preserved.
- Phase 1 topology lowering:
  step-local `routes`, string/direct/`SELF` targets, explicit entry, and first-declared entry now lower through the existing compiled FSM path.
- Phase 1 prompt contract:
  artifact/value/params placeholder validation plus inferred reads landed for compile-time-available prompt text.
- Phase 1 additive artifacts/docs:
  canonical topology files and canonical authoring docs/templates were added without removing legacy static graph output.

## Assumptions

- Phase 1 should preserve existing engine/provider behavior wherever possible and only canonicalize authoring, compile metadata, and docs.
- Runtime success compatibility still matters for existing consumers, so both `SUCCESS` and `FINISH` must be accepted during execution.

## Preserved Invariants

- Existing compiled FSM and global `transitions` fallback remain intact.
- Legacy `SUCCESS`, `review_step`, `system_step`, `out`, and `outputs` inputs remain accepted.
- Legacy `static_step_graph.json` emission remains present.

## Intended Behavior Changes

- Plain simple steps default to route tag `done` and lower the terminal target to canonical `FINISH`.
- Class namespace declaration order now determines default entry and default next-step lowering for the simple surface.
- Simple prompt placeholders fail early for unknown or ambiguous artifact references when prompt text is available at compile time.
- `Prompt.ref(...)` compile-time placeholder analysis now preserves registry semantics instead of opportunistically reading same-named local prompt files.
- Runtime tracing writes additive canonical topology artifacts beside the legacy static graph payload.

## Known Non-Changes

- No phase-2 split between do/review provider contracts or `review_writes`.
- No `StateVar`, `Param`, hook-context semantics, feedforward `llm()`/`classify()`, or topology-hash resume enforcement yet.
- No removal of legacy route metadata (`RouteInfo`) or global transition compatibility.

## Expected Side Effects

- New runs receive `topology.json`, `topology.mmd`, `route_table.md`, `artifact_contracts.json`, `prompt_refs.json`, `state_contracts.json`, `session_contracts.json`, and `compile_report.md`.
- Public workflow scaffolds and docs now steer new code toward the canonical surface instead of legacy `chain` plus `system_step`.
- Registry-backed prompt declarations no longer pick up compile-time inferred reads from colliding workflow-local files unless prompt text is explicitly available on the prompt object.

## Validation Performed

- `python3 -m py_compile autoloop/simple.py core/validation.py core/routes.py core/compiler.py core/engine.py runtime/static_graph.py runtime/tracing.py runtime/runner.py runtime/cli.py`
- `./.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py tests/runtime/test_runtime_static_graph.py tests/test_architecture_baseline_docs.py`
- `./.venv/bin/python -m pytest -q tests/runtime/test_package_cli.py`
- `python3 -m py_compile core/validation.py`
- `./.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py tests/runtime/test_runtime_static_graph.py tests/test_architecture_baseline_docs.py tests/runtime/test_package_cli.py`

## Deduplication / Centralization

- Route-target normalization was kept on the existing validation/compiler path instead of adding a parallel phase-1 compiler.
- Canonical topology artifact generation was added alongside the existing static graph writer so runtime entrypoints share one persistence path.
