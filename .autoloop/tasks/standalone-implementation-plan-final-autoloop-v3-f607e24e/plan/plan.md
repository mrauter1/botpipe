# Standalone implementation plan: final Autoloop v3 greenfield cleanup with retry-aware event validation

## Scope

This pass is a greenfield cleanup. It intentionally removes obsolete compatibility residue instead of preserving it.

Primary outcomes:

1. Invalid `Event` payloads are rejected everywhere.
2. Provider-attributable invalid events reuse the existing provider retry loop and feedback path.
3. Deterministic workflow-code invalid events fail immediately with `WorkflowExecutionError`.
4. Dead compatibility surfaces (`BoardMutation`, generated `workflow_step(...)` handlers, `contracts_path`, old stdlib `contracts` names) are removed from active code, payloads, docs, and tests.

Explicitly out of scope:

- `autoloop eject`
- source-code expansion or code generation
- compatibility aliases for removed route-contract terminology
- restoring `workflow/primitives.py` as an authoring API

## Repository findings

- `core/engine.py` already contains the provider retry loop, `_validate_outcome(...)`, `_next_retry_feedback(...)`, artifact-validation retry metadata, middleware application, after-hook normalization, and child-workflow execution. This is the right place to centralize `Event` validation.
- `core/validation.py` still contains generated simple `workflow_step(...)` handler helpers and the `BoardMutation` validation branch.
- `core/effects.py`, `core/__init__.py`, and `core/engine.py` still expose or branch on `BoardMutation`.
- `stdlib/contracts.py` and `stdlib/__init__.py` still use the old helper names.
- `core/workflow_catalog.py`, `core/workflow_capabilities.py`, and `runtime/cli.py` still expose `contracts_path`; `contracts.py` is not yet normalized into `spec_paths`.
- `autoloop/__init__.py`, `autoloop/simple.py`, and `workflow/__init__.py` still contain stale compatibility or future-lowering language.
- `core/compiler.py` still contains stale compatibility wording (`artifact_items(...): authoritative=False preserves the compatibility alias map`), so the terminology cleanup must cover active core code comments/docstrings, not only public authoring modules and docs.
- Existing tests already cover provider retry behavior, simple-surface lowering, workflow shims, and capability payloads, so the safest approach is to extend those suites rather than invent new harnesses.

## Implementation contract

### Milestone 1: Retry-aware shared event validation

Files:

- `core/engine.py`
- tests in `tests/contract/test_engine_contracts.py` and any adjacent retry/unit suites already asserting provider retry metadata

Required changes:

- Add `_validate_event(step, event, *, provider_attributable, error_cls=WorkflowExecutionError)`.
- Factor reserved-route payload checks into a shared helper only if it reduces duplication between `_validate_outcome(...)` and `_validate_event(...)` without weakening the current provider error metadata.
- Keep `_validate_outcome(...)` as the provider `Outcome` validator and preserve its retry metadata contract.
- Call `_validate_event(...)` after system handler normalization, after child-workflow result mapping, after middleware returns an `Event`, before after-hook finalization for the candidate event, and again after the after hook for the final event.
- Audit `_next_retry_feedback(...)` explicitly and keep it aligned with the request’s full retry-kind set: `illegal_route`, `invalid_payload`, `missing_required_output_artifact`, `invalid_output_artifact`, `malformed_provider_output`, and `provider_transport_failure`.
- Keep provider attribution conservative:
  - provider outcome and verifier outcome: `True`
  - middleware event on provider steps: `True`
  - after-hook string route override on provider steps: `True`
  - explicit `Event` or `AfterHookResult(event=...)` from hooks: `False`
  - system step handler and workflow-step child mapping: `False`
- Ensure invalid provider-attributable events raise `ProviderExecutionError` with `_provider_retry_kind` of `illegal_route` or `invalid_payload` plus `_failure_context`.
- Ensure deterministic invalid events raise `WorkflowExecutionError` and do not enter retry.

Validation targets:

