# Book Architecture Refactor Plan

## Goal
Refactor `autoloop_v3` into the requested final shape:

- `autoloop_v3.workflow` as the strict canonical kernel
- `autoloop_v3.runtime` as the workflow-agnostic filesystem runtime
- `autoloop_v3.stdlib` as a tiny pure authoring layer
- `autoloop_v3.extensions` as a tiny optional extension surface
- `autoloop_v3.workflows` as workflow-owned parity and conventions only

The implementation must remove compatibility-era behavior, preserve Autoloop-v1 parity against `autoloop/`, keep `autoloop_v1.py` and `Ralph_loop.py` explicit and readable, and ship with layered proof for strictness, runtime neutrality, extensions, and parity.

## Source-Of-Truth And Scope Rules
- Follow the request snapshot first, then repo-root strict workflows as readability targets, then current `autoloop_v3` docs/ADRs only when they agree, then the legacy `autoloop/` runtime as the Autoloop-v1 behavioral oracle.
- Do not edit the legacy `autoloop/` oracle.
- Treat only the explicitly requested removals as intentional behavior breaks. Preserve persisted-data compatibility that was not authorized to break.

## Current Behavior Snapshot
- The repo already has a strict `workflow`/`runtime` split, explicit sessions, typed checkpoints, and generic workspace/event files.
- The current architecture still centers `workflow.observers` as the execution seam; the requested final model is `Workflow.extensions` plus `workflow/extensions.py`.
- `autoloop_v3/workflow/__init__.py` and repo-root `workflow/__init__.py` currently expose `Engine` and `compile_workflow`, which is broader than the requested canonical authoring surface.
- `autoloop_v3.stdlib` and `autoloop_v3.extensions` do not exist yet.
- `run_autoloop_v1(...)` currently rebuilds parity through observer plumbing and direct runner composition; it must become a thin composition root over the final generic runtime plus workflow-owned parity/session-path/git policy.
- Docs, ADRs, and tests currently freeze the observer-based architecture and therefore must be rewritten together with the code.
- `autoloop_v1.py` is already close to the target shape: explicit sessions, inline `parse_phase_ids`, and explicit artifact templates are present.
- `Ralph_loop.py` is already mostly strict, but `goal_met` still needs an explicit correctness proof on every success path, including the `plan_action -> SUCCESS` route.

## Required Interfaces And Boundary Changes

### Canonical Public Surface
- `autoloop_v3.workflow` and repo-root `workflow` must expose only:
  - `Workflow`
  - `Context`
  - `Session`
  - `Artifact`
  - `Prompt`
  - `PairStep`
  - `LLMStep`
  - `SystemStep`
  - `SUCCESS`
  - `PAUSE`
  - `FAIL`
  - `GLOBAL`
- `workflow.primitives` must expose only:
  - `Event`
  - `Outcome`
  - `Checkpoint`
  - `ResolvedArtifacts`
- `Engine`, `compile_workflow`, observer types, and any compatibility helpers may remain importable from internal modules if needed by runtime/tests, but they are not part of the strict root authoring surface.

### Kernel Extension Seam
- Add `autoloop_v3/workflow/extensions.py` with the requested small protocol family:
  - `RunBinding`
  - `StepStart`
  - `StepFinish`
  - `TerminalFinish`
  - `BoundWorkflowExtension`
  - `WorkflowExtension`
- Add `Workflow.extensions: tuple[WorkflowExtension, ...] = ()`.
- The engine binds declared extensions once per run and invokes them in tuple order around step execution and terminal completion.
- Extensions may perform side effects and keep local bound state, but they may not mutate workflow state, routing, checkpoints, or other core semantics.
- Best-effort behavior must be explicit via config/policy; there is no hidden swallow-and-continue mode.

### Strict Kernel Contracts
- Remove any remaining compat concepts, aliases, and docs/tests that preserve them under new names.
- Keep one execution model:
  - definition-time validation
  - deterministic compilation
  - required `SystemStep` handlers
  - optional `PairStep`/`LLMStep` handlers
  - explicit `entry`
  - explicit sessions only
  - typed checkpoints
  - required-artifact existence assertions before step execution
  - answer injection exactly once on resume
- Replace the current observer model instead of carrying both observers and extensions.

### Generic Runtime Contracts
- `autoloop_v3.runtime` owns:
  - `.autoloop/tasks/{task_id}/runs/{run_id}` layout
  - immutable request snapshot
  - generic `events.jsonl`
  - generic checkpoint file
  - generic filesystem session persistence
  - prompt resolution
  - workflow-agnostic config and CLI
- `autoloop_v3.runtime` must not own:
  - phases
  - plan / implement / test semantics
  - Autoloop-v1 artifact names
  - raw phase log schema
  - decisions ledger schema
  - review/rework/replan semantics
  - workflow-specific git policy
