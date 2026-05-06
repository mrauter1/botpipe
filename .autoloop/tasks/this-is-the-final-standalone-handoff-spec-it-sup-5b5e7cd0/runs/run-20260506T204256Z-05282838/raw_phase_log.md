# Autoloop Raw Phase Log (run-20260506T204256Z-05282838)


---
run_id=run-20260506T204256Z-05282838 | entry=run_state
---
workspace=/home/rauter/autoloop_v3_bkp/autoloop_v3
pairs=plan,implement,test,audit
request_file=/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/request.md
session_mode=persistent


---
run_id=run-20260506T204256Z-05282838 | entry=session_turn | pair=plan | phase=producer | cycle=1 | attempt=1 | thread_id=019dff07-8be8-7403-85db-f40ae08ce678
---
provider=codex
mode=start
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/plan_producer.md
session_id=019dff07-8be8-7403-85db-f40ae08ce678


---
run_id=run-20260506T204256Z-05282838 | entry=phase_output | pair=plan | phase=producer | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dff07-8be8-7403-85db-f40ae08ce678
---
I’m treating this as a run-local planning turn: first I’ll read the authoritative request/log artifacts and the route-schema/backend code paths they refer to, then I’ll update the plan artifacts with an implementation-ready slice that stays inside the stated migration scope.

I’ve confirmed there are no clarifications beyond the initial request and the plan artifacts are effectively blank. Next I’m tracing the compiler/runtime path for `payload_schema`, `route_fields_schema`, and provider `response_schema` so the plan names the exact modules and regression surfaces.

The key gap is visible in the code: compiler currently converts missing-`jsonschema` route contracts into `schema + None validator`, and engine only enforces route contracts when a validator exists. I’m checking the provider transport boundary now to see exactly where `response_schema` is present in framework objects but dropped before backend calls.

I’ve traced both sides now. The provider contract builder already generates canonical discriminated schemas, and `RenderedProviderTurn` can carry them, but the built-in CLI transports never consume that field. The plan needs one slice for hard runtime enforcement of raw route schemas and one for explicitly plumbing/recording provider-side schema delivery with tests around both.

I have enough context to write the artifacts. The plan will stay narrow: fail closed only where raw route mappings would otherwise lose enforcement, preserve helper/legacy compatibility, and make backend schema delivery observable instead of implicit.

The plan artifacts are written. I’m doing one verification pass now for coherence: ordered phase dependencies, preserved runtime-owned YAML keys, and whether the decisions capture only the non-obvious guardrails later turns will need.

Updated the run-local planning artifacts:

- [plan.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/artifacts/plan/plan.md)
- [phase_plan.yaml](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/artifacts/plan/phase_plan.yaml)
- [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/artifacts/plan/feedback.md)
- [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/decisions.txt)

The plan is split into two ordered phases: first, fail-closed enforcement for custom raw route `payload_schema` / `route_fields_schema` without silently dropping validation; second, wiring `response_schema` into structured-output-capable backends with explicit recorded fallback for unsupported ones. It also preserves the `ControlRoutes(question=...)` and legacy top-level `question` / `reason` compatibility paths, and makes the helper-route compatibility caveat explicit so builtin question/blocked/failed behavior is not broken accidentally.

I did not run tests or change implementation code on this turn; this was a planning-only update.


---
run_id=run-20260506T204256Z-05282838 | entry=session_turn | pair=plan | phase=verifier | cycle=1 | attempt=1 | thread_id=019dff07-8be8-7403-85db-f40ae08ce678
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/plan_verifier.md
session_id=019dff07-8be8-7403-85db-f40ae08ce678


---
run_id=run-20260506T204256Z-05282838 | entry=phase_output | pair=plan | phase=verifier | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dff07-8be8-7403-85db-f40ae08ce678
---
I’m verifying the generated plan against the request, the current artifacts, and the non-obvious constraints already recorded for this run. First I’ll re-read the authoritative files and then check whether the plan introduces any unconfirmed behavior tightening or leaves backend coverage underspecified.

