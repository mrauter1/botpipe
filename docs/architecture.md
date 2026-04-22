# Architecture

The internal workflow kernel lives under `core/`.

The public authoring contract does not point users at internal modules. Authors import the strict root shims:

- `workflow`
- `workflow.primitives`

Repo-root `workflows/` is a regular Python package reserved for actual workflow packages. Each workflow package is also a regular package and must include:

- `__init__.py`
- `workflow.py`
- `workflow.toml`
- `prompts/`
- `assets/`

`workflow.toml` is metadata-only discovery input. It is limited to human-facing fields such as `name`, `title`, `description`, and `aliases`. It does not define topology, prompts, transitions, parameters, or execution semantics.

Workflow discovery scans `<root>/workflows/*/workflow.toml`, then loads the main workflow class from `workflows.<package>.workflow`. Package `__init__.py` must re-export that main class so workflow packages remain directly importable building blocks:

```python
from workflows.autoloop_v1 import AutoloopV1
```