- Preserve persisted session payload compatibility for legacy `thread_id` and existing generic session fields unless a later clarification explicitly authorizes breaking them.

### Optional Packages
- Add `autoloop_v3.stdlib` with only:
  - `control.py`
  - `prompts.py`
  - `steps.py`
  - `state/cursor.py`
- Add `autoloop_v3.extensions` with only:
  - `tracing.py`
  - `session_paths.py`
  - `git/{__init__,declaration,policy,repo,runtime,filters}.py`
- `stdlib` may import only standard library plus `autoloop_v3.workflow`.
- `extensions` are optional and invisible by default.

### Workflow-Owned Parity
- Keep exact Autoloop-v1 filename/path semantics workflow-owned:
  - `phase_dir_key(...)`
  - `sessions/plan.json`
  - `sessions/phases/{phase}.json`
- Keep raw-phase-log, decisions-ledger, clarification persistence, status mapping, cycle/attempt semantics, and any Autoloop-v1-specific git policy in workflow-owned modules.
- `run_autoloop_v1(...)` becomes the composition root that wires:
  - generic runtime pieces
  - the generic extension seam
  - Autoloop-v1 session-path strategy/policy
  - Autoloop-v1 parity log/ledger/status policy
  - optional git extension/policy when declared

## Milestones

### Milestone 1: Freeze The Architecture Contract
- Rewrite `ARCHITECTURE_DECISIONS.md`, `README.md`, `MIGRATION.md`, `docs/architecture.md`, `docs/authoring.md`, `docs/parity-matrix.md`, `docs/risk-register.md`, and ADR summaries to the final Book shape.
- Remove architecture/test language that treats `workflow.observers` as authoritative.
- Rebaseline doc tests at the same time so the suite no longer freezes the obsolete architecture.

### Milestone 2: Refactor The Strict Kernel
- Add `workflow/extensions.py` and migrate engine invocation from observers to bound workflow extensions.
- Narrow the canonical root export surface.
- Refactor `validation.py`, `compiler.py`, `engine.py`, `context.py`, `primitives.py`, and `steps.py` to the final contracts.
- Remove obsolete modules and tests that preserve the old execution seam or removed compat behavior.

### Milestone 3: Refactor The Generic Runtime
- Reshape `runtime/{config,events,loader,prompts,runner,workspace,cli}` and `runtime/stores/filesystem.py` to work with the final kernel and no workflow-specific knowledge.
- Bind workflow-declared extensions in the runner.
- Keep generic event history, prompt resolution, checkpoint persistence, session persistence, and request snapshots automatic.
- Keep session-path handling generic; exact Autoloop-v1 filenames remain outside runtime core.

### Milestone 4: Add Tiny `stdlib/` And Optional `extensions/`
- Implement the minimal authoring helpers only where they compile cleanly to kernel primitives.
- Add reusable optional extensions for tracing, session-path strategy, and git tracking.
- Keep git mechanics generic and commit policy workflow-owned.
- Keep session-path strategy generic and separate from Autoloop-v1 naming.

### Milestone 5: Migrate Workflows And Parity Harnesses
- Migrate `autoloop_v1.py` to the final strict surface without reducing readability.
- Migrate `Ralph_loop.py` to the final strict surface and prove `goal_met` correctness.
- Refactor `autoloop_v3.workflows.autoloop_v1_parity` into a thin composition root over the new runtime/extension/session-path pieces.
- Keep Autoloop-v1 parity policy explicit and local.

### Milestone 6: Replace The Test Matrix And Prove Parity
- Replace observer-era and compatibility-era tests with layered proof of the final architecture.
- Add or update toy workflow coverage to prove runtime neutrality.
- Add parity tests against the legacy `autoloop/` oracle for workspace, sessions, logs, ledgers, status mapping, clarification persistence, and final behavior.
- Run the full suite and resolve regressions before declaring completion.

## Ordered Phase Decomposition
The canonical machine-readable decomposition lives in `phase_plan.yaml`. The intended execution order is:

1. Architecture contract and doc freeze
2. Strict kernel and public surface refactor
3. Generic runtime and filesystem store refactor
4. Tiny stdlib and optional extensions
5. Workflow migrations and Autoloop-v1 parity harness rewrite
6. Layered tests, parity proof, and full-suite stabilization

## Affected Code Areas
- Kernel: `autoloop_v3/workflow/*`, repo-root `workflow/*`
- Runtime: `autoloop_v3/runtime/*`
- Optional surfaces: `autoloop_v3/stdlib/*`, `autoloop_v3/extensions/*`
- Workflow-owned policy: `autoloop_v3/workflows/*`, repo-root `autoloop_v1.py`, repo-root `Ralph_loop.py`
- Docs and decisions: `ARCHITECTURE_DECISIONS.md`, `README.md`, `MIGRATION.md`, `docs/*`, `docs/adr/*`
- Tests: `autoloop_v3/tests/*`

