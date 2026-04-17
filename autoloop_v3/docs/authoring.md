# Workflow Authoring Guide

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

- Subclass `Workflow`.
- Define a nested `State` model derived from `pydantic.BaseModel`.
- Declare `entry`.
- Declare `transitions`.

## Minimal Strict Workflow

```python
from pydantic import BaseModel

from workflow import Artifact, LLMStep, Workflow, SUCCESS
from workflow.primitives import Outcome, ResolvedArtifacts


class ExampleWorkflow(Workflow):
    class State(BaseModel):
        summary: str = ""

    notes = Artifact(".autoloop/tasks/{task_id}/notes.md")

    summarize = LLMStep(
        prompt="prompts/summarize.md",
        produces=(notes,),
    )

    entry = summarize
    transitions = {
        "summarize": {"done": SUCCESS},
    }

    def on_summarize(self, state: State, outcome: Outcome, artifacts: ResolvedArtifacts) -> State:
        return state.model_copy(update={"summary": outcome.raw_output})
```

## State Rules

- Treat state as immutable.
- Pair and LLM handlers return a new state.
- System handlers return `(state, event)`.
- Strict v3 workflows should use `model_copy(update=...)`.

## Sessions

- Declare session slots with `Session()`.
- Open a concrete binding via `ctx.open_session(ref, scope=None)`.
- Retrieve the active binding via `ctx.get_session(ref)`.
- Use scopes for phase or thread isolation.

## Artifacts

- Declare workflow-level artifacts as `Artifact(template)`.
- Declare step-local outputs in `produces`.
- Declare inputs in `requires`.
- Templates may reference `task_id`, `run_id`, `task_folder`, `run_folder`, and `state`.
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

- Step-local transition first.
- Then `GLOBAL`.
- Else runtime error.

## Validation Expectations

Definition-time validation checks:

- state shape
- `entry`
- `transitions`
- mandatory system handlers
- orphan handlers
- topology destinations
- artifact uniqueness
- artifact dependency order and acyclicity
- session references

## Running A Workflow

The generic filesystem runner is exposed as:

```bash
python -m autoloop_v3.runtime.cli path/to/workflow.py \
  --task-id example-task \
  --provider-factory package.module:factory \
  --root /repo \
  --request-text "Ship it"
```

The provider factory receives `config` and parsed `args`, then returns an object that implements the `LLMProvider` protocol.

## Compatibility Guidance

- Existing workflows may keep using `Verdict`, `on_verdict`, legacy handler arities, and `SessionLifecycle`.
- New workflows should prefer `Outcome`, `on_outcome`, and strict handler signatures.
- The generic v3 runner handles fresh runs and checkpoint-based resume. For legacy event-only resume or non-default pair or phase loop controls, continue using the legacy `autoloop` harness.
