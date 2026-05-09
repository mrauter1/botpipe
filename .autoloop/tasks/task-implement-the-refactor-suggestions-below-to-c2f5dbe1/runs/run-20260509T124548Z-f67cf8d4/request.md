Task: Implement the refactor suggestions below to reduce complexity and improve maintanability and readability. This is a greenfield project, do not keep compatibility code.

## Executive assessment

The highest-complexity Botlane functions mostly fall into four categories:

1. **Provider-policy emitters**: many independent mapping rules from Botlane policy to Codex/Claude config.
2. **Authoring/validation reducers**: many field-specific validations and error messages.
3. **Runtime orchestration**: one large state-machine loop in `Engine.run_async`.
4. **Presentation/serialization builders**: long functions building text or dataclass payloads.

The good news: most of this is **accidental per-function complexity**, not deep algorithmic complexity. It can be reduced by extracting rule tables, builders, small validators, and state-machine phases while preserving behavior. Botlane already introduced stronger typed internal models, such as branch-group result dataclasses and execution-frame abstractions, so the refactors below fit the current direction. 

Static report used: [botlane_autoloop_static_report.json](sandbox:/mnt/data/botlane_autoloop_static_report.json)

---

## Priority hotspot table

| Priority | Function                                         |      CC |       LOC | Main driver                                                    | Recommended target                  |
| -------: | ------------------------------------------------ | ------: | --------: | -------------------------------------------------------------- | ----------------------------------- |
|        1 | `ClaudePolicyEmitter._build_settings_payload`    |      81 |       190 | Policy-to-provider mapping, many independent conditions        | Main function CC ≤ 10; helpers ≤ 15 |
|        2 | `_policy_layer_to_override`                      |      56 |       136 | DSL normalization plus cross-field validation                  | CC ≤ 12                             |
|        3 | `collect_artifact_inventory` / nested `register` | 55 / 41 | 146 / 108 | Ownership, conflict detection, record mutation in one closure  | Outer CC ≤ 8; builder methods ≤ 12  |
|        4 | `_validate_simple_prompt_reference`              |      46 |       122 | Placeholder-root dispatch encoded as if-chain                  | CC ≤ 8                              |
|        5 | `CodexPolicyEmitter._build_config_payload`       |      46 |       109 | Same pattern as Claude emitter                                 | CC ≤ 10                             |
|        6 | `render_branch_group_context`                    |      45 |       132 | Markdown rendering sections in one function                    | CC ≤ 8                              |
|        7 | `Engine.run_async`                               |      40 |       526 | Run-loop state machine, checkpointing, terminal handling       | Main loop CC ≤ 12                   |
|        8 | `compiled_step_from_step_plan`                   |      39 |       196 | Type dispatch and repeated field construction                  | CC ≤ 8                              |
|        9 | `_capability_entry_from_resolved`                |      38 |        98 | Large dataclass constructor with inline fallbacks              | Defer; not high-risk                |
|       10 | `describe_workflow_class`                        |      37 |       156 | Namespace scan, lowering, validation, ordering in one function | CC ≤ 12–15                          |

---

## 1. `ClaudePolicyEmitter._build_settings_payload`

**Problem:** This function performs at least seven responsibilities: base payload setup, model emission, instruction/telemetry incompatibility reporting, permission mode translation, dangerous-bypass validation, sandbox translation, filesystem rule emission, network rule emission, env emission, and effective-enforcement reporting.

**Refactor shape:**

```python
@dataclass
class ClaudeEmissionContext:
    payload: dict[str, Any]
    unsupported: list[str]
    lossy: list[str]
    unsafe: list[str]
    cli_args: list[str]
    permission_allow: list[str]
    permission_ask: list[str]
    permission_deny: list[str]
    sandbox_payload: dict[str, Any]
    filesystem_payload: dict[str, Any]
    network_payload: dict[str, Any]
```

Then make the current method a coordinator:

```python
def _build_settings_payload(self, policy, *, workspace_root):
    ctx = _init_claude_emission(policy)
    _emit_claude_model(ctx, policy.model)
    _emit_claude_instruction_and_telemetry_notes(ctx, policy)
    _emit_claude_permissions(ctx, policy)
    sandbox_state = _emit_claude_sandbox(ctx, policy, self._capabilities)
    filesystem_state = _emit_claude_filesystem(ctx, policy, workspace_root, self._capabilities)
    network_state = _emit_claude_network(ctx, policy, self._capabilities)
    _emit_claude_env(ctx, policy.env)
    effective = _claude_effective_report(policy, filesystem_state, network_state, self._capabilities)
    return ctx.payload, ctx.cli_args, ctx.unsupported, ctx.lossy, ctx.unsafe, effective
```

**Use mapping tables for simple mode translation:**

