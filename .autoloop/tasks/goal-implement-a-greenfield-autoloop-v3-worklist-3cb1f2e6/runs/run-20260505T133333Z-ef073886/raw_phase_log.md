# Autoloop Raw Phase Log (run-20260505T133333Z-ef073886)


---
run_id=run-20260505T133333Z-ef073886 | entry=run_state
---
workspace=/home/rauter/autoloop_v3_bkp/autoloop_v3
pairs=plan,implement,test,audit
request_file=/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6/runs/run-20260505T133333Z-ef073886/request.md
session_mode=persistent


---
run_id=run-20260505T133333Z-ef073886 | entry=session_turn | pair=plan | phase=producer | cycle=1 | attempt=1 | thread_id=019df858-124c-7df2-9750-8ea2d08f9fb2
---
provider=codex
mode=start
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/plan_producer.md
session_id=019df858-124c-7df2-9750-8ea2d08f9fb2


---
run_id=run-20260505T133333Z-ef073886 | entry=phase_output | pair=plan | phase=producer | process=codex-agent | cycle=1 | attempt=1 | thread_id=019df858-124c-7df2-9750-8ea2d08f9fb2
---
I’m treating this as a planning pass for the full-suite compatibility recovery after repo-local `workflows/` support landed. I’ll inspect the authoritative run artifacts and the workflow-resolution/optimization/runtime areas that the failing suites point at, then I’ll write an implementation-ready plan into the run-local planning files.

I’ve confirmed there are no later clarifications in the raw log and the run-local planning artifacts are mostly empty. Next I’m mapping the failure clusters to the concrete runtime and helper modules so the plan stays centered on shared contracts rather than scattered test-specific patches.

The search results are already showing the contract split: discovery/resolution semantics now straddle `workflows/`, `.autoloop/workflows/`, and installed `autoloop/workflows/`, while optimization helpers and packaged workflow tests still assert canonical stored paths. I’m drilling into the actual resolver/catalog/manifest code now so the plan can isolate the shared fixes and the regression surfaces they touch.

I’ve got the main shared modules. The likely repair points are concentrated rather than broad: catalog root precedence and metadata normalization in `autoloop/core/workflow_catalog.py`, workspace/reference persistence in runtime inspection paths, and optimizer artifact normalization in `autoloop_optimizer/optimization.py`. I’m pulling the exact functions and failing test cases that define those contracts so the plan can specify milestones and rollback points precisely.

I’ve confirmed the resolver has two distinct loading paths: catalog entries with importable package modules versus isolated path loads. The risky seam is where repo-local `workflows/` entries are now treated as importable `workflows.*` packages for named/path resolution, while explicit class references and optimizer manifests still depend on older isolated or package-path behavior. I’m running the targeted suites with the project venv next so the plan reflects the actual current breakpoints, not just inferred ones.

The targeted failures line up cleanly with the request. Resolver regressions are all from the same structural shift: repo-local `workflows/` is winning discovery and import-based loading in places where the older contract still expects `.autoloop/workflows/` precedence or isolated module loading. Optimizer failures are downstream: observability validation is rejecting test bundles early, which then zeroes eligible runs and hides later route-tag behavior, and the selected-workflow manifest now records repo-local roots where older publication contracts still expect package-style `autoloop/workflows/...` paths.

The representative packaged-workflow failures aren’t random. They split into two central contracts: compile-time control-route declarations in the packaged workflows themselves, and runtime/packaging helpers that still assume installed-package surfaces under `autoloop/workflows/...` when seeding temp repos, evidence paths, and selected-workflow source manifests. I’m checking those shared interfaces now so the plan can sequence them in a way that avoids chasing suite-by-suite fallout.

I have enough to pin the work into concrete buckets now. The remaining details I’m checking are the route-contract constants and the helper installers that seed temp repos for packaged-workflow tests, because those decide whether this should be a two-phase or three-phase implementation plan.

I’ve finished the analysis pass and I’m writing the run-local plan artifacts now. The plan will break the work into shared-contract slices: first catalog/loader resolution semantics, then optimizer and selected-workflow manifest normalization, then packaged-workflow route/artifact contract repair plus full-suite proof so the implementation phase can work in dependency order instead of patching suites one by one.

I’m applying the artifact edits now: `plan.md` will become the single human-readable source of truth, `phase_plan.yaml` will get the ordered phase payload, and I’ll append only the non-obvious compatibility decisions needed to keep later turns from drifting back into suite-by-suite patching.

The artifacts are written. I’m doing a quick integrity pass now to catch any YAML/format drift before I close: the main things to verify are the `phases:` block shape and that the decisions stayed under the current runtime-created header only.

