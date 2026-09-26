"""Isolated materialization and validation for generated workflow packages."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from botpipe import ArtifactHandle, activity


class WorkflowManifestValidationError(ValueError):
    """The provider-authored manifest is malformed and can be repaired."""


@activity(retry_safe=True, name="prepare generated workflow candidate")
def prepare_generated_workflow_candidate(
    repository: str,
    destination: str,
    package_name: str,
):
    """Create a run-owned edit surface for one workspace workflow package."""
    from botpipe_optimizer import prepare_candidate_workspace

    repo = Path(repository).resolve()
    package_path = _generated_package_path(package_name)
    test_path = f"tests/runtime/test_{package_name}.py"
    requested = []
    for relative in (package_path, test_path):
        source = repo / relative
        if source.is_symlink():
            raise ValueError(f"generated workflow target is a symlink: {relative}")
        if source.exists():
            raise ValueError(
                "generated workflow target already exists; choose a new "
                f"package_name: {relative}"
            )
    anchors = [
        path
        for path in (
            repo / "pyproject.toml",
            repo / "README.md",
            repo / "labs" / "workflows" / "__init__.py",
        )
        if path.is_file() and not path.is_symlink()
    ]
    if anchors:
        requested.append(anchors[0].relative_to(repo).as_posix())
        candidate = prepare_candidate_workspace(repo, requested, destination)
    else:
        candidate = _prepare_empty_generated_candidate(repo, Path(destination))
    return replace(
        candidate,
        allowed_roots=tuple(sorted({*candidate.allowed_roots, package_path})),
        allowed_added_paths=(test_path,),
    )


def _prepare_empty_generated_candidate(repo: Path, destination: Path):
    """Create the optimizer-owned shape when authoring starts without an anchor."""
    from botpipe_optimizer.candidates import (
        CandidateWorkspace,
        _reject_symlink_alias,
        _reset_managed_root,
    )

    if not repo.is_dir():
        raise FileNotFoundError(f"repository root does not exist: {repo}")
    destination = destination.expanduser()
    _reject_symlink_alias(destination)
    root = destination.resolve()
    if root == repo or repo.is_relative_to(root):
        raise ValueError(
            "candidate destination must not be the repository or its ancestor"
        )
    _reset_managed_root(root)
    marker = {
        "managed_by": "botpipe-candidate-v1",
        "repo_root": str(repo),
        "requested_paths": [],
        "allowed_paths": [],
        "allowed_roots": [],
        "authoritative_hashes": {},
    }
    (root / ".botpipe-candidate.json").write_text(
        json.dumps(marker, sort_keys=True), encoding="utf-8"
    )
    baseline = root / "baseline"
    candidate = root / "candidate"
    baseline.mkdir()
    candidate.mkdir()
    return CandidateWorkspace(repo, root, baseline, candidate, (), (), {})


def _generated_package_path(package_name: str) -> str:
    if (
        not isinstance(package_name, str)
        or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", package_name) is None
    ):
        raise ValueError("package_name must be a Python-style identifier")
    return f".botpipe/workflows/{package_name}"


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
    *,
    max_files: int = 128,
    max_bytes: int = 2 * 1024 * 1024,
) -> dict[str, Any]:
    """Validate and materialize one complete content manifest in the candidate root."""
    try:
        manifest = json.loads(manifest_handle.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkflowManifestValidationError(
            "workflow_package_manifest must contain a JSON object"
        ) from exc
    if not isinstance(manifest, Mapping):
        raise WorkflowManifestValidationError(
            "workflow_package_manifest must contain a JSON object"
        )
    if manifest.get("package_name") != package_name:
        raise WorkflowManifestValidationError(
            "workflow_package_manifest package_name must match parameters"
        )
    workflow_reference = manifest.get("workflow_reference")
    if not isinstance(workflow_reference, str) or not workflow_reference.strip():
        raise WorkflowManifestValidationError(
            "workflow_package_manifest requires workflow_reference"
        )
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise WorkflowManifestValidationError(
            "workflow_package_manifest requires a non-empty files array"
        )
    if len(raw_files) > max_files:
        raise WorkflowManifestValidationError(
            f"workflow package exceeds max_files={max_files}"
        )

    package_prefix = _generated_package_path(package_name)
    test_path = f"tests/runtime/test_{package_name}.py"
    records: list[tuple[str, bytes, str]] = []
    seen: set[str] = set()
    total = 0
    for item in raw_files:
        if not isinstance(item, Mapping):
            raise WorkflowManifestValidationError(
                "workflow_package_manifest file entries must be objects"
            )
        try:
            relative = _generated_relative_path(item.get("path"))
        except ValueError as exc:
            raise WorkflowManifestValidationError(str(exc)) from exc
        if relative in seen:
            raise WorkflowManifestValidationError(
                f"duplicate generated file path: {relative}"
            )
        allowed = Path(relative).is_relative_to(package_prefix) or relative == test_path
        if not allowed:
            raise WorkflowManifestValidationError(
                f"generated file is outside the package boundary: {relative}"
            )
        content = item.get("content")
        if not isinstance(content, str):
            raise WorkflowManifestValidationError(
                f"generated file content must be text: {relative}"
            )
        data = content.encode("utf-8")
        total += len(data)
        if total > max_bytes:
            raise WorkflowManifestValidationError(
                f"workflow package exceeds max_bytes={max_bytes}"
            )
        role = item.get("role", "source")
        if not isinstance(role, str) or not role:
            raise WorkflowManifestValidationError(
                f"generated file role must be text: {relative}"
            )
        seen.add(relative)
        records.append((relative, data, role))
    # A manifest declares files, so no declared file may also be a directory
    # for another entry. Check the whole inventory before touching candidate bytes.
    for relative in sorted(seen):
        for parent in Path(relative).parents:
            if parent.as_posix() in seen:
                raise WorkflowManifestValidationError(
                    f"generated file paths conflict: {parent.as_posix()} and {relative}"
                )
    required = {
        f"{package_prefix}/flow.py",
        f"{package_prefix}/workflow.toml",
    }
    missing = sorted(required - seen)
    if missing:
        raise WorkflowManifestValidationError(
            "workflow package requires: " + ", ".join(missing)
        )

    entry_path = f"{package_prefix}/flow.py"
    reference_errors: list[str] = []
    if ":" not in workflow_reference:
        reference_errors.append(
            "workflow_reference must name a callable in the generated entry file"
        )
        function_name = "workflow_callable"
    else:
        declared_location, function_name = workflow_reference.rsplit(":", 1)
        function_name = function_name.strip()
        try:
            declared_location = _generated_relative_path(declared_location.strip())
        except (TypeError, ValueError) as exc:
            reference_errors.append(str(exc))
            declared_location = ""
        if declared_location != entry_path:
            reference_errors.append(
                f"workflow_reference must target the generated entry file {entry_path}"
            )
        if not function_name.isidentifier():
            reference_errors.append(
                "workflow_reference must name a valid Python callable"
            )
            function_name = "workflow_callable"
    derived_reference = f"{entry_path}:{function_name}"

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

    # The content manifest is the desired final inventory for its managed
    # boundary.  Clear only that boundary so undeclared files from an existing
    # package cannot remain as hidden dependencies.  The rest of the repository
    # is left byte-for-byte as prepared from the baseline.
    managed_package = candidate_root / package_prefix
    if managed_package.exists():
        if managed_package.is_symlink() or not managed_package.is_dir():
            raise ValueError("generated package boundary is not an ordinary directory")
        shutil.rmtree(managed_package)
    managed_test = candidate_root / test_path
    if managed_test.exists():
        if managed_test.is_symlink() or not managed_test.is_file():
            raise ValueError("generated test boundary is not an ordinary file")
        managed_test.unlink()

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
        "workflow_reference": derived_reference,
        "declared_workflow_reference": workflow_reference.strip(),
        "reference_errors": reference_errors,
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
    package_name = value.get("package_name")
    if not isinstance(package_name, str):
        raise TypeError("generated candidate package identity is missing")
    package_prefix = _generated_package_path(package_name)
    test_path = f"tests/runtime/test_{package_name}.py"
    declared_paths = {record["path"] for record in files}
    if (root / package_prefix).is_dir():
        actual_package_paths = {
            path.relative_to(root).as_posix()
            for path in (root / package_prefix).rglob("*")
            if path.is_file() and not path.is_symlink()
        }
    else:
        actual_package_paths = set()
    declared_package_paths = {
        path
        for path in declared_paths
        if path == package_prefix or Path(path).is_relative_to(package_prefix)
    }
    if actual_package_paths != declared_package_paths:
        raise ValueError("generated package inventory differs from its manifest")
    if (root / test_path).is_file() != (test_path in declared_paths):
        raise ValueError("generated test inventory differs from its manifest")
    unexpected_changes = [
        path
        for path in actual.changed_paths
        if path != test_path
        and path != package_prefix
        and not Path(path).is_relative_to(package_prefix)
    ]
    if unexpected_changes:
        raise ValueError("generated candidate contains changes outside its boundary")
    return value


def materialize_generated_workflow_manifest(
    candidate_workspace: Any,
    manifest_handle: ArtifactHandle,
    package_name: str,
    *,
    max_files: int = 128,
    max_bytes: int = 2 * 1024 * 1024,
) -> dict[str, Any]:
    """Materialize once and verify immutable manifest/source identity on replay."""
    result = _materialize_generated_workflow_manifest_activity(
        candidate_workspace,
        manifest_handle,
        package_name,
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
    manifest_diagnostics: Sequence[str] = (),
    *,
    target_test_argv: Sequence[str] | None = None,
    enforce_generated_test: bool = False,
) -> dict[str, Any]:
    """Compile and import a candidate with the existing isolated validator."""
    from botpipe_optimizer.candidates import (
        candidate_manifest,
        candidate_surface_manifest,
        validate_candidate,
    )

    package_entry = Path(workflow_reference.rsplit(":", 1)[0]).as_posix()
    parts = Path(package_entry).parts
    diagnostics = list(manifest_diagnostics)
    effective_test_argv = target_test_argv
    if enforce_generated_test:
        if parts[:2] == (".botpipe", "workflows") and len(parts) == 4:
            focused_test = f"tests/runtime/test_{parts[2]}.py"
            if not (Path(candidate_workspace.candidate_root) / focused_test).is_file():
                diagnostics.append(
                    f"generated behavioral test is required: {focused_test}"
                )
            elif target_test_command is None and target_test_argv is None:
                effective_test_argv = (
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    focused_test,
                )
        else:
            diagnostics.append(
                "generated behavioral test cannot be selected from workflow_reference"
            )

    result = validate_candidate(
        candidate_workspace,
        frozen_candidate,
        workflow_refs=(workflow_reference,),
        staging_parent=Path(staging_parent),
        target_test_argv=effective_test_argv,
        target_test_command=target_test_command,
        compile_timeout_seconds=min(timeout, 60),
        test_timeout_seconds=timeout,
    )
    if any(check.cancelled for check in result.checks):
        raise RuntimeError("generated workflow validation was cancelled")

    diagnostics.extend(result.errors)

    candidate_root = Path(candidate_workspace.candidate_root)
    allowed_entries = {
        path.relative_to(candidate_root).as_posix()
        for path in candidate_root.glob(".botpipe/workflows/*/flow.py")
        if path.is_file() and not path.is_symlink()
    }
    if package_entry not in allowed_entries:
        diagnostics.append(
            "workflow_reference must select the generated package flow.py"
        )
    if parts[:2] == (".botpipe", "workflows") and len(parts) == 4:
        manifest_path = (
            Path(candidate_workspace.candidate_root)
            / Path(*parts[:3])
            / "workflow.toml"
        )
        try:
            tomllib.loads(manifest_path.read_text(encoding="utf-8"))
            from botpipe.discovery import discover_workflows

            expected_source = (
                Path(candidate_workspace.candidate_root) / package_entry
            ).resolve()
            expected_function = workflow_reference.rsplit(":", 1)[1]
            entries = [
                entry
                for entry in discover_workflows(candidate_workspace.candidate_root)
                if entry.source_path.resolve() == expected_source
                and entry.manifest_path is not None
                and entry.manifest_path.resolve() == manifest_path.resolve()
            ]
            if (
                len(entries) != 1
                or entries[0].function != expected_function
                or entries[0].name != parts[2]
            ):
                diagnostics.append(
                    "catalog metadata must name the package and select its "
                    "flow.py callable"
                )
        except (OSError, tomllib.TOMLDecodeError, ValueError, LookupError) as exc:
            diagnostics.append(f"catalog: {exc}")
    manifest = candidate_manifest(candidate_workspace)
    surface = candidate_surface_manifest(candidate_workspace, frozen_candidate)
    candidate_files = {item["relative_path"]: item for item in surface["files"]}
    for compiled in result.compiled_workflows:
        matches = [
            relative
            for relative, item in candidate_files.items()
            if compiled["source_sha256"] == item["surface_sha256"]
            and Path(compiled["source_path"]).as_posix().endswith(f"/{relative}")
            and relative == package_entry
        ]
        if len(matches) != 1:
            diagnostics.append(
                "workflow_reference must resolve to one generated candidate source"
            )
    if diagnostics != list(result.errors):
        result = result.model_copy(
            update={"success": False, "errors": tuple(diagnostics)}
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
    if not isinstance(validation, Mapping) or not isinstance(
        validation.get("success"), bool
    ):
        raise TypeError("generated workflow validation result is malformed")
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
    manifest_diagnostics: Sequence[str] = (),
    *,
    target_test_argv: Sequence[str] | None = None,
    enforce_generated_test: bool = False,
) -> dict[str, Any]:
    """Validate once and recheck source identity after every activity replay."""
    result = _validate_generated_workflow_candidate_activity(
        candidate_workspace,
        frozen_candidate,
        workflow_reference,
        staging_parent,
        target_test_command,
        timeout,
        manifest_diagnostics,
        target_test_argv=target_test_argv,
        enforce_generated_test=enforce_generated_test,
    )
    return _revalidate_generated_workflow_validation(
        result,
        candidate_workspace=candidate_workspace,
        frozen_candidate=frozen_candidate,
    )


__all__ = [
    "WorkflowManifestValidationError",
    "freeze_generated_workflow_candidate",
    "materialize_generated_workflow_manifest",
    "prepare_generated_workflow_candidate",
    "validate_generated_workflow_candidate",
]