```python
CLAUDE_PERMISSION_MODES = {
    "ask": "default",
    "auto_edit": "acceptEdits",
    "full_auto_sandboxed": "auto",
    "deny_all": "dontAsk",
}
```

Only `full_auto_unsandboxed` needs special-case validation. That alone removes much of the `if/elif` chain.

**Expected result:** Max function CC drops from 81 to roughly 10–12. Aggregate CC may remain similar, but each rule cluster becomes independently testable.

---

## 2. `_policy_layer_to_override`

**Problem:** It combines three different phases:

1. Copy authored fields into structured payload sections.
2. Infer effective sandbox/network modes.
3. Validate incompatible combinations.

Those phases should be separate.

**Refactor shape:**

```python
def _policy_layer_to_override(policy: Policy) -> ProviderPolicyOverride:
    authored = policy._authored
    payload: dict[str, object] = {}

    _emit_model_override(payload, authored)

    effective = _resolve_policy_effects(authored)
    _emit_permission_override(payload, authored, effective)
    _emit_sandbox_override(payload, authored, effective)
    _emit_filesystem_override(payload, authored, effective)
    _emit_network_override(payload, authored, effective)

    return ProviderPolicyOverride.model_validate(payload)
```

Use small value objects:

```python
@dataclass(frozen=True)
class EffectivePolicyModes:
    sandbox_mode: str | None
    permission_mode: str | None
    network_mode: str | None
    dangerous_access: bool
```

Use mapping tables for direct field copies:

```python
_MODEL_FIELD_MAP = {
    "model": ("model", "default"),
    "provider": ("model", "provider"),
    "base_url": ("model", "base_url"),
    "effort": ("model", "effort"),
    "verbosity": ("model", "verbosity"),
    "reasoning_summary": ("model", "reasoning_summary"),
    "model_overrides": ("model", "overrides"),
}
```

**Expected result:** CC drops from 56 to around 10–12. More importantly, policy inference becomes testable without constructing a full override payload.

---

## 3. `collect_artifact_inventory` and nested `register`

**Problem:** The nested `register` closure is doing too much: name binding, owner binding, workflow-level conflict checks, qualified-name conflict checks, drift detection, producer-step registration, and record serialization.

**Refactor into a builder object:**

```python
@dataclass
class MutableArtifactRecord:
    artifact: Artifact
    name: str
    qualified_name: str
    owner_step: str | None
    workflow_level: bool = False
    producer_steps: list[str] = field(default_factory=list)


class ArtifactInventoryBuilder:
    def __init__(self, definition: Any) -> None: ...

    def register_workflow_artifact(self, name: str, artifact: Artifact) -> None: ...
    def register_step_artifact(self, step_name: str, name: str, artifact: Artifact) -> None: ...
    def register_log_artifact(self, fallback_name: str, artifact: Artifact) -> None: ...
    def build(self) -> dict[str, ArtifactInventoryRecord]: ...
```

Then split the current `register` logic into private methods:

```python
def _bind_artifact_identity(...)
def _check_reserved_name(...)
def _check_workflow_name_conflict(...)
def _check_qualified_name_conflict(...)
def _upsert_record(...)
def _record_producer_step(...)
```

**Expected result:** `collect_artifact_inventory` becomes a simple traversal with CC ≤ 8. The most complex builder method should stay below CC 12. This is a high-value refactor because artifact ownership errors are correctness-critical.

---

## 4. `_validate_simple_prompt_reference`

**Problem:** It is a large dispatcher over placeholder roots (`params`, `self`, `state`, `input`, `run`, `workflow`, `item`, `worklist`, `artifacts`, `step`, and step names), with embedded validation and error construction.

**Refactor shape:**

```python
_SIMPLE_ROOT_VALIDATORS = {
    "params": _validate_params_ref,
    "self": _validate_self_ref,
    "state": _validate_state_ref,
    "input": _validate_input_ref,
    "run": _validate_run_ref,
    "workflow": _validate_workflow_ref,
    "item": _validate_item_root_ref,
    "worklist": _validate_worklist_root_ref,
}
```

Then:

```python
def _validate_simple_prompt_reference(ref, *, surface, symbols):
    if _validate_branch_or_fan_in_ref(ref, surface, symbols):
        return None
    if ref.raw in _SPECIAL_ERRORS:
        raise WorkflowValidationError(_SPECIAL_ERRORS[ref.raw](surface))

    if ref.root == "ctx":
        return _validate_ctx_prompt_reference(ref, surface=surface, symbols=symbols)

    parts = _ref_parts(ref)
    if len(parts) == 1:
        return _validate_bare_reference(ref, surface=surface, symbols=symbols)

    validator = _SIMPLE_ROOT_VALIDATORS.get(parts[0])
    if validator is not None:
        return validator(ref, parts, surface=surface, symbols=symbols)

    return _validate_step_output_reference(ref, parts, surface=surface, symbols=symbols)
```

