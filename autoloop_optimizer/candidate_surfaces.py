"""Shared authoring helpers for baseline/candidate surface publication mechanics."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from functools import partial
from hashlib import sha256
from pathlib import Path
from typing import Any

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..core.compiler import compile_workflow
    from ..runtime.loader import resolve_workflow_reference
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from core.compiler import compile_workflow
    from runtime.loader import resolve_workflow_reference

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..stdlib.validation import (
        normalize_optional_string,
        require_mapping,
        require_non_empty_string,
        require_positive_int,
        require_string_list,
    )
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from stdlib.validation import (
        normalize_optional_string,
        require_mapping,
        require_non_empty_string,
        require_positive_int,
        require_string_list,
    )


def normalize_candidate_surface_boundary(
    repo_root: Path,
    authoring_surface: Mapping[str, Any],
    *,
    error_prefix: str,
) -> dict[str, Any]:
    """Normalize the editable repo-relative boundary for one selected workflow surface."""

    package_dir = Path(
        _require_text(
            authoring_surface.get("package_dir"),
            f"{error_prefix} must define package_dir",
        )
    ).resolve()
    try:
        package_root_relative_path = package_dir.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise ValueError(f"{error_prefix} package_dir must stay under the repo root") from exc

    baseline_relative_paths: list[str] = []
    for raw_path in _require_string_list(
        authoring_surface.get("editable_paths"),
        f"{error_prefix} must define non-empty editable_paths",
    ):
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"{error_prefix} path does not exist: {path}")
        try:
            relative_path = path.relative_to(repo_root).as_posix()
        except ValueError as exc:
            raise ValueError(f"{error_prefix} editable_paths must stay under the repo root") from exc
        if relative_path not in baseline_relative_paths:
            baseline_relative_paths.append(relative_path)

    return {
        "package_root_relative_path": package_root_relative_path,
        "doc_relative_path": _optional_repo_relative_path(
            repo_root,
            authoring_surface.get("doc_path"),
            f"{error_prefix} doc_path must stay under the repo root",
        ),
        "runtime_test_relative_path": _optional_repo_relative_path(
            repo_root,
            authoring_surface.get("runtime_test_path"),
            f"{error_prefix} runtime_test_path must stay under the repo root",
        ),
        "baseline_relative_paths": sorted(baseline_relative_paths),
    }


def materialize_baseline_surface(
    *,
    workflow_folder: Path,
    repo_root: Path,
    baseline_relative_paths: Sequence[str],
    baseline_dir_name: str,
    candidate_dir_name: str,
) -> dict[str, Any]:
    """Copy the authoritative baseline surface into the workflow folder and record file metadata."""

    normalized_relative_paths = _require_string_list(
        list(baseline_relative_paths),
        "baseline_relative_paths must define non-empty repo-relative paths",
    )
    normalized_relative_paths = [
        _require_repo_relative_path(
            relative_path,
            "baseline_relative_paths entries must stay repo-relative",
        )
        for relative_path in normalized_relative_paths
    ]
    baseline_root = workflow_folder / _require_text(
        baseline_dir_name,
        "baseline_dir_name must be non-empty",
    )
    candidate_root = workflow_folder / _require_text(
        candidate_dir_name,
        "candidate_dir_name must be non-empty",
    )
    shutil.rmtree(baseline_root, ignore_errors=True)
    shutil.rmtree(candidate_root, ignore_errors=True)

    files: list[dict[str, Any]] = []
    for relative_path in normalized_relative_paths:
        source_path = repo_root / relative_path
        if not source_path.is_file():
            raise FileNotFoundError(f"baseline source file is missing: {source_path}")
        target_path = baseline_root / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        digest = _sha256_file(source_path)
        files.append(
            {
                "relative_path": relative_path,
                "source_path": str(source_path),
                "surface_path": str(target_path),
                "surface_sha256": digest,
                "authoritative_source_sha256": digest,
                "size_bytes": source_path.stat().st_size,
            }
        )

    return {
        "surface_root": str(baseline_root),
        "relative_paths": normalized_relative_paths,
        "file_count": len(normalized_relative_paths),
        "files": files,
    }


def derive_candidate_surface_manifest(
    *,
    workflow_folder: Path,
    baseline_manifest: Mapping[str, Any],
    candidate_dir_name: str,
    baseline_manifest_label: str,
    candidate_manifest_label: str,
) -> dict[str, Any]:
    """Derive deterministic candidate-surface diff metadata from a copied baseline manifest."""

    candidate_root = workflow_folder / _require_text(
        candidate_dir_name,
        "candidate_dir_name must be non-empty",
    )
    if not candidate_root.is_dir():
        raise FileNotFoundError(f"candidate surface was not written at {candidate_root}")

    baseline_files = _manifest_file_map(
        baseline_manifest,
        f"{baseline_manifest_label} must define files as a JSON array of objects with relative_path",
    )
    baseline_relative_paths = _require_string_list(
        baseline_manifest.get("relative_paths"),
        f"{baseline_manifest_label} must define non-empty relative_paths",
    )
    candidate_relative_paths = _surface_relative_paths(candidate_root)
    if not candidate_relative_paths:
        raise ValueError(f"{candidate_manifest_label} surface must contain at least one file")

    files: list[dict[str, Any]] = []
    changed_relative_paths: list[str] = []
    added_relative_paths: list[str] = []
    for relative_path in candidate_relative_paths:
        surface_path = candidate_root / relative_path
        digest = _sha256_file(surface_path)
        baseline_entry = baseline_files.get(relative_path)
        changed_from_baseline = baseline_entry is None or digest != _require_text(
            baseline_entry.get("surface_sha256"),
            f"{baseline_manifest_label} file entries must define non-empty surface_sha256",
        )
        if baseline_entry is None:
            added_relative_paths.append(relative_path)
        if changed_from_baseline:
            changed_relative_paths.append(relative_path)
        files.append(
            {
                "relative_path": relative_path,
                "surface_path": str(surface_path),
                "surface_sha256": digest,
                "size_bytes": surface_path.stat().st_size,
                "changed_from_baseline": changed_from_baseline,
            }
        )

    return {
        "repo_root": _require_text(
            baseline_manifest.get("repo_root"),
            f"{baseline_manifest_label} must define non-empty repo_root",
        ),
        "surface_root": str(candidate_root),
        "baseline_relative_paths": baseline_relative_paths,
        "relative_paths": candidate_relative_paths,
        "file_count": len(candidate_relative_paths),
        "changed_relative_paths": changed_relative_paths,
        "added_relative_paths": added_relative_paths,
        "files": files,
    }


def validate_baseline_surface_manifest(
    baseline_manifest: Mapping[str, Any],
    repo_root: Path,
    *,
    manifest_label: str,
    expected_surface_kind: str,
    expected_boundary: Mapping[str, Any],
    boundary_field_map: Mapping[str, str] | None = None,
    optional_boundary_fields: Sequence[str] = (),
    expected_relative_paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate shared baseline-manifest mechanics and return normalized file metadata."""

    field_map = dict(boundary_field_map or {})
    optional_fields = set(optional_boundary_fields)

    if _require_text(
        baseline_manifest.get("surface_kind"),
        f"{manifest_label} must define non-empty surface_kind",
    ) != _require_text(expected_surface_kind, "expected_surface_kind must stay non-empty"):
        raise ValueError(f"{manifest_label} surface_kind must be {expected_surface_kind}")
    if _require_text(
        baseline_manifest.get("repo_root"),
        f"{manifest_label} must define non-empty repo_root",
    ) != str(repo_root):
        raise ValueError(f"{manifest_label} repo_root must match the runtime repo root")

    _validate_manifest_boundary_fields(
        baseline_manifest=baseline_manifest,
        manifest_label=manifest_label,
        expected_boundary=expected_boundary,
        boundary_field_map=field_map,
        optional_boundary_fields=optional_fields,
    )

    file_entries = _manifest_file_map(
        baseline_manifest,
        f"{manifest_label} must define files as a JSON array of objects with relative_path",
    )
    relative_paths = _require_string_list(
        baseline_manifest.get("relative_paths"),
        f"{manifest_label} must define non-empty relative_paths",
    )
    if sorted(file_entries) != relative_paths:
        raise ValueError(f"{manifest_label} files must match relative_paths")
    if expected_relative_paths is not None and relative_paths != _require_string_list(
        list(expected_relative_paths),
        "expected_relative_paths must define non-empty repo-relative paths",
    ):
        raise ValueError(f"{manifest_label} relative_paths must match the expected workflow boundary")

    surface_root = Path(
        _require_text(
            baseline_manifest.get("surface_root"),
            f"{manifest_label} must define non-empty surface_root",
        )
    )
    for relative_path, entry in file_entries.items():
        source_path = Path(
            _require_text(
                entry.get("source_path"),
                f"{manifest_label} file entries must define non-empty source_path",
            )
        )
        surface_path = Path(
            _require_text(
                entry.get("surface_path"),
                f"{manifest_label} file entries must define non-empty surface_path",
            )
        )
        if source_path != repo_root / relative_path:
            raise ValueError(f"{manifest_label} source_path entries must stay aligned to the repo root")
        if surface_path != surface_root / relative_path:
            raise ValueError(f"{manifest_label} surface_path entries must stay under the copied baseline surface")
        if not source_path.exists() or not surface_path.exists():
            raise FileNotFoundError(f"{manifest_label} file entries must point at existing files")
        expected_digest = _require_text(
            entry.get("surface_sha256"),
            f"{manifest_label} file entries must define non-empty surface_sha256",
        )
        if _sha256_file(surface_path) != expected_digest:
            raise ValueError(f"{manifest_label} surface_sha256 must match the copied baseline surface")

    return {
        "surface_root": surface_root,
        "relative_paths": relative_paths,
        "file_entries": file_entries,
    }


