# Implementation Notes

- Task ID: task-complete-botlane-no-compat-follow-up-goal-f-95d8ae7d
- Pair: implement
- Phase ID: tighten-no-compat-artifact-scope
- Phase Directory Key: tighten-no-compat-artifact-scope
- Phase Title: Tighten Repo-Root Artifact No-Compat Enforcement
- Scope: phase-local producer artifact

## Files changed

- `tests/strictness/test_no_compat.py`
- `framework_evolution_charter.md`
- `framework_gap_ledger.md`
- `framework_roadmap.md`
- `rerun_command.sh`
- `decisions.txt`

## Symbols touched

- `ARTIFACT_POLICY_TEXT_SUFFIXES`
- `ACTIVE_RECURSIVE_TOP_LEVEL_ENTRIES`
- `ACTIVE_RECURSIVE_ARTIFACT_CONTRACT_PATHS`
- `EXPLICIT_RECURSIVE_ARTIFACT_EXCEPTION_PATHS`
- `ACTIVE_CURRENT_RUN_RELATIVE_ROOT`
- `ACTIVE_CURRENT_RUN_EXACT_EXCEPTION_PATHS`
- `ACTIVE_CURRENT_RUN_REQUIRED_CLEAN_PATHS`
- `_iter_repo_root_artifact_policy_files`
- `_artifact_tree_file_inventory`
- `_artifact_tree_top_level_entries`
- `LEGACY_BRANDING_PATTERNS`
- `_text_emits_removed_legacy_branding`

## Checklist mapping

- Close scanner-root loophole: added a dedicated repo-root artifact-policy walker plus inventory assertions.
- Enforce explicit artifact-tree policy: froze exact maintained files and exact exception inventories for recursive memory and the active run tree.
- Remove remaining legacy literals from maintained recursive memory: cleaned the charter, gap ledger, roadmap, and rerun command.
- Keep historical allowance narrow: left only exact seed, recovery, lock, archived task-prompt, and current-run operational-record exceptions.
- Add regression coverage: added inventory and branding assertions that fail on new unreviewed files or legacy literals outside the exact exceptions.

## Assumptions

- The bootstrap seed, recovery state, lock pid, and archived recursive task prompts are historical or runtime-owned records that should stay frozen rather than rewritten in place.
- The active run's request/log/plan records remain exact operational exceptions because they are authoritative run artifacts, not maintained product docs.

## Preserved invariants

- No runtime, provider, CLI, overlay, or workflow behavior changed.
- Maintained product-tree scanning still uses the existing roots; repo-root artifact enforcement is additive and explicit.

## Intended behavior changes

- Strictness now treats repo-root recursive-memory files and the clean slice of the active run tree as in-contract content.
- New files under the recursive-memory tree or the active run tree must be either clean and inventoried or added as exact reviewed exceptions.

## Known non-changes

- Historical task/run records outside the exact active run slice were not rewritten.
- The repo-root recursive-memory directory name and repo-local state-root layout were not renamed in this phase.

## Expected side effects

- Inventory drift under the recursive-memory tree or the active run tree now fails the strictness suite until the explicit policy is updated.
- Legacy-branding regressions in maintained recursive-memory docs now fail even though those trees are still outside the maintained product root tuples.

## Validation performed

- `./.venv/bin/python -m pytest tests/strictness/test_no_compat.py`
- literal legacy-name scan across the maintained product tree plus the in-contract recursive-memory and active-run files
- `./.venv/bin/python -m pytest`

## Deduplication / centralization

- Centralized literal branding detection through `LEGACY_BRANDING_PATTERNS` and `_text_emits_removed_legacy_branding(...)`.
- Centralized repo-root artifact coverage through `_iter_repo_root_artifact_policy_files(...)` instead of scattering one-off assertions.
