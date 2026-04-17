# Test Strategy

- Task ID: you-are-implementing-a-new-workflow-runtime-and-c9229fad
- Pair: test
- Phase ID: compatibility-and-filesystem-runtime
- Phase Directory Key: compatibility-and-filesystem-runtime
- Phase Title: Compatibility And Filesystem Runtime
- Scope: phase-local producer artifact

## Behavior To Test Coverage Map

- Legacy workflow loading and normalization: `autoloop_v3/tests/runtime/test_compatibility_runtime.py`
  - Covers root `workflow` shim import for `autoloop_v1.py`, legacy-safe loading for `Ralph_loop.py`, and strict compilation of both workflows without source edits.
- Filesystem runtime persistence and compatibility paths: `autoloop_v3/tests/runtime/test_compatibility_runtime.py`
  - Covers compatibility session file paths, legacy `thread_id` loading, checkpoint round-trip, phase-selection save/load, implicit phase-plan scaffolding, and resume-root discovery for legacy `.superloop` state roots.
- Workspace logging and clarification persistence: `autoloop_v3/tests/runtime/test_compatibility_runtime.py`
  - Covers raw-log updates, decisions ledger question/answer entries, and persisted session clarification notes.
- Config, CLI, and runtime-option compatibility boundaries: `autoloop_v3/tests/runtime/test_compatibility_runtime.py`
  - Covers config-layer merge precedence, duplicate-config rejection, CLI option plumbing into `RunnerOptions`, explicit rejection of unsupported non-default legacy loop flags, argparse conversion of `ConfigError`, and clean CLI exits for runtime execution failures.
- Runtime execution path: `autoloop_v3/tests/runtime/test_compatibility_runtime.py`
  - Covers `autoloop_v1` end-to-end execution through the filesystem runtime, prompt-path resolution, event-log emission, raw-output persistence, and scoped plan/phase session file creation.

## Preserved Invariants Checked

- Legacy workflows continue to load unchanged through the compatibility shim or legacy-safe loader before strict compilation.
- Filesystem stores preserve the existing `.autoloop` session and run layout where phase scope and plan scope matter.
- The generic `autoloop_v3` runner does not silently accept unsupported legacy pair or phase control flags.
- CLI failures stay deterministic and user-visible: config errors route through argparse, while workflow execution errors exit without a traceback.

## Edge Cases And Failure Paths

- Edge cases: implicit phase plan scaffolding, duplicate config files in one directory, direct CLI `--phase-id` plumbing, and legacy `thread_id` session payloads.
- Failure paths: unsupported compatibility flags, resume requests against legacy-only run state without `checkpoint.json`, config discovery conflicts, and CLI-triggered execution errors.

## Flake Risk And Stabilization

- Tests use `tmp_path`, monkeypatched config loaders, and fake providers only; there is no network, wall-clock, or external process dependency.
- CLI tests stub `resolve_runtime_config`, provider-factory loading, and `run_workflow` so failures stay deterministic and independent of environment-specific config files.

## Known Gaps

- This phase does not add final parity goldens or broad legacy-oracle diffs; those remain deferred by contract.
- The generic `autoloop_v3` runner intentionally rejects non-default legacy loop-control flags rather than emulating full old-harness behavior.
