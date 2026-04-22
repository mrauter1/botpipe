# Implementation Notes

- Task ID: recursive-framework-evolution-20260422t165825-bootstrap
- Pair: implement
- Phase ID: package-cli-and-params
- Phase Directory Key: package-cli-and-params
- Phase Title: Package CLI And Parameters
- Scope: phase-local producer artifact

## Files changed

- `runtime/cli.py`
- `runtime/loader.py`
- `runtime/runner.py`
- `runtime/workspace.py`
- `recursive_autoloop/run_recursive_autoloop.sh`
- `tests/runtime/test_package_cli.py`
- `.autoloop/tasks/recursive-framework-evolution-20260422t165825-bootstrap/decisions.txt`

## Symbols touched

- `runtime.cli.build_arg_parser`
- `runtime.cli.main`
- `runtime.loader.WorkflowParameterError`
- `runtime.loader.WorkflowParameterField`
- `runtime.loader.workflow_parameter_fields`
- `runtime.loader.validate_workflow_parameters`
- `runtime.cli._resolve_provider`
- `runtime.runner.RunExecution`
- `runtime.runner.execute_workflow`
- `runtime.runner.execute_workflow_package`
- `runtime.workspace.RunRecord`
- `runtime.workspace.list_run_records`
- `runtime.workspace.resolve_run_record`

## Checklist mapping

- CLI subcommand tree: implemented in `runtime/cli.py`
- `-wf` parsing / validation / persistence: implemented via `runtime.loader.validate_workflow_parameters(...)` and `run.json` persistence through existing runner metadata writes
- public executable provider resolution: restored via `runtime.cli._resolve_provider(...)` and mutating-command `--provider-factory`
- deterministic run lookup for `resume` / `answer` / diagnostics: implemented in `runtime.workspace.resolve_run_record(...)`
- `init workflow` scaffolding: implemented in `runtime/cli.py`
- repo-owned recursive caller migration to package CLI: implemented in `recursive_autoloop/run_recursive_autoloop.sh`
- CLI tests for routing / errors / run selection / scaffolding: added in `tests/runtime/test_package_cli.py`

## Assumptions

- Default read-only and mutating command output may be JSON as long as it is deterministic and concise.
- Generic runtime/provider flags may remain on package-based commands when they do not reintroduce raw workflow targeting; `--provider-factory` is treated as that kind of generic runtime flag.
- A workflow package’s compiled workflow `name` must match manifest discovery metadata to keep workspace paths and CLI identifiers coherent.

## Preserved invariants

- Internal raw loader support remains available for non-CLI/runtime internals; only the public CLI surface was cut over.
- Resumed runs still preserve persisted `workflow_params` from `run.json`.
- Workspace layout remains `tasks/<task>/wf_<workflow>/runs/<run>` and diagnostics resolve within that layout only.

## Intended behavior changes

- Public CLI now exposes only package-based `autoloop` commands (`workflows`, `run`, `resume`, `answer`, `runs`, `logs`, `init workflow`).
- Public `--class-name`, `--request-text`, raw workflow targeting, and `--resume` flag usage are removed from the CLI surface.
- `run` now requires `--message`; `answer` now requires `--answer`; `resume` and diagnostics never create new runs.
- `-wf` pairs are validated/coerced through workflow `Parameters` and rejected when unsupported, unknown, or repeated against scalar fields.
- Workflow parameter defaults and resolved values are normalized to JSON-safe forms before CLI output or `run.json` persistence.
- Mutating package CLI commands accept a public `--provider-factory module:function` generic runtime flag so the executable path remains usable without private injection.
- The recursive wrapper now invokes `autoloop run autoloop_v1 ...` and `autoloop resume autoloop_v1 ...` instead of removed legacy flags.

## Known non-changes

- Real config-backed provider backend implementations were not added in this phase; mutating CLI commands still rely on a provider factory, now via public `--provider-factory`, internal test injection, or `AUTOLOOP_PROVIDER_FACTORY`.
- Autoloop-v1 still has package-local parity code and custom harness code paths; this phase did not relocate or delete them.
- Docs outside the active runtime/package CLI surfaces were not rewritten in this phase-local change set.

## Expected side effects

- `workflows show` now fails fast when manifest metadata and compiled workflow names disagree.
- Run inspection commands read `run.json` and checkpoint presence instead of inferring status from flat legacy paths.
- Typed workflow parameter models using values such as `Path`, `datetime`, `Enum`, sets, or nested models now render and persist without JSON serialization failures.

## Validation performed

- `python3 -m py_compile runtime/cli.py runtime/loader.py runtime/workspace.py runtime/runner.py tests/runtime/test_package_cli.py`
- `bash -n recursive_autoloop/run_recursive_autoloop.sh`
- Attempted runtime smoke validation with `python3`; blocked because the environment does not have project dependencies such as `pydantic` and does not have `pytest` installed.

## Deduplication / centralization decisions

- Kept workflow parameter coercion in `runtime.loader` so CLI/run callers and future sub-workflow code can share one validation path.
- Kept workflow parameter JSON-safe normalization in `runtime.loader` alongside validation so CLI display and `run.json` persistence share one conversion boundary instead of adding ad hoc JSON encoders elsewhere.
- Kept run listing and command-specific latest-run resolution in `runtime.workspace` so `resume`, `answer`, `runs show`, and `logs` share one selector implementation.
