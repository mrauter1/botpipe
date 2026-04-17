# Workflow Authoring Surface

## Primary Imports

```python
from workflow import (
    Workflow,
    Context,
    Session,
    SessionLifecycle,
    Artifact,
    Prompt,
    PairStep,
    LLMStep,
    SystemStep,
    SUCCESS,
    PAUSE,
    FAIL,
    GLOBAL,
)
from workflow.primitives import Event, Outcome, Verdict, Checkpoint, ResolvedArtifacts
```

## Required Workflow Shape

- A workflow subclasses `Workflow`.
- It defines a nested `State` class derived from `pydantic.BaseModel`.
- It declares `entry`.
- It declares `transitions`.

## State Rules

- Treat state as immutable.
- Pair and LLM handlers return a new state.
- System handlers return `(state, event)`.
- Strict v3 code should use `model_copy(update=...)`.

## Sessions

- Declare session slots with `Session()`.
- Open a concrete session via `ctx.open_session(ref, scope=None)`.
- Retrieve a current binding with `ctx.get_session(ref)`.
- Use scoped sessions for phase or thread isolation.

## Artifacts

- Declare workflow-level artifacts as `Artifact(template)`.
- Declare step-local outputs in `produces`.
- Declare inputs in `requires`.
- Artifact templates may reference `task_id`, `run_id`, `task_folder`, `run_folder`, and `state`.
- Dot notation such as `{state.phase.id}` is supported.
- Missing keys resolve to an empty string.

## Step Contracts

- `PairStep`
  - resolves artifacts
  - producer returns raw text
  - verifier returns `Outcome`
  - middleware may intercept
  - handler returns new state
  - routing uses `outcome.tag`
- `LLMStep`
  - resolves artifacts
  - provider returns `Outcome`
  - middleware may intercept
  - optional handler returns new state
  - routing uses `outcome.tag`
- `SystemStep`
  - handler is mandatory
  - handler returns `(state, event)`
  - middleware does not run
  - routing uses `event.tag`

## Lifecycle Hooks

- `on_start(self, ctx) -> None`
- `on_outcome(state, outcome) -> Event | None`
- Compatibility alias: `on_verdict(state, verdict) -> Event | None`

## Routing Rules

- Step-local transition first
- Then `GLOBAL`
- Else runtime error

## Validation Expectations

- Definition-time validation checks state shape, entry, transitions, system handlers, orphan handlers, topology destinations, artifact uniqueness, artifact graph order and acyclicity, and session references.

## Compatibility Guidance

- Existing workflows may continue to use `Verdict`, `on_verdict`, legacy handler arities, and `SessionLifecycle`.
- New workflows should prefer `Outcome`, `on_outcome`, and strict handler signatures so compatibility remains an adapter layer instead of the default authoring style.
