# Test Strategy

- Task ID: framework-authoring-flexibility-change-specifica-7e827c69
- Pair: test
- Phase ID: milestone-b-authoring-ergonomics-and-validation-polish
- Phase Directory Key: milestone-b-authoring-ergonomics-and-validation-polish
- Phase Title: Milestone B Authoring Ergonomics
- Scope: phase-local producer artifact

## Behavior-to-coverage map

- AC-1 worklist effects:
  `tests/unit/test_simple_surface.py`
  Covers `WorklistEffect` helper constructors, no-arg `Effects.refresh()`, and additive `Route.complete_and_advance(...)` lowering.
  `tests/contract/test_engine_contracts.py`
  Covers direct `WorklistEffect` returns from python-step handlers and route `on_taken` hooks, including active-scoped-worklist resolution and persisted status mutation.

- AC-2 validation helper alignment:
  `tests/contract/test_engine_contracts.py`
  Preserves coverage for valid/invalid `ValidationResult`, feedback writing, repair routing, and failed-route exception behavior.

- AC-3 late-bound prompt/runtime diagnostics:
  `tests/contract/test_engine_contracts.py`
  Covers prompt runtime failures for missing payload paths, missing current items, and missing worklist sources with step/worklist-aware error text.
  `tests/unit/test_primitives_and_stores.py`
  Covers artifact-template runtime payload-path failures with worklist-aware diagnostics while preserving artifact-template labeling behavior.

- AC-4 artifact ownership diagnostics:
  `tests/unit/test_validation.py`
  Covers same-identity and distinct-identity workflow-level vs produced-artifact ownership ambiguity failures, with message assertions for workflow attribute, qualified name, and producer names.

## Preserved invariants checked

- Direct `WorklistEffect` returns still flow through the existing effect pipeline and preserve deterministic worklist mutation ordering.
- Prompt runtime diagnostics changed wording only where intended; artifact-template placeholder labels remain artifact-specific.
- Validation helper behavior remains stable while nearby effects/prompt/ownership changes land.

## Edge cases and failure paths

- Direct effect return without an explicit worklist on an active scoped route hook.
- Missing prompt payload subpaths on both `item.*` and `worklist.<name>.current.*` paths.
- Distinct artifact objects sharing a public name across workflow-level and produced ownership.

## Flake-risk controls

- Use local temp directories, in-memory stores, and inline/scripted provider responses only.
- Reuse existing artifact-backed worklist fixtures and deterministic JSON payloads; no network, timing, or external process dependencies.

## Known gaps

- The environment available in this run does not provide `pytest` or `pydantic`, so these tests were authored/updated but not executed here.