- Provider invalid `question` retries and can recover.
- Provider invalid `blocked`/`failed` retries and can recover.
- Retry exhaustion preserves `failure_context.kind == "invalid_payload"` and marks retry exhaustion.
- `system_step(fn)` invalid `Event("question")` / `Event("failed")` hard-fails.
- Provider-step after-hook string retagging can retry when it produces an invalid final event.
- Explicit invalid hook-returned `Event` hard-fails.
- Child-workflow malformed pause/fail mapping hard-fails.

### Milestone 2: Remove generated workflow-step handlers and `BoardMutation`

Files:

- `core/validation.py`
- `core/effects.py`
- `core/__init__.py`
- `core/engine.py`
- tests covering simple-surface lowering, workflow validation, and public exports

Required changes:

- Delete the generated simple workflow-step helper functions from `core/validation.py` and clean up now-unused imports.
- Confirm simple `workflow_step(...)` lowers only to `core.steps.WorkflowStep`; it must not install `on_<step>` handlers or require a system fallback.
- Remove `BoardMutation` from active code instead of keeping a public placeholder.
- Delete the `BoardMutation` effect type if possible; otherwise make it private and unreachable, but do not export or document it.
- Remove engine and validation branches that special-case `BoardMutation`.

Validation targets:

- Compiled simple workflow steps are `WorkflowStep` instances with `kind == "workflow"` and no compiled `system_handler`.
- Workflow classes do not receive generated `on_<step>` handlers.
- `autoloop` and `core` do not expose `BoardMutation`.
- Active tests/docs no longer mention `BoardMutation`.

### Milestone 3: Rename route-info helpers and remove `contracts_path`

Files:

- `stdlib/contracts.py` -> `stdlib/route_infos.py`
- `stdlib/__init__.py`
- `core/workflow_catalog.py`
- `core/workflow_capabilities.py`
- `runtime/cli.py`
- tests covering stdlib exports, capability payloads, catalog discovery, and selected-workflow surfaces

Required changes:

- Rename `review_gate_contracts(...)` to `review_gate_infos(...)` and `publication_gate_contracts(...)` to `publication_gate_infos(...)`; delete the old module and names without aliases.
- Update all imports and tests to the new module and names.
- Remove `contracts_path` from `WorkflowCatalogEntry`, `WorkflowCapabilityEntry`, capability payloads, authoring-surface payloads, decomposition payloads, and CLI JSON.
- Delete `_contracts_path(...)` / `_support_contracts_path(...)`.
- Expand `_spec_paths(...)` / `_support_spec_paths(...)` so both `specs.py` and `contracts.py` are treated as spec/support files.
- Ensure `editable_paths` is derived from `spec_paths`, so `contracts.py` is still editable when present.
- Keep `legacy_workflow_path` behavior unchanged for now unless implementation proves a safe local rename; this pass only requires neutral treatment in docs/comments.

Validation targets:

- `stdlib/contracts.py` no longer exists.
- `stdlib.route_infos.review_gate_infos` and `.publication_gate_infos` exist and return `dict[str, RouteInfo]`.
- `contracts_path` and `contracts_path_repo_relative` disappear from public payloads.
- `contracts.py` appears via `spec_paths` and therefore `editable_paths`.

### Milestone 4: Tighten strictness tests and refresh docs/docstrings

Files:

- `tests/strictness/test_no_compat.py`
- `tests/test_architecture_baseline_docs.py`
- `autoloop/__init__.py`
- `autoloop/simple.py`
- `core/compiler.py`
- `workflow/__init__.py`
- active code/doc roots under `autoloop/`, `core/`, `runtime/`, `stdlib/`, `workflow/`, `tests/`, and `docs/`

Required changes:

- Expand the anti-regression scan to forbid active reintroduction of:
  - `RouteContract`
  - `route_contracts`
  - `route_required_artifacts`
  - `route contract`
  - `review_gate_contracts`
  - `publication_gate_contracts`
  - `contracts_path`
  - `contracts_path_repo_relative`
  - `BoardMutation`
  - `_install_simple_workflow_step_handler`