**Expected result:** The dispatcher drops from CC 46 to approximately 6–8. Exact error-message tests are essential because this function defines authoring UX.

---

## 5. `CodexPolicyEmitter._build_config_payload`

This has the same structural issue as the Claude emitter, but less severe.

**Refactor shape:**

```python
def _build_config_payload(self, policy):
    ctx = _init_codex_emission(policy)
    _emit_codex_model(ctx, policy.model)
    sandbox_mode = _emit_codex_permission_and_sandbox(ctx, policy)
    _emit_codex_workspace(ctx, policy, sandbox_mode)
    _emit_codex_network(ctx, policy, sandbox_mode)
    _emit_codex_unsupported_sections(ctx, policy)
    ctx.payload["shell_environment_policy"] = self._shell_environment_policy(...)
    return ctx.payload, ctx.unsupported, ctx.lossy, ctx.unsafe
```

Use tables:

```python
CODEX_PERMISSION_MODES = {
    "ask": "on-request",
    "full_auto_sandboxed": "never",
    "full_auto_unsandboxed": "never",
}

CODEX_SANDBOX_MODES = {
    "read_only": "read-only",
    "workspace_write": "workspace-write",
    "danger_full_access": "danger-full-access",
}
```

**Expected result:** CC 46 → roughly 8–10.

---

## 6. `render_branch_group_context`

**Problem:** It is presentation code with repeated “append section if items exist else append none” patterns. It is not algorithmically risky, but it inflates complexity.

**Refactor into section renderers:**

```python
def render_branch_group_context(manifest):
    branches = [_branch_payload(branch) for branch in manifest.get("branches", [])]
    sections = [
        _render_branch_group_header(manifest, branches),
        _render_completion_summary(branches),
        _render_route_summary(branches),
        _render_failure_summary(branches),
        _render_needs_input_summary(branches),
        _render_cancellation_summary(branches),
        *(_render_branch_detail(branch) for branch in branches),
    ]
    return "\n".join(_flatten_sections(sections)) + "\n"
```

Add a generic helper:

```python
def _render_list_or_none(lines, items, render_item):
    if not items:
        lines.append("- None.")
        return
    for item in items:
        lines.extend(render_item(item))
```

**Expected result:** CC 45 → around 5–8. This is safe and easy, but lower priority than policy/inventory/placeholder logic.

---

## 7. `Engine.run_async`

**Problem:** This is a runtime state machine in one method: run setup, resume restoration, context construction, per-step execution, hook notifications, checkpointing, terminal handling, and fatal handling.

**Refactor carefully.** This is high-risk code and should be done after policy/placeholder/inventory refactors.

Introduce a mutable run-loop state:

```python
@dataclass
class RunLoopState:
    state: BaseModel
    current_step_name: str
    values: dict[str, Any]
    selections: dict[str, Selection[Any]]
    selection_snapshots: dict[str, SelectionSnapshot]
    step_states: dict[str, BaseModel | dict[str, Any]]
    item_states: dict[str, BaseModel | dict[str, Any]]
    step_item_states: dict[str, dict[str, BaseModel | dict[str, Any]]]
    pending_handoffs: tuple[PendingHandoff, ...]
    current_answer: str | None = None
    current_input_response: Any | None = None
```

Then split:

```python
async def run_async(...):
    env = self._prepare_run_environment(...)
    loop = self._restore_or_initialize_loop_state(env, resume=resume, ...)
    try:
        return await self._run_loop(env, loop, max_steps=max_steps)
    finally:
        self.provider_policy_resolver = env.previous_provider_policy_resolver
```

Within `_run_loop`:

```python
for _ in range(max_steps):
    step_ctx = self._prepare_step_context(env, loop)
    step_result = await self._execute_step_with_notifications(env, loop, step_ctx)
    terminal = self._handle_step_result(env, loop, step_ctx, step_result)
    if terminal is not None:
        return terminal
```

Terminal handling should become:

```python
def _finish_terminal(...)
def _await_input_terminal(...)
def _fail_terminal(...)
def _goto_nonterminal(...)
```

**Expected result:** `Engine.run_async` CC 40 → around 10–12. The total class complexity remains, but the runtime loop becomes inspectable and much easier to debug.

---

## 8. `compiled_step_from_step_plan`

**Problem:** This is type dispatch plus repeated `CompiledStep(...)` construction. It has repeated fallback expressions like “use original compiled value else derive from IO”.

**Refactor to builder registry:**

