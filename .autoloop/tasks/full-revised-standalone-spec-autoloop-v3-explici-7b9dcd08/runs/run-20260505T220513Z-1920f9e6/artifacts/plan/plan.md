# Plan

## Objective
Restore provider-visible `route_required_writes` for ordinary `step(...)` turns and verifier turns of `produce_verify_step(...)` so provider requests expose runtime-effective required artifacts per visible route, while preserving the existing explicit route metadata surface and the accepted branch-group behavior.

## Root Cause
- `ProviderContractBuilder.route_required_writes()` currently serializes `compiled_route.required_writes`, which is the explicit/authored route metadata surface.
- For inherited routes with no explicit override, compiled route metadata intentionally stays empty while the runtime-effective required-write obligation is derived from required artifacts on the step.
- Canonical contract tests expect provider request `route_required_writes` to expose the effective obligation map, so the provider contract builder has drifted from the existing explicit-vs-effective model already used by validation and topology payloads.

## Implementation Milestone
### M1. Restore effective provider route maps without widening scope
- Update the shared provider-contract builder in `autoloop/core/engine_collaborators.py` so `route_required_writes` is computed from the runtime-effective route obligation for each provider-visible route on ordinary step requests and verifier requests.
- Reuse the shared helper in `autoloop/core/route_required_writes.py` instead of duplicating fallback logic.
- Keep producer requests unchanged: `available_routes == ()`, `routes == {}`, and `route_required_writes == {}`.
- Keep `ProviderRoute.required_writes` and `ProviderRoute.explicit_required_writes` unchanged so authored metadata, explicit empty overrides, and downstream topology/static-graph views do not change.
- Avoid changes to compiled route normalization, static-graph serialization, branch-group runtime control flow, or artifact/session semantics.

## Interface And Compatibility Notes
- Provider request `route_required_writes[route]` must expose effective required writes for every provider-visible route, including inherited required artifacts for default/global routes with no explicit override.
- `routes[route].required_writes` remains the authored/compiled route metadata surface and may stay empty when the route inherits step-level required artifacts.
- `routes[route].explicit_required_writes` remains `None` for inherited routes and `()` for explicit empty overrides.
- Branch-group execution remains on the existing shared step/verifier provider path; this fix may affect nested provider-backed branch requests only by restoring the same canonical effective route map expected for non-branch execution.
- No migration or public API change is intended; this is a contract-restoration change.

## Validation Plan
1. Re-run the two failing canonical tests in `tests/contract/test_canonical_runtime_contracts.py`.
2. Re-run metadata-focused regressions that pin explicit-vs-effective semantics:
   - `tests/unit/test_validation.py::test_compilation_keeps_public_empty_required_writes_but_marks_explicit_empty_overrides_privately`
   - `tests/runtime/test_runtime_static_graph.py::test_topology_payload_and_route_table_preserve_explicit_vs_effective_required_writes`
3. Re-run focused branch-group coverage on the shared provider path with `tests/contract/test_branch_group_runtime.py`.
4. Re-run the full repository suite with `./.venv/bin/python -m pytest -q`.

## Regression Risks And Controls
- Risk: Changing the provider map builder could accidentally change authored route metadata instead of only the effective request map.
  Control: Limit edits to provider-contract assembly and keep `routes(...)` generation untouched.
- Risk: Explicit empty overrides could be lost and incorrectly inherit required artifacts.
  Control: Use the existing effective-route helper, which already distinguishes inherited routes from explicit empty overrides.
- Risk: Branch-group provider-backed branches could regress because they reuse the same request builder.
  Control: Keep branch-group code untouched and validate with the focused branch-group runtime suite before the full-suite run.
- Risk: Producer/verifier split behavior could regress by leaking producer writes into producer requests or changing verifier writable surfaces.
  Control: Leave producer contract generation unchanged and re-run the canonical produce/verify contract test before the full suite.

## Rollback
- Revert only the provider-contract builder change if the restored effective map exposes an unexpected downstream dependency.
- Do not roll back compiled route metadata, topology payload logic, or branch-group code as part of this fix unless a separate regression is proven there.
