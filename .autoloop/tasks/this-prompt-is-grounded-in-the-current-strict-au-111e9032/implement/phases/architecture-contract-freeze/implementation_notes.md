# Implementation Notes

- Task ID: this-prompt-is-grounded-in-the-current-strict-au-111e9032
- Pair: implement
- Phase ID: architecture-contract-freeze
- Phase Directory Key: architecture-contract-freeze
- Phase Title: Freeze The Book Architecture Contract
- Scope: phase-local producer artifact

## Files Changed

- `autoloop_v3/ARCHITECTURE_DECISIONS.md`
- `autoloop_v3/README.md`
- `autoloop_v3/MIGRATION.md`
- `autoloop_v3/docs/architecture.md`
- `autoloop_v3/docs/authoring.md`
- `autoloop_v3/docs/compatibility.md`
- `autoloop_v3/docs/parity-matrix.md`
- `autoloop_v3/docs/risk-register.md`
- `autoloop_v3/docs/adr/001-package-module-layout.md`
- `autoloop_v3/docs/adr/002-workflow-compilation-model.md`
- `autoloop_v3/docs/adr/003-topology-routing-representation.md`
- `autoloop_v3/docs/adr/004-artifact-registry-and-resolution.md`
- `autoloop_v3/docs/adr/005-checkpoint-persistence-model.md`
- `autoloop_v3/docs/adr/006-session-binding-model.md`
- `autoloop_v3/docs/adr/007-provider-protocol-design.md`
- `autoloop_v3/docs/adr/008-compatibility-strategy.md`
- `autoloop_v3/docs/adr/009-handler-dispatch-and-signature-adaptation.md`
- `autoloop_v3/docs/adr/010-resume-answer-injection.md`
- `autoloop_v3/docs/adr/011-validation-architecture.md`
- `autoloop_v3/docs/adr/012-event-and-logging-model.md`
- `autoloop_v3/docs/adr/013-cli-and-runtime-harness-layout.md`
- `autoloop_v3/docs/adr/014-testing-strategy.md`
- `autoloop_v3/tests/test_architecture_baseline_docs.py`

## Symbols / Concepts Touched

- `Workflow.extensions`
- `WorkflowExtension`, `BoundWorkflowExtension`
- `GitTracking`
- `SessionPaths`
- `Tracing`
- `autoloop_v3.stdlib`
- `autoloop_v3.extensions`
- `run_autoloop_v1(...)`
- `autoloop_v3.workflows.autoloop_v1_conventions`
- `autoloop_v3.workflows.autoloop_v1_parity`

## Checklist Mapping

- Plan Milestone 1 / "Freeze The Architecture Contract": completed for architecture record, README, migration guidance, architecture docs, authoring docs, parity docs, risk docs, ADR summaries, and doc-baseline tests.
- No checklist item was intentionally deferred within this phase scope.

## Assumptions

- This phase is allowed to freeze the final requested architecture in docs before later code phases implement every API exactly.
- `docs/compatibility.md` remains useful only as a narrow retained-compatibility note, not as a second architecture document.

## Preserved Invariants

- No engine, runtime, workflow, or parity behavior was intentionally changed in this phase.
- The runtime remains documented as workflow-agnostic.
- Autoloop-v1 parity remains documented as workflow-owned.

## Intended Behavior Changes

- Architecture docs now treat `workflow` as the strict kernel, `runtime` as generic, `stdlib` as tiny authoring sugar, and `extensions` as explicit opt-in modules.
- Observer-era documentation was removed as the active execution/extension model.
- The doc baseline test now enforces the final extension-based contract instead of the old observer-based wording.

## Known Non-Changes

- No runtime or engine implementation was refactored in this phase.
- No workflow source was modified.
- `docs/compatibility.md` was kept rather than deleted, but narrowed substantially.

## Expected Side Effects

- Later implementation phases are now constrained by docs and tests that require `Workflow.extensions`, `autoloop_v3.stdlib`, and `autoloop_v3.extensions`.
- Future doc drift back toward observer-era wording should fail the doc baseline.

## Validation Performed

- `pytest autoloop_v3/tests/test_architecture_baseline_docs.py`

## Deduplication / Centralization Decisions

- `ARCHITECTURE_DECISIONS.md` is the only full candidate-matrix record.
- ADR files were kept as summary-only mirrors of the authoritative record.
- Retained compatibility details were centralized into `docs/compatibility.md` instead of being spread through the architecture docs.
