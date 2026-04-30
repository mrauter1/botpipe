from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from core.errors import WorkflowExecutionError
from core.providers.fake import ScriptedLLMProvider
from runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from runtime.loader import (
    ResolvedWorkflow,
    WorkflowDiscoveryError,
    inspect_workflow_reference,
    resolve_workflow_reference,
)
from runtime.runner import RunnerOptions, run_workflow_package
from core.primitives import Outcome


def _clear_generated_modules() -> None:
    importlib.invalidate_caches()
    for name in list(sys.modules):
        if name == "workflows" or name.startswith("workflows.") or name.startswith("_autoloop_dynamic_"):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_generated_modules():
    _clear_generated_modules()
    yield
    _clear_generated_modules()


def test_single_file_reference_runs_with_file_scoped_prompts_and_origin_metadata(tmp_path: Path) -> None:
    workflow_path = tmp_path / "examples" / "release_review.py"
    prompts_dir = workflow_path.parent / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.joinpath("ask.md").write_text("single file prompt\n", encoding="utf-8")
    workflow_path.write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from autoloop import Prompt, Raw, Workflow, step


class ReleaseReview(Workflow):
    class State(BaseModel):
        note: str = ""

    ask = step(
        prompt=Prompt.file("prompts/ask.md"),
        writes=[Raw("context_dump", path="{run_folder}/context.json")],
    )
""".strip()
        + "\n",
        encoding="utf-8",
    )

    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                request.artifacts.context_dump.write_text(
                    json.dumps(
                        {
                            "root": str(request.context.root),
                            "package_folder": str(request.context.package_folder),
                            "prompt_path": request.prompt.path,
                            "prompt_text": request.prompt.text,
                        }
                    )
                ),
                Outcome(raw_output="ok", tag="done", payload={"note": "captured"}),
            )[1]
        ]
    )

    result = run_workflow_package(
        "examples/release_review.py",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="single-file-task",
            message="Inspect single-file workflow",
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    assert result.terminal == "FINISH"

    workflow_dir = tmp_path / ".autoloop" / "tasks" / "single-file-task" / "wf_release_review"
    run_dir = next((workflow_dir / "runs").iterdir())
    context_payload = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))
    workflow_meta = json.loads((workflow_dir / "workflow.json").read_text(encoding="utf-8"))
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert Path(context_payload["root"]) == tmp_path
    assert Path(context_payload["package_folder"]) == tmp_path / "examples"
    assert Path(context_payload["prompt_path"]) == tmp_path / "examples" / "prompts" / "ask.md"
    assert context_payload["prompt_text"] == "single file prompt\n"
    assert workflow_meta["workflow"]["name"] == "release_review"
    assert workflow_meta["workflow"]["reference"] == "examples/release_review.py"
    assert workflow_meta["workflow"]["source_path"] == "examples/release_review.py"
    assert workflow_meta["workflow"]["manifest_path"] is None
    assert workflow_meta["workflow"]["class_name"] == "ReleaseReview"
    assert workflow_meta["workflow"]["authoring_shape"] == "single_file"
    assert workflow_meta["workflow"]["module_name"].startswith("_autoloop_dynamic_")
    assert run_meta["workflow"]["name"] == "release_review"
    assert run_meta["workflow"]["reference"] == "examples/release_review.py"
    assert run_meta["workflow"]["source_path"] == "examples/release_review.py"


def test_flow_package_directory_reference_supports_relative_specs_and_named_inference(tmp_path: Path) -> None:
    workflows_root = tmp_path / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    workflows_root.joinpath("__init__.py").write_text("__all__ = []\n", encoding="utf-8")

    package_dir = workflows_root / "release_review"
    prompts_dir = package_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.joinpath("ask.md").write_text("flow package prompt\n", encoding="utf-8")
    package_dir.joinpath("specs.py").write_text(
        """
from pydantic import BaseModel


class Params(BaseModel):
    mode: str = "strict"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    package_dir.joinpath("flow.py").write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from autoloop import Prompt, Raw, Workflow, step

from .specs import Params


class ReleaseReview(Workflow):
    name = "release_review"
    Params = Params

    class State(BaseModel):
        mode: str = ""

    ask = step(
        prompt=Prompt.file("prompts/ask.md"),
        writes=[Raw("context_dump", path="{run_folder}/context.json")],
    )
