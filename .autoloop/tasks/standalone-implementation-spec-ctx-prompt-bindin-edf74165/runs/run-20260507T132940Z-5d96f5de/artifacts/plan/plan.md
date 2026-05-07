# Plan

## Goal
Align `ctx.*` with the requested request/input split: `ctx.message` stays the run-local request snapshot, `ctx.input` exposes only declared typed input fields, and runner/engine/branch execution paths keep message access file-backed and lazy.

## Repo Findings
- `autoloop/core/context.py` still makes `ctx.input.message` a synthetic alias of request text through `WorkflowInputView.message` and `WorkflowInputView.model_dump()`.
- `autoloop/core/discovery.py` still special-cases `ctx.input.message` as always valid during prompt validation.
- `autoloop/core/artifacts.py` resolves `ctx.input.*` through `PromptContextView.input -> Context.input`, so runtime rendering follows the same synthetic alias instead of declared `Input` fields.
- The same `WorkflowInputView.message` alias path currently leaks into non-`ctx.*` compatibility surfaces: direct `context.input.message`, `context.input.model_dump()`, branch/child runtime assertions, and legacy bare `{input.message}` artifact-template behavior in `tests/unit/test_primitives_and_stores.py`.
- `autoloop/runtime/runner.py` still passes `message=task_request_text(prepared.run_workspace.request_file)` into `engine.run(...)` and `engine.resume(...)`.
- `autoloop/core/engine.py` still propagates `message=message` into root selection/start/step contexts, and `autoloop/core/branch_groups/context.py` still clones `message=parent.message`, both of which bypass the lazy `request.md` accessor path.
- `docs/authoring.md` and `docs/architecture.md` already describe the requested contract correctly; the main drift is in runtime code and tests, not the asserted public docs.
- Current tests already cover resume versus mutated task request and child request/input separation, but they also codify the `ctx.input.message` alias, encode legacy non-`ctx.*` `input.message` behavior, and do not yet cover unreadable run-local `request.md` after an engine/runner-backed context has been constructed.

## Implementation Plan
### 1. Remove implicit request-text aliasing from `ctx.input`
- Tighten prompt validation so `{ctx.input.message}` is accepted only when the workflow’s `Input` model explicitly declares `message`.
- Narrow the runtime `ctx.input` surface in `Context` / `WorkflowInputView` so undeclared `message` is no longer synthesized from the request snapshot.
- Update existing feature and contract tests to use `{ctx.message}` wherever request text is intended, including provider prompts, operation prompts, and `workflow_step(message=...)`.
- Treat direct Python `ctx.input.message` and `ctx.input.model_dump()` request-text aliasing as part of the same intentional narrowing: runtime tests/helpers that mean request text should migrate to `ctx.message`, and only workflows that explicitly declare `Input.message` should keep `ctx.input.message`.
- Bound the shared compatibility seam explicitly: preserve legacy bare `{input.message}` behavior only if the implementation keeps it as a separate non-`ctx.*` compatibility shim in the legacy placeholder path; do not let bare-`input` compatibility keep `ctx.input` itself aliased to request text.
- Keep `ctx.message` and `ctx.request.text` as the only built-in request-text bindings.
- Preserve explicit `Context(message=...)` overrides only as a synthetic-context escape hatch when truly needed; do not let that override preserve implicit `ctx.input.message` aliasing.
- If `sdk.md` or other in-tree examples are touched while updating these surfaces, align them to the chosen boundary in the same slice so the repo does not keep advertising the retired alias as current behavior.

### 2. Restore file-backed `ctx.message` semantics across runtime context creation
- Stop passing pre-read run request text from `runner.py` into normal `engine.run(...)` and `engine.resume(...)` calls when `request_file` is authoritative.
- Keep the `_DEFAULT_MESSAGE` sentinel through root engine contexts so `Context.message` reads via `RequestContext.text`.
- Update branch and fan-in cloned contexts to preserve `request_file` / `task_request_file` plus the sentinel instead of copying `parent.message`.
- Keep child workflow behavior unchanged: rendered `workflow_step(message=...)` strings still become the child run’s own `request.md`, but live parent/root/clone contexts must no longer switch to cached request text.
- Do not change workspace layout, request snapshot persistence, CLI flags, or supported `ctx.request.*`, `ctx.state.*`, `ctx.params.*`, or artifact-path rejection behavior.

### 3. Rebaseline regression coverage on the requested contract
- Add compile-time and runtime negative coverage for `{ctx.input.message}` when `Input.message` is undeclared.
- Add positive coverage that `{ctx.input.message}` still works when `Input` explicitly declares `message`.
- Extend runtime-backed tests to prove fresh-run and resumed contexts still read the run-local `request.md` snapshot after task-level `request.md` mutates.
- Add an engine/runner-path failure test that makes the run-local `request.md` unreadable after context construction and verifies `ctx.message` raises `WorkflowExecutionError("run request snapshot could not be read: <path>")`.
- Keep or strengthen child-workflow assertions that request text and typed child input remain distinct.
- Add explicit compatibility-boundary coverage for the shared alias path:
  - direct Python `ctx.input.message` and `ctx.input.model_dump()` no longer act as request-text aliases unless `Input.message` is declared,
  - preserved legacy bare `{input.message}` behavior, if retained, is covered as compatibility-only behavior outside the `ctx.*` contract,
  - touched examples/docs no longer claim that undeclared `ctx.input.message` is built in.

