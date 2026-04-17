# Workflow Authoring

## Imports

```python
from workflow import (
    Workflow,
    Context,
    Session,
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
from workflow.primitives import Event, Outcome, Checkpoint, ResolvedArtifacts
```

Do not use `Verdict`, `on_verdict`, or `SessionLifecycle`. Those names were removed.

## Required Shape

- Define a nested `State` subclass of `pydantic.BaseModel`.
- Declare steps on the workflow class.
- Set `entry` explicitly.
- Define `transitions`.

## Handler Contracts

- `on_start(self, ctx) -> None`
- `on_outcome(state, outcome) -> Event | None`
- `on_{pair_or_llm}(state, outcome, artifacts) -> State`
- `on_{system}(state, ctx) -> tuple[State, Event]`

`PairStep` and `LLMStep` handlers are optional. `SystemStep` handlers are required.

## Sessions

Declare slots once and open them explicitly:

```python
class Example(Workflow):
    class State(BaseModel):
        note: str = ""

    main = Session()
    ask = LLMStep(name="ask", producer="ask.md", session=main)
    entry = ask
    transitions = {ask: {"done": SUCCESS}}

    def on_start(self, ctx: Context) -> None:
        ctx.open_session(self.main)
```

If a slot is not opened before a step uses it, the engine raises a runtime error.

## Artifacts And Prompts

- Use `Artifact("{task_folder}/...")` or `Artifact("{run_folder}/...")`.
- Dot-path access such as `{state.phase.id}` is supported.
- Declare produced artifacts in `produces` and required artifacts in `requires`.
- Prefer explicit artifact templates in the workflow source instead of workflow-specific helper wrappers.
- Prompt paths must be explicit. Plain strings are the canonical shorthand for `Prompt(...)`.

## Minimal Strict Workflow

```python
from pydantic import BaseModel

from workflow import LLMStep, SUCCESS, Workflow
from workflow.primitives import Outcome


class ExampleWorkflow(Workflow):
    class State(BaseModel):
        summary: str = ""

    ask = LLMStep(name="ask", producer="prompts/ask.md")
    entry = ask
    transitions = {ask: {"done": SUCCESS}}

    @staticmethod
    def on_ask(state: State, outcome: Outcome, artifacts):
        return state.model_copy(update={"summary": outcome.raw_output})
```

## Running

Generic workflows run through `python -m autoloop_v3.runtime.cli`.

`autoloop_v1.py` is special only in its workflow-owned parity modules. Run it through `autoloop_v3.workflows.run_autoloop_v1(...)` when you need legacy-equivalent raw logs, decisions, clarification persistence, and legacy session filenames.