I’ve narrowed the likely gaps to two areas: the chosen helper-route exception is not backed by explicit acceptance/test requirements, and the requested documented unsupported-backend fallback is still optional in the plan instead of a concrete deliverable. I’m verifying those are the only material blockers before I mark the criteria.

The blockers are confirmed. They’re both implementation-plan quality issues, not source-code issues: one missing regression requirement for the helper-route exception, and one missing concrete documentation deliverable for the unsupported-backend fallback the request explicitly asked for.

Scope considered
Run-local verification of the produced planning artifacts against the immutable request, raw-log clarification history, current decisions ledger, and the repo code paths the plan relies on for route-contract compilation, helper-route defaults, engine fallback validation, and rendered-provider backend plumbing.

What I analyzed
I checked the request requirements for fail-closed route-schema handling, backend schema pass-through, explicit unsupported-backend fallback documentation, scripted/rendered regression coverage, and compatibility preservation. I also checked the relevant implementation surfaces in [autoloop/core/compiler.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/compiler.py), [autoloop/core/routes.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/routes.py), and [autoloop/core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/engine.py) to verify the plan’s assumptions.

What I reviewed
I reviewed [plan.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/artifacts/plan/plan.md), [phase_plan.yaml](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/artifacts/plan/phase_plan.yaml), [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/artifacts/plan/feedback.md), [criteria.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/artifacts/plan/criteria.md), and [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/decisions.txt). I updated the criteria checklist and appended verifier findings to feedback.

Key findings / decisions
Two blocking findings were added:
`PLAN-001`: the plan introduces a helper-route compatibility exception but does not require acceptance criteria or regression tests that prove helper defaults remain compatible while custom raw overrides fail closed.
`PLAN-002`: the request-required unsupported-backend fallback documentation is still optional in the plan instead of a concrete required deliverable.

Open issues / next step
The plan needs one revision pass to add explicit helper-route compatibility coverage under missing-`jsonschema` conditions and to make the unsupported-backend fallback documentation a named required deliverable with a concrete doc surface. Until those are fixed, the plan is not ready to mark complete.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"INCOMPLETE"}
</loop-control>


---
run_id=run-20260506T204256Z-05282838 | entry=session_turn | pair=plan | phase=producer | cycle=2 | attempt=1 | thread_id=019dff07-8be8-7403-85db-f40ae08ce678
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/plan_producer.md
session_id=019dff07-8be8-7403-85db-f40ae08ce678


---
run_id=run-20260506T204256Z-05282838 | entry=phase_output | pair=plan | phase=producer | process=codex-agent | cycle=2 | attempt=1 | thread_id=019dff07-8be8-7403-85db-f40ae08ce678
---
I’m revising the plan against the verifier’s blockers only: one gap around explicit helper-route compatibility coverage for missing-`jsonschema` environments, and one gap around making the unsupported-backend fallback documentation a required deliverable instead of optional.

I’ve got the exact fixes. I’m tightening the plan around two explicit obligations: helper-default-versus-custom-override coverage in missing-`jsonschema` environments, and a named documentation surface for the unsupported-backend fallback.

The revisions are in. I’m checking that the new acceptance criteria and deliverables actually close the verifier’s blockers and that the YAML still preserves runtime-owned metadata untouched.

Updated the plan artifacts to address both verifier blockers.

[plan.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/artifacts/plan/plan.md) now makes the helper-route exception concrete: helper-generated default question/blocked/failed route-fields contracts must stay compatible without `jsonschema`, custom helper overrides must still fail closed, and both paths are explicitly covered in the validation plan. It also makes the unsupported-backend fallback documentation mandatory, naming `docs/authoring.md` and `controlroutes.md` as required deliverables.

[phase_plan.yaml](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/artifacts/plan/phase_plan.yaml), [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/artifacts/plan/feedback.md), and [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/decisions.txt) were updated to reflect those corrections. No source code or tests were run on this planning turn.


