You are a principal software architect and implementation agent.

Use `autoloop_v3/` as the implementation workspace.

Your task is to fully implement the final architectural refinement of `autoloop_v3` so that it converges on the Book Architecture for this system.

Paul Erdős spoke of “Proofs from The Book”: arguments so elegant and compressed that they feel like the ideal form of the result. Software architecture has an analogous phenomenon. Occasionally, after years of partial solutions and accumulated complexity, someone finds a construction that reorganizes the whole problem. The resulting design is strikingly short to explain, yet it resolves far more than its surface simplicity suggests. It can feel like discovering a new chess opening: initially counterintuitive, then obviously potent. Not every architecture problem has such a solution, and one should not expect this generally. But when a system yields a design of that kind, it is worth recognizing it for what it is: a Book Architecture.

That is your decision rule.

For every design decision:
- generate the best 3 candidate solutions
- compare them carefully
- choose the one that is closest to the Book Architecture
- explain why the others lost

Do not optimize for incrementalism or convenience. Optimize for the final ideal shape.

This is a full implementation task, not a design-only task.

======================================================================
1. OBJECTIVE
======================================================================

Refine `autoloop_v3` into the final Book Architecture by eliminating the remaining architectural impurity concentrated in the Autoloop-v1 workflow-owned support layer.

The final system must satisfy all of the following:

- `autoloop_v3.workflow` remains the strict canonical engine/core
- `autoloop_v3.runtime` remains a generic task/run filesystem runtime
- `autoloop_v3.workflows` remains the workflow-owned layer for Autoloop-v1 parity policy
- no compatibility layer exists anywhere in the core/runtime
- no workflow-specific logic leaks into the generic runtime
- only truly reusable logic is promoted into framework helpers
- `autoloop_v1.py` remains a strict workflow
- `Ralph_loop.py` / `ralph_loop.py` remains a strict workflow
- `autoloop_v1.py` still runs with functionality equivalent to the legacy `autoloop/` codebase
- the final implementation is simpler to explain than the current one

======================================================================
2. CURRENT ARCHITECTURAL PROBLEM
======================================================================

The remaining impurity is the Autoloop-v1 workflow-owned support module, which currently mixes four kinds of concerns:

1. workflow semantics
2. workflow-specific operational parity policy
3. reusable infrastructure concerns
4. execution observation implemented through a provider wrapper and engine subclass

The point of this project is to split these concerns correctly.

The architecture is already close. Do not restart from scratch. Refine it into the final shape.

======================================================================
3. NON-NEGOTIABLE PRINCIPLES
======================================================================

These are mandatory.

1. `autoloop_v3/` is the implementation workspace.
2. `autoloop/` is the behavioral oracle for Autoloop-v1 parity, not the target architecture.
3. The runtime must remain workflow-agnostic.
4. The engine must remain strict and compatibility-free.
5. The support layer must not remain a disguised mini-runtime.
6. PairStep and LLMStep handlers remain optional.
7. SystemStep handlers remain required.
8. Sessions remain explicit: created with `ctx.open_session(...)`, used with direct lookup.
9. No new compatibility layer may be introduced under any name.
10. Do not over-generalize single-workflow policy into framework abstractions.

======================================================================
4. EXPLICIT SESSION MODEL
======================================================================

Preserve and reinforce this model:

Sessions are not computed. They are created.

The engine must not compute session identity from state at step execution time.

The architecture must remain:

- declare a session slot as `Session()`
- explicitly create/bind it with `ctx.open_session(slot, scope=...)`
- reuse it through topology because nobody rebinds the slot
- step execution does a direct lookup only:
  `session = ctx.get_session(step.session)`

No session-template evaluation.
No computed session-sharing policy.
No implicit lifecycle enums.
No automatic opening of missing sessions.

Missing session binding must fail clearly.

======================================================================
5. REQUIRED DESIGN DECISIONS
======================================================================

Before changing code, analyze at least these design decisions.

For each one:
- provide 3 candidates
- evaluate them against correctness, simplicity, extensibility, observability, testability, migration risk, and parity impact
- pick the Book Architecture choice
- explain why the other two lost

Write the analysis to:

`autoloop_v3/ARCHITECTURE_DECISIONS.md`

