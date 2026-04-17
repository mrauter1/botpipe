# Plan

## Objective

Refactor `autoloop_v3/` into a strict workflow core plus a workflow-agnostic runtime, then run `autoloop_v1.py` through workflow-owned parity helpers with functionality equivalent to legacy `autoloop/`. The final system must delete the compatibility layer instead of relocating it.

## Repository Findings

- `autoloop_v3.workflow` is already close to the target model, but it still contains explicit compatibility behavior:
  - `workflow.compat.normalize_workflow()`
  - `Verdict = Outcome`
  - `on_verdict` middleware handling
  - pair/llm/system handler arity adaptation
  - `SessionLifecycle.ON_START`
  - engine auto-opening step sessions when a slot is missing
- The repo-root `workflow/` package is not a strict public surface today; it maps `Workflow` to `LegacyWorkflow`.
- `runtime.loader` still injects symbols into workflow modules before import.
- `runtime.workspace`, `runtime.runner`, `runtime.config`, and `runtime.stores.filesystem` currently know Autoloop-specific concepts:
  - phase-plan scaffolding/validation/selection
  - `plan_session` / `phase_session` path special cases
  - pair/phase/git compatibility CLI flags
  - prompt-root hacks for legacy Autoloop templates
  - raw log / decisions conventions tightly bound to Autoloop naming
- `autoloop_v1.py` and `Ralph_loop.py` are already partly strict, but they still depend on the non-strict root import surface and runtime conventions that should become explicit and self-contained.
- The current docs and doc-gating tests freeze the compatibility architecture and must be replaced, not incrementally patched.

## Target Architecture

### 1. Strict Core

`autoloop_v3.workflow` becomes the only engine/compiler/authoring implementation:

- strict `Workflow` base and metaclass
- `Event`, `Outcome`, `SUCCESS`, `PAUSE`, `FAIL`, `GLOBAL`
- `Artifact`, `Prompt`, `Session`, `PairStep`, `LLMStep`, `SystemStep`
- strict validation and compilation only
- no normalization, no alias-based middleware, no inferred entry, no injected globals

Canonical handler contract:

- `on_start(self, ctx) -> None`
- `on_outcome(state, outcome) -> Event | None`
- `on_{pair_or_llm}(state, outcome, artifacts) -> State`
- `on_{system}(state, ctx) -> tuple[State, Event]`

Canonical session contract:

- declare slots as `Session`
- create bindings only via `ctx.open_session(slot, scope=...)`
- step execution performs direct lookup only
- missing binding is a runtime error naming the unopened slot
- no lifecycle enum, no session-template evaluation, no engine auto-open fallback

Prompt contract:

- keep `Prompt` plus plain-string path shorthand only if treated as canonical, documented surface
- workflows must provide resolvable prompt paths without loader or runner symbol injection

### 2. Generic Runtime

`autoloop_v3.runtime` becomes a small generic filesystem harness:

- task/run workspace roots
- immutable request snapshot
- generic checkpoint/session stores
- generic prompt file resolution
- generic run lifecycle execution

The generic runtime must not own or branch on:

- plan / implement / test
- phases or phase selection
- `phase_plan.yaml`
- Autoloop artifact names such as `decisions.txt` or `raw_phase_log.md`
- `plan_session` / `phase_session` slot-name conventions
- Autoloop-specific CLI/config flags

Git/commit policy:

- the generic runtime must not own git init, change-detection, commit, or `track_autoloop_artifacts` policy
- if legacy-equivalent git behavior remains necessary for `autoloop_v1`, it belongs in the `autoloop_v1` harness or workflow-owned helpers, optionally using small generic git utilities that stay policy-free
- `ARCHITECTURE_DECISIONS.md` must include `git policy placement` explicitly and record how retained git behavior is validated or intentionally removed

### 3. Workflow-Owned Parity Layer For `autoloop_v1`

Anything required only for `autoloop_v1` moves out of the runtime core into workflow-owned modules inside `autoloop_v3/`:

- phase-plan parsing/activation helpers
- legacy-parity workspace and artifact conventions
- decisions/raw-log/clarification persistence
- prompt path locations for legacy Autoloop templates
- session file naming policy needed for `plan.json` and `phases/{phase}.json`
- any phase lifecycle event derivation required for parity

This is not a new compatibility layer. It is the workflow implementation and its harness.

### 4. Public Import Surface

- `autoloop_v3.workflow` is the canonical API.
- The repo-root `workflow/` package may remain only as a thin strict re-export for ergonomic imports.
- The root re-export must not map to `LegacyWorkflow`, inject helpers, or normalize malformed workflows.

