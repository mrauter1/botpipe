"""Jinja rendering and validation for prompt-like templates."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterator, Mapping
from pathlib import Path
import re
from typing import Any, Callable

from jinja2 import (
    DictLoader,
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateError,
    TemplateNotFound,
    TemplateSyntaxError,
    UndefinedError,
    meta,
    nodes,
)
from .artifacts import ArtifactHandle, ResolvedArtifacts
from .errors import WorkflowExecutionError, WorkflowValidationError
from .template_refs import PlaceholderRef, TemplateRequirements
from .prompts import ResolvedPrompt


JINJA_PROMPT_CONTEXT_ROOTS = frozenset(
    {
        "message",
        "request",
        "input",
        "params",
        "workflow_params",
        "state",
        "artifacts",
        "item",
        "item_state",
        "step_item_state",
        "worklist",
        "worklists",
        "current_worklist",
        "branch",
        "fan_in",
        "run",
        "workflow",
        "task",
        "package",
        "step",
        "root",
        "run_folder",
        "workflow_folder",
        "task_folder",
        "package_folder",
        "step_name",
        "values",
        "step_state",
        "route",
        "outcome",
        "event",
        "meta",
        "history",
    }
)
_DEFAULT_EMPTY_MAPPING = object()
_OPTIONAL_JINJA_CONTEXT_ROOTS = frozenset(
    {
        "input",
        "item",
        "item_state",
        "step_item_state",
        "current_worklist",
        "route",
        "outcome",
        "event",
    }
)
_LEGACY_DOTTED_PATH = r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
_LEGACY_ARTIFACT_PLACEHOLDER_RE = re.compile(
    rf"(?<!\{{)\{{(?:"
    rf"task_folder|workflow_folder|run_folder|package_folder|root|request_file|task_id|run_id|workflow_name|"
    rf"ctx\.{_LEGACY_DOTTED_PATH}|"
    rf"input\.{_LEGACY_DOTTED_PATH}|params\.{_LEGACY_DOTTED_PATH}|"
    rf"workflow_params\.{_LEGACY_DOTTED_PATH}|state\.{_LEGACY_DOTTED_PATH}|"
    rf"item\.{_LEGACY_DOTTED_PATH}|worklist\.{_LEGACY_DOTTED_PATH}|"
    rf"branch\.{_LEGACY_DOTTED_PATH}|fan_in\.{_LEGACY_DOTTED_PATH}"
    rf")\}}(?!\}})"
)


@dataclass(frozen=True)
class JinjaPromptValidation:
    requirements: TemplateRequirements

    @property
    def roots(self) -> frozenset[str]:
        return self.requirements.roots

    @property
    def refs(self) -> tuple[PlaceholderRef, ...]:
        return self.requirements.refs

    @property
    def dynamic_artifact_access(self) -> bool:
        return self.requirements.dynamic_artifact_access


@dataclass(frozen=True)
class _PromptTemplateSource:
    text: str
    display_path: str
    loader: FileSystemLoader | DictLoader
    template_name: str
    search_root: Path | None = None


def is_file_backed_prompt(prompt: ResolvedPrompt) -> bool:
    if prompt.source == "file":
        return True
    return isinstance(prompt.reference_values.get("resolved_path"), str)


def render_prompt_template(
    prompt: ResolvedPrompt,
    context: Any,
    *,
    placeholder_label: str,
) -> str:
    if prompt.text is None:
        raise WorkflowExecutionError(f"{placeholder_label} {prompt.path!r} did not resolve to text")
    source = _prompt_template_source(prompt)
    try:
        validation = _validate_prompt_template_source(
            source,
            surface=placeholder_label,
            extra_roots=_runtime_prompt_extra_roots(context),
        )
    except WorkflowValidationError as exc:
        raise WorkflowExecutionError(str(exc)) from exc
    env = _jinja_prompt_environment(source.loader)
    try:
        template = env.get_template(source.template_name)
        return template.render(_jinja_prompt_context(context, required_roots=validation.roots))
    except WorkflowExecutionError as exc:
        raise WorkflowExecutionError(f"{placeholder_label} {source.display_path}: {exc}") from exc
    except TemplateNotFound as exc:
        raise WorkflowExecutionError(
            f"{placeholder_label} {source.display_path}: missing Jinja include {exc.name!r}"
        ) from exc
    except TemplateSyntaxError as exc:
        raise WorkflowExecutionError(_jinja_syntax_error_message(placeholder_label, source.display_path, exc)) from exc
    except UndefinedError as exc:
        raise WorkflowExecutionError(
            f"{placeholder_label} {source.display_path}: undefined Jinja value: {exc}"
        ) from exc
    except TemplateError as exc:
        raise WorkflowExecutionError(f"{placeholder_label} {source.display_path}: Jinja render failed: {exc}") from exc


def render_file_prompt_template(
    prompt: ResolvedPrompt,
    context: Any,
    *,
    placeholder_label: str,
) -> str:
    return render_prompt_template(prompt, context, placeholder_label=placeholder_label)


def render_inline_prompt_template(
    template_text: str,
    context: Any,
    *,
    placeholder_label: str,
) -> str:
    prompt = ResolvedPrompt(
        path=None,
        text=template_text,
        source="inline",
        reference_values={"source": "inline", "inline": True},
    )
    return render_prompt_template(prompt, context, placeholder_label=placeholder_label)


def render_artifact_template(
    template_text: str,
    context: Any,
    *,
    placeholder_label: str,
) -> str:
    legacy_match = _LEGACY_ARTIFACT_PLACEHOLDER_RE.search(template_text)
    if legacy_match is not None:
        raise WorkflowExecutionError(
            f"{placeholder_label} uses legacy single-brace placeholder {legacy_match.group(0)!r}; "
            "artifact templates use Jinja, for example '{{ workflow.folder }}/report.md'."
        )
    return render_inline_prompt_template(
        template_text,
        context,
        placeholder_label=placeholder_label,
    )


def validate_artifact_template(
    text: str,
    *,
    surface: str,
    extra_roots: frozenset[str] = frozenset(),
) -> JinjaPromptValidation:
    legacy_match = _LEGACY_ARTIFACT_PLACEHOLDER_RE.search(text)
    if legacy_match is not None:
        raise WorkflowValidationError(
            f"{surface} uses legacy single-brace placeholder {legacy_match.group(0)!r}; "
            "artifact templates use Jinja, for example '{{ workflow.folder }}/report.md'."
        )
    return validate_inline_prompt_template(text, surface=surface, extra_roots=extra_roots)


def validate_file_prompt_template(
    prompt: ResolvedPrompt,
    *,
    surface: str,
) -> JinjaPromptValidation:
    return validate_prompt_template(prompt, surface=surface)


def validate_prompt_template(
    prompt: ResolvedPrompt,
    *,
    surface: str,
    extra_roots: frozenset[str] = frozenset(),
) -> JinjaPromptValidation:
    if prompt.text is None:
        return JinjaPromptValidation(TemplateRequirements.empty())
    source = _prompt_template_source(prompt)
    return _validate_prompt_template_source(source, surface=surface, extra_roots=extra_roots)


def validate_inline_prompt_template(
    text: str,
    *,
    surface: str,
    extra_roots: frozenset[str] = frozenset(),
) -> JinjaPromptValidation:
    prompt = ResolvedPrompt(
        path=None,
        text=text,
        source="inline",
        reference_values={"source": "inline", "inline": True},
    )
    return validate_prompt_template(prompt, surface=surface, extra_roots=extra_roots)


def _prompt_template_source(prompt: ResolvedPrompt) -> _PromptTemplateSource:
    if prompt.text is None:
        raise ValueError("prompt template source requires prompt text")
    prompt_path = _resolved_prompt_path(prompt)
    display_path = _prompt_display_path(prompt, prompt_path)
    if prompt_path is not None and prompt_path.is_file():
        root = prompt_path.parent
        return _PromptTemplateSource(
            text=prompt.text,
            display_path=display_path,
            loader=FileSystemLoader([root]),
            template_name=prompt_path.name,
            search_root=root,
        )
    return _PromptTemplateSource(
        text=prompt.text,
        display_path=display_path,
        loader=DictLoader({display_path: prompt.text}),
        template_name=display_path,
    )


def _validate_prompt_template_source(
    source: _PromptTemplateSource,
    *,
    surface: str,
    extra_roots: frozenset[str] = frozenset(),
) -> JinjaPromptValidation:
    env = _jinja_prompt_environment(source.loader)
    requirements = _validate_template_text(
        env,
        source.text,
        surface=surface,
        root_display_path=source.display_path,
        current_display_path=source.display_path,
        allowed_roots=JINJA_PROMPT_CONTEXT_ROOTS | extra_roots,
        visited=frozenset({source.template_name}),
    )
    return JinjaPromptValidation(requirements)


def _validate_template_text(
    env: Environment,
    text: str,
    *,
    surface: str,
    root_display_path: str,
    current_display_path: str,
    allowed_roots: frozenset[str],
    visited: frozenset[str],
) -> TemplateRequirements:
    try:
        ast = env.parse(text)
    except TemplateSyntaxError as exc:
        raise WorkflowValidationError(_jinja_syntax_error_message(surface, current_display_path, exc)) from exc

    roots = set(meta.find_undeclared_variables(ast))
    refs = _jinja_template_refs(ast, surface=surface, roots=frozenset(roots))
    requirements = TemplateRequirements(
        refs=tuple(dict.fromkeys(refs)),
        roots=frozenset(roots),
        dynamic_artifact_access=_has_dynamic_artifact_access(ast),
    )
    undeclared = roots - allowed_roots
    if undeclared:
        names = ", ".join(sorted(undeclared))
        allowed = ", ".join(sorted(allowed_roots))
        raise WorkflowValidationError(
            f"{surface} {current_display_path} uses unknown Jinja variable(s): {names}. Allowed roots: {allowed}"
        )
    _validate_supported_request_text_refs(refs, surface=surface, display_path=current_display_path)

    loader = env.loader
    if loader is None:
        return requirements
    for template_name in meta.find_referenced_templates(ast):
        if template_name is None:
            continue
        if _unsafe_template_name(template_name):
            raise WorkflowValidationError(
                f"{surface} {current_display_path} includes unsafe Jinja template path {template_name!r}"
            )
        if template_name in visited:
            continue
        try:
            included_text, included_filename, _ = loader.get_source(env, template_name)
        except TemplateNotFound as exc:
            raise WorkflowValidationError(
                f"{surface} {current_display_path} includes missing Jinja template {template_name!r}"
            ) from exc
        included_display = f"{root_display_path} -> {template_name}"
        if included_filename:
            included_display = f"{included_display} ({included_filename})"
        child_requirements = _validate_template_text(
            env,
            included_text,
            surface=surface,
            root_display_path=root_display_path,
            current_display_path=included_display,
            allowed_roots=allowed_roots,
            visited=visited | {template_name},
        )
        requirements = requirements.merge(child_requirements)
    return requirements


def _jinja_prompt_environment(loader: FileSystemLoader | DictLoader) -> Environment:
    return Environment(
        loader=loader,
        autoescape=False,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        finalize=lambda value: "" if value is None else value,
    )


def _jinja_prompt_context(context: Any, *, required_roots: frozenset[str]) -> dict[str, Any]:
    values = getattr(context, "_values", {})
    artifacts = getattr(context, "artifacts", None)
    payload: dict[str, Any] = {}
    factories: dict[str, Callable[[], Any]] = {
        "message": lambda: context.message,
        "request": lambda: context.request,
        "input": lambda: _required_context_value(lambda: context.input_fields),
        "params": lambda: context.params,
        "workflow_params": lambda: context.workflow_params,
        "state": lambda: context.state,
        "artifacts": lambda: _ArtifactsTemplateView(artifacts),
        "item": lambda: _optional_context_value(lambda: _item_template_value(context)),
        "item_state": lambda: _optional_context_value(lambda: context.item_state),
        "step_item_state": lambda: _optional_context_value(lambda: context.step_item_state),
        "worklist": lambda: context.worklists,
        "worklists": lambda: context.worklists,
        "current_worklist": lambda: _optional_context_value(lambda: context.current_worklist),
        "branch": lambda: context.branch,
        "fan_in": lambda: context.fan_in,
        "run": lambda: _run_template_value(context),
        "workflow": lambda: _workflow_template_value(context),
        "task": lambda: _TemplateNamespace({"id": context.task_id, "folder": context.task_folder}),
        "package": lambda: _TemplateNamespace({"folder": context.package_folder}),
        "step": lambda: _TemplateNamespace({"name": context._step_name}),
        "root": lambda: context.root,
        "run_folder": lambda: context.run_folder,
        "workflow_folder": lambda: context.workflow_folder,
        "task_folder": lambda: context.task_folder,
        "package_folder": lambda: context.package_folder,
        "step_name": lambda: context._step_name,
        "values": lambda: _template_value(getattr(context, "_values", {})),
        "step_state": lambda: context.step_state,
        "route": lambda: context.route,
        "outcome": lambda: context.outcome,
        "event": lambda: context.event,
        "meta": lambda: context.meta,
        "history": lambda: context.history,
    }
    for root in sorted(required_roots):
        factory = factories.get(root)
        if factory is None:
            continue
        try:
            payload[root] = factory()
        except (AttributeError, WorkflowExecutionError):
            if root in _OPTIONAL_JINJA_CONTEXT_ROOTS:
                continue
            raise
    for name, value in _artifact_prompt_context_roots(artifacts).items():
        if name in required_roots:
            payload.setdefault(name, value)
    if isinstance(values, dict):
        for name, value in values.items():
            if name in required_roots:
                payload.setdefault(str(name), _template_value(value))
    return payload


def _runtime_prompt_extra_roots(context: Any) -> frozenset[str]:
    roots: set[str] = set()
    values = getattr(context, "_values", {})
    if isinstance(values, Mapping):
        roots.update(str(name) for name in values)
    roots.update(_artifact_prompt_context_roots(getattr(context, "artifacts", None)))
    return frozenset(roots)


def _artifact_prompt_context_roots(artifacts: ResolvedArtifacts | None) -> dict[str, Any]:
    if artifacts is None:
        return {}
    roots: dict[str, Any] = {}
    for key, handle in artifacts.items():
        if not isinstance(key, str) or not key:
            continue
        if "." in key:
            root, artifact_name = key.split(".", 1)
            if not root or not artifact_name:
                continue
            namespace = roots.setdefault(root, {})
            if isinstance(namespace, dict):
                namespace.setdefault(artifact_name, handle)
            continue
        roots.setdefault(key, handle)
    return {
        name: _TemplateNamespace(value) if isinstance(value, dict) else value
        for name, value in roots.items()
    }


def _required_context_value(factory: Callable[[], Any]) -> Any:
    value = factory()
    if value is None:
        raise AttributeError("required Jinja context value is unavailable")
    return _template_value(value)


def _item_template_value(context: Any) -> Any:
    item = context.item
    payload = {
        "id": getattr(item, "id"),
        "title": getattr(item, "title"),
        "status": getattr(item, "status"),
        "dir_key": getattr(item, "dir_key"),
        "payload": getattr(item, "payload"),
    }
    try:
        payload["state"] = context.item_state
    except (AttributeError, WorkflowExecutionError):
        pass
    return _TemplateNamespace(payload)


def _run_template_value(context: Any) -> Any:
    try:
        return context.run
    except AttributeError:
        return _TemplateNamespace({"id": getattr(context, "run_id", ""), "folder": context.run_folder})


def _workflow_template_value(context: Any) -> Any:
    try:
        return context.workflow
    except AttributeError:
        return _TemplateNamespace({"name": getattr(context, "workflow_name", ""), "folder": context.workflow_folder})


def _optional_context_value(factory, *, default: Any = _DEFAULT_EMPTY_MAPPING) -> Any:
    fallback = {} if default is _DEFAULT_EMPTY_MAPPING else default
    try:
        value = factory()
    except (AttributeError, WorkflowExecutionError):
        return _template_value(fallback)
    return _template_value(fallback if value is None else value)


def _template_value(value: Any) -> Any:
    if isinstance(value, _TemplateNamespace):
        return value
    if isinstance(value, Mapping):
        return _TemplateNamespace(value)
    return value


class _TemplateNamespace:
    """Attribute/index view that lets data keys like items/keys/values win."""

    def __init__(self, source: Mapping[str, Any]) -> None:
        self._source = source

    def __getitem__(self, name: str) -> Any:
        return _template_value(self._source[name])

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __iter__(self) -> Iterator[str]:
        return iter(self._source)

    def __len__(self) -> int:
        return len(self._source)


class _ArtifactsTemplateView:
    def __init__(self, artifacts: ResolvedArtifacts | None) -> None:
        self._artifacts = artifacts

    def __bool__(self) -> bool:
        return len(self) > 0

    def __len__(self) -> int:
        return len(self._unique_artifacts())

    def __iter__(self) -> Iterator[ArtifactHandle]:
        return iter(self._unique_artifacts().values())

    def _unique_artifacts(self) -> dict[str, ArtifactHandle]:
        if self._artifacts is None:
            return {}
        unique: dict[str, ArtifactHandle] = {}
        for handle in self._artifacts.values():
            key = _artifact_handle_identity(handle)
            unique.setdefault(key, handle)
        return unique

    def __getitem__(self, name: str) -> ArtifactHandle:
        if self._artifacts is None:
            raise KeyError(name)
        return self._artifacts[name]

    def __getattr__(self, name: str) -> ArtifactHandle:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def _artifact_handle_identity(handle: ArtifactHandle) -> str:
    artifact = handle.artifact
    if artifact is not None and artifact.qualified_name:
        return f"qualified:{artifact.qualified_name}"
    try:
        return f"path:{handle.path.resolve(strict=False)}"
    except OSError:
        return f"path:{handle.path}"


def _validate_supported_request_text_refs(
    refs: list[PlaceholderRef],
    *,
    surface: str,
    display_path: str,
) -> None:
    for ref in refs:
        if _is_unsupported_request_text_ref(ref):
            raise WorkflowValidationError(
                f"{surface} {display_path} uses unsupported Jinja request-text reference "
                f"'{{{{ {ref.raw} }}}}'. Use '{{{{ message }}}}' or '{{{{ request.text }}}}'."
            )


def _is_unsupported_request_text_ref(ref: PlaceholderRef) -> bool:
    return ref.root == "input" and ref.path[:1] == ("message",)


def _unsafe_template_name(template_name: str) -> bool:
    candidate = Path(template_name)
    return candidate.is_absolute() or ".." in candidate.parts


def _resolved_prompt_path(prompt: ResolvedPrompt) -> Path | None:
    resolved_path = prompt.reference_values.get("resolved_path")
    if isinstance(resolved_path, str) and resolved_path:
        return Path(resolved_path)
    if isinstance(prompt.path, str) and prompt.path:
        candidate = Path(prompt.path)
        if candidate.is_absolute() and candidate.exists():
            return candidate
    return None


def _prompt_display_path(prompt: ResolvedPrompt, prompt_path: Path | None) -> str:
    requested_path = prompt.reference_values.get("requested_path")
    if isinstance(requested_path, str) and requested_path:
        return requested_path
    if prompt_path is not None:
        return str(prompt_path)
    return prompt.path or "<inline prompt template>"


def _jinja_syntax_error_message(label: str, display_path: str, exc: TemplateSyntaxError) -> str:
    line = f":{exc.lineno}" if exc.lineno is not None else ""
    return f"{label} {display_path}{line}: Jinja syntax error: {exc.message}"


def _jinja_template_refs(
    ast: nodes.Template,
    *,
    surface: str,
    roots: frozenset[str],
) -> list[PlaceholderRef]:
    discovered: list[tuple[str, ...]] = []
    for node in ast.find_all((nodes.Name, nodes.Getattr, nodes.Getitem)):
        parts = _jinja_node_parts(node)
        if not parts or parts[0] not in roots:
            continue
        if parts not in discovered:
            discovered.append(parts)
    refs: list[PlaceholderRef] = []
    for parts in discovered:
        if any(
            other != parts and len(other) > len(parts) and other[: len(parts)] == parts
            for other in discovered
        ):
            continue
        raw = ".".join(parts)
        refs.append(PlaceholderRef(raw=raw, root=parts[0], path=tuple(parts[1:]), source=surface))
    return refs


def _has_dynamic_artifact_access(ast: nodes.Template) -> bool:
    artifact_aliases = _artifact_collection_aliases(ast)
    alias_roots = artifact_aliases - {"artifacts"}
    if _has_broad_artifact_collection_access(ast, artifact_aliases):
        return True
    if alias_roots:
        for node in ast.find_all((nodes.Name, nodes.Getattr, nodes.Getitem)):
            parts = _jinja_node_parts(node)
            if parts and parts[0] in alias_roots and getattr(node, "ctx", "load") == "load":
                return True
    for node in ast.find_all(nodes.Getitem):
        if not _is_artifact_collection_expr(node.node, artifact_aliases):
            continue
        arg = node.arg
        if not (isinstance(arg, nodes.Const) and isinstance(arg.value, str)):
            return True
    for node in ast.find_all(nodes.Filter):
        if _is_artifact_collection_expr(node.node, artifact_aliases):
            return True
    for node in ast.find_all(nodes.For):
        if _is_artifact_collection_expr(node.iter, artifact_aliases):
            return True
    return False


def _artifact_collection_aliases(ast: nodes.Template) -> frozenset[str]:
    aliases = {"artifacts"}
    changed = True
    while changed:
        changed = False
        for node in ast.find_all(nodes.Assign):
            if not isinstance(node.target, nodes.Name):
                continue
            if not _is_artifact_collection_expr(node.node, aliases):
                continue
            if node.target.name not in aliases:
                aliases.add(node.target.name)
                changed = True
        for node in ast.find_all(nodes.With):
            for target, value in zip(node.targets, node.values):
                if not isinstance(target, nodes.Name):
                    continue
                if not _is_artifact_collection_expr(value, aliases):
                    continue
                if target.name not in aliases:
                    aliases.add(target.name)
                    changed = True
    return frozenset(aliases)


def _has_broad_artifact_collection_access(ast: nodes.Template, aliases: frozenset[str]) -> bool:
    for node in ast.find_all(nodes.Output):
        if any(_is_artifact_collection_expr(child, aliases) for child in node.nodes):
            return True
    for node in ast.find_all(nodes.If):
        if _is_artifact_collection_expr(node.test, aliases):
            return True
    return False


def _is_artifact_collection_expr(node: nodes.Node, aliases: frozenset[str] | set[str]) -> bool:
    parts = _jinja_node_parts(node)
    return len(parts) == 1 and parts[0] in aliases


def _jinja_node_parts(node: nodes.Node) -> tuple[str, ...]:
    if isinstance(node, nodes.Name):
        return (node.name,)
    if isinstance(node, nodes.Getattr):
        base = _jinja_node_parts(node.node)
        return (*base, node.attr) if base else ()
    if isinstance(node, nodes.Getitem):
        base = _jinja_node_parts(node.node)
        if not base:
            return ()
        arg = node.arg
        if isinstance(arg, nodes.Const) and isinstance(arg.value, str):
            return (*base, arg.value)
    return ()


__all__ = [
    "JINJA_PROMPT_CONTEXT_ROOTS",
    "JinjaPromptValidation",
    "is_file_backed_prompt",
    "render_artifact_template",
    "render_inline_prompt_template",
    "render_file_prompt_template",
    "render_prompt_template",
    "validate_artifact_template",
    "validate_file_prompt_template",
    "validate_inline_prompt_template",
    "validate_prompt_template",
]
