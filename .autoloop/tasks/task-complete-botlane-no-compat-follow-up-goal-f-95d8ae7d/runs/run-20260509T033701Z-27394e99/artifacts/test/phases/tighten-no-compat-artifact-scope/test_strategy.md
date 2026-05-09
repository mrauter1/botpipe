# Test Strategy

- Task ID: task-complete-botlane-no-compat-follow-up-goal-f-95d8ae7d
- Pair: test
- Phase ID: tighten-no-compat-artifact-scope
- Phase Directory Key: tighten-no-compat-artifact-scope
- Phase Title: Tighten Repo-Root Artifact No-Compat Enforcement
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Repo-root artifact policy stays explicit:
  `test_active_repo_root_artifact_policy_inventories_are_explicit`
  and
  `test_active_repo_root_artifact_policy_walks_exact_contract_files_even_without_scan_root_membership`
  lock the recursive-memory inventory, the active current-run inventory, and the separate artifact-policy walker.
- Maintained artifact files stay Botlane-clean outside exact exceptions:
  `test_active_repo_root_artifact_files_do_not_emit_removed_legacy_branding_outside_exact_operational_exceptions`
  scans the in-contract recursive-memory and current-run clean files.
- Legacy wrapper token regression is direct-tested:
  `test_text_branding_scanner_flags_expected_legacy_tokens`
  now asserts that `_text_emits_removed_legacy_branding(...)` catches the legacy recursive wrapper token while not flagging Botlane replacements.

## Preserved Invariants

- Maintained product-tree scanning still excludes repo-root artifact trees from `ACTIVE_SCAN_ROOTS` and `BRANDING_SCAN_ROOTS`; the additive artifact-policy walker is the enforcement seam.
- Exact current-run exceptions remain enumerated rather than broadened to prefix skips.

## Edge Cases

- Runtime-created phase session records remain allowed as explicit clean inventory entries.
- Reviewer-owned feedback may contain legacy tokens and is covered as an exact current-run exception.

## Failure Paths

- A new repo-root artifact file without an explicit policy update fails the inventory assertions.
- A legacy wrapper token dropped from `LEGACY_BRANDING_PATTERNS` now fails the direct helper regression test even if the broader integration inventory stays unchanged.

## Known Gaps

- Historical recursive task prompts remain exact exceptions rather than being rewritten; this phase only validates that the exception list stays exact.
