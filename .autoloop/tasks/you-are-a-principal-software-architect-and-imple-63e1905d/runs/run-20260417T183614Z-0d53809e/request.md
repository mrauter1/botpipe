You are a principal software architect and implementation agent.

Use `autoloop_v3/` as the implementation workspace.

Your mission is to transform `autoloop_v3/` into the final framework. The result must be a clean, strict, book-architecture implementation of the workflow engine and runtime, with no compatibility layer, while still being able to run `autoloop_v1.py` with functionality equivalent to the legacy Autoloop codebase in `autoloop/`.

You must inspect the current repository, understand the existing `autoloop_v3` implementation, understand the legacy `autoloop/` codebase, redesign where necessary, fully implement the result, migrate workflows to the strict surface, remove the compat layer completely, and leave behind a complete tested system.

This is a full implementation task, not a design-only task.

======================================================================
0. CORE OBJECTIVE
======================================================================

Deliver a final `autoloop_v3` framework such that:

- `autoloop_v3` contains the final engine and runtime
- the compatibility layer is completely removed
- `autoloop_v1.py` and other workflows are implemented directly from the canonical primitives plus normal Python / standard library code
- `PairStep` and `LLMStep` handlers are optional, not required
- anything specific to a single workflow is defined by that workflow, not by the runtime
- anything generalizable enough to be used by multiple workflows may live in the framework standard library or by convention
- things that are policy rather than architecture may be optional configuration
- the final framework can run `autoloop_v1.py`
- the end result for `autoloop_v1.py` is functionally equivalent to the legacy `autoloop/` implementation
- no regressions are allowed

======================================================================
1. BOOK ARCHITECTURE REQUIREMENT
======================================================================

Paul Erdős spoke of “Proofs from The Book”: arguments so elegant and compressed that they feel like the ideal form of the result. Software architecture has an analogous phenomenon. Occasionally, after years of partial solutions and accumulated complexity, someone finds a construction that reorganizes the whole problem. The resulting design is strikingly short to explain, yet it resolves far more than its surface simplicity suggests. It can feel like discovering a new chess opening: initially counterintuitive, then obviously potent. Not every architecture problem has such a solution, and one should not expect this generally. But when a system yields a design of that kind, it is worth recognizing it for what it is: a Book Architecture.

Use that definition as the decision rule.

For every material design decision, generate the best 3 candidate solutions, compare them, and choose the one that is the ideal Book Architecture choice.

A Book Architecture is one that has:

- a crisp domain model
- sharp boundaries
- minimal stable public contracts
- explicit ownership of side effects
- no hidden coupling
- no workflow-domain leakage into the runtime core
- strong testability
- deterministic behavior
- replaceable adapters
- a short, elegant explanation once understood
- less machinery than the alternatives, not more
- better correctness and extensibility at the same time

Do not choose the quickest or most incremental option just because it is convenient. Choose the architecture that best satisfies the Book Architecture standard.

======================================================================
2. NON-NEGOTIABLE RULES
======================================================================

The following are mandatory:

1. `autoloop_v3/` is the implementation workspace.
   - Build there.
   - Refactor there.
   - Remove and replace modules there as needed.

2. Do not treat the legacy `autoloop/` code as the architecture.
   - It is the behavioral oracle for Autoloop_v1 parity.
   - It is not the target architecture.

3. Remove the compat layer completely.
   - Delete `workflow.compat` or equivalent.
   - Remove all legacy normalization pathways.
   - Remove runtime or compiler branching that exists only to support old workflow drift.
   - Remove loader hacks whose only purpose is to make legacy workflow definitions compile without using the canonical API.

4. Rewrite workflows to the canonical surface.
   - `autoloop_v1.py`
   - `Ralph_loop.py` or `ralph_loop.py`
   - any other workflows in scope
   They must become first-class strict workflows, not legacy payloads tolerated through shims.

5. The runtime must be workflow-agnostic.
   The runtime may know only:
   - task
   - run
   - workflow primitives
   - steps
   - events
   - outcomes
   - terminals
   - sessions
   - prompts
   - artifacts
   - checkpoints
   - provider/store protocols
   - routing
   - logging/observability
   - generic config

   The runtime must NOT know about:
   - phases as a domain concept
   - plan / implement / test as hardcoded orchestration concepts
   - Autoloop-specific artifact names
   - Autoloop-specific tags
   - workflow-specific loop semantics
   - workflow-specific phase plans
   - workflow-specific review logic

