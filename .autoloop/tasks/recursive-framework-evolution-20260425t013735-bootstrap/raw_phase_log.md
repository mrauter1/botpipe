# Autoloop Raw Phase Log


---
run_id=run-20260425T043735Z-6422224e | entry=run_state
---
workspace=/home/rauter/autoloop_v3_bkp/autoloop_v3
pairs=plan,implement,test
request_file=/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/runs/run-20260425T043735Z-6422224e/request.md
session_mode=persistent


---
run_id=run-20260425T043735Z-6422224e | entry=session_turn | pair=plan | phase=producer | cycle=1 | attempt=1 | thread_id=019dc2ed-c8a2-77e1-a6a4-7861ed474e34
---
provider=codex
mode=start
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/plan_producer.md
session_id=019dc2ed-c8a2-77e1-a6a4-7861ed474e34


---
run_id=run-20260425T043735Z-6422224e | entry=phase_output | pair=plan | phase=producer | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dc2ed-c8a2-77e1-a6a4-7861ed474e34
---
I’m treating the supplied upgrade plan as the implementation contract and checking the current repository shape plus the existing planning artifacts before I rewrite the canonical plan files.

I’ve confirmed the main framework modules and the task artifact files are present. Next I’m reading the current planning artifacts plus the core runtime surfaces that the requested contract touches, so the rewrite matches the repository’s actual shape.

The task artifacts are effectively empty stubs, and there are no later clarification entries in the run log. I’m now mapping the current public API and runtime structure so the plan phases line up with the actual modules, compatibility surfaces, and test seams.

The current framework is narrower than the requested target: artifacts are name-only, route contracts validate only against flat artifact names, sessions are `scope`-based with active scopes, and the root shim exports just the minimal surface. I’m checking where params, session snapshots, and docs/tests currently anchor those behaviors so the phase ordering covers the real migration path.

I have enough context to rewrite the planning artifacts. The plan will mirror the user’s requested implementation order, but it will also call out the repository-specific migration risks that the request implies: additive child-result fields, session/checkpoint shape migration, docs that currently claim weaker compatibility guarantees, and runtime enforcement points in `core/engine.py` / `runtime/stores/filesystem.py`.

I’m at the edit point. I’m replacing the empty plan stubs with one canonical plan document, a machine-readable ordered phase list, and short append-only feedback/decision notes that preserve the non-obvious constraints for later turns.

The plan artifacts are written. I’m doing a final sanity pass now: parse the YAML, spot-check the rendered plan files, and confirm the append-only decision block stayed within the current turn’s header.

The file contents look correct. The environment lacks `python`, so I’m re-running the required YAML parse with `python3` to satisfy the task constraint before I close out.

Updated the planning artifacts for the requested framework upgrade:

- [plan.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/plan/plan.md) now contains the implementation-ready plan, phase-by-phase milestones, interface deltas, compatibility notes, regression controls, and risk register.
- [phase_plan.yaml](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/plan/phase_plan.yaml) now contains 9 ordered phases matching the requested implementation order.
- [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/plan/feedback.md) has a concise summary of what changed and why.
- [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/decisions.txt) has the non-obvious constraints preserved under this turn’s header only.

I aligned the plan to the supplied contract and the repo’s actual baseline, including the current flat artifact inventory, scope-based session store, dict-only params, legacy child result shape, and the docs mismatch around compatibility guarantees.

Verification: `phase_plan.yaml` parsed successfully with `python3` + `yaml.safe_load` (`yaml_ok 9`).


---
run_id=run-20260425T043735Z-6422224e | entry=session_turn | pair=plan | phase=verifier | cycle=1 | attempt=1 | thread_id=019dc2ed-c8a2-77e1-a6a4-7861ed474e34
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/plan_verifier.md
session_id=019dc2ed-c8a2-77e1-a6a4-7861ed474e34


---
run_id=run-20260425T043735Z-6422224e | entry=phase_output | pair=plan | phase=verifier | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dc2ed-c8a2-77e1-a6a4-7861ed474e34
---
I’m auditing the produced planning artifacts against the request contract, the run log, and the shared decisions ledger, then I’ll update the verifier-owned criteria and feedback files only.

I’ve completed the audit. I did not find a blocking mismatch with the request or the shared decision ledger, so I’m marking the verifier criteria complete and appending a single no-blocking-findings entry to the feedback history for continuity.

Scope considered
The verifier-reviewed planning artifacts for the recursive framework evolution task, the immutable request snapshot, the authoritative raw log, and the shared decisions ledger.

What I analyzed
I checked the narrative plan against the full requested upgrade contract, the preserved compatibility constraints, the explicit `scope=` session override requirement, the migration-risk surfaces for persisted session/checkpoint state and child workflow results, and the ordered phase decomposition for dependency coherence and regression coverage.

What I reviewed
I reviewed `plan.md`, `phase_plan.yaml`, `feedback.md`, `criteria.md`, `decisions.txt`, and the run raw log. I also re-validated that `phase_plan.yaml` is parseable YAML and that required authored lists are populated, with runtime-owned metadata unchanged.

Key findings / decisions
No blocking findings.
Updated `criteria.md` to mark all five verification gates satisfied.
Appended `PLAN-001` to `feedback.md` as a non-blocking record that the plan is acceptable and why.

Open issues / next step
No open verifier blockers. The planning artifacts are ready for implementation against the current request contract.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"COMPLETE"}
</loop-control>