Decisions you must cover:

1. final package/module layout
2. final ownership boundary for Autoloop-v1 support code
3. whether `autoloop_v1_support.py` survives, is split, or is deleted
4. execution observation design
5. provider wrapper removal strategy
6. engine subclass removal strategy
7. session payload helper ownership
8. `phase_artifact_template` removal
9. final placement of `parse_phase_ids`
10. final placement of exact `phase_dir_key`
11. workspace augmentation ownership
12. cycle/attempt tracking ownership
13. clarification ledger ownership
14. raw phase log ownership
15. terminal status mapping ownership
16. final shape of `run_autoloop_v1(...)`
17. test strategy proving the final shape

======================================================================
6. FINAL DECISIONS YOU MUST IMPLEMENT
======================================================================

Unless your candidate analysis proves a strictly better Book Architecture alternative, implement the following target decisions.

----------------------------------------------------------------------
6.1 phase_artifact_template
----------------------------------------------------------------------

Remove `phase_artifact_template`.

Do not replace it with another wrapper.

Use explicit `Artifact(...)` templates directly in `autoloop_v1.py`.

Example target style:
- `Artifact("{task_folder}/implement/phases/{state.phase.dir_key}/criteria.md")`
- `Artifact("{task_folder}/test/phases/{state.phase.dir_key}/test_strategy.md")`

Reason:
The workflow DSL already expresses this cleanly. A helper adds indirection without reducing complexity.

----------------------------------------------------------------------
6.2 parse_phase_ids
----------------------------------------------------------------------

Keep `parse_phase_ids` workflow-owned.

Best placement:
- inline in `autoloop_v1.py` if only the workflow needs it
- or in a tiny workflow-owned helper module only if both the workflow and parity harness need it

Do not promote it into the framework core or runtime.

Reason:
It interprets Autoloop-v1 phase-plan meaning, which is workflow semantics.

----------------------------------------------------------------------
6.3 phase_dir_key
----------------------------------------------------------------------

Keep the exact `phase_dir_key` behavior workflow-owned as Autoloop-v1 parity policy.

Do not promote the exact `_pid-...` encoding into framework semantics.

If you discover a genuine cross-workflow need for a neutral helper, it must be a separate general helper with generic semantics, not the Autoloop-specific compatibility function.

Reason:
The exact format is part of Autoloop-v1 legacy parity, not universal framework law.

----------------------------------------------------------------------
6.4 workspace augmentation
----------------------------------------------------------------------

Do not add a generic workspace-hook/plugin system unless your design analysis proves it is truly the Book Architecture.

The default assumption is:

- keep generic workspace creation in `runtime.workspace`
- keep Autoloop-v1-specific workspace augmentation explicit in the workflow-owned parity harness

Reason:
Only one workflow currently needs this augmentation. A generic workspace extension system is likely over-abstraction.

----------------------------------------------------------------------
6.5 provider wrapper and engine subclass
----------------------------------------------------------------------

Remove the Autoloop-v1 provider wrapper and engine subclass.

Delete any equivalents of:
- `_AutoloopV1LoggingProvider`
- `_AutoloopV1Engine`

Replace them with one minimal generic execution observation extension.

Reason:
Execution observation is a truly cross-cutting concern and should not be implemented through a bespoke wrapper/subclass pair.

----------------------------------------------------------------------
6.6 execution observer
----------------------------------------------------------------------

Add one minimal generic execution observer/sink interface to the strict engine/runtime boundary.

It must be optional and support zero or more observers.

It must not alter execution semantics.

At minimum, support three event categories:

1. provider-turn event
   - after producer turn
   - after verifier turn
   - after llm turn

2. step-completion event
   - after every step

3. terminal event
   - success
   - pause
   - fail
   - fatal exception

The observer payloads must contain enough structured information for workflow-owned harnesses to implement:
- raw phase logs
- phase started/completed events
- legacy status mapping
- clarification persistence
- session-related parity behavior

But the engine must not know about any of those meanings.

Do not create a large hook system. Keep this minimal, typed, and crisp.

----------------------------------------------------------------------
6.7 cycle and attempt tracking
----------------------------------------------------------------------

Do not move Autoloop-v1 cycle/attempt semantics into the engine core.

