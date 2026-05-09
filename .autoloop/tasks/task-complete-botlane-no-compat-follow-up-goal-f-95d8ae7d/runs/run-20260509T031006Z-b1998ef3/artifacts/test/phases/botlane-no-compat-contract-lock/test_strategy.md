# Test Strategy

- Task ID: task-complete-botlane-no-compat-follow-up-goal-f-95d8ae7d
- Pair: test
- Phase ID: botlane-no-compat-contract-lock
- Phase Directory Key: botlane-no-compat-contract-lock
- Phase Title: Lock Botlane-Only Contract
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Overlay state exclusion:
  `tests/unit/optimizer/test_candidate_surfaces.py::test_candidate_surface_overlay_does_not_copy_botlane_runtime_state`
  Covers the happy path where `validate_candidate_surface_overlay(...)` copies the actual overlay source root, excludes `.botlane`, preserves candidate workflow patching, and still executes the validation command from the overlay cwd.
- Hidden legacy-name construction detection:
  `tests/strictness/test_no_compat.py::test_hidden_legacy_construction_scanner_flags_split_string_patterns`
  Covers split-string, adjacent-literal, join-based, and f-string reconstruction of `autoloop`, `Autoloop`, `AUTOLOOP`, `.autoloop`, `autoloop_optimizer`, `_autoloop_workspace_workflows`, and the old simple-flow sentinel.
- Preserved Botlane-only runtime/package surface:
  `tests/strictness/test_no_compat.py::test_supported_package_imports_succeed`
  `tests/strictness/test_no_compat.py::test_removed_legacy_package_names_are_not_importable`
  `tests/strictness/test_no_compat.py::test_removed_legacy_module_entrypoint_is_unavailable`
  `tests/strictness/test_no_compat.py::test_installed_console_scripts_expose_botlane_only`
  `tests/strictness/test_no_compat.py::test_botlane_help_succeeds_without_legacy_branding`
  Covers positive `botlane`/`botlane_optimizer` imports, negative legacy imports and `python -m autoloop`, Botlane-only console scripts, and Botlane help output without Autoloop branding.
- Preserved legacy rejection behavior:
  Existing strictness tests continue to cover `.autoloop/workflows` rejection, `.botlane/workflows` acceptance, old simple-flow sentinel rejection, new simple-flow sentinel acceptance, and explicit `autoloop.operation_replay/*` schema rejection.
- Adjacent runtime precedence regression:
  `tests/runtime/test_workflow_reference_resolution.py`
  `tests/runtime/test_workflow_catalog_roots.py`
  Covers the preserved invariant that bare workflow-name resolution prefers `.botlane/workflows` while explicit repo-local `workflows/...` references remain reachable.

## Preserved invariants checked

- Literal legacy names stay confined to `tests/strictness/test_no_compat.py` plus the audited `legacy_docs/*.md` allowlist.
- Production Python under `botlane/` and `botlane_optimizer/` does not reconstruct legacy Autoloop identifiers indirectly.
- Active persisted schema identifiers remain `botlane.*` only and explicit `autoloop.*` schema strings remain unsupported.

## Edge cases and failure paths

- Repo-local environments without an installed sibling `botlane` script still exercise the same help surface through `python -m botlane.runtime.cli --help`.
- The overlay regression asserts against the copied overlay while the temporary directory still exists, avoiding flake from post-cleanup filesystem checks.
- Hidden-construction fixtures include both direct and multi-step constant-building patterns so the scanner does not rely on literal grep hits alone.

## Known gaps

- No new packaging-specific fixture was added beyond the existing console-script and wheel smoke coverage, because the current strictness and runtime suites already cover the requested Botlane-only import/CLI contract.
- The full suite still emits one unrelated warning in `tests/unit/test_provider_boundary_core.py`; it is outside this phase scope and not normalized by new expectations here.
