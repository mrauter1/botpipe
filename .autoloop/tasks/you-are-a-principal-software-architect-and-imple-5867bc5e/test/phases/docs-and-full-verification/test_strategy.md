# Test Strategy

- Task ID: you-are-a-principal-software-architect-and-imple-5867bc5e
- Pair: test
- Phase ID: docs-and-full-verification
- Phase Directory Key: docs-and-full-verification
- Phase Title: Update Documentation And Prove The Final Shape
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 docs surface: `autoloop_v3/tests/test_architecture_baseline_docs.py`
  - freezes required docs presence
  - freezes strict public surface symbols
  - freezes `workflow.observers`, `autoloop_v3.workflows.autoloop_v1_conventions`, and `autoloop_v3.workflows.autoloop_v1_parity` references
  - freezes no-compatibility-layer and no-workspace-hook wording in the shipped docs corpus
- AC-2 engine/runtime/parity proof surface:
  - `autoloop_v3/tests/contract/test_engine_contracts.py`
  - `autoloop_v3/tests/runtime/test_compatibility_runtime.py`
  - `autoloop_v3/tests/runtime/test_workflow_integration_parity.py`
  - full regression sweep with `pytest -q autoloop_v3/tests`
- AC-3 no wrapper/subclass / no generic hook regressions:
  - doc corpus assertions in `test_architecture_baseline_docs.py`
  - source-level purity assertions in `test_engine_contracts.py`
  - parity-module source assertions in `test_compatibility_runtime.py`

## Preserved invariants checked

- strict public API remains the documented authoring surface
- sessions remain explicit and lookup-only
- execution observation remains one minimal generic seam
- Autoloop-v1 parity remains workflow-owned
- no compatibility layer or generic workspace-hook system is described or reintroduced

## Edge cases / failure paths

- fatal, pause, and fail terminal observer/runtime behavior remains covered by existing contract/runtime suites
- legacy status-reader compatibility and legacy session/log parity remain covered by runtime/parity integration suites

## Flake risk / stabilization

- tests are deterministic: source-text assertions plus scripted providers and local temporary directories only
- no network, timing, or nondeterministic ordering dependencies are introduced in this phase

## Known gaps

- this phase does not add new execution-behavior tests because the existing contract/runtime/parity suites already cover the relevant runtime behavior; the delta here is the tighter documentation baseline
