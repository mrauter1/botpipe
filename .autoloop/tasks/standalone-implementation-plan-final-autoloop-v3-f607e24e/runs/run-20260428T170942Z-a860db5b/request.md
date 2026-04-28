# Standalone implementation plan: final Autoloop v3 greenfield cleanup with retry-aware event validation

## 0. Context

This is a **greenfield cleanup pass**. There is no need to preserve compatibility with old public APIs, old route-contract naming, generated workflow-step handlers, or partially migrated compatibility surfaces.

The current implementation already contains most of the new architecture: `RouteInfo`, simple authoring helpers, callable-backed `SystemStep`, a real core `WorkflowStep`, provider `route_infos`, optional `reads`, hard `requires`, provider rendering updates, and simple workflow discovery. The remaining work is to clean up stale compatibility residue and correct event-validation behavior so recoverable provider mistakes retry with feedback instead of immediately terminating the run. 

Do **not** implement `autoloop eject`, source-code expansion, migration code generation, or any command that rewrites a simple workflow into a larger workflow package.

---

## 1. Objectives

Implement the following improvements:

1. Add shared validation for all route `Event` objects.
2. Make event validation **retry-aware** and **attribution-aware**.
3. Remove dead generated `workflow_step(...)` handler code.
4. Remove `BoardMutation` from active public exports until implemented.
5. Rename remaining “contracts” terminology to route-info / spec / support terminology.
6. Remove `contracts_path` from public capability and CLI payloads.
7. Strengthen strictness tests so removed concepts cannot reappear.
8. Update stale docstrings and docs to reflect the greenfield model.

---

## 2. Non-goals

Do not:

```text
- reintroduce RouteContract
- keep route_contracts compatibility fields
- keep route_required_artifacts compatibility fields
- keep generated workflow-step handler fallback paths
- expose unimplemented effects as public API
- preserve workflow/primitives.py as an authoring surface
- add provider/model/effort overrides to simple step declarations
- add source-code expansion or eject tooling
```

---

## 3. Correct event-validation model

### 3.1 Core invariant

Invalid route events must never be accepted.

However, invalid route events should **not always hard-fail the run**.

Correct rule:

```text
If the invalid event is provider-attributable:
  retry the provider turn with feedback according to ProviderRetryPolicy.

If the invalid event comes from deterministic workflow code:
  fail with WorkflowExecutionError.
```

Provider-attributable failures should fail only after retry exhaustion.

### 3.2 Invalid route payloads

These route payloads are invalid:

```text
question -> missing or empty question
blocked  -> missing or empty reason
failed   -> missing or empty reason
```

Also invalid:

```text
any event tag not present in step.available_routes
```

### 3.3 Provider-attributable examples

Treat these as retryable provider-attributable errors:

```text
- LLM provider returns question without question
- LLM provider returns blocked/failed without reason
- PairStep verifier returns question without question
- PairStep verifier returns blocked/failed without reason
- middleware maps provider outcome to an invalid Event
- after hook retags a provider outcome to failed/blocked/question while preserving missing provider fields
- provider-selected route requires missing or invalid output artifacts
- provider control payload fails validation
```

Provider-attributable invalid events must raise `ProviderExecutionError` with appropriate retry metadata.

### 3.4 Deterministic workflow-code examples

Treat these as non-retryable workflow-code errors:

```text
- system_step(fn) returns Event("question") without question
- system_step(fn) returns Event("failed") without reason
- workflow_step(...) maps a malformed child result to an invalid Event
- after hook explicitly returns Event("failed") without reason
- after hook explicitly returns AfterHookResult(event=Event("blocked"))
- deterministic middleware returns Event("question") without question unrelated to provider payload
```

These should raise `WorkflowExecutionError`.

---

## 4. Implement shared retry-aware event validation

### 4.1 Add helper

Add an engine helper:

```python
def _validate_event(
    self,
    step: CompiledStep,
    event: Event,
    *,
    provider_attributable: bool,
    error_cls: type[WorkflowExecutionError] = WorkflowExecutionError,
) -> None:
    ...
```

Behavior:

```text
If event is not Event:
  raise WorkflowExecutionError.

If event.tag is not legal for the step:
  provider_attributable=True  -> ProviderExecutionError with retry kind "illegal_route"
  provider_attributable=False -> WorkflowExecutionError or RoutingError

If event.tag == "question" and question is missing/empty:
  provider_attributable=True  -> ProviderExecutionError with retry kind "invalid_payload"
  provider_attributable=False -> WorkflowExecutionError

If event.tag in {"blocked", "failed"} and reason is missing/empty:
  provider_attributable=True  -> ProviderExecutionError with retry kind "invalid_payload"
  provider_attributable=False -> WorkflowExecutionError
```

### 4.2 Provider retry metadata

For provider-attributable invalid event errors, attach:

```python
error._provider_retry_kind = "invalid_payload"  # or "illegal_route"
error._failure_context = {
    "kind": "invalid_payload",
    "step": step.name,
    "route": event.tag,
    "error": "...",
    "provider_attributable": True,
}
```

For illegal routes:

```python
error._provider_retry_kind = "illegal_route"
error._failure_context = {
    "kind": "illegal_route",
    "step": step.name,
    "route": event.tag,
    "legal_routes": list(step.available_routes),
    "provider_attributable": True,
}
```

### 4.3 Reuse existing retry loop

Do not invent a new retry loop.

The existing provider retry loop should catch `ProviderExecutionError`, call `_next_retry_feedback(...)`, and retry when policy allows it.

Ensure `_next_retry_feedback(...)` handles:

```text
illegal_route
invalid_payload
missing_required_output_artifact
invalid_output_artifact
malformed_provider_output
provider_transport_failure
```

### 4.4 Use sites

Call `_validate_event(...)` in all relevant paths:

```text
1. after system handler event normalization
2. after workflow-step child result mapping
3. after middleware returns Event
4. in _finalize_step_result before after hook, for candidate_event
5. in _finalize_step_result after after hook, for final_event
6. before PAUSE/FAIL checkpointing, by ensuring final event has already been validated
```

Provider-attributability must be passed correctly.

Recommended attribution rules:

```text
LLMStep provider outcome -> provider_attributable=True
PairStep verifier outcome -> provider_attributable=True
middleware event in provider step -> provider_attributable=True unless explicitly marked otherwise
after hook returning only a route string in provider step -> provider_attributable=True
after hook returning explicit Event in provider step -> provider_attributable=False unless the hook preserves provider event fields mechanically
SystemStep handler result -> provider_attributable=False
WorkflowStep child result mapping -> provider_attributable=False
```

Keep the first implementation conservative:

```text
- route string override in provider steps may be provider_attributable=True
- explicit Event or AfterHookResult(event=...) from hook is provider_attributable=False
```

### 4.5 Provider outcome consistency

Keep `_validate_outcome(...)` for provider `Outcome` objects because it already attaches provider retry metadata.

Optionally factor shared reserved-route payload checks into:

```python
def _validate_route_payload(
    *,
    step_name: str,
    route_tag: str,
    reason: str,
    question: str | None,
    provider_attributable: bool,
    error_cls: type[WorkflowExecutionError],
) -> None:
    ...
```

Both `_validate_outcome(...)` and `_validate_event(...)` may call this helper, but provider outcome validation must continue raising `ProviderExecutionError` with retry metadata.

---

## 5. Update event-validation tests

Add tests for retry-aware behavior.

### 5.1 Provider invalid question retries

Workflow:

```python
class W(Workflow):
    ask = step("Ask if needed.")
    flow = chain(ask)
```

Provider turns:

```text
attempt 1 -> Outcome(tag="question", reason="Need input", question=None)
attempt 2 -> Outcome(tag="question", reason="Need input", question="Approve?")
```

Expected:

```text
terminal == PAUSE
checkpoint.pending_question == "Approve?"
provider was called twice
retry feedback was sent on second attempt
```

### 5.2 Provider invalid failed retries

Provider turns:

```text
attempt 1 -> Outcome(tag="failed", reason="")
attempt 2 -> Outcome(tag="failed", reason="Could not complete safely.")
```

Expected:

```text
terminal == FAIL
last_event.reason == "Could not complete safely."
provider called twice
```

### 5.3 Provider invalid blocked retries

Provider turns:

```text
attempt 1 -> Outcome(tag="blocked", reason="")
attempt 2 -> Outcome(tag="blocked", reason="Missing required external data.")
```

Expected:

```text
terminal == PAUSE
last_event.reason == "Missing required external data."
provider called twice
```

### 5.4 Provider retry exhaustion

Provider always returns:

```python
Outcome(tag="question", reason="Need input", question=None)
```

