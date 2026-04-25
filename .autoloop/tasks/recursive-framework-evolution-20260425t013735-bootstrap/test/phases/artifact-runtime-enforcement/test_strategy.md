# Test Strategy

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: test
- Phase ID: artifact-runtime-enforcement
- Phase Directory Key: artifact-runtime-enforcement
- Phase Title: Artifact Runtime Enforcement
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Provider-owned required outputs:
  - missing required produced artifact raises `ProviderExecutionError`
  - checkpoint stores additive artifact failure context
  - handler-written required JSON artifact validates after handler processing
- Optional schema-bearing outputs:
  - absent optional schema artifact is allowed
  - present optional schema artifact must validate or fail deterministically
- Route-specific required-artifact selection:
  - route contract overrides default `Artifact.required=True` selection
  - system-step route contracts enforce selected-route outputs with `WorkflowExecutionError`
- Route resolution ordering invariants:
  - invalid middleware-selected route fails as `RoutingError` before artifact validation
  - invalid system-handler route fails as `RoutingError` before artifact validation
- Preserved invariant:
  - `expected_output_schema` remains payload-only; artifact-file enforcement is covered separately through produced-artifact tests rather than payload-schema expectations

## Edge Cases / Failure Paths

- Missing required artifact files
- Invalid schema-bearing JSON outputs
- Selected-route override that intentionally leaves a default-required artifact absent
- Invalid selected route tags on both provider/middleware and system-handler execution paths

## Stabilization

- Tests use `InMemorySessionStore`, `InMemoryCheckpointStore`, and `ScriptedLLMProvider` only.
- Artifact paths resolve under temporary task/workflow folders; no timing, network, or nondeterministic ordering dependencies.

## Known Gaps

- No worklist/session-continuity coverage in this phase; those behaviors are explicitly out of scope here.
