# Test Author ↔ Test Auditor Feedback

- Task ID: recursive-framework-evolution-20260424t114109-bootstrap
- Pair: test
- Phase ID: resolver-foundation
- Phase Directory Key: resolver-foundation
- Phase Title: Resolver Foundation
- Scope: phase-local authoritative verifier artifact

- Added resolver regression coverage in `tests/runtime/test_workflow_reference_resolution.py` for named-reference ambiguity when inferred candidates conflict (`workflows/<name>/flow.py` plus `workflows/<name>.py`).
- Updated `test_strategy.md` with the behavior-to-test map covering unified resolution, prompt scoping, parameter precedence, ambiguity/failure paths, origin metadata, and explicit known gaps for out-of-phase work.
