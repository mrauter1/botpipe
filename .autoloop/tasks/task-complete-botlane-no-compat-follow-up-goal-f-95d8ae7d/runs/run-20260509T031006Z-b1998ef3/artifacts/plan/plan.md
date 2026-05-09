# Botlane No-Compat Follow-up Plan

## Current state
- No later clarification entries were appended after the immutable request snapshot.
- `botlane/core/context.py::_resolve_context_root(...)` already limits marker detection to `("botlane", "workflows")`, `(".botlane", "workflows")`, and bare `("workflows",)` with the dotted-parent guard preserved.
- `botlane/core/discovery.py::_is_simple_flow_spec(...)` already accepts only `__botlane_simple_flow_spec__`.
- `botlane_optimizer/candidate_surfaces.py::validate_candidate_surface_overlay(...)` still needs the active-state fix: its `copytree(..., ignore=...)` list omits `.botlane`.
- Maintained-tree literal scans show legacy names only in `tests/strictness/test_no_compat.py`; historical mentions are isolated under the exact `legacy_docs/` allowlist.
- `tests/strictness/test_no_compat.py` already contains the core AST-based hidden-construction scanner and the requested negative `.autoloop` / simple-flow tests, but still needs to cover the remaining requested legacy forms and Botlane-only import/CLI smoke.

## Implementation scope
1. Runtime cleanup
- Update `botlane_optimizer/candidate_surfaces.py` so overlay copies exclude `.botlane` and do not exclude `.autoloop`, literally or through hidden construction.
- Re-audit maintained production Python under `botlane/` and `botlane_optimizer/` for split-string, join-based, adjacent-literal, or f-string reconstruction of legacy Autoloop names.
- Do not add compatibility shims, migration helpers, legacy imports, old CLI forwarding, or schema/workspace fallback behavior.

2. Strictness and negative-behavior coverage
- Keep literal legacy names confined to `tests/strictness/test_no_compat.py` and the exact `legacy_docs/*.md` allowlist only.
- Extend `tests/strictness/test_no_compat.py` so the hidden-construction scanner explicitly proves detection of:
  `\"auto\" + \"loop\"`
  `\"Auto\" + \"loop\"`
  `\"AUTO\" + \"LOOP\"`
  `\".\" + \"auto\" + \"loop\"`
  `\"__auto\" + \"loop...\"`
  adjacent literals such as `\"auto\" \"loop\"`
  constant-building that recreates `.autoloop`, `autoloop_optimizer`, and `_autoloop_workspace_workflows`
- Preserve the existing exact self-scan exclusion for `tests/strictness/test_no_compat.py`, but do not ignore `.autoloop` paths globally.
- Keep or strengthen explicit negative tests for `.autoloop/workflows`, `.botlane/workflows`, the old simple-flow sentinel, the new simple-flow sentinel, `import autoloop`, `import autoloop_optimizer`, `python -m autoloop`, installed console scripts, and Botlane-only CLI help text.
- Add positive smoke proving `import botlane_optimizer` succeeds alongside `import botlane`.

3. Overlay regression and validation
- Add or update `tests/unit/optimizer/test_candidate_surfaces.py` with a regression that places `.botlane/sentinel.txt` under the exact `overlay_source_root` copied by `validate_candidate_surface_overlay(...)`.
- In that regression, assert the overlay cwd differs from the source root, `.botlane` is absent from the overlay, the candidate workflow file is present at the patched repo-relative path, and the validation command runs from the overlay cwd.
- Re-run the maintained-tree literal scan, the hidden-construction strictness suite, the optimizer candidate-surface tests, import/CLI smoke, and the full pytest suite.

## Interfaces and invariants
- `_resolve_context_root(root, task_folder, package_folder) -> Path`
  must resolve only an explicit `root`, a Botlane workspace root, or `task_folder.resolve()` fallback. `.autoloop/workflows` must not resolve the workspace root.
- `_is_simple_flow_spec(value: object) -> bool`
  must return `True` only for `__botlane_simple_flow_spec__`.
- `validate_candidate_surface_overlay(...) -> dict[str, Any]`
  must build an isolated runnable overlay, exclude live `.botlane` runtime state from the copied tree, overlay candidate files by repo-relative path, compile selected workflows from the overlay root, and run the declared validation command there.
- `tests/strictness/test_no_compat.py`
  remains the only maintained non-historical file allowed to contain literal legacy names.

## Validation
- Maintained-tree literal scan:
  `rg -n 'autoloop|Autoloop|AUTOLOOP|\\.autoloop|autoloop_optimizer|autoloop_v3|autoloop-v3|_autoloop_workspace_workflows|__autoloop_simple_flow_spec__' botlane botlane_optimizer docs recursive_botlane tests pyproject.toml MANIFEST.in __init__.py`
- Hidden-construction validation:
  rely on the AST scanner in `tests/strictness/test_no_compat.py` and extend its fixture cases to cover capitalized/env, dotted, adjacent-literal, and join-based reconstruction.
- Required test runs:
  `.venv/bin/python -m pytest tests/unit/optimizer/test_candidate_surfaces.py`
  `.venv/bin/python -m pytest tests/strictness/test_no_compat.py`
  `.venv/bin/python -m pytest`
- Smoke expectations:
  `import botlane` and `import botlane_optimizer` succeed; `import autoloop` and `import autoloop_optimizer` fail; `python -m autoloop` fails; `botlane --help` succeeds without legacy Autoloop branding.

## Risks and controls
- Risk: changing already-correct runtime files could reintroduce workspace-root or simple-flow regressions.
  Control: treat `context.py` and `discovery.py` as confirm-only unless a fresh maintained-tree scan finds a real loophole.
- Risk: hidden-construction checks may false-positive on historical material or the strictness file itself.
  Control: keep exclusions exact: `tests/strictness/test_no_compat.py` plus the audited `legacy_docs/*.md` allowlist only.
- Risk: CLI help assertions may be brittle if they snapshot full argparse output.
  Control: assert stable Botlane tokens are present and legacy Autoloop branding is absent rather than matching full output.
- Rollback: revert only newly added tests or the `.botlane` overlay-ignore change if validation isolates an environment-specific issue; do not restore any legacy Autoloop compatibility path.
