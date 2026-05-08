from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

import botlane
from botlane.core.workflow_catalog import (
    WorkflowCatalogDiscoveryError,
    WorkflowCatalogManifestError,
    discover_workflow_catalog,
    read_workflow_manifest,
    workflow_search_roots,
)
from botlane.runtime.loader import WorkflowDiscoveryError, resolve_workflow_reference


def _clear_workflow_modules() -> None:
    importlib.invalidate_caches()
    for name in list(sys.modules):
        if (
            name == "workflows"
            or name.startswith("workflows.")
            or name == "botlane.workflows"
            or name.startswith("botlane.workflows.")
            or name.startswith("_botlane_workspace_workflows.")
        ):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_modules():
    _clear_workflow_modules()
    yield
    _clear_workflow_modules()


def _configure_package_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    package_base = tmp_path / "installed" / "botlane"
    package_root = package_base / "workflows"
    package_root.mkdir(parents=True, exist_ok=True)
    (package_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    monkeypatch.setattr(botlane, "__path__", [str(package_base), *list(botlane.__path__)], raising=False)
    monkeypatch.setattr(
        "botlane.core.workflow_catalog.package_workflows_root",
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
    package_dir = root / ".botlane" / "workflows" / workflow_id
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

from botlane import Workflow, python_step


class {class_name}(Workflow):
    name = "{workflow_name or workflow_id}"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
    (package_dir / "flow.py").write_text(source + "\n", encoding="utf-8")
    return package_dir


def _write_repo_flow(
    root: Path,
    workflow_id: str,
    *,
    workflow_name: str | None = None,
    aliases: tuple[str, ...] = (),
    manifest_text: str | None = None,
    class_name: str = "RepoWorkflow",
    marker: str = "default",
    source: str | None = None,
) -> Path:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    package_dir = workflows_root / workflow_id
    package_dir.mkdir(parents=True, exist_ok=True)
    if manifest_text is None:
        aliases_source = ", ".join(f'"{alias}"' for alias in aliases)
        manifest_lines = [f'name = "{workflow_name or workflow_id}"']
        if aliases:
            manifest_lines.append(f"aliases = [{aliases_source}]")
        manifest_text = "\n".join(manifest_lines) + "\n"
    (package_dir / "workflow.toml").write_text(manifest_text, encoding="utf-8")
    if source is None:
        source = f"""
from __future__ import annotations

from botlane import Workflow, python_step


class {class_name}(Workflow):
    name = "{workflow_name or workflow_id}"
    marker = "{marker}"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
    (package_dir / "workflow.py").write_text(source + "\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text(
        f"from .workflow import {class_name}\n__all__ = ['{class_name}']\n",
        encoding="utf-8",
    )
    return package_dir


def _write_workspace_single_file(root: Path, workflow_id: str, *, class_name: str = "SingleWorkflow") -> Path:
    source_path = root / ".botlane" / "workflows" / f"{workflow_id}.py"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        f"""
from __future__ import annotations

from botlane import Workflow, python_step


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

from botlane import Workflow, python_step


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


def test_workflow_search_roots_include_repo_workspace_and_package_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_root = _configure_package_root(monkeypatch, tmp_path)

    roots = workflow_search_roots(tmp_path)

    assert tuple(root.kind for root in roots) == ("workspace", "workspace", "workspace", "package")
    assert roots[0].path == tmp_path / "workflows"
    assert roots[0].import_prefix == "workflows"
    assert roots[1].path == tmp_path / ".botlane" / "workflows"
    assert roots[2].path == tmp_path / ".autoloop" / "workflows"
    assert roots[3].path == package_root
    assert roots[0].precedence > roots[1].precedence > roots[2].precedence > roots[3].precedence


def test_discover_workflow_catalog_reads_legacy_workspace_root_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_package_root(monkeypatch, tmp_path)
    package_dir = tmp_path / ".autoloop" / "workflows" / "legacy_demo"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "workflow.toml").write_text(
        'name = "legacy_demo"\n'
        'title = "Legacy Demo"\n'
        'description = "legacy workspace workflow"\n',
        encoding="utf-8",
    )
    (package_dir / "flow.py").write_text(
        (
            "from __future__ import annotations\n\n"
            "from botlane import Workflow, python_step\n\n"
            "class LegacyDemo(Workflow):\n"
            '    name = "legacy_demo"\n\n'
            '    @python_step(name="start")\n'
            "    def start(ctx):\n"
            "        return None\n"
        ),
        encoding="utf-8",
    )

    entries = discover_workflow_catalog(tmp_path)

    assert len(entries) == 1
    assert entries[0].workflow_name == "legacy_demo"
    assert entries[0].source_root == tmp_path / ".autoloop" / "workflows"


def test_workflow_resolution_prefers_botlane_workspace_root_over_legacy_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_package_root(monkeypatch, tmp_path)
    _write_workspace_flow(
        tmp_path,
        "shared_demo",
        source="""
from __future__ import annotations

from botlane import Workflow, python_step


class SharedWorkflow(Workflow):
    name = "shared_demo"
    marker = "botlane"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip(),
    )
    legacy_dir = tmp_path / ".autoloop" / "workflows" / "shared_demo"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "workflow.toml").write_text(
        'name = "shared_demo"\n'
        'title = "Shared Demo"\n'
        'description = "legacy workspace workflow"\n',
        encoding="utf-8",
    )
    (legacy_dir / "flow.py").write_text(
        """
from __future__ import annotations

from botlane import Workflow, python_step


class SharedWorkflow(Workflow):
    name = "shared_demo"
    marker = "legacy"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

    resolved = resolve_workflow_reference(tmp_path, "shared_demo")

    assert resolved.workflow_cls.marker == "botlane"
    assert resolved.reference.source_root == tmp_path / ".botlane" / "workflows"


def test_discover_workflow_catalog_allows_missing_search_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_package_root = tmp_path / "installed" / "botlane" / "workflows"
    monkeypatch.setattr(
        "botlane.core.workflow_catalog.package_workflows_root",
        lambda: missing_package_root.resolve(),
    )

    assert discover_workflow_catalog(tmp_path) == ()


def test_discover_workflow_catalog_rejects_non_directory_search_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / ".botlane" / "workflows"
    workspace_root.parent.mkdir(parents=True, exist_ok=True)
    workspace_root.write_text("not a directory\n", encoding="utf-8")
    missing_package_root = tmp_path / "installed" / "botlane" / "workflows"
    monkeypatch.setattr(
        "botlane.core.workflow_catalog.package_workflows_root",
        lambda: missing_package_root.resolve(),
    )

    with pytest.raises(WorkflowCatalogDiscoveryError, match=str(workspace_root)):
        discover_workflow_catalog(tmp_path)


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
    assert entries["package_demo"].package_module == "botlane.workflows.package_demo"
    assert entries["package_demo"].workflow_module == "botlane.workflows.package_demo.flow"
    assert entries["local_demo"].source_root_kind == "workspace"
    assert entries["local_demo"].package_module is None
    assert entries["local_demo"].workflow_module is None
    assert entries["single_demo"].source_root_kind == "workspace"
    assert entries["single_demo"].authoring_shape == "single_file"


def test_distributed_package_catalog_exposes_botlane_v1_and_rejects_autoloop_v1(tmp_path: Path) -> None:
    entries = {entry.workflow_name: entry for entry in discover_workflow_catalog(tmp_path)}
    entry = entries["botlane_v1"]

    assert entry.source_root_kind == "package"
    assert entry.package_module == "botlane.workflows.botlane_v1"
    assert entry.workflow_module == "botlane.workflows.botlane_v1.workflow"
    assert entry.aliases == ("botlane-v1",)

    resolved_by_name = resolve_workflow_reference(tmp_path, "botlane_v1")
    resolved_by_alias = resolve_workflow_reference(tmp_path, "botlane-v1")

    assert resolved_by_name.reference.package_dir == entry.package_dir
    assert resolved_by_name.reference.workflow_module == "botlane.workflows.botlane_v1.workflow"
    assert resolved_by_alias.reference.package_dir == entry.package_dir
    assert resolved_by_alias.reference.workflow_name == "botlane_v1"

    with pytest.raises(WorkflowDiscoveryError, match="unknown workflow 'autoloop_v1'"):
        resolve_workflow_reference(tmp_path, "autoloop_v1")


def test_discover_repo_local_catalog_entries_use_workflows_namespace_defaults_and_repo_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_package_root(monkeypatch, tmp_path)
    package_dir = _write_repo_flow(tmp_path, "repo_demo", aliases=("demo_alias",))
    runtime_test = tmp_path / "tests" / "runtime" / "test_repo_demo.py"
    runtime_test.parent.mkdir(parents=True, exist_ok=True)
    runtime_test.write_text("def test_repo_demo():\n    assert True\n", encoding="utf-8")

    entries = {entry.workflow_name: entry for entry in discover_workflow_catalog(tmp_path)}
    entry = entries["repo_demo"]

    assert entry.source_root_kind == "workspace"
    assert entry.package_dir == package_dir
    assert entry.source_path == package_dir / "workflow.py"
    assert entry.package_module == "workflows.repo_demo"
    assert entry.workflow_module == "workflows.repo_demo.workflow"
    assert entry.title == "Repo Demo"
    assert entry.description == ""
    assert entry.aliases == ("demo_alias",)
    assert entry.test_paths == (runtime_test.resolve(),)


def test_manifest_requires_title_and_description_even_without_aliases(tmp_path: Path) -> None:
    manifest_path = tmp_path / "workflow.toml"
    manifest_path.write_text('name = "demo"\n', encoding="utf-8")

    with pytest.raises(WorkflowCatalogManifestError, match="must define non-empty title, description"):
        read_workflow_manifest(manifest_path)


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


def test_imported_package_class_resolves_shadowed_package_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_root = _configure_package_root(monkeypatch, tmp_path)
    package_dir = _write_package_flow(package_root, "package_demo", workflow_name="shared")
    _write_workspace_flow(tmp_path, "local_demo", workflow_name="shared", manifest=True)

    from botlane.workflows.package_demo.flow import PackageWorkflow

    resolved = resolve_workflow_reference(tmp_path, PackageWorkflow)

    assert resolved.workflow_cls is PackageWorkflow
    assert resolved.reference.source_root_kind == "package"
    assert resolved.reference.package_dir == package_dir
    assert resolved.reference.source_path == package_dir / "flow.py"
    assert resolved.reference.workflow_module == "botlane.workflows.package_demo.flow"


def test_repo_local_module_resolution_evicts_stale_workflows_namespace_between_roots(tmp_path: Path) -> None:
    first_root = tmp_path / "root_one"
    second_root = tmp_path / "root_two"
    _write_repo_flow(first_root, "repo_demo", marker="one")
    _write_repo_flow(second_root, "repo_demo", marker="two")

    first = resolve_workflow_reference(first_root, "repo_demo")
    second = resolve_workflow_reference(second_root, "repo_demo")

    assert first.reference.package_module == "workflows.repo_demo"
    assert second.reference.package_module == "workflows.repo_demo"
    assert first.reference.source_path == first_root / "workflows" / "repo_demo" / "workflow.py"
    assert second.reference.source_path == second_root / "workflows" / "repo_demo" / "workflow.py"
    assert first.workflow_cls.marker == "one"
    assert second.workflow_cls.marker == "two"
    assert second.workflow_cls is not first.workflow_cls


def test_repo_local_unique_alias_remains_resolvable_when_workspace_claims_workflow_name(tmp_path: Path) -> None:
    _write_workspace_flow(tmp_path, "shared_demo", workflow_name="shared_demo", manifest=True)
    repo_dir = _write_repo_flow(tmp_path, "shared_demo", workflow_name="shared_demo", aliases=("repo-only",))

    resolved = resolve_workflow_reference(tmp_path, "repo-only")

    assert resolved.reference.package_dir == repo_dir
    assert resolved.reference.source_path == repo_dir / "workflow.py"
    assert resolved.reference.workflow_name == "shared_demo"
    assert resolved.reference.package_module == "workflows.shared_demo"
    assert resolved.workflow_cls.__module__ == "workflows.shared_demo.workflow"


def test_named_repo_local_class_round_trip_preserves_repo_module_namespace_when_name_is_shadowed(tmp_path: Path) -> None:
    _write_workspace_flow(tmp_path, "shared_demo", workflow_name="shared_demo", manifest=True)
    repo_dir = _write_repo_flow(tmp_path, "shared_demo", workflow_name="shared_demo", aliases=("repo-only",))

    resolved_by_alias = resolve_workflow_reference(tmp_path, "repo-only")
    resolved_by_class = resolve_workflow_reference(tmp_path, resolved_by_alias.workflow_cls)

    assert resolved_by_alias.workflow_cls is resolved_by_class.workflow_cls
    assert resolved_by_class.reference.package_dir == repo_dir
    assert resolved_by_class.reference.package_module == "workflows.shared_demo"
    assert resolved_by_class.reference.workflow_module == "workflows.shared_demo.workflow"
    assert resolved_by_class.workflow_cls.__module__ == "workflows.shared_demo.workflow"


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
    assert str(tmp_path / ".botlane" / "workflows") in message
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

from botlane import Workflow, python_step


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
    package_dir = tmp_path / ".botlane" / "workflows" / "relative_demo"
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

from botlane import Workflow, python_step

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
    assert resolved.workflow_cls.__module__.startswith("_botlane_workspace_workflows.")
    assert resolved.workflow_cls.__module__.endswith(".relative_demo.flow")


def test_manifest_class_field_selects_specific_workflow_class(tmp_path: Path) -> None:
    package_dir = tmp_path / ".botlane" / "workflows" / "classed"
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

from botlane import Workflow, python_step


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


def test_manifest_module_field_selects_declared_module(tmp_path: Path) -> None:
    package_dir = tmp_path / ".botlane" / "workflows" / "module_override"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "workflow.toml").write_text(
        'name = "module_override"\n'
        'title = "Module Override"\n'
        'description = "manifest module selector"\n'
        'module = "impl"\n',
        encoding="utf-8",
    )
    (package_dir / "flow.py").write_text(
        """
from __future__ import annotations

from botlane import Workflow, python_step


class WrongWorkflow(Workflow):
    name = "wrong"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "impl.py").write_text(
        """
from __future__ import annotations

from botlane import Workflow, python_step


class ModuleOverrideWorkflow(Workflow):
    name = "module_override"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

    resolved = resolve_workflow_reference(tmp_path, "module_override")

    assert resolved.workflow_cls.__name__ == "ModuleOverrideWorkflow"
    assert resolved.reference.source_path == package_dir / "impl.py"


def test_manifest_without_module_falls_back_to_workflow_py_when_flow_missing(tmp_path: Path) -> None:
    package_dir = tmp_path / ".botlane" / "workflows" / "workflow_only"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "workflow.toml").write_text(
        'name = "workflow_only"\n'
        'title = "Workflow Only"\n'
        'description = "workflow fallback"\n',
        encoding="utf-8",
    )
    (package_dir / "workflow.py").write_text(
        """
from __future__ import annotations

from botlane import Workflow, python_step


class WorkflowOnly(Workflow):
    name = "workflow_only"

    @python_step(name="start")
    def start(ctx):
        return None
""".strip()
        + "\n",
        encoding="utf-8",
    )

    resolved = resolve_workflow_reference(tmp_path, "workflow_only")

    assert resolved.workflow_cls.__name__ == "WorkflowOnly"
    assert resolved.reference.source_path == package_dir / "workflow.py"


def test_manifest_without_class_rejects_multiple_workflow_classes(tmp_path: Path) -> None:
    package_dir = _write_workspace_flow(
        tmp_path,
        "ambiguous",
        manifest=True,
        source="""
from __future__ import annotations

from botlane import Workflow, python_step


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
