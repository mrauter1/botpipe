# Recursive Framework Evolution C8 Plan

## Cycle mode

- Selected mode: `consolidate`
- Rationale: the highest-leverage remaining duplication is the selected-workflow snapshot family. `stdlib/adaptation.py`, `stdlib/refinement.py`, and `stdlib/decomposition.py` each rebuild overlapping selected-workflow payloads, and multiple workflows repeat the same selected-workflow identity checks after calling those helpers. This improves authoring clarity without adding another workflow.

## Pre-change audit

- Three most relevant existing workflows/helpers:
  1. `stdlib/adaptation.py` plus `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
  2. `stdlib/refinement.py` plus `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
  3. `stdlib/decomposition.py` plus `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- Repeated patterns found:
  - selected-workflow resolution and `inspect_workflow_reference(...)` fan out into overlapping payload serialization in `stdlib/adaptation.py`, `stdlib/refinement.py`, and `stdlib/decomposition.py`
  - repeated `selected_workflow_name` / nested `workflow_name` alignment checks appear in `candidate_workflow_to_adapted_execution_plan`, `workflow_to_eval_suite`, `workflow_run_history_to_failure_modes`, `workflow_and_eval_to_refined_workflow_package`, and `workflow_package_to_composable_building_blocks`
  - repeated local helpers for repo-root lookup, runtime-test inference, and repo-relative path conversion remain in the selected-workflow surface family
- Simplification opportunity:
  - centralize selected-workflow payload building in `core/workflow_capabilities.py`
  - centralize selected-workflow snapshot identity validation in `stdlib/validation.py`
  - keep workflow-local publication semantics in the workflows themselves
- New workflow actually necessary: no
- What would make this family 10x easier to author and reason about:
  - one authoritative selected-workflow payload builder plus one shared validator set, so future workflows consume explicit artifacts without rewriting snapshot parsing
- Cycle decision: change and consolidate existing helpers; do not add a workflow

## Candidate options considered

1. Docs-only or no-op convergence report
   - Lowest implementation risk, but it leaves active serializer and validation duplication in the current selected-workflow family.
2. Validation-only extraction
   - Removes duplicated workflow-local checks, but leaves serializer and path-shaping duplication in the stdlib helper family.
3. Serializer plus validation convergence while preserving separate artifacts
   - Chosen because it removes duplication on both sides of the seam without collapsing `selected_workflow_capability.json`, `selected_workflow_authoring_surface.json`, and `selected_workflow_decomposition_surface.json` into one artifact.

## Chosen improvement

- Extend `core/workflow_capabilities.py` with authoritative payload builders for selected-workflow capability, authoring-surface, and decomposition-surface views.
- Keep the current public stdlib writer functions and artifact names:
  - `write_selected_workflow_capability_snapshot(...)`
  - `write_selected_workflow_authoring_surface(...)`
  - `write_selected_workflow_decomposition_surface(...)`
- Reduce those stdlib writers to thin wrappers over shared payload builders instead of letting each module re-derive path inventories independently.
- Add shared selected-workflow snapshot validators in `stdlib/validation.py` for:
  - capability snapshot identity
  - authoring-surface identity
  - decomposition-surface identity and step-count sanity
  - cross-artifact selected-workflow-name alignment
- Migrate the workflow-local validation blocks in:
  - `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
  - `workflows/workflow_to_eval_suite/workflow.py`
  - `workflows/workflow_run_history_to_failure_modes/workflow.py`
  - `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
  - `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- Keep only domain-specific publication rules local, such as case-count rules, run-history evidence checks, candidate-overlay validation, and decomposition building-block policy.

## Why this is higher leverage than a new workflow

- The repo already has a broad workflow portfolio and this cycle explicitly disallows new workflows unless reuse is insufficient.
- The same selected-workflow snapshot mechanics already sit on the critical path for adaptation, evaluation, diagnostics, refinement, and decomposition workflows.
- Consolidating that seam shortens existing workflows immediately and makes future selected-workflow consumers cheaper to author without widening the runtime or root authoring surface.

## Interfaces and expected touch points

- Core
  - `core/workflow_capabilities.py`: add shared payload builders and shared path-serialization helpers
