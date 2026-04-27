# Autoloop Raw Phase Log


---
run_id=run-20260427T164535Z-3624382b | entry=run_state
---
workspace=/home/rauter/autoloop_v3_bkp/autoloop_v3
pairs=plan,implement,test
request_file=/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/runs/run-20260427T164535Z-3624382b/request.md
session_mode=persistent


---
run_id=run-20260427T164535Z-3624382b | entry=session_turn | pair=plan | phase=producer | cycle=1 | attempt=1 | thread_id=019dcfd5-0188-7a40-905a-e48e0e87c12a
---
provider=codex
mode=start
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/plan_producer.md
session_id=019dcfd5-0188-7a40-905a-e48e0e87c12a


---
run_id=run-20260427T164535Z-3624382b | entry=phase_output | pair=plan | phase=producer | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dcfd5-0188-7a40-905a-e48e0e87c12a
---
I’m treating this as a planning turn: first I’ll read the authoritative request/log context, inspect the repository surfaces named in the cycle instructions, and identify a single high-leverage architecture improvement direction before I touch the plan artifacts.

I’m gathering the authoritative task context and a repo-wide map now. After that I’ll narrow to the workflow/helper seams that show the most repeated validation or publication logic.

The repository is now mapped enough to focus on the actual leverage point. Next I’m reading the architecture docs and scanning workflow/stdlib/test surfaces for repeated validation, publication, and prompt patterns that are still local instead of shared.

I’ve confirmed the existing shared seams: validation, typed artifact readers, parameter bundles, lifecycle/composition, and the new optimization helpers. Now I’m checking where authoring is still noisy despite those seams, especially prompt family duplication and workflow-local publication tails that remain outside the shared surfaces.

I’ve found a real cross-workflow pattern: the selected-workflow and portfolio families are still duplicating nearly identical `prompts/README.md` boilerplate and step-local framing prompt structure, even after the docs formalized the compact prompt-contract style. I’m checking the recursive ledgers now to see whether that debt is already recorded or whether this cycle should make it the primary consolidation target.

The ledgers point to a clearer remaining gap than prompt cleanup: selected-workflow context capture still looks like the main unresolved authoring-surface convergence candidate after prompt compaction and validation migration. I’m verifying how much duplication still exists across `adaptation`, `evaluation`, `diagnostics`, `refinement`, `decomposition`, and the optimizer family before I lock the plan to that direction.

Plan direction is set. I’m writing a `consolidate` plan around selected-workflow context-capture convergence: one additive authoring-only helper seam, migration of the adaptation/eval/diagnostic/decomposition/optimizer family, then scoped proof/docs/memory closeout.

I’m updating the plan artifacts now. The edits are limited to the planner-owned files plus the current-turn decision block; I’m not touching verifier-owned criteria or implementation files.

The plan artifacts are written. I’m validating the YAML and doing one consistency pass over the planner-owned files before I close the turn.

`python` isn’t on the shell path here, so I’m re-running the required YAML parse with the repository venv interpreter to satisfy the planner contract explicitly.

The venv interpreter exists but doesn’t have `PyYAML` installed. I’m checking for another local Python interpreter with `yaml.safe_load` available so the phase file still gets validated as required.

Updated the planning artifacts for cycle 2 in [plan.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/plan/plan.md), [phase_plan.yaml](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/plan/phase_plan.yaml), [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/plan/feedback.md), and [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/decisions.txt). The plan stays in `consolidate` mode and targets selected-workflow context-capture/helper convergence rather than any new workflow addition.

The plan records the pre-change audit, options considered, chosen improvement, three ordered phases, compatibility constraints, regression risks, and the expected boilerplate reduction. `phase_plan.yaml` parsed successfully with `yaml.safe_load` and now contains 3 planned phases.


---
run_id=run-20260427T164535Z-3624382b | entry=session_turn | pair=plan | phase=verifier | cycle=1 | attempt=1 | thread_id=019dcfd5-0188-7a40-905a-e48e0e87c12a
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/plan_verifier.md
session_id=019dcfd5-0188-7a40-905a-e48e0e87c12a


