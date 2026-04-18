# Workflow Authoring

## Canonical Imports

```python
from workflow import (
    Artifact,
    Context,
    FAIL,
    GLOBAL,
    LLMStep,
    PAUSE,
    PairStep,
    Prompt,
    SUCCESS,
    Session,
    SystemStep,
    Workflow,
)
from workflow.primitives import Checkpoint, Event, Outcome, ResolvedArtifacts
```

Do not use removed compatibility-era imports, aliases, or observer-era extension plumbing.

## Required Shape

- Define a nested `State` model.
- Declare steps on the workflow class.
- Set `entry` explicitly.
- Define `transitions` explicitly.
- Open sessions explicitly at their birth moment.

## Handler Contracts

- `on_start(self, ctx) -> None`
- `on_outcome(state, outcome) -> Event | None`
- `on_{pair_or_llm}(state, outcome, artifacts) -> State`
- `on_{system}(state, ctx) -> tuple[State, Event]`

`PairStep` and `LLMStep` handlers are optional. `SystemStep` handlers are required.

## Sessions

Declare slots once and open them explicitly:

```python
from pydantic import BaseModel

from workflow import Context, LLMStep, SUCCESS, Session, Workflow


class ExampleWorkflow(Workflow):
    class State(BaseModel):
        summary: str = ""

    main = Session()
    ask = LLMStep(name="ask", producer="prompts/ask.md", session=main)
    entry = ask
    transitions = {ask: {"done": SUCCESS}}

    def on_start(self, ctx: Context) -> None:
        ctx.open_session(self.main)
```

If a step references a session that was never opened, execution fails clearly.

## Artifacts And Prompts

- Use `Artifact("{task_folder}/...")` or `Artifact("{run_folder}/...")`.
- Dot-path placeholders such as `{state.phase.id}` remain workflow-owned semantics.
- Declare `requires` and `produces` explicitly.
- Required-artifact existence is asserted before step execution.
- Prompt paths may be strings or `Prompt(...)`, but resolution stays deterministic and explicit.

Prefer explicit artifact templates in workflow code over workflow-specific helper wrappers.

## Optional Extensions

Orthogonal behavior opts in through `Workflow.extensions`:

```python
class ExampleWorkflow(Workflow):
    extensions = (
        Tracing(config=TracingConfig(enabled=True)),
        SessionPaths(strategy=MySessionPathStrategy()),
        GitTracking(
            policy=MyGitPolicy(),
            config=GitTrackingConfig(enabled=True),
        ),
    )
```

Extensions may perform side effects, but they may not change workflow meaning. If a rule changes topology, semantic state, or domain behavior, keep it in workflow code.

## Tiny Stdlib

`autoloop_v3.stdlib` is optional pure sugar only:

- `control.py` for route helpers such as `global_routes(...)`
- `prompts.py` for `PromptBundle` and `PromptPair`
- `steps.py` for `pair_step(...)`
- `state/cursor.py` for `SequenceCursor`

It does not provide workflow base classes, behavioral mixins, or a decorator DSL.

## Minimal Strict Workflow

```python
from pydantic import BaseModel

from workflow import Context, LLMStep, SUCCESS, Session, Workflow
from workflow.primitives import Outcome


class ExampleWorkflow(Workflow):
    class State(BaseModel):
        summary: str = ""

    main = Session()
    ask = LLMStep(name="ask", producer="prompts/ask.md", session=main)
    entry = ask
    transitions = {ask: {"done": SUCCESS}}

    def on_start(self, ctx: Context) -> None:
        ctx.open_session(self.main)

    @staticmethod
    def on_ask(state: State, outcome: Outcome, artifacts):
        return state.model_copy(update={"summary": outcome.raw_output})
```

Generic workflows run through `python -m autoloop_v3.runtime.cli`. `autoloop_v1.py` remains special only through workflow-owned parity composition in `autoloop_v3.workflows.run_autoloop_v1(...)`.