The integrity check found one issue: `phase_plan.yaml` still has the runtime seed `phases: []` line above the authored phase block, which would make the YAML invalid. I’m removing only that stale empty list so the runtime-owned metadata stays intact and the authored payload is valid.

Updated the run-local planning artifacts:

- [plan.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6/runs/run-20260505T133333Z-ef073886/artifacts/plan/plan.md)
- [phase_plan.yaml](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6/runs/run-20260505T133333Z-ef073886/artifacts/plan/phase_plan.yaml)
- [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6/runs/run-20260505T133333Z-ef073886/artifacts/plan/feedback.md)
- [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6/runs/run-20260505T133333Z-ef073886/decisions.txt)

The plan is a 3-phase recovery sequence: first restore workflow resolution semantics, then fix optimizer observability/source-manifest contracts, then repair the remaining packaged-workflow route/artifact regressions and prove the full suite. I also validated the targeted failure clusters with the project venv and used those concrete breakpoints to drive the phase boundaries rather than broad speculative cleanup.


---
run_id=run-20260505T133333Z-ef073886 | entry=session_turn | pair=plan | phase=verifier | cycle=1 | attempt=1 | thread_id=019df858-124c-7df2-9750-8ea2d08f9fb2
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/plan_verifier.md
session_id=019df858-124c-7df2-9750-8ea2d08f9fb2


---
run_id=run-20260505T133333Z-ef073886 | entry=phase_output | pair=plan | phase=verifier | process=codex-agent | cycle=1 | attempt=1 | thread_id=019df858-124c-7df2-9750-8ea2d08f9fb2
---
I’m verifying the run-local plan artifacts against the request, the decisions ledger, and the concrete failure evidence from the targeted suites. I’ll update the criteria checkboxes to match the actual audit result, append any findings with stable IDs to `feedback.md`, and then return the loop-control status.

I found one blocking issue and it is central, not cosmetic: the plan locks in repo-local canonical-name precedence for named workflow resolution, but the request and the failing reference-resolution tests explicitly show mixed-root cases where the older contract still expects `.autoloop/workflows/` to win. I’m recording that as a blocking finding and marking the criteria accordingly.

Scope considered
- The run-local planning artifacts in `artifacts/plan/`
- The immutable request snapshot and current turn `decisions.txt`
- The concrete workflow-resolution tests directly cited by the request and implicated by the plan’s Phase 1 direction

What I analyzed
- The Phase 1 resolution strategy in `plan.md`
- The ordered phase contract in `phase_plan.yaml`
- The planner-authored non-obvious direction recorded in `decisions.txt`
- The mixed-root reference expectations in `tests/runtime/test_workflow_reference_resolution.py`

What I reviewed
- `plan.md`
- `phase_plan.yaml`
- `criteria.md`
- `feedback.md`
- `decisions.txt`
- Request coverage for workflow-resolution, optimizer, packaged-workflow, and full-suite acceptance criteria

Key findings / decisions
- Recorded `PLAN-001` as `blocking` in `feedback.md`.
- The plan currently hard-codes repo-local `workflows/` named-resolution precedence, but the request and failing reference-resolution tests explicitly require restoring mixed-root cases where `.autoloop/workflows/` remains authoritative.
- Updated `criteria.md` to leave `Intent Fidelity`, `Behavioral Safety`, `Completeness`, and `Feasibility / Compatibility` unchecked; `Technical Debt` remains checked.

Open issues / next step
- Planner needs to revise Phase 1 so named/workspace resolution restores the observed `.autoloop/workflows/` contract in mixed-root cases, then add a superseding direction for the conflicting decision entry before this plan can be marked complete.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"INCOMPLETE"}
</loop-control>


---
run_id=run-20260505T133333Z-ef073886 | entry=session_turn | pair=plan | phase=producer | cycle=2 | attempt=1 | thread_id=019df858-124c-7df2-9750-8ea2d08f9fb2
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/plan_producer.md
session_id=019df858-124c-7df2-9750-8ea2d08f9fb2


---
run_id=run-20260505T133333Z-ef073886 | entry=phase_output | pair=plan | phase=producer | process=codex-agent | cycle=2 | attempt=1 | thread_id=019df858-124c-7df2-9750-8ea2d08f9fb2
---
I’m revising the plan around the verifier’s blocking finding. First I’m tightening the Phase 1 contract against the actual mixed-root tests so the plan stops hard-coding repo-local name precedence where the older `.autoloop/workflows/` catalog contract still has to win.

