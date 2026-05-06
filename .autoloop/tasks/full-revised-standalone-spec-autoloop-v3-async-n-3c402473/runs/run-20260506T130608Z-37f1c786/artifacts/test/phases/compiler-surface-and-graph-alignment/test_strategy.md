# Test Strategy

- Task ID: full-revised-standalone-spec-autoloop-v3-async-n-3c402473
- Pair: test
- Phase ID: compiler-surface-and-graph-alignment
- Phase Directory Key: compiler-surface-and-graph-alignment
- Phase Title: Compiler, surface, and graph alignment
- Scope: phase-local producer artifact

## Behaviors covered
- Public authoring surface stability for `parallel(...)`, `fan_out(...)`, and `FanIn` exports/signatures.
- Branch-group compile-time validation for fresh-session enforcement, supported step kinds, unsafe names, non-serializable fan-out inputs, fan-in-only helper placement, and exact branch / `fan_in` placeholder-root matching.
- Branch-group compile-cache bypass invariants for v1.
- Owner-step-rooted artifact template resolution for branch and fan-in placeholders.
- Additive deterministic static-graph/topology payloads, including fan-out inputs and topology-hash sensitivity to branch-group internals.

## Preserved invariants checked
- Non-parallel authoring surface remains unchanged.
- Branch-group placeholder validation does not use prefix matching for `branch` or `fan_in`.
- Branch-group artifact rooting stays under normal workflow/owner-step roots rather than process cwd.
- Branch-group graph payloads preserve additive shape without altering top-level topology semantics.

## Edge cases and failure paths
- Unknown placeholder roots that merely share prefixes with `branch` or `fan_in` are rejected through normal reference validation.
- Invalid branch-group names, invalid branch names, non-fresh sessions, child/scoped/operation steps, and invalid fan-out payloads keep failing at compile time.
- Distinct fan-out input payloads continue to affect topology hashing.

## Validation run
- `./.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py -k 'branch_group or FanIn or branch_placeholder or fan_in_placeholder or compile_cache'`
- `./.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py -k 'branch_placeholders_under_owner_step_root or fan_in_placeholders_under_owner_step_root'`
- `./.venv/bin/python -m pytest -q tests/runtime/test_runtime_static_graph.py -k 'branch_group or topology_hash'`

## Known gaps
- No additional scoped coverage was added for CLI invocation shape because the current phase turn did not change runtime entrypoints and the relevant compatibility coverage already lives outside this narrow branch-group surface slice.
