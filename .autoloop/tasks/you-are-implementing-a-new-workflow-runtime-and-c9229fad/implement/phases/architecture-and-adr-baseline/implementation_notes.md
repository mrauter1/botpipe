# Implementation Notes

- Task ID: you-are-implementing-a-new-workflow-runtime-and-c9229fad
- Pair: implement
- Phase ID: architecture-and-adr-baseline
- Phase Directory Key: architecture-and-adr-baseline
- Phase Title: Architecture Baseline
- Scope: phase-local producer artifact

## Files Changed

- `autoloop_v3/docs/architecture.md`
- `autoloop_v3/docs/parity-matrix.md`
- `autoloop_v3/docs/compatibility.md`
- `autoloop_v3/docs/authoring.md`
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
- `.autoloop/tasks/you-are-implementing-a-new-workflow-runtime-and-c9229fad/decisions.txt`
- `.autoloop/tasks/you-are-implementing-a-new-workflow-runtime-and-c9229fad/implement/phases/architecture-and-adr-baseline/implementation_notes.md`

## Symbols Touched

- Documentation only in this phase.
- Frozen planned surfaces: `Workflow`, `Context`, `Session`, `SessionLifecycle`, `Artifact`, `Prompt`, `PairStep`, `LLMStep`, `SystemStep`, `Event`, `Outcome`, `Verdict`, `Checkpoint`, `ResolvedArtifacts`.
- Frozen planned runtime modules: `runtime.loader`, `runtime.config`, `runtime.workspace`, `runtime.logging`, `runtime.runner`, `runtime.cli`.

## Checklist Mapping

- `plan.md` milestone 1: completed feature-parity inventory and risk list.
- `plan.md` milestone 1: completed ADR set under `autoloop_v3/docs/adr/`.
- `plan.md` milestone 1: froze package layout, public interfaces, and compatibility boundary in docs.
- Deferred by phase contract: core runtime implementation, filesystem stores, providers, CLI code, and parity goldens.

## Assumptions

- The new implementation root remains `/home/rauter/autoloop_v3/autoloop_v3/`.
- A thin repo-root `workflow` shim will be added in a later phase for import ergonomics.
- Compatibility for `Ralph_loop.py` must happen at load time before strict compilation because undeclared annotations fail import once `workflow` exists.

## Preserved Invariants

- Legacy `autoloop/` code remains untouched and continues to serve as the behavior oracle.
- Compatibility stays outside the strict core.
- Phase-local artifact and session scoping remain required parity behavior.
- Resume design keeps typed checkpoints and append-only events as distinct concerns.

## Intended Behavior Changes

- None in this phase; this phase only freezes the target architecture and compatibility plan.

## Known Non-Changes

- No production runtime or engine code exists yet under `autoloop_v3/workflow` or `autoloop_v3/runtime`.
- No existing workflow files were edited.
- No CLI or provider behavior changed in this phase.

## Expected Side Effects

- Future implementation phases now have an explicit module map, public surface, compatibility boundary, and regression checklist.
- ADRs provide the required three-candidate decision record for each material design topic.

## Validation Performed

- Read and compared `autoloop_v1.py`, `Ralph_loop.py`, `autoloop/src/autoloop/main.py`, `autoloop/tests/test_phase_local_behavior.py`, and `autoloop/tests/test_autoloop_observability.py`.
- Verified there are 14 ADR files and each contains exactly three `Candidate` sections plus all required evaluation fields.
- Confirmed `Ralph_loop.py` still fails after stubbing `workflow` with `NameError: Verdict is not defined`, validating the need for a legacy-safe loader.

## Deduplication And Centralization Decisions

- Consolidated all material design decisions into one ADR set under `autoloop_v3/docs/adr/` instead of scattering rationale through notes.
- Centralized parity, compatibility, and risk baselines in dedicated docs so later phases can implement against a single frozen plan.
