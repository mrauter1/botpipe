# Recursive Framework Evolution Plan

## Scope

- Authoritative source is the immutable request snapshot at `.autoloop/tasks/recursive-framework-evolution-20260422t162807-bootstrap/runs/run-20260422T192808Z-bb1c3640/request.md`; there are no later clarification entries in the raw log.
- This is a greenfield redesign: wire compatibility may break, but capability compatibility may not.
- Feature parity that must survive the redesign includes pause/resume/answer, checkpointed recovery, tracing, git tracking, workflow composition, package-local prompt/assets, and Autoloop-v1 operational parity artifacts.

## Baseline Findings

- `workflow/` currently serves as both the internal kernel and the authoring import surface, so the `autoloop_v3.workflow` to `autoloop_v3.core` move must preserve `from workflow import ...` without leaving internals exposed.
- `runtime/cli.py` and `runtime/runner.py` still expose raw module/path/class execution, `--class-name`, `--request-text`, and `intent_mode`.
- `runtime/workspace.py` still writes `.autoloop/tasks/<task-id>/runs/<run-id>` and contains legacy `.superloop`, `context.md`, and request-merging logic.
- `runtime/prompts.py` resolves relative prompts from the workflow file directory and then the runtime root, so package-root prompt semantics do not exist yet.
- Repo-root `workflows/` currently contains framework-owned parity helpers only; the runnable workflows referenced by tests live outside the repo root today at `../autoloop_v1.py` and `../Ralph_loop.py`.
- `extensions/git` still scopes commits to `task_folder`, and Autoloop-v1 parity still depends on framework-owned `run_autoloop_v1(...)`.
- Tests and docs actively pin the old namespace, old layout, retained compatibility behavior, and the special Autoloop-v1 harness, so the redesign must rewrite the test/doc corpus rather than patching code only.

## Design Invariants

- `autoloop_v3.core` becomes the only internal kernel package; `workflow/` remains a strict authoring shim only.
- Repo-root `workflows/` is reserved for real workflow packages and remains a regular package with `__init__.py`.
- Each workflow package is importable as a regular package at its real directory path under `workflows/` and must contain `__init__.py`, `workflow.py`, and `workflow.toml`.
- Workflow directory name is the default discovery key, and `workflow.toml.name` may override the CLI/runtime workflow key when explicitly set by the package.
- Manifest overrides must map back to the scanned package directory without adding authoring-time import shims; direct Python imports continue to use the real package path.
- `aliases` remain discovery metadata for list/show output unless a later clarification explicitly promotes them to execution keys.
- Package-local prompts and assets resolve relative to the workflow package root; mutable artifacts never write into `package_folder`.
- Workspace scopes are strict: task scope is shared across workflows, workflow scope persists across runs of one workflow on one task, and run scope holds immutable or run-local artifacts only.
- Child workflow invocation is metadata-linked rather than folder-nested and never inherits parent sessions implicitly.
- Git tracking defaults to workflow scope, not task scope.

## Implementation Phases

### 1. Core Package Split And Strict Shim

- Move the implementation currently under `workflow/` to `core/`.
- Rewrite `workflow/__init__.py` and `workflow/primitives.py` as strict re-export shims for the authoring surface only.
- Update runtime, extensions, stdlib, docs, and tests to import internal types from `autoloop_v3.core.*`.
- Keep `workflow` root exports limited to `Workflow`, `Context`, `Session`, `Artifact`, `Prompt`, `PairStep`, `LLMStep`, `SystemStep`, `SUCCESS`, `PAUSE`, `FAIL`, `GLOBAL`, and `workflow.primitives` exports.
- Regression control: add/refresh tests that fail if engine/compiler/provider/store internals leak back through `workflow`.

### 2. Workflow Package Discovery And Package Migration

- Convert repo-root `workflows/` into the real workflow namespace and remove framework-owned parity modules from it.
- Migrate the current runnable workflows into packages:
- `../autoloop_v1.py` -> `workflows/autoloop_v1/`
- `../Ralph_loop.py` -> `workflows/ralph_loop/`
- Introduce manifest discovery in `runtime/loader.py` by scanning `<root>/workflows/*/workflow.toml`.
- Enforce the package contract: required files exist, `__init__.py` re-exports the main workflow class, optional `Parameters` export is discoverable, manifest `name` may override the discovered workflow key, and aliases remain metadata rather than extra execution targets.
- Resolve manifest overrides through the discovery map back to the scanned package directory; do not create alias/shim packages to manufacture new import paths.
- Update prompt resolution to search package root first and never fall back to cwd-relative behavior.
- Regression control: direct imports such as `from workflows.autoloop_v1 import AutoloopV1` and `from workflows.ralph_loop import RalphLoop` must be part of the test suite.

