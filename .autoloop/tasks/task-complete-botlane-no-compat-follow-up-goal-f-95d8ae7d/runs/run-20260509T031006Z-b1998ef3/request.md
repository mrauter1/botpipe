Task: Complete Botlane no-compat follow-up

Goal
Finish the Botlane rename by removing every hidden Autoloop compatibility path, including string-concatenated legacy identifiers, legacy workspace markers, legacy simple-flow markers, and scanner loopholes. The final codebase must behave as a greenfield Botlane project with no supported Autoloop runtime behavior.

Scope
This is a strict cleanup follow-up. Do not preserve compatibility with Autoloop, .autoloop, autoloop_optimizer, autoloop_v3, old simple-flow sentinels, old generated workspace module names, old CLI names, or old schema prefixes.

Required production-code changes

1. Remove legacy workspace root detection
   In `botlane/core/context.py`, update `_resolve_context_root` so it recognizes only Botlane/current markers:
   - `("botlane", "workflows")`
   - `(".botlane", "workflows")`
   - `("workflows",)`

   Delete the marker currently constructed as:
   - `"." + "auto" + "loop"`

   There must be no `.autoloop` fallback, no string-concatenated `.autoloop` marker, and no legacy workspace-root migration behavior.

2. Remove legacy simple-flow marker support
   In `botlane/core/discovery.py`, update `_is_simple_flow_spec` so it only accepts:
   - `__botlane_simple_flow_spec__`

   Delete support for the old marker currently constructed as:
   - `"__auto" + "loop_simple_flow_spec__"`

   A value with only `__autoloop_simple_flow_spec__` must not be recognized as a Botlane flow spec.

3. Remove string-concatenated legacy identifiers from production code
   Search all maintained source for concatenated legacy spellings, including but not limited to:
   - `"auto" + "loop"`
   - `"Auto" + "loop"`
   - `"AUTO" + "LOOP"`
   - `"." + "auto" + "loop"`
   - `"__auto" + "loop"`
   - `"_" + "auto" + "loop"`
   - `"auto" "loop"` adjacent string literals
   - f-string or join-based construction of old names

   Production code must not construct old Autoloop names indirectly.

4. Do not add compatibility aliases
   Do not add:
   - `autoloop` import packages
   - `autoloop_optimizer` import packages
   - old CLI forwarding
   - `.autoloop` fallback reads
   - schema migration from `autoloop.*`
   - old generated module-name support
   - old simple-flow sentinel support
   - migration helpers
   - compatibility warnings

Required strictness-test changes

5. Make legacy names explicit in the strictness test
   Keep old-name literals only inside `tests/strictness/test_no_compat.py`.

   Prefer explicit literals over concatenation:
   - `LEGACY_PRODUCT = "autoloop"`
   - `LEGACY_PRODUCT_CAP = "Autoloop"`
   - `LEGACY_PRODUCT_ENV = "AUTOLOOP"`
   - `LEGACY_OPTIMIZER = "autoloop_optimizer"`
   - `LEGACY_WORKSPACE_MODULE = "_autoloop_workspace_workflows"`
   - `LEGACY_STATE_ROOT_PART = ".autoloop"`

   Because this one file is intentionally excluded from active scans, it is the correct place for literal old-name test data.

6. Add a scanner for hidden legacy construction
   Add a strictness test that scans maintained Python files and fails on old-name construction patterns outside `tests/strictness/test_no_compat.py`.

   It must catch at least:
   - `"auto" + "loop"`
   - `"Auto" + "loop"`
   - `"AUTO" + "LOOP"`
   - `"." + "auto" + "loop"`
   - `"__auto" + "loop"`
   - string literal adjacency that forms `autoloop`
   - constant-building patterns that recreate `.autoloop`, `autoloop_optimizer`, or `_autoloop_workspace_workflows`

   The scanner should not rely only on simple grep for the literal word `autoloop`.

