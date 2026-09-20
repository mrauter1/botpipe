"""Shared authoring helpers for baseline/candidate surface publication mechanics."""

from __future__ import annotations

import shlex
import os
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from functools import partial
from hashlib import sha256
from pathlib import Path
from typing import Any

from botpipe.core.surface_identity import derive_surface_manifest as _derive_core_surface_manifest

from botpipe.stdlib.validation import (
    normalize_optional_string,
    require_mapping,
    require_non_empty_string,
    require_positive_int,
    require_string_list,
)

def derive_surface_manifest(root:Path,*,expected_root:Path,boundary:Mapping[str,Any],surface_kind:str,authoritative_sources:Mapping[str,Path]|None=None)->dict[str,Any]:
    """Derive one canonical manifest bound to a runtime-provided root."""
    derived=_derive_core_surface_manifest(root,expected_root=expected_root,boundary=boundary,surface_kind=surface_kind)
    files=[dict(x) for x in derived["files"]];by_path={x["relative_path"]:x for x in files}
    for relative,source_value in (authoritative_sources or {}).items():
        safe=_require_repo_relative_path(relative,"authoritative source paths must stay relative");raw=Path(source_value)
        if _has_symlink_component(raw):raise ValueError(f"authoritative source must not be a symlink: {safe}")
        source=raw.resolve(strict=True)
        if safe not in by_path or not source.is_file():raise ValueError(f"invalid authoritative source: {safe}")
        by_path[safe].update(source_path=str(source),authoritative_source_sha256=_sha256_file(source),authoritative_source_executable=_is_executable(source))
    derived["files"]=files;return derived

def validate_surface_manifest(manifest:Mapping[str,Any],*,expected_root:Path,expected_boundary:Mapping[str,Any],expected_surface_kind:str,baseline_manifest:Mapping[str,Any]|None=None,allowed_added_path_prefixes:Sequence[str]=(),allowed_added_exact_paths:Sequence[str]=())->dict[str,Any]:
    """Recompute all factual fields and reject submitted drift or forgery."""
    raw=Path(_require_text(manifest.get("root",manifest.get("surface_root")),"manifest root required"))
    if raw.is_symlink() or raw.resolve(strict=True)!=Path(expected_root).resolve(strict=True):raise ValueError("manifest root must match runtime expected root")
    identity_boundary = {key: value for key, value in expected_boundary.items() if key != "surface_kind"}
    derived=derive_surface_manifest(raw,expected_root=expected_root,boundary=identity_boundary,surface_kind=expected_surface_kind)
    for field in ("schema","surface_kind","root","surface_root","boundary","mode_semantics","surface_id","relative_paths","file_count","size_bytes"):
        if manifest.get(field)!=derived[field]:raise ValueError(f"manifest {field} must match derived surface")
    submitted=manifest.get("files")
    if not isinstance(submitted,list) or len(submitted)!=len(derived["files"]):raise ValueError("manifest files must match derived surface")
    factual=("relative_path","surface_path","surface_sha256","size_bytes","executable")
    for left,right in zip(submitted,derived["files"],strict=True):
        if not isinstance(left,Mapping) or any(left.get(x)!=right[x] for x in factual):raise ValueError("manifest files must match derived surface")
    if baseline_manifest is not None:
        baseline=set(_require_string_list(baseline_manifest.get("relative_paths"),"baseline relative_paths required"));candidate=set(derived["relative_paths"]);missing=baseline-candidate
        if missing:raise ValueError("candidate must preserve every baseline path")
        prefixes=tuple(_require_repo_relative_path(x,"allowed prefixes must stay relative") for x in allowed_added_path_prefixes);exact={_require_repo_relative_path(x,"allowed paths must stay relative") for x in allowed_added_exact_paths}
        for path in candidate-baseline:
            if path not in exact and not any(path.startswith(x+"/") for x in prefixes):raise ValueError(f"candidate added path outside boundary: {path}")
    return derived

