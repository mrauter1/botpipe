# Test Strategy

- Task ID: recursive-framework-evolution-20260423t173132-c10
- Pair: test
- Phase ID: portfolio-health-snapshot-seam
- Phase Directory Key: portfolio-health-snapshot-seam
- Phase Title: Portfolio Health Snapshot Seam
- Scope: phase-local producer artifact

## Behavior coverage map

- Shared grouped run-summary seam:
  `tests/runtime/test_workspace_and_context.py::test_workspace_lists_grouped_workflow_run_summaries_with_deterministic_filters`
  Covers grouped per-workflow counts, deterministic ordering, bounded recent-run excerpts, zero-run requested workflows, and one-shot iterable `statuses` input.
- Workflow-local portfolio health helper:
  `tests/unit/test_stdlib_and_extensions.py::test_portfolio_health_helper_writes_grouped_workflow_run_health_via_shared_resolution_and_run_summaries`
  Covers shared workflow resolution, read-only run-summary reuse, generator-backed `statuses`, zero-run selected workflows, non-importing unrelated workflow packages, and no source/run-state mutation.
- Authoring-boundary docs:
  `tests/unit/test_stdlib_and_extensions.py::test_authoring_doc_describes_additive_portfolio_health_snapshot_helper_boundary`
  Covers no governance scoring, no hidden downstream execution, and the workflow-local write boundary.

## Preserved invariants checked

- Writes stay under `ctx.workflow_folder`.
- The seam remains read-only against `.autoloop` run state and workflow packages.
- Output ordering and status normalization stay deterministic.
- The helper remains lighter than the run-history diagnostic seam.

## Edge cases

- One-shot generator input for `statuses` at both the stdlib helper and runtime summary layers.
- Selected/current workflows with zero matching runs still emit zero-count entries.
- Duplicate status filters normalize to a sorted deduplicated list.

## Failure paths

- Escaping `ctx.workflow_folder` via relative paths is rejected.
- Non-`.json` output paths are rejected.
- Blank status entries and non-positive run limits are rejected.
- Empty `workflows` selections are rejected.

## Flake risk / stabilization

- All coverage uses filesystem-only fixtures under `tmp_path`; no network, clock sleeps, or nondeterministic ordering.
- Ordering-sensitive assertions use fixed timestamps and explicit expected sort order.

## Known gaps

- No dedicated test yet for a workflow filter generator; current coverage exercises generator-backed `statuses`, which was the concrete regression path reviewed and fixed.
