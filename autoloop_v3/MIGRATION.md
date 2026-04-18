# Migration To The Final Strict Surface

`autoloop_v3` no longer tolerates compatibility-era workflow drift. Migrate workflows onto the canonical API instead of relying on aliases, injected names, or hidden normalization.

## Removed Authoring Compatibility

These are gone:

- `workflow.compat`
- `Verdict`
- `on_verdict`
- `SessionLifecycle`
- loader-injected authoring symbols
- handler arity adaptation
- inferred entry behavior
- hidden normalization of malformed workflow declarations
- observer-era extension plumbing as an authoring surface

## Canonical Replacements

- Use `Outcome` instead of `Verdict`.
- Use `on_outcome(state, outcome) -> Event | None`.
- Declare `Session()` slots and open them explicitly with `ctx.open_session(...)`.
- Give every workflow an explicit `entry`.
- Keep `transitions` explicit in Python code.
- Pair and LLM handlers use `(state, outcome, artifacts)` when present.
- System handlers use `(state, ctx)` and return `(state, event)`.
- Declare optional cross-cutting behavior through `Workflow.extensions`.

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

## Example Migration

Before:

```python
from workflow import LLMStep, SessionLifecycle, Workflow
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

from workflow import Context, LLMStep, SUCCESS, Session, Workflow
from workflow.primitives import Outcome


class NewWorkflow(Workflow):
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

## Extension Migration

Cross-cutting behavior now belongs in explicit workflow declarations:

```python
class ExampleWorkflow(Workflow):
    extensions = (
        Tracing(config=TracingConfig(enabled=True)),
        SessionPaths(strategy=MySessionPathStrategy()),
        GitTracking(policy=MyGitPolicy(), config=GitTrackingConfig(enabled=True)),
    )
```

Do not recreate the removed observer model through hidden runtime hooks. If a concern is orthogonal and optional, it belongs in `Workflow.extensions`. If it changes workflow meaning, it belongs in workflow code.

## Autoloop-v1 Placement

`autoloop_v1.py` stays a strict workflow and remains the readable canary.

What stays visible in the workflow file:

- explicit sessions
- explicit steps and transitions
- explicit artifact templates
- phase-plan parsing
- semantic state changes

What stays workflow-owned beside it:

- `autoloop_v3.workflows.autoloop_v1_conventions`
  - `phase_dir_key(...)`
  - `sessions/plan.json`
  - `sessions/phases/{phase}.json`
- `autoloop_v3.workflows.autoloop_v1_parity`
  - `run_autoloop_v1(...)`
  - `raw_phase_log.md`
  - `decisions.txt`
  - clarification persistence
  - question / blocked / failed status mapping

What stays generic:

- `.autoloop/tasks/{task_id}/runs/{run_id}`
- `request.md`
- `events.jsonl`
- `checkpoint.json`
- generic filesystem session persistence

## Retained Operational Compatibility Only

The retained compatibility scope is intentionally narrow:

- session payload compatibility for legacy `thread_id`
- config discovery from `autoloop.*` and legacy `superloop.*`
- legacy-readable status values only where parity tests require them

That retained scope is operational only. It must not be used to justify reintroducing authoring shims or hidden alternate execution behavior.
