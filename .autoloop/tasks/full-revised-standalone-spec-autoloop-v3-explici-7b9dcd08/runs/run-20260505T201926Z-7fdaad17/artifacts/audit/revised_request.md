Fix the remaining repository-wide regression that prevents the run from satisfying the original merge gate.

The branch-group implementation itself is largely aligned with the accepted asyncio-only v1 contract and the focused branch-group suites are green, but the full repository suite is still red. `./.venv/bin/python -m pytest -q` currently fails on:

- `tests/contract/test_canonical_runtime_contracts.py::test_canonical_step_contract_uses_finish_and_required_writes`
- `tests/contract/test_canonical_runtime_contracts.py::test_canonical_produce_verify_contract_splits_phase_writes_and_verifier_routes`

Required follow-up:

1. Restore the canonical provider request `route_required_writes` behavior for ordinary `step(...)` and `produce_verify_step(...)` execution.
2. Keep per-route `required_writes` and `explicit_required_writes` metadata unchanged, but ensure the provider request map exposes effective required writes for every provider-visible route, including inherited required artifacts when a route has no explicit override.
3. Preserve the branch-group behavior already implemented and validated in the focused branch-group suites.
4. Re-run the two failing canonical contract tests, then re-run the full repository suite with `./.venv/bin/python -m pytest -q` and confirm it is green.
