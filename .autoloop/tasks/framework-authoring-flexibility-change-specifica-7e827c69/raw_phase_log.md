# Autoloop Raw Phase Log


---
run_id=run-20260504T112330Z-32d8eec3 | entry=run_state
---
workspace=/home/rauter/autoloop_v3_bkp/autoloop_v3
pairs=plan,implement,test,audit
request_file=/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/request.md
session_mode=persistent


---
run_id=run-20260504T112330Z-32d8eec3 | entry=session_turn | pair=plan | phase=producer | cycle=1 | attempt=1 | thread_id=019df2ba-a5b7-73f2-9c34-3a74f1a76aa5
---
provider=codex
mode=start
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/plan_producer.md
session_id=019df2ba-a5b7-73f2-9c34-3a74f1a76aa5


---
run_id=run-20260504T112330Z-32d8eec3 | entry=phase_output | pair=plan | phase=producer | process=codex-agent | cycle=1 | attempt=1 | thread_id=019df2ba-a5b7-73f2-9c34-3a74f1a76aa5
---
I’m turning the specification into an implementation-ready plan. First I’m checking the existing planning artifacts, any clarification history, and the engine/runtime modules that control routes, worklists, sessions, and inspection so the plan matches the codebase rather than the spec in the abstract.

The run has no later clarifications and the planning artifacts are effectively empty, so I’m building from the initial specification. Next I’m mapping that spec onto the actual modules that own route injection, provider route exposure, worklist selection lifecycle, session continuity, prompt validation, and inspection output.

I’ve confirmed the spec mostly aligns with the current architecture instead of asking for a redesign. The code already has the main seams the plan can target: runtime interaction policy fields in compiled route metadata, lazy `Context.ensure_selection(...)`, runtime worklist resolution callbacks, work-item session domains, and separate inspection/static-graph payloads.

The repository is ahead of the spec in a few places, which matters for scope control. `RuntimeInteractionPolicy`, `Context.ensure_selection(...)`, and typed worklist effects already exist, so the plan needs to focus on behavior gaps and consolidation rather than inventing those APIs again.

I’ve now verified the runner and engine already plumb `full_auto` into a runtime interaction policy, and the main loop already ensures scoped selections before item-state/session-sensitive work. What remains is tightening the remaining mismatches: child-workflow fallback routes, route-summary leftovers that still imply reserved behavior, prompt-validation/runtime parity, and making the existing helper/effect surfaces consistent and fully covered by tests.

The test surface is broad and already contains coverage for several requested behaviors, including interactive-vs-full-auto route visibility, runtime static graph output, worklist effects, and validation helpers. That lets the plan anchor changes to existing contract suites instead of inventing a new test harness.

I have enough context to write the plan. I’m updating the planning artifacts now with a two-milestone decomposition that preserves the spec order, calls out which APIs already exist versus which behaviors still need alignment, and names the regression surfaces and test suites that should absorb the change.

I’m making the file edits now. The plan will explicitly preserve the spec’s milestone ordering while calling out that several requested APIs are already in-tree and should be reconciled in place rather than replaced.

The plan artifacts are updated. I’m doing a quick verification pass now to confirm the markdown, YAML, and decisions block all landed cleanly and that the plan reflects the existing codebase seams rather than the spec alone.

Updated the plan artifacts in [plan.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/artifacts/plan/plan.md), [phase_plan.yaml](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/artifacts/plan/phase_plan.yaml), [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/artifacts/plan/feedback.md), and [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/decisions.txt).

The plan keeps the spec’s Milestone A then Milestone B order, but it is grounded in the current codebase: several requested APIs already exist, so the plan explicitly extends them in place instead of creating parallel abstractions. The main runtime focus is closing the remaining route-policy and child-workflow mapping gaps, preserving lazy worklist/session behavior and checkpoint compatibility, then aligning the existing effects, validation helper, prompt placeholder validation, and artifact-ownership diagnostics in Milestone B.


