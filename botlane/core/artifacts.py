"""Artifact declarations and resolved handles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Iterator, Literal, Mapping

from pydantic import BaseModel, ValidationError

from .artifact_plan import ArtifactKind
from .errors import WorkflowExecutionError
from .placeholders import parse_placeholders, render_template_with_refs

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

def resolve_artifact_template(template: str | Artifact, context: Context) -> Path:
    """Resolve a template against runtime context."""

    artifact = template if isinstance(template, Artifact) else None
    raw_template = artifact.template if artifact is not None else template
    _reject_ctx_placeholders_in_artifact_template(raw_template)
    candidate = Path(raw_template)
    if candidate.is_absolute():
        return candidate
    if "{" not in raw_template and "}" not in raw_template and artifact is not None and artifact.owner_step is not None:
        return context.workflow_folder / artifact.owner_step / raw_template
    rendered = render_runtime_template(raw_template, context, placeholder_label="artifact template placeholder")
    rendered_path = Path(rendered)
    if rendered_path.is_absolute():
        return rendered_path
    if artifact is not None and artifact.owner_step is not None:
        return context.workflow_folder / artifact.owner_step / rendered_path
    return rendered_path


def render_runtime_template(
    template: str,
    context: Context,
    *,
    placeholder_label: str,
    replace_roots: frozenset[str] | None = None,
) -> str:
    """Render supported runtime placeholders inside free-form text."""
    refs = parse_placeholders(template, source=placeholder_label)
    return render_template_with_refs(
        template,
        refs,
        context,
        replace_roots=replace_roots,
        placeholder_label=placeholder_label,
    )


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


def _reject_ctx_placeholders_in_artifact_template(template: str) -> None:
    for ref in parse_placeholders(template, source="artifact_template"):
        if ref.root == "ctx":
            raise WorkflowExecutionError(
                "ctx.* placeholders are only supported in prompts and workflow-step messages, not artifact paths"
            )
