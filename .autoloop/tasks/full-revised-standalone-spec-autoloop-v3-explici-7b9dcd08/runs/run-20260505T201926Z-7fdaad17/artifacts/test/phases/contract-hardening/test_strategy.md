# Test Strategy

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: test
- Phase ID: contract-hardening
- Phase Directory Key: contract-hardening
- Phase Title: Contract Hardening
- Scope: phase-local producer artifact

## Behaviors covered
- Authored vs compiled branch-group metadata split remains visible through compiled workflow inspection.
- Branch-group compile-time validation rejects:
  - missing or non-fresh provider sessions in branch steps;
  - unsafe group and branch names;
  - scoped branch steps;
  - child-workflow branch and fan-in steps;
  - operation branch steps;
  - operation fan-in steps for both `simple.llm.step` and `simple.classify.step`;
  - invalid `branch` / `fan_in` placeholder placement and non-exact root matching;
  - fan-in helper usage outside fan-in.
- Composite route exposure stays sourced from fan-in routes or mechanical outcome routes only.
- Branch-group workflows bypass the compiled workflow cache.

## Preserved invariants checked
- Supported fan-in kinds still compile: prompt/LLM step, produce/verify step, authored Python step.
- Fan-out branch order and structured branch inputs remain unchanged.
- Topology/static-graph payloads still surface branch-group internals additively.

## Edge cases
- Exact placeholder-root matching distinguishes `branch` from unrelated roots like `branching`.
- Both operation authoring helpers are covered because they share the same authored `operation` kind but lower through the same runtime `PythonStep` path.

## Failure paths
- Compile-time rejection paths assert actionable `WorkflowValidationError` messages for the unsupported branch/fan-in kinds and placeholder misuse above.

## Validation run
- `.venv/bin/python -m pytest tests/unit/test_simple_surface.py -k 'fan_in_accepts_supported_step_kinds or rejects_operation_fan_in_steps or branch_group or compile_cache'`

## Known gaps
- This phase does not expand runtime concurrency/provider transport coverage; those remain out of scope for `contract-hardening`.
