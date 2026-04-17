# Implementation Plan

## Target Outcome

Refine `autoloop_v3` to the final Book Architecture where the engine emits only generic execution facts, the runtime owns only generic filesystem persistence, and Autoloop-v1 parity is implemented entirely as workflow-owned interpretation of those facts. The end state must remove the Autoloop-v1 provider wrapper, remove the engine subclass, delete `phase_artifact_template`, keep sessions explicit, and preserve legacy Autoloop-v1 behavior without leaking it into `workflow` or `runtime`.

## Confirmed Constraints

- `autoloop_v3.workflow` stays strict, canonical, and compatibility-free.
- `autoloop_v3.runtime` stays workflow-agnostic; no phase knowledge and no workspace plugin system.
- `autoloop_v3.workflows` owns Autoloop-v1 parity policy.
- `PairStep` and `LLMStep` handlers remain optional; `SystemStep` handlers remain required.
- Sessions remain explicit: declared as `Session()`, created by `ctx.open_session(...)`, consumed by direct lookup only.
- `run_autoloop_v1(...)` survives as a thin workflow-owned composition root.
- `autoloop_v1.py` and `Ralph_loop.py` stay strict workflows with canonical imports and explicit workflow logic.
- No new compatibility layer may be introduced under another name.

## Current Relevant Findings

- `autoloop_v3/workflows/autoloop_v1_support.py` currently mixes workflow semantics, parity policy, workspace augmentation, raw-log/decisions/status behavior, session JSON serialization, a provider wrapper, and an engine subclass.
- `autoloop_v3/runtime/stores/filesystem.py` already owns legacy session-payload reading and sparse metadata preservation, but payload writing and placeholder creation still leak into the Autoloop-v1 support layer.
- `autoloop_v1.py` still imports `phase_artifact_template`, `parse_phase_ids`, and `phase_dir_key` from the support module; artifact path intent is therefore split between the workflow and the harness.
- `Ralph_loop.py` currently fails strict validation because `on_execute` is not class-bound, and the direct `plan_action -> goal_met -> SUCCESS` path must still set `goal_met=True`.
- The existing parity suite already proves raw phase logs, decisions persistence, legacy session filenames, and blocked/failed/question mapping, so the refactor must preserve those assertions while changing the mechanism.
- `autoloop_v3/ARCHITECTURE_DECISIONS.md` exists but does not yet cover the 17 required final decisions for the remaining support-layer refinement; it must be replaced before implementation starts.

## Chosen Target Shape

### Core

- Add one minimal typed execution observer seam under `autoloop_v3.workflow`, preferably a small `workflow/observers.py` module plus `Engine(..., observers=())`.
- The observer surface is output-only: the engine emits frozen execution facts and ignores observer return values.
- The engine emits exactly three categories of observation:
  - provider-turn events after producer, verifier, and llm turns
  - step-completion events after every step
  - terminal events for success, pause, fail, and fatal exception
- Observer payloads must be sufficient for downstream consumers to reconstruct parity behavior without engine branching:
  - provider-turn: turn kind, step name, step kind, raw output or outcome, persisted session binding, provider metadata, task/run identifiers
  - step-completion: step name, step kind, state before, state after, emitted event, outcome, destination, task/run identifiers
  - terminal: terminal kind, final state, history, last event, last outcome, exception metadata when fatal

### Runtime

- `autoloop_v3/runtime/stores/filesystem.py` becomes the sole owner of session-payload serialization helpers.
- Promote payload-writing utilities out of the Autoloop-v1 layer into small generic store helpers such as:
  - `write_session_payload(...)`
  - `ensure_session_payload_placeholder(...)`
- Keep `load_session_payload(...)`, `thread_id` compatibility, sparse metadata preservation, and generic session paths unchanged.
- Keep workspace creation generic in `runtime.workspace`; Autoloop-specific augmentation remains an explicit parity-layer call sequence.
- Prefer routing generic `events.jsonl` step/terminal emission through the new observer seam so both generic runner and parity harness consume the same execution facts.

### Workflow-Owned Autoloop-v1 Layer