---
run_id=run-20260425T043735Z-6422224e | entry=phase_scope_resolved
---
phase_mode=single
phase_ids=artifact-model,artifact-inventory,artifact-runtime-enforcement,session-continuity,typed-params,typed-routes-effects,worklists,child-io,public-surface-docs-regression
explicit=True
current_phase_index=0


---
run_id=run-20260425T043735Z-6422224e | entry=session_turn | pair=implement | phase=producer | cycle=1 | attempt=1 | thread_id=019dc2f3-6a49-79a2-94c9-e46cf47883d9
---
provider=codex
mode=start
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/implement_producer.md
session_id=019dc2f3-6a49-79a2-94c9-e46cf47883d9


---
run_id=run-20260425T043735Z-6422224e | entry=phase_output | pair=implement | phase=producer | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dc2f3-6a49-79a2-94c9-e46cf47883d9
---
I’m implementing the `artifact-model` phase only: extending artifact declarations and handles, then adding focused tests and phase notes. I’ll inspect the current artifact, compiler, and test surfaces first so the changes stay compatible with existing workflows.

The current surface is narrower than the phase contract: `Artifact` only carries `template/name/owner`, and handles are text-only. I’m mapping where artifact metadata is compiled and validated now so the model upgrade lands without disturbing route or session behavior yet.

I’ve narrowed the dependency surface: artifact names are normalized in `core.validation`, compiled in `core.compiler`, and resolved at runtime in `core.engine`. For this phase I’m keeping behavior changes local to artifact metadata plus the minimum validation needed to reject unsupported schema placements cleanly.

I found one more dependency cluster: `CompiledArtifact` fields are surfaced through capability inspection, so any new metadata needs to be additive there rather than changing existing names or meanings. I’m checking that path before editing so the artifact upgrade doesn’t break existing introspection tests.

I have enough context to edit. The change set is: extend `core.artifacts` add typed metadata and validation helpers, wire minimal schema validation into `core.validation`, and add unit tests that cover factories, helpers, and compile-time schema rejection without touching route execution yet.

I’m in the edit phase now. The runtime-facing change stays additive: compiled artifacts keep their existing fields, but I’m preserving the richer metadata there too so later enforcement work doesn’t need another structural change.

The code changes are in place. I’m running focused unit coverage against artifact helpers and workflow validation now, because that’s the smallest set that exercises this phase without pulling in later runtime-contract work.

The shell image doesn’t expose `python` or `pytest`, so I’m switching to `python3 -m pytest` and `python3 -m compileall`. This is just an environment adjustment; the test scope stays the same.

Compilation passed. `pytest` still isn’t available in the base interpreter, so I’m checking whether the repo has a local virtualenv or runner before I close out validation as limited-by-environment.

Two failures came from the new tests assuming extra keyword support on the convenience constructors. The underlying model supports the metadata; I’m tightening the tests to match the intended constructor surface instead of widening the factories beyond the phase plan.

The focused unit suite is clean. I’m doing one extra regression pass through engine contracts, since `ArtifactHandle` and compiled artifact metadata are used there even though route enforcement is still deferred to a later phase.

I generated local bytecode while validating. I’m removing only the `__pycache__` outputs from `core/` and `tests/` so the phase leaves source changes and notes, not interpreter artifacts.

**Scope considered**

Phase-local `artifact-model` only. I analyzed the current artifact declaration, compilation, validation, and runtime resolution surfaces in [core/artifacts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/artifacts.py), [core/validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/validation.py), [core/compiler.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/compiler.py), plus the artifact-focused unit and regression tests.

**What I analyzed**

- Existing `Artifact`/`ArtifactHandle` behavior, current inventory compilation, and where compiled artifact metadata is consumed.
- Regression surfaces in engine/runtime tests that still depend on the old artifact contract.
- The phase notes and plan so the change stayed additive and did not drift into route/session/worklist work.

**What I changed**

- Extended [core/artifacts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/artifacts.py) with additive artifact metadata: `kind`, `schema`, `required`, `owner_step`, `qualified_name`, factory constructors, `bind_owner_step()`, `ArtifactValidationResult`, JSON/model helpers on `ArtifactHandle`, `ArtifactHandle.validate()`, and centralized declaration/file validation helpers.
- Kept `Artifact(...)` and existing text handle methods compatible; `resolve_artifact_template(...)` now also supports step-local relative resolution when passed an `Artifact` carrying `owner_step`.
- Added compile-time artifact schema checks in [core/validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/validation.py) so invalid schema placement fails at workflow-definition time.
- Preserved richer artifact metadata in [core/compiler.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/compiler.py) for later phases.
- Added focused coverage in [tests/unit/test_primitives_and_stores.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_primitives_and_stores.py) and [tests/unit/test_validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_validation.py).
- Updated [implementation_notes.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/implement/phases/artifact-model/implementation_notes.md) and appended phase decisions in [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/decisions.txt).

**Key findings / decisions**

- This phase stays additive: metadata and validation land now, but route-based artifact enforcement and automatic step-local owner binding remain deferred.
- Raw dict artifact schemas are accepted only for JSON artifacts and are validated eagerly with `jsonschema` when available.
- Verification passed:
  - `./.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py tests/unit/test_validation.py`
  - `./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py`
  - `./.venv/bin/python -m pytest -q tests/runtime/test_compatibility_runtime.py`
  - `./.venv/bin/python -m compileall core tests/unit/test_primitives_and_stores.py tests/unit/test_validation.py`

