# Test Strategy

- Task ID: recursive-framework-evolution-20260427t121046-c2
- Pair: test
- Phase ID: selected-workflow-helper-convergence
- Phase Directory Key: selected-workflow-helper-convergence
- Phase Title: Shared Selected-Workflow Seam
- Scope: phase-local producer artifact

## Behaviors covered

- Shared seam resolves one selected workflow, captures `selected_workflow_name`, and writes the shared top-level envelope once for helper consumers.
- Rebased public helpers preserve the existing top-level payload keys for:
  - capability snapshots
  - validated parameter snapshots
  - authoring-surface snapshots
  - decomposition-surface snapshots
  - run-history snapshots

## Preserved invariants checked

- Artifact filenames remain unchanged.
- Top-level JSON schemas remain unchanged.
- Public helper entrypoints remain stable while delegating to the private seam.
- Shared capture can be reused across multiple artifact writes without another workflow resolution.

## Edge cases

- Selected workflow references still work through aliases and single-file workflow paths.
- Run-history snapshot filtering still preserves normalized status ordering and max-run slicing.

## Failure paths

- Workflow-local JSON path validation still rejects path escape attempts and non-`.json` suffixes.
- Parameter validation still rejects unknown workflow parameters through the shared loader coercion path.

## Validation run

- `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py`

## Known gaps

- Workflow capture-step simplification is intentionally out of scope for this phase; runtime workflow migration proof remains covered by the implementation phase validation rather than new test-author changes here.
