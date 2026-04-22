# Authoring

Use the strict root `workflow` shim when authoring workflows:

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

Workflow packages live under repo-root `workflows/` and are ordinary Python packages. The package `__init__.py` must re-export the main workflow class, and may also re-export `Parameters` when the workflow defines workflow-specific parameters.

Keep the root surface strict: do not import engine internals, compiler helpers, or compatibility modules from `workflow`.
