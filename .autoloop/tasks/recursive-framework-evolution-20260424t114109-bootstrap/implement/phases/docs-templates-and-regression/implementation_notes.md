# Implementation Notes

- Task ID: recursive-framework-evolution-20260424t114109-bootstrap
- Pair: implement
- Phase ID: docs-templates-and-regression
- Phase Directory Key: docs-templates-and-regression
- Phase Title: Docs, Templates, And Regression Sweep
- Scope: phase-local producer artifact

## Files changed

- `docs/architecture.md`
- `docs/authoring.md`
- `docs/workflows/security_finding_to_verified_remediation.md`
- `.autoloop_recursive/framework_evolution_charter.md`
- `.autoloop_recursive/framework_roadmap.md`
- `workflows/release_candidate_to_go_no_go/prompts/frame_producer.md`
- `workflows/workflow_idea_to_workflow_package/prompts/frame_producer.md`
- `workflows/investigation_request_to_evidence_pack/prompts/frame_producer.md`
- `workflows/incident_to_hardening_program/prompts/frame_producer.md`
- `tests/test_architecture_baseline_docs.py`
- `tests/runtime/test_package_cli.py` (validated, no content change in this turn)
- `tests/contract/test_engine_contracts.py`
- `tests/runtime/test_workflow_reference_resolution.py`
- `tests/strictness/test_no_compat.py`
- `.autoloop/tasks/recursive-framework-evolution-20260424t114109-bootstrap/decisions.txt`

## Symbols touched

- Recursive-memory baselines: `framework_evolution_charter.md`, `framework_roadmap.md`
- Baseline/strictness tests: `test_recursive_memory_files_capture_current_framework_contracts`, `test_active_tree_does_not_reintroduce_removed_compatibility_surfaces`
- Regression expectations: `test_declared_extensions_bind_once_per_run_in_tuple_order`, `test_named_references_fail_when_inferred_candidates_conflict`

## Checklist mapping

- Plan phase 4: canonical docs refreshed for the flexible authoring doctrine.
- Plan phase 4: recursive-memory baseline/docs assertions aligned with package-CLI and flow-first wording.
- Plan phase 4: targeted suites run before the full regression sweep.
- Plan phase 4: full test suite rerun and passing.

## Assumptions

- Historical cycle outcome notes in `.autoloop_recursive/framework_roadmap.md` should stay intact even when current seams/milestones are refreshed.
- Provider-native `thread_id` handling remains an internal adapter concern, not a public compatibility surface.

## Preserved invariants

- Root `workflow` shim stayed strict; no runtime/compiler internals were documented or exported.
- `workflow.toml` remained documented as metadata-only.
- Canonical public CLI stayed name/message oriented with optional file/module refs through the unified resolver.
- Recursive wrappers kept the stable package-CLI contract.

## Intended behavior changes

- Canonical docs now say `flow.py` + `specs.py` is recommended, not required, and explicitly preserve single-file plus mature-package authoring.
- Recursive-memory baselines no longer describe wrapper/template drift as an active open issue.
- Prompt guidance now avoids spelling the retired repo-layout token literally while still warning against old layouts.
- Regression tests now match the shipped snake_case unnamed workflow fallback, duplicate-name discovery error, and internal-provider strictness exception.

## Known non-changes

- `legacy_docs/` was not removed or synchronized in this phase.
- Historical roadmap cycle entries that described earlier wrapper drift were left as historical record.
- No runtime/CLI behavior changes were introduced in this phase beyond regression-test expectation alignment.

## Expected side effects

- Baseline docs/tests now reflect the current flow-first authoring contract instead of preserving stale package-only or wrapper-drift claims.
- Strictness scanning remains aggressive on public/authoring surfaces without flagging legitimate provider-native adapter internals.

## Validation performed

- Targeted: `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py tests/runtime/test_package_cli.py`
- Regression fixes: `.venv/bin/pytest -q tests/contract/test_engine_contracts.py::test_declared_extensions_bind_once_per_run_in_tuple_order tests/runtime/test_workflow_reference_resolution.py::test_named_references_fail_when_inferred_candidates_conflict tests/strictness/test_no_compat.py::test_active_tree_does_not_reintroduce_removed_compatibility_surfaces tests/test_architecture_baseline_docs.py tests/runtime/test_package_cli.py`
- Full suite: `.venv/bin/pytest -q`

## Deduplication / centralization decisions

- Kept the strictness allowance narrow and token-specific instead of weakening repo-wide scan scope.
- Updated recursive-memory current-state prose instead of encoding stale wrapper drift in tests.
