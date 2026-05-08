# Test Author ↔ Test Auditor Feedback

- Task ID: below-is-the-revised-standalone-correction-spec-a9877342
- Pair: test
- Phase ID: public-surface-cleanup
- Phase Directory Key: public-surface-cleanup
- Phase Title: Public Surface Cleanup
- Scope: phase-local authoritative verifier artifact

- Added/updated regression coverage in `tests/unit/test_sdk_facade.py`, `tests/unit/test_simple_surface.py`, and `tests/unit/test_simple_policy.py` for cleaned public policy wording, removed SDK keyword rejection on both run/step entry points, public export guarantees, and direct `client.step(..., input=..., params=...)` coverage for both mapping and BaseModel params while keeping SDK helper writes sequence-based.

Audit note: no new findings. The added tests cover the changed public wording, the preserved export surface, removed keyword failures, and both synthetic-step params branches without introducing flake-sensitive setup.