**Open issues / next step**

- The next phase should handle artifact inventory qualification and runtime enforcement in the compiler/engine.
- No blocking issue remains for this phase.


---
run_id=run-20260425T043735Z-6422224e | entry=session_turn | pair=implement | phase=verifier | cycle=1 | attempt=1 | thread_id=019dc2f3-6a49-79a2-94c9-e46cf47883d9
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/implement_verifier.md
session_id=019dc2f3-6a49-79a2-94c9-e46cf47883d9


---
run_id=run-20260425T043735Z-6422224e | entry=phase_output | pair=implement | phase=verifier | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dc2f3-6a49-79a2-94c9-e46cf47883d9
---
I’m reviewing the `artifact-model` phase only and will audit the changed artifact/validation/test surfaces against the phase contract before updating the phase criteria and feedback files. First I’m reading the active criteria, feedback, notes, and the relevant implementation diff.

The repository baseline is unusual here: the relevant source files are currently untracked in git, so I’m reviewing the current file contents directly rather than relying on diff output. Next I’m checking the exact artifact and validation logic for regression or contract gaps.

I’ve moved from broad inspection into compatibility checking. I’m now searching for existing call patterns that the new `Artifact(...)` signature or resolution helper could have broken, because that’s the main regression risk in this phase.

I’ve found the main compatibility seam: the runtime still resolves compiled artifacts by `artifact.template`, so the new step-local relative-path branch only activates when callers pass the `Artifact` object itself. I’m validating whether that’s acceptable phase scoping or a contract gap, then I’ll record criteria and findings accordingly.

I found a second review seam beyond runtime path resolution: the compiler now stores live `artifact.schema` objects on `CompiledArtifact`. I’m checking whether that violates the plan’s deterministic compiled-workflow cache requirement in a concrete way before I finalize findings.

I’ve finished the audit pass. The implementation satisfies the phase contract as scoped, and I’m updating the reviewer-owned criteria and feedback artifacts now.

Scope considered

Phase-local `artifact-model` only. I reviewed the current contents of `core/artifacts.py`, `core/validation.py`, `core/compiler.py`, the new artifact-focused unit coverage, the implementation notes, and the shared decisions for this run.

What I analyzed

I checked the artifact declaration surface, handle helpers, compile-time schema validation, compatibility with existing `Artifact(...)` and `ArtifactHandle` text APIs, and adjacent engine/runtime usage of compiled artifacts and artifact resolution. I also verified the repo for legacy `Artifact(...)` call patterns that would have been broken by the constructor change.

What I reviewed

The implementation now exposes additive artifact metadata (`kind`, `schema`, `required`, `owner_step`, `qualified_name`), JSON/model helpers on `ArtifactHandle`, shared declaration/file validation helpers, and focused unit tests for factories, schema placement rules, and validation results. I reran:
`./.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py tests/unit/test_validation.py tests/contract/test_engine_contracts.py tests/runtime/test_compatibility_runtime.py`

Key findings / decisions

No blocking or non-blocking findings in the phase-local scope. The implementation satisfies the active phase contract as scoped, and I updated the reviewer-owned artifacts accordingly:
- `criteria.md`: all boxes checked
- `feedback.md`: recorded that no findings were identified

Open issues / next step

No issue blocks this phase. The next implementation phase can proceed to artifact inventory qualification and runtime enforcement work.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"COMPLETE"}
</loop-control>


---
run_id=run-20260425T043735Z-6422224e | entry=session_turn | pair=test | phase=producer | cycle=1 | attempt=1 | thread_id=019dc2f3-6a49-79a2-94c9-e46cf47883d9
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/test_producer.md
session_id=019dc2f3-6a49-79a2-94c9-e46cf47883d9


---
run_id=run-20260425T043735Z-6422224e | entry=phase_output | pair=test | phase=producer | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dc2f3-6a49-79a2-94c9-e46cf47883d9
---
I’m handling the `artifact-model` test phase only. I’ll inspect the current artifact tests and the phase test artifacts first, then add any missing happy-path, edge-case, or failure-path coverage before updating the phase strategy and feedback notes.

The current tests cover the core happy path, but two direct regression surfaces are still missing for this phase: optional artifact validation semantics and artifact-schema dependency failure when `jsonschema` is unavailable. I’m adding those now, along with one handle-API edge case around `read_model()` without a schema.

The added tests are deterministic and local-only, with no timing or network surface. I’m running the focused unit/contract/runtime subset again to confirm the new expectations align with the current implementation and don’t destabilize adjacent behavior.

The test runs are clean. I’m documenting the behavior-to-test map and the exact additions in the phase-owned test artifacts now, including the environment-sensitive `jsonschema` case and the preserved text-handle invariants.

I’ve finished the source and phase-artifact edits. I’m doing a quick cleanup of generated `__pycache__` directories so this turn leaves only test-source and phase-note changes.

Scope considered

Phase-local `artifact-model` only. I focused on the new artifact declaration and handle behavior in `core/artifacts.py`, the matching validation surface in `tests/unit/test_validation.py`, the handle/helper coverage in `tests/unit/test_primitives_and_stores.py`, and the phase-owned test artifacts.

