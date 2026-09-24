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
    """A pending capture cannot safely continue from mutable destinations."""


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

    def destinations(
        self, writes: Sequence[Artifact], *, create_parents: bool = False
    ) -> dict[str, Path]:
        """Validate destinations, optionally creating their parent directories."""
        writes = tuple(writes)
        _, paths = self._declarations(writes)
        if create_parents:
            for path in paths.values():
                _mkdir(path.parent)
            # Parent creation can race with another filesystem writer. Validate
            # again before handing paths to a provider.
            _, paths = self._declarations(writes)
        return paths

    def check_legacy_operation(self, operation_id: str) -> None:
        """Reject unfinished state from the removed prepare/rollback protocol."""
        operation = self._operation(operation_id)
        if (operation / "rollback.json").exists() or (
            (operation / "prepare.json").exists()
            and not (operation / "capture.json").exists()
        ):
            raise ArtifactError(
                "Unsupported legacy artifact preparation or rollback state; "
                "cannot resume this operation with this version; stored files "
                "are unchanged"
            )

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
        """Read a missing pending blob only if its exact source is unchanged."""
        try:
            _assert_plain_parents(source)
            before = source.lstat()
            if not stat.S_ISREG(before.st_mode):
                raise ArtifactCaptureRecoveryError(
                    f"Pending artifact source is no longer a file: {source}"
                )
            data = source.read_bytes()
            after = source.lstat()
        except ArtifactCaptureRecoveryError:
            raise
        except OSError as exc:
            raise ArtifactCaptureRecoveryError(
                f"Pending artifact source is unavailable: {source}"
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
                f"Pending artifact source changed while being recovered: {source}"
            )
        if len(data) != length or hashlib.sha256(data).hexdigest() != digest:
            raise ArtifactCaptureRecoveryError(
                f"Pending artifact source no longer matches its capture intent: {source}"
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
        self.check_legacy_operation(operation_id)
        manifest_path = operation / "capture.json"
        intent_path = operation / "capture.pending.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
            except (OSError, ValueError, TypeError) as exc:
                raise ArtifactCaptureRecoveryError(
                    "Artifact capture manifest is unreadable"
                ) from exc
            if (
                isinstance(manifest, dict)
                and manifest.get("version") == 2
                and manifest.get("requested") != requested
            ):
                raise ArtifactError(
                    "Artifact declarations changed for an existing operation"
                )
            result = self.captured(operation_id)
            assert result is not None
            return result
        fresh: dict[str, bytes] = {}
        if intent_path.exists():
            try:
                intent = json.loads(intent_path.read_text())
                if not isinstance(intent, dict):
                    raise TypeError("capture intent must be an object")
                if intent.get("version") != 2:
                    raise TypeError("unsupported capture intent version")
            except (OSError, ValueError, TypeError) as exc:
                raise ArtifactCaptureRecoveryError(
                    "Pending artifact capture intent is unreadable"
                ) from exc
            if intent.get("requested") != requested:
                raise ArtifactCaptureRecoveryError(
                    "Pending artifact capture does not match its declarations"
                )
            declarations = intent.get("declarations")
            if not isinstance(declarations, list) or len(declarations) != len(writes):
                raise ArtifactCaptureRecoveryError(
                    "Pending artifact capture has an invalid declaration inventory"
                )
            for artifact, declaration in zip(writes, declarations, strict=True):
                raw = Path(artifact.path)
                candidate = raw if raw.is_absolute() else self.folder / raw
                expected = {
                    **artifact.to_record(),
                    "path": str(Path(os.path.abspath(candidate))),
                }
                if declaration != expected:
                    raise ArtifactCaptureRecoveryError(
                        "Pending artifact capture has an invalid declaration inventory"
                    )
        else:
            if recover and writes and approved is None:
                raise ArtifactCaptureRecoveryError(
                    "Completed provider response has no durable artifact inventory; "
                    "reconcile all declared artifact digests before resuming"
                )
            try:
                records, paths = self._declarations(writes)
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
                            f"Required artifact is missing: {artifact.name} ({source})"
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
                "version": 2,
                "source": "operator" if approved is not None else "provider",
                "requested": requested,
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
                    for record in intent["declarations"]
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
                            f"Pending artifact blob was modified: {blob}"
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
                        f"Pending artifact digest changed during capture: {source}"
                    )
                handles[name] = handle
            required = {artifact.name for artifact in writes if artifact.required}
            if not required <= seen:
                raise TypeError("capture intent omits a required artifact")
        except ArtifactCaptureRecoveryError:
            raise
        except (ArtifactError, KeyError, OSError, StopIteration, TypeError) as exc:
            raise ArtifactCaptureRecoveryError(
                "Pending artifact capture cannot be recovered safely"
            ) from exc
        handles = ArtifactMap(handles)
        _atomic(
            manifest_path,
            _json(
                {
                    "version": 2,
                    "requested": requested,
                    "artifacts": handles.to_record(),
                }
            ),
        )
        return handles

    def captured(self, operation_id: str) -> ArtifactMap | None:
        """Recover a durable capture without consulting mutable destinations."""
        manifest_path = self._operation(operation_id) / "capture.json"
        if not manifest_path.exists():
            return None
        record = json.loads(manifest_path.read_text())
        if (
            isinstance(record, dict)
            and record.get("version") == 2
            and "artifacts" in record
        ):
            record = record["artifacts"]
        result = ArtifactMap.from_record(record)
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
