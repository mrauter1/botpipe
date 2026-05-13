# Botpipe

Botpipe is the execution layer above agentic provider harnesses such as Codex CLI
and Claude Code: executable SOPs (Standard Operating Procedures) that make
agents steerable by design, so they can act, pause, verify, and resume without
losing the plot.

Not a chat wrapper. Not just a workflow DSL. Not merely an SDK. Botpipe is a
runtime for turning open-ended model activity into execution you can observe,
resume, inspect, constrain, and trust.

Botpipe starts from a different assumption than frameworks centered on stateless
LLM API calls: the provider is already an agent. It holds session context, edits
files, uses tools, inspects a repo, makes judgments, etc... 
That power is fragile when it disappears into an invisible conversation:
context gets lost, files appear without provenance, decisions are hard to replay,
and failure often means starting over.

Botpipe exists because agentic coding and automation are becoming operational
infrastructure. They need a spine, and that spine is the SOP itself.

In Botpipe:

- steps become auditable units
- outputs become explicit artifacts
- decisions become routes
- pauses become checkpoints
- model sessions become runtime state
- verification becomes part of the workflow
- progress becomes something a human or another agent can safely continue
- repeated runs follow the same declared procedure

The goal is predictable agency: the model still has room to think, but the
possible shape of execution is visible before the run begins. The output may
vary; the process is reproducible.

In real operations, an SOP does not make every outcome identical. It makes the
work legible and repeatable: what gets checked, what evidence is collected, when
to escalate, what counts as done, and how the next operator can continue.
Botpipe brings that discipline to agentic execution.

## Installation

Botpipe targets Python 3.12+.

From this repository:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Check that the CLI can see the workflow catalog:

```bash
botpipe workflows list
```

Botpipe runs above an agentic provider harness. Use a supported provider such as
Codex CLI or Claude Code, and select it either in `botpipe.yaml` /
`botpipe.config` or at the call site:

```yaml
provider:
  name: codex
  model: your-model
```

Any mutating CLI command can also receive `--provider codex` and `--model ...`
directly.

## First Steps

Start with the smallest useful surface.

1. Make one SDK call when you want a controlled entry point into an agentic
   harness. Use the SDK directly from application code, tests, notebooks, or
   another agent:

   ```python
   from botpipe import Botpipe

   client = Botpipe(workspace=".", provider="codex")
   summary = client.llm("Summarize the current release risk.")
   ```

2. Scaffold a workflow when the process itself should become an SOP:

   ```bash
   botpipe init workflow review
   botpipe workflows show review
   botpipe run review task-1 \
     --message "Review this release" \
     --provider codex \
     --no-git
   ```

3. When the workflow pauses, resume it by task id:

   ```bash
   botpipe resume review task-1 --no-git
   botpipe answer review task-1 --answer "Approved" --no-git
   ```

Small calls and full workflows use the same runtime vocabulary: provider
configuration, policy, durable state, artifacts, routes, logs, and resumable
execution.

## Start With One Agentic Call

Botpipe does not require a full workflow on day one. The SDK can be used as a
controlled entry point for a single call through an agentic provider harness.

```python
from botpipe import Botpipe

client = Botpipe(workspace=".", provider="codex")

summary = client.llm("Summarize the current release risk.")
label = client.classify("Classify this request.", choices=["incident", "question"])
```

That gives even a small call the same runtime-owned provider configuration and
policy path. When the call needs an explicit artifact and route, run one step:

```python
from botpipe import FINISH, Botpipe, Md

client = Botpipe(workspace=".", provider="codex")

result = client.prompt_step(
    "Review the request and write a short report.",
    "Review the rollout plan.",
    writes=[Md("report", required=True)],
    routes={"done": FINISH},
)

if result.ok:
    print(result.artifacts.report.read_text())
```

Start with one call. Add artifacts, routes, verification, and checkpoints when
the operation needs them. Grow into an SOP when the process itself has to be
repeatable.

## Grow Into An Executable SOP

A Botpipe workflow is ordinary Python with explicit runtime contracts.

```python
from pydantic import BaseModel

from botpipe import FINISH, Event, Md, Prompt, Route, Text, Workflow, python_step, step


class ReviewWorkflow(Workflow):
    class Input(BaseModel):
        topic: str

    class Params(BaseModel):
        mode: str = "normal"

    class State(BaseModel):
        published: bool = False

    draft = step(
        Prompt.inline("Review {{ input.topic }}. Request: {{ message }}"),
        writes=[Md("report", required=True)],
        routes={
            "done": Route.to("publish", required_writes=["report"]),
        },
    )

    @python_step(
        requires=[draft.report],
        writes=[Text("receipt", required=True)],
        routes={"done": FINISH},
    )
    def publish(ctx):
        ctx.artifacts.receipt.write_text(f"mode={ctx.params.mode}")
        ctx.state = ctx.state.model_copy(update={"published": True})
        return Event("done")
```

