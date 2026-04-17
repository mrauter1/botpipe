# Migration To The Strict Surface

This package no longer tolerates legacy workflow drift. Migrate workflows onto the canonical API instead of relying on shims.

## Removed

- `workflow.compat`
- `Verdict`
- `on_verdict`
- `SessionLifecycle`
- loader-injected authoring symbols
- handler arity adaptation
- inferred entry behavior
- engine auto-opening of missing sessions

## Canonical Replacements

- Use `Outcome` instead of `Verdict`.
- Use `on_outcome(state, outcome) -> Event | None` instead of `on_verdict(...)`.
- Declare `Session()` slots and open them explicitly with `ctx.open_session(...)`.
- Pair and LLM handlers must accept `(state, outcome, artifacts)`.
- System handlers must accept `(state, ctx)` and return `(state, event)`.
- Define `entry` explicitly on every workflow.
- Import the symbols you use. The loader no longer injects names into workflow modules.

## Example

Before:

```python
from workflow import Workflow, LLMStep, SessionLifecycle
from workflow.primitives import Verdict


class OldWorkflow(Workflow):
    ask = LLMStep(name="ask", producer="ask.md")

    @staticmethod
    def on_ask(state, verdict):
        return state

    @staticmethod
    def on_verdict(state, verdict):
        ...
```

After:

```python
from pydantic import BaseModel

from workflow import LLMStep, SUCCESS, Workflow
from workflow.primitives import Outcome


class NewWorkflow(Workflow):
    class State(BaseModel):
        pass

    ask = LLMStep(name="ask", producer="ask.md")
    entry = ask
    transitions = {ask: {"done": SUCCESS}}

    @staticmethod
    def on_ask(state: State, outcome: Outcome, artifacts):
        return state
```

## Autoloop-v1

`autoloop_v1.py` is now a strict workflow. Run legacy-equivalent executions through `autoloop_v3.workflows.run_autoloop_v1(...)`.

What stays in the workflow file itself:

- phase-plan parsing
- explicit phase artifact templates such as `Artifact("{task_folder}/implement/phases/{state.phase.dir_key}/criteria.md")`

What stays workflow-owned beside the workflow:

- `autoloop_v3.workflows.autoloop_v1_conventions` owns exact legacy `plan.json` and `sessions/phases/{phase}.json` naming
- `autoloop_v3.workflows.autoloop_v1_parity` owns raw-phase-log and decisions persistence
- `autoloop_v3.workflows.autoloop_v1_parity` owns clarification note persistence and question / blocked / failed status mapping
- `workflow.observers` supplies the minimal generic execution observer seam used by the parity harness

That code is workflow-owned on purpose. The generic runtime remains unaware of phases, plan/implement/test policy, and Autoloop-specific artifact names.
