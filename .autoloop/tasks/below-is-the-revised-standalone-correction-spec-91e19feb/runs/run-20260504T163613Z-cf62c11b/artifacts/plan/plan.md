# Plan

## Goal
Align workflow prompt-body route wording with the shipped runtime route model without changing runtime behavior: `question` stays the only default runtime control route, while authored `blocked` and `failed` remain ordinary application routes.

## Repo Findings
- `docs/authoring.md`, `docs/architecture.md`, scoped workflow docs, and prompt `README.md` files already use the shipped route model.
- Non-README prompt bodies are the remaining drift surface: 89 prompt bodies across 15 workflow packages still contain retired `Reserved routes` wording.
- The runtime prompt-package suites that still hard-code retired wording are:
  - `tests/runtime/test_company_operation_to_recursive_improvement_cycle.py`
  - `tests/runtime/test_workflow_portfolio_to_operating_system.py`
  - `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  - `tests/runtime/test_workflow_to_eval_suite.py`
- Shared baseline coverage currently stops at `docs/workflows/*.md` and `workflows/*/prompts/README.md`; it does not scan prompt bodies, which leaves prompt-only regressions uncovered (`workflow_run_traces_to_optimization_candidates` is the clearest example).

## Implementation Plan
### 1. Rewrite prompt-body route guidance
- Update affected files under `workflows/*/prompts/*.md` excluding `README.md`.
- Replace retired `Reserved routes` / `Use reserved routes only` language with route-guidance wording that adds two stable route-model markers to each affected route-guidance section:
  - a positive `question` marker stating that `question` is the only default runtime control route,
  - a positive `blocked` / `failed` marker stating that authored `blocked` and `failed` are ordinary application routes rather than framework defaults.
- Keep workflow-specific step routes and escalation criteria unchanged around those shared markers.
- Preserve each prompt’s existing step-local intent, artifact contracts, and route-specific decision logic; only the route-model framing should change.

### 2. Update runtime prompt-package assertions
- Replace retired marker assertions in the six affected runtime suites with assertions for the new positive route-model markers.
- Keep package-specific contract markers intact so these tests still verify local prompt structure in addition to route wording.
- Do not spread new wording assertions into every package-specific suite when a shared baseline can cover the cross-cutting invariant once.

### 3. Add central prompt-body regression coverage
- Extend the shared baseline test surface in `tests/test_architecture_baseline_docs.py` to scan workflow prompt bodies directly, excluding `README.md`.
- Target prompt bodies that carry route-guidance sections, so the guard covers the real prompt-body contract without forcing minimal prompts that do not describe routing.
- Guard these invariants centrally:
  - no prompt body contains `Reserved routes`,
  - no prompt body reintroduces a reserved/default set containing `question`, `blocked`, and `failed`,
  - every updated route-guidance body contains the positive `question` marker,
  - every updated route-guidance body contains the positive authored-`blocked` / authored-`failed` application-route marker.
- Prefer stable marker-fragment assertions reused from the shipped README/docs vocabulary over full-text snapshots so prompt-specific guidance can remain compact and workflow-local.

## Interfaces And Invariants
- Prompt-body route wording contract:
  - `question` is the only default runtime control route.
  - Authored `blocked` and `failed` are workflow/application routes, not framework-default or reserved routes.
  - Prompt bodies may keep step-specific escalation criteria, but they must not frame those routes as a reserved/default trio.
  - Shared regression coverage must assert the positive route-model markers, not only the absence of retired wording.
- Test seam ownership:
  - Package-specific runtime tests continue to own prompt-local structure checks.
  - `tests/test_architecture_baseline_docs.py` owns the cross-workflow wording baseline for prompt bodies.

## Compatibility / Behavior
- No runtime engine, route resolution, workflow graph, or public API changes are expected.
- This is a prompt/documentation plus test-alignment change; no migration is required.
- Existing docs and prompt `README.md` wording should remain the source vocabulary unless drift is found during implementation.

## Validation
- Run `tests/test_architecture_baseline_docs.py`.
- Run the six runtime suites whose prompt-marker assertions change.
- Confirm the shared baseline fails both on reintroduced retired wording and on missing positive route-model markers inside updated route-guidance bodies.

## Risk Register
- Manual prompt edits across many files can drift semantically.
  Mitigation: reuse the shipped route-model marker fragments and keep edits limited to route-guidance bullets.
- A central guard can become too brittle if it snapshots full prose.
  Mitigation: assert stable positive/negative marker fragments rather than exact paragraph text.
- Some prompt families are not covered by package-local wording assertions today.
  Mitigation: baseline prompt-body scanning closes that gap directly and owns the positive route-model markers for route-guidance bodies.

## Rollback
- Revert prompt-body wording changes and the updated test assertions together if the new baseline proves too strict.
- If only the central guard is over-constrained, relax the shared assertion seam before widening package-local exceptions.