---
run_id=run-20260506T204256Z-05282838 | entry=session_turn | pair=plan | phase=verifier | cycle=2 | attempt=1 | thread_id=019dff07-8be8-7403-85db-f40ae08ce678
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/plan_verifier.md
session_id=019dff07-8be8-7403-85db-f40ae08ce678


---
run_id=run-20260506T204256Z-05282838 | entry=phase_output | pair=plan | phase=verifier | process=codex-agent | cycle=2 | attempt=1 | thread_id=019dff07-8be8-7403-85db-f40ae08ce678
---
I’m re-verifying only the revised plan surfaces and the previous blockers. The main question now is whether the new helper-route coverage and the named documentation deliverables fully close the earlier gaps without introducing any new compatibility or scope drift.

The revised plan closes the earlier gaps. I’m marking the criteria accordingly and appending one non-blocking recheck note so the feedback history shows the blockers were actually resolved on the second pass.

Scope considered
Run-local verification of the revised planning artifacts against the immutable request, raw-log history, current decisions ledger, and the specific repo code paths that motivated the prior blocking findings.

What I analyzed
I re-checked the revised helper-route compatibility treatment, missing-`jsonschema` regression coverage, required unsupported-backend fallback documentation, compatibility notes, rollback language, and phase decomposition. I also confirmed `phase_plan.yaml` parses and that runtime-owned metadata stayed unchanged.

What I reviewed
I reviewed [plan.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/artifacts/plan/plan.md), [phase_plan.yaml](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/artifacts/plan/phase_plan.yaml), [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/artifacts/plan/feedback.md), [criteria.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/artifacts/plan/criteria.md), and [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/decisions.txt). I updated the criteria checklist and appended a non-blocking recheck note to the feedback history.

Key findings / decisions
No remaining blocking findings. The previous blockers are now explicitly covered:
`PLAN-001` is closed by helper-default-versus-custom-override acceptance criteria and missing-`jsonschema` regression coverage.
`PLAN-002` is closed by required documentation deliverables in `docs/authoring.md` and `controlroutes.md`, with the strict post-parse validation invariant called out.

Open issues / next step
The planning artifacts are consistent, concrete, and ready to hand off to implementation.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"COMPLETE"}
</loop-control>


---
run_id=run-20260506T204256Z-05282838 | entry=phase_scope_resolved
---
phase_mode=single
phase_ids=route-contract-enforcement,backend-response-schema-delivery
explicit=True
current_phase_index=0


---
run_id=run-20260506T204256Z-05282838 | entry=session_turn | pair=implement | phase=producer | cycle=1 | attempt=1 | thread_id=019dff0e-7daf-7a32-806b-ba0f9ef79fd1
---
provider=codex
mode=start
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/implement_producer.md
session_id=019dff0e-7daf-7a32-806b-ba0f9ef79fd1


---
run_id=run-20260506T204256Z-05282838 | entry=phase_output | pair=implement | phase=producer | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dff0e-7daf-7a32-806b-ba0f9ef79fd1
---
I’m starting with the phase artifacts and the route-schema/compiler/runtime paths that control route contract validation and provider schema handoff. Then I’ll trace the existing tests around helper routes, raw JSON Schema contracts, and structured-output transports before editing anything.

The plan splits cleanly into two paths: fail-closed compiler/runtime validation, and backend schema delivery/observability. I’m locating the exact compiler, engine, rendered-provider, backend, and test touchpoints now so the edits stay local instead of spreading through unrelated workflow code.

There’s a very dirty worktree, mostly outside this phase, so I’m keeping scope to the route/compiler/runtime/docs/test files already implicated by the request. Next I’m reading the specific functions that currently decide when validators are compiled and whether backend transports ever see the generated response schema.

The first pass shows the compiler currently compiles every explicit route schema the same way, while the engine still has handwritten compatibility checks for helper presets. I need the exact contract around those handwritten checks and the current backend metadata shape before editing, so I’m drilling into the remaining surrounding functions and existing backend tests.

