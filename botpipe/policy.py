"""Provider-neutral execution policy.

Adapters reject constraints their CLI cannot enforce instead of copying them
into metadata and pretending they were applied.
"""

from __future__ import annotations

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
        payload = self.to_dict(exclude_none=False)
        for field in fields(self):
            value = getattr(other, field.name)
            if value is not None:
                payload[field.name] = value
        if other.sandbox_mode == SandboxMode.READ_ONLY and other.allow_write is None:
            payload["allow_write"] = ()
        if other.sandbox_mode == SandboxMode.DANGER_FULL_ACCESS:
            if other.allow_write is None:
                payload["allow_write"] = ()
            if other.network is None:
                payload["network"] = NetworkMode.FULL
                payload["network_domains"] = ()
        if (
            other.network in (NetworkMode.FULL, NetworkMode.NONE)
            and other.network_domains is None
        ):
            payload["network_domains"] = ()
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
    "PermissionMode",
    "Policy",
    "PolicyInput",
    "ProviderName",
    "ReasoningSummary",
    "SandboxMode",
]
