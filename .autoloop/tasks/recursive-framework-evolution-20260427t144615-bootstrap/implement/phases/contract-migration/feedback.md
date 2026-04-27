# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260427t144615-bootstrap
- Pair: implement
- Phase ID: contract-migration
- Phase Directory Key: contract-migration
- Phase Title: Compiler And Contract Migration
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` [core/validation.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/validation.py:412), [core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/engine.py:844): `normalize_step_route_metadata()` resolves `Route.required_outputs` against the full artifact inventory, but it never verifies that those artifacts are actually produced by the source step. That violates the requested contract for route-level output obligations and lets a workflow declare a route like `Route.to(next_step, required_outputs=("request",))` or an upstream artifact name; validation passes, the provider is told that the route requires that artifact, and runtime enforcement is satisfied by a pre-existing input instead of a new output from the current step. Minimal fix: centralize a produced-by-current-step check in the route-required-output normalization/validation path so both explicit `Route.required_outputs` and legacy `route_contracts.required_artifacts` are restricted to artifacts in `step.produces`.
- `IMP-002` `non-blocking` [core/engine.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/engine.py:1036), [core/providers/rendering.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/core/providers/rendering.py:170): the new “Required inputs” section still renders the `Required` column from `artifact.required` on the artifact declaration, not from the fact that the artifact is in `step.requires`. A workflow can now present a hard runtime precondition as `Required = no` when the artifact itself is optional as an output surface, which undercuts the clearer reads-vs-requires contract this phase is introducing. Minimal fix: either add a separate precondition flag to `ProviderArtifactRef` for input rendering or render `yes` unconditionally in the required-inputs table.
