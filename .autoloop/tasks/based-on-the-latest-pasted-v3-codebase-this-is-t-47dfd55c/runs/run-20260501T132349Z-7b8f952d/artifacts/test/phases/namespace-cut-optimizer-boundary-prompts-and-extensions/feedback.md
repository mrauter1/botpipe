# Test Author ↔ Test Auditor Feedback

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: test
- Phase ID: namespace-cut-optimizer-boundary-prompts-and-extensions
- Phase Directory Key: namespace-cut-optimizer-boundary-prompts-and-extensions
- Phase Title: Namespace Cut Optimizer Boundary Prompts And Extensions
- Scope: phase-local authoritative verifier artifact

- Added focused regressions for the new `autoloop.runtime.inspection` seam and for removed workflow-facing git/tracing exports. The inspection test currently fails on a real phase-local bug: `autoloop.runtime.inspection.load_run_metadata()` passes `validate_persisted_schema` positional arguments incorrectly and raises `TypeError`.
- TST-001 [blocking] `tests/runtime/test_optional_extensions.py`: the new extension-cleanup regression only checks that `autoloop.extensions` stops re-exporting `GitTracking`/`Tracing` names. It does not verify that the deleted module paths `autoloop.extensions.tracing` and `autoloop.extensions.git.declaration` stay non-importable. A compatibility shim or accidental file restore would still satisfy the current test while violating AC-3. Add direct import-failure assertions for those removed module paths.
- TST-002 [non-blocking] `artifacts/test/.../test_strategy.md`: the behavior-to-test map only lists the two newly added tests and omits the existing phase-relevant coverage for the hard namespace cut and prompt-registry widening. Expanding the map to include the strictness and prompt-root regressions would make the phase artifact align better with the full acceptance surface.
