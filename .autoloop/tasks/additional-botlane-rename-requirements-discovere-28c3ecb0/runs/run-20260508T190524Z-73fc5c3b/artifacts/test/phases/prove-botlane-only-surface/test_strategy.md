# Test Strategy

- Task ID: additional-botlane-rename-requirements-discovere-28c3ecb0
- Pair: test
- Phase ID: prove-botlane-only-surface
- Phase Directory Key: prove-botlane-only-surface
- Phase Title: Prove Botlane Only Surface
- Scope: phase-local producer artifact

## Behavior-to-test map
- P4-AC1 / Botlane install surface:
  Covered by `tests/runtime/test_wheel_packaging_smoke.py::test_built_wheel_installs_public_botlane_package_and_cli`.
  Checks wheel contents, installed `botlane` console script, Botlane-only help text, missing `autoloop` console script, failed `import autoloop`, failed `import autoloop_optimizer`, and failed `python -m autoloop`.
- P4-AC2 / Live-tree branding gate:
  Covered by `tests/strictness/test_no_compat.py::test_removed_compatibility_scan_scope_covers_maintained_tree_only`, `test_explicit_history_allowlist_matches_legacy_docs_inventory`, `test_branding_scan_walks_repo_root_and_skips_only_explicit_history_files`, and `test_product_tree_docs_and_fixtures_do_not_emit_removed_legacy_branding`.
  Checks maintained-scan roots, explicit `legacy_docs/*.md` history allowlist inventory, repo-root branding scan coverage, generated-state exclusions, and no legacy branding outside the allowlist.
- P4-AC3 / New writes Botlane-only while old reads stay compatible:
  Covered by `tests/runtime/test_workspace_and_context.py::test_run_creates_task_workflow_run_layout_and_immutable_request_snapshots`, `test_run_metadata_records_topology_hashes_and_artifact_contract_paths`, and existing legacy-read compatibility tests such as `test_list_run_records_reads_legacy_state_root_when_botlane_root_is_absent` and `test_resume_without_run_id_uses_latest_run_across_botlane_and_legacy_state_roots`.
  Checks `.botlane` write paths, `botlane.*` schemas for new outputs, and preserved legacy `.autoloop` read behavior.

## Edge cases and failure paths
- Adding or removing a `legacy_docs/*.md` file without updating the explicit history allowlist fails `test_explicit_history_allowlist_matches_legacy_docs_inventory`.
- Narrowing the branding scan away from repo root or accidentally scanning allowed historical files fails `test_branding_scan_walks_repo_root_and_skips_only_explicit_history_files`.
- Reintroducing legacy package paths, scripts, or help text in the built wheel fails the wheel smoke test.

## Preserved invariants
- Legacy workspace/config/artifact readers remain test-covered and are not normalized away by the Botlane-only write assertions.
- The strictness proof file itself continues to avoid embedding live legacy-brand tokens directly; it constructs compatibility tokens from fragments.

## Stability notes
- Coverage is deterministic: local filesystem only, no network calls, fixed temp dirs, and explicit wheel/venv setup.
- The wheel smoke test is the slowest slice because it builds a wheel and venv; the strictness suite is otherwise fast and file-driven.

## Known gaps
- No broad full-suite rerun was added in this phase.
- The existing `MANIFEST.in` glob auditability concern remains advisory and is not encoded as a failing test.