---
run_id=run-20260427T164535Z-3624382b | entry=phase_output | pair=plan | phase=verifier | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dcfd5-0188-7a40-905a-e48e0e87c12a
---
I’m verifying the plan artifacts now against the request, the current decision ledger, and the phase contract. I’ve found no blocking safety or intent-fidelity gaps so far; I’m tightening the verifier feedback around scope clarity and avoiding an unnecessary helper layer.

I’m updating only the verifier-owned criteria and feedback files now. The repository source and the shared decisions ledger stay untouched.

The verifier updates are in place. I’m doing a last readback of the criteria and feedback files, plus a quick YAML sanity check, before I finalize the verification result.

Scope considered

Authoritative request snapshot, raw log clarification state, the planner-produced plan artifacts under `.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/plan/`, and the shared decisions ledger for this turn.

What I analyzed

Intent fidelity against the cycle request, cycle-mode choice, pre-change audit coverage, new-workflow gate handling, compatibility and regression controls, phase decomposition quality, and whether the plan stays small/local instead of introducing avoidable framework debt.

What I reviewed

`plan.md`, `phase_plan.yaml`, `feedback.md`, `criteria.md`, and `decisions.txt`. I also re-validated `phase_plan.yaml` with `python3` plus `yaml.safe_load`; it parses successfully and contains 3 coherent planned phases.

Key findings / decisions

No blocking findings. The plan is complete and safe to proceed with as a `COMPLETE` verification result.

Two non-blocking improvements were added to verifier feedback:
- `PLAN-001`: clarify whether `workflow_and_eval_to_refined_workflow_package` is intentionally untouched or part of the migration scope.
- `PLAN-002`: tighten the "new helper module vs private helper location" wording so implementation does not add an unnecessary wrapper layer.

All verification criteria are now checked in `criteria.md`.

Open issues / next step

Planner feedback can optionally incorporate the two non-blocking clarifications before implementation, but they do not block execution of the current plan.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"COMPLETE"}
</loop-control>


---
run_id=run-20260427T164535Z-3624382b | entry=phase_scope_resolved
---
phase_mode=single
phase_ids=selected-workflow-helper-convergence,workflow-family-migration,proof-docs-and-memory-closeout
explicit=True
current_phase_index=0


---
run_id=run-20260427T164535Z-3624382b | entry=session_turn | pair=implement | phase=producer | cycle=1 | attempt=1 | thread_id=019dcfdc-72cc-76c3-a946-4168bae3a2e6
---
provider=codex
mode=start
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/implement_producer.md
session_id=019dcfdc-72cc-76c3-a946-4168bae3a2e6


---
run_id=run-20260427T164535Z-3624382b | entry=phase_output | pair=implement | phase=producer | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dcfdc-72cc-76c3-a946-4168bae3a2e6
---
I’m starting with repo-wide audit and phase artifacts, then I’ll trace the selected-workflow helper family to find the consolidation point without widening scope.

I’ve confirmed the phase plan is already narrowed to selected-workflow helper convergence. Next I’m tracing the current writers and the workflows that still re-read their own artifacts to recover the same context.

I’ve narrowed the duplication: the four stdlib writers each re-resolve the same workflow identity, and several workflows still do a write-then-read just to recover `selected_workflow_name`. I’m checking the payload builders and optimization helper next so the seam fits the whole selected-workflow family instead of only one branch.

The active phase is narrower than the full cycle: phase 1 is the shared seam itself. I’m checking the phase plan and current exports now so I can keep this turn inside the helper-family boundary instead of drifting into the later workflow-migration phase.

The seam is clear now: keep the public helper names stable, add one private selected-workflow capture/writer module underneath them, and update the existing helper tests to assert against the shared capture path instead of each module’s old local resolver.

I have enough context to edit. I’m adding a private `stdlib` seam for selected-workflow capture/envelope writing, then rebasing the four public helper modules and the helper tests on that seam without changing artifact filenames or top-level payload shapes.

The structural patch mostly fits, but the test file context drifted. I’m splitting the edit into smaller hunks so the helper seam lands cleanly before I rewire the affected tests.

The shared seam is in place. I’m validating the helper-family tests first, then I’ll run the runtime workflows that depend on these public writers to make sure the payloads stayed byte-for-byte compatible at the top level.

The unit surface is clean. I’m running the workflow packages that consume these writers directly, plus the optimizer package that composes all three selected-workflow surfaces together, because that’s the main regression edge for this seam.