- Exclude the strictness test file itself or construct forbidden strings indirectly.
- Keep `contracts.py` allowed only as a filename-level spec/support concept.
- Run a targeted repo-wide grep across active code/doc roots for stale additive/compatibility/future-lowering phrases, then update the remaining active code comments/docstrings and docs to current greenfield wording.
- Update stale wording from additive/compatibility/future-lowering language to current greenfield wording, including active `core/` comments such as the compatibility wording in `core/compiler.py`.
- Keep `workflow/primitives.py` as a runtime primitive shim only; do not expand its exports.
- Ensure docs/examples import from `autoloop.simple` or `autoloop`, not `workflow.primitives`.

Validation targets:

- Strictness scan covers the maintained active tree only.
- Public docs and active code comments/docstrings no longer describe compatibility surfaces as active authoring APIs or future lowering plans.
- `workflow.primitives.__all__` remains limited to runtime primitives.

### Milestone 5: Full verification and rollback check

Commands:

- targeted `pytest` runs for touched suites first
- full `pytest`
- any existing repo-standard lint/type command if already present and cheap to run

Required checks:

- Retry-aware provider validation tests pass.
- Capability/catalog payload expectations pass after `contracts_path` removal.
- Stdlib export tests pass after the route-info rename.
- Strictness/doc tests pass with the new forbidden token set.

Rollback posture:

- If retry-aware validation introduces broad failures, revert only the new `Event` validation wiring while preserving test additions that define the intended contract.
- If payload removals break downstream expectations, keep the removal and fix the tests/callers; do not restore deprecated fields.

## Interface deltas

- New internal engine helper: `_validate_event(...)`.
- Optional internal shared helper: `_validate_route_payload(...)` if used for both `Outcome` and `Event` validation.
- Removed public API: `BoardMutation`.
- Removed public payload fields: `contracts_path`, `contracts_path_repo_relative`.
- Removed stdlib names/module: `stdlib.contracts`, `review_gate_contracts`, `publication_gate_contracts`.
- Added stdlib names/module: `stdlib.route_infos`, `review_gate_infos`, `publication_gate_infos`.

## Regression controls

- Keep all provider retry classification inside existing `ProviderExecutionError` handling so the retry loop, checkpointing, and feedback generation do not fork.
- Validate final events before PAUSE/FAIL checkpointing so invalid pause/fail states cannot persist.
- Preserve current provider artifact-validation metadata shape; event validation should align with that shape rather than introduce a second format.
- Treat hook-returned explicit `Event` objects as deterministic by default to avoid silently blaming provider output for workflow-code mistakes.
- Remove compatibility surfaces from tests and docs in the same pass as code deletions so anti-regression coverage becomes authoritative immediately.

## Risk register

- Risk: event validation added in the wrong stage could double-raise or bypass artifact validation.
  Mitigation: validate candidate and final events explicitly, then keep artifact validation after final-event normalization only.
- Risk: provider-attribution rules could accidentally retry deterministic hook/system bugs.
  Mitigation: keep attribution conservative and encode it in targeted tests for middleware, hook string overrides, and explicit hook events.
- Risk: `contracts_path` removal can leave stale JSON assertions across multiple suites.
  Mitigation: update shared payload builders first, then fix catalog/capability/CLI expectations together.
- Risk: stdlib rename can leave orphan imports in docs or tests.
  Mitigation: use repo-wide grep before and after edits, then let the strictness scan enforce the removal.
- Risk: deleting generated workflow-step helpers can leave dead imports or hidden fallback behavior.
  Mitigation: keep lowering assertions in simple-surface tests and verify compiled workflow steps have no system handler.

## Recommended execution order

1. Land the engine validation helper plus retry-aware tests.
2. Delete generated workflow-step handler residue and `BoardMutation`.
3. Rename stdlib route-info helpers and remove `contracts_path` from catalog/capability/CLI surfaces.
4. Tighten strictness/doc coverage and refresh stale wording.
5. Run targeted suites, then full `pytest`, then any existing repo-standard verification command if present.
