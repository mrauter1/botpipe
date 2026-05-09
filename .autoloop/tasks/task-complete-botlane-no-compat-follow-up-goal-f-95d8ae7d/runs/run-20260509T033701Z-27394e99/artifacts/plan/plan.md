# Botlane No-Compat Artifact-Tree Cleanup Plan

## Objective

Close the remaining no-compat gap by making strictness explicitly cover active repo-root artifact trees and by removing legacy Autoloop literals from maintained artifact files instead of relying on scan-root omission.

## Current State

- `tests/strictness/test_no_compat.py` only scans maintained product roots plus optional files; `.autoloop_recursive/` and `.autoloop/` are outside `ACTIVE_SCAN_ROOTS` and `BRANDING_SCAN_ROOTS`.
- `recursive_botlane/` and its templates already define the canonical Botlane naming and CLI contract.
- Top-level `.autoloop_recursive/` still contains maintained files with legacy literals, including the named request files and other active memory docs.
- Repo-local `.autoloop/` currently appears to be task-history storage only; there are no repo-maintained non-task files under that root today.

## Implementation Contract

### 1. Close the scanner-root loophole

- Refactor the strictness scan setup so repo-root artifact policy is expressed explicitly instead of being implied by `ACTIVE_SCAN_ROOTS` membership.
- Keep the maintained product-tree scan intact for `botlane/`, `botlane_optimizer/`, `docs/`, `recursive_botlane/`, `tests/`, and optional top-level files.
- Add explicit artifact-tree coverage helpers/constants for repo-root operational trees:
  - `.autoloop_recursive/` as active maintained recursive memory
  - `.autoloop/` as repo-local operational storage with a separate explicit policy
- Update the scope assertions so adding a new active artifact file under either root cannot silently bypass the no-compat scan just because the root is absent from a root tuple.

### 2. Enforce the artifact-tree policy in tests

- Prefer migration over exceptions for maintained files.
- Treat top-level `.autoloop_recursive/` text files as in-contract unless they are exact operational records that cannot be renamed safely.
- Codify the current `.autoloop/` invariant in strictness:
  - today there are no maintained repo-local source files outside task-history storage
  - future maintained files under `.autoloop/` must either be Botlane-clean or be added as exact documented exceptions
- If any exception remains unavoidable, store it as exact repo-relative paths in the strictness test. Do not use directory-prefix exclusions or wildcard “ignore all `.autoloop/**`” rules.

### 3. Migrate active maintained artifact files to Botlane naming

- Audit all top-level `.autoloop_recursive/` text files, not only the three named examples.
- Use `recursive_botlane/run_recursive_botlane.sh` and `recursive_botlane/run_recursive_botlane_templates/*.tmpl` as the canonical replacement vocabulary for:
  - `Botlane` product naming
  - `botlane --workspace ... --task-id ... --intent ... --pairs ...` CLI examples
  - `.botlane_recursive/` state-root naming
  - `recursive_botlane/` wrapper/template references
- Minimum expected touch set:
  - `.autoloop_recursive/rerun_command.sh`
  - `.autoloop_recursive/framework_evolution_charter.md`
  - `.autoloop_recursive/framework_roadmap.md`
  - any other top-level `.autoloop_recursive/` maintained docs or helper files still carrying legacy literals, such as `bootstrap_seed.md`, `framework_gap_ledger.md`, `workflow_candidate_ledger.md`, and `last_action.env` if it remains active
- Separate maintained memory/docs from generated history:
  - likely operational-history candidates include `.autoloop_recursive/recovery.log` and archived task records under `.autoloop_recursive/tasks/`
  - those may remain only if enumerated as exact justified paths

### 4. Add regression coverage

- Add/adjust strictness tests so they fail when:
  - a legacy literal appears in an in-contract repo-root artifact file
  - a new active artifact file is added under `.autoloop_recursive/` or `.autoloop/` without matching the explicit policy
  - the allowlist widens from exact paths into prefix-based exclusions
- Preserve the narrow historical allowance for `legacy_docs/*.md` and `tests/strictness/test_no_compat.py`.
- Keep the existing hidden-construction, import, CLI, and compatibility-surface checks unchanged unless a scanner helper refactor requires local rewiring.

## Milestones

1. Introduce explicit repo-root artifact scan policy and scope assertions in `tests/strictness/test_no_compat.py`.
2. Migrate top-level `.autoloop_recursive/` maintained files to the Botlane vocabulary defined by `recursive_botlane/`.
3. Lock the final exact exception set, run the targeted strictness suite, perform the literal scan over the maintained tree plus covered artifact files, then run full `python -m pytest`.

## Validation

- `python -m pytest tests/strictness/test_no_compat.py`
- repo literal scan over:
  - maintained product tree already covered by strictness
  - top-level `.autoloop_recursive/` maintained files
  - any exact `.autoloop/` or `.autoloop_recursive/` operational-path exceptions retained by policy
- `python -m pytest`

## Compatibility Notes

- No runtime, CLI, provider, overlay, or package-behavior changes are intended.
- The only intentional tightening is repository policy: active repo-root artifact trees lose the ability to hide legacy literals via omitted scan roots.
- Generated historical records remain acceptable only when the final test documents them as exact operational exceptions.

## Regression Risks

- Overbroad artifact scanning could start failing on generated history instead of maintained files; the policy must distinguish maintained memory from operational records explicitly.
- Manual doc/script rewrites in `.autoloop_recursive/` can drift from the current `recursive_botlane/` contract if they are not normalized from the canonical Botlane templates/CLI wording.
- Allowlist sprawl is a real failure mode; the implementation should minimize exceptions by migrating maintained files first.

## Rollback

- Revert the strictness policy refactor and artifact-file renames together if the new scope produces false positives outside the intended maintained/operational boundary.
- Do not keep a partial state where `.autoloop_recursive/` is scanned but the maintained files still use legacy language.