7. Remove `.autoloop` from ignored scan parts
   The strictness scanner must not ignore `.autoloop` directories by default. The product tree should not contain `.autoloop` active fixtures, and ignoring that path can hide violations.

   If persisted legacy examples are ever needed, they must live under an explicit historical allowlist such as `legacy_docs/`, not inside active runtime or test fixtures.

8. Keep the historical allowlist narrow
   Historical Autoloop mentions are allowed only under explicit historical documentation files, not in runtime code, tests, examples, packaging, or current docs.

   The historical allowlist must be exact and audited. Do not use broad path-prefix exclusions except for a dedicated historical-docs directory.

Required negative behavior tests

9. Add a test proving `.autoloop/workflows` is not recognized
   Create a synthetic path under:
   - `<tmp>/.autoloop/workflows/example`

   Call the relevant context/root-resolution path and assert it does not resolve the workspace root through `.autoloop`.

   Expected behavior: Botlane should not treat `.autoloop/workflows` as a supported workspace marker.

10. Add a test proving `.botlane/workflows` still works
   Create a synthetic path under:
   - `<tmp>/.botlane/workflows/example`

   Assert the context/root-resolution logic resolves the intended workspace root.

11. Add a test proving old simple-flow sentinel is ignored
   Create a dummy object with:
   - `__autoloop_simple_flow_spec__ = True`

   Assert `_is_simple_flow_spec(obj)` returns `False`.

12. Add a test proving new simple-flow sentinel works
   Create a dummy object with:
   - `__botlane_simple_flow_spec__ = True`

   Assert `_is_simple_flow_spec(obj)` returns `True`.

13. Keep import and CLI negative tests
   Preserve or add tests proving:
   - `import autoloop` fails
   - `import autoloop_optimizer` fails
   - `python -m autoloop` fails or is absent
   - no `autoloop` console script is installed
   - `botlane --help` works
   - `botlane` help text does not mention Autoloop except in explicit historical changelog material

Repository-wide audit requirements

14. Run a literal old-name scan
   Scan maintained source, tests, docs, packaging, templates, scripts, and generated examples for:
   - `autoloop`
   - `Autoloop`
   - `AUTOLOOP`
   - `.autoloop`
   - `autoloop_optimizer`
   - `autoloop_v3`
   - `autoloop-v3`
   - `_autoloop_workspace_workflows`
   - `__autoloop_simple_flow_spec__`

   Only `tests/strictness/test_no_compat.py` and explicit historical docs may contain these literals.

15. Run a hidden-construction scan
   Scan maintained Python files for split-string or concatenated construction of those same old names. This must catch attempts to evade literal grep.

16. Re-run the package and runtime smoke tests
   At minimum:
   - `python -m pytest`
   - import smoke test for `botlane`
   - import smoke test for `botlane_optimizer`
   - negative import smoke test for `autoloop`
   - negative import smoke test for `autoloop_optimizer`
   - CLI smoke test for `botlane --help`
   - wheel/package smoke test if present

Acceptance criteria

The follow-up is complete only when:
1. No production code recognizes `.autoloop`.
2. No production code recognizes `__autoloop_simple_flow_spec__`.
3. No production code constructs Autoloop names through concatenated strings.
4. Old-name literals are confined to the explicit strictness test and historical docs.
5. The strictness scanner detects hidden old-name construction, not just literal old-name text.
6. `botlane` and `botlane_optimizer` are the only supported import namespaces.
7. `.botlane` is the only supported runtime state/workspace directory.
8. `botlane.*` is the only active framework schema prefix.
9. All tests pass.

Do not satisfy this task by hiding old names through string concatenation, dynamic construction, comments, or broad allowlists. The goal is behavioral removal, not grep avoidance.

Additional fix:

Task: Fix Botlane optimizer overlay copy so `.botlane` runtime state is excluded

Problem
`validate_candidate_surface_overlay` creates a temporary validation overlay by copying a source tree with `shutil.copytree(...)`, then applying candidate workflow files and running the validation command from the overlay cwd.

The current ignore list excludes the old legacy `.autoloop` directory through hidden string construction, but it does not exclude `.botlane`. Since `.botlane` is the active Botlane runtime state directory, validation overlays can accidentally copy live Botlane task/run/workflow state into the temporary overlay.