If the Autoloop-v1 parity layer needs cycle/attempt numbers for logs, track them in the workflow-owned observer/harness state.

Do not:
- store them in workflow state
- define them as generic engine semantics
- bury them in provider session metadata unless absolutely necessary for persistence and the design analysis proves it

Reason:
These counters are not framework semantics. They are Autoloop parity semantics.

----------------------------------------------------------------------
6.8 clarification ledger and raw phase log
----------------------------------------------------------------------

Keep these strictly Autoloop-v1-specific:

- decisions ledger schema
- clarification header/block format
- raw phase log format
- exact field names and append behavior

Do not generalize them into framework abstractions unless your candidate analysis proves a real multi-workflow need.

Reason:
These are legacy operational artifacts, not workflow-engine primitives.

----------------------------------------------------------------------
6.9 session payload helpers
----------------------------------------------------------------------

Move session payload placeholder creation and payload writing helpers fully into:

`autoloop_v3/runtime/stores/filesystem.py`

The filesystem session store owns session payload serialization.

The workflow-owned Autoloop-v1 layer may call store helpers, but must not serialize session JSON itself.

Reason:
This is infrastructure ownership, not workflow policy.

----------------------------------------------------------------------
6.10 terminal status mapping
----------------------------------------------------------------------

Keep Autoloop-v1 terminal status mapping local to the Autoloop-v1 parity layer.

Do not move it into the engine or generic runtime unless the design analysis proves a stronger Book Architecture.

Reason:
Legacy status mapping such as `blocked` is workflow-owned operational policy.

----------------------------------------------------------------------
6.11 run_autoloop_v1
----------------------------------------------------------------------

Keep `run_autoloop_v1(...)`, but make it a thin composition root.

Its job should be wiring only:
- generic runtime pieces
- generic execution observer
- Autoloop-v1 session path resolver
- Autoloop-v1 workspace augmentation
- Autoloop-v1 parity-only logging / ledger / status policies

It must not become a second runtime.

Reason:
The generic runtime must stay generic, but the system still needs an Autoloop-v1 parity entrypoint.

======================================================================
7. FILE-LEVEL IMPLEMENTATION REQUIREMENTS
======================================================================

You must inspect the current `autoloop_v3` tree and implement the final shape.

At minimum, expect to modify:

- `autoloop_v3/workflow/engine.py`
- `autoloop_v3/runtime/stores/filesystem.py`
- repo-root `autoloop_v1.py`
- repo-root `Ralph_loop.py` or `ralph_loop.py`
- `autoloop_v3/workflows/autoloop_v1_support.py` or its replacements
- docs and tests

If your final architecture is cleaner with a split, create something like:
- `autoloop_v3/workflows/autoloop_v1_parity.py`
- `autoloop_v3/workflows/autoloop_v1_conventions.py`

or delete the support file entirely if that is cleaner.

Do not add broad new framework packages unless necessary.

======================================================================
8. SPECIFIC WORKFLOW REQUIREMENTS
======================================================================

----------------------------------------------------------------------
8.1 autoloop_v1.py
----------------------------------------------------------------------

`autoloop_v1.py` must remain a strict workflow using only canonical framework primitives and standard Python.

It must:
- use canonical imports
- define `entry`
- use `Outcome`
- use `on_outcome`
- explicitly open sessions with `ctx.open_session`
- contain explicit artifact templates
- remain readable from the workflow file itself

It must not:
- rely on compat
- use `phase_artifact_template`
- depend on runtime phase knowledge

----------------------------------------------------------------------
8.2 Ralph_loop.py / ralph_loop.py
----------------------------------------------------------------------

Keep it strict and compatibility-free.

Also fix the correctness issue:
if the workflow can terminate successfully on `plan_action -> goal_met -> SUCCESS`, the state must still correctly reflect `goal_met=True`.

Ensure all success paths leave correct state.

======================================================================
9. TEST REQUIREMENTS
======================================================================

Add or update tests to prove all of the following.

----------------------------------------------------------------------
9.1 Engine / core tests
----------------------------------------------------------------------

