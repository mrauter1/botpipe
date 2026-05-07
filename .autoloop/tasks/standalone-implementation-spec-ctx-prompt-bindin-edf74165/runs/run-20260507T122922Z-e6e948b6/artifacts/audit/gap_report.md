# Original intent considered

The audit compared the immutable request snapshot, the authoritative raw phase log, the shared decisions ledger, the implementation/test artifacts for all three implement/test phases, the final code in `autoloop/core`, `autoloop/runtime`, and `docs/`, and the shipped regression tests.

The governing intent was the standalone spec for safe `ctx.*` prompt bindings:

- `ctx.message` and `ctx.request.text` must read the run-local `request.md` snapshot.
- `{ctx.input.<field>}` must refer to declared typed input fields only.
- `ctx.message`, `ctx.input`, `ctx.state`, and `ctx.params` must remain semantically distinct.
- `ctx.*` must work in provider prompts, operation prompts, and `workflow_step(message=...)`.
- `ctx.*` must be rejected in artifact path templates.

# Clarifications / superseding decisions

No later clarification removed requested behavior. The authoritative decisions reinforced the original contract:

- `decisions.txt` block 1: `ctx.message` and `ctx.request.text` must read the run-local snapshot lazily so resume, branch, and fan-in contexts observe the persisted request instead of mutable task metadata or fresh runner options.
- `decisions.txt` block 1: safe `ctx` validation must live in one shared module and be reused by compile-time and runtime code.
- `decisions.txt` block 1: `ctx.*` is prompt-only and must be rejected in artifact paths.
- `decisions.txt` block 8: synthetic child-workflow contract coverage was an acceptable substitute for runner-backed nested child execution because of an unrelated active-event-loop limitation.

# Implemented behavior

The main feature landed and is materially functional:

- `autoloop/core/context.py:37-50` adds `RequestContext.text` with the requested UTF-8 read and `WorkflowExecutionError` on file-read failure.
- `autoloop/core/context.py:331-351` adds `ctx.request_file`, `ctx.request`, and `ctx.message`.
- `autoloop/core/context_placeholders.py:8-58` centralizes the safe `ctx.*` path-shape contract.
- `autoloop/core/artifacts.py:220-302` adds `PromptContextView`, `ctx` runtime resolution, scalar rendering, and explicit artifact-path rejection for `ctx.*`.
- `autoloop/core/discovery.py:1156-1166` and `1367-1438` add compile-time `ctx.*` validation with the requested `{message}` and `{ctx}` failures.
- `autoloop/core/engine.py:1368-1373`, `2330-2335` and `autoloop/core/operations.py:623-627` render `ctx.*` in provider prompts, operation prompts, and `workflow_step(message=...)`.
- `docs/authoring.md:121-156` and `docs/architecture.md:263-321` document `ctx.*` as the preferred runtime binding namespace.

Feature-focused regression tests are present and passing. I reran:

- `tests/unit/test_primitives_and_stores.py::test_context_request_surface_reads_run_snapshot_and_task_request_file`
- `tests/unit/test_primitives_and_stores.py::test_render_runtime_template_resolves_ctx_bindings_with_scalar_values`
- `tests/unit/test_simple_surface.py::test_simple_workflow_accepts_supported_ctx_prompt_bindings`
- `tests/contract/test_engine_contracts.py::test_ctx_prompt_bindings_render_in_provider_and_operation_prompts`
- `tests/runtime/test_workspace_and_context.py::test_resume_context_message_uses_run_local_request_snapshot_not_mutated_task_request`

Result: `5 passed in 0.74s`.

# Unresolved gaps

1. `ctx.input.message` is still implemented and tested as a supported alias for the run request, which conflicts with the typed-input separation contract.

Evidence:

- `autoloop/core/context.py:90-108` defines `WorkflowInputView.message` and merges it into `ctx.input.model_dump()`.
- `autoloop/core/context.py:349-351` still exposes that composite `WorkflowInputView` as `ctx.input`.
- `autoloop/core/discovery.py:1425-1427` explicitly special-cases `ctx.input.message` as valid even when it is not a declared `Input` field.
- `tests/unit/test_primitives_and_stores.py:87-89`, `166-170`, and `211-220` assert and render `ctx.input.message`.
- `tests/contract/test_engine_contracts.py:8486-8492` uses `{ctx.input.message}` in provider and producer prompts.

Why this is material:

- The original request said `ctx.input` must remain typed structured workflow input, `{ctx.input.<field>}` is valid only for declared `Input` fields, and `ctx.input` must never alias `ctx.message`.
- The current implementation and tests preserve an alias that the requested API explicitly tried to avoid.

2. Live runtime contexts still accept an injected `message=` string, so `ctx.message` is not guaranteed to read lazily from the run-local request snapshot during normal runner-backed execution.

Evidence:

- `autoloop/core/context.py:340-343` returns cached `_message` whenever it was supplied, instead of reading `self.request.text`.
- `autoloop/runtime/runner.py:317-321` and `339-340` pass `message=task_request_text(prepared.run_workspace.request_file)` into `engine.resume(...)` and `engine.run(...)`.
- `autoloop/core/engine.py:327-330`, `383-385`, and `428-431` forward that `message` value into every root runtime `Context(...)`.
- `autoloop/core/branch_groups/context.py:166-179` clones branch/fan-in contexts with `message=parent.message`, which preserves the cached string rather than the file-backed accessor path.

Why this is material:

- The spec and decisions required `ctx.message` to come from the run-local request snapshot and to stay lazy so request-file read failures surface as `WorkflowExecutionError`.
- The current runner-backed path pre-reads the snapshot and caches the text, so real executions no longer exercise the file-backed `ctx.message` semantics that the spec required.
- Existing tests only prove snapshot stability and synthetic missing-file behavior. They do not verify that runner-backed contexts still fail correctly when the run-local request snapshot is unreadable after context construction.

# Differences justified by later clarification or analysis

- Child-workflow message forwarding was validated with a synthetic child `Context` instead of a runner-backed nested child run. That difference is justified by `decisions.txt` block 8 and the recorded phase analysis: the current nested synchronous child-run path already hits an unrelated active-event-loop limitation, so the synthetic contract test was a scoped way to verify `ctx.message` forwarding behavior without conflating it with separate runtime debt.
- No auto-injection, artifact-path rejection, compile-time `{message}` rejection, and resume snapshot stability were all implemented consistently with the request and later decisions.

# Recommended next run

Run a focused follow-up implementation to close the two remaining contract gaps:

- remove the implicit `ctx.input.message` alias from the `ctx.*` prompt-binding contract so `ctx.input` again represents declared structured input rather than request text;
- make runner-backed and cloned runtime contexts derive `ctx.message` from `request_file` instead of a cached injected string, then add regression coverage for real runtime missing/unreadable request snapshots.
