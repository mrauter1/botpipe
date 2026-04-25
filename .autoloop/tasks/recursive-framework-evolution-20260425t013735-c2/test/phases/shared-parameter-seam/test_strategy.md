# Test Strategy

- Task ID: recursive-framework-evolution-20260425t013735-c2
- Pair: test
- Phase ID: shared-parameter-seam
- Phase Directory Key: shared-parameter-seam
- Phase Title: Shared Parameter Seam
- Scope: phase-local producer artifact

## Behavior-to-Test Coverage Map

- Shared task-framing bundles: cover required `task_title`, optional text trimming to `None`, deduped `constraints`, and deduped `evidence_expectations`.
- Shared selected-workflow bundles: cover required `selected_workflow` plus `task_title`, trimming, deduped repeatable fields, and generic non-empty failures.
- Positive-int composition with the seam: cover a seam subclass that adds a local positive-int validator so inherited text/list normalization still composes correctly.
- Workflow-specific subclasses over the seam: cover `workflow_and_eval_to_refined_workflow_package.Parameters` and `workflow_package_to_composable_building_blocks.Parameters` so local required-text validators do not shadow inherited selected-workflow/task-title normalization.

## Preserved Invariants Checked

- Runtime-owned parameter resolution behavior remains external to the seam; tests assert only model behavior.
- Workflow-local fields such as `evaluation_*_path`, `target_test_command`, and `evidence_paths` keep their local normalization and defaults.
- Order-sensitive `statuses` normalization remains workflow-local and is still covered by the existing runtime suite.

## Edge Cases

- Blank optional text normalizes to `None`.
- Duplicate repeatable strings collapse to one normalized value.
- Whitespace around required text is stripped before validation.

## Failure Paths

- Blank required task text fails.
- Blank selected-workflow text fails.
- Added positive-int fields on seam subclasses reject zero.
- Workflow-specific subclasses reject blank inherited required fields even when they also add their own required-text validators.

## Known Gaps

- No new flake risks introduced; coverage is pure model validation with deterministic inputs.
- The broader runtime compatibility surface is intentionally left to the existing targeted runtime suites already passing for this phase.
