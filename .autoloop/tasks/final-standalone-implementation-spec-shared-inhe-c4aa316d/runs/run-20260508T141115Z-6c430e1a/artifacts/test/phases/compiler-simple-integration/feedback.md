# Test Author ↔ Test Auditor Feedback

- Task ID: final-standalone-implementation-spec-shared-inhe-c4aa316d
- Pair: test
- Phase ID: compiler-simple-integration
- Phase Directory Key: compiler-simple-integration
- Phase Title: Compiler And Simple Integration
- Scope: phase-local authoritative verifier artifact

## 2026-05-08 Test Update

- Added regression coverage for public `Policy` topology-hash participation at both workflow and step layers.
- Added runtime coverage proving inline `simple.llm(..., policy=Policy(...))` and `simple.classify(..., policy=Policy(...))` accept the shared public policy facade.
- Added export-matrix coverage for `PolicyInput`; this currently fails because `from autoloop.simple import PolicyInput` still succeeds, which violates the phase contract that `PolicyInput` be public only from `autoloop.policy` and `autoloop.sdk`.
