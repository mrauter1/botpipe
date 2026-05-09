# Refactor Implementation Plan

## Objective
Implement the requested Botlane complexity refactors without adding compatibility shims. Keep public behavior, emitted policy artifacts, validation wording, checkpoint behavior, and workflow semantics unchanged unless a later authoritative clarification explicitly allows a break.

## Scope
- In scope: the ten hotspots from the request, sequenced so low-risk pure translators land before authoring/inventory reducers and before runtime lifecycle extraction.
- In scope: hotspot 9, `_capability_entry_from_resolved`, remains part of the requested refactor set but is explicitly conditional: only refactor it if adjacent work already opens `botlane/core/workflow_capabilities.py`; do not touch that file just for standalone readability churn.
- In scope: targeted test expansion where current coverage is indirect or does not lock exact output/error parity.
- Out of scope: feature work, policy semantics changes, checkpoint schema changes, workflow topology changes, CLI contract changes, and unrelated cleanup.
- Out of scope: direct edits to `build/lib/*` as refactor sources of truth. Treat `botlane/*` as authoritative unless a later packaging step explicitly requires mirroring generated artifacts.

## Non-Negotiable Invariants
- `CodexPolicyEmitter` and `ClaudePolicyEmitter` must preserve emitted payload values, unsupported/lossy/unsafe classifications, validation failures, and Claude CLI arg ordering.
- `_policy_layer_to_override` must preserve current public authoring rules, including dangerous-access inference and exact incompatibility failures.
- Placeholder validation must keep exact user-facing error wording and ambiguity behavior shared between authoring-time (`discovery.py`) and runtime-safe validation (`placeholders.py`).
- Artifact inventory must preserve current identity reuse, workflow-level ownership, producer rebind, and conflict diagnostics.
- Any conditional cleanup of `_capability_entry_from_resolved` must preserve `WorkflowCapabilityEntry` field shape, path/title/alias fallback resolution, session collection, and compiled route/artifact/step projection.
- `compiled_step_from_step_plan`, `render_branch_group_context`, `Engine.run_async`, and `describe_workflow_class` must remain behavior-preserving internal restructures only.

## Phase Plan

### Phase 1: Provider Policy Translators
Focus on the highest-payoff pure translators first.

- Refactor `botlane/runtime/providers/codex_policy.py` so `_build_config_payload` becomes a small coordinator over helper emitters and table-driven mode translations.
- Refactor `botlane/runtime/providers/claude_policy.py` so `_build_settings_payload` becomes a coordinator over helper emitters, with a private emission context carrying payload fragments, capability notes, CLI args, and effective-enforcement inputs.
- Refactor `botlane/policy.py::_policy_layer_to_override` into explicit authored-field copy, effective-mode resolution, compatibility validation, and section emission helpers.
- Keep helper scope local to each module; do not introduce cross-module abstraction just because Codex and Claude share broad shape.

Interfaces and structures:
- Private module-local translation maps for permission/sandbox mode conversion.
- Private value objects such as `EffectivePolicyModes` and emission context dataclasses.
- Private helper boundaries for model, permissions, sandbox/filesystem/network, env, and effective-report assembly.

Validation gates:
- Extend `tests/runtime/test_provider_policy_emitters.py` with matrix-style parity checks for permission modes, sandbox modes, network modes, dangerous bypass, unsupported/lossy/unsafe classification, and effective-enforcement fields.
- Extend `tests/unit/test_simple_policy.py` and/or `tests/unit/test_provider_policy.py` for `_policy_layer_to_override` combinations that currently rely on indirect coverage.

### Phase 2: Authoring Reducers And Presentation Builders
Refactor deterministic validators and builders while preserving exact outputs.

- Refactor `botlane/core/placeholders.py::_validate_simple_prompt_reference` into a small dispatcher plus root-specific validators.
- Keep `botlane/core/discovery.py::_validate_simple_prompt_reference` as a thin adapter onto the shared placeholder validator so authoring-time and runtime-safe validation remain aligned.
- Refactor `botlane/core/inventory.py::collect_artifact_inventory` by moving the nested `register` closure into a private builder with explicit identity/conflict/update methods.
- Refactor `botlane/core/plan_adapters.py::compiled_step_from_step_plan` into plan-type builders plus shared common/fallback helpers.
- Refactor `botlane/core/branch_groups/manifest.py::render_branch_group_context` into section renderers and simple list helpers without changing markdown content.