The seam changes are validated across the helper unit surface and all direct runtime consumers I targeted. What remains on this turn is phase-local bookkeeping: record the non-obvious decision, write concise implementation notes, and leave docs/memory migration deferred to the later planned phase.

I’m writing the phase notes and decision ledger now. The decision I’m freezing is to keep the seam private inside `stdlib` and preserve all existing public helper names, so later workflow migration can consume the shared capture object without expanding the public authoring surface prematurely.

Pytest dirtied a few `__pycache__` artifacts in the touched helper paths. I’m removing those generated files so the phase leaves only intentional source and note changes behind.

The repository actually tracks some cached bytecode files, so deleting them would create unrelated noise. I’m restoring those tracked cache artifacts exactly and leaving them otherwise untouched.

**Scope considered**

Active phase `selected-workflow-helper-convergence` only. I stayed inside the selected-workflow helper family, the direct consuming runtime workflows for regression proof, and the phase-local artifacts in `.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/`.

**What I analyzed**

I audited the current selected-workflow writers in [stdlib/adaptation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/stdlib/adaptation.py), [stdlib/refinement.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/stdlib/refinement.py), [stdlib/decomposition.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/stdlib/decomposition.py), and [stdlib/diagnostics.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/stdlib/diagnostics.py), plus the downstream workflow consumers and the unit/runtime tests around them. The repeated pattern was the same in each helper: resolve repo root, resolve the selected workflow, recover `selected_workflow_name`, rebuild the shared envelope, then write one artifact-local payload.

**What I changed**

I added a private seam at [stdlib/_selected_workflow.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/stdlib/_selected_workflow.py) that owns selected-workflow resolution, capture metadata, and shared envelope writing. I rebased the four public writers on that seam without changing their names, artifact filenames, or top-level JSON keys. I also updated [tests/unit/test_stdlib_and_extensions.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_stdlib_and_extensions.py) so the helper-family tests assert against the shared capture path instead of each module’s old local resolver imports, and I recorded the phase decision/notes in [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/decisions.txt) and [implementation_notes.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/implement/phases/selected-workflow-helper-convergence/implementation_notes.md).

**Key findings / decisions**

I kept the new seam private on purpose so this phase removes duplication without expanding the public authoring surface early. The public helper entrypoints remain stable, and the private seam now returns capture metadata that the later workflow-migration phase can use to remove write-read-validate tails. Validation passed on:
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
- `tests/runtime/test_workflow_to_eval_suite.py`
- `tests/runtime/test_workflow_run_history_to_failure_modes.py`
- `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
- `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
- `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`
- `tests/test_architecture_baseline_docs.py`

**Open issues / next step**

This phase did not migrate workflow capture handlers or update docs/recursive memory ledgers; that remains for the planned later phases. There is 1 new helper file added, no intentional source-file deletions, and the change is a small consolidation pass rather than a surface expansion.


---
run_id=run-20260427T164535Z-3624382b | entry=session_turn | pair=implement | phase=verifier | cycle=1 | attempt=1 | thread_id=019dcfdc-72cc-76c3-a946-4168bae3a2e6
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/implement_verifier.md
session_id=019dcfdc-72cc-76c3-a946-4168bae3a2e6


---
run_id=run-20260427T164535Z-3624382b | entry=phase_output | pair=implement | phase=verifier | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dcfdc-72cc-76c3-a946-4168bae3a2e6
---
I’m reviewing the phase-local implementation against the helper-convergence contract now. I’ll inspect the changed helper files, the shared decision ledger, and the proof notes first, then I’ll update only the verifier-owned phase artifacts.

I’ve finished the substantive review. The helper seam stays within scope, keeps the existing artifact contracts intact, and the validation evidence covers the main regression surfaces, so I’m updating the phase criteria as complete and recording that there are no scoped findings.

Scope considered

Active phase `selected-workflow-helper-convergence`, the shared decisions ledger, the phase-local implementation notes, the changed selected-workflow helper family under `stdlib/`, and the targeted unit/runtime proof surfaces the implementer recorded.

What I analyzed

Intent fidelity against the phase contract, whether one shared authoring-only seam now owns selected-workflow resolution plus envelope writing, whether artifact filenames and top-level schemas stayed unchanged, and whether the new seam adds avoidable surface or leaves material duplication behind.

