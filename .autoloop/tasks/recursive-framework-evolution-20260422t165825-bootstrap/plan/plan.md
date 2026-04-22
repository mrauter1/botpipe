# Recursive Framework Evolution Plan

## Objective

- Deliver the requested greenfield redesign without preserving legacy CLI, package, config, layout, or wire compatibility.
- Preserve or improve feature compatibility: pause/resume, checkpoint recovery, tracing, git tracking, workflow composition, reusable workflow packages, and Autoloop-v1 operational parity.
- Treat `autoloop` as the canonical public CLI name. The `flowpath` text in the appended standalone CLI block is illustrative only.
- Plan from the current repository state: `core/` and the root `workflow/` shim already exist, but runtime/workspace/loader/git/docs/tests still implement large parts of the legacy contract.

## Current Baseline To Replace

- `runtime/cli.py` still exposes raw workflow targeting, `--class-name`, `--request-text`, `--resume`, and `intent_mode`.
- `runtime/loader.py` still loads raw file/module targets and discovers workflow classes heuristically.
- `runtime/workspace.py` still creates `tasks/<task>/runs/<run>` and retains `.superloop` resume logic.
- `runtime/runner.py` and `runtime/stores/filesystem.py` still assume task-scoped runs and legacy request/answer semantics.
- `core/context.py`, `core/extensions.py`, and artifact resolution only know `task_folder` and `run_folder`.
- `extensions/git/*` still scopes tracking to `task_folder`.
- `workflows/` is not yet a package-of-packages; it still holds framework-owned Autoloop-v1 parity helpers.
- Docs and tests still pin the pre-greenfield contract, including `run_autoloop_v1(...)`, task-scoped git tracking, raw-target CLI usage, and legacy compatibility language. Some tests also reference legacy top-level workflow files that are not present in this checkout.

## Non-Negotiable Invariants

- Public execution is workflow-package-based only; there is no public raw module/file/class execution mode.
- The strict authoring surface remains the root `workflow` shim plus `workflow.primitives`; tests/docs should treat that as the contract, not `autoloop_v3.workflow.*` internals.
- `workflows/` is the canonical package root for runnable and reusable workflow packages.
- Mutable runtime data lives only under task/workflow/run scopes, never under workflow package directories.
- `run_id` remains a first-class stable runtime concept even when users omit it from normal CLI usage.
- Capability compatibility is required; legacy quirks and wire formats are not.

## Target Interfaces

### Package And Discovery Contract

- Keep the internal kernel in `core/`.
- Keep `workflow/` as a strict re-export-only authoring shim with only the symbols named in the request.
- Make repo-root `workflows/` a regular package whose contents are actual workflow packages only.
- Require each workflow package to contain `__init__.py`, `workflow.py`, `workflow.toml`, `prompts/`, and `assets/`.
- Require each workflow package `__init__.py` to re-export its main workflow class and optional `Parameters`.
- Discovery scans `<root>/workflows/*/workflow.toml`; canonical workflow name comes from the package directory unless the manifest explicitly overrides it.
- Loader supports two entry forms only:
  - workflow package name or alias for CLI/runtime entry
  - imported workflow class for sub-workflow composition
- Any raw loader that remains temporarily is internal-only and must not be reachable through the public CLI or runtime contract.

### Runtime And Workspace Contract

- Task scope becomes `.autoloop/tasks/<task-id>/` with shared `task.json`, `request.md`, `messages.jsonl`, and top-level task artifacts.
- Workflow scope becomes `.autoloop/tasks/<task-id>/wf_<workflow_name>/` with persistent workflow-level files such as `workflow.json`.
- Run scope becomes `.autoloop/tasks/<task-id>/wf_<workflow_name>/runs/<run-id>/` with `request.md`, `run.json`, `events.jsonl`, `checkpoint.json`, `sessions/`, `trace.jsonl`, optional `raw/`, `children.jsonl`, and `parent.json`.
- `run.json` is the canonical run metadata file and must carry workflow name, task id, run id, status, timestamps, resolved workflow params, request snapshot reference, and parent linkage when present.
- New runs append to task `messages.jsonl`, refresh task `request.md`, and write an immutable run-local `request.md` snapshot.
- Resume logic, store paths, tracing, and status inspection must resolve within workflow scope rather than scanning flat task-scoped runs.
- No in-place compatibility migration is required for legacy `.superloop` data or old `.autoloop/tasks/<task>/runs/<run>` layouts.

