# Implement ↔ Code Reviewer Feedback

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: implement
- Phase ID: inspection-docs-and-regression
- Phase Directory Key: inspection-docs-and-regression
- Phase Title: Inspection, Docs, And Regression Sweep
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` [autoloop/runtime/static_graph.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/static_graph.py): `_route_table_text`, `_topology_mermaid`, and `_compile_report_text` still emit the old flat route view. They do not distinguish authored routes from runtime-control routes, and they do not expose policy-aware provider visibility (`interactive` vs `full_auto`) even though the phase contract explicitly includes route tables and compile reports in scope. This leaves part of the static-graph surface on the legacy contract, so AC-1 is not fully met even though the JSON payloads and CLI output were updated. Minimal fix: derive these text artifacts from the same compiled route metadata already used by `workflow_static_step_graph_payload(...)` and include at least runtime-control marking plus both provider-visible policies in the rendered summaries.
- `IMP-002` `blocking` [docs/authoring.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/docs/authoring.md:621): the artifact-ownership section still says “do not declare the same artifact in both roles unless and until an explicit managed-artifact role is introduced,” but this implementation introduced that role and retagged many shipped workflows to rely on it. That leaves the docs internally contradictory and fails AC-2’s requirement to describe the shipped artifact-ownership behavior. Minimal fix: rewrite this section to state that the managed/shared role now exists, and document the actual authoring seam used for it (`Artifact(..., role=\"managed\")` and/or `Artifact.managed(...)`).
