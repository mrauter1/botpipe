# Implement ↔ Code Reviewer Feedback

- Task ID: this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0
- Pair: implement
- Phase ID: route-contract-enforcement
- Phase Directory Key: route-contract-enforcement
- Phase Title: Fail-Closed Route Contracts
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` [tests/contract/test_engine_contracts.py] The new AC-3 scripted/rendered runtime regression cases were added to an untracked file (`git status --short -- tests/contract/test_engine_contracts.py` reports `??`), so the required regression coverage is not part of the tracked repository state and can disappear from any normal patch/commit handoff even though it passes locally. Minimal fix: move the raw-route runtime regressions into a tracked test module or ensure this file is added to version control before closing the phase.
- IMP-002 `non-blocking` [autoloop/core/routes.py::Route.to, Route.question, Route.blocked, Route.failed] `_handwritten_route_fields_validation_equivalent` is a compiler bookkeeping flag now exposed through the public route authoring constructor surface. That leaks an internal enforcement detail into user-facing API shape and will be harder to unwind later. Minimal fix: infer the helper-default marker inside a private helper or a non-init/internal field instead of threading an underscore parameter through the public constructor.
- Cycle 2 review: no new findings. `IMP-001` is resolved because `tests/contract/test_engine_contracts.py` is now tracked (`git ls-files --stage` shows the path), and `IMP-002` is resolved because the helper marker is back to non-init internal state with preservation centralized through `autoloop/core/routes.py::_replace_route(...)`.
