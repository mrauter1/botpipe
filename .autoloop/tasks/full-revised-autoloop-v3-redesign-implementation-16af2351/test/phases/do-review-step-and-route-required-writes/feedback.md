# Test Author ↔ Test Auditor Feedback

- Task ID: full-revised-autoloop-v3-redesign-implementation-16af2351
- Pair: test
- Phase ID: do-review-step-and-route-required-writes
- Phase Directory Key: do-review-step-and-route-required-writes
- Phase Title: Do review step and route required writes
- Scope: phase-local authoritative verifier artifact

- Added contract coverage for runtime `review_session` overrides using separate producer/verifier session slots.
- Added a strict failure-path test showing declared `review_requires` stops execution before verifier invocation when the do artifact is missing.
