"""Shared public policy facade for Autoloop."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import Any

from autoloop.core.provider_policy import (
    ProviderPolicy,
    ProviderPolicyOverride,
    SYSTEM_DEFAULT_PROVIDER_POLICY,
    merge_provider_policies,
)


class _PolicyEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ProviderName(_PolicyEnum):
    CODEX = "codex"
    CLAUDE = "claude"


class ModelEffort(_PolicyEnum):
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class ModelVerbosity(_PolicyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReasoningSummary(_PolicyEnum):
    AUTO = "auto"
    CONCISE = "concise"
    DETAILED = "detailed"
    NONE = "none"


class SandboxMode(_PolicyEnum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    DANGER_FULL_ACCESS = "danger_full_access"


class NetworkMode(_PolicyEnum):
    FULL = "full"
    LIMITED = "limited"
    NONE = "none"


class PermissionMode(_PolicyEnum):
    ASK = "ask"
    AUTO_EDIT = "auto_edit"
    FULL_AUTO_SANDBOXED = "full_auto_sandboxed"
    FULL_AUTO_UNSANDBOXED = "full_auto_unsandboxed"
    DENY_ALL = "deny_all"


def _policy_enum_value(
    value: object,
    *,
    enum_cls: type[_PolicyEnum],
    field_name: str,
) -> str | None:
    if value is None:
        return None
    if isinstance(value, enum_cls):
        return value.value
    raise TypeError(
        f"{field_name} must use {enum_cls.__name__} members, not {value!r}. "
        f"Use {enum_cls.__name__}.<NAME>."
    )


def _policy_string_item(value: object, *, field_name: str) -> str:
    item = value if isinstance(value, str) else str(value)
    normalized = item.strip()
    if not normalized:
        raise ValueError(f"{field_name} entries must be non-empty strings")
    return normalized


def _policy_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, bytes):
        raise TypeError(f"{field_name} must be a string, Path, or sequence of strings/Paths")
    if isinstance(value, (str, Path)):
        values: Sequence[object] = (value,)
    elif isinstance(value, Sequence):
        values = value
    else:
        raise TypeError(f"{field_name} must be a string, Path, or sequence of strings/Paths")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        if isinstance(item, bytes):
            raise TypeError(f"{field_name} entries must be strings or Paths, not bytes")
        if not isinstance(item, (str, Path)):
            raise TypeError(f"{field_name} entries must be strings or Paths, not {type(item).__name__}")
        entry = _policy_string_item(item, field_name=field_name)
        if entry in seen:
            continue
        seen.add(entry)
        normalized.append(entry)
    return tuple(normalized)


def _policy_optional_tuple(value: object, *, field_name: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    return _policy_tuple(value, field_name=field_name)


def _policy_string_mapping(value: object, *, field_name: str) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping of string keys to string values")
    normalized: dict[str, str] = {}
    for key, item in value.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            raise ValueError(f"{field_name} keys must be non-empty strings")
        normalized[normalized_key] = str(item)
    return normalized


def _policy_section(payload: dict[str, object], *keys: str) -> dict[str, object]:
    current = payload
    for key in keys:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    return current


class Policy:
    """Flat inheriting policy layer for Autoloop.

    Policy stores only supplied fields. Unset fields inherit from the effective
    base policy at resolution time, or from the explicit base= policy when provided.
    Fixed option fields use Autoloop policy enums rather than raw strings.
    network_domains implies limited network mode. allow_write implies workspace_write
    mode unless read_only=True or sandbox_mode=SandboxMode.READ_ONLY is set, which is
    invalid with allow_write. Dangerous access uses the same flat API:
    sandbox_mode=SandboxMode.DANGER_FULL_ACCESS and
    permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED internally enable the
    dangerous-bypass latch required by the nested core policy schema.
    """

    __slots__ = ("base", "_authored")

    def __init__(
        self,
        *,
        base: Policy | ProviderPolicy | None = None,
        model: str | None = None,
        provider: ProviderName | None = None,
        base_url: str | None = None,
        effort: ModelEffort | None = None,
        verbosity: ModelVerbosity | None = None,
        reasoning_summary: ReasoningSummary | None = None,
        model_overrides: Mapping[str, str] | None = None,
        sandbox_mode: SandboxMode | None = None,
        read_only: bool = False,
        allow_read: str | Path | Sequence[str | Path] | None = None,
        deny_read: str | Path | Sequence[str | Path] | None = None,
        allow_write: str | Path | Sequence[str | Path] | None = None,
        deny_write: str | Path | Sequence[str | Path] | None = None,
        network: NetworkMode | None = None,
        network_domains: str | Sequence[str] | None = None,
        deny_network_domains: str | Sequence[str] | None = None,
        allow_local_binding: bool | None = None,
        permission_mode: PermissionMode | None = None,
        allow_permissions: str | Sequence[str] | None = None,
        ask_permissions: str | Sequence[str] | None = None,
        deny_permissions: str | Sequence[str] | None = None,
    ) -> None:
        if base is not None and not isinstance(base, (Policy, ProviderPolicy)):
            raise TypeError("base must be a Policy, ProviderPolicy, or None")
        if model is not None and not isinstance(model, str):
            raise TypeError("model must be a string or None")
        if base_url is not None and not isinstance(base_url, str):
            raise TypeError("base_url must be a string or None")
        if not isinstance(read_only, bool):
            raise TypeError("read_only must be a boolean")
        if allow_local_binding is not None and not isinstance(allow_local_binding, bool):
            raise TypeError("allow_local_binding must be a boolean or None")

        authored: dict[str, object] = {}
        if model is not None:
            authored["model"] = model
        provider_value = _policy_enum_value(provider, enum_cls=ProviderName, field_name="provider")
        if provider_value is not None:
            authored["provider"] = provider_value
        if base_url is not None:
            authored["base_url"] = base_url
        effort_value = _policy_enum_value(effort, enum_cls=ModelEffort, field_name="effort")
        if effort_value is not None:
            authored["effort"] = effort_value
        verbosity_value = _policy_enum_value(verbosity, enum_cls=ModelVerbosity, field_name="verbosity")
        if verbosity_value is not None:
            authored["verbosity"] = verbosity_value
        reasoning_summary_value = _policy_enum_value(
            reasoning_summary,
            enum_cls=ReasoningSummary,
            field_name="reasoning_summary",
        )
        if reasoning_summary_value is not None:
            authored["reasoning_summary"] = reasoning_summary_value
        model_overrides_value = _policy_string_mapping(model_overrides, field_name="model_overrides")
        if model_overrides_value is not None:
            authored["model_overrides"] = model_overrides_value

        sandbox_mode_value = _policy_enum_value(sandbox_mode, enum_cls=SandboxMode, field_name="sandbox_mode")
        if sandbox_mode_value is not None:
            authored["sandbox_mode"] = sandbox_mode_value
        if read_only:
            authored["read_only"] = True
        allow_read_value = _policy_optional_tuple(allow_read, field_name="allow_read")
        if allow_read_value is not None:
            authored["allow_read"] = allow_read_value
        deny_read_value = _policy_optional_tuple(deny_read, field_name="deny_read")
        if deny_read_value is not None:
            authored["deny_read"] = deny_read_value
        allow_write_value = _policy_optional_tuple(allow_write, field_name="allow_write")
        if allow_write_value is not None:
            authored["allow_write"] = allow_write_value
        deny_write_value = _policy_optional_tuple(deny_write, field_name="deny_write")
        if deny_write_value is not None:
            authored["deny_write"] = deny_write_value

        network_value = _policy_enum_value(network, enum_cls=NetworkMode, field_name="network")
        if network_value is not None:
            authored["network"] = network_value
        network_domains_value = _policy_optional_tuple(network_domains, field_name="network_domains")
        if network_domains_value is not None:
            authored["network_domains"] = network_domains_value
        deny_network_domains_value = _policy_optional_tuple(
            deny_network_domains,
            field_name="deny_network_domains",
        )
        if deny_network_domains_value is not None:
            authored["deny_network_domains"] = deny_network_domains_value
        if allow_local_binding is not None:
            authored["allow_local_binding"] = allow_local_binding

        permission_mode_value = _policy_enum_value(
            permission_mode,
            enum_cls=PermissionMode,
            field_name="permission_mode",
        )
        if permission_mode_value is not None:
            authored["permission_mode"] = permission_mode_value
        allow_permissions_value = _policy_optional_tuple(
            allow_permissions,
            field_name="allow_permissions",
        )
        if allow_permissions_value is not None:
            authored["allow_permissions"] = allow_permissions_value
        ask_permissions_value = _policy_optional_tuple(ask_permissions, field_name="ask_permissions")
        if ask_permissions_value is not None:
            authored["ask_permissions"] = ask_permissions_value
        deny_permissions_value = _policy_optional_tuple(deny_permissions, field_name="deny_permissions")
        if deny_permissions_value is not None:
            authored["deny_permissions"] = deny_permissions_value

        object.__setattr__(self, "base", base)
        object.__setattr__(self, "_authored", authored)
        _policy_layer_to_override(self)

    def resolve(
        self,
        base: ProviderPolicy | None = None,
    ) -> ProviderPolicy:
        return resolve_policy_layer(base or SYSTEM_DEFAULT_PROVIDER_POLICY, self)

    def to_layer_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        for key, value in self._authored.items():
            if isinstance(value, dict):
                payload[key] = dict(value)
            elif isinstance(value, tuple):
                payload[key] = list(value)
            else:
                payload[key] = value
        if isinstance(self.base, Policy):
            payload["base"] = {
                "kind": "policy",
                "payload": self.base.to_layer_payload(),
            }
        elif isinstance(self.base, ProviderPolicy):
            payload["base"] = {
                "kind": "provider_policy",
                "payload": self.base.model_dump(mode="json", warnings=False),
            }
        return payload

    def __repr__(self) -> str:
        fields = ", ".join(f"{key}={value!r}" for key, value in self._authored.items())
        if self.base is not None:
            if fields:
                fields = f"base={self.base!r}, {fields}"
            else:
                fields = f"base={self.base!r}"
        return f"Policy({fields})"


PolicyInput = Policy | ProviderPolicy | ProviderPolicyOverride | None


def _policy_layer_to_override(policy: Policy) -> ProviderPolicyOverride:
    authored = policy._authored
    payload: dict[str, object] = {}

    if any(
        key in authored
        for key in (
            "model",
            "provider",
            "base_url",
            "effort",
            "verbosity",
            "reasoning_summary",
            "model_overrides",
        )
    ):
        model_payload = _policy_section(payload, "model")
        if "model" in authored:
            model_payload["default"] = authored["model"]
        if "provider" in authored:
            model_payload["provider"] = authored["provider"]
        if "base_url" in authored:
            model_payload["base_url"] = authored["base_url"]
        if "effort" in authored:
            model_payload["effort"] = authored["effort"]
        if "verbosity" in authored:
            model_payload["verbosity"] = authored["verbosity"]
        if "reasoning_summary" in authored:
            model_payload["reasoning_summary"] = authored["reasoning_summary"]
        if "model_overrides" in authored:
            model_payload["overrides"] = authored["model_overrides"]

    explicit_sandbox_mode = authored.get("sandbox_mode")
    read_only = authored.get("read_only") is True
    allow_write_authored = "allow_write" in authored
    effective_sandbox_mode = explicit_sandbox_mode
    if read_only:
        if effective_sandbox_mode is None:
            effective_sandbox_mode = SandboxMode.READ_ONLY.value
        elif effective_sandbox_mode != SandboxMode.READ_ONLY.value:
            raise ValueError("read_only=True is incompatible with sandbox_mode other than SandboxMode.READ_ONLY")
    if effective_sandbox_mode == SandboxMode.READ_ONLY.value and allow_write_authored:
        raise ValueError("allow_write cannot be set when sandbox mode is read-only")
    if not read_only and effective_sandbox_mode is None and allow_write_authored:
        effective_sandbox_mode = SandboxMode.WORKSPACE_WRITE.value

    permission_mode = authored.get("permission_mode")
    if permission_mode == PermissionMode.FULL_AUTO_UNSANDBOXED.value:
        if effective_sandbox_mode in {
            SandboxMode.READ_ONLY.value,
            SandboxMode.WORKSPACE_WRITE.value,
        }:
            raise ValueError(
                "permission_mode=PermissionMode.FULL_AUTO_UNSANDBOXED requires "
                "sandbox_mode=SandboxMode.DANGER_FULL_ACCESS"
            )
        if effective_sandbox_mode is None:
            effective_sandbox_mode = SandboxMode.DANGER_FULL_ACCESS.value

    if (
        effective_sandbox_mode == SandboxMode.DANGER_FULL_ACCESS.value
        and permission_mode == PermissionMode.FULL_AUTO_SANDBOXED.value
    ):
        raise ValueError(
            "sandbox_mode=SandboxMode.DANGER_FULL_ACCESS is incompatible with "
            "permission_mode=PermissionMode.FULL_AUTO_SANDBOXED"
        )

    network = authored.get("network")
    network_domains = authored.get("network_domains")
    if "network_domains" in authored and network_domains == ():
        raise ValueError("network_domains must not be empty when provided")
    effective_network = network
    if effective_network is None and network_domains is not None:
        effective_network = NetworkMode.LIMITED.value
    if effective_network == NetworkMode.LIMITED.value and not network_domains:
        raise ValueError("network=NetworkMode.LIMITED requires non-empty network_domains")
    if effective_network in {NetworkMode.FULL.value, NetworkMode.NONE.value} and network_domains:
        raise ValueError(
            f"network={effective_network!r} cannot be combined with network_domains"
        )

    dangerous_access = (
        effective_sandbox_mode == SandboxMode.DANGER_FULL_ACCESS.value
        or permission_mode == PermissionMode.FULL_AUTO_UNSANDBOXED.value
    )

    if any(key in authored for key in ("permission_mode", "allow_permissions", "ask_permissions", "deny_permissions")) or dangerous_access:
        permissions_payload = _policy_section(payload, "permissions")
        if permission_mode is not None:
            permissions_payload["mode"] = permission_mode
        if "allow_permissions" in authored:
            permissions_payload["allow"] = authored["allow_permissions"]
        if "ask_permissions" in authored:
            permissions_payload["ask"] = authored["ask_permissions"]
        if "deny_permissions" in authored:
            permissions_payload["deny"] = authored["deny_permissions"]
        if dangerous_access:
            permissions_payload["allow_dangerous_bypass"] = True

    if effective_sandbox_mode is not None:
        _policy_section(payload, "sandbox")["mode"] = effective_sandbox_mode

    if any(key in authored for key in ("allow_read", "deny_read", "allow_write", "deny_write")) or effective_sandbox_mode == SandboxMode.READ_ONLY.value:
        filesystem_payload = _policy_section(payload, "sandbox", "workspace", "filesystem")
        if "allow_read" in authored:
            filesystem_payload["allow_read"] = authored["allow_read"]
        if "deny_read" in authored:
            filesystem_payload["deny_read"] = authored["deny_read"]
        if "allow_write" in authored:
            filesystem_payload["allow_write"] = authored["allow_write"]
        if "deny_write" in authored:
            filesystem_payload["deny_write"] = authored["deny_write"]
        if effective_sandbox_mode == SandboxMode.READ_ONLY.value:
            filesystem_payload["allow_write"] = ()

    if any(key in authored for key in ("network", "network_domains", "deny_network_domains", "allow_local_binding")):
        network_payload = _policy_section(payload, "sandbox", "workspace", "network")
        if effective_network == NetworkMode.FULL.value:
            network_payload["enabled"] = True
            network_payload["mode"] = NetworkMode.FULL.value
            network_payload["allow_domains"] = ()
        elif effective_network == NetworkMode.NONE.value:
            network_payload["enabled"] = False
            network_payload["mode"] = NetworkMode.NONE.value
            network_payload["allow_domains"] = ()
        elif effective_network == NetworkMode.LIMITED.value:
            network_payload["enabled"] = True
            network_payload["mode"] = NetworkMode.LIMITED.value
            network_payload["allow_domains"] = network_domains
        if "deny_network_domains" in authored:
            network_payload["deny_domains"] = authored["deny_network_domains"]
        if "allow_local_binding" in authored:
            network_payload["allow_local_binding"] = authored["allow_local_binding"]

    return ProviderPolicyOverride.model_validate(payload)


def _resolve_policy_with_base(
    policy: Policy,
    base: ProviderPolicy,
    *,
    seen: set[int],
) -> ProviderPolicy:
    policy_id = id(policy)
    if policy_id in seen:
        raise ValueError("cyclic Policy(base=...) references are not allowed")
    seen.add(policy_id)
    try:
        effective_base = base
        if isinstance(policy.base, Policy):
            effective_base = _resolve_policy_with_base(policy.base, base, seen=seen)
        elif isinstance(policy.base, ProviderPolicy):
            effective_base = policy.base
        return merge_provider_policies(effective_base, _policy_layer_to_override(policy))
    finally:
        seen.remove(policy_id)


def resolve_policy_layer(
    base: ProviderPolicy,
    layer: PolicyInput,
) -> ProviderPolicy:
    if layer is None:
        return base
    if isinstance(layer, Policy):
        return _resolve_policy_with_base(layer, base, seen=set())
    if isinstance(layer, ProviderPolicyOverride):
        return merge_provider_policies(base, layer)
    if isinstance(layer, ProviderPolicy):
        return merge_provider_policies(base, layer)
    raise TypeError("policy layer must be a Policy, ProviderPolicy, ProviderPolicyOverride, or None")


__all__ = [
    "Policy",
    "PolicyInput",
    "ProviderName",
    "ModelEffort",
    "ModelVerbosity",
    "ReasoningSummary",
    "SandboxMode",
    "NetworkMode",
    "PermissionMode",
    "resolve_policy_layer",
]