I’ve confirmed the main failure mode: `_compile_route_contract()` explicitly swallows missing `jsonschema` for raw mappings, and the helper-route handwritten validation in the engine is the only reason question/blocked/failed still behave at runtime. The next step is to add a precise compiler-level distinction between helper-default route-fields contracts and custom raw mappings, then wire provider schema delivery metadata into the Codex/Claude transports and their tests.

I’ve reached the backend decision point: the code doesn’t currently pass schemas anywhere, so I need to verify whether the installed CLI surfaces expose any native schema/config path before I choose between true native delivery and an explicit prompt-only fallback. I’m checking the local `codex` and `claude` help surfaces now because that capability is environment-specific.

Plan:
1. Tighten route contract compilation so raw custom route schemas either produce validators or fail closed, while preserving the handwritten helper-default route-fields path only for semantically equivalent helper defaults.
2. Add regression coverage for missing-`jsonschema` compile behavior and for invalid custom payload/route-fields outcomes through both scripted and rendered providers.
3. Pass provider response schemas into backend transports where supported, record explicit structured-output delivery metadata for native/simplified/prompt-only modes, and add backend tests.
4. Update the phase notes and decision ledger with the non-obvious compatibility boundaries and validation performed.

I have enough context to edit. I’m changing the route helpers/compiler first so only helper-default question/blocked/failed route-fields can use the existing handwritten fallback when `jsonschema` is absent, while every custom raw route payload or route-fields mapping fails closed instead of silently degrading.

The helper/classifier change is in, but it exposed one internal seam in `Route.to(...)` that still needs the private marker threaded through. I’m patching that next, then I’ll add the missing-`jsonschema` tests before touching the transport layer.

I’m moving into the regression coverage now. The compile-path tests will lock the fail-closed behavior down before I touch backend plumbing, so if the transport work later shifts anything unexpectedly we still have a precise boundary around route contract enforcement.

I’ve locked the compile-path behavior; now I’m adding engine-level regressions that exercise the actual outcome-validation path for both fake/scripted and rendered providers. These are the tests that prove invalid custom raw payload and route-fields data still gets rejected after parse, regardless of transport style.

I’m editing the transport layer now. The native delivery path will be Codex `start` via `--output-schema`, while resume-mode Codex and Claude will record an explicit prompt-only fallback so the runtime can tell the difference between real backend schema delivery and prompt guidance only.

The transport implementation is in. I’m adding backend-facing tests against the actual command/request surface and the returned metadata so we can prove three distinct cases: native full delivery, native simplified delivery, and prompt-only fallback when the backend cannot accept a schema.

The last functional piece is documentation: I’m updating the authoring/runtime contract to make the delivery modes explicit so future changes don’t silently regress back to prompt-only behavior without anyone noticing.

I’ve finished the code paths and docs. I’m running focused tests on the new compile-time failures, runtime route validation regressions, and backend schema-delivery metadata so I can catch integration issues before touching the run artifacts.

`pytest` isn’t on PATH in this environment, so I’m rerunning through `python -m pytest`. If the environment still blocks that, I’ll at least validate syntax with `python -m compileall` and note the test runner limitation explicitly.

The shell only has `python3`, not `python`. I’m switching to `python3 -m pytest`, and if the repo dependencies are incomplete I’ll fall back to a syntax-only compile pass so we still get some validation signal.

`pytest` is unavailable, but the Python runtime is usable. I’m running a direct assertion script against the new compiler behavior, runtime route validation, and transport command/metadata assembly so we still get functional verification instead of syntax-only checks.

The system Python is missing repo dependencies like `pydantic`, so end-to-end execution isn’t possible with the ambient interpreter. I’m checking whether the repository already has a project-local virtualenv or runner before I stop at syntax-level validation.

There is a project-local `.venv`. I’m rerunning the focused test set inside that interpreter so we get real execution coverage instead of guessing from the ambient system Python.

The validation and backend transport tests are green. The engine-contract slice is still running; I’m waiting on that before I update the phase notes and close the loop.

The engine regression failures are real, but they’re environmental rather than logic regressions: this `.venv` doesn’t have `jsonschema`, so raw-schema routes now correctly fail at compile time. I’m adapting those runtime tests to install a tiny fake validator via monkeypatch so they still exercise the runtime enforcement path in a controlled “validator available” environment.

