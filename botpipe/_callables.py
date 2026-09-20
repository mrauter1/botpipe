"""A deterministic, identity-preserving graph of executable callables.

The graph retains callable objects for source inspection, but never walks a
bound receiver or callable-instance state.  Consumers serialize the shallow
node metadata and hash the complete graph once.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from functools import partial
from types import CodeType, ModuleType
from typing import Any

_SDK_MODULES = {
    "botpipe.runtime",
    "botpipe.sessions",
    "botpipe.prompts",
    "botpipe.artifacts",
    "botpipe.worklists",
}


@dataclass(frozen=True)
class CallableBinding:
    label: str
    value: Any
    required: bool = True
    kind: str = "data"


@dataclass(frozen=True)
class CallableEdge:
    label: str
    target: int


@dataclass(frozen=True)
class CallableNode:
    ordinal: int
    kind: str
    value: Any
    reference: str | None = None
    bindings: tuple[CallableBinding, ...] = ()
    edges: tuple[CallableEdge, ...] = ()
    source_targets: tuple[Any, ...] = ()
    boundary_targets: tuple[Any, ...] = ()


@dataclass(frozen=True)
class CallableGraph:
    root: int
    nodes: tuple[CallableNode, ...]

    @property
    def source_targets(self) -> tuple[Any, ...]:
        return _ordered_targets(self.nodes, "source_targets")

    @property
    def boundary_targets(self) -> tuple[Any, ...]:
        result: list[Any] = []
        seen_targets: set[int] = set()
        seen_nodes: set[int] = set()
        pending = [self.root]
        while pending:
            ordinal = pending.pop()
            if ordinal in seen_nodes:
                continue
            seen_nodes.add(ordinal)
            node = self.nodes[ordinal]
            for target in node.boundary_targets:
                marker = id(target)
                if marker not in seen_targets:
                    seen_targets.add(marker)
                    result.append(target)
            owned_edges = {
                "workflow": {"callable"},
                "partial": {edge.label for edge in node.edges},
                "method": {"callable", "owner"},
                "decorated": {"wrapped"},
                "instance": {"implementation"},
            }.get(node.kind, set())
            pending.extend(
                edge.target
                for edge in reversed(node.edges)
                if edge.label in owned_edges
            )
        return tuple(result)


def _ordered_targets(
    nodes: tuple[CallableNode, ...], field_name: str
) -> tuple[Any, ...]:
    result: list[Any] = []
    seen: set[int] = set()
    for node in nodes:
        for target in getattr(node, field_name):
            marker = id(target)
            if marker not in seen:
                seen.add(marker)
                result.append(target)
    return tuple(result)


def _referenced_names(code: CodeType) -> set[str]:
    names = set(code.co_names)
    for value in code.co_consts:
        if isinstance(value, CodeType):
            names.update(_referenced_names(value))
    return names


def _reference(value: Any) -> str:
    return f"{value.__module__}:{value.__qualname__}"


def _method_candidates(member: Any) -> tuple[Any, ...]:
    if inspect.isfunction(member):
        return (member,)
    if isinstance(member, (staticmethod, classmethod)):
        return (member.__func__,)
    if isinstance(member, property):
        return tuple(
            method
            for method in (member.fget, member.fset, member.fdel)
            if method is not None
        )
    return ()


@dataclass
class _NodeBuilder:
    value: Any
    strict_defaults: bool = False
    kind: str = ""
    reference: str | None = None
    bindings: list[CallableBinding] = field(default_factory=list)
    edges: list[CallableEdge] = field(default_factory=list)
    source_targets: tuple[Any, ...] = ()
    boundary_targets: tuple[Any, ...] = ()


def describe_callable(value: Any) -> CallableGraph:
    """Describe *value* as one rooted, edge-labelled callable graph."""

    nodes: list[_NodeBuilder] = []
    ordinals: dict[int, int] = {}
    pending: list[int] = []

    def strict_edge_labels(node: _NodeBuilder) -> set[str]:
        if node.kind == "partial":
            return {item.label for item in node.edges}
        labels = {
            "workflow": {"callable"},
            "method": {"callable", "owner"},
            "decorated": {"wrapped"},
            "class": {item.label for item in node.edges},
            "instance": {"implementation"},
        }.get(node.kind, set())
        if node.kind in {"function", "decorated"}:
            labels = labels | {
                item.label
                for item in node.edges
                if item.label.startswith(("default:", "kwdefault:"))
            }
        return labels

    def require_defaults(ordinal: int) -> None:
        upgrades = [ordinal]
        while upgrades:
            current = upgrades.pop()
            node = nodes[current]
            if node.strict_defaults:
                continue
            node.strict_defaults = True
            for index, binding in enumerate(node.bindings):
                if binding.label.startswith(("default:", "kwdefault:")):
                    node.bindings[index] = CallableBinding(
                        binding.label, binding.value, True, binding.kind
                    )
            labels = strict_edge_labels(node)
            upgrades.extend(
                item.target for item in reversed(node.edges) if item.label in labels
            )

    def edge(
        node: _NodeBuilder, label: str, target: Any, *, strict: bool = False
    ) -> None:
        node.edges.append(CallableEdge(label, visit(target, strict=strict)))

    def binding_or_edge(
        node: _NodeBuilder,
        label: str,
        bound: Any,
        *,
        required: bool,
        capture_callable_value: bool = False,
        expand_type: bool = False,
    ) -> None:
        if isinstance(bound, type) and not expand_type:
            node.bindings.append(CallableBinding(label, bound, required, "type"))
        elif callable(bound):
            edge(node, label, bound, strict=required)
            if capture_callable_value:
                node.bindings.append(CallableBinding(label, bound, required))
        else:
            node.bindings.append(CallableBinding(label, bound, required))

    def function_details(node: _NodeBuilder, function: Any) -> None:
        for index, bound in enumerate(function.__defaults__ or ()):
            binding_or_edge(
                node,
                f"default:{index}",
                bound,
                required=node.strict_defaults,
                capture_callable_value=True,
            )
        for name, bound in (function.__kwdefaults__ or {}).items():
            binding_or_edge(
                node,
                f"kwdefault:{name}",
                bound,
                required=node.strict_defaults,
                capture_callable_value=True,
            )

        namespace = function.__globals__
        for name in sorted(_referenced_names(function.__code__)):
            if name not in namespace:
                continue
            bound = namespace[name]
            if isinstance(bound, type):
                node.bindings.append(
                    CallableBinding(f"global:{name}", bound, False, "type")
                )
            elif callable(bound):
                if (
                    inspect.isfunction(bound)
                    and getattr(bound, "__module__", "") in _SDK_MODULES
                    and not _is_workflow(bound)
                ):
                    continue
                edge(node, f"global:{name}", bound)
            elif type(bound) in (str, int, float, bool, tuple) or bound is None:
                node.bindings.append(CallableBinding(f"global:{name}", bound, False))

        for name, cell in zip(
            function.__code__.co_freevars, function.__closure__ or ()
        ):
            try:
                bound = cell.cell_contents
            except ValueError:
                continue
            if isinstance(bound, type):
                node.bindings.append(
                    CallableBinding(f"closure:{name}", bound, False, "type")
                )
            elif callable(bound):
                edge(node, f"closure:{name}", bound)
            elif type(bound) in (str, int, float, bool, tuple):
                node.bindings.append(CallableBinding(f"closure:{name}", bound, False))

    def class_details(node: _NodeBuilder, cls: type) -> None:
        metaclass = type(cls)
        node.source_targets = (cls,)
        node.boundary_targets = (cls,) if metaclass is type else (cls, metaclass)
        for base_index, base in enumerate(cls.__bases__):
            if base is not object:
                edge(
                    node,
                    f"base:{base_index}",
                    base,
                    strict=node.strict_defaults,
                )
        for name, member in sorted(vars(cls).items()):
            for method_index, method in enumerate(_method_candidates(member)):
                edge(
                    node,
                    f"member:{name}:{method_index}",
                    method,
                    strict=node.strict_defaults,
                )
        # Treat a custom metaclass as an ordinary graph node. Reading type(cls)
        # and raw class dictionaries does not invoke its hooks or constructors.
        if metaclass is not type:
            edge(node, "metaclass", metaclass, strict=node.strict_defaults)

    def visit(current: Any, *, strict: bool = False) -> int:
        marker = id(current)
        existing = ordinals.get(marker)
        if existing is not None:
            if strict:
                require_defaults(existing)
            return existing

        ordinal = len(nodes)
        ordinals[marker] = ordinal
        nodes.append(_NodeBuilder(current, strict_defaults=strict))
        pending.append(ordinal)
        return ordinal

    def expand(ordinal: int) -> None:
        node = nodes[ordinal]
        current = node.value
        if _is_workflow(current):
            node.kind = "workflow"
            edge(
                node,
                "callable",
                vars(current)["fn"],
                strict=node.strict_defaults,
            )
        elif isinstance(current, partial):
            node.kind = "partial"
            edge(node, "callable", current.func, strict=True)
            for index, bound in enumerate(current.args):
                binding_or_edge(
                    node,
                    f"argument:{index}",
                    bound,
                    required=True,
                    capture_callable_value=True,
                    expand_type=True,
                )
            for name, bound in (current.keywords or {}).items():
                binding_or_edge(
                    node,
                    f"keyword:{name}",
                    bound,
                    required=True,
                    capture_callable_value=True,
                    expand_type=True,
                )
        elif inspect.ismethod(current):
            node.kind = "method"
            edge(node, "callable", current.__func__, strict=node.strict_defaults)
            owner = (
                current.__self__
                if isinstance(current.__self__, type)
                else type(current.__self__)
            )
            edge(node, "owner", owner, strict=node.strict_defaults)
        elif inspect.isfunction(current):
            wrapped = vars(current).get("__wrapped__")
            node.kind = "decorated" if callable(wrapped) else "function"
            node.source_targets = (current,)
            node.boundary_targets = (current,)
            if callable(wrapped):
                edge(node, "wrapped", wrapped, strict=node.strict_defaults)
            function_details(node, current)
        elif inspect.isbuiltin(current):
            node.kind = "builtin"
            receiver = getattr(current, "__self__", None)
            owner = None
            if receiver is not None and not isinstance(receiver, ModuleType):
                owner = receiver if isinstance(receiver, type) else type(receiver)
            node.reference = (
                f"{_reference(owner)}.{current.__name__}"
                if owner is not None
                else f"{getattr(current, '__module__', 'builtins')}:{current.__name__}"
            )
        elif inspect.ismethoddescriptor(current) and hasattr(current, "__objclass__"):
            node.kind = "method_descriptor"
            node.reference = f"{_reference(current.__objclass__)}.{current.__name__}"
        elif inspect.isclass(current):
            if current.__module__ == "builtins":
                node.kind = "builtin_type"
                node.reference = _reference(current)
            else:
                node.kind = "class"
                class_details(node, current)
        elif callable(current):
            node.kind = "instance"
            edge(
                node,
                "implementation",
                type(current),
                strict=node.strict_defaults,
            )
        else:
            raise TypeError(
                f"Unsupported callable type {type(current).__module__}."
                f"{type(current).__qualname__}"
            )

    root = visit(value, strict=True)
    expanded = 0
    while expanded < len(pending):
        expand(pending[expanded])
        expanded += 1
    frozen = tuple(
        CallableNode(
            ordinal=index,
            kind=node.kind,
            value=node.value,
            reference=node.reference,
            bindings=tuple(node.bindings),
            edges=tuple(node.edges),
            source_targets=node.source_targets,
            boundary_targets=node.boundary_targets,
        )
        for index, node in enumerate(nodes)
    )
    return CallableGraph(root=root, nodes=frozen)


def _is_workflow(value: Any) -> bool:
    return (
        type(value).__module__ == "botpipe.runtime"
        and type(value).__name__ == "Workflow"
        and "fn" in vars(value)
    )


__all__ = [
    "CallableBinding",
    "CallableEdge",
    "CallableGraph",
    "CallableNode",
    "describe_callable",
]