- Delete `autoloop_v3/workflows/autoloop_v1_support.py` and replace it with two smaller modules:
  - `autoloop_v3/workflows/autoloop_v1_conventions.py` for tiny shared Autoloop-v1 path/policy helpers that are needed by both the strict workflow and the parity harness
  - `autoloop_v3/workflows/autoloop_v1_parity.py` for `run_autoloop_v1(...)`, workspace augmentation, the parity observer, clarification persistence, raw logs, decisions ledger writes, and legacy status mapping
- Migrate `autoloop_v1.py` off `autoloop_v1_support.py` in the same slice that deletes that module. Do not create an interim bridge or placeholder support module.
- Keep `parse_phase_ids` in `autoloop_v1.py` because it is workflow semantics, not shared infrastructure.
- Keep exact `phase_dir_key` behavior in `autoloop_v1_conventions.py` because both the strict workflow and the parity harness need the same legacy encoding.
- Keep `autoloop_v1_session_path(...)` in the same tiny conventions module for the same reason.
- Track cycle/attempt numbers in the parity observer state during a run. On resume, recover the active clarification cycle/attempt from persisted raw-log/checkpoint context instead of provider session metadata.
- Derive phase-started and phase-completed legacy events from step-completion events inside the parity observer; do not reintroduce engine subclass logic.

### Strict Workflows

- `autoloop_v1.py`
  - inline explicit `Artifact(...)` templates instead of `phase_artifact_template`
  - inline `parse_phase_ids`
  - import only canonical workflow primitives plus any tiny shared Autoloop-v1 conventions helper needed for `phase_dir_key`
- `Ralph_loop.py`
  - repair the strict class structure so `on_execute` is present as the `SystemStep` handler
  - set `goal_met=True` on every success path, including `plan_action -> goal_met -> SUCCESS`

## Interface Changes To Implement

- `autoloop_v3.workflow.engine.Engine.__init__(..., observers: Sequence[ExecutionObserver] = ())`
- `autoloop_v3.workflow.observers.ExecutionObserver`
  - single method: `record(event: ExecutionEvent) -> None`
- `autoloop_v3.workflow.observers.ExecutionEvent`
  - tagged union of `ProviderTurnEvent`, `StepCompletedEvent`, and `TerminalEvent`
- `autoloop_v3.runtime.stores.filesystem`
  - export generic session payload write/placeholder helpers
  - remove workflow-owned JSON serialization from Autoloop-v1 code
- `autoloop_v3.workflows.__init__`
  - continue re-exporting `run_autoloop_v1`, but from the new parity module

## Ordered Milestones

### 1. Decision Freeze And Core Observer Seam

- Replace `autoloop_v3/ARCHITECTURE_DECISIONS.md` with the required 17 decision sections, each containing three candidates, the chosen Book Architecture option, and why the other two lost.
- Add the typed observer seam and wire `workflow.engine` to emit provider-turn, step-completion, and terminal events.
- Keep engine semantics strict: no Autoloop imports, no phase branching, no automatic session opening, and no change to handler optionality rules.
- Update engine-contract tests to prove observer delivery and non-interference.
- Rollback posture: revert only the observer wiring if it destabilizes execution; do not restore wrapper/subclass mechanisms.

### 2. Runtime Session Serialization Ownership

- Move session payload writing and placeholder creation into `runtime.stores.filesystem`.
- Update all callers to use store helpers instead of workflow-owned JSON serialization.
- Preserve `thread_id` compatibility, sparse metadata preservation, and generic path behavior.
- Add store tests for helper ownership and placeholder behavior.
- Rollback posture: keep the public store helper names stable even if internal helper factoring changes.

### 3. Split The Autoloop-v1 Parity Layer

- Replace `autoloop_v1_support.py` with a tiny conventions module plus a parity composition-root module.
- Migrate `autoloop_v1.py` in the same slice so the support module can be deleted without leaving any workflow imports behind.
- Remove `phase_artifact_template`, inline `parse_phase_ids`, and switch the workflow to explicit artifact templates as part of that same Autoloop-v1 slice.
- Remove `_AutoloopV1LoggingProvider` and `_AutoloopV1Engine`.
- Rebuild parity behavior on top of the observer seam:
  - raw phase logs
  - phase started/completed event logging
  - clarification persistence on pause/resume
  - legacy status mapping
  - legacy session filenames
  - explicit workspace augmentation and phase-plan-path seeding