Interfaces and structures:
- Module-local validator registry for placeholder roots.
- Private inventory builder and mutable record dataclass.
- Module-local plan-builder registry plus common-kwargs/fallback helpers.
- Private section renderers for branch-group markdown.

Validation gates:
- Preserve exact placeholder wording covered by `tests/unit/test_placeholder_refs.py` and `tests/unit/test_simple_surface.py`.
- Add direct artifact-inventory tests where current coverage is indirect, using `tests/unit/test_validation.py` and `tests/unit/test_route_contracts.py` as anchors.
- Preserve plan round-trip parity in `tests/unit/test_step_plans.py`.
- Preserve branch-group markdown/output behavior in `tests/contract/test_branch_result_serialization.py`.

### Conditional Hotspot 9: Workflow Capability Entry
The request includes `_capability_entry_from_resolved` as a lower-priority readability cleanup, but only if the file changes anyway. Keep that condition explicit instead of silently dropping it.

- If Phases 1-3 do not otherwise open `botlane/core/workflow_capabilities.py`, leave `_capability_entry_from_resolved` deferred and make no standalone changes there.
- If adjacent capability/discovery work already opens that file, refactor `_capability_entry_from_resolved` locally by extracting path/metadata/session fallback helpers and keeping the `WorkflowCapabilityEntry(...)` assembly behavior unchanged.

Validation gates:
- If this conditional slice activates, add focused capability-inspection tests that lock catalog-entry fallbacks, inferred support-path lists, session projection, and emitted `WorkflowCapabilityEntry` field parity.

### Phase 3: Runtime Loop And Workflow Discovery
Only start after Phases 1 and 2 are passing, because these are the highest regression surfaces.

- Refactor `botlane/core/engine.py::Engine.run_async` into run-environment setup, resume/restore initialization, per-step context preparation, step execution, terminal handling, checkpointing, and fatal-notification helpers.
- Introduce a private run-loop state carrier only if it reduces parameter sprawl; do not create a new subsystem or service layer beyond what the class already uses.
- Refactor `botlane/core/discovery.py::describe_workflow_class` into namespace scan, simple-step lowering, graph resolution, default-session resolution, and final definition assembly helpers.
- Keep runtime semantics unchanged: step history, hook ordering, checkpoint writes, terminal notifications, resume behavior, and default entry/ordering rules must remain identical.

Interfaces and structures:
- Private `RunLoopState`-style dataclass if needed for loop-local mutable state.
- Private namespace-scan result dataclass for discovery.
- Private helper methods only; no public API or persisted data contract changes.

Validation gates:
- Preserve `tests/contract/test_async_engine_spine.py` and expand engine coverage around resume, `AWAIT_INPUT`, `FAIL`, `FINISH`, `goto`, max-step exhaustion, and terminal hook failure handling.
- Preserve compile/validation behavior exercised by `tests/unit/test_validation.py`, `tests/unit/test_simple_surface.py`, and discovery/compiler contract tests.

## Risk Register
- Provider payload drift: helper extraction may accidentally change unsupported/lossy/unsafe ordering or omit fields. Mitigation: exact payload/report assertions, not only semantic assertions.
- Placeholder wording drift: dispatcher extraction can subtly change surfaced errors. Mitigation: preserve shared validator entrypoint and use exact `match=` assertions.
- Artifact ownership drift: builder extraction can break rebind and shared-identity handling. Mitigation: add direct tests for workflow-level reuse, duplicate names, and qualified-name conflicts.
- Workflow capability entry drift: low-priority cleanup can change fallback resolution in `botlane/core/workflow_capabilities.py`, where direct test coverage is lighter. Mitigation: keep it conditional on adjacent file changes and add focused capability-inspection parity tests if activated.
- Runtime control drift: `run_async` extraction can reorder notifications or checkpoint writes. Mitigation: isolate helper boundaries around existing control flow and add parity tests before any cleanup.
- Discovery ordering drift: split scanning/lowering can alter step ordering or default entry resolution. Mitigation: preserve current sort/order inputs and validate with existing workflow compilation tests.

## Rollout And Rollback
- Land work phase-by-phase in request order; each phase must leave the tree green before starting the next.
- If a phase exposes unexpected parity drift, revert that phase’s internal helper extraction only and keep prior phases intact.
- Do not batch runtime-loop extraction with unrelated cleanup; Phase 3 must remain easy to revert independently.

## Implementation Notes
- Prefer small module-local helpers over shared generic frameworks.
- Reuse existing typed models and helper conventions already present in Botlane where they reduce duplication clearly.
- Add tests before or with each risky refactor slice when coverage is currently indirect.
