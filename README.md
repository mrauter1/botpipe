# Botpipe

Botpipe is the SOP runtime for agentic workflows.

It defines and enforces Standard Operating Procedures (SOPs) for coding agents, turning one-off prompts into repeatable, auditable, and verifiable runs.

Real coding tasks are multi-turn: the agent plans, edits, runs tests, finds issues, revises, and tries again. Without orchestration, the human becomes the workflow engine, manually prompting, checking results, asking for fixes, and keeping track of what happened.

Botpipe turns agent work into governed workflow execution. You define the procedure once: the inputs, steps, policies, artifacts, verification gates, routes, and handoff points. Botpipe then runs that procedure consistently across provider-backed agents such as Codex CLI and Claude Code.

The agent still does the work. Botpipe governs the run.

An SOP in Botpipe answers questions like:

- What is the agent supposed to accomplish?
- What inputs and parameters does it receive?
- What files, commands, or network access are allowed?
- What artifacts must it produce?
- How is the work verified?
- What outcomes are valid?
- What happens on success, failure, rework or escalation?
- How many times may the agent retry or revise?
- Where are logs, state, checkpoints, and evidence stored?

Botpipe is not a chat wrapper. It is the operating layer for repeatable, inspectable, and enforceable multi-turn agentic work.

## Installation

Botpipe targets Python 3.12+.

From this repository:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Configure a supported provider in `botpipe.yaml` or pass one at runtime.

```yaml
provider:
  name: codex
  model: your-model
```

When using Codex CLI, each provider-backed step is a full Codex CLI execution.
That means the step can inspect the repository, edit files, run terminal
commands, create or update tests, and use command output to continue work.

## First Steps

Start with the smallest surface that gives you the control you need.

### CLI

Use the CLI when the workflow itself is the unit of operation and you want task
ids, run history, logs, resume behavior, and operator handoff.

```bash
# List available workflows.
botpipe workflows list --workspace .

# Inspect one workflow.
botpipe workflows show ralph_loop --workspace .

# Start a run. The JSON output includes the generated task_id and folders.
botpipe run ralph_loop "Implement the requested repository change." \
  --provider codex \
  --workspace .

# Inspect the run.
botpipe runs show ralph_loop <task-id> --workspace .
botpipe logs ralph_loop <task-id> --events --workspace .

# Resume a paused or interrupted run.
botpipe resume ralph_loop <task-id> --workspace .
```

Use the CLI path when you care about workspace execution, durable task folders,
operator-visible logs, and repeatable command-line runs.

### SDK

Use the SDK when Botpipe is called from Python code, tests, notebooks, services,
or another agent.

```python
from botpipe import Botpipe

client = Botpipe(workspace=".", provider="codex")

result = client.llm("Summarize the current repository risk.")
print(result)
```

For multi-step work, call a workflow:

```python
from botpipe import Botpipe
from botpipe.workflows.ralph_loop import RalphLoop

client = Botpipe(workspace=".", provider="codex")

result = client.run(
    RalphLoop,
    "Add CSV export support to the report generator and cover it with tests.",
    input=RalphLoop.Input(
        request="Add CSV export support to the report generator and cover it with tests."
    ),
    task_id="csv-export",
)

print(result.status)
print(result.debug.run_dir)
```

Use the SDK path when Botpipe is part of a larger program but you still want
provider configuration, policy, durable state, artifacts, routes, logs, and
resumable execution.

## Policy Security

Provider access is part of the workflow contract.

A Botpipe policy declares how a provider-backed step may run: sandbox mode,
permission mode, writable paths, denied paths, network posture, model effort,
and related provider settings. Policy is not a prompt convention. It is runtime
metadata that Botpipe resolves into provider-specific execution configuration.
Enforcement is backend-dependent; unsupported controls fail by default unless
provider-policy validation is explicitly relaxed.

A minimal locked-down policy:

```python
from botpipe import NetworkMode, PermissionMode, Policy, SandboxMode

repo_locked = Policy(
    permission_mode=PermissionMode.FULL_AUTO_SANDBOXED,
    sandbox_mode=SandboxMode.WORKSPACE_WRITE,
    allow_write=(
        "src/",
        "tests/",
        ".botpipe/",
    ),
    deny_read=(
        ".env",
        ".secrets/**",
    ),
    deny_write=(
        "/etc",
        "/usr/local/bin",
    ),
    network=NetworkMode.NONE,
)
```