- Keep `run_autoloop_v1(...)` thin: it should only assemble generic runtime pieces plus parity-only policy.
- Rollback posture: if parity assertions regress, revert the parity-module split together with the coupled `autoloop_v1.py` migration; do not reintroduce a placeholder support module.

### 4. Restore Strict Workflow Clarity

- Update `Ralph_loop.py` so it compiles strictly and leaves `goal_met=True` on all success paths.
- Add workflow-level tests proving:
  - `phase_artifact_template` is gone
  - explicit artifact templates are present
  - both repo-root workflows compile and run through the strict loader/runtime
  - `goal_met` is correct for both direct and reflected success paths
- Rollback posture: none; these changes are required correctness fixes, not optional refactors.

### 5. Docs, Baseline Tests, And Full Verification

- Update `README.md`, `MIGRATION.md`, `docs/architecture.md`, `docs/authoring.md`, `docs/compatibility.md`, `docs/parity-matrix.md`, `docs/risk-register.md`, and the rewritten `ARCHITECTURE_DECISIONS.md`.
- Update doc-baseline tests to freeze the final observer boundary and new workflow-owned module names.
- Run the relevant test matrix:
  - engine/core contracts
  - runtime/store tests
  - workflow integration tests
  - Autoloop-v1 parity tests
  - toy workflow neutrality / no-over-abstraction checks
- Rollback posture: documentation changes follow code; do not weaken tests to hide architectural drift.

## Regression Controls

- Keep the observer seam minimal and typed; do not add per-step hook families, mutable callbacks, or workflow-specific payload fields.
- Preserve the explicit session model and keep missing-session failures loud and deterministic.
- Ensure phase session rebinding remains driven only by `ctx.open_session(...)` in workflow code.
- Keep generic runtime workspace layout unchanged; Autoloop augmentation remains explicit in the parity layer.
- Preserve legacy filenames and append formats for `plan.json`, `sessions/phases/{phase}.json`, `raw_phase_log.md`, and `decisions.txt`.
- Keep generic runtime runnable for unrelated workflows without phase folders, raw logs, or decisions files.
- Ensure fatal exceptions still checkpoint and surface as failures while producing a terminal observation event for logging.

## Validation Matrix

- Engine/core
  - PairStep handlers optional
  - LLMStep handlers optional
  - SystemStep handlers required
  - explicit session opening works
  - missing session binding fails clearly
  - observers receive provider-turn, step-completion, and terminal events
  - observers do not alter state/routing semantics
- Runtime/store
  - filesystem store owns payload write and placeholder helpers
  - legacy `thread_id` payloads still load
  - sparse metadata survives restore/upsert
- Workflow strictness
  - `autoloop_v1.py` no longer imports or uses `phase_artifact_template`
  - explicit artifact templates are present in the workflow source
  - `Ralph_loop.py` compiles and preserves `goal_met`
- Autoloop-v1 parity
  - raw phase logs and decisions ledger still match expected content
  - legacy session filenames still match
  - blocked/question/failed status mapping still matches
  - parity no longer depends on provider wrapper or engine subclass
- No-over-abstraction
  - toy workflow still runs without phase knowledge
  - no generic workspace-hook system is introduced
  - engine contains no Autoloop-specific imports or conditionals

## Compatibility Notes

- Preserved public entrypoints:
  - `workflow` strict authoring surface
  - `autoloop_v3.workflows.run_autoloop_v1(...)`
- Preserved persisted compatibility:
  - legacy session payloads that only contain `thread_id`
  - legacy-readable `events.jsonl` `run_finished.status`
  - legacy Autoloop-v1 workspace artifacts and filenames
- Intentional internal cleanup:
  - direct imports of `autoloop_v3.workflows.autoloop_v1_support` disappear
  - provider wrapper / engine subclass implementation details disappear
  - `phase_artifact_template` disappears
  - `docs/compatibility.md` must be rewritten to point at the final parity/conventions split

## Open Risks To Watch During Implementation

- Resume-time clarification cycle/attempt reconstruction is the main subtlety after removing counter persistence from session metadata; prove it with targeted parity tests.
- Observer payload shape must stay small while still exposing enough data for parity observers to derive phase and status behavior without engine knowledge.
- Converting generic `events.jsonl` logging onto the observer seam must avoid double-emitting `step_executed` or `run_finished`.
