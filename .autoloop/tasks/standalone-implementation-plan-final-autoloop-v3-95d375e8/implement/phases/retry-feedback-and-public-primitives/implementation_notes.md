# Implementation Notes

- Task ID: standalone-implementation-plan-final-autoloop-v3-95d375e8
- Pair: implement
- Phase ID: retry-feedback-and-public-primitives
- Phase Directory Key: retry-feedback-and-public-primitives
- Phase Title: Retry Feedback And Public Primitives
- Scope: phase-local producer artifact

## Files changed

- `core/providers/retries.py`
- `autoloop/simple.py`
- `autoloop/__init__.py`
- `tests/unit/test_provider_retries.py`
- `tests/unit/test_simple_surface.py`

## Symbols touched

- `build_retry_feedback`
- `_problem_summary`
- `autoloop.simple.__all__`
- `autoloop.__all__`
- public imports for `Event`, `Outcome`, `Checkpoint`, `ResolvedArtifacts`, `ChildWorkflowResult`

## Checklist mapping

- Plan milestone 1: completed for retry feedback specificity in `core/providers/retries.py`
- Plan milestone 1: completed for retry-feedback tests in `tests/unit/test_provider_retries.py`
- Plan milestone 1: completed for public primitive exports in `autoloop.simple` and `autoloop`
- Plan milestone 1: completed for public-surface identity/presence tests in `tests/unit/test_simple_surface.py`

## Assumptions

- This phase remains limited to retry feedback and public primitive exports; package deletion, rename fallout, docs, and strictness rewrites are left untouched for later phases.

## Preserved invariants

- Installed-package vs repo-root import fallback in `autoloop.simple` is unchanged; only additional imports were added to the existing pattern.
- Generic invalid-payload feedback still remains the fallback when no structured failure detail is present.
- No workflow-step execution behavior or handler generation logic was changed.

## Intended behavior changes

- Invalid route payload retry feedback now surfaces `_failure_context["error"]` and includes `_failure_context["route"]` when both are present.
- Retry guidance now explicitly tells providers how to repair `question`, `blocked`, and `failed` payloads.
- `autoloop` and `autoloop.simple` now both export `Event`, `Outcome`, `Checkpoint`, `ResolvedArtifacts`, and `ChildWorkflowResult`.

## Known non-changes

- The `workflow/` package still exists in this phase.
- No runtime loader/catalog renames were implemented in this phase.
- No docs or strictness files were edited in this phase.

## Expected side effects

- Public callers can import the runtime primitives directly from `autoloop` and `autoloop.simple`.
- Retry notes shown to providers become more specific for structured route-payload failures.

## Validation performed

- `.venv/bin/python -m pytest tests/unit/test_provider_retries.py`
- `.venv/bin/python -m pytest tests/unit/test_simple_surface.py`

## Deduplication / centralization

- Reused the existing `_failure_context_field(...)` helper rather than adding a new retry-detail extractor.