Backend capability matters. For example, the current Codex CLI policy emission
surface can run in workspace-write mode and restrict writable roots, but it does
not enforce `deny_read` or domain-level network filters. If a Codex-backed run
requests those unsupported controls, Botpipe fails by default instead of
pretending they are enforced. Claude Code has a different enforcement surface.

Attach a policy at workflow level when every provider-backed step should inherit
the same boundary:

```python
from botpipe import Workflow


class SafeWorkflow(Workflow):
    policy = repo_locked
```

Attach or override a policy at step level when different steps need different
access:

```python
from botpipe import NetworkMode, PermissionMode, Policy, Prompt, SandboxMode, step

readonly_review = Policy(
    permission_mode=PermissionMode.ASK,
    sandbox_mode=SandboxMode.READ_ONLY,
    network=NetworkMode.NONE,
)

repo_edit = Policy(
    permission_mode=PermissionMode.FULL_AUTO_SANDBOXED,
    sandbox_mode=SandboxMode.WORKSPACE_WRITE,
    allow_write=("src/", "tests/", ".botpipe/"),
    deny_read=(".env", ".secrets/**"),
    network=NetworkMode.NONE,
)

review = step(
    Prompt.inline("Inspect the repository and identify the change required."),
    policy=readonly_review,
)

implement = step(
    Prompt.inline("Implement the approved change and run the relevant tests."),
    policy=repo_edit,
)
```

Use policy to make the intended security posture visible before the run starts:

- read-only review steps should not need write access
- implementation steps should write only to the paths they are expected to edit
- secret files should not live in workspaces used for autonomous execution; use
  `deny_read` only when the selected backend can enforce or honestly reject it
- network access should be disabled unless the workflow needs it
- dangerous unsandboxed execution should be rare, explicit, and reviewable

Botpipe can still run powerful providers. The difference is that the power is
declared, constrained, and auditable.

See `SECURITY.md` for the project security model, trusted-code boundary, and
vulnerability reporting process.

## Workflow Example: Minimal Ralph-loop

A Ralph-loop is a small executable SOP for agentic implementation work.

This example uses two `produce_verify_step(...)` steps:

1. `plan` writes `work.json`.
2. `implement` runs once per work item. It changes the repository directly. Its
   verifier checks the actual implementation.

Each provider-backed step is a full Codex CLI execution. It can inspect files,
edit files, run commands, create or update tests, and use terminal output as
evidence.

```python
from pydantic import BaseModel

from botpipe import FINISH, Md, Prompt, Route, Workflow, Worklist, produce_verify_step
from botpipe.core import Artifact


class RalphLoop(Workflow):
    name = "ralph_loop"

    class Input(BaseModel):
        request: str

    work = Artifact.json(
        "{{ workflow.folder }}/work.json",
        name="work",
        required=True,
    )

    items = Worklist.from_artifact(
        name="item",
        artifact=work,
        collection="items",
        item_id="id",
        title="title",
        status="status",
    )

    plan = produce_verify_step(
        producer_prompt=Prompt.inline(
            """
            Read {{ input.request }}. Inspect the repository.

            Write work.json with a complete implementation plan decomposed into
            independently implementable items.

            Shape:
            {
              "goal": "The requested outcome",
              "items": [
                {
                  "id": "item-1",
                  "title": "Short imperative title",
                  "status": "planned",
                  "goal": "What to implement",
                  "acceptance_checks": ["What must be true"]
                }
              ]
            }
            """.strip()
        ),
        verifier_prompt=Prompt.inline(
            """
            Verify work.json.

            Accept only if it fully covers {{ input.request }}, is ordered, and
            each item is independently implementable with acceptance checks.

            Write plan_review.md with the decision and required rework, if any.
            """.strip()
        ),
        producer_writes=[work],
        verifier_writes=[
            Md("plan_review", path="plan_review.md", required=True),
        ],
        routes={
            "accepted": Route.to(
                "implement",
                required_writes=["work", "plan_review"],
            ),
            "needs_rework": Route.to(
                "plan",
                required_writes=["plan_review"],
            ),
        },
    )

    implement = produce_verify_step(
        scope=items,
        requires=[plan.work],
        verifier_requires=[plan.work],
        producer_prompt=Prompt.inline(
            """
            Read work.json and the current item.

            Current item:
            - id: {{ item.id }}
            - title: {{ item.title }}
            - payload: {{ item.payload }}

            Implement this item completely and correctly in the repository.
            Edit files, add or update tests, run validation, and fix failures.
            """.strip()
        ),
        verifier_prompt=Prompt.inline(
            """
            Verify the repository implementation for the current item.

            Check work.json, the item payload, repo diff, source files, tests,
            and relevant command output.

            Accept only if the item is correctly and completely implemented
            with no remaining gaps.

            Write implementation_review.md with the decision and exact rework
            instructions if rejected.
            """.strip()
        ),
        verifier_writes=[
            Md(
                "implementation_review",
                path="items/{{ item.dir_key }}/implementation_review.md",
                required=True,
            ),
        ],
        routes={
            "accepted": Route.complete_and_advance(
                "implement",
                exhausted=FINISH,
                required_writes=["implementation_review"],
            ),
            "needs_rework": Route.to(
                "implement",
                required_writes=["implementation_review"],
            ),
        },
    )
```

