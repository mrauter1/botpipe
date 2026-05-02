# Test Strategy

- Task ID: below-is-the-full-standalone-remaining-delta-imp-45eb54ef
- Pair: test
- Phase ID: enforce-repo-compatibility-gate
- Phase Directory Key: enforce-repo-compatibility-gate
- Phase Title: Enforce Repo Compatibility Gate
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- AC-1 compile gate: `tests/runtime/test_workflow_integration_parity.py::test_all_repo_workflow_packages_resolve_and_compile_under_canonical_simple_surface`
  Confirms discovered exported workflows compile with zero tolerated failures.
- Canonical autoloop-v1 parity session surface: `test_copied_autoloop_v1_runs_without_repo_root_on_syspath` and `test_autoloop_v1_runs_through_general_runtime_and_preserves_package_local_sidecars`
  Confirms parity assertions use workflow-owned session paths (`plan.json`, `phases/<phase>.json`) and preserve package-local sidecars.
- Normalized resume clarification path: `test_autoloop_v1_parity_persists_clarifications_on_resume_without_a_custom_runner`
  Confirms resumed runs read `checkpoint.pending_input.question`, repopulate decisions/raw logs, and persist the clarification note on the canonical plan session payload.
- Legacy checkpoint fallback edge case: `test_autoloop_v1_parity_resume_clarification_falls_back_to_legacy_pending_question_checkpoint`
  Seeds a legacy `pending_question` checkpoint and directly invokes the parity extension `before_step` hook to verify backward-compatible clarification extraction without normalizing an unsupported engine resume path.
- AC-2 raw exported-workflow contract audit: `tests/unit/test_simple_surface.py`
  Covers one-argument hook/python-step declarations and banned hook state-return source snippets across discovered exported workflows.

## Preserved invariants checked
- No reintroduction of compile failures for discovered exported workflows.
- No reliance on legacy duplicate `*_session.json` parity aliases.
- No legacy continuation/thread id fields reappear in parity payloads or raw logs.

## Edge cases / failure paths
- Legacy checkpoint payloads that still carry `pending_question`.
- Resume clarification persistence writes both decision-log and session-note side effects.

## Flake risks / stabilization
- Filesystem-only tests use `tmp_path`, copied local workflow packages, and `ScriptedLLMProvider`; no network or timing dependencies are introduced.

## Known gaps
- The full affected workflow-suite sweep remains covered by the implementation-phase validation command set rather than duplicated here in another long-running test invocation.
