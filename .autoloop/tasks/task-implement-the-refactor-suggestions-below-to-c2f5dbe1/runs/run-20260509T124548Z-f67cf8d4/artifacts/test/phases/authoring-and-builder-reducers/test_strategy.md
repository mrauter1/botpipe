# Test Strategy

- Task ID: task-implement-the-refactor-suggestions-below-to-c2f5dbe1
- Pair: test
- Phase ID: authoring-and-builder-reducers
- Phase Directory Key: authoring-and-builder-reducers
- Phase Title: Authoring And Builder Reducers
- Scope: phase-local producer artifact

## Behavior-to-coverage map

- Placeholder dispatcher parity:
  `tests/unit/test_placeholder_refs.py`
  `tests/unit/test_simple_surface.py`
  Covers shared validator success paths, exact error wording, branch/fan-in placement rules, and `artifacts.*` / `step.*` alias dispatch preservation.
- Artifact inventory builder parity:
  `tests/unit/test_inventory.py`
  Covers workflow-level artifact reuse, passive-artifact producer rebind, workflow/public-name conflict diagnostics, and duplicate qualified-name diagnostics.
- Compiled step rebuild parity:
  `tests/unit/test_step_plans.py`
  Covers prompt, produce/verify, python, child-workflow, and branch-group round trips plus nested branch parity failure handling.
- Route/inventory integration safety:
  `tests/unit/test_route_contracts.py`
  Covers route contract adaptation against collected inventory and normalized compiled-route round trips.
- Branch-group rendering parity:
  `tests/contract/test_branch_result_serialization.py`
  Covers current manifest/context shape, needs-input summary behavior, and empty-section fallback rendering for route/failure/input/cancellation summaries.

## Preserved invariants checked

- Placeholder validation remains centralized through `botlane/core/placeholders.py` and keeps exact authoring UX.
- Inventory traversal still preserves workflow-level ownership and producer ordering.
- Plan-adapter refactors preserve compiled-step field parity and branch-group nested-step reconstruction semantics.
- Branch-group context rendering preserves existing markdown content while keeping explicit `(none)` / `- None.` fallbacks.

## Edge cases and failure paths

- Unknown or ambiguous placeholders remain exact-match failures through existing unit coverage.
- Artifact inventory conflict diagnostics are asserted directly instead of only via broader workflow validation paths.
- Branch-group context with no route events and no failure/input/cancellation branches still renders the prior fallback text.

## Validation run

- `.venv/bin/python -m pytest tests/unit/test_placeholder_refs.py tests/unit/test_simple_surface.py tests/unit/test_inventory.py tests/unit/test_step_plans.py tests/unit/test_route_contracts.py tests/contract/test_branch_result_serialization.py`
- `.venv/bin/python -m compileall tests/contract/test_branch_result_serialization.py tests/unit/test_inventory.py tests/unit/test_placeholder_refs.py`

## Flake risk / stabilization

- All added coverage is deterministic and in-process only; no timing, network, or nondeterministic ordering dependencies were introduced.

## Known gaps

- This phase does not extend runtime engine or workflow-discovery lifecycle coverage because those refactors are explicitly out of scope.