What I reviewed

`stdlib/_selected_workflow.py`, `stdlib/adaptation.py`, `stdlib/refinement.py`, `stdlib/decomposition.py`, `stdlib/diagnostics.py`, the helper-family test updates in `tests/unit/test_stdlib_and_extensions.py`, `.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/decisions.txt`, and `.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/implement/phases/selected-workflow-helper-convergence/implementation_notes.md`. I also checked the recorded validation coverage for the direct runtime consumers and the optimizer workflow that composes all three selected-workflow surfaces.

Key findings / decisions

No blocking findings.
No non-blocking findings.
The implementation matches the accepted phase scope: one private authoring-only helper now owns shared selected-workflow resolution, `selected_workflow_name` capture, and envelope writing, while the existing public helper entrypoints and artifact contracts remain intact.
The phase-local criteria and feedback artifacts have been updated accordingly.

Open issues / next step

No review changes are required for this phase.
Planned later phases still need to migrate workflow capture handlers and perform docs/recursive-memory closeout, but that is outside this verifier turn’s scope.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"COMPLETE"}
</loop-control>


---
run_id=run-20260427T164535Z-3624382b | entry=session_turn | pair=test | phase=producer | cycle=1 | attempt=1 | thread_id=019dcfdc-72cc-76c3-a946-4168bae3a2e6
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/test_producer.md
session_id=019dcfdc-72cc-76c3-a946-4168bae3a2e6


---
run_id=run-20260427T164535Z-3624382b | entry=phase_output | pair=test | phase=producer | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dcfdc-72cc-76c3-a946-4168bae3a2e6
---
I’m checking the current helper-family proof first so I only add tests where the new seam still has regression risk. Then I’ll update the phase-local test strategy and feedback with an explicit coverage map.

I found one worthwhile gap: the new seam should prove that a captured selected-workflow context can be reused for multiple writes without silently re-resolving. I’m adding that regression test now, then I’ll document the phase coverage map and the test-only delta in the phase artifacts.

The new regression case is in. I’m running the helper-family unit suite again so the phase artifacts can point to a fresh proof run for the added capture-reuse case, not just the earlier implementation pass.

Scope considered

Active phase `selected-workflow-helper-convergence` only. I stayed on the new private selected-workflow seam, the helper-family unit coverage in `tests/unit/test_stdlib_and_extensions.py`, and the phase-local test artifacts under `.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/test/phases/selected-workflow-helper-convergence/`.

What I analyzed

I checked the new seam against the phase contract and existing tests to find the remaining regression gap. The notable uncovered behavior was capture reuse: the new helper should support multiple artifact writes from one resolved selected-workflow context without silently re-resolving.

What I changed

I added one focused unit regression test in [tests/unit/test_stdlib_and_extensions.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_stdlib_and_extensions.py) that proves `capture_selected_workflow(...)` can drive multiple `write_selected_workflow_artifact(...)` calls with a single workflow resolution while preserving the shared envelope fields. I also updated [test_strategy.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/test/phases/selected-workflow-helper-convergence/test_strategy.md) with an explicit behavior/invariant/edge/failure coverage map and appended a concise summary to [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/test/phases/selected-workflow-helper-convergence/feedback.md).

Key findings / decisions

The new seam already had broad public-helper coverage from the implementation pass, so I kept this turn narrow and added only the missing capture-reuse regression case. Fresh proof passed with `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py` (`95 passed`).

Open issues / next step

No test blocker remains in this phase. Workflow capture-step migration and closeout docs/memory proof are still out of scope here and belong to the later planned phases.


---
run_id=run-20260427T164535Z-3624382b | entry=session_turn | pair=test | phase=verifier | cycle=1 | attempt=1 | thread_id=019dcfdc-72cc-76c3-a946-4168bae3a2e6
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/test_verifier.md
session_id=019dcfdc-72cc-76c3-a946-4168bae3a2e6


---
run_id=run-20260427T164535Z-3624382b | entry=phase_output | pair=test | phase=verifier | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dcfdc-72cc-76c3-a946-4168bae3a2e6
---
I’m auditing the phase-local test coverage now. I’ll review the added seam tests, the updated strategy map, and the scoped proof run first, then I’ll update only the test-phase audit artifacts.

