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
