# Workflow Contract Migration Plan

## Objective
Migrate the exported workflow packages under `workflows/*/workflow.py` to the enforced final public runtime contract without changing package prompts, artifact schemas, route tags, or publication behavior.

Affected packages: `autoloop_v1`, `candidate_workflow_to_adapted_execution_plan`, `company_operation_to_recursive_improvement_cycle`, `incident_to_hardening_program`, `investigation_request_to_evidence_pack`, `release_candidate_to_go_no_go`, `security_finding_to_verified_remediation`, `task_to_candidate_workflow_set`, `task_to_workflow_strategy`, `workflow_and_eval_to_refined_workflow_package`, `workflow_idea_to_workflow_package`, `workflow_package_to_composable_building_blocks`, `workflow_portfolio_to_operating_system`, `workflow_run_history_to_failure_modes`, `workflow_run_traces_to_optimization_candidates`, `workflow_to_eval_suite`.

## Current Findings
- `./.venv/bin/python` compile sweep over `discover_workflow_packages(...)` currently fails all 16 exported packages; the first blocking error in every case is an `after_review` hook arity mismatch against the enforced `hook(ctx)` contract.
- Regex inspection of the same 16 `workflow.py` files shows the remaining legacy patterns are broader than the first compile error: multi-argument hook definitions, hook returns of replacement state models, and two-argument `python_step(state, ctx)` handlers all still exist.
- Runtime tests in multiple package suites still invoke legacy package-local `WorkflowClass.on_*` helper entry points directly and often assert tuple returns such as `(next_state, event)`, which conflicts with the final ctx-driven execution surface.
- `autoloop/core/compiler.py` still wraps raw two-argument python-step handlers into a compiled `python_handler(ctx)`, so compiled-step invocation is not sufficient as the only regression surface for the raw exported authoring contract.

## Milestones
### 1. Migrate exported workflow package code
- Update every exported lifecycle hook used by step, producer, verifier, and route surfaces to `hook(ctx)` only.
- Replace reads of positional `outcome` or similar helper arguments with `ctx.outcome`, `ctx.route`, `ctx.artifacts`, `ctx.meta`, and existing `ctx` fields.
- Remove hook state-replacement returns. Hooks must update `ctx.state` directly and only return supported control values: `None`, route-tag string, `Event(...)`, `RequestInput(...)`, `Goto(...)`, or `Fail(...)`.
- Convert exported `@python_step` handlers from `(state, ctx)` to `(ctx)`, move all state reads/writes through `ctx.state`, and stop returning `(state, event)`-style compatibility tuples.
- Preserve artifact paths, prompt files, control schemas, routes, and publication outputs while changing only the handler contract.

### 2. Migrate workflow-specific test surfaces
- Update runtime tests that call `WorkflowClass.on_*` helpers directly, especially bootstrap, capture-context, route-skipping, publish, and after-verifier package helpers.
- Split behavior tests from raw-contract checks. Behavior tests may invoke declaration-local callables or compiled hooks after `compile_workflow(...)`, but raw exported-contract checks must inspect declaration signatures and/or `workflow.py` source directly so compiled wrappers cannot hide forbidden handler forms.
- Rewrite assertions to observe state from `ctx.state` plus the normalized handler return, rather than expecting returned replacement state models or tuple-based helper compatibility.
- Keep each package suite focused on its behavior; do not reintroduce package-local compat wrappers just to preserve old test call sites.

### 3. Lock in repo-level compatibility coverage
- Keep the discovered-package parity gate in `tests/runtime/test_workflow_integration_parity.py` as the repo-level compile sweep and require zero failures for all discovered exported packages.
- Add a discovered-exported-workflow audit in the existing strictness/public-surface tests that inspects raw declaration signatures and scans exported `workflow.py` files for banned hook state-return forms. Reuse the repo’s existing `forbidden_patterns` / `inspect.signature(...)` test style instead of adding runtime compatibility helpers or new infrastructure.
- Run the affected workflow runtime suites plus the parity/strictness tests as the acceptance gate for the migration.

## Interface Contract
- Lifecycle hooks: `before/after/before_producer/after_producer/before_verifier/after_verifier/on_taken(ctx) -> None | str | Event | RequestInput | Goto | Fail`.
- Python steps: `python_step(ctx) -> None | str | Event | RequestInput | Goto | Fail`.
- Hook state rules: hooks never return `ctx.state`, `ctx.state.model_copy(...)`, `state.model_copy(...)`, or any replacement `BaseModel`.
- Test compatibility note: legacy `WorkflowClass.on_*` helper entry points are no longer a supported surface for exported simple workflows. Use declaration-local or compiled callables for behavior tests, and keep raw declaration/source inspection as the contract gate for signature/return-form regressions.

## Validation
- Fast gate: `./.venv/bin/pytest tests/unit/test_simple_surface.py tests/runtime/test_workflow_integration_parity.py`, with `tests/unit/test_simple_surface.py` extended to audit discovered exported workflows for raw hook/python-step arity and banned hook state-return snippets.
- Package regression gate: run the affected runtime suites for the 16 migrated workflow packages, with special attention to `test_workflow_run_traces_to_optimization_candidates.py`, which currently has the heaviest direct-helper usage.
- Acceptance outcome: discovered exported packages compile cleanly, direct-call tests use the final ctx-only surface, and no migrated package reintroduces multi-argument hooks, hook state-return replacements, or `python_step(state, ctx)`.

## Risk Register
- State-reset drift when replacing returned models with `ctx.state` mutation could leave stale fields between runs. Control: preserve field-by-field reset parity in bootstrap and publication steps, and verify with existing runtime suites.
- After-hook payload handling could regress if `outcome` data is not fully remapped onto `ctx.outcome`. Control: migrate hook arity first, then re-run compile plus package suites that inspect outcome-derived fields.
- Test churn is broad because many suites directly call package-local handlers. Control: switch those tests to declaration-local or compiled behavior surfaces as appropriate, and keep a separate raw contract audit so the compiled wrapper layer cannot mask signature regressions.

## Rollback
- Revert only the touched `workflows/*/workflow.py` and affected test modules if a migrated package regresses.
- Do not roll back core runtime/compiler behavior; the request is to conform exported packages to the already-enforced contract.
- No persisted-data or CLI migration is required because artifact names, schemas, and workflow package discovery remain unchanged.
