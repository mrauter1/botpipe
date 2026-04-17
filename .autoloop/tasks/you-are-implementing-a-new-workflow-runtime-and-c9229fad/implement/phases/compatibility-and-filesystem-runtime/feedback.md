# Implement ↔ Code Reviewer Feedback

- Task ID: you-are-implementing-a-new-workflow-runtime-and-c9229fad
- Pair: implement
- Phase ID: compatibility-and-filesystem-runtime
- Phase Directory Key: compatibility-and-filesystem-runtime
- Phase Title: Compatibility And Filesystem Runtime
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 (`blocking`): [autoloop_v3/runtime/cli.py], [autoloop_v3/runtime/config.py], and [autoloop_v3/runtime/runner.py] expose compatibility flags and config fields such as `--pairs`, `--max-iterations`, and `--phase-mode`, but `RunnerOptions` has no fields for them and `run_workflow()` never uses or persists phase selection. Concrete regression scenario: an operator runs the new harness with `--phase-mode up-to` or configures `runtime.pairs=plan`, the command accepts the input, but execution silently ignores it and just runs the workflow entry path. That breaks the required CLI/runtime-option compatibility and phase-selection persistence contract. Minimal fix direction: centralize supported runtime options in `RunnerOptions`, thread them through the runner/workspace layer, persist/load the selected phase set via `phase_selection_file`, and reject any still-unsupported compatibility flags at parse time instead of accepting them as no-ops.

- IMP-002 (`blocking`): [autoloop_v3/runtime/runner.py] and [autoloop_v3/runtime/stores/filesystem.py] only resume runs that already have the new `checkpoint.json`; they do not reconstruct resume state from existing `.autoloop` / `.superloop` run artifacts even though that compatibility was explicitly in scope. Concrete failure scenario: I created a valid run directory with the expected raw log, request snapshot, and session files but no new checkpoint file, then called `run_workflow(..., resume=True)` and it failed immediately with `WorkflowExecutionError: resume requested but no checkpoint is available`. That means persisted session/run data from current legacy runs is not actually migration-safe to resume under the new runtime. Minimal fix direction: add a legacy resume adapter at the runner/checkpoint boundary that derives a `CheckpointPayload` from the existing run artifacts/events/session files, or explicitly detect and block legacy resumes with a targeted compatibility error before claiming resume support.