## Compatibility And Migration Notes
- Intentional removals explicitly requested:
  - compatibility layer remnants
  - `Verdict`
  - `on_verdict`
  - `SessionLifecycle`
  - loader symbol injection
  - inferred entry behavior
  - handler arity adaptation
  - any hidden normalization boundary
  - observer-based extension architecture as an authoritative surface
- Compatibility that must remain unless implementation proves otherwise:
  - Autoloop-v1 parity behavior against `autoloop/`
  - session payload compatibility for `thread_id` and existing generic fields
  - legacy-readable `run_finished.status` values where parity tests depend on them
  - exact Autoloop-v1 session filename behavior
- Do not silently broaden compatibility beyond the request. The direction is strict core plus workflow-owned parity, not “compat under another name.”

## Regression Controls
- Rewrite docs, ADRs, and baseline tests first so implementers are not dragged back toward the observer-era architecture.
- Do not carry dual extension systems. Replace `workflow.observers` with `Workflow.extensions` and update tests/docs accordingly.
- Keep public-surface narrowing explicit and update repo-root strict re-exports together with canonical `autoloop_v3.workflow`.
- Keep runtime phase-agnostic by forcing every Autoloop-v1-specific behavior into workflow-owned modules or policy objects.
- Preserve the split between raw git delta calculation and commit-eligibility filtering.
- Keep exact Autoloop-v1 filename policy outside generic session-path machinery.
- Add direct tests for `Ralph_loop.py` success via both `plan_action -> SUCCESS` and `reflect -> SUCCESS`.
- Add at least one unrelated toy workflow to prove runtime neutrality after the refactor.

## Validation Strategy
- Unit tests:
  - primitives
  - stores
  - artifact resolution
  - prompt resolution
  - validation failures
  - extension helper units
  - git repo/filter logic
  - session-path strategy helpers
- Engine contract tests:
  - Pair/LLM/System step contracts
  - optional vs required handlers
  - deterministic routing
  - pause/resume and answer injection
  - missing-session failures
  - artifact existence assertions
  - extension lifecycle and failure semantics
- Runtime integration tests:
  - workspace layout
  - request snapshot
  - `events.jsonl`
  - checkpoints
  - session persistence
  - prompt resolution
  - CLI wiring
  - runtime neutrality
- Strictness / no-compat tests:
  - no compat layer or removed symbols
  - no loader injection
  - no inferred entry
  - no handler adaptation
  - no runtime phase knowledge
  - repo-root `workflow` shim is strict re-export only
- Workflow and parity tests:
  - Autoloop-v1 happy/rework/replan/pause-resume/multi-phase cases
  - Ralph happy path and `goal_met` correctness
  - parity against legacy workspace/log/session/status behavior

## Risk Register
| Risk | Why it matters | Control |
| --- | --- | --- |
| Public-surface drift during refactor | The prompt requires a smaller canonical authoring surface than the current exports provide | Rebaseline docs/tests first and add strict export tests for both `autoloop_v3.workflow` and repo-root `workflow` |
| Dual extension models survive | Keeping both observers and extensions would recreate hidden architecture drift | Remove observer-era docs/tests and replace the seam instead of layering on top |
| Runtime absorbs workflow semantics | The request explicitly forbids phase-aware or Autoloop-aware runtime logic | Keep parity/session-path/git meaning in workflow-owned modules and add toy-workflow neutrality tests |
| Session path generalization leaks Autoloop policy | Exact `plan.json` and `phases/{phase}.json` naming must remain workflow-owned | Keep the generic session-path surface minimal and test Autoloop naming separately through workflow-owned policy |
| Persisted session payload regression | Existing runs may only have `thread_id` or sparse metadata | Preserve filesystem store read/write compatibility and add regression tests before widening the format |
| Git extension changes raw delta semantics | The current design requires raw delta and commit eligibility to stay separate | Keep delta collection in `repo.py`, filtering in `filters.py`, and add dedicated tests for both |
| Ralph `goal_met` fix covers only one success route | The prompt explicitly requires all success paths to set `goal_met=True` | Add separate tests for `plan_action -> SUCCESS` and `reflect -> SUCCESS` |
| Parity drift is hidden by new abstractions | This refactor is large enough to accidentally “clean up” required legacy behavior | Keep parity tests against `autoloop/` as gating proof and treat parity failures as blockers |

## Rollback Strategy
- Roll back in phase-sized slices rather than partial mixed states.
- If the extension-seam migration destabilizes execution, revert the kernel/runtime slices together; do not keep observers and extensions alive in parallel.
- If optional packages destabilize behavior, revert `stdlib/` and `extensions/` separately from the kernel/runtime baseline.
- If workflow migration breaks parity, revert the workflow + parity harness slice together and preserve the generic kernel/runtime changes only if the full test matrix still passes.
- Never mutate or “repair” the legacy `autoloop/` oracle as part of rollback.
