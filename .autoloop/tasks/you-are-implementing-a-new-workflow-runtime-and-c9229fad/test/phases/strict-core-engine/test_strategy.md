# Test Strategy

- Task ID: you-are-implementing-a-new-workflow-runtime-and-c9229fad
- Pair: test
- Phase ID: strict-core-engine
- Phase Directory Key: strict-core-engine
- Phase Title: Strict Core Engine
- Scope: phase-local producer artifact

## Behavior To Test Coverage Map

- Primitives and stores: `autoloop_v3/tests/unit/test_primitives_and_stores.py`
  - Covers `Event` / `Outcome` / `Verdict` surface, artifact template dot-notation and missing-key resolution, `ResolvedArtifacts` attribute access, prompt registry resolution, in-memory session snapshot restore, and checkpoint round-trip with pending question or answer preservation.
- Definition-time validation: `autoloop_v3/tests/unit/test_validation.py`
  - Covers missing `State`, missing `entry`, missing system handlers, orphan handlers, invalid destinations, duplicate artifact names, future required artifacts, undeclared session refs, workflow-level inputs, reserved hook-name precedence for `start` / `outcome` / `verdict`, and rejection of conflicting active middleware hooks.
- Deterministic execution contracts: `autoloop_v3/tests/contract/test_engine_contracts.py`
  - Covers `PairStep`, `LLMStep`, and `SystemStep` execution order, raw-output logging, `GLOBAL` routing fallback, lifecycle hooks, pause or resume with one-shot answer injection, best-effort failure checkpointing, missing-artifact checkpointing, scoped-session switching, deterministic compilation, and runtime execution for steps named `start` / `outcome` / `verdict`.

## Preserved Invariants Checked

- Strict-core workflows compile deterministically and execute without touching legacy compatibility shims.
- State updates happen through handlers returning new models; system-step middleware bypass is preserved.
- Artifact resolution remains deterministic for task/run folders and nested state placeholders.
- Session snapshots preserve both bindings and active scope selection across restore or resume.

## Edge Cases And Failure Paths

- Edge cases: missing artifact-template placeholders, step names that overlap reserved hook names, workflow-level artifacts used as inputs, and per-phase session scope switches.
- Failure paths: missing system handlers, orphan handlers, invalid topology, duplicate artifacts, future artifact requirements, undeclared sessions, missing required artifacts at runtime, handler exceptions, and conflicting active middleware hooks.

## Flake Risk And Stabilization

- Tests use `ScriptedLLMProvider`, in-memory stores, and `tmp_path`; there is no network, clock, or ordering dependency in phase scope.
- Class-local workflow definitions keep validation failures isolated per test and avoid cross-test mutable state.

## Known Gaps

- Filesystem-backed stores, runtime harness or CLI integration, and workspace compatibility normalization are deferred by phase contract.
- This phase does not assert legacy import shims or `.autoloop` workspace parity behavior.
