"""Small execution ceilings shared by workflow scopes and provider calls."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import Enum
from typing import Any


class _ValueEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ProviderName(_ValueEnum):
    CODEX = "codex"


class ModelEffort(_ValueEnum):
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class SandboxMode(_ValueEnum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    DANGER_FULL_ACCESS = "danger_full_access"


class NetworkMode(_ValueEnum):
    FULL = "full"
    NONE = "none"


_SANDBOX_NAMES = {
    "read-only": SandboxMode.READ_ONLY,
    "workspace-write": SandboxMode.WORKSPACE_WRITE,
    "full-access": SandboxMode.DANGER_FULL_ACCESS,
    "danger-full-access": SandboxMode.DANGER_FULL_ACCESS,
}
_SANDBOX_RANK = {value: index for index, value in enumerate(SandboxMode)}


@dataclass(frozen=True, slots=True)
class Policy:
    """An immutable scope ceiling; unset fields inherit without adding a ceiling."""

    model: str | None = None
    effort: str | None = None
    sandbox_mode: SandboxMode | None = None
    network: NetworkMode | None = None
    timeout: float | None = None

    def __post_init__(self) -> None:
        sandbox = self.sandbox_mode
        if sandbox is not None:
            sandbox = _SANDBOX_NAMES.get(str(sandbox), sandbox)
            object.__setattr__(self, "sandbox_mode", SandboxMode(sandbox))
        network = self.network
        if type(network) is bool:
            network = NetworkMode.FULL if network else NetworkMode.NONE
        if network is not None:
            object.__setattr__(self, "network", NetworkMode(network))
        for name in ("model", "effort"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a nonempty string")
        if self.timeout is not None and (
            isinstance(self.timeout, bool)
            or not isinstance(self.timeout, (int, float))
            or not math.isfinite(self.timeout)
            or self.timeout <= 0
        ):
            raise ValueError("timeout must be finite and greater than zero")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> Policy:
        if value is None:
            return cls()
        if not isinstance(value, Mapping):
            raise TypeError("policy must be a mapping")
        data = dict(value)
        if "sandbox" in data:
            if "sandbox_mode" in data:
                raise ValueError("use only one of sandbox and sandbox_mode")
            data["sandbox_mode"] = data.pop("sandbox")
        unknown = data.keys() - {field.name for field in fields(cls)}
        if unknown:
            raise ValueError(f"unknown policy fields: {', '.join(sorted(unknown))}")
        return cls(**data)

    def to_dict(self, *, exclude_none: bool = True) -> dict[str, Any]:
        return {
            field.name: value.value if isinstance(value, Enum) else value
            for field in fields(self)
            if (value := getattr(self, field.name)) is not None or not exclude_none
        }

    def merged(self, override: Policy | Mapping[str, Any] | None) -> Policy:
        other = override if isinstance(override, Policy) else Policy.from_dict(override)
        if (
            self.sandbox_mode is not None
            and other.sandbox_mode is not None
            and _SANDBOX_RANK[other.sandbox_mode] > _SANDBOX_RANK[self.sandbox_mode]
        ):
            raise ValueError("sandbox cannot widen the enclosing policy")
        if self.network is NetworkMode.NONE and other.network is NetworkMode.FULL:
            raise ValueError("network cannot widen the enclosing policy")
        return Policy(**{**self.to_dict(), **other.to_dict()})

    @staticmethod
    def resolve(
        base: Policy | Mapping[str, Any] | None = None,
        override: Policy | Mapping[str, Any] | None = None,
    ) -> Policy:
        return (base if isinstance(base, Policy) else Policy.from_dict(base)).merged(
            override
        )

    def effective(self) -> Policy:
        data = self.to_dict()
        data.setdefault("sandbox_mode", SandboxMode.WORKSPACE_WRITE)
        data.setdefault("network", NetworkMode.NONE)
        return Policy(**data)


PolicyInput = Policy | Mapping[str, Any] | None
__all__ = [
    "ModelEffort",
    "NetworkMode",
    "Policy",
    "PolicyInput",
    "ProviderName",
    "SandboxMode",
]
