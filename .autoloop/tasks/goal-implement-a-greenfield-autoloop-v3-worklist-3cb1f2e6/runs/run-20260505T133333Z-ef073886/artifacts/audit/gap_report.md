# Gap Report

## Original intent considered

- Restore repository-wide compatibility after repo-local `workflows/` discovery/import support landed, without reworking the accepted greenfield worklist behavior unless broader failures proved a necessary correction.
- Keep the already-green focused and adjacent suites green, fix the three named regression clusters, and finish with a green full-suite proof.
- Preserve the stated accepted behaviors around selector modes, strict progress-board shape, no legacy selector aliases or board-shape shims, `progress_artifact_worklist(...)`, and repo-local `workflows/` support.

## Clarifications / superseding decisions

- Planner turn 2 in [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6/runs/run-20260505T133333Z-ef073886/decisions.txt) superseded the initial mixed-root precedence assumption: bare names and workspace aliases remain authoritative from `.autoloop/workflows/`, while repo-local `workflows/` is an explicit-reference and named-fallback surface.
- Optimizer turn 2 superseded the earlier temp-repo materialization approach: canonical first-party `autoloop/workflows/<workflow>` labels remain, but manifest hashing and mutation checks must use the selected repo's actual `workflows/<workflow>` source bytes without copying files into the repo root.
- Packaged-workflow phase decisions recorded that provider-driven `PromptStep` and `ProduceVerifyStep` now expose framework-default `blocked` and `failed` runtime-control routes alongside `question`, and that selected-workflow boundary manifests preserve canonical labels separately from actual `source_path` provenance.

## Implemented behavior

- Workflow resolution contract restored in [autoloop/runtime/loader.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/loader.py) and adjacent catalog/capability paths:
  `.autoloop/workflows/` wins mixed-root bare-name and alias resolution, repo-local named fallback still works, and explicit repo-local file/class references keep isolated `_autoloop_workspace_workflows...` loading semantics.
- Optimizer compatibility restored in [autoloop_optimizer/optimization.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop_optimizer/optimization.py):
  schemaless runtime-owned observability payloads are migrated on read, explicit unsupported schema IDs still fail, and selected-workflow source manifests preserve canonical first-party labels while validating actual selected-source bytes.
- Shared packaged-workflow/runtime contracts were repaired centrally across files including [autoloop/core/discovery.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/discovery.py), [autoloop/core/compiler.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/compiler.py), [autoloop/runtime/runner.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/runner.py), and [autoloop_optimizer/candidate_surfaces.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop_optimizer/candidate_surfaces.py):
  shared route/artifact/source-boundary behavior now matches the repository contract, including default `blocked` / `failed` control routes, root-aware artifact handling, child-run root propagation, python-step arity compatibility, and canonical-label versus actual-source-path validation.
- Run artifacts show each requested cluster was closed and revalidated:
  `tests/runtime/test_workflow_reference_resolution.py`, `tests/unit/test_optimization_helpers.py`, the packaged-workflow/runtime suites named in the request, and the previously green focused/adjacent suites were all recorded green in the implement/test artifacts under `artifacts/implement/phases/*` and `artifacts/test/phases/*`.
- Live audit proof on 2026-05-05 confirmed the final repository state:
  `.venv/bin/python -m pytest` completed with `1215 passed, 616 warnings`.

## Unresolved gaps

- None material.

## Differences justified by later clarification or analysis

- The initial planner direction that favored repo-local canonical-name precedence was explicitly superseded in the run ledger and corrected in the implementation; this is a justified change, not a remaining gap.
- The initial optimizer fix that copied canonical `autoloop/workflows/...` trees into temp repos was explicitly superseded after reviewer feedback; the final contract keeps canonical labels but validates actual source bytes without mutating the repo root.
- The packaged-workflow phase widened beyond the originally named failing files into adjacent contract/static-graph/provider/history/builder assertions only after full-suite proof exposed shared compatibility drift. That widening was consistent with the request's acceptance criterion requiring a green full repository run.
- The final live full-suite count is `1215 passed`, while the packaged-workflow implementation note recorded `1214 passed`. The difference is justified by a later test-phase addition of one shared regression test in `tests/unit/test_stdlib_and_extensions.py`, not by unresolved behavior drift.

## Recommended next run

- No follow-up implementation run is required for this request.
