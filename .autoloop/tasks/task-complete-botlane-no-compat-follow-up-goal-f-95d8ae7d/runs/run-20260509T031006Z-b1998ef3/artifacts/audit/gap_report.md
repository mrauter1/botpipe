# Gap Report

## Original intent considered

- The immutable request required a Botlane-only runtime with no `.autoloop` workspace fallback, no `__autoloop_simple_flow_spec__` support, no hidden legacy-name construction, no legacy import/CLI/schema compatibility, a `.botlane` overlay-copy fix, a narrow historical allowlist, and strict scans/tests that catch both literal and constructed legacy names.
- The request also explicitly required that `.autoloop` not be hidden by default scan exclusions and that old-name literals be confined to `tests/strictness/test_no_compat.py` and explicit historical docs only.

## Clarifications / superseding decisions

- No raw-log clarification narrowed the repo-wide literal-confinement rule or exempted active `.autoloop` / `.autoloop_recursive` artifact trees from that rule.
- The run decisions added two relevant clarifications:
  - explicit `autoloop.*` persisted schema values must still be rejected, while existing schemaless-only migration may remain;
  - the later `botlane/core/workflow_catalog.py` precedence fix was an allowed adjacent regression repair because the full suite showed `.botlane/workflows` needed to win for named workflow resolution.

## Implemented behavior

- `botlane/core/context.py::_resolve_context_root(...)` now recognizes only `("botlane", "workflows")`, `(".botlane", "workflows")`, and bare `("workflows",)` markers.
- `botlane/core/discovery.py::_is_simple_flow_spec(...)` now recognizes only `__botlane_simple_flow_spec__`.
- `botlane_optimizer/candidate_surfaces.py::validate_candidate_surface_overlay(...)` now excludes `.botlane` from overlay copies and no longer carries the hidden legacy `.autoloop` ignore.
- `tests/strictness/test_no_compat.py` now uses explicit legacy literals, scans maintained Python for hidden legacy-name construction, covers negative legacy imports/module entrypoints, positive `botlane`/`botlane_optimizer` imports, and Botlane help text without legacy branding.
- `tests/unit/optimizer/test_candidate_surfaces.py` now proves `.botlane/sentinel.txt` under the actual copied source root is absent from the temporary overlay while candidate files are still patched into the overlay.
- The run also repaired an adjacent runtime regression in `botlane/core/workflow_catalog.py` so named workflow resolution prefers `.botlane/workflows` over repo-local `workflows/`, consistent with the Botlane workspace contract.
- Revalidation during this audit:
  - `.venv/bin/python -m pytest tests/strictness/test_no_compat.py tests/unit/optimizer/test_candidate_surfaces.py tests/runtime/test_workflow_catalog_roots.py tests/runtime/test_workflow_reference_resolution.py -q` passed (`114 passed`).
  - direct smoke checks passed for `import botlane, botlane_optimizer`, failed as expected for `import autoloop`, `import autoloop_optimizer`, and `python -m autoloop`, and `python -m botlane.runtime.cli --help` succeeded without legacy branding.
  - `.venv/bin/python -m pytest -q` passed (`1195 passed, 1 warning`).

## Unresolved gaps

1. The strictness scanners still omit active repo-root Autoloop artifact trees by construction.
   Evidence: `tests/strictness/test_no_compat.py` defines `ACTIVE_SCAN_ROOTS` as `botlane`, `botlane_optimizer`, `docs`, `recursive_botlane`, `tests`, and `pyproject.toml`, and `BRANDING_SCAN_ROOTS` is derived from those same roots plus a few top-level files. Neither `.autoloop` nor `.autoloop_recursive` is scanned.
   Why this is material: request items 7, 8, and 14 explicitly targeted scanner loopholes around `.autoloop` and repo-wide literal confinement. The current implementation removed `.autoloop` from ignored path parts, but the scanners can still miss those trees entirely because they never walk them.

2. Legacy Autoloop names remain in active non-historical artifact trees outside the explicit allowlist.
   Evidence from the final tree:
   - `.autoloop_recursive/rerun_command.sh` still invokes `recursive_autoloop/run_recursive_autoloop.sh`.
   - `.autoloop_recursive/framework_evolution_charter.md` and `.autoloop_recursive/framework_roadmap.md` still document `autoloop --workspace ...`.
   - `.autoloop/tasks/...` run artifacts still contain `.autoloop` state paths and legacy Autoloop names.
   Why this is material: the request said old-name literals should be confined to `tests/strictness/test_no_compat.py` and explicit historical docs. No authoritative clarification exempted these active artifact trees, and the current strictness tests do not enforce any policy for them.

## Differences justified by later clarification or analysis

- The change in `botlane/core/workflow_catalog.py` was outside the initially named production files, but it was justified by run-local evidence: the first full-suite run failed in workflow-resolution tests, and the fix aligns with the request’s Botlane-only workspace intent rather than widening compatibility.
- The strictness help test’s fallback to `python -m botlane.runtime.cli --help` is a test-environment stabilization detail, not a compatibility alias. Separate checks still guard the installed-console-script surface.

## Recommended next run

- Focus only on the remaining repo-wide no-compat audit gap.
- Expand the strictness scan contract so active repo-root artifact trees cannot be skipped by root selection.
- Either migrate active `.autoloop` / `.autoloop_recursive` artifacts to Botlane naming or establish a narrowly documented exact allowlist for any unavoidable operational artifacts, then make the strictness tests enforce that policy.