The provider does not receive an unbounded blob of instructions. It receives the
current task plus a runtime step contract: readable inputs, required inputs,
writable artifacts, legal routes, route-specific obligations, and expected output
shape. The model still has room to reason. The runtime keeps the lane.

## Run A Workflow

From Python:

```python
from botpipe import Botpipe

client = Botpipe(workspace=".", provider="codex")

result = client.run(
    ReviewWorkflow,
    "Review the rollout plan.",
    input=ReviewWorkflow.Input(topic="rollout"),
    params={"mode": "strict"},
)

if result.ok:
    print(result.artifacts.report.read_text())
```

From the CLI:

```bash
botpipe workflows list
botpipe workflows show review

botpipe run review task-42 --message "Review this release" -wf mode strict
botpipe resume review task-42
botpipe answer review task-42 --answer "Approved"

botpipe runs list --workflow review
botpipe runs show review task-42
botpipe logs review task-42 --events
```

Workflow references can be catalog names, files, modules, or explicit classes:

```bash
botpipe run review task-1 --message "Review this"
botpipe run workflows/review.py task-1 --message "Review this"
botpipe run .botpipe/workflows/review/flow.py:ReviewWorkflow task-1 --message "Review this"
```

## Where It Fits

Botpipe sits beside the existing LLM ecosystem rather than trying to absorb it.

Use chat frameworks, RAG systems, tool libraries, graph runtimes, provider CLIs,
and hosted platforms where they are strong. Botpipe is the layer you add when
agentic harness calls need an execution envelope: an SOP, artifacts, routes,
checkpoints, verification, resumability, and comparable evidence.

Bring in Botpipe when that work needs an executable SOP:

- durable state instead of lost chat context
- named artifacts instead of unstructured side effects
- controlled routes instead of implicit next steps
- checkpoints instead of all-or-nothing sessions
- verification loops instead of unchecked completion
- inspectable history instead of "trust me"
- policy and provider boundaries instead of ambient authority
- repeatable procedure instead of one-off improvisation

Botpipe is less about making an LLM call easy and more about making a multi-turn
LLM run governable.

## Core Primitives

- `Workflow`: the executable unit.
- `Input`: typed structured run input.
- `Params`: typed workflow configuration.
- `State`: durable workflow state.
- `step(...)`: provider-backed prompt work.
- `produce_verify_step(...)`: producer plus independent verifier.
- `python_step(...)`: deterministic local execution.
- `Route`: legal decisions and their targets.
- `Json`, `Md`, `Text`, `Raw`: declared artifacts.
- `RequestInput`: a controlled human or system pause.
- `Botpipe`: the Python SDK client.
- `botpipe`: the CLI.

Most public code imports from the root package:

```python
from botpipe import Botpipe, Workflow, step, produce_verify_step, python_step
```

## Workflow Layout

Botpipe discovers workflows from three roots:

```text
workflows/                  repo-local workflows
.botpipe/workflows/         workspace-local overrides
botpipe/workflows/          package-installed workflows
```

Resolution precedence is `.botpipe/workflows/`, then `workflows/`, then package
workflows.

A typical workflow package:

```text
workflows/review/
  flow.py
  specs.py
  workflow.toml
  prompts/
  assets/
```

`workflow.toml` is metadata only: name, title, description, and aliases. The
workflow's behavior lives in Python.

## Read Next

- [Simple API](docs/simple-api.md): author workflows
- [SDK](docs/sdk.md): run workflows and steps from Python
- [Architecture](docs/architecture.md): runtime and project boundaries
- [Authoring](docs/authoring.md): deeper authoring guidance

## When To Use It

Use Botpipe when:

- you want a single agentic harness call to go through a controlled SDK surface
- the work spans multiple turns or sessions
- the agent writes files that matter
- verification is part of the job
- a human may need to interrupt, answer, or resume
- another agent should be able to inspect and continue
- you are automating repeated agentic harness calls
- you want to automate the same multi-step agentic procedure repeatedly
- repeated runs should leave comparable artifacts and evidence
- the final output must carry evidence of how it was produced

Start with one SDK call. Keep the SOP small when the operation is small. Expand
the procedure when agentic execution has become important enough that "the model
did something" is no longer an acceptable runtime story.
