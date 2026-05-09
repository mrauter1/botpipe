from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from botlane.core.errors import WorkflowExecutionError
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from botlane.runtime.loader import (
    ResolvedWorkflow,
    WorkflowDiscoveryError,
    inspect_workflow_reference,
    resolve_workflow_reference,
)
from botlane.runtime.runner import RunnerOptions, run_workflow_package
from botlane.core.primitives import Outcome


def _clear_generated_modules() -> None:
    importlib.invalidate_caches()
    for name in list(sys.modules):
        if (
            name == "workflows"
            or name.startswith("workflows.")
            or name == "botlane.workflows"
            or name.startswith("botlane.workflows.")
            or name == "_botlane_workspace_workflows"
            or name.startswith("_botlane_workspace_workflows.")
        ):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_generated_modules():
    _clear_generated_modules()
    yield
    _clear_generated_modules()


def _workspace_catalog_root(root: Path) -> Path:
    return root / ".botlane" / "workflows"


def _write_workspace_flow(
    root: Path,
    workflow_id: str,
    *,
    workflow_name: str | None = None,
    aliases: tuple[str, ...] = (),
    source: str | None = None,
    manifest: bool = False,
) -> Path:
    package_dir = _workspace_catalog_root(root) / workflow_id
    package_dir.mkdir(parents=True, exist_ok=True)
    if manifest:
        workflow_name = workflow_name or workflow_id
        aliases_source = ", ".join(f'"{alias}"' for alias in aliases)
        (package_dir / "workflow.toml").write_text(
            "\n".join(
                (
                    f'name = "{workflow_name}"',
                    f'title = "{workflow_name.replace("_", " ").title()}"',
                    'description = "workspace workflow"',
                    f"aliases = [{aliases_source}]",
                )
            )
            + "\n",
            encoding="utf-8",
        )
    if source is None:
        source = f"""
from __future__ import annotations

from botlane import Workflow, python_step


class {workflow_id.title().replace("_", "")}Workflow(Workflow):
    name = "{workflow_name or workflow_id}"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
    (package_dir / "flow.py").write_text(source + "\n", encoding="utf-8")
    return package_dir


def _write_workspace_single_file(root: Path, workflow_id: str, *, source: str | None = None) -> Path:
    source_path = _workspace_catalog_root(root) / f"{workflow_id}.py"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    if source is None:
        source = f"""
from __future__ import annotations

from botlane import Workflow, python_step


class {workflow_id.title().replace("_", "")}Workflow(Workflow):
    name = "{workflow_id}"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
    source_path.write_text(source + "\n", encoding="utf-8")
    return source_path


def test_single_file_reference_runs_with_file_scoped_prompts_and_origin_metadata(tmp_path: Path) -> None:
    workflow_path = tmp_path / "examples" / "release_review.py"
    prompts_dir = workflow_path.parent / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.joinpath("ask.md").write_text("single file prompt\n", encoding="utf-8")
    workflow_path.write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from botlane import Prompt, Raw, Workflow, step


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

    workflow_dir = tmp_path / ".botlane" / "tasks" / "single-file-task" / "wf_release_review"
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
    assert workflow_meta["workflow"]["module_name"].startswith("_botlane_workspace_workflows.")
    assert run_meta["workflow"]["name"] == "release_review"
    assert run_meta["workflow"]["reference"] == "examples/release_review.py"
    assert run_meta["workflow"]["source_path"] == "examples/release_review.py"


