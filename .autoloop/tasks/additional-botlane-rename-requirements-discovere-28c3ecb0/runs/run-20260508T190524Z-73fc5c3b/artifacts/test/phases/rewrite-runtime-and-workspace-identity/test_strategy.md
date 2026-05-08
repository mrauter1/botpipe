# Test Strategy

- Task ID: additional-botlane-rename-requirements-discovere-28c3ecb0
- Pair: test
- Phase ID: rewrite-runtime-and-workspace-identity
- Phase Directory Key: rewrite-runtime-and-workspace-identity
- Phase Title: Rewrite Runtime And Workspace Identity
- Scope: phase-local producer artifact

## Coverage Map

- P2-AC1 CLI/runtime identity:
  `tests/runtime/test_package_cli.py`
  Covers Botlane parser `prog`, top-level help branding, run-command workspace/package help text, and absence of `autoloop` in surfaced CLI help.

- P2-AC2 workspace/generated identity:
  `tests/runtime/test_workflow_catalog_roots.py`
  Covers workflow search-root ordering, `.botlane/workflows` preference over `.autoloop/workflows`, package namespace metadata, and `_botlane_workspace_workflows` import isolation.
  `tests/runtime/test_workspace_and_context.py`
  Covers `.botlane` task/run metadata, legacy `.autoloop` run discovery, and mixed-root resume selection.

- P2-AC3 legacy read compatibility:
  `tests/runtime/test_provider_policy_config.py`
  Covers workspace config fallback from `botlane.yaml` to legacy `autoloop.yaml`, global config fallback from Botlane config dir to legacy autoloop config dir, and canonical Botlane precedence when both exist.
  `tests/unit/test_sdk_facade.py`
  Covers SDK cleanup reading legacy `.autoloop` task roots and legacy `.autoloop-sdk-task.json` sentinels while keeping Botlane schema ownership.

## Preserved Invariants

- New writes remain Botlane-only: `.botlane`, `botlane.yaml`, Botlane CLI/help text, and Botlane workflow namespace.
- Legacy inputs remain readable only as fallback/migration inputs and never outrank canonical Botlane workspace/config roots.

## Edge Cases And Failure Paths

- Duplicate workflow names across `.botlane` and `.autoloop` roots resolve to the Botlane root.
- Resume without explicit `--run-id` selects the latest readable run across both state roots.
- Legacy global config is consumed only when the canonical Botlane global config is absent.

## Known Gaps

- This environment may still lack `pytest` or runtime dependencies, so execution validation can be narrower than the authored coverage map. Static compile checks remain the fallback when that occurs.
