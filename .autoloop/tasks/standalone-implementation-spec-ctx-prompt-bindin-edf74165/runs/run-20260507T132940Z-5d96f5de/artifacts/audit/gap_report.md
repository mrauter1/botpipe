# Gap Report

## Original intent considered

- Remove implicit `ctx.input.message` support from the `ctx.*` contract so request text lives on `ctx.message`, while `{ctx.input.<field>}` only works for declared `Input` fields.
- Restore live runtime `ctx.message` to the lazy file-backed `request.md` accessor path for fresh runs, resume, and branch/fan-in clones.
- Preserve supported `{ctx.message}`, `{ctx.request.*}`, `{ctx.state.<field>}`, `{ctx.params.<field>}` behavior and keep artifact-path rejection semantics unchanged.
- Add regression coverage proving undeclared `{ctx.input.message}` fails, `{ctx.message}` still works in prompts and `workflow_step(message=...)`, runtime contexts stay snapshot-backed, unreadable snapshots raise `WorkflowExecutionError`, and child input remains distinct from request text.

## Clarifications / superseding decisions

- The raw phase log contains no later user clarification that reintroduced `ctx.input.message` as a built-in request alias.
- `decisions.txt` explicitly narrows direct Python `ctx.input.message` / `ctx.input.model_dump()` to declared `Input` fields only and preserves bare `{input.message}` only as an isolated non-`ctx.*` compatibility shim.
- `decisions.txt` also explicitly keeps `Context(message=...)` as a synthetic override seam while runner/engine root contexts and branch/fan-in clones preserve `request_file` authority.

## Implemented behavior

- `WorkflowInputView` now exposes only declared typed input fields, with no built-in synthetic `message` field ([autoloop/core/context.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/context.py:91)).
- `Context.message` is lazy and file-backed whenever `_DEFAULT_MESSAGE` is preserved, raising through `RequestContext.text` if the run-local snapshot cannot be read ([autoloop/core/context.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/context.py:336)).
- Engine root/resume contexts keep `_DEFAULT_MESSAGE` whenever `request_file` is authoritative instead of forcing cached request text ([autoloop/core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/engine.py:298)).
- Runner-backed execution now passes `request_file` / `task_request_file` into `engine.run(...)` and `engine.resume(...)` without also overriding `message=` ([autoloop/runtime/runner.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/runner.py:308)).
- Branch/fan-in clones preserve the parent request snapshot path and only forward the parent `_message` sentinel/object, so file-backed semantics survive cloning ([autoloop/core/branch_groups/context.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/branch_groups/context.py:158)).
- Compile-time validation now rejects undeclared `ctx.input.<field>` references based on declared `Input` fields, while bare `{input.message}` remains separately allowed as the documented compatibility shim ([autoloop/core/discovery.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/discovery.py:1206), [autoloop/core/discovery.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/discovery.py:1369)).
- Runtime `ctx.*` resolution now raises when `ctx.input.*` is used without workflow input, rather than falling back to request text ([autoloop/core/artifacts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/artifacts.py:612)).
- Updated runtime/unit coverage already proves the new boundary in several places, including direct Python `ctx.input.model_dump()` and resumed snapshot-backed `ctx.message` ([tests/unit/test_primitives_and_stores.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_primitives_and_stores.py:75), [tests/runtime/test_workspace_and_context.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_workspace_and_context.py:736)).

## Unresolved gaps

- One stale contract test still encodes the retired alias and fails in the live workspace: [tests/contract/test_engine_contracts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/contract/test_engine_contracts.py:8655) expects undeclared `{ctx.input.message}` to render the request text as `"Message=artifact-request"`. That contradicts both the request and the current runtime implementation, which now raises `WorkflowExecutionError("ctx.input.message requires workflow input, but no input was provided")`.
- I verified the gap directly with:
  `./.venv/bin/python -m pytest tests/contract/test_engine_contracts.py -k 'runtime_templates_resolve_ctx_input_message_without_typed_input or runtime_templates_resolve_declared_ctx_input_message_separately_from_request or engine_context_message_raises_when_run_snapshot_is_removed_after_context_construction or workflow_step_message_can_forward_ctx_message_into_child_request_snapshot or workflow_step_message_renders_ctx_bindings_before_child_invocation'`
  Result: `1 failed, 4 passed`. The only failure is `test_runtime_templates_resolve_ctx_input_message_without_typed_input`.
- Because the request explicitly required feature tests to use `{ctx.message}` wherever request text is intended, the final codebase still contains a material regression-coverage miss even though the runtime behavior itself is correct.
- The test-pair artifacts currently overstate closure: [test_strategy.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/standalone-implementation-spec-ctx-prompt-bindin-edf74165/runs/run-20260507T132940Z-5d96f5de/artifacts/test/phases/finish-ctx-request-input-separation/test_strategy.md:9) and [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/standalone-implementation-spec-ctx-prompt-bindin-edf74165/runs/run-20260507T132940Z-5d96f5de/artifacts/test/phases/finish-ctx-request-input-separation/feedback.md:12) claim the requested contract is fully covered with no open findings, but the stale failing contract test shows that is not yet true.

## Differences justified by later clarification or analysis

- Bare `{input.message}` compatibility remains supported intentionally and separately from `ctx.*`; this is consistent with the recorded decisions and does not violate the request because the user only asked to remove the implicit alias from the `ctx.*` binding contract.
- Direct Python `ctx.input.message` is now allowed only when `Input.message` is explicitly declared. That narrowing is explicitly recorded in `decisions.txt` and matches the original request.
- Keeping `Context(message=...)` as an explicit synthetic-context override seam is justified by the decisions ledger as long as runner/engine root contexts do not use it when `request_file` is authoritative.

## Recommended next run

- Update the stale contract regression in `tests/contract/test_engine_contracts.py` so undeclared `{ctx.input.message}` no longer asserts request-text aliasing.
- Keep the declared-`Input.message` positive test and the existing `ctx.message` child-workflow / unreadable-snapshot coverage.
- Rerun the focused contract subset including the stale test, then refresh the follow-up run’s verification summary based on that result.