What I analyzed

I reviewed the implemented artifact metadata and helper APIs, the existing test coverage added during implementation, the shared decisions for this run, and the active test-phase artifacts. I looked specifically for uncovered happy paths, edge cases, and environment-sensitive failure paths in the new artifact validation behavior.

What I changed

I added focused tests in [tests/unit/test_primitives_and_stores.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_primitives_and_stores.py) for:
- `ArtifactHandle.read_model()` failing without a schema
- optional missing artifact validation succeeding

I added a focused validation test in [tests/unit/test_validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_validation.py) for:
- raw artifact-schema rejection when `jsonschema` is unavailable

I updated the phase strategy and feedback artifacts:
- [test_strategy.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/test/phases/artifact-model/test_strategy.md)
- [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/test/phases/artifact-model/feedback.md)

Key findings / decisions

The added tests close two meaningful gaps in this phase:
- optional-artifact validation should not fail when the artifact is absent
- artifact-schema declarations need an explicit failure-path test for missing `jsonschema`, because that behavior is environment-sensitive

Validation passed:
- `./.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py tests/unit/test_validation.py`
- `./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py tests/runtime/test_compatibility_runtime.py`

Open issues / next step

No blocking test issue remains for this phase. Later phases should add runtime coverage once route-based artifact enforcement and step-local artifact inventory resolution are implemented.


---
run_id=run-20260425T043735Z-6422224e | entry=session_turn | pair=test | phase=verifier | cycle=1 | attempt=1 | thread_id=019dc2f3-6a49-79a2-94c9-e46cf47883d9
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/test_verifier.md
session_id=019dc2f3-6a49-79a2-94c9-e46cf47883d9


---
run_id=run-20260425T043735Z-6422224e | entry=phase_output | pair=test | phase=verifier | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dc2f3-6a49-79a2-94c9-e46cf47883d9
---
I’m auditing the `artifact-model` test phase only. I’ll verify the new and preserved artifact coverage against the phase contract, then update the test-phase criteria and feedback artifacts accordingly.

The strategy and coverage map line up with the phase contract. I’m running the focused unit plus adjacent regression subset once myself so the audit reflects observed test behavior, not just the recorded notes.

The audit run is clean. I’m updating the auditor-owned criteria and feedback artifacts now to reflect that the phase-local test coverage is sufficient and stable.

Scope considered

Phase-local `artifact-model` test scope only. I audited the updated unit tests in `tests/unit/test_primitives_and_stores.py` and `tests/unit/test_validation.py`, the phase test strategy and feedback artifacts, and the shared decisions that constrain what the tests should and should not encode.

What I analyzed

I checked whether the tests cover the new artifact metadata and helper APIs, preserve regression coverage for the existing text-handle behavior, include relevant failure paths and environment-sensitive cases, and avoid normalizing behavior that was explicitly deferred to later phases.

What I reviewed

I verified that the tests now cover:
- artifact factories, binding metadata, and step-local relative resolution helper behavior
- preserved `ArtifactHandle` text-method invariants
- JSON/model helper happy paths
- `read_model()` failure without a schema
- missing required artifact failure
- missing optional artifact success
- schema-placement rejection on non-JSON artifacts
- unsupported schema-type rejection
- raw artifact-schema rejection when `jsonschema` is unavailable

I reran:
- `./.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py tests/unit/test_validation.py`
- `./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py tests/runtime/test_compatibility_runtime.py`

Key findings / decisions

No blocking or non-blocking audit findings in the phase-local test scope. The coverage is aligned with the active phase contract, the shared decisions, and the implementation’s stated phase boundaries. I updated the auditor-owned artifacts so `criteria.md` is fully checked and `feedback.md` records the clean audit result.

Open issues / next step

No test-audit blocker remains for this phase. Later phases should extend coverage when runtime artifact enforcement and step-local artifact inventory semantics are implemented.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"COMPLETE"}
</loop-control>


---
run_id=run-20260425T043735Z-6422224e | entry=session_turn | pair=implement | phase=producer | cycle=1 | attempt=1 | thread_id=019dc2fe-51ac-7c93-8e99-98fd506ed890
---
provider=codex
mode=start
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/implement_producer.md
session_id=019dc2fe-51ac-7c93-8e99-98fd506ed890


---
run_id=run-20260425T043735Z-6422224e | entry=phase_output | pair=implement | phase=producer | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dc2fe-51ac-7c93-8e99-98fd506ed890
---
I’m implementing the `artifact-inventory` phase only: compiler-side artifact inventory, step-local binding, and deterministic reference resolution. I’ll inspect the current artifact/compiler/validation code and the phase notes first, then patch the smallest set of files that satisfy the phase acceptance criteria.

I’ve confirmed the phase notes are effectively empty, so the codebase and the main plan are the real source of detail here. Next I’m tracing how artifacts are currently collected, resolved, and exposed so I can change the compiler path without leaking into the runtime-enforcement phase.

I’ve found the current shape: artifact metadata already grew in `core.artifacts`, but compiler and validation still treat the namespace as flat. I’m checking the runtime resolution path now so the compile-time changes won’t accidentally break existing handle lookup or path rendering.

I have enough context to patch this phase cleanly. The main gap is centralized artifact reference resolution: today the compiler validates route contracts against a flat `inventory.keys()`, which can’t distinguish `plan.summary` from another step’s `summary`, and the compiled artifact map exposes only unqualified names.

