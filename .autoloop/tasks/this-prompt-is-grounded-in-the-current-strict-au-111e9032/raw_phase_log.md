# Autoloop Raw Phase Log


---
run_id=run-20260418T021238Z-9ac22268 | entry=run_state
---
workspace=/home/rauter/autoloop_v3
pairs=plan,implement,test
request_file=/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/runs/run-20260418T021238Z-9ac22268/request.md
session_mode=persistent


---
run_id=run-20260418T021238Z-9ac22268 | entry=session_turn | pair=plan | phase=producer | cycle=1 | attempt=1 | thread_id=019d9e5c-8fa4-78f2-a514-448f2903f805
---
provider=codex
mode=start
template=/home/rauter/AutoSac/.venv/lib/python3.12/site-packages/autoloop/templates/plan_producer.md
session_id=019d9e5c-8fa4-78f2-a514-448f2903f805


---
run_id=run-20260418T021238Z-9ac22268 | entry=phase_output | pair=plan | phase=producer | process=codex-agent | cycle=1 | attempt=1 | thread_id=019d9e5c-8fa4-78f2-a514-448f2903f805
---
I’m grounding the plan in the immutable request, any later clarifications in the raw log, and the current `autoloop_v3` layout before touching the planning artifacts. Then I’ll rewrite the plan, phase decomposition, feedback entry, and this turn’s decisions block to match the requested full-book-architecture refactor.

The request is fully explicit and the raw log has no later clarification entries, so I’m treating the initial snapshot as the contract. Next I’m mapping the current package, workflow files, docs, and tests to identify the real migration surface and the main regression hotspots before writing the phased plan.

I’ve confirmed the current repo already leans strict in places, but the architecture still centers an observer seam, legacy-compat docs/tests, and a smaller package surface than the requested final shape. I’m reading the kernel/runtime internals now so the plan can target the actual rewrite points rather than restating the prompt.

The remaining gap is the repo’s current migration baseline: the strict re-export shim exists, but `stdlib/` and `extensions/` do not, and the engine/runtime tests still encode the observer-based architecture. I’m pulling in the rest of the package surfaces now so the phase plan can call out exact replacements, not just high-level goals.

The current docs and tests still freeze the observer seam as the core extension point, which conflicts with the requested workflow-declared extension model. I also need the supplemental design rationale the request referenced, so I’m pulling in `additional_context.md` before finalizing the plan direction.

I have enough architecture context now. I’m checking one prior planning artifact style from this repo so the new `plan.md` and `phase_plan.yaml` stay consistent with existing autoloop planning conventions while still reflecting the full requested refactor.

I’ve finished the analysis pass. The edits I’m making now will turn the empty planning artifacts into a six-phase implementation contract, with explicit public-interface targets, workflow/runtime boundary rules, regression controls, and the non-obvious compatibility constraints later turns need to preserve.

The plan artifacts are written. I’m doing one validation pass now: checking the final markdown/yaml/decision files for coherence, dependency ordering, and any accidental drift from the request before I close out.

The artifacts look coherent on readback. I’m doing one last machine check on `phase_plan.yaml` now so the handoff is clean and later turns don’t hit a trivial schema or dependency-order problem.

`phase_plan.yaml` had one YAML-unsafe scalar in an acceptance criterion. I’m patching the quoting now and re-running the parse check so the machine-readable phase plan is actually valid.

Updated [plan.md](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/plan.md), [phase_plan.yaml](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/phase_plan.yaml), [feedback.md](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/feedback.md), and [decisions.txt](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/decisions.txt).

The plan is now an implementation-ready six-phase contract: doc/ADR freeze, strict kernel refactor, generic runtime refactor, tiny `stdlib` plus optional `extensions`, workflow/parity migration, and layered parity proof. It explicitly locks in the non-obvious constraints that matter most for later turns: replace `workflow.observers` with `Workflow.extensions`, narrow the root authoring surface, keep the runtime phase-agnostic, preserve legacy `thread_id` session payload compatibility, and keep exact Autoloop-v1 session/log/git policy workflow-owned.

I also validated that `phase_plan.yaml` parses and that its phase dependencies are ordered correctly.


---
run_id=run-20260418T021238Z-9ac22268 | entry=session_turn | pair=plan | phase=verifier | cycle=1 | attempt=1 | thread_id=019d9e5c-8fa4-78f2-a514-448f2903f805
---
provider=codex
mode=resume
template=/home/rauter/AutoSac/.venv/lib/python3.12/site-packages/autoloop/templates/plan_verifier.md
session_id=019d9e5c-8fa4-78f2-a514-448f2903f805