def validate_candidate_surface_manifest(
    candidate_manifest: Mapping[str, Any],
    *,
    repo_root: Path,
    manifest_label: str,
    expected_surface_kind: str,
    expected_boundary: Mapping[str, Any],
    boundary_field_map: Mapping[str, str] | None = None,
    optional_boundary_fields: Sequence[str] = (),
    baseline_manifest: Mapping[str, Any],
    baseline_manifest_label: str,
    allowed_added_path_prefixes: Sequence[str] = (),
    allowed_added_exact_paths: Sequence[str] = (),
    require_surface_listing_matches_disk: bool = False,
    require_file_count_matches_relative_paths: bool = False,
) -> dict[str, Any]:
    """Validate shared candidate-manifest mechanics and return normalized file metadata."""

    field_map = dict(boundary_field_map or {})
    optional_fields = set(optional_boundary_fields)

    if _require_text(
        candidate_manifest.get("surface_kind"),
        f"{manifest_label} must define non-empty surface_kind",
    ) != _require_text(expected_surface_kind, "expected_surface_kind must stay non-empty"):
        raise ValueError(f"{manifest_label} surface_kind must be {expected_surface_kind}")
    if _require_text(
        candidate_manifest.get("repo_root"),
        f"{manifest_label} must define non-empty repo_root",
    ) != str(repo_root):
        raise ValueError(f"{manifest_label} repo_root must match the runtime repo root")

    _validate_manifest_boundary_fields(
        baseline_manifest=candidate_manifest,
        manifest_label=manifest_label,
        expected_boundary=expected_boundary,
        boundary_field_map=field_map,
        optional_boundary_fields=optional_fields,
    )

    baseline_relative_paths = _require_string_list(
        baseline_manifest.get("relative_paths"),
        f"{baseline_manifest_label} must define non-empty relative_paths",
    )
    candidate_baseline_relative_paths = _require_string_list(
        candidate_manifest.get("baseline_relative_paths"),
        f"{manifest_label} must define non-empty baseline_relative_paths",
    )
    if candidate_baseline_relative_paths != baseline_relative_paths:
        raise ValueError(f"{manifest_label} baseline_relative_paths must match {baseline_manifest_label}")

    candidate_root = Path(
        _require_text(
            candidate_manifest.get("surface_root"),
            f"{manifest_label} must define non-empty surface_root",
        )
    )
    candidate_relative_paths = _require_string_list(
        candidate_manifest.get("relative_paths"),
        f"{manifest_label} must define non-empty relative_paths",
    )
    if require_surface_listing_matches_disk:
        actual_relative_paths = _surface_relative_paths(candidate_root)
        if candidate_relative_paths != actual_relative_paths:
            raise ValueError(f"{manifest_label} relative_paths must match {candidate_root.name}")
    if require_file_count_matches_relative_paths and _require_positive_int(
        candidate_manifest.get("file_count"),
        f"{manifest_label} must define positive integer file_count",
    ) != len(candidate_relative_paths):
        raise ValueError(f"{manifest_label} file_count must match {candidate_root.name}")

    missing_baseline_paths = sorted(set(baseline_relative_paths) - set(candidate_relative_paths))
    if missing_baseline_paths:
        raise ValueError(f"{manifest_label} must preserve every baseline relative_path")

    allowed_prefixes = [
        _require_repo_relative_path(prefix, "allowed_added_path_prefixes entries must stay repo-relative")
        for prefix in allowed_added_path_prefixes
    ]
    allowed_exact_paths = {
        _require_repo_relative_path(
            normalized,
            "allowed_added_exact_paths entries must stay repo-relative",
        )
        for raw_path in allowed_added_exact_paths
        if (normalized := _normalize_optional_text(raw_path)) is not None
    }
    for relative_path in candidate_relative_paths:
        if relative_path in baseline_relative_paths:
            continue
        if any(relative_path.startswith(f"{prefix}/") for prefix in allowed_prefixes):
            continue
        if relative_path in allowed_exact_paths:
            continue
        raise ValueError(f"{manifest_label} must stay within the allowed repo-relative boundary")

    file_entries = _manifest_file_map(
        candidate_manifest,
        f"{manifest_label} must define files as a JSON array of objects with relative_path",
    )
    if sorted(file_entries) != candidate_relative_paths:
        raise ValueError(f"{manifest_label} files must match relative_paths")
    for relative_path, entry in file_entries.items():
        surface_path = Path(
            _require_text(
                entry.get("surface_path"),
                f"{manifest_label} file entries must define non-empty surface_path",
            )
        )
        if surface_path != candidate_root / relative_path:
            raise ValueError(f"{manifest_label} surface_path entries must stay under {candidate_root.name}")
        if not surface_path.exists():
            raise FileNotFoundError(f"candidate surface file is missing: {surface_path}")
        expected_digest = _require_text(
            entry.get("surface_sha256"),
            f"{manifest_label} file entries must define non-empty surface_sha256",
        )
        if _sha256_file(surface_path) != expected_digest:
            raise ValueError(f"{manifest_label} surface_sha256 must match {candidate_root.name}")

    return {
        "surface_root": candidate_root,
        "relative_paths": candidate_relative_paths,
        "baseline_relative_paths": baseline_relative_paths,
        "file_entries": file_entries,
    }