I’m at the edit point now. The patch will be confined to `core/validation.py`, `core/compiler.py`, `core/engine.py`, and focused tests so this phase lands as a coherent compile-time upgrade without pulling in session or runtime-contract work early.

The inventory/compiler patch is in. I’m reviewing the resulting compiled shapes now, especially alias handling, because the safest version keeps existing unqualified artifact access working while adding canonical qualified references for the new step-local cases.

I hit one environment detail while checking syntax: this shell has `python3`, not `python`. I’m cleaning a couple of compiler nits now and then I’ll add the focused tests that prove the new qualified-name and ambiguity behavior.

I caught one real logic bug before running tests: step-local route-contract resolution was still checking global names too early. I’m fixing that ordering now so `required_artifacts=("summary",)` really picks `draft.summary` before a workflow-level `summary`.

The code parses cleanly. The test runner binary isn’t on `PATH` here, so I’m switching to `python3 -m pytest` and will use that for the focused validation pass.

The base interpreter doesn’t have `pytest` installed, so I can’t execute the test suite directly from this shell. I’m checking whether the repo has a project-local virtualenv or runner entrypoint so I can still validate without guessing.

There’s a local `.venv`, so I can validate against the project environment after all. I’m rerunning the focused unit tests there and will fix anything that falls out before I touch the phase notes.

One failing test exposed a genuine inventory edge case: the same `Artifact` object can appear first as a future `requires` reference and only later as a produced artifact. I’m making the registry tolerate that late producer binding, then I’ll rerun the focused suite.

The inventory-focused unit suite is green. Because I touched `core/engine.py` for alias resolution, I’m doing one small contract pass as a regression check instead of widening straight to the full suite.

The compile/runtime regression spot check passed too, so the phase change is stable in the paths I touched. I’m updating the phase notes now with the exact files, symbols, checklist mapping, and the one non-obvious compatibility decision this phase introduced.

Scope considered

Compiler-side artifact inventory only for the active `artifact-inventory` phase: [core/validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/validation.py), [core/compiler.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/compiler.py), [core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/engine.py), [tests/unit/test_validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_validation.py), plus the required phase notes under [.autoloop/.../implementation_notes.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/implement/phases/artifact-inventory/implementation_notes.md) and [.autoloop/.../decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/decisions.txt). I kept runtime artifact enforcement, sessions, params, routes/effects, worklists, and child IO out of scope.

What I analyzed

I traced the current artifact path through `Artifact`, `Step.__getattr__`, `collect_artifact_inventory(...)`, route-contract normalization, compiled workflow metadata, and engine artifact-handle resolution. I also checked adjacent regression surfaces where compiled artifact names are consumed, especially provider artifact access and deterministic compile caching.

What I changed

I upgraded inventory compilation so workflow-level artifacts and inline step-local outputs share one canonical inventory with `qualified_name` and `owner_step` metadata. Step-local inline artifacts now bind to names like `draft.summary`, while workflow-level artifacts keep unqualified aliases when they remain globally unique.

I added centralized artifact reference resolution in `core.validation`, including ambiguity rejection and step-local-first route-contract resolution. `RouteContract.required_artifacts` now compile to deterministic canonical names, and `CompiledWorkflow` now carries a full `artifacts_by_qualified_name` map alongside the compatibility-oriented `artifacts` alias map.

I adjusted `core.engine` artifact-handle resolution so canonical qualified handles exist without breaking existing unqualified access where it is still safe. I added focused tests for step-local binding, qualified references in compiled metadata, ambiguous unqualified references, and step-local route-contract resolution.

Key findings / decisions

The non-obvious compatibility choice is that `compiled.artifacts` remains an unqualified alias map only for globally unambiguous artifacts, while the full inventory lives in `compiled.artifacts_by_qualified_name`. That lets this phase land canonical step-local compilation without breaking existing artifact access patterns.

Validation passed with:
`./.venv/bin/python -m py_compile core/validation.py core/compiler.py core/engine.py tests/unit/test_validation.py`
`./.venv/bin/python -m pytest -q tests/unit/test_validation.py`
`./.venv/bin/python -m pytest -q tests/unit/test_primitives_and_stores.py`
`./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py -k "compiled_workflow_is_deterministic or pair_step_contract_logs_raw_output_and_updates_state or llm_step_contract_logs_outcome_raw_output_and_uses_global_route"`

Open issues / next step

Runtime artifact enforcement is still deferred, so this phase prepares canonical references and full inventory metadata but does not yet enforce `required=True` or route-selected artifact existence after execution. The next phase should consume `artifacts_by_qualified_name` directly for enforcement and checkpoint diagnostics.


---
run_id=run-20260425T043735Z-6422224e | entry=session_turn | pair=implement | phase=verifier | cycle=1 | attempt=1 | thread_id=019dc2fe-51ac-7c93-8e99-98fd506ed890
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/implement_verifier.md
session_id=019dc2fe-51ac-7c93-8e99-98fd506ed890


---
run_id=run-20260425T043735Z-6422224e | entry=phase_output | pair=implement | phase=verifier | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dc2fe-51ac-7c93-8e99-98fd506ed890
---
I’m reviewing the `artifact-inventory` phase only. I’ll inspect the phase artifacts, the implementation diffs in `core/validation.py`, `core/compiler.py`, and `core/engine.py`, and the targeted test coverage before I update the criteria and feedback files.

