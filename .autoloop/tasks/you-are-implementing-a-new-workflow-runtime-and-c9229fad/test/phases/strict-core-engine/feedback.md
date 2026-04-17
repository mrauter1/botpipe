# Test Author ↔ Test Auditor Feedback

- Task ID: you-are-implementing-a-new-workflow-runtime-and-c9229fad
- Pair: test
- Phase ID: strict-core-engine
- Phase Directory Key: strict-core-engine
- Phase Title: Strict Core Engine
- Scope: phase-local authoritative verifier artifact

## Cycle 1

- Added validator or compiler coverage for reserved hook-name precedence so steps named `start`, `outcome`, and `verdict` keep ownership of their matching `on_*` handlers instead of being reinterpreted as lifecycle or middleware hooks.
- Added a definition-time regression test that still rejects both active middleware hooks when no reserved-name collision suppresses one side.
- Updated the phase test strategy with the behavior-to-test map, preserved invariants, failure paths, stabilization notes, and known deferred gaps.
