# Original intent considered

The original request asked for two framework milestones.

- Milestone A: make provider-visible routes policy-aware, remove default provider `blocked`/`failed` routes, keep runtime/provider failures runtime-owned, and defer worklist/session/item validation to first use instead of compile time or run start.
- Milestone B: add narrow worklist effects, keep repairable validation standardized through `validation_step` / `ValidationResult`, reject ambiguous artifact ownership, allow late-bound prompt `item` / `worklist` context, and keep inspection/static-graph surfaces aligned with the new route policy.
- The acceptance criteria also explicitly required the listed tests to pass.

# Clarifications / superseding decisions

- The authoritative raw log records no later user clarification that changed intent; execution stayed anchored to the original request.
- Later run decisions narrowed implementation shape without changing requested behavior:
  - reuse existing in-tree foundations such as `RuntimeInteractionPolicy`, `ControlRoutes`, `Context.ensure_selection`, `WorklistEffect`, and `ValidationResult` instead of creating parallel abstractions;
  - centralize worklist-source `ensure()` in the shared load path so first use, restore, and refresh obey the same source policy;
  - keep lazy-selection observability additive by extending the existing `worklist_selection_resolved` event payload instead of renaming legacy payload fields.

# Implemented behavior

- Route policy and runtime-owned failure behavior are implemented in `autoloop/core/discovery.py`, `autoloop/core/compiler.py`, `autoloop/core/engine_collaborators.py`, `autoloop/core/engine.py`, and `autoloop/runtime/runner.py`.
  - Default provider `question` visibility is policy-gated by `RuntimeInteractionPolicy`.
  - Default provider `blocked` and `failed` routes are no longer injected.
  - Explicit authored `blocked` / `failed` routes remain legal and no longer require a non-empty `reason`.
  - Evidence: `tests/unit/test_validation.py` asserts provider-visible interactive vs full-auto routes, and `tests/contract/test_engine_contracts.py` covers `test_full_auto_hides_default_question_route_from_provider_contract`, `test_explicit_blocked_and_failed_routes_do_not_require_reason_field`, `test_provider_question_route_is_illegal_in_full_auto_mode`, and strict `question` payload validation.

- Lazy worklist materialization and lazy work-item session binding are implemented in `autoloop/core/context.py`, `autoloop/core/engine.py`, `autoloop/core/worklists.py`, and `autoloop/core/sessions.py`.
  - `Context.selection()` and `Context.current()` now resolve through `ensure_selection()`.
  - Scoped-step execution ensures the relevant worklist before item-state, artifact-path, and session-sensitive logic runs.
  - Worklist source `ensure()` is shared across first use, restore, and refresh.
  - Work-item continuity derives keys lazily from the current item and fails clearly when no current item exists.
  - Evidence: `tests/contract/test_engine_contracts.py` covers explicit child-route mapping failures, first-use lazy materialization, resume/refresh source `ensure()` behavior, sparse checkpoint restore, and work-item session continuity.

- Milestone B authoring ergonomics are implemented.
  - `autoloop/core/effects.py`, `autoloop/core/routes.py`, and `autoloop/core/engine_collaborators.py` support direct `WorklistEffect` returns plus additive route/effect helper sugar.
  - `autoloop/simple.py` and `autoloop/core/validation_helpers.py` expose `validation_step`, `ValidationResult`, and default repair-feedback rendering.
  - `autoloop/core/engine.py` and `autoloop/core/operations.py` now attach step/worklist context to runtime prompt placeholder failures.
  - `autoloop/core/inventory.py` rejects workflow-level vs produced-artifact ownership ambiguity, including same-public-name collisions.
  - Evidence: `tests/unit/test_simple_surface.py`, `tests/unit/test_primitives_and_stores.py`, `tests/unit/test_validation.py`, and `tests/contract/test_engine_contracts.py` contain the new effect, validation, prompt, and ownership assertions, including the operation-path `llm(...)` prompt test.

# Unresolved gaps

- Material: acceptance criterion 18 is still not evidenced in this run. The run artifacts repeatedly record that only syntax compilation and static audit were possible because the environment lacked `pytest` and runtime dependencies. The current environment still reproduces that limitation:
  - `python3 -m pytest --version` fails with `No module named pytest`.
  - `python3 -c "import pydantic"` fails with `ModuleNotFoundError: No module named 'pydantic'`.
  The requested contract/unit suites were authored and audited, but they were not observed passing in this run.

- Minor: `autoloop/core/inventory.py` still tells authors to use the managed-artifact role "once implemented", while `autoloop/core/artifacts.py` already exposes `Artifact.managed(...)` / `role="managed"`. This is diagnostic wording drift, not a behavioral contract failure.

# Differences justified by later clarification or analysis

- The lazy-selection event kept the existing `worklist_selection_resolved` payload shape and added fields such as `lazy`, `source`, and `current_index` instead of renaming established keys. The run-local analysis and tests explicitly treated this as compatibility-preserving observability, not as a request to break existing consumers.

- The specification suggested introducing several APIs, but the repository already contained usable versions of `RuntimeInteractionPolicy`, `ControlRoutes`, `Context.ensure_selection`, `WorklistEffect`, and `ValidationResult`. Later run decisions explicitly chose in-place reconciliation over creating duplicate abstractions, which preserved user intent while reducing risk.

# Recommended next run

Use a runnable project Python environment, install or activate the missing test dependencies, then execute the targeted suites for this change:

- `tests/contract/test_engine_contracts.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_primitives_and_stores.py`
- `tests/unit/test_validation.py`
- any affected runtime/static-graph suites that cover provider-visible route metadata

Fix any failures revealed by that run, and refresh the stale managed-artifact wording in `autoloop/core/inventory.py` so the diagnostic references the current public surface.
