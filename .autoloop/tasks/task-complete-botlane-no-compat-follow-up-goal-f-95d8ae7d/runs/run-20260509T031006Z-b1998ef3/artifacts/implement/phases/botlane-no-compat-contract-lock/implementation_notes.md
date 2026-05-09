# Implementation Notes

- Task ID: task-complete-botlane-no-compat-follow-up-goal-f-95d8ae7d
- Pair: implement
- Phase ID: botlane-no-compat-contract-lock
- Phase Directory Key: botlane-no-compat-contract-lock
- Phase Title: Lock Botlane-Only Contract
- Scope: phase-local producer artifact

## Files changed
- `botlane_optimizer/candidate_surfaces.py`
- `botlane/core/workflow_catalog.py`
- `tests/strictness/test_no_compat.py`
- `tests/unit/optimizer/test_candidate_surfaces.py`
- `tests/runtime/test_workflow_catalog_roots.py`

## Symbols touched
- `validate_candidate_surface_overlay`
- `workflow_search_roots`
- `test_hidden_legacy_construction_scanner_flags_split_string_patterns`
- `test_supported_package_imports_succeed`
- `test_botlane_help_succeeds_without_legacy_branding`
- `test_candidate_surface_overlay_does_not_copy_botlane_runtime_state`

## Checklist mapping
- Runtime cleanup: replaced the overlay copy ignore entry with `.botlane`; confirmed `botlane/core/context.py::_resolve_context_root` and `botlane/core/discovery.py::_is_simple_flow_spec` already matched the Botlane-only contract and did not require edits.
- Strictness and negative coverage: extended hidden legacy construction fixtures, added positive `botlane`/`botlane_optimizer` import smoke, and added Botlane help smoke without legacy branding.
- Overlay regression and validation: added a regression proving `.botlane/sentinel.txt` under the actual copied source root is absent from the temporary overlay while candidate workflow content is still patched into the overlay cwd.
- Full-suite regression fix: raised `.botlane/workflows` catalog precedence above repo-local `workflows/` for named workflow resolution, matching the existing runtime expectations while preserving explicit repo-local path/module references.

## Assumptions
- Repo-local `workflows/...` references remain intentionally supported as explicit authoring/test inputs even though named workspace resolution must prefer `.botlane/workflows`.
- Falling back to `python -m botlane.runtime.cli --help` is acceptable only for repo-local test environments where no installed `botlane` entrypoint exists beside the active interpreter.

## Preserved invariants
- No production code now reads or constructs legacy `.autoloop` overlay state ignores.
- No production code recognizes `__autoloop_simple_flow_spec__`; the existing runtime-only Botlane sentinel behavior remained unchanged.
- Explicit `autoloop.*` persisted schema strings remain rejected; no legacy-schema migration helpers were added.
- Literal legacy names remain confined to `tests/strictness/test_no_compat.py` plus the audited `legacy_docs/*.md` allowlist.

## Intended behavior changes
- Validation overlays omit live `.botlane` runtime state.
- The strictness scanner now proves detection of additional hidden legacy-name construction forms, including capitalized/env variants, adjacent literals, joins, and f-strings.
- Bare workflow-name resolution prefers `.botlane/workflows` over repo-local `workflows`.

## Known non-changes
- `botlane/core/context.py` and `botlane/core/discovery.py` were left unchanged after confirmation because they already satisfied the requested Botlane-only workspace/simple-flow behavior.
- No compatibility aliases, fallback readers, legacy imports, CLI forwarding, or schema migrations were introduced.

## Expected side effects
- Repo-local workflow packages with the same name as a `.botlane/workflows` workflow are shadowed for named resolution but remain reachable through explicit repo-local aliases, paths, or module references.
- Overlay validation temp copies no longer include `.botlane`, reducing accidental leakage of live runtime state into validation runs.

## Validation performed
- Maintained-tree literal scan:
  `rg -n 'autoloop|Autoloop|AUTOLOOP|\\.autoloop|autoloop_optimizer|autoloop_v3|autoloop-v3|_autoloop_workspace_workflows|__autoloop_simple_flow_spec__' botlane botlane_optimizer docs recursive_botlane tests pyproject.toml MANIFEST.in __init__.py`
- Hidden-construction spot scan over production Python:
  `rg -n '"auto"\\s*\\+\\s*"loop"|"Auto"\\s*\\+\\s*"loop"|"AUTO"\\s*\\+\\s*"LOOP"|"\\."\\s*\\+\\s*"auto"\\s*\\+\\s*"loop"|"__auto"\\s*\\+\\s*"loop"| "_"\\s*\\+\\s*"auto"\\s*\\+\\s*"loop"|"auto"\\s+"loop"' botlane botlane_optimizer -g '*.py'`
- Targeted tests:
  `.venv/bin/python -m pytest tests/unit/optimizer/test_candidate_surfaces.py`
  `.venv/bin/python -m pytest tests/strictness/test_no_compat.py`
  `.venv/bin/python -m pytest tests/contract/engine/test_prompt_context.py -k operation_replay`
  `.venv/bin/python -m pytest tests/runtime/test_workflow_reference_resolution.py tests/runtime/test_workflow_catalog_roots.py`
- Smoke commands:
  `.venv/bin/python -c "import botlane, botlane_optimizer"`
  `.venv/bin/python -c "import autoloop"` (expected failure)
  `.venv/bin/python -c "import autoloop_optimizer"` (expected failure)
  `.venv/bin/python -m autoloop` (expected failure)
  `.venv/bin/botlane --help` or fallback `.venv/bin/python -m botlane.runtime.cli --help`
- Full suite:
  `.venv/bin/python -m pytest` -> `1195 passed, 1 warning`

## Deduplication / centralization decisions
- Kept the hidden legacy construction enforcement centralized in `tests/strictness/test_no_compat.py` rather than adding secondary ad hoc scanners elsewhere.
- Fixed workspace-vs-repo name precedence in `workflow_search_roots()` instead of adding one-off resolution overrides in loader code.