## Interfaces And Invariants
- `ctx.message` and `ctx.request.text` are the built-in request-text surfaces and must stay lazy/file-backed whenever a run-local `request_file` exists.
- `{ctx.input.<field>}` is valid only for declared `Input.model_fields`; `ctx.input.message` is not special.
- Direct Python `ctx.input.message` is governed by the same rule as prompt bindings: it exists only when the workflow explicitly declares `Input.message`, not as a built-in request alias.
- Root engine/runner contexts, resume contexts, branch clones, and fan-in clones must preserve the same run-local request snapshot path instead of caching request text.
- `workflow_step(message="{ctx.message}", ...)` must continue to forward rendered request text into the child run’s own `request.md`.
- `Context(message=...)` may remain as an explicit override seam for synthetic contexts and tests, but runtime-backed root/clone construction must not use it when `request_file` is authoritative.
- Any retained bare `{input.message}` behavior is a legacy non-`ctx.*` compatibility surface and must be implemented and tested as such, rather than by keeping `ctx.input` aliased to request text.

## Compatibility / Behavior
- Intentional contract narrowing: `ctx.input.message` stops being a built-in alias and becomes valid only when a workflow explicitly declares `Input.message`.
- This intentional narrowing covers both prompt bindings and direct Python `ctx.input.message` / `ctx.input.model_dump()` semantics, because the request says `ctx.input` itself must not alias `ctx.message`.
- Non-`ctx.*` legacy bare `{input.message}` behavior is not part of the requested contract change. The safer default for this follow-up is to preserve it only as an isolated compatibility shim, or else explicitly migrate it with paired tests if implementation proves that keeping it would create more inconsistency than value.
- This behavior change is explicitly requested and should not be softened back into the `ctx.*` contract for compatibility convenience.
- Existing asserted docs already match the desired behavior; implementation should focus on code/test alignment and update stale internal examples like `sdk.md` only where they still contradict the shipped boundary.
- Synthetic direct-`Context(...)` tests that intentionally pass `message=` should keep working unless implementation proves that seam is unnecessary.

## Validation
- Run focused suites covering the affected seams:
  - `tests/unit/test_primitives_and_stores.py`
  - `tests/unit/test_branch_group_context_sessions.py`
  - `tests/unit/test_simple_surface.py`
  - `tests/contract/test_engine_contracts.py`
  - `tests/runtime/test_workspace_and_context.py`
- Verify both validation-time and runtime failure paths for undeclared `{ctx.input.message}`.
- Verify direct Python `ctx.input.message` and `ctx.input.model_dump()` no longer alias request text unless `Input.message` is declared.
- Verify fresh-run, resume, and branch/fan-in-adjacent paths still resolve request text from run-local `request.md`.
- Verify unreadable run-local request snapshots now fail through live engine/runner-backed `ctx.message` access rather than being masked by cached strings.
- Verify legacy bare `{input.message}` behavior explicitly either stays green as compatibility-only behavior or is intentionally migrated with paired expectation updates, rather than changing accidentally as a side effect of `ctx.*` work.

## Risk Register
- Removing the synthetic `ctx.input.message` alias can break legacy tests/helpers that treated request text as input.
  Mitigation: rewrite request-text expectations to `ctx.message`, decide the direct-Python surface explicitly, and keep any bare-`input` compatibility shim outside the `ctx.*` contract if one is absolutely necessary.
- Eliminating cached root/clone message text can expose latent file-read failures in normal runtime paths.
  Mitigation: add explicit unreadable-snapshot coverage for fresh and resumed engine/runner-backed contexts.
- A partial fix could leave compile-time and runtime behavior inconsistent.
  Mitigation: treat validator, runtime placeholder resolution, direct `Context.input` behavior, legacy bare-`input` compatibility, and test/doc updates as one change set.
- Overcorrecting could break explicit `Context(message=...)` synthetic uses that are unrelated to file-backed runtime execution.
  Mitigation: preserve the explicit override seam unless the implementation confirms it is genuinely unused.

## Rollback
- Revert validator/runtime/test changes together if downstream compatibility breaks appear outside the requested contract.
- Prefer restoring only a narrow explicit override seam or isolated bare-`input` compatibility shim over reintroducing implicit `ctx.input.message` aliasing across the full `ctx.*` surface.
- Do not ship a hybrid state where validation rejects `{ctx.input.message}` but runtime still resolves it, or vice versa.