""".strip()
        + "\n",
        encoding="utf-8",
    )

    resolved_by_name = resolve_workflow_reference(tmp_path, "release_review")
    resolved_by_directory = resolve_workflow_reference(tmp_path, "workflows/release_review")
    assert resolved_by_name.reference.source_path == package_dir / "flow.py"
    assert resolved_by_name.reference.authoring_shape == "flow_package"
    assert resolved_by_directory.parameters_cls is not None
    assert resolved_by_directory.parameters_cls.__name__ == "Params"

    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                request.artifacts.context_dump.write_text(
                    json.dumps(
                        {
                            "root": str(request.context.root),
                            "package_folder": str(request.context.package_folder),
                            "prompt_path": request.prompt.path,
                            "workflow_params": request.context.workflow_params,
                        }
                    )
                ),
                Outcome(raw_output="ok", tag="done", payload={"mode": request.context.workflow_params["mode"]}),
            )[1]
        ]
    )

    result = run_workflow_package(
        "workflows/release_review",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="flow-package-task",
            message="Inspect flow package workflow",
            workflow_params={"mode": "strict"},
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    assert result.terminal == "FINISH"
    workflow_dir = tmp_path / ".autoloop" / "tasks" / "flow-package-task" / "wf_release_review"
    run_dir = next((workflow_dir / "runs").iterdir())
    context_payload = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))

    assert Path(context_payload["root"]) == tmp_path
    assert Path(context_payload["package_folder"]) == package_dir
    assert Path(context_payload["prompt_path"]) == package_dir / "prompts" / "ask.md"
    assert context_payload["workflow_params"] == {"mode": "strict"}


def test_bare_workflow_names_are_not_shadowed_by_unrelated_repo_paths(tmp_path: Path) -> None:
    workflows_root = tmp_path / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    workflows_root.joinpath("__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    workflows_root.joinpath("demo.py").write_text(
        """
from __future__ import annotations

from autoloop import Workflow, python_step


class DemoWorkflow(Workflow):
    name = "demo"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "demo").mkdir(parents=True, exist_ok=True)

    resolved = resolve_workflow_reference(tmp_path, "demo")

    assert resolved.reference.source_path == workflows_root / "demo.py"
    assert resolved.reference.workflow_name == "demo"


