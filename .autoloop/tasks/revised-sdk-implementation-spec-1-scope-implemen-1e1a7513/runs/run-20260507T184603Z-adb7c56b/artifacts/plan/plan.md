# Revised SDK Implementation Plan

## Scope
- Implement the spec as an additive SDK expansion on top of the existing filesystem runtime.
- Keep `Autoloop.run(...)` and step helpers as thin facades over `execute_workflow_package(...)`.
- Limit behavior changes to those explicitly required by the spec: retained SDK result artifacts, retention-aware task cleanup, `{input.message}` prompt rendering, and corrected synthetic step routing.
- Keep `llm(...)` and `classify(...)` out of retention scope in this MVP.

## Current State
- `autoloop/sdk.py` already provides `run(...)`, `step(...)`, pause handling, synthetic one-step workflow generation, and basic MVP rejection for branch groups and scoped steps.
- Public SDK artifacts currently expose raw `ArtifactHandle` instances and are resolved from a local `_sdk_artifact_context(...)`.
- Synthetic routing is incomplete: default routes collapse to `"done" -> FINISH`, and explicit route targets are inferred from route names instead of preserving the caller-provided mapping.
- SDK task directories are generated under `.autoloop/tasks/<sdk-task-id>` but have no SDK sentinel or retention cleanup path.
- Engine prompt rendering currently replaces `ctx`, `item`, `worklist`, `branch`, and `fan_in`, but not `input`.

## Milestones
### M1. Public SDK surface and artifact result model
- Update `autoloop/__init__.py` exports to expose concrete step classes plus `ResultArtifact`, `RetentionPolicy`, `RetentionInfo`, and `CleanupResult`.
- Expand `autoloop/sdk.py` imports to include all supported step classes and retention utility dependencies.
- Add `ResultArtifact`, `DeclaredWriteArtifact`, `RetentionPolicy`, `RetentionInfo`, and `CleanupResult`.
- Convert `ArtifactMap`, `WorkflowResult.artifact(...)`, and `StepResult` to use retained `ResultArtifact` instances instead of public raw `ArtifactHandle`s.
- Preserve existing runtime artifact handles inside workflow execution; only the public SDK result surface changes.

### M2. Retention plumbing and safe SDK task lifecycle
- Thread `retention` through `Autoloop.__init__`, `run(...)`, `step(...)`, and all new helper methods.
- Write `.autoloop-sdk-task.json` before each SDK-backed execution once `task_id` and `task_dir` are known.
- Add `_safe_delete_sdk_task_dir(...)` with strict sentinel, ancestry, and dangerous-path guards before any deletion.
- Extend the SDK artifact-resolution helper to a full runtime-equivalent context for declared-write collection, reusing runtime field names and semantics for `root`, `task_id`, `run_id`, `workflow_name`, `task_folder`, `workflow_folder`, `run_folder`, `package_folder`, `request_file`, `task_request_file`, final `state`, `params`, `workflow_params`, `message`, typed `input`, and session snapshot/store access.
- Promote declared artifacts that resolve inside task scratch into `<root>/.autoloop/outputs/sdk/<task-id>/` or a caller override, then apply retention according to policy.
- Keep task scratch by default on failed runs, unhandled input pauses, too-many-pauses, and resume/input validation errors.
- Add `cleanup(...)` that scans only sentinel-marked SDK task directories and skips uncertain failed/paused runs unless explicitly included.

### M3. Prompt rendering and one-step workflow correctness
- Add `"input"` to engine prompt rendering roots while preserving the existing artifact-template ban on `ctx.*`.
- Keep `{ctx.message}` and `{input.message}` equivalent for workflow-backed prompt execution.
- Change `Autoloop.step(...)` to accept concrete `Step` plus optional explicit `routes`.
- Preserve the current `client.step(simple.<factory>(...), ...)` compatibility path for existing simple named declarations, while keeping concrete `Step` as the recommended authoring path.
- Build synthetic workflows by preserving caller-supplied routes exactly; only synthesize defaults when `routes is None`.
- Use spec-defined defaults: `"done" -> FINISH` for prompt/python/child-workflow steps and `"accepted" -> FINISH`, `"needs_rework" -> SELF` for produce/verify steps.
- Continue rejecting `BranchGroupStep`, scoped/worklist steps, malformed steps, and unresolved child workflow refs in the SDK MVP.

### M4. Step helpers and regression coverage
- Add `prompt_step(...)`, `produce_verify_step(...)`, `python_step(...)`, and `workflow_step(...)` as thin constructors over `client.step(...)`.
- Normalize prompt and retry inputs in SDK-local helpers instead of mutating step instances after construction.
- Clarify `workflow_step(...)` semantics by separating outer SDK `message` from child workflow `child_message`.
- Extend `tests/unit/test_sdk_facade.py` for helper methods, retention behavior, route preservation, result artifact behavior, sentinel safety, and cleanup.
- Add prompt-rendering acceptance coverage for `{input.message}`, `{ctx.message}`, typed `Workflow.Input` access, and clear failures for missing input fields.

