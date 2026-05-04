from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

import autoloop
from autoloop.core.workflow_catalog import (
    WorkflowCatalogDiscoveryError,
    discover_workflow_catalog,
    workflow_search_roots,
)
from autoloop.runtime.loader import WorkflowDiscoveryError, resolve_workflow_reference


def _clear_workflow_modules() -> None:
    importlib.invalidate_caches()
    for name in list(sys.modules):
        if (
            name == "autoloop.workflows"
            or name.startswith("autoloop.workflows.")
            or name.startswith("_autoloop_workspace_workflows.")
        ):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_modules():
    _clear_workflow_modules()
    yield
    _clear_workflow_modules()


def _configure_package_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    package_base = tmp_path / "installed" / "autoloop"
    package_root = package_base / "workflows"
    package_root.mkdir(parents=True, exist_ok=True)
    (package_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    monkeypatch.setattr(autoloop, "__path__", [str(package_base), *list(autoloop.__path__)], raising=False)
    monkeypatch.setattr(
        "autoloop.core.workflow_catalog.package_workflows_root",
        lambda: package_root.resolve(),
    )
    importlib.invalidate_caches()
    return package_root


def _write_workspace_flow(
    root: Path,
    workflow_id: str,
    *,
    workflow_name: str | None = None,
    aliases: tuple[str, ...] = (),
    manifest: bool = False,
    class_name: str = "LocalWorkflow",
    source: str | None = None,
) -> Path:
    package_dir = root / ".autoloop" / "workflows" / workflow_id
    package_dir.mkdir(parents=True, exist_ok=True)
    if manifest:
        aliases_source = ", ".join(f'"{alias}"' for alias in aliases)
        (package_dir / "workflow.toml").write_text(
            "\n".join(
                (
                    f'name = "{workflow_name or workflow_id}"',
                    f'title = "{(workflow_name or workflow_id).replace("_", " ").title()}"',
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

from autoloop import Workflow, python_step


class {class_name}(Workflow):
    name = "{workflow_name or workflow_id}"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
    (package_dir / "flow.py").write_text(source + "\n", encoding="utf-8")
    return package_dir


def _write_workspace_single_file(root: Path, workflow_id: str, *, class_name: str = "SingleWorkflow") -> Path:
    source_path = root / ".autoloop" / "workflows" / f"{workflow_id}.py"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        f"""
from __future__ import annotations

from autoloop import Workflow, python_step


class {class_name}(Workflow):
    name = "{workflow_id}"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return source_path


def _write_package_flow(
    package_root: Path,
    workflow_id: str,
    *,
    workflow_name: str | None = None,
    aliases: tuple[str, ...] = (),
    class_name: str = "PackageWorkflow",
    source: str | None = None,
) -> Path:
    package_dir = package_root / workflow_id
    package_dir.mkdir(parents=True, exist_ok=True)
    aliases_source = ", ".join(f'"{alias}"' for alias in aliases)
    (package_dir / "workflow.toml").write_text(
        "\n".join(
            (
                f'name = "{workflow_name or workflow_id}"',
                f'title = "{(workflow_name or workflow_id).replace("_", " ").title()}"',
                'description = "package workflow"',
                f"aliases = [{aliases_source}]",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    if source is None:
        source = f"""
from __future__ import annotations

from autoloop import Workflow, python_step


class {class_name}(Workflow):
    name = "{workflow_name or workflow_id}"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
    (package_dir / "flow.py").write_text(source + "\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text(
        f"from .flow import {class_name}\n__all__ = ['{class_name}']\n",
        encoding="utf-8",
    )
    return package_dir


def test_workflow_search_roots_use_only_workspace_and_package_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_root = _configure_package_root(monkeypatch, tmp_path)

    roots = workflow_search_roots(tmp_path)

    assert tuple(root.kind for root in roots) == ("workspace", "package")
    assert roots[0].path == tmp_path / ".autoloop" / "workflows"
    assert roots[1].path == package_root
    assert roots[0].precedence > roots[1].precedence
    assert all(root.path != tmp_path / "workflows" for root in roots)


def test_discover_workflow_catalog_returns_workspace_and_package_source_kinds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_root = _configure_package_root(monkeypatch, tmp_path)
    _write_package_flow(package_root, "package_demo")
    _write_workspace_flow(tmp_path, "local_demo", manifest=True)
    _write_workspace_single_file(tmp_path, "single_demo")

    entries = {entry.workflow_name: entry for entry in discover_workflow_catalog(tmp_path)}

    assert entries["package_demo"].source_root_kind == "package"
    assert entries["package_demo"].package_module == "autoloop.workflows.package_demo"
    assert entries["package_demo"].workflow_module == "autoloop.workflows.package_demo.flow"
    assert entries["local_demo"].source_root_kind == "workspace"
    assert entries["local_demo"].package_module is None
    assert entries["local_demo"].workflow_module is None
    assert entries["single_demo"].source_root_kind == "workspace"
    assert entries["single_demo"].authoring_shape == "single_file"


@pytest.mark.parametrize(
    ("package_name", "package_aliases", "workspace_name", "workspace_aliases", "reference"),
    (
        ("shared", (), "shared", (), "shared"),
        ("shared", (), "local_demo", ("shared",), "shared"),
        ("package_demo", ("shared",), "shared", (), "shared"),
        ("package_demo", ("shared",), "local_demo", ("shared",), "shared"),
    ),
)
def test_workspace_catalog_keys_shadow_package_catalog_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    package_name: str,
    package_aliases: tuple[str, ...],
    workspace_name: str,
    workspace_aliases: tuple[str, ...],
    reference: str,
) -> None:
    package_root = _configure_package_root(monkeypatch, tmp_path)
    _write_package_flow(package_root, "package_demo", workflow_name=package_name, aliases=package_aliases)
    workspace_dir = _write_workspace_flow(
        tmp_path,
        "local_demo",
        workflow_name=workspace_name,
        aliases=workspace_aliases,
        manifest=True,
    )

    resolved = resolve_workflow_reference(tmp_path, reference)
    all_entries = discover_workflow_catalog(tmp_path, include_shadowed=True)
    shadowed = [entry for entry in all_entries if entry.shadowed]

    assert resolved.reference.package_dir == workspace_dir
    assert resolved.reference.source_root_kind == "workspace"
    assert len(shadowed) == 1
    assert shadowed[0].source_root_kind == "package"
    assert shadowed[0].shadowed_by == workspace_name


def test_same_tier_resolution_key_collisions_fail_with_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_package_root(monkeypatch, tmp_path)
    _write_workspace_flow(tmp_path, "alpha", workflow_name="alpha", aliases=("shared",), manifest=True)
    _write_workspace_flow(tmp_path, "beta", workflow_name="beta", aliases=("shared",), manifest=True)

    with pytest.raises(WorkflowCatalogDiscoveryError, match="duplicate workflow resolution key 'shared'"):
        discover_workflow_catalog(tmp_path)


def test_unknown_bare_name_lists_searched_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_root = _configure_package_root(monkeypatch, tmp_path)

    with pytest.raises(WorkflowDiscoveryError) as excinfo:
        resolve_workflow_reference(tmp_path, "missing_workflow")

    message = str(excinfo.value)
    assert "missing_workflow" in message
    assert str(tmp_path) in message
    assert str(tmp_path / ".autoloop" / "workflows") in message
    assert str(package_root) in message


def test_explicit_manifest_path_resolves_outside_catalog_roots(tmp_path: Path) -> None:
    external_dir = tmp_path / "external" / "demo"
    external_dir.mkdir(parents=True, exist_ok=True)
    (external_dir / "workflow.toml").write_text(
        'name = "external_demo"\n'
        'title = "External Demo"\n'
        'description = "external workflow"\n',
        encoding="utf-8",
    )
    (external_dir / "flow.py").write_text(
        """
from __future__ import annotations

from autoloop import Workflow, python_step


class ExternalDemo(Workflow):
    name = "external_demo"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

    resolved = resolve_workflow_reference(tmp_path, str(external_dir / "workflow.toml"))

    assert resolved.reference.source_path == external_dir / "flow.py"
    assert resolved.reference.source_root_kind == "workspace"
    assert resolved.reference.package_module is None
    assert resolved.reference.workflow_module is None


def test_workspace_relative_imports_use_isolated_module_namespace(tmp_path: Path) -> None:
    package_dir = tmp_path / ".autoloop" / "workflows" / "relative_demo"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "workflow.toml").write_text(
        'name = "relative_demo"\n'
        'title = "Relative Demo"\n'
        'description = "relative import workflow"\n',
        encoding="utf-8",
    )
    (package_dir / "specs.py").write_text(
        "class Settings:\n    mode = 'strict'\n",
        encoding="utf-8",
    )
    (package_dir / "params.py").write_text(
        """
from pydantic import BaseModel

from .specs import Settings


class Params(BaseModel):
    mode: str = Settings.mode
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "contracts.py").write_text(
        "from pydantic import BaseModel\n\n\nclass Output(BaseModel):\n    pass\n",
        encoding="utf-8",
    )
    (package_dir / "flow.py").write_text(
        """
from __future__ import annotations

from autoloop import Workflow, python_step

from .params import Params
from .contracts import Output


class RelativeDemo(Workflow):
    name = "relative_demo"
    Params = Params
    Output = Output

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

    resolved = resolve_workflow_reference(tmp_path, "relative_demo")

    assert resolved.reference.source_root_kind == "workspace"
    assert resolved.workflow_cls.__module__.startswith("_autoloop_workspace_workflows.")
    assert resolved.workflow_cls.__module__.endswith(".relative_demo.flow")


def test_manifest_class_field_selects_specific_workflow_class(tmp_path: Path) -> None:
    package_dir = tmp_path / ".autoloop" / "workflows" / "classed"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "workflow.toml").write_text(
        'name = "classed"\n'
        'title = "Classed"\n'
        'description = "class selector"\n'
        'class = "SelectedWorkflow"\n',
        encoding="utf-8",
    )
    (package_dir / "flow.py").write_text(
        """
from __future__ import annotations

from autoloop import Workflow, python_step


class IgnoredWorkflow(Workflow):
    name = "ignored"

    @python_step(name="start")
    def start(ctx):
        return None


class SelectedWorkflow(Workflow):
    name = "classed"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

    resolved = resolve_workflow_reference(tmp_path, "classed")

    assert resolved.workflow_cls.__name__ == "SelectedWorkflow"


def test_manifest_without_class_rejects_multiple_workflow_classes(tmp_path: Path) -> None:
    package_dir = _write_workspace_flow(
        tmp_path,
        "ambiguous",
        manifest=True,
        source="""
from __future__ import annotations

from autoloop import Workflow, python_step


class AlphaWorkflow(Workflow):
    name = "ambiguous"

    @python_step(name="start")
    def start(ctx):
        return None


class BetaWorkflow(Workflow):
    name = "ambiguous"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip(),
    )

    with pytest.raises(WorkflowDiscoveryError, match="multiple workflow classes were found"):
        resolve_workflow_reference(tmp_path, str(package_dir / "workflow.toml"))
