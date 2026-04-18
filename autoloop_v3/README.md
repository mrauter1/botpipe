# autoloop_v3

`autoloop_v3` targets a strict Book Architecture:

- `autoloop_v3.workflow` is the strict canonical kernel.
- `autoloop_v3.runtime` is the workflow-agnostic filesystem runtime.
- `autoloop_v3.stdlib` is tiny pure authoring sugar.
- `autoloop_v3.extensions` is a tiny optional extension surface.
- `autoloop_v3.workflows` owns workflow-specific parity, conventions, and thin composition roots only.

There is no compatibility layer, no hidden normalization boundary, and no generic workspace hook or plugin system. Any repo-root `workflow/` shim, if present, is a strict re-export only.

## Canonical Surface

Import workflow authorship from `workflow`:

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

Import workflow primitives from `workflow.primitives`:

- `Event`
- `Outcome`
- `Checkpoint`
- `ResolvedArtifacts`

`PairStep` and `LLMStep` handlers are optional. `SystemStep` handlers are required.

## Execution Model

The final model is intentionally small:

1. The loader imports the workflow module without injecting symbols.
2. The workflow validates strictly and compiles deterministically.
3. The runtime creates `.autoloop/tasks/{task_id}/runs/{run_id}` and the immutable `request.md` snapshot.
4. The runtime binds any `Workflow.extensions` declarations for the run.
5. The engine executes against explicit sessions, resolved artifacts, typed checkpoints, and deterministic routing.
6. The runtime appends generic `events.jsonl`.
7. Workflow-owned parity code may add workflow-specific logs or ledgers beside the generic runtime artifacts.

## Optional Layers

`autoloop_v3.stdlib` is pure authoring sugar only. It stays small:

- `control.py`
- `prompts.py`
- `steps.py`
- `state/cursor.py`

`autoloop_v3.extensions` is explicit opt-in only:

- `Tracing(...)`
- `SessionPaths(...)`
- `GitTracking(...)`

Extensions compose through `Workflow.extensions`. They may perform side effects, but they may not alter workflow state, routing, or kernel semantics.

## Running Workflows

Generic workflows run through the generic runtime:

```bash
python -m autoloop_v3.runtime.cli path/to/workflow.py \
  --task-id example-task \
  --provider-factory package.module:factory \
  --root /repo
```

Autoloop-v1 legacy-equivalent runs stay workflow-owned:

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

That composition root owns the workflow-specific parity surface, including:

- `raw_phase_log.md`
- `decisions.txt`
- `sessions/plan.json`
- `sessions/phases/{phase}.json`
- question / blocked / failed status mapping

The exact filename conventions live in `autoloop_v3.workflows.autoloop_v1_conventions`. Raw log, clarification, and status parity live in `autoloop_v3.workflows.autoloop_v1_parity`.

## Configuration

Generic configuration stays small and typed:

- provider wiring and provider settings
- runtime controls such as `max_steps` and `intent_mode`
- extension config for optional modules

Config does not encode workflow topology, phase meaning, or commit policy.

## Retained Compatibility

The retained compatibility scope is narrow and operational only:

- legacy session payload compatibility for `thread_id`
- legacy-readable `latest_run_status` values where parity tests require them
- config discovery for `autoloop.*` and legacy `superloop.*` files

It does not restore workflow authoring shims, inferred entry behavior, or compatibility aliases.

## Reading Order

- [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md)
- [MIGRATION.md](MIGRATION.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/authoring.md](docs/authoring.md)
- [docs/compatibility.md](docs/compatibility.md)
- [docs/parity-matrix.md](docs/parity-matrix.md)
- [docs/risk-register.md](docs/risk-register.md)
