## Follow-up implementation request: finish `ctx.*` request/input separation and file-backed message semantics

The `ctx.*` prompt-binding feature is mostly implemented, but two material contract gaps remain and should be fixed in one follow-up run.

### 1. Remove implicit `ctx.input.message` support from the `ctx.*` binding contract

Requested behavior was:

- `ctx.message` is the natural-language run request.
- `ctx.input` is typed structured workflow input.
- `{ctx.input.<field>}` is valid only when the workflow declares `class Input(BaseModel)` and `<field>` is an actual declared input field.
- `ctx.input` must not alias `ctx.message`.

Current behavior still accepts and tests `{ctx.input.message}` as a request-text alias. Fix that so:

- `{ctx.input.message}` is rejected unless the workflow’s `Input` model explicitly declares a `message` field.
- Prompt validation and runtime rendering both enforce the same rule.
- Feature tests use `{ctx.message}` wherever request text is intended.

If Python-surface compatibility requires care, preserve backward compatibility only where explicitly necessary, but the prompt-binding contract itself must match the original request and stop treating `ctx.input.message` as a built-in request alias.

### 2. Make live runtime `ctx.message` file-backed again

Requested behavior was:

- `ctx.message` reads the run-local `request.md` snapshot.
- Resume keeps using that persisted run-local snapshot.
- `ctx.message` should stay lazy and raise `WorkflowExecutionError("run request snapshot could not be read: <path>")` when the snapshot cannot be read.

Current runner-backed execution still injects a pre-read `message=` string into runtime `Context(...)` construction, which means normal execution can bypass the file-backed accessor path.

Fix that so:

- root runtime contexts created by `runner.py` and `engine.py` do not override `ctx.message` with a cached string when `request_file` is authoritative;
- branch and fan-in cloned contexts preserve the request snapshot path without switching to cached text;
- live runtime behavior matches the documented file-backed `ctx.message` contract.

### Required regression coverage

Add or update tests to prove:

- `{ctx.input.message}` fails unless `Input` explicitly declares `message`;
- `{ctx.message}` continues to work across provider prompts, operation prompts, and `workflow_step(message=...)`;
- runner-backed and resumed contexts still read the run-local request snapshot;
- a real runtime context created through the engine/runner path raises `WorkflowExecutionError` when the run-local request snapshot is unreadable after context construction;
- child input remains distinct from request text.

### Non-goals

- Do not reopen the full `ctx.*` feature scope.
- Do not remove supported `{ctx.message}`, `{ctx.request.*}`, `{ctx.state.<field>}`, or `{ctx.params.<field>}` behavior.
- Do not change artifact-path rejection semantics for `ctx.*`.