### Context, Binding, Placeholder, And Prompt Contract

- Extend `Context` with `workflow_name`, `workflow_folder`, `package_folder`, `workflow_params`, and `invoke_workflow(...)`.
- Keep `task_id`, `run_id`, `task_folder`, `run_folder`, `state`, session accessors, and `answer`.
- Extend `RunBinding` with `workflow_folder` and `package_folder`.
- Add placeholders `{workflow_folder}`, `{package_folder}`, and `{workflow_name}` while keeping `{task_folder}`, `{run_folder}`, and `{state.*}`.
- `package_folder` is read-only package content; mutable artifacts must never be written there.
- Relative prompt and asset resolution order is:
  1. workflow package root
  2. explicit absolute path
  3. never current working directory

### CLI And Workflow Parameter Contract

- Public command tree is:
  - `autoloop workflows list`
  - `autoloop workflows show <workflow>`
  - `autoloop run <workflow> <task-id> --message "..."`
  - `autoloop resume <workflow> <task-id> [--run-id <run-id>]`
  - `autoloop answer <workflow> <task-id> --answer "..." [--run-id <run-id>]`
  - `autoloop runs list [--workflow <workflow>] [--task <task-id>] [--status <status>]`
  - `autoloop runs show <workflow> <task-id> [--run-id <run-id>]`
  - `autoloop logs <workflow> <task-id> [--run-id <run-id>] [--events|--trace|--raw]`
  - `autoloop init workflow <name>`
- Remove the public `exec` surface, public raw workflow targets, public `--class-name`, and public request/intent terminology.
- `run` requires `--message`; `answer` requires `--answer`; `resume` and diagnostics must not create new runs.
- `-wf <name> <value>` is repeatable, ordered, workflow-validated, persisted to run metadata, and immutable for the life of the run.
- If a workflow does not export `Parameters`, any `-wf` usage for that workflow fails before execution starts.
- Omitted `--run-id` resolves deterministically by command-specific rules; ambiguous or missing candidates fail clearly.

### Sub-Workflow And Parity Contract

- `ctx.invoke_workflow(...)` accepts either a workflow package name or an imported workflow class.
- Child workflows run under the same `task_id` but receive their own `workflow_name`, `workflow_folder`, `run_id`, run-local request snapshot, checkpoint, sessions, trace, and event log.
- Parent-child linkage is metadata only:
  - parent run writes `children.jsonl`
  - child run writes `parent.json`
- `StepFinish` must carry producer raw output and optional verifier raw output so workflow-owned parity code can reconstruct raw logs without a provider wrapper or special harness.
- Autoloop-v1 must live under `workflows/autoloop_v1/` and run through the general runtime path only; framework-owned parity modules and `run_autoloop_v1(...)` are deleted after migration.

### Git And Config Cleanup

- Git tracking default scope changes from `task_folder` to `workflow_folder`.
- Helper names, filters, and tests should be renamed to reflect workflow-scoped behavior.
- Remove compatibility-only config discovery, status values, layout probing, and payload parsing unless the behavior still serves the new architecture on its own merits.

## Milestones

1. Workflow package foundation
   - Convert `workflows/` into the canonical workflow package namespace.
   - Add manifest-based discovery, alias resolution, and strict `__init__.py` export enforcement.
   - Keep the root `workflow` shim strict and minimal.