The added test closes the main remaining gap cleanly, and the strategy map now matches the actual regression surface. I’m marking the phase artifacts complete with no audit findings.

Scope considered

Active phase `selected-workflow-helper-convergence`, the phase-local test strategy and feedback artifacts, the added helper-seam unit coverage in `tests/unit/test_stdlib_and_extensions.py`, and the shared decisions for the selected-workflow helper boundary.

What I analyzed

Whether the tests now cover the new private seam itself, whether preserved behavior for the rebased public helpers is still protected, whether the added regression case would catch silent re-resolution or envelope drift, and whether the phase strategy records happy-path, edge, failure, and known-gap coverage clearly.

What I reviewed

`.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/test/phases/selected-workflow-helper-convergence/criteria.md`, `feedback.md`, `test_strategy.md`, the scoped tests around `capture_selected_workflow(...)` and `write_selected_workflow_artifact(...)`, and the proof result for `.venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py` (`95 passed`).

Key findings / decisions

No blocking findings.
No non-blocking findings.
The added seam test closes the main remaining regression gap by proving one captured selected-workflow context can drive multiple writes without another resolver call.
The updated strategy map matches the actual covered behaviors, preserved invariants, edge cases, failure paths, and declared known gap.

Open issues / next step

No audit changes are required for this phase.
Later phases still need workflow capture-step migration and broader closeout proof, but that is outside this test-auditor turn’s scope.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"COMPLETE"}
</loop-control>


---
run_id=run-20260427T164535Z-3624382b | entry=session_turn | pair=implement | phase=producer | cycle=1 | attempt=1 | thread_id=019dcfe9-e3c2-7733-af97-8cca1e269784
---
provider=codex
mode=start
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/implement_producer.md
session_id=019dcfe9-e3c2-7733-af97-8cca1e269784


---
run_id=run-20260427T164535Z-3624382b | entry=phase_output | pair=implement | phase=producer | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dcfe9-e3c2-7733-af97-8cca1e269784
---
I’m auditing the workflow-family migration scope first: reading the phase artifacts, the standing recursive memory files, and the workflow/helper surfaces that likely own the repeated selected-workflow capture logic before I decide the exact consolidation target.

The worktree is already dirty in unrelated areas, so I’m keeping scope tight to the active phase files and the shared selected-workflow seam. Next I’m tracing where the capture/publish boilerplate still exists across the targeted workflow family and what the previous convergence phase introduced.

The previous phase already created the private seam I need. I’m opening the four targeted workflows and the optimizer/eval helpers now to see exactly where each one still writes, re-reads, and revalidates the selected-workflow artifacts instead of using the capture metadata directly.

I’ve isolated the main debt: two workflows still do the exact `write -> exists -> read -> validate -> pull selected_workflow_name` pattern, the run-history workflow does it for the capability half of a two-artifact capture, and the decomposition/optimizer family still re-resolve selected-workflow context in adjacent helpers. I’m tightening those paths without changing artifact names or publication contracts.

I’ve got the edit boundary now. Before patching, I’m checking the helper tests that pin `stdlib/evaluation.py` and `stdlib/optimization.py`, because those are the two adjacent seams most likely to fail if I swap them onto the private selected-workflow capture path.

I’m patching the workflow family now. The edits are limited to replacing the repeated capture tails with the shared selected-workflow seam, switching the simpler publish handlers onto the shared artifact-existence helper, and tightening the optimizer/source-manifest path to the same capture seam.

The first patch is in. I hit a local environment detail while sanity-checking: there’s no bare `python` on PATH here, so I’m switching verification to `.venv/bin/python` and tightening one remaining decomposition capture check before running the targeted suites.

The code compiles cleanly. Most of the targeted suites are already past their first page of dots; I’m polling the remaining runs now and then I’ll update the phase notes, decisions, and recursive memory with the actual migration footprint and residual debt.

The code changes are holding under the full targeted proof set. I’m in the closeout phase now: capturing diff metrics, appending the one implementation decision that matters for later turns, and updating the phase notes plus the standing recursive memory with the concrete debt that moved and what remains deferred.