def validate_authoritative_surface_sources_unchanged(
    baseline_manifest: Mapping[str, Any],
    repo_root: Path,
    *,
    baseline_manifest_label: str,
    drift_error_prefix: str,
) -> None:
    """Reject publication when authoritative selected-workflow sources drift after baseline capture."""

    for relative_path, entry in _manifest_file_map(
        baseline_manifest,
        f"{baseline_manifest_label} must define files as a JSON array of objects with relative_path",
    ).items():
        safe_relative_path = _require_repo_relative_path(
            relative_path,
            f"{baseline_manifest_label} relative_path entries must stay repo-relative",
        )
        source_path = repo_root / safe_relative_path
        if not source_path.exists():
            raise FileNotFoundError(f"authoritative selected workflow file is missing: {source_path}")
        current_digest = _sha256_file(source_path)
        expected_digest = _require_text(
            entry.get("authoritative_source_sha256"),
            f"{baseline_manifest_label} file entries must define non-empty authoritative_source_sha256",
        )
        if current_digest != expected_digest:
            raise ValueError(f"{drift_error_prefix}: {relative_path}")


def validate_candidate_surface_overlay(
    *,
    repo_root: Path,
    workflow_names: Sequence[str] | str,
    candidate_manifest: Mapping[str, Any],
    target_test_command: str,
    candidate_manifest_label: str,
    overlay_failure_prefix: str,
    overlay_temp_prefix: str,
) -> dict[str, Any]:
    """Compile the candidate overlay in isolation and run the declared validation command."""

    candidate_root = Path(
        _require_text(
            candidate_manifest.get("surface_root"),
            f"{candidate_manifest_label} must define non-empty surface_root",
        )
    )
    command = _require_text(target_test_command, "target_test_command must stay non-empty")
    command_args = _normalized_command_args(command)
    workflow_name_list = _require_string_list(
        workflow_names,
        "workflow_names must define at least one workflow name",
        allow_scalar=True,
    )
    overlay_source_root = _resolve_overlay_source_root(repo_root)

    with tempfile.TemporaryDirectory(prefix=overlay_temp_prefix) as tmp_dir:
        overlay_root = Path(tmp_dir) / overlay_source_root.name
        shutil.copytree(
            overlay_source_root,
            overlay_root,
            ignore=shutil.ignore_patterns(
                ".autoloop",
                ".git",
                ".pytest_cache",
                "__pycache__",
                "*.pyc",
                ".mypy_cache",
                ".ruff_cache",
                ".venv",
            ),
        )
        repo_venv = overlay_source_root / ".venv"
        overlay_venv = overlay_root / ".venv"
        if repo_venv.exists() and not overlay_venv.exists():
            overlay_venv.symlink_to(repo_venv, target_is_directory=True)

        for relative_path in _require_string_list(
            candidate_manifest.get("relative_paths"),
            f"{candidate_manifest_label} must define non-empty relative_paths",
        ):
            safe_relative_path = _require_repo_relative_path(
                relative_path,
                f"{candidate_manifest_label} relative_paths entries must stay repo-relative",
            )
            source_path = candidate_root / safe_relative_path
            if not source_path.is_file():
                raise FileNotFoundError(f"candidate surface file is missing: {source_path}")
            target_path = overlay_root / safe_relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)

        compiled_workflow_names: list[str] = []
        with _preserved_workflow_modules():
            for workflow_name in workflow_name_list:
                resolved = resolve_workflow_reference(overlay_root, workflow_name)
                compiled = compile_workflow(resolved.workflow_cls)
                compiled_workflow_names.append(compiled.workflow_name)

        completed = subprocess.run(
            command_args,
            cwd=overlay_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise ValueError(
                f"{overlay_failure_prefix}: {command}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
            )
        return {
            "compiled_workflow_names": compiled_workflow_names,
            "test_command": command,
            "test_returncode": completed.returncode,
        }


def normalize_candidate_surface_overlay_result(
    overlay_validation: Mapping[str, Any],
    *,
    expect_single_compiled_workflow: bool,
    overlay_result_label: str = "overlay validation",
) -> dict[str, Any]:
    """Normalize shared overlay-validation result payloads for workflow receipts."""

    compiled_workflow_names = _require_string_list(
        overlay_validation.get("compiled_workflow_names"),
        f"{overlay_result_label} must define non-empty compiled_workflow_names",
    )
    test_returncode = overlay_validation.get("test_returncode")
    if not isinstance(test_returncode, int) or test_returncode < 0:
        raise ValueError(f"{overlay_result_label} must define non-negative integer test_returncode")

    normalized = {
        "test_command": _require_text(
            overlay_validation.get("test_command"),
            f"{overlay_result_label} must define non-empty test_command",
        ),
        "test_returncode": test_returncode,
    }
    if expect_single_compiled_workflow:
        if len(compiled_workflow_names) != 1:
            raise ValueError(f"{overlay_result_label} must compile exactly one selected workflow")
        normalized["compiled_workflow_name"] = compiled_workflow_names[0]
        return normalized

    normalized["compiled_workflow_names"] = compiled_workflow_names
    return normalized


def _normalized_command_args(command: str) -> list[str]:
    command_args = shlex.split(command)
    if command_args and command_args[0] == "pytest":
        return [sys.executable, "-m", "pytest", *command_args[1:]]
    return command_args


def _optional_repo_relative_path(repo_root: Path, raw_value: Any, error_message: str) -> str | None:
    normalized = _normalize_optional_text(raw_value)
    if normalized is None:
        return None
    path = Path(normalized).resolve()
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise ValueError(error_message) from exc


def _manifest_file_map(manifest: Mapping[str, Any], error_message: str) -> dict[str, dict[str, Any]]:
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError(error_message)
    result: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(files):
        mapping = _require_mapping(entry, error_message)
        relative_path = _require_text(
            mapping.get("relative_path"),
            f"{error_message}; offending index {index}",
        )
        result[relative_path] = dict(mapping)
    return result


def _validate_manifest_boundary_fields(
    *,
    baseline_manifest: Mapping[str, Any],
    manifest_label: str,
    expected_boundary: Mapping[str, Any],
    boundary_field_map: Mapping[str, str],
    optional_boundary_fields: set[str],
) -> None:
    for manifest_field, boundary_field in boundary_field_map.items():
        if manifest_field in optional_boundary_fields:
            actual = _normalize_optional_text(baseline_manifest.get(manifest_field))
            expected = _normalize_optional_text(expected_boundary.get(boundary_field))
        else:
            actual = _require_text(
                baseline_manifest.get(manifest_field),
                f"{manifest_label} must define non-empty {manifest_field}",
            )
            expected = _require_text(
                expected_boundary.get(boundary_field),
                f"expected boundary must define {boundary_field}",
            )
        if actual != expected:
            raise ValueError(f"{manifest_label} {manifest_field} must match the expected workflow boundary")


def _surface_relative_paths(root: Path) -> list[str]:
    if not root.is_dir():
        raise FileNotFoundError(f"candidate surface is missing: {root}")
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


def _require_repo_relative_path(value: Any, error_message: str) -> str:
    relative_path = _require_text(value, error_message)
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(error_message)
    normalized = path.as_posix()
    if normalized in {"", "."}:
        raise ValueError(error_message)
    return normalized


def _resolve_overlay_source_root(repo_root: Path) -> Path:
    if _is_runnable_repo_root(repo_root):
        return repo_root
    try:
        import autoloop_v3
    except ImportError as exc:  # pragma: no cover - defensive fallback for broken test/runtime setup
        raise ValueError(
            "publish-time overlay validation requires a runnable repo root or an importable autoloop_v3 package"
        ) from exc

    package_root = Path(autoloop_v3.__file__).resolve().parent
    if not _is_runnable_repo_root(package_root):
        raise ValueError(f"autoloop_v3 package root is not runnable for overlay validation: {package_root}")
    return package_root


def _is_runnable_repo_root(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "__init__.py").is_file()
        and (path / "core").is_dir()
        and (path / "runtime").is_dir()
        and (path / "tests" / "conftest.py").is_file()
    )


@contextmanager
def _preserved_workflow_modules():
    preserved = {
        name: module for name, module in sys.modules.items() if name == "workflows" or name.startswith("workflows.")
    }
    try:
        yield
    finally:
        for name in tuple(sys.modules):
            if name == "workflows" or name.startswith("workflows."):
                sys.modules.pop(name, None)
        sys.modules.update(preserved)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


_require_text = partial(require_non_empty_string, coerce=True)
_require_positive_int = require_positive_int
_normalize_optional_text = normalize_optional_string
_require_string_list = partial(require_string_list, dedupe=True, coerce=True)
_require_mapping = require_mapping


__all__ = [
    "derive_candidate_surface_manifest",
    "materialize_baseline_surface",
    "normalize_candidate_surface_overlay_result",
    "normalize_candidate_surface_boundary",
    "validate_baseline_surface_manifest",
    "validate_authoritative_surface_sources_unchanged",
    "validate_candidate_surface_manifest",
    "validate_candidate_surface_overlay",
]
