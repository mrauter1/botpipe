# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: compiler-validation-normalization
- Phase Directory Key: compiler-validation-normalization
- Phase Title: Compiler And Validation Canonicalization
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` [`core/routes.py:23-174`, `core/validation.py:682-704`, `core/validation.py:838-860`]: The route surface is still centered on legacy names instead of the canonical `Route` model. `core.routes` still exports `RouteInfo`, accepts `required_outputs`, keeps the `Route.complete` alias, normalizes `SUCCESS`, and validation still builds `route_infos`/`RouteInfo` objects for lowered simple steps. That means request-relevant authoring and validation paths still accept the removed route metadata API, which violates the phase objective and AC-1/AC-2. Minimal fix: collapse route metadata into `Route` end-to-end in `core/routes.py` and the simple-lowering/validation path, and keep any old-name support only as a private migration reader instead of active authoring/validation entry points.

- IMP-002 `blocking` [`core/validation.py:681-819`, `core/context.py:174-240`, `core/engine.py:240-243`, `core/engine.py:2465-2503`]: The Pydantic state migration is only compile-time validation; runtime step/item state is still stored as plain dicts behind `MutableStateProxy`. `_normalize_simple_state_fields()` converts the declared `BaseModel` into descriptor-like field metadata, `_ensure_step_state_store()` materializes raw dict entries, and `ctx.step_state` / `ctx.item_state` / `ctx.step_item_state` expose mutable dict proxies rather than model instances. This breaks the requested semantics for model-backed state, bypasses model validation/coercion on mutation and resume, and leaves item/step-item state as unsuppressed incomplete public surfaces, so AC-3 is not met. Minimal fix: centralize step/item state storage around real Pydantic model instances plus `model_dump`/`model_validate` checkpointing, or suppress the item/step-item public context surface until that model-backed path exists.
