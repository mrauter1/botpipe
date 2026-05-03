# Test Strategy

- Task ID: standalone-remaining-delta-implementation-spec-g-e919a184
- Pair: test
- Phase ID: execution-normalization
- Phase Directory Key: execution-normalization
- Phase Title: Execution Normalization
- Scope: phase-local producer artifact

## Behavior To Coverage Map

- Hook/direct-control normalization across early lifecycle phases:
  covered by existing contract tests for `before`, `before_producer`, `after_producer`, `before_verifier`, `on_taken`, and invalid python-step hook returns; extended here with `before_verifier` `RequestInput` short-circuit coverage and invalid `before_verifier` `Goto` failure coverage in [`tests/contract/test_engine_contracts.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/contract/test_engine_contracts.py:4224).
- Provider-contract extraction for visible reads/requires/routes:
  existing contract tests cover llm and pair route/read/write payloads; extended here with missing undeclared workspace reads remaining visible as unavailable context in [`tests/contract/test_engine_contracts.py`](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/contract/test_engine_contracts.py:717).
- Preserved invariants checked:
  short-circuiting before verifier must skip the verifier turn, preserve producer-attempt attribution, keep `candidate_route` / `last_route` unset for direct controls, and checkpoint pending-input metadata with the originating hook phase.
- Edge cases covered:
  undeclared workspace read path that does not exist; producer-ran/verifier-skipped direct input request from `before_verifier`.
- Failure paths covered:
  existing suite already covers invalid route tags, invalid terminal payloads, invalid hook returns, and per-route required-write failures; extended here with invalid `before_verifier` runtime-control validation after the producer turn.
- Flake control:
  tests use `ScriptedLLMProvider`, temporary workspaces, and explicit state assertions only; no timing, network, or nondeterministic ordering dependencies.
- Known gaps:
  targeted runtime execution could not be run in this shell because `pytest` is unavailable (`pytest: command not found`, `/usr/bin/python3: No module named pytest`); syntax was checked with `python3 -m py_compile`.
