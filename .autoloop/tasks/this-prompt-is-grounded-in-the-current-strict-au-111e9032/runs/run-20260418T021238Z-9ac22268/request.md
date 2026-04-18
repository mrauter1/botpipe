This prompt is grounded in the current strict `autoloop_v1.py` workflow shape, the latest `autoloop_v3` architecture/docs/ADRs, and the legacy `autoloop` runtime, which together establish the intended strict core, generic runtime, explicit sessions, no-compat direction, workflow-owned policy, and Autoloop-v1 parity surface. It is also meant to refactor away the older compatibility-heavy `aautoloop_v1_parity.py . 
 * Also see additional_context.md for the reasoning and details of each design decision.

````text
You are a principal software architect and implementation agent.

Use `autoloop_v3/` as the implementation workspace and final framework package.

Your job is to fully refactor and redesign `autoloop_v3` wherever necessary so it converges to the final Book Architecture shape described below. You must implement the architecture, migrate the codebase to it, update tests and docs, and leave behind a clean, production-quality system.

This is a full implementation task, not a design-only task.

======================================================================
0. MISSION
======================================================================

Deliver the final `autoloop_v3` framework such that:

- `autoloop_v3.workflow` is the strict canonical kernel
- `autoloop_v3.runtime` is a workflow-agnostic filesystem runtime
- `autoloop_v3.stdlib` is a tiny optional authoring standard library
- `autoloop_v3.extensions` is a tiny optional extension surface
- there is no compatibility layer
- `autoloop_v1.py` and `Ralph_loop.py` are canonical strict workflows
- `autoloop_v1.py` runs with behavior equivalent to the legacy `autoloop/` codebase
- `Ralph_loop.py` remains clean, strict, explicit, and correct
- no regressions are introduced
- no unneeded complexity, obfuscation, speculative abstraction, or hidden behavior is introduced

Refactor aggressively if needed. Do not preserve old code merely because it exists. Keep what is correct. Remove what is wrong. Redesign where necessary.

======================================================================
1. BOOK ARCHITECTURE CRITERION
======================================================================

For every material design decision, choose the “Book Architecture” option.

Definition:

A Book Architecture is the ideal form of the system:
- smallest correct kernel
- sharp boundaries
- one meaning per concept
- no hidden coupling
- no drift-preserving shims
- explicit semantics
- side effects owned at the edge
- deterministic behavior
- testable contracts
- strong defaults for invariants
- optional extensions for orthogonal concerns
- composition over inheritance
- no second hidden execution model
- easy to explain in a few sentences after the design is understood

Do not choose the easiest local patch if it produces a worse long-term shape.
Do not preserve accidental architecture.
Do not add abstractions unless they solve a real cross-workflow problem.

======================================================================
2. SOURCE OF TRUTH PRECEDENCE
======================================================================

Use the following source-of-truth order:

1. The final architecture and rules in this prompt.
2. The current strict repo-root workflows `autoloop_v1.py` and `Ralph_loop.py` as readability and authoring-shape targets.
3. The latest `autoloop_v3` docs and ADRs only where they agree with this prompt.
4. The legacy `autoloop/` runtime as the behavioral oracle for Autoloop-v1 parity.
5. The current `autoloop_v3` code only as a starting point to refactor, not as final truth.

If the current `autoloop_v3` code conflicts with this prompt, follow this prompt.
If the repo-root strict workflows conflict with the legacy parity oracle, preserve parity while keeping the workflow definitions at least as explicit and readable.
Do not edit the legacy `autoloop/` oracle except to read it.

======================================================================
3. NON-NEGOTIABLE ARCHITECTURAL RULES
======================================================================

The final framework must obey all of the following:

1. No compatibility layer.
   - Delete `compat.py`.
   - Delete `Verdict`.
   - Delete `on_verdict`.
   - Delete `SessionLifecycle`.
   - Delete handler-arity adaptation.
   - Delete loader symbol injection.
   - Delete inferred entry behavior.
   - Delete any hidden normalization boundary.
   - Delete runtime or compiler code that exists only to tolerate malformed legacy workflows.

2. Runtime must be workflow-agnostic.
   The runtime may know:
   - task
   - run
   - checkpoint
   - generic workspace layout
   - generic sessions
   - generic events log
   - generic prompt loading
   - generic filesystem stores
   - provider/store wiring

   The runtime must NOT know:
   - phases as a domain concept
   - plan / implement / test semantics
   - Autoloop-v1 artifact names
   - Autoloop-v1 status semantics
   - raw phase log format
   - decisions ledger schema
   - phase-plan schema
   - git policy for any specific workflow
   - review/rework/replan semantics

3. Workflow-specific logic stays in workflows or workflow-owned harnesses/helpers.
   If only one workflow needs it, it does not belong in the kernel or generic runtime.

4. The workflow kernel stays strict.
   - One canonical API surface.
   - One execution model.
   - Definition-time validation.
   - Deterministic compilation.
   - Typed checkpoints.
   - Explicit sessions.
   - Optional PairStep/LLMStep handlers.
   - Required SystemStep handlers.

5. Extensions must be optional and invisible by default.
   No extension may run unless the workflow explicitly opts in.

6. `autoloop_v1.py` and `Ralph_loop.py` must not become harder to read.
   Never make them more hidden, more magical, less explicit, or more indirect than necessary.

======================================================================
4. WHAT THE FRAMEWORK SHOULD BE OPINIONATED ABOUT
======================================================================

The framework should be strongly opinionated about:
- strict canonical workflow shape
- class-definition-time validation
- deterministic compilation
- explicit sessions
- checkpoint-first resumability
- automatic generic event history
- artifact ownership and dependency validation
- required-artifact existence assertions
- explicit prompt provenance and deterministic resolution
- generic `.autoloop/tasks/{task_id}/runs/{run_id}` workspace layout
- config only for generic runtime/provider policy
- small typed protocols
- small typed extension seam
- layered testing and parity proof

The framework should NOT be opinionated about:
- phase schemas
- phase-plan meaning
- plan/implement/test domain semantics
- decisions ledger schema
- raw phase log schema
- git commit timing/messages
- workflow-specific status mapping
- workflow-specific artifact naming conventions
- workflow-specific topology semantics

======================================================================
5. THE FINAL PLACEMENT RULE
======================================================================

The final placement rule is:

- If it is an invariant that almost every workflow needs and almost nobody should disable, make it seamless by default.
- If it is an orthogonal operational concern whose behavior varies by workflow or deployment, make it policy-configured.
- If it changes workflow meaning, topology, semantic state, or domain behavior, make it explicit in workflow code.

Use this exact placement rule throughout the implementation.

======================================================================
6. WHAT MUST BE SEAMLESS BY DEFAULT
======================================================================

These behaviors must be automatic and framework-owned:

- strict workflow definition-time validation
- deterministic compilation into an immutable compiled workflow model
- typed checkpoint creation
- typed checkpoint-based resume
- session persistence and restore
- generic append-only `events.jsonl`
- immutable run request snapshot
- generic task/run workspace creation
- artifact registry compilation
- artifact uniqueness checks
- artifact dependency validation
- required-artifact existence assertion before step execution
- deterministic prompt resolution
- missing-session runtime errors with clear messages
- deterministic routing and unhandled-tag failures
- generic filesystem session persistence
- generic runtime/provider/store configuration loading

Workflow authors must not manually checkpoint, restore, or build generic event logs.

======================================================================
7. WHAT MUST BE POLICY-CONFIGURED
======================================================================

These behaviors may be configured through small typed configs/policies:

- generic workflow runtime defaults such as:
  - `max_steps`
  - `intent_mode`
- provider/model settings
- extension config
- extension failure mode
- session-path strategy for generic filesystem stores
- git extension config
- tracing extension config

Rules:
- config must stay small and typed
- config must not encode workflow meaning
- config must not become a second DSL
- config must not drive topology or semantic behavior
- workflow-specific commit policy or phase behavior must remain Python code, not config

======================================================================
8. WHAT MUST STAY EXPLICIT IN WORKFLOW CODE
======================================================================

These must remain visible in workflow code:

- `ctx.open_session(...)`
- step declarations
- transitions/topology
- SystemStep logic
- workflow-specific artifacts
- workflow-specific path conventions
- workflow-specific parsing such as phase-plan interpretation
- `on_outcome(...)` semantics or stdlib-assisted equivalent
- extension opt-in
- extension-specific policy objects
- any semantic state transitions
- any domain-specific status mapping
- any workflow-specific logs/ledgers/parity artifacts

Semantics must stay visible.
Do not hide workflow meaning behind runtime config or framework magic.

======================================================================
9. TARGET PACKAGE SHAPE
======================================================================

Refactor `autoloop_v3` to the following final shape or a cleaner equivalent with the same architectural boundaries:

autoloop_v3/
  workflow/
    __init__.py
    primitives.py
    prompts.py
    artifacts.py
    steps.py
    context.py
    validation.py
    compiler.py
    engine.py
    errors.py
    extensions.py
    providers/
      __init__.py
      protocols.py
      models.py
      fake.py
    stores/
      __init__.py
      protocols.py
      memory.py

  runtime/
    __init__.py
    cli.py
    config.py
    events.py
    loader.py
    prompts.py
    runner.py
    workspace.py
    stores/
      __init__.py
      filesystem.py

  stdlib/
    __init__.py
    control.py
    prompts.py
    steps.py
    state/
      __init__.py
      cursor.py

  extensions/
    __init__.py
    tracing.py
    session_paths.py
    git/
      __init__.py
      declaration.py
      policy.py
      repo.py
      runtime.py
      filters.py

  workflows/
    __init__.py
    autoloop_v1_parity.py
    autoloop_v1_conventions.py   # only if justified
    ...

If a module is unnecessary, delete it.
If a helper does not solve a real shared problem, do not add it.

======================================================================
10. KERNEL CONTRACT
======================================================================

The final canonical surface is:

From `workflow`:
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

From `workflow.primitives`:
- `Event`
- `Outcome`
- `Checkpoint`
- `ResolvedArtifacts`

No `Verdict`.
No `SessionLifecycle`.
No `on_verdict`.

Handlers:
- `on_start(self, ctx) -> None`
- `on_outcome(state, outcome) -> Event | None`
- Pair/LLM handlers: `(state, outcome, artifacts) -> State`
- System handlers: `(state, ctx) -> tuple[State, Event]`

Rules:
- PairStep and LLMStep handlers are optional
- if missing, state remains unchanged
- SystemStep handlers are required
- workflows must define `entry` explicitly
- workflows must import the names they use
- no loader-injected names

======================================================================
11. WORKFLOW EXTENSION MODEL
======================================================================

Add exactly one new kernel concept for extensibility:

- workflow-declared extensions

Purpose:
- enable optional orthogonal behaviors such as git tracking, tracing, metrics, session-path strategies
- keep the kernel strict
- keep workflow policy workflow-owned
- keep extensions invisible by default

The kernel must provide:
- `Workflow.extensions: tuple[WorkflowExtension, ...] = ()`

Create `autoloop_v3/workflow/extensions.py` with a minimal extension seam.

Use this shape or a cleaner equivalent:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from pydantic import BaseModel
from .primitives import Event, Outcome

@dataclass(frozen=True)
class RunBinding:
    root: Path
    task_id: str
    run_id: str
    workflow_name: str
    task_folder: Path
    run_folder: Path

@dataclass(frozen=True)
class StepStart:
    binding: RunBinding
    step_name: str
    step_kind: str
    state: BaseModel

@dataclass(frozen=True)
class StepFinish:
    binding: RunBinding
    step_name: str
    step_kind: str
    state_before: BaseModel
    state_after: BaseModel
    event: Event
    outcome: Outcome | None

@dataclass(frozen=True)
class TerminalFinish:
    binding: RunBinding
    terminal: str
    step_name: str | None
    state: BaseModel
    event: Event | None
    outcome: Outcome | None

class BoundWorkflowExtension(Protocol):
    def before_step(self, event: StepStart) -> None: ...
    def after_step(self, event: StepFinish) -> None: ...
    def on_terminal(self, event: TerminalFinish) -> None: ...

class WorkflowExtension(Protocol):
    def bind(self, binding: RunBinding) -> BoundWorkflowExtension: ...
````

Rules:

* bound extensions may perform side effects
* bound extensions may keep local bound state
* bound extensions may NOT mutate workflow state, routing, or core execution semantics
* extensions compose via tuple order
* extensions are strict by default
* best-effort behavior must be explicit, not implicit

Do not add a general event bus.
Do not add many ad hoc hook points.
Do not create a second workflow language.

======================================================================
12. STDLIB: PURE AUTHORING HELPERS
==================================

Add a very small `stdlib/` with only helpers that solve real repeated problems and compile down to kernel primitives.

Implement only these modules unless a new helper clearly solves a real shared problem:

1. `stdlib/control.py`

   * `global_routes(...)`
   * `merge_transitions(...)`
   * `pause_on_outcome_tags(...)`
   * maybe `event_on_outcome_tags(...)`

2. `stdlib/prompts.py`

   * `PromptBundle`
   * `PromptPair`

3. `stdlib/steps.py`

   * `pair_step(...)`

4. `stdlib/state/cursor.py`

   * `SequenceCursor`

Rules:

* `stdlib/` must import only standard library + `autoloop_v3.workflow`
* it must be pure authoring sugar
* it must not import `runtime` or `workflows`
* it must not introduce a second DSL
* it must not hide topology or semantics
* it must not use inheritance-heavy families

Do NOT add:

* `PhasedWorkflowBase`
* `ReactWorkflowBase`
* behavioral mixins that declare steps or handlers
* metaclass magic
* decorator DSL that rewrites topology
* config-driven workflow behavior

======================================================================
13. EXTENSIONS: OPTIONAL CROSS-CUTTING MODULES
==============================================

Add only these extension families initially:

1. `extensions/git/`
2. `extensions/session_paths.py`
3. `extensions/tracing.py`

Nothing else unless it clearly solves a real cross-workflow problem.

### 13.1 Git extension

Git tracking must have the following final shape:

* invisible by default
* workflow-declared opt-in
* workflow supplies config + policy
* before and after each step git behavior happens seamlessly
* kernel and generic runtime remain git-agnostic
* generic git repo mechanics live in the extension
* commit timing/messages/path policy live in workflow-owned policy objects

Workflow usage shape:

```python
extensions = (
    GitTracking(
        policy=AutoloopV1GitPolicy(),
        config=GitTrackingConfig(
            enabled=True,
            track_task_workspace_artifacts=True,
        ),
    ),
)
```

The extension package should include:

* `declaration.py`
* `policy.py`
* `repo.py`
* `runtime.py`
* `filters.py`

Rules:

* do not enable git globally from runtime config
* do not auto-enable git just because a repo exists
* do not hardcode Autoloop-v1 git policy into the extension
* keep raw delta computation separate from commit eligibility filtering
* do not put git semantics into the kernel or generic runtime

### 13.2 Session path extension

Provide only a generic optional session-path strategy surface.
Do not embed Autoloop-v1 `plan.json` or `phases/{phase}.json` conventions into the generic extension.
Autoloop-v1 exact filenames remain workflow-owned parity policy.

### 13.3 Tracing extension

Provide a small tracing extension using the same extension seam.
Do not turn tracing into core engine behavior.
Do not replace the generic `events.jsonl`.
Tracing is optional.

======================================================================
14. CONVENTIONS THE FRAMEWORK SHOULD ENFORCE
============================================

Adopt the following Book-shaped conventions.

### 14.1 Workflow package convention

Recommended, not mandatory:

* workflow module/package contains:

  * `workflow.py`
  * `prompts/`
  * optional `conventions.py`
  * optional `parity.py`

### 14.2 Prompt convention

* prompt paths may be explicit strings or `Prompt(...)`
* deterministic prompt resolution
* prefer workflow-module-relative prompt resolution
* `PromptBundle` optional
* no hidden global prompt registries

### 14.3 Artifact convention

* workflow declares all artifacts
* step `requires` and `produces` are real contracts
* resolved artifact handles are passed to handlers
* required-artifact existence is asserted before step execution
* no ad hoc file path resolution inside handlers

### 14.4 Session convention

* sessions declared as slots
* sessions opened explicitly at their birth moment
* sharing must be visible from the workflow
* no computed session identity
* no lifecycle enums
* no automatic session opening

### 14.5 Resumability convention

* typed checkpoint is canonical resume source
* `events.jsonl` is history, not sole resume state
* resume answers are injected exactly once through checkpoint state

### 14.6 Observability convention

* generic `events.jsonl` is always present
* workflow-owned extra logs remain local
* runtime event schema remains generic
* no workflow-specific raw logs in the generic runtime core

### 14.7 Shared control vocabulary

Soft convention only.
Recommend but do not reserve:

* `question`
* `blocked`
* `failed`

Provide stdlib helpers, but the workflow still opts in explicitly.

======================================================================
15. AUTOLOOP_V1 REQUIREMENTS
============================

`autoloop_v1.py` is the canary for readability and parity.
You must keep or improve its shape. Never make it worse.

Mandatory outcomes:

1. Keep the visible reading order:

   * State
   * Sessions
   * Artifacts
   * Steps
   * Transitions
   * Hooks/Handlers

2. Keep explicit session creation:

   * `plan_session` opened in `on_start`
   * `phase_session` opened in `on_activate_next_phase`

3. Keep explicit transitions and explicit per-phase semantics in workflow code.

4. Remove `phase_artifact_template(...)`.
   Inline explicit artifact templates directly in `autoloop_v1.py`.

5. Keep `parse_phase_ids` workflow-owned.

   * Inline it into `autoloop_v1.py` if only the workflow needs it
   * or move it into a tiny workflow-owned `autoloop_v1_conventions.py` only if it is genuinely shared with the parity harness

6. Keep the exact `phase_dir_key(...)` parity behavior workflow-owned.
   Do NOT promote the exact Autoloop `_pid-...` scheme into generic framework law.

7. Move any truly generic store/session logic out of Autoloop-v1 parity code and into the filesystem store.
   In particular:

   * session payload placeholder creation
   * session payload writes
   * legacy `thread_id` compatibility

8. Keep workflow-specific parity policy workflow-owned:

   * raw phase log format
   * decisions ledger format
   * clarification persistence
   * blocked/question/failed mapping
   * Autoloop-v1 session filename policy
   * cycle/attempt semantics for parity logs

9. Keep `run_autoloop_v1(...)`, but make it a thin composition root.
   It should wire:

   * generic runtime pieces
   * the generic extension seam
   * Autoloop-v1 session path policy
   * Autoloop-v1 parity log/ledger/status policy
   * optional git policy if enabled

10. Preserve functional equivalence to legacy `autoloop/main.py`.
    The legacy codebase remains the parity oracle.

Do NOT:

* push phase-plan logic into runtime core
* add generic workspace hook systems unless truly justified by multiple workflows
* add generic cycle counters to the engine
* add generic clarification-ledger abstractions
* hide Autoloop-v1 behavior inside runtime config

======================================================================
16. RALPH_LOOP REQUIREMENTS
===========================

`Ralph_loop.py` / `ralph_loop.py` must also be strict and readable.

Mandatory outcomes:

* canonical imports only
* `Outcome`, not `Verdict`
* `on_outcome`, not `on_verdict`
* explicit `entry`
* explicit session opening in `on_start`
* no `SessionLifecycle`
* strict handler signatures
* no loader-injected names

Correctness requirement:

* fix the `goal_met` state bug
* ensure `goal_met` is true on all success paths, including any success route from `plan_action`

Do not overcomplicate Ralph.
It should stay simple and visibly ReAct-shaped.

======================================================================
17. REMOVE OR REWRITE OUTDATED CODE AND DOCS
============================================

Refactor the current `autoloop_v3` codebase wherever necessary.

Required cleanup:

* remove `compat.py`
* remove compatibility docs that advertise removed behavior
* remove tests that assert removed compatibility behavior
* remove stale ADR/doc wording about `Verdict`, `SessionLifecycle`, `on_verdict`, loader symbol injection, handler adaptation, or inferred entry
* rename or rewrite docs so they describe the final strict architecture, not the old compat design

All docs must converge to the final Book shape.

Update:

* `ARCHITECTURE_DECISIONS.md`
* `README.md`
* `MIGRATION.md`
* `docs/architecture.md`
* `docs/authoring.md`
* `docs/parity-matrix.md`
* `docs/risk-register.md`
* ADRs

All architectural docs must reflect the final shape:

* no compat layer
* strict kernel
* generic runtime
* workflow-declared extensions
* tiny stdlib
* tiny extensions package
* workflow-owned policy
* typed checkpoints
* explicit sessions
* automatic generic event history
* git as workflow opt-in extension, not runtime policy

======================================================================
18. WHAT NOT TO DO
==================

Do NOT drift into any of these unwanted architectures:

* no compatibility layer under another name
* no hidden normalization boundary
* no runtime or compiler support for malformed workflows
* no `SessionLifecycle`
* no `Verdict`
* no `on_verdict`
* no handler arity adaptation
* no loader-injected names
* no inferred entry
* no runtime phase awareness
* no Autoloop-specific policy in generic runtime
* no git policy in generic runtime
* no generic workspace hook system unless clearly justified by multiple workflows
* no phase library in the kernel
* no behavioral mixins
* no workflow-family inheritance
* no `PhasedWorkflowBase`
* no `ReactWorkflowBase`
* no decorator DSL that rewrites workflows
* no metaclass magic
* no config-as-language
* no giant plugin/event-bus architecture
* no monolithic runtime service object
* no generic abstractions that only serve one workflow
* no second hidden execution model
* no making `autoloop_v1.py` or `Ralph_loop.py` more indirect, magical, or hard to read

If an abstraction only helps one workflow, keep it in that workflow’s owned code.

======================================================================
19. TESTING REQUIREMENTS
========================

Replace or update the current tests to prove the final strict architecture.

You must have layered proof:

### Unit tests

* primitives
* stores
* artifact resolution
* prompt resolution
* validation failures
* extension helper units
* git extension filtering/repo logic
* session path policies

### Engine contract tests

* PairStep contract
* LLMStep contract
* SystemStep contract
* Pair/LLM handlers optional
* System handlers required
* deterministic routing
* pause/resume
* answer injection exactly once
* missing session fails clearly
* artifact existence assertions
* extension lifecycle invocation
* extension failure semantics

### Runtime integration tests

* generic workspace layout
* request snapshot
* events.jsonl
* checkpoint files
* session persistence
* prompt resolution
* CLI wiring
* no workflow-specific runtime knowledge

### Strictness / no-compat tests

* no `compat.py`
* no `Verdict`
* no `SessionLifecycle`
* no `on_verdict`
* no loader symbol injection
* no inferred entry
* no handler adaptation
* no generic runtime phase knowledge
* repo-root `workflow` shim, if present, must be strict re-export only

### Workflow tests

* `autoloop_v1.py` strict workflow happy path
* `autoloop_v1.py` rework loop
* `autoloop_v1.py` replan loop
* `autoloop_v1.py` pause/resume with clarification persistence
* `autoloop_v1.py` multi-phase scoped session sharing
* `autoloop_v1.py` explicit artifact templates
* `Ralph_loop.py` happy path
* `Ralph_loop.py` goal_met correctness
* at least one unrelated toy workflow proving generic runtime neutrality

### Parity tests against legacy `autoloop/`

Must prove Autoloop-v1 parity for:

* workspace layout
* request snapshot
* checkpoint semantics
* `events.jsonl` status compatibility where required
* raw phase log behavior
* decisions ledger behavior
* clarification persistence
* session filename behavior
* phase session sharing
* blocked/question/failed behavior
* final success behavior
* legacy status readers where still relevant
* legacy session payload compatibility (`thread_id` etc.)

No architectural claim counts unless it is proved in tests.

======================================================================
20. DESIGN-DECISION PROCESS REQUIREMENT
=======================================

Before or during implementation, update the architecture decision record so it reflects the final design.

For every material design decision, provide:

* Candidate A
* Candidate B
* Candidate C
* evaluation against:

  * correctness
  * simplicity
  * extensibility
  * observability
  * testability
  * migration risk
  * parity impact
* chosen decision
* why it is the Book choice
* why the others lost

At minimum include decisions for:

* package layout
* canonical public surface
* removal of compat
* strict workflow migration
* session model
* artifact registry
* prompt model
* validation/compilation model
* checkpoint model
* provider/store protocols
* runtime harness design
* configuration boundaries
* stdlib shape
* extension seam
* git extension placement
* session-path strategy
* observability/event model
* testing strategy

Keep the record concise but precise.

======================================================================
21. IMPLEMENTATION ORDER
========================

Use this implementation order unless a clearly better sequence emerges:

1. Freeze/update docs and ADRs to the final target shape.
2. Remove compat concepts from the public surface and codebase.
3. Implement the final strict kernel shape:

   * validation
   * compiler
   * engine
   * context
   * primitives
   * stores/protocols
   * workflow/extensions.py
4. Implement the final generic runtime:

   * workspace
   * events
   * runner
   * loader
   * filesystem store
   * prompt resolution
   * config
   * CLI
5. Add the tiny `stdlib/`.
6. Add the tiny `extensions/` surface.
7. Migrate `autoloop_v1.py`.
8. Migrate `Ralph_loop.py`.
9. Refactor `autoloop_v1_support` into the final thin parity/composition shape.
10. Implement git as workflow-declared extension.
11. Finish parity tests.
12. Run the full suite and fix all regressions.

======================================================================
22. ACCEPTANCE BAR
==================

The work is complete only when all of the following are true:

* `autoloop_v3.workflow` is strict and compatibility-free
* `autoloop_v3.runtime` is generic and workflow-agnostic
* `stdlib/` exists and stays tiny
* `extensions/` exists and stays tiny
* workflows declare optional extensions explicitly
* extensions are invisible by default
* git tracking is workflow opt-in and seamless before/after each step once opted in
* `autoloop_v1.py` is at least as explicit/readable as its current strict form
* `autoloop_v1.py` no longer uses `phase_artifact_template`
* `Ralph_loop.py` is strict and correct
* no unwanted architecture or hidden compat behavior remains
* docs match the final system
* tests prove strictness, genericity, extensions, and parity
* Autoloop-v1 remains functionally equivalent to legacy `autoloop/`
* no regressions have been introduced

======================================================================
23. FINAL REPORT
================

When done, provide:

1. final file tree
2. summary of the final architecture
3. explicit list of removed compatibility features
4. summary of the extension model
5. summary of `stdlib/`
6. summary of the git extension design
7. summary of the `autoloop_v1.py` and `Ralph_loop.py` migrations
8. parity results vs legacy `autoloop/`
9. test results
10. remaining risks, if any

Do the full refactor.
Refactor or redesign `autoloop_v3` wherever necessary.
Do not protect bad architecture from deletion.
Keep or improve `autoloop_v1.py` and `Ralph_loop.py`.
Never make them worse through unnecessary complexity, obfuscation, or regression.
Always choose the Book Architecture.

```
```