---
run_id=run-20260504T112330Z-32d8eec3 | entry=session_turn | pair=plan | phase=verifier | cycle=1 | attempt=1 | thread_id=019df2ba-a5b7-73f2-9c34-3a74f1a76aa5
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/plan_verifier.md
session_id=019df2ba-a5b7-73f2-9c34-3a74f1a76aa5


---
run_id=run-20260504T112330Z-32d8eec3 | entry=phase_output | pair=plan | phase=verifier | process=codex-agent | cycle=1 | attempt=1 | thread_id=019df2ba-a5b7-73f2-9c34-3a74f1a76aa5
---
I’m verifying the plan against the full spec now, not just the generated artifacts themselves. I’m checking for intent gaps around runtime semantics, persisted-data compatibility, and any places where the condensed plan may have dropped a material behavior requirement from the original specification.

I found one material gap in the plan rather than a tooling or formatting problem: the condensed Milestone A language dropped the spec’s explicit “source-policy-driven missing-source behavior” requirement for lazy worklists. I’m recording that as a blocking finding, because without it an implementer could still ship lazy selection by hard-failing every missing backing source, which the spec explicitly forbids.

I’ve also confirmed the YAML parses and the runtime-owned metadata is intact. I’m updating the verifier artifacts now: criteria will reflect that the plan is not yet complete, and feedback will carry one blocking issue plus one smaller follow-up item.

Scope considered

Planning artifacts for this run, the immutable specification, the raw log and decisions ledger, and the framework modules/tests that the plan names for route policy, lazy worklists, sessions, prompt validation, inspection, and helper APIs.

What I analyzed

The spec’s Milestone A and B requirements against the generated [plan.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/artifacts/plan/plan.md) and [phase_plan.yaml](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/artifacts/plan/phase_plan.yaml). I also checked the current codebase seams the plan relies on and verified `phase_plan.yaml` parses and keeps the runtime-owned metadata unchanged.

What I reviewed

I updated [criteria.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/artifacts/plan/criteria.md) to reflect that the plan is not yet complete, and I appended prioritized findings to [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/artifacts/plan/feedback.md).

Key findings / decisions

`PLAN-001` is blocking. The plan dropped the spec’s explicit source-policy-driven missing-source behavior for lazy worklists. That omission materially risks an implementation that hard-fails every missing backing source, even though the request explicitly requires scaffold/ensure-capable sources to create or scaffold data at first use and forbids hard-coding “missing worklist source always fails.”

`PLAN-002` is non-blocking. The plan should mention the required first-use lazy-selection runtime event more explicitly so observability is part of the implementation contract, not just implied by general test updates.

Open issues / next step

The producer plan needs one revision focused on Milestone A lazy worklist semantics: add explicit scope and acceptance coverage for first-use `ensure/load/validate/select` behavior, source-policy-driven scaffold-or-fail handling, and the corresponding regression tests. After that, the criteria can be re-evaluated for completion.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"INCOMPLETE"}
</loop-control>


---
run_id=run-20260504T112330Z-32d8eec3 | entry=session_turn | pair=plan | phase=producer | cycle=2 | attempt=1 | thread_id=019df2ba-a5b7-73f2-9c34-3a74f1a76aa5
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/plan_producer.md
session_id=019df2ba-a5b7-73f2-9c34-3a74f1a76aa5


---
run_id=run-20260504T112330Z-32d8eec3 | entry=phase_output | pair=plan | phase=producer | process=codex-agent | cycle=2 | attempt=1 | thread_id=019df2ba-a5b7-73f2-9c34-3a74f1a76aa5
---
I’m revising the plan narrowly around the verifier’s gap rather than broadening scope. The change is to make lazy worklist first-use semantics explicit: `ensure`/scaffold-capable sources may create backing data, required external inputs may fail at first use, and lazy materialization must stay observable through the selection-resolved runtime event.

