"""Isolated materialization and validation for generated workflow packages."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from botpipe import ArtifactHandle, activity


@activity(retry_safe=True, name="prepare generated workflow candidate")
def prepare_generated_workflow_candidate(
    repository: str,
    destination: str,
    package_name: str,
    authoring_shape: str,
):
    """Create a run-owned edit surface for the requested authoring shape."""
    from botpipe_optimizer import prepare_candidate_workspace

    repo = Path(repository).resolve()
    package_path = _generated_package_path(package_name, authoring_shape)
    test_path = f"tests/runtime/test_{package_name}.py"
    requested = []
    for relative in (package_path, test_path):
        source = repo / relative
        if source.is_symlink():
            raise ValueError(f"generated workflow target is a symlink: {relative}")
        if source.exists():
            if relative.startswith(".botpipe/"):
                raise ValueError(
                    f"generated workflow target already exists; choose a new package_name: {relative}"
                )
            requested.append(relative)
    if not requested:
        anchors = [
            path
            for path in (
                repo / "pyproject.toml",
                repo / "README.md",
                repo / "labs" / "workflows" / "__init__.py",
            )
            if path.is_file() and not path.is_symlink()
        ]
        if not anchors:
            raise FileNotFoundError(
                "generated workflow validation requires one existing repository file"
            )
        requested.append(anchors[0].relative_to(repo).as_posix())
    candidate = prepare_candidate_workspace(
        repo,
        requested,
        destination,
    )
    generated_root = (
        str(Path(package_path).parent) if authoring_shape == "single" else package_path
    )
    return replace(
        candidate,
        allowed_roots=tuple(
            sorted({*candidate.allowed_roots, generated_root, "tests/runtime"})
        ),
    )


def _generated_package_path(package_name: str, authoring_shape: str) -> str:
    if authoring_shape == "single":
        return f".botpipe/workflows/{package_name}.py"
    if authoring_shape == "flow_specs":
        return f".botpipe/workflows/{package_name}"
    if authoring_shape == "package":
        return f"labs/workflows/{package_name}"
    raise ValueError(
        f"unsupported generated workflow authoring shape: {authoring_shape}"
    )


def _generated_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("generated file path must be a non-empty string")
    path = Path(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or "__pycache__" in path.parts
        or path.parts[0] == ".git"
        or (path.parts[0] == ".botpipe" and path.parts[:2] != (".botpipe", "workflows"))
    ):
        raise ValueError(f"generated file path must stay repo-relative: {value}")
    return path.as_posix()


@activity(retry_safe=True, name="materialize generated workflow manifest")
def _materialize_generated_workflow_manifest_activity(
    candidate_workspace: Any,
    manifest_handle: ArtifactHandle,
    package_name: str,
    authoring_shape: str,
    *,
    max_files: int = 128,
    max_bytes: int = 2 * 1024 * 1024,
) -> dict[str, Any]:
    """Validate and materialize one complete content manifest in the candidate root."""
    try:
        manifest = json.loads(manifest_handle.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "workflow_package_manifest must contain a JSON object"
        ) from exc
    if not isinstance(manifest, Mapping):
        raise TypeError("workflow_package_manifest must contain a JSON object")
    if manifest.get("package_name") != package_name:
        raise ValueError("workflow_package_manifest package_name must match parameters")
    if manifest.get("authoring_shape") != authoring_shape:
        raise ValueError(
            "workflow_package_manifest authoring_shape must match parameters"
        )
    workflow_reference = manifest.get("workflow_reference")
    if not isinstance(workflow_reference, str) or not workflow_reference.strip():
        raise ValueError("workflow_package_manifest requires workflow_reference")
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise ValueError("workflow_package_manifest requires a non-empty files array")
    if len(raw_files) > max_files:
        raise ValueError(f"workflow package exceeds max_files={max_files}")

    package_prefix = _generated_package_path(package_name, authoring_shape)
    single_path = package_prefix
    test_path = f"tests/runtime/test_{package_name}.py"
    records: list[tuple[str, bytes, str]] = []
    seen: set[str] = set()
    total = 0
    for item in raw_files:
        if not isinstance(item, Mapping):
            raise TypeError("workflow_package_manifest file entries must be objects")
        relative = _generated_relative_path(item.get("path"))
        if relative in seen:
            raise ValueError(f"duplicate generated file path: {relative}")
        allowed = (
            relative == single_path
            if authoring_shape == "single"
            else Path(relative).is_relative_to(package_prefix)
        ) or relative == test_path
        if not allowed:
            raise ValueError(
                f"generated file is outside the package boundary: {relative}"
            )
        content = item.get("content")
        if not isinstance(content, str):
            raise TypeError(f"generated file content must be text: {relative}")
        data = content.encode("utf-8")
        if relative.endswith(".py"):
            compile(content, relative, "exec")
        total += len(data)
        if total > max_bytes:
            raise ValueError(f"workflow package exceeds max_bytes={max_bytes}")
        role = item.get("role", "source")
        if not isinstance(role, str) or not role:
            raise TypeError(f"generated file role must be text: {relative}")
        if not isinstance(item.get("purpose"), str) or not item["purpose"].strip():
            raise TypeError(f"generated file purpose must be text: {relative}")
        if not isinstance(item.get("required"), bool):
            raise TypeError(f"generated file required flag must be boolean: {relative}")
        if (
            not isinstance(item.get("implements"), str)
            or not item["implements"].strip()
        ):
            raise TypeError(f"generated file implements must be text: {relative}")
        seen.add(relative)
        records.append((relative, data, role))
    if authoring_shape == "single":
        if single_path not in seen:
            raise ValueError(f"single-file package requires {single_path}")
    elif authoring_shape == "flow_specs" and f"{package_prefix}/flow.py" not in seen:
        raise ValueError("flow_specs authoring shape requires flow.py")
    elif authoring_shape == "package":
        required = {
            f"{package_prefix}/flow.py",
            f"{package_prefix}/specs.py",
            f"{package_prefix}/workflow.toml",
        }
        missing = sorted(required - seen)
        if missing:
            raise ValueError("package authoring shape requires: " + ", ".join(missing))

    root = Path(candidate_workspace.root).resolve()
    marker = root / ".botpipe-candidate.json"
    if not marker.is_file():
        raise ValueError("candidate workspace ownership marker is missing")
    candidate_root = Path(candidate_workspace.candidate_root).resolve()
    baseline_root = Path(candidate_workspace.baseline_root).resolve()
    if not candidate_root.is_relative_to(root) or not baseline_root.is_relative_to(
        root
    ):
        raise ValueError("candidate workspace roots escape the managed root")
    if candidate_root.exists():
        shutil.rmtree(candidate_root)
    shutil.copytree(baseline_root, candidate_root)

    materialized = []
    for relative, data, role in records:
        target = candidate_root / relative
        if any(
            parent.is_symlink()
            for parent in target.parents
            if parent != candidate_root.parent
        ):
            raise ValueError(f"generated file parent contains a symlink: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not target.is_file():
            raise ValueError(f"generated file target is not ordinary: {relative}")
        target.write_bytes(data)
        materialized.append(
            {
                "path": relative,
                "role": role,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
        )
    return {
        "schema": "botpipe.generated-workflow-candidate/v1",
        "package_name": package_name,
        "authoring_shape": authoring_shape,
        "workflow_reference": workflow_reference.strip(),
        "root": str(candidate_root),
        "manifest_artifact": manifest_handle.to_record(),
        "files": materialized,
        "compiled_python_paths": [
            record["path"] for record in materialized if record["path"].endswith(".py")
        ],
    }


def _revalidate_generated_workflow_materialization(
    result: Mapping[str, Any],
    *,
    candidate_workspace: Any,
    manifest_handle: ArtifactHandle,
) -> dict[str, Any]:
    """Bind cached materialization output to current immutable and candidate bytes."""
    from botpipe_optimizer.candidates import (
        candidate_manifest,
        validate_authoritative_sources_unchanged,
    )

    value = dict(result)
    if value.get("manifest_artifact") != manifest_handle.to_record():
        raise ValueError(
            "generated candidate is bound to a different manifest artifact"
        )
    raw = json.loads(manifest_handle.read_bytes())
    if not isinstance(raw, Mapping):
        raise TypeError("workflow_package_manifest must contain a JSON object")
    files = value.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("generated candidate record requires files")
    declared = raw.get("files")
    if not isinstance(declared, list) or len(declared) != len(files):
        raise ValueError("generated candidate file inventory differs from its manifest")
    expected = []
    for item in declared:
        if not isinstance(item, Mapping) or not isinstance(item.get("content"), str):
            raise TypeError(
                "generated candidate manifest no longer has complete content"
            )
        relative = _generated_relative_path(item.get("path"))
        data = item["content"].encode("utf-8")
        expected.append(
            {
                "path": relative,
                "role": item.get("role", "source"),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
        )
    if files != expected:
        raise ValueError("generated candidate record differs from manifest content")
    compiled = [item["path"] for item in expected if item["path"].endswith(".py")]
    if value.get("compiled_python_paths") != compiled:
        raise ValueError("generated candidate compile record differs from its manifest")
    root = Path(candidate_workspace.candidate_root).resolve()
    if value.get("root") != str(root):
        raise ValueError("generated candidate root changed")
    for record in files:
        path = root / record["path"]
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"generated candidate file is missing: {record['path']}")
        data = path.read_bytes()
        if (
            len(data) != record["size_bytes"]
            or hashlib.sha256(data).hexdigest() != record["sha256"]
        ):
            raise ValueError(f"generated candidate file changed: {record['path']}")
    validate_authoritative_sources_unchanged(candidate_workspace)
    actual = candidate_manifest(candidate_workspace)
    if set(actual.changed_paths) != {record["path"] for record in files}:
        raise ValueError("generated candidate contains unrecorded file changes")
    return value


def materialize_generated_workflow_manifest(
    candidate_workspace: Any,
    manifest_handle: ArtifactHandle,
    package_name: str,
    authoring_shape: str,
    *,
    max_files: int = 128,
    max_bytes: int = 2 * 1024 * 1024,
) -> dict[str, Any]:
    """Materialize once and verify immutable manifest/source identity on replay."""
    result = _materialize_generated_workflow_manifest_activity(
        candidate_workspace,
        manifest_handle,
        package_name,
        authoring_shape,
        max_files=max_files,
        max_bytes=max_bytes,
    )
    return _revalidate_generated_workflow_materialization(
        result,
        candidate_workspace=candidate_workspace,
        manifest_handle=manifest_handle,
    )


@activity(retry_safe=True, name="freeze generated workflow baseline")
def freeze_generated_workflow_candidate(candidate_workspace: Any, staging_parent: str):
    """Freeze the authoritative repository before materializing generated files."""
    from botpipe_optimizer.candidates import freeze_candidate_workspace

    return freeze_candidate_workspace(
        candidate_workspace,
        Path(staging_parent),
        boundary={
            "editable_paths": list(candidate_workspace.allowed_paths),
            "editable_roots": list(candidate_workspace.allowed_roots),
        },
        execution_source_root=Path(candidate_workspace.repo_root),
    )


@activity(name="validate generated workflow candidate")
def _validate_generated_workflow_candidate_activity(
    candidate_workspace: Any,
    frozen_candidate: Any,
    workflow_reference: str,
    staging_parent: str,
    target_test_command: str | None,
    timeout: float = 300,
) -> dict[str, Any]:
    """Compile/import one materialized candidate with the existing isolated validator."""
    from botpipe_optimizer.candidates import (
        candidate_manifest,
        candidate_surface_manifest,
        validate_candidate,
    )

    result = validate_candidate(
        candidate_workspace,
        frozen_candidate,
        workflow_refs=(workflow_reference,),
        staging_parent=Path(staging_parent),
        target_test_command=target_test_command,
        compile_timeout_seconds=min(timeout, 60),
        test_timeout_seconds=timeout,
    )
    if not result.success:
        raise ValueError(
            f"generated workflow validation failed: {'; '.join(result.errors)}"
        )
    manifest = candidate_manifest(candidate_workspace)
    surface = candidate_surface_manifest(candidate_workspace, frozen_candidate)
    changed_files = {
        item["relative_path"]: item
        for item in surface["files"]
        if item["relative_path"] in manifest.changed_paths
    }
    for compiled in result.compiled_workflows:
        matches = [
            relative
            for relative, item in changed_files.items()
            if compiled["source_sha256"] == item["surface_sha256"]
            and Path(compiled["source_path"]).as_posix().endswith(f"/{relative}")
        ]
        if len(matches) != 1:
            raise ValueError(
                "workflow_reference must resolve to one generated candidate source"
            )
    return {
        "validation": result.model_dump(mode="json"),
        "candidate_manifest": {
            "schema": "botpipe.generated-workflow-file-manifest/v1",
            "root": str(Path(candidate_workspace.candidate_root).resolve()),
            "surface_id": surface["surface_id"],
            "files": [
                {
                    "path": item["relative_path"],
                    "sha256": item["surface_sha256"],
                    "size_bytes": item["size_bytes"],
                }
                for item in surface["files"]
                if item["relative_path"] in manifest.changed_paths
            ],
            "changed_paths": list(manifest.changed_paths),
            "added_paths": list(manifest.added_paths),
            "removed_paths": list(manifest.removed_paths),
        },
    }


def _revalidate_generated_workflow_validation(
    result: Mapping[str, Any],
    *,
    candidate_workspace: Any,
    frozen_candidate: Any,
) -> dict[str, Any]:
    """Recheck a cached validation result against current candidate bytes."""
    from botpipe_optimizer.candidates import (
        candidate_manifest,
        candidate_surface_manifest,
    )

    value = dict(result)
    validation = value.get("validation")
    recorded = value.get("candidate_manifest")
    if not isinstance(validation, Mapping) or validation.get("success") is not True:
        raise ValueError("generated workflow validation is not successful")
    if not isinstance(recorded, Mapping):
        raise TypeError("generated workflow candidate manifest is missing")
    root = Path(candidate_workspace.candidate_root).resolve()
    if validation.get("validated_root") != str(root) or recorded.get("root") != str(
        root
    ):
        raise ValueError("generated workflow validation root changed")
    manifest = candidate_manifest(candidate_workspace)
    surface = candidate_surface_manifest(candidate_workspace, frozen_candidate)
    changed = list(manifest.changed_paths)
    files = [
        {
            "path": item["relative_path"],
            "sha256": item["surface_sha256"],
            "size_bytes": item["size_bytes"],
        }
        for item in surface["files"]
        if item["relative_path"] in manifest.changed_paths
    ]
    expected = {
        "schema": "botpipe.generated-workflow-file-manifest/v1",
        "root": str(root),
        "surface_id": surface["surface_id"],
        "files": files,
        "changed_paths": changed,
        "added_paths": list(manifest.added_paths),
        "removed_paths": list(manifest.removed_paths),
    }
    if dict(recorded) != expected:
        raise ValueError("generated workflow candidate changed after validation")
    if (
        validation.get("candidate_surface_id") != surface["surface_id"]
        or validation.get("derived_changes") != changed
    ):
        raise ValueError("generated workflow validation no longer matches its source")
    return value


def validate_generated_workflow_candidate(
    candidate_workspace: Any,
    frozen_candidate: Any,
    workflow_reference: str,
    staging_parent: str,
    target_test_command: str | None,
    timeout: float = 300,
) -> dict[str, Any]:
    """Validate once and recheck source identity after every activity replay."""
    result = _validate_generated_workflow_candidate_activity(
        candidate_workspace,
        frozen_candidate,
        workflow_reference,
        staging_parent,
        target_test_command,
        timeout,
    )
    return _revalidate_generated_workflow_validation(
        result,
        candidate_workspace=candidate_workspace,
        frozen_candidate=frozen_candidate,
    )


__all__ = [
    "freeze_generated_workflow_candidate",
    "materialize_generated_workflow_manifest",
    "prepare_generated_workflow_candidate",
    "validate_generated_workflow_candidate",
]
