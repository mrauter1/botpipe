"""Artifact declarations and resolved handles."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Iterator, Literal, Mapping

from pydantic import BaseModel, ValidationError

from .errors import WorkflowExecutionError

ArtifactKind = Literal["text", "markdown", "json", "raw"]
if TYPE_CHECKING:
    from .context import Context
    from .steps import Step


class Artifact:
    """Artifact declaration."""

    __slots__ = (
        "template",
        "name",
        "kind",
        "schema",
        "required",
        "owner",
        "owner_step",
        "qualified_name",
    )

    def __init__(
        self,
        template: str,
        name: str | None = None,
        *,
        kind: ArtifactKind = "text",
        schema: type[BaseModel] | dict[str, object] | None = None,
        required: bool = False,
        owner: Step | None = None,
        owner_step: str | None = None,
        qualified_name: str | None = None,
    ) -> None:
        self.template = template
        self.name = name
        self.kind = kind
        self.schema = schema
        self.required = required
        self.owner = owner
        self.owner_step = owner_step
        self.qualified_name = qualified_name

    @classmethod
    def text(
        cls,
        path: str,
        *,
        required: bool = False,
        name: str | None = None,
    ) -> Artifact:
        return cls(path, name=name, kind="text", required=required)

    @classmethod
    def md(
        cls,
        path: str,
        *,
        required: bool = False,
        name: str | None = None,
    ) -> Artifact:
        return cls(path, name=name, kind="markdown", required=required)

    @classmethod
    def json(
        cls,
        path: str,
        *,
        schema: type[BaseModel] | dict[str, object] | None = None,
        required: bool = False,
        name: str | None = None,
    ) -> Artifact:
        return cls(path, name=name, kind="json", schema=schema, required=required)

    @classmethod
    def raw(
        cls,
        path: str,
        *,
        required: bool = False,
        name: str | None = None,
    ) -> Artifact:
        return cls(path, name=name, kind="raw", required=required)

    def bind_name(self, name: str) -> None:
        if self.name is None:
            self.name = name
        elif self.name != name:
            raise ValueError(f"artifact already named {self.name!r}; cannot rename to {name!r}")

    def bind_owner_step(self, step_name: str) -> None:
        self.owner_step = step_name
        if self.name is None:
            raise ValueError("cannot bind owner step before artifact name is bound")
        self.qualified_name = f"{step_name}.{self.name}"

    def __repr__(self) -> str:
        return (
            f"Artifact(template={self.template!r}, name={self.name!r}, "
            f"kind={self.kind!r}, required={self.required!r}, "
            f"qualified_name={self.qualified_name!r})"
        )


@dataclass(frozen=True, slots=True)
class ArtifactValidationResult:
    """Validation result for one resolved artifact."""

    ok: bool
    path: Path
    artifact_name: str
    qualified_name: str | None = None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ArtifactHandle:
    """Concrete resolved artifact handle."""

    name: str
    path: Path
    artifact: Artifact | None = None

    def read_text(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def write_text(self, content: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(content, encoding="utf-8")

    def append(self, content: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(content)

    def exists(self) -> bool:
        return self.path.exists()

    def read_json(self) -> object:
        return json.loads(self.read_text())

    def write_json(self, value: object) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def read_model(self) -> BaseModel:
        if self.artifact is None or self.artifact.schema is None:
            raise TypeError("artifact has no schema")
        if not isinstance(self.artifact.schema, type) or not issubclass(self.artifact.schema, BaseModel):
            raise TypeError("read_model only supports Pydantic BaseModel schemas")
        payload = self.read_json()
        return self.artifact.schema.model_validate(payload)

    def write_model(self, model_or_mapping: BaseModel | Mapping[str, object]) -> None:
        if isinstance(model_or_mapping, BaseModel):
            self.write_json(model_or_mapping.model_dump(mode="json"))
        else:
            self.write_json(dict(model_or_mapping))

    def validate(self) -> ArtifactValidationResult:
        return validate_artifact_handle(self)


class ResolvedArtifacts(Mapping[str, ArtifactHandle]):
    """Read-only mapping with attribute access."""

    def __init__(self, handles: Mapping[str, ArtifactHandle]) -> None:
        self._handles = dict(handles)

    def __getitem__(self, key: str) -> ArtifactHandle:
        return self._handles[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._handles)

    def __len__(self) -> int:
        return len(self._handles)

    def __getattr__(self, item: str) -> ArtifactHandle:
        try:
            return self._handles[item]
        except KeyError as exc:
            raise AttributeError(item) from exc

    def subset(self, names: Iterable[str]) -> "ResolvedArtifacts":
        return ResolvedArtifacts({name: self._handles[name] for name in names})


@dataclass(frozen=True, slots=True)
class CompiledArtifact:
    """Immutable compiled artifact metadata."""

    name: str
    template: str
    kind: ArtifactKind
    schema: type[BaseModel] | dict[str, object] | None
    required: bool
    owner_step: str | None
    qualified_name: str | None
    workflow_level: bool
    producer_steps: tuple[str, ...]


_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


def resolve_artifact_template(template: str | Artifact, context: Context) -> Path:
    """Resolve a template against runtime context."""

    artifact = template if isinstance(template, Artifact) else None
    raw_template = artifact.template if artifact is not None else template
    candidate = Path(raw_template)
    if candidate.is_absolute():
        return candidate
    if "{" not in raw_template and "}" not in raw_template and artifact is not None and artifact.owner_step is not None:
        return context.workflow_folder / artifact.owner_step / raw_template
    rendered = render_runtime_template(raw_template, context, placeholder_label="artifact template placeholder")
    return Path(rendered)


def render_runtime_template(
    template: str,
    context: Context,
    *,
    placeholder_label: str,
    replace_roots: frozenset[str] | None = None,
) -> str:
    """Render supported runtime placeholders inside free-form text."""

    def replace(match: re.Match[str]) -> str:
        expression = match.group(1).strip()
        if not expression:
            return match.group(0) if replace_roots is not None else ""
        root_name = expression.split(".", 1)[0]
        if replace_roots is not None and root_name not in replace_roots:
            return match.group(0)
        value = _resolve_placeholder(expression, context, placeholder_label=placeholder_label)
        return "" if value is None else str(value)

    return _PLACEHOLDER_RE.sub(replace, template)


def validate_artifact_declaration(artifact: Artifact) -> tuple[str, ...]:
    errors: list[str] = []
    if artifact.schema is None:
        return ()
    if artifact.kind != "json":
        errors.append("schema is only supported for json artifacts")
        return tuple(errors)
    if isinstance(artifact.schema, type) and issubclass(artifact.schema, BaseModel):
        return ()
    if isinstance(artifact.schema, dict):
        try:
            validator_cls = _load_jsonschema_validator_cls()
            validator_cls.check_schema(artifact.schema)
        except Exception as exc:
            errors.append(str(exc))
        return tuple(errors)
    errors.append(f"unsupported schema type: {type(artifact.schema).__name__}")
    return tuple(errors)


def validate_artifact_handle(handle: ArtifactHandle) -> ArtifactValidationResult:
    artifact = handle.artifact
    errors: list[str] = []

    if artifact is None:
        return ArtifactValidationResult(ok=True, path=handle.path, artifact_name=handle.name)

    if not handle.path.exists():
        if artifact.required:
            errors.append("artifact file does not exist")
        return ArtifactValidationResult(
            ok=not errors,
            path=handle.path,
            artifact_name=handle.name,
            qualified_name=artifact.qualified_name,
            errors=tuple(errors),
        )

    if handle.path.is_dir():
        if artifact.schema is not None or artifact.kind == "json":
            errors.append("artifact path is a directory")
        return ArtifactValidationResult(
            ok=not errors,
            path=handle.path,
            artifact_name=handle.name,
            qualified_name=artifact.qualified_name,
            errors=tuple(errors),
        )

    contents: str | None = None
    if artifact.kind in {"text", "markdown", "json"}:
        contents = handle.path.read_text(encoding="utf-8")
        if not contents.strip():
            errors.append("artifact file is empty")
            return ArtifactValidationResult(
                ok=False,
                path=handle.path,
                artifact_name=handle.name,
                qualified_name=artifact.qualified_name,
                errors=tuple(errors),
            )

    if artifact.kind == "json" or artifact.schema is not None:
        raw_text = handle.path.read_text(encoding="utf-8") if contents is None else contents
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSON: {exc.msg}")
            return ArtifactValidationResult(
                ok=False,
                path=handle.path,
                artifact_name=handle.name,
                qualified_name=artifact.qualified_name,
                errors=tuple(errors),
            )

        schema = artifact.schema
        if schema is not None:
            if isinstance(schema, type) and issubclass(schema, BaseModel):
                try:
                    schema.model_validate(payload)
                except ValidationError as exc:
                    errors.append(str(exc))
            elif isinstance(schema, dict):
                try:
                    validator_cls = _load_jsonschema_validator_cls()
                    validator_cls(schema).validate(payload)
                except Exception as exc:
                    errors.append(str(exc))
            else:
                errors.append(f"unsupported schema type: {type(schema).__name__}")

    return ArtifactValidationResult(
        ok=not errors,
        path=handle.path,
        artifact_name=handle.name,
        qualified_name=artifact.qualified_name,
        errors=tuple(errors),
    )


def _load_jsonschema_validator_cls() -> type[Any]:
    try:
        from jsonschema import Draft202012Validator
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "raw artifact schema mappings require the optional jsonschema dependency"
        ) from exc
    return Draft202012Validator


def _resolve_placeholder(expression: str, context: Context, *, placeholder_label: str) -> Any:
    parts = expression.split(".")
    if not parts:
        return ""
    root_name = parts[0]
    current: Any
    if root_name == "task_id":
        current = context.task_id
    elif root_name == "run_id":
        current = context.run_id
    elif root_name == "workflow_name":
        current = context.workflow_name
    elif root_name == "task_folder":
        current = context.task_folder
    elif root_name == "workflow_folder":
        current = context.workflow_folder
    elif root_name == "run_folder":
        current = context.run_folder
    elif root_name == "package_folder":
        current = context.package_folder
    elif root_name == "state":
        current = context.state
    elif root_name == "item":
        return _resolve_item_placeholder(
            expression,
            context,
            placeholder_label=placeholder_label,
        )
    elif root_name == "worklist":
        return _resolve_worklist_placeholder(
            expression,
            context,
            placeholder_label=placeholder_label,
        )
    else:
        return ""
    for part in parts[1:]:
        if current is None:
            return ""
        if isinstance(current, Mapping):
            current = current.get(part, "")
        else:
            current = getattr(current, part, "")
    return "" if current is None else current


def _resolve_item_placeholder(
    expression: str,
    context: Context,
    *,
    placeholder_label: str,
) -> Any:
    active_worklist = getattr(context, "_active_worklist", None)
    try:
        current = context.item
    except WorkflowExecutionError as exc:
        if isinstance(active_worklist, str) and active_worklist:
            raise WorkflowExecutionError(
                f"{placeholder_label} {{{expression}}} could not load active worklist {active_worklist!r}: {exc}"
            ) from exc
        raise WorkflowExecutionError(
            f"{placeholder_label} {{{expression}}} could not resolve an active scoped work item: {exc}"
        ) from exc
    if current is None:
        raise WorkflowExecutionError(
            f"{placeholder_label} {{{expression}}} requires an active scoped work item"
        )
    return _resolve_work_item_path(
        current,
        expression=expression,
        parts=expression.split(".")[1:],
        placeholder_label=placeholder_label,
        worklist_name=active_worklist if isinstance(active_worklist, str) else None,
    )


def _resolve_worklist_placeholder(
    expression: str,
    context: Context,
    *,
    placeholder_label: str,
) -> Any:
    parts = expression.split(".")
    if len(parts) < 2 or not parts[1]:
        raise WorkflowExecutionError(
            f"{placeholder_label} {{{expression}}} must specify a declared worklist name"
        )
    worklist_name = parts[1]
    try:
        selection = context.ensure_selection(worklist_name)
    except WorkflowExecutionError as exc:
        raise WorkflowExecutionError(
            f"{placeholder_label} {{{expression}}} could not load worklist {worklist_name!r}: {exc}"
        ) from exc
    remaining = parts[2:]
    if not remaining:
        return selection
    field_name, *rest = remaining
    if field_name == "current":
        current = selection.current
        if current is None:
            raise WorkflowExecutionError(
                f"{placeholder_label} {{{expression}}} requires a current item on worklist {worklist_name!r}"
            )
        return _resolve_work_item_path(
            current,
            expression=expression,
            parts=rest,
            placeholder_label=placeholder_label,
            worklist_name=worklist_name,
        )
    if field_name == "item_ids":
        return tuple(item.id for item in selection.items)
    if field_name == "current_index":
        return selection.current_index
    if field_name == "is_exhausted":
        return selection.current is None
    return _resolve_runtime_path(
        selection,
        expression=expression,
        parts=remaining,
        placeholder_label=placeholder_label,
        payload_path=None,
    )


def _resolve_work_item_path(
    item: Any,
    *,
    expression: str,
    parts: list[str],
    placeholder_label: str,
    worklist_name: str | None,
) -> Any:
    if not parts:
        return item
    field_name, *rest = parts
    if field_name == "payload":
        payload = getattr(item, "payload", None)
        if not rest:
            return payload
        return _resolve_runtime_path(
            payload,
            expression=expression,
            parts=rest,
            placeholder_label=placeholder_label,
            payload_path=[],
        )
    if field_name in {"id", "title", "status", "dir_key"}:
        value = getattr(item, field_name, None)
        if not rest:
            return value
        return _resolve_runtime_path(
            value,
            expression=expression,
            parts=rest,
            placeholder_label=placeholder_label,
            payload_path=None,
        )
    worklist_suffix = f" on worklist {worklist_name!r}" if worklist_name else ""
    raise WorkflowExecutionError(
        f"{placeholder_label} {{{expression}}} references unsupported work item field {field_name!r}{worklist_suffix}"
    )


def _resolve_runtime_path(
    current: Any,
    *,
    expression: str,
    parts: list[str],
    placeholder_label: str,
    payload_path: list[str] | None,
) -> Any:
    value = current
    traversed = list(payload_path or [])
    for part in parts:
        if value is None:
            if payload_path is not None:
                missing_path = ".".join((*traversed, part))
                raise WorkflowExecutionError(
                    f"{placeholder_label} {{{expression}}} references missing payload path {missing_path!r}"
                )
            raise WorkflowExecutionError(
                f"{placeholder_label} {{{expression}}} requires an available runtime value before {part!r}"
            )
        try:
            value = _lookup_runtime_value(value, part)
        except (AttributeError, KeyError, TypeError) as exc:
            if payload_path is not None:
                missing_path = ".".join((*traversed, part))
                raise WorkflowExecutionError(
                    f"{placeholder_label} {{{expression}}} references missing payload path {missing_path!r}"
                ) from exc
            raise WorkflowExecutionError(
                f"{placeholder_label} {{{expression}}} references unknown runtime field {part!r}"
            ) from exc
        if payload_path is not None:
            traversed.append(part)
    return value


def _lookup_runtime_value(current: Any, part: str) -> Any:
    if isinstance(current, Mapping):
        if part not in current:
            raise KeyError(part)
        return current[part]
    if not hasattr(current, part):
        raise AttributeError(part)
    return getattr(current, part)