def verify_surface_anchor(manifest:Mapping[str,Any],*,expected_root:Path,expected_boundary:Mapping[str,Any],expected_surface_kind:str)->str:
    return str(validate_surface_manifest(manifest,expected_root=expected_root,expected_boundary=expected_boundary,expected_surface_kind=expected_surface_kind)["surface_id"])


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
    package_root_relative_path = _preferred_repo_relative_path(
        repo_root,
        actual_path=package_dir,
        repo_relative_path=authoring_surface.get("package_dir_repo_relative"),
        error_message=f"{error_prefix} package_dir must stay under the repo root",
    )

    baseline_relative_paths: list[str] = []
    baseline_source_entries: list[dict[str, str]] = []
    doc_path = _optional_path(authoring_surface.get("doc_path"))
    doc_relative_path = _preferred_optional_repo_relative_path(
        repo_root,
        actual_path=doc_path,
        repo_relative_path=authoring_surface.get("doc_path_repo_relative"),
        error_message=f"{error_prefix} doc_path must stay under the repo root",
    )
    runtime_test_path = _optional_path(authoring_surface.get("runtime_test_path"))
    runtime_test_relative_path = _preferred_optional_repo_relative_path(
        repo_root,
        actual_path=runtime_test_path,
        repo_relative_path=authoring_surface.get("runtime_test_path_repo_relative"),
        error_message=f"{error_prefix} runtime_test_path must stay under the repo root",
    )
    for raw_path in _require_string_list(
        authoring_surface.get("editable_paths"),
        f"{error_prefix} must define non-empty editable_paths",
    ):
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"{error_prefix} path does not exist: {path}")
        relative_path = _candidate_surface_relative_path(
            repo_root,
            path=path,
            package_dir=package_dir,
            package_root_relative_path=package_root_relative_path,
            doc_path=doc_path,
            doc_relative_path=doc_relative_path,
            runtime_test_path=runtime_test_path,
            runtime_test_relative_path=runtime_test_relative_path,
            error_message=f"{error_prefix} editable_paths must stay under the repo root",
        )
        if relative_path not in baseline_relative_paths:
            baseline_relative_paths.append(relative_path)
            baseline_source_entries.append(
                {
                    "relative_path": relative_path,
                    "source_path": str(path),
                }
            )

    return {
        "package_root_relative_path": package_root_relative_path,
        "doc_relative_path": doc_relative_path,
        "runtime_test_relative_path": runtime_test_relative_path,
        "baseline_relative_paths": sorted(baseline_relative_paths),
        "baseline_source_entries": sorted(baseline_source_entries, key=lambda entry: entry["relative_path"]),
    }