I have the phase artifacts and the stated compatibility decision. Next I’m reading the actual source changes with a regression lens, especially around whether this compiler-only phase accidentally changed runtime artifact behavior through `core/engine.py`.

I’ve narrowed the main review question: whether adding canonical artifact aliases in the engine changed runtime surface area beyond this phase. I’m checking for callers that iterate over `ResolvedArtifacts` or assume `compiled.artifacts` is the complete inventory, because that’s the kind of regression this phase could accidentally hide.

I found one likely regression surface already: several downstream consumers still iterate `compiled.artifacts`, which is now only the unambiguous alias map, not the full inventory. I’m verifying that with a small runtime/capability repro so I can decide whether it’s a blocking issue or just an implementation note.

I have one blocking finding. It’s not in the compiler logic itself; it’s the downstream consequence of splitting `compiled.artifacts` into an alias map without migrating existing consumers that still treat it as the authoritative inventory. I’m writing that up now and marking the criteria accordingly.

Scope considered

Phase-local review of `artifact-inventory`, centered on [core/validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/validation.py), [core/compiler.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/compiler.py), [core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/engine.py), and [tests/unit/test_validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_validation.py). I also checked request-relevant downstream consumers in [runtime/runner.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/runner.py) and [core/workflow_capabilities.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/workflow_capabilities.py) because the implementation changed the meaning of `compiled.artifacts`.

What I analyzed

I read the accepted phase contract, the implementation notes, the shared decisions ledger, and the compiler/runtime paths that consume artifact inventory. I also verified the reported test commands and reproduced the new artifact-map behavior with a small local repro using duplicate step-local artifact names.

What I reviewed

I updated [criteria.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/implement/phases/artifact-inventory/criteria.md) and appended the review finding to [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/implement/phases/artifact-inventory/feedback.md). The review result is not clean: there is one blocking regression tied to downstream consumers still treating `compiled.artifacts` as the full inventory.

Key findings / decisions

`IMP-001` is blocking. `CompiledWorkflow.artifacts` is now only the unambiguous alias map, but child-result and capability code still consume it as the authoritative artifact set. In a workflow with two step-local `summary` outputs, `compiled.artifacts` becomes empty while `compiled.artifacts_by_qualified_name` contains both canonical artifacts; `_build_child_workflow_result(...)` then drops both real files and returns no output artifacts. That is a material behavior gap against the intended unified inventory model.

Open issues / next step

The implementation needs a follow-up change that centralizes “full inventory” access and migrates downstream consumers that require the authoritative artifact set to use the canonical qualified map. After that, the phase criteria can be re-evaluated.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"INCOMPLETE"}
</loop-control>


---
run_id=run-20260425T043735Z-6422224e | entry=session_turn | pair=implement | phase=producer | cycle=2 | attempt=1 | thread_id=019dc2fe-51ac-7c93-8e99-98fd506ed890
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/implement_producer.md
session_id=019dc2fe-51ac-7c93-8e99-98fd506ed890


---
run_id=run-20260425T043735Z-6422224e | entry=phase_output | pair=implement | phase=producer | process=codex-agent | cycle=2 | attempt=1 | thread_id=019dc2fe-51ac-7c93-8e99-98fd506ed890
---
I’m addressing the reviewer’s blocking finding only: downstream consumers still treat `compiled.artifacts` as the full inventory. I’ll trace those consumers, patch them to use the authoritative canonical inventory where required, and rerun the focused validation plus the reviewer’s repro surface.

I’ve confirmed the reviewer’s repro path in the code: `runtime/runner.py` and `core/workflow_capabilities.py` still consume the alias map. I’m patching this with one centralized compiled-workflow helper so the canonical inventory choice is explicit instead of repeated ad hoc.

I’m making the follow-up fix in four places: one small helper on `CompiledWorkflow`, two downstream consumers switched to the authoritative inventory, and two regression tests that cover the exact reviewer scenario.

The fix is in. I’m validating the two downstream paths directly now: capability inspection and child-workflow output artifact collection, then I’ll rerun the phase-focused suites to make sure nothing else shifted.

The targeted tests are green, including the two new downstream regression checks. I’m running a quick direct repro of the reviewer’s duplicate-`summary` scenario as one last sanity check before I update the phase notes.

Scope considered

Reviewer-scoped fix for `artifact-inventory`: [core/compiler.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/compiler.py), [core/workflow_capabilities.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/workflow_capabilities.py), [runtime/runner.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/runner.py), and regression coverage in [tests/runtime/test_compatibility_runtime.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_compatibility_runtime.py). I left reviewer-owned artifacts untouched except for updating [implementation_notes.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/implement/phases/artifact-inventory/implementation_notes.md), and I appended the non-obvious follow-up decision to [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/decisions.txt).

What I analyzed

I traced every remaining `compiled.artifacts` consumer after the inventory split and confirmed the reviewer’s regression: child-workflow result collection and capability inspection were still reading the alias-only map instead of the canonical inventory. I also verified that engine-side alias resolution did not need further changes.

What I changed

I added `CompiledWorkflow.artifact_items(authoritative=False|True)` as the centralized inventory selector. Then I switched [runtime/runner.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/runner.py) child-result collection and [core/workflow_capabilities.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/workflow_capabilities.py) capability assembly to `artifact_items(authoritative=True)` so ambiguous step-local outputs are preserved under canonical qualified names.