## Interface Definitions
- `Autoloop.__init__(..., retention: RetentionPolicy | None = None) -> None`
- `Autoloop.run(..., retention: RetentionPolicy | None = None) -> WorkflowResult`
- `Autoloop.step(step_def: Step, ..., routes: Mapping[str, Any] | None = None, retention: RetentionPolicy | None = None) -> StepResult`
- `Autoloop.prompt_step(...) -> StepResult`
- `Autoloop.produce_verify_step(...) -> StepResult`
- `Autoloop.python_step(...) -> StepResult`
- `Autoloop.workflow_step(..., child_message: str | None = None, ...) -> StepResult`
- `Autoloop.cleanup(..., older_than: timedelta | None = None, include_failed: bool = False, dry_run: bool = False) -> CleanupResult`
- `WorkflowResult.retention: RetentionInfo | None`
- `ArtifactMap: Mapping[str, ResultArtifact]`
- `StepResult.value` becomes `None` in MVP unless a truthful value-capture path is later added.

## Compatibility Notes
- Public export changes are additive except for SDK result artifacts: callers receiving `WorkflowResult.artifacts[...]` or `WorkflowResult.artifact(...)` will now get `ResultArtifact`, not `ArtifactHandle`.
- `ResultArtifact` intentionally remains read-only/materialization-focused; write helpers stay on runtime artifact handles inside workflow execution.
- `StepResult.value = workflow_result.output` is intentionally removed because it is not truthful for general one-step execution.
- The simple authoring factories (`step`, `produce_verify_step`, `python_step`, `validation_step`, `workflow_step`) remain exported and unchanged.
- Existing `client.step(simple.llm.step(...), ...)` and comparable simple named-declaration call sites remain supported for backward compatibility in this slice; the plan only recenters documentation and new helper methods around concrete `Step` instances.
- No retention or cleanup contract is added to `llm(...)` or `classify(...)` in this slice.

## Regression Controls
- Reuse the existing SDK/runtime artifact path resolution shape and field names, but explicitly widen the SDK helper context to the full runtime-equivalent placeholder surface required by the request instead of relying on the current subset helper.
- Keep retention deletion bounded to SDK-created task directories proven by sentinel and path checks.
- Preserve existing pause-loop semantics; only inject retention before returning or raising partial-result exceptions.
- Keep workspace writes outside the current SDK task directory untouched, including previously promoted outputs.
- Limit cleanup to sentinel-marked directories and skip uncertain failed/awaiting-input state when `include_failed=False`.
- Preserve current `client.step(...)` behavior for simple named declarations unless a later user clarification explicitly authorizes narrowing that support.

## Validation
- Run focused unit coverage in `tests/unit/test_sdk_facade.py`.
- Add or extend prompt-rendering coverage in the SDK or engine contract tests for `{input.message}` and typed `input.*` placeholders.
- Verify export coverage with import-based tests or `test_simple_surface` updates.
- Verify successful SDK runs delete scratch by default, while failure/input-required/too-many-pauses retain scratch by default.
- Verify explicit `routes=` preserves `SELF`, `FINISH`, `AWAIT_INPUT`, `FAIL`, `Route(...)`, and valid concrete targets without route-name rewriting.
- Verify declared-write resolution works for templates that depend on the widened runtime-equivalent context fields rather than only the current SDK subset helper.
- Verify existing `client.step(simple.llm.step(...), ...)` and equivalent simple named-declaration call sites continue to work unchanged.

## Risk Register
- Risk: deleting non-SDK directories.
  Mitigation: sentinel, `sdk-` prefix, ancestry checks, explicit blocked paths, and refusal-first behavior.
- Risk: breaking callers that relied on `ArtifactHandle` mutators from SDK results.
  Mitigation: call out the intentional API change, keep `ResultArtifact` read helpers aligned with current read behavior, and add coverage for schema-aware reads/materialization.
- Risk: route regressions for single-step workflows, especially produce/verify rework loops.
  Mitigation: centralize default-route selection and test both defaults and explicit overrides.
- Risk: incorrect artifact promotion for task-local writes.
  Mitigation: reuse compiled artifact metadata, widen the SDK resolution context to the full runtime-equivalent field set, keep path traversal checks strict, and reject unsupported directory promotion unless implemented safely.
- Risk: cleanup removing paused or failed forensic data.
  Mitigation: conservative skip logic by default and `dry_run` coverage.
- Risk: narrowing `client.step(...)` to concrete `Step` only and breaking current simple declaration call sites.
  Mitigation: keep backward-compatibility coverage explicit in the plan and tests while shifting recommendations and helper docs toward concrete `Step` usage.

## Rollback
- Revert SDK export additions if downstream import surface needs to be narrowed.
- Revert `ArtifactMap`/`WorkflowResult` public result-model changes independently from sentinel and cleanup work if downstream compatibility fails.
- Disable retention cleanup by defaulting to `RetentionPolicy.keep_all()` temporarily if deletion behavior is suspect during rollout.
