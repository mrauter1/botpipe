# Standalone implementation plan: final Autoloop v3 cleanup fixes

## 0. Context

This is a **greenfield cleanup pass**. Do not preserve compatibility with obsolete public import surfaces, old `workflow/` shims, old “legacy” terminology, or generic retry feedback when structured failure context is available.

The current implementation already has the main new architecture: `autoloop` / `autoloop.simple` are the public surfaces, `RouteInfo` has replaced route contracts, `WorkflowStep` is a real core step, `system_step(fn)` is callable-backed, provider request models use `route_infos`, and `workflow/` still exists as a separate package in the tree. 

Do **not** implement `autoloop eject`, source-code expansion, migration code generation, or compatibility shims.

---

## 1. Goals

Implement exactly these fixes:

1. Improve provider retry feedback for invalid route payloads.
2. Remove remaining greenfield-incompatible “legacy” terminology.
3. Delete the `workflow/` package entirely.
4. Port any still-needed runtime primitives from `workflow/primitives.py` to the actual public API.
5. Keep `Checkpoint` and `ChildWorkflowResult` on the public API.
6. Confirm no workflow-step generated-handler code exists; add only a guard test.
7. Strengthen strictness tests so the removed concepts cannot reappear.

---

## 2. Public API decision

The public authoring/runtime surface is:

```python
from autoloop import ...
```

and:

```python
from autoloop.simple import ...
```

Delete the `workflow/` package. Do not keep `workflow/__init__.py`. Do not keep `workflow/primitives.py`. Do not replace it with another `workflow` shim.

### Public primitives to expose

Export these from both `autoloop.simple` and `autoloop`:

```python
Event
Outcome
Checkpoint
ResolvedArtifacts
ChildWorkflowResult
```

Keep existing public exports:

```python
AfterHookResult
Json
Md
Prompt
Raw
Route
RouteInfo
StrictWorkflow
Text
Workflow
WorkflowStep
chain
review_step
step
system_step
workflow_step
```

### Import sources

In `autoloop/simple.py`, import:

```python
from core.primitives import Event, Outcome, Checkpoint
from core.artifacts import ResolvedArtifacts
from core.context import ChildWorkflowResult
```

using the same package / fallback import style already used in the file.

Update `autoloop/simple.py.__all__` and `autoloop/__init__.py.__all__`.

---

## 3. Improve provider retry feedback for invalid route payloads

### Problem

`build_retry_feedback(...)` currently treats all `invalid_payload` failures generically. For route payload errors, this is not specific enough. The retry note should tell the provider exactly what to repair.

Examples of specific runtime failures:

```text
question route requires a non-empty question field
blocked route requires a non-empty reason field
failed route requires a non-empty reason field
```

### Required behavior

For `_provider_retry_kind == "invalid_payload"`:

1. If `failure_context["error"]` is a non-empty string, include it in the retry feedback.
2. If `failure_context["route"]` is also present, include the selected route.
3. Fall back to the generic invalid-payload message only when there is no specific error.

### Exact code change

Edit:

```text
core/providers/retries.py
```

Update `_problem_summary(...)`.

Replace the generic invalid-payload branch with:

```python
if kind == "invalid_payload":
    route = _failure_context_field(exc, "route")
    detail = _failure_context_field(exc, "error")
    if detail and route:
        return f"The selected route {route!r} has an invalid payload: {detail}."
    if detail:
        return f"The structured output payload is invalid: {detail}."
    return "The structured output payload did not satisfy the declared output contract."
```

Keep generic fallback behavior for ordinary control-schema validation errors.

### Improve action guidance

Update the action list in `build_retry_feedback(...)` to include route-payload repair guidance:

```text
Action required:
- Repair the issue using the current Runtime Step Contract.
- Use only an allowed route.
- If selecting `question`, include a non-empty top-level `question`.
- If selecting `blocked` or `failed`, include a concise non-empty `reason`.
- Write all artifacts required by the selected route.
```

### Tests

Update or add tests in:

```text
tests/unit/test_provider_retries.py
```

Add tests for:

```python
error._provider_retry_kind = "invalid_payload"
error._failure_context = {
    "route": "question",
    "error": "question route requires a non-empty question field",
}
```

Expected feedback contains:

```text
The selected route 'question' has an invalid payload: question route requires a non-empty question field.
```

Add analogous tests for:

```python
{
    "route": "failed",
    "error": "failed route requires a non-empty reason field",
}
```

Also test generic fallback:

```python
error._provider_retry_kind = "invalid_payload"
```

Expected feedback still contains:

```text
The structured output payload did not satisfy the declared output contract.
```

---

## 4. Delete the `workflow/` package

### Files to delete

Delete:

```text
workflow/__init__.py
workflow/primitives.py
workflow/
```

Do not leave a hard-fail shim.

### Update imports

Search for all references:

```bash
grep -R "from workflow" .
grep -R "import workflow" .
grep -R "workflow.primitives" .
```

Replace public-facing test/example imports with:

```python
from autoloop import Event, Outcome, Checkpoint, ResolvedArtifacts, ChildWorkflowResult
```

or:

```python
from autoloop.simple import Event, Outcome, Checkpoint, ResolvedArtifacts, ChildWorkflowResult
```

Replace internal framework-test imports with their true internal modules:

```python
from core.primitives import Event, Outcome, Checkpoint
from core.artifacts import ResolvedArtifacts
from core.context import ChildWorkflowResult
```

### Workflow-class detection

Edit:

```text
core/validation.py
```

Remove:

```python
("workflow", "Workflow")
```

from both:

```python
_is_base_workflow_class(...)
_inherits_supported_workflow_base(...)
```

Keep support for the active bases:

```python
("autoloop.simple", "Workflow")
("autoloop.simple", "StrictWorkflow")
("autoloop_v3.core", "Workflow")
("core", "Workflow")
```

if those remain valid in the repository’s import setup.

### Strictness test

Add:

```python
assert not (repo_root / "workflow").exists()
```

Also forbid active imports using regex patterns:

```python
r"^\s*from\s+workflow(\.|\s+import\b)"
r"^\s*import\s+workflow(\s|$|,)"
r"workflow\.primitives"
```

Do not forbid the substring `workflow` generally.

---

## 5. Export public runtime primitives

### Add exports

In `autoloop/simple.py`, expose:

```python
Event
Outcome
Checkpoint
ResolvedArtifacts
ChildWorkflowResult
```

In `autoloop/__init__.py`, re-export the same names.

### Tests

Update:

```text
tests/unit/test_simple_surface.py
```

Add:

```python
from autoloop import Event, Outcome, Checkpoint, ResolvedArtifacts, ChildWorkflowResult
from autoloop.simple import Event as SimpleEvent
from autoloop.simple import Outcome as SimpleOutcome
from autoloop.simple import Checkpoint as SimpleCheckpoint
from autoloop.simple import ResolvedArtifacts as SimpleResolvedArtifacts
from autoloop.simple import ChildWorkflowResult as SimpleChildWorkflowResult

assert Event is SimpleEvent
assert Outcome is SimpleOutcome
assert Checkpoint is SimpleCheckpoint
assert ResolvedArtifacts is SimpleResolvedArtifacts
assert ChildWorkflowResult is SimpleChildWorkflowResult
```

Add or update a public API test confirming:

```python
import autoloop
assert hasattr(autoloop, "Checkpoint")
assert hasattr(autoloop, "ChildWorkflowResult")
```

---

## 6. Remove remaining “legacy” terminology

### 6.1 Rename `legacy_workflow_path`

Rename this field everywhere:

```text
legacy_workflow_path -> workflow_py_path
```

Affected files likely include:

```text
core/workflow_catalog.py
core/workflow_capabilities.py
runtime/cli.py
runtime/loader.py
tests/runtime/*
tests/unit/*
```

Update dataclass fields:

```python
WorkflowCatalogEntry.workflow_py_path
WorkflowCapabilityEntry.workflow_py_path
```

Update all object construction:

```python
workflow_py_path=source_path if source_path.name == "workflow.py" else None
```

Update JSON payload keys:

```text
"workflow_py_path"
```

Remove JSON keys:

```text
"legacy_workflow_path"
```

### Do not rename `workflow_package`

Do **not** rename the authoring-shape value:

```text
workflow_package
```

That is current descriptive terminology for a package whose source file is `workflow.py`; it is not a legacy compatibility concept.

### 6.2 Rename `_load_legacy_parameter_type`

Rename:

```text
_load_legacy_parameter_type
```

to:

```text
_load_parameters_from_params_py
```

Update variable names at call sites.

For example:

```python
legacy = _load_legacy_parameter_type(...)
```

becomes:

```python
parameters_from_params_py = _load_parameters_from_params_py(...)
```

Do not keep the old function as an alias.

### 6.3 Rename `is_legacy_run_key`

Rename:

```text
is_legacy_run_key
```

to:

```text
is_run_key_bound_to_slot
```

Update imports and call sites in:

```text
core/context.py
core/stores/protocols.py
```

Use this docstring:

```python
def is_run_key_bound_to_slot(key: SessionKey | None, *, slot: str | None = None) -> bool:
    """Return whether a run-continuity key still uses the session slot as its value."""
```

This preserves the behavior while removing compatibility terminology.

### 6.4 Delete `ResolvedWorkflow.package`

In:

```text
runtime/loader.py
```

Delete:

```python
@property
def package(self) -> WorkflowReference:
    ...
```

Replace all uses of:

```python
resolved.package
```

with:

```python
resolved.reference
```

Do not keep a compatibility alias.

### 6.5 Update comments and docstrings

Search active source and docs for:

```text
legacy
compatibility alias
legacy workflow
legacy path
```

For each occurrence:

* Rename to current terminology if it describes active behavior.
* Delete if obsolete.
* Leave test filenames such as `test_compatibility_runtime.py` only if the content tests current behavior and renaming the file is out of scope.

Examples:

```text
"Compatibility alias for older runtime callers/tests."
```

should become:

```text
"Resolved workflow origin metadata."
```

or be removed with the alias.

---

## 7. Confirm no workflow-step generated-handler code remains

The user has already verified that no workflow-step helper code remains.