The code and memory updates are done. I’m doing one last pass over the exact diffs and file line numbers so the closeout can point at the real edits, then I’ll mark the plan complete and summarize the remaining deferred debt cleanly.

Scope considered

- Phase-local `workflow-family-migration` only: the selected-workflow helper seam, the four targeted workflow families, the optimizer-adjacent helper path, the phase notes, and the standing recursive memory files.
- I kept unrelated dirty worktree changes out of scope.

What I analyzed

- Phase artifacts, plan, and decisions plus [docs/architecture.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/docs/architecture.md) and [docs/authoring.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/docs/authoring.md).
- The shared seam in [stdlib/_selected_workflow.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/stdlib/_selected_workflow.py).
- Capture and publish paths in [candidate_workflow_to_adapted_execution_plan/workflow.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflows/candidate_workflow_to_adapted_execution_plan/workflow.py:257), [workflow_to_eval_suite/workflow.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflows/workflow_to_eval_suite/workflow.py:274), [workflow_run_history_to_failure_modes/workflow.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflows/workflow_run_history_to_failure_modes/workflow.py:301), [workflow_package_to_composable_building_blocks/workflow.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflows/workflow_package_to_composable_building_blocks/workflow.py:368), and [stdlib/optimization.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/stdlib/optimization.py:260).

What I changed

- The scoped capture handlers now take `selected_workflow_name` from the shared private seam instead of writing, reopening, and revalidating a fresh artifact just to recover that name:
  - [candidate_workflow_to_adapted_execution_plan/workflow.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflows/candidate_workflow_to_adapted_execution_plan/workflow.py:257)
  - [workflow_to_eval_suite/workflow.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflows/workflow_to_eval_suite/workflow.py:274)
  - [workflow_run_history_to_failure_modes/workflow.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflows/workflow_run_history_to_failure_modes/workflow.py:301)
  - [workflow_package_to_composable_building_blocks/workflow.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflows/workflow_package_to_composable_building_blocks/workflow.py:368)
- The simpler selected-workflow publish handlers now reuse the shared required-artifact existence validator:
  - [candidate_workflow_to_adapted_execution_plan/workflow.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflows/candidate_workflow_to_adapted_execution_plan/workflow.py:318)
  - [workflow_to_eval_suite/workflow.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflows/workflow_to_eval_suite/workflow.py:365)
- The optimizer-family helper path now uses the same selected-workflow capture/inspection seam for frame capture and source-manifest authoring in [stdlib/optimization.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/stdlib/optimization.py:260) and [stdlib/optimization.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/stdlib/optimization.py:820).
- I updated the phase record and standing memory in [implementation_notes.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/implement/phases/workflow-family-migration/implementation_notes.md), [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260427t121046-c2/decisions.txt), and the `.autoloop_recursive/` ledgers.

Key findings / decisions

- Cycle mode stayed `consolidate`; no new workflow was justified.
- I kept the convergence on the private seam instead of adding another public stdlib/root helper surface.
- Artifact filenames, top-level JSON payload shapes, route names, prompt paths, receipt names, CLI behavior, and `ctx.invoke_workflow(...)` behavior were preserved.
- Boilerplate removed in the scoped code paths: 4 selected-workflow capture re-read tails and 2 publish-time existence loops. Scoped tracked code diff was `+16` lines overall.
- Verification passed:
  - `.venv/bin/python -m py_compile ...`
  - `tests/runtime/test_candidate_workflow_to_adapted_execution_plan.py`
  - `tests/runtime/test_workflow_to_eval_suite.py`
  - `tests/runtime/test_workflow_run_history_to_failure_modes.py`
  - `tests/runtime/test_workflow_package_to_composable_building_blocks.py`
  - `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py`
  - `tests/unit/test_optimization_helpers.py`
  - `tests/runtime/test_workflow_and_eval_to_refined_workflow_package.py`
  - `tests/test_architecture_baseline_docs.py`
  - Total: `237 passed`

Open issues / next step

- `stdlib/evaluation.py` still keeps its helper-local snapshot-validation path; I left that unchanged in this phase because the active contract was workflow-family migration, not another helper-surface rewrite.
- Remaining deferred debt is narrower now: workflow-local selected-workflow publication policy, any future eval-helper capture convergence, and broader portfolio-shape cleanup.
