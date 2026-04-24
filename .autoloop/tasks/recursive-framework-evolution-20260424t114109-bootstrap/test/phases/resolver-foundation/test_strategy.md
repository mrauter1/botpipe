# Test Strategy

- Task ID: recursive-framework-evolution-20260424t114109-bootstrap
- Pair: test
- Phase ID: resolver-foundation
- Phase Directory Key: resolver-foundation
- Phase Title: Resolver Foundation
- Scope: phase-local producer artifact

## Behavior to test coverage

- Unified reference resolution:
  - Covered by `tests/runtime/test_workflow_reference_resolution.py` for named refs, explicit file refs, explicit directory refs, module refs, class selectors, and imported-name/path precedence edge cases.
  - Preserved invariant: all supported references resolve through one loader path without reintroducing legacy execution branches.
- Prompt and source-container scoping:
  - Covered by single-file and `flow.py` package run tests asserting prompt paths and `ctx.package_folder` / `ctx.root` values.
  - Edge case: single-file prompts resolve relative to the file parent; package prompts resolve relative to the package directory without requiring `workflow.toml`.
- Parameter precedence:
  - Covered by class-level, module-level, package-exported, legacy `params.py`, and no-parameters cases.
  - Edge case: explicit package paths must prefer package-exported `Parameters` before legacy `params.py`.
- Ambiguity and failure paths:
  - Covered by file-level multi-workflow ambiguity, named-reference inferred-candidate collisions, and workflow-origin collision checks.
  - Failure expectation: ambiguous refs fail with clear errors before execution or run-history merging.
- Origin metadata and runtime safety:
  - Covered by single-file run metadata assertions and conflicting-origin execution failure assertions.
  - Preserved invariant: equivalent refs to the same origin remain valid, but different origins cannot silently share workflow history.

## Validation approach

- Deterministic temp-directory fixtures only; no network, timers, or nondeterministic ordering.
- Use direct resolver assertions for lookup behavior and small end-to-end runtime executions where metadata, prompt resolution, or collision enforcement must be observed.

## Known gaps

- Shallow catalog discovery payload migration is out of phase scope.
- Deep capability payload migration, scaffold/builder shapes, and docs/template rewrites are intentionally not encoded in this phase test slice.