The important point is that `implement` is not a packaging or summary step. It
is the implementation step. The producer modifies the repository and runs the
needed commands. The verifier independently checks whether the implementation
fully and correctly satisfies the current plan item.

## Run the Ralph-loop

From the CLI:

```bash
botpipe run ralph_loop "Add CSV export support to the report generator and cover it with tests." \
  --task csv-export \
  --provider codex \
  --workspace .

botpipe runs show ralph_loop csv-export --workspace .
botpipe logs ralph_loop csv-export --events --workspace .
```

From Python:

```python
from botpipe import Botpipe
from botpipe.workflows.ralph_loop import RalphLoop

client = Botpipe(workspace=".", provider="codex")

result = client.run(
    RalphLoop,
    "Add CSV export support to the report generator and cover it with tests.",
    input=RalphLoop.Input(
        request="Add CSV export support to the report generator and cover it with tests."
    ),
    task_id="csv-export",
)

print(result.status)
print(result.history)
print(result.debug.run_dir)
```

## Where It Fits

Botpipe sits above provider harnesses such as Codex CLI. It does not replace the
provider. It gives provider executions a durable workflow envelope.

Add Botpipe when an agentic harness call needs:

- durable state instead of lost chat context
- named artifacts instead of unstructured side effects
- controlled routes instead of implicit next steps
- checkpoints instead of all-or-nothing sessions
- verifier loops instead of unchecked completion
- inspectable history instead of "trust me"
- policy and provider boundaries instead of ambient authority
- repeatable procedure instead of one-off improvisation

Botpipe is less about making an LLM call easy and more about making a multi-step
agentic run governable.

## Core Primitives

- `Workflow`: the executable unit.
- `Input`: typed structured run input.
- `Params`: typed workflow configuration.
- `State`: durable workflow state.
- `step(...)`: provider-backed prompt work.
- `produce_verify_step(...)`: producer plus independent verifier.
- `python_step(...)`: deterministic local execution.
- `Worklist`: scoped repeated execution over items.
- `Route`: legal decisions and their targets.
- `Json`, `Md`, `Text`, `Raw`: declared artifacts.
- `Policy`: provider access and execution constraints.
- `SandboxMode`, `NetworkMode`, `PermissionMode`: public policy controls.
- `RequestInput`: a controlled human or system pause.
- `Botpipe`: the Python SDK client.
- `botpipe`: the CLI.

Most public code imports from the root package:

```python
from botpipe import Botpipe, Policy, Workflow, Worklist, produce_verify_step, step, python_step
```

## Workflow Layout

Botpipe discovers workflows from configured workflow roots such as:

```text
workflows/                  repo-local workflows
.botpipe/workflows/         workspace-local overrides
botpipe/workflows/          package-installed workflows
```

A typical workflow package:

```text
botpipe/workflows/ralph_loop/
  workflow.py
  workflow.toml
  README.md
```

`workflow.toml` is metadata: name, title, description, aliases, and other
catalog information. The workflow behavior lives in Python.

## Read Next

- `docs/simple-api.md`: author workflows
- `docs/sdk.md`: run workflows and steps from Python
- `docs/architecture.md`: runtime and project boundaries
- `docs/authoring.md`: deeper authoring guidance
- `docs/workflow_authoring_guidelines.md`: workflow design doctrine for Codex-scale steps

## License

Botpipe is licensed under the Apache License, Version 2.0. See `LICENSE`.