Expected:

```text
run raises ProviderExecutionError after max_attempts
failure_context.kind == "invalid_payload"
retry_exhausted == True
```

### 5.5 System invalid question hard-fails

Workflow:

```python
class W(Workflow):
    ask = system_step(lambda ctx: Event("question"))
    flow = chain(ask)
```

Expected:

```text
run raises WorkflowExecutionError
no provider retry is attempted
message mentions question route requires non-empty question
```

### 5.6 System valid question pauses

```python
system_step(lambda ctx: Event("question", question="Need input?"))
```

Expected:

```text
terminal == PAUSE
checkpoint.pending_question == "Need input?"
```

### 5.7 System invalid failed hard-fails

```python
system_step(lambda ctx: Event("failed"))
```

Expected:

```text
WorkflowExecutionError
```

### 5.8 System valid failed terminates

```python
system_step(lambda ctx: Event("failed", reason="Could not continue."))
```

Expected:

```text
terminal == FAIL
last_event.reason == "Could not continue."
```

### 5.9 After hook route string in provider step retries

Provider returns:

```python
Outcome(tag="done", reason="")
```

After hook:

```python
def after(ctx, outcome):
    return "failed"
```

Expected:

```text
invalid final failed event is provider-attributable
provider retries with feedback
if second provider attempt has reason and after hook still retags, final FAIL succeeds
```

### 5.10 After hook explicit invalid Event hard-fails

After hook:

```python
def after(ctx, outcome):
    return Event("failed")
```

Expected:

```text
WorkflowExecutionError
no provider retry
```

### 5.11 WorkflowStep malformed child pause hard-fails

Child result:

```python
terminal = PAUSE
last_event = Event("question")
```

Parent `WorkflowStep` maps to invalid event.

Expected:

```text
WorkflowExecutionError
```

### 5.12 WorkflowStep valid child pause question

Child result:

```python
terminal = PAUSE
last_event = Event("question", question="Approve?")
```

Expected:

```text
parent terminal == PAUSE
pending_question == "Approve?"
```

---

## 6. Remove dead generated workflow-step handler code

### 6.1 Delete obsolete functions

Remove these from `core/validation.py` if present and unused:

```text
_install_simple_workflow_step_handler
_resolve_simple_message_artifact
_simple_workflow_step_message
_write_simple_workflow_step_outputs
_simple_workflow_step_output_payload
_simple_workflow_step_output_summary
_map_simple_workflow_child_result
_simple_artifact_reference_lookup
```

Remove any imports made unnecessary by these deletions, especially:

```python
ArtifactHandle
resolve_artifact_template
```

if no longer used elsewhere in `core/validation.py`.

### 6.2 Required behavior

`workflow_step(...)` must lower only to `core.steps.WorkflowStep`.

It must not:

```text
- lower to SystemStep
- install generated on_<step> handlers
- require on_<step>
- create staticmethod handlers dynamically
```

### 6.3 Tests

Add or keep tests proving:

```text
workflow_step(...) compiles to core.steps.WorkflowStep
compiled step kind is "workflow"
compiled step has no system_handler
workflow class does not receive generated on_<step>
WorkflowStep is executed directly by Engine
```

---

## 7. Remove `BoardMutation` from active public exports

### 7.1 Decision

`BoardMutation` is not implemented, so it must not be exported or documented.

Preferred greenfield action:

```text
Delete BoardMutation entirely.
```

### 7.2 Remove from code

Remove `BoardMutation` from:

```text
core/effects.py
core/effects.py __all__
core/__init__.py imports
core/__init__.py __all__
core/validation.py effect validation
core/engine.py route effect execution
docs
tests
```

If deleting causes too much disruption, temporarily rename it to `_BoardMutation`, but do not export or document it. Since the project is greenfield, deletion is preferred.

### 7.3 Tests

Add tests:

```python
import autoloop
assert not hasattr(autoloop, "BoardMutation")
```

If `core` remains importable:

```python
import core
assert not hasattr(core, "BoardMutation")
```

Also grep active docs/source for `BoardMutation`.

---

## 8. Rename remaining “contracts” terminology

### 8.1 Rename stdlib module

Rename:

```text
stdlib/contracts.py -> stdlib/route_infos.py
```

Delete the old file.

### 8.2 Rename functions

Rename:

```text
review_gate_contracts(...)       -> review_gate_infos(...)
publication_gate_contracts(...)  -> publication_gate_infos(...)
```

