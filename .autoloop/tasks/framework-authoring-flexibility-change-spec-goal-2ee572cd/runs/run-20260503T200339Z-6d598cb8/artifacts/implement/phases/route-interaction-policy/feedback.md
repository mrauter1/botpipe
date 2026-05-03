# Implement ↔ Code Reviewer Feedback

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: implement
- Phase ID: route-interaction-policy
- Phase Directory Key: route-interaction-policy
- Phase Title: Route Policy Rebase
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` — `tests/contract/test_engine_contracts.py::test_step_requests_include_step_control_contracts` and `::test_pair_requests_include_step_control_contracts` now expect explicit authored `failed` routes declared through `GLOBAL: {"failed": FAIL}` to disappear from provider-visible routes. That contradicts the accepted contract, which removes only default-injected `failed` while preserving explicitly authored `failed` and `blocked` routes. In a future regression where provider-visible explicit `failed` handling breaks, these tests would still pass and mask the failure. Minimal fix: restore expectations so explicitly authored `failed` remains provider-visible in these cases, while keeping only default-injected `failed` removed.
- IMP-002 `non-blocking` — `autoloop/core/compiler.py` now encodes question-visibility policy in both `_compiled_provider_visibility()` and `_compiled_step_route_visible()`. The step-level tuples are the provider-contract source of truth, but the route-level fields can diverge and will require parallel edits on the next inspection/static-graph phase. Minimal fix: centralize route-visibility policy in one helper and derive both the compiled route fields and the compiled step tuples from that single calculation, or defer the redundant route-level policy fields until the later inspection phase that consumes them.
