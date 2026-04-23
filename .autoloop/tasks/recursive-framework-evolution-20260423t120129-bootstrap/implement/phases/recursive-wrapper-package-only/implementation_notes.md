# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t120129-bootstrap
- Pair: implement
- Phase ID: recursive-wrapper-package-only
- Phase Directory Key: recursive-wrapper-package-only
- Phase Title: Remove Legacy Recursive Wrapper Paths
- Scope: phase-local producer artifact

## Files changed

- `recursive_autoloop/run_recursive_autoloop.sh`
- `recursive_autoloop/run_recursive_autoloop_templates/bootstrap_task.md.tmpl`
- `recursive_autoloop/run_recursive_autoloop_templates/cycle_task.md.tmpl`
- `recursive_autoloop/run_recursive_autoloop_templates/framework_evolution_charter.md.tmpl`
- `recursive_autoloop/run_recursive_autoloop_templates/framework_roadmap.md.tmpl`
- `recursive_autoloop/run_recursive_autoloop_templates/workflow_authoring_doctrine.md.tmpl`
- `recursive_autoloop/run_recursive_autoloop_templates/workflow_examples.md.tmpl`
- `tests/runtime/test_package_cli.py`
- `.autoloop/tasks/recursive-framework-evolution-20260423t120129-bootstrap/decisions.txt`

## Symbols touched

- `recursive_autoloop.run_recursive_autoloop.sh.record_current_action`
- `recursive_autoloop.run_recursive_autoloop.sh.require_package_autoloop_cli`
- `recursive_autoloop.run_recursive_autoloop.sh.emit_direct_resume_hint`
- `recursive_autoloop.run_recursive_autoloop.sh.run_autoloop_start_cli`
- `recursive_autoloop.run_recursive_autoloop.sh.run_autoloop_resume_cli`
- `recursive_autoloop.run_recursive_autoloop.sh.run_autoloop_start`

## Checklist mapping

- Plan Phase 4 / package-only wrapper invocation: removed legacy CLI mode detection and made start/resume helpers emit only package `autoloop run/resume` calls.
- Plan Phase 4 / keep architecture-neutral recovery behavior: preserved nested-git scoping, task discovery, resumable-run detection, and recovery guidance while dropping obsolete pair/intent plumbing.
- Plan Phase 4 / rewrite recursive templates: updated bootstrap, cycle, charter, roadmap, doctrine, and examples templates to current repo layout and package-CLI doctrine.
- Plan Phase 4 / strengthen wrapper tests: expanded file-content tests to forbid legacy wrapper strings and stale `src/autoloop/...` guidance while requiring current package-layout language.

## Assumptions

- Checking `autoloop --help` for the package-command surface (`workflows`, `runs`, `answer`) is sufficient for the wrapper’s fail-fast validation.
- `last_action.env` is wrapper-private state, so dropping `pair_selection` metadata is acceptable once package-only runs no longer accept pair-selection flags.

## Preserved invariants

- Nested-git environment isolation remains intact through `run_autoloop_binary(...)`.
- Recovery hints, bootstrap/cycle task generation, and resumable-run detection still behave as before.
- The wrapper still drives the configured workflow name under the same workspace root.

## Intended behavior changes

- The recursive wrapper no longer detects or supports legacy CLI modes.
- Start/resume execution and direct recovery hints now use only package `autoloop run/resume` commands.
- Recursive templates now direct future cycles to the current `docs/`, `core/`, `runtime/`, `extensions/`, `stdlib/`, and `workflows/` layout.

## Known non-changes

- No runtime/provider/session-schema code changed in this phase.
- No active docs under `docs/` changed in this phase; the template rewrite is limited to the recursive wrapper assets.

## Expected side effects

- The wrapper now fails fast when the installed `autoloop` does not expose the package CLI surface.
- Future recursive tasks will no longer instruct readers to inspect nonexistent `src/autoloop/...` files or to preserve legacy CLI syntax.

## Validation performed

- `./.venv/bin/python -m pytest tests/runtime/test_package_cli.py`
- `./.venv/bin/python -m pytest`

## Deduplication / centralization decisions

- Centralized the package-only CLI guard in `require_package_autoloop_cli(...)` instead of leaving legacy detection branches across multiple helper functions.
- Kept wrapper/template contract enforcement in `tests/runtime/test_package_cli.py` rather than introducing a separate one-off scanner for this phase.