The remaining engine failures are just test harness setup: the rendered-provider path needs resolvable prompt text, unlike the scripted fake provider. I’m switching those two rendered regression workflows to inline prompt text so the failures stay focused on payload and route-fields validation.

I’m at the artifact update stage now. I’m recording the non-obvious compatibility decisions and the exact validation performed so later turns don’t drift on the helper-route exception, the backend fallback contract, or the fact that this repo’s default `.venv` does not include the optional `jsonschema` package.

The code and artifacts are updated. I’m doing one last focused validation pass after the final test-harness fixes so the recorded results in the notes match the current tree exactly.

One backend test still had a harness mismatch: Claude’s executor now passes `cwd` through the subprocess helper, so the test stub needs to accept it. I’m fixing that stub and rerunning just the backend slice.

The focused validation is green now. I’m doing a final diff skim of the files in scope so the close-out reflects the actual blast radius and any notable side effects, then I’ll summarize with the required headings.

Scope considered

- Route contract compilation and runtime enforcement for raw route `payload_schema` / `route_fields_schema`.
- Rendered-provider backend delivery of generated response schemas and explicit fallback metadata.
- Phase artifacts: `decisions.txt` and `implementation_notes.md`.

What I analyzed

- Compiler route-contract lowering in [compiler.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/compiler.py) and helper route construction in [routes.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/routes.py).
- Engine-side outcome validation in [engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/engine.py).
- Rendered transport/backends in [codex.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/providers/codex.py), [claude.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/providers/claude.py), and [_common.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/providers/_common.py).
- Existing validation, engine, and backend tests plus the active plan and phase notes.

What I changed

- Tightened route contract compilation so custom raw route `payload_schema` and `route_fields_schema` mappings now fail closed when `jsonschema` is unavailable instead of silently degrading to metadata-only.
- Preserved the missing-`jsonschema` compatibility path only for default `Route.question()`, `Route.blocked()`, and `Route.failed()` route-fields contracts by marking the helper-default path explicitly in [routes.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/routes.py).
- Wired Codex native schema delivery through `codex exec --output-schema` for start turns, writing the delivered schema into run-scoped files and recording `native_full` / `native_simplified` metadata.
- Added explicit `prompt_only` structured-output fallback metadata for unsupported surfaces, including Codex resume turns and Claude turns.
- Added regression coverage in [test_validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_validation.py), [test_engine_contracts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/contract/test_engine_contracts.py), and [test_provider_backends.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_provider_backends.py).
- Updated [docs/authoring.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/docs/authoring.md) and [controlroutes.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/controlroutes.md), plus the phase [implementation_notes.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/artifacts/implement/phases/route-contract-enforcement/implementation_notes.md) and [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0/runs/run-20260506T204256Z-05282838/decisions.txt).

Key findings / decisions

- The repo’s `.venv` does not include the optional `jsonschema` package, so raw-schema routes now correctly compile-fail by default; runtime enforcement tests use a fake validator seam to cover the “validator available” path without weakening product behavior.
- Native backend schema delivery is currently available only on Codex start turns from the observed CLI surface; Codex resume and Claude are documented and tested as prompt-only fallback paths.
- Legacy `ControlRoutes(question=...)` lowering and legacy top-level `question` / `reason` parsing were left intact.

Open issues / next step

- Focused validation passed:
  - `.venv/bin/python -m pytest tests/unit/test_validation.py -k "raw_route_payload_schema_without_jsonschema_dependency or raw_route_fields_schema_without_jsonschema_dependency or helper_default_route_fields_without_jsonschema_dependency or custom_helper_route_fields_override_without_jsonschema_dependency"`
  - `.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -k "invalid_custom_raw_route_payload or invalid_custom_raw_route_fields"`
  - `.venv/bin/python -m pytest tests/runtime/test_provider_backends.py -k "response_schema or prompt_only_fallback or output_schema_file or simplified_schema_delivery"`
- I did not run the full suite.
