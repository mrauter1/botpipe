You are implementing a new workflow runtime and execution engine in a brand-new folder named `autoloop_v3`.

Your job is to fully, correctly, and production-readily implement the engine and supporting runtime so that it can execute:
1. the Workflow Definition Specification v1.1 described below,
2. the existing `Autoloop_v1` workflow in the workspace,
3. the existing Ralph Loop workflow(s) in the workspace,
with no regressions.

This is not an in-place refactor of the current implementation. Do not “improve” the existing `autoloop` package in place. Do not rewrite the current folder as the main implementation target. Build a new implementation under `autoloop_v3/` and keep the old codebase intact as a behavioral oracle and parity target.

Non-negotiable requirements:
- `autoloop_v3` must be the new implementation root.
- The engine must fully implement Workflow Definition Specification v1.1.
- The engine must run the given `Autoloop_v1` and Ralph Loop workflows correctly.
- `Autoloop_v1` workflow features and outputs must be equivalent or superior to the current Autoloop codebase in the workspace.
- No regressions are allowed.
- If you improve something, the improvement must be backward-compatible and test-proven.
- Do not stop at design. Implement the engine, stores, providers/interfaces, compatibility layer, CLI/runtime harness if needed, tests, and docs.

BOOK ARCHITECTURE DEFINITION

Use “book architecture” as the selection standard for every important design decision.

Definition of “book architecture”:
A book architecture is the ideal reference architecture one would publish in a high-quality systems design book. It is:
- explicit in contracts and invariants,
- minimal in accidental complexity,
- high-cohesion and low-coupling,
- deterministic and testable,
- layered cleanly with strict boundaries,
- extensible through protocols/interfaces rather than ad hoc conditionals,
- observable and debuggable,
- backward-compatible through isolated adapters rather than contaminating the core,
- easy to reason about under failure, pause/resume, and partial state,
- suitable for long-term maintenance.

When choosing between options, prefer the architecture that best matches that definition, even if it requires slightly more upfront structure.

MANDATORY DECISION PROCESS

Before finalizing each material design decision, create exactly 3 candidate solutions and evaluate them. This is mandatory.

For every non-trivial design decision, produce a compact ADR entry containing:
- Decision name
- Candidate A
- Candidate B
- Candidate C
- Evaluation of each candidate on:
  - correctness,
  - compatibility,
  - simplicity,
  - extensibility,
  - observability,
  - testability,
  - failure handling,
  - performance,
  - migration risk
- Selected option
- Why the selected option is the book architecture choice

Do this for all important decisions, including at minimum:
- package/module layout,
- workflow compilation model,
- topology/routing representation,
- artifact registry and resolution,
- checkpoint persistence model,
- session binding model,
- provider protocol design,
- compatibility strategy for legacy/workspace drift,
- handler dispatch and signature adaptation,
- resume/answer injection mechanism,
- validation architecture,
- event/logging model,
- CLI/runtime harness layout,
- testing strategy.

Do not merely state that you considered alternatives. Actually write them down in the repo, preferably as ADRs under something like `autoloop_v3/docs/adr/`.

PRIMARY SOURCES OF TRUTH

Treat these as authoritative, in this order:
1. The Workflow Definition Specification v1.1 in this prompt.
2. The actual workspace workflows that must run, including `Autoloop_v1` and Ralph Loop.
3. The current Autoloop codebase in the workspace as the feature-parity and behavior oracle.
4. Existing artifacts, templates, tests, and runtime conventions in the workspace.

If the current codebase and the new spec differ:
- the core engine must implement the new spec cleanly,
- but the runtime must include a compatibility layer sufficient to run the existing workspace workflows without regressions,
- compatibility must be isolated from the clean core.

DO NOT ask for clarification unless absolutely unavoidable. Inspect the workspace and make the best grounded decisions.

WORKFLOW DEFINITION SPECIFICATION V1.1 TO IMPLEMENT

You must implement these primitives and contracts.

1. Core primitives
- `Event(tag: str, reason: str = "", question: str | None = None)`
- `Outcome(raw_output: str, tag: str, reason: str = "", clarification: str | None = None, question: str | None = None, payload: dict[str, Any] = {})`
- Terminal sentinels:
  - `SUCCESS`
  - `PAUSE`
  - `FAIL`
  - `GLOBAL`