```python
_PLAN_BUILDERS = {
    PromptStepPlan: _compiled_prompt_step_from_plan,
    ProduceVerifyStepPlan: _compiled_produce_verify_step_from_plan,
    PythonStepPlan: _compiled_python_step_from_plan,
    ChildWorkflowStepPlan: _compiled_child_workflow_step_from_plan,
    BranchGroupStepPlan: _compiled_branch_group_step_from_plan,
}
```

Then:

```python
def compiled_step_from_step_plan(*args, **kwargs):
    plan, routes = _parse_compiled_step_from_step_plan_args(args, kwargs)
    common = _compiled_step_common_kwargs(plan, routes)
    original = _compiled_step_parity(plan)
    return _builder_for_plan(plan)(plan, common, original)
```

Extract fallback helpers:

```python
def _producer_reads(original, io):
    return original.producer_reads if original is not None else _compiled_reads_from_step_io(io)
```

**Expected result:** CC 39 → approximately 5–8.

---

## 9. `_capability_entry_from_resolved`

This one is lower priority despite CC 38 because the function has **max nesting 1** and is mostly a large dataclass constructor with inline fallback expressions. It is not a control-flow smell as much as a readability smell.

**Refactor only if this file changes anyway:**

```python
paths = _resolve_capability_paths(reference, catalog_entry, source_path)
metadata = _resolve_capability_metadata(reference, catalog_entry, source_path)
sessions = _compiled_non_default_sessions(compiled)
return WorkflowCapabilityEntry(..., **paths, **metadata, sessions=sessions, ...)
```

**Expected result:** CC 38 → about 10–15, but this should not be a first pass.

---

## 10. `describe_workflow_class`

**Problem:** This function does namespace scanning, simple-declaration lowering, transition lowering, entry resolution, step ordering, session defaulting, and `WorkflowDefinition` construction.

**Refactor shape:**

```python
def describe_workflow_class(workflow_cls):
    _validate_simple_authoring_models(workflow_cls)
    base = _discover_workflow_base(workflow_cls)
    scan = _scan_workflow_namespace(workflow_cls)
    lowered = _lower_discovered_simple_steps(workflow_cls, base, scan)
    graph = _resolve_workflow_graph(workflow_cls, scan, lowered)
    sessions = _resolve_default_session(workflow_cls, scan.sessions_by_name)
    return _build_workflow_definition(workflow_cls, base, scan, lowered, graph, sessions)
```

Use a scan result dataclass:

```python
@dataclass
class WorkflowNamespaceScan:
    workflow_artifacts: dict[str, Artifact]
    sessions_by_name: dict[str, Session]
    worklists_by_name: dict[str, Worklist[Any]]
    steps: list[Step]
    steps_by_name: dict[str, Step]
    step_order: dict[int, int]
    simple_seeds: list[_SimpleStepSeed]
```

**Expected result:** CC 37 → around 12–15. This is valuable, but less urgent than policy/inventory/placeholder changes.

---

## Recommended refactor sequence

**Phase 1: Low-risk, high-payoff**

1. `CodexPolicyEmitter._build_config_payload`
2. `ClaudePolicyEmitter._build_settings_payload`
3. `_policy_layer_to_override`
4. `_validate_simple_prompt_reference`

These are mostly pure functions or deterministic translators. They are ideal for golden tests.

**Phase 2: Medium-risk core cleanup**
5. `collect_artifact_inventory`
6. `compiled_step_from_step_plan`
7. `render_branch_group_context`

These need snapshot/error tests but are structurally straightforward.

**Phase 3: Runtime state-machine extraction**
8. `Engine.run_async`
9. `describe_workflow_class`

These touch core lifecycle behavior. Refactor only with strong parity coverage.

---

## Test gates before merging these changes

Use exact-output and exact-error tests, not only happy paths:

1. **Provider emitters:** golden JSON payloads for Codex and Claude across permission modes, sandbox modes, network modes, dangerous bypass, and unsupported/lossy/unsafe classifications.
2. **Policy override:** matrix tests for `read_only`, `allow_write`, `sandbox_mode`, `permission_mode`, `network`, and `network_domains`.
3. **Artifact inventory:** duplicate workflow artifacts, duplicate step artifacts, shared artifact objects, workflow-level conflicts, branch-group nested artifacts, and producer rebind.
4. **Placeholder validation:** exact error messages for unknown, ambiguous, self, step, item, worklist, branch, fan-in, and `ctx.*` references.
5. **Engine loop:** resume, `AWAIT_INPUT`, `FAIL`, `FINISH`, `goto`, hook exceptions, provider failures, checkpoint restore, and max-step exhaustion.

The highest-value immediate change is to refactor the two provider emitters plus `_policy_layer_to_override`. That likely removes the worst CC outliers without touching the runtime engine.
