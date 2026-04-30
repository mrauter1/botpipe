# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: strictness-and-suite-migration
- Phase Directory Key: strictness-and-suite-migration
- Phase Title: Migrate Active Suites And Tighten Strictness
- Scope: phase-local authoritative verifier artifact

## Findings

Previous-cycle findings `IMP-001` and `IMP-002` are resolved in this review.

- IMP-003 `blocking` — [core/compiler.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/compiler.py:96), [core/validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/validation.py:1617), and [core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/engine.py:1402) now expose `CompiledRoute.required_writes=None` for routes without an explicit route-level contract. That changes the compiled/public route shape and currently breaks the named active validation suite: rerunning `pytest tests/strictness/test_no_compat.py tests/unit/test_simple_surface.py tests/unit/test_validation.py -q` fails in [tests/unit/test_validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_validation.py:730), [tests/unit/test_validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_validation.py:795), [tests/unit/test_validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_validation.py:984), and [tests/unit/test_validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_validation.py:1215). This is an unintended regression in the maintained compiled-route surface, and it also makes the implementation notes’ recorded `112 passed` result stale. Minimal fix: keep `CompiledRoute.required_writes` stable as tuples on the public compiled route object, and move the explicit-empty override sentinel behind a private/internal field consumed only by runtime enforcement, centralized in compiler/engine rather than propagating `None` through active route metadata.
