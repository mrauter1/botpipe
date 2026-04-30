# Intent Gap Report

## Original intent considered

- Remove redundant legacy names from the public and internal implementation, keeping only canonical names such as `FINISH`, `produce_verify_step`, `producer_prompt`, `verifier_prompt`, `writes`, `required_writes`, `Route`, `Workflow`, and Pydantic `State` / `Params`.
- Keep legacy support only where a real persisted-run migration requires it, and keep that support private and reader-side.
- Update docs, examples, topology/provider payloads, static graph output, tests, and strictness checks so removed names are absent outside explicit migration fixtures.

## Clarifications / superseding decisions

- The run kept the canonical `autoloop` root surface and canonical emitted runtime/topology payloads as the acceptance gate.
- Recorded implementation decisions explicitly narrowed strictness to the canonical public/runtime surface and left the low-level compatibility harness out of scope rather than fully removing it ([decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/below-is-the-revised-standalone-implementation-s-9b605d02/runs/run-20260429T212742Z-82f66970/decisions.txt:40)).
- Those decisions explain the shipped scope, but they do not amount to a later user clarification relaxing the original internal cleanup requirement.

## Implemented behavior

- `autoloop` root exports are canonical only ([autoloop/__init__.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/__init__.py:1)).
- Public docs now describe `autoloop.simple` / `autoloop` as the authoring surface and use canonical vocabulary such as `produce_verify_step` and `required_writes` ([docs/authoring.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/docs/authoring.md:5)).
- Emitted topology/static-graph payloads are canonical, and the targeted canonical verification lane passes: `112 passed, 14 warnings` for the strictness/docs/provider/topology/reference/parity suite.
- Persisted-run/session migration for legacy `"SUCCESS"` terminals and `"default"` global-session slot naming is implemented and tested, which is consistent with the original migration allowance.

## Unresolved gaps

- `autoloop.simple` still exposes non-canonical public symbols even though docs call it the active public authoring surface. It imports and re-exports `AfterHookResult`, `Checkpoint`, `ChildWorkflowResult`, `ResolvedArtifacts`, and `WorkflowStep` ([docs/authoring.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/docs/authoring.md:5), [autoloop/simple.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/simple.py:11), [autoloop/simple.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/simple.py:650)).
- The active internal kernel still preserves the removed legacy contract instead of confining it to private migration readers. `core` re-exports `Param`, `StateVar`, `SUCCESS`, `RouteInfo`, `AfterHookResult`, `LLMStep`, `PairStep`, and `SystemStep`, and keeps the dual-package alias shim ([core/__init__.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/__init__.py:10), [core/__init__.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/__init__.py:33), [core/__init__.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/__init__.py:51)).
- Route/validation cleanup is incomplete internally. `RouteInfo` and `required_outputs` still exist, `Route.to(...)` still accepts positional `*effects`, `SUCCESS` remains a primitive, and simple workflows are still lowered through `LLMStep` / `PairStep` / `SystemStep` plus `route_infos` / `required_outputs` handling ([core/routes.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/routes.py:35), [core/primitives.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/primitives.py:10), [core/validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/validation.py:18), [core/validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/validation.py:694), [core/validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/validation.py:1613)).
- Strictness/test migration does not meet the original breadth requirement. The main strictness scan deliberately excludes `core/`, `runtime/`, and all `tests/`, so remaining legacy names are not gated there ([tests/strictness/test_no_compat.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/strictness/test_no_compat.py:39), [tests/strictness/test_no_compat.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/strictness/test_no_compat.py:78)). Active non-migration suites still encode removed names, for example provider backend tests still guard against `route_infos` / `route_required_outputs` strings ([tests/runtime/test_provider_backends.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_provider_backends.py:256)), and large low-level suites still use `SUCCESS`, `RouteInfo`, `PairStep`, `SystemStep`, `produces`, and `required_outputs` outside explicit old-run fixtures ([tests/contract/test_engine_contracts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/contract/test_engine_contracts.py:26), [tests/unit/test_validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_validation.py:10)).
- Legacy handling still appears in active writer/runtime code paths, not only private persisted-run readers. Example: static-graph generation still canonicalizes `"SUCCESS"` targets inline ([runtime/static_graph.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/static_graph.py:282)), and stdlib compatibility helpers still expose `required_outputs` and `PairStep` / `produces` vocabulary ([stdlib/composition.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/stdlib/composition.py:30), [stdlib/steps.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/stdlib/steps.py:7)).

## Differences justified by later clarification or analysis

- Keeping reader-side migration for persisted `"SUCCESS"` terminals and legacy `"default"` session-slot payloads is justified by the original spec and by the recorded run decisions ([decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/below-is-the-revised-standalone-implementation-s-9b605d02/runs/run-20260429T212742Z-82f66970/decisions.txt:2), [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/below-is-the-revised-standalone-implementation-s-9b605d02/runs/run-20260429T212742Z-82f66970/decisions.txt:28)).
- Deferring item-scoped public state rather than shipping a half-working API is consistent with the request’s “complete-or-hidden” rule for item/step-item state.
- The repo-root package migration itself is not an intent gap; the request did not require keeping the deleted tracked mirror active.

## Recommended next run

- Finish the cleanup that was scoped out of this run:
  - make `autoloop.simple` export only the intended public authoring surface;
  - remove or quarantine legacy `core` symbols and dual import shims into explicit internal compatibility modules;
  - replace remaining internal `RouteInfo` / `SUCCESS` / `PairStep` / `LLMStep` / `SystemStep` / `produces` / `required_outputs` paths with canonical compiled/runtime names, leaving legacy support only in private persisted-run readers;
  - migrate or quarantine non-migration tests so strictness can scan active code/tests rather than excluding `core/`, `runtime/`, and `tests/`.
