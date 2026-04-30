# Original intent considered

The request asked for the remaining post-canonicalization cleanup:

- trim `autoloop.simple` to the canonical authoring surface only
- remove legacy low-level contract names from active `core` modules, keeping compatibility only for real persisted-run readers
- finish internal route/runtime canonicalization, including removal of active `SUCCESS`, `route_infos`, `required_outputs`, and `produces` dependencies
- migrate active suites and strictness so banned legacy names fail outside explicit migration fixtures

# Clarifications / superseding decisions

- No later raw-log clarification changed the requested scope.
- The decisions ledger narrowed allowed retained compatibility to persisted-run/session/checkpoint readers only and said fixtures do not justify live compatibility behavior.
- The decisions ledger also treated `workflows/` as part of the maintained strictness surface.

# Implemented behavior

- `autoloop.simple` now exposes a narrow canonical surface and no longer exports `AfterHookResult`, `Checkpoint`, `ChildWorkflowResult`, `ResolvedArtifacts`, or `WorkflowStep` (`autoloop/simple.py`, `autoloop/__init__.py`).
- Active top-level `core` exports no longer include the removed public names such as `SUCCESS`, `RouteInfo`, `Param`, `StateVar`, `LLMStep`, `PairStep`, `SystemStep`, or `WorkflowStep` (`core/__init__.py:50-72`).
- Active route/runtime payload terminology is largely canonicalized: `Route.to(...)` is keyword-only for effects, and active scans outside explicit exclusions no longer show `SUCCESS`, `RouteInfo`, `route_infos`, or `required_outputs`.
- The run artifacts report passing targeted verification for strictness and canonical suites, and `./.venv/bin/pytest tests/strictness/test_no_compat.py -q` still passes in the final tree (`8 passed`).

# Unresolved gaps

- Active `core` implementation still depends on `produces`, which the request explicitly called out for removal from active modules and runtime/compiler/static-graph paths. Evidence:
  - `core/steps.py:105-135` stores `self.produces` on the base active step type.
  - `core/steps.py:160-211` still uses `produces`, `review_produces`, and `do_produces` on active producer/verifier paths.
  - `core/compiler.py:220-230` compiles writes from `step.produces`.
  - `core/validation.py:325-326`, `core/validation.py:692-775`, and `core/engine.py:2354-2359` still use `produces` in active lowering, validation, and runtime output persistence.
- Active non-migration suites still encode the legacy `produces` vocabulary instead of a canonical replacement:
  - `tests/unit/test_validation.py:236-309` and many later cases still build active workflows with `PromptStep(..., produces=...)`.
  - `tests/contract/test_engine_contracts.py:259-266` and many later cases still use `ProduceVerifyStep(..., produces=...)`.
  - `tests/runtime/test_compatibility_runtime.py:229-239` and `tests/runtime/test_compatibility_runtime.py:312-315` still author live in-memory workflows with `produces`, even though the decisions ledger says this suite should retain only persisted session/checkpoint compatibility coverage.
- Strictness does not currently enforce removal of `produces`, so the maintained-tree scanner is still too narrow for the request:
  - `tests/strictness/test_no_compat.py:167-188` bans `SUCCESS`, `RouteInfo`, `required_outputs`, and other legacy names, but does not ban `produces`.
  - The strictness suite passes in the final tree while the active source and active tests above still contain `produces`, so the acceptance criterion about failing on remaining banned names is not met.
- The dual package alias shim remains active in `core/__init__.py:32-47` even though an explicit bridge package now exists at `autoloop_v3/core/__init__.py:1-9`. The request asked to remove the shim if it was no longer strictly required, and no later clarification justified keeping both mechanisms.

# Differences justified by later clarification or analysis

- Keeping explicit compatibility exclusions for `core/_compat.py`, `tests/runtime/test_compatibility_runtime.py`, and the strictness test itself is consistent with the run decisions, but only if those files are truly compatibility-only. That justification does not cover the remaining live `produces` workflow declarations inside the excluded runtime compatibility suite.
- Retaining the explicit `autoloop_v3.core` bridge package is consistent with the recorded analysis that this checkout lacks a real maintained `autoloop_v3.core` source tree. The unresolved issue is the additional dynamic alias shim still left in `core/__init__.py`.

# Recommended next run

Follow up with a narrow cleanup pass that finishes the active `produces` migration and the remaining bridge cleanup:

- rename/remove `produces` and related live low-level vocabulary from active `core` authoring/runtime/compiler/validation/engine code paths in favor of canonical write/output terminology
- migrate active non-migration suites off `produces`, and quarantine any truly persisted-payload-only coverage explicitly
- extend strictness so active code/tests fail on remaining `produces` usage outside explicit migration fixtures
- remove the redundant `core.__init__` alias shim if the explicit `autoloop_v3.core` bridge remains the intended compatibility path