This is a real bug. Fix the active Botlane state exclusion and remove the legacy hidden `.autoloop` ignore.

Primary file
- `botlane_optimizer/candidate_surfaces.py`

Required production change

1. Locate `validate_candidate_surface_overlay`.

2. Find the `shutil.copytree(..., ignore=shutil.ignore_patterns(...))` call.

3. Replace the legacy hidden `.autoloop` ignore entry with `.botlane`.

Expected ignore list:

    ignore=shutil.ignore_patterns(
        ".botlane",
        ".git",
        ".pytest_cache",
        "__pycache__",
        "*.pyc",
        ".mypy_cache",
        ".ruff_cache",
        ".venv",
    )

4. Do not keep any of the following:
   - `"." + "auto" + "loop"`
   - literal `.autoloop`
   - any dynamically constructed legacy Autoloop state-directory ignore
   - any compatibility comment implying `.autoloop` is still supported

5. Do not add fallback behavior, migration behavior, or compatibility aliases. This is a Botlane greenfield codebase.

Regression test

Add or update a test in:

- `tests/unit/optimizer/test_candidate_surfaces.py`

Suggested test name:

- `test_candidate_surface_overlay_does_not_copy_botlane_runtime_state`

Core test requirement
The test must place `.botlane/sentinel.txt` under the exact source tree that `validate_candidate_surface_overlay` actually copies.

This is important because the function copies:

- `overlay_source_root = _resolve_overlay_source_root(repo_root)`

not necessarily `repo_root` itself.

Preferred setup
Use a simple setup where `repo_root` is also the copied source root:

1. Create a temporary `repo_root`.
2. Put a minimal `botlane/` package under `repo_root`.
3. Put `.botlane/sentinel.txt` under `repo_root`.
4. Make the candidate manifest point to a candidate workflow file.
5. Run `validate_candidate_surface_overlay`.
6. Monkeypatch `subprocess.run` to inspect the temporary overlay cwd.
7. Assert:
   - `overlay_cwd / ".botlane"` does not exist.
   - the candidate workflow file does exist in the overlay.
   - the validation command still runs from the overlay cwd.

Alternative setup
If the existing test pattern uses a phase workspace and resolves the overlay source from an installed Botlane root, then place the sentinel under that installed root:

- `installed_root/.botlane/sentinel.txt`

not under the phase workspace. The sentinel must be under the directory actually copied by `copytree`.

Recommended test assertions

The regression test should verify all of the following:

1. The temporary overlay cwd is not the original source root.
2. `.botlane` does not exist in the overlay cwd.
3. The candidate workflow file exists in the overlay cwd at its expected patched path.
4. `validate_candidate_surface_overlay` returns a successful result when the mocked validation command succeeds.
5. The test would fail before the production fix and pass after the production fix.

Strictness requirement

Update or rely on the strict no-compat scanner so production code fails if it contains hidden legacy construction such as:

- `"." + "auto" + "loop"`
- `"auto" + "loop"`
- `"__auto" + "loop"`
- split-string or concatenated construction of old Autoloop identifiers

The fix must not satisfy grep by hiding old names through dynamic string construction.

Validation commands

Run at minimum:

    python -m pytest tests/unit/optimizer/test_candidate_surfaces.py
    python -m pytest tests/strictness/test_no_compat.py
    python -m pytest

Acceptance criteria

1. `validate_candidate_surface_overlay` excludes `.botlane` from overlay copies.
2. The overlay copy no longer excludes `.autoloop`, literally or through string concatenation.
3. The regression test places `.botlane` under the actual copied source root.
4. The regression test proves `.botlane` is absent from the temporary overlay.
5. Candidate files are still copied into the overlay correctly.
6. The validation command still runs from the overlay cwd.
7. No production code contains hidden Autoloop string construction.
8. Optimizer candidate-surface tests pass.
9. Strict no-compat tests pass.
10. The full test suite passes.
