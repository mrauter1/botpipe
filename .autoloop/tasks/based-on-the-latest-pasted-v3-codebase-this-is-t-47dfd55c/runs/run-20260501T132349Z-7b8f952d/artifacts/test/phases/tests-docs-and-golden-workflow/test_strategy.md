# Test Strategy

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: test
- Phase ID: tests-docs-and-golden-workflow
- Phase Directory Key: tests-docs-and-golden-workflow
- Phase Title: Tests Docs And Golden Workflow
- Scope: phase-local producer artifact

## Coverage map

- Runtime controls and hidden routes:
  `tests/contract/test_engine_contracts.py`, `tests/runtime/test_golden_workflow.py`, `tests/runtime/test_history.py`
  Covers `RequestInput`, `Goto`, `Fail`, hidden `provider_visible=False` routes, `on_taken` chaining, runtime-control trace/history payloads, and resume behavior.
- State preservation and resumed values:
  `tests/contract/test_engine_contracts.py`, `tests/runtime/test_golden_workflow.py`
  Covers checkpointed pending input, preserved state/session mutations on failure paths, and restored `ctx.values` data after resume into later Python steps.
- History and run-record normalization:
  `tests/runtime/test_history.py`, `tests/runtime/test_workspace_and_context.py`
  Covers direct-control status derivation for `awaiting_input`, `completed`, and `failed`, plus legacy `pending_question` read-compatibility through `pending_input`.
- Namespace cut, docs, and public surface:
  `tests/strictness/test_no_compat.py`, `tests/unit/test_simple_surface.py`, `tests/test_architecture_baseline_docs.py`
  Covers removed aliases/imports, final public exports, and canonical docs/examples restricted to the shipped surface.
- Topology, prompt registry, optimizer boundary, replay mismatch:
  `tests/runtime/test_runtime_static_graph.py`, `tests/runtime/test_workflow_reference_resolution.py`, `tests/unit/test_optimization_helpers.py`, `tests/contract/test_engine_contracts.py`, `tests/contract/test_canonical_runtime_contracts.py`
  Covers early static artifact generation, hidden-route rendering, prompt resolution, stable inspection/query paths, and replay warn/fail behavior.

## Preserved invariants checked

- Direct runtime controls do not masquerade as finalized routes in history metadata.
- Legacy paused/pending-question persisted data remains readable through the new `awaiting_input` and `pending_input` public surfaces.
- Golden workflow examples stay on `autoloop` public imports and demonstrate the shipped runtime-control semantics end to end.

## Edge cases and failure paths

- Invalid pending-input resumes, invalid goto targets, raw-string non-route hook returns, redirect loops, and direct fail controls are covered in contract/runtime suites.
- Direct `Fail` telemetry status is pinned separately to prevent regressions that collapse finished direct controls back to `running`.

## Stability notes

- All additions are filesystem-local and provider-scripted; no network, time-sensitive ordering, or nondeterministic assertions were added.