def test_simple_declaration_workflow_is_discoverable_by_path_module_name_and_capability_inspection(tmp_path: Path) -> None:
    workflows_root = tmp_path / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    workflows_root.joinpath("__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    workflow_path = workflows_root / "simple_example.py"
    workflow_path.write_text(
        """
from __future__ import annotations

from autoloop.simple import Workflow, step


class SimpleExample(Workflow):
    a = step("Do A.")
""".strip()
        + "\n",
        encoding="utf-8",
    )

    resolved_by_path = resolve_workflow_reference(tmp_path, "workflows/simple_example.py")
    resolved_by_module = resolve_workflow_reference(tmp_path, "workflows.simple_example")
    resolved_by_name = resolve_workflow_reference(tmp_path, "simple_example")
    inspected = inspect_workflow_reference(tmp_path, "simple_example")

    assert resolved_by_path.reference.source_path == workflow_path
    assert resolved_by_module.reference.source_path == workflow_path
    assert resolved_by_name.reference.source_path == workflow_path
    assert resolved_by_name.reference.workflow_name == "simple_example"
    assert inspected.workflow_path == workflow_path
    assert inspected.entry_step_name == "a"
    assert inspected.routes["a"] == {
        "done": "FINISH",
        "question": "PAUSE",
        "blocked": "PAUSE",
        "failed": "FAIL",
    }


def test_resolved_workflow_exposes_reference_only() -> None:
    assert not hasattr(ResolvedWorkflow, "package")


def test_module_and_class_references_run_through_the_same_resolver_path(tmp_path: Path) -> None:
    workflows_root = tmp_path / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    workflows_root.joinpath("__init__.py").write_text("__all__ = []\n", encoding="utf-8")

    package_dir = workflows_root / "module_review"
    package_dir.mkdir(parents=True, exist_ok=True)
    package_dir.joinpath("specs.py").write_text(
        """
from pydantic import BaseModel


class Params(BaseModel):
    mode: str = "strict"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    package_dir.joinpath("__init__.py").write_text(
        "from .flow import ModuleReviewWorkflow\nfrom .specs import Params\n__all__ = ['ModuleReviewWorkflow', 'Params']\n",
        encoding="utf-8",
    )
    package_dir.joinpath("flow.py").write_text(
        """
from __future__ import annotations

from autoloop import Workflow, python_step
from .specs import Params


class ModuleReviewWorkflow(Workflow):
    name = "module_review"
    Params = Params

    @python_step(name="start")
    def start(ctx):
        (ctx.run_folder / "module.json").write_text(ctx.workflow_name, encoding="utf-8")
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

    resolved = resolve_workflow_reference(tmp_path, "workflows.module_review.flow:ModuleReviewWorkflow")
    assert resolved.parameters_cls is not None
    assert resolved.parameters_cls.__module__ == "workflows.module_review.specs"

    result = run_workflow_package(
        "workflows.module_review.flow:ModuleReviewWorkflow",
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(
            root=tmp_path,
            task_id="module-task",
            message="Run module reference",
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    assert result.terminal == "FINISH"
    workflow_dir = tmp_path / ".autoloop" / "tasks" / "module-task" / "wf_module_review"
    run_dir = next((workflow_dir / "runs").iterdir())
    assert (run_dir / "module.json").read_text(encoding="utf-8") == "module_review"


def test_file_reference_requires_class_name_when_multiple_workflows_exist(tmp_path: Path) -> None:
    workflow_path = tmp_path / "examples" / "ambiguous.py"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(
        """
from __future__ import annotations

from autoloop import Workflow, python_step


class AlphaWorkflow(Workflow):
    @python_step(name="start")
    def start(ctx):
        return None


class BetaWorkflow(Workflow):
    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkflowDiscoveryError, match="multiple workflow classes were found"):
        resolve_workflow_reference(tmp_path, "examples/ambiguous.py")

    resolved = resolve_workflow_reference(tmp_path, "examples/ambiguous.py:AlphaWorkflow")
    assert resolved.workflow_cls.__name__ == "AlphaWorkflow"


def test_named_references_fail_when_inferred_candidates_conflict(tmp_path: Path) -> None:
    workflows_root = tmp_path / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    workflows_root.joinpath("__init__.py").write_text("__all__ = []\n", encoding="utf-8")

    package_dir = workflows_root / "release_review"
    package_dir.mkdir(parents=True, exist_ok=True)
    package_dir.joinpath("flow.py").write_text(
        """
from __future__ import annotations

from autoloop import Workflow, python_step


class PackageReleaseReview(Workflow):
    name = "release_review"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )
    workflows_root.joinpath("release_review.py").write_text(
        """
from __future__ import annotations

from autoloop import Workflow, python_step


class FileReleaseReview(Workflow):
    name = "release_review"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkflowDiscoveryError, match="duplicate workflow name 'release_review'"):
        resolve_workflow_reference(tmp_path, "release_review")


def test_parameter_resolution_follows_class_module_package_legacy_then_none(tmp_path: Path) -> None:
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)
    workflows_root = tmp_path / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    workflows_root.joinpath("__init__.py").write_text("__all__ = []\n", encoding="utf-8")

    examples_dir.joinpath("class_params.py").write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from autoloop import Workflow, python_step


class ClassParamsWorkflow(Workflow):
    class Params(BaseModel):
        mode: str = "class"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

    module_params_dir = workflows_root / "module_params"
    module_params_dir.mkdir(parents=True, exist_ok=True)
    module_params_dir.joinpath("flow.py").write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from autoloop import Workflow, python_step


class Params(BaseModel):
    mode: str = "module"


class ModuleParamsWorkflow(Workflow):
    name = "module_params"
    Params = Params

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

    package_params_dir = workflows_root / "package_params"
    package_params_dir.mkdir(parents=True, exist_ok=True)
    package_params_dir.joinpath("specs.py").write_text(
        """
from pydantic import BaseModel


class Params(BaseModel):
    mode: str = "package"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    package_params_dir.joinpath("__init__.py").write_text(
        "from .flow import PackageParamsWorkflow\nfrom .specs import Params\n__all__ = ['PackageParamsWorkflow', 'Params']\n",
        encoding="utf-8",
    )
    package_params_dir.joinpath("flow.py").write_text(
        """
from __future__ import annotations

from autoloop import Workflow, python_step

from .specs import Params


class PackageParamsWorkflow(Workflow):
    name = "package_params"
    Params = Params

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

    legacy_params_dir = workflows_root / "legacy_params"
    legacy_params_dir.mkdir(parents=True, exist_ok=True)
    legacy_params_dir.joinpath("params.py").write_text(
        """
from pydantic import BaseModel


class Params(BaseModel):
    mode: str = "legacy"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    legacy_params_dir.joinpath("flow.py").write_text(
        """
from __future__ import annotations

from autoloop import Workflow, python_step


class LegacyParamsWorkflow(Workflow):
    name = "legacy_params"
    Params = None

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

    workflows_root.joinpath("no_params.py").write_text(
        """
from __future__ import annotations

from autoloop import Workflow, python_step


class NoParamsWorkflow(Workflow):
    name = "no_params"
    Params = None

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

    class_params = resolve_workflow_reference(tmp_path, "examples/class_params.py")
    module_params = resolve_workflow_reference(tmp_path, "workflows/module_params")
    package_params = resolve_workflow_reference(tmp_path, "workflows.package_params.flow:PackageParamsWorkflow")
    legacy_params = resolve_workflow_reference(tmp_path, "workflows/legacy_params")
    no_params = resolve_workflow_reference(tmp_path, "workflows/no_params.py")

    assert class_params.parameters_cls is not None
    assert class_params.parameters_cls.__qualname__.endswith("ClassParamsWorkflow.Params")
    assert module_params.parameters_cls is not None
    assert module_params.parameters_cls.__module__.startswith("_autoloop_dynamic_")
    assert package_params.parameters_cls is not None
    assert package_params.parameters_cls.__module__ == "workflows.package_params.specs"
    assert legacy_params.parameters_cls is not None
    assert legacy_params.parameters_cls.__module__.startswith("_autoloop_dynamic_")
    assert no_params.parameters_cls is None


def test_explicit_package_paths_prefer_package_exported_parameters_before_legacy_params(tmp_path: Path) -> None:
    workflows_root = tmp_path / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    workflows_root.joinpath("__init__.py").write_text("__all__ = []\n", encoding="utf-8")

    package_dir = workflows_root / "package_path_params"
    package_dir.mkdir(parents=True, exist_ok=True)
    package_dir.joinpath("__init__.py").write_text(
        "from .workflow import PackagePathParamsWorkflow\nfrom .specs import Params\n__all__ = ['PackagePathParamsWorkflow', 'Params']\n",
        encoding="utf-8",
    )
    package_dir.joinpath("specs.py").write_text(
        """
from pydantic import BaseModel


class Params(BaseModel):
    mode: str = "package"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    package_dir.joinpath("params.py").write_text(
        """
from pydantic import BaseModel


class Params(BaseModel):
    mode: str = "legacy"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    package_dir.joinpath("workflow.py").write_text(
        """
from __future__ import annotations

from autoloop import Workflow, python_step

from .specs import Params


class PackagePathParamsWorkflow(Workflow):
    name = "package_path_params"
    Params = Params

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

    resolved = resolve_workflow_reference(tmp_path, "workflows/package_path_params")

    assert resolved.parameters_cls is not None
    assert resolved.parameters_cls.__name__ == "Params"
    assert resolved.parameters_cls.model_fields["mode"].default == "package"


def test_workflow_origin_collisions_fail_before_run_history_is_merged(tmp_path: Path) -> None:
    first = tmp_path / "examples" / "alpha" / "release_review.py"
    second = tmp_path / "examples" / "beta" / "release_review.py"
    for path in (first, second):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            """
from __future__ import annotations

from autoloop import Workflow, python_step


class ReleaseReview(Workflow):
    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
            + "\n",
            encoding="utf-8",
        )

    first_result = run_workflow_package(
        "examples/alpha/release_review.py",
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(
            root=tmp_path,
            task_id="collision-task",
            message="First origin",
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )
    assert first_result.terminal == "FINISH"

    with pytest.raises(WorkflowExecutionError, match="already associated with a different origin"):
        run_workflow_package(
            "examples/beta/release_review.py",
            provider=ScriptedLLMProvider(),
            options=RunnerOptions(
                root=tmp_path,
                task_id="collision-task",
                message="Second origin",
                runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
            ),
        )
