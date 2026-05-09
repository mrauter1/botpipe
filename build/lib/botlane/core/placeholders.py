"""Internal placeholder parsing values.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .context_placeholders import CTX_MODEL_ROOTS, CTX_NESTED_FIELDS, CTX_SCALAR_FIELDS, validate_safe_ctx_reference
from .errors import WorkflowExecutionError, WorkflowValidationError


_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")
_FORBIDDEN_CTX_SEGMENT_CHARS = frozenset({'"', "'", "(", ")", "[", "]"})
_PROMPT_VALIDATION_KINDS = frozenset({"simple_prompt", "prompt", "branch_step_prompt", "fan_in_step_prompt"})
_WORKFLOW_STEP_MESSAGE_ALLOWED_ROOTS = frozenset({"ctx", "input", "item", "worklist", "branch", "fan_in"})
_RUNTIME_TEMPLATE_ALLOWED_ROOTS = frozenset(
    {
        "ctx",
        "task_id",
        "run_id",
        "workflow_name",
        "task_folder",
        "workflow_folder",
        "run_folder",
        "package_folder",
        "root",
        "request_file",
        "params",
        "workflow_params",
        "input",
        "state",
        "item",
        "worklist",
        "branch",
        "fan_in",
    }
)
_ARTIFACT_TEMPLATE_ALLOWED_ROOTS = _RUNTIME_TEMPLATE_ALLOWED_ROOTS - {"ctx"}

SIMPLE_CONTEXT_BARE_NAMES = frozenset(
    {
        "answer",
        "artifacts",
        "input",
        "item",
        "package_folder",
        "params",
        "request_file",
        "run_folder",
        "state",
        "task_folder",
        "workflow_folder",
        "workflow_params",
    }
)


@dataclass(frozen=True, slots=True)
class PlaceholderRef:
    raw: str
    root: str
    path: tuple[str, ...]
    source: str


def parse_placeholders(text: str, *, source: str) -> tuple[PlaceholderRef, ...]:
    refs: list[PlaceholderRef] = []
    for match in _PLACEHOLDER_RE.finditer(text):
        raw = match.group(1).strip()
        if raw:
            root, *path = raw.split(".")
            refs.append(PlaceholderRef(raw=raw, root=root, path=tuple(path), source=source))
            continue
        refs.append(PlaceholderRef(raw="", root="", path=(), source=source))
    return tuple(refs)


def validate_placeholder_ref(
    ref: PlaceholderRef,
    *,
    surface: str,
    symbols: Any,
) -> str | None:
    if not isinstance(symbols, Mapping):
        raise ValueError("validate_placeholder_ref requires a mapping of placeholder symbols")
    validation_kind = str(symbols.get("kind", "simple_prompt"))
    if validation_kind in _PROMPT_VALIDATION_KINDS:
        return _validate_simple_prompt_reference(ref, surface=surface, symbols=symbols)
    if validation_kind == "workflow_step_message":
        return _validate_runtime_template_reference(
            ref,
            surface=surface,
            symbols=symbols,
            allowed_roots=_WORKFLOW_STEP_MESSAGE_ALLOWED_ROOTS,
        )
    if validation_kind == "artifact_template":
        return _validate_runtime_template_reference(
            ref,
            surface=surface,
            symbols=symbols,
            allowed_roots=_ARTIFACT_TEMPLATE_ALLOWED_ROOTS,
        )
    if validation_kind in {"runtime_template", "worklist_context"}:
        return _validate_runtime_template_reference(
            ref,
            surface=surface,
            symbols=symbols,
            allowed_roots=_RUNTIME_TEMPLATE_ALLOWED_ROOTS,
        )
    raise ValueError(f"unsupported placeholder validation kind {validation_kind!r}")


def render_placeholder_ref(ref: PlaceholderRef, context: Any) -> Any:
    return _resolve_placeholder_ref(ref, context, placeholder_label="placeholder")


def render_template_with_refs(
    template: str,
    refs: tuple[PlaceholderRef, ...],
    context: Any,
    *,
    replace_roots: frozenset[str] | None = None,
    placeholder_label: str,
) -> str:
    matches = list(_PLACEHOLDER_RE.finditer(template))
    if len(matches) != len(refs):
        raise ValueError("placeholder refs do not match template placeholders")

    rendered: list[str] = []
    cursor = 0
    for match, ref in zip(matches, refs, strict=True):
        rendered.append(template[cursor : match.start()])
        cursor = match.end()
        if not ref.raw:
            rendered.append(match.group(0) if replace_roots is not None else "")
            continue
        if replace_roots is not None and ref.root not in replace_roots:
            rendered.append(match.group(0))
            continue
        value = _resolve_placeholder_ref(ref, context, placeholder_label=placeholder_label)
        if ref.root == "ctx":
            rendered.append(_render_prompt_value(value, ref=ref, placeholder_label=placeholder_label))
        else:
            rendered.append("" if value is None else str(value))
    rendered.append(template[cursor:])
    return "".join(rendered)


def resolve_artifact_template(template: Any, context: Any) -> Path:
    """Resolve an artifact template against runtime context."""

    artifact = template if hasattr(template, "template") else None
    raw_template = getattr(artifact, "template", template)
    if not isinstance(raw_template, str):
        raise TypeError("artifact template must be a string or Artifact declaration")
    _reject_ctx_placeholders_in_artifact_template(raw_template)
    candidate = Path(raw_template)
    if candidate.is_absolute():
        return candidate
    artifact_owner_step = getattr(artifact, "owner_step", None)
    if "{" not in raw_template and "}" not in raw_template and artifact_owner_step is not None:
        return context.workflow_folder / artifact_owner_step / raw_template
    rendered = render_runtime_template(raw_template, context, placeholder_label="artifact template placeholder")
    rendered_path = Path(rendered)
    if rendered_path.is_absolute():
        return rendered_path
    if artifact_owner_step is not None:
        return context.workflow_folder / artifact_owner_step / rendered_path
    return rendered_path


def render_runtime_template(
    template: str,
    context: Any,
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


def _validate_simple_prompt_reference(
    ref: PlaceholderRef,
    *,
    surface: str,
    symbols: Mapping[str, Any],
) -> str | None:
    if _validate_branch_or_fan_in_prompt_reference(ref, symbols=symbols):
        return None
    _raise_special_simple_prompt_reference_error(ref, surface=surface)
    if ref.root == "ctx":
        return _validate_ctx_prompt_reference(ref, surface=surface, symbols=symbols)

    parts = _ref_parts(ref)
    if len(parts) == 1:
        return _validate_bare_simple_prompt_reference(ref, surface=surface, symbols=symbols)

    root = parts[0]
    validator = _SIMPLE_ROOT_VALIDATORS.get(root)
    if validator is not None:
        return validator(ref, parts=parts, surface=surface, symbols=symbols)
    if root in {"artifacts", "step"} and len(parts) == 2:
        return _validate_nested_simple_prompt_reference(ref, nested_expression=parts[1], surface=surface, symbols=symbols)
    return _validate_step_output_prompt_reference(ref, parts=parts, surface=surface, symbols=symbols)


def _validate_branch_or_fan_in_prompt_reference(
    ref: PlaceholderRef,
    *,
    symbols: Mapping[str, Any],
) -> bool:
    step_name = symbols["step_name"]
    if _validate_branch_placeholder_reference(
        ref.raw,
        step_name=step_name,
        allowed=bool(symbols.get("allow_branch_placeholders", False)),
    ):
        return True
    return _validate_fan_in_placeholder_reference(
        ref.raw,
        step_name=step_name,
        allowed=bool(symbols.get("allow_fan_in_placeholders", False)),
    )


def _raise_special_simple_prompt_reference_error(ref: PlaceholderRef, *, surface: str) -> None:
    error_message = _SIMPLE_PROMPT_SPECIAL_ERRORS.get(ref.raw)
    if error_message is not None:
        raise WorkflowValidationError(error_message(surface))


def _validate_bare_simple_prompt_reference(
    ref: PlaceholderRef,
    *,
    surface: str,
    symbols: Mapping[str, Any],
) -> str | None:
    name = ref.root
    context_collision = (
        name in symbols["state_fields"]
        or name in symbols["parameter_fields"]
        or name in symbols["input_fields"]
        or name in SIMPLE_CONTEXT_BARE_NAMES
    )
    artifact_count = symbols["artifact_name_counts"].get(name, 0)
    if artifact_count > 1 or (artifact_count == 1 and context_collision):
        raise WorkflowValidationError(f"{surface} {{{ref.raw}}} is ambiguous; qualify the artifact reference")
    if artifact_count == 1:
        return name if name not in symbols["own_outputs"] else None
    if context_collision:
        return None
    raise WorkflowValidationError(f"{surface} {{{ref.raw}}} is unknown")


def _validate_params_prompt_reference(
    ref: PlaceholderRef,
    *,
    parts: tuple[str, ...],
    surface: str,
    symbols: Mapping[str, Any],
) -> None:
    field_name = parts[1]
    if field_name not in symbols["parameter_fields"]:
        raise WorkflowValidationError(f"{surface} {{{ref.raw}}} references unknown params field {field_name!r}")
    return None


def _validate_self_prompt_reference(
    ref: PlaceholderRef,
    *,
    parts: tuple[str, ...],
    surface: str,
    symbols: Mapping[str, Any],
) -> None:
    artifact_name = parts[1]
    if artifact_name not in symbols["own_outputs"]:
        raise WorkflowValidationError(f"{surface} {{{ref.raw}}} references unknown self artifact {artifact_name!r}")
    return None


def _validate_state_prompt_reference(
    ref: PlaceholderRef,
    *,
    parts: tuple[str, ...],
    surface: str,
    symbols: Mapping[str, Any],
) -> None:
    field_name = parts[1]
    if field_name not in symbols["state_fields"]:
        raise WorkflowValidationError(f"{surface} {{{ref.raw}}} references unknown state field {field_name!r}")
    return None


def _validate_input_prompt_reference(
    ref: PlaceholderRef,
    *,
    parts: tuple[str, ...],
    surface: str,
    symbols: Mapping[str, Any],
) -> None:
    field_name = parts[1]
    if field_name == "message" and len(parts) == 2:
        return None
    if not symbols["input_fields"]:
        raise WorkflowValidationError(f"{surface} {{{ref.raw}}} requires workflow input, but no input was provided")
    if field_name not in symbols["input_fields"]:
        raise WorkflowValidationError(f"{surface} {{{ref.raw}}} references unknown input field {field_name!r}")
    return None


def _validate_run_prompt_reference(
    ref: PlaceholderRef,
    *,
    parts: tuple[str, ...],
    surface: str,
    symbols: Mapping[str, Any],
) -> None:
    field_name = parts[1]
    if field_name not in {"id"}:
        raise WorkflowValidationError(f"{surface} {{{ref.raw}}} references unknown run field {field_name!r}")
    return None


def _validate_workflow_prompt_reference(
    ref: PlaceholderRef,
    *,
    parts: tuple[str, ...],
    surface: str,
    symbols: Mapping[str, Any],
) -> None:
    field_name = parts[1]
    if field_name not in {"folder"}:
        raise WorkflowValidationError(f"{surface} {{{ref.raw}}} references unknown workflow field {field_name!r}")
    return None


def _validate_item_root_prompt_reference(
    ref: PlaceholderRef,
    *,
    parts: tuple[str, ...],
    surface: str,
    symbols: Mapping[str, Any],
) -> None:
    return _validate_item_prompt_reference(
        ref,
        surface=surface,
        symbols=symbols,
        second=parts[1],
        rest=list(parts[2:]),
    )


def _validate_worklist_root_prompt_reference(
    ref: PlaceholderRef,
    *,
    parts: tuple[str, ...],
    surface: str,
    symbols: Mapping[str, Any],
) -> None:
    return _validate_worklist_prompt_reference(
        ref,
        surface=surface,
        symbols=symbols,
        worklist_name=parts[1],
        rest=list(parts[2:]),
    )


def _validate_nested_simple_prompt_reference(
    ref: PlaceholderRef,
    *,
    nested_expression: str,
    surface: str,
    symbols: Mapping[str, Any],
) -> str | None:
    return _validate_simple_prompt_reference(
        _placeholder_ref(nested_expression, source=ref.source),
        surface=surface,
        symbols=symbols,
    )


def _validate_step_output_prompt_reference(
    ref: PlaceholderRef,
    *,
    parts: tuple[str, ...],
    surface: str,
    symbols: Mapping[str, Any],
) -> str | None:
    step_name = parts[0]
    artifact_or_field = parts[1]
    rest = list(parts[2:])
    step_output_names = symbols["step_output_names"]
    if step_name not in step_output_names:
        raise WorkflowValidationError(f"{surface} {{{ref.raw}}} references unknown step {step_name!r}")
    if artifact_or_field == "value":
        return None
    if artifact_or_field == "state":
        return _validate_step_state_prompt_reference(
            ref,
            surface=surface,
            symbols=symbols,
            step_name=step_name,
            rest=rest,
        )
    if artifact_or_field == "item_state":
        return _validate_step_item_state_prompt_reference(
            ref,
            surface=surface,
            symbols=symbols,
            step_name=step_name,
            rest=rest,
        )
    if artifact_or_field == "meta":
        return None
    if artifact_or_field not in step_output_names[step_name]:
        raise WorkflowValidationError(
            f"{surface} {{{ref.raw}}} references unknown artifact {artifact_or_field!r} on step {step_name!r}"
        )
    return None if step_name == symbols["step_name"] else f"{step_name}.{artifact_or_field}"


def _validate_step_state_prompt_reference(
    ref: PlaceholderRef,
    *,
    surface: str,
    symbols: Mapping[str, Any],
    step_name: str,
    rest: list[str],
) -> None:
    if not rest:
        raise WorkflowValidationError(f"{surface} {{{ref.raw}}} must qualify a step state field")
    field_name = rest[0]
    if field_name not in symbols["step_state_fields"].get(step_name, frozenset()):
        raise WorkflowValidationError(
            f"{surface} {{{ref.raw}}} references unknown state field {field_name!r} on step {step_name!r}"
        )
    return None


def _validate_step_item_state_prompt_reference(
    ref: PlaceholderRef,
    *,
    surface: str,
    symbols: Mapping[str, Any],
    step_name: str,
    rest: list[str],
) -> None:
    if not rest:
        raise WorkflowValidationError(f"{surface} {{{ref.raw}}} must qualify a step item_state field")
    field_name = rest[0]
    available_fields = symbols["step_item_state_fields"].get(step_name, frozenset())
    if not available_fields:
        raise WorkflowValidationError(
            f"{surface} {{{ref.raw}}} requires scoped step {step_name!r} to declare item_state or use built-in scoped runtime state"
        )
    if field_name not in available_fields:
        raise WorkflowValidationError(
            f"{surface} {{{ref.raw}}} references unknown item_state field {field_name!r} on step {step_name!r}"
        )
    return None


def _validate_item_prompt_reference(
    ref: PlaceholderRef,
    *,
    surface: str,
    symbols: Mapping[str, Any],
    second: str,
    rest: list[str],
) -> None:
    scope_name = symbols["scope_name"]
    if scope_name is None:
        raise WorkflowValidationError(f"{surface} {{{ref.raw}}} requires scope=... on the same step")
    if second in {"id", "title", "status", "dir_key"} and not rest:
        return None
    if second == "payload":
        return None
    if second != "state" or not rest:
        raise WorkflowValidationError(
            f"{surface} {{{ref.raw}}} must use item.id, item.title, item.status, item.dir_key, item.payload, item.payload.<path>, or item.state.<field>"
        )
    field_name = rest[0]
    available_fields = symbols["worklist_item_state_fields"].get(scope_name, frozenset())
    if not available_fields:
        raise WorkflowValidationError(
            f"{surface} {{{ref.raw}}} requires worklist {scope_name!r} to declare item_state"
        )
    if field_name not in available_fields:
        raise WorkflowValidationError(
            f"{surface} {{{ref.raw}}} references unknown item state field {field_name!r} on worklist {scope_name!r}"
        )
    return None


def _validate_worklist_prompt_reference(
    ref: PlaceholderRef,
    *,
    surface: str,
    symbols: Mapping[str, Any],
    worklist_name: str,
    rest: list[str],
) -> None:
    worklist_item_state_fields = symbols["worklist_item_state_fields"]
    if worklist_name not in worklist_item_state_fields:
        raise WorkflowValidationError(f"{surface} {{{ref.raw}}} references unknown worklist {worklist_name!r}")
    if not rest:
        raise WorkflowValidationError(f"{surface} {{{ref.raw}}} must qualify a worklist runtime field")
    worklist_field, *worklist_rest = rest
    if worklist_field == "current":
        if not worklist_rest:
            raise WorkflowValidationError(f"{surface} {{{ref.raw}}} must qualify a current work item field")
        current_field, *current_rest = worklist_rest
        if current_field in {"id", "title", "status", "dir_key"} and not current_rest:
            return None
        if current_field == "payload":
            return None
        raise WorkflowValidationError(
            f"{surface} {{{ref.raw}}} must use worklist.<name>.current.id, .title, .status, .dir_key, .payload, or .payload.<path>"
        )
    if worklist_field in {"item_ids", "current_index", "is_exhausted"} and not worklist_rest:
        return None
    raise WorkflowValidationError(
        f"{surface} {{{ref.raw}}} must use worklist.<name>.current..., worklist.<name>.item_ids, worklist.<name>.current_index, or worklist.<name>.is_exhausted"
    )


def _validate_ctx_prompt_reference(
    ref: PlaceholderRef,
    *,
    surface: str,
    symbols: Mapping[str, Any],
) -> None:
    model_labels = {
        "input": "Input",
        "state": "State",
        "params": "Params",
    }
    qualifier_labels = {
        "request": "request",
        "input": "input",
        "state": "state",
        "params": "params",
    }
    parts = _ref_parts(ref)
    if len(parts) == 2 and parts[1] in qualifier_labels:
        raise WorkflowValidationError(
            f"{surface} {{{ref.raw}}} must qualify a {qualifier_labels[parts[1]]} field"
        )
    try:
        validated = validate_safe_ctx_reference(ref.raw)
    except ValueError as exc:
        if len(parts) == 3 and parts[1] in CTX_MODEL_ROOTS and _is_safe_field_candidate(parts[2]):
            field_name = parts[2]
            available_fields = {
                "input": symbols["input_fields"],
                "state": symbols["state_fields"],
                "params": symbols["parameter_fields"],
            }[parts[1]]
            if parts[1] == "input" and not available_fields:
                raise WorkflowValidationError(
                    f"{surface} {{{ref.raw}}} requires workflow input, but no input was provided"
                ) from exc
            if field_name not in available_fields:
                raise WorkflowValidationError(
                    f"{surface} {{{ref.raw}}} references unknown {model_labels[parts[1]]} field {field_name!r}"
                ) from exc
        raise WorkflowValidationError(f"{surface} {{{ref.raw}}} is not a supported safe dotted path") from exc

    root_name = validated[1]
    if root_name in CTX_SCALAR_FIELDS or root_name in CTX_NESTED_FIELDS:
        return None
    field_name = validated[2]
    if root_name == "input" and field_name == "message":
        return None
    available_fields = {
        "input": symbols["input_fields"],
        "state": symbols["state_fields"],
        "params": symbols["parameter_fields"],
    }[root_name]
    if root_name == "input" and not available_fields:
        raise WorkflowValidationError(f"{surface} {{{ref.raw}}} requires workflow input, but no input was provided")
    if field_name not in available_fields:
        raise WorkflowValidationError(
            f"{surface} {{{ref.raw}}} references unknown {model_labels[root_name]} field {field_name!r}"
        )
    return None


def _validate_runtime_template_reference(
    ref: PlaceholderRef,
    *,
    surface: str,
    symbols: Mapping[str, Any],
    allowed_roots: frozenset[str],
) -> str | None:
    if not ref.raw:
        return None
    if ref.root not in allowed_roots:
        raise WorkflowValidationError(f"{surface} {{{ref.raw}}} is unknown")
    if ref.root == "ctx":
        return _validate_ctx_prompt_reference(ref, surface=surface, symbols=symbols)
    if ref.root == "input":
        if not ref.path:
            return None
        return _validate_input_prompt_reference(
            ref,
            parts=_ref_parts(ref),
            surface=surface,
            symbols=symbols,
        )
    if ref.root == "params":
        if not ref.path:
            return None
        return _validate_params_prompt_reference(
            ref,
            parts=_ref_parts(ref),
            surface=surface,
            symbols=symbols,
        )
    if ref.root == "state":
        if not ref.path:
            return None
        return _validate_state_prompt_reference(
            ref,
            parts=_ref_parts(ref),
            surface=surface,
            symbols=symbols,
        )
    if ref.root == "item":
        return _validate_item_prompt_reference(
            ref,
            surface=surface,
            symbols=symbols,
            second=ref.path[0] if ref.path else "",
            rest=list(ref.path[1:]),
        )
    if ref.root == "worklist":
        return _validate_worklist_prompt_reference(
            ref,
            surface=surface,
            symbols=symbols,
            worklist_name=ref.path[0] if ref.path else "",
            rest=list(ref.path[1:]),
        )
    if ref.root == "branch":
        _validate_branch_or_fan_in_prompt_reference(ref, symbols=symbols)
        return None
    if ref.root == "fan_in":
        _validate_branch_or_fan_in_prompt_reference(ref, symbols=symbols)
        return None
    return None


def _resolve_placeholder_ref(
    ref: PlaceholderRef,
    context: Any,
    *,
    placeholder_label: str,
) -> Any:
    if not ref.raw:
        return ""
    if ref.root == "ctx":
        return _resolve_ctx_placeholder(ref, context, placeholder_label=placeholder_label)
    if ref.root == "task_id":
        current: Any = context.task_id
    elif ref.root == "run_id":
        current = context.run_id
    elif ref.root == "workflow_name":
        current = context.workflow_name
    elif ref.root == "task_folder":
        current = context.task_folder
    elif ref.root == "workflow_folder":
        current = context.workflow_folder
    elif ref.root == "run_folder":
        current = context.run_folder
    elif ref.root == "package_folder":
        current = context.package_folder
    elif ref.root == "root":
        current = context.root
    elif ref.root == "request_file":
        current = context.request_file
    elif ref.root == "params":
        current = context.params
    elif ref.root == "workflow_params":
        current = context.workflow_params
    elif ref.root == "input":
        if ref.path:
            return _resolve_input_placeholder(ref, context, placeholder_label=placeholder_label)
        current = context.input
    elif ref.root == "state":
        current = context.state
    elif ref.root == "item":
        return _resolve_item_placeholder(ref, context, placeholder_label=placeholder_label)
    elif ref.root == "worklist":
        return _resolve_worklist_placeholder(ref, context, placeholder_label=placeholder_label)
    elif ref.root == "branch":
        if getattr(context, "_branch", None) is None:
            return "{" + ref.raw + "}"
        current = context.branch
    elif ref.root == "fan_in":
        if getattr(context, "_fan_in", None) is None:
            return "{" + ref.raw + "}"
        current = context.fan_in
    else:
        return ""
    for part in ref.path:
        if current is None:
            return ""
        if isinstance(current, Mapping):
            current = current.get(part, "")
        else:
            current = getattr(current, part, "")
    return "" if current is None else current


def _resolve_input_placeholder(
    ref: PlaceholderRef,
    context: Any,
    *,
    placeholder_label: str,
) -> Any:
    parts = _ref_parts(ref)
    if len(parts) < 2:
        return context.input
    if parts[1] != "message" and context.input_fields is None:
        raise WorkflowExecutionError(
            f"{placeholder_label} {{{ref.raw}}} requires workflow input, but no input was provided"
        )
    current: Any = context.input
    for part in parts[1:]:
        if current is None:
            return ""
        if isinstance(current, Mapping):
            if part not in current:
                raise WorkflowExecutionError(
                    f"{placeholder_label} {{{ref.raw}}} references unknown input field {part!r}"
                )
            current = current[part]
            continue
        try:
            current = getattr(current, part)
        except AttributeError as exc:
            raise WorkflowExecutionError(
                f"{placeholder_label} {{{ref.raw}}} references unknown input field {part!r}"
            ) from exc
    return "" if current is None else current


def _resolve_ctx_placeholder(
    ref: PlaceholderRef,
    context: Any,
    *,
    placeholder_label: str,
) -> Any:
    try:
        parts = validate_safe_ctx_reference(ref.raw)
    except ValueError as exc:
        raise WorkflowExecutionError(
            f"{placeholder_label} {{{ref.raw}}} is not a supported safe dotted path"
        ) from exc
    view = _PromptContextView(context)
    root_name = parts[1]
    if root_name in CTX_MODEL_ROOTS:
        field_name = parts[2]
        if root_name == "input" and field_name != "message" and context.input_fields is None:
            raise WorkflowExecutionError(
                f"ctx.{root_name}.{field_name} requires workflow input, but no input was provided"
            )
        current = getattr(view, root_name)
        if current is None:
            raise WorkflowExecutionError(
                f"{placeholder_label} {{{ref.raw}}} requires an available runtime value before {field_name!r}"
            )
        try:
            return _lookup_runtime_value(current, field_name)
        except (AttributeError, KeyError, TypeError) as exc:
            raise WorkflowExecutionError(
                f"{placeholder_label} {{{ref.raw}}} references unknown runtime field {field_name!r}"
            ) from exc
    current: Any = view
    for part in parts[1:]:
        current = _lookup_runtime_value(current, part)
    return current


def _resolve_item_placeholder(
    ref: PlaceholderRef,
    context: Any,
    *,
    placeholder_label: str,
) -> Any:
    active_worklist = getattr(context, "_active_worklist", None)
    try:
        current = context.item
    except WorkflowExecutionError as exc:
        if isinstance(active_worklist, str) and active_worklist:
            raise WorkflowExecutionError(
                f"{placeholder_label} {{{ref.raw}}} could not load active worklist {active_worklist!r}: {exc}"
            ) from exc
        raise WorkflowExecutionError(
            f"{placeholder_label} {{{ref.raw}}} could not resolve an active scoped work item: {exc}"
        ) from exc
    if current is None:
        raise WorkflowExecutionError(
            f"{placeholder_label} {{{ref.raw}}} requires an active scoped work item"
        )
    return _resolve_work_item_path(
        current,
        context=context,
        ref=ref,
        parts=list(ref.path),
        placeholder_label=placeholder_label,
        worklist_name=active_worklist if isinstance(active_worklist, str) else None,
    )


def _resolve_worklist_placeholder(
    ref: PlaceholderRef,
    context: Any,
    *,
    placeholder_label: str,
) -> Any:
    parts = _ref_parts(ref)
    if len(parts) < 2 or not parts[1]:
        raise WorkflowExecutionError(
            f"{placeholder_label} {{{ref.raw}}} must specify a declared worklist name"
        )
    worklist_name = parts[1]
    try:
        selection = context.ensure_selection(worklist_name)
    except WorkflowExecutionError as exc:
        raise WorkflowExecutionError(
            f"{placeholder_label} {{{ref.raw}}} could not load worklist {worklist_name!r}: {exc}"
        ) from exc
    remaining = list(parts[2:])
    if not remaining:
        return selection
    field_name, *rest = remaining
    if field_name == "current":
        current = selection.current
        if current is None:
            raise WorkflowExecutionError(
                f"{placeholder_label} {{{ref.raw}}} requires a current item on worklist {worklist_name!r}"
            )
        return _resolve_work_item_path(
            current,
            context=context,
            ref=ref,
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
        ref=ref,
        parts=remaining,
        placeholder_label=placeholder_label,
        payload_path=None,
        worklist_name=worklist_name,
    )


def _resolve_work_item_path(
    item: Any,
    *,
    context: Any,
    ref: PlaceholderRef,
    parts: list[str],
    placeholder_label: str,
    worklist_name: str | None,
) -> Any:
    if not parts:
        return item
    field_name, *rest = parts
    if field_name == "payload":
        payload = _work_item_payload_root(item)
        if not rest:
            return payload
        return _resolve_runtime_path(
            payload,
            ref=ref,
            parts=rest,
            placeholder_label=placeholder_label,
            payload_path=[],
            worklist_name=worklist_name,
        )
    if field_name == "state":
        try:
            item_state = context.item_state
        except WorkflowExecutionError as exc:
            suffix = f" on worklist {worklist_name!r}" if worklist_name else ""
            raise WorkflowExecutionError(
                f"{placeholder_label} {{{ref.raw}}} could not resolve active item state{suffix}: {exc}"
            ) from exc
        if not rest:
            return item_state
        return _resolve_runtime_path(
            item_state,
            ref=ref,
            parts=rest,
            placeholder_label=placeholder_label,
            payload_path=None,
            worklist_name=worklist_name,
        )
    if field_name in {"id", "title", "status", "dir_key"}:
        value = _work_item_field(item, field_name)
        if not rest:
            return value
        return _resolve_runtime_path(
            value,
            ref=ref,
            parts=rest,
            placeholder_label=placeholder_label,
            payload_path=None,
            worklist_name=worklist_name,
        )
    suffix = f" on worklist {worklist_name!r}" if worklist_name else ""
    raise WorkflowExecutionError(
        f"{placeholder_label} {{{ref.raw}}} references unsupported work item field {field_name!r}{suffix}"
    )


def _resolve_runtime_path(
    current: Any,
    *,
    ref: PlaceholderRef,
    parts: list[str],
    placeholder_label: str,
    payload_path: list[str] | None,
    worklist_name: str | None = None,
) -> Any:
    value = current
    traversed = list(payload_path or [])
    suffix = f" on worklist {worklist_name!r}" if worklist_name else ""
    for part in parts:
        if value is None:
            if payload_path is not None:
                missing_path = ".".join((*traversed, part))
                raise WorkflowExecutionError(
                    f"{placeholder_label} {{{ref.raw}}} references missing payload path {missing_path!r}{suffix}"
                )
            raise WorkflowExecutionError(
                f"{placeholder_label} {{{ref.raw}}} requires an available runtime value before {part!r}{suffix}"
            )
        try:
            value = _lookup_runtime_value(value, part)
        except (AttributeError, KeyError, TypeError) as exc:
            if payload_path is not None:
                missing_path = ".".join((*traversed, part))
                raise WorkflowExecutionError(
                    f"{placeholder_label} {{{ref.raw}}} references missing payload path {missing_path!r}{suffix}"
                ) from exc
            raise WorkflowExecutionError(
                f"{placeholder_label} {{{ref.raw}}} references unknown runtime field {part!r}{suffix}"
            ) from exc
        if payload_path is not None:
            traversed.append(part)
    return value


def _render_prompt_value(value: Any, *, ref: PlaceholderRef, placeholder_label: str) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool, Path)):
        return str(value)
    raise WorkflowExecutionError(
        f"{placeholder_label} {{{ref.raw}}} resolved to a non-scalar value"
    )


def _lookup_runtime_value(current: Any, part: str) -> Any:
    if isinstance(current, Mapping):
        if part not in current:
            raise KeyError(part)
        return current[part]
    if not hasattr(current, part):
        raise AttributeError(part)
    return getattr(current, part)


def _work_item_field(item: Any, field_name: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(field_name)
    return getattr(item, field_name, None)


def _work_item_payload_root(item: Any) -> Any:
    payload = _work_item_field(item, "payload")
    if not isinstance(payload, Mapping):
        return payload
    envelope_fields = {"id", "title", "status", "dir_key"}
    if "payload" in payload and envelope_fields.intersection(payload.keys()):
        return payload["payload"]
    return payload


class _PromptContextView:
    def __init__(self, context: Any) -> None:
        self._context = context

    @property
    def message(self) -> Any:
        return self._context.message

    @property
    def request(self) -> Any:
        return self._context.request

    @property
    def request_file(self) -> Any:
        return self._context.request_file

    @property
    def input(self) -> Any:
        return self._context.input

    @property
    def state(self) -> Any:
        return self._context.state

    @property
    def params(self) -> Any:
        return self._context.params

    @property
    def task_id(self) -> Any:
        return self._context.task_id

    @property
    def run_id(self) -> Any:
        return self._context.run_id

    @property
    def workflow_name(self) -> Any:
        return self._context.workflow_name

    @property
    def task_folder(self) -> Any:
        return self._context.task_folder

    @property
    def workflow_folder(self) -> Any:
        return self._context.workflow_folder

    @property
    def run_folder(self) -> Any:
        return self._context.run_folder

    @property
    def package_folder(self) -> Any:
        return self._context.package_folder

    @property
    def root(self) -> Any:
        return self._context.root

    @property
    def run(self) -> Any:
        return type("RunView", (), {"id": self._context.run_id, "folder": self._context.run_folder})()

    @property
    def workflow(self) -> Any:
        return type(
            "WorkflowView",
            (),
            {"name": self._context.workflow_name, "folder": self._context.workflow_folder},
        )()


def _placeholder_ref(expression: str, *, source: str) -> PlaceholderRef:
    raw = expression.strip()
    if not raw:
        return PlaceholderRef(raw="", root="", path=(), source=source)
    root, *path = raw.split(".")
    return PlaceholderRef(raw=raw, root=root, path=tuple(path), source=source)


def _ref_parts(ref: PlaceholderRef) -> tuple[str, ...]:
    if not ref.raw:
        return ()
    return (ref.root, *ref.path)


def _is_safe_field_candidate(segment: str) -> bool:
    return (
        bool(segment)
        and not segment.startswith("_")
        and "__" not in segment
        and not any(character.isspace() for character in segment)
        and not any(character in _FORBIDDEN_CTX_SEGMENT_CHARS for character in segment)
    )


def _validate_branch_placeholder_reference(reference: str, *, step_name: str, allowed: bool) -> bool:
    from .branch_groups.validation import validate_branch_placeholder_reference

    return validate_branch_placeholder_reference(reference, step_name=step_name, allowed=allowed)


def _validate_fan_in_placeholder_reference(reference: str, *, step_name: str, allowed: bool) -> bool:
    from .branch_groups.validation import validate_fan_in_placeholder_reference

    return validate_fan_in_placeholder_reference(reference, step_name=step_name, allowed=allowed)


def _reject_ctx_placeholders_in_artifact_template(template: str) -> None:
    for ref in parse_placeholders(template, source="artifact_template"):
        if ref.root == "ctx":
            raise WorkflowExecutionError(
                "ctx.* placeholders are only supported in prompts and workflow-step messages, not artifact paths"
            )


_SIMPLE_PROMPT_SPECIAL_ERRORS = {
    "message": lambda surface: f"{surface} {{message}} is unknown; use {{ctx.message}}",
    "ctx": lambda surface: f"{surface} {{ctx}} must qualify a runtime context field",
}

_SIMPLE_ROOT_VALIDATORS = {
    "params": _validate_params_prompt_reference,
    "self": _validate_self_prompt_reference,
    "state": _validate_state_prompt_reference,
    "input": _validate_input_prompt_reference,
    "run": _validate_run_prompt_reference,
    "workflow": _validate_workflow_prompt_reference,
    "item": _validate_item_root_prompt_reference,
    "worklist": _validate_worklist_root_prompt_reference,
}


__all__ = [
    "PlaceholderRef",
    "SIMPLE_CONTEXT_BARE_NAMES",
    "parse_placeholders",
    "render_runtime_template",
    "render_placeholder_ref",
    "render_template_with_refs",
    "resolve_artifact_template",
    "validate_placeholder_ref",
]