6. PairStep and LLMStep handlers are optional.
   - If omitted, the engine must still run correctly.
   - Only SystemStep handlers are mandatory.

7. Workflow-specific logic belongs in workflows.
   - If something is specific only to `autoloop_v1`, put it in `autoloop_v1.py` or an `autoloop_v1`-owned helper module.
   - Do not put it in the runtime core.

8. General reusable logic may live in the framework standard library.
   - Only if it is genuinely reusable by multiple workflows.
   - Only if it remains domain-neutral.
   - If unsure, bias toward workflow-owned code rather than polluting the standard library.

9. Policy should be configuration when appropriate.
   Example:
   - git tracking policy
   - optional artifact tracking
   - logging verbosity
   - provider settings
   - sandboxing policy
   But configuration must not be used to smuggle workflow-specific orchestration into the runtime.

======================================================================
3. CANONICAL EXECUTION MODEL
======================================================================

Implement Workflow Definition Specification v1.1 as the canonical model.

Use the following as the stable conceptual contract:

Primitives:
- `Event`
- `Outcome`
- `SUCCESS`
- `PAUSE`
- `FAIL`
- `GLOBAL`

Workflow:
- nested `State` model
- `entry`
- `transitions`
- optional `name`
- optional `log_artifacts`

Sessions:
- declared as `Session` slots
- opened explicitly with `ctx.open_session(...)`
- looked up with `ctx.get_session(...)`

Artifacts:
- path templates
- resolved generically
- workflow-level and step-level
- dot-path access into state supported

Prompts:
- canonical `Prompt`
- strings may be supported only if that is chosen as part of the canonical surface, not as legacy drift

Steps:
- `PairStep`
- `LLMStep`
- `SystemStep`

Handlers:
- `on_start(self, ctx) -> None`
- `on_outcome(state, outcome) -> Event | None`
- `on_{step}` for Pair/LLM: `(state, outcome, artifacts) -> State`
- `on_{step}` for System: `(state, ctx) -> tuple[State, Event]`

Routing:
- step-local route first
- then `GLOBAL`
- else runtime error

Checkpoints:
- typed snapshot
- checkpointed pause/resume
- explicit session bindings
- explicit pending question/answer fields

Provider/store contracts:
- small
- typed
- replaceable

Definition-time validation:
- strict
- canonical
- no hidden compatibility fallback

======================================================================
4. SESSION MODEL REQUIREMENT
======================================================================

Adopt the explicit session model:

Sessions are not computed. They are created.

The engine must not compute session identity from workflow state by evaluating session templates or session key functions at step execution time.

The architecture must be:

- a session is declared as a slot on the workflow
- a session is created when `ctx.open_session(slot, scope=...)` is called
- the slot stays bound until it is rebound
- sharing is visible from workflow topology and session-opening moments
- the engine’s step execution path performs a lookup, not a derivation

The engine-side model should be conceptually as simple as:

`session = ctx.get_session(step.session)`

No session template evaluation.
No session registry that computes keys from state on demand.
No hidden identity derivation.
No implicit sharing rules.

If a slot is not opened, the error should clearly identify which session slot was never opened.

For `autoloop_v1.py`:
- the plan session is opened in `on_start`
- the phase session is opened in `activate_next_phase`
- implement and test share the phase session because nothing rebinds it between those steps

This explicit session creation model is part of the target architecture.

======================================================================
5. WHAT MUST BE REMOVED
======================================================================

You must completely remove:

- `compat.py`
- any equivalent compatibility module
- `on_verdict` compatibility shims
- `Verdict`-style legacy middleware normalization if it exists only for compatibility
- handler arity adaptation added solely for legacy workflows
- `SessionLifecycle.ON_START` compatibility mechanisms if they exist only as legacy drift
- loader hacks that inject names so legacy workflows compile without importing canonical symbols
- inferred-entry behavior used only to tolerate old workflows
- any runtime behavior that exists only to preserve old malformed workflow declarations

After the migration, workflows must be correct workflows, not legacy workflows papered over by the framework.

======================================================================
6. WHAT MUST BE MIGRATED
======================================================================

Rewrite workflows so they are canonical and self-sufficient:

At minimum:
- `autoloop_v1.py`
- `Ralph_loop.py` / `ralph_loop.py`

They must:
- import the canonical symbols they use
- define `entry` explicitly
- use `Outcome`, not legacy-only aliases
- use `on_outcome`, not `on_verdict`
- use strict handler signatures
- explicitly open sessions with `ctx.open_session`
- avoid depending on any compat loader, compat adapter, or legacy authoring shim

They should be understandable directly from:
- primitives
- standard library
- the framework’s canonical surface

======================================================================
7. WORKFLOW-SPECIFIC VS FRAMEWORK-SPECIFIC PLACEMENT
======================================================================

Use this rule rigorously:

If a behavior is only needed by one workflow, it must not live in the runtime core.

Examples likely specific to `autoloop_v1` and therefore workflow-owned unless proven otherwise:
- phase-plan parsing or activation logic
- phase-specific artifact conventions
- plan -> implement -> test topology
- phase status tracking if only `autoloop_v1` uses it
- clarification-note placement rules if only needed for Autoloop parity
- any domain semantics of “plan”, “implement”, “test”, “needs_replan”, “needs_rework”, etc.

Examples that may live in a reusable framework standard library if they are truly reusable:
- artifact template resolution
- JSON/YAML utility helpers
- event logging primitives
- checkpoint stores
- session stores
- prompt registries
- filesystem workspace helpers
- generic git helper functions, if kept policy-free
- generic append-only ledger helpers, if not Autoloop-specific by meaning

If a reusable abstraction is weak or speculative, do not lift it into the framework. Keep it local to the workflow.

======================================================================
8. CONFIGURATION RULE
======================================================================

What should be configuration may be optional configuration.

Examples:
- git tracking enabled/disabled
- whether framework artifacts are committed
- provider model settings
- event logging policy
- workspace root conventions
- sandbox policy
- provider wiring

But configuration must not turn the runtime into a workflow-specific policy engine.

If a knob exists only because one workflow needs it, reconsider its placement. It may belong in the workflow, not the runtime config.

======================================================================
9. PARITY REQUIREMENT FOR AUTOLOOP_V1
======================================================================

The final framework must be able to run `autoloop_v1.py` and the end result must be functionally equivalent to the legacy Autoloop codebase in `autoloop/`.

Use the legacy `autoloop/` folder as the parity oracle.

Preserve or improve, as applicable:
- `.autoloop/tasks/{task_id}/runs/{run_id}` workspace structure
- request snapshot behavior
- event log behavior
- checkpoint behavior
- pause/resume behavior
- question / blocked / failed behavior
- raw log behavior
- decisions / clarification persistence behavior
- session persistence behavior
- provider/session persistence semantics as needed for parity
- end-to-end workflow result and artifact production for `autoloop_v1`

If a legacy behavior is operationally important for `autoloop_v1`, parity-test it.

No regressions are allowed.

======================================================================
10. REQUIRED DESIGN PROCESS
======================================================================

Before changing code, identify all material design decisions.

At minimum include:
- package/module layout
- canonical public API surface
- removal of compat layer
- workflow migration strategy
- session model
- artifact registry and resolution
- prompt model
- workflow compilation/validation model
- checkpoint model
- provider/store protocol design
- runtime harness design
- configuration design
- git policy placement
- observability/event model
- parity-testing strategy
- migration strategy from current `autoloop_v3`

For each design decision:
- provide the best 3 candidate solutions
- compare them on correctness, simplicity, extensibility, observability, testability, migration risk, and parity impact
- choose the best one
- explain why it is the Book Architecture choice
- explain why the other two lost

Write this to:

`autoloop_v3/ARCHITECTURE_DECISIONS.md`

Do not skip this.
Do not collapse to one option without comparison.

======================================================================
11. SOURCE MATERIAL TO REVIEW
======================================================================

Review at minimum:

- current `autoloop_v3/` implementation
- current `autoloop_v3` docs and tests
- current compat-layer behavior
- current workflow files
- legacy `autoloop/` runtime
- legacy loop-control and runtime helpers
- current parity and risk docs

Use the current `autoloop_v3` as the starting codebase.
Use `autoloop/` as the behavioral oracle for Autoloop_v1 parity.

======================================================================
12. IMPLEMENTATION RULES
======================================================================