def materialize_baseline_surface(
    *,
    workflow_folder: Path,
    repo_root: Path,
    baseline_relative_paths: Sequence[str | Mapping[str, Any]],
    baseline_dir_name: str,
    candidate_dir_name: str,
) -> dict[str, Any]:
    """Copy the authoritative baseline surface into the workflow folder and record file metadata."""

    entries = list(baseline_relative_paths)
    if not entries:
        raise ValueError("baseline_relative_paths must define non-empty repo-relative paths")
    baseline_name = _require_repo_relative_path(_require_text(
        baseline_dir_name,
        "baseline_dir_name must be non-empty",
    ), "baseline_dir_name must be a contained child path")
    candidate_name = _require_repo_relative_path(_require_text(
        candidate_dir_name,
        "candidate_dir_name must be non-empty",
    ), "candidate_dir_name must be a contained child path")
    baseline_root = (workflow_folder / baseline_name).resolve()
    candidate_root = (workflow_folder / candidate_name).resolve()
    if baseline_root == candidate_root or baseline_root == workflow_folder.resolve() or candidate_root == workflow_folder.resolve():
        raise ValueError("baseline and candidate roots must be distinct contained children")
    for root in (baseline_root, candidate_root):
        try: root.relative_to(workflow_folder.resolve())
        except ValueError as exc: raise ValueError("surface roots must stay under workflow_folder") from exc
        if root.exists(): raise FileExistsError(f"refusing to replace preexisting surface root: {root}")

    normalized_relative_paths: list[str] = []
    files: list[dict[str, Any]] = []
    for raw_entry in entries:
        if isinstance(raw_entry, Mapping):
            relative_path = _require_repo_relative_path(
                _require_text(
                    raw_entry.get("relative_path"),
                    "baseline_relative_paths entries must define relative_path",
                ),
                "baseline_relative_paths entries must stay repo-relative",
            )
            source_path = Path(
                _require_text(
                    raw_entry.get("source_path"),
                    "baseline_relative_paths entries must define source_path",
                )
            ).resolve()
        else:
            relative_path = _require_repo_relative_path(
                str(raw_entry),
                "baseline_relative_paths entries must stay repo-relative",
            )
            source_path = (repo_root / relative_path).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"baseline source file is missing: {source_path}")
        normalized_relative_paths.append(relative_path)
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
        ).resolve()
        surface_path = Path(
            _require_text(
                entry.get("surface_path"),
                f"{manifest_label} file entries must define non-empty surface_path",
            )
        ).resolve()
        try:
            source_path.relative_to(repo_root)
        except ValueError as exc:
            raise ValueError(f"{manifest_label} source_path entries must stay under the repo root") from exc
        if surface_path != surface_root / relative_path:
            raise ValueError(f"{manifest_label} surface_path entries must stay under the copied baseline surface")
        if not source_path.is_file() or not surface_path.is_file():
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
        _require_repo_relative_path(
            relative_path,
            f"{baseline_manifest_label} relative_path entries must stay repo-relative",
        )
        source_path = Path(
            _require_text(
                entry.get("source_path"),
                f"{baseline_manifest_label} file entries must define non-empty source_path",
            )
        ).resolve()
        try:
            source_path.relative_to(repo_root)
        except ValueError as exc:
            raise ValueError(f"{baseline_manifest_label} source_path entries must stay under the repo root") from exc
        if not source_path.is_file():
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
    target_test_command: str | None = None,
    target_test_argv: Sequence[str] | None = None,
    candidate_manifest_label: str,
    overlay_failure_prefix: str,
    overlay_temp_prefix: str,
    expected_candidate_root: Path | None = None,
    expected_baseline_root: Path | None = None,
    expected_boundary: Mapping[str, Any] | None = None,
    baseline_surface_kind: str | None = None,
    candidate_surface_kind: str | None = None,
    baseline_manifest: Mapping[str, Any] | None = None,
    execution_snapshot: Any | None = None,
    staging_parent: Path | None = None,
    compile_timeout_seconds: float = 60,
    test_timeout_seconds: float = 600,
) -> dict[str, Any]:
    """Strict compatibility wrapper over frozen-tree subprocess validation."""
    from .candidate_validation import validate_frozen_candidate
    from .execution_trees import capture_execution_tree, cleanup_owned_directory
    if expected_candidate_root is None:raise ValueError("expected_candidate_root is required")
    if expected_baseline_root is None:raise ValueError("expected_baseline_root is required")
    if expected_boundary is None:raise ValueError("expected_boundary is required")
    if baseline_surface_kind is None or candidate_surface_kind is None:
        raise ValueError("baseline_surface_kind and candidate_surface_kind are required")
    if baseline_manifest is None:raise ValueError("baseline_manifest is required")
    workflow_name_list = _require_string_list(
        workflow_names,
        "workflow_names must define at least one workflow name",
        allow_scalar=True,
    )
    temporary=None;snapshot=execution_snapshot
    try:
        if staging_parent is None:temporary=tempfile.TemporaryDirectory(prefix=overlay_temp_prefix);staging_parent=Path(temporary.name)
        if snapshot is None:
            selected=None
            if not (Path(repo_root)/"botpipe"/"__init__.py").is_file():
                import botpipe
                selected=Path(botpipe.__file__).resolve().parent
            snapshot=capture_execution_tree(repo_root,staging_parent,selected_package_root=selected,selected_package_import_path="botpipe" if selected else None)
        result=validate_frozen_candidate(snapshot,baseline_surface_manifest=baseline_manifest,candidate_surface_manifest=candidate_manifest,expected_baseline_root=expected_baseline_root,expected_candidate_root=expected_candidate_root,expected_boundary=expected_boundary,baseline_surface_kind=baseline_surface_kind,candidate_surface_kind=candidate_surface_kind,workflow_refs=workflow_name_list,staging_parent=staging_parent,target_test_argv=target_test_argv,target_test_command=target_test_command,compile_timeout_seconds=compile_timeout_seconds,test_timeout_seconds=test_timeout_seconds)
        if not result.success:raise ValueError(f"{overlay_failure_prefix}: {'; '.join(result.errors)}")
        return result.model_dump(mode="json", by_alias=True)
    finally:
        if execution_snapshot is None and snapshot is not None and snapshot.root.exists():cleanup_owned_directory(snapshot.root,owned_parent=snapshot.owned_parent,ownership_token=snapshot.ownership_token)
        if temporary is not None:temporary.cleanup()


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