## Required Interface Changes

### Remove Completely

- `autoloop_v3/workflow/compat.py`
- `LegacyWorkflow`
- `Verdict`
- `on_verdict`
- `SessionLifecycle`
- handler arity adaptation for old signatures
- entry inference / string-to-step normalization added for legacy tolerance
- loader-time canonical symbol injection
- engine/session-store behavior that auto-opens missing step sessions

### Tighten / Introduce

- `compile_workflow()` accepts only already-strict workflow classes.
- `validation.py` accepts only strict handler signatures and explicit `entry`.
- `engine.py` routes step-local first, then `GLOBAL`, else error.
- `engine.py` resolves sessions by lookup only:
  - `binding = ctx.get_session(step.session)`
  - if `binding is None`, raise `WorkflowExecutionError` naming the slot
- `runtime/runner.py` exposes only generic workflow-run options; move pair/phase/git tracking policy to the `autoloop_v1` harness or delete if unnecessary.
- `runtime/stores/filesystem.py` stays generic on its default mapping; Autoloop-v1-specific session path mapping should use the smallest workflow-owned local adapter/hook needed to preserve `plan.json` and `phases/{phase}.json`, not a new runtime-wide path-policy framework unless a second workflow proves the need.

## Implementation Phases

### Phase 1: Book-Architecture Core And Decision Record

Scope:

- write `autoloop_v3/ARCHITECTURE_DECISIONS.md` before core refactors
- enumerate every material decision named in the request and compare 3 candidates each
- remove compat behavior from `workflow/`
- make the root `workflow/` package a strict re-export only
- update unit/contract tests to assert strict behavior instead of compatibility behavior

Milestones:

1. `ARCHITECTURE_DECISIONS.md` exists and covers:
   - package/module layout
   - public API surface
   - compat removal
   - workflow migration strategy
   - session model
   - artifact model
   - prompt model
   - validation/compilation model
   - checkpoint model
   - provider/store protocols
   - runtime harness split
   - config policy
   - git policy placement
   - observability/event model
   - parity strategy
   - migration strategy
2. `workflow.compat`, `LegacyWorkflow`, `Verdict`, `on_verdict`, `SessionLifecycle`, and handler-adapter code paths are deleted.
3. Strict validation/compiler/engine tests pass.

Regression controls:

- add failing tests first for no-compat invariants
- keep runtime/parity tests temporarily pinned until the new harness exists

### Phase 2: Runtime Core Reduction

Scope:

- strip `runtime/` down to generic task/run execution
- remove Autoloop phase/pair concepts from workspace/config/runner/store layers
- keep only generic request snapshot, checkpoint, session persistence, and prompt resolution

Milestones:

1. `runtime.workspace` no longer scaffolds or validates phase plans or creates plan/implement/test directories.
2. `runtime.runner` no longer exposes or interprets pair/phase/git compatibility flags.
3. `runtime.stores.filesystem` no longer hardcodes `plan_session` / `phase_session` behavior in its generic path logic.
4. Generic runtime can execute a toy workflow with unrelated step names end to end.

Regression controls:

- add toy-workflow tests proving the runtime has no plan/implement/test knowledge
- preserve request snapshot, checkpoint, and generic session persistence tests while removing Autoloop-specific assumptions

### Phase 3: Workflow Migration And `autoloop_v1` Parity Harness

Scope:

- finish strict migration of `autoloop_v1.py`
- finish strict migration of `Ralph_loop.py`
- create workflow-owned helpers/harness for `autoloop_v1` parity
- preserve legacy Autoloop outputs using workflow-owned code, not runtime-core code

Milestones:

1. `autoloop_v1.py` imports only canonical strict symbols, uses explicit prompt paths, and opens sessions only in readable workflow hooks.
2. `Ralph_loop.py` runs as a strict workflow with no loader injection and no relaxed handler signatures.
3. `autoloop_v1` harness preserves:
   - `.autoloop/tasks/{task_id}/runs/{run_id}`
   - request snapshots
   - `events.jsonl` semantics and `latest_run_status`-relevant status fields
   - checkpoint persistence / load / clear behavior
   - `question` / `blocked` / `failed` behavior
    - decisions/raw log conventions
    - clarification persistence
    - session persistence files
    - pause/resume behavior
4. Implement/test share the active phase session only because `activate_next_phase` rebinds the slot and nothing else does.

Regression controls:

- compare helper outputs directly against `autoloop.main` helper behavior where possible
- preserve legacy-compatible file contents, event-status behavior, checkpoint lifecycle, and session-note behavior through parity tests

### Phase 4: Proof Suite And Final Docs

Scope:

- replace stale compatibility docs/tests
- add final package docs required by the request
- prove strict engine contract, no-compat behavior, workflow execution, and legacy parity

Milestones:

1. Add/update:
   - `autoloop_v3/README.md`
   - `autoloop_v3/MIGRATION.md`
   - `autoloop_v3/ARCHITECTURE_DECISIONS.md`
   - authoring/parity notes as needed
2. Replace doc-baseline tests that currently require the compatibility architecture.
3. Full suite passes with strict surfaces only.

Regression controls:

- verify docs/tests assert absence of compat features
- keep at least one golden-path `autoloop_v1` parity run, one blocked/question/failure parity path, and one unrelated toy workflow run

## Validation Matrix

### Engine Contract

- PairStep contract
- LLMStep contract
- SystemStep contract
- Pair/LLM handlers optional
- System handlers required
- routing precedence
- pause/resume
- answer injection
- explicit session creation / rebinding
- missing unopened session fails clearly
- artifact template resolution
- validation failures

### No-Compat Proof

- strict workflows compile without `workflow.compat`
- no loader-injected authoring symbols
- no handler adaptation
- no `on_verdict`
- no inferred entry fallback
- no `SessionLifecycle`
- root `workflow.Workflow` is the strict class, not a legacy base

### Workflow Proof

- strict `autoloop_v1.py` runs successfully
- strict `Ralph_loop.py` runs successfully
- explicit session-opening moments are exercised
- topology-based phase-session sharing is verified
- at least one toy workflow with unrelated step names proves runtime agnosticism

### Legacy Parity Proof For `autoloop_v1`

- `.autoloop/tasks/{task_id}/runs/{run_id}` layout
- key task/run artifacts
- request snapshot behavior
- `events.jsonl` behavior, including legacy-compatible terminal/status interpretation
- checkpoint save/load/clear behavior
- `question` / `blocked` / `failed` behavior
- raw log behavior
- decisions / clarification behavior
- session persistence payloads and file paths
- pause/resume semantics and clarification note placement
- final successful run behavior and outputs

## Intentional Compatibility Breaks

These breaks are required by the request and should be implemented explicitly, not accidentally:

- old malformed or drifted workflows stop compiling
- loader injection disappears
- compatibility aliases disappear
- relaxed handler arities disappear
- generic runtime pair/phase compatibility knobs disappear
- phase-plan/runtime policy moves out of `autoloop_v3.runtime`

The only preserved compatibility target is behavioral parity for strict `autoloop_v1.py` relative to legacy `autoloop/`.

## Risk Register

| Risk | Why it matters | Mitigation | Exit check |
| --- | --- | --- | --- |
| Engine still auto-opens sessions after compat removal | Would silently preserve forbidden computed/implicit session behavior | Remove auto-open path early and add contract tests before migrating parity harness | Missing unopened slot raises a clear runtime error |
| Autoloop-specific code leaks back into runtime during parity work | Violates the main architecture requirement | Treat any reference to phases, pair names, or Autoloop artifact names in `runtime/` as a blocker unless clearly generic | Grep of `runtime/` shows no Autoloop-specific domain terms beyond generic task/run naming |
| Session file naming changes break legacy parity | `autoloop_v1` resume/clarification behavior depends on stable files | Keep naming policy in workflow-owned harness and compare with legacy helper outputs | `plan.json` / `phases/{phase}.json` parity tests pass |
| Event or checkpoint semantics drift during runtime split | `latest_run_status`, resume flow, and pause/failure handling depend on stable persisted behavior | Add explicit parity tests for `events.jsonl`, checkpoint save/load/clear, and `question` / `blocked` / `failed` flows before closing parity work | Event/status and checkpoint lifecycle assertions match legacy expectations |
| Prompt lookup regresses after removing runtime hacks | `autoloop_v1` depends on legacy template files | Make prompt paths explicit in workflows or workflow-owned helpers | Prompt-path tests no longer depend on injected roots |
| Current docs/tests resist the target design | They currently assert the old compat architecture | Rewrite gate tests alongside the code instead of preserving stale docs | New docs assert strict surfaces and absence of compat |

## Rollout / Rollback

- Land phase 1 and phase 2 with green strict-core and generic-runtime tests before migrating parity helpers.
- Migrate `Ralph_loop.py` only after the strict core is stable; it is the cheap proof that loader hacks are gone.
- Migrate `autoloop_v1.py` and parity harness after generic runtime boundaries are enforced; otherwise compatibility logic will drift back into `runtime/`.
- If a phase fails, revert only the in-progress phase changes; do not reintroduce deleted compat paths as temporary fixes.
