# Implement ↔ Code Reviewer Feedback

- Task ID: autoloop-v3-explicit-branch-groups-full-revised-76d1507c
- Pair: implement
- Phase ID: surface-hardening-and-regression-suite
- Phase Directory Key: surface-hardening-and-regression-suite
- Phase Title: Surface Hardening And Regression Suite
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 (`non-blocking`): [autoloop/runtime/static_graph.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/static_graph.py:349) `_branch_group_surface_payload` currently serializes `branch.input` through `_json_value(...)`, which turns fan-out mapping/list inputs into Python `repr` strings inside `topology.json` and `static_step_graph.json` instead of preserving structured JSON values. That weakens the new additive metadata for any downstream consumer that wants to inspect branch inputs programmatically. Minimal fix: store raw `branch.input` in the payload and let the existing JSON writer encode it, since branch inputs are already validated as JSON-serializable during lowering.
