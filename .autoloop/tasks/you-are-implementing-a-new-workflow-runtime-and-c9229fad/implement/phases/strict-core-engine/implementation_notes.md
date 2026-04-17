# Implementation Notes

- Task ID: you-are-implementing-a-new-workflow-runtime-and-c9229fad
- Pair: implement
- Phase ID: strict-core-engine
- Phase Directory Key: strict-core-engine
- Phase Title: Strict Core Engine
- Scope: phase-local producer artifact

## Files Changed

- `autoloop_v3/__init__.py`
- `autoloop_v3/workflow/__init__.py`
- `autoloop_v3/workflow/errors.py`
- `autoloop_v3/workflow/primitives.py`
- `autoloop_v3/workflow/prompts.py`
- `autoloop_v3/workflow/artifacts.py`
- `autoloop_v3/workflow/steps.py`
- `autoloop_v3/workflow/context.py`
- `autoloop_v3/workflow/validation.py`
- `autoloop_v3/workflow/compiler.py`
- `autoloop_v3/workflow/engine.py`
- `autoloop_v3/workflow/compat.py`
- `autoloop_v3/workflow/providers/__init__.py`
- `autoloop_v3/workflow/providers/models.py`
- `autoloop_v3/workflow/providers/protocols.py`
- `autoloop_v3/workflow/providers/fake.py`
- `autoloop_v3/workflow/stores/__init__.py`
- `autoloop_v3/workflow/stores/protocols.py`
- `autoloop_v3/workflow/stores/memory.py`
- `autoloop_v3/tests/conftest.py`
- `autoloop_v3/tests/unit/test_primitives_and_stores.py`
- `autoloop_v3/tests/unit/test_validation.py`
- `autoloop_v3/tests/contract/test_engine_contracts.py`

## Symbols Touched

- Strict authoring surface: `Workflow`, `Artifact`, `PairStep`, `LLMStep`, `SystemStep`, `Session`, `SessionLifecycle`, `Context`, `Prompt`.
- Core primitives: `Event`, `Outcome`, `Verdict`, `Checkpoint`, `SUCCESS`, `PAUSE`, `FAIL`, `GLOBAL`, `ResolvedArtifacts`.
- Compiler/runtime internals: `WorkflowMeta`, `WorkflowDefinition`, `CompiledWorkflow`, `CompiledStep`, `Engine`, `RunResult`, `has_start_hook()`, `middleware_handler_name()`.
- Store/provider doubles: `InMemorySessionStore`, `InMemoryCheckpointStore`, `SessionBinding`, `SessionSnapshot`, `ScriptedLLMProvider`.

## Checklist Mapping

- `plan.md` milestone 2: implemented spec-compliant workflow primitives, prompts, artifacts, steps, context, validation, compiler, routing, and engine.
- `plan.md` milestone 2: implemented deterministic in-memory store and provider doubles for tests.
- `plan.md` milestone 2: added contract coverage for pair, llm, system, routing, middleware, pause/resume, answer injection, failure checkpointing, missing artifacts, and scoped sessions.
- Deferred by phase contract: loader-based legacy normalization, repo-root `workflow` shim, filesystem runtime stores, CLI harness, and workspace parity goldens.

## Assumptions

- Strict-core tests target direct imports from `autoloop_v3.workflow`; the repo-root `workflow` compatibility shim remains a later-phase deliverable because legacy loading is out of scope here.
- Session scope selection for step execution is represented by an active-scope table in the session store; `ctx.open_session(ref, scope=...)` both creates or reuses a binding and marks that scope active for later steps using the same slot.
- When a workflow declares a step named `start`, `outcome`, or `verdict`, the matching `on_*` symbol is treated as the step handler first and is not also activated as a lifecycle or middleware hook in the same strict-core workflow definition.

## Preserved Invariants

- State remains a Pydantic model passed immutably between steps; the engine never mutates workflow state in place.
- Routing is compiled and deterministic: step-local tag lookup first, then `GLOBAL`, else a runtime error.
- Checkpoints remain explicit snapshots, separate from logging or event concerns.
- Workspace-specific compatibility and filesystem/runtime integration remain outside the strict core.

## Intended Behavior Changes

- Introduced the new strict workflow package under `autoloop_v3/workflow` with definition-time validation and deterministic execution semantics.
- Fixed hook-selection precedence so pure workflows can safely use step names `start`, `outcome`, and `verdict` without colliding with lifecycle or middleware dispatch.
- No behavior in the legacy `autoloop/` package was modified.

## Known Non-Changes

- No legacy-safe module loader or workflow normalization logic beyond the no-op `compat.normalize_workflow()` stub.
- No filesystem-backed checkpoint or session stores.
- No `.autoloop` workspace runner, CLI, provider adapters, or parity execution of `autoloop_v1.py` or `Ralph_loop.py` in this phase.

## Expected Side Effects

- Pure v1.1 workflows can now compile and run in deterministic tests.
- Later phases can build compatibility and filesystem runtime features on top of the frozen compiled core instead of mixing drift handling into the executor.

## Validation Performed

- `pytest -q autoloop_v3/tests` (`33 passed`)
- `python - <<'PY' ... import autoloop_v3.workflow ... PY`

## Deduplication And Centralization Decisions

- Centralized definition discovery and validation in `workflow.validation`; the metaclass and explicit `get_workflow_definition()` reuse the same rule set.
- Centralized handler signature adaptation in `workflow.compiler` so the engine only executes normalized call sites.
- Centralized reserved hook-name precedence in `workflow.validation` and `workflow.compiler` instead of scattering special cases through the executor.
- Centralized scoped-session state in `workflow.stores.memory` via `SessionSnapshot.active_scopes` rather than leaking scope logic into state models or steps.