2. Workflow base class
A workflow must expose:
- nested `State` class inheriting from `pydantic.BaseModel`
- `entry`
- `transitions`
Optional:
- `name`
- `log_artifacts`

3. State
- Persist state between steps and runs.
- Treat state as immutable.
- Handlers return a new state.
- Use `model_copy(update=...)` semantics.

4. Sessions
- `Session` is a slot marker.
- Bind concrete sessions at runtime via `ctx.open_session(ref, scope=None)`.
- Support scoped sessions so phase/thread isolation works.

5. Artifacts
Implement:
- `Artifact(template: str, name: str | None = None, owner: Step | None = None)`
- Workflow-level artifacts
- Step `produces`
- Step `requires`
- unified compiled artifact registry
- `ResolvedArtifacts`
- `ArtifactHandle` with:
  - `read_text() -> str`
  - `write_text(content: str) -> None`
  - `append(content: str) -> None`
  - `exists() -> bool`

Artifact path resolution rules:
- support placeholders:
  - `task_id`
  - `run_id`
  - `task_folder`
  - `run_folder`
  - `state`
- support dot notation like `{state.phase.id}`
- missing keys resolve to empty string

6. Steps
Implement:
- `PairStep`
- `LLMStep`
- `SystemStep`

PairStep execution contract:
1. resolve artifacts
2. call producer -> raw string
3. append raw output to log artifacts
4. call verifier -> `Outcome`
5. middleware interception
6. step handler updates state
7. route using tag

LLMStep execution contract:
1. resolve artifacts
2. call provider -> `Outcome`
3. append raw output to log artifacts
4. middleware interception
5. optional handler updates state
6. route using tag

SystemStep execution contract:
1. mandatory handler returns `(State, Event)`
2. no middleware
3. route using event tag

7. Handlers
Lifecycle hooks:
- `on_start(self, ctx) -> None`
- `on_outcome(state, outcome) -> Event | None`

Step handlers:
- `on_{name}(state, outcome, artifacts) -> State` for PairStep/LLMStep
- `on_{name}(state, ctx) -> tuple[State, Event]` for SystemStep

8. Context API
Implement a stable `Context` object exposing:
- `task_id`
- `run_id`
- `task_folder`
- `run_folder`
- `state`
- `answer`
- `open_session(ref, scope=None)`
- `get_session(ref)`

9. Routing
Implement topology lookup:
- step-local transition first
- then `GLOBAL`
- else runtime error

10. Prompts
Support:
- direct string paths
- `Prompt(path: str)`
- optional `PromptRegistry`

11. Checkpointing and resume
Implement:
- `Checkpoint(stage, state, session_bindings, pending_question=None, pending_answer=None)`
- save/load checkpoint
- pause semantics
- resume semantics
- answer injection on resume

12. Provider protocols
Implement protocols/interfaces for:
- `LLMProvider`
- `SessionStore`
- `CheckpointStore`

13. Definition-time validation
At workflow class definition time, validate:
- State exists and is a Pydantic model
- entry exists and is a step
- transitions exists and is a dict
- every SystemStep has a handler
- no orphan handlers
- topology destinations are valid
- artifact names are unique
- artifact dependency graph is acyclic
- every required artifact is produced earlier or is workflow-level
- session refs in steps are declared

CURRENT WORKSPACE PARITY REQUIREMENTS

The new engine is not enough by itself unless it can reproduce or exceed current behavior. Treat the current Autoloop implementation as a parity oracle. The new runtime must preserve at least these operational capabilities where relevant:

- task/run workspace layout under `.autoloop/tasks/{task_id}/runs/{run_id}`
- immutable request snapshot behavior
- raw logs and events log behavior
- decisions/clarification ledger behavior
- phase planning and phase activation behavior
- explicit and implicit phase handling
- phase-local artifact scoping
- scoped phase sessions
- pause on questions and blocked states
- resume from checkpoints and stored sessions
- provider abstraction and provider session persistence
- verifier/producer loop behavior
- compatibility with the loop-control contract where the workspace workflows require it
- configuration/runtime harness sufficient to actually execute workspace workflows end-to-end
- testable parity with the old implementation

AUTOLLOP_V1 AND LEGACY/WORKSPACE COMPATIBILITY

The core engine must be clean and spec-compliant, but the runtime must tolerate workspace drift needed to run the provided workflows.

