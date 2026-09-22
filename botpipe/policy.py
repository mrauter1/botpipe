"""Provider-neutral execution policy.

Adapters reject constraints their CLI cannot enforce instead of copying them
into metadata and pretending they were applied.
"""

from __future__ import annotations

import os
import math
from dataclasses import dataclass, fields
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence


class _ValueEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ProviderName(_ValueEnum):
    CODEX = "codex"
    CLAUDE = "claude"
    PI = "pi"
    JEV = "jev"


class OperationKind(_ValueEnum):
    """The effect contract selected for one provider turn."""

    GENERATE = "generate"
    QUERY = "query"
    RUN = "run"


class ModelEffort(_ValueEnum):
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class ModelVerbosity(_ValueEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReasoningSummary(_ValueEnum):
    AUTO = "auto"
    CONCISE = "concise"
    DETAILED = "detailed"
    NONE = "none"


class SandboxMode(_ValueEnum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    DANGER_FULL_ACCESS = "danger_full_access"


class NetworkMode(_ValueEnum):
    FULL = "full"
    LIMITED = "limited"
    NONE = "none"


class PermissionMode(_ValueEnum):
    ASK = "ask"
    AUTO_EDIT = "auto_edit"
    FULL_AUTO_SANDBOXED = "full_auto_sandboxed"
    FULL_AUTO_UNSANDBOXED = "full_auto_unsandboxed"
    DENY_ALL = "deny_all"


def _enum(value: Any, kind: type[_ValueEnum], name: str) -> _ValueEnum | None:
    if value is None or isinstance(value, kind):
        return value
    if isinstance(value, str):
        try:
            return kind(value)
        except ValueError as exc:
            raise ValueError(f"invalid {name}: {value!r}") from exc
    raise TypeError(f"{name} must be {kind.__name__}, a valid string, or None")


def _strings(value: Any, name: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    values: Sequence[Any] = (value,) if isinstance(value, (str, Path)) else value
    if isinstance(values, (bytes, bytearray)) or not isinstance(values, Sequence):
        raise TypeError(f"{name} must be a path/string or a sequence of them")
    result: list[str] = []
    for item in values:
        if not isinstance(item, (str, Path)):
            raise TypeError(f"{name} entries must be strings or Paths")
        text = str(item).strip()
        if not text or "\x00" in text:
            raise ValueError(f"{name} entries must be non-empty and contain no NUL")
        if text not in result:
            result.append(text)
    return tuple(result)


def _is_within(child: str, parent: str) -> bool:
    """Conservatively compare authored path scopes without touching the filesystem."""
    if any(character in child + parent for character in "*?[]"):
        return child == parent
    child_path = Path(os.path.normpath(child))
    parent_path = Path(os.path.normpath(parent))
    if child_path.is_absolute() != parent_path.is_absolute():
        return False
    if ".." in child_path.parts or ".." in parent_path.parts:
        return child == parent
    try:
        child_path.relative_to(parent_path)
    except ValueError:
        return False
    return True


def _allowed_subset(
    child: tuple[str, ...], parent: tuple[str, ...], *, paths: bool
) -> bool:
    if paths:
        return all(any(_is_within(value, root) for root in parent) for value in child)
    return set(child).issubset(parent)


def _union(parent: tuple[str, ...], child: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*parent, *child)))


def _path_intersection(
    left: tuple[str, ...] | None, right: tuple[str, ...] | None
) -> tuple[str, ...] | None:
    """Return the narrower lexical roots common to both authority sets."""
    if left is None:
        return right
    if right is None:
        return left
    result: list[str] = []
    for first in left:
        for second in right:
            narrower = (
                first
                if _is_within(first, second)
                else second
                if _is_within(second, first)
                else None
            )
            if narrower is not None and narrower not in result:
                result.append(narrower)
    return tuple(result)


def _domain_contains(pattern: str, value: str) -> bool:
    """Conservatively compare literal and leading-wildcard host scopes."""
    if pattern == value:
        return True
    if pattern.startswith("*.") and "*" not in pattern[2:]:
        suffix = pattern[1:].lower()
        candidate = value.lower()
        return candidate.endswith(suffix) and candidate != suffix[1:]
    return False


def _domain_intersection(
    left: tuple[str, ...] | None, right: tuple[str, ...] | None
) -> tuple[str, ...] | None:
    if left is None:
        return right
    if right is None:
        return left
    result: list[str] = []
    for first in left:
        for second in right:
            narrower = (
                second
                if _domain_contains(first, second)
                else first
                if _domain_contains(second, first)
                else None
            )
            if narrower is not None and narrower not in result:
                result.append(narrower)
    return tuple(result)


def _set_intersection(
    left: tuple[str, ...] | None, right: tuple[str, ...] | None
) -> tuple[str, ...] | None:
    if left is None:
        return right
    if right is None:
        return left
    allowed = set(right)
    return tuple(value for value in left if value in allowed)


def _normalize_narrowed_sandbox(
    payload: Mapping[str, Any], sandbox_mode: SandboxMode, *, read_only: bool = False
) -> dict[str, Any]:
    """Return a policy payload made valid after explicitly narrowing its sandbox."""
    narrowed = dict(payload)
    narrowed["sandbox_mode"] = sandbox_mode
    if sandbox_mode is SandboxMode.READ_ONLY:
        narrowed["allow_write"] = ()
    if (
        narrowed.get("permission_mode")
        in (
            PermissionMode.FULL_AUTO_UNSANDBOXED,
            PermissionMode.FULL_AUTO_UNSANDBOXED.value,
        )
        and sandbox_mode is not SandboxMode.DANGER_FULL_ACCESS
    ):
        narrowed["permission_mode"] = PermissionMode.FULL_AUTO_SANDBOXED
    if read_only:
        narrowed["read_only"] = True
    return narrowed


@dataclass(frozen=True, slots=True)
class Policy:
    """Immutable policy layer. ``None`` means inherit."""

    provider: ProviderName | None = None
    model: str | None = None
    base_url: str | None = None
    model_overrides: Mapping[str, str] | None = None
    effort: ModelEffort | None = None
    verbosity: ModelVerbosity | None = None
    reasoning_summary: ReasoningSummary | None = None
    sandbox_mode: SandboxMode | None = None
    read_only: bool | None = None
    permission_mode: PermissionMode | None = None
    network: NetworkMode | None = None
    allow_read: tuple[str, ...] | None = None
    deny_read: tuple[str, ...] | None = None
    allow_write: tuple[str, ...] | None = None
    deny_write: tuple[str, ...] | None = None
    network_domains: tuple[str, ...] | None = None
    deny_network_domains: tuple[str, ...] | None = None
    allow_local_binding: bool | None = None
    allow_permissions: tuple[str, ...] | None = None
    ask_permissions: tuple[str, ...] | None = None
    deny_permissions: tuple[str, ...] | None = None
    timeout: float | None = None

    def __post_init__(self) -> None:
        enum_fields = {
            "provider": ProviderName,
            "effort": ModelEffort,
            "verbosity": ModelVerbosity,
            "reasoning_summary": ReasoningSummary,
            "sandbox_mode": SandboxMode,
            "permission_mode": PermissionMode,
            "network": NetworkMode,
        }
        for name, kind in enum_fields.items():
            object.__setattr__(self, name, _enum(getattr(self, name), kind, name))
        for name in (
            "allow_read",
            "deny_read",
            "allow_write",
            "deny_write",
            "network_domains",
            "deny_network_domains",
            "allow_permissions",
            "ask_permissions",
            "deny_permissions",
        ):
            object.__setattr__(self, name, _strings(getattr(self, name), name))
        if self.base_url is not None and (
            not isinstance(self.base_url, str) or not self.base_url.strip()
        ):
            raise ValueError("base_url must be a non-empty string")
        if self.model_overrides is not None:
            if not isinstance(self.model_overrides, Mapping):
                raise TypeError("model_overrides must be a mapping")
            if any(not str(key).strip() for key in self.model_overrides):
                raise ValueError("model_overrides keys must be non-empty")
            object.__setattr__(
                self,
                "model_overrides",
                MappingProxyType(
                    {
                        str(key): str(value)
                        for key, value in self.model_overrides.items()
                    }
                ),
            )
        if self.model is not None and (
            not isinstance(self.model, str) or not self.model.strip()
        ):
            raise ValueError("model must be a non-empty string")
        if self.timeout is not None:
            if isinstance(self.timeout, bool) or not isinstance(
                self.timeout, (int, float)
            ):
                raise TypeError("timeout must be a number or None")
            if self.timeout <= 0:
                raise ValueError("timeout must be greater than zero")
            if not math.isfinite(float(self.timeout)):
                raise ValueError("timeout must be finite")
        if self.allow_local_binding is not None and not isinstance(
            self.allow_local_binding, bool
        ):
            raise TypeError("allow_local_binding must be a bool or None")
        if self.read_only is not None and not isinstance(self.read_only, bool):
            raise TypeError("read_only must be a bool or None")
        if self.read_only:
            if self.sandbox_mode not in (None, SandboxMode.READ_ONLY):
                raise ValueError("read_only conflicts with sandbox_mode")
            object.__setattr__(self, "sandbox_mode", SandboxMode.READ_ONLY)
        if (
            self.permission_mode == PermissionMode.FULL_AUTO_UNSANDBOXED
            and self.sandbox_mode is None
        ):
            object.__setattr__(self, "sandbox_mode", SandboxMode.DANGER_FULL_ACCESS)
        if self.network == NetworkMode.LIMITED and not self.network_domains:
            raise ValueError("limited network requires network_domains")
        for domain in (self.network_domains or ()) + (self.deny_network_domains or ()):
            if "://" in domain or "/" in domain:
                raise ValueError(
                    f"network domain must be a hostname pattern, not {domain!r}"
                )
        if (
            self.network in (NetworkMode.FULL, NetworkMode.NONE)
            and self.network_domains
        ):
            raise ValueError("network_domains may only be used with limited network")
        if self.sandbox_mode == SandboxMode.READ_ONLY and self.allow_write:
            raise ValueError("read-only sandbox cannot have allow_write paths")
        if (
            self.permission_mode == PermissionMode.FULL_AUTO_UNSANDBOXED
            and self.sandbox_mode not in (None, SandboxMode.DANGER_FULL_ACCESS)
        ):
            raise ValueError("full_auto_unsandboxed requires danger_full_access")
        if (
            self.permission_mode == PermissionMode.FULL_AUTO_SANDBOXED
            and self.sandbox_mode == SandboxMode.DANGER_FULL_ACCESS
        ):
            raise ValueError("full_auto_sandboxed cannot use danger_full_access")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "Policy":
        if value is None:
            return cls()
        if not isinstance(value, Mapping):
            raise TypeError("policy must be a mapping")
        known = {field.name for field in fields(cls)}
        extra = set(value) - known
        if extra:
            raise ValueError(f"unknown policy fields: {', '.join(sorted(extra))}")
        return cls(**dict(value))

    def to_dict(self, *, exclude_none: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field in fields(self):
            value = getattr(self, field.name)
            if value is None and exclude_none:
                continue
            if isinstance(value, Enum):
                value = value.value
            elif isinstance(value, tuple):
                value = list(value)
            elif isinstance(value, Mapping):
                value = dict(value)
            result[field.name] = value
        return result

    def merged(self, override: "Policy | Mapping[str, Any] | None") -> "Policy":
        other = override if isinstance(override, Policy) else Policy.from_dict(override)
        sandbox_rank = {
            SandboxMode.READ_ONLY: 0,
            SandboxMode.WORKSPACE_WRITE: 1,
            SandboxMode.DANGER_FULL_ACCESS: 2,
        }
        network_rank = {NetworkMode.NONE: 0, NetworkMode.LIMITED: 1, NetworkMode.FULL: 2}
        permission_rank = {
            PermissionMode.DENY_ALL: 0,
            PermissionMode.ASK: 1,
            PermissionMode.AUTO_EDIT: 2,
            PermissionMode.FULL_AUTO_SANDBOXED: 3,
            PermissionMode.FULL_AUTO_UNSANDBOXED: 4,
        }
        for name, ranks in (
            ("sandbox_mode", sandbox_rank),
            ("network", network_rank),
            ("permission_mode", permission_rank),
        ):
            parent_value = getattr(self, name)
            child_value = getattr(other, name)
            if (
                parent_value is not None
                and child_value is not None
                and ranks[child_value] > ranks[parent_value]
            ):
                raise ValueError(
                    f"policy override cannot broaden {name} from "
                    f"{parent_value.value!r} to {child_value.value!r}"
                )
        if self.allow_local_binding is False and other.allow_local_binding is True:
            raise ValueError("policy override cannot enable local binding")
        if (
            self.timeout is not None
            and other.timeout is not None
            and other.timeout > self.timeout
        ):
            raise ValueError("policy override cannot increase timeout")
        for name, paths in (
            ("allow_read", True),
            ("allow_write", True),
            ("network_domains", False),
            ("allow_permissions", False),
            ("ask_permissions", False),
        ):
            parent_values = getattr(self, name)
            child_values = getattr(other, name)
            if (
                parent_values is not None
                and child_values is not None
                and not _allowed_subset(child_values, parent_values, paths=paths)
            ):
                raise ValueError(f"policy override cannot broaden {name}")
        payload = self.to_dict(exclude_none=False)
        for field in fields(self):
            value = getattr(other, field.name)
            if value is not None:
                payload[field.name] = value
        for name in (
            "deny_read",
            "deny_write",
            "deny_network_domains",
            "deny_permissions",
        ):
            parent_values = getattr(self, name)
            child_values = getattr(other, name)
            if parent_values is not None and child_values is not None:
                payload[name] = _union(parent_values, child_values)
        if other.sandbox_mode == SandboxMode.READ_ONLY and other.allow_write is None:
            payload["allow_write"] = ()
        if other.sandbox_mode == SandboxMode.DANGER_FULL_ACCESS:
            if other.network is None:
                # A danger-full-access sandbox does not implicitly widen an
                # inherited network ceiling.
                if self.network is None:
                    payload["network"] = NetworkMode.FULL
                    payload["network_domains"] = ()
        if (
            other.network in (NetworkMode.FULL, NetworkMode.NONE)
            and other.network_domains is None
        ):
            payload["network_domains"] = ()
        return Policy(**payload)

    def intersect(self, ceiling: "Policy | Mapping[str, Any] | None") -> "Policy":
        """Apply current deployment authority to a previously resolved policy.

        This differs from :meth:`merged`: a saved request must retain its
        model/provider choices while every effect-bearing field becomes the
        intersection of the saved authority and the current deployment
        ceiling. Disjoint scopes close to the empty set rather than silently
        selecting either side.
        """
        other = ceiling if isinstance(ceiling, Policy) else Policy.from_dict(ceiling)
        saved = self.effective()
        sandbox_rank = {
            SandboxMode.READ_ONLY: 0,
            SandboxMode.WORKSPACE_WRITE: 1,
            SandboxMode.DANGER_FULL_ACCESS: 2,
        }
        network_rank = {
            NetworkMode.NONE: 0,
            NetworkMode.LIMITED: 1,
            NetworkMode.FULL: 2,
        }
        permission_rank = {
            PermissionMode.DENY_ALL: 0,
            PermissionMode.ASK: 1,
            PermissionMode.AUTO_EDIT: 2,
            PermissionMode.FULL_AUTO_SANDBOXED: 3,
            PermissionMode.FULL_AUTO_UNSANDBOXED: 4,
        }

        payload = saved.to_dict(exclude_none=False)
        narrowed_sandbox = (
            min(
                (saved.sandbox_mode, other.sandbox_mode),
                key=sandbox_rank.__getitem__,
            )
            if other.sandbox_mode is not None
            else saved.sandbox_mode
        )
        payload["permission_mode"] = (
            min(
                (saved.permission_mode, other.permission_mode),
                key=permission_rank.__getitem__,
            )
            if other.permission_mode is not None
            else saved.permission_mode
        )
        network = (
            min((saved.network, other.network), key=network_rank.__getitem__)
            if other.network is not None
            else saved.network
        )
        domains: tuple[str, ...] | None = None
        if network is NetworkMode.LIMITED:
            saved_domains = (
                saved.network_domains
                if saved.network is NetworkMode.LIMITED
                else None
            )
            current_domains = (
                other.network_domains
                if other.network is NetworkMode.LIMITED
                else None
            )
            domains = _domain_intersection(saved_domains, current_domains)
            if not domains:
                network = NetworkMode.NONE
                domains = ()
        elif network in (NetworkMode.NONE, NetworkMode.FULL):
            domains = saved.network_domains if other.network is None else ()
        payload["network"] = network
        payload["network_domains"] = domains

        payload["allow_read"] = _path_intersection(
            saved.allow_read, other.allow_read
        )
        payload["allow_write"] = _path_intersection(
            saved.allow_write, other.allow_write
        )
        payload = _normalize_narrowed_sandbox(payload, narrowed_sandbox)
        for name in ("allow_permissions", "ask_permissions"):
            payload[name] = _set_intersection(
                getattr(saved, name), getattr(other, name)
            )
        for name in (
            "deny_read",
            "deny_write",
            "deny_network_domains",
            "deny_permissions",
        ):
            saved_values = getattr(saved, name)
            other_values = getattr(other, name)
            payload[name] = (
                None
                if saved_values is None and other_values is None
                else _union(saved_values or (), other_values or ())
            )
        payload["allow_local_binding"] = (
            bool(saved.allow_local_binding and other.allow_local_binding)
            if other.allow_local_binding is not None
            else saved.allow_local_binding
        )
        if saved.timeout is None:
            payload["timeout"] = other.timeout
        elif other.timeout is None:
            payload["timeout"] = saved.timeout
        else:
            payload["timeout"] = min(saved.timeout, other.timeout)
        payload["read_only"] = saved.read_only
        return Policy(**payload)

    def restrict_read_only(self) -> "Policy":
        """Return this policy narrowed to a read-only sandbox.

        Unattended execution remains unattended, but loses the unsandboxed
        grant that is incompatible with a read-only sandbox. All other limits
        are retained verbatim.
        """
        payload = _normalize_narrowed_sandbox(
            self.to_dict(exclude_none=False),
            SandboxMode.READ_ONLY,
            read_only=True,
        )
        return Policy(**payload)

    @staticmethod
    def resolve(
        base: "Policy | Mapping[str, Any] | None" = None,
        override: "Policy | Mapping[str, Any] | None" = None,
    ) -> "Policy":
        resolved_base = base if isinstance(base, Policy) else Policy.from_dict(base)
        return resolved_base.merged(override)

    def effective(self) -> "Policy":
        defaults = Policy(
            sandbox_mode=SandboxMode.WORKSPACE_WRITE,
            permission_mode=PermissionMode.ASK,
            network=NetworkMode.NONE,
            allow_read=(".",),
            allow_write=(".",),
            allow_local_binding=False,
        )
        payload = defaults.to_dict(exclude_none=False)
        for field in fields(self):
            value = getattr(self, field.name)
            if value is not None:
                payload[field.name] = value
        if (
            payload["sandbox_mode"]
            in (SandboxMode.READ_ONLY, SandboxMode.READ_ONLY.value)
            and self.allow_write is None
        ):
            payload["allow_write"] = ()
        if payload["sandbox_mode"] in (
            SandboxMode.DANGER_FULL_ACCESS,
            SandboxMode.DANGER_FULL_ACCESS.value,
        ):
            if self.allow_write is None:
                payload["allow_write"] = ()
            if self.network is None:
                payload["network"] = NetworkMode.FULL
                payload["network_domains"] = ()
        return Policy(**payload)


PolicyInput = Policy | Mapping[str, Any] | None

__all__ = [
    "ModelEffort",
    "ModelVerbosity",
    "NetworkMode",
    "OperationKind",
    "PermissionMode",
    "Policy",
    "PolicyInput",
    "ProviderName",
    "ReasoningSummary",
    "SandboxMode",
]
