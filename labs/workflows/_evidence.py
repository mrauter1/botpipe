"""Small durable intake for user-declared lab evidence files."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from botpipe import activity, current_run
from botpipe.artifacts import Artifact, ArtifactError, ArtifactHandle, ArtifactStore

DEFAULT_MAX_EVIDENCE_FILES = 32
DEFAULT_MAX_EVIDENCE_FILE_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_EVIDENCE_TOTAL_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_EVIDENCE_PATH_CHARS = 1024

UnavailableReason = Literal[
    "file_count_limit",
    "missing",
    "unsafe_path",
    "not_regular_file",
    "file_too_large",
    "total_byte_limit",
    "read_failed",
]


@dataclass(frozen=True, slots=True)
class EvidenceIntakeRecord:
    """One declared source and its immutable capture outcome."""

    declared_path: str
    status: Literal["captured", "unavailable"]
    source_path: str | None = None
    artifact_name: str | None = None
    snapshot_path: str | None = None
    digest: str | None = None
    size_bytes: int | None = None
    unavailable_reason: UnavailableReason | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceIntake:
    """Stable declared-evidence records and their immutable artifact handles."""

    records: tuple[EvidenceIntakeRecord, ...]
    handles: tuple[ArtifactHandle, ...]
    captured_bytes: int


def _artifact_name(index: int, declared_path: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "_", Path(declared_path).stem.lower()).strip("_")
    stem = (stem or "source")[:32]
    identity = hashlib.sha256(declared_path.encode()).hexdigest()[:10]
    return f"declared_evidence_{index:03d}_{stem}_{identity}"


def _unavailable(
    declared_path: str, reason: UnavailableReason, detail: str
) -> EvidenceIntakeRecord:
    return EvidenceIntakeRecord(
        declared_path=declared_path,
        status="unavailable",
        unavailable_reason=reason,
        detail=detail,
    )


def _workspace_path(workspace: Path, declared_path: str) -> Path | None:
    if not declared_path or "\x00" in declared_path:
        return None
    raw = Path(declared_path)
    candidate = raw if raw.is_absolute() else workspace / raw
    candidate = Path(os.path.abspath(candidate))
    return candidate if candidate.is_relative_to(workspace) else None


def _has_symlink(workspace: Path, candidate: Path) -> bool:
    relative = candidate.relative_to(workspace)
    current = workspace
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


@activity(retry_safe=True, name="capture declared lab evidence")
def capture_declared_evidence(
    evidence_paths: Sequence[str],
    *,
    max_files: int = DEFAULT_MAX_EVIDENCE_FILES,
    max_file_bytes: int = DEFAULT_MAX_EVIDENCE_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_EVIDENCE_TOTAL_BYTES,
) -> EvidenceIntake:
    """Capture bounded regular workspace files once and record every rejection."""

    for label, value in (
        ("max_files", max_files),
        ("max_file_bytes", max_file_bytes),
        ("max_total_bytes", max_total_bytes),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{label} must be a positive integer")

    context = current_run()
    workspace = context.workspace.resolve()
    store = ArtifactStore(
        context.folder,
        workspace=workspace,
        forbidden_paths=context.client.protected_paths(context.folder),
        state_dir=context.client.state_dir,
    )
    records: list[EvidenceIntakeRecord] = []
    handles: list[ArtifactHandle] = []
    captured_bytes = 0

    for index, value in enumerate(evidence_paths):
        if index >= max_files:
            omitted = len(evidence_paths) - max_files
            records.append(
                _unavailable(
                    f"<{omitted} excess declaration{'s' if omitted != 1 else ''}>",
                    "file_count_limit",
                    f"declared evidence exceeds the {max_files}-file intake limit",
                )
            )
            break
        declared_path = str(value)
        if len(declared_path) > DEFAULT_MAX_EVIDENCE_PATH_CHARS:
            path_digest = hashlib.sha256(declared_path.encode()).hexdigest()[:16]
            records.append(
                _unavailable(
                    f"<overlong path chars={len(declared_path)} sha256={path_digest}>",
                    "unsafe_path",
                    "declared evidence path exceeds the bounded path length",
                )
            )
            continue

        publication_id = f"{context.operation_id}:declared-evidence:{index}"
        recovered = store.published(publication_id)
        if recovered is not None:
            data = recovered.read_bytes()
            handles.append(recovered)
            captured_bytes += len(data)
            records.append(
                EvidenceIntakeRecord(
                    declared_path=declared_path,
                    status="captured",
                    source_path=str(recovered.source_path),
                    artifact_name=recovered.name,
                    snapshot_path=str(recovered.path),
                    digest=recovered.digest,
                    size_bytes=len(data),
                )
            )
            continue

        candidate = _workspace_path(workspace, declared_path)
        if candidate is None or _has_symlink(workspace, candidate):
            records.append(
                _unavailable(
                    declared_path,
                    "unsafe_path",
                    "declared evidence must be a non-symlink path inside the workspace",
                )
            )
            continue

        try:
            source_stat = candidate.lstat()
        except FileNotFoundError:
            records.append(
                _unavailable(
                    declared_path, "missing", "declared evidence does not exist"
                )
            )
            continue
        except OSError as exc:
            records.append(
                _unavailable(declared_path, "read_failed", f"source stat failed: {exc}")
            )
            continue
        if not stat.S_ISREG(source_stat.st_mode):
            records.append(
                _unavailable(
                    declared_path,
                    "not_regular_file",
                    "declared evidence is not a regular file",
                )
            )
            continue
        if source_stat.st_size > max_file_bytes:
            records.append(
                _unavailable(
                    declared_path,
                    "file_too_large",
                    f"source exceeds the {max_file_bytes}-byte per-file limit",
                )
            )
            continue
        if captured_bytes + source_stat.st_size > max_total_bytes:
            records.append(
                _unavailable(
                    declared_path,
                    "total_byte_limit",
                    f"source exceeds the {max_total_bytes}-byte total intake limit",
                )
            )
            continue

        flags = os.O_RDONLY
        flags |= getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        try:
            descriptor = os.open(candidate, flags)
            with os.fdopen(descriptor, "rb") as stream:
                opened_stat = os.fstat(stream.fileno())
                if not stat.S_ISREG(opened_stat.st_mode):
                    records.append(
                        _unavailable(
                            declared_path,
                            "not_regular_file",
                            "declared evidence did not open as a regular file",
                        )
                    )
                    continue
                data = stream.read(max_file_bytes + 1)
        except OSError as exc:
            records.append(
                _unavailable(declared_path, "read_failed", f"source read failed: {exc}")
            )
            continue
        if len(data) > max_file_bytes:
            records.append(
                _unavailable(
                    declared_path,
                    "file_too_large",
                    f"source exceeds the {max_file_bytes}-byte per-file limit",
                )
            )
            continue
        if captured_bytes + len(data) > max_total_bytes:
            records.append(
                _unavailable(
                    declared_path,
                    "total_byte_limit",
                    f"source exceeds the {max_total_bytes}-byte total intake limit",
                )
            )
            continue

        name = _artifact_name(index, declared_path)
        try:
            handle = store.publish(
                Artifact.raw(candidate, name=name), data, publication_id
            )
        except ArtifactError as exc:
            records.append(
                _unavailable(
                    declared_path,
                    "unsafe_path",
                    f"source could not be published safely: {exc}",
                )
            )
            continue
        handles.append(handle)
        captured_bytes += len(data)
        records.append(
            EvidenceIntakeRecord(
                declared_path=declared_path,
                status="captured",
                source_path=str(handle.source_path),
                artifact_name=handle.name,
                snapshot_path=str(handle.path),
                digest=handle.digest,
                size_bytes=len(data),
            )
        )

    return EvidenceIntake(tuple(records), tuple(handles), captured_bytes)


def evidence_intake_context(intake: EvidenceIntake) -> list[dict[str, object]]:
    """Render compact provider-facing intake facts without reading live sources."""

    return [
        {
            "declared_path": record.declared_path,
            "status": record.status,
            "source_path": record.source_path,
            "artifact_name": record.artifact_name,
            "snapshot_path": record.snapshot_path,
            "digest": record.digest,
            "size_bytes": record.size_bytes,
            "unavailable_reason": record.unavailable_reason,
            "detail": record.detail,
        }
        for record in intake.records
    ]


def verify_evidence_intake(intake: EvidenceIntake) -> None:
    """Verify restored handles and their record mapping before provider use."""

    captured_records = tuple(
        record for record in intake.records if record.status == "captured"
    )
    if tuple(record.artifact_name for record in captured_records) != tuple(
        handle.name for handle in intake.handles
    ):
        raise ValueError("evidence intake records do not match captured handles")
    sizes = []
    for record, handle in zip(captured_records, intake.handles, strict=True):
        data = handle.read_bytes()
        if record.digest != handle.digest or record.size_bytes != len(data):
            raise ValueError("evidence intake metadata does not match captured bytes")
        sizes.append(len(data))
    if sum(sizes) != intake.captured_bytes:
        raise ValueError("evidence intake byte count does not match captured handles")


__all__ = [
    "EvidenceIntake",
    "EvidenceIntakeRecord",
    "capture_declared_evidence",
    "evidence_intake_context",
    "verify_evidence_intake",
]
