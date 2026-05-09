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

````text id="cc2mo8"
Task: Fix Botlane optimizer overlay copy so active `.botlane` runtime state is not copied

Problem
`validate_candidate_surface_overlay` copies a runnable source tree into a temporary validation overlay using `shutil.copytree(...)`. The ignore list currently excludes the legacy `.autoloop` directory through hidden string construction, but it does not exclude `.botlane`. Since `.botlane` is the active Botlane runtime state directory, overlay validation can accidentally copy live task/run/workflow state into the temporary validation tree.

This is a real bug. Fix the active Botlane state exclusion. Do not preserve the old `.autoloop` ignore as a compatibility shim.

Primary file
- `botlane_optimizer/candidate_surfaces.py`

Current bad behavior
In `validate_candidate_surface_overlay`, the `shutil.copytree(..., ignore=shutil.ignore_patterns(...))` call ignores:

- `"." + "auto" + "loop"`
- `.git`
- `.pytest_cache`
- `__pycache__`
- `*.pyc`
- `.mypy_cache`
- `.ruff_cache`
- `.venv`

but it does not ignore `.botlane`.

Required production change
Replace the legacy hidden `.autoloop` ignore entry with `.botlane`.

Expected ignore list:

```python
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
````

Do not include:

```python
"." + "auto" + "loop"
```

Do not include `.autoloop` by literal spelling either. This is a Botlane greenfield codebase; the overlay helper should ignore the active Botlane runtime state directory, not a legacy Autoloop directory.

Regression test
Add a dedicated test in:

* `tests/unit/optimizer/test_candidate_surfaces.py`

Suggested test name:

```python
def test_candidate_surface_overlay_does_not_copy_botlane_runtime_state(...)
```

Test requirements

1. Create a runnable source root that `validate_candidate_surface_overlay` will copy directly.
2. Inside that source root, create `.botlane/sentinel.txt`.
3. Run `validate_candidate_surface_overlay`.
4. Monkeypatch `subprocess.run` so the test can inspect the temporary overlay `cwd`.
5. Assert that the overlay `cwd / ".botlane"` does not exist.
6. Also assert that the candidate workflow file still exists in the overlay, proving the overlay copy and candidate patching still work.

Recommended test shape

```python
def test_candidate_surface_overlay_does_not_copy_botlane_runtime_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    package_root = repo_root / "botlane"
    (package_root / "core").mkdir(parents=True, exist_ok=True)
    (package_root / "runtime").mkdir(parents=True, exist_ok=True)
    (repo_root / "tests").mkdir(parents=True, exist_ok=True)
    (package_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (repo_root / "tests" / "conftest.py").write_text("import pytest\n", encoding="utf-8")

    runtime_state = repo_root / ".botlane"
    runtime_state.mkdir(parents=True, exist_ok=True)
    (runtime_state / "sentinel.txt").write_text("must not be copied\n", encoding="utf-8")

    workflow_folder = tmp_path / ".botlane" / "tasks" / "task-1" / "wf_demo"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    candidate_root = workflow_folder / "candidate_surface"
    candidate_file = candidate_root / "workflows" / "demo_workflow" / "workflow.py"
    candidate_file.parent.mkdir(parents=True, exist_ok=True)
    candidate_file.write_text("class DemoWorkflow:\n    pass\n", encoding="utf-8")

    observed: dict[str, Any] = {}

    def _record_resolve(root: Path, workflow_name: str) -> SimpleNamespace:
        observed.setdefault("resolve_calls", []).append((root, workflow_name))
        return SimpleNamespace(workflow_cls=workflow_name)

    def _record_compile(workflow_cls: object) -> SimpleNamespace:
        return SimpleNamespace(workflow_name=f"compiled::{workflow_cls}")

    def _record_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        cwd = kwargs["cwd"]
        observed["cwd"] = cwd
        observed["botlane_state_exists"] = (cwd / ".botlane").exists()
        observed["candidate_exists"] = (
            cwd / "workflows" / "demo_workflow" / "workflow.py"
        ).is_file()
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(candidate_surface_helpers, "resolve_workflow_reference", _record_resolve)
    monkeypatch.setattr(candidate_surface_helpers, "compile_workflow", _record_compile)
    monkeypatch.setattr(candidate_surface_helpers.subprocess, "run", _record_run)

    result = validate_candidate_surface_overlay(
        repo_root=repo_root,
        workflow_names=["demo_workflow"],
        candidate_manifest={
            "surface_root": str(candidate_root),
            "relative_paths": ["workflows/demo_workflow/workflow.py"],
        },
        target_test_command="pytest -q tests/unit/test_demo.py",
        candidate_manifest_label="candidate_surface_manifest.json",
        overlay_failure_prefix="overlay validation failed",
        overlay_temp_prefix="candidate-surface-overlay-",
    )

    assert result == {
        "compiled_workflow_names": ["compiled::demo_workflow"],
        "test_command": "pytest -q tests/unit/test_demo.py",
        "test_returncode": 0,
    }
    assert observed["cwd"] != repo_root
    assert observed["candidate_exists"] is True
    assert observed["botlane_state_exists"] is False
```

Adjust imports as needed:

* `Any`
* `Path`
* `SimpleNamespace`
* `pytest`
* `candidate_surface_helpers`
* `validate_candidate_surface_overlay`

Strictness expectation
After the production fix, this file must not contain hidden old-name construction for the ignore entry:

```python
"." + "auto" + "loop"
```

If a strictness test already scans for hidden legacy construction, it should continue to pass. If it does not catch this pattern, add or extend a strictness assertion so this pattern is not allowed in maintained production code.

Validation commands
Run at minimum:

```bash
python -m pytest tests/unit/optimizer/test_candidate_surfaces.py
python -m pytest tests/strictness/test_no_compat.py
python -m pytest
```

Acceptance criteria

1. `validate_candidate_surface_overlay` excludes `.botlane` from overlay copies.
2. `validate_candidate_surface_overlay` no longer excludes `.autoloop` through string concatenation.
3. The overlay still receives candidate files from `candidate_manifest["relative_paths"]`.
4. The regression test proves `repo_root/.botlane` is not copied into the temporary overlay.
5. No production code reintroduces hidden Autoloop string construction for this fix.
6. Optimizer candidate-surface tests pass.
7. Strict no-compat tests pass.

```

This is correct for the current implementation because the active test fixtures now use `.botlane`, while the overlay copy ignore list still contains the hidden legacy `.autoloop` construction instead of `.botlane`. :contentReference[oaicite:0]{index=0} :contentReference[oaicite:1]{index=1}
```
