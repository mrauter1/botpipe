# Test Strategy

- Task ID: recursive-framework-evolution-20260423t120129-bootstrap
- Pair: test
- Phase ID: recursive-wrapper-package-only
- Phase Directory Key: recursive-wrapper-package-only
- Phase Title: Remove Legacy Recursive Wrapper Paths
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Wrapper package-only invocation:
  - `tests/runtime/test_package_cli.py::test_recursive_wrapper_targets_the_package_cli_contract`
  - Covers absence of `AUTOLOOP_CLI_MODE`, `detect_autoloop_cli_mode`, `--intent`, `--pairs`, and legacy branches.
  - Covers emitted package-only `autoloop run/resume` commands and the package-style direct resume hint.
- Wrapper fail-fast guard:
  - `tests/runtime/test_package_cli.py::test_recursive_wrapper_targets_the_package_cli_contract`
  - Covers presence of `require_package_autoloop_cli(...)`, the expected `workflows` / `runs` / `answer` help-surface check, the fatal failure message, and the top-level invocation of that guard.
- Recursive template repo-layout doctrine:
  - `tests/runtime/test_package_cli.py::test_recursive_templates_reference_current_package_repo_layout_only`
  - Covers absence of `src/autoloop/...` and removed `docs/autoloop_workflow_framework_*` paths.
  - Covers required current-layout/package-CLI guidance across bootstrap, cycle, charter, roadmap, doctrine, and examples templates.

## Preserved invariants checked

- The wrapper still emits recovery guidance through a direct package `autoloop resume` hint.
- The maintained recursive templates still mention the current package workflow structure, workflow composition, and greenfield/feature-compatibility stance.

## Edge cases and failure paths

- Failure path covered by source assertion: wrapper aborts when `autoloop --help` does not expose the package CLI surface.
- Edge case covered by source assertion: forbidden `--task-id` is still allowed only in wrapper-owned `--task-id-prefix`, not in emitted autoloop commands.

## Flake risk and stabilization

- Tests are deterministic source inspections only; they do not depend on PATH, shell execution, network, timestamps, or filesystem ordering.
- Validation runs remain stable with `./.venv/bin/python -m pytest tests/runtime/test_package_cli.py tests/strictness/test_no_compat.py tests/test_architecture_baseline_docs.py` plus full `./.venv/bin/python -m pytest`.

## Known gaps

- The shell wrapper is not executed end-to-end under a mocked `autoloop` binary in this phase.
- Nested-git environment isolation and resumable-run discovery remain covered indirectly by untouched behavior, not by new phase-specific tests.