---
run_id=run-20260418T021238Z-9ac22268 | entry=phase_output | pair=plan | phase=verifier | process=codex-agent | cycle=1 | attempt=1 | thread_id=019d9e5c-8fa4-78f2-a514-448f2903f805
---
I’m verifying the planning artifacts against the immutable request, the raw log, the current decisions ledger, and the generated plan files. I’ll check intent coverage first, then behavioral safety, then whether the phase decomposition and criteria accurately reflect any findings before I update the verifier-owned artifacts.

I found two material gaps. The plan captures the overall architecture direction, but it does not yet lock down one current public config-compatibility boundary or the concrete workflow-facing extension APIs the prompt explicitly calls for, so I’m marking the plan incomplete and recording precise correction directions now.

Scope considered
- The immutable request snapshot, the raw log for clarification history, the shared decisions ledger, and the generated planning artifacts under `.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/`.

What I analyzed
- Intent coverage against the requested Book Architecture refactor, including the strict kernel, generic runtime, tiny `stdlib`, tiny `extensions`, workflow-owned parity, Autoloop-v1 parity, and Ralph correctness requirements.
- Behavioral safety around public-surface changes, config/CLI compatibility, persisted session data, and parity-sensitive workflow behavior.
- Phase quality in `phase_plan.yaml`, including dependency ordering, scope boundaries, acceptance criteria, and rollback coverage.

What I reviewed
- [plan.md](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/plan.md)
- [phase_plan.yaml](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/phase_plan.yaml)
- [feedback.md](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/feedback.md)
- [criteria.md](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/criteria.md)
- [decisions.txt](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/decisions.txt)

Key findings / decisions
- Marked the plan `INCOMPLETE`.
- Updated [criteria.md](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/criteria.md): only `Technical Debt` is currently satisfied.
- Appended two blocking findings to [feedback.md](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/feedback.md):
- `PLAN-001`: the plan does not explicitly preserve or intentionally remove the current `superloop.*` config-file discovery behavior, which is a public config/CLI compatibility surface.
- `PLAN-002`: the plan does not pin the requested workflow-facing optional extension APIs, especially the concrete git/session-path/tracing declaration surface and its binding through `Workflow.extensions`.

Open issues / next step
- The producer should revise the plan to make the legacy config discovery decision explicit and to add concrete workflow-facing extension interface definitions plus matching phase acceptance criteria.
- After those corrections, the plan should be re-verified for full intent fidelity, compatibility coverage, and implementation readiness.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"INCOMPLETE"}
</loop-control>


---
run_id=run-20260418T021238Z-9ac22268 | entry=session_turn | pair=plan | phase=producer | cycle=2 | attempt=1 | thread_id=019d9e5c-8fa4-78f2-a514-448f2903f805
---
provider=codex
mode=resume
template=/home/rauter/AutoSac/.venv/lib/python3.12/site-packages/autoloop/templates/plan_producer.md
session_id=019d9e5c-8fa4-78f2-a514-448f2903f805


---
run_id=run-20260418T021238Z-9ac22268 | entry=phase_output | pair=plan | phase=producer | process=codex-agent | cycle=2 | attempt=1 | thread_id=019d9e5c-8fa4-78f2-a514-448f2903f805
---
I’m addressing the verifier’s blocking gaps directly in the planning artifacts: first the current config-compatibility boundary around `superloop.*`, then the concrete workflow-facing optional extension APIs the request expects. After that I’ll revalidate the updated plan, phase criteria, feedback continuity, and this turn’s decisions block.

I’ve pinned the missing decisions. The edits I’m making now will explicitly preserve current `superloop.*` config discovery as a generic runtime compatibility boundary and define the workflow-facing extension APIs the implementation must target, so later turns can’t drift into runner-only or renamed surfaces.

I’ve updated the narrative plan; now I’m tightening the machine-readable phase contract so the same compatibility and interface decisions are explicit in phase scope, acceptance criteria, and rollback rather than living only in prose.

The blocking gaps are patched. I’m doing a final validation pass now to make sure the prose plan, phase contract, feedback continuity, and this turn’s decisions all line up and that `phase_plan.yaml` still parses cleanly after the added interface/config coverage.

One acceptance criterion introduced a YAML parser hazard because of an unquoted colon. I’m fixing that now and re-running the parse check so the phase plan stays machine-valid.

Updated [plan.md](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/plan.md), [phase_plan.yaml](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/phase_plan.yaml), [feedback.md](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/feedback.md), and the current turn block in [decisions.txt](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/decisions.txt).

