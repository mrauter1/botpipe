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