I added two runtime regression tests in [tests/runtime/test_compatibility_runtime.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_compatibility_runtime.py): one for capability inspection with duplicate step-local `summary` outputs, and one for child workflow result artifact collection with the same shape.

Key findings / decisions

The compatibility contract remains the same: `compiled.artifacts` is the unambiguous alias map, while the authoritative full inventory is the canonical qualified set. The follow-up fix makes that distinction explicit and reusable so downstream consumers stop making inconsistent assumptions.

Validation passed:
`./.venv/bin/python -m py_compile core/compiler.py core/workflow_capabilities.py runtime/runner.py tests/runtime/test_compatibility_runtime.py`
`./.venv/bin/python -m pytest -q tests/runtime/test_compatibility_runtime.py -k "canonical_artifacts_when_unqualified_aliases_are_ambiguous or child_workflow_result_preserves_canonical_outputs_when_unqualified_aliases_are_ambiguous or inspect_workflow_capabilities_adds_importing_parameter_and_step_contract_detail"`
`./.venv/bin/python -m pytest -q tests/unit/test_validation.py tests/unit/test_primitives_and_stores.py`
`./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py -k "compiled_workflow_is_deterministic or pair_step_contract_logs_raw_output_and_updates_state or llm_step_contract_logs_outcome_raw_output_and_uses_global_route"`

Open issues / next step

The reviewer’s blocking finding should now clear on re-review. The next step is the verifier turn; I did not edit reviewer-owned [criteria.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/implement/phases/artifact-inventory/criteria.md).


---
run_id=run-20260425T043735Z-6422224e | entry=session_turn | pair=implement | phase=verifier | cycle=2 | attempt=1 | thread_id=019dc2fe-51ac-7c93-8e99-98fd506ed890
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/implement_verifier.md
session_id=019dc2fe-51ac-7c93-8e99-98fd506ed890


---
run_id=run-20260425T043735Z-6422224e | entry=phase_output | pair=implement | phase=verifier | process=codex-agent | cycle=2 | attempt=1 | thread_id=019dc2fe-51ac-7c93-8e99-98fd506ed890
---
I’m re-reviewing the reviewer-reported regression only, plus the immediate downstream surfaces it touched. I’ll verify the new authoritative inventory helper, confirm the child-result and capability consumers moved to it, then update the phase artifacts accordingly.

The fix is applied in the right places, and the new tests cover the reviewer’s exact duplicate-`summary` scenario. I’m running the focused validation once from the verifier side, then I’ll clear the stale finding and mark the criteria.

The focused suites are green, including the exact downstream regression checks. I’m updating the phase artifacts now: clearing the stale reviewer state in the criteria and recording that `IMP-001` no longer reproduces on re-review.

Scope considered

Phase-local re-review of the `artifact-inventory` work, focused on the reviewer-reported regression and the direct downstream consumers it affected: `CompiledWorkflow.artifacts` vs canonical inventory access, child workflow result artifact collection, and capability inspection.

What I analyzed

I checked the updated implementation in `core/compiler.py`, `runtime/runner.py`, and `core/workflow_capabilities.py`, confirmed the new `CompiledWorkflow.artifact_items(authoritative=True)` helper is the centralized authoritative inventory path, and verified the duplicate step-local artifact scenario is now covered by runtime tests.

What I reviewed

I reran the focused validation:
- `./.venv/bin/python -m pytest -q tests/runtime/test_compatibility_runtime.py -k "canonical_artifacts_when_unqualified_aliases_are_ambiguous or child_workflow_result_preserves_canonical_outputs_when_unqualified_aliases_are_ambiguous or inspect_workflow_capabilities_adds_importing_parameter_and_step_contract_detail"`
- `./.venv/bin/python -m pytest -q tests/unit/test_validation.py tests/unit/test_primitives_and_stores.py`
- `./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py -k "compiled_workflow_is_deterministic or pair_step_contract_logs_raw_output_and_updates_state or llm_step_contract_logs_outcome_raw_output_and_uses_global_route"`

I updated [criteria.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/implement/phases/artifact-inventory/criteria.md) to checked, and I appended the re-review result to [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/implement/phases/artifact-inventory/feedback.md).

Key findings / decisions

`IMP-001` no longer reproduces. The implementation now cleanly separates the compatibility alias map from the authoritative canonical inventory and routes the affected downstream consumers to the authoritative path. I did not identify any remaining blocking or non-blocking findings in this phase scope.

Open issues / next step

No open issues in this phase review. The phase can be considered complete.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"COMPLETE"}
</loop-control>


---
run_id=run-20260425T043735Z-6422224e | entry=session_turn | pair=test | phase=producer | cycle=1 | attempt=1 | thread_id=019dc2fe-51ac-7c93-8e99-98fd506ed890
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/test_producer.md
session_id=019dc2fe-51ac-7c93-8e99-98fd506ed890


---
run_id=run-20260425T043735Z-6422224e | entry=phase_output | pair=test | phase=producer | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dc2fe-51ac-7c93-8e99-98fd506ed890
---
I’m handling the `artifact-inventory` test phase only. I’ll inspect the current coverage that landed in the implementation, compare it to the phase acceptance criteria and the reviewer-discovered regression, then add only the tests and test-phase artifacts needed to make the coverage map explicit and durable.

