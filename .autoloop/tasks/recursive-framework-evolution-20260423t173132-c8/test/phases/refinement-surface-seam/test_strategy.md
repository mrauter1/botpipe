# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c8
- Pair: test
- Phase ID: refinement-surface-seam
- Phase Directory Key: refinement-surface-seam
- Phase Title: Refinement Surface Seam
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Happy path:
- `write_selected_workflow_authoring_surface(...)` writes a workflow-local JSON snapshot for a selected workflow resolved by alias.
- The snapshot includes package files, nested prompt files, nested asset files, optional `params.py`, optional `contracts.py`, linked doc path, and inferred runtime-test path when present.
- The helper also accepts the selected workflow's main exported workflow class, preserving the shared workflow-resolution contract.

- Preserved invariants checked:
- Output stays under `ctx.workflow_folder`.
- The helper does not create a selected-workflow run/workspace or mutate the selected workflow surface.
- The helper continues to rely on shared workflow resolution and workflow-catalog seams.
- The helper remains separate from `selected_workflow_capability.json`, and the authoring docs keep prompt/runtime boundaries explicit.

- Edge cases:
- Optional authoring-surface files remain nullable when `params.py`, `contracts.py`, linked docs, or runtime tests are absent.
- Nested prompt and asset file inventories stay stable and sorted.

- Failure paths:
- Path escape via `../...` is rejected.
- Non-`.json` output paths are rejected.

## Validation run

- `.venv/bin/python -m pytest -q tests/unit/test_stdlib_and_extensions.py`
- `.venv/bin/python -m pytest -q tests/test_architecture_baseline_docs.py`

## Known gaps

- This phase does not add runtime execution tests because the seam is authoring-only and phase scope excludes refinement automation.
