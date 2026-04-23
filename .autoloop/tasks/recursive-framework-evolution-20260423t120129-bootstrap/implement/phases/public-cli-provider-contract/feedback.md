# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260423t120129-bootstrap
- Pair: implement
- Phase ID: public-cli-provider-contract
- Phase Directory Key: public-cli-provider-contract
- Phase Title: Remove Public Provider Factory Surfaces
- Scope: phase-local authoritative verifier artifact

- IMP-001 | blocking | [runtime/config.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/config.py:190), [tests/runtime/test_provider_backends.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_provider_backends.py:126)
  The new `_merge_provider_config(...)` logic delays applying generic `provider.model` / `provider.model_effort` values until after all config layers are merged. That breaks normal layer precedence: a lower-precedence generic override can now overwrite a higher-precedence provider-specific override once the final provider name is known. Concrete failure: a user-level config with `provider.model: global-model` and a repo-local config with `provider.name: claude` plus `provider.claude.model: repo-specific` resolves to `claude.model == global-model`, silently ignoring the higher-precedence local typed override. I reproduced that exact scenario in this review with `_merge_provider_config(...)`, and it materially risks selecting the wrong provider model/effort at runtime.
  Minimal fix: keep the merge centralized in `_merge_provider_config(...)`, but apply each layer's generic model/effort to the then-effective provider as that layer is processed instead of replaying one final generic override after all layers. Add a regression test covering at least global generic + local provider-specific overrides so later layers still win.

- IMP-001 follow-up | non-blocking | [runtime/config.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/runtime/config.py:190), [tests/runtime/test_provider_backends.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_provider_backends.py:167)
  Cycle 2 re-review: fixed. `_merge_provider_config(...)` now resolves the final provider name first, replays config layers in order, and applies generic model/effort overrides against that selected provider without breaking layer precedence. The new regression tests cover both the original failure mode (global generic plus later local provider-specific override) and the retained final-provider behavior under CLI `--provider`. No remaining phase-scope findings were identified.
