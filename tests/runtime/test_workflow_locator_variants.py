from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

from botpipe.runtime.loader import resolve_workflow_reference
from botpipe.runtime.workflow_locator import (
    CatalogWorkflowLocator,
    PythonFileWorkflowLocator,
    PythonModuleWorkflowLocator,
    WorkflowDirectoryLocator,
    resolve_workflow_locator,
    workflow_locator_from_resolved,
)


def _clear_workflow_modules() -> None:
    importlib.invalidate_caches()
    for name in list(sys.modules):
        if (
            name == "workflows"
            or name.startswith("workflows.")
            or name == "_botpipe_workspace_workflows"
            or name.startswith("_botpipe_workspace_workflows.")
        ):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_modules():
    _clear_workflow_modules()
    yield
    _clear_workflow_modules()


def _write_catalog_flow(root: Path, workflow_id: str, *, class_name: str = "CatalogWorkflow") -> Path:
    package_dir = root / ".botpipe" / "workflows" / workflow_id
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "workflow.toml").write_text(
        f'name = "{workflow_id}"\n'
        f'title = "{workflow_id.title()}"\n'
        'description = "catalog workflow"\n',
        encoding="utf-8",
    )
    (package_dir / "flow.py").write_text(
        (
            "from __future__ import annotations\n\n"
            "from botpipe import Workflow, python_step\n\n"
            f"class {class_name}(Workflow):\n"
            f'    name = "{workflow_id}"\n\n'
            '    @python_step(name="start")\n'
            "    def start(ctx):\n"
            "        return None\n"
        ),
        encoding="utf-8",
    )
    return package_dir


def _write_single_file(root: Path, relative_path: str, *, workflow_name: str, class_name: str) -> Path:
    source_path = root / relative_path
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        (
            "from __future__ import annotations\n\n"
            "from botpipe import Workflow, python_step\n\n"
            f"class {class_name}(Workflow):\n"
            f'    name = "{workflow_name}"\n\n'
            '    @python_step(name="start")\n'
            "    def start(ctx):\n"
            "        return None\n"
        ),
        encoding="utf-8",
    )
    return source_path


def _write_repo_module(root: Path, workflow_id: str, *, class_name: str) -> str:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    package_dir = workflows_root / workflow_id
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (package_dir / "workflow.py").write_text(
        (
            "from __future__ import annotations\n\n"
            "from botpipe import Workflow, python_step\n\n"
            f"class {class_name}(Workflow):\n"
            f'    name = "{workflow_id}"\n\n'
            '    @python_step(name="start")\n'
            "    def start(ctx):\n"
            "        return None\n"
        ),
        encoding="utf-8",
    )
    return f"workflows.{workflow_id}.workflow"


def _assert_same_resolution(left, right) -> None:
    assert left.workflow_cls.__name__ == right.workflow_cls.__name__
    assert left.reference.workflow_name == right.reference.workflow_name
    assert left.reference.kind == right.reference.kind
    assert left.reference.source_path == right.reference.source_path


def test_catalog_workflow_locator_resolves_like_named_reference(tmp_path: Path) -> None:
    _write_catalog_flow(tmp_path, "release_review", class_name="ReleaseReviewWorkflow")

    direct = resolve_workflow_reference(tmp_path, "release_review")
    locator = workflow_locator_from_resolved(direct)
    resolved = resolve_workflow_locator(tmp_path, locator)

    assert locator == CatalogWorkflowLocator(workflow_id="release_review")
    _assert_same_resolution(resolved, direct)


def test_python_file_workflow_locator_resolves_like_file_reference(tmp_path: Path) -> None:
    workflow_path = _write_single_file(
        tmp_path,
        "examples/file_review.py",
        workflow_name="file_review",
        class_name="FileReviewWorkflow",
    )

    direct = resolve_workflow_reference(tmp_path, "examples/file_review.py:FileReviewWorkflow")
    locator = PythonFileWorkflowLocator(path=workflow_path, class_name="FileReviewWorkflow")
    resolved = resolve_workflow_locator(tmp_path, locator)

    _assert_same_resolution(resolved, direct)


def test_python_module_workflow_locator_resolves_like_module_reference(tmp_path: Path) -> None:
    module_name = _write_repo_module(tmp_path, "module_review", class_name="ModuleReviewWorkflow")

    direct = resolve_workflow_reference(tmp_path, f"{module_name}:ModuleReviewWorkflow")
    locator = PythonModuleWorkflowLocator(module=module_name, class_name="ModuleReviewWorkflow")
    resolved = resolve_workflow_locator(tmp_path, locator)

    _assert_same_resolution(resolved, direct)


def test_workflow_directory_locator_resolves_like_directory_reference(tmp_path: Path) -> None:
    directory = tmp_path / "external_review"
    _write_single_file(
        directory,
        "flow.py",
        workflow_name="external_review",
        class_name="ExternalReviewWorkflow",
    )

    direct = resolve_workflow_reference(tmp_path, str(directory))
    locator = WorkflowDirectoryLocator(path=directory)
    resolved = resolve_workflow_locator(tmp_path, locator)

    _assert_same_resolution(resolved, direct)


def test_invalid_workflow_locator_fails_clearly(tmp_path: Path) -> None:
    locator = PythonFileWorkflowLocator(path=tmp_path / "missing.py", class_name="MissingWorkflow")

    with pytest.raises(FileNotFoundError, match="does not exist"):
        resolve_workflow_locator(tmp_path, locator)


def test_workflow_locator_from_resolved_rejects_workflow_class_kind(tmp_path: Path) -> None:
    workflow_path = _write_single_file(
        tmp_path,
        "ad_hoc/class_review.py",
        workflow_name="class_review",
        class_name="ClassReviewWorkflow",
    )
    spec = importlib.util.spec_from_file_location("adhoc_class_review", workflow_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    try:
        spec.loader.exec_module(module)
        workflow_cls = module.ClassReviewWorkflow

        resolved = resolve_workflow_reference(tmp_path, workflow_cls)

        assert resolved.reference.kind == "workflow_class"
        with pytest.raises(ValueError, match="does not have a locator variant"):
            workflow_locator_from_resolved(resolved)
    finally:
        sys.modules.pop(module.__name__, None)