The failing suite is more specific than just alias restoration. I’m pulling the nearby reference-resolution cases now so the revised Phase 1 contract covers the exact mixed-root rule the tests already encode, not a vague “workspace beats repo-local sometimes” statement.

I have the concrete contract now from the tests: bare names and workspace aliases stay bound to `.autoloop/workflows/` when that catalog has the key, while repo-local `workflows/` remains an explicit path/module surface and a fallback only when the workspace catalog does not claim the key. I’m rewriting Phase 1 and the machine-readable phase to that rule, then I’ll supersede the stale decision line in the current turn’s decision block.

The precedence fix is written. I’m checking the exact rewritten sections and the new decision block now to make sure the superseding direction is explicit enough for the verifier and later turns.

Updated the run-local planning artifacts to address `PLAN-001`.

The Phase 1 contract now matches the mixed-root tests: bare workflow names and workspace aliases stay authoritative from `.autoloop/workflows/`, while repo-local `workflows/` remains an explicit path/module surface and a named fallback only when the workspace catalog does not own the key. I also appended a superseding decision under the current turn header so later turns do not follow the stale repo-local-precedence direction.

Changed files:
- [plan.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6/runs/run-20260505T133333Z-ef073886/artifacts/plan/plan.md)
- [phase_plan.yaml](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6/runs/run-20260505T133333Z-ef073886/artifacts/plan/phase_plan.yaml)
- [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6/runs/run-20260505T133333Z-ef073886/artifacts/plan/feedback.md)
- [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/goal-implement-a-greenfield-autoloop-v3-worklist-3cb1f2e6/runs/run-20260505T133333Z-ef073886/decisions.txt)


---
run_id=run-20260505T133333Z-ef073886 | entry=session_turn | pair=plan | phase=verifier | cycle=2 | attempt=1 | thread_id=019df858-124c-7df2-9750-8ea2d08f9fb2
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/plan_verifier.md
session_id=019df858-124c-7df2-9750-8ea2d08f9fb2


---
run_id=run-20260505T133333Z-ef073886 | entry=phase_output | pair=plan | phase=verifier | process=codex-agent | cycle=2 | attempt=1 | thread_id=019df858-124c-7df2-9750-8ea2d08f9fb2
---
I’m doing the re-review against the revised Phase 1 contract and the superseding decision block. If the mixed-root `.autoloop/workflows/` authority is now explicit across the narrative plan, phase YAML, and decisions history, I’ll mark the criteria complete and record the blocker as resolved.

The revised plan is internally consistent again: the narrative, phase YAML, and superseding decision block now all say the same mixed-root rule. I’m marking the criteria complete and appending a short closure note for `PLAN-001` so the feedback history shows why this verifier pass can close cleanly.

Scope considered
- The run-local planning artifacts in `artifacts/plan/`
- The immutable request snapshot and current `decisions.txt`
- The mixed-root workflow-resolution tests and the revised Phase 1 contract

What I analyzed
- The revised Phase 1 narrative in `plan.md`
- The updated `restore-workflow-resolution-contract` entry in `phase_plan.yaml`
- The superseding direction added under the current planner header in `decisions.txt`
- The closure history for `PLAN-001` in `feedback.md`

What I reviewed
- `plan.md`
- `phase_plan.yaml`
- `criteria.md`
- `feedback.md`
- `decisions.txt`
- Request coverage for workflow-resolution, optimizer, packaged-workflow, and full-suite acceptance expectations

Key findings / decisions
- No remaining blocking findings.
- `PLAN-001` is now resolved and recorded as such in `feedback.md`.
- Updated `criteria.md` so all verification checkboxes are checked.

Open issues / next step
- No verifier blockers remain on the planning artifacts. The plan can proceed to implementation with the mixed-root `.autoloop/workflows/` authority explicitly preserved for bare names and aliases.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"COMPLETE"}
</loop-control>


---
run_id=run-20260505T133333Z-ef073886 | entry=phase_scope_resolved
---
phase_mode=single
phase_ids=restore-workflow-resolution-contract,reconcile-optimizer-source-contracts,repair-packaged-workflow-contracts-and-proof
explicit=True
current_phase_index=0


---
run_id=run-20260505T133333Z-ef073886 | entry=session_turn | pair=implement | phase=producer | cycle=1 | attempt=1 | thread_id=019df85f-e454-7e32-a85f-f676e36c2390
---
provider=codex
mode=start
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/implement_producer.md
session_id=019df85f-e454-7e32-a85f-f676e36c2390


