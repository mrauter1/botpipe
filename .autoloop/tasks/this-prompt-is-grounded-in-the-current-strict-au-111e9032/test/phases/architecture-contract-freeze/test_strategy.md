# Test Strategy

- Task ID: this-prompt-is-grounded-in-the-current-strict-au-111e9032
- Pair: test
- Phase ID: architecture-contract-freeze
- Phase Directory Key: architecture-contract-freeze
- Phase Title: Freeze The Book Architecture Contract
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Architecture contract freeze:
  - `ARCHITECTURE_DECISIONS.md` must keep three-candidate matrices with explicit decision/book-choice/losing-option structure.
  - ADR summaries must stay final-form, summary-only, and point back to the authoritative architecture record.
- Strict-surface docs:
  - README + architecture + authoring docs must freeze the canonical public symbols, `Workflow.extensions`, tiny `stdlib`, and tiny `extensions`.
  - Active surface docs must not reintroduce `workflow.observers` or broad root imports such as `Engine` / `compile_workflow`.
- Retained compatibility note:
  - `docs/compatibility.md` must stay narrow and operational, covering `thread_id`, `superloop.*`, and the absence of a workflow compatibility layer.
- Legacy-name confinement:
  - Removed legacy names (`workflow.compat`, `workflow.observers`, `SessionLifecycle`, `Verdict`, `on_verdict`) may appear in migration/compatibility material, and may be discussed in the full candidate-matrix architecture record, but not in public-facing docs or ADR summaries.

## Preserved Invariants Checked

- Doc baseline remains deterministic and filesystem-only.
- ADR archive remains stable at the expected 14 files.
- Shared decisions about narrow retained compatibility and extension-based architecture are encoded in tests.

## Edge Cases / Failure Paths

- Fails if a future doc edit reintroduces observer-era or compatibility-era names into README, architecture docs, authoring docs, parity docs, risk docs, or ADR summaries.
- Fails if compatibility notes expand into plugin/workspace-hook/second-execution-model language.
- Fails if the architecture record drifts away from the required candidate-matrix format.

## Validation Performed

- `pytest autoloop_v3/tests/test_architecture_baseline_docs.py`

## Flake Risk / Stabilization

- No network, time, or ordering dependencies.
- Tests read fixed repository files only and assert exact presence/absence markers.

## Known Gaps

- This phase validates the documentation contract only; it does not prove the runtime/kernel implementation matches the frozen docs yet.