You must:

1. fully refactor `autoloop_v3/` into the final architecture
2. remove the compat layer completely
3. migrate workflows to the canonical surface
4. keep the runtime core generic
5. move workflow-specific logic out of the runtime core
6. ensure PairStep and LLMStep handlers are optional
7. ensure SystemStep handlers are required
8. make session creation explicit via `ctx.open_session`
9. make session lookup a direct lookup, not computed identity derivation
10. leave behind a complete, runnable framework
11. leave behind a complete test suite
12. leave behind migration and architecture documentation
13. leave no TODOs or placeholder paths in core execution

======================================================================
13. PACKAGE QUALITY TARGET
======================================================================

The final package should read like a crisp reference implementation.

Target reading order:
- primitives
- public authoring API
- artifacts/prompts/sessions/steps
- validation and compilation
- engine
- stores/providers
- runtime harness
- workflow implementations
- tests

It should be obvious where:
- generic engine behavior lives
- reusable framework library behavior lives
- workflow-specific behavior lives
- configuration lives
- parity-specific harness behavior lives

======================================================================
14. TEST REQUIREMENTS
======================================================================

Add or update tests to prove all of the following:

Engine contract:
- PairStep contract
- LLMStep contract
- SystemStep contract
- Pair/LLM handlers optional
- System handlers required
- routing precedence
- pause/resume
- answer injection
- session creation and lookup
- explicit session rebinding behavior
- artifact template resolution
- validation failures

No-compat proof:
- workflows compile and run without compat layer
- no loader-injected canonical symbols are required
- no legacy handler adaptation is required
- no `on_verdict` / compat middleware path exists
- no inferred-entry fallback exists

Workflow proof:
- strict `autoloop_v1.py` runs successfully
- strict `Ralph_loop.py` / `ralph_loop.py` runs successfully
- explicit session-opening moments are tested
- Autoloop_v1 phase-session sharing is tested through topology and rebinding, not through computed keys

Parity proof against legacy `autoloop/`:
- workspace layout
- key artifact outputs
- event log behavior
- clarification behavior
- request snapshot behavior
- resume semantics relevant to `autoloop_v1`
- overall successful run behavior for `autoloop_v1`

Add at least one toy workflow with totally unrelated step names to prove the runtime does not know about phases or about plan/implement/test.

======================================================================
15. REQUIRED DOCUMENTS
======================================================================

At minimum produce or update:

- `autoloop_v3/ARCHITECTURE_DECISIONS.md`
- `autoloop_v3/README.md`
- `autoloop_v3/MIGRATION.md`
- any necessary authoring documentation
- any necessary parity notes

Document clearly:
- the canonical public API
- the explicit session model
- the removal of compat
- how workflow-specific logic is separated from the runtime
- what remains configurable
- what parity with legacy Autoloop_v1 means and how it is tested

======================================================================
16. PROHIBITED SOLUTIONS
======================================================================

Do NOT do any of the following:

- keep `compat.py` under another name
- silently preserve legacy authoring drift inside the compiler or engine
- hardcode Autoloop_v1 concepts into the runtime
- compute session keys from workflow state at step execution time
- keep phase-plan logic in the runtime core if it is only needed by `autoloop_v1`
- require PairStep/LLMStep handlers
- preserve legacy behavior by allowing malformed workflows instead of migrating them
- choose incremental architecture over the Book Architecture choice when the latter is clear

======================================================================
17. ACCEPTANCE BAR
======================================================================

The job is complete only when all of the following are true:

- compat layer removed
- workflows migrated
- runtime core generic
- session model explicit
- PairStep/LLMStep handlers optional
- Autoloop_v1 runs on the final framework
- Autoloop_v1 behavior is parity-verified against legacy `autoloop/`
- tests pass
- architecture decisions are documented with 3 candidates each
- the result is simpler, cleaner, and more compressed than the current modular implementation

======================================================================
18. FINAL REPORT
======================================================================

When done, provide:

1. final file tree
2. summary of major architecture decisions
3. explicit explanation of how compat was removed
4. explicit explanation of the new session model
5. summary of workflow migrations
6. parity results vs legacy `autoloop/`
7. test results
8. remaining risks, if any

Do the full work.
Do not stop at planning.
Do not preserve legacy drift through hidden shims.
Choose the Book Architecture every time.