### 3. Workspace, Message Ledger, And Binding Expansion

- Replace task-level layout `tasks/<task>/runs/<run>` with `tasks/<task>/wf_<workflow>/runs/<run>`.
- Introduce explicit workspace types:
- `TaskWorkspace`: `task.json`, `request.md`, `messages.jsonl`, shared task files
- `WorkflowWorkspace`: `workflow.json`, workflow folder, workflow `runs/`
- `RunWorkspace`: `run.json`, `request.md`, `events.jsonl`, `checkpoint.json`, `sessions/`, `trace.jsonl`, `raw/`, `children.jsonl`, optional `parent.json`
- Replace public request/intent semantics with a message model:
- `autoloop run ... --message "..."`
- task scope appends to `messages.jsonl`
- task scope renders current `request.md`
- run scope snapshots immutable `request.md`
- Extend artifact placeholders, `Context`, and `RunBinding` with `workflow_name`, `workflow_folder`, `package_folder`, and `workflow_params`.
- Keep `task_folder`, `run_folder`, `state`, `run_id`, and session accessors intact.
- Regression control: write integration tests for new path creation, immutable request snapshots, placeholder rendering, and run-local session/checkpoint/trace persistence.

### 4. Package-Based CLI And Workflow Parameters

- Replace the current raw-target parser with the required package-only command tree:
- `autoloop workflows list`
- `autoloop workflows show <workflow>`
- `autoloop run <workflow> <task-id> --message "..."`
- `autoloop resume <workflow> <task-id> [--run-id ...]`
- `autoloop answer <workflow> <task-id> --answer "..." [--run-id ...]`
- `autoloop runs list ...`
- `autoloop runs show ...`
- `autoloop logs ...`
- `autoloop init workflow <name>`
- `autoloop run` requires `--message` and accepts repeatable `-wf <name> <value>` pairs.
- `autoloop runs show` and `autoloop logs` default to the latest relevant run for the workflow/task; `--run-id` stays diagnostic or advanced rather than normal-path required.
- `autoloop logs` must expose mutually exclusive `--events`, `--trace`, and `--raw` selectors.
- Remove public raw execution, public `--class-name`, and public raw module/file/class targeting.
- Add repeatable `-wf <name> <value>` parsing, ordered collection, workflow-specific validation/coercion through optional package `Parameters`, rejection of any `-wf` usage when no `Parameters` model exists, and persistence of resolved parameters in `run.json`.
- Keep provider/runtime controls separate from workflow parameters so `-wf` cannot override generic runtime/provider options.
- Define the surviving typed config contract in the same phase: optional `autoloop.yaml` at repo root and user config dir, provider/runtime controls only, no `intent_mode`, no request-merging semantics, and no `superloop.*` discovery.
- Regression control: CLI integration tests must cover ambiguous resume selection, latest resumable run resolution, and `-wf` failure modes for unknown or invalid parameters.

### 5. Sub-Workflow Invocation And Autoloop-v1 Parity Migration

- Add an internal workflow invoker service used by runtime-backed `Context.invoke_workflow(...)`.
- Support both invocation forms:
- `ctx.invoke_workflow("child_workflow", message="...", parameters={...})`
- `ctx.invoke_workflow(ChildWorkflow, message="...", parameters={...})`
- Introduce a small structured return type, `WorkflowInvocationResult`, with at least `workflow_name`, `run_id`, `terminal_status`, `last_event`, `workflow_folder`, `run_folder`, and selected output references.
- Create child run metadata without physical nesting:
- parent run writes `children.jsonl`
- child run writes `parent.json`
- child workflow uses the same `task_id` but its own `wf_<workflow>/runs/<run-id>`
- Enrich `StepFinish` with `producer_raw_output` and `verifier_raw_output` so workflow-package-owned parity code can rebuild raw logs without a special provider wrapper.
- Migrate Autoloop-v1 into `workflows/autoloop_v1/` with package-local `parity.py` and `conventions.py`; delete framework-owned `autoloop_v3.workflows.autoloop_v1_*` and `run_autoloop_v1(...)`.
- Regression control: add integration coverage for class-based and name-based child invocation, parent/child metadata, and Autoloop-v1 parity artifacts (`sessions/plan.json`, `sessions/phases/*.json`, `raw_phase_log.md`, `decisions.txt`, question/blocked/failed mapping).