- Stdlib
  - `stdlib/adaptation.py`
  - `stdlib/refinement.py`
  - `stdlib/decomposition.py`
  - `stdlib/validation.py`
  - `stdlib/__init__.py` only if migrated workflows need the new validators via the public stdlib export surface
- Workflow migrations
  - `workflows/candidate_workflow_to_adapted_execution_plan/workflow.py`
  - `workflows/workflow_to_eval_suite/workflow.py`
  - `workflows/workflow_run_history_to_failure_modes/workflow.py`
  - `workflows/workflow_and_eval_to_refined_workflow_package/workflow.py`
  - `workflows/workflow_package_to_composable_building_blocks/workflow.py`
- Docs and proof
  - `docs/authoring.md`
  - `tests/unit/test_stdlib_and_extensions.py`
  - `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
  - `tests/runtime/test_workflow_to_eval_suite.py`
  - `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  - `tests/test_architecture_baseline_docs.py`
- Recursive memory to update during implementation closeout
  - `.autoloop_recursive/framework_evolution_charter.md`
  - `.autoloop_recursive/framework_roadmap.md`
  - `.autoloop_recursive/framework_gap_ledger.md`
  - `.autoloop_recursive/workflow_candidate_ledger.md`
  - `.autoloop_recursive/validation_debt_ledger.md`
  - Charter synchronization is mandatory even if doctrine stays unchanged; the minimum acceptable closeout is an explicit no-doctrine-change note so later cycles know the file was reviewed and synced.

## Compatibility and regression controls

- Preserve existing artifact filenames and top-level JSON keys for:
  - `selected_workflow_capability.json`
  - `selected_workflow_authoring_surface.json`
  - `selected_workflow_decomposition_surface.json`
- Preserve existing CLI behavior, runtime/provider boundaries, `ctx.invoke_workflow(...)` compatibility, and metadata-only `workflow.toml`.
- Do not merge compiled and authoring surfaces into one artifact; reuse must happen behind the existing helper boundaries.
- Keep workflow-specific publication semantics local to the workflows; shared helpers should validate generic selected-workflow identity and structure only.
- Validate with targeted unit and runtime suites before closeout.
- Synchronize every standing recursive-memory file named in the request during closeout, including `.autoloop_recursive/framework_evolution_charter.md`; if doctrine does not change, record that explicitly rather than treating the charter as skipped.
- Rollback plan:
  - revert payload-builder and validator extraction first
  - restore migrated workflows to prior inline validation if helper behavior drifts
  - reject any helper change that requires artifact contract renames or runtime-owned behavior to make the tests pass

## Boilerplate and clarity targets

- Remove duplicated selected-workflow identity checks from at least five workflow packages.
- Remove duplicated selected-workflow path-serialization tails from at least two stdlib modules.
- Reduce or eliminate repeated `_repo_root_from_context`, `_runtime_test_path`, and repo-relative path helper logic inside the selected-workflow helper family.
- Implementation closeout must report:
  - files added
  - files deleted
  - net line delta
  - repeated validation idioms removed
  - workflows changed to use shared helpers
  - new helper functions introduced or consolidated
  - old workflow-local validation blocks replaced
  - before/after readability for the touched workflow family

## Risk register

- Risk: helper extraction blurs compiled capability and editable authoring surfaces.
  - Control: keep three separate artifact products and assert their existing JSON contract shapes in tests.
- Risk: shared validators absorb domain-specific publication semantics.
  - Control: move only selected-workflow identity and structural validation; keep package-specific summary/receipt checks local.
- Risk: path serialization drift breaks refinement/decomposition baseline manifest logic.
  - Control: keep targeted refinement/decomposition runtime suites in the proof set and verify repo-relative path fields explicitly.
- Risk: new helper exports widen the public authoring surface unnecessarily.
  - Control: prefer internal reuse through existing stdlib modules; only re-export helpers that workflow modules must import directly.

## Deferred debt after this slice

- Keep local for now:
  - eval-suite case-count and case-kind rules
  - run-history evidence-window and severity rules
  - refinement evaluation-summary and overlay-proof rules
  - decomposition building-block-index and candidate-only publication checks
- Do not defer charter synchronization itself; only the doctrinal content may remain unchanged, and that no-change outcome still needs to be recorded during closeout.
- Revisit later only if repetition survives this slice:
  - portfolio and company snapshot validation convergence
  - broader publication-summary helper extraction for the portfolio-governance family
