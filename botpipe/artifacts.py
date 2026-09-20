"""Provider destinations and immutable, durably published artifact versions."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, TypeAdapter

from .storage import sync_directory as _sync_dir


class ArtifactError(ValueError):
    """An artifact destination, content, or durable snapshot is invalid."""


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
        forbidden_paths: Sequence[Path | str] = (),
    ):
        self.folder = Path(folder).resolve()
        self.workspace = (
            Path(workspace).resolve() if workspace is not None else self.folder
        )
        self.root = self.folder / ".artifacts"
        self.forbidden_paths = tuple(Path(p).resolve() for p in forbidden_paths)

    def _destination(self, artifact: Artifact) -> Path:
        raw = Path(artifact.path)
        candidate = raw if raw.is_absolute() else self.folder / raw
        if ".." in raw.parts:
            raise ArtifactError(f"Artifact path cannot contain '..': {raw}")
        resolved = candidate.resolve()
        if not (
            resolved.is_relative_to(self.folder)
            or resolved.is_relative_to(self.workspace)
        ):
            raise ArtifactError(f"Artifact path escapes workspace: {raw}")
        # Provider output must be an ordinary file, never a symlink alias to state.
        for parent in (candidate, *candidate.parents):
            if parent.is_symlink():
                raise ArtifactError(f"Artifact path contains a symlink: {candidate}")
        relative = (
            resolved.relative_to(self.folder)
            if resolved.is_relative_to(self.folder)
            else resolved.relative_to(self.workspace)
        )
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
            if manifest["prepared"]:
                return {
                    record["name"]: Path(record["path"])
                    for record in manifest["declarations"]
                }
            records, paths = self._declarations(writes)
        else:
            records, paths = self._declarations(writes)
            manifest = {
                "declarations": records,
                "requested": requested,
                "prepared": False,
                "existing": [name for name, path in paths.items() if path.exists()],
            }
            _atomic(manifest_path, _json(manifest))
        for index, (name, path) in enumerate(paths.items()):
            _mkdir(path.parent)
            backup = operation / "previous" / str(index)
            if name in manifest["existing"] and not backup.exists():
                _mkdir(backup.parent)
                os.replace(path, backup)
                _sync_dir(path.parent)
                _sync_dir(backup.parent)
        manifest["prepared"] = True
        _atomic(manifest_path, _json(manifest))
        return paths

    def restore(self, operation_id: str) -> None:
        """Restore absent old destinations after a known terminal failure only."""
        operation = self._operation(operation_id)
        manifest_path = operation / "prepare.json"
        manifest = json.loads(manifest_path.read_text())
        if (operation / "capture.json").exists():
            raise ArtifactError("Cannot restore a published operation")
        # Fence capture before exposing any old bytes, including after a crash.
        manifest["restored"] = True
        _atomic(manifest_path, _json(manifest))
        for index, record in enumerate(manifest["declarations"]):
            path = self._destination(Artifact.from_record(record))
            backup = operation / "previous" / str(index)
            if backup.exists() and not path.exists():
                _atomic(path, backup.read_bytes())

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
        return ArtifactHandle(
            artifact.name,
            path,
            source,
            artifact.kind,
            digest,
            _schema_record(artifact.schema),
        )

    def capture(self, writes: Sequence[Artifact], operation_id: str) -> ArtifactMap:
        writes = tuple(writes)
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
            result = ArtifactMap.from_record(json.loads(manifest_path.read_text()))
            for handle in result.values():
                handle.read_bytes()
            return result
        records, paths = self._declarations(writes)
        if prepared["declarations"] != records:
            raise ArtifactError("Artifact destination changed since preparation")
        contents = []
        for artifact in writes:
            source = paths[artifact.name]
            if not source.exists():
                if artifact.required:
                    raise ArtifactError(
                        f"Required artifact was not written: {artifact.name} ({source})"
                    )
                continue
            data = source.read_bytes()
            _validate(data, artifact.kind, artifact.schema)
            contents.append((artifact, source, data))
        handles = ArtifactMap(
            {
                artifact.name: self._snapshot(artifact, source, data)
                for artifact, source, data in contents
            }
        )
        _atomic(manifest_path, _json(handles.to_record()))
        return handles

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
    "ArtifactError",
    "ArtifactHandle",
    "ArtifactMap",
    "ArtifactStore",
]