---
run_id=run-20260505T133333Z-ef073886 | entry=phase_output | pair=implement | phase=producer | process=codex-agent | cycle=1 | attempt=1 | thread_id=019df85f-e454-7e32-a85f-f676e36c2390
---
I’m restoring the workflow-resolution contract for this phase, starting with the phase artifacts and the loader/catalog code that changed around repo-local `workflows/` support. After that I’ll reproduce the targeted failures, patch the shared resolution path centrally, and verify the named resolution suites before widening further.

The phase artifacts confirm the intended split: workspace catalog stays authoritative for bare names and aliases, while explicit repo-local references keep isolated loading semantics. I’m mapping that against the actual loader/catalog implementation now and reproducing the resolution failures before editing.

I’ve reproduced the five expected failures. They line up cleanly with two central issues: named precedence currently favors repo-local `workflows/`, and package-style validation/import paths are being applied to explicit repo-local directory/file/class loads that should stay isolated.

The fix is narrower than it first looked. I don’t need to rework the worklist code at all; the breakage is concentrated in catalog precedence and one branch in the loader that treats repo-local catalog entries like package-module imports even when the caller used a path/class-style reference.

I’m editing the catalog and loader now. The change is to separate named-resolution authority from import metadata: `.autoloop/workflows` wins mixed-root names and aliases, while repo-local catalog entries still keep `workflows.*` metadata but load through the isolated workspace namespace unless the caller intentionally used a package-module import.

I hit a small patch mismatch while updating one call site. I’m re-reading the affected loader block and patching the remaining sites in place rather than forcing a broad rewrite.

I’ve fixed the catalog side and the package-contract gate. I’m also hardening the direct class-reference branch so workspace classes reload through the isolated namespace instead of reusing `workflows.*` modules when that would violate the older contract.

The central changes are in place. I’m running the resolution suites that define this contract first, plus the adjacent green catalog suite, before I touch any notes or widen scope.

The contract suites are green. I’m checking the adjacent surfaces most likely to notice this split next: workspace invocation/context and the broader stdlib/extensions capability helpers that consume workflow inspection metadata.

The regression pattern is clear now. Repo-local named fallback needs module-style loading for intra-`workflows.*` imports and stable class identity, but explicit repo-local paths/classes still need isolated loading. I’m tightening that distinction instead of treating every workspace catalog entry the same way.

The remaining failures come from one overreach: I made imported class objects behave like explicit path references. That breaks repo-local named workflows that legitimately use the `workflows.*` namespace and helper seams that pass around the resolved class object. I’m narrowing that back now.

I’ve narrowed the imported-class branch back to the pre-existing behavior, while keeping the path-based isolation and named repo-local module fallback split. Re-running the adjacent suites now to confirm the contract is actually coherent rather than just green on the narrow file.

I’ve got two remaining compatibility seams: repo-local named module imports need to find sibling `params.py`, and the same `workflows.*` namespace must stay root-isolated across different repos. I’m reading the scaffolding helpers and the import path code together before the next patch so I only touch this once.

I found the remaining root cause for the stdlib/helper failures: the loader’s repo-module import path was not evicting stale `workflows.*` modules at all. That left cross-test root leakage in place, which then broke both stable class identity and `params.py` discovery. I’m restoring that guard in the runtime loader now.

The stale `workflows.*` cache issue was the missing piece. The targeted stdlib/helper failures that depended on named repo-local resolution are now green, so I’m rerunning the broader adjacent suite instead of chasing individual assertions.

The resolution phase is green on its own contract and the adjacent suites it can reasonably affect. I’m doing one bounded readout of the next failure cluster now so the notes and decision log capture a clean handoff instead of stopping at “fixed some loader code.”

I’ve validated the phase boundary: the workflow-resolution contract is green, the adjacent suites stay green, and the next failures now fall cleanly into the optimizer/source-manifest cluster rather than this loader/catalog contract. I’m writing that into the phase notes and decision ledger before closing out.

Scope considered

- Phase-local workflow resolution only: mixed-root catalog authority, repo-local named/path/class loading behavior, and capability inspection metadata.

What I analyzed

- [workflow_catalog.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/workflow_catalog.py)
- [loader.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/loader.py)
- [workflow_capabilities.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/workflow_capabilities.py)
- Targeted failures in `tests/runtime/test_workflow_reference_resolution.py`, then adjacent suites that consume the same contract.

What I changed

- Made effective catalog resolution prefer `.autoloop/workflows` over repo-local `workflows/` for bare names and aliases, without changing the published `workflow_search_roots(...)` ordering.
- Split repo-local named references from explicit repo-local path/directory references in the loader:
  - named repo-local catalog references resolve through `workflows.*` modules,
  - explicit repo-local path and directory references still resolve through isolated `_autoloop_workspace_workflows.*` modules,
  - installed package workflows still use the package-module contract.
