# Botlane No-Compat Follow-up Plan

## Current state
- No later clarifications were appended after the immutable request snapshot.
- `botlane/core/context.py::_resolve_context_root` already limits marker detection to `("botlane", "workflows")`, `(".botlane", "workflows")`, and bare `("workflows",)` with the dotted-parent guard intact.
- `botlane/core/discovery.py::_is_simple_flow_spec` already accepts only `__botlane_simple_flow_spec__`.
- `botlane_optimizer/candidate_surfaces.py::validate_candidate_surface_overlay` already ignores `.botlane` and no longer carries the hidden legacy `.autoloop` ignore entry.
- Maintained-tree literal and split-string scans found legacy names only in `tests/strictness/test_no_compat.py`; explicit historical files remain isolated under the exact `legacy_docs/` allowlist.
- Targeted baseline checks are already green with the repo venv interpreter:
  `.venv/bin/python -m pytest tests/strictness/test_no_compat.py -q`
  `.venv/bin/python -m pytest tests/unit/optimizer/test_candidate_surfaces.py -q`

## Implementation scope
1. Runtime contract confirmation
- Re-audit `botlane/core/context.py`, `botlane/core/discovery.py`, `botlane_optimizer/candidate_surfaces.py`, and directly related helpers for hidden legacy construction or fallback behavior.
- Do not add compatibility shims, migration helpers, legacy imports, old CLI forwarding, or legacy schema/workspace support.
- Only edit those production files if a deeper scan finds an actual remaining loophole; avoid churn in already-correct Botlane-only logic.

2. Strictness and regression coverage
- Keep every explicit old-name literal inside `tests/strictness/test_no_compat.py` and nowhere else in maintained code/tests/docs/packaging.
- Extend the hidden-construction scanner coverage so the strictness suite explicitly proves detection of:
  `\"auto\" + \"loop\"`
  `\"Auto\" + \"loop\"`
  `\"AUTO\" + \"LOOP\"`
  `\".\" + \"auto\" + \"loop\"`
  `\"__auto\" + \"loop...\"`
  adjacent literals such as `\"auto\" \"loop\"`
  constant-building that reconstructs `.autoloop`, `autoloop_optimizer`, or `_autoloop_workspace_workflows`
- Preserve the narrow exact-history allowlist and keep scan roots free of broad `.autoloop` exclusions.
- Keep or strengthen negative-behavior coverage for `.autoloop/workflows`, `.botlane/workflows`, old/new simple-flow sentinels, missing legacy imports, missing `python -m autoloop`, and missing `autoloop` console scripts.

3. Overlay copy regression and package smoke
- Add a dedicated optimizer regression test proving `validate_candidate_surface_overlay` does not copy `repo_root/.botlane` into the overlay while still copying the candidate workflow file and compiling from the overlay cwd.
- Strengthen packaging/runtime smoke to prove both `botlane` and `botlane_optimizer` import successfully while `autoloop` and `autoloop_optimizer` remain unavailable.
- Extend CLI help assertions to prove `botlane --help` works and does not mention legacy Autoloop branding.

## Interfaces and invariants
- `_resolve_context_root(root, task_folder, package_folder) -> Path`
  returns only an explicit `root`, a Botlane workspace root, or `task_folder.resolve()` fallback; `.autoloop/workflows` must never resolve to the workspace root.
- `_is_simple_flow_spec(value: object) -> bool`
  returns `True` only when `value` exposes `__botlane_simple_flow_spec__`.
- `validate_candidate_surface_overlay(...) -> dict[str, Any]`
  must copy a runnable overlay that excludes active runtime state directories, overlay candidate files by repo-relative path, compile selected workflows from the overlay root, and run the declared validation command there.
- `tests/strictness/test_no_compat.py`
  remains the sole maintained non-historical file allowed to spell legacy names literally; all other maintained scan targets must stay legacy-free.

## Validation
- Literal maintained-tree scan:
  `rg -n 'autoloop|Autoloop|AUTOLOOP|\\.autoloop|autoloop_optimizer|autoloop_v3|autoloop-v3|_autoloop_workspace_workflows|__autoloop_simple_flow_spec__' botlane botlane_optimizer docs recursive_botlane tests pyproject.toml MANIFEST.in Review15.md Workflow_Instructions.md rebrand.md review16.md`
- Hidden-construction validation:
  rely on the strictness AST scanner and add explicit parametrized cases for split/add/join/adjacent forms that reconstruct forbidden names.
- Required pytest runs in this environment:
  `.venv/bin/python -m pytest tests/unit/optimizer/test_candidate_surfaces.py`
  `.venv/bin/python -m pytest tests/strictness/test_no_compat.py`
  `.venv/bin/python -m pytest`
- Package/runtime smoke:
  prove `import botlane`, `import botlane_optimizer`, negative imports for `autoloop`/`autoloop_optimizer`, `python -m autoloop` failure, and `botlane --help` success without legacy branding.

## Risks and controls
- Risk: help-text assertions become brittle if they overfit argparse formatting.
  Control: assert absence of legacy names and presence of stable Botlane command nouns, not full output snapshots.
- Risk: broader hidden-construction checks false-positive on historical material or the self-test file.
  Control: keep exclusions exact: `tests/strictness/test_no_compat.py` plus the existing exact `legacy_docs/` allowlist only.
- Risk: touching already-correct production files can reintroduce workspace-root or simple-flow regressions.
  Control: prefer no-op confirmation for `context.py` and `discovery.py` unless a concrete gap is found; focus new work on tests and validation.
- Rollback: revert only newly added strictness/help assertions if they prove environment-specific or over-broad; do not restore legacy runtime compatibility.
