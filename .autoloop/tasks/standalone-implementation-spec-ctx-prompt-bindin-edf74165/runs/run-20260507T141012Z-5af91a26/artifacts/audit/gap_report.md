# Gap Report

## Original intent considered
- The request asked for the last stale contract regression to stop treating undeclared `{ctx.input.message}` as request text.
- It allowed two acceptable outcomes for that test: switch request-text coverage to `{ctx.message}` or assert the current undeclared-`ctx.input` failure behavior instead.
- Required validation had to cover the updated undeclared-`ctx.input.message` case, the declared `Input.message` positive case, unreadable run-snapshot failure, and `workflow_step(message=...)` forwarding through `{ctx.message}`.
- Non-goals were explicit: do not remove bare `{input.message}` compatibility, do not break file-backed `ctx.message`, and do not reopen runtime unless focused reruns showed a real mismatch.

## Clarifications / superseding decisions
- `raw_phase_log.md` contains no later user clarification that changes the request; the initial request remained authoritative.
- `decisions.txt` records the governing interpretation: undeclared `{ctx.input.message}` should fail unless `Workflow.Input` declares `message`, while bare `{input.message}` compatibility and file-backed `ctx.message` stay intact.
- Later implementation/test decisions are consistent with the request: once focused reruns exposed a real runtime mismatch, a narrow runtime fix became in-scope under the request’s explicit exception.

## Implemented behavior
- `PromptContextView.input` now exposes declared workflow input fields instead of the compatibility view in [autoloop/core/artifacts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/artifacts.py:239).
- `_resolve_ctx_placeholder` now applies the no-input guard uniformly for `ctx.input.*` and raises unknown-runtime-field errors for undeclared members, including `message`, in [autoloop/core/artifacts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/artifacts.py:573).
- The stale contract was converted into the undeclared-access failure case in [tests/contract/test_engine_contracts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/contract/test_engine_contracts.py:8655).
- The declared `Input.message` positive case remains and now proves separation from `ctx.message` in [tests/contract/test_engine_contracts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/contract/test_engine_contracts.py:8691).
- The required snapshot-failure and child-forwarding cases remain covered in [tests/contract/test_engine_contracts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/contract/test_engine_contracts.py:8764) and [tests/contract/test_engine_contracts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/contract/test_engine_contracts.py:8823).
- Matching unit coverage exists for undeclared failure, declared separation, and preserved bare-versus-`ctx` compatibility in [tests/unit/test_primitives_and_stores.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_primitives_and_stores.py:229), [tests/unit/test_primitives_and_stores.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_primitives_and_stores.py:264), and [tests/unit/test_primitives_and_stores.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_primitives_and_stores.py:543).
- Final audit reran the focused slice with `.venv/bin/python -m pytest ...` and got `8 passed`, including all four required contract scenarios plus the added compatibility regression guard.

## Unresolved gaps
- None.

## Differences justified by later clarification or analysis
- The final change set is slightly broader than the initial “test-only unless needed” request because focused reruns proved a real runtime mismatch: declared `ctx.input.message` still aliased request text. The request explicitly allowed reopening runtime in that case, so the narrow resolver change is justified.
- An extra unit regression test was added to lock down the intentional non-goal that bare `{input.message}` must keep using runtime/request text even when typed `Input.message` exists. This is additive protection, not scope drift.

## Recommended next run
- No follow-up implementation run is required for this request.
