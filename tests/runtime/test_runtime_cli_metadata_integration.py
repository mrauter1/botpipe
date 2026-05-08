from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

import botlane
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.runtime import cli
from botlane.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from botlane.runtime.loader import resolve_workflow_reference
from botlane.runtime.runner import RunnerOptions, run_workflow_package


def _clear_workflow_modules() -> None:
    importlib.invalidate_caches()
    for name in list(sys.modules):
        if (
            name == "botlane.workflows"
            or name.startswith("botlane.workflows.")
            or name.startswith("_botlane_workspace_workflows.")
        ):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_workflow_modules():
    _clear_workflow_modules()
    yield
    _clear_workflow_modules()


def _configure_package_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    package_base = tmp_path / "installed" / "botlane"
    package_root = package_base / "workflows"
    package_root.mkdir(parents=True, exist_ok=True)
    (package_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    monkeypatch.setattr(botlane, "__path__", [str(package_base), *list(botlane.__path__)], raising=False)
    monkeypatch.setattr("botlane.core.workflow_catalog.package_workflows_root", lambda: package_root.resolve())
    importlib.invalidate_caches()
    return package_root


def _write_workspace_workflow(root: Path, workflow_id: str, *, aliases: tuple[str, ...] = ()) -> Path:
    package_dir = root / ".botlane" / "workflows" / workflow_id
    package_dir.mkdir(parents=True, exist_ok=True)
    aliases_source = ", ".join(f'"{alias}"' for alias in aliases)
    (package_dir / "workflow.toml").write_text(
        "\n".join(
            (
                f'name = "{workflow_id}"',
                f'title = "{workflow_id.replace("_", " ").title()}"',
                'description = "workspace workflow"',
                f"aliases = [{aliases_source}]",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "prompts" / "README.md").write_text("# Prompts\n", encoding="utf-8")
    (package_dir / "assets" / ".gitkeep").write_text("", encoding="utf-8")
    (package_dir / "flow.py").write_text(
        f"""
from __future__ import annotations

from botlane import Event, FINISH, Workflow, python_step


class {workflow_id.title().replace("_", "")}Workflow(Workflow):
    name = "{workflow_id}"

    @python_step(name="bootstrap", routes={{"ready": FINISH}})
    def bootstrap(ctx):
        return Event("ready")
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return package_dir


def _write_package_workflow(package_root: Path, workflow_id: str, *, aliases: tuple[str, ...] = ()) -> Path:
    package_dir = package_root / workflow_id
    package_dir.mkdir(parents=True, exist_ok=True)
    aliases_source = ", ".join(f'"{alias}"' for alias in aliases)
    class_name = f"{workflow_id.title().replace('_', '')}Workflow"
    (package_dir / "workflow.toml").write_text(
        "\n".join(
            (
                f'name = "{workflow_id}"',
                f'title = "{workflow_id.replace("_", " ").title()}"',
                'description = "package workflow"',
                f"aliases = [{aliases_source}]",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "prompts").mkdir(exist_ok=True)
    (package_dir / "assets").mkdir(exist_ok=True)
    (package_dir / "prompts" / "README.md").write_text("# Prompts\n", encoding="utf-8")
    (package_dir / "assets" / ".gitkeep").write_text("", encoding="utf-8")
    (package_dir / "flow.py").write_text(
        f"""
from __future__ import annotations

from botlane import Event, FINISH, Workflow, python_step


class {class_name}(Workflow):
    name = "{workflow_id}"

    @python_step(name="bootstrap", routes={{"ready": FINISH}})
    def bootstrap(ctx):
        return Event("ready")
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "__init__.py").write_text(
        f"from .flow import {class_name}\n__all__ = ['{class_name}']\n",
        encoding="utf-8",
    )
    return package_dir


def test_workspace_run_metadata_records_origin_fields(tmp_path: Path) -> None:
    package_dir = _write_workspace_workflow(tmp_path, "local_demo")

    result = run_workflow_package(
        "local_demo",
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(
            root=tmp_path,
            task_id="task-local-demo",
            message="Run local demo",
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    assert result.terminal == "FINISH"
    workflow_dir = tmp_path / ".botlane" / "tasks" / "task-local-demo" / "wf_local_demo"
    run_dir = next((workflow_dir / "runs").iterdir())
    workflow_meta = json.loads((workflow_dir / "workflow.json").read_text(encoding="utf-8"))
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    for payload in (workflow_meta["workflow"], run_meta["workflow"]):
        assert payload["name"] == "local_demo"
        assert payload["reference"] == "local_demo"
        assert payload["source_root_kind"] == "workspace"
        assert payload["source_root"] == ".botlane/workflows"
        assert payload["package_folder"] == ".botlane/workflows/local_demo"
        assert payload["package_name"] == "local_demo"
        assert payload["package_module"] is None
        assert payload["workflow_module"] is None
        assert payload["source_path"] == ".botlane/workflows/local_demo/flow.py"
        assert payload["manifest_path"] == ".botlane/workflows/local_demo/workflow.toml"

    assert workflow_meta["package_folder"] == ".botlane/workflows/local_demo"
    assert run_meta["package_folder"] == ".botlane/workflows/local_demo"
    assert package_dir.exists()


def test_explicit_manifest_run_metadata_normalizes_external_origin(tmp_path: Path) -> None:
    external_dir = tmp_path / "external" / "explicit_demo"
    external_dir.mkdir(parents=True, exist_ok=True)
    (external_dir / "workflow.toml").write_text(
        'name = "explicit_demo"\n'
        'title = "Explicit Demo"\n'
        'description = "external workflow"\n',
        encoding="utf-8",
    )
    (external_dir / "flow.py").write_text(
        """
from __future__ import annotations

from botlane import Event, FINISH, Workflow, python_step


class ExplicitDemo(Workflow):
    name = "explicit_demo"

    @python_step(name="bootstrap", routes={"ready": FINISH})
    def bootstrap(ctx):
        return Event("ready")
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = run_workflow_package(
        str(external_dir / "workflow.toml"),
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(
            root=tmp_path,
            task_id="task-explicit-demo",
            message="Run explicit demo",
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    assert result.terminal == "FINISH"
    workflow_dir = tmp_path / ".botlane" / "tasks" / "task-explicit-demo" / "wf_explicit_demo"
    run_dir = next((workflow_dir / "runs").iterdir())
    payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["workflow"]

    assert payload["reference"] == str(external_dir / "workflow.toml")
    assert payload["source_root_kind"] == "workspace"
    assert payload["source_root"] is None
    assert payload["package_name"] == "explicit_demo"
    assert payload["package_module"] is None
    assert payload["workflow_module"] is None
    assert payload["package_folder"] == "external/explicit_demo"
    assert payload["source_path"] == "external/explicit_demo/flow.py"
    assert payload["manifest_path"] == "external/explicit_demo/workflow.toml"
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_meta["package_folder"] == "external/explicit_demo"


def test_explicit_python_file_run_metadata_uses_absolute_origin_outside_workspace_root(tmp_path: Path) -> None:
    external_dir = tmp_path.parent / f"{tmp_path.name}-outside"
    external_dir.mkdir(parents=True, exist_ok=True)
    external_file = external_dir / "single_explicit.py"
    external_file.write_text(
        """
from __future__ import annotations

from botlane import Event, FINISH, Workflow, python_step


class SingleExplicitWorkflow(Workflow):
    name = "single_explicit"

    @python_step(name="bootstrap", routes={"ready": FINISH})
    def bootstrap(ctx):
        return Event("ready")
""".strip()
        + "\n",
        encoding="utf-8",
    )

    resolved = resolve_workflow_reference(tmp_path, str(external_file))
    assert resolved.manifest_path is None
    assert resolved.source_root_kind == "workspace"
    assert resolved.package_module is None
    assert resolved.workflow_module is None

    result = run_workflow_package(
        str(external_file),
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(
            root=tmp_path,
            task_id="task-single-explicit",
            message="Run explicit python workflow",
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    assert result.terminal == "FINISH"
    run_dir = next((tmp_path / ".botlane" / "tasks" / "task-single-explicit" / "wf_single_explicit" / "runs").iterdir())
    payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["workflow"]

    assert payload["reference"] == str(external_file)
    assert payload["authoring_shape"] == "single_file"
    assert payload["source_root_kind"] == "workspace"
    assert payload["source_root"] is None
    assert payload["package_name"] == "single_explicit"
    assert payload["package_module"] is None
    assert payload["workflow_module"] is None
    assert payload["package_folder"] == str(external_dir)
    assert payload["source_path"] == str(external_file)
    assert payload["manifest_path"] is None


def test_package_run_metadata_records_package_modules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package_root = _configure_package_root(monkeypatch, tmp_path)
    package_dir = _write_package_workflow(package_root, "package_demo")

    resolved = resolve_workflow_reference(tmp_path, "package_demo")
    assert resolved.source_root_kind == "package"
    assert resolved.package_module == "botlane.workflows.package_demo"
    assert resolved.workflow_module == "botlane.workflows.package_demo.flow"

    result = run_workflow_package(
        "package_demo",
        provider=ScriptedLLMProvider(),
        options=RunnerOptions(
            root=tmp_path,
            task_id="task-package-demo",
            message="Run package demo",
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    assert result.terminal == "FINISH"
    run_dir = next((tmp_path / ".botlane" / "tasks" / "task-package-demo" / "wf_package_demo" / "runs").iterdir())
    payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["workflow"]

    assert payload["source_root_kind"] == "package"
    assert payload["package_folder"] == "installed/botlane/workflows/package_demo"
    assert payload["package_name"] == "package_demo"
    assert payload["package_module"] == "botlane.workflows.package_demo"
    assert payload["workflow_module"] == "botlane.workflows.package_demo.flow"
    assert payload["source_root"] == "installed/botlane/workflows"


def test_cli_workflows_list_show_and_all_emit_shadow_and_source_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    package_root = _configure_package_root(monkeypatch, tmp_path)
    package_dir = _write_package_workflow(package_root, "shared_demo", aliases=("shared",))
    workspace_dir = _write_workspace_workflow(tmp_path, "shared_demo", aliases=("shared",))

    exit_code = cli.main(["workflows", "list", "--workspace", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == [
        {
            "aliases": ["shared"],
            "authoring_shape": "manifest_package",
            "description": "workspace workflow",
            "manifest_present": True,
            "name": "shared_demo",
            "package_folder": str(workspace_dir),
            "shadowed": False,
            "shadowed_by": None,
            "source_path": str(workspace_dir / "flow.py"),
            "source_root_kind": "workspace",
            "title": "Shared Demo",
        }
    ]

    exit_code = cli.main(["workflows", "list", "--all", "--workspace", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload[0]["source_root_kind"] == "workspace"
    assert payload[0]["shadowed"] is False
    assert payload[1]["source_root_kind"] == "package"
    assert payload[1]["package_folder"] == str(package_dir)
    assert payload[1]["shadowed"] is True
    assert payload[1]["shadowed_by"] == "shared_demo"

    exit_code = cli.main(["workflows", "show", "shared_demo", "--workspace", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["name"] == "shared_demo"
    assert payload["source_root_kind"] == "workspace"
    assert payload["source_root"] == str(tmp_path / ".botlane" / "workflows")
    assert payload["package_folder"] == str(workspace_dir)
    assert payload["package_module"] is None
    assert payload["workflow_module"] is None
    assert payload["shadowed"] is False
    assert payload["shadowed_by"] is None


def test_cli_workflows_show_emits_package_source_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    package_root = _configure_package_root(monkeypatch, tmp_path)
    package_dir = _write_package_workflow(package_root, "package_show")

    exit_code = cli.main(["workflows", "show", "package_show", "--workspace", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["name"] == "package_show"
    assert payload["source_root_kind"] == "package"
    assert payload["source_root"] == str(package_root)
    assert payload["package_folder"] == str(package_dir)
    assert payload["package_name"] == "package_show"
    assert payload["package_module"] == "botlane.workflows.package_show"
    assert payload["workflow_module"] == "botlane.workflows.package_show.flow"
    assert payload["shadowed"] is False
    assert payload["shadowed_by"] is None


def test_cli_init_workflow_scaffolds_under_dot_botlane_workflows(tmp_path: Path, capsys) -> None:
    exit_code = cli.main(["init", "workflow", "demo", "--workspace", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    package_dir = tmp_path / ".botlane" / "workflows" / "demo"

    assert exit_code == 0
    assert payload["shape"] == "package"
    assert payload["package_folder"] == str(package_dir)
    assert (package_dir / "flow.py").exists()
    assert (package_dir / "workflow.toml").exists()
    assert (package_dir / "prompts" / "README.md").exists()
    assert (package_dir / "assets" / ".gitkeep").exists()
    assert not (tmp_path / "workflows").exists()

    resolved = resolve_workflow_reference(tmp_path, "demo")
    assert resolved.source_root_kind == "workspace"
    assert resolved.package_module is None
    assert resolved.workflow_module is None


def test_cli_workflows_list_help_describes_package_and_dot_botlane_roots(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["workflows", "list", "--help"])

    assert excinfo.value.code == 0
    help_text = capsys.readouterr().out
    assert "--workspace WORKSPACE" in help_text
    assert "--workspace" in help_text
    assert "--root" not in help_text
    assert "ROOT" not in help_text
    assert "workspace directory" in help_text.lower()
    assert "installed botlane package" in help_text
    assert "workspace workflows are loaded" in help_text
    assert "`.botlane/workflows/`" in help_text
    assert "autoloop" not in help_text
