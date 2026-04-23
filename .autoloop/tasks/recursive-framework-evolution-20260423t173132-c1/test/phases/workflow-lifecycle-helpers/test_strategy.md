# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c1
- Pair: test
- Phase ID: workflow-lifecycle-helpers
- Phase Directory Key: workflow-lifecycle-helpers
- Phase Title: Add Workflow Lifecycle Helpers
- Scope: phase-local producer artifact

## Behavior To Test Coverage Map

- Shared helper happy paths:
  - `open_workflow_sessions(...)` opens declared sessions on a runtime-backed context.
  - `write_workflow_json(...)` writes deterministic sorted JSON under `workflow_folder`.
  - `write_invocation_contract(...)` writes the canonical workflow/task/run/request snapshot fields.
  - `write_publication_receipt(...)` writes workflow-local receipt JSON without changing receipt payload semantics.
- Preserved workflow invariants:
  - Builder package still compiles, discovers, runs, and emits the same invocation-contract and publish-receipt artifacts.
  - Release package still compiles, discovers, runs, and emits the same invocation-contract and decision-receipt artifacts.
  - Runtime/provider boundary remains unchanged; targeted package tests remain the regression gate.
- Edge cases:
  - Invocation-contract helper keeps ctx-owned identity fields authoritative even if payload keys collide.
  - Workflow-local JSON writes support nested relative paths under `workflow_folder`.
- Failure paths:
  - Workflow-local JSON helper rejects path escape attempts such as `../escape.json`.
  - Receipt/helper JSON writes reject non-`.json` targets.
- Flake controls:
  - Use temp directories, in-memory session store, and scripted fake providers only.
  - No timing, network, or external service dependencies.
- Known gaps:
  - No broader suite rerun; this phase stays on the helper-focused unit tests plus builder/release targeted regressions.