### 6. Workflow-Scoped Git, Documentation Rewrite, And Legacy Cleanup

- Change git tracking helpers and defaults from task scope to workflow scope and update tests to prove commits stay inside `workflow_folder` unless a policy narrows further.
- Rewrite docs to describe `autoloop_v3.core`, workflow packages, package-based CLI, message-first runtime semantics, task -> workflow -> runs layout, and greenfield compatibility stance.
- Remove compatibility-only runtime behavior that the redesign explicitly abandons:
- `.superloop` state root fallback
- `superloop.*` config discovery
- `intent_mode` and `request_text` merge semantics
- legacy `thread_id` session-payload handling
- compatibility-only status mappings and old public loaders
- Replace tests that pin old behavior with the requested new coverage matrix.
- Regression control: add a final grep gate over runtime/docs/tests for forbidden public surfaces such as `autoloop_v3.workflow` as internal kernel, `autoloop_v3.workflows` framework ownership, raw-target CLI flags, and `run_autoloop_v1`.

## Interface Definitions

### Discovery / Loader

- Add a `DiscoveredWorkflow` record in `runtime/loader.py` with at least `name`, `package_dir`, `module_name`, `workflow_module`, `workflow_class_name`, `aliases`, `description`, and `parameters_model`.
- Canonical discovery API:
- `discover_workflows(root: Path) -> dict[str, DiscoveredWorkflow]`
- `load_workflow_package(root: Path, workflow_name: str) -> DiscoveredWorkflow`
- `resolve_workflow_target(target: str | type[Workflow]) -> DiscoveredWorkflow`
- `DiscoveredWorkflow` should carry both the discovered workflow key and the actual package directory/module path so manifest overrides do not require import-path shims.
- Discovery key defaults to the package directory name and may be overridden by `workflow.toml.name`; aliases stay descriptive metadata rather than additional execution keys.
- Reject packages missing required files or violating the `__init__.py` export contract before execution starts.

### Workspace / Metadata

- `task.json` stores task identity and current rendered request metadata only.
- `messages.jsonl` is append-only and records task messages and answers with timestamps and origin metadata.
- `workflow.json` stores workflow-level metadata needed across runs on the same task, including canonical workflow name and package location reference.
- `run.json` stores canonical run metadata including `task_id`, `workflow_name`, `run_id`, terminal status, immutable launch message, resolved `workflow_params`, and parent linkage when present.
- `logs` and `runs show` read from `run.json`, `events.jsonl`, `trace.jsonl`, and run/request snapshots instead of reconstructing state from legacy layouts.

### Context / Invocation

- `Context` gains `workflow_name`, `workflow_folder`, `package_folder`, `workflow_params`, and `invoke_workflow(...)`.
- `RunBinding` gains `workflow_folder` and `package_folder` while keeping `root`, `task_id`, `run_id`, `workflow_name`, `task_folder`, and `run_folder`.
- `StepFinish` gains `producer_raw_output` and `verifier_raw_output`.
- `Context.invoke_workflow(...)` should accept only runtime-backed contexts; calling it from contexts without an attached invoker should raise a clear runtime error rather than silently no-op.

### Prompt / Asset Resolution

- `Prompt("prompts/ask.md")` resolves relative to `package_folder`.
- Explicit absolute paths remain supported when authors opt in explicitly.
- Runtime must never look in cwd for relative prompts or assets.

### Runtime / Config

- Post-redesign runtime keeps one typed config contract in `autoloop.yaml`, loaded from `~/.config/autoloop/autoloop.yaml` and overridden by repo-root `autoloop.yaml` when both exist.
- The config schema stays small and typed: provider selection, provider model/effort controls, and runtime policy such as `max_steps`; workflow parameters never live in config and `intent_mode` is removed.
- CLI flags override config, and `-wf` never overrides runtime/provider controls.
- `autoloop.config` and all `superloop.*` filenames are intentionally dropped; migration is manual rewrite/rename rather than compatibility loading.
- Rollback safety: ship the new config contract and its tests before deleting the old discovery code, and revert the parser/docs/tests together if the new contract proves incomplete.

