"""Provider destinations and immutable, durably published artifact versions."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import stat
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, TypeAdapter

from .storage import sync_directory as _sync_dir


class ArtifactError(ValueError):
    """An artifact destination, content, or durable snapshot is invalid."""


class ArtifactCaptureRecoveryError(OSError):
    """A prepared capture cannot safely continue from mutable destinations."""


def _json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def _mkdir(path: Path) -> None:
    if path.exists():
        return
    _mkdir(path.parent)
    try:
        path.mkdir()
    except FileExistsError:
        pass
    _sync_dir(path.parent)


def _atomic(path: Path, data: bytes) -> None:
    _mkdir(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync_dir(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _entry(path: Path) -> dict[str, Any]:
    """Describe one directory entry without following a provider-created link."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {"kind": "absent"}
    common = {
        "device": info.st_dev,
        "inode": info.st_ino,
        "mode": info.st_mode,
        "size": info.st_size,
        "mtime_ns": info.st_mtime_ns,
    }
    if stat.S_ISREG(info.st_mode):
        return {
            "kind": "file",
            **common,
            "digest": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    if stat.S_ISLNK(info.st_mode):
        return {"kind": "symlink", **common, "target": os.readlink(path)}
    if stat.S_ISDIR(info.st_mode):
        return {"kind": "directory", **common}
    return {"kind": "other", **common}


def _same_entry(path: Path, expected: Mapping[str, Any]) -> bool:
    return _entry(path) == expected


def _assert_plain_parents(path: Path) -> None:
    """Reject redirection of an exact destination through a replaced parent."""
    for parent in path.parents:
        if parent.is_symlink():
            raise ArtifactError(f"Artifact path contains a symlink: {path}")


def _schema_record(schema: Any) -> dict[str, Any] | None:
    if schema is None:
        return None
    if isinstance(schema, Mapping):
        return dict(schema)
    record = {"json_schema": TypeAdapter(schema).json_schema()}
    if (
        isinstance(schema, type)
        and hasattr(schema, "__module__")
        and hasattr(schema, "__qualname__")
    ):
        record["python_type"] = f"{schema.__module__}:{schema.__qualname__}"
    return record


def _json_schema(schema: Any) -> dict[str, Any]:
    record = _schema_record(schema)
    assert record is not None
    return record.get("json_schema", record)


def _validate(data: bytes, kind: str, schema: Any) -> None:
    if kind == "raw":
        if schema is not None:
            raise ArtifactError("Raw artifacts do not support JSON schemas")
        return
    try:
        text = data.decode("utf-8")
        if kind == "json":
            value = json.loads(
                text,
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
            )
            if schema is not None:
                if isinstance(schema, Mapping):
                    import jsonschema

                    jsonschema.validate(value, _json_schema(schema))
                else:
                    TypeAdapter(schema).validate_python(value)
        elif schema is not None:
            raise ArtifactError("Schemas require a JSON artifact")
    except Exception as exc:
        raise ArtifactError(f"Invalid {kind} artifact: {exc}") from exc


@dataclass(frozen=True)
class Artifact:
    path: Path | str
    name: str | None = field(default=None, kw_only=True)
    kind: str = field(default="text", kw_only=True)
    required: bool = field(default=False, kw_only=True)
    schema: Any = field(default=None, kw_only=True, repr=False)

    def __post_init__(self) -> None:
        path = Path(self.path)
        if not str(self.path) or path.name in {"", ".", ".."}:
            raise ArtifactError("Artifact path must name a file")
        if self.kind not in {"text", "md", "json", "raw"}:
            raise ArtifactError(f"Unknown artifact kind: {self.kind}")
        name = self.name if self.name is not None else path.stem
        if not isinstance(name, str) or not name.strip():
            raise ArtifactError("Artifact name must be a nonempty string")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "name", name)

    @classmethod
    def json(cls, path: Path | str, *, schema: Any = None, **kwargs: Any) -> Artifact:
        return cls(path, kind="json", schema=schema, **kwargs)

    @classmethod
    def md(cls, path: Path | str, **kwargs: Any) -> Artifact:
        return cls(path, kind="md", **kwargs)

    @classmethod
    def text(cls, path: Path | str, **kwargs: Any) -> Artifact:
        return cls(path, kind="text", **kwargs)

    @classmethod
    def raw(cls, path: Path | str, **kwargs: Any) -> Artifact:
        return cls(path, kind="raw", **kwargs)

    def to_record(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "name": self.name,
            "kind": self.kind,
            "required": self.required,
            "schema": _schema_record(self.schema),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Artifact:
        return cls(**dict(record))


@dataclass(frozen=True)
class ArtifactHandle:
    name: str
    path: Path
    source_path: Path
    kind: str
    digest: str
    schema: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "source_path", Path(self.source_path))

    def read_bytes(self) -> bytes:
        data = self.path.read_bytes()
        if hashlib.sha256(data).hexdigest() != self.digest:
            raise ArtifactError(f"Artifact snapshot was modified: {self.path}")
        return data

    def read_text(self, encoding: str = "utf-8") -> str:
        return self.read_bytes().decode(encoding)

    def read_json(self) -> Any:
        return json.loads(self.read_text())

    def read_model(self, model: Any = None) -> Any:
        model = model or self.schema
        if isinstance(model, Mapping):
            reference = model.get("python_type")
            if not reference or "<locals>" in reference:
                raise ArtifactError("Pass a model type to read_model for this schema")
            module, qualified = reference.split(":", 1)
            model = importlib.import_module(module)
            for name in qualified.split("."):
                model = getattr(model, name)
        if model is None:
            raise ArtifactError("read_model requires a model type or declared schema")
        return TypeAdapter(model).validate_python(self.read_json())

    def to_record(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "source_path": str(self.source_path),
            "kind": self.kind,
            "digest": self.digest,
            "schema": _schema_record(self.schema),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> ArtifactHandle:
        return cls(**dict(record))


class ArtifactMap(Mapping[str, ArtifactHandle]):
    def __init__(self, handles: Mapping[str, ArtifactHandle] | None = None):
        self._handles = dict(handles or {})

    def __getitem__(self, key: str) -> ArtifactHandle:
        return self._handles[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._handles)

    def __len__(self) -> int:
        return len(self._handles)

    def __getattr__(self, name: str) -> ArtifactHandle:
        try:
            return self._handles[name]
        except KeyError:
            raise AttributeError(name) from None

    def to_record(self) -> dict[str, Any]:
        return {name: handle.to_record() for name, handle in self.items()}

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> ArtifactMap:
        return cls(
            {name: ArtifactHandle.from_record(value) for name, value in record.items()}
        )


class ArtifactStore:
    def __init__(
        self,
        folder: Path | str,
        *,
        workspace: Path | str | None = None,
        allowed_roots: Sequence[Path | str] = (),
        forbidden_paths: Sequence[Path | str] = (),
    ):
        self.folder = Path(folder).resolve()
        self.workspace = (
            Path(workspace).resolve() if workspace is not None else self.folder
        )
        self.root = self.folder / ".artifacts"
        self.allowed_roots = (
            self.folder,
            self.workspace,
            *(Path(p).resolve() for p in allowed_roots),
        )
        self.forbidden_paths = tuple(Path(p).resolve() for p in forbidden_paths)

    def _destination(self, artifact: Artifact) -> Path:
        raw = Path(artifact.path)
        candidate = raw if raw.is_absolute() else self.folder / raw
        if ".." in raw.parts:
            raise ArtifactError(f"Artifact path cannot contain '..': {raw}")
        resolved = candidate.resolve()
        root = next(
            (root for root in self.allowed_roots if resolved.is_relative_to(root)), None
        )
        if root is None:
            raise ArtifactError(f"Artifact path escapes workspace: {raw}")
        # Provider output must be an ordinary file, never a symlink alias to state.
        for parent in (candidate, *candidate.parents):
            if parent.is_symlink():
                raise ArtifactError(f"Artifact path contains a symlink: {candidate}")
        relative = resolved.relative_to(root)
        if any(
            part in {".artifacts", "receipts", ".receipts"} for part in relative.parts
        ):
            raise ArtifactError(f"Artifact path targets runtime metadata: {raw}")
        if resolved.name.endswith(
            (
                ".db",
                ".db-wal",
                ".db-shm",
                ".sqlite",
                ".sqlite-wal",
                ".sqlite-shm",
                ".sqlite3",
                ".sqlite3-wal",
                ".sqlite3-shm",
            )
        ):
            raise ArtifactError(f"Artifact path targets a database: {raw}")
        if any(
            resolved == path
            or resolved.is_relative_to(path)
            or (resolved.exists() and path.exists() and resolved.samefile(path))
            for path in self.forbidden_paths
        ):
            raise ArtifactError(f"Artifact path targets protected state: {raw}")
        if resolved.exists() and not resolved.is_file():
            raise ArtifactError(f"Artifact destination is not a file: {raw}")
        return resolved

    def _declarations(
        self, writes: Sequence[Artifact]
    ) -> tuple[list[dict[str, Any]], dict[str, Path]]:
        records, paths = [], {}
        for artifact in writes:
            if not isinstance(artifact, Artifact):
                raise TypeError("writes must contain Artifact declarations")
            if artifact.name in paths:
                raise ArtifactError(f"Duplicate artifact name: {artifact.name}")
            path = self._destination(artifact)
            if path in paths.values():
                raise ArtifactError(f"Duplicate artifact destination: {path}")
            paths[artifact.name] = path
            records.append({**artifact.to_record(), "path": str(path)})
        return records, paths

    def _operation(self, operation_id: str) -> Path:
        if not isinstance(operation_id, str) or not operation_id:
            raise ArtifactError("A nonempty operation_id is required")
        return (
            self.root / "operations" / hashlib.sha256(operation_id.encode()).hexdigest()
        )

    def destinations(self, writes: Sequence[Artifact]) -> dict[str, Path]:
        """Resolve declarations without starting or resuming a preparation."""
        _, paths = self._declarations(tuple(writes))
        return paths

    def prepare(self, writes: Sequence[Artifact], operation_id: str) -> dict[str, Path]:
        writes = tuple(writes)
        requested = [artifact.to_record() for artifact in writes]
        operation = self._operation(operation_id)
        manifest_path = operation / "prepare.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            if manifest["requested"] != requested:
                raise ArtifactError(
                    "Artifact declarations changed for an existing operation"
                )
            if manifest.get("restored"):
                raise ArtifactError(
                    "Artifact preparation was restored; use a new operation attempt"
                )
            if (operation / "rollback.json").exists():
                raise ArtifactError(
                    "Artifact preparation was rolled back; use a new operation attempt"
                )
            if manifest["prepared"]:
                _sync_dir(manifest_path.parent)
                return {
                    record["name"]: Path(record["path"])
                    for record in manifest["declarations"]
                }
            records, paths = self._declarations(writes)
        else:
            records, paths = self._declarations(writes)
            _mkdir(operation)
            for path in paths.values():
                _mkdir(path.parent)
            # Revalidate after creating parents, before inventorying or moving a
            # destination. Rollback uses atomic renames, never copy-and-unlink.
            records, paths = self._declarations(writes)
            device = operation.stat().st_dev
            for path in paths.values():
                if path.parent.stat().st_dev != device:
                    raise ArtifactError(
                        f"Artifact destination crosses the transaction filesystem: {path}"
                    )
            entries = [
                {"name": name, "path": str(path), "previous": _entry(path)}
                for name, path in paths.items()
            ]
            manifest = {
                "version": 2,
                "declarations": records,
                "requested": requested,
                "prepared": False,
                "existing": [
                    entry["name"]
                    for entry in entries
                    if entry["previous"]["kind"] != "absent"
                ],
                "entries": entries,
            }
            _atomic(manifest_path, _json(manifest))
        entries = manifest.get("entries")
        if entries is None:
            # Compatibility with an interrupted operation from the original
            # manifest format. Such a manifest has not yet moved all files.
            entries = []
            for index, (name, path) in enumerate(paths.items()):
                backup = operation / "previous" / str(index)
                previous_path = backup if backup.exists() else path
                entries.append(
                    {
                        "name": name,
                        "path": str(path),
                        "previous": (
                            _entry(previous_path)
                            if name in manifest["existing"]
                            else {"kind": "absent"}
                        ),
                    }
                )
            manifest["entries"] = entries
            manifest["version"] = 2
            _atomic(manifest_path, _json(manifest))
        for index, entry in enumerate(entries):
            path = Path(entry["path"])
            _assert_plain_parents(path)
            backup = operation / "previous" / str(index)
            previous = entry["previous"]
            if previous["kind"] == "file" and not backup.exists():
                if not _same_entry(path, previous):
                    raise ArtifactError(
                        f"Artifact destination changed during preparation: {path}"
                    )
                _mkdir(backup.parent)
                os.replace(path, backup)
                _sync_dir(path.parent)
                _sync_dir(backup.parent)
            elif previous["kind"] == "file":
                if not _same_entry(backup, previous) or path.exists():
                    raise ArtifactError(
                        f"Artifact backup conflicts with its inventory: {path}"
                    )
                _sync_dir(path.parent)
                _sync_dir(backup.parent)
            elif previous["kind"] == "absent":
                if path.exists() or path.is_symlink():
                    raise ArtifactError(
                        f"Artifact destination appeared during preparation: {path}"
                    )
            else:
                raise ArtifactError(
                    f"Artifact destination was not an ordinary file: {path}"
                )
        manifest["prepared"] = True
        _atomic(manifest_path, _json(manifest))
        return paths

    def restore(self, operation_id: str) -> None:
        """Restore absent old destinations after a known terminal failure only."""
        operation = self._operation(operation_id)
        manifest_path = operation / "prepare.json"
        manifest = json.loads(manifest_path.read_text())
        if (operation / "capture.json").exists() or (
            operation / "capture.pending.json"
        ).exists():
            raise ArtifactError("Cannot restore an operation with a prepared capture")
        if manifest.get("restore_completed"):
            # The first restore may have hard-linked backup and destination.
            # Once completion is durable, later destination edits must not be
            # mistaken for backup corruption during a replay.
            _sync_dir(manifest_path.parent)
            return
        # Fence capture before exposing any old bytes, including after a crash.
        manifest["restored"] = True
        _atomic(manifest_path, _json(manifest))
        entries = manifest.get("entries")
        if entries is None:
            existing = set(manifest.get("existing", ()))
            entries = [
                {
                    "name": record["name"],
                    "path": record["path"],
                    "previous": (
                        _entry(operation / "previous" / str(index))
                        if record["name"] in existing
                        and (operation / "previous" / str(index)).exists()
                        else _entry(Path(record["path"]))
                        if record["name"] in existing
                        else {"kind": "absent"}
                    ),
                }
                for index, record in enumerate(manifest["declarations"])
            ]
            manifest["version"] = 2
            manifest["entries"] = entries
            _atomic(manifest_path, _json(manifest))
        if len(entries) != len(manifest["declarations"]):
            raise ArtifactError("Artifact restoration inventory is incomplete")
        for index, (record, entry) in enumerate(
            zip(manifest["declarations"], entries, strict=True)
        ):
            path = self._destination(Artifact.from_record(record))
            if entry["name"] != record["name"] or entry["path"] != str(path):
                raise ArtifactError(
                    "Artifact restoration inventory does not match preparation"
                )
            _assert_plain_parents(path)
            backup = operation / "previous" / str(index)
            previous = entry["previous"]
            if previous["kind"] == "absent":
                # Conservative restore never removes an entry that appeared
                # after preparation; there are no old bytes to put back.
                continue
            if previous["kind"] != "file":
                raise ArtifactError(f"Invalid previous artifact inventory: {path}")
            if backup.exists():
                if not _same_entry(backup, previous):
                    raise ArtifactError(f"Artifact backup was modified: {backup}")
                if path.exists() or path.is_symlink():
                    # A possibly live provider owns any entry now present at
                    # the destination. Conservative restore never overwrites,
                    # removes, or rejects that entry.
                    continue
                else:
                    try:
                        # Preparation verifies that backup and destination share
                        # a filesystem. link() publishes the complete old entry
                        # only while the destination is still absent, avoiding
                        # the check-then-replace overwrite race in _atomic().
                        os.link(backup, path, follow_symlinks=False)
                    except FileExistsError as exc:
                        raise ArtifactError(
                            f"Artifact destination conflicts with restoration: {path}"
                        ) from exc
                _sync_dir(path.parent)
                _sync_dir(backup.parent)
            elif not _same_entry(path, previous):
                # A partially completed preparation may not have moved this
                # entry yet. Otherwise, losing both copies is an integrity error.
                raise ArtifactError(
                    f"Artifact restoration conflicts with its inventory: {path}"
                )
            else:
                _sync_dir(path.parent)
        manifest["restore_completed"] = True
        _atomic(manifest_path, _json(manifest))

    def rollback(self, operation_id: str) -> None:
        """Quarantine one known-stopped attempt and restore all prior files.

        The caller must establish that the provider can no longer write these
        destinations. Unlike :meth:`restore`, this method deliberately removes
        present attempt outputs from their declared paths.
        """
        operation = self._operation(operation_id)
        prepare_path = operation / "prepare.json"
        if not prepare_path.exists():
            raise ArtifactError("Artifacts must be prepared before rollback")
        if (operation / "capture.json").exists() or (
            operation / "capture.pending.json"
        ).exists():
            raise ArtifactError("Cannot roll back an operation with a prepared capture")
        prepared = json.loads(prepare_path.read_text())
        if not prepared.get("prepared") or prepared.get("restored"):
            raise ArtifactError("Artifact preparation cannot be rolled back")
        entries = prepared.get("entries")
        if entries is None:
            entries = []
            existing = set(prepared.get("existing", ()))
            for index, record in enumerate(prepared["declarations"]):
                path = Path(record["path"])
                backup = operation / "previous" / str(index)
                if record["name"] in existing and not backup.exists():
                    raise ArtifactError("Artifact preparation lacks a rollback backup")
                entries.append(
                    {
                        "name": record["name"],
                        "path": str(path),
                        "previous": (
                            _entry(backup)
                            if record["name"] in existing
                            else {"kind": "absent"}
                        ),
                    }
                )
            prepared["version"] = 2
            prepared["entries"] = entries
            _atomic(prepare_path, _json(prepared))

        rollback_path = operation / "rollback.json"
        if rollback_path.exists():
            rollback = json.loads(rollback_path.read_text())
            if rollback["declarations"] != prepared["declarations"]:
                raise ArtifactError("Artifact rollback declaration conflict")
        else:
            attempts = []
            device = operation.stat().st_dev
            for entry in entries:
                path = Path(entry["path"])
                _assert_plain_parents(path)
                if not path.parent.exists() or path.parent.stat().st_dev != device:
                    raise ArtifactError(
                        f"Artifact destination crosses the transaction filesystem: {path}"
                    )
                attempts.append(
                    {
                        "name": entry["name"],
                        "path": str(path),
                        "attempted": _entry(path),
                    }
                )
            rollback = {
                "version": 1,
                "declarations": prepared["declarations"],
                "attempts": attempts,
                "completed": False,
            }
            # Fence capture before moving any attempted output.
            _atomic(rollback_path, _json(rollback))
        _sync_dir(rollback_path.parent)

        attempts = rollback["attempts"]
        if len(attempts) != len(entries):
            raise ArtifactError("Artifact rollback inventory is incomplete")
        quarantine_root = operation / "quarantine"
        _mkdir(quarantine_root)
        for index, (entry, attempt) in enumerate(zip(entries, attempts, strict=True)):
            path = Path(entry["path"])
            if attempt["name"] != entry["name"] or attempt["path"] != str(path):
                raise ArtifactError(
                    "Artifact rollback inventory does not match preparation"
                )
            _assert_plain_parents(path)
            previous = entry["previous"]
            attempted = attempt["attempted"]
            backup = operation / "previous" / str(index)
            quarantine = quarantine_root / str(index)

            if attempted["kind"] == "absent":
                if quarantine.exists() or quarantine.is_symlink():
                    raise ArtifactError(f"Unexpected artifact quarantine: {quarantine}")
            elif quarantine.exists() or quarantine.is_symlink():
                if not _same_entry(quarantine, attempted):
                    raise ArtifactError(
                        f"Artifact quarantine was modified: {quarantine}"
                    )
                _sync_dir(path.parent)
                _sync_dir(quarantine.parent)
            else:
                if not _same_entry(path, attempted):
                    raise ArtifactError(
                        f"Artifact destination changed during rollback: {path}"
                    )
                os.replace(path, quarantine)
                _sync_dir(path.parent)
                _sync_dir(quarantine.parent)

            if previous["kind"] == "file":
                if backup.exists():
                    if path.exists() or path.is_symlink():
                        raise ArtifactError(
                            f"Artifact destination conflicts with rollback: {path}"
                        )
                    if not _same_entry(backup, previous):
                        raise ArtifactError(f"Artifact backup was modified: {backup}")
                    os.replace(backup, path)
                    _sync_dir(backup.parent)
                    _sync_dir(path.parent)
                elif not _same_entry(path, previous):
                    raise ArtifactError(
                        f"Restored artifact conflicts with its inventory: {path}"
                    )
                else:
                    _sync_dir(backup.parent)
                    _sync_dir(path.parent)
            elif previous["kind"] == "absent":
                if path.exists() or path.is_symlink():
                    raise ArtifactError(f"New artifact remains after rollback: {path}")
            else:
                raise ArtifactError(f"Invalid previous artifact inventory: {path}")

        rollback["completed"] = True
        _atomic(rollback_path, _json(rollback))

    def _snapshot(
        self, artifact: Artifact, source: Path, data: bytes
    ) -> ArtifactHandle:
        digest = hashlib.sha256(data).hexdigest()
        path = self.root / "blobs" / digest[:2] / digest / source.name
        if path.exists():
            if path.read_bytes() != data:
                raise ArtifactError(f"Artifact snapshot was modified: {path}")
        else:
            _atomic(path, data)
            path.chmod(0o444)
        _sync_dir(path.parent)
        return ArtifactHandle(
            artifact.name,
            path,
            source,
            artifact.kind,
            digest,
            _schema_record(artifact.schema),
        )

    def _capture_source(self, source: Path, *, digest: str, length: int) -> bytes:
        """Read a missing prepared blob only if its exact source is unchanged."""
        try:
            _assert_plain_parents(source)
            before = source.lstat()
            if not stat.S_ISREG(before.st_mode):
                raise ArtifactCaptureRecoveryError(
                    f"Prepared artifact source is no longer a file: {source}"
                )
            data = source.read_bytes()
            after = source.lstat()
        except ArtifactCaptureRecoveryError:
            raise
        except OSError as exc:
            raise ArtifactCaptureRecoveryError(
                f"Prepared artifact source is unavailable: {source}"
            ) from exc
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_size,
            value.st_mtime_ns,
        )
        if identity(before) != identity(after):
            raise ArtifactCaptureRecoveryError(
                f"Prepared artifact source changed while being recovered: {source}"
            )
        if len(data) != length or hashlib.sha256(data).hexdigest() != digest:
            raise ArtifactCaptureRecoveryError(
                f"Prepared artifact source no longer matches its capture intent: {source}"
            )
        return data

    @staticmethod
    def _approved_digests(writes, expected):
        if expected is None:
            return None
        if type(expected) is not dict or set(expected) != {a.name for a in writes}:
            raise ArtifactError(
                "Artifact reconciliation must name every declared output"
            )
        for artifact in writes:
            digest = expected[artifact.name]
            if digest is None:
                if artifact.required:
                    raise ArtifactError(
                        f"Required artifact cannot be absent: {artifact.name}"
                    )
            elif (
                type(digest) is not str
                or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)
            ):
                raise ArtifactError(
                    f"Artifact reconciliation needs a SHA-256 digest: {artifact.name}"
                )
        return dict(expected)

    def check_capture_digests(self, writes, expected):
        """Check an operator's complete selection without publishing or mutating it."""
        approved = self._approved_digests(writes, expected)
        if approved is None:
            raise ArtifactError("Artifact reconciliation requires explicit digests")
        _, paths = self._declarations(writes)
        for artifact in writes:
            source = paths[artifact.name]
            digest = approved[artifact.name]
            if digest is None:
                if source.exists() or source.is_symlink():
                    raise ArtifactError(
                        f"Artifact was approved as absent but exists: {artifact.name}"
                    )
            else:
                try:
                    self._capture_source(
                        source, digest=digest, length=source.stat().st_size
                    )
                except OSError as exc:
                    raise ArtifactError(
                        f"Artifact does not match its approved digest: {artifact.name}"
                    ) from exc
        return approved

    def has_capture_evidence(self, operation_id: str) -> bool:
        operation = self._operation(operation_id)
        return any(
            (operation / name).exists()
            for name in ("capture.json", "capture.pending.json")
        )

    def capture(
        self,
        writes: Sequence[Artifact],
        operation_id: str,
        *,
        recover: bool = False,
        expected_digests: Mapping[str, str | None] | None = None,
    ) -> ArtifactMap:
        writes = tuple(writes)
        approved = self._approved_digests(writes, expected_digests)
        requested = [artifact.to_record() for artifact in writes]
        operation = self._operation(operation_id)
        prepare_path = operation / "prepare.json"
        if not prepare_path.exists():
            raise ArtifactError("Artifacts must be prepared before provider dispatch")
        prepared = json.loads(prepare_path.read_text())
        if (
            not prepared["prepared"]
            or prepared.get("restored")
            or prepared["requested"] != requested
        ):
            raise ArtifactError("Artifact preparation does not match this capture")
        manifest_path = operation / "capture.json"
        if manifest_path.exists():
            result = self.captured(operation_id)
            assert result is not None
            return result
        if (operation / "rollback.json").exists():
            raise ArtifactError("Cannot capture a rolled-back operation")
        intent_path = operation / "capture.pending.json"
        fresh: dict[str, bytes] = {}
        if intent_path.exists():
            try:
                intent = json.loads(intent_path.read_text())
                if not isinstance(intent, dict):
                    raise TypeError("capture intent must be an object")
                if intent.get("version") != 1:
                    raise TypeError("unsupported capture intent version")
            except (OSError, ValueError, TypeError) as exc:
                raise ArtifactCaptureRecoveryError(
                    "Prepared artifact capture intent is unreadable"
                ) from exc
            if intent.get("declarations") != prepared["declarations"]:
                raise ArtifactCaptureRecoveryError(
                    "Prepared artifact capture does not match its declarations"
                )
        else:
            if recover and writes and approved is None:
                raise ArtifactCaptureRecoveryError(
                    "Completed provider response has no durable artifact inventory; "
                    "reconcile all declared artifact digests before resuming"
                )
            try:
                records, paths = self._declarations(writes)
                if prepared["declarations"] != records:
                    raise ArtifactError(
                        "Artifact destination changed since preparation"
                    )
            except ArtifactError as exc:
                if approved is not None:
                    raise ArtifactCaptureRecoveryError(
                        "Artifact destination changed after operator approval"
                    ) from exc
                raise
            contents = []
            for artifact in writes:
                source = paths[artifact.name]
                if not source.exists():
                    if approved is not None and approved[artifact.name] is not None:
                        raise ArtifactCaptureRecoveryError(
                            f"Approved artifact is missing: {artifact.name}"
                        )
                    if artifact.required:
                        raise ArtifactError(
                            f"Required artifact was not written: {artifact.name} ({source})"
                        )
                    continue
                if approved is not None and approved[artifact.name] is None:
                    raise ArtifactCaptureRecoveryError(
                        f"Artifact approved as absent now exists: {artifact.name}"
                    )
                if approved is not None:
                    try:
                        data = self._capture_source(
                            source,
                            digest=approved[artifact.name],
                            length=source.stat().st_size,
                        )
                    except OSError as exc:
                        raise ArtifactCaptureRecoveryError(
                            f"Artifact changed after operator approval: {artifact.name}"
                        ) from exc
                else:
                    data = source.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                _validate(data, artifact.kind, artifact.schema)
                contents.append(
                    {
                        "name": artifact.name,
                        "source_path": str(source),
                        "digest": digest,
                        "length": len(data),
                    }
                )
                fresh[artifact.name] = data
            intent = {
                "version": 1,
                "source": "operator" if approved is not None else "provider",
                "declarations": records,
                "contents": contents,
            }
            # The complete validated set is durable before publishing any blob.
            _atomic(intent_path, _json(intent))

        if approved is not None:
            observed = {artifact.name: None for artifact in writes}
            try:
                observed.update(
                    {item["name"]: item["digest"] for item in intent["contents"]}
                )
            except (KeyError, TypeError) as exc:
                raise ArtifactCaptureRecoveryError(
                    "Invalid reconciled capture inventory"
                ) from exc
            if observed != approved or intent.get("source") != "operator":
                raise ArtifactCaptureRecoveryError(
                    "Capture inventory differs from operator reconciliation"
                )

        artifacts = {artifact.name: artifact for artifact in writes}
        handles = {}
        try:
            contents = intent["contents"]
            if not isinstance(contents, list):
                raise TypeError("contents must be a list")
            seen = set()
            for item in contents:
                name = item["name"]
                source = Path(item["source_path"])
                digest = item["digest"]
                length = item["length"]
                if (
                    name in seen
                    or name not in artifacts
                    or not isinstance(digest, str)
                    or len(digest) != 64
                    or any(character not in "0123456789abcdef" for character in digest)
                    or not isinstance(length, int)
                    or isinstance(length, bool)
                    or length < 0
                ):
                    raise TypeError("invalid capture content record")
                declaration = next(
                    record
                    for record in prepared["declarations"]
                    if record["name"] == name
                )
                if str(source) != declaration["path"]:
                    raise TypeError("capture source does not match its declaration")
                seen.add(name)
                blob = self.root / "blobs" / digest[:2] / digest / source.name
                if blob.exists():
                    data = blob.read_bytes()
                    if (
                        len(data) != length
                        or hashlib.sha256(data).hexdigest() != digest
                    ):
                        raise ArtifactCaptureRecoveryError(
                            f"Prepared artifact blob was modified: {blob}"
                        )
                elif name in fresh:
                    data = fresh[name]
                else:
                    data = self._capture_source(source, digest=digest, length=length)
                # Recovery must enforce the same content contract as the fresh
                # path even if the durable intent or blob was damaged later.
                _validate(data, artifacts[name].kind, artifacts[name].schema)
                handle = self._snapshot(artifacts[name], source, data)
                if handle.digest != digest:
                    raise ArtifactCaptureRecoveryError(
                        f"Prepared artifact digest changed during capture: {source}"
                    )
                handles[name] = handle
            required = {artifact.name for artifact in writes if artifact.required}
            if not required <= seen:
                raise TypeError("capture intent omits a required artifact")
        except ArtifactCaptureRecoveryError:
            raise
        except (ArtifactError, KeyError, OSError, StopIteration, TypeError) as exc:
            raise ArtifactCaptureRecoveryError(
                "Prepared artifact capture cannot be recovered safely"
            ) from exc
        handles = ArtifactMap(handles)
        _atomic(manifest_path, _json(handles.to_record()))
        return handles

    def captured(self, operation_id: str) -> ArtifactMap | None:
        """Recover a durable capture without consulting mutable destinations."""
        manifest_path = self._operation(operation_id) / "capture.json"
        if not manifest_path.exists():
            return None
        result = ArtifactMap.from_record(json.loads(manifest_path.read_text()))
        for handle in result.values():
            handle.read_bytes()
            _sync_dir(handle.path.parent)
        # A prior call may have completed os.replace before directory fsync
        # failed. Repeating the sync makes recovery safe before ledger commit.
        _sync_dir(manifest_path.parent)
        return result

    def published(self, operation_id: str) -> ArtifactHandle | None:
        """Recover a managed publication that preceded its ledger commit."""
        manifest_path = self._operation(operation_id) / "publish.json"
        if not manifest_path.exists():
            return None
        record = json.loads(manifest_path.read_text())
        handle = ArtifactHandle.from_record(record["handle"])
        handle.read_bytes()
        return handle

    def publish(
        self, artifact: Artifact, value: Any, operation_id: str
    ) -> ArtifactHandle:
        """Publish a managed logical version without mutating its source destination."""
        source = self._destination(artifact)
        if isinstance(value, BaseModel):
            value = value.model_dump(mode="json")
        data = (
            _json(value)
            if artifact.kind == "json"
            else value
            if isinstance(value, bytes)
            else str(value).encode()
        )
        _validate(data, artifact.kind, artifact.schema)
        operation = self._operation(operation_id)
        manifest_path = operation / "publish.json"
        declaration = {**artifact.to_record(), "path": str(source)}
        if manifest_path.exists():
            record = json.loads(manifest_path.read_text())
            if (
                record["declaration"] != declaration
                or record["handle"]["digest"] != hashlib.sha256(data).hexdigest()
            ):
                raise ArtifactError(
                    "Published artifact changed for an existing operation"
                )
            handle = ArtifactHandle.from_record(record["handle"])
            handle.read_bytes()
            return handle
        handle = self._snapshot(artifact, source, data)
        _atomic(
            manifest_path,
            _json({"declaration": declaration, "handle": handle.to_record()}),
        )
        return handle

    def materialize(
        self, handle: ArtifactHandle, destination: Path | str | None = None
    ) -> Path:
        """Write a friendly mutable alias; its immutable version remains unchanged."""
        path = self._destination(Artifact(destination or handle.source_path))
        _atomic(path, handle.read_bytes())
        return path


__all__ = [
    "Artifact",
    "ArtifactCaptureRecoveryError",
    "ArtifactError",
    "ArtifactHandle",
    "ArtifactMap",
    "ArtifactStore",
]
