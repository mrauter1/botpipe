# autoloop_v3

`autoloop_v3` is a strict workflow framework with three layers:

- `autoloop_v3.workflow`: canonical authoring surface, validation, compilation, engine, provider/store protocols.
- `autoloop_v3.runtime`: generic filesystem runtime for task/run workspaces, request snapshots, events, checkpoints, prompt resolution, and session persistence.
- `autoloop_v3.workflows`: workflow-owned parity and conventions modules. `run_autoloop_v1()` lives here because legacy Autoloop behavior is workflow policy, not runtime-core architecture.

There is no compatibility layer. The root `workflow/` package is only a strict re-export of the canonical surface.

## Public Surface

Author workflows with:

- `Workflow`
- `Context`
- `Session`
- `Artifact`
- `Prompt`
- `PairStep`
- `LLMStep`
- `SystemStep`
- `SUCCESS`
- `PAUSE`
- `FAIL`
- `GLOBAL`

From `workflow.primitives` use:

- `Event`
- `Outcome`
- `Checkpoint`
- `ResolvedArtifacts`

`PairStep` and `LLMStep` handlers are optional. `SystemStep` handlers are required.

## Session Model

Sessions are declared as slots and opened explicitly:

```python
class Example(Workflow):
    main = Session()

    def on_start(self, ctx: Context) -> None:
        ctx.open_session(self.main)
```

The engine only performs lookup:

```python
session = ctx.get_session(step.session)
```

There is no `SessionLifecycle`, no automatic opening, and no computed session identity.

## Execution Observation

The core exposes one minimal observer seam through `workflow.observers`:

- provider-turn events after producer, verifier, and llm calls
- step-completed events after every step
- terminal events for success, pause, fail, and fatal exceptions

The observer surface is output-only. It does not alter engine semantics. `run_autoloop_v1(...)` uses this seam to rebuild raw logs, phase events, clarification persistence, and legacy status mapping without provider wrappers or engine subclasses.

## Running Workflows

Generic runtime:

```bash
python -m autoloop_v3.runtime.cli path/to/workflow.py \
  --task-id example-task \
  --provider-factory package.module:factory \
  --root /repo
```

Autoloop-v1 parity harness:

```python
from pathlib import Path

from autoloop_v3.runtime.runner import RunnerOptions
from autoloop_v3.workflows import run_autoloop_v1

result = run_autoloop_v1(
    Path("autoloop_v1.py"),
    provider=provider,
    options=RunnerOptions(root=Path("."), task_id="task-1", request_text="Ship it"),
)
```

The harness preserves legacy-oriented raw logs, decisions, and session filenames such as:

- `.autoloop/tasks/{task_id}/raw_phase_log.md`
- `.autoloop/tasks/{task_id}/decisions.txt`
- `.autoloop/tasks/{task_id}/runs/{run_id}/raw_phase_log.md`
- `.autoloop/tasks/{task_id}/runs/{run_id}/sessions/plan.json`
- `.autoloop/tasks/{task_id}/runs/{run_id}/sessions/phases/{phase}.json`

The exact legacy session filenames live in `autoloop_v3.workflows.autoloop_v1_conventions`. Raw-log, clarification-ledger, and status policies live in `autoloop_v3.workflows.autoloop_v1_parity`.

## Configuration

Generic configuration stays intentionally small:

- provider wiring and settings such as `provider.name`, `provider.codex.model`, `provider.codex.model_effort`, `provider.claude.model`, `provider.claude.effort`, and `provider.claude.permission_strategy`
- runtime controls such as `max_steps` and `intent_mode`

Legacy discovery of `superloop.*` config filenames remains only as config-file compatibility. It does not restore legacy workflow authoring behavior.

## Reading Order

- [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md)
- [MIGRATION.md](MIGRATION.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/authoring.md](docs/authoring.md)
- [docs/parity-matrix.md](docs/parity-matrix.md)
