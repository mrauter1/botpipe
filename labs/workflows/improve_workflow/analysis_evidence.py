"""Immutable, citable journal evidence for workflow investigation turns."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any


class GroundingError(ValueError):
    """A model citation can be corrected without recapturing evidence."""


class AnalysisIntegrityError(ValueError):
    """The frozen analysis evidence is missing, redirected, or changed."""


@dataclass(frozen=True, slots=True)
class FrozenAnalysisEvidence:
    root: str
    managed_root: str
    marker_sha256: str
    hashes: dict[str, str]


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    ).encode()


def _slug(value: Any, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or fallback)).strip("-.")
    return (cleaned or fallback)[:96]


def _plain_file(path: Path, *, label: str) -> bytes:
    if path.is_symlink():
        raise AnalysisIntegrityError(f"{label} is a symlink")
    try:
        before = path.lstat()
        data = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise AnalysisIntegrityError(f"{label} is unavailable") from exc
    identity = lambda stat: (
        stat.st_dev,
        stat.st_ino,
        stat.st_mode,
        stat.st_size,
        stat.st_mtime_ns,
    )
    if identity(before) != identity(after) or not path.is_file():
        raise AnalysisIntegrityError(f"{label} changed while being captured")
    return data


def _artifact_records(value: Any):
    if isinstance(value, dict):
        if {
            "name",
            "path",
            "source_path",
            "kind",
            "digest",
        } <= value.keys():
            yield value
        for nested in value.values():
            yield from _artifact_records(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _artifact_records(nested)


def freeze_analysis_evidence(
    inspections: tuple[dict[str, Any], ...],
    destination: str | Path,
    *,
    max_bytes: int = 50 * 1024 * 1024,
) -> FrozenAnalysisEvidence:
    """Materialize journal projections and every referenced artifact version."""

    managed = Path(destination)
    if managed.is_symlink() or (managed / "evidence").is_symlink():
        raise AnalysisIntegrityError(
            "analysis evidence destination must not be a symlink"
        )
    input_id = sha256(
        _json_bytes({"inspections": inspections, "max_bytes": max_bytes})
    ).hexdigest()
    published = _published_generation(managed, input_id=input_id, max_bytes=max_bytes)
    if published is not None:
        return published
    files: dict[str, bytes] = {}
    total_bytes = 0
    catalog: list[dict[str, Any]] = []
    omissions: list[dict[str, Any]] = []
    seen_artifacts: set[tuple[str, str]] = set()

    def add(relative: str, data: bytes, *, required: bool = False) -> bool:
        nonlocal total_bytes
        if relative in files and files[relative] != data:
            raise AnalysisIntegrityError(f"analysis evidence path collided: {relative}")
        if relative not in files and total_bytes + len(data) > max_bytes:
            if required:
                raise ValueError(
                    "frozen analysis evidence metadata exceeds max_evidence_bytes"
                )
            omissions.append(
                {
                    "path": relative,
                    "reason": "max_evidence_bytes",
                    "bytes": len(data),
                    "sha256": sha256(data).hexdigest(),
                }
            )
            return False
        if relative not in files:
            total_bytes += len(data)
        files[relative] = data
        return True

    for run_index, inspection in enumerate(inspections, 1):
        run = inspection.get("run") if isinstance(inspection, dict) else None
        if not isinstance(run, dict):
            raise AnalysisIntegrityError("captured run inspection is malformed")
        run_ref = (
            f"{run.get('task_id')}/{run.get('run_id')}"
            if run.get("task_id")
            else str(run.get("run_id") or run_index)
        )
        prefix = f"runs/{run_index:03d}-{_slug(run_ref, 'run')}"
        run_record = f"{prefix}/run.json"
        add(run_record, _json_bytes(run))
        journal_paths: list[str] = []
        raw_run_folder = run.get("folder")
        if isinstance(raw_run_folder, str):
            run_folder = Path(raw_run_folder)
            if run_folder.is_symlink():
                raise AnalysisIntegrityError("recorded run folder is a symlink")
            try:
                resolved_run_folder = run_folder.resolve(strict=True)
            except OSError:
                omissions.append(
                    {
                        "path": f"{prefix}/journal",
                        "reason": "recorded_run_folder_unavailable",
                        "bytes": None,
                        "sha256": None,
                    }
                )
                resolved_run_folder = None
            patterns = (
                "ledger.jsonl",
                "input.json",
                "request.md",
                "operations/*/attempts/*/prompt.md",
                "operations/*/attempts/*/request.json",
                "operations/*/attempts/*/response.md",
                ".artifacts/operations/*/capture*.json",
                ".artifacts/blobs/*/*/*",
            )
            seen_journal_sources: set[Path] = set()
            for pattern in patterns if resolved_run_folder is not None else ():
                for source_path in sorted(run_folder.glob(pattern)):
                    if source_path in seen_journal_sources:
                        continue
                    seen_journal_sources.add(source_path)
                    relative_source = source_path.relative_to(run_folder).as_posix()
                    if source_path.is_symlink():
                        raise AnalysisIntegrityError(
                            f"recorded journal evidence is a symlink: {relative_source}"
                        )
                    resolved_source = source_path.resolve(strict=True)
                    if not resolved_source.is_relative_to(resolved_run_folder):
                        raise AnalysisIntegrityError(
                            f"recorded journal evidence escaped its run: {relative_source}"
                        )
                    bundle_path = f"{prefix}/journal/{relative_source}"
                    captured = add(
                        bundle_path,
                        _plain_file(
                            source_path,
                            label=f"recorded journal evidence {relative_source}",
                        ),
                    )
                    if captured:
                        journal_paths.append(bundle_path)
        operations = inspection.get("operations", ())
        if not isinstance(operations, list):
            raise AnalysisIntegrityError("captured run operations are malformed")
        operation_paths: list[str] = []
        operation_evidence: list[dict[str, Any]] = []
        for operation_index, operation in enumerate(operations, 1):
            if not isinstance(operation, dict):
                raise AnalysisIntegrityError("captured operation is malformed")
            op_prefix = (
                f"{prefix}/operations/{operation_index:03d}-"
                f"{_slug(operation.get('id'), 'operation')}"
            )
            op_path = f"{op_prefix}/record.json"
            if add(op_path, _json_bytes(operation)):
                operation_paths.append(op_path)
            operation_id = str(operation.get("id") or "")
            journal_component = (
                operation_id
                if re.fullmatch(r"[A-Za-z0-9_.-]+", operation_id)
                else "operation-" + sha256(operation_id.encode()).hexdigest()
            )
            related_journal = [
                path
                for path in journal_paths
                if f"/operations/{journal_component}/" in path
            ]
            operation_evidence.append(
                {
                    "operation_id": operation_id,
                    "record": op_path if op_path in files else None,
                    "journal_records": related_journal,
                }
            )
            inputs = operation.get("inputs")
            if isinstance(inputs, dict):
                prompt = inputs.get("value", {}).get("prompt")
                if isinstance(prompt, str):
                    add(f"{op_prefix}/prompt.md", prompt.encode())
            response = operation.get("response")
            if isinstance(response, dict) and isinstance(response.get("text"), str):
                add(f"{op_prefix}/response.md", response["text"].encode())
            if operation.get("error") is not None:
                add(f"{op_prefix}/error.json", _json_bytes(operation["error"]))
            # Only completed durable results contain authoritative artifact
            # handles. Prompt/input dictionaries may coincidentally have the
            # same keys and must never become filesystem read capabilities.
            for artifact in _artifact_records(operation.get("result")):
                digest = artifact.get("digest")
                artifact_path = artifact.get("path")
                if not (
                    isinstance(digest, str)
                    and re.fullmatch(r"[0-9a-f]{64}", digest)
                    and isinstance(artifact_path, str)
                ):
                    raise AnalysisIntegrityError(
                        "recorded artifact identity is malformed"
                    )
                identity = (digest, str(artifact.get("name")))
                if identity in seen_artifacts:
                    continue
                seen_artifacts.add(identity)
                artifact_source = Path(artifact_path)
                if not artifact_source.exists():
                    omissions.append(
                        {
                            "path": f"artifacts/{digest}-{_slug(artifact.get('name'), 'artifact')}",
                            "reason": "recorded_artifact_unavailable",
                            "bytes": None,
                            "sha256": digest,
                        }
                    )
                    continue
                data = _plain_file(
                    artifact_source, label=f"recorded artifact {artifact.get('name')}"
                )
                if sha256(data).hexdigest() != digest:
                    raise AnalysisIntegrityError(
                        "recorded artifact version digest changed"
                    )
                name = _slug(artifact.get("name"), "artifact")
                add(f"artifacts/{digest}-{name}", data)
        catalog.append(
            {
                "run_ref": run_ref,
                "status": run.get("status"),
                "workflow_version": run.get("version"),
                "workflow_surface_id": run.get("surface_id"),
                "run_record": run_record if run_record in files else None,
                "operation_records": operation_paths,
                "operation_evidence": operation_evidence,
                "journal_records": journal_paths,
            }
        )
    index = _json_bytes({"runs": catalog, "omissions": omissions})
    add("index.json", index, required=True)
    hashes = {relative: sha256(data).hexdigest() for relative, data in files.items()}
    marker = _json_bytes(
        {
            "schema": "botpipe.analysis-evidence/v1",
            "input_id": input_id,
            "max_bytes": max_bytes,
            "hashes": hashes,
        }
    )
    completed = _completed_generation(managed, marker, hashes)
    if completed is not None:
        return completed
    managed.parent.mkdir(parents=True, exist_ok=True)
    # Stage outside the frozen source root that owns ``destination``. A hard
    # interruption can leave an inert generation, but cannot expose a partial
    # final tree or perturb the source inventory checked by the caller.
    staging_parent = managed.parent.parent
    staging = Path(
        tempfile.mkdtemp(prefix=f".{managed.name}.pending-", dir=staging_parent)
    )
    staging_marker = staging / ".botpipe-analysis-evidence.json"
    installed = False
    try:
        # This exact final marker is also the ownership proof for cleanup of the
        # unique staging directory created by this invocation.
        staging_marker.write_bytes(marker)
        staging_root = staging / "evidence"
        for relative, data in sorted(files.items()):
            path = staging_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        for path in staging_root.rglob("*"):
            if path.is_file():
                os.chmod(path, 0o444)
        os.chmod(staging_marker, 0o444)
        try:
            os.replace(staging, managed)
            installed = True
        except OSError:
            # A concurrent/replayed invocation may have installed the exact
            # generation. Anything else remains an integrity conflict.
            completed = _completed_generation(managed, marker, hashes)
            if completed is None:
                raise
            return completed
    finally:
        if not installed and staging.exists():
            _remove_owned_staging(staging, marker)
    completed = _completed_generation(managed, marker, hashes)
    assert completed is not None
    return completed


def _completed_generation(
    managed: Path, marker: bytes, hashes: dict[str, str]
) -> FrozenAnalysisEvidence | None:
    if not managed.exists() and not managed.is_symlink():
        return None
    if managed.is_symlink() or not managed.is_dir():
        raise AnalysisIntegrityError("analysis evidence destination is not owned")
    marker_path = managed / ".botpipe-analysis-evidence.json"
    if marker_path.is_symlink() or not marker_path.is_file():
        raise AnalysisIntegrityError("analysis evidence destination is not owned")
    if marker_path.read_bytes() != marker:
        raise AnalysisIntegrityError("existing analysis evidence generation differs")
    frozen = FrozenAnalysisEvidence(
        root=str(managed / "evidence"),
        managed_root=str(managed),
        marker_sha256=sha256(marker).hexdigest(),
        hashes=hashes,
    )
    verify_analysis_evidence(frozen)
    return frozen


def _published_generation(
    managed: Path, *, input_id: str, max_bytes: int
) -> FrozenAnalysisEvidence | None:
    if not managed.exists() and not managed.is_symlink():
        return None
    if managed.is_symlink() or not managed.is_dir():
        raise AnalysisIntegrityError("analysis evidence destination is not owned")
    marker_path = managed / ".botpipe-analysis-evidence.json"
    if marker_path.is_symlink() or not marker_path.is_file():
        raise AnalysisIntegrityError("analysis evidence destination is not owned")
    marker = marker_path.read_bytes()
    try:
        record = json.loads(marker)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisIntegrityError(
            "analysis evidence ownership marker is invalid"
        ) from exc
    if (
        not isinstance(record, dict)
        or set(record) != {"schema", "input_id", "max_bytes", "hashes"}
        or record.get("schema") != "botpipe.analysis-evidence/v1"
        or record.get("input_id") != input_id
        or record.get("max_bytes") != max_bytes
        or not isinstance(record.get("hashes"), dict)
    ):
        raise AnalysisIntegrityError("existing analysis evidence generation differs")
    hashes = record["hashes"]
    if any(
        not isinstance(relative, str)
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        for relative, digest in hashes.items()
    ):
        raise AnalysisIntegrityError("analysis evidence ownership marker is invalid")
    frozen = FrozenAnalysisEvidence(
        root=str(managed / "evidence"),
        managed_root=str(managed),
        marker_sha256=sha256(marker).hexdigest(),
        hashes=hashes,
    )
    verify_analysis_evidence(frozen)
    return frozen


def _remove_owned_staging(staging: Path, marker: bytes) -> None:
    marker_path = staging / ".botpipe-analysis-evidence.json"
    try:
        if (
            marker_path.is_symlink()
            or not marker_path.is_file()
            or marker_path.read_bytes() != marker
        ):
            return
        for path in sorted(staging.rglob("*"), reverse=True):
            if not path.is_symlink():
                os.chmod(path, 0o700 if path.is_dir() else 0o600)
        shutil.rmtree(staging)
    except OSError:
        # An incomplete cleanup is an inert uniquely named generation. It is
        # never mistaken for the final destination or deleted by a later call.
        return


def verify_analysis_evidence(frozen: FrozenAnalysisEvidence) -> None:
    raw_root = Path(frozen.root)
    raw_managed = Path(frozen.managed_root)
    if raw_root.is_symlink() or raw_managed.is_symlink():
        raise AnalysisIntegrityError(
            "frozen analysis evidence paths must not be symlinks"
        )
    managed = raw_managed.resolve(strict=True)
    root = raw_root.resolve(strict=True)
    if root != managed / "evidence":
        raise AnalysisIntegrityError(
            "frozen analysis evidence escaped its managed root"
        )
    marker = managed / ".botpipe-analysis-evidence.json"
    if marker.is_symlink() or not marker.is_file():
        raise AnalysisIntegrityError("frozen analysis evidence marker is invalid")
    if sha256(marker.read_bytes()).hexdigest() != frozen.marker_sha256:
        raise AnalysisIntegrityError("frozen analysis evidence marker changed")
    entries = tuple(root.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise AnalysisIntegrityError("frozen analysis evidence contains a symlink")
    actual_paths = {
        path.relative_to(root).as_posix() for path in entries if path.is_file()
    }
    if actual_paths != set(frozen.hashes):
        raise AnalysisIntegrityError("frozen analysis evidence file set changed")
    actual = {
        relative: sha256(_bounded_file(root, relative).read_bytes()).hexdigest()
        for relative in frozen.hashes
    }
    if actual != frozen.hashes:
        raise AnalysisIntegrityError("frozen analysis evidence changed")


def validate_exact_quote(root: Path, relative: str, quote: str) -> None:
    try:
        text = _bounded_file(root.resolve(strict=True), relative).read_text("utf-8")
    except UnicodeDecodeError as exc:
        raise GroundingError(f"citation path is not UTF-8 text: {relative}") from exc
    if quote not in text:
        raise GroundingError(f"citation quote was not found verbatim in {relative}")


def _bounded_file(root: Path, relative: str) -> Path:
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts or relative != raw.as_posix():
        raise AnalysisIntegrityError(
            f"analysis evidence path escapes its root: {relative}"
        )
    path = root / raw
    if path.is_symlink():
        raise AnalysisIntegrityError("analysis evidence citation targets a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise GroundingError(f"citation path does not exist: {relative}") from exc
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise AnalysisIntegrityError(
            f"analysis evidence path escapes its root: {relative}"
        )
    return resolved


__all__ = [
    "AnalysisIntegrityError",
    "FrozenAnalysisEvidence",
    "GroundingError",
    "freeze_analysis_evidence",
    "validate_exact_quote",
    "verify_analysis_evidence",
]