Do not refactor workflow-step execution.

Only add a guard in strictness tests for:

```text
_install_simple_workflow_step_handler
```

No implementation change is needed unless the guard fails.

---

## 8. Update strictness tests

Create or update:

```text
tests/strictness/test_no_compat.py
```

### Forbidden strings / symbols

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
legacy_workflow_path
_load_legacy_parameter_type
is_legacy_run_key
"Compatibility alias"
workflow.primitives
```

For import statements from the deleted `workflow` package, use regex:

```python
r"^\s*from\s+workflow(\.|\s+import\b)"
r"^\s*import\s+workflow(\s|$|,)"
```

Do not forbid the general word `workflow`.

### Forbidden paths

Assert these paths do not exist:

```text
workflow/
stdlib/contracts.py
```

### Allowed terms

Allow:

```text
contracts.py
```

only as a support/spec filename surfaced through `spec_paths`.

Allow the authoring-shape string:

```text
workflow_package
```

Allow test filenames containing:

```text
compatibility
```

only if the contents do not contain the forbidden compatibility symbols above.

---

## 9. Update capability and CLI tests

### Payload rename tests

Update tests to assert payloads contain:

```text
workflow_py_path
```

and do not contain:

```text
legacy_workflow_path
```

Check all relevant payloads:

```text
workflow_capability_payload(...)
selected_workflow_authoring_surface_payload(...)
selected_workflow_decomposition_surface_payload(...)
runtime CLI workflows show payload
```

### Loader tests

Replace all uses of:

```python
resolved.package
```

with:

```python
resolved.reference
```

Add a test:

```python
assert not hasattr(ResolvedWorkflow, "package")
```

### CLI test

Add or update runtime CLI test:

```text
autoloop workflows show ...
```

Expected JSON includes:

```text
workflow_py_path
```

and does not include:

```text
legacy_workflow_path
```

---

## 10. Update docs

Update active docs and examples so they import only from:

```python
from autoloop import ...
```

or:

```python
from autoloop.simple import ...
```

No active docs should mention:

```text
workflow.primitives
from workflow
import workflow
legacy_workflow_path
RouteContract
BoardMutation
```

Docs may mention a user file named:

```text
contracts.py
```

only as a support/spec/schema file under `spec_paths`.

---

## 11. Implementation order

Use this order:

1. Improve `core/providers/retries.py` feedback specificity.
2. Add retry-feedback tests.
3. Export `Event`, `Outcome`, `Checkpoint`, `ResolvedArtifacts`, and `ChildWorkflowResult` from `autoloop.simple` and `autoloop`.
4. Port all imports from `workflow` / `workflow.primitives`.
5. Delete the `workflow/` package.
6. Remove `("workflow", "Workflow")` from workflow-class detection.
7. Rename `legacy_workflow_path` to `workflow_py_path`.
8. Rename `_load_legacy_parameter_type` to `_load_parameters_from_params_py`.
9. Rename `is_legacy_run_key` to `is_run_key_bound_to_slot`.
10. Delete `ResolvedWorkflow.package` and update call sites.
11. Update capability, CLI, runtime, and loader tests.
12. Strengthen strictness tests for forbidden paths, symbols, and imports.
13. Update docs.
14. Run targeted tests.
15. Run full test suite.

Targeted tests:

```bash
pytest tests/unit/test_provider_retries.py
pytest tests/unit/test_simple_surface.py
pytest tests/strictness/test_no_compat.py
pytest tests/runtime/test_package_cli.py
pytest tests/runtime/test_workflow_reference_resolution.py
```

Then:

```bash
pytest
```

---

## 12. Acceptance criteria

The patch is complete only when all are true:

```text
Provider retry feedback for invalid route payloads includes failure_context["error"] when present.

Retry feedback for invalid question/blocked/failed payloads tells the provider exactly which field is missing.

Generic invalid_payload feedback still works when no specific failure context exists.

autoloop and autoloop.simple export Event, Outcome, Checkpoint, ResolvedArtifacts, and ChildWorkflowResult.

workflow/ no longer exists.

No active source or docs import workflow or workflow.primitives.

workflow-class detection no longer references ("workflow", "Workflow").

legacy_workflow_path is renamed to workflow_py_path everywhere.

No public JSON payload contains legacy_workflow_path.

_load_legacy_parameter_type is renamed to _load_parameters_from_params_py.

is_legacy_run_key is renamed to is_run_key_bound_to_slot.

ResolvedWorkflow.package is deleted; all uses move to ResolvedWorkflow.reference.

workflow_package authoring-shape value remains unchanged.

Strictness tests forbid the removed symbols and paths.

No workflow-step generated-handler code is added or changed; existing absence is only guarded by tests.

All targeted tests pass.

Full pytest passes.

No autoloop eject or source-code expansion command exists.
```

## 13. Final instruction for the implementing agent

Prefer deletion and renaming over compatibility. The repository should present one current architecture: public authoring/runtime primitives through `autoloop` / `autoloop.simple`, internal mechanics through `core`, and no `workflow` package. Keep runtime behavior unchanged except for improving provider retry feedback specificity and removing obsolete names.