def test_flow_package_directory_reference_supports_relative_specs_and_named_inference(tmp_path: Path) -> None:
    catalog_package_dir = _workspace_catalog_root(tmp_path) / "release_review"
    explicit_package_dir = tmp_path / "workflows" / "release_review"

    prompts_dir = catalog_package_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.joinpath("ask.md").write_text("flow package prompt\n", encoding="utf-8")
    catalog_package_dir.joinpath("workflow.toml").write_text(
        'name = "release_review"\n'
        'title = "Release Review"\n'
        'description = "workspace workflow"\n',
        encoding="utf-8",
    )
    specs_source = """
from pydantic import BaseModel


class Params(BaseModel):
    mode: str = "strict"
""".strip()
    catalog_package_dir.joinpath("specs.py").write_text(specs_source + "\n", encoding="utf-8")
    flow_source = """
from __future__ import annotations

from pydantic import BaseModel

from botlane import Prompt, Raw, Workflow, step

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
    catalog_package_dir.joinpath("flow.py").write_text(flow_source + "\n", encoding="utf-8")

    (explicit_package_dir / "prompts").mkdir(parents=True, exist_ok=True)
    (explicit_package_dir / "prompts" / "ask.md").write_text("flow package prompt\n", encoding="utf-8")
    (explicit_package_dir / "specs.py").write_text(specs_source + "\n", encoding="utf-8")
    (explicit_package_dir / "flow.py").write_text(flow_source + "\n", encoding="utf-8")

    resolved_by_name = resolve_workflow_reference(tmp_path, "release_review")
    resolved_by_directory = resolve_workflow_reference(tmp_path, "workflows/release_review")
    assert resolved_by_name.reference.source_path == catalog_package_dir / "flow.py"
    assert resolved_by_name.reference.source_root == _workspace_catalog_root(tmp_path)
    assert resolved_by_name.reference.authoring_shape == "manifest_package"
    assert resolved_by_directory.reference.source_path == explicit_package_dir / "flow.py"
    assert resolved_by_directory.parameters_cls is not None
    assert resolved_by_directory.parameters_cls.__module__.startswith("_botlane_workspace_workflows.")
    assert resolved_by_directory.parameters_cls.__module__.endswith(".release_review.specs")

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
    workflow_dir = tmp_path / ".botlane" / "tasks" / "flow-package-task" / "wf_release_review"
    run_dir = next((workflow_dir / "runs").iterdir())
    context_payload = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))

    assert Path(context_payload["root"]) == tmp_path
    assert Path(context_payload["package_folder"]) == explicit_package_dir
    assert Path(context_payload["prompt_path"]) == explicit_package_dir / "prompts" / "ask.md"
    assert context_payload["workflow_params"] == {"mode": "strict"}


def test_bare_workflow_names_are_not_shadowed_by_unrelated_repo_paths(tmp_path: Path) -> None:
    package_dir = _write_workspace_flow(
        tmp_path,
        "demo",
        manifest=True,
        source="""
from __future__ import annotations

from botlane import Workflow, python_step


class DemoWorkflow(Workflow):
    name = "demo"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
    )
    (tmp_path / "demo").mkdir(parents=True, exist_ok=True)

    resolved = resolve_workflow_reference(tmp_path, "demo")

    assert resolved.reference.source_path == package_dir / "flow.py"
    assert resolved.reference.source_root == _workspace_catalog_root(tmp_path)
    assert resolved.reference.workflow_name == "demo"


def test_manifest_aliases_resolve_from_workspace_catalog_root_only(tmp_path: Path) -> None:
    explicit_package_dir = tmp_path / "workflows" / "release_review"
    explicit_package_dir.mkdir(parents=True, exist_ok=True)
    explicit_package_dir.joinpath("flow.py").write_text(
        """
from __future__ import annotations

from botlane import Workflow, python_step


class ReleaseReview(Workflow):
    name = "release_review"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkflowDiscoveryError, match="unknown workflow 'review-release'"):
        resolve_workflow_reference(tmp_path, "review-release")

    catalog_package_dir = _write_workspace_flow(
        tmp_path,
        "release_review",
        workflow_name="release_review",
        aliases=("review-release",),
        manifest=True,
        source="""
from __future__ import annotations

from botlane import Workflow, python_step


class ReleaseReview(Workflow):
    name = "release_review"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip(),
    )

    resolved = resolve_workflow_reference(tmp_path, "review-release")

    assert resolved.reference.source_path == catalog_package_dir / "flow.py"
    assert resolved.reference.source_root == _workspace_catalog_root(tmp_path)
    assert resolved.reference.workflow_name == "release_review"