The plan now closes both verifier findings. It explicitly preserves legacy `superloop.*` config discovery as a generic runtime compatibility contract, and it pins the workflow-facing optional extension APIs the implementation must target: `GitTracking(...)`, `SessionPaths(...)`, and `Tracing(...)`, all opted into through `Workflow.extensions`. I also mirrored those decisions into the machine-readable phase contract with scope, acceptance, regression, and rollback coverage.

Validation: `phase_plan.yaml` parses successfully and its dependency ordering still checks out.


---
run_id=run-20260418T021238Z-9ac22268 | entry=session_turn | pair=plan | phase=verifier | cycle=2 | attempt=1 | thread_id=019d9e5c-8fa4-78f2-a514-448f2903f805
---
provider=codex
mode=resume
template=/home/rauter/AutoSac/.venv/lib/python3.12/site-packages/autoloop/templates/plan_verifier.md
session_id=019d9e5c-8fa4-78f2-a514-448f2903f805


---
run_id=run-20260418T021238Z-9ac22268 | entry=phase_output | pair=plan | phase=verifier | process=codex-agent | cycle=2 | attempt=1 | thread_id=019d9e5c-8fa4-78f2-a514-448f2903f805
---
The revised plan now covers the two previously blocking gaps in both prose and phase criteria. I’m marking the criteria accordingly and appending a re-review closure note to the feedback history so the next turn has a clean verification record.

Scope considered
- The immutable request snapshot, the raw log clarification history, the shared decisions ledger, and the current planning artifacts under `.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/`.

What I analyzed
- Intent coverage for the strict kernel, generic runtime, tiny `stdlib`, tiny `extensions`, workflow-owned parity, Autoloop-v1 parity, and Ralph correctness requirements.
- Behavioral safety around public-surface narrowing, runtime config/CLI compatibility, persisted session compatibility, workflow-facing extension opt-in, and parity-sensitive workflow behavior.
- Phase quality in `phase_plan.yaml`, including dependency ordering, acceptance criteria, and rollback/regression coverage.

What I reviewed
- [plan.md](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/plan.md)
- [phase_plan.yaml](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/phase_plan.yaml)
- [feedback.md](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/feedback.md)
- [criteria.md](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/criteria.md)
- [decisions.txt](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/decisions.txt)

Key findings / decisions
- Marked the plan `COMPLETE`.
- Updated [criteria.md](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/criteria.md) so all verification criteria are now checked.
- Appended a closure note to [feedback.md](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/plan/feedback.md) confirming the previous blockers are addressed.
- Re-checked `phase_plan.yaml`; it remains parseable and dependency ordering is valid.

Open issues / next step
- No blocking findings remain in the planning artifacts.
- The plan is ready for the next loop phase to use as the implementation contract.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"COMPLETE"}
</loop-control>


---
run_id=run-20260418T021238Z-9ac22268 | entry=phase_scope_resolved
---
phase_mode=single
phase_ids=architecture-contract-freeze,strict-kernel-extension-seam,generic-runtime-filesystem-refactor,stdlib-and-optional-extensions,workflow-migrations-and-parity-harness,layered-tests-and-parity-proof
explicit=True
current_phase_index=0


---
run_id=run-20260418T021238Z-9ac22268 | entry=session_turn | pair=implement | phase=producer | cycle=1 | attempt=1 | thread_id=019d9e6b-2316-7420-9590-985904101c64
---
provider=codex
mode=start
template=/home/rauter/AutoSac/.venv/lib/python3.12/site-packages/autoloop/templates/implement_producer.md
session_id=019d9e6b-2316-7420-9590-985904101c64


---
run_id=run-20260418T021238Z-9ac22268 | entry=phase_output | pair=implement | phase=producer | process=codex-agent | cycle=1 | attempt=1 | thread_id=019d9e6b-2316-7420-9590-985904101c64
---
I’m treating this as a doc-contract freeze pass for the `architecture-contract-freeze` phase. I’ll read the authoritative phase artifacts, current architecture/docs/tests, and then rewrite only the documentation/test baseline needed to lock the requested strict-kernel/generic-runtime/optional-extensions shape.

I’ve confirmed the phase is narrowly about freezing the architecture contract: docs, ADRs, migration guidance, and doc-focused tests. Next I’m reading the current baseline to identify exactly where observer-era and compat-era language is still being enforced so I can rewrite that contract cleanly instead of patching around it.