The implementation already added most of the behavior coverage, but there’s one small gap worth locking down in the test phase: the new `CompiledWorkflow.artifact_items(...)` helper itself. I’m adding a focused unit test for the authoritative-vs-alias split so future changes can’t regress that contract silently.

Scope considered

Phase-local test work for `artifact-inventory` only. I reviewed the landed implementation and existing coverage in `tests/unit/test_validation.py`, `tests/unit/test_primitives_and_stores.py`, `tests/runtime/test_compatibility_runtime.py`, and the focused contract checks already used in this phase.

What I analyzed

I mapped the phase acceptance criteria and the shared decisions to the concrete tests already present. The main remaining gap was the newly introduced `CompiledWorkflow.artifact_items(authoritative=True)` boundary itself: the implementation had downstream regression tests, but not a direct unit test locking the alias-vs-authoritative split.

What I changed

I added `tests/unit/test_validation.py::test_compiled_workflow_artifact_items_distinguish_alias_and_authoritative_inventories` to pin the canonical-vs-alias inventory contract for duplicate step-local artifact names.

I updated [.autoloop/.../test_strategy.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/test/phases/artifact-inventory/test_strategy.md) with an explicit behavior-to-test coverage map, preserved invariants, edge cases, reliability notes, and known gaps. I also appended a concise test summary to [.autoloop/.../feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/test/phases/artifact-inventory/feedback.md), and recorded the non-obvious test boundary in [decisions.txt](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/decisions.txt).

Key findings / decisions

The authoritative regression boundary for this phase is now explicit in tests: `compiled.artifact_items(authoritative=True)` is the full canonical inventory, while the default alias view may legitimately be empty when all unqualified names are ambiguous. The test strategy now ties AC-03/AC-04 coverage to specific unit and runtime tests instead of leaving that mapping implicit.

Open issues / next step

No blocking gaps remain in this phase’s test scope. The next step is the auditor/verifier pass for the test phase.


---
run_id=run-20260425T043735Z-6422224e | entry=session_turn | pair=test | phase=verifier | cycle=1 | attempt=1 | thread_id=019dc2fe-51ac-7c93-8e99-98fd506ed890
---
provider=codex
mode=resume
template=/home/rauter/.local/share/pipx/venvs/autoloop/lib/python3.12/site-packages/autoloop/templates/test_verifier.md
session_id=019dc2fe-51ac-7c93-8e99-98fd506ed890


---
run_id=run-20260425T043735Z-6422224e | entry=phase_output | pair=test | phase=verifier | process=codex-agent | cycle=1 | attempt=1 | thread_id=019dc2fe-51ac-7c93-8e99-98fd506ed890
---
I’m auditing the `artifact-inventory` test phase only. I’ll verify the new coverage against the accepted phase scope and the shared decisions, rerun the focused tests once, then update the test-phase criteria and feedback based on whether any material coverage gaps remain.

The coverage matches the phase scope cleanly: unit tests cover the compile-time binding and ambiguity rules, and runtime tests pin the downstream canonical inventory consumers. I’m marking the audit criteria complete and recording that no additional findings remain.

Scope considered

Phase-local audit of the `artifact-inventory` test work only: the updated strategy and feedback artifacts, the new unit/runtime coverage in `tests/unit/test_validation.py` and `tests/runtime/test_compatibility_runtime.py`, and the preserved regression checks referenced from the strategy.

What I analyzed

I compared the test coverage against the active phase scope, acceptance criteria AC-03 and AC-04, and the shared decisions about canonical-vs-alias artifact inventory behavior. I also checked that the tests cover both the compile-time binding/ambiguity rules and the reviewer-discovered downstream regression surface around authoritative inventory consumers.

What I reviewed

I reran the focused audit validation:
- `./.venv/bin/python -m pytest -q tests/runtime/test_compatibility_runtime.py -k "canonical_artifacts_when_unqualified_aliases_are_ambiguous or child_workflow_result_preserves_canonical_outputs_when_unqualified_aliases_are_ambiguous or inspect_workflow_capabilities_adds_importing_parameter_and_step_contract_detail"`
- `./.venv/bin/python -m pytest -q tests/unit/test_validation.py tests/unit/test_primitives_and_stores.py`
- `./.venv/bin/python -m pytest -q tests/contract/test_engine_contracts.py -k "compiled_workflow_is_deterministic or pair_step_contract_logs_raw_output_and_updates_state or llm_step_contract_logs_outcome_raw_output_and_uses_global_route"`

I updated [criteria.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/test/phases/artifact-inventory/criteria.md) and appended the audit outcome to [feedback.md](/home/rauter/autoloop_v3_bkp/autoloop_v3/.autoloop/tasks/recursive-framework-evolution-20260425t013735-bootstrap/test/phases/artifact-inventory/feedback.md).

Key findings / decisions

No blocking or non-blocking audit findings remain. The tests now cover:
- step-local artifact binding and qualified-name compilation,
- ambiguous reference rejection,
- deterministic route-contract resolution,
- the alias-vs-authoritative inventory split itself,
- downstream runtime consumers that must preserve canonical qualified artifacts.

Open issues / next step

No open issues in this test-phase audit. The phase can be considered complete.

<loop-control>
{"schema":"docloop.loop_control/v1","kind":"promise","promise":"COMPLETE"}
</loop-control>