def test_inspecting_imported_repo_catalog_class_preserves_aliases_and_exported_params(tmp_path: Path) -> None:
    workflows_root = tmp_path / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    workflows_root.joinpath("__init__.py").write_text("__all__ = []\n", encoding="utf-8")

    package_dir = workflows_root / "release_review"
    package_dir.mkdir(parents=True, exist_ok=True)
    package_dir.joinpath("workflow.toml").write_text(
        'name = "release_review"\n'
        'title = "Release Review"\n'
        'description = "repo workflow"\n'
        'aliases = ["review-release"]\n',
        encoding="utf-8",
    )
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
        "from .flow import ReleaseReview\nfrom .specs import Params\n__all__ = ['ReleaseReview', 'Params']\n",
        encoding="utf-8",
    )
    package_dir.joinpath("flow.py").write_text(
        """
from __future__ import annotations

from botlane import Workflow, python_step
from .specs import Params


class ReleaseReview(Workflow):
    name = "release_review"
    Params = Params

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

    resolved = resolve_workflow_reference(tmp_path, "review-release")
    inspected = inspect_workflow_reference(tmp_path, resolved.workflow_cls)

    assert inspected.workflow_name == "release_review"
    assert inspected.authoring_shape == "manifest_package"
    assert inspected.aliases == ("review-release",)
    assert inspected.parameters_supported is True
    assert inspected.parameters_model == "workflows.release_review.specs.Params"
    assert [field.name for field in inspected.parameters] == ["mode"]


def test_simple_declaration_workflow_is_discoverable_by_path_module_name_and_capability_inspection(tmp_path: Path) -> None:
    workflows_root = tmp_path / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    workflows_root.joinpath("__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    workflow_path = workflows_root / "simple_example.py"
    workflow_path.write_text(
        """
from __future__ import annotations

from botlane.simple import Workflow, step


class SimpleExample(Workflow):
    a = step("Do A.")
""".strip()
        + "\n",
        encoding="utf-8",
    )
    catalog_path = _write_workspace_single_file(
        tmp_path,
        "simple_example",
        source="""
from __future__ import annotations

from botlane.simple import Workflow, step


class SimpleExample(Workflow):
    a = step("Do A.")
""".strip(),
    )

    resolved_by_path = resolve_workflow_reference(tmp_path, "workflows/simple_example.py")
    resolved_by_name = resolve_workflow_reference(tmp_path, "simple_example")
    inspected = inspect_workflow_reference(tmp_path, "simple_example")

    assert resolved_by_path.reference.source_path == workflow_path
    assert resolved_by_name.reference.source_path == catalog_path
    assert resolved_by_name.reference.source_root == _workspace_catalog_root(tmp_path)
    assert resolved_by_name.reference.workflow_name == "simple_example"
    assert inspected.workflow_path == catalog_path
    assert inspected.entry_step_name == "a"
    assert inspected.routes["a"] == {
        "done": "FINISH",
        "question": "AWAIT_INPUT",
    }


def test_resolved_workflow_exposes_reference_only() -> None:
    assert not hasattr(ResolvedWorkflow, "package")


def test_explicit_class_references_use_workspace_isolated_module_namespace(tmp_path: Path) -> None:
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

from botlane import Workflow, python_step
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

    resolved = resolve_workflow_reference(tmp_path, "workflows/module_review/flow.py:ModuleReviewWorkflow")
    assert resolved.parameters_cls is not None
    assert resolved.parameters_cls.__module__.startswith("_botlane_workspace_workflows.")
    assert resolved.parameters_cls.__module__.endswith(".module_review.specs")

    result = run_workflow_package(
        "workflows/module_review/flow.py:ModuleReviewWorkflow",
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(
            root=tmp_path,
            task_id="module-task",
            message="Run module reference",
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    assert result.terminal == "FINISH"
    workflow_dir = tmp_path / ".botlane" / "tasks" / "module-task" / "wf_module_review"
    run_dir = next((workflow_dir / "runs").iterdir())
    assert (run_dir / "module.json").read_text(encoding="utf-8") == "module_review"


def test_imported_repo_local_class_references_use_workspace_isolated_module_namespace(tmp_path: Path) -> None:
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

from botlane import Workflow, python_step
from .specs import Params


class ModuleReviewWorkflow(Workflow):
    name = "module_review"
    Params = Params

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.syspath_prepend(str(tmp_path))
        from workflows.module_review.flow import ModuleReviewWorkflow

        resolved = resolve_workflow_reference(tmp_path, ModuleReviewWorkflow)

    assert resolved.workflow_cls is not ModuleReviewWorkflow
    assert resolved.workflow_cls.__module__.startswith("_botlane_workspace_workflows.")
    assert resolved.workflow_cls.__module__.endswith(".module_review.flow")
    assert resolved.parameters_cls is not None
    assert resolved.parameters_cls.__module__.startswith("_botlane_workspace_workflows.")
    assert resolved.parameters_cls.__module__.endswith(".module_review.specs")


def test_file_reference_requires_class_name_when_multiple_workflows_exist(tmp_path: Path) -> None:
    workflow_path = tmp_path / "examples" / "ambiguous.py"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(
        """
from __future__ import annotations

from botlane import Workflow, python_step


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
    workflows_root = _workspace_catalog_root(tmp_path)
    workflows_root.mkdir(parents=True, exist_ok=True)

    package_dir = workflows_root / "release_review"
    package_dir.mkdir(parents=True, exist_ok=True)
    package_dir.joinpath("workflow.toml").write_text(
        'name = "release_review"\n'
        'title = "Release Review"\n'
        'description = "workspace workflow"\n',
        encoding="utf-8",
    )
    package_dir.joinpath("flow.py").write_text(
        """
from __future__ import annotations

from botlane import Workflow, python_step


class PackageReleaseReview(Workflow):
    name = "release_review"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )
    _write_workspace_single_file(
        tmp_path,
        "release_review",
        source="""
from __future__ import annotations

from botlane import Workflow, python_step


class FileReleaseReview(Workflow):
    name = "release_review"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
    )

    with pytest.raises(WorkflowDiscoveryError, match="duplicate workflow resolution key 'release_review'"):
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

from botlane import Workflow, python_step


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

from botlane import Workflow, python_step


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

from botlane import Workflow, python_step

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

from botlane import Workflow, python_step


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

from botlane import Workflow, python_step


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
    package_params = resolve_workflow_reference(tmp_path, "workflows/package_params")
    legacy_params = resolve_workflow_reference(tmp_path, "workflows/legacy_params")
    no_params = resolve_workflow_reference(tmp_path, "workflows/no_params.py")

    assert class_params.parameters_cls is not None
    assert class_params.parameters_cls.__qualname__.endswith("ClassParamsWorkflow.Params")
    assert module_params.parameters_cls is not None
    assert module_params.parameters_cls.__module__.startswith("_botlane_workspace_workflows.")
    assert module_params.parameters_cls.__module__.endswith(".module_params.flow")
    assert package_params.parameters_cls is not None
    assert package_params.parameters_cls.__module__.startswith("_botlane_workspace_workflows.")
    assert package_params.parameters_cls.__module__.endswith(".package_params.specs")
    assert legacy_params.parameters_cls is not None
    assert legacy_params.parameters_cls.__module__.startswith("_botlane_workspace_workflows.")
    assert legacy_params.parameters_cls.__module__.endswith(".params")
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

from botlane import Workflow, python_step

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

from botlane import Workflow, python_step


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
