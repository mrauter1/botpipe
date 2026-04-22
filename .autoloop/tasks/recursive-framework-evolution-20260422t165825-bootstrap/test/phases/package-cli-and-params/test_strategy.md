# Test Strategy

- Task ID: recursive-framework-evolution-20260422t165825-bootstrap
- Pair: test
- Phase ID: package-cli-and-params
- Phase Directory Key: package-cli-and-params
- Phase Title: Package CLI And Parameters
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Public package CLI surface:
  `tests/runtime/test_package_cli.py::test_cli_help_exposes_package_commands_only`
  Covers the command tree and guards against legacy raw-target flags in the public parser help.
- Workflow discovery and resolution:
  `tests/runtime/test_package_cli.py::test_cli_workflows_show_reports_parameters_and_aliases`
  `tests/runtime/test_package_cli.py::test_cli_workflow_resolution_prefers_canonical_names_and_rejects_ambiguous_aliases`
  Covers metadata rendering, canonical-name precedence over alias matches, and ambiguous alias failure behavior.
- Workflow parameter validation and persistence:
  `tests/runtime/test_package_cli.py::test_cli_serializes_typed_workflow_parameters_as_json_safe_values`
  `tests/runtime/test_package_cli.py::test_cli_rejects_invalid_or_unsupported_workflow_params`
  Covers typed default serialization, run metadata persistence, unsupported `-wf`, duplicate scalar params, and unknown params.
- Mutating command contract:
  `tests/runtime/test_package_cli.py::test_cli_mutating_commands_accept_public_provider_factory_flag`
  `tests/runtime/test_package_cli.py::test_cli_run_resume_answer_and_diagnostics_follow_package_contract`
  `tests/runtime/test_package_cli.py::test_cli_latest_run_selection_and_explicit_run_id_targeting_are_deterministic`
  Covers `run`/`resume`/`answer` summaries, public provider-factory wiring, latest-run selection, explicit `--run-id` targeting, and pause/resume behavior without creating extra runs.
- Read-only command contract:
  `tests/runtime/test_package_cli.py::test_cli_run_resume_answer_and_diagnostics_follow_package_contract`
  `tests/runtime/test_package_cli.py::test_cli_latest_run_selection_and_explicit_run_id_targeting_are_deterministic`
  Covers `runs list`, `runs show`, `logs`, missing raw log failure, and diagnostics against multiple runs.
- Scaffolding and repo-owned caller migration:
  `tests/runtime/test_package_cli.py::test_cli_init_workflow_scaffolds_package_and_rejects_duplicates`
  `tests/runtime/test_package_cli.py::test_recursive_wrapper_targets_the_package_cli_contract`
  Covers package scaffold output and the recursive wrapper’s required `autoloop run/resume` shape.

## Preserved Invariants Checked

- Canonical workflow names win over alias matches.
- Omitted `--run-id` resolves the latest applicable run deterministically.
- Explicit `--run-id` targets the requested run even when a newer candidate exists.
- Wrapper-local `--pairs` / `--full-auto-answers` behavior is intentionally not asserted because explicit clarification removed it from this phase contract.

## Edge Cases And Failure Paths

- Ambiguous alias resolution fails with a resolution error and candidate names.
- Missing raw logs fail with `EXIT_RESOLUTION_ERROR`.
- Unsupported or malformed `-wf` usage fails with `EXIT_USAGE_ERROR`.
- Duplicate `init workflow` targets fail with `EXIT_USAGE_ERROR`.

## Reliability Notes

- All CLI tests use temporary repo roots and local workflow packages only.
- Multi-run selection coverage uses sequential paused runs rather than sleeps or manual timestamp mutation.
- Provider-factory coverage uses a local throwaway module and system-only workflows so no network or model backend is required.

## Known Gaps

- The environment available in this loop does not have `pytest` or project runtime dependencies such as `pydantic`, so validation here is limited to syntax checks rather than executing the test file.