Return type:

```python
dict[str, RouteInfo]
```

Do not keep aliases with the old names.

### 8.3 Update imports

Search and replace all imports and references.

Examples:

```python
from stdlib.contracts import review_gate_contracts
```

becomes:

```python
from stdlib.route_infos import review_gate_infos
```

Update `stdlib/__init__.py`.

### 8.4 Tests

Add tests:

```text
stdlib/contracts.py does not exist
review_gate_contracts does not appear in active source
publication_gate_contracts does not appear in active source
stdlib.route_infos.review_gate_infos exists
stdlib.route_infos.publication_gate_infos exists
```

---

## 9. Remove `contracts_path` from public payloads

### 9.1 New model

A user file named `contracts.py` may still exist as a schema/spec/support file, but it must be exposed through:

```text
spec_paths
support_paths
schema_paths
```

Use existing `spec_paths` unless a broader support-file field already exists.

### 9.2 Remove fields

Remove `contracts_path` from:

```text
WorkflowCatalogEntry
WorkflowCapabilityEntry
workflow_capability_payload(...)
selected_workflow_authoring_surface_payload(...)
selected_workflow_decomposition_surface_payload(...)
runtime CLI workflows show payload
runtime loader manifest package construction
tests
```

Remove:

```text
contracts_path_repo_relative
```

from decomposition payloads.

### 9.3 Catalog discovery

Delete helpers like:

```text
_contracts_path(...)
_support_contracts_path(...)
```

Update `_spec_paths(...)` so it includes:

```text
specs.py
contracts.py
```

when present.

Example:

```python
def _spec_paths(source_path: Path) -> tuple[Path, ...]:
    if source_path.name not in {"flow.py", "workflow.py", "__init__.py"}:
        return ()
    paths = []
    for filename in ("specs.py", "contracts.py"):
        candidate = source_path.parent / filename
        if candidate.is_file():
            paths.append(candidate.resolve())
    return tuple(paths)
```

### 9.4 Editable paths

Ensure `editable_paths` includes all `spec_paths`, including `contracts.py` if present.

### 9.5 Tests

Add tests:

```text
capability payload has no contracts_path key
selected authoring surface payload has no contracts_path key
decomposition payload has no contracts_path_repo_relative key
contracts.py, if present, appears in spec_paths
editable_paths includes contracts.py through spec_paths
```

---

## 10. Tighten strictness tests

### 10.1 Add grep-based anti-regression test

Create or update:

```text
tests/strictness/test_no_compat.py
```

Scan active source and docs.

Recommended roots:

```text
autoloop/
core/
runtime/
stdlib/
extensions/
workflow/
tests/
docs/ if present
README.md if present
```

Exclude:

```text
.git/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.venv/
dist/
build/
*.pyc
tests/strictness/test_no_compat.py itself
archived migration notes if explicitly archived
```

### 10.2 Forbidden terms

Forbid active matches for:

```text
RouteContract
route_contracts
route_required_artifacts
"route contract"
review_gate_contracts
publication_gate_contracts
contracts_path
contracts_path_repo_relative
BoardMutation
_install_simple_workflow_step_handler
```

Because the test itself may need to contain those strings, either exclude the test file or build strings indirectly:

```python
FORBIDDEN = [
    "Route" + "Contract",
    "route_" + "contracts",
]
```

### 10.3 Allowed term

Allow:

```text
contracts.py
```

only as a user schema/spec file name.

Do not allow:

```text
contracts_path
```

---

## 11. `workflow/` shim policy

### 11.1 `workflow/__init__.py`

Acceptable behavior:

```text
workflow/__init__.py may remain as a hard-fail or no-authoring shim pointing users to autoloop.simple or autoloop.
```

### 11.2 `workflow/primitives.py`

Preferred greenfield behavior:

```text
delete workflow/primitives.py
```

Acceptable fallback:

```text
keep workflow/primitives.py only as a runtime primitive shim, not an authoring surface.
```

If kept, it must not export:

```text
LLMStep
PairStep
SystemStep
WorkflowStep
Artifact
RouteInfo authoring helpers
step
review_step
workflow_step
system_step
```

It may expose only low-level immutable runtime primitives, for example:

```text
Event
Outcome
Checkpoint
ResolvedArtifacts
ChildWorkflowResult
```

### 11.3 Tests

Add tests:

```text
public docs do not import from workflow.primitives
workflow.primitives does not expose authoring step classes
workflow.primitives does not expose simple helper functions
```

---

## 12. Update stale docstrings and comments

Search active code for stale phrases:

```text
Additive public authoring surface
future simple-step lowering
Foundation declaration for future
compatibility alias
legacy workflow shim
legacy workflow path
```

Update to current terminology.

Examples:

```text
"Simple public authoring surface."
"Simple step declaration lowered during workflow definition discovery."
"Child-workflow invocation step declaration."
"Runtime primitive re-export; not an authoring API."
```

If fields such as `legacy_workflow_path` remain, either rename them or document them neutrally.

Preferred rename:

```text
legacy_workflow_path -> workflow_py_path
```

If renaming is too broad for this pass, do not expose it in public docs as a compatibility concept.

---

## 13. Implementation order

Follow this order.

### Step 1: Retry-aware event validation

1. Add `_validate_event(...)`.
2. Add shared reserved-route payload validation helper if useful.
3. Wire validation into system, workflow, middleware, candidate-event, and final-event paths.
4. Classify provider-attributable versus deterministic workflow-code failures.
5. Ensure provider-attributable invalid events enter the existing retry loop with feedback.
6. Add event-validation retry tests.

### Step 2: Remove generated workflow-step handler code

1. Delete obsolete generated-handler functions.
2. Remove unused imports.
3. Confirm `workflow_step(...)` lowers only to `WorkflowStep`.
4. Add tests proving no generated `on_<step>` handler exists.

### Step 3: Remove `BoardMutation`

1. Delete `BoardMutation` or make it private and unreachable.
2. Remove exports.
3. Remove validation/engine branches.
4. Add import-failure and grep tests.

### Step 4: Rename stdlib route-info helpers

1. Rename `stdlib/contracts.py` to `stdlib/route_infos.py`.
2. Rename functions.
3. Update imports.
4. Delete old module.
5. Add strictness tests.

### Step 5: Remove `contracts_path`

1. Remove from dataclasses.
2. Remove from capability payloads.
3. Remove from CLI payloads.
4. Add `contracts.py` to `spec_paths`.
5. Update tests.

### Step 6: Tighten strictness tests

1. Add forbidden-term scan.
2. Add public API assertions.
3. Run strictness tests.

### Step 7: Docs and docstrings

1. Update stale docstrings.
2. Remove compatibility language.
3. Ensure docs import from `autoloop.simple` or `autoloop`.
4. Run doc tests if present.

### Step 8: Full test run

Run:

```bash
pytest
```

Also run any existing lint/type/test command if present.

---

## 14. Acceptance criteria

The implementation is complete when:

```text
Invalid question/blocked/failed route payloads are never accepted.

Provider-attributable invalid events retry with feedback according to ProviderRetryPolicy.

Provider-attributable invalid events fail only after retry exhaustion.

Deterministic workflow-code invalid events fail with WorkflowExecutionError.

system_step(fn) invalid Event("question") without question hard-fails.

provider invalid question/blocked/failed route retries and can recover on a later attempt.

after hook route string override in provider step can trigger provider retry if it creates an invalid provider-attributable final event.

after hook explicit invalid Event hard-fails as workflow-code error.

workflow_step(...) compiles to real WorkflowStep and never installs generated on_<step> handlers.

Dead generated workflow-step helper code is removed.

BoardMutation is not importable from active public APIs.

BoardMutation is not documented or exported.

stdlib/contracts.py is gone.

review_gate_contracts and publication_gate_contracts are gone.

review_gate_infos and publication_gate_infos exist and return RouteInfo metadata.

contracts_path and contracts_path_repo_relative are absent from public payloads.

contracts.py, if present as a user support file, appears through spec_paths.

No active source/docs contain RouteContract, route_contracts, route_required_artifacts, "route contract", contracts_path, or BoardMutation.

workflow/primitives.py, if retained, is not an authoring surface.

Docs and examples use autoloop.simple or autoloop.

All tests pass.

No autoloop eject or source-code expansion command exists.
```

---

## 15. Final instruction for the implementing agent

Prefer deletion over compatibility. This is a greenfield cleanup pass. Any remaining old name must represent a real current concept, not preserve an obsolete API. Invalid route events must remain strict, but recoverable provider mistakes should use the existing retry-and-feedback loop rather than immediately terminating the run.