- PairStep handlers optional
- LLMStep handlers optional
- SystemStep handlers required
- explicit session opening still works
- missing session binding still fails clearly
- execution observers receive provider-turn events
- execution observers receive step-completion events
- execution observers receive terminal events
- observers do not alter execution semantics

----------------------------------------------------------------------
9.2 Runtime store tests
----------------------------------------------------------------------

- filesystem store owns session payload serialization helpers
- legacy `thread_id` compatibility still works
- sparse metadata preservation still works
- placeholder payload helpers work through the store

----------------------------------------------------------------------
9.3 Workflow tests
----------------------------------------------------------------------

- `autoloop_v1.py` has no `phase_artifact_template`
- `autoloop_v1.py` uses explicit artifact templates
- `autoloop_v1.py` remains strict and runs
- `Ralph_loop.py` / `ralph_loop.py` remains strict and runs
- `goal_met` correctness is fixed on all success paths

----------------------------------------------------------------------
9.4 Autoloop parity tests
----------------------------------------------------------------------

- Autoloop-v1 parity still works against legacy `autoloop/`
- raw phase logs still match expected behavior
- decisions ledger still matches expected behavior
- legacy session filenames still match expected behavior
- blocked/question/failed mapping still matches expected behavior
- parity no longer depends on provider wrapper or engine subclass

----------------------------------------------------------------------
9.5 No-over-abstraction tests
----------------------------------------------------------------------

- generic runtime still runs unrelated toy workflows without phase knowledge
- no new generic workspace-hook system exists unless explicitly justified and tested
- engine has no Autoloop-specific imports or branching

======================================================================
10. DOCUMENTATION REQUIREMENTS
======================================================================

Update all relevant docs so they reflect the final architecture, including:

- `README.md`
- `MIGRATION.md`
- `docs/architecture.md`
- `docs/authoring.md`
- `docs/parity-matrix.md`
- `docs/risk-register.md`
- `ARCHITECTURE_DECISIONS.md`

The docs must clearly state:

- no compatibility layer
- strict public API
- explicit session model
- minimal generic execution observer
- workflow-owned Autoloop-v1 parity logic
- why certain concerns were intentionally not generalized
- how the final shape is closer to the Book Architecture

======================================================================
11. ACCEPTANCE CRITERIA
======================================================================

The task is complete only when all of the following are true:

1. `phase_artifact_template` is gone
2. `autoloop_v1.py` uses explicit artifact templates
3. `_AutoloopV1LoggingProvider` is gone
4. `_AutoloopV1Engine` is gone
5. a minimal generic execution observer exists
6. session payload write helpers live in `runtime.stores.filesystem`
7. Autoloop-v1 workflow semantics remain outside the engine/runtime core
8. PairStep and LLMStep handlers remain optional
9. SystemStep handlers remain required
10. the runtime remains workflow-agnostic
11. Autoloop-v1 parity suite passes
12. no compatibility layer is reintroduced
13. the final code is simpler and more compressed than the current shape
14. the final design decisions are documented with 3 candidates each and justified as the Book Architecture choices

======================================================================
12. IMPLEMENTATION ORDER
======================================================================

Use this order unless your candidate analysis proves a clearly superior one:

1. analyze all required design decisions and write `ARCHITECTURE_DECISIONS.md`
2. add the minimal execution observer abstraction
3. remove provider wrapper and engine subclass
4. move session payload write helpers into filesystem store
5. remove `phase_artifact_template`
6. inline explicit artifact templates in `autoloop_v1.py`
7. split or shrink the Autoloop-v1 support layer
8. fix `Ralph_loop.py` / `ralph_loop.py` correctness
9. update tests
10. update docs
11. run full test suite
12. confirm legacy parity behavior

======================================================================
13. FINAL REPORT FORMAT
======================================================================

When finished, provide:

1. final file tree
2. summary of design decisions
3. explicit explanation of why the final shape is closer to the Book Architecture
4. explicit list of what was moved to general helpers
5. explicit list of what remained strictly Autoloop-specific
6. explanation of the new execution observer
7. parity results vs legacy `autoloop/`
8. test results
9. remaining risks, if any

Do the full work.
Do not stop at planning.
Do not preserve bespoke wrapper/subclass mechanisms if the observer replaces them.
Do not over-abstract one-workflow policy.
Choose the Book Architecture every time.