def _preferred_repo_relative_path(
    repo_root: Path,
    *,
    actual_path: Path,
    repo_relative_path: Any,
    error_message: str,
) -> str:
    preferred = _normalize_optional_text(repo_relative_path)
    if preferred is not None:
        return _require_repo_relative_path(preferred, error_message)
    try:
        return actual_path.resolve().relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise ValueError(error_message) from exc


def _preferred_optional_repo_relative_path(
    repo_root: Path,
    *,
    actual_path: Path | None,
    repo_relative_path: Any,
    error_message: str,
) -> str | None:
    preferred = _normalize_optional_text(repo_relative_path)
    if preferred is not None:
        return _require_repo_relative_path(preferred, error_message)
    if actual_path is None:
        return None
    try:
        return actual_path.resolve().relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise ValueError(error_message) from exc


def _candidate_surface_relative_path(
    repo_root: Path,
    *,
    path: Path,
    package_dir: Path,
    package_root_relative_path: str,
    doc_path: Path | None,
    doc_relative_path: str | None,
    runtime_test_path: Path | None,
    runtime_test_relative_path: str | None,
    error_message: str,
) -> str:
    resolved = path.resolve()
    try:
        package_relative = resolved.relative_to(package_dir.resolve())
    except ValueError:
        package_relative = None
    if package_relative is not None:
        return str(Path(package_root_relative_path) / package_relative)
    if doc_path is not None and doc_relative_path is not None and resolved == doc_path.resolve():
        return doc_relative_path
    if runtime_test_path is not None and runtime_test_relative_path is not None and resolved == runtime_test_path.resolve():
        return runtime_test_relative_path
    try:
        return resolved.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise ValueError(error_message) from exc


def _optional_path(raw_value: Any) -> Path | None:
    normalized = _normalize_optional_text(raw_value)
    return None if normalized is None else Path(normalized).resolve()


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

def _is_executable(path:Path)->bool:return bool(path.stat(follow_symlinks=False).st_mode&0o111) if os.name=="posix" else False
def _has_symlink_component(path:Path,*,stop:Path|None=None)->bool:
    current=path.absolute();boundary=None if stop is None else stop.absolute()
    while True:
        if current.is_symlink():return True
        if boundary is not None and current==boundary:return False
        if current.parent==current:return False
        current=current.parent


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
        import botpipe
    except ImportError as exc:  # pragma: no cover - defensive fallback for broken test/runtime setup
        raise ValueError(
            "publish-time overlay validation requires a runnable repo root or an importable botpipe package"
        ) from exc

    package_root = Path(botpipe.__file__).resolve().parent.parent
    if not _is_runnable_repo_root(package_root):
        raise ValueError(f"botpipe package root is not runnable for overlay validation: {package_root}")
    return package_root


def _is_runnable_repo_root(path: Path) -> bool:
    if not path.is_dir() or not (path / "tests" / "conftest.py").is_file():
        return False
    if (path / "__init__.py").is_file() and (path / "core").is_dir() and (path / "runtime").is_dir():
        return True
    return (
        (path / "botpipe" / "__init__.py").is_file()
        and (path / "botpipe" / "core").is_dir()
        and (path / "botpipe" / "runtime").is_dir()
    )


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
    "derive_surface_manifest",
    "derive_candidate_surface_manifest",
    "materialize_baseline_surface",
    "normalize_candidate_surface_overlay_result",
    "normalize_candidate_surface_boundary",
    "validate_baseline_surface_manifest",
    "validate_authoritative_surface_sources_unchanged",
    "validate_candidate_surface_manifest",
    "validate_candidate_surface_overlay",
    "validate_surface_manifest",
    "verify_surface_anchor",
]