The current baseline still hard-codes the old observer seam in the architecture record, architecture docs, parity matrix, and the doc baseline test. I’m now reading the existing docs and ADR summaries in bulk so I can replace that contract in one pass rather than leave partial contradictions behind.

I have enough context to change files. I’m replacing the observer-era and broad-compat wording with the final contract: `workflow` as strict kernel, `runtime` as generic runtime, `stdlib` as tiny authoring sugar, `extensions` as explicit opt-in modules, and a narrow retained-compatibility note only for runtime/data compatibility.

The core docs and baseline test now point at the new contract. I’m rewriting the ADR summaries next so the archive stops pointing back to observers and instead summarizes the final surface: strict kernel, workflow-declared extensions, tiny stdlib, narrow compatibility, and workflow-owned parity.

I’ve finished the rewrite pass. I’m checking the resulting corpus for leftover observer-era wording and then running the doc baseline test slice so I can fix any contract gaps directly instead of leaving mismatched assertions behind.

The failures are all contract-shape issues, not implementation bugs: a few docs still name removed surfaces directly, the compatibility note is broader than intended, and the config markers weren’t present in the shared corpus. I’m tightening those docs and leaving the baseline test strict where it should be strict.

The doc baseline now passes. I’m recording the phase-local notes and shared decisions next so the later implementation phases inherit the intended contract instead of drifting back toward the old observer/compat shape.

I found one generated `.pyc` change from running pytest. I’m restoring that tracked cache artifact to its pre-run state so the phase diff stays limited to the docs, ADR summaries, notes, and the doc baseline test.

Scope considered

- Phase-local doc freeze only: [ARCHITECTURE_DECISIONS.md](/home/rauter/autoloop_v3/autoloop_v3/ARCHITECTURE_DECISIONS.md), [README.md](/home/rauter/autoloop_v3/autoloop_v3/README.md), [MIGRATION.md](/home/rauter/autoloop_v3/autoloop_v3/MIGRATION.md), [docs/architecture.md](/home/rauter/autoloop_v3/autoloop_v3/docs/architecture.md), [docs/authoring.md](/home/rauter/autoloop_v3/autoloop_v3/docs/authoring.md), [docs/compatibility.md](/home/rauter/autoloop_v3/autoloop_v3/docs/compatibility.md), [docs/parity-matrix.md](/home/rauter/autoloop_v3/autoloop_v3/docs/parity-matrix.md), [docs/risk-register.md](/home/rauter/autoloop_v3/autoloop_v3/docs/risk-register.md), all ADR summaries under [docs/adr](/home/rauter/autoloop_v3/autoloop_v3/docs/adr), and [test_architecture_baseline_docs.py](/home/rauter/autoloop_v3/autoloop_v3/tests/test_architecture_baseline_docs.py).
- I also updated the phase artifact notes in [implementation_notes.md](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/implement/phases/architecture-contract-freeze/implementation_notes.md) and appended phase decisions in [decisions.txt](/home/rauter/autoloop_v3/.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/decisions.txt).
- Unrelated untracked files at repo root were left untouched.

What I analyzed

- The active phase contract, plan, criteria, feedback, and shared decisions.
- The current architecture/docs corpus for observer-era and compatibility-era assertions.
- The doc baseline test to see exactly what the repo was freezing before this phase.

What I changed

- Rewrote the architecture record with 18 candidate-matrix decisions covering package layout, public surface, compat removal, session model, artifacts, prompts, validation/compilation, checkpoints, protocols, runtime boundary, config, stdlib, extension seam, git, session paths, observability, and testing.
- Rewrote the main docs to target the final contract: strict `workflow`, generic `runtime`, tiny `stdlib`, tiny optional `extensions`, and workflow-owned parity.
- Rewrote all ADR summaries so they point at the final contract instead of the observer-era model.
- Kept [docs/compatibility.md](/home/rauter/autoloop_v3/autoloop_v3/docs/compatibility.md) as a narrow operational-compatibility note only.
- Rebased the doc baseline test to enforce `Workflow.extensions`, `GitTracking` / `SessionPaths` / `Tracing`, tiny `stdlib`, narrow retained compatibility, and the absence of the old observer-era surface from active docs.

Key findings / decisions

- The main drift was architectural documentation, not behavior: the repo was still freezing `workflow.observers` as the extension seam.
- `docs/compatibility.md` should remain, but only for retained runtime/data compatibility such as `thread_id`, legacy-readable status consumers, and `superloop.*` config discovery.
- Removed/legacy names are now confined to migration/compatibility material instead of being treated as active surface docs.
- Validation performed: `pytest autoloop_v3/tests/test_architecture_baseline_docs.py` and it passes.

