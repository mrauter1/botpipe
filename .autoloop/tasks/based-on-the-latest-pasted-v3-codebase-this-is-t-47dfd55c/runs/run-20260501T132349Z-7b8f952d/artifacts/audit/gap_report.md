# Gap Report

## Original intent considered

- Reviewed the immutable request snapshot at `.autoloop/tasks/.../runs/run-20260501T132349Z-7b8f952d/request.md`, including the requested hard cuts around `AWAIT_INPUT`, `RequestInput` / `Goto` / `Fail`, hidden routes, public API cleanup, namespace/package cleanup, optimizer boundary changes, schema/tracing work, session-store unification, replay changes, and the final golden workflow/docs/test pass.
- Reviewed the authoritative clarification ledger in `raw_phase_log.md`, the non-obvious decision ledger in `decisions.txt`, and the phase-local implement/test artifacts under `.autoloop/tasks/.../artifacts/implement/phases/*` and `.autoloop/tasks/.../artifacts/test/phases/*`.
- Compared those artifacts against the final codebase under `autoloop/`, `autoloop_optimizer/`, `workflows/`, `docs/`, and `tests/`.

## Clarifications / superseding decisions

- Decision block 3 limited `on_route` removal to the public simple authoring surface in phase 1, while allowing internal core-step `on_route` plumbing to remain during the runtime-control transition. Public topology payloads still had to stop exposing `on_route`.
- Decision blocks 3, 4, 7, and 19 explicitly preserved read compatibility for legacy persisted `paused` / `pending_question` data while making new writes and public-facing status payloads canonical as `AWAIT_INPUT`, `awaiting_input`, and `pending_input`.
- Decision blocks 9 and 10 required legacy schema-less runtime artifacts to remain readable, but explicit unknown schema ids to fail clearly.
- Decision block 15 allowed thin `InMemorySessionStore` / `FilesystemSessionStore` wrappers to remain on top of the new backend-composed `SessionStore` so runtime/tests would not need a second compatibility layer.

## Implemented behavior

- Public authoring/export surface matches the requested cutover: `autoloop/__init__.py` exports `Workflow`, step builders, `llm`, `classify`, `Route`, `Event`, `Outcome`, `RequestInput`, `Goto`, `Fail`, `FINISH`, `AWAIT_INPUT`, `FAIL`, and `SELF`; `PAUSE`, `SUCCESS`, `StrictWorkflow`, `RouteInfo`, `chain`, `review_step`, `do_review_step`, `system_step`, and other removed names are guarded by `tests/strictness/test_no_compat.py` and `tests/unit/test_simple_surface.py`.
- Runtime controls and pending-input behavior are implemented in `autoloop/core/primitives.py`, `autoloop/core/engine.py`, `autoloop/core/context.py`, `autoloop/core/errors.py`, and `autoloop/runtime/runner.py`, with direct coverage in `tests/contract/test_engine_contracts.py` for `RequestInput`, `Goto`, `Fail`, invalid control validation, checkpoint persistence, resumed input validation, preserved state/session on failure, and runtime-control trace metadata.
- Hidden routes and provider-visible filtering are implemented in `autoloop/core/providers/rendering.py` and `autoloop/runtime/static_graph.py`, with coverage in `tests/runtime/test_runtime_static_graph.py` and `tests/runtime/test_runtime_tracing.py` for hidden-route topology visibility, provider filtering, runtime-control hook locations, and route/finalization metadata.
- Namespace cleanup landed: the live tree is under `autoloop/`; the deleted compatibility package `autoloop_v3/` and top-level `core` / `runtime` / `stdlib` / `extensions` package roots are absent; strictness tests assert those imports fail.
- Stable inspection/query APIs exist in `autoloop/runtime/inspection.py` and are consumed by optimizer modules under `autoloop_optimizer/`.
- Session store composition exists in `autoloop/core/stores/session_store.py` and `autoloop/runtime/stores/filesystem.py`.
- The final proof layer exists: `tests/runtime/test_golden_workflow.py`, `docs/authoring.md`, `tests/test_architecture_baseline_docs.py`, and the logged phase slices (`166 passed`, `275 passed`, `277 passed`) cover the requested golden workflow, canonical docs, hidden routes, runtime controls, topology artifacts, and telemetry/history. I also re-ran a representative current-tree slice:
  `./.venv/bin/python -m pytest -q tests/strictness/test_no_compat.py tests/runtime/test_golden_workflow.py tests/runtime/test_workspace_and_context.py::test_run_record_projects_legacy_pending_question_as_pending_input tests/runtime/test_history.py::test_context_history_marks_fail_runtime_control_as_failed`
  Result: `15 passed in 2.43s`.

## Unresolved gaps

- No material unresolved gaps found against the authoritative request plus later clarifications.

## Differences justified by later clarification or analysis

- Internal core-step `on_route` support still exists in `autoloop/core/steps.py`, `autoloop/core/compiler.py`, `autoloop/core/engine.py`, and related contract tests, but the public simple surface no longer accepts or exports `on_route`, and public topology payloads omit it. This matches decision block 3 and does not leave a public API gap.
- `RunRecord.paused` and `RunRecord.pending_question` remain read aliases in `autoloop/runtime/workspace.py`, and legacy persisted data is projected into canonical `awaiting_input` / `pending_input` read surfaces. New runtime writes are `pending_input`-only. This matches decision blocks 3, 4, 7, and 19.
- Legacy schema-less runtime artifacts remain readable through the inspection/history/optimizer readers, while explicit unknown schema ids fail. That is the intended compatibility contract from decision blocks 9 and 10, not an incomplete schema rollout.
- Deleted workflow-facing extension modules are gone at the source level (`autoloop/extensions/tracing.py` and `autoloop/extensions/git/declaration.py` do not exist). Residual `__pycache__` entries are not part of the live source/import surface and are already guarded by direct import-failure tests.

## Recommended next run

- No follow-up implementation run is required for this request.