The first patch failed on file boundaries, not on substance. I’m reapplying the changes in smaller chunks so the plan, phase YAML, feedback history, and decisions ledger all move together without touching verifier-owned criteria.

The decisions file now has a fresh header for this turn, so I can record the non-obvious lazy-worklist constraint in the correct block instead of mutating the previous turn’s history. I’m applying the artifact updates again in smaller, file-scoped patches.

The revisions are in. I’m doing one last consistency pass to make sure the narrative plan, phase acceptance criteria, feedback history, and the new turn-local decision line all say the same thing about lazy worklist first-use behavior and observability.

Updated [plan.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/artifacts/plan/plan.md), [phase_plan.yaml](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/artifacts/plan/phase_plan.yaml), [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/artifacts/plan/feedback.md), and the current-turn block in [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/decisions.txt).

The Milestone A plan now explicitly preserves source-policy-driven lazy worklist first-use semantics: `ensure`/scaffold-capable sources may create backing data, required external inputs may fail at first use, `ensure_worklist_selection(...)` is named as the `ensure/load/validate/select` pipeline, and first-use `worklist_selection_resolved` observability is now part of scope, acceptance, and validation.


---
run_id=run-20260504T112330Z-32d8eec3 | entry=session_turn | pair=plan | phase=verifier | cycle=2 | attempt=1 | thread_id=019df2ba-a5b7-73f2-9c34-3a74f1a76aa5
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/plan_verifier.md
session_id=019df2ba-a5b7-73f2-9c34-3a74f1a76aa5


---
run_id=run-20260504T112330Z-32d8eec3 | entry=phase_output | pair=plan | phase=verifier | process=codex-agent | cycle=2 | attempt=1 | thread_id=019df2ba-a5b7-73f2-9c34-3a74f1a76aa5
---
I’m doing the final verification pass now that the Milestone A gap is addressed. I’m checking that the revised plan, phase acceptance criteria, and decisions ledger now align on source-policy-driven lazy worklist behavior and that there are no remaining blocking intent gaps before I flip the criteria back to complete.

The revised plan now matches the missing Milestone A behavior and the YAML still parses cleanly. I’m marking the criteria complete and appending a short verifier closure note so the feedback history shows that the prior blocking gap was resolved rather than silently disappearing.

Scope considered

The authoritative specification, the current planning artifacts, the verifier-owned criteria, the shared decisions ledger, and the specific Milestone A changes made after the prior blocking finding.

What I analyzed

I re-checked the revised plan against the original runtime-semantics requirements, with focus on lazy worklist first-use behavior, source-policy-driven missing-source handling, first-use observability, checkpoint compatibility, and consistency between the narrative plan and machine-readable phase acceptance criteria. I also re-validated that `phase_plan.yaml` parses and retains the runtime-owned metadata unchanged.

What I reviewed

I updated [criteria.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/artifacts/plan/criteria.md) to fully checked, and I appended a closure note to [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/artifacts/plan/feedback.md) recording that the previous blocking and follow-up findings are now covered.

Key findings / decisions