Implement a compatibility layer that is isolated from the clean core and supports, if present in the workspace:
- `Verdict` as an alias or compatibility wrapper for `Outcome`
- `on_verdict` as a compatibility alias for `on_outcome`
- step handlers with multiple legacy-compatible arities, such as:
  - `(state, outcome, artifacts)`
  - `(state, outcome)`
  - `(state, verdict, artifacts)`
  - `(state, verdict)`
- workflow normalization before strict compilation
- any other small compatibility shims required by actual workspace workflows

Important:
- do not pollute the clean core with legacy conditionals everywhere,
- normalize/adapt legacy workflows in one place, then compile them into the strict engine model.

EXPECTED IMPLEMENTATION SHAPE

Build the new system under `autoloop_v3/`.

Use a book-architecture layout. A strong default is:
- `autoloop_v3/workflow/`
  - `__init__.py`
  - `primitives.py`
  - `prompts.py`
  - `artifacts.py`
  - `steps.py`
  - `context.py`
  - `validation.py`
  - `compiler.py`
  - `engine.py`
  - `compat.py`
  - `providers/`
  - `stores/`
- `autoloop_v3/runtime/`
  - filesystem-backed stores
  - provider adapters
  - runner/CLI harness
- `autoloop_v3/tests/`
- `autoloop_v3/docs/`

You may choose a better module split if your ADR process proves it is the book architecture choice.

IMPLEMENTATION RULES

- Strong typing throughout.
- Clean error model.
- Filesystem-backed default stores for checkpoints/artifacts/sessions.
- Deterministic engine behavior.
- No hidden globals.
- No silent failure swallowing.
- Best-effort checkpoint on failure.
- Excellent unit and integration tests.
- Keep the public workflow authoring surface small and stable.
- Preserve import ergonomics needed by the workspace workflows.
- If existing workflows import `workflow`, provide a compatible public API surface without editing their source unless strictly required for test fixtures.

TESTING REQUIREMENTS

You must build an extensive test suite that proves correctness and parity.

At minimum include:
1. unit tests for all primitives and stores
2. artifact resolution tests, including dot notation and missing-key behavior
3. routing tests, including `GLOBAL`
4. lifecycle hook tests
5. PairStep contract tests
6. LLMStep contract tests
7. SystemStep contract tests
8. checkpoint save/load tests
9. pause/resume tests
10. answer injection tests
11. definition-time validation tests for all required failures
12. compatibility-layer tests
13. golden tests for `Autoloop_v1`
14. golden/integration tests for Ralph Loop workflows
15. parity tests comparing old and new behavior for critical scenarios
16. failure-path tests, including handler exceptions and missing artifacts
17. tests for phase-scoped sessions and phase artifact scoping

Use fake providers and fake stores to keep tests deterministic. Add filesystem integration tests for the default runtime.

DELIVERABLES

Produce all of the following:
1. the implementation under `autoloop_v3/`
2. ADRs documenting major decisions with 3 candidates each
3. a concise architecture document
4. a parity matrix mapping current Autoloop behavior to the new engine/runtime
5. a compatibility note describing legacy/workspace shims
6. tests proving the engine works
7. a minimal runner/CLI or execution harness sufficient to run the target workflows in practice
8. developer documentation for authoring workflows against the new engine

ACCEPTANCE GATES

The task is complete only if all of the following are true:
- `autoloop_v3` exists and contains the new implementation
- the engine is cleanly layered and documented
- the engine conforms to Workflow Definition Specification v1.1
- `Autoloop_v1` executes correctly
- Ralph Loop workflow(s) execute correctly
- no existing required behavior regresses
- tests are comprehensive and passing
- compatibility shims are isolated and justified
- the architecture chosen is the book architecture choice and the ADRs prove why

EXECUTION ORDER

Follow this order:
1. inspect workspace workflows, templates, current Autoloop implementation, and Ralph Loop assets
2. build a feature-parity inventory and risk list
3. write ADRs with 3 candidates per major decision
4. choose the book architecture options
5. implement the clean core
6. implement compatibility normalization/adapters
7. implement runtime/stores/providers/harness
8. write tests
9. prove parity
10. document remaining risks, if any, and eliminate them if possible

Important final instruction:
Do not produce a shallow scaffold. Do not stop at interfaces. Implement the real engine end-to-end.