## Compatibility And Migration Notes

- Intentional behavior breaks, all explicitly permitted by the request:
- public CLI becomes package-based only
- internal kernel package moves to `autoloop_v3.core`
- framework-owned `autoloop_v3.workflows` disappears
- runtime layout changes to task -> workflow -> runs
- session/checkpoint/config payload compatibility is dropped when it only exists for legacy wire support
- `autoloop.yaml` becomes the sole surviving config filename; `autoloop.config` and `superloop.*` are removed as part of the greenfield cutover
- There is no planned runtime migration path for old `.autoloop` or `.superloop` state. Old runs become archival once the redesign lands.
- Config migration is explicit and manual: users either rewrite existing runtime settings into the new `autoloop.yaml` schema or run with CLI defaults/flags only.
- Existing workflows must move into repo-root packages before the raw-target CLI is removed, otherwise capability compatibility would regress.

## Validation Strategy

- Unit coverage:
- strict `workflow` shim exports only the approved authoring surface
- manifest validation and loader discovery
- placeholder resolution for `workflow_folder`, `package_folder`, and `workflow_name`
- workflow-parameter coercion and rejection rules
- typed config parsing/merging for the surviving `autoloop.yaml` contract
- Contract coverage:
- `Context.invoke_workflow(...)` return contract and failure behavior
- `RunBinding` / `StepFinish` extension events include the new fields
- prompt resolution prefers package root over cwd
- Runtime integration coverage:
- all package-based CLI commands
- `autoloop run` requiring `--message`, `logs` mode selectors, and latest-run defaulting for `runs show` / `logs`
- task/workflow/run workspace creation and resume/answer behavior
- parent/child metadata links without nested folders
- Autoloop-v1 parity artifacts via the general runtime only
- workflow-scoped git tracking and run-local tracing
- Doc/test hygiene:
- rewrite docs and assertions together
- add grep-style guards for removed public terms and compatibility-only behavior

## Risk Register

| Risk | Why it matters | Mitigation |
| --- | --- | --- |
| `workflow` -> `core` split leaks or breaks imports | The same package currently serves internal and public roles | Move implementation first, then replace `workflow` with thin re-exports and add explicit shim-surface tests |
| Workflow naming drifts between discovery key, manifest override, and package path | Direct imports and CLI discovery become inconsistent | Track both the discovered workflow key and the real package path, fail on duplicate discovered keys, and test direct imports plus manifest-override lookups together |
| Workspace refactor breaks resume/checkpoint/session lookup | Resume behavior is capability-critical | Introduce `WorkflowWorkspace` explicitly, keep run-local checkpoint/session ownership, and add end-to-end run/resume/answer coverage before deleting old layout |
| Config cleanup strands provider/runtime controls | The redesign removes legacy config names and fields while keeping typed runtime config as a supported interface | Define one canonical `autoloop.yaml` contract, test CLI/config precedence, document manual migration, and remove legacy discovery only after the new parser is covered |
| Child invocation causes nested-folder or session-leak regressions | Sub-workflows are a first-class requirement | Centralize child-run creation in one invoker service, persist parent/child metadata only, and prohibit implicit session inheritance |
| Autoloop-v1 parity regresses after removing the special harness | This is the strongest operational compatibility requirement in the request | Add raw outputs to `StepFinish`, migrate parity code into the package, and prove parity artifacts through integration tests before deleting `run_autoloop_v1(...)` |
| Git tracking commits too much after multi-workflow tasks arrive | Task scope becomes overly broad under the new layout | Rename helpers around workflow scope, default to `workflow_folder`, and test commit pathspecs against multi-workflow tasks |
| Legacy strings remain in docs/tests and mask real regressions | The public contract is changing everywhere at once | Finish with a repository-wide forbidden-surface sweep after code, docs, and tests are all updated |

## Rollout And Rollback

- Land the redesign in the six ordered phases above; do not intermingle package discovery, workspace migration, and CLI removal in one unverified step.
- Do not delete the old raw-target runtime path until packaged workflows, new workspace layout, and package-based CLI tests are already green in the branch.
- Roll back only at phase boundaries by reverting the incomplete slice and its tests/docs together; avoid hybrid states where old docs describe new code or old runtime paths coexist publicly with the new CLI.
