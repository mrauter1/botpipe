# Gap Report

## Original intent considered

- The immutable request required a `tests/`-only follow-up that:
  1. repaired retained split tests so underscore-prefixed helpers from `_shared.py` were imported explicitly instead of leaking through `from ... import *`,
  2. updated `tests/strictness/test_no_compat.py` for the removed `tests/contract/test_engine_contracts.py` monolith,
  3. removed the remaining direct `autoloop.workflows.*.params` imports from retained shared tests, especially `tests/unit/stdlib/test_authoring_helpers.py`,
  4. preserved the earlier cleanup by not restoring deleted parity/docs/workflow-package runtime suites.
- Required validation target: `.venv/bin/python -m pytest tests/strictness/test_no_compat.py tests/contract tests/unit -q`.

## Clarifications / superseding decisions

- The raw phase log did not add any later user clarification that changed the request.
- `decisions.txt` block 1 constrained the fix style: keep `_shared.py` private, do not restore monoliths, and import underscore-prefixed helpers explicitly at retained split call sites.
- `decisions.txt` block 2 allowed two additional stale-assertion updates inside `tests/` only when they matched maintained runtime semantics: `question` routes defaulting to no required writes, and `WorkflowInputView.message` remaining available.
- `decisions.txt` blocks 3 and 4 recorded implementation/test decisions that stayed within scope: local synthetic parameter models replaced repo-owned workflow-package params imports, and an AST-based structural regression guard was added.

## Implemented behavior

- Retained split files now import the private helpers they actually use while keeping `_shared.py` private. Examples:
  - `tests/contract/engine/test_prompt_context.py` explicitly imports `_load_replay_store`.
  - `tests/unit/extensions/test_git_and_session_paths.py` explicitly imports `_git`.
  - `tests/contract/engine/test_core_contracts.py` explicitly imports `_chain_hooks`, `_RecordingExtension`, and `_workspace`, and defines a local `PACKAGE_ROOT` for its moved path context.
- `tests/unit/stdlib/test_authoring_helpers.py` no longer directly imports repo-owned workflow-package params modules. It now defines local synthetic `RefinementParameters` and `DecompositionParameters` models and includes a structural AST guard against reintroducing those forbidden `ImportFrom` dependencies.
- `tests/strictness/test_no_compat.py` now asserts that `tests/contract/test_engine_contracts.py` is not in the maintained scan set.
- `tests/contract/test_canonical_runtime_contracts.py` and `tests/unit/test_branch_group_context_sessions.py` were updated to match maintained runtime behavior inside the allowed `tests/` scope:
  - `question` routes require no writes by default.
  - Branch and fan-in child contexts still expose `ctx.input.message`.
- Preserved-cleanup check: `rg --files tests -g '*.py' | rg 'parity|docs|workflow_package|workflow-package|engine_contracts\\.py$'` returned no source matches, so the deleted stale suites/monolith were not restored under `tests/`.
- Final verification on the current codebase passed:
  - `.venv/bin/python -m pytest tests/strictness/test_no_compat.py tests/contract tests/unit -q`
  - Result: `786 passed, 1 warning in 14.37s`

## Unresolved gaps

- No material unresolved gap remains against the request.

## Differences justified by later clarification or analysis

- The implementation touched `tests/contract/test_canonical_runtime_contracts.py` and `tests/unit/test_branch_group_context_sessions.py` in addition to the initially named files because the planning verifier found those stale assertions still failing inside the exact required pytest target, and `decisions.txt` block 2 limited those updates to maintained-runtime alignment within `tests/` only.
- The AST-based regression guard in `tests/unit/stdlib/test_authoring_helpers.py` is an extra protective test, not a scope expansion. It directly supports request item 3 by preventing the removed workflow-package params dependency from returning.
- The test-phase verifier noted one optional hardening gap in that new guard: it currently rejects forbidden `ast.ImportFrom` nodes but not equivalent dotted `ast.Import` aliases. That is non-blocking for this request because the current codebase has no forbidden direct imports and the mandated validation target is green.

## Recommended next run

- No follow-up implementation run is required for this request.
- Optional future hardening only if desired: broaden the AST source guard in `tests/unit/stdlib/test_authoring_helpers.py` to also reject forbidden dotted `import ... as ...` forms.