The prior blocking gap is resolved. The plan now explicitly preserves source-policy-driven lazy worklist first-use semantics, names the `ensure`/scaffold/load/validate/select` pipeline, preserves checkpoint compatibility, and includes first-use selection-resolved observability in both the narrative and phase acceptance criteria.

No new blocking or non-blocking findings were identified on this pass.

Open issues / next step

No verifier-side open issues remain for the planning artifacts in this cycle. The plan is complete and ready for downstream implementation work.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"COMPLETE"}
</loop-control>


---
run_id=run-20260504T112330Z-32d8eec3 | entry=phase_scope_resolved
---
phase_mode=single
phase_ids=milestone-a-runtime-route-policy-and-lazy-scoped-runtime,milestone-b-authoring-ergonomics-and-validation-polish
explicit=True
current_phase_index=0


---
run_id=run-20260504T112330Z-32d8eec3 | entry=session_turn | pair=implement | phase=producer | cycle=1 | attempt=1 | thread_id=019df2c3-200f-73f2-9d49-64451ced9529
---
provider=codex
mode=start
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/implement_producer.md
session_id=019df2c3-200f-73f2-9d49-64451ced9529


---
run_id=run-20260504T112330Z-32d8eec3 | entry=phase_output | pair=implement | phase=producer | process=codex-agent | cycle=1 | attempt=1 | thread_id=019df2c3-200f-73f2-9d49-64451ced9529
---
I’m implementing Milestone A only: route policy, explicit child-route mapping, lazy worklist/session behavior, and aligned inspection/tests. I’ll read the phase artifacts and the relevant engine/discovery/runtime code first so the changes stay inside the approved scope.

The planning artifacts confirm most Milestone A foundations already exist in-tree, so I’m checking where behavior still diverges before I edit anything. Next I’m tracing the route-policy, child-mapping, lazy-selection, session, and inspection code paths together with their tests.

The codebase already carries most of the requested APIs, so the likely work is contract hardening and gap-closing rather than new architecture. I’m reading the exact discovery and engine paths now to isolate the remaining divergence before editing.

I’ve confirmed the broad shape already matches the spec, but two likely gaps stand out: child workflow mapping still synthesizes `blocked`/`failed` unconditionally, and lazy worklist resolution still wraps `initial_selection()` too coarsely to report first-use phases/source policy clearly. I’m drilling into the worklist source implementations and the existing tests for those exact paths now.

I’ve narrowed the likely changes to a small set of runtime contract gaps rather than a broad refactor. I’m running the targeted contract tests for child mapping, lazy worklists, and route visibility now so I can patch exactly what is still off-spec.

`pytest` isn’t on the shell path here, so I’m checking the project’s runner and then I’ll use the available test entrypoint instead of guessing.

I’ve got the concrete patch shape now: keep the existing APIs, tighten child route mapping, make first-use worklist resolution explicitly phased and source-aware, and improve the lazy session/worklist observability messages. I’m editing those focused runtime paths next, then I’ll add the missing contract tests around undeclared child routes and first-use worklist behavior.

I’ve applied the runtime-side changes and I’m doing a quick compatibility pass now. One important detail is making the new source `ensure()` behavior optional so existing custom sources don’t break if they only implement `load/save/validate`.

The runtime code changes are in place and syntactically clean. I’m finishing the phase-local bookkeeping now: recording the non-obvious compatibility decisions and writing concise implementation notes that map the edits back to the checklist and validation I could actually perform in this environment.

Scope considered

Milestone A only: policy-aware provider/runtime routing, explicit child-workflow route mapping, lazy worklist/session behavior, targeted contract tests, and the phase-local notes/decision artifacts. I kept scope to [autoloop/core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/engine.py:942), [autoloop/core/worklists.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/worklists.py:105), [autoloop/core/context.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/context.py:691), [autoloop/core/sessions.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/sessions.py:61), and [tests/contract/test_engine_contracts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/contract/test_engine_contracts.py:4046).

What I analyzed

I traced the current discovery/compiler/runtime path first. The route-policy and inspection/static-graph foundations were already aligned with the requested `question`/`blocked`/`failed` contract, so the remaining gaps were in child-workflow terminal mapping, first-use worklist resolution/error shaping, worklist-selection observability, and the no-current-item work-item session error path.

What I changed

I made child workflow `FAIL` and await-without-question map to `failed` and `blocked` only when the parent step actually declares those routes, with a targeted runtime error naming the step, child terminal, mapped route, declared routes, and the fix. I also changed lazy worklist materialization to run explicit `ensure -> load -> validate -> select` phases, kept `ensure()` optional for compatibility with existing custom sources, and made `worklist_selection_resolved` events include `lazy`, `source`, and `current_index`.

I updated the work-item continuity error to name the session slot, worklist, and step when no current item exists. I added/updated contract tests for undeclared child `failed`/`blocked` mapping, scaffold-on-first-use worklist resolution, additive worklist-selection event payloads, and the new session error wording. I also updated the phase-local [implementation_notes.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/artifacts/implement/phases/milestone-a-runtime-route-policy-and-lazy-scoped-runtime/implementation_notes.md:1) and [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/decisions.txt:1).

Key findings / decisions

The authored-vs-runtime-control inspection/static-graph split was already present, so I intentionally did not touch those payload producers in this turn. The non-obvious compatibility choice was to make worklist source `ensure()` optional at runtime, so existing custom sources that only implement `load/save/validate` do not break.

Validation I could perform here was limited to syntax: `python3 -m py_compile` passed for the touched code and test files. I could not run `pytest` in this shell because `pytest` is not installed, and direct runtime smoke tests are also blocked by missing installed dependencies such as `pydantic`.

Open issues / next step

The next step is an environment-backed test pass once dependencies are available, starting with `tests/contract/test_engine_contracts.py` for the updated child-mapping and lazy-worklist cases, then the adjacent runtime inspection/static-graph suites for regression confirmation.


---
run_id=run-20260504T112330Z-32d8eec3 | entry=session_turn | pair=implement | phase=verifier | cycle=1 | attempt=1 | thread_id=019df2c3-200f-73f2-9d49-64451ced9529
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/implement_verifier.md
session_id=019df2c3-200f-73f2-9d49-64451ced9529


---
run_id=run-20260504T112330Z-32d8eec3 | entry=phase_output | pair=implement | phase=verifier | process=codex-agent | cycle=1 | attempt=1 | thread_id=019df2c3-200f-73f2-9d49-64451ced9529
---
I’m reviewing only the Milestone A implementation and its review artifacts. I’ll read the criteria and feedback files first, then audit the touched runtime paths and tests for regressions against the accepted phase contract.

I found one area that needs closer scrutiny before I can mark this complete: the new phased worklist resolution only calls `ensure()` from `Engine._ensure_worklist_selection`, but resume/restore and refresh paths still reload sources directly. I’m checking those adjacent paths now to confirm whether that creates a real source-policy regression.

I confirmed the core regression risk: the new `ensure()` semantics are not centralized, so restore and refresh still bypass source policy and can hard-fail scaffold-capable sources. I’m recording that as a blocking finding and updating the criteria accordingly.

Scope considered

Milestone A runtime-semantics changes only: the touched runtime files, the added contract-test coverage, the active implementation notes, and the phase-local criteria/feedback artifacts.

What I analyzed

I reviewed the engine’s child-workflow mapping path, the new phased worklist materialization flow, the surrounding `Worklist` restore/refresh helpers, the work-item session continuity change, and the updated contract tests against AC-1 through AC-4 and the run-local decisions.

What I reviewed

I updated [criteria.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/artifacts/implement/phases/milestone-a-runtime-route-policy-and-lazy-scoped-runtime/criteria.md:1) and appended findings to [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/framework-authoring-flexibility-change-specifica-7e827c69/runs/run-20260504T112330Z-32d8eec3/artifacts/implement/phases/milestone-a-runtime-route-policy-and-lazy-scoped-runtime/feedback.md:1).

Key findings / decisions

- `IMP-001` `blocking`: the new source-policy `ensure()` behavior is only applied in `Engine._ensure_worklist_selection(...)`. Resume restore and refresh still go through `Worklist.load_items()` / `reload_items()` without any ensure step, so scaffold-capable sources can still fail on resume or refresh if backing data is absent. That violates AC-3’s source-policy-driven lazy-worklist contract.
- `IMP-002` `non-blocking`: the required Milestone A contract/runtime suites were not executed in this environment; only syntax compilation was performed.

Open issues / next step

Centralize worklist `ensure()` into the shared load/reload/restore path so fresh materialization, restore, and refresh all honor source capabilities consistently, then rerun the targeted Milestone A contract/runtime suites once dependencies are available.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"INCOMPLETE"}
</loop-control>


---
run_id=run-20260504T112330Z-32d8eec3 | entry=session_turn | pair=implement | phase=producer | cycle=2 | attempt=1 | thread_id=019df2c3-200f-73f2-9d49-64451ced9529
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/implement_producer.md
session_id=019df2c3-200f-73f2-9d49-64451ced9529


---
run_id=run-20260504T112330Z-32d8eec3 | entry=phase_output | pair=implement | phase=producer | process=codex-agent | cycle=2 | attempt=1 | thread_id=019df2c3-200f-73f2-9d49-64451ced9529
---
I’m addressing the reviewer’s blocking finding only: source `ensure()` has to cover restore and refresh paths, not just first materialization. I’ll trace the shared worklist load/reload helpers, patch that centralization point, and update the phase notes and decision ledger accordingly.

The fix is straightforward: move `ensure()` into the shared worklist load/reload path, but let the engine keep separate ensure-vs-load error phases by opting out when it already did the explicit ensure step. I’m editing that centralization point and adding resume/refresh regression tests for ensure-capable sources.

The code change is in, and I added explicit regression tests for both resume-restore and refresh with ensure-capable sources so the reviewer’s scenario is covered directly. I’m doing a final syntax pass and then I’ll update the notes/decision ledger to reflect the new centralization point.

I spotted one bookkeeping issue in `decisions.txt`: the runtime created a new turn header, so the new turn’s decision needs to live under that header as well. I’m fixing that artifact now without touching earlier entries.

Scope considered

Milestone A reviewer feedback only, specifically `IMP-001` around source-policy-driven lazy worklist behavior on restore and refresh. I kept scope to the shared worklist load path, the engine’s phased first-use path, the affected contract tests, and the phase-local notes/decision artifacts.

What I analyzed

I traced the reviewer’s failing scenario through `Engine._ensure_worklist_selection(...)`, `Worklist.load_items()/reload_items()`, `restore_selection(...)`, and `refresh_selection(...)`. The real gap was that `ensure()` had been introduced only on the engine’s first-materialization branch, while restore and refresh still reloaded sources directly.

What I changed

I centralized source `ensure()` in `Worklist._load_source_items(..., ensure=...)`, so `load_items()`, `reload_items()`, restore, and refresh all honor source-policy semantics on cache misses and forced reloads. To preserve the granular `ensure -> load -> validate -> select` error phases for first-use lazy materialization, the engine now calls `_load_source_items(..., ensure=False)` only after its explicit ensure phase succeeds.

I added regression tests for the reviewer’s scenarios in `tests/contract/test_engine_contracts.py`: one for resume restoring a materialized worklist after the backing data is deleted, and one for `ctx.worklist(...).refresh()` recreating missing backing data via source `ensure()`. I also updated `implementation_notes.md` and appended the turn-local centralization decision under the latest run header in `decisions.txt`.

Key findings / decisions

The centralization point is now the shared worklist load path rather than the engine-only first-use branch. That keeps first materialization, resume restore, and refresh behavior aligned without weakening the engine’s phased runtime error reporting.

Validation I could perform here remains limited to syntax: `python3 -m py_compile autoloop/core/engine.py autoloop/core/worklists.py tests/contract/test_engine_contracts.py` passed. I still could not run `pytest` in this shell because the environment does not provide `pytest` or the installed runtime deps needed for execution.

Open issues / next step

The remaining open item is environment-backed validation. The next step is for the verifier to rerun the Milestone A contract/runtime review against the updated restore/refresh coverage and confirm that `IMP-001` is cleared.
