# Test Author ↔ Test Auditor Feedback

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: test
- Phase ID: enforce-repo-compatibility-gate
- Phase Directory Key: enforce-repo-compatibility-gate
- Phase Title: Enforce Repo Compatibility Gate
- Scope: phase-local authoritative verifier artifact

- Added a parity regression in `tests/runtime/test_workflow_integration_parity.py` for legacy `pending_question` checkpoints by directly invoking the autoloop-v1 parity extension hook, alongside the existing canonical-session-path and normalized `pending_input.question` resume assertions.
- Revalidated the fast gate with `./.venv/bin/pytest tests/unit/test_simple_surface.py tests/runtime/test_workflow_integration_parity.py -q` (`62 passed`).
- `TST-000` `non-blocking`: No audit findings. The new direct-hook legacy-checkpoint regression matches the recorded phase decision, avoids normalizing the engine’s intentionally unsupported legacy resume path, and keeps the repo-level compatibility gate stable under reviewer-run validation.
