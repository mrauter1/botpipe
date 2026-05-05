# Test Strategy

- Task ID: goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6
- Pair: test
- Phase ID: reconcile-optimizer-source-contracts
- Phase Directory Key: reconcile-optimizer-source-contracts
- Phase Title: Reconcile Optimizer Source Contracts
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Observability schema migration and eligible-run preservation
  - Covered by `tests/unit/test_optimization_helpers.py`
  - Verifies schemaless `run.json`, `trace.jsonl`, `git_tracking.jsonl`, and `static_step_graph.json` are accepted while explicit unsupported schema IDs still fail.
  - Verifies eligible runs remain counted even when route filters match no steps, and runtime-control / question routes remain distinct.

- Canonical selected-workflow manifest labels
  - Covered by `test_write_selected_workflow_source_manifest_normalizes_alias_to_canonical_workflow_name`
  - Verifies first-party workflow aliases normalize to canonical `autoloop/workflows/<workflow>` package labels.

- Canonical labels must not mutate repo-local sources
  - Covered by `test_write_selected_workflow_source_manifest_does_not_materialize_canonical_repo_tree`
  - Verifies manifest capture stays read-only and does not create `autoloop/workflows/...` in temp repos that only contain `workflows/...`.

- Canonical labels must still hash actual selected-source bytes
  - Covered by `test_write_selected_workflow_source_manifest_records_hashes`
  - Covered by `test_write_selected_workflow_source_manifest_uses_repo_local_bytes_under_canonical_first_party_labels`
  - Verifies manifest entries keep canonical labels while hashing the selected repo-local file contents.

- Mutation detection against the selected source
  - Covered by `test_validate_selected_workflow_source_unchanged_detects_mutation`
  - Runtime publication seam additionally covered by `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py -k selected_workflow_source_changed`
  - Verifies downstream manifest comparison fails when the selected repo-local source changes after capture.

## Preserved Invariants Checked

- No legacy schema-ID broadening beyond supported schemaless v1 payloads.
- Route-tag normalization keeps runtime-control and question behavior distinct.
- First-party canonical manifest labels remain stable even when the selected source resolves from repo-local `workflows/...`.

## Edge Cases / Failure Paths

- Schemaless legacy observability payloads.
- Explicit unsupported schema IDs.
- Route filter with zero matching observations.
- Selected-source mutation after manifest capture.
- Temp repos with only repo-local `workflows/...` copies and no `autoloop/workflows/...` tree.

## Flake / Stability Notes

- Tests use temp directories and direct file edits only; no timing, network, or nondeterministic ordering dependencies.

## Known Gaps

- Full optimizer runtime file still has unrelated out-of-phase packaged-workflow failures (`blocked` / `failed` route contracts and missing framework artifacts), so this phase validates the selected-workflow mutation path with a targeted runtime test rather than the full runtime suite.
