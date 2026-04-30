# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: consumer-migration-and-package-cleanup
- Phase Directory Key: consumer-migration-and-package-cleanup
- Phase Title: Consumer Migration
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking`:
  AC-1 is still unmet because active consumer tests still author or assert banned public names outside any explicit migration-only fixture boundary. Representative examples remain in [tests/runtime/test_workflow_reference_resolution.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_workflow_reference_resolution.py:48), [tests/runtime/test_workflow_reference_resolution.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_workflow_reference_resolution.py:229), [tests/runtime/test_security_finding_to_verified_remediation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_security_finding_to_verified_remediation.py:765), [tests/unit/test_stdlib_and_extensions.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_stdlib_and_extensions.py:139), and [tests/unit/test_stdlib_and_extensions.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_stdlib_and_extensions.py:5199). These still use or generate `SUCCESS`, `SystemStep`, `RouteInfo`, `required_outputs`, `route_infos`, and class-level `transitions`, which directly contradicts the phase objective to migrate active docs/tests/workflow packages to the canonical contract. Minimal fix: finish migrating these active tests to `FINISH`, `python_step`, `Route`, `required_writes`, and step-local `routes`, or move true legacy-compat coverage into explicit migration fixtures that are clearly outside the active canonical consumer surface.
