# Implement ↔ Code Reviewer Feedback

- Task ID: full-revised-autoloop-v3-redesign-implementation-16af2351
- Pair: implement
- Phase ID: workflow-migration-and-cleanup
- Phase Directory Key: workflow-migration-and-cleanup
- Phase Title: Workflow migration and cleanup
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking`
  File/symbol refs: `workflows/autoloop_v1/workflow.py`, `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`, `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`, `workflows/release_candidate_to_go_no_go/workflow.py`, `workflows/security_finding_to_verified_remediation/workflow.py`, `workflows/task_to_workflow_strategy/workflow.py`, `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`, `workflows/workflow_idea_to_workflow_package/workflow.py`, `workflows/workflow_package_to_composable_building_blocks/workflow.py`, `workflows/workflow_run_history_to_failure_modes/workflow.py`, `workflows/workflow_run_traces_to_optimization_candidates/workflow.py`, `workflows/workflow_to_eval_suite/workflow.py`.
  Concrete issue: the phase objective says to finish migrating bundled workflows onto the canonical authoring model, but a large part of the bundled workflow set still depends on `PairStep`, `SystemStep`, `SUCCESS`, and global `transitions` / `merge_transitions`. That leaves AC-1 unmet and means the compatibility-era surface still has active first-party runtime dependencies.
  Risk / regression scenario: any attempt to demote or remove the deprecated compatibility surface after this patch set will immediately break untouched bundled workflows, inspect expectations, and downstream examples that import them as canonical packages.
  Minimal fix direction: migrate the remaining bundled workflow packages to `python_step(...)`, `do_review_step(...)`, `FINISH`, and step-local `routes`, then update any package-local prompts/inspect expectations that still assume the legacy compiled topology shape.

- IMP-002 `blocking`
  File/symbol refs: `docs/authoring.md:146`, `docs/authoring.md:159`, `docs/authoring.md:192`, `docs/authoring.md:287`, `docs/authoring.md:420`, `docs/authoring.md:442`, `docs/workflows/release_candidate_to_go_no_go.md:50`, `docs/workflows/release_candidate_to_go_no_go.md:80`, plus the other `docs/workflows/*.md` files still documenting `route_infos`.
  Concrete issue: the remaining docs and examples still teach compatibility-era constructs such as `SystemStep`, `PairStep`, `SUCCESS`, global `transitions`, `RouteInfo`, and `route_infos` as normal authoring inputs. The active phase explicitly requires retiring that emphasis so the canonical public guidance remains authoritative.
  Risk / regression scenario: readers following the docs after this patch will still author new workflows against deprecated surfaces, which directly undermines the migration and keeps future cleanup blocked behind more legacy churn.
  Minimal fix direction: rewrite the remaining docs/examples so canonical `Workflow` / `step` / `do_review_step` / `python_step`, `Prompt.file(...)`, `FINISH`, and step-local `routes` are the primary path, and demote any unavoidable compatibility notes to clearly marked migration-only callouts.

- IMP-003 `blocking`
  File/symbol refs: `workflows/investigation_request_to_evidence_pack/workflow.py:126`, `workflows/task_to_candidate_workflow_set/workflow.py:161`, `workflows/incident_to_hardening_program/workflow.py:146`, `workflows/workflow_portfolio_to_operating_system/workflow.py:260`, `workflows/*/contracts.py` modules that still import `core.RouteInfo`.
  Concrete issue: even the partially migrated workflows still rely on `route_infos=...` and `RouteInfo` contract bundles as public authoring inputs. That conflicts with this phase's cleanup target and with AC-3's requirement that first-party suites stop depending on removable compatibility surfaces.
  Risk / regression scenario: removing or even aggressively demoting `RouteInfo` after this patch remains unsafe because converted workflows still require it to compile. The codebase therefore looks migrated at the step declaration level while still carrying a hidden hard dependency on the old route metadata surface.
  Minimal fix direction: move route metadata ownership onto canonical `Route.to(...)` declarations or another explicitly retained internal-only lowering path, and update the first-party workflow contract modules so bundled workflows no longer import public `RouteInfo`.

## Follow-up Review - Cycle 2

- IMP-004 `blocking`
  File/symbol refs: `workflows/company_operation_to_recursive_improvement_cycle/workflow.py`, `workflows/security_finding_to_verified_remediation/workflow.py`, `workflows/task_to_workflow_strategy/workflow.py`, `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`, `workflows/workflow_package_to_composable_building_blocks/workflow.py`, `workflows/workflow_run_traces_to_optimization_candidates/workflow.py`.
  Concrete issue: the latest producer pass reduced the legacy footprint, but these six bundled workflows still depend on `PairStep`, `SystemStep`, `SUCCESS`, and global `transitions`. AC-1 still requires the bundled workflow set itself to finish the canonical migration, not only a subset.
  Risk / regression scenario: deprecated-surface cleanup remains unsafe because first-party workflow packages still require the compatibility declarations to compile and to preserve their current topology.
  Minimal fix direction: finish the same declaration-level migration pattern used in the latest batch for the remaining six workflow packages, preserving their existing handlers while replacing legacy declarations with `python_step(...)`, `do_review_step(...)`, `FINISH`, and step-local `routes`.

- IMP-005 `blocking`
  File/symbol refs: `docs/authoring.md:146`, `docs/authoring.md:159`, `docs/authoring.md:192`, `docs/authoring.md:287`, `docs/authoring.md:420`, `docs/authoring.md:442`, `docs/workflows/release_candidate_to_go_no_go.md:50`, `docs/workflows/release_candidate_to_go_no_go.md:80`, `docs/workflows/security_finding_to_verified_remediation.md:114`, `docs/workflows/task_to_workflow_strategy.md:118`, and the other `docs/workflows/*.md` files still documenting `route_infos`.
  Concrete issue: the documentation set still presents compatibility-era constructs and contracts as normal authoring guidance, including `PairStep`, `SystemStep`, `SUCCESS`, global `transitions`, `RouteInfo`, and `route_infos`. That still violates the phase requirement to retire legacy documentation emphasis and keep the canonical surface authoritative.
  Risk / regression scenario: users following the current docs will keep writing new workflows against deprecated inputs, extending the compatibility surface just as the phase is supposed to remove it.
  Minimal fix direction: rewrite the remaining docs/examples so canonical `Workflow` / `step` / `do_review_step` / `python_step`, `Prompt.file(...)`, `FINISH`, and step-local `routes` are the primary path, with any compatibility mention demoted to migration-only notes.

- IMP-006 `blocking`
  File/symbol refs: `workflows/release_candidate_to_go_no_go/workflow.py:101`, `workflows/workflow_idea_to_workflow_package/workflow.py:116`, `workflows/workflow_run_history_to_failure_modes/workflow.py:155`, `workflows/workflow_to_eval_suite/workflow.py:131`, `workflows/investigation_request_to_evidence_pack/workflow.py:126`, `workflows/task_to_candidate_workflow_set/workflow.py:161`, `workflows/incident_to_hardening_program/workflow.py:146`, `workflows/workflow_portfolio_to_operating_system/workflow.py:260`, plus the remaining `workflows/*/contracts.py` modules that still import `core.RouteInfo`.
  Concrete issue: the latest migration batch converted step declarations but still leaves public `route_infos=...` and `RouteInfo` as the route metadata path for both newly migrated and previously migrated bundled workflows. That means the first-party workflow layer still depends on a compatibility-era metadata surface even after declaration migration.
  Risk / regression scenario: AC-3 cannot be satisfied while bundled workflows and their contract modules continue importing `RouteInfo`, because strictness/docs/integration suites would still need the deprecated route metadata API to exist.
  Minimal fix direction: finish the second-pass contract cleanup described in the implementation notes by moving bundled workflow route metadata onto canonical `Route.to(...)` declarations or another explicitly retained internal lowering path, then update the docs/tests to stop presenting `route_infos` as a public workflow authoring input.

## Follow-up Review - Cycle 3

- Resolution note
  `IMP-001` and `IMP-002` are superseded by the later migration passes and no longer describe the active blocker set.
  `IMP-003` is narrowed to `IMP-007`: the remaining compatibility dependency is the older first-party `RouteInfo` / `route_infos` usage, not the legacy step declaration surface.
  `IMP-004` is resolved: bundled workflow packages no longer rely on `PairStep`, `SystemStep`, `SUCCESS`, or package-local `transitions`.
  `IMP-005` is resolved materially: the public workflow docs now teach canonical step-local routes and `Route.to(...)` metadata instead of presenting `route_infos` / `RouteInfo` as the normal authoring path.

- IMP-007 `blocking`
  File/symbol refs: `workflows/investigation_request_to_evidence_pack/contracts.py`, `workflows/investigation_request_to_evidence_pack/workflow.py`, `workflows/task_to_candidate_workflow_set/contracts.py`, `workflows/task_to_candidate_workflow_set/workflow.py`, `workflows/incident_to_hardening_program/contracts.py`, `workflows/incident_to_hardening_program/workflow.py`, `workflows/release_candidate_to_go_no_go/contracts.py`, `workflows/release_candidate_to_go_no_go/workflow.py`, `workflows/workflow_idea_to_workflow_package/contracts.py`, `workflows/workflow_idea_to_workflow_package/workflow.py`, `workflows/workflow_to_eval_suite/contracts.py`, `workflows/workflow_to_eval_suite/workflow.py`, `workflows/workflow_run_history_to_failure_modes/contracts.py`, `workflows/workflow_run_history_to_failure_modes/workflow.py`, `workflows/workflow_portfolio_to_operating_system/contracts.py`, and `workflows/workflow_portfolio_to_operating_system/workflow.py`.
  Concrete issue: the declaration migration is complete, but these earlier-migrated first-party packages still import `core.RouteInfo` and still pass `route_infos=...` into canonical workflow declarations. That leaves the first-party workflow layer dependent on the deprecated route-metadata surface even after the legacy step surface is gone.
  Risk / regression scenario: any attempt to demote or remove `RouteInfo` now will still break bundled workflow packages, strictness checks, and integration suites, so AC-3 remains unmet.
  Minimal fix direction: finish the remaining second-pass route-metadata cleanup by converting those contract bundles to `Route.to(...)` targets and switching the corresponding workflow declarations from `route_infos=` to `routes=`.

- IMP-008 `blocking`
  File/symbol refs: `.autoloop/tasks/full-revised-autoloop-v3-redesign-implementation-16af2351/implement/phases/workflow-migration-and-cleanup/implementation_notes.md`, phase acceptance criterion `AC-3`.
  Concrete issue: the implementation notes explicitly say the strictness/docs/contract/runtime/workflow integration suites were not run after the broad workflow and doc migration. This phase’s acceptance criteria require those suites to pass without depending on removed compatibility surfaces.
  Risk / regression scenario: the workflow migration touched many first-party packages and contract modules at once. Without running the required suites, regressions in inspect expectations, docs assertions, or compatibility cleanup boundaries can survive unnoticed until a later cleanup removes the shim they still rely on.
  Minimal fix direction: run the required strictness/docs/contract/runtime/workflow integration suites in a valid environment and fix any remaining compatibility-surface dependencies they expose before marking the phase complete.
