# Test Strategy

- Task ID: recursive-framework-evolution-20260423t150056-c1
- Pair: test
- Phase ID: release-go-no-go-package
- Phase Directory Key: release-go-no-go-package
- Phase Title: Ship Release Go No-Go Workflow
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Discovery and package metadata:
  covered by `test_repo_workflows_namespace_discovers_release_go_no_go_package`
  checks canonical package discovery, manifest path, and alias registration.
- Explicit workflow contract compilation:
  covered by `test_release_go_no_go_package_compiles_with_explicit_control_contracts`
  checks step order, entry step, legal routes, and normalized typed `route_contracts`.
- Workflow-local documentation contract:
  covered by `test_release_go_no_go_package_docs_capture_decision_records`
  checks the shipped workflow doc retains the required decision-record and contract sections.
- Public parameter validation and normalization:
  covered by `test_release_go_no_go_package_rejects_blank_release_name`
  and `test_release_go_no_go_package_normalizes_repeatable_evidence_paths`
  checks the required parameter failure path plus trimming, blank filtering, and deduplication for repeatable `evidence_paths`.
- End-to-end happy path:
  covered by `test_release_go_no_go_package_runs_and_emits_terminal_receipt`
  checks scripted-provider route flow, artifact creation, invocation contract contents, decision summary contents, and deterministic receipt publication.
- Deterministic publish failure path:
  covered by `test_release_go_no_go_publish_decision_rejects_missing_recommendation`
  checks the system publish step refuses malformed `decision_summary.json` content and does not emit a receipt.

## Preserved invariants checked

- Runtime-injected control data stays limited to `expected_output_schema`, `available_routes`, and `route_contracts`.
- The new package remains discoverable without changing the package loader contract.
- Publication still depends on authoritative artifacts rather than free-form provider prose.

## Edge cases

- Repeatable workflow parameter input with whitespace, duplicates, and blank entries in `evidence_paths`.
- Publish-step behavior when the authoritative JSON summary omits the final recommendation.

## Failure paths

- Blank `release_name` input is rejected through workflow parameter validation.
- `publish_decision` raises when `decision_summary.json` is missing `recommended_decision`, preventing a false-success receipt.

## Flake risk / stabilization

- Tests are filesystem-local and use `tmp_path` plus `ScriptedLLMProvider` or direct system-step invocation.
- Module-cache isolation is enforced through `_clear_workflow_modules()` and the autouse fixture to avoid cross-test package import leakage.

## Commands exercised

- `.venv/bin/pytest -q tests/runtime/test_release_candidate_to_go_no_go.py tests/runtime/test_workflow_builder_package.py tests/unit/test_validation.py tests/contract/test_engine_contracts.py`

## Known gaps

- Recursive-memory baseline coverage remains outside this phase and is handled by the later closeout work; this phase does not try to normalize that unrelated docs residual.