- Stopped applying package export validation to workspace/repo-local catalog entries in capability inspection.
- Made capability lookup search `include_shadowed=True` so explicit shadowed paths keep their metadata.
- Restored stale `workflows.*` module eviction when switching roots, so repo-local named workflow imports do not leak across workspaces.

Key findings / decisions

- The breakage was centralized, not workflow-by-workflow: catalog key authority and loader import mode had drifted apart.
- Repo-local named fallback must keep `workflows.*` identity for cross-workflow imports and stable model names; isolation is only correct for explicit repo-local path/directory references.
- Validated green:
  - `tests/runtime/test_workflow_reference_resolution.py`
  - `tests/runtime/test_workflow_catalog_roots.py`
  - `tests/runtime/test_runtime_cli_metadata_integration.py`
  - `tests/runtime/test_workspace_and_context.py`
  - `tests/unit/test_stdlib_and_extensions.py`

Open issues / next step

- The next failure cluster is still `tests/unit/test_optimization_helpers.py`: 10 failures remain, centered on observability bundle validation, trace-corpus eligibility/filtering, and canonical selected-workflow source-manifest paths.
- I did not run full `.venv/bin/python -m pytest` after this phase, and the repository is not globally green yet.


---
run_id=run-20260505T133333Z-ef073886 | entry=session_turn | pair=implement | phase=verifier | cycle=1 | attempt=1 | thread_id=019df85f-e454-7e32-a85f-f676e36c2390
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/implement_verifier.md
session_id=019df85f-e454-7e32-a85f-f676e36c2390


---
run_id=run-20260505T133333Z-ef073886 | entry=phase_output | pair=implement | phase=verifier | process=codex-agent | cycle=1 | attempt=1 | thread_id=019df85f-e454-7e32-a85f-f676e36c2390
---
I’m reviewing the phase-local loader/catalog changes against the acceptance criteria and the recorded decisions first, then I’ll verify whether the implementation notes and test evidence justify marking the phase complete.

The recorded decisions and implementation notes line up with the intended split. I’m reading the final loader/catalog code directly now to check for any hidden compatibility holes that the targeted suite might miss before I mark criteria.

I found one place where the implementation may still be too coarse: whole-entry shadowing in the effective catalog can drop a repo-local unique alias even when only the workflow name collides with `.autoloop/workflows`. I’m reproducing that specific mixed-root case before I decide whether it’s a blocking contract miss.

I have two blocking contract gaps, both within the phase scope. I’m recording them in the verifier artifact now; the criteria stay incomplete because the implementation still misses one key-level fallback case and one explicit class-reference behavior promised in the phase contract.

Scope considered

- Phase-local workflow-resolution changes only: [workflow_catalog.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/workflow_catalog.py), [loader.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/runtime/loader.py), and [workflow_capabilities.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/core/workflow_capabilities.py), plus the active phase artifacts and decisions ledger.

What I analyzed

- The accepted phase contract, implementation notes, and run-local decisions.
- The final loader/catalog/capability code paths for named resolution, explicit path/class loading, and shadowed-entry metadata recovery.
- The validation evidence cited by the implementer, and two focused repros for mixed-root alias fallback and direct repo-local class-object resolution.

What I reviewed

- `criteria.md`: left incomplete because blocking findings remain.
- `feedback.md`: appended `IMP-001` and `IMP-002` as blocking findings.
- The implementation does satisfy the tested `.autoloop` authority split and adjacent suite stability, but it still misses two contract details that were explicitly in scope.

Key findings / decisions

- `IMP-001` blocking: whole-entry shadowing in `_effective_catalog` still drops unique lower-precedence repo-local aliases when only the workflow name collides, so repo-local named fallback is not actually key-based.
- `IMP-002` blocking: `_resolve_imported_class_reference` still leaves direct repo-local `workflows.*` class-object references in the `workflows.*` namespace instead of reloading them through `_autoloop_workspace_workflows.*`, which conflicts with the explicit class-reference requirement in the phase contract.

Open issues / next step

- Fix key-level mixed-root shadowing so unclaimed repo-local aliases survive collisions with `.autoloop/workflows`.
- Fix direct repo-local class-object references to use isolated loading, and move any internal callers that need named `workflows.*` metadata onto the named catalog resolution path instead of relying on class-object round-trips.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"INCOMPLETE"}
</loop-control>
