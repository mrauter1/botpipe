# Implementation Notes

- Task ID: full-revised-autoloop-v3-redesign-implementation-16af2351
- Pair: implement
- Phase ID: workflow-migration-and-cleanup
- Phase Directory Key: workflow-migration-and-cleanup
- Phase Title: Workflow migration and cleanup
- Scope: phase-local producer artifact

## Files Changed

- `workflows/investigation_request_to_evidence_pack/workflow.py`
- `workflows/incident_to_hardening_program/workflow.py`
- `workflows/task_to_candidate_workflow_set/workflow.py`
- `workflows/workflow_portfolio_to_operating_system/workflow.py`
- `autoloop_optimizer/__init__.py`
- `autoloop_optimizer/_selected_workflow.py`
- `autoloop_optimizer/adaptation.py`
- `autoloop_optimizer/candidate_surfaces.py`
- `autoloop_optimizer/company.py`
- `autoloop_optimizer/decomposition.py`
- `autoloop_optimizer/diagnostics.py`
- `autoloop_optimizer/evaluation.py`
- `autoloop_optimizer/optimization.py`
- `autoloop_optimizer/portfolio.py`
- `autoloop_optimizer/refinement.py`
- `stdlib/_selected_workflow.py`
- `stdlib/adaptation.py`
- `stdlib/candidate_surfaces.py`
- `stdlib/company.py`
- `stdlib/decomposition.py`
- `stdlib/diagnostics.py`
- `stdlib/evaluation.py`
- `stdlib/optimization.py`
- `stdlib/portfolio.py`
- `stdlib/refinement.py`
- `docs/authoring.md`
- `docs/architecture.md`
- `pyproject.toml`
- `.autoloop/tasks/full-revised-autoloop-v3-redesign-implementation-16af2351/decisions.txt`

## Symbols Touched

- Workflow declarations: `bootstrap`, `capture_*`, `publish_*`, `frame_*`, `analyze_*`, `package_*`
- New package surface: `autoloop_optimizer.*`
- Compatibility shim modules: `stdlib._selected_workflow`, `stdlib.adaptation`, `stdlib.candidate_surfaces`, `stdlib.company`, `stdlib.decomposition`, `stdlib.diagnostics`, `stdlib.evaluation`, `stdlib.optimization`, `stdlib.portfolio`, `stdlib.refinement`

## Checklist Mapping

- AC-1 partial: migrated four bundled workflow packages from `SystemStep` / `PairStep` plus global `transitions` to `python_step(...)` / `do_review_step(...)` with step-local `routes` and `Prompt.file(...)`
- AC-2 partial: moved optimizer/application helper implementations into sibling package `autoloop_optimizer`, leaving `stdlib` compatibility shims
- AC-3 deferred: full suite migration, remaining bundled workflows, and doc/test cleanup not completed in this turn

## Assumptions

- Existing workflow-local `on_<step>` outcome handlers remain valid compatibility seams for `do_review_step(...)` during migration
- `stdlib` shims may remain temporarily while call sites move to `autoloop_optimizer`

## Preserved Invariants

- Publication validators and receipt payload logic stay workflow-local
- Existing artifact paths, state models, session names, and verifier payload schemas remain unchanged
- Runtime control middleware `on_outcome = event_on_outcome_tags(...)` remains active

## Intended Behavior Changes

- The migrated workflows now declare topology on the step objects themselves instead of relying on global `transitions`
- Optimizer/application helpers are now housed under `autoloop_optimizer` rather than living only in `stdlib`

## Known Non-Changes

- Route metadata bundles still use `route_infos` / `RouteInfo` compatibility inputs
- Remaining bundled workflows, docs, and tests still need canonical-surface cleanup
- Top-level `autoloop` exports were not reduced in this turn

## Expected Side Effects

- Compiler/inspect output for the four migrated workflows should now reflect step-local route declarations sourced from the simple surface
- Existing imports from `stdlib` continue to resolve through the compatibility shims

## Validation Performed

- `python3 -m py_compile workflows/investigation_request_to_evidence_pack/workflow.py workflows/incident_to_hardening_program/workflow.py workflows/task_to_candidate_workflow_set/workflow.py workflows/workflow_portfolio_to_operating_system/workflow.py autoloop_optimizer/__init__.py autoloop_optimizer/_selected_workflow.py autoloop_optimizer/adaptation.py autoloop_optimizer/candidate_surfaces.py autoloop_optimizer/company.py autoloop_optimizer/decomposition.py autoloop_optimizer/diagnostics.py autoloop_optimizer/evaluation.py autoloop_optimizer/optimization.py autoloop_optimizer/portfolio.py autoloop_optimizer/refinement.py stdlib/_selected_workflow.py stdlib/adaptation.py stdlib/candidate_surfaces.py stdlib/company.py stdlib/decomposition.py stdlib/diagnostics.py stdlib/evaluation.py stdlib/optimization.py stdlib/portfolio.py stdlib/refinement.py`

## Deduplication / Centralization

- Centralized moved optimizer/application helper implementations under `autoloop_optimizer`
- Replaced copied helper bodies in `stdlib` with import-only shims to avoid duplicated logic
