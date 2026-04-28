# Test Strategy

- Task ID: standalone-implementation-plan-final-autoloop-v3-95d375e8
- Pair: test
- Phase ID: retry-feedback-and-public-primitives
- Phase Directory Key: retry-feedback-and-public-primitives
- Phase Title: Retry Feedback And Public Primitives
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Retry feedback specificity:
  `tests/unit/test_provider_retries.py::test_build_retry_feedback_formats_specialized_retry_messages`
  covers generic retry kinds plus route-specific `invalid_payload` summaries for `question` and `failed`, and asserts the expanded repair guidance bullets.
- Retry feedback edge/fallback behavior:
  `tests/unit/test_provider_retries.py::test_build_retry_feedback_invalid_payload_without_route_still_surfaces_specific_error`
  covers detail-without-route formatting, and
  `tests/unit/test_provider_retries.py::test_build_retry_feedback_falls_back_to_exception_message_or_step_name`
  preserves non-provider fallback messaging.
- Public primitive export presence:
  `tests/unit/test_simple_surface.py::test_autoloop_simple_exports_requested_public_authoring_surface`
  asserts the root `autoloop` surface exposes the requested primitives and existing public names.
- Public primitive identity across surfaces:
  `tests/unit/test_simple_surface.py::test_autoloop_public_primitives_match_autoloop_simple_surface`
  pins identity between `autoloop` and `autoloop.simple` for all five primitives.
- Import-mode regression coverage:
  `tests/unit/test_simple_surface.py::test_autoloop_simple_imports_in_installed_package_mode`
  and
  `tests/unit/test_simple_surface.py::test_autoloop_simple_imports_with_repo_root_fallback_only`
  exercise the existing installed-package / repo-root import split and now also assert root-surface re-export identity for the new primitives.

## Preserved invariants checked

- Generic invalid-payload feedback remains the fallback when no structured error detail exists.
- `autoloop.simple` remains importable in both installed-package and repo-root modes.
- `autoloop` re-exports remain aliases of the `autoloop.simple` primitive objects rather than wrappers or copies.

## Edge cases and failure paths

- `invalid_payload` with route and detail.
- `invalid_payload` with detail but no route.
- Blank exception message fallback for non-specialized errors.

## Flake-risk assessment

- No timing, network, or nondeterministic ordering dependencies were added.
- The import-mode probe uses a temporary copied package tree and explicit `PYTHONPATH`, which keeps setup isolated and deterministic.

## Known gaps

- This phase does not test later out-of-scope cleanup work such as `workflow/` deletion, rename fallout, docs, or strictness rewrites.
