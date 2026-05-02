# Original intent considered

- Migrate the exported workflow packages under `workflows/*/workflow.py` to the enforced public runtime contract:
  hooks must be `hook(ctx)` only, hook state replacement must happen by mutating `ctx.state` instead of returning replacement state, and exported `python_step` handlers must be `python_step(ctx)`.
- Update workflow-specific tests that still assumed removed helper forms.
- Add repo-level regression coverage so discovered exported workflow packages compile cleanly and raw exported sources no longer contain removed public-contract forms.

# Clarifications / superseding decisions

- No later clarification changed the requested behavior. The raw log and `decisions.txt` only narrowed implementation details.
- `decisions.txt` records that compiled handler helpers are an allowed direct-test surface, but they are not sufficient as the only regression gate because the compiler still normalizes raw two-argument `python_step` handlers. The raw exported-source audit therefore had to stay separate.
- `decisions.txt` also records three implementation-adjacent constraints that were consistent with intent:
  removing `handoff=` metadata from routes that target downstream `python_step` nodes because the compiler rejects that contract,
  aligning autoloop-v1 parity assertions with canonical session files and normalized `pending_input.question`,
  and widening overlay runnable-root detection so workflow-builder publication tests validate this packaged repo layout.

# Implemented behavior

- Repo-level source audit now rejects the removed exported authoring forms in discovered workflow packages via `tests/unit/test_simple_surface.py::test_discovered_exported_workflow_sources_avoid_removed_public_contract_forms`.
  Independent audit rerun result: `0` violations.
- Repo-level compile sweep now requires discovered exported workflow packages to compile with zero tolerated failures via `tests/runtime/test_workflow_integration_parity.py::test_all_repo_workflow_packages_resolve_and_compile_under_canonical_simple_surface`.
  Independent audit rerun result: `COMPILED_COUNT=16`, `FAILURE_COUNT=0`.
- Fast acceptance gate passed during the audit:
  `./.venv/bin/pytest tests/unit/test_simple_surface.py tests/runtime/test_workflow_integration_parity.py`
  Result: `62 passed`.
- The phase artifacts record the broader narrowed acceptance rerun from implementation:
  `421 passed, 602 warnings` for the affected workflow runtime suites plus the compile/raw-contract gates.
- Spot checks confirm the migrated source shape now matches the contract:
  `workflows/release_candidate_to_go_no_go/workflow.py` uses ctx-only after-verifier hooks and `bootstrap(ctx)`,
  `tests/runtime/workflow_contract_helpers.py` invokes compiled handlers and returns normalized control values,
  `tests/runtime/test_workflow_run_traces_to_optimization_candidates.py` uses those helpers instead of legacy `WorkflowClass.on_*` entry points.
- Direct class-style legacy helper calls were not found in active runtime or unit tests by audit search:
  `rg -n "\\b[A-Z][A-Za-z0-9_]*\\.on_[A-Za-z0-9_]+\\(" tests/runtime tests/unit`
  Result: no matches.

# Unresolved gaps

- No material unresolved gaps found.

# Differences justified by later clarification or analysis

- `autoloop_optimizer/candidate_surfaces.py` was changed even though it is outside `workflows/*/workflow.py`.
  This is justified by the recorded implementation analysis because workflow-builder publication coverage depends on recognizing this repository's packaged `autoloop/{core,runtime}` layout; without that fix, the requested package-regression coverage would not stay valid.
- `workflows/autoloop_v1/parity.py` and parity assertions in `tests/runtime/test_workflow_integration_parity.py` were updated beyond simple hook/step signature migration.
  This is justified by the repo-level compatibility gate requirement and the recorded decision that canonical session files are `sessions/plan.json` and `sessions/phases/<phase>.json`, with clarification resume logic reading `pending_input.question` and falling back to legacy `pending_question` only for backward-compatible checkpoint coverage.
- Route-contract tables in several package `contracts.py` files were tightened to remove `handoff=` metadata for downstream `python_step` targets.
  This is justified by compiler-enforced validation and does not remove requested workflow behavior; it aligns exported declarations with the already enforced engine contract.

# Recommended next run

- No follow-up implementation run is required for this request.
