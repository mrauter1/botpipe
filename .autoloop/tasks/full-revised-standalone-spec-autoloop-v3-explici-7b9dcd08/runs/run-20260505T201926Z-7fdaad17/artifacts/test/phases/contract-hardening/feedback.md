# Test Author ↔ Test Auditor Feedback

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: test
- Phase ID: contract-hardening
- Phase Directory Key: contract-hardening
- Phase Title: Contract Hardening
- Scope: phase-local authoritative verifier artifact

- Added compile-time regression coverage for operation-based fan-in rejection across both operation authoring helpers: `simple.llm.step` and `simple.classify.step`.
- Updated the phase test strategy with an explicit behavior-to-coverage map for declaration/compiled spec split, validation failures, composite route exposure, and compile-cache bypass.
