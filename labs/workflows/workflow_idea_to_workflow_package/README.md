# Workflow Idea to Workflow Package

This experimental discovery alias delegates to the packaged
[`workflow_author`](../../../botpipe/workflows/workflow_author/README.md).
It uses the same bounded author/test/review loop, mandatory behavioral tests,
transcript, candidate isolation and typed `WorkflowAuthorResult`.

```python
from botpipe import Botpipe
from labs.workflows.workflow_idea_to_workflow_package import Params, workflow_callable

with Botpipe(workspace=".") as runtime:
    run = runtime.run(
        workflow_callable,
        Params(package_name="customer_escalation"),
        request="Review customer escalations.",
    )
```

Check `run.value.shipped`, `findings`, `reference`, `candidate_root` and `validation`.
The alias never skips the generated behavioral tests and does not publish the candidate.
