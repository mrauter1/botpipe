# Implementation Notes

- Task ID: full-revised-standalone-spec-autoloop-v3-async-n-3c402473
- Pair: implement
- Phase ID: compiler-surface-and-graph-alignment
- Phase Directory Key: compiler-surface-and-graph-alignment
- Phase Title: Compiler, surface, and graph alignment
- Scope: phase-local producer artifact

## Files changed
- `.autoloop/tasks/full-revised-standalone-spec-autoloop-v3-async-n-3c402473/runs/run-20260506T130608Z-37f1c786/decisions.txt`
- `.autoloop/tasks/full-revised-standalone-spec-autoloop-v3-async-n-3c402473/runs/run-20260506T130608Z-37f1c786/artifacts/implement/phases/compiler-surface-and-graph-alignment/implementation_notes.md`

## Symbols touched
- No production symbols changed in this turn.

## Checklist mapping
- M5 / AC-1: verified the existing simple surface exports, branch-group validation rules, and compile-cache bypass behavior already satisfy the scoped contract.
- M5 / AC-2: verified templated branch and fan-in artifact rooting already resolves under normal owner-step workflow roots, and branch-group static-graph/topology payloads remain additive and deterministic.

## Assumptions
- The active phase scope allows a no-code closeout when the requested behavior is already present and phase-local validation confirms it.

## Preserved invariants
- Public non-parallel authoring APIs remain unchanged.
- `simple.parallel(...)`, `simple.fan_out(...)`, and `FanIn` exports remain unchanged.
- Branch-group workflows still bypass the compile cache in v1.
- Branch and fan-in placeholder validation continues to compare the exact root token.
- Branch-group graph payloads remain additive and deterministic.

## Intended behavior changes
- None. This turn records a validation-only closeout.

## Known non-changes
- No edits to `autoloop/core/*`, `autoloop/runtime/static_graph.py`, or `autoloop/simple.py`.
- No new tests were added because the existing targeted suites already cover the phase acceptance criteria.

## Expected side effects
- None beyond this phase artifact update and the recorded decision entry.

## Validation performed
- `./.venv/bin/python -m pytest -q tests/unit/test_simple_surface.py -k 'branch_group or FanIn or branch_placeholder or fan_in_placeholder or compile_cache'`
- `./.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py -k 'branch_placeholders_under_owner_step_root or fan_in_placeholders_under_owner_step_root'`
- `./.venv/bin/python -m pytest -q tests/runtime/test_runtime_static_graph.py -k 'branch_group or topology_hash'`

## Deduplication / centralization decisions
- Kept existing ownership boundaries intact because the current discovery/compiler/artifact/static-graph split already matches the scoped phase contract.
