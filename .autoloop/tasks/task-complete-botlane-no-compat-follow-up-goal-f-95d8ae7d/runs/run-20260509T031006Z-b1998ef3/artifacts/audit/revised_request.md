Task: Finish Botlane no-compat cleanup for active Autoloop artifact trees and scanner scope

Goal
Close the remaining gap between the completed Botlane-only runtime cleanup and the repo-wide no-compat contract. Runtime behavior, overlay copying, negative imports/CLI, hidden-construction detection, and the full test suite are already green. The remaining work is to remove or explicitly isolate legacy Autoloop names in active repo-root artifact trees and make the strictness scanner enforce that policy instead of skipping those trees by root selection.

Scope
- `tests/strictness/test_no_compat.py`
- active repo-root artifact trees that still contain legacy names, especially `.autoloop_recursive/` and repo-local `.autoloop/` operational content
- any directly related scripts/docs/templates under those trees that still use `autoloop`, `.autoloop`, `recursive_autoloop`, or other legacy names

Required changes

1. Close the scanner-root loophole.
   Update the strictness scan logic so repo-root Autoloop artifact trees are not omitted simply because they are absent from `ACTIVE_SCAN_ROOTS` / `BRANDING_SCAN_ROOTS`.

2. Enforce an explicit policy for active artifact trees.
   Choose one of these and make it explicit in tests:
   - Preferred: migrate active maintained artifact trees to Botlane naming so they no longer contain legacy Autoloop names.
   - Only if unavoidable: define a narrow, exact allowlist for specific operational artifact paths that must remain outside the no-compat contract. Do not use broad prefix exclusions such as “ignore all `.autoloop/**`”.

3. Remove remaining legacy literals from active non-historical artifact trees.
   At minimum, address the active examples surfaced by the audit:
   - `.autoloop_recursive/rerun_command.sh`
   - `.autoloop_recursive/framework_evolution_charter.md`
   - `.autoloop_recursive/framework_roadmap.md`
   - any other active `.autoloop_recursive/` or repo-local `.autoloop/` files that still carry legacy names and are not part of an exact approved allowlist

4. Keep the historical allowlist narrow.
   Historical legacy-name mentions may remain only in `legacy_docs/*.md` and `tests/strictness/test_no_compat.py`, plus any exact operational-path allowlist that is truly unavoidable and explicitly documented in the strictness test.

5. Add regression coverage for the artifact-tree policy.
   The strictness suite must fail if a legacy name appears in an active repo-root artifact tree outside the final explicit allowlist.

Validation

- `python -m pytest tests/strictness/test_no_compat.py`
- literal legacy-name scan over the maintained product tree plus the active artifact trees covered by the final policy
- `python -m pytest`

Acceptance criteria

1. The strictness scanners can no longer miss `.autoloop` / `.autoloop_recursive` trees merely because those roots were not traversed.
2. Active non-historical artifact trees no longer contain legacy Autoloop names unless covered by a narrow exact allowlist.
3. Old-name literals are again confined to `tests/strictness/test_no_compat.py`, `legacy_docs/*.md`, and any explicitly justified exact operational-path allowlist.
4. Full tests pass after the scanner-scope and artifact cleanup changes.
