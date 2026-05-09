# Implementation Notes

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: implement
- Phase ID: placeholder-reference-graph
- Phase Directory Key: placeholder-reference-graph
- Phase Title: Placeholder And Reference Graph
- Scope: phase-local producer artifact

## Files changed

- `botlane/core/placeholders.py`
- `botlane/core/artifacts.py`
- `botlane/core/reference_graph.py`
- `botlane/core/compiler.py`
- `tests/unit/test_placeholder_refs.py`

## Symbols touched

- `validate_placeholder_ref`
- `render_runtime_template`
- `resolve_artifact_template`
- `ReferenceGraph`
- `ReferenceGraphBuilder`
- `compile_workflow`
- `_compile_reference_graph`

## Checklist mapping

- Plan Phase 5 / centralize placeholder parsing and rendering: completed via canonical runtime/template helpers in `placeholders.py` and thin delegates in `artifacts.py`.
- Plan Phase 5 / attach compiler-owned `ReferenceGraph`: completed via compiler-side graph construction from `WorkflowPlan` step/artifact data.
- Plan Phase 5 / preserve artifact-handle behavior: preserved; `ArtifactHandle.artifact` behavior was not changed.

## Assumptions

- Registry-backed prompts without resolved text should continue producing no compile-time placeholder refs.
- Broader static-graph failures outside prompt-ref persistence are not part of this phase unless caused by the placeholder/reference-graph edits.

## Preserved invariants

- `artifacts.py` no longer owns placeholder parsing helpers and keeps only delegate entrypoints for runtime template/artifact-template resolution.
- Runtime template rendering behavior and error wording for prompt/artifact/workflow-step message execution stay unchanged on the exercised paths.
- `WorkflowPlan.reference_graph` remains internal and is not exported through public package surfaces.

## Intended behavior changes

- `WorkflowPlan.reference_graph` is now populated from canonical plan data instead of `ReferenceGraph.empty()`.
- Placeholder validation now supports non-simple surfaces (`workflow_step_message`, `artifact_template`, `runtime_template`, `worklist_context`) through the shared parser/validator entrypoint.

## Known non-changes

- No new placeholder syntax was added.
- No public artifact-handle API or route/public export surface changed.
- Compiler-side artifact-template validation is observational/best-effort for contextual workflow-level templates to avoid tightening accepted authoring behavior in this phase.

## Expected side effects

- Static-graph/topology prompt-ref artifacts now read from compiler-owned `ReferenceGraph` data, including nested branch and fan-in steps.
- Inferred artifact reads are now available from the compiled graph without reparsing prompt strings at runtime.

## Validation performed

- Passed: `.venv/bin/python -m pytest tests/unit/test_placeholder_refs.py -q`
- Passed: `.venv/bin/python -m pytest tests/runtime/test_runtime_static_graph.py::test_topology_artifacts_are_written_additively_with_canonical_finish_surface tests/contract/engine/test_prompt_context.py -q`
- Broader spot-check surfaced unrelated existing failures in `tests/runtime/test_runtime_static_graph.py`:
  `test_branch_group_payloads_are_additive_in_static_graph_and_topology`
  `test_topology_payload_keeps_explicit_global_route_required_writes_concrete`

## Deduplication / centralization decisions

- Placeholder parsing, runtime rendering, and artifact-template resolution now live canonically in `placeholders.py`.
- Reference-graph collection walks canonical `StepPlan` / `BranchGroupPlan` structures instead of relying on authored-step placeholder backreferences.