Open issues / next step

- No phase-local blocker remains.
- The next implementation phases now need to make the code match the frozen docs: replace the observer seam with `Workflow.extensions`, add `autoloop_v3.stdlib` and `autoloop_v3.extensions`, and then migrate `autoloop_v1.py`, `Ralph_loop.py`, and the parity harness onto that final surface.


---
run_id=run-20260418T021238Z-9ac22268 | entry=session_turn | pair=implement | phase=verifier | cycle=1 | attempt=1 | thread_id=019d9e6b-2316-7420-9590-985904101c64
---
provider=codex
mode=resume
template=/home/rauter/AutoSac/.venv/lib/python3.12/site-packages/autoloop/templates/implement_verifier.md
session_id=019d9e6b-2316-7420-9590-985904101c64


---
run_id=run-20260418T021238Z-9ac22268 | entry=phase_output | pair=implement | phase=verifier | process=codex-agent | cycle=1 | attempt=1 | thread_id=019d9e6b-2316-7420-9590-985904101c64
---
I’m reviewing the phase-local doc freeze diff against the phase contract and shared decisions. I’ll inspect the changed docs/tests, check the authoritative notes/criteria/feedback state, and rerun the doc baseline so I can decide whether this phase is complete or needs follow-up.

The repository diff plumbing is not giving a useful patch view here, so I’m reviewing the changed files directly against the phase contract and shared decisions. I’m focusing on the architecture record, the public-facing docs, the compatibility note, and the baseline test because those are the acceptance-critical artifacts for this phase.

The changed files are aligned with the phase objective so far. I’m doing one last mechanical pass for forbidden observer-era surface in the rewritten docs/ADRs and rerunning the doc baseline to decide whether there are any findings worth blocking on.

I don’t have a blocking issue to raise from this pass. I’m marking the phase criteria complete and appending a no-findings review note so the artifact trail reflects that the doc freeze passed review and validation.

Scope considered

- Phase-local review of the rewritten doc contract for `architecture-contract-freeze`.
- Reviewed the changed architecture/docs/test surface plus the authoritative phase artifacts: `criteria.md`, `feedback.md`, `implementation_notes.md`, and shared `decisions.txt`.
- Stayed out of non-`.autoloop/tasks/...` writes as required.

What I analyzed

- The phase objective, acceptance criteria, implementation notes, and shared decisions.
- The rewritten [autoloop_v3/ARCHITECTURE_DECISIONS.md](/home/rauter/autoloop_v3/autoloop_v3/ARCHITECTURE_DECISIONS.md), [README.md](/home/rauter/autoloop_v3/autoloop_v3/README.md), [MIGRATION.md](/home/rauter/autoloop_v3/autoloop_v3/MIGRATION.md), [docs/architecture.md](/home/rauter/autoloop_v3/autoloop_v3/docs/architecture.md), [docs/authoring.md](/home/rauter/autoloop_v3/autoloop_v3/docs/authoring.md), [docs/compatibility.md](/home/rauter/autoloop_v3/autoloop_v3/docs/compatibility.md), [docs/parity-matrix.md](/home/rauter/autoloop_v3/autoloop_v3/docs/parity-matrix.md), [docs/risk-register.md](/home/rauter/autoloop_v3/autoloop_v3/docs/risk-register.md), ADR summaries, and [test_architecture_baseline_docs.py](/home/rauter/autoloop_v3/autoloop_v3/tests/test_architecture_baseline_docs.py).
- Mechanical checks for forbidden observer-era/compat-era surface in active docs, plus the doc baseline test run.

What I reviewed

- Intent fidelity against AC-1 through AC-3.
- Conformance to the shared decisions: `Workflow.extensions` as the target seam, narrow retained compatibility, workflow-owned parity, and preserved `superloop.*`/`thread_id` compatibility notes.
- Validation evidence: `pytest autoloop_v3/tests/test_architecture_baseline_docs.py` passed during review.

Key findings / decisions

- No blocking findings.
- The doc set now consistently describes `workflow` as the strict kernel, `runtime` as workflow-agnostic, `stdlib` as tiny authoring sugar, and `extensions` as tiny optional modules.
- `docs/compatibility.md` remains narrow and operational, which matches the recorded decision and phase scope.
- I updated the phase artifacts accordingly: all criteria boxes checked and `feedback.md` records a no-findings review note.

Open issues / next step

- No phase-local blocker remains.
- Next phases need to implement the code changes that these rewritten docs/tests now freeze.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"COMPLETE"}
</loop-control>
