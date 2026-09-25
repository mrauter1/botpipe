# Ad-hoc Executor

`ad_hoc_executor` is the safe escape hatch used by `adaptive_goal` when the
orchestrator needs a bounded local action that is not represented by a registered
capability.

It is deliberately:

- pre-authored rather than generated at runtime;
- workspace-write sandboxed;
- network-disabled;
- forbidden from external side effects;
- producer/verifier gated;
- required to emit the standard `capability_result.json` protocol.

If a recurring ad-hoc pattern becomes valuable, promote it through a separate
candidate-workflow generation/evaluation process rather than trusting generated
Botpipe Python inside an active mission.
