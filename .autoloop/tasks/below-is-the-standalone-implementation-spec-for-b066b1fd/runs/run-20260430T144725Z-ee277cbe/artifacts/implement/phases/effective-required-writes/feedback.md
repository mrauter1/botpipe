# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: implement
- Phase ID: effective-required-writes
- Phase Directory Key: effective-required-writes
- Phase Title: Normalize Effective Required Writes
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` `[runtime/static_graph.py:_topology_route_payload, core/compiler.py:_topology_hash_payload, core/route_required_writes.py:effective_route_required_writes]` Top-level `global_routes` now serialize `effective_required_writes=[]` whenever the route inherits artifact-level required writes, because the shared helper is called with `step_name="GLOBAL"` and therefore has no step context. Concrete failure: for a workflow with `GLOBAL: {"failed": FAIL}` and a required output artifact, `workflow_topology_payload(compiled)["steps"][...]["routes"]["failed"]["effective_required_writes"]` resolves to `["ask.report"]`, but `workflow_topology_payload(compiled)["global_routes"]["failed"]["effective_required_writes"]` resolves to `[]`. That makes `topology.json` internally inconsistent and misses AC-2’s requirement that topology artifacts expose explicit and effective required-write sets consistently. Minimal fix: do not emit a concrete effective set for context-free `global_routes` unless the route has an explicit override; instead emit `null` or a per-step projection for inherited globals, and add regression coverage for a required artifact plus inherited `GLOBAL` route. 
