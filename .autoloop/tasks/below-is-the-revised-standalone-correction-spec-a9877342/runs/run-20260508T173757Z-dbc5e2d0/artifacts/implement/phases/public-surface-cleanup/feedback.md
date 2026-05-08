# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-revised-standalone-correction-spec-a9877342
- Pair: implement
- Phase ID: public-surface-cleanup
- Phase Directory Key: public-surface-cleanup
- Phase Title: Public Surface Cleanup
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` — [autoloop/sdk.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/autoloop/sdk.py) `Autoloop.step`, `_build_synthetic_step_workflow`, `_coerce_sdk_params`: AC-3 requires the public `client.step(..., params=...)` contract to remain supported, but the implementation still builds synthetic step workflows without a `Params` model. Non-empty step params therefore flow into `coerce_workflow_parameter_mapping(parameters_cls=None, ...)` and raise `WorkflowParameterError("workflow does not declare Params and does not accept workflow parameters")`. The new tests only add removed-keyword rejection and do not cover successful `client.step(..., params=...)` usage, so this regression remains undetected. Minimal fix: centralize step-param support in `_build_synthetic_step_workflow` by synthesizing or propagating a `Params` model for the synthetic workflow the same way input is synthesized, then add a direct regression test proving `client.step(..., input=..., params=...)` succeeds and exposes params through the runtime context.
