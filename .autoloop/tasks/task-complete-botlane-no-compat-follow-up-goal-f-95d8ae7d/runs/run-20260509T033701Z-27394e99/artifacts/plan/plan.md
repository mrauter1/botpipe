# Botlane No-Compat Artifact-Tree Cleanup Plan

## Objective

Close the remaining no-compat gap by making strictness explicitly cover active repo-root artifact trees and by removing legacy Autoloop literals from maintained artifact files instead of relying on scan-root omission.

## Current State

- `tests/strictness/test_no_compat.py` only scans maintained product roots plus optional files; `.autoloop_recursive/` and `.autoloop/` are outside `ACTIVE_SCAN_ROOTS` and `BRANDING_SCAN_ROOTS`.
- `recursive_botlane/` and its templates already define the canonical Botlane naming and CLI contract.
- Top-level `.autoloop_recursive/` still contains maintained files with legacy literals, including the named request files and other active memory docs.
- Repo-local `.autoloop/` has no maintained non-task source files today, but the active run tree under `.autoloop/tasks/task-complete-botlane-no-compat-follow-up-goal-f-95d8ae7d/runs/run-20260509T033701Z-27394e99/` contains runtime-owned operational records that already emit legacy literals through task text and repo-relative paths.

## Implementation Contract

### 1. Close the scanner-root loophole

- Refactor the strictness scan setup so repo-root artifact policy is expressed explicitly instead of being implied by `ACTIVE_SCAN_ROOTS` membership.
- Keep the maintained product-tree scan intact for `botlane/`, `botlane_optimizer/`, `docs/`, `recursive_botlane/`, `tests/`, and optional top-level files.
- Add explicit artifact-tree coverage helpers/constants for repo-root operational trees:
  - `.autoloop_recursive/` as active maintained recursive memory
  - `.autoloop/` as repo-local operational storage with an explicit active-run policy centered on the authoritative current run tree
- Update the scope assertions so adding a new active artifact file under either root cannot silently bypass the no-compat scan just because the root is absent from a root tuple.

### 2. Enforce the artifact-tree policy in tests

- Prefer migration over exceptions for maintained files.
- Treat top-level `.autoloop_recursive/` text files as in-contract unless they are exact operational records that cannot be renamed safely.
- For repo-local `.autoloop/`, distinguish three categories explicitly:
  - no maintained non-task source files currently exist outside task-history storage
  - the current active run tree under `.autoloop/tasks/task-complete-botlane-no-compat-follow-up-goal-f-95d8ae7d/runs/run-20260509T033701Z-27394e99/` is in scope for policy, because it is active repo-root operational content
  - only runtime-owned or immutable-generated files from that active run tree may remain as operational exceptions
- Build the `.autoloop/` exception set from the exact current run inventory, not from directory prefixes. Minimum expected exact-path review set:
  - `request.md`
  - `raw_phase_log.md`
  - `run.json`
  - `events.jsonl`
  - `decisions.txt`
  - `sessions/plan.json`
  - current run-local artifact files under `artifacts/plan/`
- Any active `.autoloop/` file outside that exact operational-record set must be Botlane-clean or removed from the active artifact policy.
- Do not use directory-prefix exclusions or wildcard “ignore all `.autoloop/**`” rules.

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
  - repo-local `.autoloop/` exceptions should stay limited to the exact current-run operational records above rather than widening to `.autoloop/tasks/**`

### 4. Add regression coverage

- Add/adjust strictness tests so they fail when:
  - a legacy literal appears in an in-contract repo-root artifact file
  - a new active artifact file is added under `.autoloop_recursive/` or under the active `.autoloop/tasks/.../runs/...` tree without matching the explicit policy
  - the allowlist widens from exact paths into prefix-based exclusions
- Preserve the narrow historical allowance for `legacy_docs/*.md` and `tests/strictness/test_no_compat.py`.
- Keep the existing hidden-construction, import, CLI, and compatibility-surface checks unchanged unless a scanner helper refactor requires local rewiring.

## Milestones

1. Introduce explicit repo-root artifact scan policy and scope assertions in `tests/strictness/test_no_compat.py`, including the active `.autoloop/tasks/.../runs/...` inventory.
2. Migrate top-level `.autoloop_recursive/` maintained files to the Botlane vocabulary defined by `recursive_botlane/`.
3. Lock the final exact exception set for `.autoloop_recursive/` operational records and the active current-run `.autoloop/` files, run the targeted strictness suite, perform the literal scan over the maintained tree plus covered artifact files, then run full `python -m pytest`.

## Validation

- `python -m pytest tests/strictness/test_no_compat.py`
- repo literal scan over:
  - maintained product tree already covered by strictness
  - top-level `.autoloop_recursive/` maintained files
  - the exact active current-run `.autoloop/` operational-record set
  - any exact `.autoloop_recursive/` operational-path exceptions retained by policy
- `python -m pytest`

## Compatibility Notes

- No runtime, CLI, provider, overlay, or package-behavior changes are intended.
- The only intentional tightening is repository policy: active repo-root artifact trees lose the ability to hide legacy literals via omitted scan roots.
- Generated historical records remain acceptable only when the final test documents them as exact operational exceptions, and repo-local `.autoloop/` exceptions must stay bounded to the exact active current-run record set instead of broad task-history prefixes.

## Regression Risks

- Overbroad artifact scanning could start failing on generated history instead of maintained files; the policy must distinguish maintained memory from operational records explicitly.
- Under-scoping `.autoloop/` to a non-task invariant would leave the current active run tree outside the contract and recreate the verifier's loophole; the implementation must enumerate that exact operational-record slice.
- Manual doc/script rewrites in `.autoloop_recursive/` can drift from the current `recursive_botlane/` contract if they are not normalized from the canonical Botlane templates/CLI wording.
- Allowlist sprawl is a real failure mode; the implementation should minimize exceptions by migrating maintained files first.

## Rollback

- Revert the strictness policy refactor and artifact-file renames together if the new scope produces false positives outside the intended maintained/operational boundary.
- If the active `.autoloop/` inventory is mis-scoped, tighten it back to the exact current-run record list rather than reintroducing `.autoloop/tasks/**`-style exclusions.
- Do not keep a partial state where `.autoloop_recursive/` is scanned but the maintained files still use legacy language.
