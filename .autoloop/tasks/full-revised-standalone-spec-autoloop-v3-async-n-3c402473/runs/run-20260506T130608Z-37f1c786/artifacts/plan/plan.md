# Async-Native Provider And Branch-Group Rewrite Plan

## Scope anchors
- Treat provider execution, provider transports, and branch-group execution as greenfield internals.
- Preserve the public non-parallel authoring surface and ordinary runtime entrypoints; any remaining sync runtime calls must be thin outer shells over async internals.
- Additive branch-group APIs stay `parallel(...)`, `fan_out(...)`, `FanIn.results()`, and `FanIn.context()`.
- Do not keep sync-provider compatibility, async-capability probes, thread-backed fallbacks, or dual sync/async execution families.
- Preserve exported sequential `llm(...)` and `classify(...)` helpers unless a later authoritative clarification explicitly permits breaking them; branch-group operation steps remain rejected in v1.

## Repository findings that drive the plan
- `autoloop/core/engine.py` still owns the only top-level run loop and duplicates sync provider execution paths that overlap with async logic in `autoloop/core/engine_collaborators.py`.
- `autoloop/core/providers/protocols.py` still defines both sync and async provider/transport protocols plus `supports_async_*` probing helpers.
- `autoloop/core/providers/rendered.py` still exposes sync methods, async `_async` methods, and a sync bridge helper.
- `autoloop/runtime/providers/codex.py` and `autoloop/runtime/providers/claude.py` still ship sync `run_turn(...)` transport execution via `subprocess.run(...)` alongside async variants.
- `autoloop/core/providers/fake.py` is still sync-first with async wrappers.
- `autoloop/core/branch_groups/runtime.py` still probes provider async support at runtime and owns scheduling directly; `autoloop/core/branch_groups/sessions.py` still falls back to parent active sessions on some lookups.
- Branch-group compile cache is already bypassed in `autoloop/core/compiler.py`; static-graph payloads are already additive in `autoloop/runtime/static_graph.py`.
- Existing contract/unit/runtime tests still encode deprecated `_async` provider methods and sync transport methods, so test migration is part of the implementation work, not a follow-up.

## Target interfaces and ownership

```python
class LLMProvider(Protocol):
    async def run_llm(self, request: LLMRequest) -> OutcomeResponse: ...
    async def run_producer(self, request: ProducerRequest) -> ProducerResponse: ...
    async def run_verifier(self, request: VerifierRequest) -> OutcomeResponse: ...

class ProviderTransport(Protocol):
    async def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult: ...
```

```python
class Engine:
    async def run_async(...) -> RunResult: ...
    async def resume_async(...) -> RunResult: ...
    def run(...): ...
    def resume(...): ...
```

```python
class StepDispatcher:
    async def execute(..., route_mode: Literal["finalize", "capture"] = "finalize") -> StepExecutionResult: ...
    def execute(..., route_mode: Literal["finalize", "capture"] = "finalize") -> StepExecutionResult: ...
```

- `engine.py` remains the workflow cursor and wrapper owner only.
- `engine_collaborators.py` becomes the single source of truth for provider-backed step execution and capture-mode behavior.
- `branch_groups/runtime.py` orchestrates composite execution only; launch/cancel scheduling logic should move into `branch_groups/scheduler.py` if extraction is needed to keep ownership clear.
- `runtime/static_graph.py` may keep the outer payload assembly, but branch-group-specific nested payload helpers should move to `autoloop/core/branch_groups/static_graph.py` if current graph logic becomes scattered.
- `compiler.py` keeps the branch-group compile-cache bypass in v1 unless a full branch-group cache key lands with matching tests.

## Milestones

### M1. Async engine spine
- Add `Engine.run_async(...)` and `Engine.resume_async(...)` as the single execution core.
- Convert `Engine.run(...)` and `Engine.resume(...)` into `asyncio.run(...)` shells that reject active-event-loop use with a clear error.
- Move provider-backed execution ownership out of `engine.py` sync methods and into `StepDispatcher.execute_async(...)`.
- Keep synchronous Python steps and hooks in the event loop as the explicit v1 limitation.

### M2. Provider contract cutover
- Replace dual provider/transport protocols with the async-only contracts above.
- Delete `AsyncLLMProvider`, `AsyncProviderTransport`, `supports_async_llm_provider(...)`, and `supports_async_provider_transport(...)`.
- Make provider construction validate coroutine-callable methods/transport entrypoints so invalid providers fail before runtime branch execution.
- Rework `autoloop/core/operations.py` so exported sequential operation helpers do not require sync provider protocol methods; do not expand operation branch support.

### M3. Async rendered provider and built-in transports
- Make `RenderedLLMProvider` async-only and remove sync provider methods, `_async` methods, and sync bridge helpers.
- Convert Codex and Claude transports to async-only `run_turn(...)` using `asyncio.create_subprocess_exec(...)`, async stdin/stdout/stderr, and explicit cancellation termination/kill handling.
- Keep transport parsing semantics equivalent to current Codex/Claude behavior.
- Ensure backend builders return validated async-native providers only; remove or reduce compatibility wrappers so they do not reintroduce sync execution paths.

