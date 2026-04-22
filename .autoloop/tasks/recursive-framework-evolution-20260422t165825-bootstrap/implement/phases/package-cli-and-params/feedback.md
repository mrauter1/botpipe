# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260422t165825-bootstrap
- Pair: implement
- Phase ID: package-cli-and-params
- Phase Directory Key: package-cli-and-params
- Phase Title: Package CLI And Parameters
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` — `runtime.loader.validate_workflow_parameters(...)`, `runtime.loader.workflow_parameter_fields(...)`, and `runtime.workspace.update_run_metadata(...)` keep workflow params/defaults in Python mode instead of a JSON-safe form. A workflow such as `class Parameters(BaseModel): output_dir: Path = Path("reports")` or one using `datetime` / `Enum` values will validate successfully, then fail when `run.json` or `workflows show` is emitted because `_write_json(...)` and `_emit_json(...)` call `json.dumps(...)` on non-serializable objects. This breaks AC-3/AC-4 for typed parameter models. Minimal fix: centralize workflow-parameter normalization into one JSON-safe serializer (for example `model_dump(mode="json")` or equivalent normalization helper) and use it for both persisted `run.json` metadata and CLI output.

- IMP-002 `blocking` — `runtime.cli._resolve_provider(...)` removes the old public provider-factory path but does not replace it with any repo-backed provider implementation. In the current tree there is no config-to-provider mapping for the configured `codex` / `claude` names, so `autoloop run`, `resume`, and `answer` fail unless callers inject a private factory or set `AUTOLOOP_PROVIDER_FACTORY` manually. That regresses the executable CLI from “public entrypoint” to “test seam only,” which violates the phase objective and feature-compatibility requirement. Minimal fix: add a real runtime provider resolver behind the public CLI (centralized near `_resolve_provider`) or keep the existing executable path functional until a real provider backend exists.

- IMP-003 `blocking` — repo-owned callers still use the removed CLI surface. `recursive_autoloop/run_recursive_autoloop.sh` continues to invoke `autoloop` with legacy flags such as `--workspace`, `--task-id`, and `--resume`, so the repo’s main recursive driver will immediately fail against the new parser even if the provider issue is fixed. This is a direct operational regression introduced by the CLI cutover. Minimal fix: update repo callers to the new `autoloop run/resume/answer/...` contract or provide a temporary compatibility bridge at one central invocation boundary until those callers are migrated.

## Re-review (Cycle 2)

- IMP-001 resolved — workflow parameter defaults and resolved values now normalize through one JSON-safe loader path, and the added typed-parameter test covers `Path`, `datetime`, and `Enum` cases.

- IMP-002 resolved — mutating package commands now expose a public `--provider-factory module:function` path again, so the executable CLI is no longer limited to private injection or environment-only seams.

- IMP-003 resolved narrowly — the recursive wrapper no longer calls removed top-level flags like `--workspace`, `--task-id`, or `--resume`.

- IMP-004 `blocking` — `recursive_autoloop/run_recursive_autoloop.sh:512-559` updates the wrapper to the new package CLI shape, but it silently drops the old `--pairs "$pair_selection"` and `--full-auto-answers` behavior instead of preserving those controls through an equivalent package-CLI path. The concrete regression is that recursive bootstrap/cycle runs now ignore the wrapper’s requested pair selection and may stop on questions that previously auto-advanced, even though the request explicitly forbids feature regressions. Minimal fix: preserve those wrapper behaviors through a supported new-CLI mapping at one central boundary, such as explicit generic runtime flags or validated workflow parameters that the target workflow actually consumes, rather than just deleting the controls during the migration.