2. Runtime workspace and context migration
   - Move runtime persistence to task -> workflow -> runs.
   - Add `messages.jsonl`, run metadata, new placeholders, context fields, binding fields, and package-root prompt resolution.
3. Public CLI and workflow parameters
   - Replace the raw-target CLI with the package-based `autoloop` command tree.
   - Add deterministic run lookup and validated `-wf` parsing/persistence.
4. Sub-workflows, parity migration, and git scope
   - Add `ctx.invoke_workflow(...)`, child run metadata, `StepFinish` raw-output enrichment, Autoloop-v1 package migration, and workflow-scoped git tracking.
5. Docs, tests, and legacy removal
   - Rewrite docs and tests to the new contract and remove compatibility-only code paths that no longer serve the redesign.

## Regression Prevention And Validation

- Add or replace tests for all requested acceptance surfaces:
  - workflow package discovery from repo-root `workflows/`
  - required `__init__.py` export contract
  - direct workflow-to-workflow imports
  - package-based CLI commands
  - `-wf` parsing and validation
  - task -> workflow -> runs workspace creation
  - task `messages.jsonl`
  - immutable run `request.md` snapshots
  - package-root prompt resolution
  - new placeholder resolution
  - class-based and name-based sub-workflow invocation
  - parent-child linkage metadata
  - workflow-folder git tracking
  - run-local tracing
  - Autoloop-v1 parity via package-local code only
  - strict root `workflow` shim surface
- Replace stale tests that reference removed legacy workflow files or `run_autoloop_v1(...)`; they are not compatibility requirements.
- Land code, docs, and tests together for each public-contract change so the branch never describes two conflicting runtime models at once.

## Compatibility, Migration, And Rollback Notes

- Intentional behavior breaks allowed by the request:
  - remove raw-target CLI usage
  - remove public `--class-name`
  - remove public request/intent terminology
  - remove compatibility-only `.superloop` and old-layout resume behavior
  - remove framework-owned parity modules and custom Autoloop-v1 harness
  - narrow default git tracking from task scope to workflow scope
- No backward-compatible data migration is required for old run/session/config payloads unless a specific behavior is re-justified by the new architecture.
- Rollout should be phase-local and revertible by commit:
  - do not support both old and new public CLI surfaces in parallel
  - do not leave mixed flat-run and workflow-scoped runtime layouts active at the same time
  - if a phase fails validation, revert that phase’s commit rather than adding shims

## Risk Register

- Discovery drift
  - Risk: manifest metadata, package names, aliases, and `__init__.py` exports disagree.
  - Control: enforce one loader path and dedicated discovery tests.
- Workspace migration bugs
  - Risk: resume/log/status code reads the wrong run after introducing workflow scope.
  - Control: centralize path resolution in workspace/runtime helpers and test every command-specific run lookup rule.
- Prompt resolution regressions
  - Risk: existing relative prompts silently start resolving from cwd or task folders.
  - Control: route all relative prompt resolution through package-root-aware registry tests.
- Parameter validation gaps
  - Risk: `-wf` values leak into generic runtime config or mutate during resume.
  - Control: separate parser paths, persist resolved params in `run.json`, and reject unknown params before execution.
- Sub-workflow persistence bugs
  - Risk: child runs inherit parent sessions implicitly or land in nested folders.
  - Control: explicit child run creation API, dedicated parent/child metadata tests, and no nested run directories.
- Autoloop-v1 parity loss
  - Risk: raw logs, session naming, clarification persistence, or status mapping drift during package migration.
  - Control: migrate parity after `StepFinish` enrichment and preserve package-local parity tests as a release gate.
- Git scope overreach or underreach
  - Risk: workflow-scoped tracking accidentally commits unrelated task files or misses workflow-owned files.
  - Control: rename scope helpers, update filters, and test both inclusive and exclusive deltas.
- Stale documentation/tests masking regressions
  - Risk: old docs and tests keep reintroducing removed compatibility goals.
  - Control: rewrite them in the same phase that removes the legacy surfaces.