### M4. Branch-group runtime and session refactor
- Remove runtime async-support probing; branch groups simply await the async provider contract.
- Extract scheduling/cancellation into a focused async branch scheduler if needed, using only `asyncio.create_task(...)`, `asyncio.Semaphore`, and `task.cancel()`.
- Tighten branch-local session overlays so fresh branch sessions are execution-local, keyed by branch identity, start with `session_id=None`, and never activate parent provider sessions.
- Preserve shared `StateCell`, shared `ctx.values`, route capture semantics, manifest order, and the rule that branch destinations are captured and never followed.

### M5. Compiler, discovery, artifacts, and graph alignment
- Keep `simple.py` public exports stable for `parallel`, `fan_out`, and `FanIn`.
- Align branch-group validation with the spec: path-safe names, exact placeholder-root checks, fresh-session enforcement, fan-in helper placement, child-workflow/scoped-step rejection, and operation-branch rejection.
- Keep templated artifact path rooting consistent with normal step-owned artifacts and ensure branch evidence stays under `{workflow_folder}/_branch_groups/...`.
- Preserve additive static-graph/topology payloads while updating their internal ownership if branch-group-specific helpers need extraction.
- Leave compile-cache behavior as bypass for branch-group workflows in v1 unless a complete key update is implemented with tests.

### M6. Test and strictness hardening
- Replace tests that currently assert deprecated `_async` provider surfaces with async-only protocol/transport assertions.
- Expand strictness coverage to fail on sync provider methods, sync transport methods, provider async wrappers that call sync code, runtime async-support probes, and forbidden thread-backed primitives.
- Update runtime provider tests to patch only async subprocess execution in transports.
- Verify branch-group runtime, compile-time validation, provider behavior, static graph, and sequential runtime parity against the new merge gate.

## Compatibility and intentional behavior notes
- Public non-parallel authoring APIs remain stable: `Workflow`, `step(...)`, `llm(...)`, `produce_verify_step(...)`, `python_step(...)`, `workflow_step(...)`, `Session`, `Continuity`, `Route`, `Event`, `Outcome`, artifact helpers, route/hook/worklist declarations, CLI shape, and normal runtime runner usage.
- `Engine.run(...)` and CLI callers remain available, but they become sync wrappers over async internals only.
- Calling a sync runtime wrapper from an already running event loop becomes a clear failure instead of silently bridging to sync provider execution.
- Branch-group behavior continues to be additive only; no implicit parallelism is introduced from reads/writes/routes/worklists.
- Operation branch steps remain rejected in v1; preserving exported sequential operation helpers is a compatibility obligation, not permission to admit them into branch groups.

## Regression controls
- Keep one provider-backed step execution source of truth in async collaborators; do not keep duplicate sync and async provider logic after the cutover.
- Fail invalid providers/transports at construction time, not after branch scheduling starts.
- Keep fan-in execution blocked if `results.json` or `context.md` writing fails.
- Keep branch route `on_taken` hooks disabled in capture mode and fan-in finalization occurring exactly once at the composite level.
- Preserve declaration-order manifest output independent of completion order.
- Keep compile-cache bypass for branch-group workflows until a complete branch-group cache key is proven by tests.

## Validation matrix
- Contract tests: async step dispatcher, branch-group runtime, engine entrypoint active-loop failures, provider protocol shape.
- Unit tests: rendered provider, fake provider, branch placeholder/fan-in helper validation, session key behavior, manifest/context rendering.
- Runtime tests: Codex/Claude transport subprocess execution and cancellation, static graph/topology payloads, runner/CLI parity, branch evidence paths under workflow folders.
- Strictness tests: forbidden thread-backed primitives, forbidden sync provider/transport surfaces, forbidden async-support probes, forbidden sync transport execution in built-in transports.

## Risk register
- R1. Public `llm(...)`/`classify(...)` helpers currently depend on sync `run_operation(...)`.
  Mitigation: treat them as compatibility-sensitive and migrate their internals during the provider cutover instead of silently breaking them.
- R2. Duplicated sync logic in `engine.py` and async logic in `engine_collaborators.py` can drift during the rewrite.
  Mitigation: make async collaborators authoritative early and delete duplicated sync provider execution code rather than maintaining both.
- R3. Provider subprocess cancellation can leak CLI processes or produce partial stderr-only failures.
  Mitigation: centralize async subprocess termination/kill behavior and cover it with provider transport tests.
- R4. Branch session overlays can leak parent active bindings or synthesize incorrect provider-session evidence.
  Mitigation: constrain branch fresh-key generation, forbid parent fallback for provider-backed fresh lookups, and assert first-turn `session_id=None` plus persisted returned ids.
- R5. Manifest/context/static-graph payloads can drift from the requested schema during refactors.
  Mitigation: keep payload helpers centralized and cover them with deterministic manifest/context/static-graph tests.

## Rollout and rollback
- Land the rewrite in milestone order so the async engine spine exists before provider protocol removal and before transport conversion.
- Do not merge a partial provider cutover that leaves both sync and async provider method families active.
- If a phase destabilizes sequential runtime behavior, roll back the full phase rather than reintroducing sync compatibility helpers inside providers or branch-group runtime.
